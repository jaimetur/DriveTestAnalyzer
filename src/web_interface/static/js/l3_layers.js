/* Layer 3 - DT Logs on the maps of Non-Qualified Calls: the layers of the KMZ files of the NQ team, drawn from the parsed
   drivetest logs of the workspace (l3_dt_logs.call_layers).

   Every layer of the KMZ files is here: Direction, RAN Configuration, Events, L3 Signaling and the LTE and NR PCell, SCell
   and neighbour cells (EARFCN or NRARFCN, PCI, RSRP, RSRQ, SINR) and UE Tx Power, each split by its channel and then by
   its PCI, with the marker shapes and colour ranges of their legend (circle RSRP, triangle RSRQ, inverted triangle SINR,
   pentagon Tx Power, square channel and RAN Configuration, diamond PCI and L3, hexagon event, arrow direction; NR points
   with a black dot in the middle). A layer tree switches them on and off (the whole set, a layer, a channel or a PCI) and
   a click on a point shows its values. The maps keep their own drawing, navigation and images (nq_call_map.js). */
(() => {
  'use strict';

  const STATE_KEY = 'nq-l3-layers';
  // The colour ranges of the legend of the KMZ files: worst first (dark red) to best (blue).
  const RANGE_COLOURS = ['#8b0000', '#ff0000', '#ff8c00', '#ffe600', '#90ee64', '#00bfff', '#0000ff'];
  // The lower bound of every range after the first one, as the legend writes them.
  const SCALES = {
    rsrp: {label: 'RSRP', unit: 'dBm', bounds: [-120, -107, -100, -90, -80, -70]},
    rsrq: {label: 'RSRQ', unit: 'dB', bounds: [-24, -20, -16, -14, -12, -10]},
    sinr: {label: 'SINR', unit: 'dB', bounds: [-10, -5, 0, 5, 10, 20]},
  };
  // UE Tx Power, the other way round: the higher the worse (above 24, above 22, above 15, above 5, above 0, from −10, below).
  const TX_RANGES = [[24, '> 24'], [22, '22 – 24'], [15, '15 – 22'], [5, '5 – 15'], [0, '0 – 5'], [-10, '−10 – 0'], [-Infinity, '< −10']];
  const RAN_COLOURS = {'LTE': '#1c5dbf', '5G EN-DC': '#f22424', '5G SA': '#1cbf1c', 'GSM': '#24c26a', 'UNKNOWN': '#c924f2'};
  const EVENT_COLOURS = {'4G': '#00b000', '5G EN-DC': '#00bfff', '5G NR': '#0000ff', 'Other': '#868e96'};
  const L3_COLOURS = {'LTE-RRC': '#00b000', 'NR-RRC': '#0000ff', 'LTE-NAS': '#e6c200', 'NR-NAS': '#00bfff', 'SIP': '#9400d3', 'Other': '#868e96'};
  // The channels and PCIs, each in a colour of its own (the same channel or PCI keeps its colour on every map).
  const CATEGORY_COLOURS = ['#1c7ed6', '#e8590c', '#2b8a3e', '#ae3ec9', '#f08c00', '#0b7285', '#c2255c', '#5c940d', '#5f3dc4', '#a61e4d',
    '#1098ad', '#d9480f', '#364fc7', '#087f5b', '#862e9c', '#e67700'];
  const SHAPE_OF = {earfcn: 'square', nrarfcn: 'square', pci: 'diamond', rsrp: 'circle', rsrq: 'triangle', sinr: 'triangle-down',
    tx: 'pentagon', ran: 'square', event: 'hexagon', l3: 'diamond', direction: 'arrow'};
  const METRIC_LABELS = {earfcn: 'EARFCN', nrarfcn: 'NRARFCN', pci: 'PCI', rsrp: 'RSRP', rsrq: 'RSRQ', sinr: 'SINR', tx: 'UE Tx Power'};
  const EVENT_GROUPS = ['4G', '5G EN-DC', '5G NR', 'Other'];
  const L3_GROUPS = ['LTE-NAS', 'LTE-RRC', 'NR-NAS', 'NR-RRC', 'SIP', 'Other'];
  const RAN_GROUPS = ['LTE', '5G EN-DC', '5G SA', 'GSM', 'UNKNOWN'];
  // The layers of the tree, by section, as the KMZ files name them (LTE_PCell_RSRP...).
  const cellLayers = (prefix, kind, metrics) => metrics.map((metric) => ({key: `${kind}:${metric}`, kind, metric,
    name: `${prefix}_${metric === 'tx' ? 'UE_Tx_Power' : METRIC_LABELS[metric]}`, label: METRIC_LABELS[metric]}));
  const SECTIONS = [
    {key: 'route', label: 'Route', note: 'The way of the UE and its RAN', layers: [
      {key: 'direction', name: 'Direction', label: 'Direction of travel'},
      {key: 'ran', name: 'RAN_Configuration', label: 'RAN Configuration', groups: RAN_GROUPS}]},
    {key: 'signalling', label: 'Signalling', note: 'Events and L3 messages', layers: [
      {key: 'event', name: 'Event', label: 'Events', groups: EVENT_GROUPS},
      {key: 'l3', name: 'L3_Signaling', label: 'L3 Signaling', groups: L3_GROUPS}]},
    {key: 'lte', label: 'LTE', note: 'Serving, secondary and neighbour cells', blocks: [
      {label: 'PCell', layers: [...cellLayers('LTE_PCell', 'lte_pcell', ['earfcn', 'pci', 'rsrp', 'rsrq', 'sinr']),
        {key: 'lte_tx:tx', kind: 'lte_tx', metric: 'tx', name: 'LTE_PCell_UE_Tx_Power', label: 'UE Tx Power'}]},
      {label: 'SCell', layers: cellLayers('LTE_SCell', 'lte_scell', ['earfcn', 'pci', 'rsrp', 'rsrq', 'sinr'])},
      {label: 'NCell', layers: cellLayers('LTE_NCell', 'lte_ncell', ['earfcn', 'pci', 'rsrp', 'rsrq'])}]},
    {key: 'nr', label: 'NR', note: 'Serving, secondary and neighbour cells', blocks: [
      {label: 'PCell', layers: [...cellLayers('NR_PCell', 'nr_pcell', ['nrarfcn', 'pci', 'rsrp', 'rsrq', 'sinr']),
        {key: 'nr_tx:tx', kind: 'nr_tx', metric: 'tx', name: 'NR_PCell_UE_Tx_Power', label: 'UE Tx Power'}]},
      {label: 'SCell', layers: cellLayers('NR_SCell', 'nr_scell', ['nrarfcn', 'pci', 'rsrp', 'rsrq', 'sinr'])},
      {label: 'NCell', layers: cellLayers('NR_NCell', 'nr_ncell', ['nrarfcn', 'pci', 'rsrp', 'rsrq'])},
      {label: 'LTE NCell', layers: cellLayers('NR_LNCell', 'nr_lncell', ['earfcn', 'pci', 'rsrp', 'rsrq'])}]},
  ];
  const LAYERS = SECTIONS.flatMap((section) => (section.layers
    || section.blocks.flatMap((block) => block.layers.map((layer) => ({...layer, block: block.label})))).map((layer) => ({section: section.key, ...layer})));
  const LAYER = Object.fromEntries(LAYERS.map((layer) => [layer.key, layer]));
  const SERVING = new Set(['lte_pcell', 'lte_scell', 'lte_tx', 'nr_pcell', 'nr_scell', 'nr_tx', 'gsm', 'wcdma']);
  const NR_KINDS = new Set(['nr_pcell', 'nr_scell', 'nr_ncell', 'nr_tx']);
  // The layers of a new map: the PCell RSRP of LTE and NR, as the KMZ files open.
  const DEFAULT_ON = ['lte_pcell:rsrp', 'nr_pcell:rsrp'];

  const node = (tag, text, className) => {
    const element = document.createElement(tag);
    if (text !== undefined && text !== null) element.textContent = text;
    if (className) element.className = className;
    return element;
  };
  const number = (value, digits = 1) => (value === null || value === undefined || value === '' ? '' : Number(value).toFixed(digits).replace(/\.0+$/, ''));
  const hash = (text) => [...String(text)].reduce((value, character) => (value * 31 + character.charCodeAt(0)) >>> 0, 7);
  const categoryColour = (value) => CATEGORY_COLOURS[hash(value) % CATEGORY_COLOURS.length];

  // -- the colour and the shape of a point of a layer ------------------------------------------------------------------
  const rangeIndex = (metric, value) => {
    if (value === null || value === undefined) return -1;
    if (metric === 'tx') return TX_RANGES.findIndex(([low]) => (low === -Infinity ? true : low === -10 ? value >= low : value > low));
    const bounds = SCALES[metric].bounds;
    let index = 0;
    while (index < bounds.length && value >= bounds[index]) index += 1;
    return index;
  };
  const rangeColour = (metric, value) => {
    const index = rangeIndex(metric, value);
    if (index < 0) return '#adb5bd';
    return metric === 'tx' ? RANGE_COLOURS[RANGE_COLOURS.length - 1 - index] : RANGE_COLOURS[index];
  };
  const rangeLabels = (metric) => {
    if (metric === 'tx') return TX_RANGES.map(([, text], index) => [text, RANGE_COLOURS[RANGE_COLOURS.length - 1 - index]]);
    const bounds = SCALES[metric].bounds;
    return RANGE_COLOURS.map((colour, index) => [index === 0 ? `< ${bounds[0]}` : index === bounds.length ? `≥ ${bounds.at(-1)}`
      : `${bounds[index - 1]} – ${bounds[index]}`, colour]);
  };

  const shapePath = (context, shape, x, y, size) => {
    context.beginPath();
    if (shape === 'circle') { context.arc(x, y, size, 0, Math.PI * 2); return; }
    if (shape === 'square') { context.rect(x - size * .85, y - size * .85, size * 1.7, size * 1.7); return; }
    const polygon = (sides, rotation, scale = 1) => {
      for (let index = 0; index < sides; index += 1) {
        const angle = rotation + index * Math.PI * 2 / sides;
        const [px, py] = [x + Math.cos(angle) * size * scale, y + Math.sin(angle) * size * scale];
        if (index) context.lineTo(px, py); else context.moveTo(px, py);
      }
      context.closePath();
    };
    if (shape === 'diamond') polygon(4, -Math.PI / 2, 1.15);
    else if (shape === 'triangle') polygon(3, -Math.PI / 2, 1.25);
    else if (shape === 'triangle-down') polygon(3, Math.PI / 2, 1.25);
    else if (shape === 'pentagon') polygon(5, -Math.PI / 2, 1.1);
    else if (shape === 'hexagon') polygon(6, 0, 1.1);
    else context.arc(x, y, size, 0, Math.PI * 2);
  };
  const drawMarker = (context, shape, x, y, size, colour, {nr = false, outline = '#fff', heading = null} = {}) => {
    if (shape === 'arrow') {
      context.save();
      context.translate(x, y);
      context.rotate((heading || 0) * Math.PI / 180);
      context.beginPath();
      context.moveTo(0, -size * 1.3);
      context.lineTo(size, size);
      context.lineTo(0, size * .45);
      context.lineTo(-size, size);
      context.closePath();
      context.fillStyle = colour;
      context.strokeStyle = outline;
      context.lineWidth = 1.2;
      context.fill();
      context.stroke();
      context.restore();
      return;
    }
    shapePath(context, shape, x, y, size);
    context.fillStyle = colour;
    context.fill();
    context.lineWidth = 1.2;
    context.strokeStyle = outline;
    context.stroke();
    if (nr) {
      context.beginPath();
      context.arc(x, y, Math.max(1.4, size * .32), 0, Math.PI * 2);
      context.fillStyle = '#111';
      context.fill();
    }
  };
  // A small marker for the tree and the legend.
  const markerIcon = (shape, colour, {nr = false, size = 14} = {}) => {
    const canvas = node('canvas', undefined, 'nq-l3-icon');
    const ratio = window.devicePixelRatio || 1;
    canvas.width = size * ratio;
    canvas.height = size * ratio;
    canvas.style.width = `${size}px`;
    canvas.style.height = `${size}px`;
    const context = canvas.getContext('2d');
    context.scale(ratio, ratio);
    drawMarker(context, shape, size / 2, size / 2, size * .32, colour, {nr, outline: 'rgba(0,0,0,.35)', heading: 45});
    return canvas;
  };

  // -- the state of the layers, shared by every map of the page ---------------------------------------------------------
  const readState = () => {
    try { return JSON.parse(localStorage.getItem(STATE_KEY) || '{}') || {}; } catch (_error) { return {}; }
  };
  const stored = readState();
  const state = {
    master: stored.master !== false,
    on: new Set(Array.isArray(stored.on) ? stored.on.filter((key) => LAYER[key]) : DEFAULT_ON),
    // Channels (layer|channel) and PCIs (layer|channel|pci) switched off inside a layer that is on.
    off: new Set(Array.isArray(stored.off) ? stored.off : []),
    open: new Set(Array.isArray(stored.open) ? stored.open : ['lte', 'nr']),
    ue: stored.ue || 'all',
    panel: stored.panel !== false,
  };
  const saveState = () => {
    try {
      localStorage.setItem(STATE_KEY, JSON.stringify({master: state.master, on: [...state.on], off: [...state.off].slice(0, 400),
        open: [...state.open], ue: state.ue, panel: state.panel}));
    } catch (_error) { /* A private window keeps them for the page. */ }
  };
  const listeners = new Set();
  const changed = () => { saveState(); listeners.forEach((listener) => listener()); };

  // -- the data of a call (or of several), ready to draw -------------------------------------------------------------
  const channelKey = (kind, freq) => `${NR_KINDS.has(kind) ? 'NR' : 'LTE'}:${freq}`;
  // The points of the layers of the payload of call_layers: by layer, each with its channel and PCI groups.
  const prepare = (payload) => {
    if (!payload || !payload.ues || !Object.keys(payload.ues).length) return null;
    const columns = payload.columns;
    const at = Object.fromEntries(columns.map((name, index) => [name, index]));
    const channels = payload.channels || {};
    const ues = Object.keys(payload.ues).sort();
    const points = [];
    const tracks = {};
    for (const ue of ues) {
      const item = payload.ues[ue];
      tracks[ue] = (item.track || []).map(([ms, lat, lon]) => ({ms, lat, lon}));
      for (const row of item.points || []) {
        const point = {ue, dataset: item.session.dataset_id};
        for (const name of columns) point[name] = row[at[name]];
        if (point.freq !== null && point.freq !== undefined) point.channel = channels[channelKey(point.kind, point.freq)] || String(point.freq);
        points.push(point);
      }
    }
    // Every layer: its points, then by channel (or group) and PCI.
    const layers = {};
    const add = (layerKey, point, group, sub) => {
      const layer = layers[layerKey] || (layers[layerKey] = {count: 0, groups: new Map()});
      layer.count += 1;
      const entry = layer.groups.get(group) || {count: 0, subs: new Map()};
      entry.count += 1;
      if (sub !== null) entry.subs.set(sub, (entry.subs.get(sub) || 0) + 1);
      layer.groups.set(group, entry);
    };
    for (const point of points) {
      if (point.kind === 'event') add('event', point, point.grp || 'Other', null);
      else if (point.kind === 'l3') add('l3', point, point.grp || 'Other', null);
      if (SERVING.has(point.kind)) add('ran', point, point.ran || 'UNKNOWN', null);
      for (const layer of LAYERS) {
        if (layer.kind !== point.kind) continue;
        if (['rsrp', 'rsrq', 'sinr', 'tx'].includes(layer.metric) && (point[layer.metric] === null || point[layer.metric] === undefined)) continue;
        add(layer.key, point, layer.metric === 'tx' ? '' : point.channel || '', layer.metric === 'tx' ? null : `PCI ${point.pci ?? '—'}`);
      }
    }
    const trackPoints = Object.values(tracks).flat();
    if (trackPoints.length > 1) layers.direction = {count: trackPoints.length, groups: new Map()};
    const sessions = Object.fromEntries(ues.map((ue) => [ue, payload.ues[ue].session]));
    return {points, layers, tracks, ues, sessions, joinId: payload.join_id};
  };

  const ueShown = (data, ue) => state.ue === 'all' || !data.ues.includes(state.ue) || ue === state.ue;
  // Whether a point is drawn by a layer: the layer, its channel (or group) and its PCI on.
  const pointLayerShown = (layerKey, point) => {
    if (!state.master || !state.on.has(layerKey)) return false;
    const layer = LAYER[layerKey];
    const group = layerKey === 'event' || layerKey === 'l3' ? point.grp || 'Other' : layerKey === 'ran' ? point.ran || 'UNKNOWN'
      : layer.metric === 'tx' ? '' : point.channel || '';
    if (state.off.has(`${layerKey}|${group}`)) return false;
    if (layer.kind && layer.metric !== 'tx' && state.off.has(`${layerKey}|${group}|PCI ${point.pci ?? '—'}`)) return false;
    return true;
  };
  const colourOf = (layerKey, point) => {
    const layer = LAYER[layerKey];
    if (layerKey === 'ran') return RAN_COLOURS[point.ran] || RAN_COLOURS.UNKNOWN;
    if (layerKey === 'event') return EVENT_COLOURS[point.grp] || EVENT_COLOURS.Other;
    if (layerKey === 'l3') return L3_COLOURS[point.grp] || L3_COLOURS.Other;
    if (layer.metric === 'earfcn' || layer.metric === 'nrarfcn') return categoryColour(point.channel);
    if (layer.metric === 'pci') return categoryColour(`PCI ${point.pci}`);
    return rangeColour(layer.metric, point[layer.metric]);
  };

  // -- drawing on a map ------------------------------------------------------------------------------------------------
  // The way of each UE, its direction arrows and the points of every layer on (the serving cells above their neighbours),
  // each one a hit for the tooltip and the selection of the map.
  const DRAW_ORDER = ['direction', 'ran', 'lte_ncell', 'nr_lncell', 'nr_ncell', 'lte_scell', 'nr_scell', 'lte_pcell', 'nr_pcell', 'lte_tx', 'nr_tx', 'event', 'l3'];
  const drawOrder = (layerKey) => {
    const kind = LAYER[layerKey]?.kind || layerKey;
    const index = DRAW_ORDER.indexOf(kind);
    return index < 0 ? DRAW_ORDER.length : index;
  };
  const draw = (context, data, {project, hits, zoom = 15, width = Infinity, height = Infinity}) => {
    if (!data || !state.master) return;
    const size = zoom >= 17 ? 5.2 : zoom >= 15 ? 4.4 : zoom >= 13 ? 3.6 : 3;
    const layersOn = [...state.on].filter((key) => data.layers[key]).sort((a, b) => drawOrder(a) - drawOrder(b));
    if (layersOn.includes('direction')) {
      for (const ue of data.ues) {
        if (!ueShown(data, ue)) continue;
        const track = data.tracks[ue] || [];
        let last = null;
        for (let index = 0; index < track.length - 1; index += 1) {
          const [x1, y1] = project(track[index].lat, track[index].lon), [x2, y2] = project(track[index + 1].lat, track[index + 1].lon);
          if (Math.hypot(x2 - x1, y2 - y1) < .5) continue;
          if (last && Math.hypot(x1 - last[0], y1 - last[1]) < 34) continue;
          const heading = Math.atan2(x2 - x1, -(y2 - y1)) * 180 / Math.PI;
          drawMarker(context, 'arrow', x1, y1, size * 1.25, ue === 'B' ? '#495057' : '#212529', {heading});
          hits.push({x: x1, y: y1, r: size + 4, kind: 'l3', item: {layer: 'direction', point: {...track[index], ue, heading: (heading + 360) % 360}}, priority: 3.9});
          last = [x1, y1];
        }
      }
    }
    for (const layerKey of layersOn) {
      if (layerKey === 'direction') continue;
      const layer = LAYER[layerKey];
      const shape = layer.metric ? SHAPE_OF[layer.metric] : SHAPE_OF[layerKey];
      for (const point of data.points) {
        if (point.lat === null || point.lon === null || !ueShown(data, point.ue)) continue;
        const kindMatches = layerKey === 'ran' ? SERVING.has(point.kind) : layerKey === 'event' || layerKey === 'l3' ? point.kind === layerKey : point.kind === layer.kind;
        if (!kindMatches) continue;
        if (layer.metric && ['rsrp', 'rsrq', 'sinr', 'tx'].includes(layer.metric) && (point[layer.metric] === null || point[layer.metric] === undefined)) continue;
        if (!pointLayerShown(layerKey, point)) continue;
        const [x, y] = project(point.lat, point.lon);
        if (x < -20 || y < -20 || x > width + 20 || y > height + 20) continue;
        const neighbour = /ncell/.test(point.kind);
        const pointSize = neighbour ? size * .82 : layerKey === 'event' || layerKey === 'l3' ? size * 1.08 : size;
        drawMarker(context, shape, x, y, pointSize, colourOf(layerKey, point), {nr: NR_KINDS.has(point.kind)});
        hits.push({x, y, r: pointSize + 3, kind: 'l3', item: {layer: layerKey, point}, priority: layerKey === 'event' || layerKey === 'l3' ? 4.2 : 4.1});
      }
    }
  };
  // The way of the UE shown (A, else the first UE) for the road of the call, its start and its end.
  const wayOf = (data) => {
    if (!data) return null;
    const ue = state.ue !== 'all' && data.tracks[state.ue] ? state.ue : data.ues.includes('A') ? 'A' : data.ues[0];
    const track = data.tracks[ue] || [];
    return track.length > 1 ? track.map((point) => [point.lat, point.lon]) : null;
  };
  const bounds = (data) => {
    const points = Object.values(data?.tracks || {}).flat();
    if (!points.length) return null;
    return {north: Math.max(...points.map((point) => point.lat)), south: Math.min(...points.map((point) => point.lat)),
      east: Math.max(...points.map((point) => point.lon)), west: Math.min(...points.map((point) => point.lon))};
  };

  // -- what a point says (the tooltip and the selection) ----------------------------------------------------------------
  const time = (point) => String(point.ts || '').replace(/^\d{4}-\d{2}-\d{2} /, '');
  const describe = (item, data) => {
    const {layer: layerKey, point} = item;
    const layer = LAYER[layerKey];
    const session = data?.sessions?.[point.ue] || {};
    const common = [['Time', point.ts || ''], ['UE', point.ue === 'Data' ? 'Data' : `UE ${point.ue}`], ['RAN Configuration', point.ran || '']];
    if (layerKey === 'direction') {
      return {title: 'Direction of travel', rows: [['Time', point.ms ? new Date(point.ms).toISOString().replace('T', ' ').slice(0, 23) : ''],
        ['UE', point.ue], ['Heading', `${Math.round(point.heading)}°`]]};
    }
    if (point.kind === 'event') {
      return {title: point.name || 'Event', rows: [...common, ['Group', point.grp], ['Summary', point.detail || ''], ['JoinID', data?.joinId]]};
    }
    if (point.kind === 'l3') {
      const way = String(point.direction || '').toUpperCase();
      return {title: point.name || 'L3 message', rows: [...common, ['Layer', point.grp], ['Direction', ['U', 'UL'].includes(way) ? 'Uplink'
        : ['D', 'DL'].includes(way) ? 'Downlink' : point.direction || ''], ['SIP', point.detail || ''],
      ['Channel', point.channel || ''], ['PCI', point.pci ?? ''], ['JoinID', data?.joinId]]};
    }
    const kindLabel = {lte_pcell: 'LTE PCell', lte_scell: 'LTE SCell', lte_ncell: 'LTE NCell', nr_pcell: 'NR PCell', nr_scell: 'NR SCell',
      nr_ncell: 'NR NCell', nr_lncell: 'LTE NCell of NR', lte_tx: 'LTE PCell', nr_tx: 'NR PCell', gsm: 'GSM serving cell', wcdma: 'WCDMA serving cell'}[point.kind] || point.kind;
    const value = layer?.metric && ['rsrp', 'rsrq', 'sinr', 'tx'].includes(layer.metric) ? point[layer.metric] : null;
    const unit = layer?.metric === 'tx' ? 'dBm' : SCALES[layer?.metric]?.unit || '';
    const title = layerKey === 'ran' ? `${point.ran || 'RAN'} · ${kindLabel}`
      : `${kindLabel} ${layer?.label || ''}${value !== null ? ` · ${number(value)} ${unit}` : ''}`.trim();
    return {title, rows: [...common, ['Channel', point.channel || ''], ['PCI', point.pci ?? ''],
      ['RSRP', point.rsrp !== null && point.rsrp !== undefined ? `${number(point.rsrp)} dBm` : ''],
      ['RSRQ', point.rsrq !== null && point.rsrq !== undefined ? `${number(point.rsrq)} dB` : ''],
      ['SINR', point.sinr !== null && point.sinr !== undefined ? `${number(point.sinr)} dB` : ''],
      ['UE Tx Power', point.tx !== null && point.tx !== undefined ? `${number(point.tx)} dBm` : ''],
      [NR_KINDS.has(point.kind) ? 'NCI' : 'ECI', point.cell || ''], ['Session', [session.service, session.call_status].filter(Boolean).join(' · ')]]};
  };

  // -- the layer tree ----------------------------------------------------------------------------------------------------
  const toggle = (checked, label, onChange, {small = false} = {}) => {
    const wrap = node('label', undefined, `nq-l3-switch${small ? ' is-small' : ''}`);
    const box = node('input');
    box.type = 'checkbox';
    box.checked = checked;
    box.setAttribute('aria-label', label);
    box.addEventListener('change', () => onChange(box.checked));
    wrap.append(box, node('span', undefined, 'nq-l3-switch-track'));
    return wrap;
  };
  const count = (value) => node('span', Number(value).toLocaleString('en-GB'), 'nq-l3-count');
  const layerColour = (layer) => (layer.key === 'ran' ? RAN_COLOURS.LTE : layer.key === 'event' ? EVENT_COLOURS['4G']
    : layer.key === 'l3' ? L3_COLOURS.SIP : layer.key === 'direction' ? '#212529' : layer.metric === 'earfcn' || layer.metric === 'nrarfcn'
      ? '#1c7ed6' : layer.metric === 'pci' ? '#ae3ec9' : layer.metric === 'tx' ? RANGE_COLOURS[2] : RANGE_COLOURS[5]);
  const groupColour = (layer, group) => (layer.key === 'ran' ? RAN_COLOURS[group] : layer.key === 'event' ? EVENT_COLOURS[group]
    : layer.key === 'l3' ? L3_COLOURS[group] : categoryColour(group));

  // The tree of the layers of a map, in ``host``; ``redraw`` paints the map again after a change.
  const createTree = (host, getData, redraw) => {
    const panel = node('section', undefined, 'nq-l3-panel');
    const render = () => {
      const data = getData();
      panel.hidden = !data;
      if (!data) { panel.replaceChildren(); return; }
      panel.classList.toggle('is-collapsed', !state.panel);
      const head = node('header', undefined, 'nq-l3-head');
      const title = node('button', undefined, 'nq-l3-title');
      title.type = 'button';
      title.setAttribute('aria-expanded', String(state.panel));
      title.title = state.panel ? 'Fold the layers' : 'Show the layers of the Layer 3 - DT Logs';
      title.append(node('span', 'Layer 3 - DT Logs', 'nq-l3-title-text'), node('span', state.panel ? '▾' : '▸', 'nq-l3-chevron'));
      title.addEventListener('click', (event) => { event.stopPropagation(); state.panel = !state.panel; changed(); });
      head.append(title, toggle(state.master, 'Show the Layer 3 - DT Logs', (checked) => { state.master = checked; changed(); }));
      panel.replaceChildren(head);
      if (!state.panel) return;
      const body = node('div', undefined, 'nq-l3-body');
      if (!state.master) body.classList.add('is-off');
      // The two ends of a voice call: one of them or both.
      if (data.ues.length > 1) {
        const ues = node('div', undefined, 'nq-l3-ues');
        ues.setAttribute('role', 'radiogroup');
        ues.setAttribute('aria-label', 'UE shown');
        for (const [value, text] of [['all', 'Both'], ...data.ues.map((ue) => [ue, `UE ${ue}`])]) {
          const button = node('button', text, `nq-l3-ue${state.ue === value ? ' is-on' : ''}`);
          button.type = 'button';
          button.setAttribute('role', 'radio');
          button.setAttribute('aria-checked', String(state.ue === value));
          button.addEventListener('click', (event) => { event.stopPropagation(); state.ue = value; changed(); });
          ues.append(button);
        }
        body.append(ues);
      }
      const layerRow = (layer) => {
        const info = data.layers[layer.key];
        if (!info) return null;
        const row = node('div', undefined, 'nq-l3-layer');
        const line = node('div', undefined, 'nq-l3-line');
        const on = state.on.has(layer.key);
        const expandable = info.groups.size > 1 || [...info.groups.values()].some((entry) => entry.subs.size > 1);
        const openKey = `layer:${layer.key}`;
        const nr = layer.kind && NR_KINDS.has(layer.kind);
        line.append(toggle(on, `Show ${layer.label}`, (checked) => { if (checked) state.on.add(layer.key); else state.on.delete(layer.key); changed(); }),
          markerIcon(layer.metric ? SHAPE_OF[layer.metric] : SHAPE_OF[layer.key], layerColour(layer), {nr}));
        const name = node('span', layer.label, 'nq-l3-name');
        name.title = layer.name;
        line.append(name, count(info.count));
        if (expandable) {
          const more = node('button', state.open.has(openKey) ? '−' : '+', 'nq-l3-more');
          more.type = 'button';
          more.title = state.open.has(openKey) ? 'Fold its channels and PCIs' : 'Show its channels and PCIs';
          more.addEventListener('click', (event) => { event.stopPropagation(); if (state.open.has(openKey)) state.open.delete(openKey); else state.open.add(openKey); changed(); });
          line.append(more);
        }
        row.append(line);
        if (expandable && state.open.has(openKey)) {
          const groups = node('div', undefined, 'nq-l3-groups');
          for (const [group, entry] of [...info.groups.entries()].sort((a, b) => b[1].count - a[1].count)) {
            const groupKey = `${layer.key}|${group}`;
            const groupRow = node('div', undefined, 'nq-l3-group');
            const groupLine = node('div', undefined, 'nq-l3-line');
            groupLine.append(toggle(!state.off.has(groupKey), `Show ${group}`, (checked) => {
              if (checked) state.off.delete(groupKey); else state.off.add(groupKey); changed();
            }, {small: true}));
            const swatch = node('span', undefined, 'nq-l3-swatch');
            swatch.style.background = groupColour(layer, group);
            groupLine.append(swatch, node('span', group || '—', 'nq-l3-name'), count(entry.count));
            groupRow.append(groupLine);
            if (entry.subs.size) {
              const chips = node('div', undefined, 'nq-l3-chips');
              for (const [sub, subCount] of [...entry.subs.entries()].sort((a, b) => b[1] - a[1])) {
                const subKey = `${groupKey}|${sub}`;
                const chip = node('button', undefined, `nq-l3-chip${state.off.has(subKey) ? '' : ' is-on'}`);
                chip.type = 'button';
                chip.setAttribute('aria-pressed', String(!state.off.has(subKey)));
                chip.title = `${state.off.has(subKey) ? 'Show' : 'Hide'} ${sub} of ${group}`;
                const dot = node('span', undefined, 'nq-l3-chip-dot');
                dot.style.background = categoryColour(sub);
                chip.append(dot, node('span', sub.replace('PCI ', '')), node('small', String(subCount)));
                chip.addEventListener('click', (event) => { event.stopPropagation(); if (state.off.has(subKey)) state.off.delete(subKey); else state.off.add(subKey); changed(); });
                chips.append(chip);
              }
              groupRow.append(chips);
            }
            groups.append(groupRow);
          }
          row.append(groups);
        }
        return row;
      };
      for (const section of SECTIONS) {
        const layers = section.layers ? section.layers : section.blocks.flatMap((block) => block.layers);
        const shown = layers.filter((layer) => data.layers[layer.key]);
        if (!shown.length) continue;
        const card = node('section', undefined, `nq-l3-section is-${section.key}`);
        const opened = state.open.has(section.key);
        const sectionHead = node('button', undefined, 'nq-l3-section-head');
        sectionHead.type = 'button';
        sectionHead.setAttribute('aria-expanded', String(opened));
        const active = shown.filter((layer) => state.on.has(layer.key)).length;
        sectionHead.append(node('span', section.label, 'nq-l3-section-name'), node('span', section.note, 'nq-l3-section-note'),
          node('span', active ? `${active} on` : '', 'nq-l3-section-on'), node('span', opened ? '▾' : '▸', 'nq-l3-chevron'));
        sectionHead.addEventListener('click', (event) => { event.stopPropagation(); if (opened) state.open.delete(section.key); else state.open.add(section.key); changed(); });
        card.append(sectionHead);
        if (opened) {
          const list = node('div', undefined, 'nq-l3-section-body');
          if (section.layers) shown.forEach((layer) => list.append(layerRow(layer)));
          else {
            for (const block of section.blocks) {
              const rows = block.layers.filter((layer) => data.layers[layer.key]);
              if (!rows.length) continue;
              list.append(node('p', block.label, 'nq-l3-block'));
              rows.forEach((layer) => list.append(layerRow(layer)));
            }
          }
          card.append(list);
        }
        body.append(card);
      }
      const footer = node('div', undefined, 'nq-l3-footer');
      const none = node('button', 'Hide all', 'nq-l3-link');
      none.type = 'button';
      none.addEventListener('click', (event) => { event.stopPropagation(); state.on.clear(); changed(); });
      const reset = node('button', 'PCell RSRP', 'nq-l3-link');
      reset.type = 'button';
      reset.title = 'Show only the PCell RSRP of LTE and NR, as the map opens';
      reset.addEventListener('click', (event) => { event.stopPropagation(); state.on = new Set(DEFAULT_ON); state.off.clear(); changed(); });
      footer.append(none, reset);
      body.append(footer);
      panel.append(body);
    };
    // The wheel and the clicks of the tree stay in it (they never move the map).
    ['wheel', 'pointerdown', 'dblclick'].forEach((type) => panel.addEventListener(type, (event) => event.stopPropagation(), {passive: true}));
    host.append(panel);
    const listener = () => { render(); redraw(); };
    listeners.add(listener);
    render();
    return {render, destroy: () => { listeners.delete(listener); panel.remove(); }};
  };

  // -- the legend of the layers on (below the map, in its images too) ------------------------------------------------
  const legend = (data) => {
    if (!data || !state.master) return null;
    const layersOn = [...state.on].filter((key) => data.layers[key]);
    if (!layersOn.length) return null;
    const box = node('div', undefined, 'nq-l3-legend');
    box.append(node('p', 'Layer 3 - DT Logs', 'nq-l3-legend-title'));
    const metricsShown = new Map();
    for (const key of layersOn) {
      const layer = LAYER[key];
      if (['rsrp', 'rsrq', 'sinr', 'tx'].includes(layer.metric)) {
        const entry = metricsShown.get(layer.metric) || {layers: [], nr: false};
        entry.layers.push(`${layer.section === 'nr' ? 'NR' : 'LTE'} ${layer.block || ''}`.trim());
        entry.nr = entry.nr || NR_KINDS.has(layer.kind);
        metricsShown.set(layer.metric, entry);
      }
    }
    for (const [metric, entry] of metricsShown) {
      const row = node('div', undefined, 'nq-l3-legend-row');
      row.append(node('span', `${METRIC_LABELS[metric]} (${metric === 'tx' ? 'dBm' : SCALES[metric].unit})`, 'nq-l3-legend-name'));
      for (const [text, colour] of rangeLabels(metric)) {
        const item = node('span', undefined, 'nq-l3-legend-item');
        item.append(markerIcon(SHAPE_OF[metric], colour), node('span', text));
        row.append(item);
      }
      box.append(row);
    }
    for (const key of layersOn.filter((item) => ['ran', 'event', 'l3'].includes(item))) {
      const layer = LAYER[key];
      const colours = key === 'ran' ? RAN_COLOURS : key === 'event' ? EVENT_COLOURS : L3_COLOURS;
      const row = node('div', undefined, 'nq-l3-legend-row');
      row.append(node('span', layer.label, 'nq-l3-legend-name'));
      for (const group of data.layers[key].groups.keys()) {
        const item = node('span', undefined, 'nq-l3-legend-item');
        item.append(markerIcon(SHAPE_OF[key], colours[group] || '#868e96'), node('span', group));
        row.append(item);
      }
      box.append(row);
    }
    const channelLayers = layersOn.filter((key) => ['earfcn', 'nrarfcn', 'pci'].includes(LAYER[key].metric) || key === 'direction');
    if (channelLayers.length) {
      const row = node('div', undefined, 'nq-l3-legend-row');
      row.append(node('span', 'Shapes', 'nq-l3-legend-name'));
      for (const key of channelLayers) {
        const layer = LAYER[key];
        const item = node('span', undefined, 'nq-l3-legend-item');
        item.append(markerIcon(layer.metric ? SHAPE_OF[layer.metric] : SHAPE_OF[key], layerColour(layer), {nr: NR_KINDS.has(layer.kind)}),
          node('span', `${layer.section === 'nr' ? 'NR ' : layer.section === 'lte' ? 'LTE ' : ''}${layer.block ? `${layer.block} ` : ''}${layer.label}`));
        row.append(item);
      }
      box.append(row);
    }
    const note = node('p', 'NR points have a black dot in the middle. A channel or a PCI keeps its colour on every map.', 'nq-l3-legend-note');
    box.append(note);
    return box;
  };

  window.L3Layers = {prepare, draw, describe, createTree, legend, wayOf, bounds, state, onChange: (listener) => listeners.add(listener),
    LAYERS, SECTIONS, rangeColour, rangeIndex};
})();
