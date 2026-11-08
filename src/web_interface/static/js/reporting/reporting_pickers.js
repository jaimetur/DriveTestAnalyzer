/* Reporting: the filterable multi-select pickers the report editor uses (the values of a filter, Campaigns), as
   window.reportingPickers. */
(() => {
  'use strict';

  const node = (tag, text, className) => {
    const element = document.createElement(tag);
    if (text !== undefined && text !== null) element.textContent = text;
    if (className) element.className = className;
    return element;
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
})();
