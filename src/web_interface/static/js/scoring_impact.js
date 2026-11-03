// Methodology Impact of Scoring & GAP Analysis: two methodologies face to face, A against B, with the scope of the open Saved
// Filter. The same tests are scored with both in the background (see scoring_impact.py), so every figure comes from the methodology
// and none from the network.
(() => {
  const POLL_MS = 1500;
  const STORAGE_KEY = 'scoring-methodology-impact';
  const PAGE_ROWS = 12;
  // Differences below this are shown as no change.
  const NO_CHANGE = .005;
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const CAUSES = {weights: 'Points moved between KPIs', rules: 'Other thresholds, formula or filters', new: 'New KPIs', removed: 'Removed KPIs'};
  const options = new Map();
  const impacts = new Map();
  // The comparisons asked to the server since the page opened: drawing them again (another environment, the operators…) does not.
  const validated = new Set();
  const mapData = new Map();
  const geometry = new Map();
  const expanded = new Set();
  const choices = {field: null, measure: 'national', table: null, changeKind: null};
  // The operators enabled in the panels drawn, which the documents show.
  let chosenOperators = null;
  // The width the charts are drawn at, that of their card: their text keeps its size on every screen.
  let chartWidth = 860;
  // The colours of the theme of the panels drawn.
  let palette = {};
  let renderToken = 0;
  let pollTimer = null;

  const number = (value, digits = 1) => (Number.isFinite(Number(value)) && value !== null && value !== undefined
    ? Number(value).toLocaleString('en-US', {minimumFractionDigits: digits, maximumFractionDigits: digits}) : 'N/A');
  const signed = (value, digits = 2) => {
    if (!Number.isFinite(Number(value)) || value === null || value === undefined) return 'N/A';
    const text = number(Math.abs(value), digits);
    return Math.abs(value) < 10 ** -digits / 2 ? text : `${value > 0 ? '+' : '−'}${text}`;
  };
  const ordinal = (value) => {
    const rest = value % 100;
    return `${value}${rest >= 11 && rest <= 13 ? 'th' : ({1: 'st', 2: 'nd', 3: 'rd'}[value % 10] || 'th')}`;
  };
  const sum = values => values.reduce((total, value) => total + (Number(value) || 0), 0);

  function element(tag, className = '', ...children) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    node.append(...children.filter(child => child !== null && child !== undefined && child !== false).map(child => (child instanceof Node ? child : String(child))));
    return node;
  }

  function svgElement(tag, attributes = {}, text = null) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const [key, value] of Object.entries(attributes)) if (value !== null && value !== undefined) node.setAttribute(key, value);
    if (text !== null) node.textContent = text;
    return node;
  }

  function withTitle(node, text) {
    if (text) node.append(svgElement('title', {}, text));
    return node;
  }

  function readStored() {
    try {
      const stored = JSON.parse(window.sessionStorage.getItem(STORAGE_KEY) || '{}');
      return stored && typeof stored === 'object' ? stored : {};
    } catch (_error) {
      return {};
    }
  }

  function selectionOf(filterId, offered) {
    const stored = readStored()[filterId];
    const selection = {...offered.defaults, ...(stored && typeof stored === 'object' ? stored : {})};
    if (!offered.nr_modes.includes(selection.nr_mode)) selection.nr_mode = offered.defaults.nr_mode;
    // (A campaign or methodology that is no longer there takes the default of its NR Mode.)
    const defaults = offered.by_nr_mode[selection.nr_mode];
    const campaigns = (offered.campaigns[selection.nr_mode] || []).map(entry => entry.value);
    const methodologies = offered.methodologies.map(item => item.id);
    for (const [key, values] of [['campaign_a', campaigns], ['campaign_b', campaigns], ['campaign', campaigns], ['methodology_a', methodologies], ['methodology_b', methodologies]]) {
      if (!values.includes(selection[key])) selection[key] = defaults[key];
    }
    return selection;
  }

  function rememberSelection(filterId, selection) {
    try {
      window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify({...readStored(), [filterId]: selection}));
    } catch (_error) { /* Only a convenience: the selection is the default one after a reload. */ }
  }

  const queryOf = (selection, extra = {}) => new URLSearchParams({...selection, ...extra}).toString();

  // ---- Colours ---------------------------------------------------------------------------------------------------------
  function hexChannels(value) {
    const text = String(value || '').trim().replace('#', '');
    const full = text.length === 3 ? [...text].map(item => item + item).join('') : text;
    return /^[0-9a-f]{6}$/i.test(full) ? [0, 2, 4].map(index => parseInt(full.slice(index, index + 2), 16)) : null;
  }
  const mix = (first, second, share) => {
    const [from, to] = [hexChannels(first) || [255, 255, 255], hexChannels(second) || [0, 0, 0]];
    return `rgb(${from.map((value, index) => Math.round(value + (to[index] - value) * share)).join(',')})`;
  };
  const lightness = channels => (.2126 * channels[0] + .7152 * channels[1] + .0722 * channels[2]) / 255;

  function paletteOf(ctx, pane) {
    const style = getComputedStyle(pane.closest('[data-scoring-workspace]') || pane);
    const surface = ctx.theme?.surface || '#FFFFFF';
    const ink = ctx.theme?.ink || '#1F2A37';
    return {surface, ink, a: '#94a3b8', b: style.getPropertyValue('--st-title').trim() || '#a21caf',
      gain: style.getPropertyValue('--st-gain').trim() || '#4ca65a', loss: style.getPropertyValue('--st-loss').trim() || '#e8414f',
      zero: mix(surface, ink, .07), grid: mix(surface, ink, .18), muted: mix(surface, ink, .55), dark: lightness(hexChannels(surface) || [255, 255, 255]) < .4};
  }

  // A value from the loss colour to the gain colour; a root scale so the small differences show beside the large ones.
  function heatColor(value, scale) {
    if (value === null || value === undefined || !Number.isFinite(Number(value))) return palette.zero;
    if (!scale || Math.abs(value) < NO_CHANGE) return palette.zero;
    const share = Math.min(1, Math.sqrt(Math.abs(value) / scale));
    return mix(palette.surface, value > 0 ? palette.gain : palette.loss, .14 + share * .86);
  }

  function inkOn(color) {
    const channels = String(color).match(/\d+/g)?.slice(0, 3).map(Number) || hexChannels(color) || [255, 255, 255];
    const parsed = String(color).startsWith('rgb') ? channels : (hexChannels(color) || channels);
    return lightness(parsed) > .58 ? '#17232d' : '#ffffff';
  }

  // The colour of an operator, readable on the theme (a black operator on a dark theme takes its ink).
  function operatorColor(item, ctx) {
    const color = ctx.safeHexColor(item?.color) || palette.ink;
    const channels = hexChannels(color);
    return palette.dark && channels && lightness(channels) < .2 ? palette.ink : color;
  }

  // ---- Cells and tables --------------------------------------------------------------------------------------------------
  function toneOf(delta, inverse = false) {
    if (delta === null || delta === undefined || Math.abs(delta) < NO_CHANGE) return 'flat';
    return (delta > 0) !== inverse ? 'gain' : 'loss';
  }

  // The letter of each methodology, the same one in every panel.
  const sideBadge = side => element('span', `scoring-impact-badge is-${side}`, side.toUpperCase());

  // A cell of the impact: its difference on the colour of the difference, and the value with each methodology.
  function shiftCell(cell, scale, {inverse = false, title = '', flip = false, digits = 1} = {}) {
    const box = element('td', 'scoring-impact-cell');
    if (!cell || (cell.before === null && cell.after === null)) {
      box.classList.add('is-empty');
      box.textContent = '—';
      return box;
    }
    const tone = toneOf(cell.delta, inverse);
    box.dataset.tone = tone;
    if (tone !== 'flat') {
      const share = Math.min(1, Math.sqrt(Math.abs(cell.delta) / Math.max(Number(scale) || 0, NO_CHANGE)));
      const color = mix(palette.surface, tone === 'gain' ? palette.gain : palette.loss, .12 + share * .58);
      // (Over the colours each theme gives the cells of a table.)
      box.style.setProperty('background', color, 'important');
      box.style.setProperty('color', inkOn(color), 'important');
    }
    const head = element('span', 'scoring-impact-head', element('b', '', signed(cell.delta)));
    if (flip) head.append(element('em', 'scoring-impact-flag', 'Changes side'));
    box.append(head, element('small', '', `${cell.before === null ? 'none' : number(cell.before, digits)} → ${cell.after === null ? 'none' : number(cell.after, digits)}`));
    if (title) box.title = title;
    return box;
  }

  function operatorHeader(item, safeHexColor) {
    const cell = element('th', 'scoring-impact-operator', `${item.label}${item.is_reference ? ' (reference)' : ''}`);
    const color = safeHexColor(item.color);
    if (color) cell.style.setProperty('--operator-color', color);
    return cell;
  }

  function kpiLabel(row, extra = null) {
    const type = String(row.kpi_type || '').trim().toLocaleLowerCase();
    const name = element('span', 'scoring-kpi-name', row.kpi || row.code);
    const line = element('span', 'scoring-kpi-name-row');
    if (type === 'reliable' || type === 'diff') {
      const badge = element('span', 'scoring-kpi-badge', type === 'reliable' ? 'R' : 'D');
      badge.dataset.kpiType = type;
      badge.title = `${row.kpi_type} KPI`;
      line.append(badge);
    }
    line.append(name);
    return element('div', 'scoring-impact-label', line, extra);
  }

  function kindChips(kinds, labels) {
    const box = element('span', 'scoring-impact-chips');
    for (const kind of kinds || []) {
      const chip = element('span', 'scoring-impact-chip', labels[kind] || kind);
      chip.dataset.kind = kind;
      box.append(chip);
    }
    return box;
  }

  // Rows of a label and a cell per operator, which share the scale of their table.
  function matrix(firstHeader, operators, rows, ctx, {inverse = false, total = null, extraHeaders = [], digits = 1} = {}) {
    const table = element('table', 'scoring-insight-table scoring-impact-matrix');
    const head = table.createTHead().insertRow();
    head.append(element('th', '', firstHeader), ...operators.map(item => operatorHeader(item, ctx.safeHexColor)),
      ...extraHeaders.map(text => element('th', '', text)));
    const body = table.createTBody();
    const cellsOf = row => operators.map(item => row.cells?.[item.operator]);
    const scale = Math.max(0, ...rows.flatMap(row => cellsOf(row).map(cell => Math.abs(Number(cell?.delta) || 0))));
    const addRow = (section, row, rowScale) => {
      const line = section.insertRow();
      const first = line.insertCell();
      first.className = 'scoring-impact-row-label';
      first.append(row.label);
      for (const item of operators) {
        const cell = row.cells?.[item.operator];
        line.append(shiftCell(cell, rowScale, {inverse, flip: Boolean(cell?.flip), digits, title: row.titleOf ? row.titleOf(item, cell) : ''}));
      }
      for (const extra of row.extra || []) line.insertCell().append(extra);
    };
    for (const row of rows) addRow(body, row, scale);
    if (total) {
      const footer = table.createTFoot();
      addRow(footer, total, Math.max(0, ...cellsOf(total).map(cell => Math.abs(Number(cell?.delta) || 0))));
    }
    return element('div', 'scoring-insight-table-wrap', table);
  }

  function pagedRows(key, rows, drawRows) {
    const open = expanded.has(key);
    const shown = open || rows.length <= PAGE_ROWS ? rows : rows.slice(0, PAGE_ROWS);
    const box = element('div', 'scoring-impact-paged', drawRows(shown));
    if (rows.length > PAGE_ROWS) {
      const toggle = element('button', 'scoring-impact-more', open ? `Show the first ${PAGE_ROWS}` : `Show all ${rows.length}`);
      toggle.type = 'button';
      toggle.addEventListener('click', () => {
        if (open) expanded.delete(key);
        else expanded.add(key);
        box.replaceWith(pagedRows(key, rows, drawRows));
      });
      box.append(toggle);
    }
    return box;
  }

  const note = text => element('p', 'scoring-insight-note', text);
  const subtitle = text => element('h5', 'scoring-impact-subtitle', text);

  function selectField(label, values, value, onChange) {
    const wrapper = element('label', 'scoring-environment-filter scoring-insight-select', label);
    const select = element('select');
    for (const [key, text, disabled] of values) {
      const option = element('option', '', text);
      option.value = key;
      if (disabled) option.disabled = true;
      select.append(option);
    }
    select.value = value;
    select.addEventListener('change', () => onChange(select.value));
    wrapper.append(select);
    return wrapper;
  }

  function panel(body, key, label, title, ctx) {
    const section = ctx.insightSection(body, title, `scoring-impact-${key}-card`, false);
    section.dataset.impactPanel = label;
    return section;
  }

  // ---- Charts (each fits its card: it scales with its width) ---------------------------------------------------------------
  // Bars either side of zero, from the largest: a label, the bar and its value.
  function divergingChart(items, {labelWidth: wantedLabel = 240, valueWidth = 66, rowHeight = 26, digits = 2, inverse = false, width = chartWidth} = {}) {
    const height = Math.max(rowHeight * items.length + 8, 30);
    const svg = svgElement('svg', {viewBox: `0 0 ${width} ${height}`, class: 'scoring-impact-chart', role: 'img'});
    const labelWidth = Math.min(wantedLabel, width * .38);
    const room = Math.max((width - labelWidth - valueWidth * 2) / 2, 10);
    const middle = labelWidth + valueWidth + room;
    const scale = Math.max(NO_CHANGE, ...items.map(item => Math.abs(Number(item.value) || 0)));
    svg.append(svgElement('line', {x1: middle, x2: middle, y1: 0, y2: height, stroke: palette.grid}));
    const roomChars = Math.max(12, Math.floor(labelWidth / 7));
    items.forEach((item, index) => {
      const y = index * rowHeight + 4;
      const value = Number(item.value) || 0;
      const reach = Math.abs(value) / scale * room;
      const label = withTitle(svgElement('text', {x: labelWidth - 8, y: y + rowHeight / 2 + (item.detail ? -2 : 2), 'text-anchor': 'end', fill: item.color || 'currentColor', 'font-size': 12, 'font-weight': item.color ? 700 : 500},
        String(item.label).length > roomChars ? `${String(item.label).slice(0, roomChars - 1)}…` : item.label), String(item.label));
      if (item.detail) svg.append(svgElement('text', {x: labelWidth - 8, y: y + rowHeight / 2 + 10, 'text-anchor': 'end', fill: palette.muted, 'font-size': 9.5}, item.detail));
      const tone = toneOf(value, inverse);
      const bar = withTitle(svgElement('rect', {x: value < 0 ? middle - reach : middle, y: y + 3, width: Math.max(reach, tone === 'flat' ? 0 : 1), height: rowHeight - 9, rx: 3,
        fill: tone === 'gain' ? palette.gain : palette.loss}), item.title || `${item.label}: ${signed(value, digits)}`);
      const text = svgElement('text', {x: value < 0 ? middle - reach - 5 : middle + reach + 5, y: y + rowHeight / 2 + 2, 'text-anchor': value < 0 ? 'end' : 'start', 'font-size': 12, 'font-weight': 700,
        fill: tone === 'flat' ? palette.muted : tone === 'gain' ? palette.gain : palette.loss}, signed(value, digits));
      svg.append(label, bar, text);
    });
    return svg;
  }

  // Per row, its parts stacked either side of zero, each in its colour.
  function stackedDiverging(rows, partsMeta, {labelWidth: wantedLabel = 150, width = chartWidth, rowHeight = 34} = {}) {
    const labelWidth = Math.min(wantedLabel, width * .25);
    const height = rowHeight * rows.length + 8;
    const svg = svgElement('svg', {viewBox: `0 0 ${width} ${height}`, class: 'scoring-impact-chart', role: 'img'});
    const room = (width - labelWidth - 70) / 2;
    const middle = labelWidth + room;
    const extent = Math.max(NO_CHANGE, ...rows.map(row => Math.max(sum(Object.values(row.parts).filter(value => value > 0)), -sum(Object.values(row.parts).filter(value => value < 0)))));
    svg.append(svgElement('line', {x1: middle, x2: middle, y1: 0, y2: height, stroke: palette.grid}));
    rows.forEach((row, index) => {
      const y = index * rowHeight + 4;
      svg.append(svgElement('text', {x: labelWidth - 10, y: y + rowHeight / 2 + 1, 'text-anchor': 'end', 'font-size': 13, 'font-weight': 700, fill: row.color || 'currentColor'}, row.label));
      let right = middle;
      let leftEdge = middle;
      for (const part of partsMeta) {
        const value = Number(row.parts[part.key]) || 0;
        if (Math.abs(value) < NO_CHANGE) continue;
        const reach = Math.abs(value) / extent * room;
        const x = value > 0 ? right : leftEdge - reach;
        svg.append(withTitle(svgElement('rect', {x, y: y + 4, width: Math.max(reach, 1), height: rowHeight - 12, fill: part.color}), `${row.label} · ${part.label}: ${signed(value)}`));
        if (reach > 44) svg.append(svgElement('text', {x: x + reach / 2, y: y + rowHeight / 2 + 1, 'text-anchor': 'middle', 'font-size': 10.5, 'font-weight': 700, fill: inkOn(part.color)}, signed(value, Math.abs(value) >= 10 ? 1 : 2)));
        if (value > 0) right += reach; else leftEdge -= reach;
      }
      const tone = toneOf(row.total);
      svg.append(svgElement('text', {x: width - 4, y: y + rowHeight / 2 + 2, 'text-anchor': 'end', 'font-size': 13, 'font-weight': 800,
        fill: tone === 'flat' ? palette.muted : tone === 'gain' ? palette.gain : palette.loss}, signed(row.total)));
    });
    return svg;
  }

  // The ranking with each methodology, each operator joined to itself: a level line keeps its position.
  function rankingChart(combined, operators, doc, ctx, {width = Math.min(chartWidth, 760)} = {}) {
    const placed = side => operators.filter(item => combined.operators[item.operator]?.[side] !== null && combined.operators[item.operator]?.[side] !== undefined)
      .sort((first, second) => combined.operators[second.operator][side] - combined.operators[first.operator][side]);
    const before = placed('before');
    const after = placed('after');
    const rowHeight = 36;
    const top = 30;
    const height = top + Math.max(before.length, after.length) * rowHeight + 2;
    const room = Math.min(210, Math.max(118, width * .3));
    const svg = svgElement('svg', {viewBox: `0 0 ${width} ${height}`, class: 'scoring-impact-chart', role: 'img'});
    const heads = [[room - 12, 'end', 'A', doc.before.profile_name, palette.a], [width - room + 12, 'start', 'B', doc.after.profile_name, palette.b]];
    for (const [x, anchor, letter, name, fill] of heads) {
      const clipped = name.length > room / 7 ? `${name.slice(0, Math.floor(room / 7) - 1)}…` : name;
      svg.append(withTitle(svgElement('text', {x, y: 14, 'text-anchor': anchor, 'font-size': 12, 'font-weight': 800, fill}, `${letter} · ${clipped}`), name));
    }
    const yOf = index => top + index * rowHeight + rowHeight / 2;
    for (const item of operators) {
      const first = before.indexOf(item);
      const second = after.indexOf(item);
      if (first < 0 || second < 0) continue;
      const color = operatorColor(item, ctx);
      svg.append(svgElement('line', {x1: room, y1: yOf(first), x2: width - room, y2: yOf(second), stroke: color, 'stroke-width': first === second ? 2.5 : 4, 'stroke-opacity': first === second ? .45 : 1, 'stroke-linecap': 'round'}));
      for (const [x, y] of [[room, yOf(first)], [width - room, yOf(second)]]) svg.append(svgElement('circle', {cx: x, cy: y, r: 5, fill: color, stroke: palette.surface, 'stroke-width': 1.5}));
    }
    const line = (list, side, anchor, x) => list.forEach((item, index) => {
      const value = number(combined.operators[item.operator][side], 1);
      const label = item.label.length > room / 11 ? `${item.label.slice(0, Math.floor(room / 11) - 1)}…` : item.label;
      const text = svgElement('text', {x, y: yOf(index) + 4, 'text-anchor': anchor, 'font-size': 13, fill: 'currentColor'});
      const name = svgElement('tspan', {'font-weight': 800, fill: operatorColor(item, ctx)}, label);
      const figure = svgElement('tspan', {'font-weight': 500, fill: palette.muted}, value);
      text.append(svgElement('tspan', {'font-weight': 800}, `${index + 1}. `), name, svgElement('tspan', {}, '  '), figure);
      svg.append(withTitle(text, `${item.label}: ${value} points`));
    });
    line(before, 'before', 'end', room - 12);
    line(after, 'after', 'start', width - room + 12);
    svg.style.maxWidth = `${width}px`;
    svg.style.margin = '0 auto';
    return svg;
  }

  // The GAP with each methodology, as two bars from the reference.
  function gapChart(items, {width = chartWidth} = {}) {
    const rowHeight = 46;
    const height = items.length * rowHeight + 6;
    const labelWidth = Math.min(130, width * .24);
    const totalWidth = Math.min(150, width * .26);
    const svg = svgElement('svg', {viewBox: `0 0 ${width} ${height}`, class: 'scoring-impact-chart', role: 'img'});
    const extent = Math.max(NO_CHANGE, ...items.flatMap(item => [Math.abs(item.before || 0), Math.abs(item.after || 0)]));
    const anySide = items.some(item => (item.before || 0) > 0 || (item.after || 0) > 0) && items.some(item => (item.before || 0) < 0 || (item.after || 0) < 0);
    const valueRoom = 46;
    const span = width - labelWidth - totalWidth - valueRoom * 2;
    const allNegative = !items.some(item => (item.before || 0) > 0 || (item.after || 0) > 0);
    const middle = anySide ? labelWidth + valueRoom + span / 2 : allNegative ? labelWidth + valueRoom + span : labelWidth + valueRoom;
    const room = anySide ? span / 2 : span;
    svg.append(svgElement('line', {x1: middle, x2: middle, y1: 0, y2: height, stroke: palette.grid, 'stroke-width': 1.5}));
    items.forEach((item, index) => {
      const y = index * rowHeight + 3;
      svg.append(svgElement('text', {x: labelWidth - 8, y: y + rowHeight / 2 + 2, 'text-anchor': 'end', 'font-size': 13, 'font-weight': 800, fill: item.color}, item.label));
      [['before', palette.a, 'A', 5], ['after', palette.b, 'B', 22]].forEach(([side, fill, letter, offset]) => {
        const value = item[side];
        if (value === null || value === undefined) return;
        const reach = Math.abs(value) / extent * room;
        svg.append(withTitle(svgElement('rect', {x: value < 0 ? middle - reach : middle, y: y + offset, width: Math.max(reach, 1), height: 14, rx: 2, fill}), `${item.label} with ${letter}: ${signed(value, 1)} points against the reference`));
        svg.append(svgElement('text', {x: value < 0 ? middle - reach - 5 : middle + reach + 5, y: y + offset + 11, 'text-anchor': value < 0 ? 'end' : 'start', 'font-size': 11, 'font-weight': 600, fill: palette.muted}, signed(value, 1)));
      });
      const tone = toneOf(item.delta);
      svg.append(svgElement('text', {x: width - 4, y: y + rowHeight / 2 + (item.flip ? -3 : 3), 'text-anchor': 'end', 'font-size': 14, 'font-weight': 800,
        fill: tone === 'flat' ? palette.muted : tone === 'gain' ? palette.gain : palette.loss}, signed(item.delta)));
      if (item.flip) svg.append(svgElement('text', {x: width - 4, y: y + rowHeight / 2 + 12, 'text-anchor': 'end', 'font-size': 10.5, 'font-weight': 800, fill: palette.loss}, 'Changes side'));
    });
    return svg;
  }

  // A grid of small charts of an operator each: how many fit a row and the width each one is drawn at.
  function smallMultiples(count) {
    const columns = chartWidth < 700 ? 1 : count === 2 || count === 4 ? 2 : Math.min(3, Math.max(count, 1));
    const grid = element('div', 'scoring-impact-small-multiples');
    grid.style.gridTemplateColumns = `repeat(${columns}, minmax(0, 1fr))`;
    return {grid, width: Math.max(260, Math.floor((chartWidth - (columns - 1) * 12) / columns) - 26)};
  }

  function legend(items) {
    const box = element('div', 'scoring-location-legend');
    for (const item of items) {
      const swatch = element('i');
      swatch.style.background = item.color;
      box.append(element('span', '', swatch, item.label));
    }
    return box;
  }

  const sidesLegend = doc => element('div', 'scoring-impact-sides-legend', element('span', '', sideBadge('a'), doc.before.profile_name), element('span', '', sideBadge('b'), doc.after.profile_name));

  // ---- Panels ---------------------------------------------------------------------------------------------------------
  function headPanel(body, doc, part, scoring, ctx, control) {
    const section = panel(body, 'head', '', `Methodology Impact${scoring === 'most_reliable' ? ' — Most Reliable Network' : ''}`, ctx);
    delete section.dataset.impactPanel;
    const method = (side, summary, source) => element('div', `scoring-impact-method is-${side}`, sideBadge(side),
      element('div', '', element('strong', '', summary.profile_name), source ? element('small', '', `Methodology of ${source}`) : null));
    section.append(element('div', 'scoring-impact-versus', method('a', doc.before, doc.methodology_of?.before), element('span', 'scoring-impact-vs', 'vs'), method('b', doc.after, doc.methodology_of?.after)));
    const reference = part.operators.find(item => item.is_reference)?.label || part.reference;
    section.append(element('p', 'scoring-impact-context', `The same tests of ${doc.after.campaign_label} (${doc.nr_mode}) scored with both, so every difference comes from the methodology. GAP reference: ${reference}.`));
    if (scoring !== ctx.scoring) section.append(note('The Most Reliable scoring is not compared: one of the methodologies does not have it. This is the Best Network scoring.'));
    const {headline, facts = []} = part.conclusions || {};
    if (headline) section.append(element('p', 'scoring-impact-headline', headline));
    if (facts.length) {
      const grid = element('div', 'scoring-impact-facts');
      for (const fact of facts) {
        const card = element('article', 'scoring-impact-fact', element('span', '', fact.title), element('strong', '', fact.text));
        card.dataset.tone = fact.tone;
        grid.append(card);
      }
      section.append(grid);
    }
    for (const text of doc.notes) section.append(note(text));
    section.append(ctx.insightControls(control));
    return section;
  }

  // The points of each category with each methodology, face to face.
  function butterfly(rows, doc, labelOf) {
    const peak = Math.max(NO_CHANGE, ...rows.flatMap(row => [Number(row.before) || 0, Number(row.after) || 0]));
    const box = element('div', 'scoring-impact-butterfly');
    box.append(element('div', 'scoring-impact-butterfly-head', element('span', '', sideBadge('a'), doc.before.profile_name), element('span'), element('span', '', sideBadge('b'), doc.after.profile_name), element('span')));
    for (const row of rows) {
      const bar = (side) => {
        const fill = element('i');
        fill.style.width = `${(Number(row[side]) || 0) / peak * 100}%`;
        return element('span', `scoring-impact-butterfly-bar is-${side === 'before' ? 'a' : 'b'}`, fill, element('b', '', number(row[side], 1)));
      };
      const tone = Math.abs(row.delta) >= NO_CHANGE ? (row.delta > 0 ? 'gain' : 'loss') : 'flat';
      const line = element('div', 'scoring-impact-butterfly-row', bar('before'), element('strong', '', labelOf(row)), bar('after'),
        element('span', `scoring-impact-pill is-${tone}`, tone === 'flat' ? 'Same' : signed(row.delta, 1)));
      line.dataset.moved = String(tone !== 'flat');
      box.append(line);
    }
    return box;
  }

  function sideValue(row, side, peak, doc) {
    const value = row[side === 'a' ? 'before' : 'after'];
    const absent = (side === 'a' && row.status === 'added') || (side === 'b' && row.status === 'removed');
    if (absent) return element('div', `scoring-impact-diff-side is-${side} is-absent`, sideBadge(side), element('span', '', `Not in ${side === 'a' ? doc.before.profile_name : doc.after.profile_name}`));
    const fill = element('i');
    fill.style.width = `${(Number(value) || 0) / peak * 100}%`;
    return element('div', `scoring-impact-diff-side is-${side}`, sideBadge(side), element('span', 'scoring-impact-diff-bar', fill), element('b', '', `${number(value, 1)} pts`));
  }

  // A row per value that changes: what it is, its value in A and in B. The environments with the same change go together.
  function diffLines(details) {
    const groups = new Map();
    for (const item of details || []) {
      const key = JSON.stringify([item.label, item.before, item.after]);
      if (!groups.has(key)) groups.set(key, {...item, environments: []});
      if (item.environment) groups.get(key).environments.push(item.environment);
    }
    const box = element('div', 'scoring-impact-diff-lines');
    for (const item of groups.values()) {
      box.append(element('div', 'scoring-impact-diff-line', element('span', 'scoring-impact-diff-what', element('strong', '', item.label), item.environments.length ? element('small', '', item.environments.join(', ')) : null),
        element('code', 'is-a', item.before), element('code', 'is-b', item.after)));
    }
    return box;
  }

  function changesList(box, doc, changes) {
    const kind = choices.changeKind;
    const kpis = changes.kpis.filter(row => !kind || row.kinds.includes(kind));
    const peak = Math.max(NO_CHANGE, ...changes.kpis.flatMap(row => [Number(row.before) || 0, Number(row.after) || 0]));
    const categories = new Map();
    for (const row of kpis) {
      const name = row.category || 'Other';
      if (!categories.has(name)) categories.set(name, []);
      categories.get(name).push(row);
    }
    box.replaceChildren();
    for (const [name, rows] of categories) {
      const group = element('section', 'scoring-impact-diff-group', element('header', '', element('h5', '', name), element('small', '', `${rows.length} KPI${rows.length === 1 ? '' : 's'}`)));
      for (const row of rows) {
        const tone = toneOf(row.delta);
        const line = element('article', 'scoring-impact-diff-row',
          element('div', 'scoring-impact-diff-kpi', kpiLabel(row), kindChips(row.kinds, changes.kinds)),
          sideValue(row, 'a', peak, doc), sideValue(row, 'b', peak, doc),
          element('span', `scoring-impact-pill is-${tone}`, tone === 'flat' ? 'Same pts' : `${signed(row.delta, 1)} pts`));
        line.dataset.status = row.status;
        const details = (row.details || []).filter(item => !(row.status !== 'changed' && item.kind === 'points'));
        if (details.length) line.append(diffLines(details));
        group.append(line);
      }
      box.append(group);
    }
    if (!kpis.length) box.append(note('No KPI has this change.'));
  }

  function changesPanel(body, doc, part, ctx) {
    const changes = part.changes;
    const section = panel(body, 'changes', 'What changed', 'What changed in the methodology', ctx);
    if (changes.same) {
      section.append(note('Both methodologies are the same: nothing that scores a test changes between them.'));
      return;
    }
    const listBox = element('div', 'scoring-impact-diff');
    const tiles = element('div', 'scoring-impact-tiles');
    const kinds = [['added', 'New KPIs'], ['removed', 'Removed KPIs'], ['points', 'Points changed'], ['thresholds', 'Thresholds changed'],
      ['calculation', 'Formula or filters changed'], ['scoring', 'Score mapping changed'], ['definition', 'Definition changed']].filter(([kind]) => changes.counts[kind] > 0);
    if (!kinds.some(([kind]) => kind === choices.changeKind)) choices.changeKind = null;
    const buttons = kinds.map(([kind, label]) => {
      const tile = element('button', 'scoring-impact-tile', element('strong', '', number(changes.counts[kind], 0)), element('span', '', label));
      tile.type = 'button';
      tile.dataset.kind = kind;
      tile.setAttribute('aria-pressed', String(choices.changeKind === kind));
      tile.title = 'Show only these KPIs';
      tile.addEventListener('click', () => {
        choices.changeKind = choices.changeKind === kind ? null : kind;
        buttons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.kind === choices.changeKind)));
        changesList(listBox, doc, changes);
      });
      return tile;
    });
    const same = element('div', 'scoring-impact-tile', element('strong', '', number(changes.counts.unchanged || 0, 0)), element('span', '', 'Unchanged KPIs'));
    same.dataset.kind = 'unchanged';
    tiles.append(...buttons, same);
    section.append(tiles);
    const categories = changes.categories.filter(row => row.before > 0 || row.after > 0);
    if (categories.some(row => Math.abs(row.delta) >= NO_CHANGE)) section.append(subtitle('Points per category'), butterfly(categories, doc, row => row.category));
    else section.append(note('Every category keeps its points: a KPI that gives or takes points shares them within its category.'));
    if (changes.environments.some(row => Math.abs(row.delta) >= NO_CHANGE)) section.append(subtitle('Points per environment'), butterfly(changes.environments, doc, row => row.label));
    if (changes.kpis.length) {
      section.append(subtitle(`KPI by KPI: the ${changes.kpis.length} that change`), listBox);
      changesList(listBox, doc, changes);
    }
    if (changes.settings.length) {
      const settings = diffLines(changes.settings);
      settings.classList.add('scoring-impact-general');
      section.append(subtitle('General settings'), settings);
    }
  }

  function scoringPanel(body, doc, part, chosen, environment, ctx) {
    const section = panel(body, 'scoring', 'Operators', 'Scoring of each operator with A and with B', ctx);
    const combined = part.scoring.Combined || part.scoring[part.environments[0]?.name];
    const operators = part.operators.filter(item => chosen.includes(item.operator));
    if (combined) {
      const cards = element('div', 'scoring-impact-cards');
      const ordered = [...operators].sort((left, right) => (combined.operators[left.operator]?.rank_after ?? 99) - (combined.operators[right.operator]?.rank_after ?? 99));
      for (const item of ordered) {
        const cell = combined.operators[item.operator];
        if (!cell) continue;
        const tone = toneOf(cell.delta);
        const moved = (cell.rank_before || 0) - (cell.rank_after || 0);
        const rank = element('span', `scoring-impact-rank is-${moved > 0 ? 'gain' : moved < 0 ? 'loss' : 'flat'}`,
          cell.rank_before && cell.rank_after && moved ? `${ordinal(cell.rank_before)} → ${ordinal(cell.rank_after)}` : (cell.rank_after ? ordinal(cell.rank_after) : ''));
        const card = element('article', 'scoring-impact-card',
          element('header', '', element('strong', '', `${item.label}${item.is_reference ? ' (reference)' : ''}`), rank),
          element('div', `scoring-impact-big is-${tone}`, signed(cell.delta)),
          element('div', 'scoring-impact-card-sides', element('span', '', sideBadge('a'), number(cell.before, 1)), element('span', '', sideBadge('b'), number(cell.after, 1))));
        const color = ctx.safeHexColor(item.color);
        if (color) card.style.setProperty('--operator-color', color);
        cards.append(card);
      }
      section.append(subtitle(`All Environments, of ${number(combined.max_after, 0)} points`), cards);
      if (operators.length > 1) section.append(subtitle('Who is ahead of whom'), rankingChart(combined, operators, doc, ctx));
    }
    const drivers = part.drivers?.[environment];
    const moved = operators.filter(item => drivers?.[item.operator] && Math.abs(drivers[item.operator].total) >= NO_CHANGE);
    if (moved.length) {
      const colours = {weights: ctx.theme?.categories?.[0] || '#4472C4', rules: ctx.theme?.categories?.[2] || '#C55A11', new: palette.gain, removed: palette.loss};
      const meta = Object.entries(CAUSES).map(([key, label]) => ({key, label, color: colours[key]}))
        .filter(item => moved.some(operator => Math.abs(drivers[operator.operator].causes[item.key] || 0) >= NO_CHANGE));
      section.append(subtitle('Why each operator moves'), stackedDiverging(moved.map(item => ({
        label: item.label, color: operatorColor(item, ctx), parts: drivers[item.operator].causes, total: drivers[item.operator].total,
      })), meta), legend(meta));
    }
    const environments = part.environments.filter(item => item.name !== 'Combined');
    if (environments.length) {
      section.append(subtitle('Each environment'));
      section.append(matrix('Environment', operators, environments.map(item => ({
        label: element('div', 'scoring-impact-label', element('strong', '', item.label),
          element('small', '', `Maximum ${number(part.scoring[item.name]?.max_before, 0)} → ${number(part.scoring[item.name]?.max_after, 0)} points`)),
        cells: part.scoring[item.name]?.operators || {},
      })), ctx));
    }
  }

  // The points of each operator in a category, with a bar as long as the maximum of the category in each methodology.
  function categoryCard(row, operators, ctx) {
    const scale = Math.max(NO_CHANGE, Number(row.max_before) || 0, Number(row.max_after) || 0);
    const card = element('article', 'scoring-impact-category', element('header', '', element('strong', '', row.category),
      element('small', '', `Maximum ${number(row.max_before, 1)} → ${number(row.max_after, 1)}`)));
    const line = (side, value, maximum) => {
      const fill = element('i');
      fill.style.width = `${maximum ? (Number(value) || 0) / maximum * 100 : 0}%`;
      const track = element('span', 'scoring-impact-pair-track', fill);
      track.style.width = `${(Number(maximum) || 0) / scale * 100}%`;
      return element('div', `scoring-impact-pair-line is-${side}`, element('span', 'scoring-impact-pair-scale', track), element('small', '', value === null || value === undefined ? '—' : number(value, 1)));
    };
    for (const item of operators) {
      const cell = row.operators[item.operator];
      if (!cell) continue;
      const name = element('strong', 'scoring-impact-pair-name', item.label);
      name.style.color = operatorColor(item, ctx);
      const tone = toneOf(cell.delta);
      card.append(element('div', 'scoring-impact-pair', name, element('div', 'scoring-impact-pair-bars', line('a', cell.before, row.max_before), line('b', cell.after, row.max_after)),
        element('b', `is-${tone}`, signed(cell.delta, 1))));
    }
    return card;
  }

  function categoryPanel(body, doc, part, chosen, environment, label, ctx) {
    const rows = part.categories[environment] || [];
    if (!rows.length) return;
    const section = panel(body, 'category', 'Categories', `Impact per category · ${label}`, ctx);
    const operators = part.operators.filter(item => chosen.includes(item.operator));
    const moved = rows.filter(row => row.peak >= NO_CHANGE).sort((first, second) => second.peak - first.peak);
    const same = rows.filter(row => row.peak < NO_CHANGE);
    if (moved.length) {
      section.append(sidesLegend(doc));
      const grid = element('div', 'scoring-impact-category-grid');
      for (const row of moved) grid.append(categoryCard(row, operators, ctx));
      section.append(grid);
    }
    if (same.length) section.append(note(`${moved.length ? 'Not affected' : 'No category moves'}: ${same.map(row => row.category).join(', ')}.`));
  }

  function kpiPanel(body, part, chosen, environment, label, ctx) {
    const all = part.kpis[environment] || [];
    const rows = all.filter(row => (row.kinds || []).length || row.peak >= NO_CHANGE);
    const section = panel(body, 'kpi', 'KPIs', `KPIs affected · ${label}`, ctx);
    if (!rows.length) {
      section.append(note('No KPI changes.'));
      return;
    }
    const operators = part.operators.filter(item => chosen.includes(item.operator));
    const {grid, width} = smallMultiples(operators.length);
    for (const item of operators) {
      const moved = rows.map(row => ({label: row.kpi, value: row.operators[item.operator]?.delta, category: row.category}))
        .filter(row => row.value !== null && row.value !== undefined && Math.abs(row.value) >= NO_CHANGE)
        .sort((first, second) => Math.abs(second.value) - Math.abs(first.value)).slice(0, 8).sort((first, second) => second.value - first.value);
      if (!moved.length) continue;
      const caption = element('figcaption', '', item.label);
      caption.style.color = operatorColor(item, ctx);
      grid.append(element('figure', 'scoring-chart-card scoring-impact-figure', caption,
        divergingChart(moved.map(row => ({label: row.label, detail: row.category, value: row.value, title: `${row.category} · ${row.label}: ${signed(row.value)}`})), {labelWidth: 230, valueWidth: 48, rowHeight: 32, width})));
    }
    if (grid.childElementCount) section.append(subtitle('What gives and takes the most points from each operator'), grid);
    const titleOf = (item, cell) => (cell ? `${item.label}\nKPI value: ${number(cell.value_before, 2)} → ${number(cell.value_after, 2)}\nScore: ${number((cell.score_before ?? NaN) * 100, 1)}% → ${number((cell.score_after ?? NaN) * 100, 1)}%` : '');
    section.append(subtitle(`The ${rows.length} KPIs, those that move most first`), pagedRows(`kpis:${environment}`, rows, shown => matrix('KPI', operators, shown.map(row => ({
      label: kpiLabel(row, element('small', '', `${row.category} · maximum ${number(row.max_before, 1)} → ${number(row.max_after, 1)}`)),
      cells: row.operators, titleOf,
    })), ctx)));
  }

  // ---- Maps ---------------------------------------------------------------------------------------------------------------
  function diagramOfMap(payload, shapes, item, scale) {
    const svg = svgElement('svg', {class: 'scoring-loss-map-svg scoring-impact-map'});
    const {boundaries = {}, outlines = []} = shapes || {};
    const rings = Object.entries(boundaries).flatMap(([name, polygons]) => polygons.map(ring => [name, ring]));
    const places = payload.rows.filter(row => row.place);
    const points = rings.length ? rings.flatMap(([, ring]) => ring)
      : outlines.length ? outlines.flat()
        : places.flatMap(row => [[row.place.longitude, row.place.latitude], ...(row.place.route || []).map(([lat, lon]) => [lon, lat])]);
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
    const pathOf = ring => `M${ring.map(([x, y]) => project(x, y).map(value => value.toFixed(1)).join(',')).join('L')}Z`;
    const values = new Map(payload.rows.map(row => [row.name, row.cells[item.operator]]));
    const unitText = payload.measure === 'national' ? 'National points' : payload.measure === 'rate' ? 'National points per 1,000 tests' : 'points of the area';
    const describe = (name, cell) => (cell ? `${name}\n${item.label}: ${signed(cell.value)} ${unitText}`
      + `${payload.measure === 'own' ? `\nScoring: ${number(cell.before, 1)} → ${number(cell.after, 1)}` : `\nPoints lost: ${number(cell.before, 2)} → ${number(cell.after, 2)}`}${cell.tests ? `\nTests: ${number(cell.tests, 0)}` : ''}` : `${name}: no tests of ${item.label}`);
    for (const ring of outlines) svg.append(svgElement('path', {d: pathOf(ring), fill: palette.zero, stroke: palette.surface, 'stroke-width': .5}));
    for (const [name, ring] of rings) {
      const cell = values.get(name);
      svg.append(withTitle(svgElement('path', {d: pathOf(ring), fill: cell ? heatColor(cell.value, scale) : palette.zero, stroke: palette.surface, 'stroke-width': .5}), describe(name, cell)));
    }
    if (!rings.length) {
      const ordered = [...places].filter(row => row.cells[item.operator]).sort((first, second) => Math.abs(first.cells[item.operator].value || 0) - Math.abs(second.cells[item.operator].value || 0));
      for (const row of ordered) {
        const cell = row.cells[item.operator];
        const value = cell.value || 0;
        const color = Math.abs(value) < NO_CHANGE ? palette.grid : value > 0 ? palette.gain : palette.loss;
        const size = Math.sqrt(Math.min(1, Math.abs(value) / (scale || 1)));
        if (row.place.kind === 'route' && row.place.route?.length) {
          svg.append(withTitle(svgElement('polyline', {points: row.place.route.map(([lat, lon]) => project(lon, lat).map(coordinate => coordinate.toFixed(1)).join(',')).join(' '), fill: 'none', stroke: color, 'stroke-width': 2 + size * 7, 'stroke-opacity': .8, 'stroke-linecap': 'round'}), describe(row.name, cell)));
        } else {
          const [x, y] = project(row.place.longitude, row.place.latitude);
          svg.append(withTitle(svgElement('circle', {cx: x.toFixed(1), cy: y.toFixed(1), r: (3 + size * 18).toFixed(1), fill: color, 'fill-opacity': .78, stroke: palette.surface, 'stroke-width': .8}), describe(row.name, cell)));
        }
      }
    }
    return svg;
  }

  function rankedList(rows, tone) {
    const list = element('ol', `scoring-impact-ranked is-${tone}`);
    for (const row of rows) list.append(element('li', '', element('span', '', row.name), element('b', '', signed(row.value))));
    return list;
  }

  function colourScale(scale, unit) {
    const bar = element('span', 'scoring-impact-scale');
    bar.style.background = `linear-gradient(90deg, ${palette.loss}, ${palette.zero} 50%, ${palette.gain})`;
    return element('div', 'scoring-impact-scale-row', element('span', '', `${signed(-scale)} worse with B`), bar, element('span', '', `${signed(scale)} better with B`), element('small', '', unit));
  }

  async function loadGeometry(ctx, doc, field) {
    const key = `${doc.key}|${field}`;
    if (!geometry.has(key)) {
      geometry.set(key, ctx.requestJson(`/api/scoring/saved-filters/${encodeURIComponent(ctx.savedFilterId)}/impact/boundaries/${encodeURIComponent(field)}?key=${doc.key}`)
        .catch(() => ({boundaries: {}, outlines: []})));
    }
    return geometry.get(key);
  }

  function mapsPanel(body, doc, part, chosen, environment, label, ctx) {
    const section = panel(body, 'maps', 'Maps', `Maps: where B gives or takes points · ${label}`, ctx);
    const controls = element('div', 'scoring-loss-controls');
    const box = element('div', 'scoring-impact-maps-body', element('div', 'scoring-empty', 'Loading the maps…'));
    section.append(controls, box);
    const token = renderToken;
    const drawMap = async () => {
      const query = {key: doc.key, scoring: doc.scorings[ctx.scoring] ? ctx.scoring : 'best_network', environment, field: choices.field || '', measure: choices.measure};
      const cacheKey = JSON.stringify(query);
      let payload = mapData.get(cacheKey);
      if (!payload) {
        try {
          payload = await ctx.requestJson(`/api/scoring/saved-filters/${encodeURIComponent(ctx.savedFilterId)}/impact/map?${new URLSearchParams(query)}`);
          mapData.set(cacheKey, payload);
        } catch (error) {
          box.replaceChildren(element('div', 'scoring-empty', error.message || 'The maps could not be read.'));
          return;
        }
      }
      if (token !== renderToken) return;
      choices.field = payload.field;
      choices.measure = payload.measure;
      const names = {City: 'City', Region: 'Region', Cluster: 'Cluster', Area: payload.area_label || 'Map Area', 'Postal Code': 'Postal Code'};
      controls.replaceChildren(
        selectField('Map per', ['City', 'Region', 'Cluster', 'Area', 'Postal Code'].map(name => [name, names[name], !payload.available.includes(name)]), payload.field, (value) => { choices.field = value; drawMap(); }),
        selectField('Measure', [['national', 'National points'], ['rate', 'National points per 1,000 tests'], ['own', 'Scoring of the area']].map(([value, text]) => [value, text, !payload.measures.includes(value)]), payload.measure, (value) => { choices.measure = value; drawMap(); }));
      box.replaceChildren();
      if (doc.maps_error) box.append(note(`The National points could not be mapped: ${doc.maps_error}. The scoring of each area is still shown.`));
      if (!payload.rows.length) {
        box.append(element('div', 'scoring-empty', 'These tests have no values for this map.'));
        return;
      }
      const operators = part.operators.filter(item => chosen.includes(item.operator));
      const values = operators.flatMap(item => payload.rows.map(row => Math.abs(row.cells[item.operator]?.value ?? 0))).filter(value => value > 0).sort((first, second) => first - second);
      // (The largest few do not take the whole scale.)
      const scale = values.length ? values[Math.min(values.length - 1, Math.floor(values.length * .98))] : 1;
      const unit = payload.measure === 'own' ? 'points of the area' : payload.measure === 'rate' ? 'National points per 1,000 tests' : 'National points';
      if (payload.shape !== 'none') {
        const shapes = await loadGeometry(ctx, doc, payload.field);
        if (token !== renderToken) return;
        const grid = element('div', `scoring-loss-map-grid${operators.length > 1 ? ' is-multiple' : ''}`);
        // Side by side, to compare them, as many as fit.
        grid.style.gridTemplateColumns = `repeat(${chartWidth >= 900 ? Math.min(4, operators.length) : chartWidth >= 640 ? Math.min(2, operators.length) : 1}, minmax(0, 1fr))`;
        for (const item of operators) {
          const summary = payload.analysis.operators?.[item.operator];
          const title = element('h5', 'scoring-loss-map-operator', item.label);
          title.style.color = operatorColor(item, ctx);
          const figure = element('div', 'scoring-loss-map-figure', diagramOfMap(payload, shapes, item, scale));
          const card = element('article', 'scoring-loss-map-card scoring-impact-map-card', title, figure);
          if (summary) {
            card.append(element('div', 'scoring-impact-map-summary', element('span', 'is-gain', `${number(summary.up, 0)} areas better`), element('span', 'is-loss', `${number(summary.down, 0)} areas worse`)));
            const lists = element('div', 'scoring-impact-ranked-pair');
            if (summary.top?.length) lists.append(element('div', '', element('strong', 'is-gain', 'Gains most'), rankedList(summary.top, 'gain')));
            if (summary.bottom?.length) lists.append(element('div', '', element('strong', 'is-loss', 'Loses most'), rankedList(summary.bottom, 'loss')));
            card.append(lists);
          }
          grid.append(card);
        }
        box.append(colourScale(scale, unit), grid);
        grid.querySelectorAll('.scoring-loss-map-figure').forEach(figure => ctx.enableMapZoom?.(figure, figure.querySelector('svg')));
      } else {
        box.append(note(`The ${payload.label} areas have no polygons or positions to draw: their values are in the panel below.`));
      }
      if (payload.attribution) box.append(note(payload.attribution));
      box.append(note(payload.measure === 'own'
        ? 'The scoring of each area with B minus its scoring with A.'
        : `What each area gives or takes of the National scoring of the operator: the areas add up to its difference.${payload.measure === 'rate' ? ' Per 1,000 tests, so an area does not move only because it was measured more; the areas with few tests are left out.' : ''}`));
    };
    drawMap();
  }

  function areaTablePanel(body, part, chosen, environment, label, ctx) {
    const levels = Object.keys(part.areas || {});
    if (!levels.length) return;
    const section = panel(body, 'area', 'Areas', `Impact per area · ${label}`, ctx);
    if (!levels.includes(choices.table)) choices.table = levels[0];
    const box = element('div');
    const drawTable = (name) => {
      const rows = part.areas[name]?.[environment] || [];
      const operators = part.operators.filter(item => chosen.includes(item.operator));
      const swaps = rows.filter(row => row.leader_before !== row.leader_after);
      const labels = Object.fromEntries(part.operators.map(item => [item.operator, item.label]));
      box.replaceChildren(element('p', 'scoring-impact-context', rows.length ? `The leader changes in ${swaps.length} of the ${rows.length} ${name} areas.` : `These tests have no ${name} areas.`),
        pagedRows(`areas:${name}:${environment}`, rows, shown => matrix(name, operators, shown.map(row => ({
          label: element('strong', '', row.area), cells: row.operators,
          extra: [row.leader_before === row.leader_after ? element('span', 'scoring-impact-leader', labels[row.leader_after] || row.leader_after || '')
            : element('span', 'scoring-impact-leader is-changed', `${labels[row.leader_before] || row.leader_before} → ${labels[row.leader_after] || row.leader_after}`)],
        })), ctx, {extraHeaders: ['Leader']})));
    };
    section.append(ctx.insightControls(selectField('Area', levels.map(name => [name, name]), choices.table, (value) => { choices.table = value; drawTable(value); })), box);
    drawTable(choices.table);
  }

  function gapPanel(body, doc, part, chosen, environment, label, ctx) {
    const gap = part.gap[environment];
    if (!gap) return;
    const reference = part.operators.find(item => item.is_reference);
    const section = panel(body, 'gap', 'GAP', `GAP against ${reference?.label || part.reference} · ${label}`, ctx);
    const operators = part.operators.filter(item => chosen.includes(item.operator) && !item.is_reference);
    if (!operators.length) {
      section.append(note('Enable an operator other than the reference to see its GAP.'));
      return;
    }
    section.append(sidesLegend(doc), gapChart(operators.filter(item => gap.total[item.operator]).map(item => ({
      label: item.label, color: operatorColor(item, ctx), ...gap.total[item.operator],
    })).sort((first, second) => second.delta - first.delta)));
    const categories = gap.categories.filter(row => row.peak >= NO_CHANGE);
    if (categories.length) section.append(subtitle('Per category'), matrix('Category', operators, categories.map(row => ({label: element('strong', '', row.category), cells: row.operators})), ctx));
    const kpis = gap.kpis.filter(row => row.peak >= NO_CHANGE);
    if (kpis.length) {
      section.append(subtitle('Per KPI, those that move most first'), pagedRows(`gap:${environment}`, kpis, shown => matrix('KPI', operators, shown.map(row => ({
        label: kpiLabel(row, element('small', '', row.category)), cells: row.operators,
      })), ctx)));
    }
  }

  function pointsPanel(body, doc, part, chosen, environment, label, ctx) {
    const lost = part.points_lost[environment];
    if (!lost) return;
    const section = panel(body, 'points', 'Points Lost', `Points Lost · ${label}`, ctx);
    const operators = part.operators.filter(item => chosen.includes(item.operator) && lost.operators[item.operator]);
    const shown = lost.kinds.filter(kind => (kind.kpis || []).length || operators.some(item => lost.operators[item.operator].parts_before?.[kind.key] || lost.operators[item.operator].parts_after?.[kind.key]));
    const [notCompleted, minimum, below, quality] = ctx.theme?.stake || ['#6e1222', '#a51c30', '#e8414f', '#f4a3aa'];
    const colours = {not_completed: notCompleted, below_minimum: minimum, below_par: below, quality};
    const peak = Math.max(1, ...operators.flatMap(item => [lost.operators[item.operator].before, lost.operators[item.operator].after].map(value => Number(value) || 0)));
    const bar = (side, parts, total) => {
      const stack = element('span', 'scoring-impact-stack');
      for (const kind of shown) {
        const value = Number(parts?.[kind.key]) || 0;
        if (value <= 0) continue;
        const segment = element('i', '', value / peak > .08 ? number(value, 0) : '');
        segment.style.width = `${value / peak * 100}%`;
        segment.style.background = colours[kind.key];
        segment.title = `${kind.label}: ${number(value, 2)} points`;
        stack.append(segment);
      }
      return element('div', 'scoring-impact-lost-line', sideBadge(side), stack, element('small', '', number(total, 1)));
    };
    const list = element('div', 'scoring-impact-lost');
    for (const item of operators) {
      const row = lost.operators[item.operator];
      const name = element('strong', '', `${item.label}${item.is_reference ? ' (reference)' : ''}`);
      name.style.color = operatorColor(item, ctx);
      const tone = toneOf(row.delta, true);
      list.append(element('div', 'scoring-impact-lost-row', name,
        element('div', 'scoring-impact-lost-bars', bar('a', row.parts_before, row.before), bar('b', row.parts_after, row.after)),
        element('div', 'scoring-impact-lost-total', element('b', `is-${tone}`, signed(row.delta)), element('small', '', 'points lost'))));
    }
    section.append(sidesLegend(doc), list, legend(shown.map(kind => ({color: colours[kind.key], label: kind.label}))));
    const inScope = part.operators.filter(item => chosen.includes(item.operator));
    const categories = lost.categories.filter(row => row.peak >= NO_CHANGE);
    if (categories.length) {
      section.append(subtitle('Per category'), matrix('Category', inScope, categories.map(row => ({label: element('strong', '', row.category), cells: row.operators})), ctx, {inverse: true}));
    }
    const kpis = lost.kpis.filter(row => row.peak >= NO_CHANGE);
    if (kpis.length) {
      section.append(subtitle('Per KPI, those that move most first'), pagedRows(`lost:${environment}`, kpis, rows => matrix('KPI', inScope, rows.map(row => ({
        label: kpiLabel(row, element('small', '', row.category)), cells: row.operators,
      })), ctx, {inverse: true})));
    }
    section.append(note('The points lost of a KPI are its maximum minus the points scored, so they also move when the methodology gives it another maximum. More points lost are shown in red.'));
  }

  // To go to a panel without scrolling the whole tab.
  function jumpLinks(head, body) {
    const nav = element('nav', 'scoring-impact-nav');
    nav.setAttribute('aria-label', 'Panels of the Methodology Impact');
    for (const section of body.querySelectorAll('[data-impact-panel]')) {
      const link = element('button', '', section.dataset.impactPanel);
      link.type = 'button';
      link.addEventListener('click', () => section.scrollIntoView({behavior: 'smooth', block: 'start'}));
      nav.append(link);
    }
    head.append(nav);
  }

  function draw(body, doc, ctx) {
    body.replaceChildren();
    if (doc.same_methodology) {
      panel(body, 'head', '', 'Methodology Impact', ctx).append(note(`Both campaigns are scored with ${doc.before.profile_name}, so the methodology changes nothing between them. Choose two campaigns with different methodologies, or Two methodologies.`));
      return;
    }
    // (A scoring that one of the methodologies does not have is not compared: Best Network is.)
    const scoring = doc.scorings[ctx.scoring] ? ctx.scoring : 'best_network';
    const part = doc.scorings[scoring];
    const environments = part.environments.map(item => item.name);
    const environment = environments.includes(ctx.environment) ? ctx.environment : (environments.includes('Combined') ? 'Combined' : environments[0]);
    if (!environment) {
      body.append(element('div', 'scoring-empty', 'These tests have no results in the environments of either methodology.'));
      return;
    }
    palette = paletteOf(ctx, body);
    body.style.setProperty('--impact-b-ink', inkOn(palette.b));
    chartWidth = Math.max(280, (body.parentElement?.clientWidth || 900) - 64);
    const {control, chosen} = ctx.insightOperatorChips('impact-operators', part.operators, {all: true});
    chosenOperators = chosen;
    const label = part.environments.find(item => item.name === environment)?.label || environment;
    const head = headPanel(body, doc, part, scoring, ctx, control);
    changesPanel(body, doc, part, ctx);
    scoringPanel(body, doc, part, chosen, environment, ctx);
    categoryPanel(body, doc, part, chosen, environment, label, ctx);
    kpiPanel(body, part, chosen, environment, label, ctx);
    mapsPanel(body, doc, part, chosen, environment, label, ctx);
    areaTablePanel(body, part, chosen, environment, label, ctx);
    gapPanel(body, doc, part, chosen, environment, label, ctx);
    pointsPanel(body, doc, part, chosen, environment, label, ctx);
    jumpLinks(head, body);
  }

  function progressCard(body, state) {
    const percent = Math.max(2, Math.min(100, Number(state.progress) || 0));
    const fill = element('span');
    fill.style.width = `${percent}%`;
    body.replaceChildren(element('div', 'scoring-impact-progress', element('strong', '', 'Scoring the tests with both methodologies'),
      element('span', 'scoring-impact-progress-bar', fill), element('small', '', state.message || 'Waiting')));
  }

  function controlsBar(offered, selection, ctx, onChange) {
    // Each NR Mode has campaigns of its own.
    const set = (key, value) => onChange({...selection, [key]: value, ...(key === 'nr_mode' ? offered.by_nr_mode[value] : {})});
    const field = (label, key, entries) => {
      const wrapper = selectField(label, entries, selection[key], value => set(key, value));
      wrapper.querySelector('select').dataset.impactField = key;
      return wrapper;
    };
    const entries = (offered.campaigns[selection.nr_mode] || []).map(entry => [entry.value, `${entry.label} · ${entry.methodology_name}`]);
    const box = element('section', 'scoring-result-card scoring-impact-controls');
    const modes = element('div', 'scoring-impact-mode');
    modes.setAttribute('role', 'group');
    modes.setAttribute('aria-label', 'What to compare');
    for (const [value, text] of [['campaigns', 'The methodologies of two campaigns'], ['methodologies', 'Two methodologies']]) {
      const button = element('button', '', text);
      button.type = 'button';
      button.setAttribute('aria-pressed', String(selection.mode === value));
      button.addEventListener('click', () => set('mode', value));
      modes.append(button);
    }
    const fields = element('div', 'scoring-loss-controls');
    fields.append(modes);
    if (offered.nr_modes.length > 1) fields.append(field('NR Mode', 'nr_mode', offered.nr_modes.map(mode => [mode, mode])));
    if (selection.mode === 'campaigns') {
      fields.append(field('From campaign', 'campaign_a', entries), field('To campaign (its tests are scored)', 'campaign_b', entries));
    } else {
      const methodologies = offered.methodologies.map(item => [item.id, item.name]);
      fields.append(field('First methodology', 'methodology_a', methodologies), field('Second methodology', 'methodology_b', methodologies),
        field('Tests of the campaign', 'campaign', entries));
    }
    const exports = element('div', 'scoring-impact-exports');
    for (const [kind, label] of [['csv', 'CSV'], ['ppt', 'PowerPoint'], ['word', 'Word']]) {
      const link = element('a', '', `Export to ${label}`);
      link.href = '#';
      link.dataset.impactExport = kind;
      link.title = `The Methodology Impact shown below as ${label}`;
      link.setAttribute('aria-disabled', 'true');
      link.addEventListener('click', (event) => {
        event.preventDefault();
        if (link.getAttribute('aria-disabled') === 'true') return;
        const extra = {environment: ctx.environment || 'Combined', scoring: ctx.scoring, theme: ctx.theme?.id || ''};
        if (chosenOperators) extra.operators = JSON.stringify(chosenOperators);
        ctx.download(`/scoring/saved-filters/${encodeURIComponent(ctx.savedFilterId)}/impact/export/${kind}?${queryOf(selection, extra)}`, label);
      });
      exports.append(link);
    }
    box.append(fields, exports);
    return box;
  }

  function showError(body, message, retry = null) {
    const box = element('div', 'scoring-empty scoring-impact-error', message);
    if (retry) {
      const button = element('button', 'scoring-impact-more', 'Calculate again');
      button.type = 'button';
      button.addEventListener('click', retry);
      box.append(button);
    }
    body.replaceChildren(box);
  }

  async function load(pane, body, bar, selection, ctx, token, retry = false, statusKey = null) {
    window.clearTimeout(pollTimer);
    // (Another Saved Filter is shown, or the results are being calculated again.)
    if (!pane.contains(body)) return;
    const cacheKey = `${ctx.savedFilterId}|${queryOf(selection)}`;
    const setExports = enabled => bar.querySelectorAll('[data-impact-export]').forEach((link) => {
      link.setAttribute('aria-disabled', String(!enabled));
    });
    const cached = impacts.get(cacheKey);
    if (cached && !retry && !statusKey) {
      setExports(!cached.same_methodology);
      draw(body, cached, ctx);
      if (validated.has(cacheKey)) return;
    }
    let state;
    try {
      // While it is calculated, only how it goes (its key does not have to be worked out again).
      state = await ctx.requestJson(statusKey
        ? `/api/scoring/saved-filters/${encodeURIComponent(ctx.savedFilterId)}/impact/status?key=${statusKey}`
        : `/api/scoring/saved-filters/${encodeURIComponent(ctx.savedFilterId)}/impact?${queryOf(selection, retry ? {retry: 'true'} : {})}`);
    } catch (error) {
      if (token === renderToken) showError(body, error.message || 'The Methodology Impact could not be calculated.');
      return;
    }
    if (token !== renderToken || !pane.contains(body)) return;
    if (state.status === 'completed' && state.impact) {
      const same = cached && cached.key === state.impact.key;
      impacts.set(cacheKey, state.impact);
      validated.add(cacheKey);
      setExports(!state.impact.same_methodology);
      if (!same) draw(body, state.impact, ctx);
      return;
    }
    setExports(false);
    if (state.status === 'failed') {
      showError(body, `The Methodology Impact could not be calculated: ${state.error}`, () => load(pane, body, bar, selection, ctx, token, true));
      return;
    }
    progressCard(body, state);
    if (!pane.hidden) pollTimer = window.setTimeout(() => load(pane, body, bar, selection, ctx, token, false, state.key || statusKey), POLL_MS);
  }

  async function render(pane, ctx) {
    const token = ++renderToken;
    window.clearTimeout(pollTimer);
    if (!ctx.savedFilterId) {
      pane.replaceChildren(element('div', 'scoring-empty', 'No Saved Filter is selected.'));
      return;
    }
    let offered = options.get(ctx.savedFilterId);
    if (!offered) {
      pane.replaceChildren(element('div', 'scoring-empty', 'Loading the Methodology Impact…'));
      try {
        offered = await ctx.requestJson(`/api/scoring/saved-filters/${encodeURIComponent(ctx.savedFilterId)}/impact/options`);
      } catch (error) {
        if (token === renderToken) pane.replaceChildren(element('div', 'scoring-empty', error.message || 'The Methodology Impact could not be opened.'));
        return;
      }
      if (token !== renderToken) return;
      options.set(ctx.savedFilterId, offered);
    }
    // (Its cards are styled as those of the panes.)
    const body = element('div', 'scoring-impact-body scoring-nr-mode-body');
    const open = (selection) => {
      rememberSelection(ctx.savedFilterId, selection);
      const current = renderToken;
      const bar = controlsBar(offered, selection, ctx, (next) => {
        renderToken += 1;
        open(next);
      });
      pane.replaceChildren(bar, body);
      progressCard(body, {progress: 2, message: 'Looking for this comparison'});
      load(pane, body, bar, selection, ctx, current);
    };
    open(selectionOf(ctx.savedFilterId, offered));
  }

  window.ScoringImpact = {render};
})();
