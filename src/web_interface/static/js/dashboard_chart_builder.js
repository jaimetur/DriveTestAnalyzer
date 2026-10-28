/* The chart builder of the Dashboard Designer (ticket #26, phase 2): the data pane, shelves and Chart Type of a chart.

   A chart is built Tableau-like: the fields of its source (dimensions and measures told apart, grouped by the sections of
   the CDR Field Dictionary) are dragged to its shelves — Measure, Rows, Columns, Legend, Filters and Repeat by — and Chart Type
   offers the chart types the shelves can draw, the others greyed with the reason. Each change gives the values of the
   chart as its template row writes them (KPI, Rows Split, Columns Split, Legend, Filters, Chart type, Dynamic Rows/Columns
   Field), so the same engine and renderer draw it. Used by Design (dashboard_designer.js) and by Chart Builder. */
(() => {
  'use strict';
  const h = (tag, props = {}, ...children) => {
    const element = document.createElement(tag);
    for (const [key, value] of Object.entries(props || {})) {
      if (value === undefined || value === null || value === false) continue;
      if (key === 'class') element.className = value;
      else if (key === 'text') element.textContent = value;
      else if (key === 'dataset') Object.assign(element.dataset, value);
      else if (key === 'style') Object.assign(element.style, value);
      else if (key.startsWith('on') && typeof value === 'function') element.addEventListener(key.slice(2), value);
      else if (typeof value === 'boolean') element.toggleAttribute(key, value);
      else element.setAttribute(key, value);
    }
    element.append(...children.flat().filter(child => child !== null && child !== undefined && child !== false));
    return element;
  };
  const identity = value => String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, '');

  const SOURCES = [['CDR-Data', 'Data'], ['CDR-Voice', 'Voice'], ['CDR-Speech', 'Speech'], ['CDR-All', 'RF All']];
  const NR_MODES = [['', 'Dashboard'], ['NSA', 'NSA'], ['SA', 'SA']];
  // The settings a chart type keeps among its Filters, shown with Chart Type instead of as filters.
  const SETTINGS = ['threshold', 'buckets', 'binsize', 'classcolours', 'histogramoperator', 'nrmode'];
  const AGGREGATIONS = [['', 'As the chart type counts it'], ['AVG', 'Average'], ['MEDIAN', 'Median'], ['SUM', 'Sum'], ['COUNT', 'Count'], ['COUNTD', 'Count distinct'], ['MIN', 'Minimum'], ['MAX', 'Maximum']];
  // Chart Type: each chart type, its picture and what its shelves need.
  const TYPES = [
    {type: 'CDF Line', icon: 'M3 20 C 8 19, 9 8, 13 6 S 19 4, 21 4', need: s => s.numeric === 1 && s.measures === 1 || 'One numeric measure'},
    {type: 'Multi KPI CDF Lines', icon: 'M3 20 C 8 19, 9 8, 13 6 S 19 4, 21 4 M3 20 C 10 20, 12 13, 15 11 S 19 9, 21 8', need: s => s.numeric >= 2 && s.numeric === s.measures || 'Two numeric measures or more'},
    {type: 'Average Vertical Bars', icon: 'M5 20V11M10 20V6M15 20V13M20 20V9', need: s => s.numeric >= 1 && s.splits >= 1 || 'A numeric measure and a Rows or Columns split'},
    {type: 'Median Vertical Bars', icon: 'M5 20V13M10 20V8M15 20V11M20 20V6', need: s => s.numeric >= 1 && s.splits >= 1 || 'A numeric measure and a Rows or Columns split'},
    {type: '100% Stacked Vertical Bars', icon: 'M6 20V4M12 20V4M18 20V4M4 10h4M10 13h4M16 8h4', need: s => s.text === 1 && s.measures === 1 || 'One dimension as the measure (such as Call_Status)'},
    {type: 'Count Stacked Horizontal Bars', icon: 'M4 6h12M4 12h16M4 18h9', need: s => s.measures === 1 || 'One measure'},
    {type: 'Threshold Stacked Vertical Bars', icon: 'M6 20V8M12 20V5M18 20V10M3 12h18', need: s => s.numeric === 1 && s.measures === 1 || 'One numeric measure', setting: 'Threshold'},
    {type: 'Distribution Stacked Vertical Bars', icon: 'M6 20V4M12 20V4M18 20V4M4 8h4M4 14h4M10 10h4M16 12h4', need: s => s.numeric === 1 && s.measures === 1 || 'One numeric measure', setting: 'Buckets'},
    {type: 'Histogram Bars', icon: 'M4 20v-4M7 20v-8M10 20V6M13 20V9M16 20v-6M19 20v-2', need: s => s.numeric === 1 && s.measures === 1 || 'One numeric measure', setting: 'Bin Size'},
    {type: 'Histogram Line', icon: 'M3 20 L6 16 L9 9 L12 6 L15 11 L18 17 L21 19', need: s => s.numeric === 1 && s.measures === 1 || 'One numeric measure', setting: 'Bin Size'},
    {type: 'Scatter', icon: 'M6 17h.01M9 12h.01M12 15h.01M14 8h.01M17 11h.01M19 5h.01', need: s => s.numeric === 2 && s.measures === 2 || 'Two numeric measures'},
    {type: 'Table', icon: 'M4 5h16v14H4zM4 10h16M4 15h16M10 5v14', need: s => s.measures >= 1 || 'A measure'},
    {type: 'Dynamic Table', icon: 'M4 5h16v14H4zM4 10h16M10 5v14M15 5v14', need: s => s.measures >= 1 || 'A measure'},
    {type: 'Map', icon: 'M12 21s-6-6.2-6-11a6 6 0 0 1 12 0c0 4.8-6 11-6 11zM12 12a2 2 0 1 0 0-4 2 2 0 0 0 0 4', need: s => s.geo || 'Latitude and Longitude in the source'},
  ];
  const SHELVES = [
    ['kpi', 'Measure', 'The KPI the chart measures (several for Multi KPI CDF Lines, Scatter or a Table)'],
    ['rows_split', 'Rows', 'Categories or table rows, in order (Operator × Campaign)'],
    ['columns_split', 'Columns', 'Series or table columns, in order'],
    ['legend', 'Legend', 'The fields the legend explains'],
    ['filters', 'Filters', 'Conditions on the rows of the chart'],
    ['repeat', 'Repeat by', 'One chart per value of a field (with a dynamic layout of the slide)'],
  ];

  const splitParts = (value, separator) => String(value || '').split(separator).map(part => part.trim()).filter(Boolean);
  const kpiParts = value => splitParts(value, /\s+vs\s+|\s*\|\s*/i);
  const kpiField = part => { const match = /^(SUM|COUNTD|COUNT|AVERAGE|AVG|MEAN|MAX|MIN|MEDIAN)\s*\(\s*(.+?)\s*\)$/i.exec(part); return match ? match[2] : part; };
  const kpiAggregation = part => (/^(SUM|COUNTD|COUNT|AVERAGE|AVG|MEAN|MAX|MIN|MEDIAN)\s*\(/i.exec(part)?.[1] || '').toUpperCase().replace(/^AVERAGE$|^MEAN$/, 'AVG');
  const conditions = value => splitParts(value, /;|\n+/);
  const conditionField = condition => (/^(.+?)\s+(NOT\s+CONTAINS|NOT\s+IN|CONTAINS|IN|>=|<=|!=|=|>|<)\s+/i.exec(condition)?.[1] || condition).trim();
  const isSetting = condition => SETTINGS.includes(identity(conditionField(condition)));

  /** Render the builder of one chart into ``host``.
   *  options: {values, fields: {source: [{name, type, category}]}, calculated: [names], parameters: [...],
   *            lockedFilters: [labels], fieldValues: async (source, field) => [{value, count}], onChange(changes),
   *            showSource (false: the source and NR Mode are chosen elsewhere, as in Chart Builder)} */
  function render(host, options) {
    const values = {...options.values};
    const source = String(values.cdr_source || 'CDR-Data');
    const sourceKey = source.toLowerCase();
    const fieldList = [...(options.fields?.[sourceKey] || [])];
    for (const name of options.calculated || []) if (!fieldList.some(item => identity(item.name) === identity(name))) fieldList.push({name, type: 'text', category: 'Auto-calculated Fields'});
    const typeOf = name => fieldList.find(item => identity(item.name) === identity(name))?.type || 'text';
    const change = changes => options.onChange(changes);
    const filterList = conditions(values.filters);
    const settings = filterList.filter(isSetting);
    const plainFilters = filterList.filter(condition => !isSetting(condition));
    const nrMode = (() => {
      const condition = settings.find(item => identity(conditionField(item)) === 'nrmode');
      const match = condition && /\(([^)]*)\)/.exec(condition);
      const modes = match ? match[1].split(',').map(item => item.trim().toUpperCase()) : [];
      return modes.length === 1 ? modes[0] : '';
    })();
    const writeFilters = (plain, kept = settings) => change({filters: [...plain, ...kept].join('; ')});

    // The state the shelves give Chart Type.
    const measures = kpiParts(values.kpi);
    const numeric = measures.filter(part => typeOf(kpiField(part)) === 'number').length;
    const shelfState = {
      measures: measures.length, numeric, text: measures.length - numeric,
      splits: splitParts(values.rows_split, '×').length + splitParts(values.columns_split, '×').length,
      geo: fieldList.some(item => identity(item.name) === 'latitude') && fieldList.some(item => identity(item.name) === 'longitude'),
    };

    // Data pane
    let query = '';
    const fieldsHost = h('div', {class: 'ds-cb-fields'});
    const paintFields = () => {
      const groups = new Map();
      for (const item of fieldList) {
        if (query && !item.name.toLowerCase().includes(query)) continue;
        const group = item.category || 'Other fields';
        if (!groups.has(group)) groups.set(group, []);
        groups.get(group).push(item);
      }
      fieldsHost.replaceChildren(...[...groups.entries()].map(([group, items]) => h('details', {class: 'ds-cb-group', open: Boolean(query) || group !== 'Other fields'},
        h('summary', {}, group, h('span', {class: 'ds-cb-count', text: String(items.length)})),
        h('div', {class: 'ds-cb-group-fields'}, items.sort((left, right) => (left.type === right.type ? left.name.localeCompare(right.name) : left.type === 'text' ? -1 : 1)).map(fieldPill)))));
      if (!fieldsHost.childElementCount) fieldsHost.append(h('p', {class: 'ds-cb-empty', text: fieldList.length ? 'No field matches.' : 'The fields appear once the Dashboard is prepared.'}));
    };
    const fieldPill = item => {
      const pill = h('button', {type: 'button', class: `ds-cb-field is-${item.type}`, draggable: 'true', title: `${item.name} · ${item.type === 'number' ? 'measure (numbers)' : 'dimension (values)'} · drag it to a shelf, or click to choose one`,
        onclick: event => openMenu(event.currentTarget, SHELVES.map(([key, label]) => [label, () => addToShelf(key, item.name)]))},
      h('span', {class: 'ds-cb-type', text: item.type === 'number' ? '#' : 'Abc'}), item.name);
      pill.addEventListener('dragstart', event => { event.dataTransfer.setData('application/x-ds-field', item.name); event.dataTransfer.effectAllowed = 'copy'; });
      return pill;
    };
    const search = h('input', {type: 'search', class: 'ds-cb-search', placeholder: 'Search fields', 'aria-label': 'Search fields',
      oninput: event => { query = event.target.value.trim().toLowerCase(); paintFields(); }});
    paintFields();

    // Shelves
    function shelfItems(key) {
      if (key === 'kpi') return measures;
      if (key === 'rows_split' || key === 'columns_split') return splitParts(values[key], '×');
      if (key === 'legend') return splitParts(values.legend, ',');
      if (key === 'filters') return plainFilters;
      return [values.dynamic_rows_field ? `Rows: ${values.dynamic_rows_field}` : '', values.dynamic_columns_field ? `Columns: ${values.dynamic_columns_field}` : ''].filter(Boolean);
    }
    function writeShelf(key, items) {
      if (key === 'kpi') change({kpi: items.join(' | ')});
      else if (key === 'rows_split' || key === 'columns_split') change({[key]: items.join(' × ')});
      else if (key === 'legend') change({legend: items.join(', ')});
      else if (key === 'filters') writeFilters(items);
    }
    function addToShelf(key, field) {
      if (key === 'filters') { openFilterDialog(field); return; }
      if (key === 'repeat') {
        openMenu(document.activeElement || host, [['Repeat as rows', () => change({dynamic_rows_field: field})], ['Repeat as columns', () => change({dynamic_columns_field: field})]]);
        return;
      }
      const items = shelfItems(key).filter(item => identity(key === 'kpi' ? kpiField(item) : item) !== identity(field));
      const next = key === 'kpi' && !['Multi KPI CDF Lines', 'Scatter', 'Table', 'Dynamic Table'].includes(values.chart_type) ? [field] : [...items, field];
      const changes = {};
      if (key === 'kpi') changes.kpi = next.join(' | ');
      else if (key === 'legend') changes.legend = next.join(', ');
      else changes[key] = next.join(' × ');
      if (key === 'kpi') Object.assign(changes, suggestType({...shelfState, measures: next.length, numeric: next.filter(part => typeOf(kpiField(part)) === 'number').length, text: next.filter(part => typeOf(kpiField(part)) !== 'number').length}));
      change(changes);
    }
    // Chart Type proposes the chart type the measures call for when the current one cannot draw them.
    function suggestType(state) {
      const current = TYPES.find(item => item.type.toLowerCase() === String(values.chart_type || '').toLowerCase());
      if (current && current.need(state) === true) return {};
      const best = state.numeric >= 2 ? (state.numeric === 2 ? 'Scatter' : 'Multi KPI CDF Lines')
        : state.text >= 1 ? '100% Stacked Vertical Bars'
          : state.splits ? 'Average Vertical Bars' : 'CDF Line';
      return {chart_type: best};
    }
    const shelf = ([key, label, title]) => {
      const items = shelfItems(key);
      const zone = h('div', {class: `ds-cb-shelf-items${items.length ? '' : ' is-empty'}`, 'aria-label': `${label} shelf`},
        key === 'filters' ? (options.lockedFilters || []).map(text => h('span', {class: 'ds-cb-pill is-locked', title: 'A filter of the Dashboard: it applies to every chart', text})) : null,
        items.map((item, index) => shelfPill(key, item, index, items)),
        items.length ? null : h('span', {class: 'ds-cb-drop-hint', text: key === 'filters' ? 'Drop a field to filter' : 'Drop a field here'}));
      zone.addEventListener('dragover', event => {
        if ([...event.dataTransfer.types].some(type => type.startsWith('application/x-ds-'))) { event.preventDefault(); zone.classList.add('is-drop'); }
      });
      zone.addEventListener('dragleave', () => zone.classList.remove('is-drop'));
      zone.addEventListener('drop', event => {
        zone.classList.remove('is-drop');
        const field = event.dataTransfer.getData('application/x-ds-field');
        const moved = event.dataTransfer.getData('application/x-ds-pill');
        event.preventDefault();
        if (field) { addToShelf(key, field); return; }
        if (moved) {
          const [fromKey, fromIndex] = JSON.parse(moved);
          const target = event.target.closest('.ds-cb-pill[data-index]');
          movePill(fromKey, Number(fromIndex), key, target && target.dataset.shelf === key ? Number(target.dataset.index) : null);
        }
      });
      return h('div', {class: `ds-cb-shelf is-${key}`, title}, h('span', {class: 'ds-cb-shelf-label', text: label}), zone);
    };
    function movePill(fromKey, fromIndex, toKey, toIndex) {
      if (fromKey === 'filters' || toKey === 'filters' || fromKey === 'repeat' || toKey === 'repeat') return;
      const source = shelfItems(fromKey);
      const [item] = source.splice(fromIndex, 1);
      if (!item) return;
      const field = fromKey === 'kpi' ? kpiField(item) : item;
      if (fromKey === toKey) {
        source.splice(toIndex ?? source.length, 0, item);
        writeShelf(fromKey, source);
        return;
      }
      const target = shelfItems(toKey).filter(existing => identity(toKey === 'kpi' ? kpiField(existing) : existing) !== identity(field));
      target.splice(toIndex ?? target.length, 0, toKey === 'kpi' ? field : field);
      const changes = {};
      for (const [key, items] of [[fromKey, source], [toKey, target]]) {
        if (key === 'kpi') changes.kpi = items.join(' | ');
        else if (key === 'legend') changes.legend = items.join(', ');
        else changes[key] = items.join(' × ');
      }
      change(changes);
    }
    const shelfPill = (key, item, index, items) => {
      const isMeasure = key === 'kpi';
      const field = isMeasure ? kpiField(item) : key === 'filters' ? conditionField(item) : item;
      const aggregation = isMeasure ? kpiAggregation(item) : '';
      const pill = h('span', {class: `ds-cb-pill is-${key === 'filters' ? 'filter' : typeOf(field)}`, draggable: key === 'filters' || key === 'repeat' ? 'false' : 'true', dataset: {shelf: key, index: String(index)}, tabindex: '0'},
        h('button', {type: 'button', class: 'ds-cb-pill-label', title: key === 'filters' ? 'Change the filter' : isMeasure ? 'Aggregation and order' : 'Order',
          onclick: event => {
            if (key === 'filters') { openFilterDialog(field, item, index); return; }
            if (key === 'repeat') return;
            const actions = [];
            if (isMeasure) actions.push(...AGGREGATIONS.map(([code, label]) => [`${aggregation === code ? '✓ ' : ''}${label}`, () => {
              const next = [...items]; next[index] = code ? `${code}(${field})` : field; writeShelf('kpi', next);
            }]));
            if (index > 0) actions.push(['Move before', () => { const next = [...items]; next.splice(index - 1, 0, next.splice(index, 1)[0]); writeShelf(key, next); }]);
            if (index < items.length - 1) actions.push(['Move after', () => { const next = [...items]; next.splice(index + 1, 0, next.splice(index, 1)[0]); writeShelf(key, next); }]);
            if (actions.length) openMenu(event.currentTarget, actions);
          }},
        isMeasure && aggregation ? `${AGGREGATIONS.find(([code]) => code === aggregation)?.[1] || aggregation} of ${field}` : item),
        h('button', {type: 'button', class: 'ds-cb-pill-remove', 'aria-label': `Remove ${item}`, onclick: () => {
          if (key === 'repeat') change(item.startsWith('Rows:') ? {dynamic_rows_field: ''} : {dynamic_columns_field: ''});
          else writeShelf(key, items.filter((_value, position) => position !== index));
        }}, '×'));
      pill.addEventListener('dragstart', event => { event.dataTransfer.setData('application/x-ds-pill', JSON.stringify([key, index])); event.dataTransfer.effectAllowed = 'move'; });
      return pill;
    };

    // Filter dialog: the values of a field with their samples in the Dashboard's selection, or a numeric condition;
    // a parameter of the template can stand for the values.
    function openFilterDialog(field, existing = '', index = -1) {
      closeMenus();
      const numberField = typeOf(field) === 'number';
      const match = existing && /^(.+?)\s+(NOT\s+CONTAINS|NOT\s+IN|CONTAINS|IN|>=|<=|!=|=|>|<)\s+(.+)$/i.exec(existing);
      const operator = (match?.[2] || (numberField ? '<' : 'IN')).toUpperCase().replace(/\s+/g, ' ');
      const raw = match?.[3] || '';
      const listed = raw.replace(/^\(|\)$/g, '').split(',').map(item => item.trim()).filter(Boolean);
      const parameter = /^\(?\{([^}]+)\}\)?$/.exec(raw.trim())?.[1] || '';
      const dialog = h('div', {class: 'ds-design-popover ds-cb-filter', role: 'dialog', 'aria-label': `Filter ${field}`});
      const usable = (options.parameters || []).filter(item => (numberField ? item.type === 'number' : item.type === 'values'));
      const parameterSelect = h('select', {'aria-label': 'Use parameter'}, h('option', {value: '', text: 'No parameter: the values below'}), usable.map(item => h('option', {value: item.name, text: `{${item.name}}`, selected: item.name === parameter})));
      const commit = text => {
        const plain = [...plainFilters];
        if (index >= 0) plain.splice(index, 1, ...(text ? [text] : []));
        else if (text) plain.push(text);
        closeMenus();
        writeFilters(plain);
      };
      dialog.append(h('h4', {text: `Filter · ${field}`}));
      if (usable.length) dialog.append(h('label', {class: 'ds-cb-row'}, 'Use parameter', parameterSelect));
      if (numberField) {
        const operatorSelect = h('select', {'aria-label': 'Condition'}, ['<', '<=', '>', '>=', '=', '!='].map(item => h('option', {value: item, text: item, selected: item === operator})));
        const valueInput = h('input', {type: 'number', step: 'any', value: parameter ? '' : raw, 'aria-label': 'Value'});
        dialog.append(h('div', {class: 'ds-cb-row'}, operatorSelect, valueInput));
        dialog.append(h('div', {class: 'ds-cb-actions'},
          h('button', {type: 'button', onclick: () => commit(parameterSelect.value ? `${field} ${operatorSelect.value} {${parameterSelect.value}}` : valueInput.value === '' ? '' : `${field} ${operatorSelect.value} ${valueInput.value}`)}, 'Keep'),
          index >= 0 ? h('button', {type: 'button', onclick: () => commit('')}, 'Remove') : null));
      } else {
        const modes = [['IN', 'Include'], ['NOT IN', 'Exclude'], ['CONTAINS', 'Contains']];
        const modeSelect = h('select', {'aria-label': 'Condition'}, modes.map(([code, label]) => h('option', {value: code, text: label, selected: code === operator})));
        const listHost = h('div', {class: 'ds-cb-values'}, h('p', {class: 'ds-cb-empty', text: 'Reading the values…'}));
        const searchValues = h('input', {type: 'search', placeholder: 'Search values', 'aria-label': 'Search values'});
        const textInput = h('input', {type: 'text', value: operator === 'CONTAINS' ? listed.join(', ') : '', placeholder: 'Text the values contain', 'aria-label': 'Contains'});
        let all = [];
        const chosen = new Set(operator === 'CONTAINS' || parameter ? [] : listed);
        const paint = () => {
          const query = searchValues.value.trim().toLowerCase();
          listHost.replaceChildren(...all.filter(item => !query || String(item.value).toLowerCase().includes(query)).slice(0, 400).map(item => h('label', {class: 'ds-cb-value'},
            h('input', {type: 'checkbox', checked: chosen.has(String(item.value)), onchange: event => { if (event.target.checked) chosen.add(String(item.value)); else chosen.delete(String(item.value)); }}),
            h('span', {text: String(item.value)}), item.count !== undefined ? h('span', {class: 'ds-cb-count', text: Number(item.count).toLocaleString()}) : null)));
          if (!listHost.childElementCount) listHost.append(h('p', {class: 'ds-cb-empty', text: all.length ? 'No value matches.' : 'No values in the selection.'}));
        };
        searchValues.addEventListener('input', paint);
        const syncMode = () => { textInput.hidden = modeSelect.value !== 'CONTAINS'; listHost.hidden = searchValues.hidden = modeSelect.value === 'CONTAINS'; };
        modeSelect.addEventListener('change', syncMode);
        dialog.append(h('div', {class: 'ds-cb-row'}, modeSelect), searchValues, listHost, textInput,
          h('div', {class: 'ds-cb-actions'},
            h('button', {type: 'button', onclick: () => {
              const mode = modeSelect.value;
              if (parameterSelect.value) { commit(`${field} ${mode === 'CONTAINS' ? 'IN' : mode} ({${parameterSelect.value}})`); return; }
              if (mode === 'CONTAINS') { commit(textInput.value.trim() ? `${field} CONTAINS (${textInput.value.trim()})` : ''); return; }
              commit(chosen.size ? `${field} ${mode} (${[...chosen].join(', ')})` : '');
            }}, 'Keep'),
            index >= 0 ? h('button', {type: 'button', onclick: () => commit('')}, 'Remove') : null));
        syncMode();
        Promise.resolve(options.fieldValues?.(source, field)).then(items => { all = items || []; paint(); }).catch(() => { all = []; paint(); });
      }
      placePopover(dialog, host.querySelector('.ds-cb-shelf.is-filters') || host);
    }

    // Chart Type and the setting of the chart type chosen.
    const chartTypes = h('div', {class: 'ds-cb-types', role: 'group', 'aria-label': 'Chart Type'}, TYPES.map(item => {
      const verdict = item.need(shelfState);
      const active = item.type.toLowerCase() === String(values.chart_type || '').toLowerCase();
      return h('button', {type: 'button', class: `ds-cb-type-button${active ? ' is-active' : ''}${verdict === true ? '' : ' is-unavailable'}`,
        title: verdict === true ? item.type : `${item.type}: needs ${verdict.toLowerCase()}`, 'aria-pressed': String(active),
        onclick: () => change({chart_type: item.type})},
      h('svg', {viewBox: '0 0 24 24', 'aria-hidden': 'true'}), h('span', {text: item.type}));
    }));
    chartTypes.querySelectorAll('svg').forEach((svg, position) => {
      svg.innerHTML = `<path d="${TYPES[position].icon}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>`;
    });
    const chosenType = TYPES.find(item => item.type.toLowerCase() === String(values.chart_type || '').toLowerCase());
    const settingRow = (() => {
      if (!chosenType?.setting) return null;
      const key = identity(chosenType.setting);
      const current = settings.find(item => identity(conditionField(item)) === key);
      const value = current ? current.replace(/^.+?\s*=\s*/, '') : '';
      const input = h('input', {type: 'text', value, placeholder: chosenType.setting === 'Buckets' ? '1, 5, 10, 20' : chosenType.setting === 'Threshold' ? '1.6 or {Threshold}' : '1',
        'aria-label': chosenType.setting, onchange: event => {
          const kept = settings.filter(item => identity(conditionField(item)) !== key);
          if (event.target.value.trim()) kept.push(`${chosenType.setting} = ${event.target.value.trim()}`);
          writeFilters(plainFilters, kept);
        }});
      return h('label', {class: 'ds-cb-row ds-cb-setting'}, chosenType.setting, input);
    })();

    host.replaceChildren(...[
      options.showSource === false ? null : h('div', {class: 'ds-cb-source'},
        h('div', {class: 'ds-cb-segmented', role: 'group', 'aria-label': 'Source'}, SOURCES.map(([value, label]) => h('button', {type: 'button', class: value === source ? 'is-active' : '', 'aria-pressed': String(value === source), onclick: () => change({cdr_source: value})}, label))),
        h('div', {class: 'ds-cb-segmented', role: 'group', 'aria-label': 'NR Mode of the chart', title: 'The NR Mode of the CDRs the chart reads (Dashboard: those of the Dashboard)'}, NR_MODES.map(([value, label]) => h('button', {type: 'button', class: value === nrMode ? 'is-active' : '', 'aria-pressed': String(value === nrMode), onclick: () => {
          const kept = settings.filter(item => identity(conditionField(item)) !== 'nrmode');
          if (value) kept.push(`NR Mode IN (${value})`);
          writeFilters(plainFilters, kept);
        }}, label)))),
      h('div', {class: 'ds-cb-shelves'}, SHELVES.map(shelf)),
      h('div', {class: 'ds-cb-chart-types'}, h('span', {class: 'ds-cb-shelf-label', text: 'Chart Type'}), chartTypes, settingRow),
      h('div', {class: 'ds-cb-data'}, h('span', {class: 'ds-cb-shelf-label', text: `Fields · ${SOURCES.find(([value]) => value === source)?.[1] || source}`}), search, fieldsHost),
    ].filter(Boolean));
  }

  // Menus and popovers (the classes of the Designer's).
  function closeMenus() { document.querySelectorAll('.ds-design-popover').forEach(node => node.remove()); }
  function placePopover(popover, anchor) {
    document.body.append(popover);
    const box = anchor.getBoundingClientRect();
    const width = popover.offsetWidth, height = popover.offsetHeight;
    let left = Math.max(8, Math.min(box.left, window.innerWidth - width - 8));
    let top = box.bottom + 4;
    if (top + height > window.innerHeight - 8) top = Math.max(8, box.top - height - 4);
    Object.assign(popover.style, {left: `${left}px`, top: `${top}px`});
    popover.querySelector('input, select, button')?.focus({preventScroll: true});
  }
  function openMenu(anchor, actions) {
    closeMenus();
    const menu = h('div', {class: 'ds-design-popover ds-design-menu', role: 'menu'}, actions.map(([label, action]) => h('button', {
      type: 'button', role: 'menuitem', onclick: () => { closeMenus(); action(); },
    }, label)));
    placePopover(menu, anchor);
  }

  window.DashboardChartBuilder = {render, kpiParts, kpiField};
})();
