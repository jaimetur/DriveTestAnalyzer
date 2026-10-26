/* Non-Qualified Calls → the map of a call: the area where it failed with what helps its analysis and troubleshooting.
   The call (where it started and ended) and the cells it went through at their sites, the inventory sites around with their
   sectors, bands, PCI and states, the other Non-Qualified Calls around (its repetitions at the same site and its hotspot)
   and the radio levels (LTE and NR RSRP and SINR) of the tests around it, on OpenStreetMap.

   It navigates like the maps of Network Insights: dragging moves it, Ctrl/Cmd+wheel (or a pinch) zooms towards the
   pointer (in the larger map the wheel alone too; in the call panel the wheel alone scrolls the panel), Ctrl/Cmd+drag
   draws a rectangle to zoom into, Alt/Opt+drag measures a distance and its bearing, the − / + / Fit buttons zoom, a
   double-click opens it larger (where a double-click zooms in) and the image buttons download it as a PNG image or copy
   it as a screenshot (image_buttons.js). The RSRP / SINR samples show only when their button of the map is on. */
(() => {
  'use strict';

  const REFERENCE_ZOOM = 21, MIN_TILE_ZOOM = 3, MAX_TILE_ZOOM = 19, WEDGES_FROM_ZOOM = 14, LABELS_FROM_ZOOM = 15;
  const MIN_RESOLUTION = 2 ** (REFERENCE_ZOOM - MAX_TILE_ZOOM) / 4, MAX_RESOLUTION = 2 ** (REFERENCE_ZOOM - MIN_TILE_ZOOM);
  const WORLD = 256 * 2 ** REFERENCE_ZOOM;
  const COLOURS = {
    call: '#b0234f', path: '#3d1824', start: '#2e8b57', handover: '#f08a24', end: '#d7263d', both: '#d7263d', nr_leg: '#6d46a8',
    group: '#d62828', place: '#7b3fe4', own: '#f08a24', other: '#6c757d', samePci: '#d6336c', noValue: '#adb5bd',
    completed: '#2e8b57', failed: '#d7263d', radius: '#7d1238',
    sameType: '#b0234f', otherType: '#1c7ed6', sameCampaign: '#b0234f', otherCampaign: '#6c757d',
  };
  // Whether an NQ call is of a group of the call: its hotspot, its cluster or its run of consecutive failures.
  const inGroup = (failure) => Boolean(failure.same_hotspot || failure.same_cluster || failure.same_run);
  // The test columns of the payload (see nq_call_map.nearby_tests).
  const COLUMN = {latitude: 0, longitude: 1, operator: 2, kind: 3, failed: 4, lte_rsrp: 5, lte_sinr: 6, nr_rsrp: 7, nr_sinr: 8, test: 9, start: 10, cdr: 11};
  const METRICS = {
    lte_rsrp: {label: 'LTE RSRP', unit: 'dBm', classes: 'rsrp'}, lte_sinr: {label: 'LTE SINR', unit: 'dB', classes: 'sinr'},
    nr_rsrp: {label: 'NR RSRP', unit: 'dBm', classes: 'rsrp'}, nr_sinr: {label: 'NR SINR', unit: 'dB', classes: 'sinr'},
    result: {label: 'Result (completed or failed)', unit: ''},
  };
  const KIND_LABELS = {voice: 'Voice', whatsapp: 'WhatsApp', data: 'Data', ping: 'Ping', speech: 'Speech'};
  const SERVICE_LABELS = {voice: 'Voice', speech: 'Speech', data: 'Data'};
  // The layers chosen above the map; the RSRP / SINR samples have their own button on the map.
  const LAYERS = {failures: 'NQ calls', sites: 'Sites', path: 'Cell path'};
  const FAILURE_SCOPES = {cdr: 'This CDR', campaign: 'Its campaign', every: 'Every campaign'};
  // What the colour of the NQ calls tells (their size always marks those of its groups and of its site).
  const FAILURE_COLOURS = {relation: 'Relation', type: 'Call type', campaign: 'Campaign'};
  const SETTINGS_KEY = 'nq-call-map-settings';
  const HINT = 'Drag to move · wheel or Ctrl/Cmd+wheel to zoom · Ctrl/Cmd+drag a rectangle to zoom into it · Alt/Opt+drag to measure · double-click to zoom in';
  const PANEL_HINT = 'Drag to move · Ctrl/Cmd+wheel to zoom · Ctrl/Cmd+drag a rectangle to zoom into it · Alt/Opt+drag to measure · double-click to enlarge';

  const node = (tag, text, className) => {
    const element = document.createElement(tag);
    if (text !== undefined && text !== null) element.textContent = text;
    if (className) element.className = className;
    return element;
  };
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const toWorld = (latitude, longitude) => {
    const radians = clamp(Number(latitude), -85.05112878, 85.05112878) * Math.PI / 180;
    return [(Number(longitude) + 180) / 360 * WORLD, (1 - Math.asinh(Math.tan(radians)) / Math.PI) / 2 * WORLD];
  };
  const toLonLat = (x, y) => [x / WORLD * 360 - 180, Math.atan(Math.sinh(Math.PI * (1 - 2 * y / WORLD))) * 180 / Math.PI];
  const metresPerWorldPixel = (latitude) => 40075016.686 * Math.cos(latitude * Math.PI / 180) / WORLD;
  const geodesic = ([lon1, lat1], [lon2, lat2]) => {
    const radians = Math.PI / 180, phi1 = lat1 * radians, phi2 = lat2 * radians, dPhi = phi2 - phi1, dLambda = (lon2 - lon1) * radians;
    const a = Math.sin(dPhi / 2) ** 2 + Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLambda / 2) ** 2;
    const bearing = Math.atan2(Math.sin(dLambda) * Math.cos(phi2), Math.cos(phi1) * Math.sin(phi2) - Math.sin(phi1) * Math.cos(phi2) * Math.cos(dLambda));
    return {metres: 6371008.8 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a)), bearing: (bearing / radians + 360) % 360};
  };
  const distanceText = (km) => (km === null || km === undefined ? '' : km < 1 ? `${Math.round(km * 1000)} m` : `${Number(km).toFixed(km < 10 ? 2 : 1)} km`);
  const metresText = (metres) => distanceText(metres / 1000);
  const dbText = (value, unit) => (value === null || value === undefined || value === '' ? '—' : `${Number(value).toFixed(1)} ${unit}`);
  const median = (values) => {
    if (!values.length) return null;
    const sorted = [...values].sort((a, b) => a - b), middle = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
  };
  const readSettings = () => {
    try { return JSON.parse(localStorage.getItem(SETTINGS_KEY) || '{}') || {}; } catch (_error) { return {}; }
  };
  const storeSettings = (settings) => {
    try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings)); } catch (_error) { /* A private window keeps them for the page. */ }
  };

  // -- OpenStreetMap tiles, shared by every map of the page -------------------------------------------
  const tiles = new Map();
  const tile = (url, redraw) => {
    let record = tiles.get(url);
    if (!record) {
      const image = new Image();
      record = {image, status: 'loading', waiting: new Set()};
      image.addEventListener('load', () => { record.status = 'ready'; record.waiting.forEach((callback) => callback()); record.waiting.clear(); });
      image.addEventListener('error', () => {
        // A tile server that does not allow it is asked again plainly: the map shows, but cannot be saved as an image.
        if (image.crossOrigin) { image.removeAttribute('crossorigin'); image.src = url; return; }
        record.status = 'error';
        record.waiting.clear();
      });
      image.decoding = 'async';
      // Asked for with CORS, so the map can be saved as an image or copied as a screenshot.
      image.crossOrigin = 'anonymous';
      image.src = url;
      tiles.set(url, record);
    }
    if (record.status === 'loading') record.waiting.add(redraw);
    return record;
  };

  // Holding Ctrl/Cmd turns the hand over the maps into the crosshair of the zoom rectangle, and Alt/Opt into the ruler.
  const modifierKeys = (event) => {
    const root = document.documentElement;
    root.classList.toggle('nq-map-ruler', Boolean(event.altKey));
    root.classList.toggle('nq-map-rectangle', !event.altKey && Boolean(event.ctrlKey || event.metaKey));
  };
  window.addEventListener('keydown', modifierKeys);
  window.addEventListener('keyup', modifierKeys);
  window.addEventListener('blur', () => document.documentElement.classList.remove('nq-map-ruler', 'nq-map-rectangle'));

  // The colour of a test for the measure chosen (its class, as the maps of Network Insights), grey without a value.
  const testColour = (row, metric, classes) => {
    if (metric === 'result') return row[COLUMN.failed] ? COLOURS.failed : COLOURS.completed;
    const value = row[COLUMN[metric]];
    if (value === null || value === undefined) return COLOURS.noValue;
    const levels = classes[METRICS[metric].classes] || [];
    return (levels.find((level) => level.lower === null || value >= level.lower) || levels.at(-1) || {}).colour || COLOURS.noValue;
  };

  // One map view of a call (the one in the panel, or the larger one): its canvas, controls, legend and tooltip.
  function createView(card, shared, {expanded = false, onExpand = null, legendHost = null} = {}) {
    card.classList.add('nq-map-card');
    const canvas = node('canvas', undefined, 'nq-map-canvas');
    canvas.setAttribute('role', 'img');
    canvas.setAttribute('aria-label', 'Map of the area where the call failed');
    canvas.tabIndex = 0;
    const tooltip = node('div', undefined, 'nq-map-tooltip');
    tooltip.hidden = true;
    const selectionBox = node('div', undefined, 'nq-map-selection');
    selectionBox.hidden = true;
    const ruler = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    ruler.setAttribute('class', 'nq-map-measure');
    ruler.setAttribute('aria-hidden', 'true');
    const legend = node('div', undefined, 'nq-map-legend');
    const attribution = node('div', '© OpenStreetMap contributors', 'nq-map-attribution');
    // The RSRP / SINR samples: shown or hidden with their own button, and the measure that colours them.
    const samples = node('div', undefined, 'nq-map-samples');
    const samplesToggle = node('button', undefined, 'nq-map-samples-toggle');
    samplesToggle.type = 'button';
    samplesToggle.append(node('span', undefined, 'nq-map-samples-dot'), node('span', 'RSRP / SINR samples'));
    samplesToggle.addEventListener('click', (event) => { event.stopPropagation(); shared.setSamples(!shared.settings.layers.tests); });
    const samplesMeasure = node('select', undefined, 'nq-map-samples-measure');
    samplesMeasure.setAttribute('aria-label', 'Colour the samples by');
    samplesMeasure.title = 'Colour the samples by';
    for (const [key, metric] of Object.entries(METRICS)) {
      const option = node('option', metric.label);
      option.value = key;
      samplesMeasure.append(option);
    }
    samplesMeasure.addEventListener('change', () => shared.setColour(samplesMeasure.value));
    samples.append(samplesToggle, samplesMeasure);
    samples.hidden = true;
    // In the call panel the wheel alone scrolls the panel: a moment's note says how to zoom.
    const wheelHint = node('div', 'Ctrl/Cmd + wheel to zoom the map', 'nq-map-wheel-hint');
    wheelHint.hidden = true;
    let wheelHintTimer = 0;
    const level = node('output', '', 'nq-map-zoom-level');
    const controls = node('div', undefined, `nq-map-zoom${expanded ? ' is-shown' : ''}`);
    controls.setAttribute('role', 'group');
    controls.setAttribute('aria-label', 'Map zoom');
    const button = (text, title, action, className = '') => {
      const element = node('button', text, `nq-map-zoom-button ${className}`.trim());
      element.type = 'button';
      element.title = title;
      element.setAttribute('aria-label', title);
      element.addEventListener('click', (event) => { event.stopPropagation(); action(); });
      return element;
    };
    // ``size``: the size of the map the view was drawn at (see draw).
    let view = null, size = null, frame = 0, hits = [], measure = null, drag = null, hovered = null;
    const zoomBy = (factor, dx = 0, dy = 0) => {
      if (!view) return;
      const resolution = clamp(view.resolution * factor, MIN_RESOLUTION, MAX_RESOLUTION);
      view = {x: view.x + dx * (view.resolution - resolution), y: view.y + dy * (view.resolution - resolution), resolution};
      redraw();
    };
    // The area of the radius, and every NQ call of the groups and of the site of the call shown, wherever it is.
    const fit = () => {
      const data = shared.data;
      if (!data) return;
      const [cx, cy] = toWorld(data.centre[0], data.centre[1]);
      const reach = data.radius_km * 1000 / metresPerWorldPixel(data.centre[0]);
      let [west, east, north, south] = [cx - reach, cx + reach, cy - reach, cy + reach];
      for (const failure of data.failures) {
        if (failure.latitude === null || !(inGroup(failure) || failure.same_place) || !shared.showsFailure(failure)) continue;
        const [x, y] = toWorld(failure.latitude, failure.longitude);
        [west, east, north, south] = [Math.min(west, x), Math.max(east, x), Math.min(north, y), Math.max(south, y)];
      }
      const width = canvas.clientWidth || 600, height = canvas.clientHeight || 400;
      const resolution = Math.max((east - west) / Math.max(80, width), (south - north) / Math.max(80, height)) * 1.1;
      view = {x: (west + east) / 2, y: (north + south) / 2, resolution: clamp(resolution, MIN_RESOLUTION, MAX_RESOLUTION)};
      size = canvas.clientWidth && canvas.clientHeight ? {width, height} : null;
      redraw();
    };
    controls.append(button('−', 'Zoom out', () => zoomBy(2)), level, button('+', 'Zoom in', () => zoomBy(.5)),
      button('Fit', 'Show the whole area of the radius and every NQ call of the hotspot, cluster, consecutive run and site of the call', fit, 'nq-map-zoom-reset'));
    card.replaceChildren(canvas, ruler, selectionBox, samples, controls, attribution, wheelHint, tooltip);
    // The legend goes below the map (in its images too), so it hides none of it.
    (legendHost || card).replaceChildren(legend);

    const project = (latitude, longitude) => {
      const [x, y] = toWorld(latitude, longitude);
      return [canvas.clientWidth / 2 + (x - view.x) / view.resolution, canvas.clientHeight / 2 + (y - view.y) / view.resolution];
    };
    const pointerOffset = (event) => {
      const bounds = canvas.getBoundingClientRect();
      return [event.clientX - bounds.left - bounds.width / 2, event.clientY - bounds.top - bounds.height / 2];
    };
    const placeAt = (event) => {
      const [dx, dy] = pointerOffset(event);
      return toLonLat(view.x + dx * view.resolution, view.y + dy * view.resolution);
    };

    // -- drawing -------------------------------------------------------------------------------------
    const triangle = (context, x, y, size) => {
      context.beginPath();
      context.moveTo(x, y - size);
      context.lineTo(x + size * .9, y + size * .7);
      context.lineTo(x - size * .9, y + size * .7);
      context.closePath();
    };
    const diamond = (context, x, y, size) => {
      context.beginPath();
      context.moveTo(x, y - size);
      context.lineTo(x + size, y);
      context.lineTo(x, y + size);
      context.lineTo(x - size, y);
      context.closePath();
    };
    const pin = (context, x, y, size, colour) => {
      context.beginPath();
      context.moveTo(x, y);
      context.bezierCurveTo(x - size * .2, y - size * .6, x - size * .9, y - size * 1.05, x - size * .9, y - size * 1.55);
      context.arc(x, y - size * 1.55, size * .9, Math.PI, 0);
      context.bezierCurveTo(x + size * .9, y - size * 1.05, x + size * .2, y - size * .6, x, y);
      context.closePath();
      context.fillStyle = colour;
      context.strokeStyle = '#fff';
      context.lineWidth = 2;
      context.fill();
      context.stroke();
      context.beginPath();
      context.arc(x, y - size * 1.55, size * .35, 0, Math.PI * 2);
      context.fillStyle = '#fff';
      context.fill();
    };
    const label = (context, text, x, y, colour = '#2d1520', align = 'left') => {
      context.font = '700 11px "IBM Plex Sans", system-ui, sans-serif';
      context.textAlign = align;
      context.textBaseline = 'middle';
      context.lineWidth = 3;
      context.strokeStyle = 'rgba(255,255,255,.92)';
      context.strokeText(text, x, y);
      context.fillStyle = colour;
      context.fillText(text, x, y);
    };

    const draw = () => {
      frame = 0;
      const data = shared.data;
      if (!card.isConnected || !data) return;
      const width = canvas.clientWidth, height = canvas.clientHeight;
      if (!width || !height) return;
      if (!view) fit();
      // A map that changes size (the legend below it growing with the samples, a resized window) keeps its top left corner
      // where it was: what it shows does not move.
      if (size && (size.width !== width || size.height !== height)) {
        view = {...view, x: view.x + (width - size.width) / 2 * view.resolution, y: view.y + (height - size.height) / 2 * view.resolution};
      }
      size = {width, height};
      const ratio = window.devicePixelRatio || 1;
      if (canvas.width !== Math.round(width * ratio) || canvas.height !== Math.round(height * ratio)) {
        canvas.width = Math.round(width * ratio);
        canvas.height = Math.round(height * ratio);
      }
      const context = canvas.getContext('2d');
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.fillStyle = '#e8edef';
      context.fillRect(0, 0, width, height);
      // The tiles of the zoom level closest to the view, scaled to it.
      const zoom = clamp(Math.round(REFERENCE_ZOOM - Math.log2(view.resolution)), MIN_TILE_ZOOM, MAX_TILE_ZOOM);
      const factor = 2 ** (REFERENCE_ZOOM - zoom), scale = factor / view.resolution, count = 2 ** zoom;
      const left = view.x / factor - width / 2 / scale, top = view.y / factor - height / 2 / scale;
      for (let ty = Math.max(0, Math.floor(top / 256)); ty <= Math.min(count - 1, Math.floor((top + height / scale) / 256)); ty += 1) {
        for (let tx = Math.floor(left / 256); tx <= Math.floor((left + width / scale) / 256); tx += 1) {
          const wrapped = ((tx % count) + count) % count;
          const url = String(data.basemap.url_template).replace('{z}', zoom).replace('{x}', wrapped).replace('{y}', ty);
          const record = tile(url, redraw);
          if (record.status === 'ready') {
            context.drawImage(record.image, (tx * 256 - left) * scale, (ty * 256 - top) * scale, 256 * scale + .5, 256 * scale + .5);
          }
        }
      }
      level.textContent = `Zoom ${zoom}`;
      hits = [];
      const settings = shared.settings;
      const layers = settings.layers;
      const call = data.call;
      const failurePoint = data.centre;
      const metresPerPixel = metresPerWorldPixel(failurePoint[0]) * view.resolution;
      // The radius around where the call failed.
      const [cx, cy] = project(failurePoint[0], failurePoint[1]);
      context.beginPath();
      context.arc(cx, cy, data.radius_km * 1000 / metresPerPixel, 0, Math.PI * 2);
      context.setLineDash([7, 6]);
      context.strokeStyle = COLOURS.radius;
      context.globalAlpha = .55;
      context.lineWidth = 1.6;
      context.stroke();
      context.setLineDash([]);
      context.globalAlpha = 1;
      // The tests around, in the colour of their level.
      const operators = data.tests.operators;
      const testRadius = zoom >= 16 ? 5 : zoom >= 13 ? 4 : 3;
      if (layers.tests) {
        for (const row of data.tests.rows) {
          if (!shared.operatorShown(operators[row[COLUMN.operator]])) continue;
          const [x, y] = project(row[COLUMN.latitude], row[COLUMN.longitude]);
          if (x < -10 || y < -10 || x > width + 10 || y > height + 10) continue;
          context.beginPath();
          context.arc(x, y, testRadius, 0, Math.PI * 2);
          context.fillStyle = testColour(row, settings.colour, data.classes);
          context.fill();
          context.lineWidth = .8;
          context.strokeStyle = 'rgba(255,255,255,.85)';
          context.stroke();
          hits.push({x, y, r: testRadius + 2, kind: 'test', item: row, priority: 1});
        }
      }
      // The sectors of the sites (once close enough), those of the cells of the call in the colour of their role and the
      // cells with the PCI and channel of a cell of the call dashed.
      const pathCells = new Map(data.trace.filter((step) => step.site).map((step) => [`${step.site}|${step.cell}`, step.role]));
      const sectorRadius = clamp(150 / metresPerPixel, 14, 64);
      const sites = layers.sites ? data.sites : data.sites.filter((site) => layers.path && site.roles.length);
      if (zoom >= WEDGES_FROM_ZOOM) {
        for (const site of sites) {
          const [x, y] = project(site.latitude, site.longitude);
          if (x < -80 || y < -80 || x > width + 80 || y > height + 80) continue;
          for (const cell of site.cells) {
            const role = layers.path ? pathCells.get(`${site.key}|${cell.identity}`) : null;
            if (!layers.sites && !role) continue;
            const beam = clamp(Number(cell.beamwidth) || 65, 24, 140);
            const reach = role ? sectorRadius * 1.25 : sectorRadius;
            context.beginPath();
            if (cell.azimuth === null || cell.azimuth === undefined) context.arc(x, y, reach * .45, 0, Math.PI * 2);
            else {
              context.moveTo(x, y);
              context.arc(x, y, reach, (cell.azimuth - beam / 2 - 90) * Math.PI / 180, (cell.azimuth + beam / 2 - 90) * Math.PI / 180);
              context.closePath();
            }
            const colour = role ? COLOURS[role] : cell.colour || '#868e96';
            context.globalAlpha = role ? .38 : .13;
            context.fillStyle = colour;
            context.fill();
            context.globalAlpha = role ? .95 : .55;
            context.lineWidth = role ? 2.2 : 1.2;
            context.strokeStyle = cell.same_pci ? COLOURS.samePci : colour;
            if (cell.same_pci) { context.setLineDash([5, 3]); context.lineWidth = 2.4; context.globalAlpha = 1; }
            context.stroke();
            context.setLineDash([]);
            context.globalAlpha = 1;
          }
        }
      }
      // The cells the call went through: a line from where they served it to their site.
      // The cell that served the start from where the call started, the one that served the end (or the whole call) from where
      // it failed, and each handover cell between them from the point of the call's way (start to end) nearest to its site:
      // the CDR does not record where each handover took place.
      const start = call.start, end = call.end || call.start;
      if (layers.path) {
        for (const step of data.trace) {
          if (step.latitude === undefined || step.latitude === null) continue;
          const [x2, y2] = project(step.latitude, step.longitude);
          let x1, y1;
          if (step.role === 'handover' && start && call.end) {
            const [ax, ay] = project(start[0], start[1]), [bx, by] = project(call.end[0], call.end[1]);
            const length = (bx - ax) ** 2 + (by - ay) ** 2;
            const along = length ? clamp(((x2 - ax) * (bx - ax) + (y2 - ay) * (by - ay)) / length, 0, 1) : 0;
            [x1, y1] = [ax + along * (bx - ax), ay + along * (by - ay)];
          } else {
            const from = step.role === 'start' && start ? start : end || failurePoint;
            [x1, y1] = project(from[0], from[1]);
          }
          context.beginPath();
          context.moveTo(x1, y1);
          context.lineTo(x2, y2);
          context.setLineDash(step.role === 'nr_leg' ? [3, 4] : [8, 5]);
          context.lineWidth = 2.4;
          context.strokeStyle = COLOURS[step.role] || COLOURS.path;
          context.stroke();
          context.setLineDash([]);
        }
      }
      // The sites: a triangle in the colour of their vendor, the serving site ringed, the order of the cells of the call
      // beside the sites that served it.
      for (const site of sites) {
        const [x, y] = project(site.latitude, site.longitude);
        if (x < -20 || y < -20 || x > width + 20 || y > height + 20) continue;
        const onPath = layers.path && site.roles.length;
        const size = site.serving || onPath ? 8 : zoom >= 12 ? 6 : 4.5;
        if (site.serving) {
          context.beginPath();
          context.arc(x, y, size + 6, 0, Math.PI * 2);
          context.strokeStyle = COLOURS.call;
          context.lineWidth = 2.5;
          context.stroke();
        }
        triangle(context, x, y, size);
        context.fillStyle = (site.cells.find((cell) => cell.colour) || {}).colour || '#868e96';
        context.fill();
        context.lineWidth = 1.4;
        context.strokeStyle = '#fff';
        context.stroke();
        hits.push({x, y, r: size + 4, kind: 'site', item: site, priority: 3});
        if (onPath) {
          const orders = data.trace.filter((step) => step.site === site.key).map((step) => (step.role === 'nr_leg' ? 'NR' : step.order));
          const badge = [...new Set(orders)].join('·');
          const role = data.trace.find((step) => step.site === site.key).role;
          context.font = '800 10px "IBM Plex Sans", system-ui, sans-serif';
          const badgeWidth = Math.max(16, context.measureText(badge).width + 8);
          context.beginPath();
          context.roundRect?.(x + size + 2, y - size - 12, badgeWidth, 15, 7.5);
          if (!context.roundRect) context.rect(x + size + 2, y - size - 12, badgeWidth, 15);
          context.fillStyle = COLOURS[role] || COLOURS.path;
          context.fill();
          context.fillStyle = '#fff';
          context.textAlign = 'center';
          context.textBaseline = 'middle';
          context.fillText(badge, x + size + 2 + badgeWidth / 2, y - size - 4.5);
        }
        if (zoom >= LABELS_FROM_ZOOM && (zoom >= LABELS_FROM_ZOOM + 1 || onPath || site.serving)) label(context, site.site_id, x, y + size + 9, '#2d1520', 'center');
      }
      // The other Non-Qualified Calls: those of its groups (hotspot, cluster, run of consecutive failures) and of its site,
      // then the others. The calls on one point make one mark with how many they are (the most related gives its colour);
      // coloured by relation, a call of its groups at its site too is ringed in the colour of the site; coloured by call type
      // or campaign, those of its groups are ringed in red and those of its site in violet.
      if (layers.failures) {
        const stacks = new Map();
        for (const failure of data.failures) {
          if (failure.self || failure.latitude === null || !shared.showsFailure(failure)) continue;
          const [x, y] = project(failure.latitude, failure.longitude);
          if (x < -10 || y < -10 || x > width + 10 || y > height + 10) continue;
          const key = `${Math.round(x / 4)}:${Math.round(y / 4)}`;
          if (!stacks.has(key)) stacks.set(key, {x, y, items: []});
          stacks.get(key).items.push(failure);
        }
        const rank = (failure) => (inGroup(failure) ? 0 : failure.same_place ? 1 : failure.same_operator ? 2 : 3);
        for (const {x, y, items} of stacks.values()) {
          items.sort((first, second) => rank(first) - rank(second));
          const [failure] = items;
          const size = inGroup(failure) || failure.same_place ? 7 : 5.5;
          diamond(context, x, y, size);
          context.fillStyle = shared.failureColour(failure);
          context.fill();
          context.lineWidth = 1.6;
          context.strokeStyle = '#fff';
          context.stroke();
          const rings = settings.failureColour === 'relation'
            ? (inGroup(failure) && items.some((item) => item.same_place) ? [COLOURS.place] : [])
            : [...(items.some(inGroup) ? [COLOURS.group] : []), ...(items.some((item) => item.same_place) ? [COLOURS.place] : [])];
          rings.forEach((ring, index) => {
            diamond(context, x, y, size + 3 + index * 3);
            context.lineWidth = 2.2;
            context.strokeStyle = ring;
            context.stroke();
          });
          if (items.length > 1) {
            const badge = `×${items.length}`;
            context.font = '800 10px "IBM Plex Sans", system-ui, sans-serif';
            const badgeWidth = Math.max(16, context.measureText(badge).width + 8);
            context.beginPath();
            context.roundRect?.(x + size - 1, y - size - 13, badgeWidth, 14, 7);
            if (!context.roundRect) context.rect(x + size - 1, y - size - 13, badgeWidth, 14);
            context.fillStyle = '#2d1520';
            context.fill();
            context.fillStyle = '#fff';
            context.textAlign = 'center';
            context.textBaseline = 'middle';
            context.fillText(badge, x + size - 1 + badgeWidth / 2, y - size - 6);
          }
          hits.push({x, y, r: size + 3, kind: 'failure', item: failure, priority: 4, stack: items.length});
        }
      }
      // The call: from where it started to where it ended (where it failed).
      if (start) {
        const [x1, y1] = project(start[0], start[1]);
        if (call.end) {
          const [x2, y2] = project(call.end[0], call.end[1]);
          context.beginPath();
          context.moveTo(x1, y1);
          context.lineTo(x2, y2);
          context.lineWidth = 5;
          context.strokeStyle = '#fff';
          context.stroke();
          context.lineWidth = 2.6;
          context.strokeStyle = COLOURS.path;
          context.stroke();
          context.beginPath();
          context.arc(x1, y1, 6, 0, Math.PI * 2);
          context.fillStyle = COLOURS.start;
          context.fill();
          context.lineWidth = 2;
          context.strokeStyle = '#fff';
          context.stroke();
          hits.push({x: x1, y: y1, r: 9, kind: 'start', item: call, priority: 5});
        }
      }
      const [px, py] = project(failurePoint[0], failurePoint[1]);
      pin(context, px, py, 10, COLOURS.call);
      hits.push({x: px, y: py - 15, r: 13, kind: 'call', item: call, priority: 6});
      // The selected element, ringed.
      const chosen = shared.selection;
      const marked = chosen && hits.find((hit) => hit.item === chosen.item && hit.kind === chosen.kind);
      if (marked) {
        context.beginPath();
        context.arc(marked.x, marked.y, Math.max(11, marked.r + 5), 0, Math.PI * 2);
        context.lineWidth = 5;
        context.strokeStyle = 'rgba(255,255,255,.95)';
        context.stroke();
        context.lineWidth = 2.5;
        context.strokeStyle = '#1e1b4b';
        context.stroke();
      }
      drawMeasure();
    };
    const redraw = () => { if (!frame) frame = requestAnimationFrame(draw); };

    // -- the distance tool (Alt/Opt+drag), kept on the map until the next click or Escape -------------------------
    const drawMeasure = () => {
      if (!measure || !view) { ruler.replaceChildren(); return; }
      const [x1, y1] = project(measure.from[1], measure.from[0]), [x2, y2] = project(measure.to[1], measure.to[0]);
      const {metres, bearing} = geodesic(measure.from, measure.to);
      const svg = (tag) => document.createElementNS('http://www.w3.org/2000/svg', tag);
      const halo = svg('line'), line = svg('line'), first = svg('circle'), last = svg('circle'), text = svg('text');
      for (const element of [halo, line]) {
        element.setAttribute('x1', x1); element.setAttribute('y1', y1); element.setAttribute('x2', x2); element.setAttribute('y2', y2);
      }
      halo.setAttribute('class', 'nq-map-measure-halo');
      line.setAttribute('class', 'nq-map-measure-line');
      for (const [circle, x, y] of [[first, x1, y1], [last, x2, y2]]) {
        circle.setAttribute('cx', x); circle.setAttribute('cy', y); circle.setAttribute('r', 4.5); circle.setAttribute('class', 'nq-map-measure-end');
      }
      const length = Math.hypot(x2 - x1, y2 - y1) || 1, ux = (x2 - x1) / length, uy = (y2 - y1) / length;
      text.setAttribute('x', x2 + ux * 26);
      text.setAttribute('y', y2 + uy * 26);
      text.setAttribute('text-anchor', ux < -.3 ? 'end' : ux > .3 ? 'start' : 'middle');
      text.setAttribute('dominant-baseline', uy < -.3 ? 'auto' : uy > .3 ? 'hanging' : 'middle');
      text.setAttribute('class', 'nq-map-measure-label');
      text.textContent = `${metresText(metres)} · ${Math.round(bearing)}°`;
      ruler.replaceChildren(halo, line, first, last, text);
    };
    const clearMeasure = () => { if (measure) { measure = null; drawMeasure(); } };
    const onKey = (event) => { if (event.key === 'Escape') clearMeasure(); };
    document.addEventListener('keydown', onKey);

    // -- the element under the pointer: its tooltip, and the one chosen with a click ------------------------------
    const hitAt = (event) => {
      const bounds = canvas.getBoundingClientRect();
      const x = event.clientX - bounds.left, y = event.clientY - bounds.top;
      let best = null;
      for (const hit of hits) {
        const distance = Math.hypot(hit.x - x, hit.y - y);
        if (distance > hit.r + 2) continue;
        if (!best || hit.priority > best.hit.priority || (hit.priority === best.hit.priority && distance < best.distance)) best = {hit, distance};
      }
      return best?.hit || null;
    };
    const showTooltip = (hit, event) => {
      if (!hit) { tooltip.hidden = true; canvas.classList.remove('is-pointing'); return; }
      canvas.classList.add('is-pointing');
      const {title, rows} = shared.describe(hit.kind, hit.item);
      tooltip.replaceChildren(node('strong', title));
      for (const [name, value] of [...(hit.stack > 1 ? [['At this point', `${hit.stack} NQ calls`]] : []), ...rows.slice(0, 9)]) {
        if (value === '' || value === null || value === undefined) continue;
        const line = node('div');
        line.append(node('span', name), node('b', String(value)));
        tooltip.append(line);
      }
      tooltip.hidden = false;
      const bounds = card.getBoundingClientRect(), box = tooltip.getBoundingClientRect();
      let left = event.clientX - bounds.left + 14, top = event.clientY - bounds.top + 14;
      if (left + box.width > bounds.width - 6) left = event.clientX - bounds.left - box.width - 14;
      if (top + box.height > bounds.height - 6) top = event.clientY - bounds.top - box.height - 14;
      tooltip.style.left = `${Math.max(6, left)}px`;
      tooltip.style.top = `${Math.max(6, top)}px`;
    };

    // -- navigation, as the maps of Network Insights ------------------------------------------------------------
    // The wheel zooms towards the pointer in the larger map; in the call panel only with Ctrl/Cmd (or a pinch, which
    // the browsers send with Ctrl), so the wheel alone scrolls the panel.
    canvas.addEventListener('wheel', (event) => {
      if (!expanded && !(event.ctrlKey || event.metaKey)) {
        wheelHint.hidden = false;
        clearTimeout(wheelHintTimer);
        wheelHintTimer = setTimeout(() => { wheelHint.hidden = true; }, 1400);
        return;
      }
      event.preventDefault();
      tooltip.hidden = true;
      wheelHint.hidden = true;
      zoomBy(Math.exp(event.deltaY * (event.deltaMode === 1 ? .05 : .0018)), ...pointerOffset(event));
    }, {passive: false});
    // In the panel a double-click opens the larger map; in the larger map it zooms in.
    canvas.addEventListener('dblclick', (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (expanded || !onExpand) zoomBy(.5, ...pointerOffset(event));
      else onExpand();
    });
    canvas.addEventListener('pointerdown', (event) => {
      if ((event.button !== 0 && event.button !== 1) || !view) return;
      modifierKeys(event);
      const measuring = event.button === 0 && event.altKey;
      const pan = !measuring && (event.button === 1 || !(event.ctrlKey || event.metaKey));
      drag = {id: event.pointerId, pan, measuring, startX: event.clientX, startY: event.clientY, x: event.clientX, y: event.clientY};
      try { canvas.setPointerCapture?.(event.pointerId); } catch (_error) { /* A pointer that is gone already. */ }
      canvas.classList.add(measuring ? 'is-measuring' : pan ? 'is-panning' : 'is-selecting');
      tooltip.hidden = true;
      if (measuring) { measure = {from: placeAt(event), to: placeAt(event)}; drawMeasure(); }
      event.preventDefault();
    });
    canvas.addEventListener('pointermove', (event) => {
      if (!drag) {
        hovered = hitAt(event);
        showTooltip(hovered, event);
        return;
      }
      if (event.pointerId !== drag.id) return;
      if (drag.measuring) { measure.to = placeAt(event); drawMeasure(); return; }
      if (drag.pan) {
        view = {...view, x: view.x - (event.clientX - drag.x) * view.resolution, y: view.y - (event.clientY - drag.y) * view.resolution};
        drag.x = event.clientX;
        drag.y = event.clientY;
        redraw();
        return;
      }
      drag.x = event.clientX;
      drag.y = event.clientY;
      const bounds = card.getBoundingClientRect();
      Object.assign(selectionBox.style, {
        left: `${Math.min(drag.startX, drag.x) - bounds.left}px`, top: `${Math.min(drag.startY, drag.y) - bounds.top}px`,
        width: `${Math.abs(drag.x - drag.startX)}px`, height: `${Math.abs(drag.y - drag.startY)}px`,
      });
      selectionBox.hidden = false;
    });
    canvas.addEventListener('pointerleave', () => { if (!drag) { tooltip.hidden = true; canvas.classList.remove('is-pointing'); } });
    const stopDrag = (event) => {
      if (!drag || event.pointerId !== drag.id) return;
      const finished = drag;
      drag = null;
      selectionBox.hidden = true;
      try { canvas.releasePointerCapture?.(event.pointerId); } catch (_error) { /* Released already. */ }
      canvas.classList.remove('is-panning', 'is-selecting', 'is-measuring');
      const moved = Math.hypot(event.clientX - finished.startX, event.clientY - finished.startY) >= 4;
      if (finished.measuring) {
        if (!moved) clearMeasure();
        return;
      }
      if (finished.pan && !moved && event.type === 'pointerup') {
        // A click chooses the element under the pointer and clears the measured distance; a click beside every element
        // keeps the chosen one (as the first click of the double-click that opens the larger map).
        clearMeasure();
        const hit = hitAt(event);
        if (hit) shared.select({kind: hit.kind, item: hit.item});
        return;
      }
      if (finished.pan || event.type !== 'pointerup' || Math.abs(event.clientX - finished.startX) < 8 || Math.abs(event.clientY - finished.startY) < 8) return;
      // The dragged rectangle fills the map.
      const [startX, startY] = pointerOffset({clientX: finished.startX, clientY: finished.startY});
      const [endX, endY] = pointerOffset(event);
      const factor = Math.max(Math.abs(endX - startX) / canvas.clientWidth, Math.abs(endY - startY) / canvas.clientHeight);
      view = {x: view.x + (startX + endX) / 2 * view.resolution, y: view.y + (startY + endY) / 2 * view.resolution,
        resolution: clamp(view.resolution * factor, MIN_RESOLUTION, MAX_RESOLUTION)};
      redraw();
    };
    canvas.addEventListener('pointerup', stopDrag);
    canvas.addEventListener('pointercancel', stopDrag);
    const resizer = new ResizeObserver(() => redraw());
    resizer.observe(card);

    // The legend: the levels of the measure chosen and the marks of the map.
    const renderLegend = () => {
      const data = shared.data, settings = shared.settings;
      legend.replaceChildren();
      samples.hidden = !data;
      samplesToggle.classList.toggle('is-on', Boolean(settings.layers.tests));
      samplesToggle.setAttribute('aria-pressed', String(Boolean(settings.layers.tests)));
      samplesToggle.title = settings.layers.tests ? 'Hide the RSRP / SINR samples of the tests around'
        : 'Show the RSRP / SINR samples of the tests around, coloured by the measure chosen beside';
      samplesMeasure.hidden = !settings.layers.tests;
      samplesMeasure.value = settings.colour;
      if (!data) return;
      let list = null;
      const group = (title) => {
        list = node('ul');
        list.append(node('li', title, 'nq-map-legend-title'));
        legend.append(list);
      };
      const item = (mark, text, colour, extra = '') => {
        const entry = node('li');
        const swatch = node('span', undefined, `nq-map-mark is-${mark}${extra ? ` ${extra}` : ''}`);
        swatch.style.setProperty('--mark', colour);
        entry.append(swatch, node('span', text));
        list.append(entry);
      };
      // The levels of the samples stay in the legend while they are hidden (dimmed), so showing them changes neither the
      // legend nor the size of the map.
      const metric = METRICS[settings.colour];
      if (metric) {
        group(`RSRP / SINR samples · ${metric.label}${settings.layers.tests ? '' : ' (hidden)'}`);
        list.classList.toggle('is-off', !settings.layers.tests);
        if (settings.colour === 'result') {
          item('dot', 'Completed', COLOURS.completed);
          item('dot', 'Not completed', COLOURS.failed);
        } else {
          const levels = data.classes[metric.classes] || [];
          levels.forEach((levelItem, index) => {
            const upper = index ? levels[index - 1].lower : null;
            const range = levelItem.lower === null ? `< ${upper}` : upper === null ? `≥ ${levelItem.lower}` : `${levelItem.lower} to ${upper}`;
            item('dot', `${levelItem.label} (${range} ${metric.unit})`, levelItem.colour);
          });
          item('dot', 'No value', COLOURS.noValue);
        }
      }
      group('Call and NQ calls');
      item('pin', 'This call (where it failed)', COLOURS.call);
      if (data.call.end) item('dot', 'Where it started', COLOURS.start);
      if (settings.layers.failures) {
        shared.failureLegend().forEach(([text, colour, extra]) => item('diamond', text, colour, extra));
        item('count', 'NQ calls at one point (how many)', '#2d1520');
      }
      const located = data.trace.some((step) => step.site);
      if ((settings.layers.sites && data.sites.length) || (settings.layers.path && located)) {
        group('Sites and cells');
        item('triangle', 'Site (colour of its vendor)', '#868e96');
        item('ring', 'Serving site of the call', COLOURS.call);
      }
      // Only the roles the cells of the call have on the map (a call served by one cell has neither start nor handovers).
      if (settings.layers.path && located) {
        const roles = new Set(data.trace.filter((step) => step.site).map((step) => step.role));
        if (roles.has('both')) item('line', 'Cell that served the whole call', COLOURS.both);
        if (roles.has('start')) item('line', 'Cell that served the start', COLOURS.start);
        if (roles.has('handover')) item('line', 'Handover cell (between the start and the end)', COLOURS.handover);
        if (roles.has('end')) item('line', 'Cell that served the end', COLOURS.end);
        if (roles.has('nr_leg')) item('line', 'NR leg (by PCI)', COLOURS.nr_leg, 'is-dotted');
      }
      if (settings.layers.sites && data.sites.some((site) => site.cells.some((cell) => cell.same_pci))) {
        item('line', 'Same PCI and channel as a cell of the call', COLOURS.samePci, 'is-dashed');
      }
      item('line', `Radius ${distanceText(data.radius_km)}`, COLOURS.radius, 'is-dashed');
    };

    return {
      redraw, fit, renderLegend,
      view: () => view && {...view},
      setView: (value) => { view = value ? {...value} : null; size = null; redraw(); },
      centreOn: (latitude, longitude) => {
        if (!view) return;
        [view.x, view.y] = toWorld(latitude, longitude);
        view = {...view, resolution: Math.min(view.resolution, 2 ** (REFERENCE_ZOOM - 16))};
        redraw();
      },
      destroy: () => { resizer.disconnect(); document.removeEventListener('keydown', onKey); },
    };
  }

  // -- the map panel of the call in the drawer, and its larger view ----------------------------------------------
  function mount({panel, expandDialog, api, toast, openCall, useRootCause = null, canEdit = () => false, campaignLabel, cdrTime, number}) {
    const stored = readSettings();
    const settings = {
      // Each call opens with the radius of its hotspot and cluster (or 1 km); the radius chosen holds while it stays open.
      radius_km: 1, tests: stored.tests === 'campaign' ? 'campaign' : 'cdr',
      colour: METRICS[stored.colour] ? stored.colour : '', operators: ['all', 'focus'].includes(stored.operators) ? stored.operators : 'own',
      // The Non-Qualified Calls around drawn: those of every campaign until another choice.
      failures: FAILURE_SCOPES[stored.failures] ? stored.failures : 'every',
      failureColour: FAILURE_COLOURS[stored.failureColour] ? stored.failureColour : 'relation',
      // The RSRP / SINR samples start hidden, so the map shows the call, its cells and the sites first.
      layers: {tests: false, failures: true, sites: true, path: true, ...(stored.layers || {})},
    };
    const save = () => storeSettings({tests: settings.tests, colour: settings.colour,
      operators: settings.operators, failures: settings.failures, failureColour: settings.failureColour, layers: settings.layers});
    let callKey = '', loadedKey = '', controller = null, expandedView = null;
    const toolbar = node('div', undefined, 'nq-map-toolbar');
    const status = node('p', '', 'nq-map-status');
    status.setAttribute('role', 'status');
    const card = node('div');
    const waiting = node('div', undefined, 'nq-map-waiting');
    const cards = node('div', undefined, 'nq-map-cards');
    const selected = node('section', undefined, 'nq-map-info nq-map-selected');
    selected.hidden = true;
    const callCard = node('section', undefined, 'nq-map-info');
    const areaCard = node('section', undefined, 'nq-map-info nq-map-area');
    const failuresCard = node('section', undefined, 'nq-map-info nq-map-failures');
    // What the map suggests, the decisions at its place, its drive and its serving site.
    const diagnosisCard = node('section', undefined, 'nq-map-info nq-map-diagnosis');
    const decisionsCard = node('section', undefined, 'nq-map-info nq-map-decisions');
    const driveCard = node('section', undefined, 'nq-map-info nq-map-drive');
    const siteCard = node('section', undefined, 'nq-map-info nq-map-site-health');
    cards.append(callCard, failuresCard, diagnosisCard, decisionsCard, driveCard, siteCard, areaCard);
    const mapWrap = node('div', undefined, 'nq-map-wrap');
    const mapLegend = node('div', undefined, 'nq-map-legend-host');
    // The element chosen goes right below the map and its legend, so its images (download and screenshot) show it too.
    mapWrap.append(card, waiting, mapLegend, selected);
    panel.replaceChildren(toolbar, status, mapWrap, node('p', PANEL_HINT, 'form-note nq-map-hint'), cards);

    const shared = {data: null, settings, selection: null};
    // The Non-Qualified Calls around that the map and its list show: those of the CDR, the campaign (and NR Mode) or every
    // campaign chosen, of its operator or of every operator (its repetitions and its hotspot whatever the operators chosen).
    shared.showsFailure = (failure) => {
      const call = shared.data?.call;
      if (!call || failure.self) return true;
      if (settings.failures === 'cdr' && failure.dataset_id !== call.dataset_id) return false;
      if (settings.failures === 'campaign' && (failure.campaign !== call.campaign || failure.nr_mode !== call.nr_mode)) return false;
      return inGroup(failure) || failure.same_place || (shared.operatorChoice() === 'own' ? failure.same_operator : shared.operatorShown(failure.operator));
    };
    // The operators chosen: that of the call, the Focus operators of the Operator Maps (that of the call while the
    // workspace has none) or every operator.
    let focusNames = new Set();
    shared.operatorChoice = () => (settings.operators === 'focus' && !focusNames.size ? 'own' : settings.operators);
    shared.operatorShown = (name) => {
      const choice = shared.operatorChoice();
      if (choice === 'all') return true;
      const value = String(name || '').trim().toLowerCase();
      return choice === 'focus' ? focusNames.has(value) : value === String(shared.data?.call.operator || '').trim().toLowerCase();
    };
    const views = () => [panelView, expandedView].filter(Boolean);
    const redrawAll = () => views().forEach((view) => { view.renderLegend(); view.redraw(); });
    shared.setSamples = (shown) => { settings.layers.tests = shown; save(); redrawAll(); };
    shared.setColour = (colour) => { settings.colour = colour; settings.layers.tests = true; save(); redrawAll(); };
    shared.select = (choice) => {
      shared.selection = choice;
      renderSelected();
      views().forEach((view) => view.redraw());
    };

    // -- what the map says of each element ---------------------------------------------------------------------
    // The campaign by its Campaign Maps label, with the NR Mode when the label does not say it.
    const campaignText = (campaign, mode) => {
      const text = campaignLabel(campaign);
      return mode && !new RegExp(`(^|[^A-Z])${mode}([^A-Z]|$)`, 'i').test(text) ? [text, mode].filter(Boolean).join(' · ') : text;
    };
    const kindLabel = (failure) => KIND_LABELS[failure.kind] || SERVICE_LABELS[failure.service] || failure.service;
    const failureText = (item) => [item.failure_classification, item.failure_category, item.failure_subcategory].filter(Boolean).join(' · ');
    // The colour of an NQ call by the choice of Colour NQ calls by, and the lines of the legend that explain it.
    const sameCampaign = (failure, call) => failure.campaign === call.campaign && failure.nr_mode === call.nr_mode;
    shared.failureColour = (failure) => {
      const call = shared.data?.call || {};
      if (settings.failureColour === 'type') return failure.kind === call.kind ? COLOURS.sameType : COLOURS.otherType;
      if (settings.failureColour === 'campaign') return sameCampaign(failure, call) ? COLOURS.sameCampaign : COLOURS.otherCampaign;
      return inGroup(failure) ? COLOURS.group : failure.same_place ? COLOURS.place : failure.same_operator ? COLOURS.own : COLOURS.other;
    };
    shared.failureLegend = () => {
      const data = shared.data;
      const call = data.call;
      if (settings.failureColour !== 'relation') {
        // Whatever the colour, the calls of its groups and of its site keep their rings (and are larger).
        const rings = [['Ringed in red: of its hotspot, cluster or consecutive run', '#adb5bd', 'is-ringed is-ringed-group'],
          ['Ringed in violet: at its site', '#adb5bd', 'is-ringed']];
        if (settings.failureColour === 'type') {
          return [[`NQ calls of its call type (${KIND_LABELS[call.kind] || call.service_label || 'its type'})`, COLOURS.sameType],
            ['NQ calls of other call types', COLOURS.otherType], ...rings];
        }
        return [[`NQ calls of its campaign (${campaignText(call.campaign, call.nr_mode) || 'its campaign'})`, COLOURS.sameCampaign],
          ['NQ calls of other campaigns', COLOURS.otherCampaign], ...rings];
      }
      const lines = [['NQ call of its hotspot, cluster or consecutive run', COLOURS.group],
        ['Ringed: also at its site', COLOURS.group, 'is-ringed'], ['NQ call at its site (not of its groups)', COLOURS.place],
        [`Other NQ calls of ${call.operator || 'its operator'}`, COLOURS.own]];
      if (shared.operatorChoice() === 'all') lines.push(['NQ calls of other operators', COLOURS.other]);
      const own = String(call.operator || '').trim().toLowerCase();
      if (shared.operatorChoice() === 'focus' && (data.focus_labels || []).some((label) => label.trim().toLowerCase() !== own)) {
        lines.push(['NQ calls of the other Focus operators', COLOURS.other]);
      }
      return lines;
    };
    const siteName = (site) => `Site ${site.site_id} · ${site.network}${site.host_network && site.host_network !== site.network ? ` on ${site.host_network}` : ''}`;
    shared.describe = (kind, item) => {
      const data = shared.data;
      if (kind === 'call' || kind === 'start') {
        return {title: kind === 'start' ? 'Where the call started' : 'This call', rows: [
          ['Call type', KIND_LABELS[item.kind] || item.service_label], ['JOIN_ID', item.join_id], ['Operator', item.operator], ['Campaign', campaignText(item.campaign, item.nr_mode)],
          ['Result', item.result], ['Failure', failureText(item)], ['Phase', item.failure_phase],
          ['Technology', item.technology], ['Started', cdrTime(item.start_time)], ['Ended', item.end_time ? cdrTime(item.end_time) : ''],
          ['Serving site', item.serving_site ? `${item.serving_site}${item.serving_host ? ` (${item.serving_host})` : ''}` : ''],
          ['Serving distance', item.serving_distance_km !== null && item.serving_distance_km !== undefined ? distanceText(item.serving_distance_km) : ''],
        ]};
      }
      if (kind === 'failure') {
        const flags = [item.same_hotspot ? 'Same hotspot' : '', item.same_cluster ? 'Same cluster' : '', item.same_run ? 'Same consecutive run' : '',
          item.same_place ? 'Same site' : ''].filter(Boolean).join(' · ');
        return {title: `NQ call · ${item.operator}`, rows: [
          ['Call type', kindLabel(item)], ['Relation', flags], ['JOIN_ID', item.join_id], ['Campaign', campaignText(item.campaign, item.nr_mode)],
          ['Result', item.result], ['Failure', failureText(item)], ['Test', item.test_name], ['Started', cdrTime(item.start_time)],
          ['Status', item.status], ['Root cause', [item.root_category, item.root_cause].filter(Boolean).join(' · ')],
          ['Place', item.place_label], ['Distance', distanceText(item.distance_km)],
        ]};
      }
      if (kind === 'site') {
        const technologies = [...new Set(item.cells.map((cell) => `${cell.technology} ${cell.band}`.trim()))].join(', ');
        return {title: siteName(item), rows: [
          ['Role', item.roles.join(', ') || (item.serving ? 'Serving site' : '')], ['Vendor', item.vendors.join(', ')],
          ['Cells', `${item.cells.length} · ${technologies}`], ['Type', item.site_type], ['eMOCN', item.emocn],
          ['Same PCI', item.cells.filter((cell) => cell.same_pci).map((cell) => `${cell.name || cell.identity} (${cell.same_pci})`).join(', ')],
          ['Distance', distanceText(item.distance_km)], ['Rank by distance', item.rank],
        ]};
      }
      const operator = data.tests.operators[item[COLUMN.operator]] || '';
      const cdr = data.tests.cdrs?.[item[COLUMN.cdr]];
      return {title: `${SERVICE_LABELS[data.tests.kinds[item[COLUMN.kind]]] || 'Test'} test · ${operator}`, rows: [
        ['Campaign', cdr ? campaignText(cdr.campaign, cdr.nr_mode) : ''],
        ['CDR', cdr ? [SERVICE_LABELS[cdr.kind] || cdr.kind, cdr.stage ? cdr.stage[0].toUpperCase() + cdr.stage.slice(1) : ''].filter(Boolean).join(' · ') : ''],
        ['Test', data.tests.test_names[item[COLUMN.test]]], ['Started', cdrTime(item[COLUMN.start])],
        ['Result', item[COLUMN.failed] ? 'Not completed' : 'Completed'],
        ['LTE RSRP', dbText(item[COLUMN.lte_rsrp], 'dBm')], ['LTE SINR', dbText(item[COLUMN.lte_sinr], 'dB')],
        ['NR RSRP', dbText(item[COLUMN.nr_rsrp], 'dBm')], ['NR SINR', dbText(item[COLUMN.nr_sinr], 'dB')],
      ]};
    };
    const definitionList = (rows) => {
      const list = node('dl', undefined, 'nq-map-facts');
      for (const [name, value] of rows) {
        if (value === '' || value === null || value === undefined) continue;
        list.append(node('dt', name), node('dd', String(value)));
      }
      return list;
    };
    const siteCellsTable = (site) => {
      const roles = new Map(shared.data.trace.filter((step) => step.site === site.key).map((step) => [step.cell, step]));
      const table = node('table', undefined, 'nq-map-table');
      const head = node('tr');
      ['Cell', 'Tech', 'Band', 'Channel', 'PCI', 'Azimuth', 'Beam', 'State', 'Note'].forEach((name) => head.append(node('th', name)));
      table.append(node('thead'), node('tbody'));
      table.tHead.append(head);
      for (const cell of site.cells) {
        const row = node('tr');
        const step = roles.get(cell.identity);
        if (step) {
          row.classList.add('is-path');
          row.style.setProperty('--role', COLOURS[step.role] || COLOURS.path);
        }
        if (cell.same_pci) row.classList.add('is-same-pci');
        const note = [step ? step.role_label : '', cell.same_pci ? `Same PCI and channel: ${cell.same_pci}` : ''].filter(Boolean).join(' · ');
        [cell.name || cell.identity, cell.technology, cell.band, cell.channel, cell.pci, cell.azimuth ?? '—', cell.beamwidth ?? '—', cell.state, note]
          .forEach((value) => row.append(node('td', String(value ?? ''))));
        table.tBodies[0].append(row);
      }
      const wrap = node('div', undefined, 'table-wrap nq-map-table-wrap');
      wrap.append(table);
      return wrap;
    };
    // The element chosen on the map (or in the lists): its details, the cells of a site and the call of a failure.
    const selectedContent = () => {
      const choice = shared.selection;
      if (!choice || !shared.data) return null;
      const {title, rows} = shared.describe(choice.kind, choice.item);
      const content = node('div', undefined, 'nq-map-selected-content');
      const head = node('header');
      head.append(node('h4', title));
      const close = node('button', '×', 'nq-map-info-close');
      close.type = 'button';
      close.title = 'Clear the selection';
      close.setAttribute('aria-label', 'Clear the selection');
      close.addEventListener('click', () => shared.select(null));
      head.append(close);
      content.append(head, definitionList(rows));
      if (choice.kind === 'site') content.append(siteCellsTable(choice.item));
      if (choice.kind === 'failure' && !choice.item.self) {
        const open = node('button', 'Open this call', 'nq-secondary-action');
        open.type = 'button';
        open.addEventListener('click', () => { if (expandDialog.open) expandDialog.close(); openCall(choice.item.call_key); });
        content.append(open);
      }
      return content;
    };
    const renderSelected = () => {
      const content = selectedContent();
      selected.hidden = !content;
      selected.replaceChildren(...(content ? [content] : []));
      const floating = expandDialog.querySelector('.nq-map-selected-float');
      if (floating) {
        const copy = selectedContent();
        floating.hidden = !copy;
        floating.replaceChildren(...(copy ? [copy] : []));
      }
    };

    // -- the cards below the map ---------------------------------------------------------------------------------
    const cardHead = (title, note = '') => {
      const head = node('header');
      head.append(node('h4', title));
      if (note) head.append(node('p', note, 'form-note'));
      return head;
    };
    const renderCall = () => {
      const data = shared.data, call = data.call;
      callCard.replaceChildren(cardHead('This call', [call.service_label, call.operator, campaignText(call.campaign, call.nr_mode)].filter(Boolean).join(' · ')));
      callCard.append(definitionList(shared.describe('call', call).rows.filter(([name]) => name !== 'JOIN_ID')));
      // The cells it went through, in order, with their site.
      const path = node('ol', undefined, 'nq-map-path');
      for (const step of data.trace) {
        const entry = node('li', undefined, step.site ? 'is-located' : 'is-missing');
        entry.style.setProperty('--role', COLOURS[step.role] || COLOURS.path);
        const role = node('span', step.role === 'nr_leg' ? 'NR' : String(step.order), 'nq-map-path-order');
        const text = node('div');
        text.append(node('strong', step.role_label));
        const cellText = [step.technology, step.band, step.cell ? `Cell ${step.cell}` : '', step.pci ? `PCI ${step.pci}` : '',
          step.channel ? `${step.technology === 'NR' ? 'NR-ARFCN' : 'EARFCN'} ${step.channel}` : ''].filter(Boolean).join(' · ');
        text.append(node('span', cellText));
        text.append(node('small', step.site ? `Site ${step.site_id} · ${step.network}${step.host_network && step.host_network !== step.network ? ` on ${step.host_network}` : ''} · ${distanceText(step.distance_km)} from the call${step.inventory?.name ? ` · ${step.inventory.name}` : ''}`
          : 'Not in the Network Inventory of the networks that serve the operator'));
        entry.append(role, text);
        if (step.site) {
          entry.tabIndex = 0;
          entry.title = 'Show its site on the map';
          const choose = () => {
            const site = data.sites.find((item) => item.key === step.site);
            if (site) { shared.select({kind: 'site', item: site}); panelView.centreOn(site.latitude, site.longitude); }
          };
          entry.addEventListener('click', choose);
          entry.addEventListener('keydown', (event) => { if (event.key === 'Enter') choose(); });
        }
        path.append(entry);
      }
      if (data.trace.length) callCard.append(node('h5', 'Cells of the call'), path);
      // Its radio values: Min, Avg and Max of each measure together.
      const measures = call.radio.filter((item) => 'avg' in item);
      if (measures.length) {
        const table = node('table', undefined, 'nq-map-table');
        const head = node('tr');
        ['Measure', 'Min', 'Avg', 'Max'].forEach((name) => head.append(node('th', name)));
        table.append(node('thead'), node('tbody'));
        table.tHead.append(head);
        for (const item of measures) {
          const row = node('tr');
          [item.name, item.min, item.avg || item.median, item.max].forEach((value) => row.append(node('td', value || '—')));
          table.tBodies[0].append(row);
        }
        const wrap = node('div', undefined, 'table-wrap nq-map-table-wrap');
        wrap.append(table);
        callCard.append(node('h5', 'Radio of the call'), wrap);
      }
      const others = call.radio.filter((item) => !('avg' in item));
      if (others.length) {
        const more = node('details', undefined, 'nq-map-more');
        more.append(node('summary', `Cells, handovers and serving fields of the CDR (${others.length})`),
          definitionList(others.map((item) => [item.name, item.value])));
        callCard.append(more);
      }
    };
    // The tests around per operator: how many failed and their median levels, the operator of the call first.
    const renderArea = () => {
      const data = shared.data, rows = data.tests.rows;
      const scope = data.tests_scopes[data.tests_scope] || '';
      areaCard.replaceChildren(cardHead('Radio around the call', `${number(data.tests.total)} tests within ${distanceText(data.radius_km)} · ${scope}`));
      if (!rows.length) {
        areaCard.append(node('p', 'No test of the chosen CDRs has a position within the radius.', 'nq-map-empty'));
        return;
      }
      const groups = new Map();
      for (const row of rows) {
        const operator = data.tests.operators[row[COLUMN.operator]] || '—';
        if (!groups.has(operator)) groups.set(operator, []);
        groups.get(operator).push(row);
      }
      const own = String(data.call.operator || '').toLowerCase();
      const ordered = [...groups.entries()].sort((a, b) => (a[0].toLowerCase() === own ? -1 : b[0].toLowerCase() === own ? 1 : b[1].length - a[1].length));
      const table = node('table', undefined, 'nq-map-table nq-map-area-table');
      const head = node('tr');
      ['Operator', 'Tests', 'Not completed', 'LTE RSRP', 'LTE SINR', 'NR RSRP', 'NR SINR', 'RSRP < −110', 'SINR < 0'].forEach((name) => head.append(node('th', name)));
      table.append(node('thead'), node('tbody'));
      table.tHead.append(head);
      const values = (part, column) => part.map((row) => row[column]).filter((value) => value !== null && value !== undefined);
      for (const [operator, part] of ordered) {
        const failed = part.filter((row) => row[COLUMN.failed]).length;
        const lteRsrp = values(part, COLUMN.lte_rsrp), lteSinr = values(part, COLUMN.lte_sinr);
        const nrRsrp = values(part, COLUMN.nr_rsrp), nrSinr = values(part, COLUMN.nr_sinr);
        const share = (list, test) => (list.length ? `${Math.round(list.filter(test).length / list.length * 100)}%` : '—');
        const row = node('tr', undefined, operator.toLowerCase() === own ? 'is-own' : '');
        [operator, number(part.length), `${number(failed)} (${Math.round(failed / part.length * 100)}%)`,
          dbText(median(lteRsrp), 'dBm'), dbText(median(lteSinr), 'dB'), dbText(median(nrRsrp), 'dBm'), dbText(median(nrSinr), 'dB'),
          share([...lteRsrp, ...nrRsrp], (value) => value < -110), share([...lteSinr, ...nrSinr], (value) => value < 0)]
          .forEach((value) => row.append(node('td', value)));
        table.tBodies[0].append(row);
      }
      const wrap = node('div', undefined, 'table-wrap nq-map-table-wrap');
      wrap.append(table);
      areaCard.append(wrap, node('p', 'Medians of the tests around (the RSRP and SINR of each test is its average over the test); '
        + 'the last columns count LTE and NR values together.', 'form-note'));
      // The sites around.
      const located = data.sites.length;
      const samePci = data.sites.flatMap((site) => site.cells.filter((cell) => cell.same_pci).map((cell) => ({site, cell})));
      const facts = [['Sites within the radius', located ? `${number(data.sites.filter((site) => site.distance_km <= data.radius_km).length)} of ${data.families.join(', ')}` : 'None'],
        ['Nearest site', data.sites[0] ? `${siteName(data.sites[0])} · ${distanceText(data.sites[0].distance_km)}` : ''],
        ['Same PCI and channel as a cell of the call', samePci.map(({site, cell}) => `${cell.name || cell.identity} (Site ${site.site_id}, ${distanceText(site.distance_km)})`).join(', ')],
        ['Network Inventory', data.snapshots.map((item) => `${item.file_name} (${item.snapshot_date})`).filter((value, index, list) => list.indexOf(value) === index).join(', ')]];
      areaCard.append(node('h5', 'Sites around'), definitionList(facts));
    };
    // The other Non-Qualified Calls: its repetitions at the same site, its hotspot, then those around.
    const renderFailures = () => {
      const data = shared.data;
      const others = data.failures.filter((item) => !item.self);
      const shown = others.filter(shared.showsFailure);
      const scope = settings.failures === 'every' ? '' : ` · ${settings.failures === 'cdr' ? 'of this CDR' : 'of its campaign'}`;
      failuresCard.replaceChildren(cardHead('Non-Qualified Calls around',
        `${number(shown.filter((item) => item.same_hotspot).length)} in its hotspot · ${number(shown.filter((item) => item.same_cluster).length)} in its cluster · `
        + `${number(shown.filter((item) => item.same_run).length)} in its consecutive run · ${number(shown.filter((item) => item.same_place).length)} at its site · `
        + `${number(shown.filter((item) => item.distance_km !== null && item.distance_km <= data.radius_km).length)} within ${distanceText(data.radius_km)}${scope}`));
      if (!shown.length) {
        failuresCard.append(node('p', 'No other Non-Qualified Call around.', 'nq-map-empty'));
        return;
      }
      const list = node('ul', undefined, 'nq-map-failure-list');
      for (const item of shown.slice(0, 150)) {
        const entry = node('li');
        entry.style.setProperty('--mark', shared.failureColour(item));
        const mark = node('span', undefined, 'nq-map-mark is-diamond');
        const text = node('div');
        const title = node('strong', `${kindLabel(item)} · ${item.operator} · ${campaignText(item.campaign, item.nr_mode)}`);
        const tags = [item.same_hotspot ? 'Hotspot' : '', item.same_cluster ? 'Cluster' : '', item.same_run ? 'Consecutive' : '',
          item.same_place ? 'Same site' : ''].filter(Boolean);
        text.append(title);
        tags.forEach((tag) => text.append(node('span', tag, 'nq-map-tag')));
        text.append(node('small', [item.result, failureText(item), cdrTime(item.start_time), distanceText(item.distance_km), item.status].filter(Boolean).join(' · ')));
        const open = node('button', 'Open', 'nq-link-action');
        open.type = 'button';
        open.title = 'Open this call';
        open.addEventListener('click', (event) => { event.stopPropagation(); openCall(item.call_key); });
        entry.append(mark, text, open);
        if (item.latitude !== null) {
          entry.tabIndex = 0;
          const choose = () => { shared.select({kind: 'failure', item}); panelView.centreOn(item.latitude, item.longitude); };
          entry.addEventListener('click', choose);
          entry.addEventListener('keydown', (event) => { if (event.key === 'Enter') choose(); });
        }
        list.append(entry);
      }
      failuresCard.append(list);
      if (shown.length > 150) failuresCard.append(node('p', `And ${number(shown.length - 150)} more on the map.`, 'form-note'));
    };
    // Diagnosis hints: one finding per check, the worst first in its colour; a click shows the site it is about.
    const LEVELS = {bad: 'To check', warn: 'Worth a look', ok: 'Fine', info: 'Note'};
    const renderDiagnosis = () => {
      const data = shared.data;
      const counts = data.diagnosis.reduce((total, check) => ({...total, [check.level]: (total[check.level] || 0) + 1}), {});
      diagnosisCard.replaceChildren(cardHead('Diagnosis hints', `What the map suggests: ${['bad', 'warn', 'ok'].filter((level) => counts[level])
        .map((level) => `${counts[level]} ${LEVELS[level].toLowerCase()}`).join(' · ') || 'nothing to compare'}`));
      const list = node('ul', undefined, 'nq-map-checks');
      const order = {bad: 0, warn: 1, info: 2, ok: 3};
      const siteFor = (check) => {
        if (check.key === 'distance') {
          const end = [...data.trace].reverse().find((step) => step.site && ['end', 'both'].includes(step.role));
          return end && data.sites.find((site) => site.key === end.site);
        }
        if (check.key === 'pci') return data.sites.find((site) => site.cells.some((cell) => cell.same_pci));
        if (check.key === 'state') return data.sites.find((site) => site.cells.some((cell) => ['Locked', 'Halted', 'Disabled', 'In progress', 'Planned'].includes(cell.state)));
        return null;
      };
      for (const check of [...data.diagnosis].sort((a, b) => order[a.level] - order[b.level])) {
        const entry = node('li', undefined, `is-${check.level}`);
        const badge = node('span', LEVELS[check.level], 'nq-map-level');
        const text = node('div');
        text.append(node('strong', check.title), node('small', check.detail));
        entry.append(badge, text);
        const site = siteFor(check);
        if (site) {
          entry.classList.add('is-linked');
          entry.tabIndex = 0;
          entry.title = 'Show the site on the map';
          const choose = () => { shared.select({kind: 'site', item: site}); panelView.centreOn(site.latitude, site.longitude); };
          entry.addEventListener('click', choose);
          entry.addEventListener('keydown', (event) => { if (event.key === 'Enter') choose(); });
        }
        list.append(entry);
      }
      diagnosisCard.append(list);
    };
    // The root causes already decided for the NQ calls at its place and in its hotspot, with Use for this call.
    const renderDecisions = () => {
      const {decisions} = shared.data;
      decisionsCard.replaceChildren(cardHead('Decisions at its place',
        `${number(decisions.related)} NQ calls at its site or in its hotspot · ${number(decisions.undecided)} without a root cause yet`));
      if (!decisions.groups.length) {
        decisionsCard.append(node('p', decisions.related ? 'No root cause has been chosen yet for the NQ calls at its place.'
          : 'No other NQ call at its place or in its hotspot.', 'nq-map-empty'));
        return;
      }
      const list = node('ul', undefined, 'nq-map-decision-list');
      for (const group of decisions.groups.slice(0, 8)) {
        const entry = node('li');
        const text = node('div');
        text.append(node('strong', [group.root_category, group.root_cause].filter(Boolean).join(' · ')));
        const statuses = Object.entries(group.statuses).map(([name, count]) => `${count} ${name}`).join(', ');
        text.append(node('small', [`${number(group.calls)} call${group.calls === 1 ? '' : 's'}`, group.campaigns.map((campaign) => campaignLabel(campaign)).join(', '),
          statuses, group.root_domain && `Domain ${group.root_domain}`].filter(Boolean).join(' · ')));
        if (group.join_ids.length) text.append(node('small', `JOIN_ID ${group.join_ids.join(', ')}`, 'nq-map-join-ids'));
        entry.append(node('span', String(group.calls), 'nq-map-count'), text);
        if (useRootCause && canEdit()) {
          const use = node('button', 'Use', 'nq-link-action');
          use.type = 'button';
          use.title = 'Give this call the same Root Category and Root Cause';
          use.addEventListener('click', () => useRootCause(group.root_category, group.root_cause));
          entry.append(use);
        }
        list.append(entry);
      }
      decisionsCard.append(list);
    };
    // The tests of its operator in the minutes before and after it: how the radio and the results went along its drive.
    const clock = (seconds) => `${seconds < 0 ? '−' : '+'}${Math.floor(Math.abs(seconds) / 60)}:${String(Math.abs(seconds) % 60).padStart(2, '0')}`;
    const renderDrive = () => {
      const data = shared.data, {drive} = data;
      const scope = data.tests_scopes[data.tests_scope] || '';
      driveCard.replaceChildren(cardHead('Its drive', `${number(drive.total || 0)} tests of ${data.call.operator || 'its operator'} within ±${drive.minutes} min · ${scope}`));
      if (!drive.rows.length) {
        driveCard.append(node('p', 'No test of its operator in the minutes around the call (the CDR may give no time, or choose every CDR of its campaign).', 'nq-map-empty'));
        return;
      }
      const table = node('table', undefined, 'nq-map-table nq-map-drive-table');
      const head = node('tr');
      ['Time', 'From it', 'Test', 'Result', 'RSRP', 'SINR', 'Distance'].forEach((name) => head.append(node('th', name)));
      table.append(node('thead'), node('tbody'));
      table.tHead.append(head);
      for (const item of drive.rows) {
        const row = node('tr', undefined, `${item.self ? 'is-self' : ''}${item.failed ? ' is-failed' : ''}`.trim());
        const rsrp = item.lte_rsrp ?? (item.nr_rsrp !== null ? item.nr_rsrp : null);
        const sinr = item.lte_sinr ?? (item.nr_sinr !== null ? item.nr_sinr : null);
        const tech = item.lte_rsrp !== null ? '' : item.nr_rsrp !== null ? ' NR' : '';
        [item.time, item.self ? 'This call' : clock(item.offset_s), [SERVICE_LABELS[item.kind] || item.kind, item.test].filter(Boolean).join(' · '),
          item.failed ? 'Not completed' : 'Completed', rsrp === null ? '—' : `${rsrp}${tech}`, sinr === null ? '—' : `${sinr}`, distanceText(item.distance_km)]
          .forEach((value) => row.append(node('td', value)));
        row.title = 'Show it on the map';
        row.addEventListener('click', () => panelView.centreOn(item.latitude, item.longitude));
        table.tBodies[0].append(row);
      }
      const wrap = node('div', undefined, 'table-wrap nq-map-table-wrap');
      wrap.append(table);
      driveCard.append(wrap, node('p', 'RSRP in dBm and SINR in dB (LTE, else NR): the averages of each test.', 'form-note'));
    };
    // The calls its serving site served in each campaign and how many were Non-Qualified, against its operator everywhere.
    const renderSiteHealth = () => {
      const data = shared.data, health = data.site_health;
      const site = data.sites.find((item) => item.serving);
      siteCard.replaceChildren(cardHead('Serving site health', health ? `Site ${health.site_id}${health.host_network ? ` (${health.host_network})` : ''} · the calls that started on it` : ''));
      if (!health || !health.campaigns.length) {
        siteCard.append(node('p', health ? 'No call of the indexed CDRs started on its serving site.' : 'The CDR gives no serving site of the call.', 'nq-map-empty'));
        return;
      }
      const operator = data.call.operator || 'Its operator';
      const table = node('table', undefined, 'nq-map-table');
      const head = node('tr');
      ['Campaign', 'Calls', 'NQ', 'NQ rate', `${operator} overall`, 'Every operator'].forEach((name) => head.append(node('th', name)));
      table.append(node('thead'), node('tbody'));
      table.tHead.append(head);
      for (const item of health.campaigns) {
        const row = node('tr');
        const rate = node('td', item.rate === null ? '—' : `${item.rate}%`);
        if (item.rate !== null && item.operator_rate) {
          if (item.rate >= item.operator_rate * 2 && item.nq >= 2) rate.className = 'is-bad';
          else if (item.rate >= item.operator_rate * 1.5 && item.nq >= 1) rate.className = 'is-warn';
          rate.title = `${item.rate}% on this site against ${item.operator_rate}% for ${operator} on every site`;
        }
        row.append(node('td', campaignText(item.campaign, item.nr_mode)), node('td', number(item.calls)),
          node('td', number(item.nq)), rate, node('td', item.operator_rate === null ? '—' : `${item.operator_rate}%`),
          node('td', item.all_rate === null ? '—' : `${item.all_rate}% of ${number(item.all_calls)}`));
        table.tBodies[0].append(row);
      }
      const wrap = node('div', undefined, 'table-wrap nq-map-table-wrap');
      wrap.append(table);
      siteCard.append(wrap);
      if (site) {
        const bands = [...new Set(site.cells.map((cell) => `${cell.technology} ${cell.band}`.trim()))].join(', ');
        const flagged = site.cells.filter((cell) => cell.state && cell.state !== 'In service');
        siteCard.append(definitionList([['Cells', `${site.cells.length} · ${bands}`], ['Vendor', site.vendors.join(', ')],
          ['Not in service', flagged.map((cell) => `${cell.name || cell.identity} (${cell.state})`).join(', ')], ['Distance', distanceText(site.distance_km)]]));
      }
    };
    const renderCards = () => {
      if (!shared.data) return;
      renderSelected();
      renderCall();
      renderArea();
      renderFailures();
      renderDiagnosis();
      renderDecisions();
      renderDrive();
      renderSiteHealth();
    };

    // -- the controls above the map ----------------------------------------------------------------------------
    const select = (labelText, name, options, value, onChange, title) => {
      const wrapper = node('label', undefined, 'nq-map-control');
      wrapper.append(node('span', labelText));
      const element = node('select');
      element.dataset.nqMap = name;
      for (const [optionValue, optionText] of options) {
        const option = node('option', optionText);
        option.value = optionValue;
        element.append(option);
      }
      element.value = value;
      if (title) wrapper.title = title;
      element.addEventListener('change', () => onChange(element.value));
      wrapper.append(element);
      return wrapper;
    };
    const renderToolbar = () => {
      const data = shared.data;
      // This CDR names its type: a campaign has a CDR per type (Voice, Data...), and the calls of a Data CDR are not those of a
      // Voice call.
      const cdrType = SERVICE_LABELS[data?.call.service] || '';
      const scopes = (entries) => Object.entries(entries).map(([value, text]) => [value, value === 'cdr' && cdrType ? `${text} (${cdrType})` : text]);
      const radii = data?.radii_km || [0.5, 1, 2, 5, 10];
      const layers = node('div', undefined, 'nq-map-layers');
      layers.setAttribute('role', 'group');
      layers.setAttribute('aria-label', 'Layers of the map');
      for (const [key, text] of Object.entries(LAYERS)) {
        const toggle = node('label', undefined, 'nq-map-layer');
        const box = node('input');
        box.type = 'checkbox';
        box.checked = settings.layers[key] !== false;
        box.addEventListener('change', () => { settings.layers[key] = box.checked; save(); redrawAll(); renderFailures(); });
        toggle.append(box, node('span', text));
        layers.append(toggle);
      }
      toolbar.replaceChildren(
        select('Radius', 'radius', radii.map((value) => [String(value), `${distanceText(value)}${value === data?.group_radius_km ? ' (groups)' : ''}`]),
          String(settings.radius_km), (value) => {
            settings.radius_km = Number(value); load();
          }, 'The area around where the call failed: its sites, Non-Qualified Calls and tests. A call opens with the radius that holds every NQ call of its hotspot and cluster, else with 1 km'),
        select('RSRP / SINR samples from', 'tests', scopes(data?.tests_scopes || {cdr: 'This CDR', campaign: 'Every CDR of its campaign'}), settings.tests, (value) => {
          settings.tests = value; save(); load();
        }, 'The tests whose RSRP / SINR the samples and the Radio around the call show: the CDR of the call, or every CDR of its campaign and NR Mode (Voice, Speech and Data together)'),
        select('NQ calls from', 'failures', scopes(data?.failure_scopes || FAILURE_SCOPES), settings.failures, (value) => {
          settings.failures = value; save(); redrawAll(); renderFailures();
        }, 'The Non-Qualified Calls around that the map and its list show: those of the CDR of the call (of its type only: the Voice CDR of a Voice call), of every CDR of its campaign and NR Mode, or of every campaign (the Diagnosis hints and the Decisions at its place count those of every campaign)'),
        select('Colour NQ calls by', 'failure-colour', Object.entries(FAILURE_COLOURS), settings.failureColour, (value) => {
          settings.failureColour = value; save(); redrawAll(); renderFailures();
        }, 'What the colour of the Non-Qualified Calls around tells: how they relate to the call (same site, hotspot, operator), whether they are of its call type, or of its campaign (the repetitions and the calls of its hotspot are always larger)'),
        select('Operators', 'operators', [['own', `${data?.call.operator || 'Its operator'} only`],
          ...(focusNames.size ? [['focus', 'Focus operators only']] : []), ['all', 'Every operator']], shared.operatorChoice(), (value) => {
          settings.operators = value; save(); redrawAll(); renderFailures();
        }, 'The samples and Non-Qualified Calls of the operator of the call, of the Focus operators of the Operator Maps'
          + `${data?.focus_labels?.length ? ` (${data.focus_labels.join(', ')})` : ''} or of every operator (its repetitions and hotspot always show)`),
        layers);
    };

    // -- loading the map of a call -------------------------------------------------------------------------------
    let request = null;
    const setWaiting = (text) => {
      waiting.hidden = !text;
      waiting.replaceChildren(...(text ? [node('p', text)] : []));
    };
    // Load the map of the call shown (true once it is there).
    const load = async () => {
      if (!callKey) return false;
      request?.abort();
      const controllerAbort = new AbortController();
      request = controllerAbort;
      const key = callKey;
      setWaiting('Preparing the map of the call… The first map of a CDR reads its tests: it can take a few seconds.');
      status.textContent = '';
      try {
        const query = new URLSearchParams({tests: settings.tests});
        if (loadedKey === key) query.set('radius_km', String(settings.radius_km));
        const data = await api(`/api/non-qualified-calls/calls/${encodeURIComponent(key)}/map?${query}`, {signal: controllerAbort.signal});
        if (request !== controllerAbort || key !== callKey) return false;
        const sameCall = loadedKey === key;
        shared.data = data;
        focusNames = new Set((data.focus_operators || []).map((name) => String(name).trim().toLowerCase()).filter(Boolean));
        settings.radius_km = data.radius_km;
        // The samples are coloured by the RSRP of the radio of the call (NR in SA) until another measure is chosen.
        if (!METRICS[settings.colour]) settings.colour = data.call.nr_mode === 'SA' ? 'nr_rsrp' : 'lte_rsrp';
        loadedKey = key;
        if (!sameCall) shared.selection = null;
        else if (shared.selection) {
          // The element chosen stays chosen when the radius or the tests change, if it is still on the map.
          const {kind, item} = shared.selection;
          const same = kind === 'site' ? data.sites.find((site) => site.key === item.key)
            : kind === 'failure' ? data.failures.find((failure) => failure.call_key === item.call_key)
              : kind === 'call' || kind === 'start' ? data.call : null;
          shared.selection = same ? {kind, item: same} : null;
        }
        setWaiting('');
        status.textContent = data.notes.join(' ');
        status.hidden = !data.notes.length;
        renderToolbar();
        renderCards();
        panelView.setView(null);
        if (expandedView) expandedView.setView(null);
        redrawAll();
        return true;
      } catch (error) {
        if (error.name === 'AbortError') return false;
        if (request === controllerAbort) {
          setWaiting('');
          shared.data = null;
          loadedKey = '';
          card.querySelector('canvas')?.getContext('2d')?.clearRect(0, 0, 10000, 10000);
          status.hidden = false;
          status.textContent = error.message;
          [selected, callCard, areaCard, failuresCard, diagnosisCard, decisionsCard, driveCard, siteCard].forEach((item) => item.replaceChildren());
          selected.hidden = true;
          toast(error.message, 'error');
        }
        return false;
      }
    };

    // -- the larger view (a double-click on the map) ---------------------------------------------------------------
    const expandContent = expandDialog.querySelector('[data-nq-map-expand-content]');
    const openExpanded = () => {
      if (!shared.data) return;
      const call = shared.data.call;
      expandDialog.querySelector('[data-nq-map-expand-title]').textContent = ['Call Area Map', call.operator,
        campaignText(call.campaign, call.nr_mode), call.join_id].filter(Boolean).join(' · ');
      // What the map could not show (a call without position, operators without inventory), then how it navigates.
      expandDialog.querySelector('[data-nq-map-expand-meta]').textContent = [...shared.data.notes, HINT].join(' · ');
      expandedView?.destroy();
      const wrap = node('div', undefined, 'nq-map-expand-wrap');
      const large = node('div', undefined, 'nq-map-expand-card');
      const legendHost = node('div', undefined, 'nq-map-legend-host');
      const floating = node('aside', undefined, 'nq-map-info nq-map-selected nq-map-selected-float');
      floating.hidden = true;
      // The element chosen floats over the map, inside what its images show.
      wrap.append(large, legendHost, floating);
      expandContent.replaceChildren(wrap);
      if (!expandDialog.open) expandDialog.showModal();
      expandedView = createView(large, shared, {expanded: true, legendHost});
      expandedView.setView(panelView.view());
      expandedView.renderLegend();
      renderSelected();
    };
    expandDialog.querySelector('[data-nq-map-expand-close]').addEventListener('click', () => expandDialog.close());
    expandDialog.addEventListener('click', (event) => { if (event.target === expandDialog) expandDialog.close(); });
    expandDialog.addEventListener('close', () => {
      if (expandDialog.open) return;
      expandedView?.destroy();
      expandedView = null;
      expandContent.replaceChildren();
      panelView.redraw();
    });

    const panelView = createView(card, shared, {onExpand: openExpanded, legendHost: mapLegend});
    renderToolbar();
    setWaiting('');

    // The larger map opened at once (the Map buttons of Failure Details and Call Details), while its map is prepared.
    const openLarge = async (key) => {
      if (!key) return;
      callKey = key;
      if (loadedKey !== key || !shared.data) {
        expandDialog.querySelector('[data-nq-map-expand-title]').textContent = 'Call Area Map';
        expandDialog.querySelector('[data-nq-map-expand-meta]').textContent = HINT;
        const waitingLarge = node('div', undefined, 'nq-map-waiting');
        waitingLarge.append(node('p', 'Preparing the map of the call… The first map of a CDR reads its tests: it can take a few seconds.'));
        expandedView?.destroy();
        expandedView = null;
        expandContent.replaceChildren(waitingLarge);
        if (!expandDialog.open) expandDialog.showModal();
        if (!(await load()) || callKey !== key) {
          if (expandDialog.open && !expandedView) expandDialog.close();
          return;
        }
      }
      openExpanded();
    };

    controller = {
      openLarge,
      // Show the map of a call (loaded again only for another call).
      show(key) {
        if (!key) return;
        callKey = key;
        if (loadedKey === key && shared.data) { redrawAll(); return; }
        load();
      },
      hide() {
        request?.abort();
        request = null;
        callKey = '';
        setWaiting('');
        if (expandDialog.open) expandDialog.close();
      },
      title: () => {
        const call = shared.data?.call;
        return call ? ['Call Area Map', call.operator, call.join_id].filter(Boolean).join(' · ') : 'Call Area Map';
      },
      details: () => ({section: 'Call Area Map', context: {call_key: shared.data?.call.call_key || '', join_id: shared.data?.call.join_id || '',
        radius_km: String(shared.data?.radius_km ?? ''), tests: settings.tests, failures: settings.failures, failure_colour: settings.failureColour,
        colour: settings.colour}}),
    };
    return controller;
  }

  window.NqCallMap = {mount};
})();
