/* Network Insights: one shared selection drives every panel. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const config = JSON.parse($('ni-config').textContent);
  $('ni-cities').dataset.multiselectPresetValues = (config.main_cities || []).join('|');
  $('ni-cities').dispatchEvent(new Event('multiselect:options-updated'));
  const storageKey = config.selection_storage_key;
  let savedSelection = {};
  try {
    // The page opens with the selection of the last analysis, so that analysis comes back with it; without one,
    // with the last selection.
    const analysed = storageKey ? JSON.parse(localStorage.getItem(`${storageKey}:last-analysis:selection`) || 'null') : null;
    const stored = analysed && typeof analysed === 'object' && !Array.isArray(analysed) ? analysed
      : storageKey ? JSON.parse(localStorage.getItem(storageKey) || '{}') : {};
    if (stored && typeof stored === 'object' && !Array.isArray(stored)) savedSelection = stored;
  } catch {}
  const selectionControls = ['ni-nr-mode', 'ni-technology', 'ni-group', 'ni-coverage-threshold',
    'ni-interference-threshold', 'ni-nr-coverage-threshold', 'ni-nr-interference-threshold', 'ni-grid',
    'ni-deployment-group', 'ni-sites-source', 'ni-snapshot', 'ni-overshoot', 'ni-deployment-technology',
    'ni-bandwidth-tests', 'ni-nr-duplex-split'];
  for (const id of selectionControls) {
    const control = $(id);
    const value = savedSelection.controls?.[id];
    if (value === undefined) continue;
    if (control.multiple && Array.isArray(value)) {
      for (const option of control.options) option.selected = value.includes(option.value);
      control.dispatchEvent(new Event('multiselect:options-updated'));
    } else if (control.tagName === 'SELECT') {
      if ([...control.options].some(option => option.value === String(value) && !option.disabled)) control.value = value;
    } else if (Number.isFinite(Number(value))) control.value = value;
  }
  const pendingFilterRestore = new Map(Object.entries(savedSelection.filters || {})
    .filter(([, values]) => Array.isArray(values)));
  const syncTechnologyGrouping = () => {
    const control = $('ni-group');
    // LTE+NR analyses LTE and NR in separate sections, each with its own
    // thresholds, so Technology is never a grouping and RSRP/SINR are never pooled.
    const existing = [...control.options].find(option => option.value === 'technology');
    if (existing) {
      existing.remove();
      control.dispatchEvent(new Event('multiselect:options-updated'));
    }
    const technology = $('ni-technology').value;
    document.querySelectorAll('[data-ni-radio]').forEach(label => {
      label.hidden = ![label.dataset.niRadio, 'lte_nr'].includes(technology);
    });
  };
  syncTechnologyGrouping();
  // Operator stays checked unless Vendor is checked.
  const enforceOperatorGrouping = () => {
    const control = $('ni-group');
    const option = value => [...control.options].find(item => item.value === value);
    const operator = option('operator');
    if (!operator) return;
    const required = !option('vendor')?.selected;
    const changed = operator.disabled !== required || (required && !operator.selected);
    operator.disabled = required;
    operator.dataset.disabledReason = 'Operator is required unless Vendor is selected.';
    if (required) operator.selected = true;
    // Synchronize the existing menu without rebuilding and closing it.
    if (changed) control.dispatchEvent(new Event('change', {bubbles: true}));
  };
  enforceOperatorGrouping();
  $('ni-group').addEventListener('change', enforceOperatorGrouping);
  const kinds = [['data', 'CDR Data'], ['voice', 'CDR Voice'], ['speech', 'CDR Speech']];
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, character => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[character]));
  const number = (value, digits = 1) => (value === null || value === undefined || !Number.isFinite(Number(value)) ? '—' : Number(value).toFixed(digits));
  const integer = value => (Number.isFinite(Number(value)) ? Number(value).toLocaleString('en-US') : '—');
  let analysis = null;
  // The request of the shown analysis, whose filters the scope pills of the measurement panels name.
  let analysedFilters = null;
  let analysing = 0;
  // Map payloads by `<technology>-<coverage|interference>`.
  const mapPayloads = {};
  const sections = () => analysis?.sections || (analysis ? [analysis] : []);
  const multipleSections = () => sections().length > 1;

  // The colour theme of the charts and tables, of the page and of the exports (the themes of Scoring, see
  // scoring_themes.py): the one the user chose in this workspace.
  const themes = Array.isArray(config.themes) ? config.themes : [];
  let activeTheme = themes.find(theme => theme.id === config.theme) || themes[0] || {};
  // Its colours (see network_insights_findings.js palette): the scale of the quality classes, the series of the bands.
  let themeColours = null;
  const scaleColour = (index, count) => {
    const scale = themeColours?.scale || [];
    return scale.length ? scale[Math.round((count - 1 - index) / Math.max(1, count - 1) * (scale.length - 1))] : '';
  };
  const alpha = (colour, amount) => {
    const text = String(colour || '').replace('#', '');
    if (!/^[0-9a-f]{6}$/i.test(text)) return colour;
    return `rgba(${[0, 2, 4].map(index => parseInt(text.slice(index, index + 2), 16)).join(',')},${amount})`;
  };
  const applyTheme = () => {
    const root = $('network-insights');
    root.dataset.niTheme = activeTheme.id || 'netcheck';
    // The CDFs and maps in the font and colours of the theme (dark cards in a dark theme).
    globalThis.canvasChartStyle = (config.chart_styles || {})[activeTheme.id] || null;
    globalThis.redrawCanvasCharts?.();
    const colours = window.NetworkInsightsFindings?.palette(activeTheme);
    if (!colours) return;
    themeColours = colours;
    const tokens = {surface: colours.surface, ink: colours.ink, muted: colours.muted, accent: colours.accent, soft: colours.soft,
      line: colours.line, track: colours.track, header: colours.header, 'header-text': colours.headerText,
      'row-alt': colours.rowAlt, hover: colours.hover, gain: colours.gain, loss: colours.loss};
    colours.scale.forEach((colour, index) => { tokens[`scale-${index}`] = colour; });
    colours.series.forEach((colour, index) => { tokens[`series-${index}`] = colour; });
    for (const [name, value] of Object.entries(tokens)) if (value) root.style.setProperty(`--nit-${name}`, value);
    if (colours.font) root.style.setProperty('--nit-font', colours.font);
  };

  const status = (message, tone = '') => {
    const element = $('ni-status');
    element.textContent = message;
    element.dataset.tone = tone;
  };

  // The CDRs follow the NR Mode and the Campaign (chosen by the server): the CDRs used are listed read-only,
  // by type, and follow every change of the filters (dimmed while the new ones load).
  let shownCdrs = null;
  const renderAutoCdrs = (cdrs, {loading = false} = {}) => {
    const host = $('ni-auto-cdrs');
    let title = host.querySelector(':scope > .ni-auto-cdrs-title');
    if (!title) {
      title = document.createElement('p');
      title.className = 'ni-auto-cdrs-title';
      host.prepend(title);
    }
    title.innerHTML = `<strong>CDRs used</strong> <span>${escapeHtml($('ni-nr-mode').value)} · chosen from the NR Mode and Campaign</span>`;
    // The operators out of scope in the NR Mode (the NR Modes of the Operator Maps), left out of the analysis.
    const outOfScope = globalThis.outOfScopePill?.($('ni-nr-mode').value);
    if (outOfScope) title.append(' ', outOfScope);
    if (cdrs) shownCdrs = cdrs;
    globalThis.renderAutoCdrList?.(host, cdrs || shownCdrs, {loading: loading || !cdrs});
  };
  // The server chooses the CDRs from the NR Mode and Campaign.
  const selectedDatasets = () => ({});
  const selectedValues = id => [...$(id).selectedOptions].map(option => option.value);
  // One campaign: Latest campaign (the default) and Previous campaign come first in Campaign, and follow the newest
  // campaigns; then each campaign.
  const campaignPresetOrder = (config.campaign_presets || []).map(([value]) => value);
  const campaignPresets = Object.fromEntries(config.campaign_presets || []);
  const isCampaignPreset = value => Object.prototype.hasOwnProperty.call(campaignPresets, value);
  const allSelected = id => {
    const options = [...$(id).options].filter(option => option.value);
    return options.length > 0 && options.every(option => option.selected);
  };
  // An unfiltered selector (every value or none) sends no restriction; the Campaign is sent as it is.
  const filterValues = id => (id === 'ni-campaigns' ? selectedValues(id).slice(0, 1) : allSelected(id) ? [] : selectedValues(id));
  // Campaigns as the workspace Campaign Maps show them (campaign_labels.js); the filter keeps the full value.
  const campaignLabel = (value) => (globalThis.campaignLabel ? globalThis.campaignLabel(value) : String(value ?? ''));
  // The Campaign of a selection: its Latest campaign or Previous campaign, else the newest of its campaigns that are
  // listed (a selection saved with several keeps one), else Latest campaign (also for Latest 2, 3 or 4 campaigns and
  // All available campaigns, saved before Network Insights analysed one campaign).
  const chosenCampaign = (previous, values) => campaignPresetOrder.find(value => previous.includes(value))
    ?? values.filter(value => previous.includes(value)).at(-1) ?? campaignPresetOrder[0];
  const fillCampaigns = values => {
    const control = $('ni-campaigns');
    const restored = pendingFilterRestore.get('ni-campaigns');
    pendingFilterRestore.delete('ni-campaigns');
    const chosen = chosenCampaign(restored || selectedValues('ni-campaigns'), values);
    const listed = [...campaignPresetOrder, ...values];
    // The same values and choice keep the selector as it is.
    if (control.options.length === listed.length && [...control.options].every((option, index) => option.value === listed[index])
      && control.value === chosen) return;
    const campaigns = document.createElement('optgroup');
    campaigns.label = 'Campaigns';
    campaigns.dataset.dividerBefore = 'true';
    campaigns.append(...values.map(value => new Option(campaignLabel(value), value)));
    control.replaceChildren(...campaignPresetOrder.map(value => new Option(campaignPresets[value], value)), ...(values.length ? [campaigns] : []));
    control.value = chosen;
  };
  const fillSelector = (id, values) => {
    if (id === 'ni-campaigns') { fillCampaigns(values); return; }
    const control = $(id);
    const restored = pendingFilterRestore.get(id);
    const previous = new Set(restored || selectedValues(id));
    // A first list (or a saved filter without values) starts with every value; afterwards the choice stays as the
    // user left it, also with no value checked (Select None), which does not restrict either.
    const keepAll = restored ? !restored.length : !control.options.length || allSelected(id);
    pendingFilterRestore.delete(id);
    const wasLoading = control.dataset.multiselectNoValuesLabel !== 'No values available';
    control.dataset.multiselectNoValuesLabel = 'No values available';
    const isSelected = value => keepAll || previous.has(value);
    // The same values and choices keep the selector as it is (its menu stays as the user left it).
    const current = [...control.options];
    if (!wasLoading && current.length === values.length
      && current.every((option, index) => option.value === values[index] && option.selected === isSelected(values[index]))) return;
    control.replaceChildren(...values.map(value => {
      const option = document.createElement('option');
      option.value = value;
      option.textContent = value;
      option.selected = isSelected(value);
      return option;
    }));
    control.dispatchEvent(new Event('multiselect:options-updated'));
  };

  const filterNames = ['operators', 'operator_vendors', 'vendor_operators', 'vendors', 'regions', 'clusters', 'cities', 'environments', 'campaigns'];
  const fillFilterOptions = options => {
    if (options.operators) $('ni-vendors').dataset.multiselectOperatorValues = JSON.stringify(options.operators);
    for (const field of filterNames) {
      if (Object.prototype.hasOwnProperty.call(options, field)) fillSelector(`ni-${field}`, options[field] || []);
    }
  };
  let optionsRequest = null;
  let optionsTimer = null;
  // While the combinations of some CDRs are still being read, the lists are asked for again a few times.
  let pendingTimer = null, pendingRetries = 0;
  const optionsCache = new Map();
  const cdrsCache = new Map();
  // Every filter lists the values of every CDR of the NR Mode that the other filters leave.
  const filterSelection = () => ({
    nr_mode: $('ni-nr-mode').value,
    ...Object.fromEntries(filterNames.map(field => [field, $(`ni-${field}`).options.length && !pendingFilterRestore.has(`ni-${field}`)
      ? filterValues(`ni-${field}`) : pendingFilterRestore.get(`ni-${field}`) || []])),
  });
  const loadFilterOptions = async () => {
    optionsRequest?.abort();
    const selection = filterSelection();
    const key = JSON.stringify(selection);
    const cached = optionsCache.get(key);
    if (cached) fillFilterOptions(cached);
    if (cdrsCache.has(key)) renderAutoCdrs(cdrsCache.get(key));
    if (cached && cdrsCache.has(key) && filterNames.every(field => Object.prototype.hasOwnProperty.call(cached, field))) return;
    if (!cdrsCache.has(key)) renderAutoCdrs(null, {loading: true});
    const controller = new AbortController();
    optionsRequest = controller;
    for (const field of filterNames) {
      if (cached && Object.prototype.hasOwnProperty.call(cached, field)) continue;
      const control = $(`ni-${field}`);
      // Only an empty selector says it is loading: a filled one keeps its values until the new ones arrive.
      if (control.options.length) continue;
      control.dataset.multiselectNoValuesLabel = 'Loading values…';
      const trigger = control.nextElementSibling?.querySelector('.multiselect-trigger-label');
      if (trigger) trigger.textContent = 'Loading values…';
    }
    try {
      const loadPart = async vendorOnly => {
        const response = await fetch(`/api/network-insights/filter-options${vendorOnly ? '?vendor_only=true' : ''}`, {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(selection), signal: controller.signal,
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.detail || 'Unable to load filter values.');
        if (controller.signal.aborted) return;
        if (payload.cdrs) { cdrsCache.set(key, payload.cdrs); renderAutoCdrs(payload.cdrs); }
        const merged = {...(optionsCache.get(key) || {}), ...payload.options};
        if (payload.pending) pending = true;
        else optionsCache.set(key, merged);
        fillFilterOptions(payload.options);
        refreshInventory();
      };
      let pending = false;
      // Cached dimensions render independently of the first Vendor lookup.
      const results = await Promise.allSettled([loadPart(false), loadPart(true)]);
      const failure = results.find(result => result.status === 'rejected');
      if (failure) throw failure.reason;
      clearTimeout(pendingTimer);
      if (pending && pendingRetries < 20) {
        pendingRetries += 1;
        pendingTimer = setTimeout(() => { void loadFilterOptions(); }, 4000);
      } else if (!pending) pendingRetries = 0;
    } catch (error) {
      if (error.name !== 'AbortError') {
        for (const field of filterNames) {
          if (Object.prototype.hasOwnProperty.call(optionsCache.get(key) || {}, field)) continue;
          const control = $(`ni-${field}`);
          control.dataset.multiselectNoValuesLabel = 'Unable to load values';
          control.dispatchEvent(new Event('multiselect:options-updated'));
        }
        status(error.message, 'error');
      }
    }
  };
  const scheduleFilterOptions = () => {
    clearTimeout(optionsTimer);
    optionsRequest?.abort();
    optionsTimer = setTimeout(() => { void loadFilterOptions(); }, 150);
  };

  const requestBody = (mapOperator = '') => ({
    datasets: selectedDatasets(),
    nr_mode: $('ni-nr-mode').value,
    technology: $('ni-technology').value,
    group: selectedValues('ni-group'),
    operators: filterValues('ni-operators'),
    operator_vendors: filterValues('ni-operator_vendors'),
    vendor_operators: filterValues('ni-vendor_operators'),
    vendors: filterValues('ni-vendors'),
    campaigns: filterValues('ni-campaigns'),
    regions: filterValues('ni-regions'),
    clusters: filterValues('ni-clusters'),
    cities: filterValues('ni-cities'),
    environments: filterValues('ni-environments'),
    coverage_threshold: Number($('ni-coverage-threshold').value),
    interference_threshold: Number($('ni-interference-threshold').value),
    nr_coverage_threshold: Number($('ni-nr-coverage-threshold').value),
    nr_interference_threshold: Number($('ni-nr-interference-threshold').value),
    grid_metres: Number($('ni-grid').value),
    min_samples: 3,
    map_operator: mapOperator,
    snapshot: $('ni-snapshot').value,
    overshoot_km: Number($('ni-overshoot').value) || 5,
  });

  // Modal shown while an analysis runs; Hide leaves it running in the background.
  const progress = {timer: null, started: 0};
  const showProgress = (message, title = 'Network analysis in progress') => {
    const dialog = $('ni-progress-dialog');
    $('ni-progress-title').textContent = title;
    $('ni-progress-message').textContent = message;
    progress.started = Date.now();
    const tick = () => { $('ni-progress-elapsed').textContent = `Elapsed: ${Math.floor((Date.now() - progress.started) / 1000)} s`; };
    tick();
    clearInterval(progress.timer);
    progress.timer = setInterval(tick, 1000);
    if (!dialog.open) dialog.showModal?.();
  };
  const hideProgress = () => {
    clearInterval(progress.timer);
    const dialog = $('ni-progress-dialog');
    if (dialog.open) dialog.close();
  };
  $('ni-progress-hide').onclick = hideProgress;
  $('ni-progress-dialog').addEventListener('cancel', () => clearInterval(progress.timer));

  // The last analysed request, to show its stored result again when the page
  // opens with the same selection.
  const lastAnalysisKey = storageKey ? `${storageKey}:last-analysis` : '';
  const readLastAnalysis = () => {
    try { return JSON.parse(localStorage.getItem(lastAnalysisKey) || 'null'); } catch { return null; }
  };
  const analyse = async (mapOperator = '', {cachedOnly = false} = {}) => {
    const request = ++analysing;
    const button = $('ni-analyse');
    const body = requestBody(mapOperator);
    button.disabled = true; button.classList.add('is-busy');
    if (cachedOnly) {
      status('Showing the last analysis of this selection…', 'busy');
    } else {
      status('Analysing the selected CDRs… CDRs analysed for the first time are read and prepared first.', 'busy');
      showProgress('Analysing the selected CDRs. CDRs analysed for the first time (or changed since) are read and prepared first, which can take from a few seconds to a minute or more depending on their size; after that, new filters take a few seconds and repeated analyses are immediate.');
    }
    try {
      const response = await fetch(`/api/network-insights/analysis${cachedOnly ? '?cached_only=true' : ''}`, {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
      });
      if (cachedOnly && response.status === 204) {
        // The stored result is no longer valid (the CDRs, their inputs or the app changed): the last analysis
        // runs again by itself.
        if (request === analysing) void analyse(mapOperator);
        return;
      }
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || 'Unable to analyse the selected CDRs.');
      if (request !== analysing) return;
      analysis = payload;
      analysedFilters = body;
      rememberSelection();
      try {
        if (lastAnalysisKey) {
          localStorage.setItem(lastAnalysisKey, JSON.stringify(body));
          localStorage.setItem(`${lastAnalysisKey}:selection`, JSON.stringify(savedSelection));
        }
      } catch {}
      // The filters keep the values of every CDR of the NR Mode (filter-options): the analysed CDRs follow the
      // chosen Campaign, so their own values would leave only that campaign to choose from.
      render();
      const comparison = payload.comparison ? ` Changes compare ${payload.comparison.latest} with ${payload.comparison.previous}.` : '';
      const counts = (payload.sections || [payload]).map(section =>
        `${integer(section.overview.reduce((total, row) => total + row.samples, 0))} ${section.technology_label}`).join(' and ');
      status(`Analysed ${counts} samples.${comparison}${payload.warnings.length ? ` ${payload.warnings.join(' ')}` : ''}`, payload.warnings.length ? 'warning' : 'done');
    } catch (error) {
      if (request === analysing) status(cachedOnly ? '' : error.message, cachedOnly ? '' : 'error');
    } finally {
      if (request === analysing) { button.disabled = false; button.classList.remove('is-busy'); hideProgress(); }
    }
  };
  // Opening or reloading the page with the selection of the last analysis shows
  // its stored result; a changed selection waits for Analyse Network.
  const showLastAnalysis = () => {
    const last = readLastAnalysis();
    if (!last || analysis || analysing) return;
    const comparable = body => JSON.stringify({...body, map_operator: ''});
    if (comparable(requestBody()) === comparable(last)) void analyse(last.map_operator || '', {cachedOnly: true});
  };

  // Summary Network Insights of the current selection, as PowerPoint or Word.
  document.querySelectorAll('[data-ni-export]').forEach((button) => button.addEventListener('click', async () => {
    const kind = button.dataset.niExport;
    const label = kind === 'word' ? 'Word' : 'PowerPoint';
    button.disabled = true; button.classList.add('is-busy');
    status(`Generating the Summary Network Insights ${label}… Charts and maps are rendered at full size.`, 'busy');
    showProgress(`Preparing the Summary Network Insights ${label}: the analysis of the selected CDRs, its charts and the maps of every group are rendered at full size, so it can take a minute or more. The document downloads when it is ready.`,
      `Preparing the ${label} document`);
    try {
      const response = await fetch(`/api/network-insights/export/${kind}?theme=${encodeURIComponent(activeTheme.id || '')}`, {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(requestBody(analysis?.maps?.operator || '')),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || `Unable to export the ${label} summary.`);
      }
      const disposition = response.headers.get('content-disposition') || '';
      const name = /filename\*?=(?:UTF-8'')?"?([^";]+)/i.exec(disposition)?.[1];
      const link = document.createElement('a');
      link.href = URL.createObjectURL(await response.blob());
      link.download = name ? decodeURIComponent(name) : `Summary Network Insights.${kind === 'word' ? 'docx' : 'pptx'}`;
      document.body.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(link.href), 10000);
      status(`Summary Network Insights ${label} downloaded.`, 'done');
    } catch (error) {
      status(error.message, 'error');
      hideProgress();
      globalThis.showInfoDialog?.(error.message, {tone: 'error', title: 'The document could not be generated'});
    } finally {
      button.disabled = false; button.classList.remove('is-busy');
      hideProgress();
    }
  }));

  const delta = (value, unit, betterHigher) => {
    if (value === null || value === undefined) return '';
    const improved = betterHigher ? value > 0 : value < 0;
    const sign = value > 0 ? '+' : '';
    return `<span class="ni-delta ${value === 0 ? '' : improved ? 'is-better' : 'is-worse'}">${sign}${number(value)}${unit}</span>`;
  };
  const sectionTitle = section => `<h3 class="ni-technology-title">${escapeHtml(section.technology_label)} <span>Low coverage below ${escapeHtml(section.coverage_threshold)} dBm · high interference below ${escapeHtml(section.interference_threshold)} dB</span></h3>`;
  const renderOverview = () => {
    const host = $('ni-overview');
    host.replaceChildren();
    for (const section of sections()) {
      if (multipleSections()) host.insertAdjacentHTML('beforeend', sectionTitle(section));
      renderOverviewCards(host, section);
    }
  };
  const renderOverviewCards = (host, section) => {
    for (const row of section.overview) {
      const colour = analysis.colours[row.operator] || '#6D46A8';
      const deltas = row.deltas || {};
      const card = document.createElement('article');
      card.className = 'ni-operator-card';
      card.style.setProperty('--ni-operator', colour);
      card.innerHTML = `<h3>${escapeHtml(row.operator)}</h3>
        <dl>
          <div><dt>Median RSRP</dt><dd>${number(row.rsrp_median)} dBm ${delta(deltas.rsrp_median, ' dB', true)}</dd></div>
          <div><dt>Low coverage</dt><dd>${number(row.low_coverage_share)}% ${delta(deltas.low_coverage_share, ' pp', false)}</dd></div>
          <div><dt>Median SINR</dt><dd>${number(row.sinr_median)} dB ${delta(deltas.sinr_median, ' dB', true)}</dd></div>
          <div><dt>High interference</dt><dd>${number(row.high_interference_share)}% ${delta(deltas.high_interference_share, ' pp', false)}</dd></div>
          <div><dt>Observed eNodeBs</dt><dd>${integer(row.observed_enodebs)}</dd></div>
          <div><dt>Samples</dt><dd>${integer(row.samples)}</dd></div>
        </dl>`;
      host.append(card);
    }
  };
  const classBar = classes => `<span class="ni-class-bar">${(classes || []).map((item, index, all) =>
    `<span style="width:${item.share}%;background:${scaleColour(index, all.length) || item.colour}" title="${escapeHtml(item.label)}: ${number(item.share)}%"></span>`).join('')}</span>`;
  // RF Quality: CDFs and table per technology (LTE and NR separately with LTE+NR).
  const renderRfSections = () => {
    const host = $('ni-rf-sections');
    host.innerHTML = sections().map(section => `<section class="ni-technology-section">
      ${multipleSections() ? sectionTitle(section) : ''}
      <div class="ni-chart-grid">
        <div class="ni-cdf-block"><div class="ni-chart-card"><canvas id="ni-${section.technology}-rsrp-cdf" role="img" aria-label="${escapeHtml(section.technology_label)} RSRP cumulative distribution"></canvas></div>
          ${percentileTable(`${section.technology_label} RSRP percentiles`, section.rf_rows.map(row => ({row, values: [row.rsrp_p10, row.rsrp_median, row.rsrp_p90]})), 'dBm', 1)}</div>
        <div class="ni-cdf-block"><div class="ni-chart-card"><canvas id="ni-${section.technology}-sinr-cdf" role="img" aria-label="${escapeHtml(section.technology_label)} SINR cumulative distribution"></canvas></div>
          ${percentileTable(`${section.technology_label} SINR percentiles`, section.rf_rows.map(row => ({row, values: [row.sinr_p10, row.sinr_median, row.sinr_p90]})), 'dB', 1)}</div>
      </div>
      <div class="table-wrap ni-table-wrap"><table class="ni-table">${rfTable(section)}</table></div>
    </section>`).join('');
    for (const section of sections()) {
      renderChart($(`ni-${section.technology}-rsrp-cdf`), section.charts.rsrp_cdf);
      renderChart($(`ni-${section.technology}-sinr-cdf`), section.charts.sinr_cdf);
    }
  };
  // NR quality per carrier: the NR samples of each group per NR band, their medians and quality classes.
  const renderNrBands = () => {
    const table = $('ni-nr-bands');
    const rows = analysis.nr_bands || [];
    if (!rows.length) { table.innerHTML = '<tbody><tr><td class="form-note">The selected samples measured no NR band.</td></tr></tbody>'; return; }
    table.innerHTML = `<thead><tr><th>${escapeHtml(analysis.group_label || 'All samples')}</th><th>NR band</th><th>Samples</th><th>Share of the group</th><th>Median SS-RSRP</th><th>RSRP classes</th><th>Median SS-SINR</th><th>SINR classes</th></tr></thead>
      <tbody>${rows.map(row => `<tr><td><span class="ni-swatch" style="background:${analysis.colours[row.column] || analysis.colours[row.column.split(' · ')[0]] || '#6D46A8'}"></span>${escapeHtml(row.column)}</td><td>${technologyChip('NR')} ${escapeHtml(row.band)}</td>
        <td class="num">${integer(row.samples)}</td><td><span class="ni-share"><span style="width:${row.share}%"></span></span> ${number(row.share)}%</td>
        <td class="num">${row.rsrp_median === null ? '—' : `${number(row.rsrp_median)} dBm`}</td><td>${classBar(row.rsrp_classes)}</td>
        <td class="num">${row.sinr_median === null ? '—' : `${number(row.sinr_median)} dB`}</td><td>${classBar(row.sinr_classes)}</td></tr>`).join('')}</tbody>`;
  };
  // Latency & Interactivity: a table per environment, the groups as rows and the measures as columns, each cell shaded by
  // its rank among the groups (green the best, red the worst).
  const renderInteractivity = () => {
    const host = $('ni-interactivity');
    const detail = analysis.interactivity || {};
    if (!detail.cells?.length) { host.innerHTML = '<p class="form-note">The selected CDRs have no interactivity (gaming and video chat) tests.</p>'; return; }
    const shade = (rank, of) => {
      if (!rank || !of || of < 2) return '';
      const position = (rank - 1) / (of - 1);
      const colour = position <= .5 ? alpha(themeColours?.gain || '#4CA65A', (.5 - position) * .7 + .08)
        : alpha(themeColours?.loss || '#E8414F', (position - .5) * .7 + .08);
      return ` style="background:${colour}"`;
    };
    const unit = {failed: '%', loss_share: '%', rtt_median: ' ms', rtt_p90: ' ms', jitter: ' ms'};
    host.innerHTML = `<div class="ni-interactivity-grid">${detail.environments.map(environment => {
      const cells = detail.cells.filter(cell => cell.environment === environment);
      return `<div class="ni-interactivity-card"><h4 class="ni-strip-title">${escapeHtml(environment)}</h4><div class="table-wrap ni-table-wrap"><table class="ni-table"><thead><tr><th>${escapeHtml(analysis.group_label || 'All samples')}</th><th>Tests</th>${detail.measures.map(measure => `<th>${escapeHtml(measure.label)}</th>`).join('')}</tr></thead>
        <tbody>${cells.map(cell => `<tr><td><span class="ni-swatch" style="background:${analysis.colours[cell.column] || analysis.colours[cell.column.split(' · ')[0]] || '#6D46A8'}"></span>${escapeHtml(cell.column)}</td><td class="num">${integer(cell.tests)}</td>${detail.measures.map(measure => {
          const value = cell[measure.key];
          return `<td class="num"${shade(cell[`${measure.key}_rank`], cell[`${measure.key}_of`])}>${value === null || value === undefined ? '—' : `${number(value)}${unit[measure.key] || ''}`}</td>`;
        }).join('')}</tr>`).join('')}</tbody></table></div></div>`;
    }).join('')}</div>`;
  };
  // P10, P50 and P90 of every group under its CDF: the values below which 10%, 50% and 90% of the samples fall.
  // Each group as a band from its P10 to its P90 in its colour with its median marked, on one scale for all the groups.
  const percentileTable = (title, entries, unit, digits, {heading = analysis.group_label || 'All samples', colours = analysis.colours} = {}) => {
    const known = entries.flatMap(({values}) => values).filter(value => value !== null && value !== undefined && Number.isFinite(Number(value)));
    if (!known.length) return '';
    const low = Math.min(...known);
    const high = Math.max(...known);
    const span = high - low || 1;
    const at = value => `${((Number(value) - low) / span) * 100}%`;
    const text = value => (value === null || value === undefined ? '—' : number(value, digits));
    return `<div class="ni-percentiles ni-range-chart" role="img" aria-label="${escapeHtml(title)}: P10, P50 and P90 of every group">
      <p class="ni-range-legend"><span>${escapeHtml(heading)}</span><span><i class="ni-range-key"></i>P10 to P90 · <b>|</b> P50 (${escapeHtml(unit)})</span></p>
      ${entries.map(({row, values: [p10, p50, p90]}) => {
        const colour = colours?.[row.operator] || '#6D46A8';
        const label = `${row.operator}${row.group ? ` · ${row.group}` : ''}`;
        return `<div class="ni-range-row" title="${escapeHtml(label)}: P10 ${text(p10)}, P50 ${text(p50)}, P90 ${text(p90)} ${escapeHtml(unit)}">
          <span class="ni-range-name"><span class="ni-swatch" style="background:${colour}"></span>${escapeHtml(label)}</span>
          <span class="ni-range-track">${p10 !== null && p90 !== null ? `<span class="ni-range-band" style="left:${at(p10)};width:calc(${at(p90)} - ${at(p10)});background:${alpha(colour, .35)};border-color:${colour}"></span>
            <span class="ni-range-value is-low" style="right:calc(100% - ${at(p10)})">${text(p10)}</span><span class="ni-range-value" style="left:${at(p90)}">${text(p90)}</span>` : ''}
            ${p50 !== null ? `<span class="ni-range-median" style="left:${at(p50)};background:${colour}"><b>${text(p50)}</b></span>` : ''}</span></div>`;
      }).join('')}</div>`;
  };
  const rfTable = section => {
    const grouped = Boolean(section.rf_rows.some(row => row.group));
    const measure = (value, unit) => (number(value) === '—' ? '—' : `${number(value)} ${unit}`);
    // The shares below the thresholds as bars in the loss colour of the theme, the largest of the table full.
    const largest = key => Math.max(...section.rf_rows.map(row => Number(row[key]) || 0), 0.1);
    const shareBar = (value, key) => `<span class="ni-inline-bar"><span style="width:${(Number(value) || 0) / largest(key) * 100}%"></span></span>${number(value)}%`;
    return `<thead><tr><th>${escapeHtml(analysis.group_label || 'All samples')}</th>${grouped ? `<th>${escapeHtml(analysis.group_label)}</th>` : ''}<th>Samples</th><th>${escapeHtml(section.technology_label)} RSRP samples</th><th>Median RSRP</th><th>P10 RSRP</th><th>Low coverage</th><th>RSRP classes</th><th>Median SINR</th><th>P10 SINR</th><th>High interference</th><th>SINR classes</th></tr></thead>
    <tbody>${section.rf_rows.map(row => `<tr>
      <td><span class="ni-swatch" style="background:${analysis.colours[row.operator] || '#6D46A8'}"></span>${escapeHtml(row.operator)}</td>
      ${grouped ? `<td>${escapeHtml(row.group)}</td>` : ''}
      <td class="num">${integer(row.samples)}</td><td class="num">${integer(row.rsrp_samples)}</td><td class="num">${measure(row.rsrp_median, 'dBm')}</td><td class="num">${measure(row.rsrp_p10, 'dBm')}</td>
      <td class="num">${shareBar(row.low_coverage_share, 'low_coverage_share')}</td><td>${classBar(row.rsrp_classes)}</td>
      <td class="num">${measure(row.sinr_median, 'dB')}</td><td class="num">${measure(row.sinr_p10, 'dB')}</td>
      <td class="num">${shareBar(row.high_interference_share, 'high_interference_share')}</td><td>${classBar(row.sinr_classes)}</td></tr>`).join('')}</tbody>`;
  };

  // In-chart zoom controls, as in PPT Designer: zoom out/in, level, reset
  // and pan arrows while zoomed. Dragging a rectangle also zooms.
  const panPaths = {left: 'M15 5 8 12l7 7', right: 'm9 5 7 7-7 7', up: 'M5 15 12 8l7 7', down: 'm5 9 7 7 7-7'};
  // The payload drawn on every canvas, to draw it again larger when it is double-clicked.
  const chartPayloads = new WeakMap();
  const renderChart = (canvas, payload) => {
    if (!canvas) return;
    chartPayloads.set(canvas, payload);
    globalThis.renderCanvasChart(canvas, payload);
    const card = canvas.parentElement;
    if (!card || card.querySelector(':scope > .ni-chart-zoom')) return;
    const button = (text, title, className = '') => {
      const element = document.createElement('button');
      element.type = 'button'; element.className = `ni-chart-zoom-button ${className}`.trim();
      element.title = title; element.setAttribute('aria-label', title); element.textContent = text;
      return element;
    };
    const controls = document.createElement('div');
    controls.className = 'ni-chart-zoom'; controls.setAttribute('role', 'group'); controls.setAttribute('aria-label', 'Chart zoom');
    const zoomOut = button('−', 'Zoom out');
    const level = document.createElement('output'); level.className = 'ni-chart-zoom-level';
    const zoomIn = button('+', 'Zoom in');
    const reset = button('1:1', 'Reset zoom', 'ni-chart-zoom-reset');
    controls.append(zoomOut, level, zoomIn, reset);
    const pans = Object.entries(panPaths).map(([direction, path]) => {
      const pan = button('', `Move view ${direction}`, `ni-chart-pan ni-chart-pan-${direction}`);
      pan.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${path}"/></svg>`;
      pan.onclick = event => { event.stopPropagation(); globalThis.panCanvasChart?.(canvas, direction); sync(); };
      return [direction, pan];
    });
    const sync = () => {
      const zoom = Math.max(1, Number(globalThis.getCanvasChartZoom?.(canvas)) || 1);
      level.textContent = `${Math.round(zoom * 100)}%`;
      zoomOut.disabled = reset.disabled = zoom <= 1; zoomIn.disabled = zoom >= 4;
      const state = globalThis.getCanvasChartPanState?.(canvas) || {};
      for (const [direction, pan] of pans) {
        pan.hidden = zoom <= 1;
        pan.disabled = !state[`canPan${direction[0].toUpperCase()}${direction.slice(1)}`];
      }
    };
    const apply = zoom => { globalThis.setCanvasChartZoom?.(canvas, Math.max(1, Math.min(4, zoom))); sync(); };
    zoomOut.onclick = event => { event.stopPropagation(); apply((globalThis.getCanvasChartZoom?.(canvas) || 1) - .25); };
    zoomIn.onclick = event => { event.stopPropagation(); apply((globalThis.getCanvasChartZoom?.(canvas) || 1) + .25); };
    reset.onclick = event => { event.stopPropagation(); apply(1); };
    canvas.addEventListener('designchartzoom', sync);
    canvas.addEventListener('designchartpan', sync);
    card.append(controls, ...pans.map(([, pan]) => pan));
    sync();
  };

  // A port of the server's OpenStreetMap tile geometry, used to zoom maps.
  const osmWorld = (latitude, longitude, zoom) => {
    const scale = 256 * 2 ** zoom;
    const bounded = Math.max(Math.min(latitude, 85.05112878), -85.05112878) * Math.PI / 180;
    return [(longitude + 180) / 360 * scale, (1 - Math.asinh(Math.tan(bounded)) / Math.PI) / 2 * scale];
  };
  const zoomMap = (kind, latitude, longitude) => {
    const controller = geoMaps.get($(`ni-${kind}-map`));
    if (!controller) return;
    // About 24 grid squares span the zoomed height.
    controller.showArea(longitude, latitude, Math.max(0.01, Number($('ni-grid').value) / 111_320 * 12));
    $('ni-map-note').textContent = `Zoomed to ${number(latitude, 4)}, ${number(longitude, 4)}.`;
  };
  const hotspotTable = (kind, rows, unit) => {
    if (!rows.length) return '<tbody><tr><td class="form-note">No grid square has most samples below the threshold.</td></tr></tbody>';
    return `<thead><tr><th>Area</th><th>Region</th><th>Samples</th><th>Mean</th><th>Below</th></tr></thead><tbody>${rows.map(row => `<tr>
      <td><button type="button" class="ni-zoom" data-kind="${kind}" data-latitude="${row.latitude}" data-longitude="${row.longitude}" title="Zoom the map to ${number(row.latitude, 4)}, ${number(row.longitude, 4)}">${escapeHtml(row.city || `${number(row.latitude, 3)}, ${number(row.longitude, 3)}`)}</button></td>
      <td>${escapeHtml(row.region || '—')}</td><td class="num">${integer(row.samples)}</td>
      <td class="num">${number(row.mean)} ${unit}</td><td class="num">${number(row.bad_share)}%</td></tr>`).join('')}</tbody>`;
  };
  // The inventory sites of the maps (legend entries marked with a triangle) follow the Inventory sites check.
  // Site entries of the legend show the site triangle, also in maps of analyses stored before it ('… sectors').
  const mapView = payload => {
    if (!payload || payload.type !== 'map') return payload;
    const items = (payload.legend?.items || []).map(item => !item.marker && / (sites|sectors)$/.test(String(item.label)) ? {...item, marker: 'triangle'} : item);
    const marked = {...payload, legend: {...payload.legend, items}};
    return $('ni-map-sites')?.checked !== false ? marked
      : {...marked, sectors: [], legend: {...marked.legend, items: items.filter(item => !['triangle', 'ring', 'ring-dashed'].includes(item.marker))}};
  };
  $('ni-map-sites')?.addEventListener('change', () => {
    for (const canvas of document.querySelectorAll('#network-insights canvas')) geoMaps.get(canvas)?.redraw();
  });
  // Locked, halted, disabled, planned and in-progress cells of the inventory snapshot around the weak areas.
  const stateChips = row => {
    const details = String(row.summary || '').split(' · ');
    return `<span class="ni-state-list">${(row.states || []).map((item, index) =>
      `<span class="ni-state-chip" data-state="${escapeHtml(item.state)}">${escapeHtml(details[index] || `${item.state}: ${item.cells}`)}</span>`).join('')}</span>`;
  };
  const cellStatusBlock = (radio, status) => {
    if (!status) return '';
    const dates = (status.snapshot_dates || []).join(', ') || 'its date';
    return `<section class="ni-cell-status"><h4 class="ni-subtitle">Cell status near the weak areas <span class="form-note">(sites within ${number(status.radius_km, 0)} km of the areas above)</span></h4>
      <div class="table-wrap ni-table-wrap"><table class="ni-table"><thead><tr><th>Site</th><th>Network → Host</th><th>Vendor</th><th>Flagged cells</th><th>On air</th><th>Nearest weak area</th><th>Distance km</th></tr></thead>
      <tbody>${(status.rows || []).map(row => `<tr>
        <td><button type="button" class="ni-zoom" data-kind="${radio}-${escapeHtml(row.area_kind)}" data-latitude="${row.latitude}" data-longitude="${row.longitude}" title="Zoom the ${escapeHtml(row.area_kind)} map to the site">${escapeHtml(row.site)}</button></td>
        <td>${escapeHtml(row.network)} → ${escapeHtml(row.host)}</td><td>${escapeHtml(row.vendor || '—')}</td><td>${stateChips(row)}</td>
        <td>${row.on_air ? 'Yes' : 'Not yet'}</td><td>${escapeHtml(row.area_kind === 'interference' ? 'Interference' : 'Coverage')} · ${escapeHtml(row.area)}</td>
        <td class="num">${number(row.distance_km, 2)}</td></tr>`).join('') || `<tr><td colspan="7" class="form-note">No site with locked, halted, disabled, planned or in-progress cells lies within ${number(status.radius_km, 0)} km of these areas.</td></tr>`}</tbody></table></div>
      <p class="form-note ni-note"><span>The states are those of the inventory snapshot (${escapeHtml(dates)}), not of the day of the measurements. Locked and Halted come from the administrative or OSS state and Disabled from the operational state of cells in service, which the snapshot gives for ${number(status.known_share)}% of the cells of these networks (mostly Ericsson cells); the other cells are only flagged when their status is In progress or Planned. On the maps these sites carry a ring, dashed when they are not on air yet or have planned cells.</span></p></section>`;
  };
  // Coverage and interference maps per technology, for one shared Group.
  const renderMaps = () => {
    const maps = analysis.maps;
    const selector = $('ni-map-operator');
    // Follow the displayed table order rather than the map payload's source order.
    const availableGroups = new Set(sections().flatMap(section => section.maps.operators));
    const orderedGroups = [...new Set(analysis.rf_rows.map(row => row.operator))]
      .filter(group => availableGroups.has(group));
    const displayedGroups = new Set(orderedGroups);
    orderedGroups.push(...[...availableGroups].filter(group => !displayedGroups.has(group))
      .sort((left, right) => left.localeCompare(right, undefined, {sensitivity: 'base', numeric: true})));
    selector.replaceChildren(...orderedGroups.map(operator => {
      const option = document.createElement('option'); option.value = operator; option.textContent = operator; option.selected = operator === maps.operator; return option;
    }));
    for (const key of Object.keys(mapPayloads)) delete mapPayloads[key];
    $('ni-map-sections').innerHTML = sections().map(section => {
      const radio = section.technology;
      const label = escapeHtml(section.technology_label);
      return `<section class="ni-technology-section">
        ${multipleSections() ? sectionTitle(section) : ''}
        <div class="ni-map-grid">
          <section class="ni-map-card"><h3>${label} Coverage (mean RSRP per grid square)</h3><div class="ni-chart-card ni-map-canvas"><canvas id="ni-${radio}-coverage-map" role="img" aria-label="${label} coverage map"></canvas></div>
            <h4>Weakest coverage areas</h4><div class="table-wrap ni-table-wrap ni-hotspot-wrap"><table class="ni-table ni-hotspots">${hotspotTable(`${radio}-coverage`, section.maps.coverage_hotspots, 'dBm')}</table></div></section>
          <section class="ni-map-card"><h3>${label} Interference (mean SINR per grid square)</h3><div class="ni-chart-card ni-map-canvas"><canvas id="ni-${radio}-interference-map" role="img" aria-label="${label} interference map"></canvas></div>
            <h4>Highest interference areas</h4><div class="table-wrap ni-table-wrap ni-hotspot-wrap"><table class="ni-table ni-hotspots">${hotspotTable(`${radio}-interference`, section.maps.interference_hotspots, 'dB')}</table></div></section>
        </div>
        ${cellStatusBlock(radio, section.maps.cell_status)}
      </section>`;
    }).join('');
    for (const section of sections()) {
      for (const kind of ['coverage', 'interference']) {
        const key = `${section.technology}-${kind}`;
        mapPayloads[key] = section.maps[kind];
        showMap($(`ni-${key}-map`), section.maps[kind]);
      }
    }
    $('ni-map-note').textContent = `${maps.operator} · grid ${number(maps.coverage_grid_metres, 0)} m${maps.coverage_grid_metres !== Number($('ni-grid').value) ? ' (coarsened to keep the map readable)' : ''}.`;
  };
  let clusterInventories = null;
  const renderSites = () => {
    const observed = $('ni-sites-source').value === 'observed';
    const missing = analysis?.missing_inventory_operators || [];
    $('ni-sites-pending').hidden = !observed || !missing.length;
    $('ni-sites-pending').innerHTML = missing.length
      ? `<strong>Pending input:</strong> site inventories for ${missing.map(escapeHtml).join(', ')}.` : '';
    $('ni-sites-note').hidden = !observed;
    $('ni-sites-inventory-note').hidden = observed;
    $('ni-inventory-totals').hidden = observed;
    const table = $('ni-sites-table');
    if (!observed) {
      const rows = clusterInventories?.rows || [];
      table.innerHTML = rows.length
        ? `<thead><tr><th>Operator</th><th>Inventory sites</th><th>Inventory cells</th></tr></thead><tbody>${rows.map(row => `<tr><td>${escapeHtml(row.operator)}</td><td class="num">${integer(row.sites)}</td><td class="num">${integer(row.cells)}</td></tr>`).join('')}</tbody>`
        : '<tbody><tr><td class="form-note">No supported site/cell inventory is available.</td></tr></tbody>';
      return;
    }
    if (!analysis) {
      table.innerHTML = '<tbody><tr><td class="form-note">No analysis yet.</td></tr></tbody>';
      return;
    }
    const grouped = Boolean(analysis.rf_rows.some(row => row.group));
    const technology = multipleSections();
    table.innerHTML = `<thead><tr><th>${escapeHtml(analysis.group_label || 'All samples')}</th>${grouped ? `<th>${escapeHtml(analysis.group_label)}</th>` : ''}${technology ? '<th>Technology</th>' : ''}<th>Observed eNodeBs</th><th>Observed cells</th><th>Samples</th><th>Samples per eNodeB</th></tr></thead><tbody>${analysis.rf_rows.map(row => `<tr>
      <td><span class="ni-swatch" style="background:${analysis.colours[row.operator] || '#6D46A8'}"></span>${escapeHtml(row.operator)}</td>${grouped ? `<td>${escapeHtml(row.group)}</td>` : ''}${technology ? `<td>${technologyChip(row.technology)}</td>` : ''}
      <td class="num">${integer(row.observed_enodebs)}</td><td class="num">${integer(row.observed_cells)}</td><td class="num">${integer(row.samples)}</td>
      <td class="num">${row.observed_enodebs ? number(row.samples / row.observed_enodebs) : '—'}</td></tr>`).join('')}</tbody>`;
  };
  const renderLicensed = summary => {
    const host = $('ni-licensed');
    const classes = config.band_classes || [];
    if (!summary.length) {
      host.innerHTML = `<p class="ni-pending-box"><strong>Pending input.</strong> No licensed spectrum is configured for this workspace yet. ${config.can_edit ? 'Add each Operator\'s holdings (band, duplex, class and MHz) in <a href="/workspace-config#spectrum-holdings">Workspace Config → Mappings &amp; Reference Data → Spectrum Holdings</a>.' : 'Ask an editor to add them in Workspace Config.'}</p>`;
      return;
    }
    const maximum = Math.max(...summary.map(row => row.total), 1);
    host.innerHTML = `<div class="table-wrap ni-table-wrap"><table class="ni-table"><thead><tr><th>Operator</th>${classes.map(name => `<th>${escapeHtml(name)} (MHz)</th>`).join('')}<th>Total (MHz)</th><th></th></tr></thead><tbody>${summary.map(row => `<tr>
      <td>${escapeHtml(row.operator)}</td>${classes.map(name => `<td class="num">${number(row[name])}</td>`).join('')}<td class="num"><strong>${number(row.total)}</strong></td>
      <td class="ni-spectrum-bar-cell"><span class="ni-class-bar ni-spectrum-bar" style="width:${row.total / maximum * 100}%">${classes.map((name, index) => `<span style="width:${row.total ? row[name] / row.total * 100 : 0}%;background:${themeColours?.series?.[[2, 0, 4][index]] || ['#5C940D', '#1C7ED6', '#C2255C'][index]}" title="${escapeHtml(name)}: ${number(row[name])} MHz"></span>`).join('')}</span></td></tr>`).join('')}</tbody></table></div>`;
  };
  // The spectrum observed as one bar per group and technology: the share of its samples on each band, each band in one
  // colour of the series of the theme.
  const renderBandShares = rows => {
    const host = $('ni-observed-chart');
    if (!rows.length) { host.innerHTML = ''; return; }
    const series = themeColours?.series || ['#5B7A99', '#A9C4DB', '#8BA88E', '#C9B27C', '#B48C7C', '#8E87A0', '#DADDE0'];
    host.innerHTML = ['LTE', 'NR'].map(technology => {
      const own = rows.filter(row => row.technology === technology);
      if (!own.length) return '';
      const bands = [...new Set(own.map(row => row.band))];
      const colour = band => {
        const index = bands.indexOf(band);
        return index < series.length ? series[index] : alpha(series[index % series.length], .55);
      };
      const groups = [...new Set(own.map(row => row.operator))];
      return `<section class="ni-band-share-card"><h4>${technologyChip(technology)} Serving band, % of the samples</h4>
        ${groups.map(group => `<div class="ni-band-share-row"><span class="ni-range-name"><span class="ni-swatch" style="background:${analysis.colours[group] || '#6D46A8'}"></span>${escapeHtml(group)}</span>
          <span class="ni-band-share-bar">${own.filter(row => row.operator === group).map(row => `<span style="flex:0 0 ${row.share}%;background:${colour(row.band)}" title="${escapeHtml(`${group} · ${row.band}: ${number(row.share)}% of the samples`)}">${row.share >= 7 ? escapeHtml(row.band) : ''}</span>`).join('')}</span></div>`).join('')}
        <p class="ni-band-share-legend">${bands.map(band => `<span><i style="background:${colour(band)}"></i>${escapeHtml(band)}${(() => { const frequency = own.find(row => row.band === band)?.frequency_mhz; return frequency ? ` · ${integer(frequency)} MHz` : ''; })()}</span>`).join('')}</p>
      </section>`;
    }).join('');
  };
  const renderSpectrum = () => {
    renderLicensed(analysis.spectrum.licensed);
    const table = $('ni-observed-spectrum');
    const rows = analysis.spectrum.observed;
    renderBandShares(rows);
    if (!rows.length) { table.innerHTML = '<tbody><tr><td class="form-note">The selected CDRs report no serving bands.</td></tr></tbody>'; return; }
    table.innerHTML = `<thead><tr><th>${escapeHtml(analysis.group_label || 'All samples')}</th><th>Technology</th><th>Band</th><th>Frequency</th><th>Duplex</th><th>Class</th><th>Samples</th><th>Share</th><th>Typical DL bandwidth</th></tr></thead><tbody>${rows.map(row => `<tr>
      <td><span class="ni-swatch" style="background:${analysis.colours[row.operator] || '#6D46A8'}"></span>${escapeHtml(row.operator)}</td><td>${technologyChip(row.technology)}</td><td>${escapeHtml(row.band)}</td>
      <td class="num">${row.frequency_mhz ? `${integer(row.frequency_mhz)} MHz` : '—'}</td><td>${escapeHtml(row.duplex || '—')}</td><td>${escapeHtml(row.band_class || '—')}</td>
      <td class="num">${integer(row.samples)}</td><td><span class="ni-share"><span style="width:${row.share}%"></span></span> ${number(row.share)}%</td>
      <td class="num">${row.typical_bandwidth_mhz ? `${number(row.typical_bandwidth_mhz, 0)} MHz` : '—'}</td></tr>`).join('')}</tbody>`;
    renderBandwidth();
  };
  // Bandwidth per band and primary bandwidth (LTE + NR) of the CDR Data tests: the download tests or every test.
  const bandwidthWidth = value => `${Number(value).toLocaleString('en-US', {maximumFractionDigits: 1})} MHz`;
  // The primary bandwidth chart carries its own title and, under it, the line that explains its figures, as a slide does.
  const ladderTitle = config.bandwidth_title || 'Primary bandwidth of each test: LTE + NR';
  const ladderFrame = (body, caption = '', attributes = '') => `<div class="ni-ladder"${attributes}><div class="ni-ladder-head"><h3 class="ni-ladder-title">${escapeHtml(ladderTitle)}</h3>${caption ? `<p class="ni-ladder-caption">${escapeHtml(caption)}</p>` : ''}</div>${body}</div>`;
  const renderBandwidth = () => {
    const bandwidth = analysis?.spectrum?.bandwidth;
    const table = $('ni-band-bandwidth');
    const host = $('ni-total-bandwidth');
    if (!bandwidth) {
      table.innerHTML = '<tbody><tr><td class="form-note">No analysis yet.</td></tr></tbody>';
      host.innerHTML = ladderFrame('<p class="form-note">No analysis yet.</p>');
      $('ni-bandwidth-status').textContent = '';
      return;
    }
    const scope = bandwidth.scopes[$('ni-bandwidth-tests').value] ? $('ni-bandwidth-tests').value : 'download';
    const view = bandwidth.scopes[scope];
    $('ni-bandwidth-status').textContent = view.tests
      ? (scope === 'download' ? `${integer(view.tests)} download tests of the CDR Data.` : `${integer(view.tests)} CDR Data tests of every type.`)
      : 'No CDR Data tests in this selection: only CDR Data reports bandwidths.';
    // Bandwidth per band: one column per bandwidth seen, the samples of each band and their share of the band.
    // A bandwidth with no samples, or under 3% of the known samples of every band, is left out (its samples are Other),
    // unless it is the only bandwidth of a band (as network_insights.shown_bandwidths, for the exports).
    const shownWidths = new Set();
    for (const row of view.bands) {
      const counts = Object.entries(row.bandwidths).filter(([, count]) => count);
      const known = counts.reduce((sum, [, count]) => sum + count, 0);
      for (const [width, count] of counts) if (counts.length === 1 || count / known * 100 >= 3) shownWidths.add(width);
    }
    const widths = [...shownWidths].sort((left, right) => Number(left) - Number(right));
    const hiddenWidths = row => Object.entries(row.bandwidths).filter(([width, count]) => count && !shownWidths.has(width));
    const withOther = view.bands.some(row => hiddenWidths(row).length);
    table.innerHTML = view.bands.length ? `<thead><tr><th>${escapeHtml(analysis.group_label || 'All samples')}</th><th>Technology</th><th>Band</th><th>Duplex</th><th>Samples</th>${widths.map(width => `<th>${bandwidthWidth(width)}</th>`).join('')}${withOther ? '<th title="Bandwidths under 3% of the samples of every band">Other</th>' : ''}<th>Unknown</th><th>Typical</th></tr></thead>
      <tbody>${view.bands.map(row => `<tr><td><span class="ni-swatch" style="background:${analysis.colours[row.operator] || '#6D46A8'}"></span>${escapeHtml(row.operator)}</td><td>${technologyChip(row.technology)}</td><td>${escapeHtml(row.band)}</td><td>${escapeHtml(row.duplex || '—')}</td><td class="num">${integer(row.samples)}</td>
        ${widths.map(width => {
          const count = row.bandwidths[width] || 0;
          const share = row.samples ? count / row.samples * 100 : 0;
          return count ? `<td class="num ni-heat" style="--ni-heat:${Math.min(share, 100) / 100}" title="${escapeHtml(row.band)} at ${bandwidthWidth(width)}: ${number(share)}% of its samples">${integer(count)} <small>${number(share, 0)}%</small></td>` : '<td class="num ni-heat-empty">—</td>';
        }).join('')}${withOther ? (() => {
          const hidden = hiddenWidths(row);
          const count = hidden.reduce((sum, [, value]) => sum + value, 0);
          return count ? `<td class="num" title="${escapeHtml(hidden.map(([width, value]) => `${bandwidthWidth(width)}: ${integer(value)}`).join(', '))}">${integer(count)} <small>${number(row.samples ? count / row.samples * 100 : 0, 0)}%</small></td>` : '<td class="num ni-heat-empty">—</td>';
        })() : ''}
        <td class="num">${row.unknown ? integer(row.unknown) : '—'}</td><td class="num">${row.typical_bandwidth_mhz ? bandwidthWidth(row.typical_bandwidth_mhz) : '—'}</td></tr>`).join('')}</tbody>`
      : '<tbody><tr><td class="form-note">The selected tests report no serving bands.</td></tr></tbody>';
    const split = $('ni-ladder-split').value;
    const splitLadders = view.split_ladders || {};
    for (const option of $('ni-ladder-split').options) {
      option.disabled = option.value !== 'group' && !splitLadders[option.value];
      option.title = option.disabled ? 'The tests of this selection have no serving cell of the Vendor Mapping with this field' : '';
    }
    const ladders = split !== 'group' && splitLadders[split] ? splitLadders[split] : view.ladders;
    renderLadders(host, bandwidth, ladders, scope, split !== 'group' && splitLadders[split] ? $('ni-ladder-split').selectedOptions[0].textContent : '');
    renderLocationStrips(view.locations, bandwidth);
  };
  // Download tests by location: per City (the most measured ones) and group, the share of the tests under 25 MHz and the
  // share that failed or reached 5 Mbit/s or less, each cell shaded by its share.
  const renderLocationStrips = (locations, bandwidth) => {
    const host = $('ni-bandwidth-locations');
    if (!locations || !locations.cities.length) {
      host.innerHTML = '<p class="form-note">The selected download tests have no City with enough tests.</p>';
      return;
    }
    const strip = (key, title, colour, note) => {
      const peak = Math.max(1, ...locations.rows.flatMap(row => Object.values(row.cells).map(cell => cell[key] || 0)));
      return `<div class="ni-strip"><h4 class="ni-strip-title">${escapeHtml(title)}</h4><div class="table-wrap ni-table-wrap"><table class="ni-table ni-strip-table"><thead><tr><th>${escapeHtml(bandwidth.column_label)}</th>${locations.cities.map(city => `<th>${escapeHtml(city)}</th>`).join('')}</tr></thead>
        <tbody>${locations.rows.map(row => `<tr><td><span class="ni-swatch" style="background:${escapeHtml(bandwidth.column_colours[row.column] || '#6D46A8')}"></span>${escapeHtml(row.column)}</td>${locations.cities.map(city => {
          const cell = row.cells[city];
          if (!cell || cell[key] === null || cell[key] === undefined) return '<td class="num ni-heat-empty">—</td>';
          const few = cell.tests < locations.min_tests;
          return `<td class="num ni-strip-cell${few ? ' is-few' : ''}" style="--ni-strip:${colour};--ni-strip-share:${Math.min(1, cell[key] / peak)}" title="${escapeHtml(`${row.column} · ${city}: ${number(cell[key])}% of ${integer(key === 'narrow_share' ? cell.known : cell.judged)} download tests${few ? ` (under ${locations.min_tests} tests)` : ''}`)}">${number(cell[key], 0)}%</td>`;
        }).join('')}</tr>`).join('')}</tbody></table></div><p class="form-note">${escapeHtml(note)}</p></div>`;
    };
    host.innerHTML = strip('narrow_share', `Share of the download tests under ${locations.narrow_below_mhz} MHz of primary bandwidth (LTE + NR)`, '181,19,43',
      'Of the tests with a known bandwidth. Hatched: under the minimum of tests.')
      + strip('slow_share', `Share of the download tests failed or at ${locations.slow_mbps} Mbit/s or less`, '232,65,79',
        'Failed: the result is not completed; slow: the mean data rate of the test. Hatched: under the minimum of tests.');
  };
  // The line under the title of the ladders: what the ladders and their number show and the group with the most tests
  // under 25 MHz in each environment (shared with the PowerPoint and Word summaries).
  const ladderCaption = (bandwidth, ladders, scope) => {
    const narrow = bandwidth.narrow_below_mhz;
    const highlights = ladders.highlights || [];
    return `Each ladder splits the ${scope === 'download' ? 'download tests' : 'CDR Data tests'} with a known bandwidth by their primary bandwidth (the LTE carriers and the NR primary cell; the CDRs do not report the NR secondary carriers), widest at the bottom; the number beside it is the share under ${narrow} MHz (dark red) and the one below it the share at ${bandwidth.wide_from_mhz ?? 100} MHz or more.${highlights.length
      ? ` Most under ${narrow} MHz: ${highlights.map(item => `${item.environment}, ${item.column} (${number(item.narrow_share, 0)}%)`).join('; ')}.` : ''}`;
  };
  // Primary bandwidth: per group (column) and environment (row), one block per bandwidth class, widest at the bottom,
  // as wide as the class midpoint and as tall as its share of the tests; the figure is the share below 25 MHz.
  const renderLadders = (host, bandwidth, ladders, scope, splitLabel = '') => {
    if (!ladders.cells.some(cell => cell.known)) {
      host.innerHTML = ladderFrame('<p class="form-note">The selected tests report no LTE or NR bandwidth.</p>');
      return;
    }
    // The classes in the scale of the theme, the widest in its best colour.
    const ladder = themeColours ? window.NetworkInsightsFindings.ladderColours(themeColours, bandwidth.classes.length) : [];
    const classes = bandwidth.classes.map((item, index) => ({...item, colour: ladder[index] || item.colour}));
    const columns = ladders.columns;
    const rows = ladders.environments;
    const labelWidth = 170, columnWidth = 210, header = 40, rowHeight = 180, legendHeight = 56;
    const wide = bandwidth.wide_from_mhz ?? 100;
    const width = labelWidth + columns.length * columnWidth;
    const height = header + rows.length * rowHeight + legendHeight;
    const widest = Math.max(...classes.map(item => item.width));
    const cells = new Map(ladders.cells.map(cell => [`${cell.column}\u0000${cell.environment}`, cell]));
    const parts = [];
    columns.forEach((column, index) => {
      const x = labelWidth + index * columnWidth + columnWidth / 2;
      parts.push(`<text class="ni-ladder-column" x="${x}" y="${header - 14}" text-anchor="middle" fill="${escapeHtml(bandwidth.column_colours[column] || '#312e81')}">${escapeHtml(column)}</text>`);
    });
    rows.forEach((row, rowIndex) => {
      const top = header + rowIndex * rowHeight;
      const base = top + rowHeight - 32;
      const plot = rowHeight - 56;
      // The widest share at 100 MHz or more of the row is in bold, as in benchmark slides.
      const rowCells = columns.map(column => cells.get(`${column}\u0000${row}`)).filter(cell => cell?.known);
      const mostWide = rowCells.length > 1 ? Math.max(...rowCells.map(cell => cell.wide_share ?? 0)) : null;
      parts.push(`<text class="ni-ladder-row" x="12" y="${top + rowHeight / 2}" dominant-baseline="middle">${escapeHtml(row)}</text>`);
      if (rowIndex) parts.push(`<line class="ni-ladder-divider" x1="0" x2="${width}" y1="${top}" y2="${top}"></line>`);
      columns.forEach((column, index) => {
        const centre = labelWidth + index * columnWidth + columnWidth / 2;
        const span = columnWidth - 28;
        parts.push(`<line class="ni-ladder-base" x1="${centre - span / 2}" x2="${centre + span / 2}" y1="${base}" y2="${base}"></line>`);
        const cell = cells.get(`${column}\u0000${row}`);
        if (!cell || !cell.known) {
          parts.push(`<text class="ni-ladder-empty" x="${centre}" y="${base - 12}" text-anchor="middle">${cell ? 'No bandwidth' : 'No tests'}</text>`);
          return;
        }
        let cursor = base;
        // The figure stands right of the narrow blocks (up to 40–59 MHz), level with the top of the ladder.
        let narrowTop = base;
        const narrowRight = centre + (classes.at(-3)?.width || widest) / widest * span / 2;
        classes.forEach((item, classIndex) => {
          const share = cell.shares[classIndex];
          const blockWidth = item.width / widest * span;
          const blockHeight = share / 100 * plot;
          cursor -= blockHeight;
          if (classIndex === classes.length - 1) narrowTop = cursor;
          if (blockHeight <= 0) return;
          parts.push(`<rect x="${centre - blockWidth / 2}" y="${cursor}" width="${blockWidth}" height="${blockHeight}" fill="${item.colour}"><title>${escapeHtml(`${column} · ${row} · ${item.label}: ${number(share)}% (${integer(cell.counts[classIndex])} of ${integer(cell.known)} tests)`)}</title></rect>`);
        });
        parts.push(`<text class="ni-ladder-wide${mostWide !== null && cell.wide_share === mostWide ? ' is-most' : ''}" x="${centre}" y="${base + 19}" text-anchor="middle"><title>${escapeHtml(`${column} · ${row}: ${number(cell.wide_share)}% of ${integer(cell.known)} tests at ${wide} MHz or more`)}</title>${number(cell.wide_share, 0)}% at ${wide} MHz+</text>`);
        // The share under 25 MHz takes the colour of its block.
        parts.push(`<text class="ni-ladder-figure" x="${narrowRight + 6}" y="${narrowTop + 4}" dominant-baseline="hanging" style="fill:${classes.at(-1).colour}"><title>${escapeHtml(`${column} · ${row}: ${number(cell.narrow_share)}% of ${integer(cell.known)} tests below ${bandwidth.narrow_below_mhz} MHz; median ${number(cell.median_mhz, 0)} MHz`)}</title>${number(cell.narrow_share, 0)}%</text>`);
      });
    });
    // The legend, widest class first, under the ladders.
    const legendTop = header + rows.length * rowHeight + 22;
    // The classes follow the legend title, which is wider than the row labels.
    let legendX = Math.max(labelWidth, 12 + 'Primary bandwidth, MHz (LTE + NR)'.length * 8.6 + 18);
    parts.push(`<text class="ni-ladder-legend-title" x="12" y="${legendTop + 6}" dominant-baseline="middle">Primary bandwidth, MHz (LTE + NR)</text>`);
    classes.forEach(item => {
      parts.push(`<rect x="${legendX}" y="${legendTop - 2}" width="16" height="16" rx="2" fill="${item.colour}"></rect><text class="ni-ladder-legend" x="${legendX + 22}" y="${legendTop + 6}" dominant-baseline="middle">${escapeHtml(item.label)}</text>`);
      legendX += 34 + item.label.length * 8.2;
    });
    const svgWidth = Math.max(width, legendX + 12);
    const known = ladders.cells.reduce((total, cell) => total + cell.known, 0);
    host.innerHTML = `${ladderFrame(`<div class="ni-ladder-scroll"><svg viewBox="0 0 ${svgWidth} ${height}" style="min-width:${Math.min(svgWidth, 160 + columns.length * 150)}px" xmlns="http://www.w3.org/2000/svg">${parts.join('')}</svg></div>`,
      ladderCaption(bandwidth, ladders, scope), ` role="img" aria-label="${escapeHtml(`${ladderTitle}, per ${bandwidth.column_label} and environment`)}"`)}
      <p class="form-note">${integer(known)} tests with a known bandwidth${ladders.unknown ? `; ${integer(ladders.unknown)} without one are left out` : ''}${ladders.without_environment ? `; ${integer(ladders.without_environment)} tests without an environment are not shown` : ''}. Columns: ${escapeHtml(splitLabel || bandwidth.column_label)}${splitLabel ? ' (the combinations with 20 tests or more of a known bandwidth)' : ''}.</p>`;
  };
  // NR sites by duplex mode of the inventory snapshot, after the Analysis Selection filters that describe it.
  let nrDuplexPayload = null, nrDuplexController = null, nrDuplexTimer = null, nrDuplexKey = '', nrDuplexFilters = null;
  const nrDuplexRequest = () => ({...requestBody(), split: $('ni-nr-duplex-split').value});
  const loadNrDuplex = async ({force = false} = {}) => {
    const table = $('ni-nr-duplex-sites');
    if (!(config.snapshots || []).length) {
      table.innerHTML = '<tbody><tr><td class="form-note">No inventory snapshot is available.</td></tr></tbody>';
      return;
    }
    const body = nrDuplexRequest();
    nrDuplexFilters = body;
    // Only the filters that restrict the inventory, the snapshot and the split change the counts.
    const key = JSON.stringify(['snapshot', 'split', 'operators', 'operator_vendors', 'vendors', 'regions', 'clusters', 'cities'].map(name => body[name]));
    if (!force && key === nrDuplexKey && nrDuplexPayload) return;
    nrDuplexKey = key;
    nrDuplexController?.abort();
    const controller = new AbortController();
    nrDuplexController = controller;
    $('ni-nr-duplex-status').textContent = 'Counting the NR sites…';
    try {
      const response = await fetch('/api/network-insights/nr-duplex-sites', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body), signal: controller.signal,
      });
      const payload = await response.json();
      if (nrDuplexController !== controller) return;
      if (!response.ok) throw new Error(payload.detail || 'Unable to count the NR sites.');
      nrDuplexPayload = payload;
      renderNrDuplex();
    } catch (error) {
      if (error.name === 'AbortError' || nrDuplexController !== controller) return;
      nrDuplexKey = '';
      $('ni-nr-duplex-status').textContent = '';
      table.innerHTML = `<tbody><tr><td class="form-note">${escapeHtml(error.message)}</td></tr></tbody>`;
    }
  };
  const scheduleNrDuplex = () => { clearTimeout(nrDuplexTimer); nrDuplexTimer = setTimeout(() => { void loadNrDuplex(); }, 300); };
  const renderNrDuplex = () => {
    const payload = nrDuplexPayload;
    const table = $('ni-nr-duplex-sites');
    const rows = payload?.rows || [];
    const filters = Object.keys(payload?.filters || {}).length;
    const missing = payload?.missing_operators || [];
    $('ni-nr-duplex-status').textContent = `${filters ? 'Filtered inventory' : 'Whole inventory'} · ${(payload?.selection || []).map(item => `${item.operator} ${item.snapshot_date}`).join(', ')}${missing.length ? ` · no inventory for ${missing.join(', ')}` : ''}`;
    if (!rows.length) { table.innerHTML = '<tbody><tr><td class="form-note">No in-service NR site matches the filters.</td></tr></tbody>'; return; }
    const split = Boolean(payload.split);
    const swatch = row => row.all_networks ? '' : `<span class="ni-swatch" style="background:${payload.colours?.[row.operator] || '#6D46A8'}"></span>`;
    table.innerHTML = `<thead><tr>${split ? `<th rowspan="2">${escapeHtml(payload.split_label)}</th>` : ''}<th rowspan="2">Network</th><th colspan="6" class="ni-group-head ni-group-start">Logical sites (site IDs)</th><th colspan="3" class="ni-group-head ni-group-start is-physical">Physical sites (within ${integer(payload.radius_m)} m)</th></tr>
      <tr><th class="ni-group-start">With NR</th><th>NR TDD</th><th>NR FDD</th><th>TDD and FDD</th><th>TDD only</th><th>FDD only</th><th class="ni-group-start">With NR</th><th>NR TDD</th><th>NR FDD</th></tr></thead>
      <tbody>${rows.map(row => `<tr class="${row.all_networks ? 'ni-total-row' : ''}">${split ? `<td>${escapeHtml(row.area)}</td>` : ''}<td>${swatch(row)}${escapeHtml(row.operator)}</td>
        <td class="num ni-group-start">${integer(row.sites)}</td><td class="num"><strong>${integer(row.tdd_sites)}</strong></td><td class="num"><strong>${integer(row.fdd_sites)}</strong></td>
        <td class="num">${integer(row.both_sites)}</td><td class="num">${integer(row.tdd_only_sites)}</td><td class="num">${integer(row.fdd_only_sites)}</td>
        <td class="num ni-group-start">${integer(row.physical_sites)}</td><td class="num"><strong>${integer(row.physical_tdd_sites)}</strong></td><td class="num"><strong>${integer(row.physical_fdd_sites)}</strong></td></tr>`).join('')}</tbody>`;
  };
  $('ni-nr-duplex-split').addEventListener('change', () => { void loadNrDuplex(); });
  $('ni-bandwidth-tests').addEventListener('change', renderBandwidth);
  $('ni-ladder-split').addEventListener('change', renderBandwidth);
  // Key Findings: their footnotes end with the scope and Campaigns of the analysis.
  const renderFindings = () => {
    const filters = analysedFilters || {};
    // The campaigns the views compare: the latest one with a split by Campaign.
    const campaigns = analysis.findings?.campaigns || [];
    const scope = `Scope: ${scopeItems(filters).map(item => item.label).join(' · ')}${campaigns.length ? `; ${campaigns.length > 1 ? 'Campaigns' : 'Campaign'}: ${campaigns.join(', ')}.` : '.'}`;
    window.NetworkInsightsFindings?.render($('ni-findings'), analysis.findings, activeTheme, scope);
  };
  const render = () => {
    if (!analysis) return;
    renderOverview();
    renderFindings();
    renderRfSections();
    renderNrBands();
    renderInteractivity();
    renderMaps();
    renderServing();
    renderNrAvailability();
    renderSites();
    renderSpectrum();
  };

  // Every table of the page: headers of numeric columns align with their figures, and tables with many
  // rows scroll inside their frame under a fixed header.
  const polishTables = () => {
    for (const table of document.querySelectorAll('#network-insights table.ni-table')) {
      const body = table.tBodies[0];
      const rows = body ? body.rows.length : 0;
      const wrap = table.parentElement;
      if (wrap?.classList.contains('ni-table-wrap')) wrap.classList.toggle('is-long', rows > 15);
      if (!table.tHead || !rows) continue;
      // The column of every header cell, following its colspan and rowspan.
      const columns = [];
      [...table.tHead.rows].forEach((row, rowIndex) => {
        let column = 0;
        for (const cell of row.cells) {
          while (columns[rowIndex]?.[column]) column += 1;
          for (let down = 0; down < cell.rowSpan; down += 1) {
            for (let across = 0; across < cell.colSpan; across += 1) (columns[rowIndex + down] ||= [])[column + across] = cell;
          }
          column += cell.colSpan;
        }
      });
      const sample = [...body.rows].find(row => row.cells.length > 1);
      if (!sample) continue;
      [...sample.cells].forEach((cell, index) => {
        if (!cell.classList.contains('num')) return;
        for (const row of columns) if (row[index]?.colSpan === 1) row[index].classList.add('num');
      });
    }
  };
  // Scope pills, as in Scoring: every chart and table names its area (the City, Cluster or Region filters, the most
  // specific first, else National), its operators and its vendors (All Operators and All Vendors without a filter) and,
  // when chosen, its environments. A long list keeps its first two names and counts the others; the tooltip lists them
  // all. The measurement panels name the filters of the shown analysis, the NR sites by duplex mode and the site
  // tables those of their own request, and the panels of the whole inventory name no filter.
  const scopeItems = (filters = {}, {environments = true} = {}) => {
    const values = key => [...new Set((filters?.[key] || []).map(value => String(value ?? '').trim())
      .filter(value => value && !isCampaignPreset(value)))];
    const pill = (list, level, plural) => {
      const name = list.length > 1 ? plural : level;
      const shown = list.length > 3 ? [...list.slice(0, 2), `${list.length - 2} more`] : list;
      return {label: `${name}: ${shown.length > 1 ? `${shown.slice(0, -1).join(', ')} & ${shown.at(-1)}` : shown[0]}`,
        title: `${name}: ${list.join(', ')}`};
    };
    const area = [['cities', 'City', 'Cities'], ['clusters', 'Cluster', 'Clusters'], ['regions', 'Region', 'Regions']]
      .map(([key, level, plural]) => (values(key).length ? pill(values(key), level, plural) : null)).find(Boolean);
    const operators = values('operators');
    const vendors = values('vendors');
    const items = [
      {kind: 'area', ...(area || {label: 'National', title: 'National: no City, Cluster or Region filter'})},
      {kind: 'operator', ...(operators.length ? pill(operators, 'Operator', 'Operators')
        : {label: 'All Operators', title: 'All Operators: no Operator filter'})},
      {kind: 'vendor', ...(vendors.length ? pill(vendors, 'Vendor', 'Vendors') : {label: 'All Vendors', title: 'All Vendors: no Vendor filter'})},
    ];
    const chosen = environments ? values('environments') : [];
    if (chosen.length) items.push({kind: 'environment', ...pill(chosen, 'Environment', 'Environments')});
    return items;
  };
  const scopePills = (items, key) => `<span class="ni-scope-pills" data-scope="${escapeHtml(key)}">${items.map(item =>
    `<span class="ni-scope-pill is-${item.kind}" title="${escapeHtml(item.title)}">${escapeHtml(item.label)}</span>`).join('')}</span>`;
  // A title ends with the pills (its text alone is kept for the larger views); a chart or table without a title of its
  // own has them in a line above it.
  const applyScope = (element, items, mode) => {
    const key = JSON.stringify(items);
    if (mode === 'title') {
      const current = element.querySelector(':scope > .ni-scope-pills');
      if (current?.dataset.scope === key) return;
      current?.remove();
      if (element.dataset.title === undefined) element.dataset.title = element.textContent.replace(/\s+/g, ' ').trim();
      element.insertAdjacentHTML('beforeend', scopePills(items, key));
      return;
    }
    const previous = element.previousElementSibling;
    const row = previous?.classList.contains('ni-scope-row') ? previous : null;
    if (row?.firstElementChild?.dataset.scope === key) return;
    row?.remove();
    element.insertAdjacentHTML('beforebegin', `<div class="ni-scope-row">${scopePills(items, key)}</div>`);
  };
  const applyScopes = () => {
    const all = selector => [...document.querySelectorAll(selector)];
    // The tables of a panel that have no title of their own (the CDF percentiles belong to their chart).
    const untitled = host => [...(host?.querySelectorAll(':scope > .ni-table-wrap:not(.ni-percentiles)') || [])].filter(wrap => {
      let previous = wrap.previousElementSibling;
      while (previous?.classList.contains('ni-scope-row')) previous = previous.previousElementSibling;
      return !previous?.matches('h3, h4');
    });
    const targets = [];
    const add = (elements, items, mode) => { if (items) for (const element of elements) if (element) targets.push([element, items, mode]); };
    const measured = analysis && analysedFilters ? scopeItems(analysedFilters) : null;
    const wholeInventory = scopeItems({}, {environments: false});
    add([$('ni-overview').querySelector(':scope > :not(.ni-scope-row)')], measured, 'row');
    add(all('#ni-map-sections .ni-map-card h3, #ni-map-sections h4.ni-subtitle'), measured, 'title');
    add(all('#ni-rf-sections .ni-cdf-block > .ni-chart-card, #ni-serving .ni-cdf-block > .ni-chart-card, #ni-serving > .ni-kpi-grid'), measured, 'row');
    add([...all('#ni-rf-sections .ni-technology-section'), $('ni-nr')].flatMap(untitled), measured, 'row');
    add(all('#ni-serving h4, #ni-nr h4'), measured, 'title');
    add([$('ni-observed-title'), $('ni-band-bandwidth-title'), $('ni-total-bandwidth').querySelector('.ni-ladder-title')], measured, 'title');
    add([$('ni-sites-table').parentElement], $('ni-sites-source').value === 'observed' ? measured : wholeInventory, 'row');
    if (snapshotPayload) {
      add([...all('#ni-snapshot-panel h4'), $('ni-deployed-title'), $('ni-density-title')], wholeInventory, 'title');
      add(all('#ni-deployment .ni-network-table h3'), wholeInventory, 'title');
    }
    add([$('ni-licensed-title')], wholeInventory, 'title');
    if (nrDuplexPayload) add([$('ni-nr-duplex-title')], scopeItems(nrDuplexFilters || {}, {environments: false}), 'title');
    for (const section of all('#ni-deployment section.ni-inventory[data-ni-source]')) {
      add([section.querySelector(':scope > h3')], scopeItems(requestBody(), {environments: section.dataset.niSource === 'observed'}), 'title');
    }
    for (const [element, items, mode] of targets) applyScope(element, items, mode);
  };
  let polishPending = false;
  new MutationObserver(() => {
    // The pills follow every render at once (applying them again changes nothing).
    applyScopes();
    if (polishPending) return;
    polishPending = true;
    requestAnimationFrame(() => { polishPending = false; polishTables(); });
  }).observe(document.getElementById('network-insights'), {childList: true, subtree: true});

  // Double-clicking a chart, map or table opens it larger, as in Scoring: charts and maps are drawn again at the
  // size of the dialog (with their zoom controls) and tables are copied whole.
  const expandDialog = $('ni-expand-dialog');
  const panelTitle = element => element.closest('details')?.querySelector('summary h2')?.textContent?.trim() || 'Network Insights';
  const headingBefore = element => {
    const body = element.closest('.collapsible-panel-body') || element.closest('details');
    const headings = [...(body?.querySelectorAll('h3, h4') || [])].filter(heading => heading.compareDocumentPosition(element) & Node.DOCUMENT_POSITION_FOLLOWING);
    const heading = headings.at(-1);
    return heading?.dataset.title || heading?.textContent?.replace(/\s+/g, ' ').trim() || '';
  };
  // The scope pills of a chart, map or table: those of its title or of the line above it.
  const scopeOf = element => {
    const body = element.closest('.collapsible-panel-body') || element.closest('details');
    const marks = [...(body?.querySelectorAll('h3, h4, .ni-scope-row') || [])].filter(mark =>
      mark.contains(element) || element.contains(mark) || mark.compareDocumentPosition(element) & Node.DOCUMENT_POSITION_FOLLOWING);
    return marks.filter(mark => mark.querySelector(':scope > .ni-scope-pills') || mark.matches('.ni-scope-row')).at(-1)
      ?.querySelector('.ni-scope-pills') || null;
  };
  const openExpanded = (kind, title, meta, build, scope = null) => {
    if (!expandDialog) return;
    $('ni-expand-kind').textContent = kind;
    $('ni-expand-title').textContent = title;
    if (scope) $('ni-expand-title').append(scope.cloneNode(true));
    $('ni-expand-meta').textContent = meta === title ? '' : meta;
    const content = $('ni-expand-content');
    content.replaceChildren();
    content.classList.toggle('is-table', kind === 'Table');
    expandDialog.showModal();
    build(content);
  };
  // Every map navigates like a web map: dragging moves it, the wheel zooms towards the pointer and Ctrl/Cmd+drag
  // draws a rectangle to zoom into, down to the most detailed OpenStreetMap level. From zoom level 12 the inventory
  // sites of the view are loaded (map-sites) and, from level 13, drawn as sectors.
  const REFERENCE_ZOOM = 21, MIN_TILE_ZOOM = 4, MAX_TILE_ZOOM = 19, SITES_FROM_ZOOM = 12, WEDGES_FROM_ZOOM = 13;
  const MIN_RESOLUTION = 2 ** (REFERENCE_ZOOM - MAX_TILE_ZOOM) / 4, MAX_RESOLUTION = 2 ** (REFERENCE_ZOOM - MIN_TILE_ZOOM);
  const worldToLonLat = (x, y, zoom) => {
    const scale = 256 * 2 ** zoom;
    return [x / scale * 360 - 180, Math.atan(Math.sinh(Math.PI * (1 - 2 * y / scale))) * 180 / Math.PI];
  };
  const siteKey = site => `${site.lon},${site.lat},${site.label}`;
  const geoMaps = new WeakMap();
  // Holding Ctrl/Cmd turns the hand over the maps into the crosshair of the zoom rectangle, and Alt/Opt into the
  // ruler of the distance tool.
  const rectangleKey = event => {
    const root = document.documentElement;
    root.classList.toggle('ni-measure', Boolean(event.altKey));
    root.classList.toggle('ni-rectangle-zoom', !event.altKey && Boolean(event.ctrlKey || event.metaKey));
  };
  window.addEventListener('keydown', rectangleKey);
  window.addEventListener('keyup', rectangleKey);
  window.addEventListener('blur', () => document.documentElement.classList.remove('ni-rectangle-zoom', 'ni-measure'));
  // Great-circle distance (metres) and initial bearing (degrees from north) between two places.
  const geodesic = ([lon1, lat1], [lon2, lat2]) => {
    const radians = Math.PI / 180, phi1 = lat1 * radians, phi2 = lat2 * radians, dPhi = phi2 - phi1, dLambda = (lon2 - lon1) * radians;
    const a = Math.sin(dPhi / 2) ** 2 + Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLambda / 2) ** 2;
    const bearing = Math.atan2(Math.sin(dLambda) * Math.cos(phi2), Math.cos(phi1) * Math.sin(phi2) - Math.sin(phi1) * Math.cos(phi2) * Math.cos(dLambda));
    return {metres: 6371008.8 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a)), bearing: (bearing / radians + 360) % 360};
  };
  const distanceLabel = metres => metres < 1000 ? `${integer(Math.round(metres))} m` : `${number(metres / 1000, metres < 10000 ? 2 : 1)} km`;
  const geoMap = (canvas, base, start, {expanded = false} = {}) => {
    globalThis.renderCanvasChart(canvas, {...mapView(start), geo_navigation: true, point_shape: 'square'});
    const first = globalThis.getCanvasMapView?.(canvas);
    if (!first?.worldBounds) return null;
    canvas.classList.add('ni-geo-canvas');
    canvas.addEventListener('pointermove', rectangleKey);
    const clampResolution = value => Math.max(MIN_RESOLUTION, Math.min(MAX_RESOLUTION, value));
    // A view: its centre in world pixels at REFERENCE_ZOOM and the world pixels per plot pixel.
    const viewOf = (bounds, zoom) => {
      const factor = 2 ** (REFERENCE_ZOOM - zoom);
      return {x: (bounds[0] + bounds[2]) / 2 * factor, y: (bounds[1] + bounds[3]) / 2 * factor,
        resolution: clampResolution(Math.max((bounds[2] - bounds[0]) * factor / first.width, (bounds[3] - bounds[1]) * factor / first.height))};
    };
    const whole = Array.isArray(base.basemap?.world_bounds) ? viewOf(base.basemap.world_bounds.map(Number), Number(base.basemap.zoom)) : viewOf(first.worldBounds, first.zoom);
    let view = viewOf(first.worldBounds, first.zoom), frame = 0, fetchTimer = 0, fetchController = null, current = null;
    const loaded = new Map(), fetched = new Set();
    const legend = new Map((base.legend?.items || []).map(item => [item.label, item]));
    const source = base.sector_source;
    const level = document.createElement('output');
    level.className = 'ni-chart-zoom-level';
    const payload = () => {
      const geometry = globalThis.getCanvasMapView(canvas);
      const zoom = Math.max(MIN_TILE_ZOOM, Math.min(MAX_TILE_ZOOM, Math.round(REFERENCE_ZOOM - Math.log2(view.resolution))));
      const factor = 2 ** (REFERENCE_ZOOM - zoom);
      const halfWidth = view.resolution * geometry.width / 2, halfHeight = view.resolution * geometry.height / 2;
      const bounds = [(view.x - halfWidth) / factor, (view.y - halfHeight) / factor, (view.x + halfWidth) / factor, (view.y + halfHeight) / factor];
      const [west, north] = worldToLonLat(bounds[0], bounds[1], zoom);
      const [east, south] = worldToLonLat(bounds[2], bounds[3], zoom);
      const metresPerPixel = 40075016.686 * Math.cos((north + south) / 2 * Math.PI / 180) / (256 * 2 ** REFERENCE_ZOOM) * view.resolution;
      const sites = new Map((base.sectors || []).map(site => [siteKey(site), site]));
      for (const [key, site] of loaded) sites.set(key, site);
      const shown = mapView({...base, sectors: [...sites.values()], legend: {...base.legend, items: [...legend.values()]}});
      return {...shown, geo_navigation: true, point_shape: 'square', domain: {x: [west, east], y: [south, north]},
        basemap: {...base.basemap, zoom, tile_range: bounds.map(value => Math.floor(value / 256)), world_bounds: bounds},
        point_radius: zoom >= WEDGES_FROM_ZOOM ? 9 : zoom >= 10 ? 7 : 5, sector_wedges: zoom >= WEDGES_FROM_ZOOM,
        // Sectors about 140 m long on the ground, so neighbouring sites rarely overlap.
        sector_radius: Math.max(12, Math.min(48, 140 / metresPerPixel)), view: {zoom, west, south, east, north}};
    };
    // The sites of the view (with a margin, so short moves need no new request), once close enough.
    const loadSites = area => {
      clearTimeout(fetchTimer);
      if (!source?.families?.length || area.zoom < SITES_FROM_ZOOM || $('ni-map-sites')?.checked === false) return;
      fetchTimer = setTimeout(async () => {
        const marginX = (area.east - area.west) * .25, marginY = (area.north - area.south) * .25;
        const bbox = [area.west - marginX, area.south - marginY, area.east + marginX, area.north + marginY].map(value => Number(value.toFixed(4)));
        const key = bbox.join(',');
        if (fetched.has(key)) return;
        fetchController?.abort();
        fetchController = new AbortController();
        try {
          const response = await fetch('/api/network-insights/map-sites', {
            method: 'POST', headers: {'Content-Type': 'application/json'}, signal: fetchController.signal,
            body: JSON.stringify({snapshot: source.snapshot || '', families: source.families, bbox}),
          });
          if (!response.ok) return;
          const result = await response.json();
          fetched.add(key);
          for (const site of result.sectors || []) loaded.set(siteKey(site), site);
          for (const item of result.legend || []) if (!legend.has(item.label)) legend.set(item.label, item);
          if (canvas.isConnected) redraw();
        } catch (error) {
          if (error.name !== 'AbortError') console.warn('Network Insights map sites', error);
        }
      }, 250);
    };
    const draw = () => {
      frame = 0;
      if (!canvas.isConnected) return;
      current = payload();
      globalThis.renderCanvasChart(canvas, current);
      chartPayloads.set(canvas, current);
      level.textContent = `Zoom ${current.view.zoom}`;
      loadSites(current.view);
      drawMeasure();
    };
    const redraw = () => { if (!frame) frame = requestAnimationFrame(draw); };
    // The place under the pointer stays under it while zooming.
    const zoomBy = (factor, dx = 0, dy = 0) => {
      const resolution = clampResolution(view.resolution * factor);
      view = {x: view.x + dx * (view.resolution - resolution), y: view.y + dy * (view.resolution - resolution), resolution};
      redraw();
    };
    const pointerOffset = event => {
      const geometry = globalThis.getCanvasMapView(canvas), bounds = canvas.getBoundingClientRect();
      const x = ((event.clientX - bounds.left) / geometry.scaleX - geometry.originX) / geometry.cameraZoom;
      const y = ((event.clientY - bounds.top) / geometry.scaleY - geometry.originY) / geometry.cameraZoom;
      return [x - (geometry.left + geometry.width / 2), y - (geometry.top + geometry.height / 2)];
    };
    // The distance tool (Alt/Opt+drag): a line between two places with its length and bearing, kept on the map
    // (and moving with it) until the next click or Escape.
    const placeAt = event => {
      const [dx, dy] = pointerOffset(event);
      return worldToLonLat(view.x + dx * view.resolution, view.y + dy * view.resolution, REFERENCE_ZOOM);
    };
    const screenOf = ([longitude, latitude]) => {
      const geometry = globalThis.getCanvasMapView(canvas), bounds = canvas.getBoundingClientRect(), card = canvas.parentElement.getBoundingClientRect();
      const world = osmWorld(latitude, longitude, REFERENCE_ZOOM);
      const logicalX = geometry.left + geometry.width / 2 + (world[0] - view.x) / view.resolution;
      const logicalY = geometry.top + geometry.height / 2 + (world[1] - view.y) / view.resolution;
      return [bounds.left - card.left + (logicalX * geometry.cameraZoom + geometry.originX) * geometry.scaleX,
        bounds.top - card.top + (logicalY * geometry.cameraZoom + geometry.originY) * geometry.scaleY];
    };
    const ruler = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    ruler.setAttribute('class', 'ni-measure-overlay');
    ruler.setAttribute('aria-hidden', 'true');
    canvas.parentElement.append(ruler);
    let measure = null;
    const drawMeasure = () => {
      if (!measure) { ruler.replaceChildren(); return; }
      const [x1, y1] = screenOf(measure.from), [x2, y2] = screenOf(measure.to);
      const {metres, bearing} = geodesic(measure.from, measure.to);
      const text = `${distanceLabel(metres)} · ${integer(Math.round(bearing))}°`;
      const svg = tag => document.createElementNS('http://www.w3.org/2000/svg', tag);
      const halo = svg('line'), line = svg('line'), start = svg('circle'), end = svg('circle'), label = svg('text');
      for (const element of [halo, line]) { element.setAttribute('x1', x1); element.setAttribute('y1', y1); element.setAttribute('x2', x2); element.setAttribute('y2', y2); }
      halo.setAttribute('class', 'ni-measure-halo'); line.setAttribute('class', 'ni-measure-line');
      for (const [circle, x, y] of [[start, x1, y1], [end, x2, y2]]) { circle.setAttribute('cx', x); circle.setAttribute('cy', y); circle.setAttribute('r', 4.5); circle.setAttribute('class', 'ni-measure-end'); }
      // The label sits beyond the end, along the line, so the pointer dragging the end never covers it.
      const length = Math.hypot(x2 - x1, y2 - y1) || 1, ux = (x2 - x1) / length, uy = (y2 - y1) / length;
      label.setAttribute('x', x2 + ux * 26); label.setAttribute('y', y2 + uy * 26);
      label.setAttribute('text-anchor', ux < -.3 ? 'end' : ux > .3 ? 'start' : 'middle');
      label.setAttribute('dominant-baseline', uy < -.3 ? 'auto' : uy > .3 ? 'hanging' : 'middle');
      label.setAttribute('class', 'ni-measure-label');
      label.textContent = text;
      ruler.replaceChildren(halo, line, start, end, label);
      measure.text = text;
      canvas.setAttribute('title', `Distance ${text}`);
    };
    const clearMeasure = () => { if (!measure) return; measure = null; canvas.removeAttribute('title'); drawMeasure(); };
    document.addEventListener('keydown', event => { if (event.key === 'Escape') clearMeasure(); });
    canvas.addEventListener('wheel', event => {
      event.preventDefault();
      zoomBy(Math.exp(event.deltaY * (event.deltaMode === 1 ? .05 : .0018)), ...pointerOffset(event));
    }, {passive: false});
    // On the page a double-click opens the larger map; in the larger map it zooms in.
    if (expanded) canvas.addEventListener('dblclick', event => { event.stopPropagation(); zoomBy(.5, ...pointerOffset(event)); });
    const selection = document.createElement('div');
    selection.className = 'ds-chart-zoom-selection';
    selection.hidden = true;
    canvas.parentElement.append(selection);
    let drag = null;
    canvas.addEventListener('pointerdown', event => {
      if (event.button !== 0 && event.button !== 1) return;
      const measuring = event.button === 0 && event.altKey;
      const pan = !measuring && (event.button === 1 || !(event.ctrlKey || event.metaKey));
      drag = {id: event.pointerId, pan, measuring, startX: event.clientX, startY: event.clientY, x: event.clientX, y: event.clientY};
      canvas.setPointerCapture?.(event.pointerId);
      canvas.classList.add(measuring ? 'is-measuring' : pan ? 'is-panning' : 'is-selecting');
      if (measuring) { measure = {from: placeAt(event), to: placeAt(event)}; drawMeasure(); }
      event.preventDefault();
    });
    canvas.addEventListener('pointermove', event => {
      if (!drag || event.pointerId !== drag.id) return;
      if (drag.measuring) { measure.to = placeAt(event); drawMeasure(); return; }
      if (drag.pan) {
        const geometry = globalThis.getCanvasMapView(canvas);
        view = {...view, x: view.x - (event.clientX - drag.x) / geometry.scaleX / geometry.cameraZoom * view.resolution,
          y: view.y - (event.clientY - drag.y) / geometry.scaleY / geometry.cameraZoom * view.resolution};
        drag.x = event.clientX; drag.y = event.clientY;
        redraw();
        return;
      }
      drag.x = event.clientX; drag.y = event.clientY;
      const card = canvas.parentElement.getBoundingClientRect();
      selection.style.left = `${Math.min(drag.startX, drag.x) - card.left}px`;
      selection.style.top = `${Math.min(drag.startY, drag.y) - card.top}px`;
      selection.style.width = `${Math.abs(drag.x - drag.startX)}px`;
      selection.style.height = `${Math.abs(drag.y - drag.startY)}px`;
      selection.hidden = false;
    });
    const stopDrag = event => {
      if (!drag || event.pointerId !== drag.id) return;
      const finished = drag;
      drag = null;
      selection.hidden = true;
      canvas.releasePointerCapture?.(event.pointerId);
      canvas.classList.remove('is-panning', 'is-selecting', 'is-measuring');
      const moved = Math.hypot(event.clientX - finished.startX, event.clientY - finished.startY) >= 4;
      if (finished.measuring) {
        if (moved) status(`Distance on the map: ${measure.text}.`, 'done');
        else clearMeasure();
        return;
      }
      // A click without moving clears the measured distance.
      if (finished.pan && !moved) clearMeasure();
      if (finished.pan || event.type !== 'pointerup' || Math.abs(event.clientX - finished.startX) < 8 || Math.abs(event.clientY - finished.startY) < 8) return;
      // The dragged rectangle fills the map.
      const [startX, startY] = pointerOffset({clientX: finished.startX, clientY: finished.startY});
      const [endX, endY] = pointerOffset(event);
      const geometry = globalThis.getCanvasMapView(canvas);
      const factor = Math.max(Math.abs(endX - startX) / geometry.width, Math.abs(endY - startY) / geometry.height);
      view = {x: view.x + (startX + endX) / 2 * view.resolution, y: view.y + (startY + endY) / 2 * view.resolution,
        resolution: clampResolution(view.resolution * factor)};
      redraw();
    };
    canvas.addEventListener('pointerup', stopDrag);
    canvas.addEventListener('pointercancel', stopDrag);
    const button = (text, title, action, className = '') => {
      const element = document.createElement('button');
      element.type = 'button'; element.className = `ni-chart-zoom-button ${className}`.trim();
      element.textContent = text; element.title = title; element.setAttribute('aria-label', title);
      element.addEventListener('click', event => { event.stopPropagation(); action(); });
      return element;
    };
    const controls = document.createElement('div');
    controls.className = `ni-chart-zoom${expanded ? ' ni-geo-zoom' : ''}`;
    controls.setAttribute('role', 'group'); controls.setAttribute('aria-label', 'Map zoom');
    controls.append(button('−', 'Zoom out', () => zoomBy(2)), level, button('+', 'Zoom in', () => zoomBy(.5)),
      button('Fit', 'Show the whole map', () => { view = {...whole}; redraw(); }, 'ni-chart-zoom-reset'));
    canvas.parentElement.append(controls);
    const controller = {
      redraw,
      current: () => current,
      fit: () => { view = {...whole}; redraw(); },
      // Centre the map on a place, showing `span` degrees of latitude above and below it.
      showArea: (longitude, latitude, span) => {
        const top = osmWorld(latitude + span, longitude, REFERENCE_ZOOM), bottom = osmWorld(latitude - span, longitude, REFERENCE_ZOOM);
        const geometry = globalThis.getCanvasMapView(canvas);
        view = {x: top[0], y: (top[1] + bottom[1]) / 2, resolution: clampResolution((bottom[1] - top[1]) / geometry.height)};
        redraw();
      },
    };
    geoMaps.set(canvas, controller);
    draw();
    return controller;
  };
  // A map with a basemap navigates; an empty map is drawn as it is.
  const showMap = (canvas, payload) => {
    if (!canvas) return;
    if (payload?.type === 'map' && payload.basemap && geoMap(canvas, payload, payload)) return;
    renderChart(canvas, payload);
  };
  document.getElementById('network-insights')?.addEventListener('dblclick', event => {
    if (event.target.closest('.ni-expand-dialog, button, a, input, select, label, .ni-chart-zoom')) return;
    const canvas = event.target.closest('.ni-chart-card')?.querySelector('canvas');
    if (canvas && chartPayloads.has(canvas)) {
      const payload = chartPayloads.get(canvas);
      const mapHeading = canvas.closest('.ni-map-card')?.querySelector('h3');
      const heading = mapHeading?.dataset.title || mapHeading?.textContent?.trim();
      const isMap = payload.type === 'map' && Boolean(payload.basemap);
      // A map keeps every site and legend entry of its analysis; the Inventory sites check still applies.
      const full = isMap ? (mapPayloads[canvas.id.replace(/^ni-/, '').replace(/-map$/, '')] || payload) : payload;
      openExpanded(isMap ? 'Map' : 'Chart', heading || payload.title || panelTitle(canvas),
        isMap ? `${panelTitle(canvas)} · drag to move, wheel or Ctrl/Cmd+drag a rectangle to zoom, Alt/Opt+drag to measure, double-click to zoom in` : panelTitle(canvas), content => {
          const card = document.createElement('div');
          card.className = 'ni-chart-card ni-expand-chart';
          const large = document.createElement('canvas');
          large.setAttribute('role', 'img');
          large.setAttribute('aria-label', canvas.getAttribute('aria-label') || 'Chart');
          card.append(large);
          content.append(card);
          if (!isMap || !geoMap(large, full, payload, {expanded: true})) renderChart(large, payload);
        }, scopeOf(canvas));
      return;
    }
    const ladder = event.target.closest('.ni-ladder');
    if (ladder?.querySelector('svg')) {
      // The dialog header shows the title of the chart and the line under it.
      const ladderHeading = ladder.querySelector('.ni-ladder-title');
      openExpanded('Chart', ladderHeading?.dataset.title || ladderHeading?.textContent || panelTitle(ladder),
        ladder.querySelector('.ni-ladder-caption')?.textContent || panelTitle(ladder), content => {
          const copy = ladder.cloneNode(true);
          copy.classList.add('ni-expand-ladder');
          copy.querySelector('.ni-ladder-head')?.remove();
          copy.querySelector('svg')?.style.removeProperty('min-width');
          content.append(copy);
        }, scopeOf(ladder));
      return;
    }
    const table = event.target.closest('table.ni-table');
    if (!table) return;
    openExpanded('Table', headingBefore(table) || panelTitle(table), panelTitle(table), content => {
      const copy = table.cloneNode(true);
      copy.querySelectorAll('.ni-column-filter').forEach(button => button.remove());
      // The actions of the table (zoom to an area) belong to the page: in the copy they are plain text.
      copy.querySelectorAll('button').forEach(button => {
        const text = document.createElement('span');
        text.className = 'ni-expand-label';
        text.textContent = button.textContent;
        button.replaceWith(text);
      });
      const wrap = document.createElement('div');
      wrap.className = 'table-wrap ni-table-wrap';
      wrap.append(copy);
      content.append(wrap);
    }, scopeOf(table));
  });
  // Floating buttons over each panel and over its charts, maps and tables (on touch screens, a tap shows them) download it
  // as a PNG image, as it is shown, or copy it to the clipboard as a screenshot, also in the larger view of a chart, map or
  // table (image_buttons.js); App Events records each one.
  const imageTables = '.ni-table-wrap:not(.ni-percentiles)';
  const imageCharts = '.ni-chart-card, .ni-map-card, .ni-ladder, .ni-percentiles, .ni-finding, .ni-operator-card, .ni-interactivity-card, .ni-kpi-grid';
  const imageHeading = heading => heading?.dataset?.title || heading?.textContent?.replace(/\s+/g, ' ').trim() || '';
  window.attachImageButtons?.({
    root: $('network-insights'), targets: `details.ni-panel, ${imageTables}, ${imageCharts}, .ni-expand-content`,
    tables: `${imageTables}, .ni-expand-content.is-table`, charts: `${imageCharts}, .ni-expand-content`,
    exclude: '.ni-chart-zoom, .ni-column-filter', obstacles: '.ni-chart-zoom, summary .summary-inline-actions',
    module: 'network-insights', fallbackName: 'Network Insights',
    // The title of its panel, then its own: the heading of a map or ladder, the name of a chart, the title above a table.
    title: target => {
      if (target.matches('.ni-expand-content')) return $('ni-expand-title')?.firstChild?.textContent?.trim();
      const own = target.matches('details') ? ''
        : target.matches('.ni-ladder') ? imageHeading(target.querySelector('.ni-ladder-title'))
          : imageHeading(target.querySelector(':scope > :is(h3, h4), :scope > header :is(h3, h4)'))
            || imageHeading(target.closest('.ni-map-card')?.querySelector(':scope > :is(h3, h4)'))
            || target.querySelector(':scope > canvas')?.getAttribute('aria-label') || (target.matches(imageTables) ? headingBefore(target) : '');
      return [...new Set([panelTitle(target), own].filter(Boolean))].join(' — ');
    },
    details: target => ({
      section: target.closest('.ni-expand-dialog') ? 'Larger view' : panelTitle(target),
      context: {theme: $('ni-theme')?.value || ''},
    }),
  });
  $('ni-expand-close')?.addEventListener('click', () => expandDialog.close());
  expandDialog?.addEventListener('click', event => { if (event.target === expandDialog) expandDialog.close(); });
  // The close event arrives after the dialog closed: a view opened meanwhile keeps its content.
  expandDialog?.addEventListener('close', () => { if (!expandDialog.open) $('ni-expand-content').replaceChildren(); });

  // Serving cells of the samples in the inventory snapshot: distances, overshooting and hosting.
  const swatch = label => `<span class="ni-swatch" style="background:${analysis?.colours?.[label] || '#6D46A8'}"></span>`;
  // A network of the inventory snapshot with its Operator Maps colour.
  const networkColour = name => snapshotPayload?.colours?.[name] || '#6D46A8';
  const networkName = name => `<span class="ni-swatch" style="background:${networkColour(name)}"></span>${escapeHtml(name)}`;
  // Each technology in its own colour (LTE, NR), wherever a table names it.
  const technologyChip = value => `<span class="ni-tech ni-tech-${String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, '-')}">${escapeHtml(value || '—')}</span>`;
  const shareBar = (value, tone = '') => value === null || value === undefined ? '—'
    : `<span class="ni-share ${tone}"><span style="width:${Math.max(0, Math.min(100, value))}%"></span></span> ${number(value)}%`;
  const pendingSnapshot = '<p class="ni-pending-box"><strong>Pending input.</strong> Upload a Multivendor Mapping or a Network Inventory (Cell Configuration KMZ packages included) in Workspace: its cells describe the serving cells of the samples.</p>';
  const breakdownTable = (title, rows, label) => `<section class="ni-mini-table"><h4>${escapeHtml(title)}</h4>
    <div class="table-wrap ni-table-wrap"><table class="ni-table"><thead><tr><th>${escapeHtml(analysis.group_label || 'All samples')}</th><th>${escapeHtml(label)}</th><th>Samples</th><th>Median km</th><th>Overshooting</th></tr></thead>
    <tbody>${rows.map(row => `<tr><td>${swatch(row.operator)}${escapeHtml(row.operator)}</td><td>${escapeHtml(row.value)}</td><td class="num">${integer(row.samples)}</td><td class="num">${number(row.median_km, 2)}</td><td class="num">${row.overshoot_share === null || row.overshoot_share === undefined ? '—' : `${number(row.overshoot_share)}%`}</td></tr>`).join('') || '<tr><td colspan="5" class="form-note">No sample was matched with an inventory cell.</td></tr>'}</tbody></table></div></section>`;
  // The NR cell of the NSA samples, found from their NR PCI and band/SSB frequency around the LTE anchor.
  const nrLegBlock = serving => {
    const leg = serving.nr_leg;
    if (!leg) return '';
    const group = escapeHtml(analysis.group_label || 'All samples');
    return `<h4>NR cell of the NSA samples <span class="form-note">(CDR Data: NR PCI and SSB NR-ARFCN of the samples anchored on LTE)</span></h4>
      <div class="table-wrap ni-table-wrap"><table class="ni-table"><thead><tr><th>${group}</th><th>Samples with NR PCI</th><th>NR cell found</th><th>On the anchor site</th><th>Only candidate nearby</th><th>Nearest of several</th><th>Median km</th><th>P90 km</th><th>NR vendors</th></tr></thead>
      <tbody>${leg.rows.map(row => `<tr><td>${swatch(row.operator)}${escapeHtml(row.operator)}</td><td class="num">${integer(row.with_nr_pci)}</td><td>${shareBar(row.found_share)}</td>
        <td class="num">${number(row.anchor_site_share)}%</td><td class="num">${number(row.only_candidate_share)}%</td><td class="num">${number(row.nearest_share)}%</td>
        <td class="num">${number(row.median_km, 2)}</td><td class="num">${number(row.p90_km, 2)}</td>
        <td>${(row.vendors || []).map(item => `${escapeHtml(item.vendor)} ${number(item.share, 0)}%`).join(' · ') || '—'}</td></tr>`).join('') || '<tr><td colspan="9" class="form-note">The selected CDRs report no NR PCI on LTE-anchored samples (only CDR Data reports it).</td></tr>'}</tbody></table></div>
      <div class="ni-breakdown-grid">${breakdownTable('By NR vendor', leg.by_vendor, 'NR vendor')}</div>
      <p class="form-note ni-note"><span>NSA CDRs only identify the LTE anchor cell. The NR cell is the one with the sample's NR PCI whose band and carrier contain its SSB frequency: on the anchor's site first (<strong>On the anchor site</strong>); otherwise the nearest one of the networks that serve the Operator, the anchor's network first, within ${number(serving.max_distance_km)} km — <strong>Only candidate nearby</strong> when no other cell of that network qualifies, <strong>Nearest of several</strong> (ambiguous) otherwise. Distances are measured from the sample to the NR cell's site.</span></p>`;
  };
  // MIMO: TX antennas of the serving cells in the snapshot against the rank and layers the samples reported.
  const mimoBlock = serving => {
    const rows = serving.mimo;
    if (!rows) return '';
    const group = escapeHtml(analysis.group_label || 'All samples');
    return `<h4>MIMO: inventory TX antennas and reported rank <span class="form-note">(CDR Data: Rank Index and NR maximum MIMO layers)</span></h4>
      <div class="table-wrap ni-table-wrap"><table class="ni-table"><thead><tr><th>${group}</th><th>Technology</th><th>TX antennas</th><th>Inventory field</th><th>Samples</th><th>Mean rank</th><th>Time per rank</th><th>Rank 2+</th><th>Mean max layers</th><th>Rank use</th></tr></thead>
      <tbody>${rows.map(row => `<tr><td>${swatch(row.operator)}${escapeHtml(row.operator)}</td><td>${technologyChip(row.technology)}</td><td>${escapeHtml(row.mimo)}</td>
        <td>${escapeHtml((row.modes || []).join(', ') || '—')}</td><td class="num">${integer(row.samples)}</td>
        <td class="num">${number(row.mean_rank, 2)}</td><td>${row.rank_classes?.length ? classBar(row.rank_classes) : '—'}</td>
        <td class="num">${row.rank2_share === null ? '—' : `${number(row.rank2_share)}%`}</td><td class="num">${number(row.mean_layers, 2)}</td>
        <td class="num">${row.rank_use === null ? '—' : `${number(row.rank_use)}%`}</td></tr>`).join('') || '<tr><td colspan="10" class="form-note">The selected CDRs report no rank for samples served by cells of the snapshot (only CDR Data reports it).</td></tr>'}</tbody></table></div>
      <p class="form-note ni-note"><span>TX antennas come from the TXRX mode (for example 4T4R, mostly Huawei cells) or the number of used TX antennas (mostly Ericsson cells) of the cell that served the sample: the LTE cell for LTE, and for NR the NR cell of SA samples or the one found for NSA samples. <strong>Not set</strong> groups the cells whose inventory gives neither. Time per rank shows the share of time at rank 1 to 4; <strong>Rank use</strong> is the mean rank divided by the TX antennas, at most 4 (the layers of the measuring device).</span></p>`;
  };
  const renderServing = () => {
    const host = $('ni-serving');
    const serving = analysis?.serving;
    if (!analysis) { host.innerHTML = '<p class="form-note">No analysis yet.</p>'; return; }
    if (!serving) { host.innerHTML = pendingSnapshot; return; }
    host.innerHTML = `<div class="ni-kpi-grid">${serving.summary.map(row => `<article class="ni-operator-card" style="--ni-operator:${analysis.colours[row.operator] || '#6D46A8'}">
        <h3>${escapeHtml(row.operator)}${row.matched ? '' : ' <span class="ni-card-flag">No inventory</span>'}</h3>
        <dl>
          <div><dt>Serving cell found</dt><dd>${number(row.matched_share)}% <small>${integer(row.matched)} of ${integer(row.with_cell)}</small></dd></div>
          <div><dt>Median distance</dt><dd>${number(row.median_km, 2)} km</dd></div>
          <div><dt>P90 distance</dt><dd>${number(row.p90_km, 2)} km</dd></div>
          <div><dt>Overshooting (&gt; ${number(serving.overshoot_km)} km)</dt><dd>${number(row.overshoot_share)}%</dd></div>
          <div><dt>Hosted by another network</dt><dd>${number(row.hosted_elsewhere_share)}%</dd></div>
          <div><dt>Samples</dt><dd>${integer(row.samples)}</dd></div>
        </dl>${row.matched ? '' : '<p class="ni-card-foot">The snapshot has no cells of the networks that serve this group: upload their Network Inventory in Workspace.</p>'}</article>`).join('')}</div>
      <div class="ni-chart-grid"><div class="ni-cdf-block"><div class="ni-chart-card"><canvas id="ni-serving-cdf" role="img" aria-label="Cumulative distribution of the distance to the serving site"></canvas></div>
        ${percentileTable('Distance to the serving site percentiles', serving.summary.map(row => ({row, values: [row.p10_km, row.median_km, row.p90_km]})), 'km', 2)}</div>
        ${serving.vendor_distance_cdf ? `<div class="ni-cdf-block"><div class="ni-chart-card"><canvas id="ni-serving-vendor-cdf" role="img" aria-label="Cumulative distribution of the distance to the serving site by RAN vendor"></canvas></div>
        ${percentileTable('Distance to the serving site by RAN vendor percentiles', (serving.vendor_distances || []).map(row => ({row, values: [row.p10_km, row.median_km, row.p90_km]})), 'km', 2, {heading: 'RAN vendor (all groups)', colours: serving.vendor_colours})}</div>` : ''}</div>
      <div class="ni-breakdown-grid">
        ${breakdownTable('By serving band', serving.by_band, 'Band')}
        ${breakdownTable('By RAN vendor', serving.by_vendor, 'Vendor')}
        ${breakdownTable('By serving network', serving.by_network || [], 'Serving Network')}
        ${breakdownTable('By host network', serving.by_host, 'Host Network')}
      </div>
      <h4>Overshooting cells <span class="form-note">(the cells that served the most samples beyond ${number(serving.overshoot_km)} km)</span></h4>
      <div class="table-wrap ni-table-wrap"><table class="ni-table"><thead><tr><th>${escapeHtml(analysis.group_label || 'All samples')}</th><th>Cell</th><th>Site</th><th>Band</th><th>Vendor</th><th>Network → Host</th><th>Samples beyond</th><th>Samples served</th><th>Median km</th><th>Max km</th></tr></thead>
      <tbody>${serving.overshooting_cells.map(row => `<tr><td>${swatch(row.operator)}${escapeHtml(row.operator)}</td><td>${escapeHtml(row.cell)}</td><td>${escapeHtml(row.site)}</td><td>${escapeHtml(row.band)}</td><td>${escapeHtml(row.vendor)}</td><td>${escapeHtml(row.network)} → ${escapeHtml(row.host)}</td><td class="num">${integer(row.samples_beyond)}</td><td class="num">${integer(row.samples)}</td><td class="num">${number(row.median_km, 2)}</td><td class="num">${number(row.max_km, 2)}</td></tr>`).join('') || `<tr><td colspan="10" class="form-note">No sample was served from farther than ${number(serving.overshoot_km)} km.</td></tr>`}</tbody></table></div>
      <p class="form-note ni-note">Cells farther than ${number(serving.max_distance_km)} km from a sample are never taken as its serving cell (Workspace Config → Serving Networks).</p>
      ${nrLegBlock(serving)}
      ${mimoBlock(serving)}`;
    renderChart($('ni-serving-cdf'), serving.distance_cdf);
    if (serving.vendor_distance_cdf) renderChart($('ni-serving-vendor-cdf'), serving.vendor_distance_cdf);
  };
  const renderNrAvailability = () => {
    const host = $('ni-nr');
    const nr = analysis?.serving?.nr_availability;
    if (!analysis) { host.innerHTML = '<p class="form-note">No analysis yet.</p>'; return; }
    if (!nr) { host.innerHTML = pendingSnapshot; return; }
    const leg = nr.rows.some(row => 'nr_found_share' in row);
    host.innerHTML = `<div class="table-wrap ni-table-wrap"><table class="ni-table"><thead><tr><th>${escapeHtml(analysis.group_label || 'All samples')}</th><th>Samples on LTE cells</th><th>On sites with NR</th><th>Without NR there</th><th>NR gap on 5G sites</th><th>Without NR on other sites</th>${leg ? '<th>NR cell found</th><th>NR on the anchor site</th><th>Median km to the NR site</th>' : ''}</tr></thead>
      <tbody>${nr.rows.map(row => `<tr><td>${swatch(row.operator)}${escapeHtml(row.operator)}</td><td class="num">${integer(row.anchored)}</td><td class="num">${integer(row.on_nr_sites)}</td><td class="num">${integer(row.without_nr_on_nr_sites)}</td><td>${shareBar(row.gap_share, 'is-warning')}</td><td>${shareBar(row.without_nr_elsewhere_share)}</td>${leg ? `<td>${shareBar(row.nr_found_share)}</td><td>${shareBar(row.nr_on_anchor_share)}</td><td class="num">${number(row.nr_median_km, 2)}</td>` : ''}</tr>`).join('') || `<tr><td colspan="${leg ? 9 : 6}" class="form-note">No sample was served by an LTE cell of the snapshot.</td></tr>`}</tbody></table></div>
      <h4>5G sites with the most samples without NR</h4>
      <div class="table-wrap ni-table-wrap"><table class="ni-table"><thead><tr><th>${escapeHtml(analysis.group_label || 'All samples')}</th><th>Site</th><th>Vendor</th><th>Samples without NR</th><th>Samples anchored there</th><th>Position</th></tr></thead>
      <tbody>${nr.sites.map(row => `<tr><td>${swatch(row.operator)}${escapeHtml(row.operator)}</td><td>${escapeHtml(row.site)}</td><td>${escapeHtml(row.vendor)}</td><td class="num">${integer(row.samples_without_nr)}</td><td class="num">${integer(row.samples)}</td><td>${row.latitude === null ? '—' : `${number(row.latitude, 4)}, ${number(row.longitude, 4)}`}</td></tr>`).join('') || '<tr><td colspan="6" class="form-note">Every sample anchored on a 5G site measured NR.</td></tr>'}</tbody></table></div>
      ${nr.nr_sites ? `<h4>NR sites serving the most NSA samples <span class="form-note">(the NR cell found for each sample, see Serving Cells)</span></h4>
      <div class="table-wrap ni-table-wrap"><table class="ni-table"><thead><tr><th>${escapeHtml(analysis.group_label || 'All samples')}</th><th>NR site</th><th>Vendor</th><th>Samples</th><th>From the anchor site</th><th>Median km</th><th>Position</th></tr></thead>
      <tbody>${nr.nr_sites.map(row => `<tr><td>${swatch(row.operator)}${escapeHtml(row.operator)}</td><td>${escapeHtml(row.site)}</td><td>${escapeHtml(row.vendor)}</td><td class="num">${integer(row.samples)}</td><td>${shareBar(row.from_anchor_share)}</td><td class="num">${number(row.median_km, 2)}</td><td>${row.latitude === null ? '—' : `${number(row.latitude, 4)}, ${number(row.longitude, 4)}`}</td></tr>`).join('') || '<tr><td colspan="7" class="form-note">No NR cell was found for the NSA samples.</td></tr>'}</tbody></table></div>` : ''}`;
  };

  // The inventory snapshot: networks, host networks, data quality, density and deployed spectrum.
  let snapshotPayload = null;
  let snapshotController = null;
  const snapshotRequest = () => ({
    snapshot: $('ni-snapshot').value,
    group: isSiteTable($('ni-deployment-group').value) ? 'host_network' : $('ni-deployment-group').value,
    in_service_only: $('ni-deployment-in-service').checked,
    technology: $('ni-deployment-technology').value,
    compare: compareSnapshot,
  });
  let compareSnapshot = '';
  const loadSnapshot = async () => {
    snapshotController?.abort();
    const controller = new AbortController();
    snapshotController = controller;
    if (!(config.snapshots || []).length) {
      snapshotPayload = null;
      renderSnapshot();
      return null;
    }
    try {
      const response = await fetch('/api/network-insights/snapshot', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(snapshotRequest()), signal: controller.signal,
      });
      const payload = await response.json();
      if (snapshotController !== controller) return null;
      if (!response.ok) throw new Error(payload.detail || 'Unable to load the inventory snapshot.');
      snapshotPayload = payload;
      renderSnapshot();
      return payload;
    } catch (error) {
      if (error.name !== 'AbortError' && snapshotController === controller) {
        $('ni-snapshot-panel').innerHTML = `<p class="form-note">${escapeHtml(error.message)}</p>`;
      }
      return null;
    }
  };
  const renderSnapshot = () => {
    const panel = $('ni-snapshot-panel');
    if (!snapshotPayload) {
      panel.innerHTML = pendingSnapshot;
      $('ni-density').innerHTML = pendingSnapshot;
      $('ni-deployed-spectrum').innerHTML = '<tbody><tr><td class="form-note">No inventory snapshot is available.</td></tr></tbody>';
      return;
    }
    const matrix = snapshotPayload.host_matrix;
    // The snapshot in use: the choice of the Analysis Selection and the file each network takes.
    const used = new Map();
    for (const item of snapshotPayload.selection) {
      const entry = used.get(item.dataset_id) || {date: item.snapshot_date, file: item.file_name, networks: []};
      entry.networks.push(item.operator);
      used.set(item.dataset_id, entry);
    }
    // The snapshots in use are not offered to compare with; a comparison with one of them is dropped.
    if (compareSnapshot && used.has(Number(compareSnapshot))) { compareSnapshot = ''; void loadSnapshot(); return; }
    const choice = $('ni-snapshot');
    const usedText = [...used.values()].map(entry => `${entry.date} · ${entry.file} (${entry.networks.join(', ')})`).join('; ');
    const inUse = `<div class="ni-snapshot-in-use"><span class="ni-snapshot-in-use-label">Snapshot in use</span>
      <strong>${escapeHtml(choice.options[choice.selectedIndex]?.textContent || 'Newest of each network')}</strong>
      <span>${[...used.values()].map(entry => `<span class="ni-snapshot-file-chip">${escapeHtml(entry.date)} · ${escapeHtml(entry.file)} <small>${escapeHtml(entry.networks.join(', '))}</small></span>`).join('')}</span>
      <span class="form-note">Change it in Launch Analysis → Inventory snapshot.</span></div>`;
    panel.innerHTML = `${inUse}<div class="ni-snapshot-cards">${snapshotPayload.selection.map(item => `<article class="ni-snapshot-card" style="--ni-operator:${snapshotPayload.colours?.[item.operator] || 'var(--ni-color)'}">
        <p class="eyebrow">${escapeHtml(item.snapshot_date)}</p><h3>${escapeHtml(item.operator)}</h3>
        <p class="ni-snapshot-file" title="${escapeHtml(item.file_name)}">${escapeHtml(item.file_name)}</p>
        <div class="ni-snapshot-counts"><div><strong>${integer(item.sites)}</strong><small>sites</small></div><div><strong>${integer(item.cells)}</strong><small>cells</small></div>
        ${Object.entries(item.technologies || {}).map(([technology, cells]) => `<div class="ni-tech-count ni-tech-count-${String(technology).toLowerCase().replace(/[^a-z0-9]+/g, '-')}"><strong>${integer(cells)}</strong><small>${escapeHtml(technology)} cells</small></div>`).join('')}</div>
        <p class="form-note">Networks: ${escapeHtml((item.networks || []).join(', ') || '—')}</p></article>`).join('')}</div>
      <h4>Owner network × host network <span class="form-note">(in-service cells and sites: the owner's cells carried by the host's equipment)</span></h4>
      <div class="table-wrap ni-table-wrap"><table class="ni-table ni-matrix"><thead><tr><th>Owner \\ Host</th>${matrix.hosts.map(hostName => `<th class="ni-network-head" style="--ni-network:${networkColour(hostName)}">${networkName(hostName)}</th>`).join('')}</tr></thead>
      <tbody>${matrix.owners.map(owner => `<tr><th>${networkName(owner)}</th>${matrix.hosts.map(hostName => {
        const cells = matrix.cells[`${owner}|${hostName}`];
        return `<td class="num${owner === hostName ? ' is-own' : ''}">${cells ? `${integer(cells)} <small>${integer(matrix.sites[`${owner}|${hostName}`])} sites</small>` : '—'}</td>`;
      }).join('')}</tr>`).join('')}</tbody></table></div>
      <h4>Inventory quality</h4>
      <div class="table-wrap ni-table-wrap"><table class="ni-table"><thead><tr><th>Network</th><th>Cells</th><th>Not in service</th><th>Locked / disabled</th><th>Without position</th><th>Without azimuth</th><th>Without band</th><th>Without vendor</th><th>Duplicate identities</th><th>Statuses</th></tr></thead>
      <tbody>${snapshotPayload.quality.map(row => `<tr><td>${networkName(row.operator)}</td><td class="num">${integer(row.cells)}</td><td class="num">${integer(row.not_in_service)}</td><td class="num">${integer(row.locked_or_disabled)}</td><td class="num">${integer(row.without_position)}</td><td class="num">${integer(row.without_azimuth)}</td><td class="num">${integer(row.without_band)}</td><td class="num">${integer(row.without_vendor)}</td><td class="num">${integer(row.duplicate_identities)}</td><td><div class="ni-status-list">${Object.entries(row.statuses || {}).map(([status, count]) => `<span>${escapeHtml(status)} <b>${integer(count)}</b></span>`).join('')}</div></td></tr>`).join('')}</tbody></table></div>
      <h4>Changes from another snapshot</h4>
      <div class="ni-map-toolbar"><div class="ni-compare-current"><span>Current snapshot</span><strong title="${escapeHtml(usedText)}">${escapeHtml(usedText)}</strong></div><label>Compare with<select id="ni-snapshot-compare"><option value="">Choose a snapshot</option>${snapshotPayload.snapshots.filter(item => !used.has(item.dataset_id)).map(item => `<option value="${item.dataset_id}"${String(item.dataset_id) === compareSnapshot ? ' selected' : ''}>${escapeHtml(item.snapshot_date)} · ${escapeHtml(item.file_name)}</option>`).join('')}</select></label></div>
      ${renderComparison(snapshotPayload.comparison)}
      <p class="form-note ni-note">${integer(snapshotPayload.snapshots.length)} snapshot${snapshotPayload.snapshots.length === 1 ? '' : 's'} in the workspace: ${snapshotPayload.snapshots.map(item => `${escapeHtml(item.snapshot_date)} · ${escapeHtml(item.file_name)} (${escapeHtml(item.networks.join(', ') || '—')})`).join('; ')}. Change the Inventory snapshot of the Analysis Selection to compare them.</p>`;
    renderDensity();
    renderDeployedSpectrum();
  };
  const renderComparison = comparison => {
    if (!comparison) return '<p class="form-note">Choose another snapshot to see the cells added and removed and the vendor swaps of every network both snapshots describe.</p>';
    if (!comparison.networks.length) return `<p class="form-note">${escapeHtml(comparison.file_name)} describes none of the networks of the current snapshot.</p>`;
    return `<p class="form-note">Current snapshot compared with ${escapeHtml(comparison.snapshot_date)} · ${escapeHtml(comparison.file_name)} (cells matched by technology and identity).</p>
      <div class="table-wrap ni-table-wrap"><table class="ni-table"><thead><tr><th>Network</th><th>Cells now</th><th>Cells then</th><th>In both</th><th>Added</th><th>Removed</th><th>Vendor changed</th><th>Sites with a vendor change</th><th>Vendor swaps</th><th>Regions with most changes</th></tr></thead>
      <tbody>${comparison.networks.map(row => `<tr><td>${networkName(row.operator)}</td><td class="num">${integer(row.cells)}</td><td class="num">${integer(row.cells_before)}</td><td class="num">${integer(row.common)}</td>
        <td class="num">${integer(row.added)}</td><td class="num">${integer(row.removed)}</td><td class="num"><strong>${integer(row.vendor_changed)}</strong></td><td class="num">${integer(row.sites_with_vendor_change)}</td>
        <td><div class="ni-status-list">${row.swaps.map(swap => `<span>${escapeHtml(swap.from)} → ${escapeHtml(swap.to)} <b>${integer(swap.cells)}</b></span>`).join('') || '—'}</div></td>
        <td><div class="ni-status-list">${row.regions.map(region => `<span>${escapeHtml(region.region)} <b>${integer(region.cells)}</b></span>`).join('') || '—'}</div></td></tr>`).join('')}</tbody></table></div>`;
  };
  document.addEventListener('change', event => {
    if (event.target.id !== 'ni-snapshot-compare') return;
    compareSnapshot = event.target.value;
    void loadSnapshot();
  });
  let densityDimension = '';
  let densityAll = false;
  const renderDensity = () => {
    const host = $('ni-density');
    const density = snapshotPayload?.density || {};
    const polygons = snapshotPayload?.polygons || [];
    $('ni-cluster-pending').hidden = polygons.length > 0;
    const available = ['cluster', 'region'].filter(key => density[key]?.length);
    if (!available.length) { host.innerHTML = '<p class="form-note">The inventory snapshot has no located sites.</p>'; return; }
    // The dimension with imported polygons (and so areas) first.
    const preferred = available.find(key => polygons.includes(key === 'cluster' ? 'clusters' : 'regions')) || available[0];
    const dimension = available.includes(densityDimension) ? densityDimension : preferred;
    const rows = density[dimension];
    // Networks in the order of the Operator Maps.
    const networkRank = name => { const index = (snapshotPayload?.network_order || []).indexOf(name); return index < 0 ? Infinity : index; };
    const networks = [...new Set(rows.map(row => row.operator))].sort((left, right) => networkRank(left) - networkRank(right) || left.localeCompare(right));
    const areas = new Map();
    for (const row of rows) {
      const area = areas.get(row.area) || {area: row.area, area_km2: row.area_km2, total: 0, networks: {}};
      area.networks[row.operator] = row;
      area.total += row.sites;
      areas.set(row.area, area);
    }
    const ordered = [...areas.values()].sort((left, right) => right.total - left.total);
    const shown = densityAll ? ordered : ordered.slice(0, 25);
    const label = dimension === 'cluster' ? 'Cluster' : 'Region';
    host.innerHTML = `<div class="ni-map-toolbar">${available.length > 1 ? `<label>Split sites by<select id="ni-density-dimension">${available.map(key => `<option value="${key}"${key === dimension ? ' selected' : ''}>${key === 'cluster' ? 'Cluster' : 'Region'}</option>`).join('')}</select></label>` : ''}
      <p class="form-note">${integer(ordered.length)} ${label.toLowerCase()}${ordered.length === 1 ? '' : 's'}${polygons.includes(dimension === 'cluster' ? 'clusters' : 'regions') ? ' from the imported polygons, with their areas' : ' from the inventory field, without areas'}; the ${shown.length < ordered.length ? `${shown.length} with the most sites are shown` : 'complete list is shown'}.</p>
      ${ordered.length > 25 ? `<button type="button" class="ni-secondary-action" id="ni-density-all">${densityAll ? 'Show the first 25' : `Show all ${integer(ordered.length)}`}</button>` : ''}</div>
      <div class="table-wrap ni-table-wrap"><table class="ni-table ni-density-table"><thead><tr><th rowspan="2">${label}</th><th rowspan="2">Area km²</th>${networks.map(network => `<th colspan="4" class="ni-density-network ni-density-start" style="--ni-network:${snapshotPayload?.colours?.[network] || 'var(--ni-color)'}">${escapeHtml(network)}</th>`).join('')}</tr>
      <tr>${networks.map(() => '<th class="ni-density-start">Sites</th><th>With NR</th><th>Sites/km²</th><th>Median ISD</th>').join('')}</tr></thead>
      <tbody>${shown.map(area => `<tr><td>${escapeHtml(area.area)}</td><td class="num">${area.area_km2 === null ? '—' : integer(Math.round(area.area_km2))}</td>${networks.map(network => {
        const row = area.networks[network];
        return row ? `<td class="num ni-density-start">${integer(row.sites)}</td><td class="num">${integer(row.nr_sites)}</td><td class="num">${row.sites_per_km2 === null ? '—' : number(row.sites_per_km2, 3)}</td><td class="num">${number(row.median_isd_km, 2)} km</td>`
          : '<td class="num ni-density-start">—</td><td class="num">—</td><td class="num">—</td><td class="num">—</td>';
      }).join('')}</tr>`).join('')}</tbody></table></div>
      <p class="form-note ni-note">Median ISD: the median distance from each in-service site to the nearest site of the same network (the inter-site distance).</p>`;
  };
  document.addEventListener('change', event => {
    if (event.target.id !== 'ni-density-dimension') return;
    densityDimension = event.target.value;
    renderDensity();
  });
  document.addEventListener('click', event => {
    if (event.target.id !== 'ni-density-all') return;
    densityAll = !densityAll;
    renderDensity();
  });
  const renderDeployedSpectrum = () => {
    const table = $('ni-deployed-spectrum');
    const rows = snapshotPayload?.spectrum || [];
    if (!rows.length) { table.innerHTML = '<tbody><tr><td class="form-note">The inventory snapshot has no in-service cells with a band.</td></tr></tbody>'; return; }
    table.innerHTML = `<thead><tr><th>Network</th><th>Technology</th><th>Band</th><th>Class</th><th>Sites</th><th>Cells</th><th>Carriers</th><th>Typical bandwidth</th><th>Deployed MHz</th><th>Channels</th></tr></thead><tbody>${rows.map(row => `<tr>
      <td>${networkName(row.operator)}</td><td>${technologyChip(row.technology)}</td><td>${escapeHtml(row.band)}</td><td>${escapeHtml(row.band_class || '—')}</td>
      <td class="num">${integer(row.sites)}</td><td class="num">${integer(row.cells)}</td><td class="num">${integer(row.carriers)}</td>
      <td class="num">${row.typical_bandwidth_mhz ? `${number(row.typical_bandwidth_mhz, 0)} MHz` : '—'}</td><td class="num">${row.deployed_mhz ? number(row.deployed_mhz, 0) : '—'}</td>
      <td>${escapeHtml((row.channels || []).join(', '))}</td></tr>`).join('')}</tbody>`;
  };
  const csvValue = value => {
    const text = String(value ?? '');
    return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
  };
  const downloadCsv = (name, rows) => {
    const url = URL.createObjectURL(new Blob([rows.map(row => row.map(csvValue).join(',')).join('\n') + '\n'], {type: 'text/csv'}));
    const link = document.createElement('a');
    link.href = url; link.download = name;
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const deploymentCsvRows = tables => [['Operator', snapshotPayload.group_label, 'Sites', 'Cells', 'LTE Cells', 'NR Cells'],
    ...tables.flatMap(table => table.rows.map(row => [table.operator, row.group, row.sites, row.cells, row.lte_cells, row.nr_cells]))];
  const renderDeploymentTables = () => {
    const host = $('ni-deployment');
    const tables = snapshotPayload?.deployment || [];
    $('ni-deployment-export-all').disabled = !tables.length;
    if (!tables.length) { host.innerHTML = snapshotPayload ? '<p class="form-note">No cell of the snapshot matches the Technology and status choices.</p>' : pendingSnapshot; return; }
    host.innerHTML = tables.map((table, index) => {
      const maximum = table.rows.reduce((value, row) => Math.max(value, row.sites), 1);
      return `<section class="ni-inventory ni-network-table" style="--ni-operator:${snapshotPayload.colours?.[table.operator] || 'var(--ni-color)'}"><header class="ni-section-head"><h3><span class="ni-network-name"><span class="ni-swatch"></span>${escapeHtml(table.operator)}</span> <span>${integer(table.totals.sites)} sites · ${integer(table.totals.cells)} cells (${integer(table.totals.lte_cells)} LTE, ${integer(table.totals.nr_cells)} NR)</span></h3>
        <button type="button" class="ni-secondary-action ni-export-action" data-ni-deployment-csv="${index}">Export CSV</button></header>
        <div class="table-wrap ni-table-wrap"><table class="ni-table"><thead><tr><th>${escapeHtml(table.group_label)}</th><th>Sites</th><th>Cells</th><th>LTE cells</th><th>NR cells</th><th></th></tr></thead><tbody>${table.rows.map(row => `<tr>
          <td>${escapeHtml(row.group)}</td><td class="num">${integer(row.sites)}</td><td class="num">${integer(row.cells)}</td><td class="num">${integer(row.lte_cells)}</td><td class="num">${integer(row.nr_cells)}</td>
          <td><span class="ni-share"><span style="width:${row.sites / maximum * 100}%"></span></span></td></tr>`).join('')}</tbody></table></div></section>`;
    }).join('');
  };
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-ni-deployment-csv]');
    if (!button || !snapshotPayload) return;
    const table = snapshotPayload.deployment[Number(button.dataset.niDeploymentCsv)];
    if (table) downloadCsv(`network-deployment-${snapshotPayload.group}_${table.operator}.csv`, deploymentCsvRows([table]));
  });

  // Sites/Cells tables: complete inventories or cells observed in the CDRs.
  const siteTableTitle = source => source === 'observed' ? 'Observed Sites/Cells (from CDRs)' : 'Full Sites/Cells Inventory';
  const renderInventory = inventory => {
    const lastPage = Math.max(0, Math.ceil(inventory.total_rows / inventory.page_size) - 1);
    const filters = inventory.filters || {};
    const active = Object.keys(filters).length;
    return `<section class="ni-inventory" data-ni-inventory="${escapeHtml(inventory.operator)}" data-ni-operator-label="${escapeHtml(inventory.operator_label || inventory.operator)}" data-ni-source="${escapeHtml(inventory.source || 'inventory')}" data-ni-filters="${escapeHtml(JSON.stringify(filters))}">
      <h3>${escapeHtml(inventory.operator_label || inventory.operator)} · ${siteTableTitle(inventory.source)}</h3>
      <div class="ni-map-toolbar">
        <button type="button" class="ni-secondary-action ni-export-action" data-ni-inventory-export>Export CSV</button>
        ${active ? `<button type="button" class="ni-secondary-action" data-ni-filters-clear>Clear ${integer(active)} filter${active === 1 ? '' : 's'}</button>` : ''}
        <button type="button" class="ni-secondary-action ni-page-action" data-ni-inventory-page="${inventory.page - 1}" ${inventory.page === 0 ? 'disabled' : ''}>Previous</button>
        <span class="form-note">Page ${integer(inventory.page + 1)} of ${integer(lastPage + 1)} · ${integer(inventory.total_rows)} rows · ${integer(inventory.columns.length)} columns</span>
        <button type="button" class="ni-secondary-action ni-page-action" data-ni-inventory-page="${inventory.page + 1}" ${inventory.page >= lastPage ? 'disabled' : ''}>Next</button>
      </div>
      <div class="table-wrap ni-table-wrap"><table class="ni-table"><thead><tr>${inventory.columns.map(column => `<th${inventory.key_columns.includes(column) ? ' class="ni-inventory-key-column"' : ''}><span class="ni-column-head">${escapeHtml(column)}<button type="button" class="ni-column-filter${filters[column] ? ' is-active' : ''}" data-ni-filter-column="${escapeHtml(column)}" title="Filter ${escapeHtml(column)}" aria-label="Filter ${escapeHtml(column)}">▾</button></span></th>`).join('')}</tr></thead>
      <tbody>${inventory.rows.map(row => `<tr>${row.map((value, index) => `<td${inventory.key_columns.includes(inventory.columns[index]) ? ' class="ni-inventory-key-column"' : ''}>${escapeHtml(value ?? '')}</td>`).join('')}</tr>`).join('') || `<tr><td colspan="${inventory.columns.length || 1}" class="form-note">${active ? 'No rows match the column filters.' : 'No rows.'}</td></tr>`}</tbody></table></div>
    </section>`;
  };

  let inventorySelection = null;
  let displayedDeploymentGroup = '';
  const isSiteTable = group => group === 'inventory' || group === 'observed';
  const cardFilters = card => { try { return JSON.parse(card.dataset.niFilters || '{}'); } catch { return {}; } };
  const fileName = response => {
    const disposition = response.headers.get('content-disposition') || '';
    const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition);
    return match ? decodeURIComponent(match[1]) : '';
  };
  const downloadDeploymentCsv = async (button, operator = '', filters = {}) => {
    if (button.disabled) return;
    const selection = inventorySelection;
    const group = displayedDeploymentGroup;
    button.disabled = true;
    try {
      if (!isSiteTable(group)) {
        downloadCsv(`network-deployment-${group}_all.csv`, deploymentCsvRows(snapshotPayload?.deployment || []));
        return;
      }
      const response = await fetch('/api/network-insights/sites/export', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({...selection, operator, filters}),
      });
      if (!response.ok) {
        const payload = await response.json();
        throw new Error(payload.detail || 'Unable to export the deployment tables.');
      }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url;
      link.download = fileName(response) || `network-deployment-${group}.csv`;
      document.body.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      $('ni-deployment-status').textContent = error.message;
    } finally {
      if (displayedDeploymentGroup === group && !deploymentController?.signal.aborted) button.disabled = false;
    }
  };
  // Reload one table with its page and column filters.
  const reloadSiteTable = async (card, page, filters) => {
    const controller = deploymentController;
    const controls = [...card.querySelectorAll('button')].map(control => [control, control.disabled]);
    controls.forEach(([control]) => { control.disabled = true; });
    try {
      const response = await fetch('/api/network-insights/sites/page', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, signal: controller.signal,
        body: JSON.stringify({...inventorySelection, operator: card.dataset.niInventory, page, filters}),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || 'Unable to load the table page.');
      if (deploymentController === controller && card.isConnected) {
        card.outerHTML = renderInventory({...payload, operator_label: card.dataset.niOperatorLabel});
      }
    } catch (error) {
      if (error.name !== 'AbortError' && deploymentController === controller && card.isConnected) {
        $('ni-deployment-status').textContent = error.message;
        controls.forEach(([control, disabled]) => { control.disabled = disabled; });
      }
    }
  };

  // Excel-style column filter: the values of the column under the other filters.
  let filterMenu = null;
  let placeFilterMenu = null;
  const closeFilterMenu = () => { filterMenu?.remove(); filterMenu = null; placeFilterMenu = null; };
  const openFilterMenu = async (card, button) => {
    closeFilterMenu();
    const column = button.dataset.niFilterColumn;
    const filters = cardFilters(card);
    const menu = document.createElement('section');
    menu.className = 'excel-column-filter-menu ni-filter-menu';
    menu.setAttribute('role', 'dialog');
    menu.setAttribute('aria-label', `Filter ${column}`);
    menu.innerHTML = `<p class="form-note">Loading values of ${escapeHtml(column)}…</p>`;
    document.body.append(menu);
    filterMenu = menu;
    // The menu is fixed to the viewport: place it under its column button again on every scroll.
    const place = () => {
      const bounds = button.getBoundingClientRect();
      if (!button.isConnected || bounds.bottom < 0 || bounds.top > window.innerHeight) { closeFilterMenu(); return; }
      const width = Math.min(300, window.innerWidth - 20);
      menu.style.width = `${width}px`;
      menu.style.left = `${Math.max(10, Math.min(bounds.left, window.innerWidth - width - 10))}px`;
      const below = bounds.bottom + 5;
      const height = menu.offsetHeight;
      menu.style.top = `${below + height <= window.innerHeight - 10 ? below : Math.max(10, bounds.top - height - 5)}px`;
    };
    placeFilterMenu = place;
    place();
    try {
      const response = await fetch('/api/network-insights/sites/values', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({...inventorySelection, operator: card.dataset.niInventory, filters, column}),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || 'Unable to load the column values.');
      if (filterMenu !== menu) return;
      const selected = new Set(filters[column] || payload.values.map(item => item.value));
      menu.innerHTML = `<strong class="ni-filter-title">${escapeHtml(column)}</strong>
        <input type="search" placeholder="Search values" autocomplete="off" aria-label="Search values of ${escapeHtml(column)}">
        <div class="excel-column-filter-toolbar"><button type="button" data-ni-filter-all>Select all</button><button type="button" data-ni-filter-none>Clear</button></div>
        <div class="excel-column-filter-options">${payload.values.map(item => `<label><input type="checkbox" value="${escapeHtml(item.value)}" ${selected.has(item.value) ? 'checked' : ''}><span>${item.value === '' ? '(Blanks)' : escapeHtml(item.value)}</span><small>${integer(item.count)}</small></label>`).join('') || '<p class="form-note">No values.</p>'}</div>
        ${payload.truncated ? '<p class="form-note">Showing the first 2,000 values; search to narrow them.</p>' : ''}
        <div class="excel-column-filter-footer"><button type="button" data-ni-filter-cancel>Cancel</button><button type="button" data-ni-filter-reset>Remove filter</button><button type="button" data-ni-filter-apply>Apply</button></div>`;
      place();
      const boxes = () => [...menu.querySelectorAll('.excel-column-filter-options input')];
      const visible = () => boxes().filter(box => !box.closest('label').hidden);
      const search = menu.querySelector('input[type="search"]');
      // Typing filters the listed values; Select all and Clear act on the listed values.
      search.addEventListener('input', () => {
        const query = search.value.trim().toLocaleLowerCase();
        boxes().forEach(box => {
          const text = box.closest('label').querySelector('span').textContent.toLocaleLowerCase();
          box.closest('label').hidden = Boolean(query) && !text.includes(query);
        });
      });
      menu.querySelector('[data-ni-filter-all]').addEventListener('click', () => visible().forEach(box => { box.checked = true; }));
      menu.querySelector('[data-ni-filter-none]').addEventListener('click', () => visible().forEach(box => { box.checked = false; }));
      menu.querySelector('[data-ni-filter-cancel]').addEventListener('click', closeFilterMenu);
      menu.querySelector('[data-ni-filter-reset]').addEventListener('click', () => {
        delete filters[column];
        closeFilterMenu();
        void reloadSiteTable(card, 0, filters);
      });
      menu.querySelector('[data-ni-filter-apply]').addEventListener('click', () => {
        const chosen = boxes().filter(box => box.checked).map(box => box.value);
        if (chosen.length === boxes().length && !payload.truncated) delete filters[column];
        else filters[column] = chosen;
        closeFilterMenu();
        void reloadSiteTable(card, 0, filters);
      });
      requestAnimationFrame(() => search.focus());
    } catch (error) {
      if (filterMenu === menu) menu.innerHTML = `<p class="form-note">${escapeHtml(error.message)}</p>`;
    }
  };
  document.addEventListener('pointerdown', event => {
    if (filterMenu && !filterMenu.contains(event.target) && !event.target.closest('[data-ni-filter-column]')) closeFilterMenu();
  });
  document.addEventListener('keydown', event => { if (event.key === 'Escape') closeFilterMenu(); });
  window.addEventListener('resize', closeFilterMenu);
  document.addEventListener('scroll', event => {
    if (placeFilterMenu && !filterMenu?.contains(event.target)) placeFilterMenu();
  }, {capture: true, passive: true});

  $('ni-deployment-export-all').addEventListener('click', event => { void downloadDeploymentCsv(event.currentTarget); });
  $('ni-deployment').addEventListener('click', async event => {
    const card = event.target.closest('[data-ni-inventory]');
    if (!card || !inventorySelection) return;
    const filterButton = event.target.closest('[data-ni-filter-column]');
    if (filterButton) { void openFilterMenu(card, filterButton); return; }
    if (event.target.closest('[data-ni-filters-clear]')) { void reloadSiteTable(card, 0, {}); return; }
    const exportButton = event.target.closest('[data-ni-inventory-export]');
    if (exportButton) {
      void downloadDeploymentCsv(exportButton, card.dataset.niInventory, cardFilters(card));
      return;
    }
    const button = event.target.closest('[data-ni-inventory-page]');
    if (!button || button.disabled) return;
    void reloadSiteTable(card, Number(button.dataset.niInventoryPage), cardFilters(card));
  });

  let deploymentController = null;
  const loadDeployment = async () => {
    deploymentController?.abort();
    const controller = new AbortController();
    deploymentController = controller;
    const group = $('ni-deployment-group').value;
    const host = $('ni-deployment');
    const note = $('ni-deployment-status');
    $('ni-deployment-export-all').disabled = true;
    inventorySelection = null;
    document.querySelectorAll('[data-ni-deployment-filter]').forEach(element => { element.hidden = isSiteTable(group); });
    if (!isSiteTable(group)) {
      displayedDeploymentGroup = group;
      note.textContent = 'Loading the inventory snapshot…';
      const payload = await loadSnapshot();
      if (deploymentController !== controller) return;
      renderDeploymentTables();
      note.textContent = payload
        ? `Distinct sites and cells of each owner network in the inventory snapshot${payload.in_service_only ? ' (in service only)' : ''}. Host Network shows whose equipment carries the cells; Region and Cluster use the imported polygons when there are any.`
        : '';
      return;
    }
    if (!(config.inventories || []).length && group === 'inventory') {
      host.innerHTML = '<p class="ni-pending-box"><strong>Pending input.</strong> Upload the Vodafone or Three cell inventories as Vendor mapping datasets in Workspace to list their complete rows.</p>';
      return;
    }
    note.textContent = 'Loading the cell inventories…';
    host.querySelectorAll('button').forEach(button => { button.disabled = true; });
    const timeout = setTimeout(() => controller.abort(), 120000);
    try {
      const selection = isSiteTable(group) ? {...requestBody(), source: group} : null;
      const response = isSiteTable(group)
        ? await fetch('/api/network-insights/sites/tables', {
          method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(selection), signal: controller.signal,
        })
        : await fetch(`/api/network-insights/deployment?group=${encodeURIComponent(group)}`, {signal: controller.signal});
      const payload = await response.json();
      if (deploymentController !== controller) return;
      if (!response.ok) throw new Error(payload.detail || 'Unable to load the cell inventories.');
      displayedDeploymentGroup = group;
      if (isSiteTable(group)) {
        inventorySelection = selection;
        $('ni-deployment-export-all').disabled = !payload.tables.length;
        host.innerHTML = payload.tables.map(renderInventory).join('') || '<p class="form-note">No table matches the selected operators.</p>';
        note.textContent = group === 'observed'
          ? 'Sites and LTE cells observed in the selected CDRs, filtered by the Analysis Selection (CDRs, Operator, Operator_Vendor, Vendor, Region, Cluster, City and Campaign). Use ▾ on a column to filter it; CSV exports every matching row.'
          : 'Complete uploaded inventories, filtered by Operator, Operator_Vendor, Vendor, Region, Cluster, City and Technology. CDR selection, NR Mode and Campaigns do not restrict inventory rows. Use ▾ on a column to filter it; CSV exports every matching row and column.';
        return;
      }
      $('ni-deployment-export-all').disabled = !payload.inventories.length;
      inventorySelection = null;
      host.innerHTML = payload.inventories.map(inventory => {
        const maximum = inventory.rows.reduce((maximum, row) => Math.max(maximum, row.sites), 1);
        const available = inventory.available_groups.includes(group);
        return `<section class="ni-inventory"><h3>${escapeHtml(inventory.operator)} <span>${escapeHtml(inventory.file_name)}</span></h3>
          <a class="ghost-link ni-export-action" href="/api/network-insights/deployment/${inventory.id}/export?group=${encodeURIComponent(group)}" download>Export CSV</a>
          ${available ? '' : `<p class="form-note">This inventory has no ${escapeHtml(payload.group_label)} column; totals are shown instead.</p>`}
          <table class="ni-table"><thead><tr><th>${escapeHtml(available ? payload.group_label : 'Inventory')}</th><th>Sites</th><th>Cells</th><th></th></tr></thead><tbody>${inventory.rows.map(row => `<tr>
            <td>${escapeHtml(row.group)}</td><td class="num">${integer(row.sites)}</td><td class="num">${integer(row.cells)}</td>
            <td><span class="ni-share"><span style="width:${row.sites / maximum * 100}%"></span></span></td></tr>`).join('')}</tbody></table></section>`;
      }).join('');
      note.textContent = 'Sites and cells counted from the uploaded cell inventories (distinct site and cell identifiers).';
    } catch (error) {
      if (deploymentController !== controller) return;
      note.textContent = error.name === 'AbortError'
        ? 'Loading the inventories timed out. Change the grouping or try again.' : error.message;
    } finally {
      clearTimeout(timeout);
    }
  };

  const loadClusterInventories = async () => {
    try {
      const response = await fetch('/api/network-insights/cluster-inventories');
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || 'Unable to load site inventories.');
      clusterInventories = payload;
      $('ni-inventory-totals').innerHTML = payload.rows.map(row =>
        `<article class="ni-inventory-total"><span>${escapeHtml(row.operator)} inventory</span><div class="ni-inventory-site-count"><strong>${integer(row.sites)}</strong><small>sites</small></div><small>${integer(row.cells)} cells</small></article>`).join('');
      renderSites();
    } catch (error) {
      if ($('ni-sites-source').value === 'inventory') $('ni-sites-table').innerHTML = `<tbody><tr><td class="form-note">${escapeHtml(error.message)}</td></tr></tbody>`;
    }
  };
  $('ni-sites-source').onchange = () => { renderSites(); if (!clusterInventories) void loadClusterInventories(); };
  renderSites();
  void loadClusterInventories();

  const rememberSelection = () => {
    const filters = Object.fromEntries(filterNames.map(field => {
      const id = `ni-${field}`;
      return [id, $(id).options.length && !pendingFilterRestore.has(id) ? filterValues(id) : savedSelection.filters?.[id] || []];
    }));
    savedSelection = {
      controls: Object.fromEntries(selectionControls.map(id => [id,
        $(id).multiple ? selectedValues(id) : $(id).value])),
      filters,
      map_group: $('ni-map-operator').value || savedSelection.map_group || '',
    };
    try { if (storageKey) localStorage.setItem(storageKey, JSON.stringify(savedSelection)); } catch {}
  };
  $('network-insights').addEventListener('change', rememberSelection);
  let inventoryRefreshTimer = null;
  const refreshInventory = () => {
    if (!isSiteTable($('ni-deployment-group').value)) return;
    clearTimeout(inventoryRefreshTimer);
    deploymentController?.abort();
    $('ni-deployment-export-all').disabled = true;
    $('ni-deployment').querySelectorAll('button').forEach(button => { button.disabled = true; });
    inventoryRefreshTimer = setTimeout(() => { void loadDeployment(); }, 150);
  };
  $('network-insights').addEventListener('change', event => {
    if (event.target.closest('.ni-selection-panel')) { refreshInventory(); scheduleNrDuplex(); }
  });

  $('ni-technology').onchange = syncTechnologyGrouping;
  $('ni-nr-mode').onchange = () => { renderAutoCdrs(null); scheduleFilterOptions(); };
  // Each filter narrows the lists of the others (and the Campaign chooses the CDRs).
  for (const field of filterNames) $(`ni-${field}`).addEventListener('change', scheduleFilterOptions);
  // Keep the map Operator across analyses when it is still part of the selection.
  $('ni-analyse').onclick = () => { void analyse($('ni-map-operator').value || savedSelection.map_group || ''); };
  $('ni-map-operator').onchange = () => { void analyse($('ni-map-operator').value || savedSelection.map_group || ''); };
  $('ni-map-reset').onclick = () => {
    for (const kind of Object.keys(mapPayloads)) geoMaps.get($(`ni-${kind}-map`))?.fit();
    if (analysis) $('ni-map-note').textContent = `${analysis.maps.operator} · whole area.`;
  };
  document.addEventListener('click', event => {
    const button = event.target.closest('.ni-zoom');
    if (button) zoomMap(button.dataset.kind, Number(button.dataset.latitude), Number(button.dataset.longitude));
  });
  $('ni-deployment-group').onchange = () => { void loadDeployment(); };
  $('ni-deployment-technology').onchange = () => { void loadDeployment(); };
  $('ni-deployment-in-service').onchange = () => { void loadDeployment(); };
  $('ni-snapshot').addEventListener('change', () => {
    void loadDeployment();
    if (analysis) status('The inventory snapshot changed: press Analyse Network to apply it to the serving cells of the samples.');
  });
  // Reloading the page keeps its scroll position. The panels arrive after the page loads (the stored analysis, the
  // snapshot and the deployment), so the position is applied again as the page grows, until the user moves it.
  const scrollKey = 'drivetest-analyzer:/network-insights:scroll';
  let savedScroll = 0;
  try { history.scrollRestoration = 'manual'; savedScroll = Number(sessionStorage.getItem(scrollKey)) || 0; } catch {}
  let followingScroll = savedScroll > 0;
  const rememberScroll = () => { try { sessionStorage.setItem(scrollKey, String(followingScroll ? savedScroll : window.scrollY)); } catch {} };
  let scrollTimer = 0;
  window.addEventListener('scroll', () => { if (!followingScroll) { clearTimeout(scrollTimer); scrollTimer = setTimeout(rememberScroll, 200); } }, {passive: true});
  window.addEventListener('pagehide', rememberScroll);
  if (followingScroll) {
    const growth = 'ResizeObserver' in window ? new ResizeObserver(() => { if (followingScroll) window.scrollTo(0, savedScroll); }) : null;
    const stopFollowing = () => { followingScroll = false; growth?.disconnect(); };
    for (const type of ['wheel', 'touchmove', 'keydown', 'pointerdown']) window.addEventListener(type, stopFollowing, {once: true, passive: true});
    growth?.observe(document.body);
    window.scrollTo(0, savedScroll);
    setTimeout(stopFollowing, 15000);
  }
  renderAutoCdrs(null);
  // -- favourite Analysis Selections, kept in the workspace ------------------------------------------------------
  // Opening one makes it the selection of the page and analyses it (at once when the analysis is stored).
  const FAVOURITE_OPENED = 'network-insights:favourite-opened';
  let favourites = Array.isArray(config.favourites) ? config.favourites : [];
  const favouriteStatus = (message, tone = '') => {
    const element = $('ni-favourite-status');
    element.textContent = message || '';
    element.dataset.tone = tone;
  };
  const renderFavourites = (selected = '') => {
    const select = $('ni-favourite');
    select.replaceChildren(new Option('Current selection', ''), ...favourites.map(item => new Option(item.name, String(item.id))));
    select.value = favourites.some(item => String(item.id) === String(selected)) ? String(selected) : '';
    $('ni-favourite-delete').disabled = !select.value || !config.can_edit;
    $('ni-favourite-rename').disabled = $('ni-favourite-delete').disabled;
    $('ni-favourite-save').disabled = !config.can_edit;
  };
  let openedFavourite = '';
  try { openedFavourite = sessionStorage.getItem(FAVOURITE_OPENED) || ''; sessionStorage.removeItem(FAVOURITE_OPENED); } catch {}
  const chosenFavourite = favourites.find(item => String(item.id) === openedFavourite);
  // The choices and filters of a selection, to tell whether the page opens with those of a favourite: the controls the
  // favourite keeps (a control added since it was saved is left out) and every filter, in any order.
  const sameSelection = (favourite, selection) => {
    const values = value => (Array.isArray(value) ? value : value === undefined || value === null || value === '' ? [] : [value])
      .map(String).sort().join('|');
    const controls = favourite?.controls || {};
    const filters = new Set([...Object.keys(favourite?.filters || {}), ...Object.keys(selection?.filters || {})]);
    return Object.keys(controls).every(id => values(controls[id]) === values(selection?.controls?.[id]))
      && [...filters].every(id => values(favourite?.filters?.[id]) === values(selection?.filters?.[id]));
  };
  // A reload keeps the favourite the page opens with: the one just opened, else one with the same choices and filters,
  // so the selector does not fall back to Current selection.
  const shownFavourite = chosenFavourite || favourites.find(item => sameSelection(item.selection, savedSelection));
  renderFavourites(shownFavourite ? String(shownFavourite.id) : '');
  if (shownFavourite) $('ni-favourite-name').value = shownFavourite.name;
  $('ni-favourite').addEventListener('change', async () => {
    const favourite = favourites.find(item => String(item.id) === $('ni-favourite').value);
    $('ni-favourite-delete').disabled = !favourite || !config.can_edit;
    $('ni-favourite-rename').disabled = $('ni-favourite-delete').disabled;
    if (!favourite) return;
    try {
      await fetch(`/api/network-insights/favourites/${favourite.id}/open`, {method: 'POST', credentials: 'same-origin'});
      if (storageKey) {
        localStorage.setItem(storageKey, JSON.stringify(favourite.selection));
        localStorage.removeItem(`${storageKey}:last-analysis:selection`);
        localStorage.removeItem(`${storageKey}:last-analysis`);
      }
      sessionStorage.setItem(FAVOURITE_OPENED, String(favourite.id));
    } catch {}
    location.reload();
  });
  $('ni-favourite-save').addEventListener('click', async () => {
    const name = $('ni-favourite-name').value.trim();
    if (!name) { favouriteStatus('Enter a name for the favourite.', 'error'); $('ni-favourite-name').focus(); return; }
    rememberSelection();
    const selected = favourites.find(item => String(item.id) === $('ni-favourite').value);
    // The chosen favourite is updated when its name is kept; another name saves a new favourite.
    const update = selected && selected.name.toLocaleLowerCase() === name.toLocaleLowerCase();
    try {
      const response = await fetch(update ? `/api/network-insights/favourites/${selected.id}` : '/api/network-insights/favourites', {
        method: update ? 'PUT' : 'POST', headers: {'Content-Type': 'application/json'}, credentials: 'same-origin',
        body: JSON.stringify({name, selection: savedSelection}),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || 'Unable to save the favourite.');
      favourites = payload.favourites;
      renderFavourites(payload.favourite.id);
      favouriteStatus(`${payload.favourite.name} saved as a favourite.`, 'done');
    } catch (error) {
      favouriteStatus(error.message, 'error');
    }
  });
  // Renaming keeps the selection the favourite saved (not the changes of the panel), as the favourites of Reporting.
  $('ni-favourite-rename').addEventListener('click', async () => {
    const selected = favourites.find(item => String(item.id) === $('ni-favourite').value);
    if (!selected) return;
    const answer = typeof window.showTextInputDialog === 'function'
      ? await window.showTextInputDialog('New name', {title: 'Rename Favourite', value: selected.name, maxLength: 120, confirmLabel: 'Rename', cancelLabel: 'Cancel'})
      : window.prompt('New name of the favourite Analysis Selection', selected.name);
    const name = String(answer ?? '').trim();
    if (!name || name === selected.name) return;
    try {
      const response = await fetch(`/api/network-insights/favourites/${selected.id}/rename`, {
        method: 'POST', headers: {'Content-Type': 'application/json'}, credentials: 'same-origin', body: JSON.stringify({name}),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || 'Unable to rename the favourite.');
      favourites = payload.favourites;
      renderFavourites(payload.favourite.id);
      $('ni-favourite-name').value = payload.favourite.name;
      favouriteStatus(`${selected.name} renamed to ${payload.favourite.name}.`, 'done');
    } catch (error) {
      favouriteStatus(error.message, 'error');
    }
  });
  $('ni-favourite-delete').addEventListener('click', async () => {
    const selected = favourites.find(item => String(item.id) === $('ni-favourite').value);
    if (!selected) return;
    const confirmed = typeof window.showConfirmDialog === 'function'
      ? Boolean(await window.showConfirmDialog('', {title: 'Delete Favourite', copyHtml: `<p>Delete the favourite Analysis Selection <strong>${escapeHtml(selected.name)}</strong>?</p>`,
        confirmLabel: 'Delete', cancelLabel: 'Cancel'}))
      : window.confirm(`Delete the favourite Analysis Selection ${selected.name}?`);
    if (!confirmed) return;
    try {
      const response = await fetch(`/api/network-insights/favourites/${selected.id}`, {method: 'DELETE', credentials: 'same-origin'});
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || 'Unable to delete the favourite.');
      favourites = payload.favourites;
      renderFavourites('');
      $('ni-favourite-name').value = '';
      favouriteStatus(`${selected.name} deleted.`, 'done');
    } catch (error) {
      favouriteStatus(error.message, 'error');
    }
  });

  applyTheme();
  // Another theme colours the page at once and is kept for the next visit and the exports.
  $('ni-theme').addEventListener('change', () => {
    const theme = themes.find(item => item.id === $('ni-theme').value);
    if (!theme || theme.id === activeTheme.id) return;
    activeTheme = theme;
    applyTheme();
    render();
    fetch('/api/network-insights/theme', {
      method: 'PUT', credentials: 'same-origin', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({theme: theme.id}),
    }).catch(() => {});
  });

  void loadFilterOptions().then(() => {
    // A favourite just opened is analysed (its stored analysis, when there is one, is shown at once).
    if (chosenFavourite) void analyse();
    else showLastAnalysis();
    void loadNrDuplex();
  });
  void loadDeployment();
  // The site tables do not read the snapshot: the Snapshot, density and spectrum panels still need it.
  if (isSiteTable($('ni-deployment-group').value)) void loadSnapshot();
})();
