/* Reporting: the Bundle Report Templates panel. Its common filters, its four sections with their sub-modules, charts and
   tables (checked and ordered by dragging), the options of each section, the favourites and the export dialog that
   previews every page before the download. */
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
  let currentJob = null;
  // The last report generated from the panel, kept in the workspace: Open last report opens it whenever there is one.
  let lastReport = null;

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

  // The Campaigns of a section, which choose its CDRs: first Latest campaign, Latest 2, 3 and 4 campaigns, Previous campaign and All available campaigns,
  // which follow the newest campaigns at each export and stand alone, then the campaigns of
  // the NR Mode of the common filters (listed again when it changes, keeping a Latest choice).
  function scopeFields(saved, modeOf = nrMode) {
    const row = node('div', undefined, 'brt-scope');
    const presets = Object.entries(options.campaign_presets || {});
    const campaignValues = () => [...(options.campaigns?.[modeOf()] || [])]
      .sort((left, right) => (pickers().campaignCompare ? pickers().campaignCompare(left, right) : 0));
    let campaigns = null;
    // (Beside the Campaigns, the GAP reference of Scoring & GAP Analysis.)
    const renderCampaigns = (selected) => {
      const field = multiField('Campaigns', campaignValues(), selected, {exclusive: presets});
      field.classList.add('brt-campaigns-field');
      if (campaigns?.isConnected) campaigns.replaceWith(field);
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
    // The NR Mode on its own row: it lists the campaigns of every section and the Dashboards.
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
    nsaVsSa.title = 'Score the NSA and SA CDRs of the campaigns of this section side by side (always split by Campaign); '
      + 'the other sections keep the NR Mode of the report';
    nrModes.append(nsaVsSa);
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
      trendCampaigns = multiField('Campaigns', campaignValues(), selected, {exclusive: presets, allLabel: 'Same as the section'});
      trendCampaigns.title = 'The campaigns of the Scoring Trend and the National & Geographical Areas Trends (none: the campaigns of the section)';
      trendCampaigns.classList.add('brt-campaigns-field');
      trendHost.replaceChildren(trendCampaigns);
    };
    renderTrendCampaigns(saved.area_summary.campaigns || []);
    const refreshTrendCampaigns = () => {
      renderTrendCampaigns((trendCampaigns?.getValue?.() || []).filter((value) => presets.some(([key]) => key === value)));
    };
    nrModeHandlers.push(refreshTrendCampaigns);
    nsaVsSa.box.addEventListener('change', () => { syncReference(); refreshTrendCampaigns(); box.onNrModeChange?.(); });
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
      nsa_vs_sa: nsaVsSa.box.checked,
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

  function itemRow(sectionKey, catalogueItem, saved) {
    const row = node('li', undefined, 'brt-item');
    row.dataset.key = catalogueItem.key;
    const head = node('div', undefined, 'brt-item-head');
    const enabled = check(catalogueItem.title, saved ? saved.enabled : sectionKey !== 'dashboards', 'brt-check brt-item-check');
    head.append(handleButton('brt-item-handle', catalogueItem.title), enabled);
    if (catalogueItem.nr_mode) {
      // Each Dashboard is made for one NR Mode: the list shows those of the NR Mode of the common filters.
      row.dataset.nrMode = catalogueItem.nr_mode;
      head.append(node('span', catalogueItem.nr_mode, 'brt-badge'));
    }
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
      // A Dashboard keeps its name and NR Mode, which find it again in another workspace.
      ...(sectionKey === 'dashboards' ? {label: catalogueItem.title, nr_mode: catalogueItem.nr_mode || ''}
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
    if (!allowed) body.append(node('p', 'Your account cannot use this module: the section is left out.', 'form-note'));
    // (The Scoring section can compare NSA vs SA: its campaigns follow its own NR Mode then.)
    let sectionMode = nrMode;
    const scope = scopeFields(saved.options || {}, () => sectionMode());
    body.append(scope);
    const list = node('ol', undefined, 'brt-items');
    list.setAttribute('aria-label', `Sub-modules of ${title}`);
    const savedItems = Object.fromEntries((saved.items || []).map((item) => [item.key, item]));
    const catalogueItems = Object.fromEntries(catalogue.items.map((item) => [item.key, item]));
    const order = [...(saved.items || []).map((item) => item.key).filter((key) => catalogueItems[key]),
      ...catalogue.items.map((item) => item.key).filter((key) => !savedItems[key])];
    order.forEach((key) => list.append(itemRow(saved.key, catalogueItems[key], savedItems[key])));
    if (saved.key === 'dashboards' && !catalogue.items.length) {
      list.append(node('li', 'There are no saved Dashboards in this workspace.', 'form-note brt-empty'));
    }
    sortable(list, '.brt-item', '.brt-item-handle', changed);
    body.append(list);
    const optionsBox = saved.key === 'scoring' ? scoringOptions(saved.options)
      : saved.key === 'network_insights' ? networkOptions(saved.options)
        : saved.key === 'non_qualified_calls' ? callsOptions(saved.options) : null;
    if (optionsBox?.scopeFields) scope.append(...optionsBox.scopeFields);
    if (optionsBox?.nrMode) {
      sectionMode = optionsBox.nrMode;
      scope.refresh(true);
      optionsBox.onNrModeChange = () => { scope.refresh(); changed(); };
    }
    if (optionsBox) {
      const optionsWrap = node('div', undefined, 'brt-section-options');
      optionsWrap.append(node('h4', 'Options'), optionsBox);
      body.append(optionsWrap);
    }
    card.append(head, body);
    const empty = node('li', '', 'form-note brt-empty');
    const refresh = () => {
      if (saved.key === 'dashboards') {
        const mode = nrMode();
        list.querySelectorAll(':scope > .brt-item').forEach((row) => { row.hidden = Boolean(row.dataset.nrMode) && row.dataset.nrMode !== mode; });
        empty.textContent = `There are no saved ${mode} Dashboards in this workspace.`;
        if (catalogue.items.length) list.append(empty);
        empty.hidden = [...list.querySelectorAll(':scope > .brt-item')].some((row) => !row.hidden);
      }
      const rows = [...list.querySelectorAll(':scope > .brt-item')].filter((row) => !row.hidden);
      const chosen = rows.filter((row) => !row.classList.contains('is-off')).length;
      const noun = saved.key === 'dashboards' ? 'Dashboards' : 'sub-modules';
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
      filters: collectFilters(),
      sections: [...$('brt-sections').children].map((card) => card.collect()),
    };
  }

  function changed() {
    try { localStorage.setItem(DRAFT_KEY, JSON.stringify({definition: collect(), favourite: $('brt-favourite').value, name: $('brt-name').value})); } catch {}
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
    filterPickers = {};
    renderFilters();
    renderSections();
  }

  // -- favourites ----------------------------------------------------------------------------------
  function renderFavourites(selected = '') {
    const select = $('brt-favourite');
    select.replaceChildren(node('option', 'New Bundle Report Template'));
    select.firstElementChild.value = '';
    favourites.forEach((item) => {
      const option = node('option', item.name);
      option.value = String(item.id);
      select.append(option);
    });
    select.value = selected && favourites.some((item) => String(item.id) === String(selected)) ? String(selected) : '';
    $('brt-delete').disabled = !select.value || !brtOptions.can_edit;
    $('brt-rename').disabled = $('brt-delete').disabled;
    $('brt-save').disabled = !brtOptions.can_edit;
  }
  // The Reporting Jobs follow the favourites they generate.
  const favouritesChanged = () => document.dispatchEvent(new CustomEvent('bundle-report-template:favourites-changed'));
  const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (character) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[character]));
  // The jobs that generate a favourite: those based on it and the others.
  const jobsOf = async (favourite) => {
    try { return await api(`/api/reporting/bundle-report-template/favourites/${favourite.id}/jobs`); } catch { return {based_on: [], others: []}; }
  };

  $('brt-favourite').addEventListener('change', () => {
    const favourite = favourites.find((item) => String(item.id) === $('brt-favourite').value);
    definition = clone(favourite ? favourite.definition : brtOptions.defaults);
    $('brt-name').value = favourite ? favourite.name : '';
    $('brt-delete').disabled = !favourite || !brtOptions.can_edit;
    $('brt-rename').disabled = $('brt-delete').disabled;
    render();
    changed();
    status(favourite ? `${favourite.name} loaded.` : '');
  });
  $('brt-name').addEventListener('input', changed);
  $('brt-title').addEventListener('input', changed);
  $('brt-subtitle').addEventListener('input', changed);
  $('brt-theme').addEventListener('change', () => { definition.theme = $('brt-theme').value; changed(); });

  $('brt-save').addEventListener('click', async () => {
    const name = $('brt-name').value.trim();
    if (!name) { status('Enter a name for the favourite.', 'error'); $('brt-name').focus(); return; }
    // A name that a favourite already has overwrites it once the user confirms; another name saves a new favourite.
    const existing = favourites.find((item) => item.name.toLocaleLowerCase() === name.toLocaleLowerCase());
    if (existing) {
      const escape = (value) => String(value).replace(/[&<>"']/g, (character) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[character]));
      const confirmed = typeof window.showConfirmDialog === 'function'
        ? Boolean(await window.showConfirmDialog('', {title: 'Overwrite Favourite',
          copyHtml: `<p>A favourite Bundle Report Template named <strong>${escape(existing.name)}</strong> already exists. Overwrite it with this report?</p>`,
          confirmLabel: 'Overwrite', cancelLabel: 'Cancel'}))
        : window.confirm(`A favourite Bundle Report Template named ${existing.name} already exists. Overwrite it with this report?`);
      if (!confirmed) return;
    }
    try {
      const result = await api(existing ? `/api/reporting/bundle-report-template/favourites/${existing.id}` : '/api/reporting/bundle-report-template/favourites', {
        method: existing ? 'PUT' : 'POST', body: JSON.stringify({name, definition: collect()}),
      });
      favourites = result.favourites;
      renderFavourites(result.favourite.id);
      changed();
      status(`${result.favourite.name} saved as a favourite.`, 'done');
      favouritesChanged();
    } catch (error) {
      status(error.message, 'error');
    }
  });

  // Renaming keeps what the favourite saved (not the changes of the panel); the jobs based on it with its name take
  // the new one.
  $('brt-rename').addEventListener('click', async () => {
    const selected = favourites.find((item) => String(item.id) === $('brt-favourite').value);
    if (!selected) return;
    const named = (await jobsOf(selected)).based_on.filter((name) => name.toLocaleLowerCase() === selected.name.toLocaleLowerCase());
    const note = named.length ? `The Reporting Job${named.length === 1 ? '' : 's'} based on it with its name will take the new one.` : '';
    const answer = typeof showTextInputDialog === 'function'
      ? await showTextInputDialog('New name', {title: 'Rename Favourite', value: selected.name, maxLength: 120, confirmLabel: 'Rename', cancelLabel: 'Cancel', note})
      : window.prompt('New name of the favourite Bundle Report Template', selected.name);
    const name = String(answer ?? '').trim();
    if (!name || name === selected.name) return;
    try {
      const result = await api(`/api/reporting/bundle-report-template/favourites/${selected.id}/rename`, {method: 'POST', body: JSON.stringify({name})});
      favourites = result.favourites;
      renderFavourites(result.favourite.id);
      $('brt-name').value = result.favourite.name;
      changed();
      const jobs = result.renamed_jobs || [];
      status(`${selected.name} renamed to ${result.favourite.name}.${jobs.length ? ` Reporting Jobs renamed: ${jobs.length}.` : ''}`, 'done');
      favouritesChanged();
    } catch (error) {
      status(error.message, 'error');
    }
  });

  $('brt-delete').addEventListener('click', async () => {
    const selected = favourites.find((item) => String(item.id) === $('brt-favourite').value);
    if (!selected) return;
    // The jobs based on it are disabled and the others that generate it no longer find it.
    const jobs = await jobsOf(selected);
    const list = (names) => `<ul>${names.map((name) => `<li>${escapeHtml(name)}</li>`).join('')}</ul>`;
    const copy = `<p>Delete the favourite Bundle Report Template <strong>${escapeHtml(selected.name)}</strong>?</p>`
      + (jobs.based_on.length ? `<p>These Reporting Jobs based on it will be disabled:</p>${list(jobs.based_on)}` : '')
      + (jobs.others.length ? `<p>These Reporting Jobs also generate it and will tell that it no longer exists:</p>${list(jobs.others)}` : '');
    const confirmed = typeof window.showConfirmDialog === 'function'
      ? Boolean(await window.showConfirmDialog('', {title: 'Delete Favourite', copyHtml: copy, confirmLabel: 'Delete', cancelLabel: 'Cancel'}))
      : window.confirm(`Delete the favourite Bundle Report Template ${selected.name}?`);
    if (!confirmed) return;
    try {
      const result = await api(`/api/reporting/bundle-report-template/favourites/${selected.id}`, {method: 'DELETE'});
      favourites = result.favourites;
      renderFavourites('');
      $('brt-name').value = '';
      changed();
      const disabled = result.disabled_jobs || [];
      status(`${selected.name} deleted.${disabled.length ? ` Reporting Jobs disabled: ${disabled.join(', ')}.` : ''}`, 'done');
      favouritesChanged();
    } catch (error) {
      status(error.message, 'error');
    }
  });

  // -- export dialog --------------------------------------------------------------------------------
  const dialog = $('brt-dialog');
  const formatLabel = (format) => (format === 'word' ? 'Word' : 'PowerPoint');
  // The format shown in the preview: each report generated opens in PowerPoint. Both are generated before the preview
  // opens, so switching between them is immediate.
  let previewFormat = 'powerpoint';
  const shownFormat = (job) => job.formats?.[previewFormat] || {previews: 0, navigation: [], file_name: ''};

  function stopPolling() {
    if (pollTimer) window.clearTimeout(pollTimer);
    pollTimer = null;
  }

  function showJob(job) {
    const wasReady = currentJob?.id === job.id && currentJob?.status === 'ready';
    currentJob = job;
    jobSeenAt = Date.now();
    const ready = job.status === 'ready';
    if (ready) lastReport = job;
    const failed = job.status === 'failed';
    const pending = isPending(job);
    $('brt-dialog-title').textContent = job.title || 'Drive Test Analyzer Report';
    $('brt-dialog-format').textContent = ready ? formatLabel(previewFormat) : 'PowerPoint and Word';
    $('brt-dialog-progress').hidden = ready;
    const bar = $('brt-progress-bar');
    bar.style.width = `${Math.max(3, job.progress || 0)}%`;
    bar.parentElement.setAttribute('aria-valuenow', String(job.progress || 0));
    $('brt-dialog-message').textContent = failed ? job.error || job.message : job.message || '';
    $('brt-dialog-message').dataset.tone = failed ? 'error' : '';
    // While it runs the report can be cancelled or hidden; finished, the dialog closes.
    $('brt-dialog-cancel').hidden = !pending;
    $('brt-dialog-hide').hidden = !pending;
    $('brt-dialog-done').hidden = pending;
    $('brt-dialog-close').setAttribute('aria-label', pending ? 'Hide the progress' : 'Close the preview');
    updateElapsed();
    updateGenerateButton();
    if (wasReady) return;
    const warnings = $('brt-warnings');
    warnings.replaceChildren(...(job.warnings || []).map((warning) => node('li', warning)));
    warnings.hidden = !(job.warnings || []).length;
    $('brt-format-switch').hidden = !ready;
    // Ready, the dialog takes almost the whole screen: the sections and pages on the left, the chosen page on the right.
    dialog.classList.toggle('is-previewing', ready);
    if (ready) showFormat(0);
    else $('brt-download').hidden = true;
  }

  // The chosen format of a ready report: its summary, download, sections and pages, from ``index`` (a slide or page).
  function showFormat(index) {
    const job = currentJob;
    const shown = shownFormat(job);
    const pages = shown.previews || 0;
    const unit = previewFormat === 'word' ? 'page' : 'slide';
    const count = pages || job.outline.length;
    const reused = (job.reused || []).length ? ` Reused from an earlier export (their data has not changed): ${job.reused.join(', ')}`
      + `${job.document_reused ? ', and the documents composed from them' : ''}.` : '';
    $('brt-dialog-summary').hidden = false;
    $('brt-dialog-summary').textContent = `${count} ${unit}${count === 1 ? '' : 's'} · Processed in ${duration(job.elapsed_seconds)} · Choose a section or ${unit} on the left to check it before downloading.${reused}${pages ? '' : ' The preview needs LibreOffice: the list shows the title of each slide.'}`;
    $('brt-dialog-format').textContent = formatLabel(previewFormat);
    const download = $('brt-download');
    download.hidden = false;
    download.href = `/api/reporting/bundle-report-template/jobs/${job.id}/download/${previewFormat}`;
    download.textContent = `Download ${formatLabel(previewFormat)}`;
    $('brt-format-switch').querySelectorAll('[data-brt-format]').forEach((button) => {
      const current = button.dataset.brtFormat === previewFormat;
      button.classList.toggle('is-current', current);
      button.setAttribute('aria-pressed', String(current));
    });
    // Word shows portrait pages; PowerPoint landscape slides.
    dialog.classList.toggle('is-word', previewFormat === 'word');
    $('brt-preview').hidden = false;
    renderNavigation(job);
    stage.classList.toggle('is-empty', !pages);
    if (pages) showPage(index);
    else viewerImage.removeAttribute('src');
  }

  // Switching the format keeps the section shown: its first page (or slide) in the other format.
  function switchFormat(format) {
    if (format === previewFormat || currentJob?.status !== 'ready') return;
    const group = (shownFormat(currentJob).navigation || []).find((item) => item.pages.some((page) => page.index === viewerIndex));
    previewFormat = format;
    const target = group && (shownFormat(currentJob).navigation || []).find((item) => item.title === group.title);
    showFormat(target?.pages[0]?.index || 0);
  }

  // The sections of the report with their pages (or slides): selecting one shows it.
  function renderNavigation(job) {
    const nav = $('brt-preview-nav');
    const shown = shownFormat(job);
    const groups = (shown.navigation || []).length ? shown.navigation
      : [{title: 'Pages', pages: Array.from({length: shown.previews || job.outline.length}, (_value, index) => ({index, title: job.outline[index]?.title || `Page ${index + 1}`}))}];
    nav.replaceChildren(...groups.map((group) => {
      const section = node('section', undefined, 'brt-nav-section');
      const heading = node('button', group.title, 'brt-nav-heading');
      heading.type = 'button';
      heading.title = `Go to ${group.title}`;
      heading.addEventListener('click', () => { if (group.pages.length) showPage(group.pages[0].index); });
      const list = node('ol', undefined, 'brt-nav-pages');
      group.pages.forEach((page) => {
        const item = node('li');
        const button = node('button', undefined, 'brt-nav-page');
        button.type = 'button';
        button.dataset.page = String(page.index);
        button.append(node('span', String(page.index + 1), 'brt-nav-number'), node('span', page.title, 'brt-nav-title'));
        button.title = page.title;
        button.disabled = !shown.previews;
        button.addEventListener('click', () => showPage(page.index));
        item.append(button);
        list.append(item);
      });
      section.append(heading, list);
      return section;
    }));
  }

  // -- the chosen page, zoomed with the wheel, a rectangle or the buttons, as the Scoring charts ---------------------
  const stage = $('brt-viewer-stage');
  const viewerImage = $('brt-viewer-image');
  let viewerIndex = 0;
  // Each page shown has its token: images of a page left in the meantime are ignored when they arrive.
  let pageToken = 0;
  let view = {scale: 1, fit: 1, x: 0, y: 0};
  const prefetched = new Map();

  function renderView() {
    viewerImage.style.transform = `translate(${view.x}px, ${view.y}px) scale(${view.scale})`;
    stage.classList.toggle('is-zoomed', view.scale > view.fit * 1.001);
  }
  // The page keeps covering the stage once larger than it, and stays centred while smaller.
  function clampView() {
    const width = viewerImage.naturalWidth * view.scale, height = viewerImage.naturalHeight * view.scale;
    view.x = width <= stage.clientWidth ? (stage.clientWidth - width) / 2 : Math.min(0, Math.max(stage.clientWidth - width, view.x));
    view.y = height <= stage.clientHeight ? (stage.clientHeight - height) / 2 : Math.min(0, Math.max(stage.clientHeight - height, view.y));
  }
  // A slide fills the width of the stage; a Word page its height (both fit whole).
  function fitView() {
    if (!viewerImage.naturalWidth || !stage.clientWidth) return;
    view.fit = Math.min(stage.clientWidth / viewerImage.naturalWidth, stage.clientHeight / viewerImage.naturalHeight);
    view.scale = view.fit;
    clampView();
    renderView();
  }
  function zoomView(factor, centerX = stage.clientWidth / 2, centerY = stage.clientHeight / 2) {
    const next = Math.min(view.fit * 12, Math.max(view.fit, view.scale * factor));
    view.x = centerX - (centerX - view.x) * next / view.scale;
    view.y = centerY - (centerY - view.y) * next / view.scale;
    view.scale = next;
    clampView();
    renderView();
  }
  const pageUrl = (index, large = true) => `/api/reporting/bundle-report-template/jobs/${currentJob.id}/preview/${previewFormat}/${index}${large ? '?large=true' : ''}`;
  function showPage(index) {
    const total = shownFormat(currentJob || {}).previews || 0;
    if (!total) return;
    viewerIndex = Math.max(0, Math.min(total - 1, index));
    const unit = previewFormat === 'word' ? 'Page' : 'Slide';
    $('brt-page-label').textContent = `${unit} ${viewerIndex + 1} / ${total}`;
    viewerImage.alt = `${unit} ${viewerIndex + 1}`;
    // The page shows at once from its preview image, then sharper once its large rendering arrives (keeping the zoom).
    const token = ++pageToken;
    let sharp = false;
    viewerImage.onload = () => { if (token === pageToken && !sharp) { stage.classList.remove('is-loading'); fitView(); } };
    viewerImage.src = pageUrl(viewerIndex, false);
    const large = new Image();
    large.onload = () => {
      if (token !== pageToken) return;
      const zoom = view.fit && viewerImage.naturalWidth ? view.scale / view.fit : 1;
      sharp = true;
      viewerImage.onload = () => {
        if (token !== pageToken) return;
        stage.classList.remove('is-loading');
        fitView();
        if (zoom > 1.001) zoomView(zoom);
      };
      viewerImage.src = large.src;
    };
    large.src = pageUrl(viewerIndex);
    document.querySelectorAll('.brt-nav-page').forEach((button) => {
      const current = Number(button.dataset.page) === viewerIndex;
      button.classList.toggle('is-current', current);
      if (current) {
        button.setAttribute('aria-current', 'page');
        button.scrollIntoView({block: 'nearest'});
      } else {
        button.removeAttribute('aria-current');
      }
    });
    // The next page is fetched ahead, so moving through the report does not wait for it.
    const next = viewerIndex + 1;
    if (next < total && !prefetched.has(`${currentJob.id}:${previewFormat}:${next}`)) {
      const image = new Image();
      image.src = pageUrl(next);
      prefetched.set(`${currentJob.id}:${previewFormat}:${next}`, image);
    }
  }
  const local = (event) => {
    const bounds = stage.getBoundingClientRect();
    return {x: event.clientX - bounds.left, y: event.clientY - bounds.top};
  };
  stage.addEventListener('wheel', (event) => {
    if (!viewerImage.naturalWidth) return;
    event.preventDefault();
    const point = local(event);
    zoomView(Math.exp(-event.deltaY * 0.0015), point.x, point.y);
  }, {passive: false});
  let drag = null;
  stage.addEventListener('pointerdown', (event) => {
    if ((event.button !== 0 && event.button !== 1) || !viewerImage.naturalWidth) return;
    event.preventDefault();
    const start = local(event);
    const pan = event.button === 1 || event.shiftKey;
    const rectangle = pan ? null : node('div', undefined, 'brt-viewer-rect');
    if (rectangle) stage.append(rectangle);
    drag = {start, pan, rectangle, x: view.x, y: view.y};
    try { stage.setPointerCapture(event.pointerId); } catch {}
    stage.classList.toggle('is-panning', pan);
  });
  stage.addEventListener('pointermove', (event) => {
    if (!drag) return;
    const point = local(event);
    if (drag.pan) {
      view.x = drag.x + point.x - drag.start.x;
      view.y = drag.y + point.y - drag.start.y;
      clampView();
      renderView();
      return;
    }
    Object.assign(drag.rectangle.style, {
      left: `${Math.min(drag.start.x, point.x)}px`, top: `${Math.min(drag.start.y, point.y)}px`,
      width: `${Math.abs(point.x - drag.start.x)}px`, height: `${Math.abs(point.y - drag.start.y)}px`,
    });
  });
  const endDrag = (event) => {
    if (!drag) return;
    const {start, pan, rectangle} = drag;
    drag = null;
    stage.classList.remove('is-panning');
    if (pan || !rectangle) return;
    rectangle.remove();
    if (!event) return;
    const point = local(event);
    const width = Math.abs(point.x - start.x), height = Math.abs(point.y - start.y);
    // A click (or a tiny rectangle) does not zoom.
    if (width < 8 || height < 8) return;
    const factor = Math.min(stage.clientWidth / width, stage.clientHeight / height);
    const centerX = (start.x + point.x) / 2, centerY = (start.y + point.y) / 2;
    const next = Math.min(view.fit * 12, view.scale * factor);
    view.x = stage.clientWidth / 2 - (centerX - view.x) * next / view.scale;
    view.y = stage.clientHeight / 2 - (centerY - view.y) * next / view.scale;
    view.scale = next;
    clampView();
    renderView();
  };
  stage.addEventListener('pointerup', endDrag);
  stage.addEventListener('pointercancel', () => endDrag(null));
  stage.addEventListener('dblclick', fitView);
  dialog.addEventListener('keydown', (event) => {
    if (!dialog.classList.contains('is-previewing') || event.target.closest?.('input, select, textarea')) return;
    if (event.key === 'ArrowLeft') showPage(viewerIndex - 1);
    else if (event.key === 'ArrowRight') showPage(viewerIndex + 1);
    else if (event.key === '+' || event.key === '=') zoomView(1.4);
    else if (event.key === '-') zoomView(1 / 1.4);
    else if (event.key === '0') fitView();
    else return;
    event.preventDefault();
  });
  dialog.querySelectorAll('[data-brt-viewer]').forEach((button) => button.addEventListener('click', () => {
    const action = button.dataset.brtViewer;
    if (action === 'previous') showPage(viewerIndex - 1);
    else if (action === 'next') showPage(viewerIndex + 1);
    else if (action === 'zoom-in') zoomView(1.4);
    else if (action === 'zoom-out') zoomView(1 / 1.4);
    else fitView();
  }));
  window.addEventListener('resize', () => { if (dialog.open && dialog.classList.contains('is-previewing')) fitView(); });

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
  // While a report is generated in the background, Generate shows its progress and opens its dialog.
  function updateGenerateButton() {
    const button = root.querySelector('[data-brt-export]');
    const label = button?.querySelector('span');
    if (!label) return;
    const pending = isPending(currentJob) && Boolean(currentJob.id);
    label.textContent = pending ? `Generating · ${currentJob.progress || 0}% · ${clock(elapsedNow(currentJob))}` : 'Generate';
    button.classList.toggle('is-generating', pending);
    if (currentJob?.status === 'ready') lastReport = currentJob;
    $('brt-open-last').hidden = pending || !lastReport || dialog.open;
  }
  function openPreview() {
    if (!dialog.open) dialog.showModal();
    const job = currentJob;
    currentJob = null;
    $('brt-preview').hidden = true;
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
        ? Boolean(await window.showConfirmDialog('', {title: 'Report Ready', copyHtml: `<p><strong>${escape(job.title)}</strong> is ready in PowerPoint and Word (processed in ${duration(job.elapsed_seconds)}).</p><p>Open its preview to check it and download it?</p>`,
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

  async function poll(jobId) {
    try {
      const result = await api(`/api/reporting/bundle-report-template/jobs/${jobId}`);
      if (currentJob && currentJob.id && currentJob.id !== jobId) return;
      const before = currentJob?.status;
      if (!dialog.open && result.job.status === 'ready') currentJob = result.job;
      else showJob(result.job);
      if (isPending(result.job)) pollTimer = window.setTimeout(() => poll(jobId), 1500);
      else if (before !== result.job.status || !dialog.open) { currentJob = result.job; updateElapsed(); await finished(result.job); }
    } catch (error) {
      if (/no longer available/i.test(error.message)) { forgetJob(); currentJob = null; updateGenerateButton(); return; }
      $('brt-dialog-message').textContent = error.message;
      pollTimer = window.setTimeout(() => poll(jobId), 5000);
    }
  }

  // The report is generated in PowerPoint and in Word, with both previews, before the preview opens.
  async function exportReport() {
    if (isPending(currentJob) && currentJob.id) { openPreview(); return; }
    stopPolling();
    previewFormat = 'powerpoint';
    $('brt-preview').hidden = true;
    $('brt-preview-nav').replaceChildren();
    viewerImage.removeAttribute('src');
    stage.classList.remove('is-empty', 'is-loading');
    showJob({id: '', status: 'queued', progress: 0, message: 'Starting…', title: $('brt-title').value.trim() || $('brt-name').value.trim() || 'Drive Test Analyzer Report',
      warnings: [], formats: {}, outline: []});
    if (!dialog.open) dialog.showModal();
    try {
      const result = await api('/api/reporting/bundle-report-template/jobs', {method: 'POST', body: JSON.stringify({
        definition: collect(), name: $('brt-name').value.trim(), refresh: !$('brt-reuse').checked,
      })});
      showJob(result.job);
      rememberJob(result.job);
      pollTimer = window.setTimeout(() => poll(result.job.id), 1000);
    } catch (error) {
      showJob({id: '', status: 'failed', progress: 0, message: error.message, error: error.message, title: 'Drive Test Analyzer Report',
        warnings: [], formats: {}, outline: []});
    }
  }

  root.querySelectorAll('[data-brt-export]').forEach((button) => button.addEventListener('click', () => {
    // While a report is generated, Generate opens its progress again, with Cancel and Hide (also before the panel and
    // the progress of a report followed after a reload have arrived).
    if (isPending(currentJob) && currentJob.id) { openPreview(); return; }
    if (!currentJob && resumingJob) {
      jobSeenAt = Date.now();
      currentJob = {id: resumingJob.id, status: 'running', progress: 0, message: 'Following the report being generated…',
        title: resumingJob.title || 'Drive Test Analyzer Report', warnings: [], formats: {}, outline: []};
      openPreview();
      return;
    }
    if (!definition) { status('The Bundle Report Template is still loading.', 'error'); return; }
    void exportReport();
  }));
  $('brt-format-switch').querySelectorAll('[data-brt-format]').forEach((button) => button.addEventListener('click', () => switchFormat(button.dataset.brtFormat)));
  // Hide keeps the report being generated; Cancel stops it; once it has finished, the dialog closes.
  const hideDialog = () => { dialog.close(); updateGenerateButton(); };
  async function cancelJob() {
    const job = currentJob;
    stopPolling();
    forgetJob();
    if (job?.id) {
      try { showJob((await api(`/api/reporting/bundle-report-template/jobs/${job.id}/cancel`, {method: 'POST'})).job); } catch {}
    }
    currentJob = null;
    dialog.close();
    updateGenerateButton();
    status('The report was cancelled.');
  }
  $('brt-dialog-close').addEventListener('click', () => (isPending(currentJob) ? hideDialog() : dialog.close()));
  $('brt-dialog-hide').addEventListener('click', hideDialog);
  $('brt-dialog-cancel').addEventListener('click', () => { void cancelJob(); });
  $('brt-dialog-done').addEventListener('click', () => dialog.close());
  $('brt-open-last').addEventListener('click', () => {
    if (!lastReport || (isPending(currentJob) && currentJob.id)) return;
    currentJob = lastReport;
    openPreview();
  });
  // Escape hides a report being generated, as Hide does.
  dialog.addEventListener('cancel', (event) => { if (isPending(currentJob)) { event.preventDefault(); hideDialog(); } });
  dialog.addEventListener('close', updateGenerateButton);

  // A report generated before this page opened (in the background, or from another page): its dialog follows it.
  let resumingJob = null;
  async function resumeJob() {
    const asked = new URLSearchParams(window.location.search).get('bundle_report_template_job');
    if (asked) {
      // Opened once: reloading the page does not open it again.
      const url = new URL(window.location.href);
      url.searchParams.delete('bundle_report_template_job');
      window.history.replaceState(window.history.state, '', url);
    }
    let stored = null;
    try { stored = JSON.parse(localStorage.getItem(JOB_KEY) || 'null'); } catch {}
    const jobId = asked || stored?.id;
    if (!jobId) return;
    // Generate tells at once that a report is being generated, before its progress arrives.
    const label = root.querySelector('[data-brt-export] span');
    if (label && !asked && !stored?.notified && !currentJob) {
      label.textContent = 'Generating…';
      resumingJob = {id: jobId, title: stored?.title};
    }
    try {
      const {job} = await api(`/api/reporting/bundle-report-template/jobs/${jobId}`);
      resumingJob = null;
      // Its progress opened meanwhile from Generate: the dialog shows what arrived.
      const opened = dialog.open && currentJob?.id === job.id;
      currentJob = job;
      jobSeenAt = Date.now();
      if (opened) { showJob(job); if (isPending(job)) pollTimer = window.setTimeout(() => poll(job.id), 1500); else await finished(job); return; }
      if (asked && job.status === 'ready') { openPreview(); return; }
      // Told on another page and left for later: Open last report opens it.
      if (stored?.notified && !asked) { forgetJob(); updateGenerateButton(); return; }
      if (isPending(job)) { updateElapsed(); updateGenerateButton(); pollTimer = window.setTimeout(() => poll(job.id), 1500); return; }
      await finished(job);
    } catch (error) {
      // A report no longer kept is forgotten; a busy or unreachable server is asked again.
      if (/no longer available/i.test(error?.message || '')) { forgetJob(); updateGenerateButton(); }
      else window.setTimeout(resumeJob, 5000);
    }
  }

  // -- start -------------------------------------------------------------------------------------------
  async function load() {
    // The favourites come with the Bundle Report Template options and show at once; the filter values of every CDR (the
    // Reporting options) arrive after them and complete the panel.
    const optionsRequest = api('/api/reporting/options');
    optionsRequest.catch(() => {});
    let draft = null;
    // A draft saved when Bundle Report Templates had a former name is restored too.
    const formerDraftKeys = ['reporting:bundle-reports-template:draft', 'reporting:reporting-jobs-template:draft', 'reporting:complete-report:draft'];
    try { draft = JSON.parse([DRAFT_KEY, ...formerDraftKeys].map((key) => localStorage.getItem(key)).find(Boolean) || 'null'); } catch {}
    try {
      brtOptions = await api('/api/reporting/bundle-report-template/options');
      favourites = brtOptions.favourites || [];
      if (!lastReport && brtOptions.last_report) { lastReport = brtOptions.last_report; updateGenerateButton(); }
      renderFavourites(draft?.favourite || '');
      $('brt-name').value = draft?.name || '';
      $('brt-favourite').disabled = true;
      options = await optionsRequest;
    } catch (error) {
      status(error.message, 'error');
      $('brt-filters').replaceChildren(node('p', error.message, 'form-note'));
      return;
    }
    $('brt-favourite').disabled = false;
    definition = clone(draft?.definition && draft.definition.sections ? mergeDefaults(draft.definition) : brtOptions.defaults);
    render();
    if (options.catalogues_pending) status('The filter values of some CDRs are being prepared in the background; reload the page in a few minutes to see all of them.', 'info');
  }

  // A draft saved by an earlier version gets the sections and options it lacks; the Campaigns it had as a common filter
  // go to every section.
  function mergeDefaults(saved) {
    const defaults = clone(brtOptions.defaults);
    const legacy = saved.filters?.campaigns !== undefined ? {campaigns: saved.filters.campaigns} : {};
    const sections = (saved.sections || []).filter((section) => defaults.sections.some((item) => item.key === section.key));
    defaults.sections.forEach((section) => {
      const found = sections.find((item) => item.key === section.key);
      if (!found) sections.push({...section, options: {...section.options, ...legacy}});
      else found.options = {...section.options, ...legacy, ...(found.options || {})};
    });
    return {...defaults, ...saved, filters: {...defaults.filters, ...(saved.filters || {})}, sections};
  }

  // A report being generated is followed at once, without waiting for the panel (a busy server answers its options
  // late).
  void resumeJob();
  void load();
})();
