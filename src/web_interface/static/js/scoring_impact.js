// Methodology Impact of Scoring & GAP Analysis: what a change of methodology does to the results, with the scope of the open
// Saved Filter. The same tests are scored with both methodologies in the background (see scoring_impact.py), so every figure
// comes from the methodology and none from the network: who it favours, why, where and how stable it is.
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
  const choices = {field: null, measure: 'national', compare: 'each', cube: null, cubeOperator: null, table: null};
  // The operators enabled in the panels drawn, which the documents show.
  let chosenOperators = null;
  // The width the charts are drawn at, that of their card: their text keeps its size on every screen.
  let chartWidth = 860;
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
    return {surface, ink, gain: style.getPropertyValue('--st-gain').trim() || '#4ca65a', loss: style.getPropertyValue('--st-loss').trim() || '#e8414f',
      zero: mix(surface, ink, .07), grid: mix(surface, ink, .18), muted: mix(surface, ink, .55), dark: lightness(hexChannels(surface) || [255, 255, 255]) < .4};
  }

  // A value from the loss colour to the gain colour; a root scale so the small differences show beside the large ones.
  function heatColor(value, scale, palette) {
    if (value === null || value === undefined || !Number.isFinite(Number(value))) return palette.zero;
    if (!scale || Math.abs(value) < NO_CHANGE) return palette.zero;
    const share = Math.min(1, Math.sqrt(Math.abs(value) / scale));
    return mix(palette.surface, value > 0 ? palette.gain : palette.loss, .14 + share * .86);
  }

  function inkOn(color, palette) {
    const channels = String(color).match(/\d+/g)?.slice(0, 3).map(Number) || hexChannels(color) || [255, 255, 255];
    const parsed = String(color).startsWith('rgb') ? channels : (hexChannels(color) || channels);
    return lightness(parsed) > .58 ? '#17232d' : '#ffffff';
  }

  // The colour of an operator, readable on the theme (a black operator on a dark theme takes its ink).
  function operatorColor(item, ctx, palette) {
    const color = ctx.safeHexColor(item?.color) || palette.ink;
    const channels = hexChannels(color);
    return palette.dark && channels && lightness(channels) < .2 ? palette.ink : color;
  }

  // ---- Cells and tables --------------------------------------------------------------------------------------------------
  // The bar either side of zero of a difference, as long as the difference against the largest of its table.
  function track(delta, scale, tone) {
    const bar = element('span', 'scoring-impact-track');
    const share = Math.abs(Number(delta) || 0) / Math.max(Number(scale) || 0, NO_CHANGE);
    if (share > 0 && tone !== 'flat') {
      const fill = element('i', `is-${delta > 0 ? 'right' : 'left'} is-${tone}`);
      fill.style.width = `${Math.min(share, 1) * 50}%`;
      bar.append(fill);
    }
    return bar;
  }

  function toneOf(delta, inverse = false) {
    if (delta === null || delta === undefined || Math.abs(delta) < NO_CHANGE) return 'flat';
    return (delta > 0) !== inverse ? 'gain' : 'loss';
  }

  // A cell of the impact: its difference with the bar, and the value before and after.
  function shiftCell(cell, scale, {inverse = false, title = '', flip = false, digits = 1} = {}) {
    const box = element('td', 'scoring-impact-cell');
    if (!cell || (cell.before === null && cell.after === null)) {
      box.classList.add('is-empty');
      box.textContent = '—';
      return box;
    }
    const tone = toneOf(cell.delta, inverse);
    box.dataset.tone = tone;
    const head = element('span', 'scoring-impact-head', element('b', `is-${tone}`, signed(cell.delta)));
    if (flip) head.append(element('em', 'scoring-impact-flag', 'Changes side'));
    box.append(head, track(cell.delta, scale, tone),
      element('small', '', `${cell.before === null ? 'none' : number(cell.before, digits)} → ${cell.after === null ? 'none' : number(cell.after, digits)}`));
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
      if (row.className) line.className = row.className;
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

  // ---- Charts (each fits its card: it scales with its width) ---------------------------------------------------------------
  // Bars either side of zero, from the largest: a label, the bar and its value.
  function divergingChart(items, palette, {labelWidth: wantedLabel = 240, valueWidth = 66, rowHeight = 26, digits = 2, inverse = false, width = chartWidth} = {}) {
    const height = Math.max(rowHeight * items.length + 8, 30);
    const svg = svgElement('svg', {viewBox: `0 0 ${width} ${height}`, class: 'scoring-impact-chart', role: 'img'});
    const labelWidth = Math.min(wantedLabel, width * .38);
    const room = Math.max((width - labelWidth - valueWidth * 2) / 2, 10);
    const middle = labelWidth + valueWidth + room;
    const scale = Math.max(NO_CHANGE, ...items.map(item => Math.abs(Number(item.value) || 0)));
    svg.append(svgElement('line', {x1: middle, x2: middle, y1: 0, y2: height, stroke: palette.grid}));
    const room_chars = Math.max(12, Math.floor(labelWidth / 7));
    items.forEach((item, index) => {
      const y = index * rowHeight + 4;
      const value = Number(item.value) || 0;
      const reach = Math.abs(value) / scale * room;
      const label = withTitle(svgElement('text', {x: labelWidth - 8, y: y + rowHeight / 2 + 2, 'text-anchor': 'end', fill: item.color || 'currentColor', 'font-size': 12, 'font-weight': item.color ? 700 : 500},
        String(item.label).length > room_chars ? `${String(item.label).slice(0, room_chars - 1)}…` : item.label), String(item.label));
      const tone = toneOf(value, inverse);
      const bar = withTitle(svgElement('rect', {x: value < 0 ? middle - reach : middle, y: y + 3, width: Math.max(reach, tone === 'flat' ? 0 : 1), height: rowHeight - 9, rx: 2,
        fill: tone === 'gain' ? palette.gain : palette.loss}), item.title || `${item.label}: ${signed(value, digits)}`);
      const text = svgElement('text', {x: value < 0 ? middle - reach - 5 : middle + reach + 5, y: y + rowHeight / 2 + 2, 'text-anchor': value < 0 ? 'end' : 'start', 'font-size': 12, 'font-weight': 700,
        fill: tone === 'flat' ? palette.muted : tone === 'gain' ? palette.gain : palette.loss}, signed(value, digits));
      svg.append(label, bar, text);
    });
    return svg;
  }

  // A heatmap: rows by columns, each cell in the colour of its value.
  function heatTable(firstHeader, columns, rows, palette, {digits = 2, scale = null, format = null} = {}) {
    const values = rows.flatMap(row => row.cells.map(cell => Math.abs(Number(cell?.value) || 0)));
    const peak = scale ?? Math.max(NO_CHANGE, ...values);
    const table = element('table', 'scoring-insight-table scoring-impact-heat');
    table.createTHead().insertRow().append(element('th', '', firstHeader), ...columns.map((column) => {
      const cell = element('th', '', column.label ?? column);
      if (column.color) cell.style.color = column.color;
      return cell;
    }));
    const body = table.createTBody();
    for (const row of rows) {
      const line = body.insertRow();
      const first = line.insertCell();
      first.className = 'scoring-impact-row-label';
      first.append(row.label);
      for (const cell of row.cells) {
        const box = line.insertCell();
        const value = cell?.value;
        if (value === null || value === undefined) {
          box.textContent = '—';
          box.className = 'scoring-impact-heat-cell is-empty';
          continue;
        }
        const color = heatColor(value, peak, palette);
        box.className = 'scoring-impact-heat-cell';
        // (Over the colours each theme gives the cells of a table.)
        box.style.setProperty('background', color, 'important');
        box.style.setProperty('color', inkOn(color, palette), 'important');
        box.textContent = format ? format(value) : signed(value, digits);
        if (cell.title) box.title = cell.title;
      }
    }
    return element('div', 'scoring-insight-table-wrap', table);
  }

  // Per row, its parts stacked either side of zero, each in its colour.
  function stackedDiverging(rows, partsMeta, palette, {labelWidth: wantedLabel = 150, width = chartWidth, rowHeight = 34} = {}) {
    const labelWidth = Math.min(wantedLabel, width * .25);
    const height = rowHeight * rows.length + 8;
    const svg = svgElement('svg', {viewBox: `0 0 ${width} ${height}`, class: 'scoring-impact-chart', role: 'img'});
    const room = (width - labelWidth - 90) / 2;
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
        if (reach > 44) svg.append(svgElement('text', {x: x + reach / 2, y: y + rowHeight / 2 + 1, 'text-anchor': 'middle', 'font-size': 10.5, 'font-weight': 700, fill: inkOn(part.color, palette)}, signed(value, Math.abs(value) >= 10 ? 1 : 2)));
        if (value > 0) right += reach; else leftEdge -= reach;
      }
      const tone = toneOf(row.total);
      svg.append(svgElement('text', {x: width - 4, y: y + rowHeight / 2 + 2, 'text-anchor': 'end', 'font-size': 13, 'font-weight': 800,
        fill: tone === 'flat' ? palette.muted : tone === 'gain' ? palette.gain : palette.loss}, signed(row.total)));
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

  // Each step adds to the one before, from zero to the total.
  function waterfallChart(steps, total, palette, {width = 420, height = 210, color = null} = {}) {
    const svg = svgElement('svg', {viewBox: `0 0 ${width} ${height}`, class: 'scoring-impact-chart', role: 'img'});
    const levels = [0];
    let running = 0;
    for (const step of steps) {
      running += step.value;
      levels.push(running);
    }
    const low = Math.min(0, ...levels, total);
    const high = Math.max(0, ...levels, total);
    const spread = Math.max(high - low, NO_CHANGE);
    const top = 16;
    const bottom = height - 38;
    const y = value => top + (high - value) / spread * (bottom - top);
    const count = steps.length + 1;
    const band = (width - 8) / count;
    svg.append(svgElement('line', {x1: 0, x2: width, y1: y(0), y2: y(0), stroke: palette.grid}));
    running = 0;
    steps.forEach((step, index) => {
      const start = running;
      running += step.value;
      const x = 4 + index * band;
      svg.append(withTitle(svgElement('rect', {x: x + 3, y: Math.min(y(start), y(running)), width: band - 6, height: Math.max(Math.abs(y(start) - y(running)), 1),
        fill: step.value >= 0 ? palette.gain : palette.loss}), `${step.label}: ${signed(step.value)}`));
      svg.append(svgElement('text', {x: x + band / 2, y: Math.min(y(start), y(running)) - 3, 'text-anchor': 'middle', 'font-size': 9.5, 'font-weight': 700, fill: 'currentColor'}, signed(step.value, Math.abs(step.value) >= 10 ? 1 : 2)));
      String(step.label).split(/[\s/]+/).slice(0, 2).forEach((word, line) => svg.append(svgElement('text', {x: x + band / 2, y: bottom + 12 + line * 10, 'text-anchor': 'middle', 'font-size': 8.5, fill: palette.muted}, word.length > 10 ? `${word.slice(0, 9)}…` : word)));
    });
    const x = 4 + steps.length * band;
    svg.append(withTitle(svgElement('rect', {x: x + 3, y: Math.min(y(0), y(total)), width: band - 6, height: Math.max(Math.abs(y(0) - y(total)), 1), fill: color || palette.ink}), `Total: ${signed(total)}`));
    svg.append(svgElement('text', {x: x + band / 2, y: Math.min(y(0), y(total)) - 3, 'text-anchor': 'middle', 'font-size': 10, 'font-weight': 800, fill: 'currentColor'}, signed(total)));
    svg.append(svgElement('text', {x: x + band / 2, y: bottom + 12, 'text-anchor': 'middle', 'font-size': 8.5, 'font-weight': 700, fill: palette.muted}, 'Total'));
    return svg;
  }

  // Dots of two measures with the straight line that fits them and the lines of zero.
  function scatterChart(points, palette, {xLabel = '', yLabel = '', fit = null, color = null, width = 420, height = 280, describe = null, showZeroX = true} = {}) {
    const svg = svgElement('svg', {viewBox: `0 0 ${width} ${height}`, class: 'scoring-impact-chart', role: 'img'});
    if (!points.length) return svg;
    const [left, right, top, bottom] = [46, 10, 10, 34];
    const rangeOf = (values, withZero) => {
      const low = Math.min(...values, ...(withZero ? [0] : []));
      const high = Math.max(...values, ...(withZero ? [0] : []));
      const margin = Math.max((high - low) * .08, NO_CHANGE);
      return [low - margin, high + margin];
    };
    const [minX, maxX] = rangeOf(points.map(point => point.x), showZeroX);
    const [minY, maxY] = rangeOf(points.map(point => point.y), true);
    const px = value => left + (value - minX) / (maxX - minX) * (width - left - right);
    const py = value => top + (maxY - value) / (maxY - minY) * (height - top - bottom);
    svg.append(svgElement('rect', {x: left, y: top, width: width - left - right, height: height - top - bottom, fill: 'none', stroke: palette.grid}));
    if (minY < 0 && maxY > 0) svg.append(svgElement('line', {x1: left, x2: width - right, y1: py(0), y2: py(0), stroke: palette.grid}));
    if (showZeroX && minX < 0 && maxX > 0) svg.append(svgElement('line', {x1: px(0), x2: px(0), y1: top, y2: height - bottom, stroke: palette.grid}));
    for (const [value, anchor] of [[minX, 'start'], [maxX, 'end']]) svg.append(svgElement('text', {x: px(value), y: height - bottom + 13, 'text-anchor': anchor, 'font-size': 9.5, fill: palette.muted}, number(value, Math.abs(value) >= 100 ? 0 : 1)));
    for (const value of [minY, maxY]) svg.append(svgElement('text', {x: left - 4, y: py(value) + (value === maxY ? 8 : -2), 'text-anchor': 'end', 'font-size': 9.5, fill: palette.muted}, number(value, 1)));
    svg.append(svgElement('text', {x: (left + width - right) / 2, y: height - 6, 'text-anchor': 'middle', 'font-size': 10.5, fill: palette.muted}, xLabel));
    svg.append(svgElement('text', {x: 11, y: (top + height - bottom) / 2, 'text-anchor': 'middle', 'font-size': 10.5, fill: palette.muted, transform: `rotate(-90 11 ${(top + height - bottom) / 2})`}, yLabel));
    if (fit) {
      // (The line stays inside the frame.)
      const clip = value => Math.min(Math.max(value, minY), maxY);
      svg.append(svgElement('line', {x1: px(minX), y1: py(clip(fit.slope * minX + fit.intercept)), x2: px(maxX), y2: py(clip(fit.slope * maxX + fit.intercept)), stroke: color || palette.ink, 'stroke-width': 1.6, 'stroke-dasharray': '5 4'}));
    }
    for (const point of points) {
      svg.append(withTitle(svgElement('circle', {cx: px(point.x), cy: py(point.y), r: 3.6, fill: color || palette.ink, 'fill-opacity': .72, stroke: palette.surface, 'stroke-width': .6}), describe ? describe(point) : point.name));
    }
    return svg;
  }

  // Each operator's areas as dots along the value, with the box of their middle half.
  function spreadChart(rows, operators, analysis, palette, ctx, {width = chartWidth} = {}) {
    const items = operators.filter(item => analysis.operators?.[item.operator]);
    const rowHeight = 46;
    const left = Math.min(120, width * .24);
    const height = items.length * rowHeight + 30;
    const svg = svgElement('svg', {viewBox: `0 0 ${width} ${height}`, class: 'scoring-impact-chart', role: 'img'});
    const values = items.flatMap(item => rows.map(row => row.cells[item.operator]?.value).filter(value => value !== null && value !== undefined));
    const extent = Math.max(NO_CHANGE, ...values.map(Math.abs));
    const x = value => left + (value + extent) / (2 * extent) * (width - left - 20);
    svg.append(svgElement('line', {x1: x(0), x2: x(0), y1: 2, y2: height - 22, stroke: palette.grid}));
    for (const value of [-extent, 0, extent]) svg.append(svgElement('text', {x: x(value), y: height - 6, 'text-anchor': value < 0 ? 'start' : value > 0 ? 'end' : 'middle', 'font-size': 10, fill: palette.muted}, signed(value)));
    items.forEach((item, index) => {
      const summary = analysis.operators[item.operator];
      const y = index * rowHeight + 24;
      const color = operatorColor(item, ctx, palette);
      svg.append(svgElement('text', {x: left - 10, y: y + 4, 'text-anchor': 'end', 'font-size': 12.5, 'font-weight': 700, fill: color}, item.label));
      if (summary.q1 !== null && summary.q3 !== null) {
        svg.append(svgElement('rect', {x: x(summary.q1), y: y - 11, width: Math.max(x(summary.q3) - x(summary.q1), 1), height: 22, fill: color, 'fill-opacity': .13, stroke: color, 'stroke-opacity': .45, rx: 2}));
        svg.append(svgElement('line', {x1: x(summary.median), x2: x(summary.median), y1: y - 11, y2: y + 11, stroke: color, 'stroke-width': 2}));
      }
      // (Only those that move, the largest ones when there are thousands.)
      const moving = rows.map(row => ({name: row.name, value: row.cells[item.operator]?.value})).filter(point => point.value !== null && point.value !== undefined && Math.abs(point.value) >= NO_CHANGE)
        .sort((first, second) => Math.abs(second.value) - Math.abs(first.value)).slice(0, 260);
      moving.forEach((point, position) => {
        const jitter = ((position * 7) % 15) - 7;
        svg.append(withTitle(svgElement('circle', {cx: x(point.value), cy: y + jitter, r: 2.8, fill: point.value > 0 ? palette.gain : palette.loss, 'fill-opacity': .7}), `${item.label} · ${point.name}: ${signed(point.value)}`));
      });
    });
    return svg;
  }

  // How much of the movement the areas that move most hold.
  function concentrationChart(operators, analysis, palette, ctx, {width = 420, height = 250} = {}) {
    const [left, right, top, bottom] = [36, 10, 10, 30];
    const svg = svgElement('svg', {viewBox: `0 0 ${width} ${height}`, class: 'scoring-impact-chart', role: 'img'});
    const px = value => left + value * (width - left - right);
    const py = value => top + (1 - value) * (height - top - bottom);
    svg.append(svgElement('rect', {x: left, y: top, width: width - left - right, height: height - top - bottom, fill: 'none', stroke: palette.grid}));
    svg.append(svgElement('line', {x1: px(0), y1: py(0), x2: px(1), y2: py(1), stroke: palette.grid, 'stroke-dasharray': '4 4'}));
    for (const value of [0, .5, 1]) {
      svg.append(svgElement('text', {x: left - 4, y: py(value) + 3, 'text-anchor': 'end', 'font-size': 9.5, fill: palette.muted}, `${value * 100}%`));
      svg.append(svgElement('text', {x: px(value), y: height - bottom + 12, 'text-anchor': 'middle', 'font-size': 9.5, fill: palette.muted}, `${value * 100}%`));
    }
    svg.append(svgElement('text', {x: (left + width - right) / 2, y: height - 4, 'text-anchor': 'middle', 'font-size': 10, fill: palette.muted}, 'Share of the areas, those that move most first'));
    for (const item of operators) {
      const curve = analysis.operators?.[item.operator]?.curve;
      if (!curve?.length) continue;
      svg.append(withTitle(svgElement('polyline', {points: curve.map(([x, y]) => `${px(x).toFixed(1)},${py(y).toFixed(1)}`).join(' '), fill: 'none', stroke: operatorColor(item, ctx, palette), 'stroke-width': 2}), item.label));
    }
    return svg;
  }

  // The difference of each operator on the tests of each campaign.
  function campaignChart(campaigns, operators, palette, ctx, {width = chartWidth, height = 250} = {}) {
    const [left, right, top, bottom] = [52, 16, 12, 30];
    const svg = svgElement('svg', {viewBox: `0 0 ${width} ${height}`, class: 'scoring-impact-chart', role: 'img'});
    const values = campaigns.flatMap(item => Object.values(item.operators || {}));
    const extent = Math.max(NO_CHANGE, ...values.map(Math.abs));
    const px = index => left + (campaigns.length > 1 ? index / (campaigns.length - 1) : .5) * (width - left - right);
    const py = value => top + (extent - value) / (2 * extent) * (height - top - bottom);
    svg.append(svgElement('line', {x1: left, x2: width - right, y1: py(0), y2: py(0), stroke: palette.grid}));
    for (const value of [-extent, 0, extent]) svg.append(svgElement('text', {x: left - 6, y: py(value) + 3, 'text-anchor': 'end', 'font-size': 10, fill: palette.muted}, signed(value)));
    campaigns.forEach((item, index) => svg.append(svgElement('text', {x: px(index), y: height - bottom + 16, 'text-anchor': 'middle', 'font-size': 11, 'font-weight': item.current ? 800 : 500, fill: 'currentColor'}, item.label)));
    for (const operator of operators) {
      const color = operatorColor(operator, ctx, palette);
      const points = campaigns.map((item, index) => [index, item.operators?.[operator.operator]]).filter(([, value]) => value !== null && value !== undefined);
      if (points.length > 1) svg.append(svgElement('polyline', {points: points.map(([index, value]) => `${px(index).toFixed(1)},${py(value).toFixed(1)}`).join(' '), fill: 'none', stroke: color, 'stroke-width': 2}));
      for (const [index, value] of points) svg.append(withTitle(svgElement('circle', {cx: px(index), cy: py(value), r: 4, fill: color, stroke: palette.surface}), `${operator.label} · ${campaigns[index].label}: ${signed(value)}`));
    }
    return svg;
  }

  // ---- Panels ---------------------------------------------------------------------------------------------------------
  // The share of each category or environment of a methodology, as a stacked bar.
  function allocationBars(groups, doc, categoricalColors, field = 'category') {
    const peak = Math.max(1, sum(groups.map(row => row.before)), sum(groups.map(row => row.after)));
    const colorOf = index => categoricalColors[index % categoricalColors.length];
    const row = (name, side) => {
      const bar = element('span', 'scoring-impact-stack');
      groups.forEach((group, index) => {
        const value = Number(group[side]) || 0;
        if (value <= 0) return;
        const segment = element('i', '', value / peak > .05 ? number(value, 0) : '');
        segment.style.width = `${value / peak * 100}%`;
        segment.style.background = colorOf(index);
        segment.title = `${group[field] ?? group.label}: ${number(value, 2)} points`;
        bar.append(segment);
      });
      return element('div', 'scoring-impact-stack-row', element('strong', '', name), bar);
    };
    return element('div', 'scoring-impact-allocation', row(doc.before.profile_name, 'before'), row(doc.after.profile_name, 'after'),
      legend(groups.map((group, index) => ({color: colorOf(index), label: group[field] ?? group.label}))));
  }

  // The changes of a KPI, once per change: the environments with the same change are named together.
  function detailLines(details) {
    const groups = new Map();
    for (const item of details || []) {
      const key = JSON.stringify([item.label, item.before, item.after]);
      if (!groups.has(key)) groups.set(key, {...item, environments: []});
      if (item.environment) groups.get(key).environments.push(item.environment);
    }
    const box = element('div', 'scoring-impact-details');
    for (const item of groups.values()) {
      box.append(element('div', '', element('strong', '', `${item.label}${item.environments.length ? ` (${item.environments.join(', ')})` : ''}: `),
        element('code', '', item.before), ' → ', element('code', '', item.after)));
    }
    return box;
  }

  function conclusionsPanel(section, part) {
    if (!part.conclusions?.length) return;
    const grid = element('div', 'scoring-impact-conclusions');
    for (const item of part.conclusions) {
      const card = element('article', 'scoring-impact-conclusion', element('span', 'scoring-impact-conclusion-title', item.title),
        element('strong', '', item.headline), element('p', '', item.text));
      card.dataset.tone = item.tone || 'neutral';
      grid.append(card);
    }
    section.append(grid);
  }

  function changesPanel(pane, doc, part, palette, ctx) {
    const changes = part.changes;
    const section = ctx.insightSection(pane, `What changed: ${doc.before.profile_name} → ${doc.after.profile_name}`, 'scoring-impact-changes-card', false);
    if (changes.same) {
      section.append(note('Both methodologies are the same: nothing that scores a test changes between them.'));
      return;
    }
    const tiles = element('div', 'scoring-impact-tiles');
    for (const [kind, label] of [['added', 'New KPIs'], ['removed', 'Removed KPIs'], ['points', 'Other points'], ['thresholds', 'Other thresholds'],
      ['calculation', 'Other formula or filters'], ['scoring', 'Other score mapping'], ['definition', 'Other definition'], ['unchanged', 'Unchanged KPIs']]) {
      const count = changes.counts[kind] || 0;
      if (!count && !['added', 'removed', 'unchanged'].includes(kind)) continue;
      const tile = element('div', 'scoring-impact-tile', element('strong', '', number(count, 0)), element('span', '', label));
      tile.dataset.kind = kind;
      tiles.append(tile);
    }
    section.append(tiles);
    const categorical = ctx.theme?.categories || ['#4472C4', '#7030A0', '#C55A11', '#5B9BD5', '#A64D79', '#548235'];
    section.append(subtitle('Points of each category'), allocationBars(changes.categories, doc, categorical));
    const moved = changes.categories.filter(row => Math.abs(row.delta) >= NO_CHANGE);
    section.append(note(moved.length
      ? moved.map(row => `${row.category}: ${number(row.before, 2)} → ${number(row.after, 2)}`).join(' · ')
      : 'Every category keeps its points: a KPI that gives or takes points shares them within its category.'));
    if (changes.environments.some(row => Math.abs(row.delta) >= NO_CHANGE)) {
      section.append(subtitle('Points of each environment'), allocationBars(changes.environments, doc, categorical, 'label'));
    }
    const shifted = changes.kpis.filter(row => Math.abs(row.delta) >= NO_CHANGE).sort((first, second) => second.delta - first.delta);
    if (shifted.length) {
      section.append(subtitle('The points each KPI gains or loses'), divergingChart(shifted.map(row => ({
        label: `${row.kpi}`, value: row.delta, title: `${row.category}: ${number(row.before, 2)} → ${number(row.after, 2)} points`,
      })), palette, {labelWidth: 330}));
    }
    if (changes.settings.length) section.append(subtitle('General settings'), detailLines(changes.settings));
    if (changes.kpis.length) {
      const details = element('details', 'scoring-impact-more-details', element('summary', '', `Each change of the ${changes.kpis.length} KPIs that change`));
      const table = element('table', 'scoring-insight-table scoring-impact-matrix');
      table.createTHead().insertRow().append(...['KPI', 'Category', 'What changes', 'Points', 'Changes'].map(text => element('th', '', text)));
      const body = table.createTBody();
      for (const row of changes.kpis) {
        const line = body.insertRow();
        line.dataset.status = row.status;
        line.insertCell().append(kpiLabel(row));
        line.insertCell().append(row.category || '');
        line.insertCell().append(kindChips(row.kinds, changes.kinds));
        const points = line.insertCell();
        points.className = 'scoring-insight-number';
        points.textContent = `${number(row.before, 2)} → ${number(row.after, 2)}`;
        line.insertCell().append(detailLines(row.details));
      }
      details.append(element('div', 'scoring-insight-table-wrap', table));
      section.append(details);
    }
  }

  function scoringPanel(pane, part, chosen, ctx) {
    const section = ctx.insightSection(pane, 'Impact on the scoring: each operator in All Environments and in each environment', 'scoring-impact-scoring-card', false);
    const combined = part.scoring.Combined || part.scoring[part.environments[0]?.name];
    const operators = part.operators.filter(item => chosen.includes(item.operator));
    if (combined) {
      const scale = Math.max(...operators.map(item => Math.abs(Number(combined.operators[item.operator]?.delta) || 0)), 0);
      const cards = element('div', 'scoring-impact-cards');
      const ordered = [...operators].sort((left, right) => (combined.operators[left.operator]?.rank_after ?? 99) - (combined.operators[right.operator]?.rank_after ?? 99));
      for (const item of ordered) {
        const cell = combined.operators[item.operator];
        if (!cell) continue;
        const tone = toneOf(cell.delta);
        const color = ctx.safeHexColor(item.color);
        const moved = (cell.rank_before || 0) - (cell.rank_after || 0);
        const rank = element('span', `scoring-impact-rank is-${moved > 0 ? 'gain' : moved < 0 ? 'loss' : 'flat'}`,
          cell.rank_before && cell.rank_after && moved ? `${ordinal(cell.rank_before)} → ${ordinal(cell.rank_after)}` : (cell.rank_after ? ordinal(cell.rank_after) : ''));
        const card = element('article', 'scoring-impact-card',
          element('header', '', element('strong', '', `${item.label}${item.is_reference ? ' (reference)' : ''}`), rank),
          element('div', `scoring-impact-big is-${tone}`, signed(cell.delta)),
          track(cell.delta, scale, tone),
          element('small', '', `${number(cell.before, 1)} → ${number(cell.after, 1)} of ${number(combined.max_after, 0)} points`));
        if (color) card.style.setProperty('--operator-color', color);
        cards.append(card);
      }
      section.append(subtitle('All Environments'), cards);
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
    section.append(note('Each difference is the points of the operator with the second methodology minus those with the first one, on the same tests, so it comes from the methodology alone.'));
  }

  function competitionPanel(pane, part, chosen, environment, palette, ctx) {
    const data = part.competition?.[environment];
    if (!data) return;
    const operators = part.operators.filter(item => chosen.includes(item.operator) && data.relative[item.operator] !== undefined);
    if (operators.length < 2) return;
    const section = ctx.insightSection(pane, 'Who it favours and who it hurts, against the other operators', 'scoring-impact-competition-card', false);
    const ordered = [...operators].sort((first, second) => data.relative[second.operator] - data.relative[first.operator]);
    section.append(subtitle(`Each operator against the mean of the operators (${signed(data.mean)})`),
      divergingChart(ordered.map(item => ({label: item.label, value: data.relative[item.operator], color: operatorColor(item, ctx, palette)})), palette, {labelWidth: 150, rowHeight: 30}),
      note('If the change moved every operator alike it would not change anything between them: this is what it changes.'));
    const columns = operators.map(item => ({label: item.label, color: operatorColor(item, ctx, palette)}));
    const rows = operators.map(first => ({
      label: element('strong', '', first.label),
      cells: operators.map((second) => {
        const step = data.matrix[first.operator]?.[second.operator];
        return step ? {value: step.delta, title: `${first.label} against ${second.label}: ${signed(step.before, 1)} → ${signed(step.after, 1)} points`} : null;
      }),
    }));
    section.append(subtitle('Head to head: how much each row gains against each column'), heatTable('Against', columns, rows, palette));
    if (data.margins?.length) {
      const labels = Object.fromEntries(part.operators.map(item => [item.operator, item.label]));
      const margins = element('table', 'scoring-insight-table scoring-impact-matrix');
      margins.createTHead().insertRow().append(...['Operators', 'Distance before', 'Distance after', 'Change', 'Share of the distance'].map(text => element('th', '', text)));
      const body = margins.createTBody();
      for (const step of data.margins) {
        const line = body.insertRow();
        line.insertCell().append(element('strong', '', `${labels[step.operator]} over ${labels[step.next]}`));
        for (const text of [number(step.before, 2), number(step.after, 2)]) {
          const cell = line.insertCell();
          cell.className = 'scoring-insight-number';
          cell.textContent = text;
        }
        const change = line.insertCell();
        change.className = `scoring-insight-number is-${toneOf(step.delta)}`;
        change.textContent = signed(step.delta);
        const share = line.insertCell();
        share.className = 'scoring-insight-number';
        share.textContent = step.share === null ? 'N/A' : `${number(step.share * 100, 1)}%`;
      }
      section.append(subtitle('The distance between one position and the next'), element('div', 'scoring-insight-table-wrap', margins),
        note('Share of the distance: how much of the distance between two operators the methodology gives or takes. Near 100% the position could change.'));
    }
  }

  function driversPanel(pane, part, chosen, environment, palette, ctx) {
    const data = part.drivers?.[environment];
    if (!data) return;
    const operators = part.operators.filter(item => chosen.includes(item.operator) && data[item.operator]);
    if (!operators.length) return;
    const section = ctx.insightSection(pane, 'Why each operator moves', 'scoring-impact-drivers-card', false);
    const colours = {weights: ctx.theme?.categories?.[0] || '#4472C4', rules: ctx.theme?.categories?.[2] || '#C55A11', new: palette.gain, removed: palette.loss};
    const meta = Object.entries(CAUSES).map(([key, label]) => ({key, label, color: colours[key]}))
      .filter(item => operators.some(operator => Math.abs(data[operator.operator].causes[item.key] || 0) >= NO_CHANGE));
    section.append(subtitle('What causes the difference of each operator'), stackedDiverging(operators.map(item => ({
      label: item.label, color: operatorColor(item, ctx, palette), parts: data[item.operator].causes, total: data[item.operator].total,
    })), meta, palette), legend(meta),
    note('Points moved between KPIs: what the operator gains or loses at the same score, because a KPI is worth other points. Other thresholds, formula or filters: what scores differently with its new maximum.'));
    const {grid, width} = smallMultiples(operators.length);
    for (const item of operators) {
      const categories = Object.entries(data[item.operator].categories).filter(([, value]) => Math.abs(value.delta) >= NO_CHANGE)
        .map(([label, value]) => ({label, value: value.delta}));
      if (!categories.length) continue;
      grid.append(element('figure', 'scoring-chart-card scoring-impact-figure', element('figcaption', '', item.label),
        waterfallChart(categories, data[item.operator].total, palette, {color: operatorColor(item, ctx, palette), width})));
    }
    if (grid.childElementCount) section.append(subtitle('From category to category, up to its total'), grid);
  }

  function exposurePanel(pane, part, chosen, environment, palette, ctx) {
    const data = part.exposure?.[environment];
    if (!data || data.kpis < 3) return;
    const section = ctx.insightSection(pane, 'With or against the strengths of each operator', 'scoring-impact-exposure-card', false);
    const operators = part.operators.filter(item => chosen.includes(item.operator) && data.operators[item.operator]?.points?.length);
    const {grid, width} = smallMultiples(operators.length);
    for (const item of operators) {
      const entry = data.operators[item.operator];
      const color = operatorColor(item, ctx, palette);
      const reading = entry.r === null ? 'no correlation' : `r = ${signed(entry.r)}`;
      grid.append(element('figure', 'scoring-chart-card scoring-impact-figure', element('figcaption', '', item.label, element('small', '', ` · ${reading}`)),
        scatterChart(entry.points, palette, {xLabel: 'Points the KPI gains or loses', yLabel: 'Against the mean (score %)', fit: entry.r === null ? null : entry.fit, color, width,
          describe: point => `${point.kpi} (${point.category})\nThe KPI: ${signed(point.x)} points\n${item.label} against the mean: ${signed(point.y, 1)} points of score %`})));
    }
    section.append(grid);
    const table = element('table', 'scoring-insight-table scoring-impact-matrix');
    table.createTHead().insertRow().append(...['Operator', 'Correlation', 'Reads', 'What the points moved give it, against the others'].map(text => element('th', '', text)));
    const body = table.createTBody();
    for (const item of operators) {
      const entry = data.operators[item.operator];
      const line = body.insertRow();
      const name = element('strong', '', item.label);
      name.style.color = operatorColor(item, ctx, palette);
      line.insertCell().append(name);
      const r = line.insertCell();
      r.className = 'scoring-insight-number';
      r.textContent = entry.r === null ? 'N/A' : number(entry.r, 2);
      const size = Math.abs(entry.r ?? 0);
      line.insertCell().append(entry.r === null ? 'No correlation'
        : size < .3 ? 'No clear relation' : `${size >= .7 ? 'Strong' : size >= .5 ? 'Moderate' : 'Weak'}: the points go ${entry.r > 0 ? 'towards' : 'away from'} its strengths`);
      const net = line.insertCell();
      net.className = `scoring-insight-number is-${toneOf(entry.net)}`;
      net.textContent = signed(entry.net);
    }
    section.append(element('div', 'scoring-insight-table-wrap', table),
      note(`Each dot is one of the ${data.kpis} KPIs with other points: right, the methodology gives it points; up, the operator beats the mean of the operators in it. A line that rises means the points go towards its strengths. With few KPIs, a correlation is only a hint.`));
  }

  function categoryPanel(pane, part, chosen, environment, ctx) {
    const rows = part.categories[environment] || [];
    if (!rows.length) return;
    const section = ctx.insightSection(pane, 'Impact per category', 'scoring-impact-category-card', false);
    const operators = part.operators.filter(item => chosen.includes(item.operator));
    const scoring = part.scoring[environment];
    const total = scoring ? {label: element('strong', '', 'Total'), cells: scoring.operators} : null;
    section.append(matrix('Category', operators, rows.map(row => ({
      label: element('div', 'scoring-impact-label', element('strong', '', row.category),
        element('small', '', `${row.service} · maximum ${number(row.max_before, 1)} → ${number(row.max_after, 1)}`)),
      cells: row.operators,
    })), ctx, {total}));
    section.append(note('The points of each category with both methodologies; the colour and bar show the difference, against the largest of the table.'));
  }

  function kpiPanel(pane, part, chosen, environment, palette, ctx) {
    const all = part.kpis[environment] || [];
    const rows = all.filter(row => (row.kinds || []).length || row.peak >= NO_CHANGE);
    if (!rows.length) {
      ctx.insightSection(pane, 'KPIs affected', 'scoring-impact-kpi-card', false).append(note('No KPI changes.'));
      return;
    }
    const section = ctx.insightSection(pane, `KPIs affected: ${rows.length} of ${all.length}, those that move most first`, 'scoring-impact-kpi-card', false);
    const operators = part.operators.filter(item => chosen.includes(item.operator));
    const {grid, width} = smallMultiples(operators.length);
    for (const item of operators) {
      const moved = rows.map(row => ({label: row.kpi, value: row.operators[item.operator]?.delta, category: row.category}))
        .filter(row => row.value !== null && row.value !== undefined && Math.abs(row.value) >= NO_CHANGE)
        .sort((first, second) => Math.abs(second.value) - Math.abs(first.value)).slice(0, 8).sort((first, second) => second.value - first.value);
      if (!moved.length) continue;
      grid.append(element('figure', 'scoring-chart-card scoring-impact-figure', element('figcaption', '', item.label),
        divergingChart(moved.map(row => ({label: row.label, value: row.value, title: `${row.category} · ${row.label}: ${signed(row.value)}`})), palette, {labelWidth: 230, valueWidth: 48, rowHeight: 24, width})));
    }
    if (grid.childElementCount) section.append(subtitle('The KPIs that move each operator most'), grid);
    const heatRows = rows.slice(0, 20).map(row => ({
      label: kpiLabel(row, element('small', '', row.category)),
      cells: operators.map(item => {
        const cell = row.operators[item.operator];
        return cell ? {value: cell.delta, title: `${item.label}: ${number(cell.before, 2)} → ${number(cell.after, 2)} points\nKPI value: ${number(cell.value_before, 2)} → ${number(cell.value_after, 2)}`} : null;
      }),
    }));
    section.append(subtitle('The KPIs against the operators'), heatTable('KPI', operators.map(item => ({label: item.label, color: operatorColor(item, ctx, palette)})), heatRows, palette));
    const titleOf = (item, cell) => (cell ? `${item.label}\nKPI value: ${number(cell.value_before, 2)} → ${number(cell.value_after, 2)}\nScore: ${number((cell.score_before ?? NaN) * 100, 1)}% → ${number((cell.score_after ?? NaN) * 100, 1)}%` : '');
    section.append(element('details', 'scoring-impact-more-details', element('summary', '', 'Each KPI with its points before and after'),
      pagedRows(`kpis:${environment}`, rows, shown => matrix('KPI', operators, shown.map(row => ({
        label: kpiLabel(row, element('small', '', `${row.category} · maximum ${number(row.max_before, 1)} → ${number(row.max_after, 1)}`)),
        extra: [kindChips(row.kinds, part.changes.kinds)], cells: row.operators, titleOf,
      })), ctx, {extraHeaders: ['What changes']}))));
    section.append(note('A KPI one methodology does not have counts none there. Hover a cell for the value and the score of the KPI with both methodologies.'));
  }

  // ---- Maps ---------------------------------------------------------------------------------------------------------------
  function diagramOfMap(payload, shapes, item, palette, scale, relative) {
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
    const describe = (name, cell) => (cell ? `${name}\n${item.label}: ${signed(cell.value)} ${unitText}${relative ? ' against the other operators' : ''}`
      + `${payload.measure === 'own' ? `\nScoring: ${number(cell.before, 1)} → ${number(cell.after, 1)}` : `\nPoints lost: ${number(cell.before, 2)} → ${number(cell.after, 2)}`}${cell.tests ? `\nTests: ${number(cell.tests, 0)}` : ''}` : `${name}: no tests of ${item.label}`);
    for (const ring of outlines) svg.append(svgElement('path', {d: pathOf(ring), fill: palette.zero, stroke: palette.surface, 'stroke-width': .5}));
    for (const [name, ring] of rings) {
      const cell = values.get(name);
      svg.append(withTitle(svgElement('path', {d: pathOf(ring), fill: cell ? heatColor(cell.value, scale, palette) : palette.zero, stroke: palette.surface, 'stroke-width': .5}), describe(name, cell)));
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

  function colourScale(scale, palette, unit) {
    const bar = element('span', 'scoring-impact-scale');
    bar.style.background = `linear-gradient(90deg, ${palette.loss}, ${palette.zero} 50%, ${palette.gain})`;
    return element('div', 'scoring-impact-scale-row', element('span', '', signed(-scale)), bar, element('span', '', signed(scale)), element('small', '', unit));
  }

  async function loadGeometry(ctx, doc, field) {
    const key = `${doc.key}|${field}`;
    if (!geometry.has(key)) {
      geometry.set(key, ctx.requestJson(`/api/scoring/saved-filters/${encodeURIComponent(ctx.savedFilterId)}/impact/boundaries/${encodeURIComponent(field)}?key=${doc.key}`)
        .catch(() => ({boundaries: {}, outlines: []})));
    }
    return geometry.get(key);
  }

  function spreadPanels(body, payload, part, chosen, palette, ctx) {
    const operators = part.operators.filter(item => chosen.includes(item.operator) && payload.analysis.operators?.[item.operator]);
    if (!operators.length) return;
    const rows = payload.rows;
    const analysis = payload.analysis;
    body.append(subtitle(`How the impact spreads among the ${rows.length} ${payload.label} areas`),
      spreadChart(rows, operators, analysis, palette, ctx),
      note('Each dot is an area that moves; the box holds the middle half of the areas of the operator and the line inside it their median. A wide spread means the methodology hits some areas more than others.'));
    const table = element('table', 'scoring-insight-table scoring-impact-matrix');
    table.createTHead().insertRow().append(...['Operator', 'Areas up', 'Areas down', 'Total', 'Typical spread', `Share of the top ${analysis.operators[operators[0].operator].concentration_areas} areas`, 'Against the value before', 'Against the tests'].map(text => element('th', '', text)));
    const lines = table.createTBody();
    for (const item of operators) {
      const entry = analysis.operators[item.operator];
      const line = lines.insertRow();
      const name = element('strong', '', item.label);
      name.style.color = operatorColor(item, ctx, palette);
      line.insertCell().append(name);
      for (const [text, className] of [[number(entry.up, 0), ''], [number(entry.down, 0), ''], [signed(entry.total), `is-${toneOf(entry.total)}`], [number(entry.deviation, 3), ''],
        [entry.concentration === null ? 'N/A' : `${number(entry.concentration * 100, 0)}%`, ''], [entry.r_before === null ? 'N/A' : `r = ${number(entry.r_before, 2)}`, ''], [entry.r_tests === null ? 'N/A' : `r = ${number(entry.r_tests, 2)}`, '']]) {
        const cell = line.insertCell();
        cell.className = `scoring-insight-number ${className}`.trim();
        cell.textContent = text;
      }
    }
    body.append(element('div', 'scoring-insight-table-wrap', table));
    const {grid: pair, width: pairWidth} = smallMultiples(2);
    pair.append(element('figure', 'scoring-chart-card scoring-impact-figure', element('figcaption', '', 'How concentrated the movement is'),
      concentrationChart(operators, analysis, palette, ctx, {width: pairWidth}), legend(operators.map(item => ({color: operatorColor(item, ctx, palette), label: item.label})))));
    if (operators.length > 1) {
      const columns = operators.map(item => ({label: item.label, color: operatorColor(item, ctx, palette)}));
      pair.append(element('figure', 'scoring-chart-card scoring-impact-figure', element('figcaption', '', 'Do the operators move together in the same areas?'),
        heatTable('Correlation', columns, operators.map(first => ({
          label: element('strong', '', first.label),
          cells: operators.map(second => (first.operator === second.operator ? null : {value: analysis.together?.[first.operator]?.[second.operator] ?? null,
            title: `${first.label} and ${second.label}`})),
        })), palette, {scale: 1, format: value => number(value, 2)}),
        note('Near +1: the same areas move for both, so it comes from the tests of the area. Near 0: each operator moves in its own areas.')));
    }
    body.append(pair);
    const measureBefore = payload.measure === 'own' ? 'Scoring of the area before' : 'National points lost before';
    const {grid: scatterGrid, width: scatterWidth} = smallMultiples(operators.length);
    for (const item of operators) {
      const entry = analysis.operators[item.operator];
      const points = rows.map(row => ({name: row.name, cell: row.cells[item.operator]})).filter(({cell}) => cell && cell.before !== null && cell.before !== undefined && cell.value !== null && cell.value !== undefined)
        .map(({name, cell}) => ({name, x: cell.before, y: cell.value})).sort((first, second) => Math.abs(second.y) - Math.abs(first.y)).slice(0, 300);
      if (points.length < 3) continue;
      scatterGrid.append(element('figure', 'scoring-chart-card scoring-impact-figure',
        element('figcaption', '', item.label, element('small', '', entry.r_before === null ? '' : ` · r = ${number(entry.r_before, 2)}`)),
        scatterChart(points, palette, {xLabel: measureBefore, yLabel: 'Difference', fit: entry.r_before === null ? null : entry.fit_before, color: operatorColor(item, ctx, palette), showZeroX: false, width: scatterWidth,
          describe: point => `${point.name}\nBefore: ${number(point.x, 2)}\nDifference: ${signed(point.y)}`})));
    }
    if (scatterGrid.childElementCount) body.append(subtitle(`Does it depend on the area? The difference against the ${measureBefore.toLowerCase()}`), scatterGrid);
  }

  function mapsPanel(pane, doc, part, chosen, environment, palette, ctx) {
    const section = ctx.insightSection(pane, 'Maps: one methodology against the other', 'scoring-impact-maps-card', false);
    const controls = element('div', 'scoring-loss-controls');
    const body = element('div', 'scoring-impact-maps-body', element('div', 'scoring-empty', 'Loading the maps…'));
    section.append(controls, body);
    const token = renderToken;
    const drawMap = async () => {
      const query = {key: doc.key, scoring: doc.scorings[ctx.scoring] ? ctx.scoring : 'best_network', environment, field: choices.field || '', measure: choices.measure, relative: choices.compare === 'relative'};
      const cacheKey = JSON.stringify(query);
      let payload = mapData.get(cacheKey);
      if (!payload) {
        try {
          payload = await ctx.requestJson(`/api/scoring/saved-filters/${encodeURIComponent(ctx.savedFilterId)}/impact/map?${new URLSearchParams(query)}`);
          mapData.set(cacheKey, payload);
        } catch (error) {
          body.replaceChildren(element('div', 'scoring-empty', error.message || 'The maps could not be read.'));
          return;
        }
      }
      if (token !== renderToken) return;
      choices.field = payload.field;
      choices.measure = payload.measure;
      const names = {City: 'City', Region: 'Region', Cluster: 'Cluster', Area: payload.area_label || 'Map Area', 'Postal Code': 'Postal Code'};
      controls.replaceChildren(
        selectField('Map per', ['City', 'Region', 'Cluster', 'Area', 'Postal Code'].map(name => [name, names[name], !payload.available.includes(name)]), payload.field, (value) => { choices.field = value; drawMap(); }),
        selectField('Measure', [['national', 'National points'], ['rate', 'National points per 1,000 tests'], ['own', 'Scoring of the area']].map(([value, text]) => [value, text, !payload.measures.includes(value)]), payload.measure, (value) => { choices.measure = value; drawMap(); }),
        selectField('Show', [['each', 'What moves for each operator'], ['relative', 'Against the other operators']], choices.compare, (value) => { choices.compare = value; drawMap(); }));
      body.replaceChildren();
      if (doc.maps_error) body.append(note(`The National points could not be mapped: ${doc.maps_error}. The scoring of each area is still shown.`));
      if (!payload.rows.length) {
        body.append(element('div', 'scoring-empty', 'These tests have no values for this map.'));
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
          title.style.color = operatorColor(item, ctx, palette);
          const svg = diagramOfMap(payload, shapes, item, palette, scale, payload.relative);
          const figure = element('div', 'scoring-loss-map-figure', svg);
          const card = element('article', 'scoring-loss-map-card scoring-impact-map-card', title, figure);
          if (summary) {
            const lists = element('div', 'scoring-impact-ranked-pair');
            if (summary.top?.length) lists.append(element('div', '', element('strong', 'is-gain', 'Gains most'), rankedList(summary.top.slice(0, 6), 'gain')));
            if (summary.bottom?.length) lists.append(element('div', '', element('strong', 'is-loss', 'Loses most'), rankedList(summary.bottom.slice(0, 6), 'loss')));
            card.append(lists);
          }
          grid.append(card);
        }
        body.append(colourScale(scale, palette, unit), grid);
        grid.querySelectorAll('.scoring-loss-map-figure').forEach(figure => ctx.enableMapZoom?.(figure, figure.querySelector('svg')));
      } else {
        body.append(note(`The ${payload.label} areas have no polygons or positions to draw: their values are below.`));
      }
      if (payload.attribution) body.append(note(payload.attribution));
      body.append(note(payload.measure === 'own'
        ? 'Scoring of the area: its own scoring (scaled to the full maximum in All Environments) with the second methodology minus the first one.'
        : 'National points: what the area gives or takes of the National scoring of the operator, so they add up to its difference. Green: it loses fewer points with the second methodology; red: it loses more.'
          + (payload.measure === 'rate' ? ' Per 1,000 tests, so an area does not move only because it was measured more; the areas with few tests are left out.' : '')));
      spreadPanels(body, payload, part, chosen, palette, ctx);
    };
    drawMap();
  }

  function areaCubePanel(pane, part, chosen, environment, palette, ctx) {
    const levels = Object.keys(part.area_categories || {});
    if (!levels.length) return;
    const section = ctx.insightSection(pane, 'Which categories move in which areas', 'scoring-impact-cube-card', false);
    const operators = part.operators.filter(item => chosen.includes(item.operator));
    if (!levels.includes(choices.cube)) choices.cube = levels[levels.length - 1];
    if (!operators.some(item => item.operator === choices.cubeOperator)) choices.cubeOperator = operators[0]?.operator;
    const body = element('div');
    const drawCube = () => {
      const rows = part.area_categories[choices.cube]?.[environment] || [];
      const name = choices.cubeOperator;
      const categories = [...new Set(rows.flatMap(row => Object.keys(row.categories)))].filter(category => rows.some(row => Math.abs(row.categories[category]?.[name] || 0) >= NO_CHANGE));
      const ranked = rows.map(row => ({row, peak: Math.max(0, ...categories.map(category => Math.abs(row.categories[category]?.[name] || 0)))})).filter(item => item.peak >= NO_CHANGE)
        .sort((first, second) => second.peak - first.peak).slice(0, 20);
      body.replaceChildren(ranked.length ? heatTable(choices.cube, categories, ranked.map(({row}) => ({
        label: element('strong', '', row.area),
        cells: categories.map(category => ({value: row.categories[category]?.[name] ?? null, title: `${row.area} · ${category}: ${signed(row.categories[category]?.[name] ?? 0)} points of the area`})),
      })), palette) : note('No category moves in these areas for this operator.'));
    };
    section.append(ctx.insightControls(
      selectField('Area', levels.map(name => [name, name]), choices.cube, (value) => { choices.cube = value; drawCube(); }),
      selectField('Operator', operators.map(item => [item.operator, item.label]), choices.cubeOperator, (value) => { choices.cubeOperator = value; drawCube(); })), body,
    note('The difference of each category in the scoring of each area, the areas that move most first (up to 20).'));
    drawCube();
  }

  function areaTablePanel(pane, part, chosen, environment, ctx) {
    const levels = Object.keys(part.areas || {});
    if (!levels.length) return;
    const section = ctx.insightSection(pane, 'Who leads each area, before and after', 'scoring-impact-area-card', false);
    if (!levels.includes(choices.table)) choices.table = levels[0];
    const body = element('div');
    const drawTable = (name) => {
      const rows = part.areas[name]?.[environment] || [];
      const operators = part.operators.filter(item => chosen.includes(item.operator));
      const swaps = rows.filter(row => row.leader_before !== row.leader_after);
      const labels = Object.fromEntries(part.operators.map(item => [item.operator, item.label]));
      body.replaceChildren(pagedRows(`areas:${name}:${environment}`, rows, shown => matrix(name, operators, shown.map(row => ({
        label: element('strong', '', row.area), cells: row.operators,
        extra: [row.leader_before === row.leader_after ? element('span', 'scoring-impact-leader', labels[row.leader_after] || row.leader_after || '')
          : element('span', 'scoring-impact-leader is-changed', `${labels[row.leader_before] || row.leader_before} → ${labels[row.leader_after] || row.leader_after}`)],
      })), ctx, {extraHeaders: ['Leader']})),
      note(`${rows.length} ${name} areas, those that move most first; the leader changes in ${swaps.length}. Each is scored on the whole country, as the Geographical Areas; in All Environments the environments measured in an area are scaled to the full maximum.`));
    };
    section.append(ctx.insightControls(selectField('Area', levels.map(name => [name, name]), choices.table, (value) => { choices.table = value; drawTable(value); })), body);
    drawTable(choices.table);
  }

  function servingPanel(pane, part, chosen, environment, ctx) {
    const fields = {Vendor: 'Vendor of the serving cell', 'Site Type': 'Kind of site of the serving cell'};
    const present = Object.keys(fields).filter(name => (part.serving?.[name]?.[environment] || []).some(row => row.peak >= NO_CHANGE));
    if (!present.length) return;
    const section = ctx.insightSection(pane, 'Who serves the tests that move', 'scoring-impact-serving-card', false);
    const operators = part.operators.filter(item => chosen.includes(item.operator));
    for (const name of present) {
      section.append(subtitle(fields[name]), matrix(fields[name], operators, part.serving[name][environment].filter(row => row.peak >= NO_CHANGE).map(row => ({
        label: element('strong', '', row.name), cells: row.operators,
      })), ctx, {digits: 2}));
    }
    section.append(note('What the operator gains (positive) or loses of its National scoring in the tests served by each one; below each figure, the National points lost with the first and the second methodology.'));
  }

  function gapPanel(pane, part, chosen, environment, palette, ctx) {
    const gap = part.gap[environment];
    if (!gap) return;
    const reference = part.operators.find(item => item.is_reference);
    const section = ctx.insightSection(pane, `Impact on the GAP Analysis against ${reference?.label || part.reference}`, 'scoring-impact-gap-card', false);
    const operators = part.operators.filter(item => chosen.includes(item.operator) && !item.is_reference);
    if (!operators.length) {
      section.append(note('Enable an operator other than the reference to see its GAP.'));
      return;
    }
    section.append(subtitle('How much the GAP of each operator moves'), divergingChart(operators.filter(item => gap.total[item.operator]).map(item => {
      const cell = gap.total[item.operator];
      return {label: `${item.label}: ${signed(cell.before, 1)} → ${signed(cell.after, 1)}${cell.flip ? ' (changes side)' : ''}`, value: cell.delta, color: operatorColor(item, ctx, palette)};
    }).sort((first, second) => second.value - first.value), palette, {labelWidth: 280, rowHeight: 30}));
    const total = {label: element('strong', '', 'Total GAP'), cells: gap.total};
    section.append(matrix('Category', operators, gap.categories.map(row => ({label: element('strong', '', row.category), cells: row.operators})), ctx, {total}));
    const kpis = gap.kpis.filter(row => row.peak >= NO_CHANGE);
    if (kpis.length) {
      section.append(element('details', 'scoring-impact-more-details', element('summary', '', 'The KPIs whose GAP moves most'),
        pagedRows(`gap:${environment}`, kpis, shown => matrix('KPI', operators, shown.map(row => ({
          label: kpiLabel(row, element('small', '', row.category)), cells: row.operators,
        })), ctx))));
    }
    section.append(note('Operator minus reference, before → after; the bar shows how much the GAP moves. Changes side: the operator goes from ahead of the reference to behind it, or the other way round.'));
  }

  function pointsPanel(pane, part, chosen, environment, ctx) {
    const lost = part.points_lost[environment];
    if (!lost) return;
    const section = ctx.insightSection(pane, 'Impact on the Points Lost', 'scoring-impact-points-card', false);
    const operators = part.operators.filter(item => chosen.includes(item.operator) && lost.operators[item.operator]);
    const shown = lost.kinds.filter(kind => (kind.kpis || []).length || operators.some(item => lost.operators[item.operator].parts_before?.[kind.key] || lost.operators[item.operator].parts_after?.[kind.key]));
    const [notCompleted, minimum, below, quality] = ctx.theme?.stake || ['#6e1222', '#a51c30', '#e8414f', '#f4a3aa'];
    const colours = {not_completed: notCompleted, below_minimum: minimum, below_par: below, quality};
    const peak = Math.max(1, ...operators.flatMap(item => [lost.operators[item.operator].before, lost.operators[item.operator].after].map(value => Number(value) || 0)));
    const bar = (parts) => {
      const box = element('span', 'scoring-impact-stack');
      for (const kind of shown) {
        const value = Number(parts?.[kind.key]) || 0;
        if (value <= 0) continue;
        const segment = element('i', '', value / peak > .08 ? number(value, 0) : '');
        segment.style.width = `${value / peak * 100}%`;
        segment.style.background = colours[kind.key];
        segment.title = `${kind.label}: ${number(value, 2)} points`;
        box.append(segment);
      }
      return box;
    };
    const list = element('div', 'scoring-impact-lost');
    for (const item of operators) {
      const row = lost.operators[item.operator];
      const name = element('strong', '', `${item.label}${item.is_reference ? ' (reference)' : ''}`);
      const color = ctx.safeHexColor(item.color);
      if (color) name.style.color = color;
      const tone = toneOf(row.delta, true);
      list.append(element('div', 'scoring-impact-lost-row', name,
        element('div', 'scoring-impact-lost-bars', bar(row.parts_before), bar(row.parts_after)),
        element('div', 'scoring-impact-lost-total', element('b', `is-${tone}`, signed(row.delta)), element('small', '', `${number(row.before, 1)} → ${number(row.after, 1)} lost`))));
    }
    section.append(list, legend(shown.map(kind => ({color: colours[kind.key], label: kind.label}))), note('In each operator, the upper bar is the first methodology and the lower one the second.'));
    const inScope = part.operators.filter(item => chosen.includes(item.operator));
    section.append(subtitle('Points lost per category'),
      matrix('Category', inScope, lost.categories.map(row => ({label: element('strong', '', row.category), cells: row.operators})), ctx, {inverse: true}));
    const kpis = lost.kpis.filter(row => row.peak >= NO_CHANGE);
    if (kpis.length) {
      section.append(element('details', 'scoring-impact-more-details', element('summary', '', 'The KPIs whose points lost move most'),
        pagedRows(`lost:${environment}`, kpis, rows => matrix('KPI', inScope, rows.map(row => ({
          label: kpiLabel(row, element('small', '', row.category)), cells: row.operators,
        })), ctx, {inverse: true}))));
    }
    section.append(note('More points lost are shown in the colour of a loss. The points lost of a KPI are its maximum minus the points scored, so they also move when the methodology gives it another maximum.'));
  }

  function stabilityPanel(pane, doc, part, chosen, palette, ctx) {
    const data = part.stability;
    const campaigns = data?.campaigns || [];
    if (campaigns.length < 2) return;
    const section = ctx.insightSection(pane, 'Is it stable? The same change on the tests of other campaigns', 'scoring-impact-stability-card', false);
    const comparable = campaigns.filter(item => item.comparable).sort((first, second) => (globalThis.campaignCompare?.(first.campaign, second.campaign) ?? 0));
    const operators = part.operators.filter(item => chosen.includes(item.operator));
    if (comparable.length > 1) {
      section.append(campaignChart(comparable, operators, palette, ctx), legend(operators.map(item => ({color: operatorColor(item, ctx, palette), label: item.label}))));
      const table = element('table', 'scoring-insight-table scoring-impact-matrix');
      table.createTHead().insertRow().append(...['Operator', 'Campaigns up', 'Campaigns down', 'Mean', 'From', 'To'].map(text => element('th', '', text)));
      const body = table.createTBody();
      for (const item of operators) {
        const entry = data.summary[item.operator];
        if (!entry) continue;
        const line = body.insertRow();
        const name = element('strong', '', item.label);
        name.style.color = operatorColor(item, ctx, palette);
        line.insertCell().append(name);
        for (const [text, className] of [[number(entry.up, 0), ''], [number(entry.down, 0), ''], [signed(entry.mean), `is-${toneOf(entry.mean)}`], [signed(entry.low), ''], [signed(entry.high), '']]) {
          const cell = line.insertCell();
          cell.className = `scoring-insight-number ${className}`.trim();
          cell.textContent = text;
        }
      }
      section.append(element('div', 'scoring-insight-table-wrap', table));
    }
    const left = campaigns.filter(item => !item.comparable);
    if (left.length) {
      const kpis = [...new Set(left.flatMap(item => item.missing || []))];
      section.append(note(`${left.map(item => item.label).join(', ')} cannot be compared: ${kpis.length ? `they have no tests of ${kpis.slice(0, 4).join(', ')}${kpis.length > 4 ? '…' : ''}` : 'they have no results'}.`));
    }
    section.append(note(`What ${doc.after.profile_name} gives against ${doc.before.profile_name} on the same tests of each campaign. It says nothing of how the network changes between them: only whether the methodology moves each operator the same way every time.`));
  }

  function comparisonBanner(doc, part) {
    const side = (title, summary, source) => element('div', 'scoring-impact-side', element('span', '', title), element('strong', '', summary.profile_name), source ? element('small', '', `of ${source}`) : null);
    return element('div', 'scoring-impact-banner', side('First methodology', doc.before, doc.methodology_of?.before), element('span', 'scoring-impact-arrow', '→'), side('Second methodology', doc.after, doc.methodology_of?.after),
      element('div', 'scoring-impact-side', element('span', '', 'Tests scored with both'), element('strong', '', `${doc.after.campaign_label} · ${doc.nr_mode}`)),
      element('div', 'scoring-impact-side', element('span', '', 'GAP reference'), element('strong', '', part.operators.find(item => item.is_reference)?.label || part.reference)));
  }

  function draw(body, doc, ctx) {
    body.replaceChildren();
    if (doc.same_methodology) {
      const section = ctx.insightSection(body, 'Methodology Impact', 'scoring-impact-head-card', false);
      section.append(note(`Both campaigns are scored with ${doc.before.profile_name}, so the methodology changes nothing between them. Choose two campaigns with different methodologies, or Two methodologies.`));
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
    const palette = paletteOf(ctx, body);
    chartWidth = Math.max(280, (body.parentElement?.clientWidth || 900) - 64);
    const {control, chosen} = ctx.insightOperatorChips('impact-operators', part.operators, {all: true});
    chosenOperators = chosen;
    const head = ctx.insightSection(body, `Methodology Impact${scoring === 'most_reliable' ? ' — Most Reliable Network' : ''}`, 'scoring-impact-head-card', false);
    head.append(comparisonBanner(doc, part));
    if (scoring !== ctx.scoring) head.append(note('The Most Reliable scoring is not compared: one of the methodologies does not have it. This is the Best Network scoring.'));
    head.append(subtitle('What stands out'));
    conclusionsPanel(head, part);
    if (doc.notes.length) head.append(...doc.notes.map(note));
    head.append(ctx.insightControls(control));
    changesPanel(body, doc, part, palette, ctx);
    scoringPanel(body, part, chosen, ctx);
    competitionPanel(body, part, chosen, environment, palette, ctx);
    driversPanel(body, part, chosen, environment, palette, ctx);
    exposurePanel(body, part, chosen, environment, palette, ctx);
    categoryPanel(body, part, chosen, environment, ctx);
    kpiPanel(body, part, chosen, environment, palette, ctx);
    mapsPanel(body, doc, part, chosen, environment, palette, ctx);
    areaCubePanel(body, part, chosen, environment, palette, ctx);
    areaTablePanel(body, part, chosen, environment, ctx);
    servingPanel(body, part, chosen, environment, ctx);
    gapPanel(body, part, chosen, environment, palette, ctx);
    pointsPanel(body, part, chosen, environment, ctx);
    stabilityPanel(body, doc, part, chosen, palette, ctx);
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
