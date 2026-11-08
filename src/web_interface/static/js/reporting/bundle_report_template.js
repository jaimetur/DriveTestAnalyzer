/* Reporting: the Reports tab. The reports as cards (what each includes, its schedule and its last run), the editor of a
   report in steps (its cover, common filters, five sections with their sub-modules, charts and tables, checked and
   ordered by dragging, and its schedule), and the dialog that follows a report being generated and previews every
   page of a run before the download. */
(() => {
  'use strict';

  const root = document.getElementById('bundle-report-template');
  if (!root) return;
  const $ = (id) => document.getElementById(id);
  const node = (tag, text, className) => {
    const element = document.createElement(tag);
    if (text !== undefined && text !== null) element.textContent = text;
    if (className) element.className = className;
    return element;
  };
  const clone = (value) => JSON.parse(JSON.stringify(value));
  const api = async (url, init = {}) => {
    const response = await fetch(url, {credentials: 'same-origin', ...init,
      headers: init.body ? {'Content-Type': 'application/json', ...(init.headers || {})} : init.headers});
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'The request failed.');
    return payload;
  };
  const DRAFT_KEY = 'reporting:bundle-report-template:draft';
  const COLLAPSED_KEY = (key) => `reporting:bundle-report-template:collapsed:${key}`;
  const FILTERS = [['operators', 'Operators', 'Operator'], ['operator_vendors', 'Operator_Vendor', 'Operator_Vendor'],
    ['vendor_operators', 'Vendor_Operator', 'Vendor_Operator'], ['vendors', 'Vendors', 'Vendor'], ['regions', 'Regions', 'Region'],
    ['clusters', 'Clusters', 'Cluster'], ['cities', 'Cities', 'City']];
  const NI_ENVIRONMENTS = ['Cities', 'Towns', 'Roads and railways'];

  let options = null;
  let brtOptions = null;
  let definition = null;
  let filterPickers = {};
  let favourites = [];
  let pollTimer = null;
  // The run shown in the preview dialog (see jobFromRun).
  let currentJob = null;

  const status = (message, tone = '') => {
    const element = $('brt-status');
    element.textContent = message || '';
    element.dataset.tone = tone;
  };
  const pickers = () => window.reportingPickers || {};
  const readFlag = (key) => { try { return localStorage.getItem(key) === '1'; } catch { return false; } };
  const writeFlag = (key, value) => { try { if (value) localStorage.setItem(key, '1'); else localStorage.removeItem(key); } catch {} };

  // -- ordering by dragging (pointer, touch and keyboard) ---------------------------------
  function sortable(list, itemSelector, handleSelector, onChange) {
    list.addEventListener('pointerdown', (event) => {
      const handle = event.target.closest(handleSelector);
      const item = handle?.closest(itemSelector);
      if (!handle || !item || item.parentElement !== list) return;
      event.preventDefault();
      try { handle.setPointerCapture?.(event.pointerId); } catch {}
      item.classList.add('is-dragging');
      list.classList.add('is-sorting');
      const move = (moveEvent) => {
        if (moveEvent.clientY < 70) window.scrollBy(0, -14);
        else if (moveEvent.clientY > window.innerHeight - 70) window.scrollBy(0, 14);
        const others = [...list.children].filter((element) => element !== item && element.matches(itemSelector));
        const next = others.find((element) => {
          const box = element.getBoundingClientRect();
          return moveEvent.clientY < box.top + box.height / 2;
        });
        if (next) {
          if (item.nextElementSibling !== next) list.insertBefore(item, next);
        } else if (list.lastElementChild !== item) {
          list.append(item);
        }
      };
      // The window follows the pointer, captured by the handle or not.
      const stop = () => {
        window.removeEventListener('pointermove', move);
        window.removeEventListener('pointerup', stop);
        window.removeEventListener('pointercancel', stop);
        item.classList.remove('is-dragging');
        list.classList.remove('is-sorting');
        onChange();
      };
      window.addEventListener('pointermove', move);
      window.addEventListener('pointerup', stop);
      window.addEventListener('pointercancel', stop);
    });
    list.addEventListener('keydown', (event) => {
      const handle = event.target.closest(handleSelector);
      const item = handle?.closest(itemSelector);
      if (!handle || !item || item.parentElement !== list) return;
      if (event.key === 'ArrowUp' && item.previousElementSibling) list.insertBefore(item, item.previousElementSibling);
      else if (event.key === 'ArrowDown' && item.nextElementSibling) list.insertBefore(item.nextElementSibling, item);
      else return;
      event.preventDefault();
      handle.focus();
      onChange();
    });
  }
  const handleButton = (className, label) => {
    const button = node('button', '', `brt-handle ${className}`);
    button.type = 'button';
    button.title = `Drag to move ${label}, or use the arrow keys`;
    button.setAttribute('aria-label', `Move ${label}`);
    button.innerHTML = '<svg viewBox="0 0 12 18" aria-hidden="true"><circle cx="3" cy="3" r="1.6"/><circle cx="9" cy="3" r="1.6"/><circle cx="3" cy="9" r="1.6"/><circle cx="9" cy="9" r="1.6"/><circle cx="3" cy="15" r="1.6"/><circle cx="9" cy="15" r="1.6"/></svg>';
    return button;
  };

  // -- small fields ---------------------------------------------------------------------------
  const check = (label, checked, className = 'brt-check') => {
    const wrapper = node('label', undefined, className);
    const box = node('input');
    box.type = 'checkbox';
    box.checked = Boolean(checked);
    wrapper.append(box, node('span', label));
    wrapper.box = box;
    return wrapper;
  };
  const selectField = (label, choices, value) => {
    const wrapper = node('label', label, 'brt-field');
    const select = node('select');
    choices.forEach(([key, text]) => {
      const option = node('option', text);
      option.value = key;
      option.selected = String(key) === String(value);
      select.append(option);
    });
    wrapper.append(select);
    wrapper.input = select;
    return wrapper;
  };
  // One colour theme for the whole report, beside its title: every section that supports themes takes it.
  // The default theme of the application (that of a new report) when none is chosen.
  const defaultTheme = () => brtOptions?.defaults?.theme || 'netcheck';
  const reportTheme = () => $('brt-theme').value || definition?.theme || defaultTheme();
  const numberField = (label, value, step, title = '') => {
    const wrapper = node('label', label, 'brt-field');
    const input = node('input');
    input.type = 'number';
    input.step = String(step);
    input.value = String(value);
    if (title) wrapper.title = title;
    wrapper.append(input);
    wrapper.input = input;
    return wrapper;
  };
  const multiField = (label, values, selected, extra = {}) => {
    const {multiPicker} = pickers();
    if (!multiPicker) return node('p', `${label}: unavailable`, 'form-note');
    return multiPicker(label, values, selected || [], {...extra, onChange: () => { extra.onChange?.(); changed(); }});
  };

  // -- common filters --------------------------------------------------------------------------
  const nrMode = () => filterPickers.nr_mode?.value || 'NSA';
  // What follows the NR Mode of the common filters in the sections shown now (cleared when they are drawn again).
  let nrModeHandlers = [];

  // One campaign (Network Insights): Latest campaign (the default), Previous campaign or one campaign. A section saved
  // with several keeps the newest one, and one saved with Latest 2, 3 or 4 campaigns or All available campaigns Latest
  // campaign.
  const singleCampaignField = (values, selected, presets) => {
    const listed = [...presets.map(([key]) => key), ...values];
    const chosen = presets.find(([key]) => selected.includes(key))?.[0]
      ?? values.filter((value) => selected.includes(value)).at(-1) ?? presets[0]?.[0] ?? '';
    const label = (value) => pickers().campaignLabel?.(value) ?? value;
    const field = selectField('Campaign', listed.map((value) => [value, presets.find(([key]) => key === value)?.[1] ?? label(value)]), chosen);
    field.input.addEventListener('change', changed);
    field.getValue = () => (field.input.value ? [field.input.value] : []);
    return field;
  };

  // The Campaigns of a section, which choose its CDRs: first Latest campaign, Latest 2, 3 and 4 campaigns, Previous campaign and All available campaigns,
  // which follow the newest campaigns at each export and stand alone, then the campaigns of
  // the NR Mode of the common filters (listed again when it changes, keeping a Latest choice). With ``single`` (Network
  // Insights), one Campaign.
  function scopeFields(saved, modeOf = nrMode, {single = false} = {}) {
    const row = node('div', undefined, 'brt-scope');
    const presets = single ? (options.single_campaign_presets || []).map((key) => [key, options.campaign_presets?.[key] || key])
      : Object.entries(options.campaign_presets || {});
    const campaignValues = () => [...(options.campaigns?.[modeOf()] || [])]
      .sort((left, right) => (pickers().campaignCompare ? pickers().campaignCompare(left, right) : 0));
    let campaigns = null;
    // (Beside the Campaigns, the GAP reference of Scoring & GAP Analysis.)
    const renderCampaigns = (selected) => {
      const field = single ? singleCampaignField(campaignValues(), selected, presets)
        : multiField('Campaigns', campaignValues(), selected, {exclusive: presets});
      field.classList.add('brt-campaigns-field');
      // (Replaced in its row even before the section is on the page: Scoring lists its own NR Mode as it is drawn.)
      if (campaigns?.parentNode) campaigns.replaceWith(field);
      else row.prepend(field);
      campaigns = field;
    };
    renderCampaigns(saved.campaigns || []);
    // Another NR Mode lists its own campaigns, keeping a Latest choice (every choice with ``keep``).
    row.refresh = (keep = false) => {
      renderCampaigns((campaigns?.getValue?.() || []).filter((value) => keep || presets.some(([key]) => key === value)));
    };
    nrModeHandlers.push(() => row.refresh());
    row.collect = () => ({campaigns: campaigns?.getValue?.() || []});
    return row;
  }

  function renderFilters() {
    const host = $('brt-filters');
    const filters = definition.filters;
    // The NR Mode on its own row: it lists the campaigns of every section, and every PPT Design reads its CDRs.
    const mode = selectField('NR Mode', [['NSA', 'NSA (Non-Standalone)'], ['SA', 'SA (Standalone)']], filters.nr_mode || 'NSA');
    mode.input.id = 'brt-nr-mode';
    filterPickers.nr_mode = mode.input;
    mode.input.addEventListener('change', () => { nrModeHandlers.forEach((handler) => handler()); changed(); });
    const modeRow = node('div', undefined, 'brt-filter-mode');
    modeRow.append(mode);
    const grid = node('div', undefined, 'brt-filter-grid');
    const fields = FILTERS.map(([key, label, valuesKey]) => {
      // The Operators take patterns (VF*, -Lebara; see valuePatterns in app.js).
      const extra = key === 'cities' ? {preset: {label: 'Main Cities (workspace list at each export)', values: options.main_cities || [],
        checked: filters.main_cities, dynamic: true}} : key === 'operators' ? {patterns: true} : {};
      filterPickers[key] = multiField(label, options.values?.[valuesKey] || [], filters[key], extra);
      return filterPickers[key];
    });
    grid.append(...fields);
    host.replaceChildren(modeRow, grid);
  }

  function collectFilters() {
    const value = (key) => filterPickers[key]?.getValue?.() || [];
    return {
      nr_mode: nrMode(),
      ...Object.fromEntries(FILTERS.map(([key]) => [key, value(key)])),
      main_cities: Boolean(filterPickers.cities?.getPreset?.()),
    };
  }

  // -- sections ----------------------------------------------------------------------------------
  const sectionCatalogue = (key) => brtOptions.catalogue.sections.find((section) => section.key === key);
  const operatorValues = () => options.values?.Operator || [];

  function scoringOptions(saved) {
    const box = node('div', undefined, 'brt-options');
    const scorings = node('fieldset', undefined, 'brt-choice-group');
    scorings.append(node('legend', 'Scorings'));
    const scoringBoxes = brtOptions.scorings.map((item) => {
      const field = check(item.label, saved.scorings.includes(item.value));
      field.box.value = item.value;
      scorings.append(field);
      return field.box;
    });
    const environments = node('fieldset', undefined, 'brt-choice-group');
    environments.append(node('legend', 'Environments'));
    const environmentBoxes = [{value: 'all', label: 'All Environments'}, ...brtOptions.scoring_environments].map((item) => {
      const field = check(item.label, saved.environments.includes(item.value));
      field.box.value = item.value;
      if (item.value === 'all') field.title = 'All the environments combined';
      environments.append(field);
      return field.box;
    });
    const methodologies = [['by-campaign', 'By campaign (each campaign with its methodology)'],
      ...(options.methodologies || []).filter((item) => item.id !== 'by-campaign').map((item) => [item.id, item.name])];
    const methodology = selectField('Methodology', methodologies, saved.methodology);
    const operators = operatorValues();
    // (Same operator in NSA, each operator in SA compared with itself in NSA, is a reference of NSA vs SA only.)
    const sameOperator = '@same-operator-nsa';
    const reference = selectField('GAP reference', [...(operators.includes(saved.baseline_operator) || saved.baseline_operator === sameOperator
      ? operators : [saved.baseline_operator, ...operators]).map((value) => [value, value]), [sameOperator, 'Same operator in NSA']],
    saved.baseline_operator);
    const tables = node('fieldset', undefined, 'brt-choice-group');
    tables.append(node('legend', 'Scoring tables'));
    const kpiValues = check('Show KPI values', saved.kpi_values);
    const gapValues = check('Show GAP values', saved.gap_values);
    tables.append(kpiValues, gapValues);
    // Every operator in the panels that export the Focus operators (Workspace Config > Scoring Export Panels).
    const operatorChoices = node('fieldset', undefined, 'brt-choice-group');
    operatorChoices.append(node('legend', 'Operators'));
    const allOperators = check('Export All Operators in Focus panels', saved.all_operators);
    allOperators.title = 'Show every operator in the panels that export the Focus operators of the Operator Maps';
    operatorChoices.append(allOperators);
    // NSA vs SA: the NSA and SA CDRs of the campaigns of the section side by side, each campaign with its NR Mode,
    // whatever the NR Mode of the report (offered when the workspace has CDRs of both NR Modes).
    const nrModes = node('fieldset', undefined, 'brt-choice-group');
    nrModes.append(node('legend', 'NR Mode'));
    const nsaVsSa = check('Compare NSA vs SA', saved.nsa_vs_sa);
    nsaVsSa.title = 'Score the NSA and SA CDRs of the campaigns of this module side by side (always split by Campaign); '
      + 'the other modules keep the NR Mode of the report';
    // How the document shows each NR Mode, as the NSA vs SA and NSA & SA charts of the Scoring & GAP Analysis results.
    const nrLayout = selectField('NSA vs SA', brtOptions.nr_layouts || [], saved.nr_layout);
    nrLayout.title = 'Each panel of NSA followed by the same panel of SA, or every panel of NSA and then every panel of SA';
    const nrCharts = selectField('NSA & SA charts', brtOptions.nr_charts || [], saved.nr_charts);
    nrCharts.title = 'The Scoring Charts and Scoring Trends with NSA and SA in the same chart (the trends on one axis of quarters, '
      + 'SA dashed) or with the charts of each NR Mode on their own';
    const nrViews = node('div', undefined, 'brt-option-grid brt-nr-views');
    nrViews.append(nrLayout, nrCharts);
    const syncNrViews = () => { nrViews.hidden = !nsaVsSa.box.checked; };
    syncNrViews();
    nrModes.append(nsaVsSa, nrViews);
    nrModes.hidden = !saved.nsa_vs_sa && !((options.campaigns?.NSA || []).length && (options.campaigns?.SA || []).length);
    box.nrMode = () => (nsaVsSa.box.checked ? 'NSA+SA' : nrMode());
    const sameOperatorOption = [...reference.input.options].find((option) => option.value === sameOperator);
    const syncReference = () => {
      sameOperatorOption.hidden = sameOperatorOption.disabled = !nsaVsSa.box.checked;
      if (!nsaVsSa.box.checked && reference.input.value === sameOperator) {
        reference.input.value = operators.find((value) => value.toLowerCase() === 'ee') || operators[0] || 'EE';
      }
    };
    syncReference();
    // The Geographical Areas & Scoring Trends, always included: the areas of both tabs (the Breakdown and the Separate
    // cities) and the campaigns and time split of the Scoring Trends, on the whole country.
    const trends = node('fieldset', undefined, 'brt-choice-group brt-trends');
    trends.append(node('legend', 'Geographical Areas & Scoring Trends'));
    const presets = Object.entries(options.campaign_presets || {});
    const campaignValues = () => [...(options.campaigns?.[box.nrMode()] || [])]
      .sort((left, right) => (pickers().campaignCompare ? pickers().campaignCompare(left, right) : 0));
    const trendHost = node('div', undefined, 'brt-trend-campaigns');
    let trendCampaigns = null;
    const renderTrendCampaigns = (selected) => {
      trendCampaigns = multiField('Campaigns', campaignValues(), selected, {exclusive: presets, allLabel: 'Same as the module'});
      trendCampaigns.title = 'The campaigns of the Scoring Trend and the National & Geographical Areas Trends (none: the campaigns of the module)';
      trendCampaigns.classList.add('brt-campaigns-field');
      trendHost.replaceChildren(trendCampaigns);
    };
    renderTrendCampaigns(saved.area_summary.campaigns || []);
    const refreshTrendCampaigns = () => {
      renderTrendCampaigns((trendCampaigns?.getValue?.() || []).filter((value) => presets.some(([key]) => key === value)));
    };
    nrModeHandlers.push(refreshTrendCampaigns);
    nsaVsSa.box.addEventListener('change', () => { syncReference(); syncNrViews(); refreshTrendCampaigns(); box.onNrModeChange?.(); });
    trends.title = 'Always the whole country: the Region, Cluster and City filters do not apply to Geographical Areas and Scoring Trends';
    const area = node('fieldset', undefined, 'brt-choice-group brt-area');
    area.append(node('legend', 'Geographical Areas'));
    area.title = 'The areas of the Geographical Areas and Scoring Trends tabs';
    const breakdown = selectField('Breakdown', brtOptions.area_summary_breakdowns.map((value) => [value, value === 'None' ? 'None (Separate cities only)' : value]),
      saved.area_summary.breakdown);
    const savedCities = saved.area_summary.cities || [];
    const cities = multiField('Separate cities', [...new Set([...(options.values?.City || []), ...savedCities])], savedCities, {
      allLabel: 'None', list: true,
      preset: {label: 'Main Cities (workspace list at each export)', values: options.main_cities || [], checked: saved.area_summary.main_cities, dynamic: true},
    });
    cities.title = 'Each one scored apart with its own tests (with Breakdown None, the only areas)';
    area.append(breakdown, cities);
    const trendOptions = node('fieldset', undefined, 'brt-choice-group brt-area');
    trendOptions.append(node('legend', 'Scoring Trends'));
    trendOptions.title = 'The Scoring Trends tab only';
    const timeSplit = selectField('Time split', brtOptions.area_summary_time_splits.map((value) => [value, value === 'All' ? 'All selected CDRs' : value]),
      saved.area_summary.time_split);
    trendOptions.append(trendHost, timeSplit);
    // The two subpanels side by side, as on the Scoring & GAP Analysis page.
    const columns = node('div', undefined, 'brt-trends-columns');
    columns.append(area, trendOptions);
    trends.append(columns);
    // The GAP reference and the Methodology go beside the Campaigns of the section, as on the Scoring & GAP Analysis
    // page (the Focus operators of the PowerPoint and Word are those of the Operator Maps).
    box.scopeFields = [reference, methodology];
    box.append(scorings, environments, tables, operatorChoices, nrModes, trends);
    box.collect = () => ({
      nsa_vs_sa: nsaVsSa.box.checked, nr_layout: nrLayout.input.value, nr_charts: nrCharts.input.value,
      scorings: scoringBoxes.filter((item) => item.checked).map((item) => item.value),
      environments: environmentBoxes.filter((item) => item.checked).map((item) => item.value),
      kpi_values: kpiValues.box.checked, gap_values: gapValues.box.checked, all_operators: allOperators.box.checked,
      baseline_operator: reference.input.value, methodology: methodology.input.value,
      area_summary: {enabled: true, breakdown: breakdown.input.value, time_split: timeSplit.input.value,
        cities: cities.getValue?.() || [], main_cities: Boolean(cities.getPreset?.()), campaigns: trendCampaigns?.getValue?.() || []},
    });
    return box;
  }

  function networkOptions(saved) {
    const box = node('div', undefined, 'brt-options');
    const technology = selectField('Technology', Object.entries(brtOptions.network_technologies), saved.technology);
    const group = multiField('Split by', Object.keys(brtOptions.network_groupings), saved.group);
    // The Split by picker lists keys: their labels are shown instead.
    group.querySelectorAll?.('.rj-multi-option span').forEach((span) => {
      span.textContent = brtOptions.network_groupings[span.textContent] || span.textContent;
    });
    const fields = [
      numberField('LTE coverage below (dBm)', saved.coverage_threshold, 1, 'Samples below this LTE RSRP count as low coverage'),
      numberField('LTE interference below (dB)', saved.interference_threshold, 0.5, 'Samples below this LTE SINR count as high interference'),
      numberField('NR coverage below (dBm)', saved.nr_coverage_threshold, 1, 'Samples below this NR SS-RSRP count as low coverage'),
      numberField('NR interference below (dB)', saved.nr_interference_threshold, 0.5, 'Samples below this NR SS-SINR count as high interference'),
      numberField('Overshooting beyond (km)', saved.overshoot_km, 0.5, 'Samples served from farther than this distance count as overshooting'),
    ];
    const gridSize = selectField('Map grid', [['100', '100 m'], ['250', '250 m'], ['500', '500 m'], ['1000', '1 km']], String(saved.grid_metres));
    const environments = multiField('Environments', NI_ENVIRONMENTS, saved.environments);
    const grid = node('div', undefined, 'brt-option-grid');
    grid.append(technology, group, ...fields, gridSize, environments);
    box.append(grid);
    const number = (field, fallback) => {
      const value = Number.parseFloat(field.input.value);
      return Number.isFinite(value) ? value : fallback;
    };
    box.collect = () => ({
      technology: technology.input.value, group: group.getValue?.() || [],
      coverage_threshold: number(fields[0], -110), interference_threshold: number(fields[1], 0),
      nr_coverage_threshold: number(fields[2], -115), nr_interference_threshold: number(fields[3], -3),
      overshoot_km: number(fields[4], 5), grid_metres: Number(gridSize.input.value) || 250,
      environments: environments.getValue?.() || [],
    });
    return box;
  }

  function callsOptions(saved) {
    const box = node('div', undefined, 'brt-options');
    const periods = selectField('Progress periods', Object.entries(brtOptions.nq_granularities), saved.granularity);
    const calls = selectField('Calls', [['', 'Every call'], ['1', 'Open calls only']], saved.open_only ? '1' : '');
    const suggestions = selectField('Root Cause Analysis', [['1', 'Count suggested root causes'], ['', 'Labelled root causes only']],
      saved.include_suggestions ? '1' : '');
    const notClassified = check('Show Not classified calls', saved.show_not_classified);
    const empty = check('Show calls without a value in the phases', saved.show_empty);
    const grid = node('div', undefined, 'brt-option-grid');
    grid.append(periods, calls, suggestions);
    const flags = node('div', undefined, 'brt-inline');
    flags.append(notClassified, empty);
    box.append(grid, flags);
    box.collect = () => ({
      granularity: periods.input.value, open_only: calls.input.value === '1', include_suggestions: suggestions.input.value === '1',
      show_not_classified: notClassified.box.checked, show_empty: empty.box.checked,
    });
    return box;
  }

  // CDR Analysis: the Global Comparison and Global CDF Comparison of its charts and the metrics of each CDR type (All, the
  // default, includes every metric, also future ones), as a CDR Analysis artifact of a Reporting Job.
  function cdrOptions(saved) {
    const box = node('div', undefined, 'brt-options');
    const aggregation = selectField('Global Comparison', Object.entries(options.cdr_aggregations || {}), saved.aggregation);
    const cdf = selectField('Global CDF Comparison', Object.entries(options.cdr_cdf_groupings || {}), saved.cdf_grouping);
    const metrics = Object.entries(options.cdr_kinds || {}).map(([kind, label]) => {
      const chosen = saved.metrics?.[kind] || [];
      const field = multiField(`${label} metrics`, [...new Set([...((options.cdr_metrics || {})[kind] || []), ...chosen])], chosen);
      field.dataset.kind = kind;
      return field;
    });
    const grid = node('div', undefined, 'brt-option-grid');
    grid.append(aggregation, cdf, ...metrics);
    box.append(grid);
    box.collect = () => ({
      aggregation: aggregation.input.value, cdf_grouping: cdf.input.value,
      metrics: Object.fromEntries(metrics.map((field) => [field.dataset.kind, field.getValue?.() || []]).filter(([, values]) => values.length)),
    });
    return box;
  }

  function itemRow(sectionKey, catalogueItem, saved) {
    const row = node('li', undefined, 'brt-item');
    row.dataset.key = catalogueItem.key;
    const head = node('div', undefined, 'brt-item-head');
    const enabled = check(catalogueItem.title, saved ? saved.enabled : sectionKey !== 'designs', 'brt-check brt-item-check');
    head.append(handleButton('brt-item-handle', catalogueItem.title), enabled);
    row.append(head);
    const boxes = [];
    if (catalogueItem.components.length) {
      const count = node('span', '', 'brt-count');
      const toggle = node('button', 'Charts & tables', 'brt-expand');
      toggle.type = 'button';
      const components = node('div', undefined, 'brt-components');
      catalogueItem.components.forEach((component) => {
        const field = check(component.title, saved ? saved.components?.[component.key] !== false : true);
        field.box.value = component.key;
        // The Scoring panels that export the Focus operators (Workspace Config > Scoring Export Panels).
        if (component.operators === 'focus') {
          const tag = node('span', 'Focus', 'brt-badge brt-focus-tag');
          tag.title = 'Exports the Focus operators of the Operator Maps (every operator with Export All Operators in Focus panels)';
          field.append(tag);
        }
        components.append(field);
        boxes.push(field.box);
      });
      const collapsedKey = COLLAPSED_KEY(`${sectionKey}:${catalogueItem.key}`);
      // Sub-modules show their charts and tables when expanded (remembered in this browser).
      const apply = (open) => {
        components.hidden = !open;
        toggle.setAttribute('aria-expanded', String(open));
        toggle.classList.toggle('is-open', open);
      };
      apply(readFlag(collapsedKey));
      toggle.addEventListener('click', () => { const open = components.hidden; apply(open); writeFlag(collapsedKey, open); });
      const refresh = () => {
        const chosen = boxes.filter((box) => box.checked).length;
        count.textContent = chosen === boxes.length ? `All ${boxes.length}` : `${chosen} of ${boxes.length}`;
        row.classList.toggle('is-off', !enabled.box.checked || !chosen);
      };
      components.addEventListener('change', refresh);
      enabled.box.addEventListener('change', refresh);
      head.append(count, toggle);
      row.append(components);
      refresh();
    } else {
      const refresh = () => row.classList.toggle('is-off', !enabled.box.checked);
      enabled.box.addEventListener('change', refresh);
      refresh();
    }
    row.collect = () => ({
      key: catalogueItem.key, enabled: enabled.box.checked,
      // A PPT Design keeps its name and NR Mode, which find it again in another workspace.
      ...(sectionKey === 'designs' ? {label: catalogueItem.title, nr_mode: catalogueItem.nr_mode || ''}
        : {components: Object.fromEntries(boxes.map((box) => [box.value, box.checked]))}),
    });
    return row;
  }

  function sectionCard(saved) {
    const catalogue = sectionCatalogue(saved.key);
    const allowed = brtOptions.allowed_sections[saved.key];
    const title = brtOptions.section_titles[saved.key] || catalogue.title;
    const card = node('li', undefined, `brt-section brt-section-${saved.key}`);
    card.dataset.key = saved.key;
    const head = node('div', undefined, 'brt-section-head');
    const enabled = check(title, allowed && saved.enabled, 'brt-check brt-section-check');
    enabled.box.disabled = !allowed;
    const summary = node('span', '', 'brt-count');
    const collapse = node('button', 'Collapse', 'collapse-chip brt-collapse');
    collapse.type = 'button';
    head.append(handleButton('brt-section-handle', title), enabled, summary, collapse);
    const body = node('div', undefined, 'brt-section-body');
    if (!allowed) body.append(node('p', 'Your account cannot use this module: it is left out.', 'form-note'));
    // (The Scoring section can compare NSA vs SA: its campaigns follow its own NR Mode then.)
    let sectionMode = nrMode;
    const scope = scopeFields(saved.options || {}, () => sectionMode(), {single: saved.key === 'network_insights'});
    body.append(scope);
    const list = node('ol', undefined, 'brt-items');
    list.setAttribute('aria-label', `Sub-modules of ${title}`);
    const savedItems = Object.fromEntries((saved.items || []).map((item) => [item.key, item]));
    const catalogueItems = Object.fromEntries(catalogue.items.map((item) => [item.key, item]));
    const order = [...(saved.items || []).map((item) => item.key).filter((key) => catalogueItems[key]),
      ...catalogue.items.map((item) => item.key).filter((key) => !savedItems[key])];
    order.forEach((key) => list.append(itemRow(saved.key, catalogueItems[key], savedItems[key])));
    if (saved.key === 'designs' && !catalogue.items.length) {
      list.append(node('li', 'There are no saved PPT Designs in this workspace.', 'form-note brt-empty'));
    }
    sortable(list, '.brt-item', '.brt-item-handle', changed);
    const optionsBox = saved.key === 'scoring' ? scoringOptions(saved.options)
      : saved.key === 'network_insights' ? networkOptions(saved.options)
        : saved.key === 'non_qualified_calls' ? callsOptions(saved.options)
          : saved.key === 'dataset_analysis' ? cdrOptions(saved.options) : null;
    if (optionsBox?.scopeFields) scope.append(...optionsBox.scopeFields);
    if (optionsBox?.nrMode) {
      sectionMode = optionsBox.nrMode;
      scope.refresh(true);
      optionsBox.onNrModeChange = () => { scope.refresh(); changed(); };
    }
    // Below the Campaigns, the Options of the module and then its sub-modules (or PPT Designs), each in a subpanel.
    if (optionsBox) {
      const optionsWrap = node('div', undefined, 'brt-subpanel brt-section-options');
      optionsWrap.append(node('h4', 'Options'), optionsBox);
      body.append(optionsWrap);
    }
    const itemsWrap = node('div', undefined, 'brt-subpanel brt-section-items');
    itemsWrap.append(node('h4', saved.key === 'designs' ? 'PPT Designs' : 'Sub-modules'), list);
    body.append(itemsWrap);
    card.append(head, body);
    const empty = node('li', '', 'form-note brt-empty');
    const refresh = () => {
      if (saved.key === 'designs') {
        // Every PPT Design reads the CDRs of the NR Mode of the common filters.
        empty.textContent = 'There are no saved PPT Designs in this workspace.';
        if (catalogue.items.length) list.append(empty);
        empty.hidden = [...list.querySelectorAll(':scope > .brt-item')].some((row) => !row.hidden);
      }
      const rows = [...list.querySelectorAll(':scope > .brt-item')].filter((row) => !row.hidden);
      const chosen = rows.filter((row) => !row.classList.contains('is-off')).length;
      const noun = saved.key === 'designs' ? 'PPT Designs' : 'sub-modules';
      summary.textContent = `${chosen} of ${rows.length} ${noun}`;
      card.classList.toggle('is-off', !enabled.box.checked);
    };
    nrModeHandlers.push(refresh);
    const collapsedKey = COLLAPSED_KEY(`section:${saved.key}`);
    const apply = (collapsed) => {
      card.classList.toggle('is-collapsed', collapsed);
      collapse.textContent = collapsed ? 'Expand' : 'Collapse';
      collapse.setAttribute('aria-expanded', String(!collapsed));
    };
    apply(readFlag(collapsedKey));
    collapse.addEventListener('click', () => { const collapsed = !card.classList.contains('is-collapsed'); apply(collapsed); writeFlag(collapsedKey, collapsed); });
    card.addEventListener('change', refresh);
    refresh();
    card.collect = () => ({
      key: saved.key, enabled: enabled.box.checked,
      items: [...list.querySelectorAll(':scope > .brt-item')].map((row) => row.collect()),
      options: {...(optionsBox ? optionsBox.collect() : {}), ...scope.collect()},
    });
    return card;
  }

  function renderSections() {
    nrModeHandlers = [];
    const list = $('brt-sections');
    list.replaceChildren(...definition.sections.map((section) => sectionCard(section)));
  }
  sortable($('brt-sections'), '.brt-section', '.brt-section-handle', changed);

  function collect() {
    return {
      title: $('brt-title').value.trim(),
      subtitle: $('brt-subtitle').value.trim(),
      theme: reportTheme(),
      chart_pictures: $('brt-chart-pictures').checked,
      filters: collectFilters(),
      sections: [...$('brt-sections').children].map((card) => card.collect()),
    };
  }

  // The report being edited is kept in this browser, so a reload opens it again with its changes.
  function changed() {
    if (root.hidden || !definition) return;
    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify({id: editingId, name: $('brt-name').value, definition: collect(),
        schedule: collectSchedule(), step}));
    } catch {}
  }

  function render() {
    $('brt-title').value = definition.title || '';
    $('brt-subtitle').value = definition.subtitle || '';
    // Reports saved before the common theme take that of their Scoring section.
    const theme = $('brt-theme');
    const scoringTheme = (definition.sections || []).find((section) => section.key === 'scoring')?.options?.theme;
    theme.replaceChildren(...(options.scoring_themes || []).map((item) => {
      const option = node('option', item.label || item.id);
      option.value = item.id;
      if (item.description) option.title = item.description;
      return option;
    }));
    theme.value = definition.theme || scoringTheme || defaultTheme();
    if (!theme.value && theme.options.length) theme.selectedIndex = 0;
    $('brt-chart-pictures').checked = definition.chart_pictures === true;
    filterPickers = {};
    renderFilters();
    renderSections();
  }

  // -- reports ----------------------------------------------------------------------------------------
  // Each report is a card with what it includes, its schedule and its last run (the state History loads, see
  // reporting_history.js). Its editor opens beside the list on a wide screen and over the page on a phone, in four steps.
  const page = document.getElementById('report-jobs');
  let pageState = {reports: [], runs: [], can_edit: false};
  let editingId = null;
  // The chip chosen stays in this browser.
  const LIST_FILTER_KEY = 'reporting:reports-filter';
  let listFilter = (() => { try { return localStorage.getItem(LIST_FILTER_KEY) || 'all'; } catch { return 'all'; } })();
  const canEdit = () => Boolean(brtOptions?.can_edit);
  const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (character) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[character]));
  const MODULE_TAGS = {scoring: ['SCO', 'Scoring & GAP Analysis'], network_insights: ['NI', 'Network Insights'],
    non_qualified_calls: ['NQ', 'Non-Qualified Calls'], designs: ['PPT', 'PPT Designer'], dataset_analysis: ['CDR', 'CDR Analysis']};
  const RUN_LABELS = {queued: 'Queued', running: 'Running', stopping: 'Stopping', sent: 'Sent', completed: 'Ready', partial: 'Partial',
    failed: 'Failed', stopped: 'Stopped'};
  const ACTIVE_RUNS = ['queued', 'running', 'stopping'];
  const localTime = (value) => {
    const parsed = new Date(value || '');
    return Number.isNaN(parsed.getTime()) ? '' : parsed.toLocaleString(undefined, {dateStyle: 'medium', timeStyle: 'short'});
  };
  const scheduled = (report) => Boolean(report.schedule.enabled && report.schedule.schedule?.mode !== 'manual');
  const reportSchedule = (report) => (!report ? 'Only with Generate'
    : scheduled(report) ? report.schedule.recurrence
      : report.schedule.schedule?.mode !== 'manual' ? `Paused · ${report.schedule.recurrence}` : 'Only with Generate');

  // The labels of a report (also above its runs in History), one row each: its modules; the area it filters, its NR Mode
  // and the Operator or Vendor it filters; and its campaigns.
  function labelsOf(labels) {
    const box = node('div', undefined, 'rp-labels');
    const row = (className) => { const line = node('div', undefined, `rp-label-row ${className}`); box.append(line); return line; };
    const modules = row('rp-label-modules');
    (labels?.modules || []).forEach((key) => {
      const [short, title] = MODULE_TAGS[key] || [key, key];
      const tag = node('span', short, `rp-module rp-module-${key}`);
      tag.title = title;
      modules.append(tag);
    });
    const scopes = row('rp-label-scopes');
    const scopeTag = (scope) => {
      const tag = node('span', scope.text, `rp-scope rp-scope-${scope.dimension}`);
      tag.title = scope.title;
      scopes.append(tag);
    };
    const parties = ['operator', 'vendor'];
    (labels?.scopes || []).filter((scope) => !parties.includes(scope.dimension)).forEach(scopeTag);
    if (labels?.nr_mode) scopes.append(node('span', labels.nr_mode, `rp-mode rp-mode-${String(labels.nr_mode).toLowerCase()}`));
    (labels?.scopes || []).filter((scope) => parties.includes(scope.dimension)).forEach(scopeTag);
    const campaigns = row('rp-label-campaigns');
    (labels?.campaigns || []).forEach((choice) => {
      const tag = node('span', choice.campaigns, 'rp-campaigns');
      tag.title = `Campaigns of ${choice.modules.map((key) => (MODULE_TAGS[key] || [key, key])[1]).join(', ')}`;
      campaigns.append(tag);
    });
    box.querySelectorAll('.rp-label-row:empty').forEach((line) => line.remove());
    return box;
  }
  window.reportingLabels = labelsOf;

  function menuButton(label, title, handler, className = '') {
    const button = node('button', label, `rp-menu-item ${className}`.trim());
    button.type = 'button';
    button.title = title;
    button.addEventListener('click', (event) => { event.currentTarget.closest('details')?.removeAttribute('open'); handler(); });
    return button;
  }

  function reportCard(report) {
    const card = node('li', undefined, 'rp-card');
    card.dataset.reportId = report.id;
    card.classList.toggle('is-selected', report.id === editingId);
    const head = node('div', undefined, 'rp-card-head');
    const name = node(canEdit() ? 'button' : 'span', report.name, 'rp-card-name');
    if (canEdit()) {
      name.type = 'button';
      name.title = 'Edit this report';
      name.addEventListener('click', () => { void openEditor(report.id); });
    }
    const star = node('button', report.starred ? '★' : '☆', `rp-star${report.starred ? ' is-starred' : ''}`);
    star.type = 'button';
    star.title = report.starred ? 'Take it away from your favourites' : 'Add it to your favourites';
    star.setAttribute('aria-label', `${star.title}: ${report.name}`);
    star.setAttribute('aria-pressed', String(Boolean(report.starred)));
    star.addEventListener('click', () => { void toggleStar(report); });
    head.append(name, star);
    const schedule = node('p', undefined, `rp-card-schedule${scheduled(report) ? ' is-scheduled' : ''}`);
    schedule.append(node('span', undefined, 'rp-dot'), node('span', reportSchedule(report)));
    if (scheduled(report) && report.schedule.next_run_at) schedule.append(node('span', ` · next ${localTime(report.schedule.next_run_at)}`, 'rp-next'));
    if (report.schedule.send_email) schedule.append(node('span', ` · emailed to ${report.schedule.recipients.length}`, 'rp-next'));
    const last = report.last_run ? (pageState.runs.find((run) => run.id === report.last_run.id) || report.last_run) : null;
    const pending = Boolean(last && ACTIVE_RUNS.includes(last.status));
    const result = node('p', undefined, 'rp-card-result');
    if (last) {
      result.append(node('span', RUN_LABELS[last.status] || last.status, `rj-status rj-status-${last.status}`));
      result.append(pending ? ` ${last.progress || 0}% · ${last.message || ''}` : ` ${localTime(last.finished_at || last.started_at || last.created_at)}`);
    } else {
      result.append(node('span', 'Not generated yet', 'form-note'));
    }
    const actions = node('div', undefined, 'rp-card-actions');
    const generate = node('button', pending ? 'Follow' : 'Generate', 'rp-primary');
    generate.type = 'button';
    generate.title = pending ? 'Follow the report being generated' : 'Generate the report now, in the formats of its schedule';
    generate.addEventListener('click', () => (pending ? window.openReportRun(last.id) : generateReport(report)));
    actions.append(generate);
    if (last && !pending && last.has_preview) {
      const preview = node('button', 'Preview', 'rp-secondary');
      preview.type = 'button';
      preview.title = 'Open the preview of the last report generated';
      preview.addEventListener('click', () => window.openReportRun(last.id));
      actions.append(preview);
    }
    if (canEdit()) {
      const edit = node('button', 'Edit', 'rp-secondary');
      edit.type = 'button';
      edit.addEventListener('click', () => { void openEditor(report.id); });
      const more = node('details', undefined, 'rp-more');
      const summary = node('summary', '⋯');
      summary.title = 'More actions';
      summary.setAttribute('aria-label', `More actions on ${report.name}`);
      const menu = node('div', undefined, 'rp-menu');
      menu.append(menuButton('Duplicate', 'Save a copy of this report, without its schedule', () => duplicateReport(report)),
        menuButton('Rename', 'Rename this report (its runs keep their name)', () => renameReport(report)));
      const deletable = window.canDeleteShared?.(report.created_by) ?? true;
      const remove = menuButton('Delete', deletable ? 'Delete this report with its schedule and its runs in History' : window.sharedDeleteRefusal?.('report') || '',
        () => deleteReport(report), 'rp-danger');
      remove.disabled = !deletable;
      menu.append(remove);
      more.append(summary, menu);
      actions.append(edit, more);
    }
    card.append(head, labelsOf(report.labels), schedule, result, actions);
    return card;
  }

  function renderList() {
    const query = $('rp-search').value.trim().toLocaleLowerCase();
    const shown = pageState.reports.filter((report) => (!query || report.name.toLocaleLowerCase().includes(query))
      && (listFilter === 'all' || (listFilter === 'starred' ? report.starred
        : listFilter === 'scheduled' ? scheduled(report) : report.labels.nr_mode === listFilter)));
    $('rp-count-reports').textContent = pageState.reports.length ? String(pageState.reports.length) : '';
    $('rp-new').hidden = !canEdit();
    const list = $('rp-list');
    if (!shown.length) {
      const text = listFilter === 'starred' && !query ? 'No favourites yet: mark the reports you want at hand with their star.'
        : pageState.reports.length ? 'No report matches the search.'
        : canEdit() ? 'No report yet: + New report designs the first one.' : 'No report yet.';
      list.replaceChildren(node('li', text, 'form-note rp-empty'));
      return;
    }
    // (A menu stays open while the state of the page refreshes the cards.)
    const openMenu = list.querySelector('details.rp-more[open]')?.closest('.rp-card')?.dataset.reportId;
    list.replaceChildren(...shown.map(reportCard));
    if (openMenu) {
      const menu = list.querySelector(`.rp-card[data-report-id="${CSS.escape(openMenu)}"] details.rp-more`);
      if (menu) menu.open = true;
    }
  }
  // One ⋯ menu open at a time; a click elsewhere or Escape closes it.
  const closeMenus = (except = null) => document.querySelectorAll('details.rp-more[open]').forEach((menu) => { if (menu !== except) menu.open = false; });
  $('rp-list').addEventListener('toggle', (event) => { if (event.target.matches?.('details.rp-more') && event.target.open) closeMenus(event.target); }, true);
  document.addEventListener('click', (event) => { if (!event.target.closest?.('details.rp-more')) closeMenus(); });
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeMenus(); });
  document.addEventListener('reporting:state', (event) => {
    pageState = event.detail;
    // (A report saved or renamed elsewhere comes with its definition from the options.)
    renderList();
  });
  $('rp-search').addEventListener('input', renderList);
  const chips = [...document.querySelectorAll('[data-rp-filter]')];
  if (!chips.some((chip) => chip.dataset.rpFilter === listFilter)) listFilter = 'all';
  const showChip = () => chips.forEach((chip) => chip.setAttribute('aria-pressed', String(chip.dataset.rpFilter === listFilter)));
  showChip();
  chips.forEach((chip) => chip.addEventListener('click', () => {
    listFilter = chip.dataset.rpFilter;
    try { localStorage.setItem(LIST_FILTER_KEY, listFilter); } catch {}
    showChip();
    renderList();
  }));
  // The star of a report is of each user, and shows at once.
  async function toggleStar(report) {
    const starred = !report.starred;
    report.starred = starred;
    renderList();
    try {
      await api(`/api/reporting/bundle-report-template/favourites/${report.id}/star`, {method: 'POST', body: JSON.stringify({starred})});
    } catch (error) {
      report.starred = !starred;
      renderList();
      status(error.message, 'error');
    }
  }
  const refreshPage = () => document.dispatchEvent(new CustomEvent('reporting:refresh'));
  async function reloadReports() {
    brtOptions = {...brtOptions, favourites: (await api('/api/reporting/bundle-report-template/options')).favourites};
    favourites = brtOptions.favourites || [];
  }

  // -- the editor, in steps ----------------------------------------------------------------------------------
  const STEPS = ['cover', 'filters', 'modules', 'schedule'];
  let step = 'cover';
  function showStep(name) {
    step = STEPS.includes(name) ? name : 'cover';
    root.querySelectorAll('[data-rp-panel]').forEach((panel) => { panel.hidden = panel.dataset.rpPanel !== step; });
    root.querySelectorAll('[data-rp-step]').forEach((button) => {
      if (button.dataset.rpStep === step) button.setAttribute('aria-current', 'step'); else button.removeAttribute('aria-current');
    });
    const index = STEPS.indexOf(step);
    $('rp-step-back').disabled = index === 0;
    $('rp-step-next').hidden = index === STEPS.length - 1;
    root.querySelector('.rp-editor-body').scrollTop = 0;
    changed();
  }
  root.querySelectorAll('[data-rp-step]').forEach((button) => button.addEventListener('click', () => showStep(button.dataset.rpStep)));
  $('rp-step-back').addEventListener('click', () => showStep(STEPS[Math.max(0, STEPS.indexOf(step) - 1)]));
  $('rp-step-next').addEventListener('click', () => showStep(STEPS[Math.min(STEPS.length - 1, STEPS.indexOf(step) + 1)]));

  // The schedule of the report: whether it is generated on its own and when, its formats and whom it is emailed to.
  const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  $('rp-weekdays').replaceChildren(...WEEKDAYS.map((label, index) => {
    const item = node('label', undefined, 'rp-weekday');
    const box = node('input');
    box.type = 'checkbox';
    box.value = String(index);
    item.append(box, node('span', label));
    return item;
  }));
  function fillSchedule(saved) {
    const schedule = saved?.schedule || {mode: 'manual', time: '08:00'};
    $('rp-enabled').checked = saved ? saved.enabled !== false : true;
    $('rp-mode').value = schedule.mode || 'manual';
    $('rp-time').value = schedule.time || '08:00';
    $('rp-date').value = schedule.date || '';
    $('rp-day').value = schedule.day_of_month || 1;
    $('rp-weekdays').querySelectorAll('input').forEach((box) => { box.checked = (schedule.weekdays || [0]).includes(Number(box.value)); });
    const formats = saved?.formats || ['powerpoint', 'word'];
    $('rp-format-powerpoint').checked = formats.includes('powerpoint');
    $('rp-format-word').checked = formats.includes('word');
    $('rp-send-email').checked = Boolean(saved?.send_email);
    $('rp-recipients').value = (saved?.recipients || []).join(', ');
    syncSchedule();
  }
  function collectSchedule() {
    const mode = $('rp-mode').value;
    const schedule = {mode, time: $('rp-time').value || '08:00'};
    if (mode === 'once') schedule.date = $('rp-date').value;
    if (mode === 'weekly') schedule.weekdays = [...$('rp-weekdays').querySelectorAll('input:checked')].map((box) => Number(box.value));
    if (mode === 'monthly') schedule.day_of_month = Number($('rp-day').value) || 1;
    const formats = ['powerpoint', 'word'].filter((format) => $(`rp-format-${format}`).checked);
    return {enabled: $('rp-enabled').checked, schedule, formats: formats.length ? formats : ['powerpoint'],
      send_email: $('rp-send-email').checked, recipients: $('rp-recipients').value.split(/[,;\s]+/).map((value) => value.trim()).filter(Boolean)};
  }
  function syncSchedule() {
    const mode = $('rp-mode').value;
    root.querySelectorAll('[data-rp-schedule]').forEach((field) => { field.hidden = !field.dataset.rpSchedule.split(' ').includes(mode); });
    root.querySelector('[data-rp-email]').hidden = !$('rp-send-email').checked;
    const report = pageState.reports.find((item) => item.id === editingId);
    $('rp-next-run').textContent = mode === 'manual' ? 'Only when Generate is pressed: choose a recurrence to generate it on its own.'
      : !$('rp-enabled').checked ? 'Paused: it keeps its schedule but is only generated with Generate.'
        : report?.schedule?.next_run_at && report.schedule.schedule?.mode === mode ? `Next on ${localTime(report.schedule.next_run_at)}.` : 'On the schedule below, once saved.';
    $('rp-timezone').textContent = options?.timezone ? `Times are those of the server (${options.timezone}).` : '';
    if (!options?.email_configured && $('rp-send-email').checked) $('rp-timezone').textContent += ' Email Delivery is not configured yet: the files are kept in History until it is.';
  }
  root.querySelector('[data-rp-panel="schedule"]').addEventListener('input', () => { syncSchedule(); changed(); });
  root.querySelector('[data-rp-panel="schedule"]').addEventListener('change', () => { syncSchedule(); changed(); });

  async function openEditor(reportId, draft = null) {
    if (!brtOptions || !options) { status('The report editor is still loading.', 'error'); return; }
    const report = reportId == null ? null : favourites.find((item) => item.id === reportId);
    editingId = report ? report.id : null;
    definition = clone(draft?.definition ? mergeDefaults(draft.definition) : report ? report.definition : brtOptions.defaults);
    $('brt-name').value = draft?.name ?? (report ? report.name : '');
    $('rp-editor-title').textContent = report ? report.name : 'New report';
    $('rp-editor-kind').textContent = report ? 'Edit report' : 'New report';
    render();
    fillSchedule(draft?.schedule || pageState.reports.find((item) => item.id === editingId)?.schedule || null);
    root.hidden = false;
    page.classList.add('is-editing');
    document.documentElement.classList.toggle('rp-sheet-open', window.matchMedia('(max-width: 900px)').matches);
    showStep(draft?.step || 'cover');
    renderList();
    if (!window.matchMedia('(max-width: 900px)').matches) root.scrollIntoView({block: 'nearest'});
  }
  function closeEditor() {
    root.hidden = true;
    editingId = null;
    page.classList.remove('is-editing');
    document.documentElement.classList.remove('rp-sheet-open');
    try { localStorage.removeItem(DRAFT_KEY); } catch {}
    renderList();
  }
  $('rp-new').addEventListener('click', () => { void openEditor(null); });
  $('rp-editor-close').addEventListener('click', closeEditor);

  // Save keeps the report and its schedule; a name another report has is refused.
  async function saveReport() {
    const name = $('brt-name').value.trim();
    if (!name) { status('Enter a name for the report.', 'error'); showStep('cover'); $('brt-name').focus(); return null; }
    const clash = favourites.find((item) => item.name.toLocaleLowerCase() === name.toLocaleLowerCase() && item.id !== editingId);
    if (clash) { status(`A report named ${clash.name} already exists: choose another name.`, 'error'); showStep('cover'); return null; }
    const schedule = collectSchedule();
    if (schedule.send_email && !schedule.recipients.length) { status('Add at least one email recipient or turn email off.', 'error'); showStep('schedule'); return null; }
    try {
      const result = await api(editingId ? `/api/reporting/bundle-report-template/favourites/${editingId}` : '/api/reporting/bundle-report-template/favourites', {
        method: editingId ? 'PUT' : 'POST', body: JSON.stringify({name, definition: collect(), schedule}),
      });
      favourites = result.favourites;
      brtOptions.favourites = favourites;
      status(`${result.favourite.name} saved.`, 'done');
      refreshPage();
      return result.favourite;
    } catch (error) {
      status(error.message, 'error');
      return null;
    }
  }
  $('brt-save').addEventListener('click', async () => { if (await saveReport()) closeEditor(); });
  $('rp-generate-edited').addEventListener('click', async () => {
    const saved = await saveReport();
    if (!saved) return;
    closeEditor();
    generateReport(saved);
  });

  async function duplicateReport(report) {
    const source = favourites.find((item) => item.id === report.id);
    if (!source) return;
    const taken = new Set(favourites.map((item) => item.name.toLocaleLowerCase()));
    let name = `${source.name} (copy)`;
    for (let copy = 2; taken.has(name.toLocaleLowerCase()); copy += 1) name = `${source.name} (copy ${copy})`;
    try {
      const result = await api('/api/reporting/bundle-report-template/favourites', {method: 'POST', body: JSON.stringify({name: name.slice(0, 120), definition: source.definition})});
      favourites = result.favourites;
      brtOptions.favourites = favourites;
      status(`${result.favourite.name} saved.`, 'done');
      refreshPage();
    } catch (error) { status(error.message, 'error'); }
  }
  async function renameReport(report) {
    const answer = typeof showTextInputDialog === 'function'
      ? await showTextInputDialog('New name', {title: 'Rename Report', value: report.name, maxLength: 120, confirmLabel: 'Rename', cancelLabel: 'Cancel',
        note: 'Its schedule takes the new name; the runs in History keep the one they had.'})
      : window.prompt('New name of the report', report.name);
    const name = String(answer ?? '').trim();
    if (!name || name === report.name) return;
    try {
      const result = await api(`/api/reporting/bundle-report-template/favourites/${report.id}/rename`, {method: 'POST', body: JSON.stringify({name})});
      favourites = result.favourites;
      brtOptions.favourites = favourites;
      status(`${report.name} renamed to ${result.favourite.name}.`, 'done');
      refreshPage();
    } catch (error) { status(error.message, 'error'); }
  }
  async function deleteReport(report) {
    const runs = pageState.runs.filter((run) => run.report_id === report.id).length;
    const copy = `<p>Delete the report <strong>${escapeHtml(report.name)}</strong>${scheduled(report) ? ' and its schedule' : ''}?</p>`
      + (runs ? `<p>Its ${runs} run${runs === 1 ? '' : 's'} in History and their files are deleted too. This cannot be undone.</p>` : '<p>This cannot be undone.</p>');
    const confirmed = typeof window.showConfirmDialog === 'function'
      ? Boolean(await window.showConfirmDialog('', {title: 'Delete Report', copyHtml: copy, confirmLabel: 'Delete', cancelLabel: 'Cancel'}))
      : window.confirm(`Delete the report ${report.name}?`);
    if (!confirmed) return;
    try {
      const result = await api(`/api/reporting/bundle-report-template/favourites/${report.id}`, {method: 'DELETE'});
      favourites = result.favourites;
      brtOptions.favourites = favourites;
      if (editingId === report.id) closeEditor();
      status(`${report.name} deleted.`, 'done');
      refreshPage();
    } catch (error) { status(error.message, 'error'); }
  }

  $('brt-name').addEventListener('input', () => { $('rp-editor-title').textContent = $('brt-name').value.trim() || 'New report'; changed(); });
  $('brt-title').addEventListener('input', changed);
  $('brt-subtitle').addEventListener('input', changed);
  $('brt-theme').addEventListener('change', () => { definition.theme = $('brt-theme').value; changed(); });
  $('brt-chart-pictures').addEventListener('change', () => { definition.chart_pictures = $('brt-chart-pictures').checked; changed(); });


  // -- generating a report, and viewing it -----------------------------------------------------------------
  // The dialog follows a report being generated; ready, it opens in the slide viewer of the presentations.
  const dialog = $('brt-dialog');
  const formatLabel = (format) => (format === 'word' ? 'Word' : 'PowerPoint');

  function stopPolling() {
    if (pollTimer) window.clearTimeout(pollTimer);
    pollTimer = null;
  }

  function showJob(job) {
    currentJob = job;
    jobSeenAt = Date.now();
    if (job.status === 'ready') {
      if (dialog.open) dialog.close();
      openReportViewer(job);
      return;
    }
    const failed = job.status === 'failed';
    const pending = isPending(job);
    $('brt-dialog-title').textContent = job.title || 'Drive Test Analyzer Report';
    $('brt-dialog-format').textContent = pending ? 'Generating the report' : 'Report';
    const bar = $('brt-progress-bar');
    bar.style.width = `${Math.max(3, job.progress || 0)}%`;
    bar.parentElement.setAttribute('aria-valuenow', String(job.progress || 0));
    $('brt-dialog-message').textContent = failed ? job.error || job.message : job.message || '';
    $('brt-dialog-message').dataset.tone = failed ? 'error' : '';
    // While it runs the report can be stopped or hidden; finished, the dialog closes.
    $('brt-dialog-cancel').hidden = !pending;
    $('brt-dialog-hide').hidden = !pending;
    $('brt-dialog-done').hidden = pending;
    $('brt-dialog-close').setAttribute('aria-label', pending ? 'Hide the progress' : 'Close');
    updateElapsed();
  }

  // A report in the slide viewer: its sections with their slides or pages, its formats, its warnings and its download.
  function reportPresentation(job, format, available) {
    const shown = job.formats?.[format] || {previews: 0, navigation: []};
    const groups = (shown.navigation || []).length ? shown.navigation
      : [{title: 'Pages', pages: Array.from({length: shown.previews || 0}, (_value, index) => ({index, title: job.outline[index]?.title || `Page ${index + 1}`}))}];
    // (A section is listed once, with the pages that have a preview.)
    const merged = new Map();
    groups.forEach((group) => {
      const pages = group.pages.filter((page) => page.index < (shown.previews || 0));
      if (pages.length) merged.set(group.title, [...(merged.get(group.title) || []), ...pages]);
    });
    const sections = [...merged].map(([title, pages]) => ({title, slides: pages.map((page) => page.title), pages}));
    const pageOf = sections.flatMap((section) => section.pages.map((page) => page.index));
    const reused = (job.reused || []).length ? [`Reused from an earlier export (their data has not changed): ${job.reused.join(', ')}${job.document_reused ? ', and the documents composed from them' : ''}.`] : [];
    return {
      id: `report-run-${job.id}-${format}`, title: job.title, kicker: formatLabel(format), unit: format === 'word' ? 'page' : 'slide',
      sections, download: shown.file_name, downloadLabel: formatLabel(format), notes: [...(job.warnings || []), ...reused],
      urls: {
        slide: (index, thumb = false) => `/api/reporting/runs/${job.id}/preview/${format}/${pageOf[index] ?? index}${thumb ? '' : '?large=true'}`,
        file: job.downloads?.[format] || '#',
      },
      link: (index = 0) => `${window.location.origin}/reporting?report_run=${job.id}${index > 0 ? `&slide=${index + 1}` : ''}`,
      formats: available.length > 1 ? available.map((key) => ({
        label: formatLabel(key), current: key === format,
        // The other format opens at the same section.
        select: (index) => {
          let first = 0;
          const section = sections.find((item) => { first += item.slides.length; return index < first; });
          const other = reportPresentation(job, key, available);
          const position = section ? other.sections.findIndex((item) => item.title === section.title) : -1;
          const target = position < 0 ? 0 : other.sections.slice(0, position).reduce((total, item) => total + item.slides.length, 0);
          window.PresentationViewer.open(other, target);
        },
      })) : [],
    };
  }
  function openReportViewer(job, index = 0) {
    const available = ['powerpoint', 'word'].filter((format) => job.formats?.[format]?.previews);
    if (!available.length || !window.PresentationViewer?.open) {
      if (!dialog.open) dialog.showModal();
      showJob({...job, status: 'failed', error: 'This report has no preview, which needs LibreOffice: download its files in History.'});
      return;
    }
    window.PresentationViewer.open(reportPresentation(job, available[0], available), index);
  }

  // The report keeps being generated when its dialog is hidden: a dialog tells when it is ready, here or (see app.js)
  // on any other page, where the job is remembered in this browser.
  const JOB_KEY = 'drivetest.bundleReportTemplate.job';
  let jobSeenAt = 0;
  let elapsedTimer = null;
  const isPending = (job) => ['queued', 'running'].includes(job?.status);
  const rememberJob = (job) => { try { localStorage.setItem(JOB_KEY, JSON.stringify({id: job.id, title: job.title})); } catch {} };
  const forgetJob = () => { try { localStorage.removeItem(JOB_KEY); } catch {} };
  const elapsedNow = (job) => (job?.elapsed_seconds || 0) + (isPending(job) ? Math.round((Date.now() - jobSeenAt) / 1000) : 0);
  const clock = (seconds) => `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
  const duration = (seconds = 0) => (seconds >= 60 ? `${Math.floor(seconds / 60)} min ${String(seconds % 60).padStart(2, '0')} s` : `${seconds} s`);
  function updateElapsed() {
    const job = currentJob;
    $('brt-dialog-elapsed').textContent = !job ? '' : isPending(job) ? `Processing time: ${clock(elapsedNow(job))}`
      : job.status === 'failed' || job.status === 'cancelled' ? `Processing time: ${duration(job.elapsed_seconds)}` : '';
    if (isPending(job) && !elapsedTimer) elapsedTimer = window.setInterval(() => { updateElapsed(); updateGenerateButton(); }, 1000);
    if (!isPending(job) && elapsedTimer) { window.clearInterval(elapsedTimer); elapsedTimer = null; }
  }
  // (The cards of the reports show the progress of a report being generated, from the state of the page.)
  function updateGenerateButton() {}
  function openPreview() {
    const job = currentJob;
    if (job.status !== 'ready' && !dialog.open) dialog.showModal();
    showJob(job);
    if (job.status === 'ready') forgetJob();
  }
  async function finished(job) {
    if (dialog.open) {
      if (job.status !== 'queued' && job.status !== 'running') forgetJob();
      return;
    }
    if (job.status === 'ready') {
      const escape = (value) => String(value).replace(/[&<>"']/g, (character) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[character]));
      const open = typeof window.showConfirmDialog === 'function'
        ? Boolean(await window.showConfirmDialog('', {title: 'Report Ready', copyHtml: `<p><strong>${escape(job.title)}</strong> is ready (processed in ${duration(job.elapsed_seconds)}).</p><p>Open its preview to check it and download it?</p>`,
          confirmLabel: 'Open preview', cancelLabel: 'Later'}))
        : window.confirm(`${job.title} is ready. Open its preview?`);
      forgetJob();
      if (open) openPreview();
      else updateGenerateButton();
    } else if (job.status === 'failed') {
      forgetJob();
      if (typeof window.showInfoDialog === 'function') window.showInfoDialog(job.error || job.message, {title: 'Report Failed', tone: 'error'});
      else status(job.error || job.message, 'error');
    } else {
      forgetJob();
    }
  }

  // A run as the dialog shows it: generating (running), ready with its preview, or failed (also stopped).
  function jobFromRun({run, report}) {
    const pending = ['queued', 'running', 'stopping'].includes(run.status);
    const done = ['sent', 'completed', 'partial'].includes(run.status);
    const started = Date.parse(run.started_at || run.created_at || '');
    const ended = run.finished_at ? Date.parse(run.finished_at) : Date.now();
    return {
      id: run.id, status: pending ? 'running' : done && report ? 'ready' : 'failed', progress: run.progress || 0,
      message: run.message || (pending ? 'Waiting to start' : ''),
      error: run.error || (done && !report ? 'This run has no preview: download its files in History.' : run.status === 'stopped' ? run.message : ''),
      title: report?.title || run.task_name, formats: report?.formats || {}, outline: report?.outline || [],
      warnings: report?.warnings || [], reused: report?.reused || [], document_reused: Boolean(report?.document_reused),
      downloads: report?.downloads || {}, elapsed_seconds: Number.isNaN(started) ? 0 : Math.max(0, Math.round((ended - started) / 1000)),
    };
  }

  async function poll(runId) {
    try {
      const job = jobFromRun(await api(`/api/reporting/runs/${runId}/report`));
      if (currentJob && currentJob.id && currentJob.id !== runId) return;
      // Followed in its dialog it opens by itself when it is ready; hidden, a dialog tells when it is.
      const followed = dialog.open;
      if (followed) showJob(job);
      else { currentJob = job; jobSeenAt = Date.now(); }
      if (isPending(job)) { pollTimer = window.setTimeout(() => poll(runId), 1500); return; }
      updateElapsed();
      refreshPage();
      if (followed) forgetJob();
      else await finished(job);
    } catch (error) {
      if (/no longer exists/i.test(error.message)) { forgetJob(); currentJob = null; return; }
      $('brt-dialog-message').textContent = error.message;
      pollTimer = window.setTimeout(() => poll(runId), 5000);
    }
  }

  // Generate: a run of the report (in the formats of its schedule), followed in the dialog and listed in History.
  async function generateReport(report) {
    if (isPending(currentJob) && currentJob.id) { openPreview(); return; }
    stopPolling();
    showJob({id: '', status: 'queued', progress: 0, message: 'Starting…', title: report.name, warnings: [], formats: {}, outline: []});
    if (!dialog.open) dialog.showModal();
    try {
      const result = await api(`/api/reporting/bundle-report-template/favourites/${report.id}/generate`, {method: 'POST',
        body: JSON.stringify({refresh: !$('brt-reuse').checked})});
      currentJob = {...currentJob, id: result.run_id};
      rememberJob({id: result.run_id, title: report.name});
      refreshPage();
      pollTimer = window.setTimeout(() => poll(result.run_id), 1000);
    } catch (error) {
      showJob({id: '', status: 'failed', progress: 0, message: error.message, error: error.message, title: report.name,
        warnings: [], formats: {}, outline: []});
    }
  }
  // Preview (or Follow) of a run in History or on a card: at a slide of a link, the slide viewer of a report ready.
  window.openReportRun = async (runId, index = 0) => {
    stopPolling();
    try {
      const job = jobFromRun(await api(`/api/reporting/runs/${runId}/report`));
      currentJob = job;
      jobSeenAt = Date.now();
      if (job.status === 'ready') { openReportViewer(job, index); return; }
      if (!dialog.open) dialog.showModal();
      showJob(job);
      if (isPending(job)) pollTimer = window.setTimeout(() => poll(job.id), 1500);
    } catch (error) {
      status(error.message, 'error');
    }
  };

  // Hide keeps the report being generated; Stop stops it after the step it is on; once it has finished, the dialog closes.
  const hideDialog = () => { dialog.close(); updateGenerateButton(); };
  async function cancelJob() {
    const job = currentJob;
    stopPolling();
    forgetJob();
    if (job?.id) {
      try { await api('/api/reporting/runs/stop', {method: 'POST', body: JSON.stringify({ids: [job.id]})}); } catch (error) { status(error.message, 'error'); }
    }
    currentJob = null;
    dialog.close();
    refreshPage();
    status('The report stops after the step it is on.');
  }
  $('brt-dialog-close').addEventListener('click', () => (isPending(currentJob) ? hideDialog() : dialog.close()));
  $('brt-dialog-hide').addEventListener('click', hideDialog);
  $('brt-dialog-cancel').addEventListener('click', () => { void cancelJob(); });
  $('brt-dialog-done').addEventListener('click', () => dialog.close());
  // Escape hides a report being generated, as Hide does.
  dialog.addEventListener('cancel', (event) => { if (isPending(currentJob)) { event.preventDefault(); hideDialog(); } });

  // A report generated before this page opened (Hide, or told on another page): its dialog follows it, and a link of
  // another page (?report_run=) opens its preview.
  async function resumeJob() {
    const asked = new URLSearchParams(window.location.search).get('report_run');
    if (asked) {
      // Opened once: reloading the page does not open it again.
      const url = new URL(window.location.href);
      const slide = Math.max(0, (Number.parseInt(url.searchParams.get('slide') || '1', 10) || 1) - 1);
      url.searchParams.delete('report_run');
      url.searchParams.delete('slide');
      window.history.replaceState(window.history.state, '', url);
      void window.openReportRun(Number(asked), slide);
      forgetJob();
      return;
    }
    let stored = null;
    try { stored = JSON.parse(localStorage.getItem(JOB_KEY) || 'null'); } catch {}
    if (!stored?.id || stored.notified) { if (stored?.notified) forgetJob(); return; }
    try {
      const job = jobFromRun(await api(`/api/reporting/runs/${stored.id}/report`));
      currentJob = job;
      jobSeenAt = Date.now();
      if (isPending(job)) { updateElapsed(); pollTimer = window.setTimeout(() => poll(job.id), 1500); return; }
      await finished(job);
    } catch (error) {
      if (/no longer exists/i.test(error?.message || '')) forgetJob();
      else window.setTimeout(resumeJob, 5000);
    }
  }

  // -- start -------------------------------------------------------------------------------------------
  async function load() {
    // The reports come with their options and show at once (their cards with the state of the page); the filter values
    // of every CDR (the Reporting options) arrive after them and complete the editor.
    const optionsRequest = api('/api/reporting/options');
    optionsRequest.catch(() => {});
    let draft = null;
    try { draft = JSON.parse(localStorage.getItem(DRAFT_KEY) || 'null'); } catch {}
    try {
      brtOptions = await api('/api/reporting/bundle-report-template/options');
      favourites = brtOptions.favourites || [];
      renderList();
      options = await optionsRequest;
    } catch (error) {
      status(error.message, 'error');
      return;
    }
    if (options.catalogues_pending) status('The filter values of some CDRs are being prepared in the background; reload the page in a few minutes to see all of them.', 'info');
    // The report being edited before a reload opens again with its changes (a report deleted meanwhile, as a new one).
    // (Drafts of the panel of before, without steps, are left.)
    if (draft?.definition && draft.step && canEdit()) {
      const exists = draft.id == null || favourites.some((item) => item.id === draft.id);
      await openEditor(exists ? draft.id : null, draft);
    }
  }

  // A draft saved by an earlier version gets the sections and options it lacks (a section added later, such as CDR
  // Analysis, unchecked, as in the favourites saved before it); the Campaigns it had as a common filter go to every section.
  const LATER_SECTIONS = ['dataset_analysis'];
  function mergeDefaults(saved) {
    const defaults = clone(brtOptions.defaults);
    const legacy = saved.filters?.campaigns !== undefined ? {campaigns: saved.filters.campaigns} : {};
    const sections = (saved.sections || []).filter((section) => defaults.sections.some((item) => item.key === section.key));
    defaults.sections.forEach((section) => {
      const found = sections.find((item) => item.key === section.key);
      if (!found) sections.push({...section, enabled: section.enabled && !LATER_SECTIONS.includes(section.key), options: {...section.options, ...legacy}});
      else found.options = {...section.options, ...legacy, ...(found.options || {})};
    });
    return {...defaults, ...saved, filters: {...defaults.filters, ...(saved.filters || {})}, sections};
  }

  // A report being generated is followed at once, without waiting for the panel (a busy server answers its options
  // late).
  void resumeJob();
  void load();
})();
