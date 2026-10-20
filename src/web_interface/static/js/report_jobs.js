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
  const STATUS_LABELS = {queued: 'Queued', running: 'Running', stopping: 'Stopping', sent: 'Sent', completed: 'Completed',
    partial: 'Partial', failed: 'Failed', stopped: 'Stopped'};
  // Runs waiting, running or finishing the step they are on after a user stopped them; those Stop and Rerun act on.
  const ACTIVE_RUN_STATUSES = ['queued', 'running', 'stopping'];
  const STOPPABLE_RUN_STATUSES = ['queued', 'running'];
  const RERUN_STATUSES = ['failed', 'stopped'];

  let state = {tasks: [], runs: [], can_edit: false};
  let options = null;
  let editingId = null;
  // When the edited job was last saved on the server, so a draft of an older version is not restored.
  let editingUpdatedAt = '';
  let pollTimer = null;

  // Reloading the page keeps its scroll position. The panels fill in after the page loads (the Bundle Report Template, the
  // jobs and their runs), so the position is applied again as the page grows, until the user moves it.
  const SCROLL_KEY = 'drivetest-analyzer:/reporting:scroll';
  const navigation = performance.getEntriesByType?.('navigation')?.[0]?.type;
  let savedScroll = 0;
  try { savedScroll = ['reload', 'back_forward'].includes(navigation) ? Number(sessionStorage.getItem(SCROLL_KEY)) || 0 : 0; } catch (_) { /* Storage is optional. */ }
  // A section chosen in a menu (#…) opens the page there instead.
  let followingScroll = savedScroll > 0 && !window.location.hash;
  const rememberScroll = () => { try { sessionStorage.setItem(SCROLL_KEY, String(followingScroll ? savedScroll : window.scrollY)); } catch (_) { /* Storage is optional. */ } };
  let scrollTimer = 0;
  window.addEventListener('scroll', () => { if (!followingScroll) { clearTimeout(scrollTimer); scrollTimer = setTimeout(rememberScroll, 200); } }, {passive: true});
  window.addEventListener('pagehide', rememberScroll);
  if (followingScroll) {
    if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
    const growth = 'ResizeObserver' in window ? new ResizeObserver(() => { if (followingScroll) window.scrollTo(0, savedScroll); }) : null;
    const stopFollowing = () => { followingScroll = false; growth?.disconnect(); };
    for (const type of ['wheel', 'touchmove', 'keydown', 'pointerdown']) window.addEventListener(type, stopFollowing, {once: true, passive: true});
    growth?.observe(document.body);
    window.scrollTo(0, savedScroll);
    setTimeout(stopFollowing, 15000);
  }

  // (In the toolbar of the jobs, or in the bar of the Run History with target 'rj-runs-status'.)
  const status = (message, tone = '', target = 'rj-status') => {
    const element = $(target);
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
  // A cell with a date and its time on the line below, which keeps the Next Run and Last Run columns of the jobs narrow.
  const timeCell = (value) => {
    const parsed = value ? new Date(value) : null;
    if (!parsed || Number.isNaN(parsed.getTime())) return node('td', value ? String(value) : '—');
    const cell = node('td', undefined, 'rj-time-cell');
    cell.title = localTime(value);
    cell.append(node('span', parsed.toLocaleDateString(undefined, {dateStyle: 'medium'})),
      node('span', parsed.toLocaleTimeString(undefined, {timeStyle: 'short'})));
    return cell;
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
  // `allLabel` names every value selected (or none), which saves no restriction. With ``list`` the values are a plain
  // list instead (such as Separate cities): none means none, and every value is every value. With ``patterns`` a filter
  // with * (such as VF*) is added as a pattern of its own, which takes every value it matches, also those that appear
  // later (* stands for any characters, whatever the case).
  function multiPicker(label, values, selected = [], {preset = null, onChange = null, exclusive = [], allLabel = 'All', list = false,
    patterns = false} = {}) {
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
    const isPattern = (value) => Boolean(globalThis.valuePatterns?.isPattern(value));
    const patternValues = patterns ? [...new Set([...values, ...selected].map(String).filter(isPattern))] : [];
    if (patterns) values = values.filter((value) => !isPattern(value));
    // An empty saved selection means every value: they all start checked.
    const chosen = new Set(exclusiveChosen ? [] : (selected.length || list ? selected : values).map(String));
    const takenBy = (value) => values.filter((item) => globalThis.valuePatterns.set([value]).accepts(item));
    const patternBoxes = [];
    const patternRow = (value, checked) => {
      const row = node('label', undefined, 'rj-multi-option rj-multi-pattern');
      const box = node('input'); box.type = 'checkbox'; box.value = value; box.checked = checked;
      row.append(box, node('span', value), node('span', globalThis.valuePatterns.tag(value), 'user-choice-tag user-choice-tag-pattern'));
      const taken = takenBy(value);
      row.title = taken.length ? `Takes now: ${taken.join(', ')}` : 'Takes no value now';
      patternBoxes.push(box);
      return row;
    };
    patternValues.forEach((value) => menu.append(patternRow(value, chosen.has(value))));
    const boxes = values.map((value) => {
      const row = node('label', undefined, 'rj-multi-option');
      const box = node('input'); box.type = 'checkbox'; box.value = String(value); box.checked = chosen.has(String(value));
      row.append(box, node('span', ['Campaign', 'Campaigns'].includes(label) ? campaignLabel(value) : String(value)));
      menu.append(row);
      return box;
    });
    if (!values.length) menu.append(node('p', 'No values available.', 'table-help'));
    if (patterns) {
      search.placeholder = 'Filter, or type a pattern such as VF* or -Lebara';
      const addPattern = node('button', '', 'workspace-user-picker-toggle rj-multi-pattern-add');
      addPattern.type = 'button';
      addPattern.hidden = true;
      search.after(addPattern);
      addPattern.before(node('p', globalThis.valuePatterns?.help || '', 'multiselect-pattern-help'));
      const add = () => {
        const value = search.value.trim();
        if (!isPattern(value)) return;
        let box = patternBoxes.find((item) => item.value.toLocaleLowerCase() === value.toLocaleLowerCase());
        if (!box) {
          const row = patternRow(value, true);
          (menu.querySelector('.rj-multi-pattern') || boxes[0]?.parentElement)?.before(row) ?? menu.append(row);
          box = row.querySelector('input');
        }
        box.checked = true;
        // Every value checked means every value: the pattern chooses on its own.
        if (boxes.length && boxes.every((item) => item.checked)) boxes.forEach((item) => { item.checked = false; });
        search.value = '';
        search.dispatchEvent(new Event('input'));
        refresh();
        onChange?.();
      };
      addPattern.addEventListener('click', add);
      search.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && isPattern(search.value.trim())) { event.preventDefault(); add(); }
      });
      search.addEventListener('input', () => {
        const value = search.value.trim();
        addPattern.hidden = !isPattern(value);
        addPattern.textContent = `＋ Add pattern “${value}” · takes ${isPattern(value) ? takenBy(value).length : 0} now`;
      });
    }
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
      const chosenPatterns = patternBoxes.filter((box) => box.checked).map((box) => box.value);
      // All: every value selected, or none (no restriction either way); the patterns chosen are named.
      const state = chosenPatterns.length && !(count === enabled && !list)
        ? [chosenPatterns.join(', '), ...(count ? [`${count} of ${enabled}`] : [])].join(' + ')
        : count === 0 || (count === enabled && !list) ? allLabel : `${count} of ${enabled}`;
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
      patternBoxes.forEach((box) => { box.parentElement.hidden = Boolean(query) && !isPattern(query) && !box.value.toLocaleLowerCase().includes(query); });
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
      const every = !list && checked.length === boxes.filter((box) => !box.disabled).length;
      const chosenPatterns = patternBoxes.filter((box) => box.checked).map((box) => box.value);
      return every ? [] : [...chosenPatterns, ...checked];
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
  // The Bundle Report Templates panel of the page builds its filters with the same pickers.
  window.reportingPickers = {multiPicker, campaignLabel, campaignCompare};
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
        // The Operators take patterns (VF*, -Lebara; see valuePatterns in app.js).
        const picker = multiPicker(text, values[text] || [], current[key] || [], {...(preset ? {preset} : {}), onChange,
          patterns: key === 'operators'});
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
  // offers first Latest campaign, Latest 2, 3 and 4 campaigns, Previous campaign and All available campaigns, which follow the newest campaigns at each run and stand
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
        : multiPicker(name, values[name] || [], selected[name] || [], name === 'City' ? {exclusive: dashboardCityChoices(selected[name])}
          : {patterns: name.replace(/[^a-z]/gi, '').toLowerCase() === 'operator'})]).filter(([, picker]) => picker);
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
  // What a favourite Bundle Report Template includes: its sections in order, each with its sub-modules.
  function favouriteContents(sections) {
    const list = node('ul', undefined, 'rj-artifact-contents');
    sections.forEach((section) => {
      const row = node('li');
      row.append(node('span', section.title, 'rj-artifact-section'), document.createTextNode(`: ${section.items.join(', ')}`));
      list.append(row);
    });
    return list;
  }
  function renderArtifactGroups(list, groups) {
    groups.forEach((group) => {
      const item = node('li');
      item.append(node('strong', group.module, 'rj-artifact-module'));
      const entries = group.items.map((entry) => (typeof entry === 'string' ? withColouredFormats(entry) : entry));
      const contents = group.contents || [];
      // A favourite Bundle Report Template deleted since the job was saved.
      const missing = group.missing || [];
      const missingNote = () => node('div', 'The associated Bundle Report Template no longer exists.', 'rj-artifact-missing');
      if (entries.length > 1) {
        const nested = node('ul', undefined, 'rj-artifact-entries');
        entries.forEach((entry, index) => {
          const row = node('li'); row.append(entry);
          if (missing[index]) row.append(missingNote());
          if (contents[index]?.length) row.append(favouriteContents(contents[index]));
          nested.append(row);
        });
        item.append(nested);
      } else if (entries.length) {
        const text = entries[0].textContent || '';
        item.append(document.createTextNode(text.startsWith('(') ? ' ' : ' · '), entries[0]);
        // A fragment empties when appended; the row text above was read before that.
        if (missing[0]) item.append(missingNote());
        if (contents[0]?.length) item.append(favouriteContents(contents[0]));
      }
      list.append(item);
    });
  }

  let scoringFormatId = 0;
  function scoringEntry(entry = {}) {
    const card = node('div', undefined, 'rj-entry');
    const label = node('input'); label.type = 'text'; label.placeholder = 'Optional artifact name'; label.value = entry.label || '';
    // As in Scoring & GAP Analysis, NSA vs SA (with CDRs of both NR Modes) scores the NSA and SA CDRs of the campaigns
    // side by side, each campaign with its NR Mode.
    const bothModes = ['NSA', 'SA'].every((mode) => options.datasets.some((item) => item.nr_mode === mode));
    const nrMode = select([['NSA', 'NSA'], ['SA', 'SA'], ...(bothModes || entry.nr_mode === 'NSA+SA' ? [['NSA+SA', 'NSA vs SA']] : [])],
      entry.nr_mode || 'NSA');
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
    const cdrsInUse = () => options.datasets.filter((item) => (nrMode.value === 'NSA+SA' ? ['NSA', 'SA'] : [nrMode.value])
      .includes(item.nr_mode)).map((item) => item.id);
    // The name in the email on its own row; then, as on the Scoring & GAP Analysis page, the GAP reference and the
    // methodology beside the campaigns (the Focus operators of its PowerPoint and Word are those of the Operator Maps).
    const nameRow = node('div', undefined, 'rj-grid rj-one-row');
    nameRow.append(field('Name in the email', label));
    head.append(field('NR Mode', nrMode), campaigns.field, field('GAP reference operator', baseline), field('Methodology', methodology), remove);
    // NSA vs SA: how the document shows each NR Mode, as the NSA vs SA and NSA & SA charts of the Scoring & GAP Analysis
    // results (offered while NR Mode is NSA vs SA).
    const nrLayout = select(options.nr_layouts || [], entry.nr_layout || 'interleaved');
    const nrCharts = select(options.nr_charts || [], entry.nr_charts || 'same');
    const nrViews = node('div', undefined, 'rj-grid rj-one-row rj-nr-views');
    nrViews.append(field('NSA vs SA', nrLayout), field('NSA & SA charts', nrCharts));
    nrViews.children[0].title = 'Each panel of NSA followed by the same panel of SA, or every panel of NSA and then every panel of SA';
    nrViews.children[1].title = 'The Scoring Charts and Scoring Trends with NSA and SA in the same chart (the trends on one axis of '
      + 'quarters, SA dashed) or with the charts of each NR Mode on their own';
    const syncNrViews = () => { nrViews.hidden = nrMode.value !== 'NSA+SA'; };
    syncNrViews();
    nrMode.addEventListener('change', () => { campaigns.refresh(); syncNrViews(); });
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
          // No theme here: the theme of the job colours every artifact.
          mainCities: options.main_cities || [], defaults, operatorGroups: options.operator_groups || [], themes: []},
        actions: [['apply', 'Apply to this artifact']],
      });
      if (choice) { report = choice.configuration; describeReport(); }
    });
    reportRow.append(node('span', 'Report content:', 'rj-inline-label'), reportSummary, configure);
    describeReport();
    card.append(entryHead(card, 'Scoring', () => [nrMode.selectedOptions[0]?.textContent, label.value.trim()].filter(Boolean).join(' · ')),
      formats, nameRow, head, nrViews, campaigns.preview, reportRow);
    card.getValue = () => ({
      label: label.value.trim(), nr_mode: nrMode.value, auto_cdrs: true, campaigns: campaigns.getValue(), formats: formats.getValue(),
      scoring_profile_id: methodology.value, baseline_operator: baseline.value.trim() || 'EE', report,
      nr_layout: nrLayout.value, nr_charts: nrCharts.value,
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
    // Campaign offers first Latest campaign, Latest 2, 3 and 4 campaigns, Previous campaign and All available campaigns, each
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
        ...(key === 'operator' ? {patterns: true} : {}),
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
    // The one theme of the job, read by every artifact that supports themes.
    $('rj-theme').replaceChildren(...(options.scoring_themes || []).map((item) => [item.id, item.label || item.id])
      .map(([value, label]) => { const option = node('option', label); option.value = value; return option; }));
    $('rj-theme').value = (options.scoring_themes || []).some((item) => item.id === definition.theme) ? definition.theme : (options.default_theme || 'netcheck');
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
    fillFavourite(task, definition);
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

  // A job starts from a favourite Bundle Report Template (the default for a new job when there is one) or has its artifacts
  // designed in the editor. A job that only generates one favourite opens as such.
  const favouriteChoices = () => (options.providers.find((provider) => provider.key === 'bundle_report_template')?.values?.favourites || [])
    .map((item) => (Array.isArray(item) ? item : [item, item]).map(String));
  const jobSource = () => document.querySelector('input[name="rj-source"]:checked')?.value || 'editor';
  function favouriteOf(definition) {
    const report = definition.modules?.bundle_report_template || {};
    const chosen = report.options?.filters?.favourites || [];
    const others = Boolean(definition.dataset_analysis?.enabled) || (definition.network_insights || []).length > 0
      || (definition.dashboards || []).length > 0 || (definition.scoring || []).length > 0
      || Object.entries(definition.modules || {}).some(([key, module]) => key !== 'bundle_report_template' && module?.enabled);
    return report.enabled && chosen.length === 1 && !others ? {id: String(chosen[0]), formats: report.formats || []} : null;
  }
  function fillFavourite(task, definition) {
    const choices = favouriteChoices();
    const saved = favouriteOf(definition);
    const source = saved || (!task?.id && choices.length && !task?.definition) ? 'favourite' : 'editor';
    document.querySelectorAll('input[name="rj-source"]').forEach((radio) => { radio.checked = radio.value === source; });
    const picker = select(choices.length ? choices : [['', 'No favourite Bundle Report Template yet']], saved?.id || choices[0]?.[0] || '');
    picker.id = 'rj-favourite';
    picker.disabled = !choices.length;
    // Without favourites the editor designs the artifacts: a clear tip says how much easier a favourite makes it.
    $('rj-favourite-tip').hidden = Boolean(choices.length);
    $('rj-favourite-field').replaceChildren(field('Favourite Bundle Report Template', picker));
    formatChoices($('rj-favourite-formats'), 'rj-favourite', saved?.formats?.length ? saved.formats : ['powerpoint', 'word'], ['powerpoint', 'word']);
    $('rj-favourite-note').textContent = choices.length
      ? 'Each run generates the favourite as it is saved then: its sections, filters and Campaigns (the latest ones are chosen again at each run).'
      : 'There is no favourite Bundle Report Template yet: save one in the Bundle Report Templates panel above, or design the artifacts.';
    // A new job takes the name of its favourite (until it is given another).
    const nameOf = (id) => choices.find(([value]) => value === id)?.[1] || '';
    let named = nameOf(picker.value);
    if (!task?.id && !$('rj-name').value.trim() && source === 'favourite') $('rj-name').value = named;
    picker.addEventListener('change', () => {
      if (!$('rj-name').value.trim() || $('rj-name').value.trim() === named) $('rj-name').value = nameOf(picker.value);
      named = nameOf(picker.value);
    });
  }
  document.querySelectorAll('input[name="rj-source"]').forEach((radio) => radio.addEventListener('change', () => {
    if (jobSource() === 'favourite' && !$('rj-name').value.trim()) {
      const picker = $('rj-favourite');
      $('rj-name').value = picker?.selectedOptions?.[0]?.textContent && !picker.disabled ? picker.selectedOptions[0].textContent : '';
    }
    syncEditor();
    syncArtifactTabs();
  }));

  function syncEditor() {
    const source = jobSource();
    document.querySelectorAll('[data-rj-source]').forEach((element) => { element.hidden = element.dataset.rjSource !== source; });
    document.querySelectorAll('[data-rj-module]').forEach((card) => {
      if (source === 'favourite') card.dataset.rjSourceHidden = 'true';
      else delete card.dataset.rjSourceHidden;
    });
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
    const base = editorDefinition();
    return {
      name: $('rj-name').value.trim(),
      definition: jobSource() === 'favourite' ? favouriteDefinition(base) : base,
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

  // A job from a favourite generates only its Bundle Report Template, in the formats chosen.
  function favouriteDefinition(base) {
    const favourite = $('rj-favourite')?.value || '';
    return {
      ...base, dataset_analysis: {...base.dataset_analysis, enabled: false}, network_insights: [], dashboards: [], scoring: [],
      modules: {
        ...Object.fromEntries(Object.entries(base.modules).map(([key, module]) => [key, {...module, enabled: false}])),
        bundle_report_template: {enabled: true, formats: $('rj-favourite-formats').getValue(), options: {filters: {favourites: favourite ? [favourite] : []}}},
      },
    };
  }

  function editorDefinition() {
    return {
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
        theme: $('rj-theme').value || options.default_theme || '',
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
      const cell = node('td', undefined, 'rj-editor-cell'); cell.colSpan = 9;
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
    // An editor reopened by a reload keeps the position of the page.
    if (!followingScroll) editor.scrollIntoView({behavior: 'smooth', block: 'start'});
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
  // Only admins, super-admins and the user who created a job delete it: Delete is locked for the others.
  const lockedForOthers = (button, createdBy, label) => {
    if (!(window.canDeleteShared?.(createdBy) ?? true)) {
      button.disabled = true;
      button.title = window.sharedDeleteRefusal(label);
    }
    return button;
  };
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

  // The header of the panel counts the jobs, those of a favourite Bundle Report Template and those with manual artifacts.
  function renderTaskCounts() {
    const favourites = state.tasks.filter((task) => task.based_on === 'favourite').length;
    $('rj-count-total').textContent = `Total Jobs: ${state.tasks.length}`;
    $('rj-count-favourite').textContent = `Bundle Report Template: ${favourites}`;
    $('rj-count-manual').textContent = `Manual Artifacts: ${state.tasks.length - favourites}`;
  }

  // -- order of the jobs ----------------------------------------------------
  // Editors drag a job by its handle (or move it with the up and down arrow keys on the handle) to order the table;
  // the order is kept in the workspace and travels with the jobs.
  let draggedRow = null;
  let orderBefore = '';
  const taskRows = () => [...$('rj-tasks').tBodies[0].querySelectorAll('tr[data-task-id]')];
  const currentOrder = () => taskRows().map((row) => Number(row.dataset.taskId));
  async function saveOrder() {
    const ids = currentOrder();
    if (JSON.stringify(ids) === orderBefore) return;
    orderBefore = JSON.stringify(ids);
    state.tasks.sort((first, second) => ids.indexOf(first.id) - ids.indexOf(second.id));
    placeEditor();
    try {
      await api('/api/reporting/tasks/order', {method: 'POST', body: JSON.stringify({ids})});
      status('Order of the Reporting Jobs saved.', 'done');
    } catch (error) {
      status(error.message, 'error');
      await refresh();
    }
  }
  function dragHandle() {
    const handle = node('button', '⠿', 'rj-drag-handle');
    handle.type = 'button';
    handle.title = 'Drag to order the Reporting Jobs (or press the up and down arrow keys)';
    handle.setAttribute('aria-label', 'Move this Reporting Job');
    return handle;
  }
  // Dragging follows the pointer (mouse, pen or touch), as the sections of the Bundle Report Template.
  const tasksBody = $('rj-tasks').tBodies[0];
  tasksBody.addEventListener('pointerdown', (event) => {
    const handle = event.target.closest('.rj-drag-handle');
    const row = handle?.closest('tr[data-task-id]');
    if (!row) return;
    event.preventDefault();
    try { handle.setPointerCapture?.(event.pointerId); } catch {}
    draggedRow = row;
    orderBefore = JSON.stringify(currentOrder());
    row.classList.add('rj-dragging');
    const move = (moveEvent) => {
      if (moveEvent.clientY < 70) window.scrollBy(0, -14);
      else if (moveEvent.clientY > window.innerHeight - 70) window.scrollBy(0, 14);
      const next = taskRows().filter((element) => element !== row).find((element) => {
        const box = element.getBoundingClientRect();
        return moveEvent.clientY < box.top + box.height / 2;
      });
      if (next) {
        if (row.nextElementSibling !== next) next.before(row);
      } else {
        const rows = taskRows();
        if (rows[rows.length - 1] !== row) rows[rows.length - 1].after(row);
      }
    };
    const stop = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', stop);
      window.removeEventListener('pointercancel', stop);
      row.classList.remove('rj-dragging');
      draggedRow = null;
      void saveOrder();
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', stop);
    window.addEventListener('pointercancel', stop);
  });
  tasksBody.addEventListener('keydown', (event) => {
    const handle = event.target.closest('.rj-drag-handle');
    const row = handle?.closest('tr[data-task-id]');
    if (!row || !['ArrowUp', 'ArrowDown'].includes(event.key)) return;
    event.preventDefault();
    const rows = taskRows();
    const target = rows[rows.indexOf(row) + (event.key === 'ArrowUp' ? -1 : 1)];
    if (!target) return;
    orderBefore = JSON.stringify(currentOrder());
    if (event.key === 'ArrowUp') target.before(row); else target.after(row);
    handle.focus();
    void saveOrder();
  });

  // The box that selects a job (for editors), on top of the tab on the left of its name by which it is dragged, as the
  // cards of the Favourites Filters of Scoring & GAP Analysis.
  function taskCheck(task) {
    const holder = node('label', undefined, 'rj-task-check-box');
    holder.title = 'Select this job to move or delete it with the buttons above the table';
    const box = node('input', undefined, 'rj-task-check');
    box.type = 'checkbox';
    box.dataset.taskCheck = task.id;
    box.checked = checkedTaskIds.has(task.id);
    box.setAttribute('aria-label', `Select ${task.name}`);
    holder.append(box);
    return holder;
  }

  // Below the areas of a job, always on one line: the modules it generates artifacts of, abbreviated in the colours of
  // their artifact panels (see job_modules), and after a separator its NR Modes, outlined.
  const MODULE_TAGS = {scoring: 'SCO', network_insights: 'NI', non_qualified_calls: 'NQ', dashboards: 'PPT', dataset_analysis: 'CDR'};
  function moduleLine(task) {
    const line = node('div', undefined, 'rj-task-modules');
    (task.modules || []).forEach((key) => {
      const tag = node('span', MODULE_TAGS[key] || key.slice(0, 3).toUpperCase(), 'rj-task-module');
      tag.dataset.module = key;
      tag.title = ARTIFACT_MODULE_LABELS[key] || key;
      line.append(tag);
    });
    const modes = (task.nr_modes || []).map(modeLabel);
    if (modes.length && line.childElementCount) line.append(node('span', undefined, 'rj-task-separator'));
    line.append(...modes);
    return line.childElementCount ? line : null;
  }

  // On a line of their own, the campaigns of the job (see job_campaigns): each choice once, after the modules that make
  // it when its modules choose differently (SCO · PPT: Latest 2 campaigns).
  function campaignTags(task) {
    const choices = task.campaigns || [];
    if (!choices.length) return null;
    const line = node('div', undefined, 'rj-task-campaigns');
    choices.forEach((choice) => {
      const modules = choices.length > 1 ? choice.modules.map((key) => MODULE_TAGS[key] || key.slice(0, 3).toUpperCase()).join(' · ') : '';
      const label = node('span', modules ? `${modules}: ${choice.campaigns}` : choice.campaigns, 'rj-task-campaign');
      label.title = `Campaigns of ${choice.modules.map((key) => ARTIFACT_MODULE_LABELS[key] || key).join(', ')}: ${choice.campaigns}`;
      line.append(label);
    });
    return line;
  }

  // The first line of the name of a job, as the labels of the cards of the Favourites Filters of Scoring & GAP Analysis:
  // the only Region, Cluster, City, Operator or Vendor each of its artifacts filters (Nationwide when none), once each,
  // in the colour of the field (see job_scope).
  function scopeTabs(task) {
    const tabs = node('div', undefined, 'rj-task-tabs');
    (task.scopes || []).forEach((scope) => {
      const label = node('span', scope.text, 'rj-task-scope');
      label.dataset.dimension = scope.dimension;
      label.title = scope.title;
      tabs.append(label);
    });
    return tabs.childElementCount ? tabs : null;
  }
  // An NR Mode of the job, outlined in its colour (NSA vs SA in both).
  function modeLabel(mode) {
    const label = node('span', mode === 'NSA+SA' ? undefined : mode, 'rj-task-mode');
    label.dataset.nrMode = mode === 'NSA+SA' ? 'nsa-vs-sa' : mode.toLowerCase();
    label.title = `NR Mode: ${mode === 'NSA+SA' ? 'NSA vs SA' : mode}`;
    if (mode === 'NSA+SA') {
      for (const [part, partMode] of [['NSA', 'nsa'], [' vs ', ''], ['SA', 'sa']]) {
        const piece = node('span', part);
        if (partMode) piece.dataset.nrMode = partMode;
        label.append(piece);
      }
    }
    return label;
  }

  function renderTasks() {
    renderTaskCounts();
    // A job being dragged keeps its row until it is dropped (the next refresh shows the rest).
    if (draggedRow) return;
    const body = $('rj-tasks').tBodies[0];
    if (!state.tasks.length) {
      emptyRow(body, 'No Reporting Jobs yet.', 10);
      placeEditor();
      syncBulk();
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
      // Whether the job generates a favourite Bundle Report Template or the artifacts chosen in the Job Editor.
      const fromFavourite = task.based_on === 'favourite';
      const basedOn = cellWith(node('span', fromFavourite ? 'Bundle Report Template' : 'Manual Artifacts', `rj-based-on${fromFavourite ? ' rj-based-on-favourite' : ''}`));
      basedOn.title = fromFavourite ? 'The job generates a favourite Bundle Report Template' : 'The artifacts of the job were chosen in the Job Editor';
      const last = task.last_run;
      const lastCell = timeCell(last ? last.started_at || last.created_at : '');
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
          lockedForOthers(actionButton('×', 'Delete the job and its runs', async () => {
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
          }, 'danger-button icon-action'), task.created_by, 'Reporting Job'),
        );
      }
      // Enable/Disable: an enabled job runs on its schedule (▶ Run now works either way), without editing it.
      const switchLabel = node('label', undefined, 'rj-enabled-switch rj-table-switch');
      switchLabel.title = task.enabled ? 'Enabled: the job runs on its schedule. Switch it off to disable it'
        : 'Disabled: the job never runs on its schedule. Switch it on to enable it';
      const switchBox = node('input');
      switchBox.type = 'checkbox';
      switchBox.checked = Boolean(task.enabled);
      switchBox.disabled = !state.can_edit;
      switchBox.setAttribute('aria-label', `${task.enabled ? 'Disable' : 'Enable'} ${task.name}`);
      const switchTrack = node('span', undefined, 'rj-switch');
      switchTrack.setAttribute('aria-hidden', 'true');
      switchLabel.append(switchBox, switchTrack, node('span', task.enabled ? 'Enabled' : 'Disabled', 'rj-table-switch-text'));
      switchBox.addEventListener('change', async () => {
        switchBox.disabled = true;
        try {
          await api(`/api/reporting/tasks/${task.id}/enabled`, {method: 'POST', body: JSON.stringify({enabled: switchBox.checked})});
          status(`${task.name} ${switchBox.checked ? 'enabled' : 'disabled'}.`, 'done');
        } catch (error) {
          status(error.message, 'error');
        }
        await refresh();
      });
      const nameCell = node('td', undefined, `rj-task-name-cell${state.can_edit ? ' is-editable' : ''}`);
      if (state.can_edit) nameCell.append(dragHandle(), taskCheck(task));
      const tabs = scopeTabs(task);
      if (tabs) nameCell.append(tabs);
      const modules = moduleLine(task);
      if (modules) nameCell.append(modules);
      const campaigns = campaignTags(task);
      if (campaigns) nameCell.append(campaigns);
      nameCell.append(node('span', task.name, 'rj-task-name'));
      row.append(
        nameCell, cellWith(artifacts), basedOn,
        node('td', task.recurrence), task.enabled ? timeCell(task.next_run_at) : node('td', 'Disabled'),
        node('td', task.send_email ? `Yes · ${task.recipients.length} recipient${task.recipients.length === 1 ? '' : 's'}` : 'No'),
        lastCell, statusCell, cellWith(switchLabel), cellWith(actions),
      );
      row.cells[5].title = task.recipients.join(', ');
      return row;
    }));
    placeEditor();
    syncBulk();
  }

  // -- several jobs at once ---------------------------------------------------
  // Editors check jobs (or Select all) to move them one place up or down together, as dragging them would, or to delete
  // them together, as the Favourites Filters of Scoring & GAP Analysis.
  const checkedTaskIds = new Set();
  let deletingCheckedTasks = false;
  const selectAllTasks = $('rj-select-all');
  const moveTaskButtons = [...document.querySelectorAll('[data-rj-move]')];
  const deleteCheckedTasks = $('rj-delete-selected');
  // The order of the jobs with each checked one a place up (step -1) or down (step 1): a checked one trades places with
  // the unchecked one next to it, so checked ones side by side move together and stop at the end.
  function movedTaskOrder(order, step) {
    const moved = [...order];
    const indexes = moved.map((_, index) => index);
    for (const index of step < 0 ? indexes.slice(1) : indexes.slice(0, -1).reverse()) {
      if (checkedTaskIds.has(moved[index]) && !checkedTaskIds.has(moved[index + step])) {
        [moved[index], moved[index + step]] = [moved[index + step], moved[index]];
      }
    }
    return moved;
  }
  function syncBulk() {
    const ids = state.tasks.map((task) => task.id);
    for (const id of [...checkedTaskIds]) if (!ids.includes(id)) checkedTaskIds.delete(id);
    $('rj-bulk').hidden = !state.can_edit || !ids.length;
    selectAllTasks.checked = ids.length > 0 && checkedTaskIds.size === ids.length;
    selectAllTasks.indeterminate = checkedTaskIds.size > 0 && checkedTaskIds.size < ids.length;
    // A button is off when no checked job can move that way.
    for (const button of moveTaskButtons) {
      const step = button.dataset.rjMove === 'up' ? -1 : 1;
      button.disabled = deletingCheckedTasks || movedTaskOrder(ids, step).join() === ids.join();
    }
    deleteCheckedTasks.textContent = checkedTaskIds.size ? `Delete (${checkedTaskIds.size})` : 'Delete';
    deleteCheckedTasks.disabled = deletingCheckedTasks || !checkedTaskIds.size;
  }
  // The bar is held at the top while the table is scrolled; then a band behind it hides the page above it.
  const syncBulkStuck = () => {
    const bar = $('rj-bulk');
    const top = parseFloat(getComputedStyle(bar).top) || 0;
    bar.classList.toggle('is-stuck', !bar.hidden && bar.getBoundingClientRect().top <= top + 1
      && $('rj-tasks').getBoundingClientRect().top < top + bar.offsetHeight);
  };
  window.addEventListener('scroll', syncBulkStuck, {passive: true});
  window.addEventListener('resize', syncBulkStuck);
  tasksBody.addEventListener('change', (event) => {
    const box = event.target.closest('[data-task-check]');
    if (!box) return;
    if (box.checked) checkedTaskIds.add(Number(box.dataset.taskCheck));
    else checkedTaskIds.delete(Number(box.dataset.taskCheck));
    syncBulk();
  });
  selectAllTasks.addEventListener('change', () => {
    checkedTaskIds.clear();
    if (selectAllTasks.checked) state.tasks.forEach((task) => checkedTaskIds.add(task.id));
    tasksBody.querySelectorAll('[data-task-check]').forEach((box) => { box.checked = checkedTaskIds.has(Number(box.dataset.taskCheck)); });
    syncBulk();
  });
  // Move Up and Move Down save the new order as dragging does; the moved jobs light up where they land, and the one that
  // leads the way stays in view below the bar of these buttons, which stays at the top while the table is scrolled.
  moveTaskButtons.forEach((button) => button.addEventListener('click', () => {
    const step = button.dataset.rjMove === 'up' ? -1 : 1;
    const order = state.tasks.map((task) => task.id);
    const moved = movedTaskOrder(order, step);
    if (moved.join() === order.join()) return;
    const rows = new Map(taskRows().map((row) => [Number(row.dataset.taskId), row]));
    orderBefore = JSON.stringify(order);
    moved.forEach((id) => tasksBody.append(rows.get(id)));
    void saveOrder();
    syncBulk();
    const lit = moved.filter((id) => checkedTaskIds.has(id)).map((id) => rows.get(id));
    lit.forEach((row) => { row.classList.remove('rj-moved'); void row.offsetWidth; row.classList.add('rj-moved'); });
    const leading = step < 0 ? lit[0] : lit[lit.length - 1];
    if (leading) {
      const bar = $('rj-bulk');
      const clear = (parseFloat(getComputedStyle(bar).top) || 0) + bar.offsetHeight + 12;
      const box = leading.getBoundingClientRect();
      if (box.top < clear) window.scrollBy({top: box.top - clear, behavior: 'auto'});
      else if (box.bottom > window.innerHeight - 12) window.scrollBy({top: box.bottom - window.innerHeight + 12, behavior: 'auto'});
    }
  }));
  // The checked jobs are deleted together after one confirmation, each as its own Delete would (with its runs and their
  // artifacts, and recorded in App Events); those that cannot be deleted are named.
  deleteCheckedTasks.addEventListener('click', async () => {
    const targets = state.tasks.filter((task) => checkedTaskIds.has(task.id));
    if (!targets.length || deletingCheckedTasks) return;
    // None of them is deleted while one belongs to another user (only admins, super-admins and its creator delete it).
    const refused = targets.filter((task) => !(window.canDeleteShared?.(task.created_by) ?? true));
    if (refused.length) {
      status(`${window.sharedDeleteRefusal('Reporting Job')} (${refused.map((task) => task.name).join(', ')}). No job was deleted.`, 'error');
      return;
    }
    const count = targets.length;
    const plural = count === 1 ? '' : 's';
    const runs = state.runs.filter((run) => targets.some((task) => task.id === run.task_id)).length;
    if (!await confirmDelete(`Delete ${count} Reporting Job${plural}`, `
      <p>${count === 1 ? 'This Reporting Job' : `These ${count} Reporting Jobs`} will be deleted permanently:</p>
      <ul>${targets.map((task) => `<li><strong>${escapeText(task.name)}</strong></li>`).join('')}</ul>
      <p>Together with ${count === 1 ? 'its' : 'their'} schedule and email delivery, ${runs ? `<strong>${runs}</strong> run${runs === 1 ? '' : 's'} in the Run History` : 'the run history'} and every artifact generated by those runs.</p>
      <p>This cannot be undone. To keep a job without running it, disable it instead.</p>`,
    count === 1 ? 'Delete Job' : `Delete ${count} Jobs`, `Delete ${count} Reporting Job${plural}, their run history and artifacts?`)) return;
    deletingCheckedTasks = true;
    syncBulk();
    status(`Deleting ${count} Reporting Job${plural}…`);
    try {
      const result = await api('/api/reporting/tasks/delete', {method: 'POST', body: JSON.stringify({ids: targets.map((task) => task.id)})});
      const deleted = new Set(result.deleted || []);
      deleted.forEach((id) => checkedTaskIds.delete(id));
      if (deleted.has(editingId)) closeEditor();
      status(`${deleted.size} Reporting Job${deleted.size === 1 ? '' : 's'} deleted.`, 'done');
    } catch (error) {
      status(error.message, 'error');
    }
    deletingCheckedTasks = false;
    await refresh();
  });

  function renderRuns() {
    const body = $('rj-runs').tBodies[0];
    if (!state.runs.length) {
      emptyRow(body, 'No runs yet.', 9);
      syncRunsHeight();
      syncRunsBulk();
      return;
    }
    body.replaceChildren(...state.runs.map((run) => {
      const row = node('tr');
      row.dataset.runId = run.id;
      const statusCell = node('td');
      statusCell.append(statusBadge(run));
      const duration = runDuration(run);
      const active = ACTIVE_RUN_STATUSES.includes(run.status);
      if (active) statusCell.append(node('small', ` ${run.progress}% · ${run.message}`));
      else if (duration) statusCell.append(node('small', ` in ${duration}`, 'rj-duration'));
      // (Who stopped it, and when.)
      if (run.status === 'stopped' && run.message) statusCell.append(node('small', ` ${run.message}`));
      if (!active && run.error) statusCell.append(node('small', ` ${run.error}`, 'rj-error'));
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
      if (state.can_edit && RERUN_STATUSES.includes(run.status)) {
        actions.append(actionButton('↻', 'Rerun: run it again from the beginning', onRuns(rerunRuns, run), 'icon-action rj-rerun'));
      }
      if (state.can_edit && STOPPABLE_RUN_STATUSES.includes(run.status)) {
        actions.append(actionButton('■', run.status === 'queued' ? 'Stop: it does not start' : 'Stop after the step it is on',
          onRuns(stopRuns, run), 'icon-action rj-stop'));
      }
      if (state.can_edit && !active) {
        actions.append(actionButton('×', 'Delete this run and its artifacts', onRuns(deleteRuns, run), 'danger-button icon-action'));
      }
      // The run as its job: the labels of the job above its name, as in the Reporting Jobs table.
      const task = state.tasks.find((item) => item.id === run.task_id);
      const jobCell = node('td', undefined, 'rj-run-job');
      for (const labels of task ? [scopeTabs(task), moduleLine(task), campaignTags(task)] : []) if (labels) jobCell.append(labels);
      jobCell.append(node('span', run.task_name, 'rj-task-name'));
      const runCell = node('td', undefined, 'rj-run-id');
      if (state.can_edit) runCell.append(runCheck(run));
      runCell.append(String(run.id));
      const cells = [runCell, jobCell, node('td', run.trigger === 'schedule' ? 'Schedule' : `Manual · ${run.requested_by}`),
        node('td', localTime(run.started_at || run.created_at)), statusCell, node('td', run.send_email ? (run.email_status || 'Pending') : 'No email')];
      // What all the artifacts of the run take on disk.
      const size = node('td', run.artifacts_size ? formatSize(run.artifacts_size) : '—', 'rj-size');
      size.title = 'Size of all the artifacts of this run';
      row.append(...cells, cellWith(artifacts), size, cellWith(actions));
      return row;
    }));
    syncRunsHeight();
    syncRunsBulk();
  }

  // -- several runs at once -------------------------------------------------------
  // Editors check runs (or Select all) to run again those that failed or were stopped, stop those queued or running,
  // or delete those that are not, together; each button counts the checked runs it acts on.
  const checkedRunIds = new Set();
  let actingOnCheckedRuns = false;
  const runsBody = $('rj-runs').tBodies[0];
  const selectAllRuns = $('rj-runs-select-all');
  const rerunCheckedRuns = $('rj-rerun-selected');
  const stopCheckedRuns = $('rj-stop-selected');
  const deleteCheckedRuns = $('rj-delete-runs-selected');
  function runCheck(run) {
    const holder = node('label', undefined, 'rj-run-check');
    holder.title = 'Select this run to rerun, stop or delete it with the buttons above the table';
    const box = node('input');
    box.type = 'checkbox';
    box.dataset.runCheck = run.id;
    box.checked = checkedRunIds.has(run.id);
    box.setAttribute('aria-label', `Select run ${run.id} of ${run.task_name}`);
    holder.append(box);
    return holder;
  }
  const checkedRuns = (statuses) => state.runs.filter((run) => checkedRunIds.has(run.id) && statuses(run.status));
  function syncRunsBulk() {
    const ids = state.runs.map((run) => run.id);
    for (const id of [...checkedRunIds]) if (!ids.includes(id)) checkedRunIds.delete(id);
    $('rj-runs-bulk').hidden = !state.can_edit || !ids.length;
    selectAllRuns.checked = ids.length > 0 && checkedRunIds.size === ids.length;
    selectAllRuns.indeterminate = checkedRunIds.size > 0 && checkedRunIds.size < ids.length;
    for (const [button, label, statuses] of [
      [rerunCheckedRuns, 'Rerun', (value) => RERUN_STATUSES.includes(value)],
      [stopCheckedRuns, 'Stop', (value) => STOPPABLE_RUN_STATUSES.includes(value)],
      [deleteCheckedRuns, 'Delete', (value) => !ACTIVE_RUN_STATUSES.includes(value)],
    ]) {
      const count = checkedRuns(statuses).length;
      button.textContent = count ? `${label} (${count})` : label;
      button.disabled = actingOnCheckedRuns || !count;
    }
  }
  runsBody.addEventListener('change', (event) => {
    const box = event.target.closest('[data-run-check]');
    if (!box) return;
    if (box.checked) checkedRunIds.add(Number(box.dataset.runCheck));
    else checkedRunIds.delete(Number(box.dataset.runCheck));
    syncRunsBulk();
  });
  selectAllRuns.addEventListener('change', () => {
    checkedRunIds.clear();
    if (selectAllRuns.checked) state.runs.forEach((run) => checkedRunIds.add(run.id));
    runsBody.querySelectorAll('[data-run-check]').forEach((box) => { box.checked = checkedRunIds.has(Number(box.dataset.runCheck)); });
    syncRunsBulk();
  });
  // (The buttons of a row tell their errors in the bar of the Run History.)
  const onRuns = (action, run) => async () => {
    try { await action([run]); } catch (error) { status(error.message, 'error', 'rj-runs-status'); }
  };
  const runList = (runs) => `<ul>${runs.map((run) => `<li>Run <strong>#${run.id}</strong> of <strong>${escapeText(run.task_name)}</strong></li>`).join('')}</ul>`;
  const runsText = (count) => `${count} run${count === 1 ? '' : 's'}`;
  // Failed (also interrupted) and stopped runs start again from the beginning, each in its own row, with what their
  // job generates now.
  async function rerunRuns(runs) {
    const result = await api('/api/reporting/runs/rerun', {method: 'POST', body: JSON.stringify({ids: runs.map((run) => run.id)})});
    const skipped = (result.skipped || []).length;
    status(`${runsText((result.rerun || []).length)} queued again.${skipped ? ` ${runsText(skipped)} could not be run again.` : ''}`,
      'done', 'rj-runs-status');
    await refresh();
  }
  // A queued run does not start; a running one stops after the step it is on, keeping what it generated.
  async function stopRuns(runs) {
    const count = runs.length;
    if (!await confirmDelete(count === 1 ? 'Stop Run' : `Stop ${count} Runs`, `
      <p>${count === 1 ? 'This run' : `These ${count} runs`} will be stopped:</p>${runList(runs)}
      <p>A queued run does not start; a running run stops after the step it is on and keeps the artifacts it generated,
      without sending its email. Rerun runs it again from the beginning.</p>`,
    count === 1 ? 'Stop Run' : `Stop ${count} Runs`, `Stop ${runsText(count)}?`)) return;
    const result = await api('/api/reporting/runs/stop', {method: 'POST', body: JSON.stringify({ids: runs.map((run) => run.id)})});
    const stopping = (result.stopping || []).length;
    status(`${runsText((result.stopped || []).length + stopping)} stopped${stopping ? ` (${stopping} after the step ${stopping === 1 ? 'it is' : 'they are'} on)` : ''}.`,
      'done', 'rj-runs-status');
    await refresh();
  }
  async function deleteRuns(runs) {
    const count = runs.length;
    const artifacts = runs.reduce((total, run) => total + run.artifacts.length, 0);
    if (!await confirmDelete(count === 1 ? 'Delete Run' : `Delete ${count} Runs`, `
      <p>${count === 1 ? 'This run' : `These ${count} runs`} and ${count === 1 ? 'its' : 'their'} <strong>${artifacts}</strong>
      artifact${artifacts === 1 ? '' : 's'} will be deleted permanently:</p>${runList(runs)}
      <p>The Reporting Jobs and their other runs are kept. This cannot be undone.</p>`,
    count === 1 ? 'Delete Run' : `Delete ${count} Runs`, `Delete ${runsText(count)} and their artifacts?`)) return;
    const result = await api('/api/reporting/runs/delete', {method: 'POST', body: JSON.stringify({ids: runs.map((run) => run.id)})});
    (result.deleted || []).forEach((id) => checkedRunIds.delete(id));
    status(`${runsText((result.deleted || []).length)} deleted.`, 'done', 'rj-runs-status');
    await refresh();
  }
  for (const [button, action, statuses] of [
    [rerunCheckedRuns, rerunRuns, (value) => RERUN_STATUSES.includes(value)],
    [stopCheckedRuns, stopRuns, (value) => STOPPABLE_RUN_STATUSES.includes(value)],
    [deleteCheckedRuns, deleteRuns, (value) => !ACTIVE_RUN_STATUSES.includes(value)],
  ]) {
    button.addEventListener('click', async () => {
      const runs = checkedRuns(statuses);
      if (!runs.length || actingOnCheckedRuns) return;
      actingOnCheckedRuns = true;
      syncRunsBulk();
      try { await action(runs); } catch (error) { status(error.message, 'error', 'rj-runs-status'); }
      actingOnCheckedRuns = false;
      syncRunsBulk();
    });
  }

  // Run History shows the latest 10 runs; the older ones are reached by scrolling its table.
  const RUN_HISTORY_ROWS = 10;
  function syncRunsHeight() {
    const table = $('rj-runs');
    const wrapper = table.closest('.table-wrap');
    requestAnimationFrame(() => {
      // (A collapsed panel has nothing to measure: it is measured again when opened.)
      if (!wrapper.offsetParent) return;
      const rows = Array.from(table.tBodies[0].rows);
      // (Phones show each run as a card, one under the other.)
      if (rows.length <= RUN_HISTORY_ROWS || window.matchMedia('(max-width: 640px)').matches) {
        wrapper.style.maxHeight = '';
        return;
      }
      const rowsHeight = rows.slice(0, RUN_HISTORY_ROWS).reduce((height, row) => height + row.getBoundingClientRect().height, 0);
      // (Borders and a horizontal scrollbar are kept out of the rows.)
      const frame = wrapper.offsetHeight - wrapper.clientHeight;
      wrapper.style.maxHeight = `${Math.ceil(table.tHead.getBoundingClientRect().height + rowsHeight + frame)}px`;
    });
  }
  $('rj-runs').closest('details').addEventListener('toggle', syncRunsHeight);
  window.addEventListener('resize', syncRunsHeight);

  const formatSize = (bytes) => {
    const units = ['B', 'KB', 'MB', 'GB'];
    let value = Number(bytes) || 0;
    let unit = 0;
    while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit += 1; }
    return `${value >= 100 || unit === 0 ? Math.round(value) : value.toFixed(1)} ${units[unit]}`;
  };

  async function refresh() {
    state = await api('/api/reporting/state');
    $('rj-new').hidden = !state.can_edit;
    renderTasks();
    renderRuns();
    clearTimeout(pollTimer);
    const active = state.runs.some((run) => ACTIVE_RUN_STATUSES.includes(run.status));
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
    // A job from a favourite needs one (without it, the Bundle Report Template artifact would generate every favourite).
    if (jobSource() === 'favourite' && !$('rj-favourite')?.value) {
      status('Choose the favourite Bundle Report Template of the job, or design its artifacts.', 'error');
      return;
    }
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

  // Saving, renaming or deleting a favourite Bundle Report Template changes the jobs that generate it.
  document.addEventListener('bundle-report-template:favourites-changed', () => { void refresh().catch((error) => status(error.message, 'error')); });

  void refresh().then(restoreDraft).catch((error) => status(error.message, 'error'));
})();
