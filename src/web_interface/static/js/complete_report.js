/* Reporting: the Complete Report panel. Its common filters, its four sections with their sub-modules, charts and
   tables (checked and ordered by dragging), the options of each section, the favourites and the export dialog that
   previews every page before the download. */
(() => {
  'use strict';

  const root = document.getElementById('complete-report');
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
  const DRAFT_KEY = 'reporting:complete-report:draft';
  const COLLAPSED_KEY = (key) => `reporting:complete-report:collapsed:${key}`;
  const FILTERS = [['operators', 'Operators', 'Operator'], ['operator_vendors', 'Operator_Vendor', 'Operator_Vendor'],
    ['vendor_operators', 'Vendor_Operator', 'Vendor_Operator'], ['vendors', 'Vendors', 'Vendor'], ['regions', 'Regions', 'Region'],
    ['clusters', 'Clusters', 'Cluster'], ['cities', 'Cities', 'City']];
  const NI_ENVIRONMENTS = ['Cities', 'Towns', 'Roads and railways'];

  let options = null;
  let crOptions = null;
  let definition = null;
  let filterPickers = {};
  let favourites = [];
  let pollTimer = null;
  let currentJob = null;

  const status = (message, tone = '') => {
    const element = $('cr-status');
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
    const button = node('button', '', `cr-handle ${className}`);
    button.type = 'button';
    button.title = `Drag to move ${label}, or use the arrow keys`;
    button.setAttribute('aria-label', `Move ${label}`);
    button.innerHTML = '<svg viewBox="0 0 12 18" aria-hidden="true"><circle cx="3" cy="3" r="1.6"/><circle cx="9" cy="3" r="1.6"/><circle cx="3" cy="9" r="1.6"/><circle cx="9" cy="9" r="1.6"/><circle cx="3" cy="15" r="1.6"/><circle cx="9" cy="15" r="1.6"/></svg>';
    return button;
  };

  // -- small fields ---------------------------------------------------------------------------
  const check = (label, checked, className = 'cr-check') => {
    const wrapper = node('label', undefined, className);
    const box = node('input');
    box.type = 'checkbox';
    box.checked = Boolean(checked);
    wrapper.append(box, node('span', label));
    wrapper.box = box;
    return wrapper;
  };
  const selectField = (label, choices, value) => {
    const wrapper = node('label', label, 'cr-field');
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
  const numberField = (label, value, step, title = '') => {
    const wrapper = node('label', label, 'cr-field');
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

  // The Campaigns of a section, which choose its CDRs: first Latest campaign, Previous campaign, Latest 2 campaigns and
  // All available campaigns, which follow the newest campaigns at each export and stand alone, then the campaigns of
  // the NR Mode of the common filters (listed again when it changes, keeping a Latest choice).
  function scopeFields(saved) {
    const row = node('div', undefined, 'cr-scope');
    const presets = Object.entries(options.campaign_presets || {});
    const campaignValues = () => [...(options.campaigns?.[nrMode()] || [])]
      .sort((left, right) => (pickers().campaignCompare ? pickers().campaignCompare(left, right) : 0));
    let campaigns = null;
    const renderCampaigns = (selected) => {
      campaigns = multiField('Campaigns', campaignValues(), selected, {exclusive: presets});
      row.replaceChildren(campaigns);
    };
    renderCampaigns(saved.campaigns || []);
    nrModeHandlers.push(() => {
      renderCampaigns((campaigns?.getValue?.() || []).filter((value) => presets.some(([key]) => key === value)));
    });
    row.collect = () => ({campaigns: campaigns?.getValue?.() || []});
    return row;
  }

  function renderFilters() {
    const host = $('cr-filters');
    const filters = definition.filters;
    // The NR Mode on its own row: it lists the campaigns of every section and the Dashboards.
    const mode = selectField('NR Mode', [['NSA', 'NSA (Non-Standalone)'], ['SA', 'SA (Standalone)']], filters.nr_mode || 'NSA');
    mode.input.id = 'cr-nr-mode';
    filterPickers.nr_mode = mode.input;
    mode.input.addEventListener('change', () => { nrModeHandlers.forEach((handler) => handler()); changed(); });
    const modeRow = node('div', undefined, 'cr-filter-mode');
    modeRow.append(mode);
    const grid = node('div', undefined, 'cr-filter-grid');
    const fields = FILTERS.map(([key, label, valuesKey]) => {
      const extra = key === 'cities' ? {preset: {label: 'Main Cities (workspace list at each export)', values: options.main_cities || [],
        checked: filters.main_cities, dynamic: true}} : {};
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
  const sectionCatalogue = (key) => crOptions.catalogue.sections.find((section) => section.key === key);
  const operatorValues = () => options.values?.Operator || [];

  function scoringOptions(saved) {
    const box = node('div', undefined, 'cr-options');
    const scorings = node('fieldset', undefined, 'cr-choice-group');
    scorings.append(node('legend', 'Scorings'));
    const scoringBoxes = crOptions.scorings.map((item) => {
      const field = check(item.label, saved.scorings.includes(item.value));
      field.box.value = item.value;
      scorings.append(field);
      return field.box;
    });
    const environments = node('fieldset', undefined, 'cr-choice-group');
    environments.append(node('legend', 'Environments'));
    const environmentBoxes = [{value: 'all', label: 'All Environments'}, ...crOptions.scoring_environments].map((item) => {
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
    const reference = selectField('GAP reference', (operators.includes(saved.baseline_operator) ? operators : [saved.baseline_operator, ...operators])
      .map((value) => [value, value]), saved.baseline_operator);
    const compared = multiField('Compared operators', operators, saved.compared_operators);
    compared.title = 'The operators GAP Analysis compares with the GAP reference (all when none is chosen)';
    const theme = selectField('Theme', (options.scoring_themes || []).map((item) => [item.id, item.label || item.id]), saved.theme);
    const tables = node('fieldset', undefined, 'cr-choice-group');
    tables.append(node('legend', 'Scoring tables'));
    const kpiValues = check('Show KPI values', saved.kpi_values);
    const gapValues = check('Show GAP values', saved.gap_values);
    tables.append(kpiValues, gapValues);
    // The Scoring Trends: their campaigns (none: those of the section) and, inside them, the National & Areas Trends.
    const trends = node('fieldset', undefined, 'cr-choice-group cr-trends');
    trends.append(node('legend', 'Scoring Trends'));
    const presets = Object.entries(options.campaign_presets || {});
    const campaignValues = () => [...(options.campaigns?.[nrMode()] || [])]
      .sort((left, right) => (pickers().campaignCompare ? pickers().campaignCompare(left, right) : 0));
    const trendHost = node('div', undefined, 'cr-trend-campaigns');
    let trendCampaigns = null;
    const renderTrendCampaigns = (selected) => {
      trendCampaigns = multiField('Campaigns', campaignValues(), selected, {exclusive: presets, allLabel: 'Same as the section'});
      trendCampaigns.title = 'The campaigns of the Scoring Trend and the National & Areas Trends (none: the campaigns of the section)';
      trendHost.replaceChildren(trendCampaigns);
    };
    renderTrendCampaigns(saved.area_summary.campaigns || []);
    nrModeHandlers.push(() => {
      renderTrendCampaigns((trendCampaigns?.getValue?.() || []).filter((value) => presets.some(([key]) => key === value)));
    });
    const area = node('fieldset', undefined, 'cr-choice-group cr-area');
    const areaEnabled = check('Include National & Areas Trends', saved.area_summary.enabled);
    areaEnabled.title = 'When the common filters choose no Region, Cluster or City: the National scoring next to each area, with the campaigns of the Scoring Trends';
    const areaLegend = node('legend');
    areaLegend.append(areaEnabled);
    area.append(areaLegend);
    const breakdown = selectField('Rows', crOptions.area_summary_breakdowns.map((value) => [value, value === 'None' ? 'National only' : `Each ${value}`]),
      saved.area_summary.breakdown);
    const timeSplit = selectField('Time split', crOptions.area_summary_time_splits.map((value) => [value, value === 'All' ? 'All selected CDRs' : value]),
      saved.area_summary.time_split);
    area.append(breakdown, timeSplit);
    trends.append(trendHost, area);
    const grid = node('div', undefined, 'cr-option-grid');
    grid.append(methodology, reference, theme, compared);
    box.append(scorings, environments, tables, grid, trends);
    box.collect = () => ({
      scorings: scoringBoxes.filter((item) => item.checked).map((item) => item.value),
      environments: environmentBoxes.filter((item) => item.checked).map((item) => item.value),
      kpi_values: kpiValues.box.checked, gap_values: gapValues.box.checked,
      baseline_operator: reference.input.value, methodology: methodology.input.value,
      compared_operators: compared.getValue?.() || [], theme: theme.input.value,
      area_summary: {enabled: areaEnabled.box.checked, breakdown: breakdown.input.value, time_split: timeSplit.input.value,
        campaigns: trendCampaigns?.getValue?.() || []},
    });
    return box;
  }

  function networkOptions(saved) {
    const box = node('div', undefined, 'cr-options');
    const technology = selectField('Technology', Object.entries(crOptions.network_technologies), saved.technology);
    const group = multiField('Split by', Object.keys(crOptions.network_groupings), saved.group);
    // The Split by picker lists keys: their labels are shown instead.
    group.querySelectorAll?.('.rj-multi-option span').forEach((span) => {
      span.textContent = crOptions.network_groupings[span.textContent] || span.textContent;
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
    const grid = node('div', undefined, 'cr-option-grid');
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
    const box = node('div', undefined, 'cr-options');
    const periods = selectField('Progress periods', Object.entries(crOptions.nq_granularities), saved.granularity);
    const calls = selectField('Calls', [['', 'Every call'], ['1', 'Open calls only']], saved.open_only ? '1' : '');
    const suggestions = selectField('Root Cause Analysis', [['1', 'Count suggested root causes'], ['', 'Labelled root causes only']],
      saved.include_suggestions ? '1' : '');
    const notClassified = check('Show Not classified calls', saved.show_not_classified);
    const empty = check('Show calls without a value in the phases', saved.show_empty);
    const grid = node('div', undefined, 'cr-option-grid');
    grid.append(periods, calls, suggestions);
    const flags = node('div', undefined, 'cr-inline');
    flags.append(notClassified, empty);
    box.append(grid, flags);
    box.collect = () => ({
      granularity: periods.input.value, open_only: calls.input.value === '1', include_suggestions: suggestions.input.value === '1',
      show_not_classified: notClassified.box.checked, show_empty: empty.box.checked,
    });
    return box;
  }

  function itemRow(sectionKey, catalogueItem, saved) {
    const row = node('li', undefined, 'cr-item');
    row.dataset.key = catalogueItem.key;
    const head = node('div', undefined, 'cr-item-head');
    const enabled = check(catalogueItem.title, saved ? saved.enabled : sectionKey !== 'dashboards', 'cr-check cr-item-check');
    head.append(handleButton('cr-item-handle', catalogueItem.title), enabled);
    if (catalogueItem.nr_mode) {
      // Each Dashboard is made for one NR Mode: the list shows those of the NR Mode of the common filters.
      row.dataset.nrMode = catalogueItem.nr_mode;
      head.append(node('span', catalogueItem.nr_mode, 'cr-badge'));
    }
    row.append(head);
    const boxes = [];
    if (catalogueItem.components.length) {
      const count = node('span', '', 'cr-count');
      const toggle = node('button', 'Charts & tables', 'cr-expand');
      toggle.type = 'button';
      const components = node('div', undefined, 'cr-components');
      catalogueItem.components.forEach((component) => {
        const field = check(component.title, saved ? saved.components?.[component.key] !== false : true);
        field.box.value = component.key;
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
    const allowed = crOptions.allowed_sections[saved.key];
    const title = crOptions.section_titles[saved.key] || catalogue.title;
    const card = node('li', undefined, `cr-section cr-section-${saved.key}`);
    card.dataset.key = saved.key;
    const head = node('div', undefined, 'cr-section-head');
    const enabled = check(title, allowed && saved.enabled, 'cr-check cr-section-check');
    enabled.box.disabled = !allowed;
    const summary = node('span', '', 'cr-count');
    const collapse = node('button', 'Collapse', 'collapse-chip cr-collapse');
    collapse.type = 'button';
    head.append(handleButton('cr-section-handle', title), enabled, summary, collapse);
    const body = node('div', undefined, 'cr-section-body');
    if (!allowed) body.append(node('p', 'Your account cannot use this module: the section is left out.', 'form-note'));
    const scope = scopeFields(saved.options || {});
    body.append(scope);
    const list = node('ol', undefined, 'cr-items');
    list.setAttribute('aria-label', `Sub-modules of ${title}`);
    const savedItems = Object.fromEntries((saved.items || []).map((item) => [item.key, item]));
    const catalogueItems = Object.fromEntries(catalogue.items.map((item) => [item.key, item]));
    const order = [...(saved.items || []).map((item) => item.key).filter((key) => catalogueItems[key]),
      ...catalogue.items.map((item) => item.key).filter((key) => !savedItems[key])];
    order.forEach((key) => list.append(itemRow(saved.key, catalogueItems[key], savedItems[key])));
    if (saved.key === 'dashboards' && !catalogue.items.length) {
      list.append(node('li', 'There are no saved Dashboards in this workspace.', 'form-note cr-empty'));
    }
    sortable(list, '.cr-item', '.cr-item-handle', changed);
    body.append(list);
    const optionsBox = saved.key === 'scoring' ? scoringOptions(saved.options)
      : saved.key === 'network_insights' ? networkOptions(saved.options)
        : saved.key === 'non_qualified_calls' ? callsOptions(saved.options) : null;
    if (optionsBox) {
      const optionsWrap = node('div', undefined, 'cr-section-options');
      optionsWrap.append(node('h4', 'Options'), optionsBox);
      body.append(optionsWrap);
    }
    card.append(head, body);
    const empty = node('li', '', 'form-note cr-empty');
    const refresh = () => {
      if (saved.key === 'dashboards') {
        const mode = nrMode();
        list.querySelectorAll(':scope > .cr-item').forEach((row) => { row.hidden = Boolean(row.dataset.nrMode) && row.dataset.nrMode !== mode; });
        empty.textContent = `There are no saved ${mode} Dashboards in this workspace.`;
        if (catalogue.items.length) list.append(empty);
        empty.hidden = [...list.querySelectorAll(':scope > .cr-item')].some((row) => !row.hidden);
      }
      const rows = [...list.querySelectorAll(':scope > .cr-item')].filter((row) => !row.hidden);
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
      items: [...list.querySelectorAll(':scope > .cr-item')].map((row) => row.collect()),
      options: {...(optionsBox ? optionsBox.collect() : {}), ...scope.collect()},
    });
    return card;
  }

  function renderSections() {
    nrModeHandlers = [];
    const list = $('cr-sections');
    list.replaceChildren(...definition.sections.map((section) => sectionCard(section)));
  }
  sortable($('cr-sections'), '.cr-section', '.cr-section-handle', changed);

  function collect() {
    return {
      title: $('cr-title').value.trim(),
      subtitle: $('cr-subtitle').value.trim(),
      filters: collectFilters(),
      sections: [...$('cr-sections').children].map((card) => card.collect()),
    };
  }

  function changed() {
    try { localStorage.setItem(DRAFT_KEY, JSON.stringify({definition: collect(), favourite: $('cr-favourite').value, name: $('cr-name').value})); } catch {}
  }

  function render() {
    $('cr-title').value = definition.title || '';
    $('cr-subtitle').value = definition.subtitle || '';
    filterPickers = {};
    renderFilters();
    renderSections();
  }

  // -- favourites ----------------------------------------------------------------------------------
  function renderFavourites(selected = '') {
    const select = $('cr-favourite');
    select.replaceChildren(node('option', 'New Complete Report'));
    select.firstElementChild.value = '';
    favourites.forEach((item) => {
      const option = node('option', item.name);
      option.value = String(item.id);
      select.append(option);
    });
    select.value = selected && favourites.some((item) => String(item.id) === String(selected)) ? String(selected) : '';
    $('cr-delete').disabled = !select.value || !crOptions.can_edit;
    $('cr-save').disabled = !crOptions.can_edit;
  }

  $('cr-favourite').addEventListener('change', () => {
    const favourite = favourites.find((item) => String(item.id) === $('cr-favourite').value);
    definition = clone(favourite ? favourite.definition : crOptions.defaults);
    $('cr-name').value = favourite ? favourite.name : '';
    $('cr-delete').disabled = !favourite || !crOptions.can_edit;
    render();
    changed();
    status(favourite ? `${favourite.name} loaded.` : '');
  });
  $('cr-name').addEventListener('input', changed);
  $('cr-title').addEventListener('input', changed);
  $('cr-subtitle').addEventListener('input', changed);

  $('cr-save').addEventListener('click', async () => {
    const name = $('cr-name').value.trim();
    if (!name) { status('Enter a name for the favourite.', 'error'); $('cr-name').focus(); return; }
    // A name that a favourite already has overwrites it once the user confirms; another name saves a new favourite.
    const existing = favourites.find((item) => item.name.toLocaleLowerCase() === name.toLocaleLowerCase());
    if (existing) {
      const escape = (value) => String(value).replace(/[&<>"']/g, (character) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[character]));
      const confirmed = typeof window.showConfirmDialog === 'function'
        ? Boolean(await window.showConfirmDialog('', {title: 'Overwrite Favourite',
          copyHtml: `<p>A favourite Complete Report named <strong>${escape(existing.name)}</strong> already exists. Overwrite it with this report?</p>`,
          confirmLabel: 'Overwrite', cancelLabel: 'Cancel'}))
        : window.confirm(`A favourite Complete Report named ${existing.name} already exists. Overwrite it with this report?`);
      if (!confirmed) return;
    }
    try {
      const result = await api(existing ? `/api/reporting/complete-report/favourites/${existing.id}` : '/api/reporting/complete-report/favourites', {
        method: existing ? 'PUT' : 'POST', body: JSON.stringify({name, definition: collect()}),
      });
      favourites = result.favourites;
      renderFavourites(result.favourite.id);
      changed();
      status(`${result.favourite.name} saved as a favourite.`, 'done');
    } catch (error) {
      status(error.message, 'error');
    }
  });

  $('cr-delete').addEventListener('click', async () => {
    const selected = favourites.find((item) => String(item.id) === $('cr-favourite').value);
    if (!selected) return;
    const escape = (value) => String(value).replace(/[&<>"']/g, (character) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[character]));
    const confirmed = typeof window.showConfirmDialog === 'function'
      ? Boolean(await window.showConfirmDialog('', {title: 'Delete Favourite', copyHtml: `<p>Delete the favourite Complete Report <strong>${escape(selected.name)}</strong>?</p>`,
        confirmLabel: 'Delete', cancelLabel: 'Cancel'}))
      : window.confirm(`Delete the favourite Complete Report ${selected.name}?`);
    if (!confirmed) return;
    try {
      const result = await api(`/api/reporting/complete-report/favourites/${selected.id}`, {method: 'DELETE'});
      favourites = result.favourites;
      renderFavourites('');
      $('cr-name').value = '';
      changed();
      status(`${selected.name} deleted.`, 'done');
    } catch (error) {
      status(error.message, 'error');
    }
  });

  // -- export dialog --------------------------------------------------------------------------------
  const dialog = $('cr-dialog');
  const formatLabel = (format) => (format === 'word' ? 'Word' : 'PowerPoint');
  // The format shown in the preview (remembered in this browser): both are generated before the preview opens, so
  // switching between them is immediate.
  const FORMAT_KEY = 'drivetest.completeReport.previewFormat';
  let previewFormat = 'powerpoint';
  try { if (localStorage.getItem(FORMAT_KEY) === 'word') previewFormat = 'word'; } catch {}
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
    const failed = job.status === 'failed';
    const pending = isPending(job);
    $('cr-dialog-title').textContent = job.title || 'Complete Report';
    $('cr-dialog-format').textContent = ready ? formatLabel(previewFormat) : 'PowerPoint and Word';
    $('cr-dialog-progress').hidden = ready;
    const bar = $('cr-progress-bar');
    bar.style.width = `${Math.max(3, job.progress || 0)}%`;
    bar.parentElement.setAttribute('aria-valuenow', String(job.progress || 0));
    $('cr-dialog-message').textContent = failed ? job.error || job.message : job.message || '';
    $('cr-dialog-message').dataset.tone = failed ? 'error' : '';
    // While it runs the report can be cancelled or hidden; finished, the dialog closes.
    $('cr-dialog-cancel').hidden = !pending;
    $('cr-dialog-hide').hidden = !pending;
    $('cr-dialog-done').hidden = pending;
    $('cr-dialog-close').setAttribute('aria-label', pending ? 'Hide the progress' : 'Close the preview');
    updateElapsed();
    updateGenerateButton();
    if (wasReady) return;
    const warnings = $('cr-warnings');
    warnings.replaceChildren(...(job.warnings || []).map((warning) => node('li', warning)));
    warnings.hidden = !(job.warnings || []).length;
    $('cr-format-switch').hidden = !ready;
    // Ready, the dialog takes almost the whole screen: the sections and pages on the left, the chosen page on the right.
    dialog.classList.toggle('is-previewing', ready);
    if (ready) showFormat(0);
    else $('cr-download').hidden = true;
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
    $('cr-dialog-summary').hidden = false;
    $('cr-dialog-summary').textContent = `${count} ${unit}${count === 1 ? '' : 's'} · Processed in ${duration(job.elapsed_seconds)} · Choose a section or ${unit} on the left to check it before downloading.${reused}${pages ? '' : ' The preview needs LibreOffice: the list shows the title of each slide.'}`;
    $('cr-dialog-format').textContent = formatLabel(previewFormat);
    const download = $('cr-download');
    download.hidden = false;
    download.href = `/api/reporting/complete-report/jobs/${job.id}/download/${previewFormat}`;
    download.textContent = `Download ${formatLabel(previewFormat)}`;
    $('cr-format-switch').querySelectorAll('[data-cr-format]').forEach((button) => {
      const current = button.dataset.crFormat === previewFormat;
      button.classList.toggle('is-current', current);
      button.setAttribute('aria-pressed', String(current));
    });
    // Word shows portrait pages; PowerPoint landscape slides.
    dialog.classList.toggle('is-word', previewFormat === 'word');
    $('cr-preview').hidden = false;
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
    try { localStorage.setItem(FORMAT_KEY, format); } catch {}
    const target = group && (shownFormat(currentJob).navigation || []).find((item) => item.title === group.title);
    showFormat(target?.pages[0]?.index || 0);
  }

  // The sections of the report with their pages (or slides): selecting one shows it.
  function renderNavigation(job) {
    const nav = $('cr-preview-nav');
    const shown = shownFormat(job);
    const groups = (shown.navigation || []).length ? shown.navigation
      : [{title: 'Pages', pages: Array.from({length: shown.previews || job.outline.length}, (_value, index) => ({index, title: job.outline[index]?.title || `Page ${index + 1}`}))}];
    nav.replaceChildren(...groups.map((group) => {
      const section = node('section', undefined, 'cr-nav-section');
      const heading = node('button', group.title, 'cr-nav-heading');
      heading.type = 'button';
      heading.title = `Go to ${group.title}`;
      heading.addEventListener('click', () => { if (group.pages.length) showPage(group.pages[0].index); });
      const list = node('ol', undefined, 'cr-nav-pages');
      group.pages.forEach((page) => {
        const item = node('li');
        const button = node('button', undefined, 'cr-nav-page');
        button.type = 'button';
        button.dataset.page = String(page.index);
        button.append(node('span', String(page.index + 1), 'cr-nav-number'), node('span', page.title, 'cr-nav-title'));
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
  const stage = $('cr-viewer-stage');
  const viewerImage = $('cr-viewer-image');
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
  const pageUrl = (index, large = true) => `/api/reporting/complete-report/jobs/${currentJob.id}/preview/${previewFormat}/${index}${large ? '?large=true' : ''}`;
  function showPage(index) {
    const total = shownFormat(currentJob || {}).previews || 0;
    if (!total) return;
    viewerIndex = Math.max(0, Math.min(total - 1, index));
    const unit = previewFormat === 'word' ? 'Page' : 'Slide';
    $('cr-page-label').textContent = `${unit} ${viewerIndex + 1} / ${total}`;
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
    document.querySelectorAll('.cr-nav-page').forEach((button) => {
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
    const rectangle = pan ? null : node('div', undefined, 'cr-viewer-rect');
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
  dialog.querySelectorAll('[data-cr-viewer]').forEach((button) => button.addEventListener('click', () => {
    const action = button.dataset.crViewer;
    if (action === 'previous') showPage(viewerIndex - 1);
    else if (action === 'next') showPage(viewerIndex + 1);
    else if (action === 'zoom-in') zoomView(1.4);
    else if (action === 'zoom-out') zoomView(1 / 1.4);
    else fitView();
  }));
  window.addEventListener('resize', () => { if (dialog.open && dialog.classList.contains('is-previewing')) fitView(); });

  // The report keeps being generated when its dialog is hidden: a dialog tells when it is ready, here or (see app.js)
  // on any other page, where the job is remembered in this browser.
  const JOB_KEY = 'drivetest.completeReport.job';
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
    $('cr-dialog-elapsed').textContent = !job ? '' : isPending(job) ? `Processing time: ${clock(elapsedNow(job))}`
      : job.status === 'failed' || job.status === 'cancelled' ? `Processing time: ${duration(job.elapsed_seconds)}` : '';
    if (isPending(job) && !elapsedTimer) elapsedTimer = window.setInterval(() => { updateElapsed(); updateGenerateButton(); }, 1000);
    if (!isPending(job) && elapsedTimer) { window.clearInterval(elapsedTimer); elapsedTimer = null; }
  }
  // While a report is generated in the background, Generate shows its progress and opens its dialog.
  function updateGenerateButton() {
    const button = root.querySelector('[data-cr-export]');
    const label = button?.querySelector('span');
    if (!label) return;
    const pending = isPending(currentJob) && Boolean(currentJob.id);
    label.textContent = pending ? `Generating · ${currentJob.progress || 0}% · ${clock(elapsedNow(currentJob))}` : 'Generate';
    button.classList.toggle('is-generating', pending);
    $('cr-open-last').hidden = pending || currentJob?.status !== 'ready' || dialog.open;
  }
  function openPreview() {
    if (!dialog.open) dialog.showModal();
    const job = currentJob;
    currentJob = null;
    $('cr-preview').hidden = true;
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
        ? Boolean(await window.showConfirmDialog('', {title: 'Complete Report Ready', copyHtml: `<p><strong>${escape(job.title)}</strong> is ready in PowerPoint and Word (processed in ${duration(job.elapsed_seconds)}).</p><p>Open its preview to check it and download it?</p>`,
          confirmLabel: 'Open preview', cancelLabel: 'Later'}))
        : window.confirm(`${job.title} is ready. Open its preview?`);
      forgetJob();
      if (open) openPreview();
      else updateGenerateButton();
    } else if (job.status === 'failed') {
      forgetJob();
      if (typeof window.showInfoDialog === 'function') window.showInfoDialog(job.error || job.message, {title: 'Complete Report Failed', tone: 'error'});
      else status(job.error || job.message, 'error');
    } else {
      forgetJob();
    }
  }

  async function poll(jobId) {
    try {
      const result = await api(`/api/reporting/complete-report/jobs/${jobId}`);
      if (currentJob && currentJob.id && currentJob.id !== jobId) return;
      const before = currentJob?.status;
      if (!dialog.open && result.job.status === 'ready') currentJob = result.job;
      else showJob(result.job);
      if (isPending(result.job)) pollTimer = window.setTimeout(() => poll(jobId), 1500);
      else if (before !== result.job.status || !dialog.open) { currentJob = result.job; updateElapsed(); await finished(result.job); }
    } catch (error) {
      if (/no longer available/i.test(error.message)) { forgetJob(); currentJob = null; updateGenerateButton(); return; }
      $('cr-dialog-message').textContent = error.message;
      pollTimer = window.setTimeout(() => poll(jobId), 5000);
    }
  }

  // The report is generated in PowerPoint and in Word, with both previews, before the preview opens.
  async function exportReport() {
    if (isPending(currentJob) && currentJob.id) { openPreview(); return; }
    stopPolling();
    $('cr-preview').hidden = true;
    $('cr-preview-nav').replaceChildren();
    viewerImage.removeAttribute('src');
    stage.classList.remove('is-empty', 'is-loading');
    showJob({id: '', status: 'queued', progress: 0, message: 'Starting…', title: $('cr-title').value.trim() || $('cr-name').value.trim() || 'Complete Report',
      warnings: [], formats: {}, outline: []});
    if (!dialog.open) dialog.showModal();
    try {
      const result = await api('/api/reporting/complete-report/jobs', {method: 'POST', body: JSON.stringify({
        definition: collect(), name: $('cr-name').value.trim(), refresh: !$('cr-reuse').checked,
      })});
      showJob(result.job);
      rememberJob(result.job);
      pollTimer = window.setTimeout(() => poll(result.job.id), 1000);
    } catch (error) {
      showJob({id: '', status: 'failed', progress: 0, message: error.message, error: error.message, title: 'Complete Report',
        warnings: [], formats: {}, outline: []});
    }
  }

  root.querySelectorAll('[data-cr-export]').forEach((button) => button.addEventListener('click', () => {
    if (!definition) { status('The Complete Report is still loading.', 'error'); return; }
    void exportReport();
  }));
  $('cr-format-switch').querySelectorAll('[data-cr-format]').forEach((button) => button.addEventListener('click', () => switchFormat(button.dataset.crFormat)));
  // Hide keeps the report being generated; Cancel stops it; once it has finished, the dialog closes.
  const hideDialog = () => { dialog.close(); updateGenerateButton(); };
  async function cancelJob() {
    const job = currentJob;
    stopPolling();
    forgetJob();
    if (job?.id) {
      try { showJob((await api(`/api/reporting/complete-report/jobs/${job.id}/cancel`, {method: 'POST'})).job); } catch {}
    }
    currentJob = null;
    dialog.close();
    updateGenerateButton();
    status('The Complete Report was cancelled.');
  }
  $('cr-dialog-close').addEventListener('click', () => (isPending(currentJob) ? hideDialog() : dialog.close()));
  $('cr-dialog-hide').addEventListener('click', hideDialog);
  $('cr-dialog-cancel').addEventListener('click', () => { void cancelJob(); });
  $('cr-dialog-done').addEventListener('click', () => dialog.close());
  $('cr-open-last').addEventListener('click', () => { if (currentJob?.status === 'ready') openPreview(); });
  // Escape hides a report being generated, as Hide does.
  dialog.addEventListener('cancel', (event) => { if (isPending(currentJob)) { event.preventDefault(); hideDialog(); } });
  dialog.addEventListener('close', updateGenerateButton);

  // A report generated before this page opened (in the background, or from another page): its dialog follows it.
  async function resumeJob() {
    const asked = new URLSearchParams(window.location.search).get('complete_report_job');
    if (asked) {
      // Opened once: reloading the page does not open it again.
      const url = new URL(window.location.href);
      url.searchParams.delete('complete_report_job');
      window.history.replaceState(window.history.state, '', url);
    }
    let stored = null;
    try { stored = JSON.parse(localStorage.getItem(JOB_KEY) || 'null'); } catch {}
    const jobId = asked || stored?.id;
    if (!jobId) return;
    try {
      const {job} = await api(`/api/reporting/complete-report/jobs/${jobId}`);
      currentJob = job;
      jobSeenAt = Date.now();
      if (asked && job.status === 'ready') { openPreview(); return; }
      // Told on another page and left for later: Open last report opens it.
      if (stored?.notified && !asked) { forgetJob(); updateGenerateButton(); return; }
      if (isPending(job)) { updateElapsed(); updateGenerateButton(); pollTimer = window.setTimeout(() => poll(job.id), 1500); return; }
      await finished(job);
    } catch {
      forgetJob();
    }
  }

  // -- start -------------------------------------------------------------------------------------------
  async function load() {
    try {
      [options, crOptions] = await Promise.all([api('/api/reporting/options'), api('/api/reporting/complete-report/options')]);
    } catch (error) {
      status(error.message, 'error');
      $('cr-filters').replaceChildren(node('p', error.message, 'form-note'));
      return;
    }
    favourites = crOptions.favourites || [];
    let draft = null;
    try { draft = JSON.parse(localStorage.getItem(DRAFT_KEY) || 'null'); } catch {}
    definition = clone(draft?.definition && draft.definition.sections ? mergeDefaults(draft.definition) : crOptions.defaults);
    renderFavourites(draft?.favourite || '');
    $('cr-name').value = draft?.name || '';
    render();
    if (options.catalogues_pending) status('The filter values of some CDRs are being prepared in the background; reload the page in a few minutes to see all of them.', 'info');
    void resumeJob();
  }

  // A draft saved by an earlier version gets the sections and options it lacks; the Campaigns it had as a common filter
  // go to every section.
  function mergeDefaults(saved) {
    const defaults = clone(crOptions.defaults);
    const legacy = saved.filters?.campaigns !== undefined ? {campaigns: saved.filters.campaigns} : {};
    const sections = (saved.sections || []).filter((section) => defaults.sections.some((item) => item.key === section.key));
    defaults.sections.forEach((section) => {
      const found = sections.find((item) => item.key === section.key);
      if (!found) sections.push({...section, options: {...section.options, ...legacy}});
      else found.options = {...section.options, ...legacy, ...(found.options || {})};
    });
    return {...defaults, ...saved, filters: {...defaults.filters, ...(saved.filters || {})}, sections};
  }

  void load();
})();
