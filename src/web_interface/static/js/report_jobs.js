/* Reporting: scheduled Reporting Jobs, their editor and run history. */
(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const node = (tag, text, className) => {
    const element = document.createElement(tag);
    if (text !== undefined && text !== null) element.textContent = text;
    if (className) element.className = className;
    return element;
  };
  const FORMAT_LABELS = {powerpoint: 'PowerPoint', word: 'Word', excel: 'Excel'};
  const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
  const NETWORK_FILTERS = [['operators', 'Operator'], ['operator_vendors', 'Operator_Vendor'], ['vendor_operators', 'Vendor_Operator'], ['vendors', 'Vendor'],
    ['regions', 'Region'], ['clusters', 'Cluster'], ['cities', 'City'], ['campaigns', 'Campaign']];
  const STATUS_LABELS = {queued: 'Queued', running: 'Running', sent: 'Sent', completed: 'Completed', partial: 'Partial', failed: 'Failed'};

  let state = {tasks: [], runs: [], can_edit: false};
  let options = null;
  let editingId = null;
  // When the edited job was last saved on the server, so a draft of an older version is not restored.
  let editingUpdatedAt = '';
  let pollTimer = null;

  const status = (message, tone = '') => {
    const element = $('rj-status');
    element.textContent = message || '';
    element.dataset.tone = tone;
  };
  const api = async (url, init = {}) => {
    const response = await fetch(url, {credentials: 'same-origin', ...init,
      headers: init.body ? {'Content-Type': 'application/json', ...(init.headers || {})} : init.headers});
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'The request failed.');
    return payload;
  };
  const cellWith = (...children) => { const cell = node('td'); cell.append(...children); return cell; };
  const emptyRow = (body, text, columns) => {
    const cell = node('td', text, 'form-note'); cell.colSpan = columns;
    const row = node('tr'); row.append(cell); body.replaceChildren(row);
  };
  const localTime = (value) => {
    if (!value) return '—';
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString(undefined, {dateStyle: 'medium', timeStyle: 'short'});
  };

  // -- reusable pickers ---------------------------------------------------
  // A filterable multi-select dropdown; getValue() returns the checked values.
  // Only one dropdown is open at a time; a click outside or Escape closes it.
  // ``preset`` adds a first "Main Cities" choice: with ``dynamic`` it is a
  // flag read at run time (getPreset()), otherwise it checks those values.
  // Campaigns as the workspace Campaign Maps show and order them (campaign_labels.js); filters keep the full value.
  const campaignLabel = (value) => (globalThis.campaignLabel ? globalThis.campaignLabel(value) : String(value ?? ''));
  const campaignCompare = (left, right) => (globalThis.campaignCompare ? globalThis.campaignCompare(left, right) : 0);

  // ``exclusive`` lists [value, label] choices shown first that stand alone (Latest campaign, Latest 2 campaigns):
  // checking one clears the others and every value, checking a value clears them.
  function multiPicker(label, values, selected = [], {preset = null, onChange = null, exclusive = []} = {}) {
    const wrapper = node('details', undefined, 'workspace-user-picker rj-multi');
    const summary = node('summary');
    const caption = node('span', '', 'rj-multi-caption');
    summary.append(caption, node('span', '', 'workspace-user-picker-chevron'));
    const menu = node('div', undefined, 'workspace-user-picker-menu rj-multi-menu');
    const search = node('input', undefined, 'workspace-user-picker-search');
    search.type = 'search'; search.placeholder = 'Filter…'; search.setAttribute('aria-label', `Filter ${label}`);
    menu.append(search);
    let presetBox = null;
    if (preset) {
      const row = node('label', undefined, 'rj-multi-option rj-multi-preset');
      presetBox = node('input'); presetBox.type = 'checkbox'; presetBox.checked = Boolean(preset.checked);
      row.append(presetBox, node('span', preset.label));
      row.title = preset.values.length ? preset.values.join(', ') : 'No Main Cities are set in Workspace Config.';
      menu.append(row);
    }
    const exclusiveBoxes = exclusive.map(([value, text], index) => {
      const row = node('label', undefined, 'rj-multi-option rj-multi-exclusive');
      const box = node('input'); box.type = 'checkbox'; box.value = String(value); box.checked = selected.map(String).includes(String(value));
      row.append(box, node('span', text));
      if (index === exclusive.length - 1) row.classList.add('rj-multi-exclusive-last');
      menu.append(row);
      return box;
    });
    const exclusiveChosen = exclusiveBoxes.some((box) => box.checked);
    // An empty saved selection means every value: they all start checked.
    const chosen = new Set(exclusiveChosen ? [] : (selected.length ? selected : values).map(String));
    const boxes = values.map((value) => {
      const row = node('label', undefined, 'rj-multi-option');
      const box = node('input'); box.type = 'checkbox'; box.value = String(value); box.checked = chosen.has(String(value));
      row.append(box, node('span', ['Campaign', 'Campaigns'].includes(label) ? campaignLabel(value) : String(value)));
      menu.append(row);
      return box;
    });
    if (!values.length) menu.append(node('p', 'No values available.', 'table-help'));
    // Select All / None acts on the listed (filtered) values.
    if (values.length) {
      const toggleAll = node('button', 'Select All / None', 'workspace-user-picker-toggle rj-multi-toggle');
      toggleAll.type = 'button';
      toggleAll.addEventListener('click', () => {
        const listed = boxes.filter((box) => !box.disabled && !box.parentElement.hidden);
        const select = listed.some((box) => !box.checked);
        listed.forEach((box) => { box.checked = select; });
        exclusiveBoxes.forEach((box) => { box.checked = false; });
        if (presetBox && !preset.dynamic) presetBox.checked = false;
        refresh();
        onChange?.();
      });
      search.after(toggleAll);
    }
    const refresh = () => {
      if (presetBox && preset.dynamic) boxes.forEach((box) => { box.disabled = presetBox.checked; });
      const count = boxes.filter((box) => box.checked && !box.disabled).length;
      const enabled = boxes.filter((box) => !box.disabled).length;
      // All: every value selected, or none (no restriction either way).
      const state = count === 0 || count === enabled ? 'All' : `${count} of ${enabled}`;
      const exclusiveChoice = exclusiveBoxes.find((box) => box.checked);
      caption.textContent = exclusiveChoice ? exclusiveChoice.nextElementSibling.textContent
        : presetBox?.checked && preset.dynamic ? preset.label : state;
      summary.title = `${label}: ${caption.textContent}`;
    };
    presetBox?.addEventListener('change', () => {
      if (!preset.dynamic) {
        const wanted = new Set(preset.values.map((value) => String(value).toLocaleLowerCase()));
        boxes.forEach((box) => { box.checked = presetBox.checked && wanted.has(box.value.toLocaleLowerCase()); });
      }
      refresh();
    });
    menu.addEventListener('change', (event) => {
      if (exclusiveBoxes.includes(event.target) && event.target.checked) {
        // A choice that stands alone clears the other ones and every value.
        exclusiveBoxes.forEach((box) => { box.checked = box === event.target; });
        boxes.forEach((box) => { box.checked = false; });
      } else if (boxes.includes(event.target) && event.target.checked) {
        exclusiveBoxes.forEach((box) => { box.checked = false; });
      }
      refresh();
      onChange?.();
    });
    search.addEventListener('input', () => {
      const query = search.value.trim().toLocaleLowerCase();
      boxes.forEach((box) => { box.parentElement.hidden = Boolean(query) && !box.value.toLocaleLowerCase().includes(query); });
    });
    wrapper.addEventListener('toggle', () => {
      if (!wrapper.open) return;
      document.querySelectorAll('details.rj-multi[open]').forEach((other) => { if (other !== wrapper) other.open = false; });
      search.focus();
    });
    wrapper.append(summary, menu);
    refresh();
    // The filter name sits above its selector, which shows only the selection.
    const field = node('div', undefined, 'rj-multi-field');
    field.append(node('span', label, 'rj-multi-label'), wrapper);
    // All (or nothing selected) is saved as no restriction, so future values are included too.
    field.getValue = () => {
      const exclusiveChoice = exclusiveBoxes.find((box) => box.checked);
      if (exclusiveChoice) return [exclusiveChoice.value];
      const checked = boxes.filter((box) => box.checked && !box.disabled).map((box) => box.value);
      return checked.length === boxes.filter((box) => !box.disabled).length ? [] : checked;
    };
    field.getPreset = () => Boolean(presetBox?.checked);
    field.checkedValues = () => boxes.filter((box) => box.checked && !box.disabled).map((box) => box.value);
    field.listedValues = () => boxes.map((box) => box.value);
    field.setCheckedValues = (checked) => {
      const wanted = new Set(checked.map(String));
      boxes.forEach((box) => { box.checked = wanted.has(box.value); });
      refresh();
    };
    return field;
  }
  document.addEventListener('click', (event) => {
    document.querySelectorAll('details.rj-multi[open]').forEach((picker) => { if (!picker.contains(event.target)) picker.open = false; });
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') document.querySelectorAll('details.rj-multi[open]').forEach((picker) => { picker.open = false; });
  });
  // A row of checkboxes where only one can be checked, such as the CDR Analysis aggregation.
  function singleChoiceRow(label, choices, value) {
    const row = node('div', undefined, 'rj-inline rj-single-choice');
    row.append(node('span', `${label}:`, 'rj-inline-label'));
    const boxes = Object.entries(choices).map(([key, text]) => {
      const option = node('label', undefined, 'rj-check');
      const box = node('input'); box.type = 'checkbox'; box.value = key; box.checked = key === value;
      box.addEventListener('change', () => {
        if (!box.checked) { box.checked = true; return; }
        boxes.forEach((other) => { if (other !== box) other.checked = false; });
      });
      option.append(box, node('span', text));
      row.append(option);
      return box;
    });
    if (!boxes.some((box) => box.checked) && boxes.length) boxes[0].checked = true;
    row.getValue = () => boxes.find((box) => box.checked)?.value || '';
    return row;
  }

  // Filter values of a set of CDRs: the union of their catalogues, vendors in the order of the Vendor filters.
  const vendorRank = (value) => {
    const text = String(value ?? '');
    if (/\s-\sAll(?: Vendors)?$/i.test(text)) return 2;
    const key = text.toLowerCase().replace(/[^a-z0-9]/g, '');
    return ['mixed', 'othervendor', 'allvendor'].some((part) => key.includes(part)) ? 1 : 0;
  };
  const valuesForDatasets = (ids) => {
    const union = {};
    ids.forEach((id) => Object.entries((options.values_by_dataset || {})[id] || {}).forEach(([field, values]) => {
      values.forEach((value) => (union[field] ||= new Set()).add(value));
    }));
    // Operators and Vendors keep the order of the Operator and Vendor Maps, as the server lists them.
    const MAPPED_FIELDS = ['Operator', 'Vendor', 'Operator_Vendor', 'Vendor_Operator'];
    const mapOrder = (field, value) => {
      const index = (options.values?.[field] || []).indexOf(value);
      return index < 0 ? Number.MAX_SAFE_INTEGER : index;
    };
    return Object.fromEntries(Object.entries(union).map(([field, values]) => [field, [...values].sort((left, right) => (
      (MAPPED_FIELDS.includes(field) ? mapOrder(field, left) - mapOrder(field, right) : 0)
      || (['Vendor', 'Operator_Vendor', 'Vendor_Operator'].includes(field) ? vendorRank(left) - vendorRank(right) : 0)
      || (field === 'Campaign' ? campaignCompare(left, right) : 0)
      || String(left).localeCompare(String(right), undefined, {sensitivity: 'base'})))]));
  };
  // A row of filter pickers whose values follow the CDRs of the entry; refresh() keeps what is already chosen.
  function scopedFilters(definitions, saved = {}, presetFor = () => null, className = 'rj-filters') {
    const container = node('div', undefined, className);
    let pickers = [];
    container.refresh = (datasetIds) => {
      const current = pickers.length ? Object.fromEntries(pickers.map(([key, picker]) => [key, picker.getValue()])) : saved;
      const presets = Object.fromEntries(pickers.map(([key, picker]) => [key, picker.getPreset()]));
      const values = valuesForDatasets(datasetIds);
      pickers = definitions.map(([key, text]) => {
        const preset = presetFor(key, pickers.length ? presets[key] : undefined);
        // Operator_Vendor and Vendor_Operator hold the same values the other way round: they stay in sync.
        const partnerKey = {operator_vendors: 'vendor_operators', vendor_operators: 'operator_vendors'}[key];
        const onChange = partnerKey ? () => {
          const partner = container.picker(partnerKey);
          if (partner) partner.setCheckedValues(operatorVendorPairs.mirrorValues(picker.checkedValues(), partner.listedValues()));
        } : null;
        const picker = multiPicker(text, values[text] || [], current[key] || [], {...(preset ? {preset} : {}), onChange});
        picker.dataset.rjFilter = key;
        return [key, picker];
      });
      container.replaceChildren(...pickers.map(([, picker]) => picker));
    };
    container.values = () => Object.fromEntries(pickers.map(([key, picker]) => [key, picker.getValue()]));
    container.picker = (key) => pickers.find(([name]) => name === key)?.[1];
    return container;
  }

  const mainCitiesPreset = (checked = false, dynamic = false) => ({
    label: dynamic ? 'Main Cities (workspace list at each run)' : 'Main Cities', values: options.main_cities || [], checked, dynamic,
  });

  // The campaigns of an entry choose its CDRs: those of its NR Mode that the combined CDR tables include (the Final
  // CDR of each campaign, else its newest Weekly or Daily CDRs, or the In Combined? choice of Workspace). One list
  // offers first Latest campaign, Previous campaign and Latest 2 campaigns, which follow the newest campaigns at each run and stand
  // alone, then the campaigns (every campaign when all or none are checked). `compact` lists each campaign once, as
  // the Campaign Maps show it, and `complete` leaves out the campaigns without Data, Voice and Speech CDRs (Scoring).
  // The CDRs used now are listed.
  function campaignPicker(nrModeOf, saved = [], {compact = false, complete = false, onChange = null} = {}) {
    const wrapper = node('div', undefined, 'rj-campaign-picker');
    const presets = Object.entries(options.campaign_presets || {});
    const isPreset = (value) => presets.some(([key]) => key === value);
    const pickerHost = node('div', undefined, 'rj-campaign-values');
    // The CDRs used now, by type, as the modules list them.
    const preview = node('div', undefined, 'rj-auto-cdrs');
    const previewCaption = node('p', 'CDRs used now (chosen again at each run)', 'form-note rj-auto-cdrs-caption');
    const previewList = node('div', undefined, 'rj-auto-cdrs-list');
    const previewLeft = node('p', '', 'form-note rj-auto-cdrs-left');
    previewLeft.hidden = true;
    preview.append(previewCaption, previewList, previewLeft);
    let picker = null;
    let chosen = [...(saved || [])];
    let previewRequest = 0;
    const listed = () => {
      const raw = options.campaigns?.[nrModeOf()] || [];
      return [...new Set(compact ? raw.map((value) => campaignLabel(value)) : raw)].sort(campaignCompare);
    };
    const value = () => (picker ? picker.getValue() : chosen);
    const refreshPreview = async () => {
      const request = ++previewRequest;
      globalThis.renderAutoCdrList?.(previewList, null, {loading: true});
      try {
        const result = await api('/api/reporting/auto-cdrs', {method: 'POST', body: JSON.stringify({nr_mode: nrModeOf(), campaigns: value(), complete})});
        if (request !== previewRequest) return;
        previewCaption.textContent = 'CDRs used now (chosen again at each run)';
        globalThis.renderAutoCdrList?.(previewList, result.cdr_rows || result.cdrs || {});
        previewLeft.textContent = result.incomplete_campaigns?.length ? `Left out without every CDR type: ${result.incomplete_campaigns.join(', ')}` : '';
        previewLeft.hidden = !previewLeft.textContent;
      } catch (error) {
        if (request === previewRequest) previewCaption.textContent = `CDRs used now: ${error.message}`;
      }
    };
    const render = () => {
      if (picker) chosen = picker.getValue();
      picker = multiPicker('Campaigns', listed(), chosen, {exclusive: presets, onChange: () => { void refreshPreview(); onChange?.(); }});
      pickerHost.replaceChildren(picker);
    };
    wrapper.append(pickerHost, preview);
    // The selector goes beside NR Mode and the CDRs it chooses below that row.
    pickerHost.classList.add('rj-campaign-field');
    wrapper.field = pickerHost;
    wrapper.preview = preview;
    wrapper.getValue = value;
    // Another NR Mode lists its own campaigns (a Latest choice stays: it follows the newest campaigns of each mode).
    wrapper.refresh = () => { chosen = (picker ? picker.getValue() : chosen).filter(isPreset); picker = null; render(); void refreshPreview(); };
    render();
    void refreshPreview();
    return wrapper;
  }

  // Dataset checklist with an "every ready dataset" switch (an empty selection).
  // Artifact cards and entries collapse to keep long jobs readable; the state
  // is remembered in this browser across page reloads.
  const collapseKey = (key) => `reporting:collapsed:${key}`;
  const readCollapsed = (key) => { try { return localStorage.getItem(collapseKey(key)) === '1'; } catch { return false; } };
  const writeCollapsed = (key, collapsed) => {
    try { if (collapsed) localStorage.setItem(collapseKey(key), '1'); else localStorage.removeItem(collapseKey(key)); } catch {}
  };
  const collapseButton = (card, label, key = null) => {
    const button = node('button', 'Collapse', 'collapse-chip rj-collapse'); button.type = 'button';
    const apply = (collapsed) => {
      card.classList.toggle('is-collapsed', collapsed);
      button.textContent = collapsed ? 'Expand' : 'Collapse';
      button.setAttribute('aria-expanded', String(!collapsed));
      button.title = `${collapsed ? 'Expand' : 'Collapse'} ${label}`;
    };
    // `key` may be a function: entries only know their position once added.
    const currentKey = () => (typeof key === 'function' ? key() : key);
    button.addEventListener('click', (event) => {
      event.preventDefault(); event.stopPropagation();
      const collapsed = !card.classList.contains('is-collapsed');
      apply(collapsed);
      if (currentKey()) writeCollapsed(currentKey(), collapsed);
    });
    button.restore = () => { if (currentKey()) apply(readCollapsed(currentKey())); };
    apply(false);
    button.restore();
    return button;
  };
  const entryHead = (card, kind, describe) => {
    const head = node('div', undefined, 'rj-entry-head');
    const title = node('strong', '', 'rj-entry-title');
    const refresh = () => { title.textContent = `${kind} · ${describe() || 'New entry'}`; };
    const entryKey = () => (card.parentElement
      ? `${editingId ?? 'new'}:${kind}:${[...card.parentElement.children].indexOf(card)}` : null);
    const button = collapseButton(card, kind, entryKey);
    head.append(title, button);
    // The entry is added to its list right after it is built.
    setTimeout(() => button.restore(), 0);
    card.addEventListener('change', refresh);
    card.addEventListener('input', refresh);
    card.refreshTitle = refresh;
    setTimeout(refresh, 0);
    return head;
  };

  // Output formats as compact chips under the artifact's own checkbox; at least one stays checked.
  function formatChoices(container, prefix, selected, formats = options.formats) {
    container.replaceChildren(node('span', 'Format:', 'rj-inline-label'));
    container.classList.add('rj-formats');
    const boxes = formats.map((format) => {
      const row = node('label', undefined, 'rj-check rj-format-chip');
      const box = node('input'); box.type = 'checkbox'; box.value = format; box.checked = selected.includes(format);
      box.dataset.format = prefix;
      // A document (PowerPoint or Word) stays checked; Excel, when offered, is an optional extra.
      box.addEventListener('change', () => { if (!documents().some((item) => item.checked)) box.checked = true; });
      row.append(box, node('span', FORMAT_LABELS[format] || format));
      container.append(row);
      return box;
    });
    const documents = () => {
      const documentBoxes = boxes.filter((box) => box.value !== 'excel');
      return documentBoxes.length ? documentBoxes : boxes;
    };
    if (documents().length && !documents().some((box) => box.checked)) documents()[0].checked = true;
    container.getValue = () => boxes.filter((box) => box.checked).map((box) => box.value);
  }

  const select = (choices, value) => {
    const element = node('select');
    choices.forEach(([choice, label]) => {
      const option = node('option', label); option.value = choice; option.selected = String(choice) === String(value ?? '');
      element.append(option);
    });
    return element;
  };
  const field = (label, control, className = '') => {
    const wrapper = node('label', undefined, className);
    wrapper.append(document.createTextNode(label), control);
    return wrapper;
  };

  // -- artifact entries ---------------------------------------------------
  // A Dashboard artifact offers the Dashboard's own options: Scope, dates and every Adaptative Filter (the Campaign
  // first, which chooses the CDRs), prefilled with its saved definition.
  function dashboardEntry(entry = null) {
    const card = node('div', undefined, 'rj-entry');
    // NR Mode comes first: it decides which Dashboards and CDRs are offered.
    const modeOf = (item) => String(item?.technology || 'nsa').toUpperCase() === 'SA' ? 'SA' : 'NSA';
    const initial = options.dashboards.find((item) => item.id === entry?.dashboard_id);
    const nrMode = select([['NSA', 'NSA'], ['SA', 'SA']], initial ? modeOf(initial) : (options.dashboards.some((item) => modeOf(item) === 'NSA') ? 'NSA' : 'SA'));
    const modeDashboards = () => options.dashboards.filter((item) => modeOf(item) === nrMode.value);
    const dashboard = node('select');
    const noDashboards = node('p', '', 'form-note');
    // A new entry starts with the first Dashboard of the NR Mode not added yet.
    const fillDashboards = (selectedId = '') => {
      const added = new Set([...$('rj-dashboards').children].filter((other) => other !== card).map((other) => other.getValue?.().dashboard_id));
      const available = modeDashboards();
      const chosen = available.find((item) => item.id === selectedId) || available.find((item) => !added.has(item.id)) || available[0];
      dashboard.replaceChildren(...available.map((item) => {
        const option = node('option', item.name); option.value = item.id; option.selected = item.id === chosen?.id; return option;
      }));
      dashboard.disabled = !available.length;
      noDashboards.textContent = available.length ? '' : `There are no saved ${nrMode.value} Dashboards in this workspace.`;
    };
    fillDashboards(entry?.dashboard_id);
    const label = node('input'); label.type = 'text'; label.placeholder = 'Optional artifact name'; label.value = entry?.label || '';
    const remove = node('button', '×', 'danger-button icon-action'); remove.type = 'button'; remove.title = 'Remove this Dashboard';
    remove.addEventListener('click', () => card.remove());
    const scope = select([['single', 'Operator Comparison'], ['multivendor', 'Multivendor Comparison']], 'single');
    const comparison = select([['vendor_only', 'Vendor Only (All Operators Combined)'], ['operator_vendor', 'Operator - Vendor']], 'operator_vendor');
    const comparisonField = field('Vendor comparison', comparison);
    const dateFrom = node('input'); dateFrom.type = 'date';
    const dateTo = node('input'); dateTo.type = 'date';
    // The Campaigns choose the CDRs: they follow NR Mode in its row and the CDRs they choose are listed below it.
    const campaignSlot = node('div', undefined, 'rj-campaign-slot');
    const campaignPreviewSlot = node('div', undefined, 'rj-campaign-preview-slot');
    let campaigns = null;
    const head = node('div', undefined, 'rj-grid rj-one-row');
    head.append(field('NR Mode', nrMode), campaignSlot, field('Dashboard', dashboard), field('Name in the email', label), field('Scope', scope), comparisonField,
      field('Date from (empty: oldest)', dateFrom), field('Date to (empty: newest)', dateTo), remove);
    const filters = node('div', undefined, 'rj-filters');
    const filterNote = node('p', '', 'form-note');
    let pickers = [];
    let current = null;
    let loadTimer = null;
    let loadRequest = 0;
    const isCampaign = (name) => String(name).toLowerCase() === 'campaign';
    const chosenFilters = () => Object.fromEntries(pickers.map(([name, picker]) => [name, picker.getValue()]).filter(([, values]) => values.length));

    // The Campaign chooses the CDRs; every filter lists the values of every CDR of the NR Mode that the others leave.
    const definitionFor = () => ({
      ...current.saved, scope: scope.value, vendor_comparison: comparison.value, auto_cdrs: true,
      filters: chosenFilters(), date_from: dateFrom.value || 'Oldest', date_to: dateTo.value || 'Newest',
    });
    // City offers Main Cities first, as in the Dashboard: the Main Cities of the workspace at each run.
    const dashboardCityChoices = (chosen = []) => ((options.main_cities || []).length || (chosen || []).includes('@main-cities')
      ? [['@main-cities', 'Main Cities']] : []);
    // The Campaigns of the Dashboard (or of this entry), beside NR Mode.
    const setCampaigns = (saved) => {
      const name = current.fields.find(isCampaign);
      campaigns = name ? campaignPicker(() => nrMode.value, saved || [], {onChange: () => scheduleLoad()}) : null;
      campaignSlot.replaceChildren(...(campaigns ? [campaigns.field] : []));
      campaignPreviewSlot.replaceChildren(...(campaigns ? [campaigns.preview] : []));
    };
    const renderFilters = (values, selected) => {
      pickers = current.fields.map((name) => [name, isCampaign(name)
        ? campaigns
        : multiPicker(name, values[name] || [], selected[name] || [], name === 'City' ? {exclusive: dashboardCityChoices(selected[name])} : {})]).filter(([, picker]) => picker);
      filters.replaceChildren(...pickers.filter(([name]) => !isCampaign(name)).map(([, picker]) => picker));
    };
    // Filter values are the ones the selected CDRs offer, as in the Dashboard.
    const loadFilterValues = async () => {
      const request = ++loadRequest;
      const selected = Object.fromEntries(pickers.map(([name, picker]) => [name, picker.getValue()]));
      filterNote.textContent = 'Loading the filter values of the CDRs of this NR Mode…';
      try {
        const result = await api('/api/ppt-dashboards/filter-options/batch', {
          method: 'POST', body: JSON.stringify({definition: definitionFor(), fields: current.fields}),
        });
        if (request !== loadRequest) return;
        renderFilters(result.options || {}, selected);
        filterNote.textContent = 'Empty filters include every value. The Campaign chooses the CDRs.';
      } catch (error) {
        if (request === loadRequest) filterNote.textContent = `Filter values are unavailable: ${error.message}`;
      }
    };
    const scheduleLoad = () => { clearTimeout(loadTimer); loadTimer = setTimeout(() => { void loadFilterValues(); }, 300); };
    const apply = (config, saved) => {
      const fields = [...new Set([...options.dashboard_filter_fields, ...(saved.custom_fields || [])])];
      current = {saved, fields: [...fields.filter(isCampaign), ...fields.filter((name) => !isCampaign(name))]};
      scope.value = config.scope || saved.scope || 'single';
      comparison.value = config.vendor_comparison || saved.vendor_comparison || 'operator_vendor';
      dateFrom.value = /^\d{4}-\d{2}-\d{2}$/.test(config.date_from || '') ? config.date_from : '';
      dateTo.value = /^\d{4}-\d{2}-\d{2}$/.test(config.date_to || '') ? config.date_to : '';
      const savedFilters = config.filters || {};
      setCampaigns(savedFilters[Object.keys(savedFilters).find(isCampaign)] || []);
      renderFilters({}, savedFilters);
      comparisonField.hidden = scope.value !== 'multivendor';
      scheduleLoad();
    };
    const savedDashboard = () => options.dashboards.find((item) => item.id === dashboard.value) || {};
    dashboard.addEventListener('change', () => { const saved = savedDashboard(); apply(saved, saved); });
    nrMode.addEventListener('change', () => {
      fillDashboards();
      const saved = savedDashboard();
      if (dashboard.value) apply(saved, saved);
      else { current = {saved: {}, fields: []}; setCampaigns([]); filters.replaceChildren(); filterNote.textContent = ''; }
    });
    scope.addEventListener('change', () => { comparisonField.hidden = scope.value !== 'multivendor'; scheduleLoad(); });
    comparison.addEventListener('change', scheduleLoad);
    // Campaign first: it chooses the CDRs.
    current = {saved: {}, fields: []};
    card.append(entryHead(card, 'Dashboard', () => [nrMode.value, dashboard.selectedOptions[0]?.textContent, label.value.trim()].filter(Boolean).join(' · ')),
      head, campaignPreviewSlot, noDashboards, node('strong', 'Adaptative Filters'), filterNote, filters);
    if (dashboard.value) apply(entry || savedDashboard(), savedDashboard());
    card.getValue = () => ({
      dashboard_id: dashboard.value, label: label.value.trim(), scope: scope.value, vendor_comparison: comparison.value,
      auto_cdrs: true, date_from: dateFrom.value, date_to: dateTo.value, filters: chosenFilters(),
    });
    return card;
  }

  // A Scoring artifact offers the Scoring calculation options: NR Mode, Campaigns (which choose the CDRs),
  // filters, Main Cities, aggregation levels, methodology and GAP reference.
  // Artifact lists: the module in bold on the first level and, when it has several entries,
  // its entries indented below it. Items are texts or elements (download links).
  const ARTIFACT_MODULE_LABELS = {
    dataset_analysis: 'CDR Analysis', network_insights: 'Network Insights', dashboards: 'PPT Dashboards',
    scoring: 'Scoring & GAP Analysis', non_qualified_calls: 'Non-Qualified Calls',
  };
  function artifactEntryTitle(title, module) {
    const text = String(title || '');
    if (text.includes(' · ')) return text.slice(text.indexOf(' · ') + 3);
    return text.startsWith(module) ? text.slice(module.length).trim() || text : text;
  }
  // The formats at the end of an entry, "(PPT/Word/Excel)", each in its own colour.
  const FORMAT_CLASSES = {PPT: 'rj-format-ppt', Word: 'rj-format-word', Excel: 'rj-format-excel'};
  const FILE_FORMATS = {pptx: 'PPT', ppt: 'PPT', docx: 'Word', doc: 'Word', xlsx: 'Excel', xls: 'Excel', csv: 'CSV'};
  function withColouredFormats(text) {
    const fragment = document.createDocumentFragment();
    const match = /^(.*?)\(((?:PPT|Word|Excel)(?:\/(?:PPT|Word|Excel))*)\)\s*$/.exec(String(text || ''));
    if (!match) { fragment.append(String(text || '')); return fragment; }
    if (match[1]) fragment.append(match[1]);
    fragment.append('(');
    match[2].split('/').forEach((format, index) => {
      if (index) fragment.append('/');
      fragment.append(node('span', format, `rj-format ${FORMAT_CLASSES[format]}`));
    });
    fragment.append(')');
    return fragment;
  }
  function renderArtifactGroups(list, groups) {
    groups.forEach((group) => {
      const item = node('li');
      item.append(node('strong', group.module, 'rj-artifact-module'));
      const entries = group.items.map((entry) => (typeof entry === 'string' ? withColouredFormats(entry) : entry));
      if (entries.length > 1) {
        const nested = node('ul', undefined, 'rj-artifact-entries');
        entries.forEach((entry) => { const row = node('li'); row.append(entry); nested.append(row); });
        item.append(nested);
      } else if (entries.length) {
        const text = entries[0].textContent || '';
        item.append(document.createTextNode(text.startsWith('(') ? ' ' : ' · '), entries[0]);
        // A fragment empties when appended; the row text above was read before that.
      }
      list.append(item);
    });
  }

  let scoringFormatId = 0;
  function scoringEntry(entry = {}) {
    const card = node('div', undefined, 'rj-entry');
    const label = node('input'); label.type = 'text'; label.placeholder = 'Optional artifact name'; label.value = entry.label || '';
    const nrMode = select([['NSA', 'NSA'], ['SA', 'SA']], entry.nr_mode || 'NSA');
    // As in Scoring & GAP Analysis, each campaign can be scored with its own methodology: the default of a new entry.
    const byCampaign = options.methodologies.length ? [['by-campaign', 'By campaign (each campaign with its methodology)']] : [];
    const savedMethodology = Object.prototype.hasOwnProperty.call(entry, 'scoring_profile_id') ? entry.scoring_profile_id || '' : byCampaign.length ? 'by-campaign' : '';
    const methodology = select([...byCampaign, ['', 'Default methodology'], ...options.methodologies.map((item) => [item.id, item.name])], savedMethodology);
    const baseline = node('input'); baseline.type = 'text'; baseline.value = entry.baseline_operator || 'EE';
    const remove = node('button', '×', 'danger-button icon-action'); remove.type = 'button'; remove.title = 'Remove this Scoring artifact';
    remove.addEventListener('click', () => card.remove());
    // The campaigns choose the CDRs (each campaign with Data, Voice and Speech CDRs); the report editor lists the
    // values of every CDR of the NR Mode. They follow NR Mode in its row; the CDRs they choose are listed below.
    const campaigns = campaignPicker(() => nrMode.value, entry.campaigns || [], {complete: true});
    const head = node('div', undefined, 'rj-grid rj-one-row');
    head.append(field('NR Mode', nrMode), campaigns.field, field('Name in the email', label), field('Methodology', methodology), field('GAP reference operator', baseline), remove);
    const cdrsInUse = () => options.datasets.filter((item) => item.nr_mode === nrMode.value).map((item) => item.id);
    nrMode.addEventListener('change', () => campaigns.refresh());
    const formats = node('div', undefined, 'rj-formats');
    formatChoices(formats, `rj-scoring-${scoringFormatId += 1}`, entry.formats || ['powerpoint'], ['powerpoint', 'word']);
    // The report scenarios (filters and aggregation) and content, edited with the Scoring & GAP
    // Analysis report editor; every Scoring artifact must have one.
    let report = entry.report || null;
    const reportSummary = node('span', '', '');
    const reportRow = node('div', undefined, 'rj-inline rj-scoring-report');
    const currentDefaults = () => ({filters: {}, levels: ['Operator'], mainCities: false,
      operators: valuesForDatasets(cdrsInUse()).Operator || []});
    const describeReport = () => {
      const scenarios = report?.scenarios || [];
      reportSummary.textContent = scenarios.length
        ? `${scenarios.length} scenario${scenarios.length === 1 ? '' : 's'}: ${scenarios.map((item) => item.name).join(', ')}`
        : 'Not configured: choose the scenarios and content of the report';
      reportSummary.classList.toggle('rj-report-missing', !scenarios.length);
    };
    const configure = node('button', 'Configure report…', 'ghost-link'); configure.type = 'button';
    configure.title = 'Choose the scenarios (filters and Split by levels) and the slides of each scoring';
    configure.addEventListener('click', async () => {
      if (!window.ScoringReportEditor) return;
      const defaults = currentDefaults();
      const choice = await window.ScoringReportEditor.open({
        title: 'Scoring report of this artifact',
        configuration: report || window.ScoringReportEditor.defaultConfiguration(defaults),
        context: {filterOptions: valuesForDatasets(cdrsInUse()), operators: defaults.operators,
          mainCities: options.main_cities || [], defaults, operatorGroups: options.operator_groups || [],
          themes: options.scoring_themes || []},
        actions: [['apply', 'Apply to this artifact']],
      });
      if (choice) { report = choice.configuration; describeReport(); }
    });
    reportRow.append(node('span', 'Report content:', 'rj-inline-label'), reportSummary, configure);
    describeReport();
    card.append(entryHead(card, 'Scoring', () => [nrMode.value, label.value.trim()].filter(Boolean).join(' · ')),
      formats, head, campaigns.preview, reportRow);
    card.getValue = () => ({
      label: label.value.trim(), nr_mode: nrMode.value, auto_cdrs: true, campaigns: campaigns.getValue(), formats: formats.getValue(),
      scoring_profile_id: methodology.value, baseline_operator: baseline.value.trim() || 'EE',
      report,
    });
    return card;
  }

  // A module artifact (for example Non-Qualified Calls): formats, its single
  // choices (settings) and its multi-value filters.
  function providerCard(provider, config) {
    const card = node('section', undefined, 'rj-card');
    card.dataset.rjModule = provider.key;
    const toggle = node('label', undefined, 'rj-card-toggle');
    const box = node('input'); box.type = 'checkbox'; box.checked = Boolean(config.enabled);
    toggle.append(box, node('strong', provider.label));
    const body = node('div', undefined, 'rj-card-body rj-provider-body');
    const formats = node('div', undefined, 'rj-formats');
    formatChoices(formats, `rj-provider-${provider.key}`, config.formats || [provider.formats[0]], provider.formats);
    const excelChip = formats.querySelector('input[value="excel"]')?.closest('label');
    if (excelChip) {
      excelChip.title = `Excel exports only the ${provider.label} detail: every call with its follow-up, comments and history. `
        + 'The Executive Summary and Progress Status are in the PowerPoint or Word document, which is always generated.';
    }
    const saved = config.options || {};
    const settings = (provider.settings || []).map((setting) => {
      const control = select(setting.choices, String(saved[setting.key] ?? setting.default ?? ''));
      return [setting.key, control, field(setting.label, control)];
    });
    const settingsRow = node('div', undefined, 'rj-grid rj-one-row');
    settingsRow.append(...settings.map(([, , wrapper]) => wrapper));
    // A filter can list only the values of the choice of an earlier one: "campaign@nr_mode" maps each NR Mode to
    // its campaigns, so Campaign lists those of the NR Modes chosen (all of them when NR Mode is not restricted).
    const dependencies = Object.fromEntries(Object.keys(provider.values || {}).filter((name) => name.includes('@')).map((name) => {
      const [key, parent] = name.split('@');
      return [key, {parent, map: provider.values[name] || {}}];
    }));
    const pickerByKey = new Map();
    // Values are [value, label] pairs or plain values.
    // Campaign offers first Latest campaign, Previous campaign, Latest 2 campaigns and All available campaigns, each
    // alone, resolved at each run among the campaigns of the NR Modes chosen.
    const campaignPresets = Object.entries(options.campaign_presets || {});
    const makePicker = ({key, label}, chosen) => {
      let values = (provider.values?.[key] || []).map((item) => (Array.isArray(item) ? item : [item, item]));
      const dependency = dependencies[key];
      const presets = key === 'campaign' ? campaignPresets : [];
      if (dependency) {
        const parentChoice = pickerByKey.get(dependency.parent)?.getValue() || [];
        const allowed = new Set((parentChoice.length ? parentChoice : Object.keys(dependency.map))
          .flatMap((value) => dependency.map[value] || []).map(String));
        values = values.filter(([value]) => allowed.has(String(value)));
        chosen = chosen.filter((value) => allowed.has(String(value)) || presets.some(([preset]) => preset === value));
      }
      const dependents = Object.keys(dependencies).filter((name) => dependencies[name].parent === key);
      const picker = multiPicker(label, values.map(([value]) => value), chosen, {
        ...(key === 'city' ? {preset: mainCitiesPreset()} : {}),
        ...(presets.length ? {exclusive: presets} : {}),
        ...(dependents.length ? {onChange: () => dependents.forEach(rebuildPicker)} : {}),
      });
      // Show the labels (for example CDR names) while keeping their values.
      const labels = new Map(values.map(([value, text]) => [String(value), String(text)]));
      picker.querySelectorAll('.rj-multi-option:not(.rj-multi-preset) span').forEach((span) => {
        span.textContent = labels.get(span.textContent) ?? span.textContent;
      });
      pickerByKey.set(key, picker);
      return picker;
    };
    const rebuildPicker = (key) => {
      const filter = (provider.filters || []).find((item) => item.key === key);
      const previous = pickerByKey.get(key);
      if (!filter || !previous) return;
      previous.replaceWith(makePicker(filter, previous.getValue()));
    };
    (provider.filters || []).forEach((filter) => makePicker(filter, saved.filters?.[filter.key] || []));
    const pickers = (provider.filters || []).map(({key}) => [key, pickerByKey.get(key)]);
    const filters = node('div', undefined, 'rj-filters');
    filters.append(...pickers.map(([, picker]) => picker));
    body.append(formats, ...(settings.length ? [settingsRow] : []),
      ...(pickers.length ? [node('strong', 'Filters'), node('p', 'Empty filters include every value.', 'form-note'), filters] : []));
    const syncBody = () => { body.hidden = !box.checked; };
    box.addEventListener('change', syncBody); syncBody();
    card.append(toggle, body);
    card.getValue = () => [provider.key, {
      enabled: box.checked, formats: formats.getValue(),
      options: {
        ...Object.fromEntries(settings.map(([key, control]) => [key, control.value])),
        filters: Object.fromEntries([...pickerByKey].map(([key, picker]) => [key, picker.getValue()]).filter(([, values]) => values.length)),
      },
    }];
    return card;
  }

  // A Network Insights artifact offers the module's options: NR Mode, technology, LTE/NR thresholds, grouping,
  // Campaigns (which choose the CDRs) and filters.
  let networkFormatId = 0;
  function networkEntry(entry = {}) {
    const selection = entry.selection || {};
    const card = node('div', undefined, 'rj-entry');
    const formats = node('div', undefined, 'rj-formats');
    formatChoices(formats, `rj-ni-${networkFormatId += 1}`, entry.formats || ['powerpoint']);
    const label = node('input'); label.type = 'text'; label.placeholder = 'Optional artifact name'; label.value = entry.label || '';
    const nrMode = select([['NSA', 'NSA'], ['SA', 'SA']], selection.nr_mode || 'NSA');
    const technology = select(Object.entries(options.technologies), selection.technology || 'lte');
    const number = (value, step) => { const input = node('input'); input.type = 'number'; input.step = step; input.value = value; return input; };
    const thresholds = [
      ['lte', 'LTE coverage below (dBm)', 'coverage_threshold', number(selection.coverage_threshold ?? -110, 1)],
      ['lte', 'LTE interference below (dB)', 'interference_threshold', number(selection.interference_threshold ?? 0, 0.5)],
      ['nr', 'NR coverage below (dBm)', 'nr_coverage_threshold', number(selection.nr_coverage_threshold ?? -115, 1)],
      ['nr', 'NR interference below (dB)', 'nr_interference_threshold', number(selection.nr_interference_threshold ?? -3, 0.5)],
    ].map(([radio, text, key, input]) => ({radio, key, input, wrapper: field(text, input)}));
    // Only the thresholds of the selected technologies are shown.
    const syncThresholds = () => thresholds.forEach((item) => { item.wrapper.hidden = ![item.radio, 'lte_nr'].includes(technology.value); });
    technology.addEventListener('change', syncThresholds); syncThresholds();
    const remove = node('button', '×', 'danger-button icon-action'); remove.type = 'button'; remove.title = 'Remove this Network Insights artifact';
    remove.addEventListener('click', () => card.remove());
    // The Campaigns choose the CDRs: they follow NR Mode in its row and the CDRs they choose are listed below.
    const campaigns = campaignPicker(() => nrMode.value, selection.campaigns || [], {compact: true});
    const head = node('div', undefined, 'rj-grid rj-one-row');
    head.append(field('NR Mode', nrMode), campaigns.field, field('Technology', technology), field('Name in the email', label),
      ...thresholds.map((item) => item.wrapper), remove);
    const groups = selection.group || ['operator', 'campaign'];
    const grouping = node('div', undefined, 'rj-inline');
    grouping.append(node('span', 'Grouping:', 'rj-inline-label'), ...Object.entries(options.network_groupings).map(([value, text]) => {
      const row = node('label', undefined, 'rj-check');
      const box = node('input'); box.type = 'checkbox'; box.value = value; box.checked = groups.includes(value);
      row.append(box, node('span', text));
      return row;
    }));
    // As in Network Insights, Operator stays checked unless Vendor groups the samples instead.
    const groupBox = (value) => grouping.querySelector(`input[value="${value}"]`);
    const enforceOperator = () => {
      const operator = groupBox('operator');
      if (!operator) return;
      const required = !groupBox('vendor')?.checked;
      operator.disabled = required;
      operator.title = required ? 'Operator is required unless Vendor is selected.' : '';
      if (required) operator.checked = true;
    };
    grouping.addEventListener('change', enforceOperator);
    enforceOperator();
    // The other filters list the values of every CDR of the NR Mode.
    const filters = scopedFilters(NETWORK_FILTERS.filter(([key]) => key !== 'campaigns'), selection,
      (key) => (key === 'cities' ? mainCitiesPreset() : null), 'rj-filters rj-filters-one-row');
    const cdrsInUse = () => options.datasets.filter((item) => item.nr_mode === nrMode.value).map((item) => item.id);
    nrMode.addEventListener('change', () => { campaigns.refresh(); filters.refresh(cdrsInUse()); });
    filters.refresh(cdrsInUse());
    card.append(entryHead(card, 'Network Insights', () => [nrMode.value, technology.selectedOptions[0]?.textContent, label.value.trim()].filter(Boolean).join(' · ')),
      formats, head, campaigns.preview, grouping, node('strong', 'Filters'), filters);
    card.getValue = () => ({
      label: label.value.trim(), formats: formats.getValue(), auto_cdrs: true,
      selection: {
        nr_mode: nrMode.value, technology: technology.value,
        group: [...grouping.querySelectorAll('input:checked')].map((box) => box.value),
        ...Object.fromEntries(thresholds.map((item) => [item.key, Number(item.input.value)])),
        ...filters.values(), campaigns: campaigns.getValue(),
      },
    });
    return card;
  }

  // -- editor -------------------------------------------------------------

  // Artifacts are organised in tabs: one per artifact type, in its module colour, with a check when it is
  // included in the job. Every artifact stays in the form, so saving reads all of them.
  // The selected artifact tab is remembered by the browser, so reloading the page keeps it.
  const ARTIFACT_TAB_KEY = 'drivetest-analyzer:reporting-artifact-tab';
  let activeArtifact = (() => { try { return localStorage.getItem(ARTIFACT_TAB_KEY) || ''; } catch { return ''; } })();
  const ARTIFACT_TAB_ICONS = {
    dataset_analysis: '.module-tab-datasets-analysis', network_insights: '.module-tab-network-insights',
    dashboards: '.module-tab-ppt-dashboards', scoring: '.module-tab-scoring', non_qualified_calls: '.module-tab-non-qualified-calls',
  };
  function syncArtifactTabs() {
    const host = $('rj-artifact-tabs');
    if (!host) return;
    const cards = [...document.querySelectorAll('.rj-card[data-rj-module]')].filter((card) => !card.hidden);
    if (!cards.some((card) => card.dataset.rjModule === activeArtifact)) activeArtifact = cards[0]?.dataset.rjModule || '';
    host.replaceChildren(...cards.map((card) => {
      const toggle = card.querySelector(':scope > .rj-card-toggle input[type="checkbox"]');
      const tab = node('button', undefined, 'rj-artifact-tab');
      tab.type = 'button';
      tab.setAttribute('role', 'tab');
      tab.dataset.module = card.dataset.rjModule;
      tab.classList.toggle('is-included', Boolean(toggle?.checked));
      tab.setAttribute('aria-selected', String(card.dataset.rjModule === activeArtifact));
      tab.title = toggle?.checked ? 'Included in the job' : 'Not included in the job';
      // The icon of the module's main tab follows the inclusion check.
      const icon = document.querySelector(`.module-tabs ${ARTIFACT_TAB_ICONS[card.dataset.rjModule] || '.none'} .module-tab-icon`)?.cloneNode(true);
      // Its own class: the navigation hides its tab icons on narrow windows.
      icon?.setAttribute('class', 'rj-tab-icon');
      // The inclusion check follows the artifact name.
      tab.append(...(icon ? [icon] : []),
        node('span', card.querySelector(':scope > .rj-card-toggle strong')?.textContent || card.dataset.rjModule),
        node('span', '', 'rj-tab-state'));
      tab.addEventListener('click', () => {
        activeArtifact = card.dataset.rjModule;
        try { localStorage.setItem(ARTIFACT_TAB_KEY, activeArtifact); } catch { /* Storage unavailable: the tab is still selected. */ }
        syncArtifactTabs();
      });
      return tab;
    }));
    cards.forEach((card) => card.classList.toggle('is-tab-hidden', card.dataset.rjModule !== activeArtifact));
  }
  document.addEventListener('change', (event) => {
    if (event.target.closest?.('.rj-card[data-rj-module] > .rj-card-toggle')) syncArtifactTabs();
  });

  function fillEditor(task) {
    const definition = task?.definition || {};
    const dataset = definition.dataset_analysis || {};
    const network = definition.network_insights || [];
    editingId = task?.id ?? null;
    editingUpdatedAt = task?.updated_at || '';
    $('rj-editor-title').textContent = task?.id ? `Edit ${task.name}` : 'New Reporting Job';
    $('rj-name').value = task?.name || '';
    $('rj-da-enabled').checked = Boolean(dataset.enabled);
    formatChoices(document.querySelector('[data-rj-formats="rj-da"]'), 'rj-da', dataset.formats || ['powerpoint']);
    // CDR Analysis chooses its CDRs from its NR Mode and Campaigns, as the other artifacts, and lists them below.
    const daNrMode = select([['NSA', 'NSA'], ['SA', 'SA']], dataset.nr_mode || 'NSA');
    const daCampaigns = campaignPicker(() => daNrMode.value, dataset.campaigns || [], {compact: true});
    $('rj-da-scope').replaceChildren(field('NR Mode', daNrMode), daCampaigns.field);
    $('rj-da-scope').getValue = () => ({nr_mode: daNrMode.value, campaigns: daCampaigns.getValue()});
    $('rj-da-cdrs').replaceChildren(daCampaigns.preview);
    $('rj-da-aggregation').replaceWith(Object.assign(singleChoiceRow('Global Comparison', options.cdr_aggregations || {}, dataset.aggregation || 'all'), {id: 'rj-da-aggregation'}));
    $('rj-da-cdf').replaceWith(Object.assign(singleChoiceRow('Global CDF Comparison', options.cdr_cdf_groupings || {}, dataset.cdf_grouping || 'operator'), {id: 'rj-da-cdf'}));
    // One metric selector per CDR type; All (the default) includes every metric, also future ones.
    const savedMetrics = dataset.metrics && !Array.isArray(dataset.metrics) ? dataset.metrics : {};
    $('rj-da-metrics').replaceChildren(...Object.entries(options.cdr_kinds || {}).map(([kind, label]) => {
      const metrics = (options.cdr_metrics || {})[kind] || [];
      const picker = multiPicker(label, metrics, savedMetrics[kind] || []);
      picker.dataset.rjMetrics = kind;
      return picker;
    }));
    // The Campaigns choose the CDRs; the other filters list the values of every CDR of the NR Mode.
    const daFilters = scopedFilters(NETWORK_FILTERS.filter(([key]) => key !== 'campaigns'), dataset.filters || {},
      (key) => (key === 'cities' ? mainCitiesPreset() : null), 'rj-filters rj-filters-one-row');
    daFilters.id = 'rj-da-filters';
    $('rj-da-filters').replaceWith(daFilters);
    const daCdrsInUse = () => options.datasets.filter((item) => item.nr_mode === daNrMode.value).map((item) => item.id);
    daFilters.refresh(daCdrsInUse());
    daNrMode.addEventListener('change', () => { daCampaigns.refresh(); daFilters.refresh(daCdrsInUse()); });
    // Jobs saved with a single Network Insights selection show it as one entry.
    const networkEntries = Array.isArray(network) ? network : (network.enabled ? [network] : []);
    $('rj-network').replaceChildren(...networkEntries.map(networkEntry));
    $('rj-dashboards').replaceChildren(...(definition.dashboards || []).map(dashboardEntry));
    $('rj-scoring').replaceChildren(...(definition.scoring || []).map(scoringEntry));
    // Each artifact type is included independently.
    $('rj-ni-enabled').checked = networkEntries.length > 0;
    $('rj-dashboards-enabled').checked = (definition.dashboards || []).length > 0;
    $('rj-scoring-enabled').checked = (definition.scoring || []).length > 0;
    // Only the modules the user can use offer artifacts.
    const labels = {dataset_analysis: 'CDR Analysis', network_insights: 'Network Insights', dashboards: 'PPT Dashboards', scoring: 'Scoring & GAP Analysis'};
    const unavailable = Object.entries(options.allowed_modules).filter(([, allowed]) => !allowed).map(([module]) => module);
    document.querySelectorAll('[data-rj-module]').forEach((section) => { section.hidden = unavailable.includes(section.dataset.rjModule); });
    $('rj-modules-note').hidden = !unavailable.length;
    $('rj-modules-note').textContent = `Artifacts of modules not activated for your account are not available: ${unavailable.map((module) => labels[module]).join(', ')}.`;
    const modules = definition.modules || {};
    $('rj-providers').replaceChildren(...options.providers.map((provider) => providerCard(provider, modules[provider.key] || {})));
    syncArtifactTabs();
    $('rj-send-email').checked = Boolean(task?.send_email);
    $('rj-recipients').value = (task?.recipients || []).join(', ');
    const schedule = task?.schedule || {mode: 'manual', time: '08:00'};
    $('rj-schedule-mode').value = schedule.mode || 'manual';
    $('rj-schedule-date').value = schedule.date || '';
    $('rj-schedule-time').value = schedule.time || '08:00';
    $('rj-schedule-day').value = schedule.day_of_month || 1;
    $('rj-schedule-weekdays').replaceChildren(...WEEKDAYS.map((day, index) => {
      const row = node('label', undefined, 'rj-check');
      const box = node('input'); box.type = 'checkbox'; box.value = index; box.checked = (schedule.weekdays || [0]).includes(index);
      row.append(box, node('span', day.slice(0, 3)));
      return row;
    }));
    $('rj-enabled').checked = task ? Boolean(task.enabled) : true;
    syncEnabledLabel();
    $('rj-timezone').textContent = `Times use the application timezone ${options.timezone}. Enabled jobs run whenever the application is running, also when another workspace is open; a run that fell due while the application was stopped starts at the next check.`;
    $('rj-email-note').textContent = options.email_configured
      ? 'Without email, each run only keeps its artifacts for download.'
      : 'Email delivery is not configured yet: set the SMTP server in Config → Application Config → Email Delivery.';
    syncEditor();
    openEditor(task?.id ?? null);
    // What the job looks like when the editor opens, to detect unsaved changes.
    editorSnapshot = JSON.stringify(editorPayload());
    saveDraft();
  }

  // The open Job Editor is kept as a draft in this browser, so reloading the page reopens it as it was.
  const DRAFT_KEY = 'drivetest-analyzer:reporting-job-draft';
  const readDraft = () => { try { return JSON.parse(window.localStorage.getItem(DRAFT_KEY) || 'null'); } catch { return null; } };
  const clearDraft = () => { try { window.localStorage.removeItem(DRAFT_KEY); } catch { /* Storage unavailable. */ } };
  let draftTimer = 0;
  const saveDraft = () => {
    window.clearTimeout(draftTimer);
    draftTimer = window.setTimeout(() => {
      if (!editorOpen || !options) return;
      try {
        window.localStorage.setItem(DRAFT_KEY, JSON.stringify({
          workspace: state.workspace_id, editingId, editingUpdatedAt, snapshot: editorSnapshot, payload: editorPayload(),
        }));
      } catch { /* Storage unavailable: the editor simply does not survive a reload. */ }
    }, 300);
  };
  async function restoreDraft() {
    const draft = readDraft();
    if (!draft || !state.can_edit || draft.workspace !== state.workspace_id || !draft.payload) return;
    const task = draft.editingId !== null ? state.tasks.find((item) => item.id === draft.editingId) : null;
    if (draft.editingId !== null && !task) { clearDraft(); return; }
    // The job changed on the server since the draft (imported, transferred or saved elsewhere): open what is saved.
    if (task && draft.editingUpdatedAt !== task.updated_at) {
      clearDraft();
      status('The unsaved changes of the Job Editor were discarded because the job changed since then.', 'info');
      return;
    }
    await ensureOptions();
    const recipients = String(draft.payload.recipients || '').split(/[,;\n]/).map((item) => item.trim()).filter(Boolean);
    fillEditor({...(task || {}), ...draft.payload, recipients, id: task ? task.id : undefined, name: draft.payload.name || task?.name || ''});
    if (draft.snapshot) editorSnapshot = draft.snapshot;
    if (editorDirty()) status('The Job Editor was reopened with its unsaved changes.', 'info');
  }

  // Leaving the editor with unsaved changes asks first.
  let editorSnapshot = null;
  const editorDirty = () => editorOpen && editorSnapshot !== null && JSON.stringify(editorPayload()) !== editorSnapshot;
  async function confirmDiscard() {
    if (!editorDirty()) return true;
    const copy = '<p>This Reporting Job has unsaved changes.</p><p>Discard them and close the Job Editor?</p>';
    return typeof window.showConfirmDialog === 'function'
      ? Boolean(await window.showConfirmDialog('', {title: 'Discard Changes', copyHtml: copy, confirmLabel: 'Discard changes', cancelLabel: 'Keep editing'}))
      : window.confirm('Discard the unsaved changes of this Reporting Job?');
  }

  function syncEditor() {
    document.querySelectorAll('[data-rj-section]').forEach((section) => {
      const enabled = section.querySelector('.rj-card-toggle input').checked;
      section.querySelector('[data-rj-body]').hidden = !enabled;
    });
    document.querySelector('[data-rj-email-body]').hidden = !$('rj-send-email').checked;
    const mode = $('rj-schedule-mode').value;
    document.querySelectorAll('[data-rj-schedule]').forEach((element) => {
      element.hidden = !element.dataset.rjSchedule.split(' ').includes(mode);
    });
  }

  function editorPayload() {
    return {
      name: $('rj-name').value.trim(),
      definition: {
        dataset_analysis: {
          enabled: $('rj-da-enabled').checked && options.allowed_modules.dataset_analysis, formats: document.querySelector('[data-rj-formats="rj-da"]').getValue(),
          ...$('rj-da-scope').getValue(), auto_cdrs: true, dataset_ids: [], cdr_selection: '',
          metrics: Object.fromEntries([...$('rj-da-metrics').querySelectorAll('[data-rj-metrics]')]
            .map((picker) => [picker.dataset.rjMetrics, picker.getValue()]).filter(([, chosen]) => chosen.length)),
          filters: Object.fromEntries([...$('rj-da-filters').querySelectorAll('[data-rj-filter]')]
            .map((picker) => [picker.dataset.rjFilter, picker.getValue()]).filter(([, values]) => values.length)),
          aggregation: $('rj-da-aggregation').getValue?.() || 'all',
          cdf_grouping: $('rj-da-cdf').getValue?.() || 'operator',
        },
        network_insights: options.allowed_modules.network_insights && $('rj-ni-enabled').checked ? [...$('rj-network').children].map((card) => card.getValue()) : [],
        dashboards: $('rj-dashboards-enabled').checked ? [...$('rj-dashboards').children].map((card) => card.getValue()) : [],
        scoring: $('rj-scoring-enabled').checked ? [...$('rj-scoring').children].map((card) => card.getValue()) : [],
        modules: Object.fromEntries([...$('rj-providers').children].map((card) => card.getValue())),
      },
      send_email: $('rj-send-email').checked,
      recipients: $('rj-recipients').value,
      schedule: {
        mode: $('rj-schedule-mode').value, date: $('rj-schedule-date').value, time: $('rj-schedule-time').value || '08:00',
        day_of_month: Number($('rj-schedule-day').value || 1),
        weekdays: [...$('rj-schedule-weekdays').querySelectorAll('input:checked')].map((box) => Number(box.value)),
      },
      enabled: $('rj-enabled').checked,
    };
  }

  // The switch says whether the job runs on its schedule.
  const syncEnabledLabel = () => {
    const label = document.querySelector('[data-rj-enabled-label]');
    if (label) label.textContent = $('rj-enabled').checked ? 'Job enabled' : 'Job disabled';
  };
  document.getElementById('rj-enabled')?.addEventListener('change', syncEnabledLabel);

  // The editor unfolds inside the jobs table, right below the job being edited (above the others),
  // or at the top for a new job, and folds away on Cancel, Save or ×.
  const editorHome = document.createComment('rj-editor');
  // Kept by reference: refreshing the table detaches the editor row until placeEditor() puts it back.
  const editorElement = document.getElementById('rj-editor');
  let editorOpen = false;
  function placeEditor() {
    const editor = editorElement;
    const body = $('rj-tasks').tBodies[0];
    let row = document.getElementById('rj-editor-row');
    if (!editorOpen) {
      if (row) { editorHome.after(editor); row.remove(); }
      return;
    }
    if (!row) {
      row = node('tr'); row.id = 'rj-editor-row'; row.className = 'rj-editor-row';
      const cell = node('td', undefined, 'rj-editor-cell'); cell.colSpan = 8;
      row.append(cell);
    }
    row.cells[0].append(editor);
    const edited = editingId !== null ? body.querySelector(`tr[data-task-id="${editingId}"]`) : null;
    if (edited) edited.after(row); else body.prepend(row);
  }
  function openEditor(taskId) {
    const editor = editorElement;
    if (!editorHome.isConnected) editor.before(editorHome);
    const panel = editor.closest('details') || $('rj-tasks').closest('details');
    if (panel) panel.open = true;
    document.querySelectorAll('#rj-tasks tr.rj-editing').forEach((row) => row.classList.remove('rj-editing'));
    if (taskId !== null) document.querySelector(`#rj-tasks tr[data-task-id="${taskId}"]`)?.classList.add('rj-editing');
    editorOpen = true;
    placeEditor();
    editor.hidden = false;
    editor.classList.remove('is-closing');
    editor.classList.add('is-opening');
    editor.addEventListener('animationend', () => editor.classList.remove('is-opening'), {once: true});
    editor.scrollIntoView({behavior: 'smooth', block: 'start'});
  }
  function closeEditor() {
    const editor = editorElement;
    editingId = null;
    editorSnapshot = null;
    window.clearTimeout(draftTimer);
    clearDraft();
    document.querySelectorAll('#rj-tasks tr.rj-editing').forEach((row) => row.classList.remove('rj-editing'));
    if (editor.hidden) return;
    editor.classList.add('is-closing');
    editor.addEventListener('animationend', () => {
      editor.hidden = true; editor.classList.remove('is-closing');
      editorOpen = false;
      placeEditor();
    }, {once: true});
  }

  async function ensureOptions() {
    options = await api('/api/reporting/options');
    if (options.catalogues_pending) {
      status('The filter values of some CDRs are being prepared in the background; reopen the editor in a few minutes to see all of them.', 'info');
    }
    return options;
  }

  // -- tables -------------------------------------------------------------
  // Deletions ask with the application's confirmation dialog (the browser's one only as a fallback).
  const escapeText = (value) => String(value ?? '').replace(/[&<>"']/g, (character) => (
    {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[character]));
  const confirmDelete = async (title, copyHtml, confirmLabel, fallback) => (typeof window.showConfirmDialog === 'function'
    ? Boolean(await window.showConfirmDialog('', {title, copyHtml, confirmLabel, cancelLabel: 'Cancel'}))
    : window.confirm(fallback));
  const actionButton = (label, title, handler, className = 'icon-action') => {
    const button = node('button', label, className);
    button.type = 'button'; button.title = title; button.setAttribute('aria-label', title);
    button.addEventListener('click', async () => {
      button.disabled = true;
      try { await handler(); } catch (error) { status(error.message, 'error'); } finally { button.disabled = false; }
    });
    return button;
  };
  const statusBadge = (run) => {
    if (!run) return node('span', 'Never run', 'form-note');
    const badge = node('span', STATUS_LABELS[run.status] || run.status, `rj-status rj-status-${run.status}`);
    badge.title = run.error || run.message || '';
    return badge;
  };
  // How long a finished run took, "45s", "3m 12s" or "1h 05m".
  const runDuration = (run) => {
    const start = Date.parse(run.started_at || ''); const end = Date.parse(run.finished_at || '');
    if (Number.isNaN(start) || Number.isNaN(end) || end < start) return '';
    const seconds = Math.round((end - start) / 1000);
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, '0')}s`;
    return `${Math.floor(seconds / 3600)}h ${String(Math.floor(seconds / 60) % 60).padStart(2, '0')}m`;
  };
  const downloadLink = (run) => {
    const link = node('a', '⬇', 'icon-action rj-download');
    link.href = `/api/reporting/runs/${run.id}/download`;
    link.title = 'Download the artifacts of this run (ZIP)';
    link.setAttribute('aria-label', link.title);
    return link;
  };

  function renderTasks() {
    const body = $('rj-tasks').tBodies[0];
    if (!state.tasks.length) {
      emptyRow(body, 'No Reporting Jobs yet.', 8);
      placeEditor();
      return;
    }
    body.replaceChildren(...state.tasks.map((task) => {
      const row = node('tr');
      row.dataset.taskId = task.id;
      if (!task.enabled) row.classList.add('rj-disabled');
      if (editingId === task.id) row.classList.add('rj-editing');
      const artifacts = node('ul', undefined, 'rj-artifacts');
      if (task.artifact_groups) renderArtifactGroups(artifacts, task.artifact_groups);
      else task.artifacts.forEach((text) => artifacts.append(node('li', text)));
      const last = task.last_run;
      const lastCell = node('td', last ? localTime(last.started_at || last.created_at) : '—');
      const statusCell = node('td');
      statusCell.append(statusBadge(last));
      const actions = node('div', undefined, 'table-actions rj-task-actions');
      if (state.can_edit) {
        actions.append(actionButton('▶', 'Run now', async () => {
          await api(`/api/reporting/tasks/${task.id}/run`, {method: 'POST'});
          status(`${task.name} started.`, 'done'); await refresh();
        }));
      }
      if (last && last.artifacts.some((item) => item.status === 'ready')) actions.append(downloadLink(last));
      if (state.can_edit) {
        actions.append(
          actionButton('✎', 'Edit', async () => { if (!await confirmDiscard()) return; await ensureOptions(); fillEditor(task); }),
          actionButton('⧉', 'Duplicate (disabled copy)', async () => {
            await api(`/api/reporting/tasks/${task.id}/duplicate`, {method: 'POST'});
            status(`${task.name} duplicated.`, 'done'); await refresh();
          }),
          actionButton(task.enabled ? '⏸' : '⏵', task.enabled ? 'Disable the schedule' : 'Enable the schedule', async () => {
            await api(`/api/reporting/tasks/${task.id}/enabled`, {method: 'POST', body: JSON.stringify({enabled: !task.enabled})});
            await refresh();
          }),
          actionButton('×', 'Delete the job and its runs', async () => {
            const runs = state.runs.filter((run) => run.task_id === task.id).length;
            if (!await confirmDelete('Delete Reporting Job', `
              <p>The Reporting Job <strong>${escapeText(task.name)}</strong> will be deleted permanently, together with:</p>
              <ul>
                <li>its schedule and email delivery${task.enabled ? ' (it will stop running)' : ''};</li>
                <li>${runs ? `its <strong>${runs}</strong> run${runs === 1 ? '' : 's'} in the Run History` : 'its run history'};</li>
                <li>every artifact generated by those runs.</li>
              </ul>
              <p>This cannot be undone. To keep the job without running it, disable it instead.</p>`,
            'Delete Job', `Delete ${task.name}, its run history and artifacts?`)) return;
            await api(`/api/reporting/tasks/${task.id}`, {method: 'DELETE'});
            status(`${task.name} deleted.`, 'done'); await refresh();
          }, 'danger-button icon-action'),
        );
      }
      row.append(
        node('td', task.name), cellWith(artifacts),
        node('td', task.enabled ? localTime(task.next_run_at) : 'Disabled'), node('td', task.recurrence),
        node('td', task.send_email ? `Yes · ${task.recipients.length} recipient${task.recipients.length === 1 ? '' : 's'}` : 'No'),
        lastCell, statusCell, cellWith(actions),
      );
      row.cells[4].title = task.recipients.join(', ');
      return row;
    }));
    placeEditor();
  }

  function renderRuns() {
    const body = $('rj-runs').tBodies[0];
    if (!state.runs.length) {
      emptyRow(body, 'No runs yet.', 8);
      return;
    }
    body.replaceChildren(...state.runs.map((run) => {
      const row = node('tr');
      const statusCell = node('td');
      statusCell.append(statusBadge(run));
      const duration = runDuration(run);
      if (['queued', 'running'].includes(run.status)) statusCell.append(node('small', ` ${run.progress}% · ${run.message}`));
      else if (duration) statusCell.append(node('small', ` in ${duration}`, 'rj-duration'));
      if (!['queued', 'running'].includes(run.status) && run.error) statusCell.append(node('small', ` ${run.error}`, 'rj-error'));
      const artifacts = node('ul', undefined, 'rj-artifacts');
      // Grouped like the jobs table: one line per entry with its formats, "NSA LTE (PPT/Word)", where each
      // format is the download link of its file; failed files follow with their error.
      const byModule = new Map();
      run.artifacts.forEach((item, index) => {
        // Only the files of this run that still exist are listed (the index stays the download link).
        if (item.status === 'ready' && item.available === false) return;
        const module = ARTIFACT_MODULE_LABELS[item.module] || item.module || 'Artifacts';
        const title = artifactEntryTitle(item.title, module);
        if (!byModule.has(module)) byModule.set(module, new Map());
        const entries = byModule.get(module);
        if (item.status !== 'ready') {
          entries.set(`failed-${index}`, {failed: node('span', `${title}: ${item.error || 'failed'}`, 'rj-error')});
          return;
        }
        const match = /^(.*?)\s*\((PPT|Word|Excel)\)\s*$/.exec(title);
        const base = match ? match[1] : title;
        const extension = String(item.file_name || '').split('.').pop().toLowerCase();
        const format = match ? match[2] : (FILE_FORMATS[extension] || extension.toUpperCase() || 'File');
        // Same-named entries (two dashboards called alike) stay apart: a format already present starts a new line.
        let key = base;
        for (let copy = 2; entries.has(key) && entries.get(key).formats.some((link) => link.textContent === format); copy += 1) key = `${base}\u0000${copy}`;
        if (!entries.has(key)) entries.set(key, {base, formats: []});
        const link = node('a', format, `rj-format ${FORMAT_CLASSES[format] || ''}`);
        link.href = `/api/reporting/runs/${run.id}/artifacts/${index}`;
        link.title = item.file_name;
        entries.get(key).formats.push(link);
      });
      renderArtifactGroups(artifacts, [...byModule].map(([module, entries]) => ({
        module,
        items: [...entries].map(([, entry]) => {
          if (entry.failed) return entry.failed;
          const line = document.createDocumentFragment();
          if (entry.base) line.append(`${entry.base} `);
          line.append('(');
          entry.formats.forEach((link, position) => { if (position) line.append('/'); line.append(link); });
          line.append(')');
          return line;
        }),
      })));
      const actions = node('div', undefined, 'table-actions');
      if (run.artifacts.some((item) => item.status === 'ready' && item.available !== false)) actions.append(downloadLink(run));
      if (state.can_edit && !['queued', 'running'].includes(run.status)) {
        actions.append(actionButton('×', 'Delete this run and its artifacts', async () => {
          if (!await confirmDelete('Delete Run', `
            <p>Run <strong>#${run.id}</strong> of <strong>${escapeText(run.task_name)}</strong> and its
            <strong>${run.artifacts.length}</strong> artifact${run.artifacts.length === 1 ? '' : 's'} will be deleted permanently.</p>
            <p>The Reporting Job and its other runs are kept. This cannot be undone.</p>`,
          'Delete Run', `Delete run ${run.id} of ${run.task_name} and its artifacts?`)) return;
          await api(`/api/reporting/runs/${run.id}`, {method: 'DELETE'}); await refresh();
        }, 'danger-button icon-action'));
      }
      const cells = [node('td', String(run.id)), node('td', run.task_name), node('td', run.trigger === 'schedule' ? 'Schedule' : `Manual · ${run.requested_by}`),
        node('td', localTime(run.started_at || run.created_at)), statusCell, node('td', run.send_email ? (run.email_status || 'Pending') : 'No email')];
      row.append(...cells, cellWith(artifacts), cellWith(actions));
      return row;
    }));
  }

  async function refresh() {
    state = await api('/api/reporting/state');
    $('rj-new').hidden = !state.can_edit;
    renderTasks();
    renderRuns();
    clearTimeout(pollTimer);
    const active = state.runs.some((run) => ['queued', 'running'].includes(run.status));
    pollTimer = setTimeout(() => { void refresh().catch((error) => status(error.message, 'error')); }, active ? 4000 : 30000);
  }

  // -- events -------------------------------------------------------------
  // Every edit refreshes the draft kept for a reload.
  ['input', 'change', 'click'].forEach((type) => document.addEventListener(type, (event) => {
    if (event.target.closest?.('#rj-form')) saveDraft();
  }));
  document.addEventListener('change', (event) => {
    if (event.target.closest('#rj-form')) syncEditor();
  });
  $('rj-new').addEventListener('click', async () => {
    if (!await confirmDiscard()) return;
    try { await ensureOptions(); fillEditor(null); } catch (error) { status(error.message, 'error'); }
  });
  $('rj-add-dashboard').addEventListener('click', () => {
    if (!options.dashboards.length) { status('There are no saved Dashboards in this workspace.', 'error'); return; }
    $('rj-dashboards').append(dashboardEntry());
  });
  $('rj-add-scoring').addEventListener('click', () => $('rj-scoring').append(scoringEntry()));
  document.querySelectorAll('#rj-form .rj-card[data-rj-section]').forEach((card) => {
    card.append(collapseButton(card, card.querySelector('.rj-card-toggle strong')?.textContent || 'artifact', `section:${card.dataset.rjSection}`));
  });
  $('rj-add-network').addEventListener('click', () => $('rj-network').append(networkEntry()));
  // Checking an artifact type without entries starts its first entry.
  document.querySelectorAll('[data-rj-entries]').forEach((toggle) => toggle.addEventListener('change', () => {
    const host = $(toggle.dataset.rjEntries);
    if (!toggle.checked || host.children.length) return;
    if (host.id === 'rj-network') host.append(networkEntry());
    else if (host.id === 'rj-scoring') host.append(scoringEntry());
    else if (options.dashboards.length) host.append(dashboardEntry());
  }));
  $('rj-cancel').addEventListener('click', async () => { if (await confirmDiscard()) closeEditor(); });
  $('rj-editor-close').addEventListener('click', async () => { if (await confirmDiscard()) closeEditor(); });
  $('rj-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const button = $('rj-save');
    button.disabled = true;
    try {
      const payload = editorPayload();
      const result = await api(editingId ? `/api/reporting/tasks/${editingId}` : '/api/reporting/tasks', {
        method: editingId ? 'PUT' : 'POST', body: JSON.stringify(payload),
      });
      status(`${result.task.name} saved.`, 'done');
      closeEditor();
      await refresh();
    } catch (error) {
      status(error.message, 'error');
      window.alert(error.message);
    } finally {
      button.disabled = false;
    }
  });

  void refresh().then(restoreDraft).catch((error) => status(error.message, 'error'));
})();
