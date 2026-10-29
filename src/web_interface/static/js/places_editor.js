/* Free layouts of the Designer (ticket #26, phase 4): the places of a slide adjusted on a grid.

   A layout starts from one ready to use (two charts above and one as wide as both below, a tall one beside two…) or from
   the grid of the slide, which takes rows and columns more or fewer. The rows and columns of the grid are resized by
   dragging the lines between them, and neighbouring places are merged into one (a chart over two columns) or split again;
   a place deleted leaves its cells empty (a + puts a place back in one), and Center puts a place midway in the free cells
   beside it, adding the lines of the grid it needs. The result is the geometry of the places, as fractions of the chart area of the slide's layout (the same coordinates
   the viewer lays charts out with, and the PPT export places them by), kept with the grid it came from so it can be
   adjusted again. */
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
  const inReadingOrder = areas => [...areas].sort((left, right) => left[0] - right[0] || left[1] - right[1]);
  // Which place of ``after`` each place of ``before`` (both grids on the same cells) becomes: the one covering its top-left
  // cell, or -1 when another place of before took it (places merged into one) or the cell is gone. Of places merged into
  // one, the first that holds something (``holds(index)``) keeps it, else the first in reading order.
  function cellMapping(before, after, holds = () => false) {
    const ordered = inReadingOrder(after);
    const places = inReadingOrder(before);
    const result = places.map(() => -1);
    const taken = new Set();
    const order = places.map((_area, index) => index).sort((left, right) => Number(holds(right)) - Number(holds(left)) || left - right);
    for (const index of order) {
      const target = ordered.findIndex(next => covers(next, places[index][0], places[index][1]));
      if (target < 0 || taken.has(target)) continue;
      taken.add(target);
      result[index] = target;
    }
    return result;
  }
  // Layouts ready to start from: a grid whose places span its cells ([row, column, rows, columns]).
  const thirds = [1 / 3, 1 / 3, 1 / 3], sixths = Array(6).fill(1 / 6);
  const PRESETS = [
    ['One', gridSpec(1, 1)],
    ['Two side by side', gridSpec(1, 2)],
    ['Two stacked', gridSpec(2, 1)],
    ['Two above, one wide below', {rows: [.5, .5], columns: [.5, .5], areas: [[0, 0, 1, 1], [0, 1, 1, 1], [1, 0, 1, 2]]}],
    ['One wide above, two below', {rows: [.5, .5], columns: [.5, .5], areas: [[0, 0, 1, 2], [1, 0, 1, 1], [1, 1, 1, 1]]}],
    ['One tall at the left, two at the right', {rows: [.5, .5], columns: [.6, .4], areas: [[0, 0, 2, 1], [0, 1, 1, 1], [1, 1, 1, 1]]}],
    ['Two at the left, one tall at the right', {rows: [.5, .5], columns: [.4, .6], areas: [[0, 0, 1, 1], [1, 0, 1, 1], [0, 1, 2, 1]]}],
    ['Four', gridSpec(2, 2)],
    ['Three above, one wide below', {rows: [.5, .5], columns: thirds, areas: [[0, 0, 1, 1], [0, 1, 1, 1], [0, 2, 1, 1], [1, 0, 1, 3]]}],
    ['One wide above, three below', {rows: [.5, .5], columns: thirds, areas: [[0, 0, 1, 3], [1, 0, 1, 1], [1, 1, 1, 1], [1, 2, 1, 1]]}],
    ['One tall at the left, three at the right', {rows: thirds, columns: [.6, .4], areas: [[0, 0, 3, 1], [0, 1, 1, 1], [1, 1, 1, 1], [2, 1, 1, 1]]}],
    ['Three above, two below', {rows: [.5, .5], columns: sixths, areas: [[0, 0, 1, 2], [0, 2, 1, 2], [0, 4, 1, 2], [1, 0, 1, 3], [1, 3, 1, 3]]}],
    ['Two above, three below', {rows: [.5, .5], columns: sixths, areas: [[0, 0, 1, 3], [0, 3, 1, 3], [1, 0, 1, 2], [1, 2, 1, 2], [1, 4, 1, 2]]}],
    ['Six', gridSpec(2, 3)],
  ];
  const MAXIMUM_ROWS = 6, MAXIMUM_COLUMNS = 12;

  /** Open the editor. options: {title, grid: {rows, columns, areas} or null, rows, columns (of the layout), labels (what each
   *  place holds now, by place), onSave(result)}
   *  where result is {grid, geometry, mapping: old place -> new place (or -1 when merged away)} or null to reset. */
  function open(options) {
    let spec = options.grid && Array.isArray(options.grid.areas) ? structuredClone(options.grid) : gridSpec(options.rows || 1, options.columns || 1);
    spec.rows = normalized(spec.rows); spec.columns = normalized(spec.columns);
    const original = structuredClone(spec);
    let selected = new Set();
    // The places of before as the grid the places are now compared with knows them: the grid of before, or the layout
    // last started from, which takes the places of before in reading order.
    let reference = {spec: original, places: original.areas.map((_area, index) => index)};
    const overlay = h('div', {class: 'confirm-overlay ds-overlay ds-secondary ppt-designer ds-design-dialog-overlay'});
    const board = h('div', {class: 'ds-layout-board', role: 'application', 'aria-label': 'Places of the slide'});
    const note = h('p', {class: 'form-note', text: 'Start from a layout, or give the grid more or fewer rows and columns. Drag the lines between rows or columns to resize them. Click a place, Shift+click another to select the places between them, then Merge; Split gives a merged place its cells back. Delete empties the places chosen (+ puts a place back in an empty cell), and Center puts a place midway in the empty cells beside it.'});
    const mergeButton = h('button', {type: 'button', class: 'ds-design-action', onclick: () => merge()}, 'Merge');
    const splitButton = h('button', {type: 'button', class: 'ds-design-action', onclick: () => split()}, 'Split');
    const deleteButton = h('button', {type: 'button', class: 'ds-design-action', title: 'Delete the places chosen: their cells stay empty', onclick: () => remove()}, 'Delete');
    const centerButton = h('button', {type: 'button', class: 'ds-design-action', onclick: () => center()}, 'Center');
    const close = () => overlay.remove();
    const ordered = () => inReadingOrder(spec.areas);
    // A layout to start from, drawn small: the places of the elements of the slide follow in reading order.
    const presets = h('div', {class: 'ds-layout-presets', role: 'group', 'aria-label': 'Layouts'}, PRESETS.map(([name, preset]) =>
      h('button', {type: 'button', class: 'ds-layout-preset', title: name, 'aria-label': name, onclick: () => {
        spec = structuredClone(preset);
        reference = {spec: structuredClone(preset), places: original.areas.map((_area, index) => (index < preset.areas.length ? index : -1))};
        selected = new Set();
        paint();
      }}, h('span', {class: 'ds-layout-preset-board', 'aria-hidden': 'true'}, geometry(preset).map(([left, top, width, height]) =>
        h('span', {class: 'ds-layout-preset-place', style: {left: `${left}%`, top: `${top}%`, width: `${width}%`, height: `${height}%`}}))))));
    // One row or column more at the bottom or right, or the last one less (a place only in it goes away, one across it
    // narrows).
    function resize(kind, change) {
      const count = spec[kind].length;
      const maximum = kind === 'rows' ? MAXIMUM_ROWS : MAXIMUM_COLUMNS;
      if (change > 0 && count < maximum) {
        spec[kind] = normalized([...spec[kind].map(size => size * count / (count + 1)), 1 / (count + 1)]);
        const other = kind === 'rows' ? spec.columns.length : spec.rows.length;
        for (let index = 0; index < other; index += 1) spec.areas.push(kind === 'rows' ? [count, index, 1, 1] : [index, count, 1, 1]);
      } else if (change < 0 && count > 1) {
        const last = count - 1, start = kind === 'rows' ? 0 : 1, span = kind === 'rows' ? 2 : 3;
        spec.areas = spec.areas.filter(area => area[start] < last).map(area => {
          const next = [...area];
          if (next[start] + next[span] > last) next[span] = last - next[start];
          return next;
        });
        spec[kind] = normalized(spec[kind].slice(0, -1));
      } else return;
      selected = new Set();
      paint();
    }
    const counter = (kind, label) => h('span', {class: 'ds-layout-counter', role: 'group', 'aria-label': label},
      h('span', {class: 'ds-layout-counter-label', text: label}),
      h('button', {type: 'button', class: 'ds-layout-counter-step', 'aria-label': `One ${label.toLowerCase().replace(/s$/, '')} less`, title: `The last ${label.toLowerCase().replace(/s$/, '')} less`, onclick: () => resize(kind, -1)}, '−'),
      h('output', {class: 'ds-layout-counter-value', 'data-counter': kind}),
      h('button', {type: 'button', class: 'ds-layout-counter-step', 'aria-label': `One ${label.toLowerCase().replace(/s$/, '')} more`, title: `One ${label.toLowerCase().replace(/s$/, '')} more`, onclick: () => resize(kind, 1)}, '+'));
    const counters = h('div', {class: 'ds-layout-counters'}, counter('rows', 'Rows'), counter('columns', 'Columns'));
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
    // Delete: the places chosen go, their cells stay empty (what they hold goes to a free place when applied).
    function remove() {
      if (!selected.size || selected.size >= spec.areas.length) return;
      spec.areas = ordered().filter((_area, index) => !selected.has(index));
      selected = new Set();
      paint();
    }
    const covered = (row, column) => spec.areas.some(area => covers(area, row, column));
    // The empty cells beside a place, along rows (columns) or columns (rows), over all of its height or width: [first, end).
    function freeRun(area, kind) {
      const [at, span, across, acrossSpan] = kind === 'columns' ? [1, 3, 0, 2] : [0, 2, 1, 3];
      const empty = index => [...Array(area[acrossSpan]).keys()].every(offset => {
        const line = area[across] + offset;
        return kind === 'columns' ? !covered(line, index) : !covered(index, line);
      });
      let first = area[at], end = area[at] + area[span];
      while (first > 0 && empty(first - 1)) first -= 1;
      while (end < spec[kind].length && empty(end)) end += 1;
      return [first, end];
    }
    // Where a place goes when centred in the empty cells beside it: its start and end on each side it has empty cells on.
    function centring(area) {
      const plan = [];
      for (const kind of ['columns', 'rows']) {
        const [at, span] = kind === 'columns' ? [1, 3] : [0, 2];
        const [first, end] = freeRun(area, kind);
        if (first === area[at] && end === area[at] + area[span]) continue;
        const start = index => sum(spec[kind].slice(0, index));
        const size = start(area[at] + area[span]) - start(area[at]);
        const from = (start(first) + start(end) - size) / 2;
        if (Math.abs(from - start(area[at])) < 0.0005) continue;
        plan.push({kind, from, to: from + size});
      }
      return plan;
    }
    const lineIndex = (kind, position) => {
      let start = 0;
      for (let index = 0; index <= spec[kind].length; index += 1) {
        if (Math.abs(start - position) < 0.0005) return index;
        start += spec[kind][index] ?? 0;
      }
      return -1;
    };
    // A line of the grid at ``position`` (a fraction of the board): the row or column it falls in is split in two, and the
    // places across it take both halves.
    function addLine(kind, position) {
      if (lineIndex(kind, position) >= 0) return;
      const [at, span] = kind === 'columns' ? [1, 3] : [0, 2];
      let start = 0;
      for (let index = 0; index < spec[kind].length; index += 1) {
        const end = start + spec[kind][index];
        if (position < end) {
          spec[kind].splice(index, 1, position - start, end - position);
          for (const area of spec.areas) {
            if (area[at] > index) area[at] += 1;
            else if (area[at] + area[span] > index) area[span] += 1;
          }
          return;
        }
        start = end;
      }
    }
    function center() {
      const index = [...selected][0];
      const area = selected.size === 1 ? ordered()[index] : null;
      const plan = area ? centring(area) : [];
      if (!plan.length) return;
      const lines = kind => plan.filter(step => step.kind === kind).flatMap(step => [step.from, step.to]).filter(position => lineIndex(kind, position) < 0).length;
      if (spec.columns.length + lines('columns') > MAXIMUM_COLUMNS || spec.rows.length + lines('rows') > MAXIMUM_ROWS) {
        note.textContent = `Centring it needs more than ${MAXIMUM_ROWS} rows or ${MAXIMUM_COLUMNS} columns: give the grid fewer first.`;
        return;
      }
      // The places of before keep following the places they became: the reference is the grid as it is now.
      const now = mapping(), before = ordered();
      for (const {kind, from, to} of plan) {
        addLine(kind, from);
        addLine(kind, to);
        const [at, span] = kind === 'columns' ? [1, 3] : [0, 2];
        area[at] = lineIndex(kind, from);
        area[span] = lineIndex(kind, to) - area[at];
      }
      const after = ordered();
      reference = {spec: structuredClone(spec), places: now.map(place => (place < 0 ? -1 : after.indexOf(before[place])))};
      selected = new Set([after.indexOf(area)]);
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
    // What a place holds: the elements of the places of before that become it.
    const holds = index => mapping().flatMap((place, before) => (place === index && options.labels?.[before] ? [options.labels[before]] : []));
    function paint() {
      const rects = geometry(spec);
      overlay.querySelectorAll('[data-counter]').forEach(output => { output.textContent = String(spec[output.dataset.counter].length); });
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
            holds(index).length ? h('span', {class: 'ds-layout-holds', text: holds(index).join(' + ')}) : h('span', {class: 'ds-layout-holds is-free', text: 'Free place'}),
            area[2] > 1 || area[3] > 1 ? h('small', {class: 'ds-layout-span', text: `${area[2]} × ${area[3]} cells`}) : null);
        }),
        // The empty cells: a + puts a place back in one.
        ...spec.rows.flatMap((_row, row) => spec.columns.map((_column, column) => [row, column])).filter(([row, column]) => !covered(row, column)).map(([row, column]) => {
          const [left, top, width, height] = geometry({...spec, areas: [[row, column, 1, 1]]})[0];
          return h('button', {type: 'button', class: 'ds-layout-empty', style: {left: `${left}%`, top: `${top}%`, width: `${width}%`, height: `${height}%`},
            title: 'An empty cell: put a place in it', 'aria-label': `Put a place in the empty cell of row ${row + 1}, column ${column + 1}`,
            onclick: () => { spec.areas.push([row, column, 1, 1]); selected = new Set(); paint(); }}, '+');
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
      deleteButton.disabled = !selected.size || selected.size >= spec.areas.length;
      const centred = selected.size === 1 && centring(ordered()[[...selected][0]]).length > 0;
      centerButton.disabled = !centred;
      centerButton.title = centred ? 'Center the place chosen in the empty cells beside it' : 'Choose a place with empty cells beside it (Delete empties a place)';
    }
    // Which new place each place of before becomes (-1 when none: merged into another, or gone with its row or column).
    function mapping() {
      const held = new Set(reference.places.filter((place, before) => place >= 0 && options.labels?.[before]));
      const now = cellMapping(reference.spec.areas, spec.areas, place => held.has(place));
      return reference.places.map(place => (place < 0 ? -1 : now[place] ?? -1));
    }
    const dialog = h('section', {class: 'confirm-panel ds-design-dialog is-wide', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Adjust places', tabindex: '-1'},
      h('div', {class: 'section-head'}, h('div', {}, h('p', {class: 'eyebrow', text: options.title || 'Slide'}), h('h2', {text: 'Adjust places'})), h('button', {type: 'button', class: 'ds-dialog-close', 'aria-label': 'Close', onclick: close}, '×')),
      note, presets, counters, board,
      h('div', {class: 'ds-design-dialog-actions'},
        mergeButton, splitButton, deleteButton, centerButton,
        h('button', {type: 'button', class: 'ds-design-action', title: 'The places of the layout as the slide master has them', onclick: () => { close(); options.onSave(null); }}, 'Reset places'),
        h('button', {type: 'button', class: 'ds-design-action', onclick: close}, 'Cancel'),
        h('button', {type: 'button', class: 'ds-design-action ds-design-primary', onclick: () => {
          const result = {grid: {rows: spec.rows.map(value => Math.round(value * 10000) / 10000), columns: spec.columns.map(value => Math.round(value * 10000) / 10000), areas: ordered()}, geometry: geometry(spec), mapping: mapping()};
          close();
          options.onSave(result);
        }}, 'Apply')));
    overlay.append(dialog);
    overlay.addEventListener('keydown', event => {
      if (event.key === 'Escape') { event.stopPropagation(); close(); }
      // Delete or Backspace on the board deletes the places chosen.
      else if ((event.key === 'Delete' || event.key === 'Backspace') && board.contains(event.target)) { event.preventDefault(); event.stopPropagation(); remove(); }
    });
    (document.getElementById('ds-viewer') || document.body).append(overlay);
    overlay.hidden = false;
    paint();
    dialog.focus();
  }

  window.PlacesEditor = {open, geometry, gridSpec, cellMapping};
})();
