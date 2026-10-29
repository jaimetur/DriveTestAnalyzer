/* The chart builder of the Designer (ticket #26, phase 2): the data pane, shelves and Chart Type of a chart.

   A chart is built Tableau-like: the fields of its source (dimensions and measures told apart, grouped by the sections of
   the CDR Field Dictionary) are dragged to its shelves — Measure, Rows, Columns, Legend, Filters and Repeat by — and Chart Type
   offers the chart types the shelves can draw, the others greyed with the reason. Each change gives the values of the
   chart as its template row writes them (KPI, Rows Split, Columns Split, Legend, Filters, Chart type, Dynamic Rows/Columns
   Field), so the same engine and renderer draw it. Used by the Designer (designer.js) and by Chart Builder. */
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

  // The CDRs a chart reads and the NR Mode of those CDRs, with what each choice means.
  const SOURCES = [['CDR-Data', 'Data', 'The CDRs of the data tests'], ['CDR-Voice', 'Voice', 'The CDRs of the voice calls'],
    ['CDR-Speech', 'Speech', 'The CDRs of the speech quality tests'], ['CDR-All', 'RF All', 'The CDRs of every test (Data, Voice and Speech together), for their radio fields']];
  const NR_MODES = [['NSA', 'NSA', 'Only the CDRs of the NSA campaigns'], ['SA', 'SA', 'Only the CDRs of the SA campaigns']];
  // The settings a chart type keeps among its Filters, shown with Chart Type instead of as filters.
  const SETTINGS = ['threshold', 'buckets', 'binsize', 'classcolours', 'histogramoperator', 'nrmode'];
  const AGGREGATIONS = [['', 'As the chart type counts it'], ['AVG', 'Average'], ['MEDIAN', 'Median'], ['SUM', 'Sum'], ['COUNT', 'Count'], ['COUNTD', 'Count distinct'], ['MIN', 'Minimum'], ['MAX', 'Maximum']];
  // Chart Type: each chart type, a small picture of it (A, B and C are the colours of its series) and what its shelves
  // need.
  const A = 'var(--ds-cb-a)', B = 'var(--ds-cb-b)', C = 'var(--ds-cb-c)', G = 'var(--ds-cb-grid)';
  const curve = (colour, d) => `<path d="${d}" fill="none" stroke="${colour}" stroke-width="2.4" stroke-linecap="round"/>`;
  const bar = (colour, x, y, w, h) => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="1" fill="${colour}"/>`;
  const axes = `<path d="M5 4v26h38" fill="none" stroke="${G}" stroke-width="1.4"/>`;
  const PICTURES = {
    'CDF Line': axes + curve(A, 'M6 29C14 29 15 10 22 8S36 5 42 5') + curve(B, 'M6 29C18 29 20 16 26 13S38 9 42 9'),
    'Multi KPI CDF Lines': axes + curve(A, 'M6 29C12 29 13 9 20 7S36 5 42 5') + curve(B, 'M6 29C16 29 18 14 25 11S38 8 42 8') + curve(C, 'M6 29C20 29 24 20 30 17S40 13 42 13'),
    'Average Vertical Bars': axes + bar(A, 8, 14, 5, 16) + bar(B, 14, 9, 5, 21) + bar(A, 24, 17, 5, 13) + bar(B, 30, 11, 5, 19) + `<path d="M7 12h29" stroke="${C}" stroke-width="1.6" stroke-dasharray="3 2"/>`,
    'Median Vertical Bars': axes + bar(A, 8, 12, 5, 18) + bar(B, 14, 16, 5, 14) + bar(A, 24, 8, 5, 22) + bar(B, 30, 14, 5, 16) + `<path d="M7 18h6M14 21h5M24 15h5M30 20h5" stroke="#fff" stroke-width="1.6"/>`,
    '100% Stacked Vertical Bars': axes + [8, 17, 26, 35].map((x, i) => bar(A, x, 5, 6, 14 + i) + bar(B, x, 19 + i, 6, 6 - i) + bar(C, x, 25, 6, 5)).join(''),
    'Count Stacked Horizontal Bars': axes + bar(A, 6, 7, 18, 5) + bar(B, 24, 7, 8, 5) + bar(A, 6, 15, 26, 5) + bar(B, 32, 15, 6, 5) + bar(A, 6, 23, 12, 5) + bar(B, 18, 23, 10, 5),
    'Threshold Stacked Vertical Bars': axes + [8, 17, 26, 35].map((x, i) => bar(B, x, 6, 6, 6 + i * 2) + bar(A, x, 12 + i * 2, 6, 18 - i * 2)).join('') + `<path d="M6 16h37" stroke="${C}" stroke-width="1.6" stroke-dasharray="3 2"/>`,
    'Distribution Stacked Vertical Bars': axes + [8, 17, 26, 35].map((x, i) => bar(A, x, 5, 6, 6 + i) + bar(B, x, 11 + i, 6, 7) + bar(C, x, 18 + i, 6, 12 - i)).join(''),
    'Histogram Bars': axes + [[7, 24], [12, 17], [17, 9], [22, 6], [27, 10], [32, 18], [37, 25]].map(([x, y]) => bar(A, x, y, 4, 30 - y)).join(''),
    'Histogram Line': axes + curve(A, 'M6 29C12 28 14 8 22 7S30 26 42 28') + curve(B, 'M6 29C16 29 20 13 27 12S36 27 42 29'),
    'Scatter': axes + [[10, 24], [14, 19], [17, 22], [21, 15], [25, 17], [29, 11], [33, 13], [37, 7]].map(([x, y], i) => `<circle cx="${x}" cy="${y}" r="2" fill="${i % 2 ? B : A}"/>`).join(''),
    'Table': `<rect x="5" y="5" width="38" height="24" rx="2" fill="none" stroke="${G}" stroke-width="1.4"/>` + bar(A, 5, 5, 38, 6) + `<path d="M5 17h38M5 23h38M17 5v24M30 5v24" stroke="${G}" stroke-width="1.2"/>`,
    'Dynamic Table': `<rect x="5" y="5" width="38" height="24" rx="2" fill="none" stroke="${G}" stroke-width="1.4"/>` + bar(A, 5, 5, 38, 6) + bar(B, 18, 12, 11, 5) + bar(C, 30, 18, 12, 5) + bar(B, 6, 24, 11, 4) + `<path d="M5 17h38M5 23h38M17 5v24M30 5v24" stroke="${G}" stroke-width="1.2"/>`,
    'Map': `<path d="M5 9l11-4 15 4 12-4v20l-12 4-15-4-11 4z" fill="none" stroke="${G}" stroke-width="1.4"/>` + [[11, 17], [17, 24], [36, 20]].map(([x, y], i) => `<circle cx="${x}" cy="${y}" r="2.4" fill="${[A, B, A][i]}"/>`).join('') + `<path d="M26 24c0-3.5 4.5-6.5 4.5-10.5a4.5 4.5 0 0 0-9 0c0 4 4.5 7 4.5 10.5z" fill="${C}"/><circle cx="26" cy="13.5" r="1.7" fill="#fff"/>`,
  };
  const TYPES = [
    {type: 'CDF Line', need: s => s.numeric === 1 && s.measures === 1 || 'One numeric measure'},
    {type: 'Multi KPI CDF Lines', need: s => s.numeric >= 2 && s.numeric === s.measures || 'Two numeric measures or more'},
    {type: 'Average Vertical Bars', need: s => s.numeric >= 1 && s.splits >= 1 || 'A numeric measure and a Rows or Columns split'},
    {type: 'Median Vertical Bars', need: s => s.numeric >= 1 && s.splits >= 1 || 'A numeric measure and a Rows or Columns split'},
    {type: '100% Stacked Vertical Bars', need: s => s.text === 1 && s.measures === 1 || 'One dimension as the measure (such as Call_Status)'},
    {type: 'Count Stacked Horizontal Bars', need: s => s.measures === 1 || 'One measure'},
    {type: 'Threshold Stacked Vertical Bars', need: s => s.numeric === 1 && s.measures === 1 || 'One numeric measure', setting: 'Threshold'},
    {type: 'Distribution Stacked Vertical Bars', need: s => s.numeric === 1 && s.measures === 1 || 'One numeric measure', setting: 'Buckets'},
    {type: 'Histogram Bars', need: s => s.numeric === 1 && s.measures === 1 || 'One numeric measure', setting: 'Bin Size'},
    {type: 'Histogram Line', need: s => s.numeric === 1 && s.measures === 1 || 'One numeric measure', setting: 'Bin Size'},
    {type: 'Scatter', need: s => s.numeric === 2 && s.measures === 2 || 'Two numeric measures'},
    {type: 'Table', need: s => s.measures >= 1 || 'A measure'},
    {type: 'Dynamic Table', need: s => s.measures >= 1 || 'A measure'},
    {type: 'Map', need: s => s.geo || 'Latitude and Longitude in the source'},
  ];
  // Chart Type of the Designer: the chart types grouped by what they show.
  const TYPE_GROUPS = [
    ['Distribution', ['CDF Line', 'Multi KPI CDF Lines', 'Histogram Bars', 'Histogram Line']],
    ['Comparison', ['Average Vertical Bars', 'Median Vertical Bars', 'Scatter']],
    ['Composition', ['100% Stacked Vertical Bars', 'Count Stacked Horizontal Bars', 'Threshold Stacked Vertical Bars', 'Distribution Stacked Vertical Bars']],
    ['Tables and maps', ['Table', 'Dynamic Table', 'Map']],
  ];
  const SHELVES = [
    ['kpi', 'Measure', 'The KPI the chart measures (several for Multi KPI CDF Lines, Scatter or a Table)'],
    ['rows_split', 'Rows', 'Categories or table rows, in order (Operator × Campaign)'],
    ['columns_split', 'Columns', 'Series or table columns, in order'],
    ['legend', 'Legend', 'The fields the legend explains'],
    ['filters', 'Filters', 'Conditions on the rows of the chart'],
    ['repeat', 'Repeat by', 'One chart per value of a field, side by side in the place of this one (small multiples)'],
  ];

  // An SVG picture (SVG elements need their own namespace, which innerHTML of an <svg> gives them).
  const picture = type => {
    const holder = document.createElement('span');
    holder.className = 'ds-cb-picture';
    holder.innerHTML = `<svg viewBox="0 0 48 34" aria-hidden="true">${PICTURES[type] || ''}</svg>`;
    return holder;
  };
  const splitParts = (value, separator) => String(value || '').split(separator).map(part => part.trim()).filter(Boolean);
  const kpiParts = value => splitParts(value, /\s+vs\s+|\s*\|\s*/i);
  const kpiField = part => { const match = /^(SUM|COUNTD|COUNT|AVERAGE|AVG|MEAN|MAX|MIN|MEDIAN)\s*\(\s*(.+?)\s*\)$/i.exec(part); return match ? match[2] : part; };
  const kpiAggregation = part => (/^(SUM|COUNTD|COUNT|AVERAGE|AVG|MEAN|MAX|MIN|MEDIAN)\s*\(/i.exec(part)?.[1] || '').toUpperCase().replace(/^AVERAGE$|^MEAN$/, 'AVG');
  const conditions = value => splitParts(value, /;|\n+/);
  const conditionField = condition => (/^(.+?)\s+(NOT\s+CONTAINS|NOT\s+IN|CONTAINS|IN|>=|<=|!=|=|>|<)\s+/i.exec(condition)?.[1] || condition).trim();
  const isSetting = condition => SETTINGS.includes(identity(conditionField(condition)));

  // The fields, filters and measures of a chart, as the builder and Chart Type read them.
  function analyse(options) {
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
    return {values, source, fieldList, typeOf, change, settings, plainFilters, nrMode, writeFilters, measures, shelfState};
  }
  const chosenTypeOf = values => TYPES.find(item => item.type.toLowerCase() === String(values.chart_type || '').toLowerCase()) || null;
  const typeButton = (item, {values, shelfState, change}, props = {}) => {
    const verdict = item.need(shelfState);
    const active = item.type.toLowerCase() === String(values.chart_type || '').toLowerCase();
    return h('button', {type: 'button', class: `ds-cb-type-button${active ? ' is-active' : ''}${verdict === true ? '' : ' is-unavailable'}`,
      title: verdict === true ? item.type : `${item.type}: needs ${verdict.toLowerCase()}`, 'aria-pressed': String(active), dataset: {type: item.type},
      onclick: () => change({chart_type: item.type}), ...props},
    picture(item.type), h('span', {text: item.type}));
  };
  // The NR Mode of the CDRs a chart reads, kept as the filter NR Mode IN (SA) when the chart keeps one of its own. One button
  // per result: a PPT Design of one NR Mode reads only its CDRs (its NR Mode, the other greyed until NSA & SA is chosen in
  // PPT Filters; a chart that keeps it shows why it is empty), one of NSA & SA both or either; a template (eachPpt) is shared
  // by Designs of any NR Mode, so its chart follows the NR Mode of each one (PPT Mode) or keeps one.
  function nrModeRow({nrMode, settings, plainFilters, writeFilters}, pptNrMode = '', eachPpt = false) {
    const pptMode = String(pptNrMode || '').trim();
    const read = pptMode && !eachPpt ? pptMode.split('&').map(mode => mode.trim().toUpperCase()) : ['NSA', 'SA'];
    const single = read.length === 1;
    const choose = value => {
      const kept = settings.filter(item => identity(conditionField(item)) !== 'nrmode');
      if (value) kept.push(`NR Mode IN (${value})`);
      writeFilters(plainFilters, kept);
    };
    const choices = single
      ? NR_MODES.map(([value, text, title]) => (value === read[0] ? ['', text, `The ${text} CDRs: the PPT Design reads only those`] : [value, text, title]))
      : [['', eachPpt ? 'PPT Mode' : pptMode ? 'NSA & SA' : 'PPT', eachPpt ? 'The NR Mode of each PPT Design that follows the template' : 'The CDRs of both NR Modes, as the PPT Design reads them'], ...NR_MODES];
    const isActive = value => value === nrMode || (single && !value && nrMode === read[0]);
    return h('div', {class: 'ds-cb-source-row', title: 'The NR Mode of the CDRs the chart reads'}, h('span', {class: 'ds-cb-shelf-label', text: 'NR Mode'}),
      h('div', {class: 'ds-cb-segmented', role: 'group', 'aria-label': 'NR Mode of the CDRs the chart reads'}, choices.map(([value, text, title]) => {
        const unread = Boolean(value) && !read.includes(value);
        return h('button', {type: 'button', class: `${isActive(value) ? 'is-active' : ''}${unread ? ' is-unread' : ''}`, 'aria-pressed': String(isActive(value)),
          disabled: unread && !isActive(value), onclick: () => { if (!isActive(value)) choose(value); },
          title: unread ? `The PPT Design reads only the ${pptMode} CDRs: choose NR Mode NSA & SA in PPT Filters to show the ${value} ones` : title}, text);
      })));
  }
  // The setting of the chart type chosen (Threshold, Buckets, Bin Size), kept among the filters of the chart.
  function settingRow({values, settings, plainFilters, writeFilters}) {
    const chosenType = chosenTypeOf(values);
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
  }

  /** Render Chart Type of one chart into ``host``: its chart types grouped by what they show, the ones the shelves cannot
   *  draw greyed, the setting of the one chosen and what the one pointed at needs. Same options as render(). */
  function renderTypes(host, options) {
    const context = analyse(options);
    const hint = h('p', {class: 'ds-cb-types-hint', 'aria-live': 'polite'});
    const describe = item => {
      if (!item) { hint.replaceChildren('Drop fields on the shelves: the chart types they can draw light up.'); return; }
      const verdict = item.need(context.shelfState);
      hint.replaceChildren(h('strong', {text: item.type}), verdict === true ? ' · ready with these fields' : ` · needs ${verdict.toLowerCase()}`);
    };
    const chosen = chosenTypeOf(context.values);
    const point = item => ({onmouseenter: () => describe(item), onfocus: () => describe(item), onmouseleave: () => describe(chosen), onblur: () => describe(chosen)});
    host.replaceChildren(...[
      ...TYPE_GROUPS.map(([label, names]) => h('div', {class: 'ds-cb-type-group', role: 'group', 'aria-label': label},
        h('span', {class: 'ds-cb-type-group-label', text: label}),
        h('div', {class: 'ds-cb-types'}, names.map(name => TYPES.find(item => item.type === name)).filter(Boolean).map(item => typeButton(item, context, point(item)))))),
      settingRow(context), hint].filter(Boolean));
    describe(chosen);
  }

  /** Render the builder of one chart into ``host``.
   *  options: {values, fields: {source: [{name, type, category}]}, calculated: [names], parameters: [...],
   *            lockedFilters: [labels], onLockedFilter (opens the filters of the PPT, where those change),
   *            fieldValues: async (source, field) => [{value, count}], onChange(changes),
   *            showSource (false: the source and NR Mode are chosen elsewhere, as in Chart Builder), pptNrMode (the NR Mode
   *            of the PPT Design: NSA, SA or NSA & SA), eachPpt (a template chart: each PPT Design keeps its NR Mode),
   *            chartTypes (false: Chart Type is drawn apart, with renderTypes)} */
  function render(host, options) {
    const context = analyse(options);
    const {values, source, fieldList, typeOf, change, settings, plainFilters, writeFilters, measures, shelfState} = context;

    // Data pane
    let query = '';
    const fieldsHost = h('div', {class: 'ds-cb-fields'});
    // The groups in the order they are used most: the main fields first, the fields of no section last.
    const GROUP_ORDER = ['CDR-Main fields', 'Normalised fields', 'Network Insights', 'Non-Qualified Calls', 'DT Analyzer RCA', 'Vendor Mapping', 'Auto-calculated Fields'];
    const groupRank = group => (group === 'Other fields' ? 1000 : GROUP_ORDER.includes(group) ? GROUP_ORDER.indexOf(group) : 500);
    const paintFields = () => {
      const groups = new Map();
      for (const item of fieldList) {
        if (query && !item.name.toLowerCase().includes(query)) continue;
        const group = item.category || 'Other fields';
        if (!groups.has(group)) groups.set(group, []);
        groups.get(group).push(item);
      }
      fieldsHost.replaceChildren(...[...groups.entries()].sort(([left], [right]) => groupRank(left) - groupRank(right) || left.localeCompare(right)).map(([group, items]) => h('details', {class: 'ds-cb-group', open: Boolean(query)},
        h('summary', {}, group, h('span', {class: 'ds-cb-count', text: String(items.length)})),
        h('div', {class: 'ds-cb-group-fields'}, items.sort((left, right) => (left.type === right.type ? left.name.localeCompare(right.name) : left.type === 'text' ? -1 : 1)).map(fieldPill)))));
      if (!fieldsHost.childElementCount) fieldsHost.append(h('p', {class: 'ds-cb-empty', text: fieldList.length ? 'No field matches.' : 'The fields appear once the Design is prepared.'}));
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
      return values.repeat?.field ? [values.repeat.field] : [];
    }
    function writeShelf(key, items) {
      if (key === 'kpi') change({kpi: items.join(' | ')});
      else if (key === 'rows_split' || key === 'columns_split') change({[key]: items.join(' × ')});
      else if (key === 'legend') change({legend: items.join(', ')});
      else if (key === 'filters') writeFilters(items);
    }
    function addToShelf(key, field) {
      if (key === 'filters') { openFilterDialog(field); return; }
      if (key === 'repeat') { change({repeat: {field}}); return; }
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
        key === 'filters' ? (options.lockedFilters || []).map(text => (options.onLockedFilter
          ? h('button', {type: 'button', class: 'ds-cb-pill is-locked is-editable', title: 'A filter of the PPT: it applies to every chart. Click to change it in PPT Filters', onclick: options.onLockedFilter}, text)
          : h('span', {class: 'ds-cb-pill is-locked', title: 'A filter of the PPT: it applies to every chart', text}))) : null,
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
          if (key === 'repeat') change({repeat: null});
          else writeShelf(key, items.filter((_value, position) => position !== index));
        }}, '×'));
      pill.addEventListener('dragstart', event => { event.dataTransfer.setData('application/x-ds-pill', JSON.stringify([key, index])); event.dataTransfer.effectAllowed = 'move'; });
      return pill;
    };

    // Filter dialog: the values of a field with their samples in the Design's selection, or a numeric condition;
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
    const chartTypes = options.chartTypes === false ? null : h('div', {class: 'ds-cb-types', role: 'group', 'aria-label': 'Chart Type'}, TYPES.map(item => typeButton(item, context)));

    host.replaceChildren(...[
      options.showSource === false ? null : h('div', {class: 'ds-cb-source'},
        h('div', {class: 'ds-cb-source-row', title: 'The CDRs the chart reads'}, h('span', {class: 'ds-cb-shelf-label', text: 'Source'}),
          h('div', {class: 'ds-cb-segmented', role: 'group', 'aria-label': 'Source: the CDRs the chart reads'}, SOURCES.map(([value, label, title]) => h('button', {type: 'button', class: value === source ? 'is-active' : '', 'aria-pressed': String(value === source), title, onclick: () => change({cdr_source: value})}, label)))),
        nrModeRow(context, options.pptNrMode, options.eachPpt)),
      h('div', {class: 'ds-cb-shelves'}, SHELVES.filter(([key]) => key !== 'repeat' || options.showSource !== false).map(shelf)),
      chartTypes ? h('div', {class: 'ds-cb-chart-types'}, h('span', {class: 'ds-cb-shelf-label', text: 'Chart Type'}), chartTypes, settingRow(context)) : null,
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

  window.ChartShelves = {render, renderTypes, picture, kpiParts, kpiField};
})();
