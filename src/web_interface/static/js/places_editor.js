/* Free layouts of the Designer (ticket #26, phase 4): the places of a slide adjusted on a grid.

   The rows and columns of the grid are resized by dragging the lines between them, and neighbouring places are merged
   into one (a chart over two columns) or split again. The result is the geometry of the places, as fractions of the chart
   area of the slide's layout (the same coordinates the viewer lays charts out with, and the PPT export places them by),
   kept with the grid it came from so it can be adjusted again. */
(() => {
  'use strict';
  const h = (tag, props = {}, ...children) => {
    const element = document.createElement(tag);
    for (const [key, value] of Object.entries(props || {})) {
      if (value === undefined || value === null || value === false) continue;
      if (key === 'class') element.className = value;
      else if (key === 'text') element.textContent = value;
      else if (key === 'style') Object.assign(element.style, value);
      else if (key === 'dataset') Object.assign(element.dataset, value);
      else if (key.startsWith('on') && typeof value === 'function') element.addEventListener(key.slice(2), value);
      else if (typeof value === 'boolean') element.toggleAttribute(key, value);
      else element.setAttribute(key, value);
    }
    element.append(...children.flat().filter(child => child !== null && child !== undefined && child !== false));
    return element;
  };
  const GUTTER = 2;
  const MINIMUM = 0.08;
  const sum = values => values.reduce((total, value) => total + value, 0);
  const normalized = values => { const total = sum(values) || 1; return values.map(value => value / total); };

  /** A grid of rows × columns, each place one cell. */
  function gridSpec(rows, columns) {
    const areas = [];
    for (let row = 0; row < rows; row += 1) for (let column = 0; column < columns; column += 1) areas.push([row, column, 1, 1]);
    return {rows: Array(rows).fill(1 / rows), columns: Array(columns).fill(1 / columns), areas};
  }
  // The places of a grid as rectangles in percent of the chart area, in reading order, with a gutter between them.
  function geometry(spec) {
    const rowStart = index => sum(spec.rows.slice(0, index)) * 100;
    const columnStart = index => sum(spec.columns.slice(0, index)) * 100;
    const ordered = [...spec.areas].sort((left, right) => left[0] - right[0] || left[1] - right[1]);
    return ordered.map(([row, column, rowSpan, columnSpan]) => {
      const x = columnStart(column), y = rowStart(row);
      const width = columnStart(column + columnSpan) - x, height = rowStart(row + rowSpan) - y;
      const left = column > 0 ? GUTTER / 2 : 0, right = column + columnSpan < spec.columns.length ? GUTTER / 2 : 0;
      const top = row > 0 ? GUTTER / 2 : 0, bottom = row + rowSpan < spec.rows.length ? GUTTER / 2 : 0;
      return [x + left, y + top, width - left - right, height - top - bottom].map(value => Math.round(value * 1000) / 1000);
    });
  }
  const covers = (area, row, column) => row >= area[0] && row < area[0] + area[2] && column >= area[1] && column < area[1] + area[3];

  /** Open the editor. options: {title, grid: {rows, columns, areas} or null, rows, columns (of the layout), labels (what each
   *  place holds now, by place), onSave(result)}
   *  where result is {grid, geometry, mapping: old place -> new place (or -1 when merged away)} or null to reset. */
  function open(options) {
    let spec = options.grid && Array.isArray(options.grid.areas) ? structuredClone(options.grid) : gridSpec(options.rows || 1, options.columns || 1);
    spec.rows = normalized(spec.rows); spec.columns = normalized(spec.columns);
    const original = structuredClone(spec);
    let selected = new Set();
    const overlay = h('div', {class: 'confirm-overlay ds-overlay ds-secondary ppt-designer ds-design-dialog-overlay'});
    const board = h('div', {class: 'ds-layout-board', role: 'application', 'aria-label': 'Places of the slide'});
    const note = h('p', {class: 'form-note', text: 'Drag the lines between rows or columns to resize them. Click a place, Shift+click another to select the places between them, then Merge; Split gives a merged place its cells back.'});
    const mergeButton = h('button', {type: 'button', class: 'ds-design-action', onclick: () => merge()}, 'Merge');
    const splitButton = h('button', {type: 'button', class: 'ds-design-action', onclick: () => split()}, 'Split');
    const close = () => overlay.remove();
    const ordered = () => [...spec.areas].sort((left, right) => left[0] - right[0] || left[1] - right[1]);
    function selection() {
      const areas = ordered().filter((_area, index) => selected.has(index));
      if (!areas.length) return null;
      const top = Math.min(...areas.map(area => area[0])), left = Math.min(...areas.map(area => area[1]));
      const bottom = Math.max(...areas.map(area => area[0] + area[2])), right = Math.max(...areas.map(area => area[1] + area[3]));
      return {top, left, bottom, right};
    }
    // The places a rectangle covers: merged only when no place crosses its edge.
    function within(bounds) {
      const inside = [], crossing = [];
      ordered().forEach((area, index) => {
        const overlaps = area[0] < bounds.bottom && area[0] + area[2] > bounds.top && area[1] < bounds.right && area[1] + area[3] > bounds.left;
        if (!overlaps) return;
        const contained = area[0] >= bounds.top && area[0] + area[2] <= bounds.bottom && area[1] >= bounds.left && area[1] + area[3] <= bounds.right;
        (contained ? inside : crossing).push(index);
      });
      return {inside, crossing};
    }
    function merge() {
      const bounds = selection();
      if (!bounds) return;
      const {inside, crossing} = within(bounds);
      if (crossing.length || inside.length < 2) return;
      const keep = ordered().filter((_area, index) => !inside.includes(index));
      spec.areas = [...keep, [bounds.top, bounds.left, bounds.bottom - bounds.top, bounds.right - bounds.left]];
      selected = new Set();
      paint();
    }
    function split() {
      const areas = ordered();
      const next = [];
      areas.forEach((area, index) => {
        if (!selected.has(index) || (area[2] === 1 && area[3] === 1)) { next.push(area); return; }
        for (let row = area[0]; row < area[0] + area[2]; row += 1) for (let column = area[1]; column < area[1] + area[3]; column += 1) next.push([row, column, 1, 1]);
      });
      spec.areas = next;
      selected = new Set();
      paint();
    }
    function startDrag(kind, index, event) {
      event.preventDefault();
      const box = board.getBoundingClientRect();
      const sizes = spec[kind];
      const before = sum(sizes.slice(0, index)), pair = sizes[index] + sizes[index + 1];
      const move = moveEvent => {
        const position = kind === 'columns' ? (moveEvent.clientX - box.left) / box.width : (moveEvent.clientY - box.top) / box.height;
        const first = Math.min(pair - MINIMUM, Math.max(MINIMUM, position - before));
        sizes[index] = first;
        sizes[index + 1] = pair - first;
        paint();
      };
      const stop = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', stop); };
      window.addEventListener('pointermove', move);
      window.addEventListener('pointerup', stop);
    }
    // What a place holds: the elements of the places of before whose top-left cell it covers.
    const originalAreas = [...original.areas].sort((left, right) => left[0] - right[0] || left[1] - right[1]);
    const holds = area => originalAreas.flatMap((before, index) => (covers(area, before[0], before[1]) && options.labels?.[index] ? [options.labels[index]] : []));
    function paint() {
      const rects = geometry(spec);
      board.replaceChildren(
        ...ordered().map((area, index) => {
          const [left, top, width, height] = rects[index];
          return h('button', {type: 'button', class: `ds-layout-place${selected.has(index) ? ' is-selected' : ''}`, style: {left: `${left}%`, top: `${top}%`, width: `${width}%`, height: `${height}%`},
            'aria-pressed': String(selected.has(index)), 'aria-label': `Place ${index + 1}`,
            onclick: event => {
              if (event.shiftKey && selected.size) {
                const first = ordered()[[...selected][0]];
                const bounds = {top: Math.min(first[0], area[0]), left: Math.min(first[1], area[1]),
                  bottom: Math.max(first[0] + first[2], area[0] + area[2]), right: Math.max(first[1] + first[3], area[1] + area[3])};
                selected = new Set(within(bounds).inside);
              } else selected = selected.has(index) && selected.size === 1 ? new Set() : new Set([index]);
              paint();
            }}, h('span', {class: 'ds-layout-number', text: String(index + 1)}),
            holds(area).length ? h('span', {class: 'ds-layout-holds', text: holds(area).join(' + ')}) : h('span', {class: 'ds-layout-holds is-free', text: 'Free place'}),
            area[2] > 1 || area[3] > 1 ? h('small', {class: 'ds-layout-span', text: `${area[2]} × ${area[3]} cells`}) : null);
        }),
        ...spec.columns.slice(0, -1).map((_size, index) => h('span', {class: 'ds-layout-divider is-column', style: {left: `${sum(spec.columns.slice(0, index + 1)) * 100}%`},
          title: 'Drag to resize the columns', onpointerdown: event => startDrag('columns', index, event)})),
        ...spec.rows.slice(0, -1).map((_size, index) => h('span', {class: 'ds-layout-divider is-row', style: {top: `${sum(spec.rows.slice(0, index + 1)) * 100}%`},
          title: 'Drag to resize the rows', onpointerdown: event => startDrag('rows', index, event)})),
      );
      const bounds = selection();
      const coverage = bounds ? within(bounds) : {inside: [], crossing: []};
      mergeButton.disabled = coverage.inside.length < 2 || coverage.crossing.length > 0;
      splitButton.disabled = !ordered().some((area, index) => selected.has(index) && (area[2] > 1 || area[3] > 1));
    }
    // Which new place each place of before becomes: the one covering its top-left cell (-1 when another one there now
    // starts before it, the place merged into another).
    function mapping() {
      const before = [...original.areas].sort((left, right) => left[0] - right[0] || left[1] - right[1]);
      const after = ordered();
      const taken = new Set();
      return before.map(area => {
        const index = after.findIndex(next => covers(next, area[0], area[1]));
        if (index < 0 || taken.has(index)) return -1;
        taken.add(index);
        return index;
      });
    }
    const dialog = h('section', {class: 'confirm-panel ds-design-dialog is-wide', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Adjust places', tabindex: '-1'},
      h('div', {class: 'section-head'}, h('div', {}, h('p', {class: 'eyebrow', text: options.title || 'Slide'}), h('h2', {text: 'Adjust places'})), h('button', {type: 'button', class: 'ds-dialog-close', 'aria-label': 'Close', onclick: close}, '×')),
      note, board,
      h('div', {class: 'ds-design-dialog-actions'},
        mergeButton, splitButton,
        h('button', {type: 'button', class: 'ds-design-action', title: 'The places of the layout as the slide master has them', onclick: () => { close(); options.onSave(null); }}, 'Reset places'),
        h('button', {type: 'button', class: 'ds-design-action', onclick: close}, 'Cancel'),
        h('button', {type: 'button', class: 'ds-design-action ds-design-primary', onclick: () => {
          const result = {grid: {rows: spec.rows.map(value => Math.round(value * 10000) / 10000), columns: spec.columns.map(value => Math.round(value * 10000) / 10000), areas: ordered()}, geometry: geometry(spec), mapping: mapping()};
          close();
          options.onSave(result);
        }}, 'Apply')));
    overlay.append(dialog);
    overlay.addEventListener('keydown', event => { if (event.key === 'Escape') { event.stopPropagation(); close(); } });
    (document.getElementById('ds-viewer') || document.body).append(overlay);
    overlay.hidden = false;
    paint();
    dialog.focus();
  }

  window.PlacesEditor = {open, geometry, gridSpec};
})();
