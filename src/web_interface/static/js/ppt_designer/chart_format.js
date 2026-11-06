/* The Format of a chart (ticket #26): its series, legend, labels and axes, kept in its style (see formattedPayload in
   canvas_charts.js), and the cards that change them on the chart itself: a series from its legend, the range of a numeric
   axis, the values of a category axis. The Designer and Chart Builder share it: ChartFormat.editor(host) gives the Format of
   the charts of a host, which says how to read and write a chart (see editor). */
(() => {
  'use strict';
  const clone = value => (value === undefined ? undefined : structuredClone(value));
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
  const field = (label, control, note) => h('label', {class: 'ds-design-field'}, h('span', {class: 'ds-design-field-label', text: label}), control, note ? h('span', {class: 'ds-design-field-note', text: note}) : null);
  const selectInput = (options, value, onchange, id) => {
    const select = h('select', {id, onchange: event => onchange(event.target.value)});
    for (const [optionValue, optionLabel] of options) {
      const option = h('option', {value: optionValue, text: optionLabel});
      option.selected = String(optionValue) === String(value ?? '');
      select.append(option);
    }
    if (![...select.options].some(option => option.selected) && value) {
      const option = h('option', {value, text: value}); option.selected = true; select.append(option);
    }
    return select;
  };
  const textInput = (value, oninput, props = {}) => h(props.multiline ? 'textarea' : 'input', {
    ...(props.multiline ? {rows: props.rows || 3} : {type: 'text'}), id: props.id, list: props.list, placeholder: props.placeholder,
    value: props.multiline ? undefined : value ?? '', oninput: event => oninput(event.target.value), spellcheck: 'false',
  }, props.multiline ? value ?? '' : null);
  function closeMenus() { document.querySelectorAll('.ds-design-popover').forEach(node => node.remove()); }
  function placePopover(popover, anchor, event) {
    document.body.append(popover);
    const box = anchor.getBoundingClientRect();
    const width = popover.offsetWidth, height = popover.offsetHeight;
    let left = event?.clientX ?? box.left, top = event?.clientY ?? box.bottom + 4;
    left = Math.max(8, Math.min(left, window.innerWidth - width - 8));
    if (top + height > window.innerHeight - 8) top = Math.max(8, (event?.clientY ?? box.top) - height - 4);
    Object.assign(popover.style, {left: `${left}px`, top: `${top}px`});
    popover.querySelector('button:not(:disabled)')?.focus({preventScroll: true});
  }
  const LABEL_POSITIONS = [['', 'Default'], ['none', 'None'], ['top', 'Top'], ['up', 'Up'], ['middle', 'Middle'], ['down', 'Down']];
  const SIZES = [['', 'Default'], ['Small', 'Small'], ['Medium', 'Medium'], ['Large', 'Large']];
  const DASH_NAMES = [['', 'Default'], ['solid', 'Solid'], ['dashed', 'Dashed'], ['dotted', 'Dotted']];

  /** The Format of the charts of a host: {element(id): the values of a chart (its style, axis ranges and filters),
   *  write(id, values): changes them (a promise), canvas(id): the canvas the chart is drawn on, status(text), report(error),
   *  settled(): a promise of the changes still being written, label(element): the name of a chart, refresh(): draws the
   *  panel again, debounced(fn): fn a moment after the last call}. */
  function editor(host) {
    // The clipboards of the line of a series and of the format of a chart, and the groups of Format left open.
    const own = {};
    const guarded = fn => async (...args) => { try { return await fn(...args); } catch (error) { host.report(error); return undefined; } };
    const legendItems = elementId => { const canvas = host.canvas(elementId); return canvas && globalThis.getCanvasChartLegendItems ? globalThis.getCanvasChartLegendItems(canvas) : []; };
    const styleOf = element => clone(element?.style && typeof element.style === 'object' ? element.style : {});
    const cleanStyle = style => {
      const prune = value => {
        if (!value || typeof value !== 'object' || Array.isArray(value)) return value;
        const result = {};
        for (const [key, item] of Object.entries(value)) {
          const cleaned = prune(item);
          if (cleaned === '' || cleaned === null || cleaned === undefined || (typeof cleaned === 'object' && !Array.isArray(cleaned) && !Object.keys(cleaned).length)) continue;
          result[key] = cleaned;
        }
        return result;
      };
      return prune(style) || {};
    };
    function setStyle(elementId, change) {
      const current = host.element(elementId);
      if (!current) { host.report(new Error('This element is only in this Design: change it in This Design scope, or apply it to the template first.')); return undefined; }
      const style = styleOf(current);
      change(style);
      return host.write(elementId, {style: cleanStyle(style)});
    }
    // The values of a field of the Rows or Columns in the order they were dragged to on the chart (as in Tableau); without
    // values the field takes its own order back.
    const orderValues = (elementId, field, values) => setStyle(elementId, style => {
      style.order = {...(style.order || {})};
      if (values?.length) style.order[field] = [...values]; else delete style.order[field];
    });
    const setSeries = (elementId, name, values) => setStyle(elementId, style => {
      style.series = style.series || {};
      style.series[name] = {...(style.series[name] || {}), ...values};
    });
    function openSeriesFormat(anchor, elementId, name, event) {
      closeMenus();
      const element = host.element(elementId);
      const current = styleOf(element).series?.[name] || {};
      const original = legendItems(elementId).find(item => item.label === name)?.colour || '#4B2C82';
      const colour = h('input', {type: 'color', value: /^#[0-9a-f]{6}$/i.test(current.colour || '') ? current.colour : (/^#[0-9a-f]{6}$/i.test(original) ? original : '#4B2C82'), 'aria-label': `Colour of ${name}`,
        onchange: event2 => guarded(() => setSeries(elementId, name, {colour: event2.target.value.toUpperCase()}))()});
      const width = h('input', {type: 'number', min: '1', max: '10', step: '0.5', value: current.width ?? '', placeholder: 'Default', 'aria-label': 'Line width',
        onchange: event2 => guarded(() => setSeries(elementId, name, {width: event2.target.value === '' ? '' : Number(event2.target.value)}))()});
      const dash = selectInput(DASH_NAMES, current.dash || '', value => guarded(() => setSeries(elementId, name, {dash: value}))());
      const opacity = h('input', {type: 'range', min: '0.2', max: '1', step: '0.05', value: current.opacity ?? 1, 'aria-label': 'Opacity',
        onchange: event2 => guarded(() => setSeries(elementId, name, {opacity: Number(event2.target.value) >= 1 ? '' : Number(event2.target.value)}))()});
      const popover = h('div', {class: 'ds-design-popover ds-design-series', role: 'dialog', 'aria-label': `Format of ${name}`},
        h('h4', {text: name}),
        h('label', {class: 'ds-design-format-row'}, 'Colour', colour),
        h('label', {class: 'ds-design-format-row'}, 'Line width', width),
        h('label', {class: 'ds-design-format-row'}, 'Line', dash),
        h('label', {class: 'ds-design-format-row'}, 'Opacity', opacity),
        // The line of a series (its width, dash and opacity, not its colour: the colour tells the series apart) copied to paste
        // on another series, of this chart or another. It is read once the changes made here are kept.
        h('div', {class: 'ds-design-format-actions'},
          h('button', {type: 'button', title: 'Copy the line width, line and opacity of this series (not its colour), to paste them on another series',
            onclick: guarded(async () => {
              await host.settled();
              const now = styleOf(host.element(elementId)).series?.[name] || {};
              own.seriesClipboard = {from: name, values: {width: now.width ?? '', dash: now.dash || '', opacity: now.opacity ?? ''}};
              host.status(`Line of ${name} copied: open another series and paste it there.`);
              closeMenus();
            })}, 'Copy line of this series'),
          own.seriesClipboard && own.seriesClipboard.from !== name ? h('button', {type: 'button', title: `Give this series the line width, line and opacity of ${own.seriesClipboard.from} (its colour stays)`,
            onclick: () => { closeMenus(); guarded(() => setSeries(elementId, name, clone(own.seriesClipboard.values)))(); }}, `Paste line of ${own.seriesClipboard.from}`) : null),
        h('div', {class: 'ds-design-format-actions'},
          h('button', {type: 'button', title: 'The colour of the Operator / Vendor Maps of the workspace, and the default line', onclick: () => { closeMenus(); guarded(() => setStyle(elementId, style => { if (style.series) delete style.series[name]; }))(); }}, 'Default'),
          h('button', {type: 'button', onclick: closeMenus}, 'Close')));
      placePopover(popover, anchor, event);
    }
    // The range of a numeric axis, chosen with a slider of two thumbs (as in Tableau): applied when a thumb is released;
    // Automatic gives the axis its own range back. The Y axis of a CDF is in percent (0–100).
    // The card of an axis, as in Tableau: what the axis holds (its kind, its field) in the head, the range or the values
    // in the body, and the actions at its foot; each choice is laid out at once.
    function axisCard(kind, title, label, body, foot, badge = null) {
      return h('div', {class: 'ds-design-popover ds-axis-card', role: 'dialog', 'aria-label': label},
        h('header', {class: 'ds-axis-head'},
          h('div', {class: 'ds-axis-heading'}, h('span', {class: 'ds-axis-kind', text: kind}), h('h4', {text: title}), badge),
          h('button', {type: 'button', class: 'ds-axis-close', 'aria-label': 'Close', title: 'Close', onclick: closeMenus}, '×')),
        ...body,
        h('footer', {class: 'ds-axis-foot'}, ...foot));
    }
    // The range of a numeric axis: two handles on its track (the part of the track where the values of the chart lie is
    // marked), or its start and end typed; the chart takes it when a handle is released. Automatic gives the range back to
    // the values of the chart.
    function openAxisRange(anchor, elementId, axis, event) {
      closeMenus();
      const key = axis.axis === 'y' ? 'axis_y_range' : 'axis_x_range';
      const automatic = !String(host.element(elementId)?.[key] || '').trim();
      const low = Math.min(axis.extent[0], axis.domain[0]), high = Math.max(axis.extent[1], axis.domain[1]);
      const span = high - low || 1;
      const decimals = axis.percent ? 0 : Math.max(0, Math.min(4, 2 - Math.floor(Math.log10(span))));
      const step = Number((span / 200).toFixed(decimals)) || 10 ** -decimals;
      const round = value => Number(Number(value).toFixed(decimals));
      const unit = axis.percent ? '%' : '';
      let start = round(axis.domain[0]), end = round(axis.domain[1]);
      const handle = (value, label) => h('input', {type: 'range', class: 'ds-axis-handle', min: String(round(low)), max: String(round(high)), step: String(step), value: String(value), 'aria-label': label});
      const from = handle(start, 'Start of the axis'), to = handle(end, 'End of the axis');
      const number = (value, label) => h('input', {type: 'number', class: 'ds-axis-number', step: String(step), value: String(value), 'aria-label': label});
      const fromNumber = number(start, 'Start'), toNumber = number(end, 'End');
      const fill = h('span', {class: 'ds-axis-fill'});
      const values = h('span', {class: 'ds-axis-values-band', title: `The values of the chart: ${round(axis.extent[0])}${unit} to ${round(axis.extent[1])}${unit}`,
        style: {left: `${(axis.extent[0] - low) / span * 100}%`, width: `${Math.max(0, axis.extent[1] - axis.extent[0]) / span * 100}%`}});
      const paint = () => {
        fill.style.left = `${(start - low) / span * 100}%`;
        fill.style.width = `${Math.max(0, end - start) / span * 100}%`;
        fromNumber.value = String(start); toNumber.value = String(end);
      };
      let timer = 0;
      const commit = () => {
        clearTimeout(timer);
        timer = setTimeout(() => guarded(() => host.write(elementId, {[key]: `[${start},${end}]`}))(), 150);
      };
      from.addEventListener('input', () => { start = Math.min(round(from.value), end - step); from.value = String(start); paint(); });
      to.addEventListener('input', () => { end = Math.max(round(to.value), start + step); to.value = String(end); paint(); });
      from.addEventListener('change', commit); to.addEventListener('change', commit);
      fromNumber.addEventListener('change', () => { start = Math.min(round(fromNumber.value), end - step); from.value = String(start); paint(); commit(); });
      toNumber.addEventListener('change', () => { end = Math.max(round(toNumber.value), start + step); to.value = String(end); paint(); commit(); });
      const card = axisCard(axis.axis === 'y' ? 'Y axis' : 'X axis', `Range${unit ? ` (${unit})` : ''}`, 'Range of the axis', [
        h('div', {class: 'ds-axis-readout'},
          h('label', {class: 'ds-axis-bound'}, h('span', {text: 'From'}), fromNumber),
          h('span', {class: 'ds-axis-dash', 'aria-hidden': 'true'}, '→'),
          h('label', {class: 'ds-axis-bound'}, h('span', {text: 'To'}), toNumber)),
        h('div', {class: 'ds-axis-slider'}, h('span', {class: 'ds-axis-rail'}), values, fill, from, to),
        h('div', {class: 'ds-axis-scale'}, h('span', {text: `${round(low)}${unit}`}),
          h('span', {class: 'ds-axis-scale-note', text: 'values of the chart'}), h('span', {text: `${round(high)}${unit}`})),
      ], [
        h('button', {type: 'button', class: 'ds-axis-secondary', disabled: automatic, title: 'The range the chart takes from its values',
          onclick: () => { closeMenus(); guarded(() => host.write(elementId, {[key]: ''}))(); }}, 'Automatic'),
        h('button', {type: 'button', class: 'ds-axis-primary', onclick: closeMenus}, 'Close'),
      ], automatic ? h('span', {class: 'ds-axis-badge', text: 'Automatic'}) : h('span', {class: 'ds-axis-badge is-set', text: 'Set here'}));
      placePopover(card, anchor, event);
      paint();
    }
    // The values of a category axis (a level of its Rows or Columns): unticked ones are left out of the chart (a filter of
    // the chart on that field, NOT IN), Only keeps one, Show all puts them back; at least one value always stays.
    function openAxisValues(anchor, elementId, axis, event) {
      closeMenus();
      const element = host.element(elementId);
      const field = axis.dimension;
      if (!element || !field) return;
      const pattern = new RegExp(`^${field.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s+NOT\\s+IN\\s*\\((.*)\\)$`, 'i');
      const conditions = (element.filters || '').split(/;|\n+/).map(item => item.trim()).filter(Boolean);
      const current = conditions.find(item => pattern.test(item));
      const excluded = new Set(current ? pattern.exec(current)[1].split(',').map(item => item.trim()).filter(Boolean) : []);
      const values = [...new Set([...(axis.values || []), ...excluded])];
      const write = () => {
        const kept = conditions.filter(item => !pattern.test(item));
        if (excluded.size) kept.push(`${field} NOT IN (${[...excluded].join(', ')})`);
        guarded(() => host.write(elementId, {filters: kept.join('; ')}))();
      };
      let query = '';
      const list = h('ul', {class: 'ds-axis-list', role: 'group', 'aria-label': `Values of ${field}`});
      const count = h('span', {class: 'ds-axis-count'});
      const showAll = h('button', {type: 'button', class: 'ds-axis-secondary', onclick: () => { excluded.clear(); write(); paint(); }}, 'Show all');
      const paint = () => {
        const shown = values.filter(value => value.toLocaleLowerCase().includes(query));
        list.replaceChildren(...(shown.length ? shown.map(value => {
          const on = !excluded.has(value);
          return h('li', {class: `ds-axis-option${on ? ' is-on' : ''}${value === axis.value ? ' is-clicked' : ''}`},
            h('button', {type: 'button', class: 'ds-axis-toggle', role: 'checkbox', 'aria-checked': String(on), title: on ? `Leave ${value} out of the chart` : `Show ${value}`,
              onclick: () => {
                if (on && excluded.size >= values.length - 1) return;
                if (on) excluded.add(value); else excluded.delete(value);
                write(); paint();
              }},
            h('span', {class: 'ds-axis-check', 'aria-hidden': 'true'}), h('span', {class: 'ds-axis-label', text: value})),
            h('button', {type: 'button', class: 'ds-axis-only', title: `Show only ${value}`,
              onclick: () => { excluded.clear(); values.filter(item => item !== value).forEach(item => excluded.add(item)); write(); paint(); }}, 'Only'));
        }) : [h('li', {class: 'ds-axis-empty', text: 'No value matches.'})]));
        count.textContent = `${values.length - excluded.size} of ${values.length} shown`;
        showAll.disabled = !excluded.size;
      };
      const search = values.length > 7 ? h('input', {type: 'search', class: 'ds-axis-search', placeholder: 'Search values', 'aria-label': 'Search values',
        oninput: event2 => { query = event2.target.value.trim().toLocaleLowerCase(); paint(); }}) : null;
      const kind = ['row', 'table-row'].includes(axis.axis) ? 'Rows' : 'Columns';
      // The values dragged to another order on the chart take the order of their field back.
      const ordered = Array.isArray(styleOf(element).order?.[field]);
      const defaultOrder = ordered ? h('button', {type: 'button', class: 'ds-axis-secondary', title: `Give the values of ${field} their own order back (they were dragged to another one on the chart)`,
        onclick: () => { closeMenus(); guarded(() => orderValues(elementId, field, null))(); }}, 'Default order') : null;
      const card = axisCard(kind, field, `Values of ${field}`, [
        h('div', {class: 'ds-axis-toolbar'}, search, count),
        list,
        h('p', {class: 'ds-axis-hint', text: 'Drag a value on the chart, before or after another one, to change their order.'}),
      ], [showAll, defaultOrder, h('button', {type: 'button', class: 'ds-axis-primary', onclick: closeMenus}, 'Close')]);
      paint();
      placePopover(card, anchor, event);
    }

    function formatSection(elementId, element) {
      const style = styleOf(element);
      const items = legendItems(elementId);
      const series = h('div', {class: 'ds-design-series-list'}, items.length
        ? items.map(item => {
          const own = style.series?.[item.label] || {};
          return h('button', {type: 'button', class: `ds-design-series-item${Object.keys(own).length ? ' is-changed' : ''}`, title: 'Colour, line and opacity of this series', onclick: event => openSeriesFormat(event.currentTarget, elementId, item.label)},
            h('span', {class: 'ds-design-swatch', style: {background: own.colour || item.colour || '#ccc', opacity: own.opacity ?? 1}}), item.label);
        })
        : h('p', {class: 'ds-design-empty', text: 'The series of the chart appear here once it is drawn (its legend).'}));
      const set = (path, value) => guarded(() => setStyle(elementId, target => {
        const keys = path.split('.');
        let node = target;
        keys.slice(0, -1).forEach(key => { node[key] = node[key] && typeof node[key] === 'object' ? node[key] : {}; node = node[key]; });
        node[keys.at(-1)] = value;
      }))();
      const integer = value => (value === '' ? '' : Math.max(0, Math.min(6, Math.round(Number(value)))));
      // The colour of a text, with a button back to the default one.
      const textColour = (what, value, write) => field('Text colour', h('div', {class: 'ds-design-input-row'},
        h('input', {type: 'color', value: value || '#263B4A', 'aria-label': `${what} text colour`, onchange: event => write(event.target.value.toUpperCase())}),
        h('button', {type: 'button', class: 'ds-design-token', title: `Default ${what.toLowerCase()} text colour`, onclick: () => write('')}, '↺')));
      // A closed group says what it holds.
      const named = (list, value) => list.find(([key]) => key === (value || ''))?.[1] || value;
      const LEGEND_PLACES = [['', 'Default'], ['top', 'Top'], ['bottom', 'Bottom'], ['left', 'Left'], ['right', 'Right'], ['none', 'Hidden']];
      const changedSeries = Object.values(style.series || {}).filter(item => Object.keys(item || {}).length).length;
      const summaries = {
        Series: items.length ? `${items.length} series${changedSeries ? ` · ${changedSeries} changed` : ''}` : '',
        Legend: [named(LEGEND_PLACES, style.legend?.position), style.legend?.size ? `${style.legend.size} text` : '', style.legend?.colour ? 'Coloured' : '', style.legend?.bold === false ? 'Not bold' : ''].filter(Boolean).join(' · '),
        Labels: [named(LABEL_POSITIONS, style.labels?.position), style.labels?.size ? `${style.labels.size} text` : '', style.labels?.colour ? 'Coloured' : '', style.labels?.bold ? 'Bold' : ''].filter(Boolean).join(' · '),
        Axes: [style.axes?.x?.title ? `X: ${style.axes.x.title}` : '', style.axes?.y?.title ? `Y: ${style.axes.y.title}` : '', style.axes?.x?.decimals !== undefined && style.axes?.x?.decimals !== '' ? `${style.axes.x.decimals} decimals` : ''].filter(Boolean).join(' · ') || 'As the chart names them',
      };
      // The groups open are kept for the next chart (all of them at first); several can be open at once.
      own.formatOpen = own.formatOpen || new Set(['Series', 'Legend', 'Labels', 'Axes']);
      const group = (label, ...children) => {
        const node = h('details', {class: 'ds-design-format-group', open: own.formatOpen.has(label)},
          h('summary', {}, h('span', {class: 'ds-design-format-group-name', text: label}), h('span', {class: 'ds-design-format-group-value', text: summaries[label] || ''})), ...children);
        node.addEventListener('toggle', () => { if (node.open) own.formatOpen.add(label); else own.formatOpen.delete(label); });
        return node;
      };
      return h('div', {class: 'ds-design-format'},
        // The format of a chart (series colours, legend, labels, axes and their ranges) copied to paste on another chart.
        h('div', {class: 'ds-design-format-actions'},
          h('button', {type: 'button', title: 'Copy the series colours, legend, labels, axes and axis ranges of this chart, to paste them on another chart',
            onclick: () => {
              own.formatClipboard = {style, legend_position: element.legend_position, label_position: element.label_position, label_format: element.label_format, axis_x_range: element.axis_x_range, axis_y_range: element.axis_y_range};
              own.formatClipboardFrom = host.label(element);
              host.status('Format copied: choose another chart and paste it there.');
              host.refresh();
            }}, 'Copy format of this chart'),
          own.formatClipboard ? h('button', {type: 'button', title: `Give this chart the series colours, legend, labels, axes and axis ranges of ${own.formatClipboardFrom}`,
            onclick: () => guarded(() => host.write(elementId, clone(own.formatClipboard)))()}, `Paste format of ${own.formatClipboardFrom}`) : null),
        h('p', {class: 'ds-design-field-note', text: 'The format is its series colours, legend, labels, axes and axis ranges.'}),
        group('Series',
          h('p', {class: 'ds-design-field-note', text: 'Click a series in the legend of the chart, or here, to change its colour, line and opacity.'}),
          series,
          h('div', {class: 'ds-design-format-actions'},
            h('button', {type: 'button', disabled: !style.series || !Object.values(style.series).some(item => item.colour || item.opacity), title: 'The colours of the Operator / Vendor Maps of the workspace for every series',
              onclick: () => guarded(() => setStyle(elementId, target => { for (const item of Object.values(target.series || {})) { delete item.colour; delete item.opacity; } }))()}, 'Default colours'))),
        group('Legend', h('div', {class: 'ds-design-two'},
          field('Position', selectInput(LEGEND_PLACES, style.legend?.position || '', value => set('legend.position', value))),
          field('Text size', selectInput(SIZES, style.legend?.size || '', value => set('legend.size', value)))),
        h('div', {class: 'ds-design-two'},
          textColour('Legend', style.legend?.colour, value => set('legend.colour', value)),
          // The legend is bold unless turned off.
          h('label', {class: 'ds-design-check'}, h('input', {type: 'checkbox', checked: style.legend?.bold !== false, onchange: event => set('legend.bold', event.target.checked ? '' : false)}), 'Bold'))),
        group('Labels', h('div', {class: 'ds-design-two'},
          field('Position', selectInput(LABEL_POSITIONS, style.labels?.position || '', value => set('labels.position', value))),
          field('Text size', selectInput(SIZES, style.labels?.size || '', value => set('labels.size', value)))),
        h('div', {class: 'ds-design-two'},
          textColour('Label', style.labels?.colour, value => set('labels.colour', value)),
          h('label', {class: 'ds-design-check'}, h('input', {type: 'checkbox', checked: Boolean(style.labels?.bold), onchange: event => set('labels.bold', event.target.checked || '')}), 'Bold'))),
        group('Axes', h('div', {class: 'ds-design-two'},
          field('X axis title', textInput(style.axes?.x?.title, host.debounced(value => setStyle(elementId, target => { target.axes = target.axes || {}; target.axes.x = {...(target.axes.x || {}), title: value}; })), {id: 'ds-design-axis-x-title', placeholder: 'As the chart names it'})),
          field('Y axis title', textInput(style.axes?.y?.title, host.debounced(value => setStyle(elementId, target => { target.axes = target.axes || {}; target.axes.y = {...(target.axes.y || {}), title: value}; })), {id: 'ds-design-axis-y-title', placeholder: 'As the chart names it'}))),
        field('X axis decimals', h('input', {type: 'number', min: '0', max: '6', step: '1', value: style.axes?.x?.decimals ?? '', placeholder: 'Default',
          onchange: event => set('axes.x.decimals', integer(event.target.value))}), 'The decimals of the values of the X axis of a CDF.')));
    }

    return {styleOf, formatSection, openSeriesFormat, openAxisRange, openAxisValues, orderValues: guarded(orderValues)};
  }

  window.ChartFormat = {editor};
})();
