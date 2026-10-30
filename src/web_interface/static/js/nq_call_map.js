/* Non-Qualified Calls → the map of a call: the area where it failed with what helps its analysis and troubleshooting.
   The call (where it started and ended) and the cells it went through at their sites, the inventory sites around with their
   sectors, bands, PCI and states, the other Non-Qualified Calls around (its repetitions at the same site and its hotspot)
   and the radio levels (LTE and NR RSRP and SINR) of the tests around it, on OpenStreetMap.

   It navigates like the maps of Network Insights: dragging moves it, Ctrl/Cmd+wheel (or a pinch) zooms towards the
   pointer (in the larger map the wheel alone too; in the call panel the wheel alone scrolls the panel), Ctrl/Cmd+drag
   draws a rectangle to zoom into, Alt/Opt+drag measures a distance and its bearing (with the elevation profile of the
   ground between its ends, from the Terrain Tiles of AWS Open Data), the − / + / Fit buttons zoom, a
   double-click opens it larger (where a double-click zooms in) and the image buttons download it as a PNG image or copy
   it as a screenshot (image_buttons.js). The RSRP / SINR samples of the CDRs show only when the switch of their card on
   the map is on, and the route only when Route is on. */
(() => {
  'use strict';

  const REFERENCE_ZOOM = 21, MIN_TILE_ZOOM = 3, MAX_TILE_ZOOM = 19, WEDGES_FROM_ZOOM = 14, LABELS_FROM_ZOOM = 15;
  const MIN_RESOLUTION = 2 ** (REFERENCE_ZOOM - MAX_TILE_ZOOM) / 4, MAX_RESOLUTION = 2 ** (REFERENCE_ZOOM - MIN_TILE_ZOOM);
  const WORLD = 256 * 2 ** REFERENCE_ZOOM;
  const COLOURS = {
    // (The handovers cyan: never the orange of the hotspot nor the green of the start.)
    call: '#b0234f', path: '#3d1824', start: '#2e8b57', handover: '#0c8fb0', end: '#d7263d', both: '#d7263d', nr_leg: '#6d46a8',
    route: '#5c636a',
    // The groups of the call: its hotspot (and its zone) orange, a cluster purple (never the green of the site where the call
    // started), a time window blue.
    hotspot: '#e8590c', cluster: '#ae3ec9', run: '#1971c2',
    samePci: '#d6336c', noValue: '#adb5bd',
    completed: '#2e8b57', failed: '#d7263d', radius: '#7d1238', hotZone: '#e8590c',
  };
  // The group of the call that filters the list of calls (its filter, key and name, set by the page), if any: a cluster or
  // a time window shows alone on the map, with its shape.
  let groupFocus = null;
  const inFocus = (failure) => Boolean(groupFocus && (groupFocus.filter === 'hotspot' ? failure.cluster_key === groupFocus.key
    : groupFocus.filter === 'consecutive_issue' ? failure.consecutive_key === groupFocus.key
      : failure.repeat_key === groupFocus.key || failure.repeat_all_key === groupFocus.key));
  const focusKind = () => (groupFocus?.filter === 'clustered_issue' ? 'cluster' : groupFocus?.filter === 'consecutive_issue' ? 'run' : '');
  // The keys of the clusters and time windows the map draws a shape around (its own and those of its hotspot).
  let ringKeys = {cluster: new Set(), run: new Set()};
  const setRings = (rings) => {
    ringKeys = {cluster: new Set(), run: new Set()};
    (rings || []).forEach((ring) => { if (ring.key && ringKeys[ring.kind]) ringKeys[ring.kind].add(ring.key); });
  };
  // The groups an NQ call is of, in their order of priority: the hotspot of the call, a cluster, then a time window (of the
  // call or of its hotspot).
  const memberships = (failure) => [
    ...(failure.same_hotspot ? ['hotspot'] : []),
    ...(failure.same_cluster || failure.same_cluster_all || (Boolean(failure.repeat_key) && ringKeys.cluster.has(failure.repeat_key)) ? ['cluster'] : []),
    ...(failure.same_run || (Boolean(failure.consecutive_key) && ringKeys.run.has(failure.consecutive_key)) ? ['run'] : []),
  ];
  // Those the map shows: with a cluster or a time window filtering the list, that one alone.
  const groupsOf = (failure) => (focusKind() ? (inFocus(failure) ? [focusKind()] : []) : memberships(failure));
  // The NQ calls of the other groups, hidden while a cluster or a time window filters the list.
  const hiddenByFocus = (failure) => Boolean(focusKind()) && !inFocus(failure) && memberships(failure).length > 0;
  const GROUP_COLOURS = {hotspot: COLOURS.hotspot, cluster: COLOURS.cluster, run: COLOURS.run};
  // Whether an NQ call is of a group of the call shown.
  const inGroup = (failure) => groupsOf(failure).length > 0;
  // Whether the map draws the hotspot zone of the call: a hotspot of 2 calls or more, unless one of its groups filters the list.
  const hotspotShown = (data) => (data?.groups?.hotspot || 0) >= 2 && !focusKind();
  // The shapes the map draws: every one, or with a cluster or a time window filtering the list, its own (one around its
  // calls when the call has none of it, such as its cluster of every NR Mode).
  const visibleRings = (data) => {
    const kind = focusKind();
    if (!data || !kind) return data?.rings || [];
    const found = (data.rings || []).filter((ring) => ring.kind === kind && ring.key === groupFocus.key);
    if (found.length) return found;
    const calls = data.failures.filter((failure) => failure.latitude !== null && (failure.self || inFocus(failure)));
    if (calls.length < 2) return [];
    const centre = [calls.reduce((sum, item) => sum + item.latitude, 0) / calls.length, calls.reduce((sum, item) => sum + item.longitude, 0) / calls.length];
    const metres = Math.max(...calls.map((item) => geodesic([centre[1], centre[0]], [item.longitude, item.latitude]).metres)) * 1.04 + 40;
    const path = kind === 'run' ? [...calls].sort((a, b) => String(a.start_time).localeCompare(String(b.start_time))).map((item) => [item.latitude, item.longitude]) : undefined;
    return [{kind, key: groupFocus.key, own: true, calls: calls.length, metres, minor_metres: metres, angle: 0, centre, path,
      label: `${kind === 'run' ? 'Its time window' : 'Its cluster'}: ${calls.length} NQ calls`}];
  };
  // The test columns of the payload (see nq_call_map.nearby_tests).
  const COLUMN = {latitude: 0, longitude: 1, operator: 2, kind: 3, failed: 4, lte_rsrp: 5, lte_sinr: 6, nr_rsrp: 7, nr_sinr: 8, test: 9, start: 10, cdr: 11};
  const METRICS = {
    lte_rsrp: {label: 'LTE RSRP', unit: 'dBm', classes: 'rsrp'}, lte_sinr: {label: 'LTE SINR', unit: 'dB', classes: 'sinr'},
    nr_rsrp: {label: 'NR RSRP', unit: 'dBm', classes: 'rsrp'}, nr_sinr: {label: 'NR SINR', unit: 'dB', classes: 'sinr'},
    result: {label: 'Result (completed or failed)', unit: ''},
  };
  // The measures of the RSRP / SINR samples, each a layer of their card, in the shapes of the layers of the KMZ files
  // (l3_layers.js): RSRP a circle, SINR an inverted triangle, the result a square; NR with a black dot in the middle.
  const SAMPLE_SHAPES = {lte_rsrp: 'circle', lte_sinr: 'triangle-down', nr_rsrp: 'circle', nr_sinr: 'triangle-down', result: 'square'};
  const SAMPLE_MARKS = {circle: 'dot', 'triangle-down': 'triangle-down', square: 'square'};
  const SAMPLE_ICON_COLOURS = {lte_rsrp: '#1c5dbf', lte_sinr: '#1c5dbf', nr_rsrp: '#6b3fb5', nr_sinr: '#6b3fb5', result: '#2e8b57'};
  const drawSample = (context, key, x, y, size, colour) => {
    if (window.L3Layers?.drawMarker) {
      window.L3Layers.drawMarker(context, SAMPLE_SHAPES[key], x, y, size, colour, {nr: key.startsWith('nr_'), outline: 'rgba(255, 255, 255, .85)'});
      return;
    }
    context.beginPath();
    context.arc(x, y, size, 0, Math.PI * 2);
    context.fillStyle = colour;
    context.fill();
  };
  // What the card From CDR switches (``cdr`` the whole of it): the layers of the map from the CDRs and the Non-Qualified
  // Calls, and the measures of the samples; while it is off none of them is drawn.
  // On the map of a call, each group of the call has its switch too: the shapes of its clusters, time windows and hotspot
  // zone, and their outlines on the NQ calls (Per Group).
  const CDR_LAYER_LABELS = {failures: 'NQ calls', cluster: 'Clusters', run: 'Time windows', paths: 'Time-window paths', hotspot: 'Hotspot zone',
    sites: 'Sites', path: 'Cell path', route: 'Route'};
  const shownLayers = (settings) => (settings.layers.cdr === false
    ? {...settings.layers, ...Object.fromEntries(Object.keys(CDR_LAYER_LABELS).map((key) => [key, false]))} : settings.layers);
  const shownMeasures = (settings) => (settings.layers.cdr === false ? [] : Object.keys(METRICS).filter((key) => settings.measures.includes(key)));
  // The measures of the samples kept in the browser: those of the colour of the samples before the card From CDR (none while
  // they were hidden).
  const storedMeasures = (stored, fallback = []) => {
    const old = stored.layers && 'tests' in stored.layers;
    const measures = Array.isArray(stored.measures) ? stored.measures.filter((key) => METRICS[key]) : METRICS[stored.colour] ? [stored.colour] : fallback;
    return old && stored.layers.tests !== true ? [] : measures;
  };
  const KIND_LABELS = {voice: 'Voice', whatsapp: 'WhatsApp', data: 'Data', ping: 'Ping', speech: 'Speech'};
  const SERVICE_LABELS = {voice: 'Voice', speech: 'Speech', data: 'Data'};
  // The Non-Qualified Calls around a call: those of the campaigns chosen in the filters of the page (every campaign while
  // none is chosen), or those of the campaign of the call.
  const FAILURE_SCOPES = {selected: 'Selected campaigns', campaign: 'Call campaign'};
  // What the colour of the NQ calls tells, the same on both maps: the site of their CDR, their call type, the domain of their
  // root cause (decided, else that of the DT Analyzer RCA), their campaign or their operator. The map of a call opens by
  // site, NQ Maps by call type; on the map of a call, Per Group rings the NQ calls of its groups besides.
  const FAILURE_COLOURS = {site: 'Site', type: 'Call type', domain: 'Root cause domain', campaign: 'Campaign', operator: 'Operator'};
  const AREA_FAILURE_COLOURS = {type: 'Call type', domain: 'Root cause domain', campaign: 'Campaign', operator: 'Operator', site: 'Site'};
  const KIND_COLOURS = {voice: '#b0234f', speech: '#7048e8', whatsapp: '#2b8a3e', data: '#1c7ed6', ping: '#f08c00'};
  const DOMAIN_COLOURS = () => window.L3Layers?.DOMAIN_COLOURS || {};
  const failureDomain = (failure) => failure.root_domain || failure.dta_domain || '';
  const domainColour = (failure) => DOMAIN_COLOURS()[failureDomain(failure)] || '#adb5bd';
  // The NQ calls of a map coloured by their root cause domain: a line of the legend for each domain shown.
  const domainLegend = (failures) => [...new Set(failures.map((failure) => failureDomain(failure) || 'No root cause'))].sort()
    .map((domain) => [domain === 'No root cause' ? 'No root cause yet' : domain, DOMAIN_COLOURS()[domain] || '#adb5bd']);
  const categoryColour = (value) => window.L3Layers?.categoryColour?.(value) || '#495057';
  // The site of an NQ call, as its CDR gives it (with the network that hosts it), and its name in the legend.
  const siteOf = (failure) => (failure?.site_id ? {key: `${failure.host_network || ''}|${failure.site_id}`,
    name: `Site ${failure.site_id}${failure.host_network ? ` (${failure.host_network})` : ''}`} : null);
  // The sites the legend names (those with most NQ calls first); the others keep a colour of their own. On the map of a
  // call, those of its own site (``ownSite``) are burgundy.
  const MAX_SITE_LINES = 12;
  const OWN_SITE_COLOUR = '#800020';
  // The colour of an NQ call by ``choice`` (FAILURE_COLOURS).
  const failureColourBy = (choice, failure, ownSite = '') => {
    if (choice === 'type') return KIND_COLOURS[failure.kind] || '#495057';
    if (choice === 'campaign') return categoryColour(`campaign:${failure.campaign}|${failure.nr_mode}`);
    if (choice === 'operator') return categoryColour(`operator:${failure.operator}`);
    if (choice === 'site') {
      const site = siteOf(failure);
      return !site ? '#adb5bd' : ownSite && site.key === ownSite ? OWN_SITE_COLOUR : categoryColour(`site:${site.key}`);
    }
    return domainColour(failure);
  };
  // The lines of the legend of the NQ calls shown, coloured by ``choice``: one for each value they have (by site, with how
  // many NQ calls each, the site of the call first).
  const failureLegendBy = (choice, failures, {campaignText, ownSite = ''}) => {
    if (choice === 'domain') return domainLegend(failures);
    const lines = new Map();
    for (const failure of failures) {
      const site = choice === 'site' ? siteOf(failure) : null;
      const text = choice === 'type' ? KIND_LABELS[failure.kind] || failure.service_label || 'Other'
        : choice === 'campaign' ? campaignText(failure.campaign, failure.nr_mode) || 'No campaign'
          : choice === 'operator' ? failure.operator || 'No operator' : site ? site.name : 'No site';
      const line = lines.get(text) || {text, colour: failureColourBy(choice, failure, ownSite), count: 0, own: Boolean(site && site.key === ownSite)};
      line.count += 1;
      lines.set(text, line);
    }
    const found = [...lines.values()];
    if (choice !== 'site') return found.sort((first, second) => first.text.localeCompare(second.text)).map((line) => [line.text, line.colour]);
    // (Those whose CDR gives no site go last.)
    const sites = found.filter((line) => line.text !== 'No site')
      .sort((first, second) => second.own - first.own || second.count - first.count || first.text.localeCompare(second.text));
    const shown = sites.slice(0, MAX_SITE_LINES)
      .map((line) => [`${line.text}${line.own ? ', the site of this call' : ''} · ${line.count}`, line.colour]);
    if (sites.length > MAX_SITE_LINES) shown.push([`${sites.length - MAX_SITE_LINES} more sites, each in a colour of its own`, '#ced4da']);
    found.filter((line) => line.text === 'No site').forEach((line) => shown.push([`No site · ${line.count}`, line.colour]));
    return shown;
  };
  const SETTINGS_KEY = 'nq-call-map-settings';
  // The maps under the layers, chosen on each map (the same one on every map of the page), from tile servers that need no
  // key: OpenStreetMap in grey by default (its streets under a white veil, so that the samples, events and calls stand out),
  // Plain and Dark without symbols or labels (up to zoom 16, enlarged beyond). ``short``: its name on a narrow map (a phone).
  const BASEMAPS = {
    streets: {label: 'OpenStreetMap (original)', short: 'OpenStreetMap', url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', max: 19, attribution: '© OpenStreetMap contributors'},
    light: {label: 'OpenStreetMap in grey (light)', short: 'OSM in grey', url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', max: 19, grey: true, veil: .5,
      attribution: '© OpenStreetMap contributors'},
    plain: {label: 'Plain (no labels)', short: 'Plain', url: 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}',
      max: 16, attribution: 'Tiles © Esri — Esri, HERE, Garmin, OpenStreetMap contributors'},
    terrain: {label: 'Terrain (elevation)', short: 'Terrain', url: 'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', subdomains: 'abc', max: 17,
      attribution: '© OpenStreetMap contributors, SRTM · © OpenTopoMap (CC-BY-SA)'},
    topographic: {label: 'Topographic', url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}', max: 19,
      attribution: 'Tiles © Esri — Esri, HERE, Garmin, USGS, NGA, OpenStreetMap contributors'},
    satellite: {label: 'Satellite', url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', max: 19,
      attribution: 'Tiles © Esri — Esri, Maxar, Earthstar Geographics, GIS User Community'},
    dark: {label: 'Dark', url: 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}',
      max: 16, attribution: 'Tiles © Esri — Esri, HERE, Garmin, OpenStreetMap contributors'},
  };
  const BASEMAP_KEY = 'nq-map-basemap';
  const basemapViews = new Set();
  const basemap = {key: 'light'};
  try { if (BASEMAPS[localStorage.getItem(BASEMAP_KEY)]) basemap.key = localStorage.getItem(BASEMAP_KEY); } catch (_error) { /* Light. */ }
  const setBasemap = (key) => {
    if (!BASEMAPS[key]) return;
    basemap.key = key;
    try { localStorage.setItem(BASEMAP_KEY, key); } catch (_error) { /* A private window keeps it for the page. */ }
    basemapViews.forEach((view) => view());
  };
  const tileUrl = (zoom, x, y) => {
    const map = BASEMAPS[basemap.key];
    const subdomains = map.subdomains || '';
    return map.url.replace('{s}', subdomains ? subdomains[(x + y) % subdomains.length] : '').replace('{z}', zoom).replace('{x}', x).replace('{y}', y);
  };
  const HINT = 'Drag to move · wheel or Ctrl/Cmd+wheel to zoom · Ctrl/Cmd+drag a rectangle to zoom into it · Alt/Opt+drag to measure · double-click to zoom in';
  const PANEL_HINT = 'Drag to move · Ctrl/Cmd+wheel to zoom · Ctrl/Cmd+drag a rectangle to zoom into it · Alt/Opt+drag to measure · double-click to enlarge';

  const node = (tag, text, className) => {
    const element = document.createElement(tag);
    if (text !== undefined && text !== null) element.textContent = text;
    if (className) element.className = className;
    return element;
  };
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  // A switch as those of the layers of the Layer 3 - DT Logs (l3_layers.js).
  const switchControl = (checked, label, onChange) => {
    const wrap = node('label', undefined, 'nq-l3-switch');
    const box = node('input');
    box.type = 'checkbox';
    box.checked = checked;
    box.setAttribute('aria-label', label);
    box.addEventListener('change', () => onChange(box.checked));
    wrap.append(box, node('span', undefined, 'nq-l3-switch-track'));
    return wrap;
  };
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

  // -- the elevation of the ground: the Terrain Tiles of AWS Open Data (Terrarium PNG tiles: metres = R × 256 + G + B / 256
  // − 32768), read in the browser, for the elevation profile of the distance tool ---------------------------------------
  const TERRAIN_URL = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png';
  const TERRAIN_ATTRIBUTION = 'Elevation: Terrain Tiles (AWS Open Data · Mapzen, SRTM, Copernicus and others)';
  const PROFILE_SAMPLES = 200;
  const terrainTiles = new Map();
  const terrainTile = (zoom, x, y) => {
    const key = `${zoom}/${x}/${y}`;
    if (!terrainTiles.has(key)) {
      terrainTiles.set(key, new Promise((resolve) => {
        const image = new Image();
        image.crossOrigin = 'anonymous';
        image.addEventListener('load', () => {
          const canvas = document.createElement('canvas');
          canvas.width = canvas.height = 256;
          const context = canvas.getContext('2d', {willReadFrequently: true});
          context.drawImage(image, 0, 0);
          try { resolve(context.getImageData(0, 0, 256, 256).data); } catch (_error) { resolve(null); }
        });
        image.addEventListener('error', () => { terrainTiles.delete(key); resolve(null); });
        image.src = TERRAIN_URL.replace('{z}', zoom).replace('{x}', x).replace('{y}', y);
      }));
    }
    return terrainTiles.get(key);
  };
  // The elevation (m) of a place at a zoom of the terrain tiles, between its four nearest pixels; null where it is unknown.
  const elevationAt = async (latitude, longitude, zoom) => {
    const size = 256 * 2 ** zoom;
    const radians = clamp(latitude, -85.05, 85.05) * Math.PI / 180;
    const px = (longitude + 180) / 360 * size - .5, py = (1 - Math.asinh(Math.tan(radians)) / Math.PI) / 2 * size - .5;
    const x0 = Math.floor(px), y0 = Math.floor(py);
    const value = async (x, y) => {
      const wrapped = ((x % size) + size) % size, row = clamp(y, 0, size - 1);
      const data = await terrainTile(zoom, Math.floor(wrapped / 256), Math.floor(row / 256));
      if (!data) return null;
      const index = ((row % 256) * 256 + (wrapped % 256)) * 4;
      return data[index] * 256 + data[index + 1] + data[index + 2] / 256 - 32768;
    };
    const [a, b, c, d] = await Promise.all([value(x0, y0), value(x0 + 1, y0), value(x0, y0 + 1), value(x0 + 1, y0 + 1)]);
    if ([a, b, c, d].some((item) => item === null)) return a;
    const fx = px - x0, fy = py - y0;
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy;
  };
  // The ground between two places ([longitude, latitude]): PROFILE_SAMPLES + 1 points evenly along the straight line between
  // them, at the zoom of the terrain tiles that suits its length.
  const elevationProfile = async (from, to) => {
    const {metres} = geodesic(from, to);
    const zoom = metres > 80000 ? 10 : metres > 30000 ? 11 : metres > 10000 ? 12 : metres > 3000 ? 13 : metres > 800 ? 14 : 15;
    const points = await Promise.all(Array.from({length: PROFILE_SAMPLES + 1}, async (_item, index) => {
      const share = index / PROFILE_SAMPLES;
      const longitude = from[0] + (to[0] - from[0]) * share, latitude = from[1] + (to[1] - from[1]) * share;
      return {share, metres: metres * share, longitude, latitude, elevation: await elevationAt(latitude, longitude, zoom)};
    }));
    return {metres, zoom, points};
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
  // A way of screen points as a winding road: taken every few pixels and swung from side to side in smooth bends (more of
  // them on a longer way, never wider than about a tenth of it), its ends where the way starts and ends. Always the same
  // bends for the same way, so the map does not change when it is redrawn.
  const windingRoad = (points) => {
    const lengths = [0];
    for (let index = 1; index < points.length; index += 1) {
      lengths.push(lengths[index - 1] + Math.hypot(points[index][0] - points[index - 1][0], points[index][1] - points[index - 1][1]));
    }
    const total = lengths.at(-1);
    if (total < 16) return points;
    const count = Math.ceil(total / 3), samples = [];
    let segment = 1;
    for (let step = 0; step <= count; step += 1) {
      const at = total * step / count;
      while (segment < points.length - 1 && lengths[segment] < at) segment += 1;
      const share = (at - lengths[segment - 1]) / ((lengths[segment] - lengths[segment - 1]) || 1);
      samples.push([points[segment - 1][0] + (points[segment][0] - points[segment - 1][0]) * share,
        points[segment - 1][1] + (points[segment][1] - points[segment - 1][1]) * share]);
    }
    const waves = clamp(total / 120, .75, 3.5), swing = Math.min(22, total * .1);
    return samples.map(([x, y], step) => {
      const [ax, ay] = samples[Math.max(0, step - 3)], [bx, by] = samples[Math.min(samples.length - 1, step + 3)];
      const length = Math.hypot(bx - ax, by - ay) || 1;
      const share = step / (samples.length - 1);
      const offset = swing * Math.sin(Math.PI * share) ** .6
        * (Math.sin(2 * Math.PI * waves * share) + .35 * Math.sin(2 * Math.PI * waves * 1.7 * share + 1.3)) / 1.35;
      return [x - (by - ay) / length * offset, y + (bx - ax) / length * offset];
    });
  };

  // The way of the car around the call: ``anchor`` is the call in the route of its car, ``next`` the test of its car after
  // where its way ended (past the tests its simulated way goes by).
  const carStretches = (data) => {
    const route = data.drive?.route || [], call = data.call;
    const anchor = route.findIndex((point) => point[2] === 0);
    const passed = call.way && call.way.by !== 'before' ? Math.max(0, call.way.points.length - 2) : 0;
    return {route, anchor, next: anchor >= 0 ? anchor + 1 + passed : -1};
  };
  // A winding road (see windingRoad) in the colour of the call (grey for the way of its car): a white edge, a dashed white
  // centre line and an arrow at its end, or at a share of its length (none when ``arrow`` is null), towards where it went.
  // ``scale`` narrows it (the many routes of NQ Maps far out).
  const paintRoad = (context, road, {colour = COLOURS.path, alpha = 1, arrow = 'end', scale = 1} = {}) => {
    const trace = () => {
      context.beginPath();
      context.moveTo(road[0][0], road[0][1]);
      for (let index = 1; index < road.length - 1; index += 1) {
        context.quadraticCurveTo(road[index][0], road[index][1], (road[index][0] + road[index + 1][0]) / 2, (road[index][1] + road[index + 1][1]) / 2);
      }
      context.lineTo(road.at(-1)[0], road.at(-1)[1]);
    };
    context.save();
    context.globalAlpha = alpha;
    context.lineCap = 'round';
    context.lineJoin = 'round';
    [[9, '#fff', []], [6.5, colour, []], [1.3, '#fff', [5, 6]]].forEach(([width, stroke, dash]) => {
      trace();
      context.setLineDash(dash.map((value) => value * scale));
      context.lineWidth = width * scale;
      context.strokeStyle = stroke;
      context.stroke();
    });
    context.setLineDash([]);
    if (arrow === null) {
      context.restore();
      return;
    }
    const tip = arrow === 'end' ? road.length - 1 : Math.min(road.length - 1, Math.max(3, Math.round(arrow * (road.length - 1))));
    const [ex, ey] = road[tip], [bx, by] = road[Math.max(0, tip - 3)];
    const length = Math.hypot(ex - bx, ey - by) || 1;
    const [ux, uy] = [(ex - bx) / length, (ey - by) / length];
    const reach = (arrow === 'end' ? 9 : 6) * scale, back = 14 * scale - reach, side = 8 * scale;
    context.beginPath();
    context.moveTo(ex + ux * reach, ey + uy * reach);
    context.lineTo(ex - ux * back - uy * side, ey - uy * back + ux * side);
    context.lineTo(ex - ux * back + uy * side, ey - uy * back - ux * side);
    context.closePath();
    context.fillStyle = colour;
    context.fill();
    context.lineWidth = 1.5;
    context.strokeStyle = '#fff';
    context.stroke();
    context.restore();
  };

  // One map view of a call (the one in the panel, or the larger one): its canvas, controls, legend and tooltip.
  function createView(card, shared, {expanded = false, onExpand = null, legendHost = null, onViewChange = null} = {}) {
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
    // The elevation profile of the distance measured, at the bottom of the map (in its images too), as Google Earth shows it.
    const profileBox = node('section', undefined, 'nq-map-profile');
    profileBox.hidden = true;
    ['wheel', 'pointerdown', 'dblclick'].forEach((type) => profileBox.addEventListener(type, (event) => event.stopPropagation(), {passive: true}));
    const legend = node('div', undefined, 'nq-map-legend');
    const attribution = node('div', BASEMAPS[basemap.key].attribution, 'nq-map-attribution');
    // The map under the layers (BASEMAPS), the same on every map of the page.
    const basemapChoice = node('label', undefined, 'nq-map-basemap');
    basemapChoice.title = 'The map under the layers: Light and Plain show little of their own so that the samples and events stand out';
    const basemapSelect = node('select');
    basemapSelect.setAttribute('aria-label', 'Map type');
    for (const [key, map] of Object.entries(BASEMAPS)) {
      const option = node('option', map.label);
      option.value = key;
      basemapSelect.append(option);
    }
    basemapSelect.value = basemap.key;
    basemapSelect.addEventListener('change', () => setBasemap(basemapSelect.value));
    // On a narrow map (a phone) the map types take their short names, so that the choice fits beside the zoom buttons.
    let shortNames = false;
    const nameBasemaps = () => {
      const short = card.clientWidth > 0 && card.clientWidth <= 600;
      if (short === shortNames) return;
      shortNames = short;
      for (const option of basemapSelect.options) option.textContent = (short && BASEMAPS[option.value].short) || BASEMAPS[option.value].label;
    };
    basemapChoice.append(node('span', 'Map'), basemapSelect);
    ['wheel', 'pointerdown', 'dblclick'].forEach((type) => basemapChoice.addEventListener(type, (event) => event.stopPropagation(), {passive: true}));
    const basemapChanged = () => {
      basemapSelect.value = basemap.key;
      attribution.textContent = BASEMAPS[basemap.key].attribution;
      redraw();
    };
    basemapViews.add(basemapChanged);
    // The cards over the top left of the map: the RSRP / SINR samples of the CDRs (shown or hidden with its switch, the
    // measure that colours them and, on the map of a call, the CDRs they come from), above the layers of the Layer 3 - DT
    // Logs (l3_layers.js).
    const panels = node('div', undefined, 'nq-map-panels');
    const samples = node('section', undefined, 'nq-l3-panel nq-map-samples-panel');
    samples.hidden = true;
    ['wheel', 'pointerdown', 'dblclick'].forEach((type) => samples.addEventListener(type, (event) => event.stopPropagation(), {passive: true}));
    panels.append(samples);
    // From CDR: what the map shows from the CDRs and their Non-Qualified Calls, as the card From Logs shows what comes
    // from the logs (l3_layers.js): the measures of the RSRP / SINR samples, each a layer with its switch, its marker and how
    // many samples have it (several at once: side by side at each test), with the CDRs they come from on the map of a call;
    // then the NQ calls, the sites, the cell path and time-window paths of a call and the route (``shared.cdrLayers``). Its
    // switch shows or hides all of it. It opens folded on every map (collapseCards folds it again for another call).
    let samplesOpen = false;
    const renderSamples = () => {
      const data = shared.data, settings = shared.settings;
      samples.hidden = !data;
      if (!data) return;
      const on = settings.layers.cdr !== false;
      samples.classList.toggle('is-collapsed', !samplesOpen);
      const head = node('header', undefined, 'nq-l3-head');
      const title = node('button', undefined, 'nq-l3-title');
      title.type = 'button';
      title.setAttribute('aria-expanded', String(samplesOpen));
      title.title = samplesOpen ? 'Fold the layers from the CDR' : 'Show the layers from the CDR';
      title.append(node('span', 'From CDR', 'nq-l3-title-text'), node('span', samplesOpen ? '▾' : '▸', 'nq-l3-chevron'));
      // A click anywhere on its header but its switch folds or unfolds it (its title is the button for the keyboard).
      head.addEventListener('click', (event) => {
        event.stopPropagation();
        if (event.target.closest('.nq-l3-switch')) return;
        samplesOpen = !samplesOpen;
        renderSamples();
      });
      head.append(title, switchControl(on, 'Show what comes from the CDR', (checked) => shared.setLayer('cdr', checked)));
      // (Drawn again after each switch: its body keeps where it was scrolled.)
      const scrolled = samples.querySelector('.nq-l3-body')?.scrollTop || 0;
      samples.replaceChildren(head);
      if (!samplesOpen) return;
      const body = node('div', undefined, `nq-l3-body${on ? '' : ' is-off'}`);
      const row = (checked, label, icon, text, count, onChange) => {
        const layer = node('div', undefined, 'nq-l3-layer');
        const line = node('div', undefined, 'nq-l3-line');
        line.append(switchControl(checked, label, onChange));
        if (icon && window.L3Layers?.markerIcon) line.append(window.L3Layers.markerIcon(...icon));
        line.append(node('span', text, 'nq-l3-name'));
        if (count !== null) line.append(node('span', count.toLocaleString('en-GB'), 'nq-l3-count'));
        layer.append(line);
        body.append(layer);
      };
      body.append(node('p', 'RSRP / SINR (from CDR samples)', 'nq-l3-block'));
      if (shared.samplesScope) {
        const scopes = node('div', undefined, 'nq-l3-ues');
        scopes.setAttribute('role', 'radiogroup');
        scopes.setAttribute('aria-label', 'CDRs of the samples');
        scopes.title = shared.samplesScope.title;
        for (const [value, text] of shared.samplesScope.options()) {
          const chosen = value === shared.samplesScope.value();
          const button = node('button', text, `nq-l3-ue${chosen ? ' is-on' : ''}`);
          button.type = 'button';
          button.setAttribute('role', 'radio');
          button.setAttribute('aria-checked', String(chosen));
          button.addEventListener('click', (event) => { event.stopPropagation(); if (!chosen) shared.samplesScope.set(value); });
          scopes.append(button);
        }
        body.append(scopes);
      }
      const rows = data.tests?.rows || [];
      for (const [key, metric] of Object.entries(METRICS)) {
        const count = key === 'result' ? rows.length : rows.filter((item) => item[COLUMN[key]] !== null && item[COLUMN[key]] !== undefined).length;
        row(settings.measures.includes(key), `Show the ${metric.label} of the samples`, [SAMPLE_SHAPES[key], SAMPLE_ICON_COLOURS[key], {nr: key.startsWith('nr_')}],
          metric.label, count, (checked) => shared.setMeasure(key, checked));
      }
      const note = shared.samplesNote?.();
      if (note) body.append(node('p', note, 'nq-l3-area-note'));
      body.append(node('p', 'Calls, sites and routes', 'nq-l3-block'));
      const icons = {failures: ['diamond', COLOURS.call], sites: ['triangle', '#868e96'], path: ['arrow', COLOURS.handover], paths: ['road', COLOURS.run],
        route: ['road', data.area ? COLOURS.route : COLOURS.path], cluster: ['ring', COLOURS.cluster], run: ['ring', COLOURS.run], hotspot: ['ring', COLOURS.hotZone]};
      const rings = visibleRings(data);
      const paths = rings.some((ring) => ring.path && ring.path.length > 1);
      for (const key of shared.cdrLayers || []) {
        // A group only when the call has one of it.
        if ((key === 'paths' && !paths) || ((key === 'cluster' || key === 'run') && !rings.some((ring) => ring.kind === key))
          || (key === 'hotspot' && !hotspotShown(data))) continue;
        const count = key === 'failures' ? data.failures.filter((failure) => !failure.self && failure.latitude !== null && shared.showsFailure(failure)).length
          : key === 'sites' ? data.sites.length : key === 'cluster' || key === 'run' ? rings.filter((ring) => ring.kind === key).length : null;
        const text = key === 'route' ? (data.area ? 'Route (the drive of each CDR between its tests)' : 'Route (its way and that of its car)') : CDR_LAYER_LABELS[key];
        row(settings.layers[key] !== false, `Show the ${CDR_LAYER_LABELS[key]}`, icons[key], text, count, (checked) => shared.setLayer(key, checked));
      }
      samples.append(body);
      body.scrollTop = scrolled;
    };
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
    // The area of the radius and of the rings of its groups, and every NQ call of the groups and of the site of the call
    // shown, wherever it is.
    const fit = () => {
      const data = shared.data;
      if (!data) return;
      const [cx, cy] = toWorld(data.centre[0], data.centre[1]);
      const reach = data.radius_km * 1000 / metresPerWorldPixel(data.centre[0]);
      let [west, east, north, south] = [cx - reach, cx + reach, cy - reach, cy + reach];
      for (const ring of visibleRings(data)) {
        const [x, y] = toWorld(ring.centre[0], ring.centre[1]);
        const r = ring.metres / metresPerWorldPixel(ring.centre[0]);
        [west, east, north, south] = [Math.min(west, x - r), Math.max(east, x + r), Math.min(north, y - r), Math.max(south, y + r)];
      }
      for (const failure of data.failures) {
        if (failure.latitude === null || !(inGroup(failure) || failure.same_place) || !shared.showsFailure(failure)) continue;
        const [x, y] = toWorld(failure.latitude, failure.longitude);
        [west, east, north, south] = [Math.min(west, x), Math.max(east, x), Math.min(north, y), Math.max(south, y)];
      }
      // The whole way of the UE of its Layer 3 - DT Logs.
      const l3Bounds = window.L3Layers?.bounds(shared.l3);
      if (l3Bounds) {
        const [x1, y1] = toWorld(l3Bounds.north, l3Bounds.west), [x2, y2] = toWorld(l3Bounds.south, l3Bounds.east);
        [west, east, north, south] = [Math.min(west, x1), Math.max(east, x2), Math.min(north, y1), Math.max(south, y2)];
      }
      const width = canvas.clientWidth || 600, height = canvas.clientHeight || 400;
      const resolution = Math.max((east - west) / Math.max(80, width), (south - north) / Math.max(80, height)) * 1.1;
      view = {x: (west + east) / 2, y: (north + south) / 2, resolution: clamp(resolution, MIN_RESOLUTION, MAX_RESOLUTION)};
      size = canvas.clientWidth && canvas.clientHeight ? {width, height} : null;
      redraw();
    };
    const FIT_TITLE = 'Show the whole area of the radius and every NQ call of the hotspot, cluster, time window and site of the call';
    const fitButton = button('Fit', FIT_TITLE, fit, 'nq-map-zoom-reset');
    controls.append(button('−', 'Zoom out', () => zoomBy(2)), level, button('+', 'Zoom in', () => zoomBy(.5)), fitButton);
    // The panels over the bottom of the map: the elevation profile, and over the larger map the signalling timeline.
    const bottomStack = node('div', undefined, 'nq-map-bottom');
    bottomStack.append(profileBox);
    card.replaceChildren(canvas, ruler, selectionBox, panels, controls, basemapChoice, bottomStack, attribution, wheelHint, tooltip);
    // The legend goes below the map (in its images too), so it hides none of it.
    (legendHost || card).replaceChildren(legend);
    // The layers of the Layer 3 - DT Logs of the call (l3_layers.js), over the map so that its images show them.
    const l3Tree = window.L3Layers ? window.L3Layers.createTree(panels, () => shared.l3, () => { renderLegend(); redraw(); }) : null;

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
      nameBasemaps();
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
      // The tiles of the zoom level closest to the view (at most the last one of the map chosen), scaled to it.
      const zoom = clamp(Math.round(REFERENCE_ZOOM - Math.log2(view.resolution)), MIN_TILE_ZOOM, MAX_TILE_ZOOM);
      const tileZoom = Math.min(zoom, BASEMAPS[basemap.key].max || MAX_TILE_ZOOM);
      const factor = 2 ** (REFERENCE_ZOOM - tileZoom), scale = factor / view.resolution, count = 2 ** tileZoom;
      const left = view.x / factor - width / 2 / scale, top = view.y / factor - height / 2 / scale;
      const map = BASEMAPS[basemap.key];
      if (map.grey) context.filter = 'grayscale(1)';
      for (let ty = Math.max(0, Math.floor(top / 256)); ty <= Math.min(count - 1, Math.floor((top + height / scale) / 256)); ty += 1) {
        for (let tx = Math.floor(left / 256); tx <= Math.floor((left + width / scale) / 256); tx += 1) {
          const wrapped = ((tx % count) + count) % count;
          const url = tileUrl(tileZoom, wrapped, ty);
          const record = tile(url, redraw);
          if (record.status === 'ready') {
            context.drawImage(record.image, (tx * 256 - left) * scale, (ty * 256 - top) * scale, 256 * scale + .5, 256 * scale + .5);
          }
        }
      }
      context.filter = 'none';
      if (map.veil) {
        context.fillStyle = `rgba(255, 255, 255, ${map.veil})`;
        context.fillRect(0, 0, width, height);
      }
      level.textContent = `Zoom ${zoom}`;
      hits = [];
      const settings = shared.settings;
      const layers = shownLayers(settings);
      // The route from the CDR: the way of the call and of its car (on NQ Maps the drive of each CDR), with its START and END.
      const routeShown = layers.route !== false;
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
      // The shape of a group: a few pixels wider, so that the marks of the calls on its edge show inside it at any zoom (the
      // map turns the y axis of the plane of the shape downwards).
      const shape = (target, ring) => {
        const [rx, ry] = project(ring.centre[0], ring.centre[1]);
        target.beginPath();
        target.ellipse(rx, ry, ring.metres / metresPerPixel + 9, (ring.minor_metres || ring.metres) / metresPerPixel + 9,
          -(ring.angle || 0), 0, Math.PI * 2);
      };
      // The hotspot zone: where its clusters OR its time windows are (their envelope), or with the AND join where they meet
      // (their intersection), in an orange of its own: tinted over the shapes of its groups and outlined outside them.
      let hotZone = null;
      // (The zone takes every shape of its groups, those switched off too.)
      const visible = visibleRings(data);
      if (hotspotShown(data) && layers.hotspot !== false) {
        const spatial = visible.filter((ring) => ring.kind !== 'run');
        const timed = visible.filter((ring) => ring.kind === 'run');
        const meet = data.hotspot_join === 'and' && spatial.length && timed.length;
        const layer = (rings) => {
          const found = document.createElement('canvas');
          [found.width, found.height] = [canvas.width, canvas.height];
          const target = found.getContext('2d');
          target.setTransform(ratio, 0, 0, ratio, 0, 0);
          target.fillStyle = '#000';
          rings.forEach((ring) => { shape(target, ring); target.fill(); });
          return found;
        };
        const zone = layer(meet ? spatial : [...spatial, ...timed]);
        const area = zone.getContext('2d');
        area.setTransform(1, 0, 0, 1, 0, 0);
        if (meet) {
          area.globalCompositeOperation = 'destination-in';
          area.drawImage(layer(timed), 0, 0);
        }
        // Its edge, a few pixels outside it, clear of the lines of the shapes: the zone moved every way that far, less the
        // zone moved a little less.
        const grown = (pixels) => {
          const found = document.createElement('canvas');
          [found.width, found.height] = [canvas.width, canvas.height];
          const target = found.getContext('2d');
          for (let step = 0; step < 16; step += 1) {
            const angle = step * Math.PI / 8;
            target.drawImage(zone, Math.cos(angle) * pixels, Math.sin(angle) * pixels);
          }
          target.drawImage(zone, 0, 0);
          return found;
        };
        const edge = grown(Math.round(7 * ratio));
        const line = edge.getContext('2d');
        line.globalCompositeOperation = 'destination-out';
        line.drawImage(grown(Math.round(3 * ratio)), 0, 0);
        for (const target of [area, line]) {
          target.globalCompositeOperation = 'source-in';
          target.fillStyle = COLOURS.hotZone;
          target.fillRect(0, 0, canvas.width, canvas.height);
        }
        const paint = (layerCanvas, alpha) => {
          context.save();
          context.setTransform(1, 0, 0, 1, 0, 0);
          context.globalAlpha = alpha;
          context.drawImage(layerCanvas, 0, 0);
          context.restore();
        };
        hotZone = {fill: () => paint(zone, .22), edge: () => paint(edge, .95)};
      }
      // The shapes of its groups, as the Groups slide draws them: a circle around each cluster in purple and an ellipse along
      // each time window in blue of its hotspot (what they make together), those of the call itself bolder, the larger
      // below; the hotspot when one of its calls is in neither. Their tint first, then the hotspot zone, then their lines and
      // the edge of the zone.
      const shapes = visible.filter((ring) => layers[ring.kind] !== false).sort((a, b) => b.metres - a.metres);
      for (const ring of shapes) {
        shape(context, ring);
        context.fillStyle = GROUP_COLOURS[ring.kind];
        context.globalAlpha = .08;
        context.fill();
        context.globalAlpha = 1;
      }
      hotZone?.fill();
      for (const ring of shapes) {
        shape(context, ring);
        context.strokeStyle = GROUP_COLOURS[ring.kind];
        context.globalAlpha = ring.own ? 1 : .85;
        context.lineWidth = ring.own ? 3 : 2;
        context.stroke();
        context.globalAlpha = 1;
      }
      hotZone?.edge();
      // Each time window as its failures follow one another (each within the Time window of the one before).
      // Their order is numbered beside each failure, above the NQ calls (see below).
      const pathNumbers = [];
      for (const ring of layers.paths === false ? [] : visible.filter((item) => item.path && item.path.length > 1)) {
        context.beginPath();
        ring.path.forEach(([latitude, longitude], index) => {
          const [px, py] = project(latitude, longitude);
          if (index) context.lineTo(px, py); else context.moveTo(px, py);
          pathNumbers.push([px, py, index + 1]);
        });
        context.lineJoin = 'round';
        context.lineWidth = ring.own ? 5 : 4;
        context.strokeStyle = '#fff';
        context.stroke();
        context.lineWidth = ring.own ? 2.6 : 2;
        context.strokeStyle = COLOURS.run;
        context.setLineDash([8, 5]);
        context.stroke();
        context.setLineDash([]);
      }
      // The tests around, in the colour of their level.
      const operators = data.tests.operators;
      const testRadius = zoom >= 16 ? 5 : zoom >= 13 ? 4 : 3;
      // NQ Maps, as roads (narrower far out): first, below everything, the drive of each CDR (from the CDR, when its route is
      // on) as the map of a call sketches the way of its car: winding grey roads, thin and faint, only between tests close in
      // time and place (2 minutes and 2 km at most, at a speed a car can drive: not those of another car measuring nearby).
      const roadScale = zoom >= 15 ? 1 : zoom >= 13 ? .8 : zoom >= 11 ? .6 : .45;
      const paintPieces = (pieces, colour, kind, item, priority, {scale = roadScale, alpha = .9} = {}) => {
        for (const piece of pieces.filter((points) => points.length > 1)) {
          const xs = piece.map(([x]) => x), ys = piece.map(([, y]) => y);
          if (Math.max(...xs) < -10 || Math.max(...ys) < -10 || Math.min(...xs) > width + 10 || Math.min(...ys) > height + 10) continue;
          const reach = Math.hypot(piece.at(-1)[0] - piece[0][0], piece.at(-1)[1] - piece[0][1]);
          paintRoad(context, piece, {colour, alpha, arrow: reach >= 40 ? 'end' : null, scale});
          const [mx, my] = piece[Math.floor(piece.length / 2)];
          hits.push({x: mx, y: my, r: 8, kind, item: typeof item === 'function' ? item(piece) : item, priority});
        }
      };
      if (data.area && routeShown && data.tests.rows.length) {
        const drives = new Map();
        for (const row of data.tests.rows) {
          if (!shared.operatorShown(operators[row[COLUMN.operator]])) continue;
          const key = row[COLUMN.cdr];
          if (!drives.has(key)) drives.set(key, []);
          drives.get(key).push(row);
        }
        for (const [cdr, rows] of drives) {
          rows.sort((first, second) => String(first[COLUMN.start]).localeCompare(String(second[COLUMN.start])));
          const pieces = [[]];
          rows.forEach((row, index) => {
            const last = rows[index - 1];
            if (last) {
              const seconds = Math.abs(Date.parse(String(row[COLUMN.start]).replace(' ', 'T')) - Date.parse(String(last[COLUMN.start]).replace(' ', 'T'))) / 1000;
              const metres = geodesic([last[COLUMN.longitude], last[COLUMN.latitude]], [row[COLUMN.longitude], row[COLUMN.latitude]]).metres;
              if (!(seconds <= 120) || metres > 2000 || metres > Math.max(150, seconds * 40)) pieces.push([]);
            }
            pieces.at(-1).push(project(row[COLUMN.latitude], row[COLUMN.longitude]));
          });
          const sketched = pieces.filter((piece) => piece.length > 1).map((piece) => windingRoad(piece)).filter((road) => road.length > 2);
          paintPieces(sketched, COLOURS.route, 'cdr_route', {cdr: data.tests.cdrs?.[cdr], tests: rows.length, from: rows[0][COLUMN.start], to: rows.at(-1)[COLUMN.start],
            operator: operators[rows[0][COLUMN.operator]]}, 1.5, {scale: roadScale * .7, alpha: .6});
        }
      }
      // Each measure on in its shape, side by side at each test when there are several (those without a value then left out).
      const measures = shownMeasures(settings);
      if (measures.length) {
        const spread = measures.length > 1 ? testRadius * 1.8 : 0;
        for (const row of data.tests.rows) {
          if (!shared.operatorShown(operators[row[COLUMN.operator]])) continue;
          const [x, y] = project(row[COLUMN.latitude], row[COLUMN.longitude]);
          if (x < -10 || y < -10 || x > width + 10 || y > height + 10) continue;
          measures.forEach((key, index) => {
            if (measures.length > 1 && key !== 'result' && (row[COLUMN[key]] === null || row[COLUMN[key]] === undefined)) return;
            const sx = x + (index - (measures.length - 1) / 2) * spread;
            drawSample(context, key, sx, y, testRadius, testColour(row, key, data.classes));
            hits.push({x: sx, y, r: testRadius + 2, kind: 'test', item: row, priority: 1});
          });
        }
      }
      // The sectors of the sites (once close enough; those of the cells of the call always), these in the colour of their role and the
      // cells with the PCI and channel of a cell of the call dashed.
      // (A cell met more than once takes its most telling role: the end, then the start, then a handover.)
      const ROLE_RANK = {both: 4, end: 3, start: 2, nr_leg: 1, handover: 0};
      const pathCells = new Map();
      data.trace.filter((step) => step.site).forEach((step) => {
        const key = `${step.site}|${step.cell}`;
        if (!pathCells.has(key) || ROLE_RANK[step.role] > ROLE_RANK[pathCells.get(key)]) pathCells.set(key, step.role);
      });
      const sectorRadius = clamp(150 / metresPerPixel, 14, 64);
      const sites = layers.sites ? data.sites : data.sites.filter((site) => (layers.path && site.roles.length) || site.ends?.length);
      // The cells of the call show at every zoom, the others once close enough.
      const everyCell = zoom >= WEDGES_FROM_ZOOM;
      const named = [];
      {
        for (const site of sites) {
          const [x, y] = project(site.latitude, site.longitude);
          if (x < -80 || y < -80 || x > width + 80 || y > height + 80) continue;
          for (const cell of site.cells) {
            const role = layers.path ? pathCells.get(`${site.key}|${cell.identity}`) : null;
            if ((!layers.sites || !everyCell) && !role) continue;
            const beam = clamp(Number(cell.beamwidth) || 65, 24, 140);
            const reach = role ? sectorRadius * 1.25 : sectorRadius;
            const omni = cell.azimuth === null || cell.azimuth === undefined;
            const from = (cell.azimuth - beam / 2 - 90) * Math.PI / 180, to = (cell.azimuth + beam / 2 - 90) * Math.PI / 180;
            context.beginPath();
            if (omni) context.arc(x, y, reach * .45, 0, Math.PI * 2);
            else {
              context.moveTo(x, y);
              context.arc(x, y, reach, from, to);
              context.closePath();
            }
            // Hovering a sector shows its cell (the site keeps its centre; a cell of the call before those it overlaps).
            hits.push({x, y, r: omni ? reach * .45 : reach, wedge: omni ? null : [from, to], kind: 'cell', item: cell, priority: role ? 2.5 : 2});
            // The cells that served the start and the end of the call (where it failed) are named at the tip of their sector.
            if (role === 'start' || role === 'end' || role === 'both') {
              const angle = omni ? -Math.PI / 2 : cell.azimuth * Math.PI / 180 - Math.PI / 2;
              named.push([cell.name || cell.identity, x + Math.cos(angle) * (reach + 10), y + Math.sin(angle) * (reach + 10), COLOURS[role]]);
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
        for (const [text, lx, ly, colour] of named) label(context, text, lx, ly, colour, 'center');
      }
      // The cells the call went through: the cell of its start joined to where it started, the cell of its end (or of the whole
      // call) to where it failed and the NR cell of an NSA call to where it failed, each by a dashed line to the cell; each
      // handover an arrow from the cell before it to the cell after it, numbered with the order of that cell (as the Cells of
      // the call list and the badges of the sites): the CDR does not record where each handover took place.
      const start = call.start, end = call.end || call.start;
      const handoverBadges = [];
      if (layers.path) {
        // Where a cell of the call is: the middle of its sector when the map shows the sectors (Sites on, from zoom 14), else
        // the side of its site where it points (its site for an omnidirectional cell).
        const sectorsShown = layers.sites && zoom >= WEDGES_FROM_ZOOM;
        const siteOf = new Map(data.sites.map((site) => [site.key, site]));
        const cellPoint = (step) => {
          const site = siteOf.get(step.site);
          const [x, y] = site ? project(site.latitude, site.longitude) : project(step.latitude, step.longitude);
          const cell = site?.cells.find((item) => item.identity === step.cell);
          if (!cell || cell.azimuth === null || cell.azimuth === undefined) return [x, y];
          const angle = cell.azimuth * Math.PI / 180 - Math.PI / 2;
          const reach = sectorsShown ? sectorRadius * 1.25 * .6 : 9;
          return [x + Math.cos(angle) * reach, y + Math.sin(angle) * reach];
        };
        // A line with a white edge, so it shows over the shapes of the groups and the sectors.
        const edged = (x1, y1, x2, y2, colour, dash) => {
          for (const [width, style, pattern] of [[5, 'rgba(255,255,255,.9)', []], [2.6, colour, dash]]) {
            context.beginPath();
            context.moveTo(x1, y1);
            context.lineTo(x2, y2);
            context.setLineDash(pattern);
            context.lineWidth = width;
            context.strokeStyle = style;
            context.stroke();
          }
          context.setLineDash([]);
        };
        const lines = [];
        const path = data.trace.filter((step) => step.role !== 'nr_leg');
        for (const step of data.trace) {
          if (step.latitude === undefined || step.latitude === null) continue;
          const first = step === path[0], last = step === path[path.length - 1];
          if (step.role !== 'nr_leg' && !first && !last) continue;
          const [x2, y2] = cellPoint(step);
          const from = first && step.role !== 'both' && start ? start : end || failurePoint;
          const [x1, y1] = project(from[0], from[1]);
          lines.push({step, x1, y1, x2, y2});
        }
        // Lines with the same ends (the cells of the start and the end on one site, served from the same point) go side by
        // side, each in its colour, instead of one over the other.
        const together = (a, b) => Math.hypot(a.x1 - b.x1, a.y1 - b.y1) < 6 && Math.hypot(a.x2 - b.x2, a.y2 - b.y2) < 6;
        const bundles = [];
        lines.forEach((line) => { (bundles.find((bundle) => together(bundle[0], line)) || bundles[bundles.push([]) - 1]).push(line); });
        for (const bundle of bundles) {
          bundle.forEach(({step, x1, y1, x2, y2}, index) => {
            const length = Math.hypot(x2 - x1, y2 - y1) || 1;
            const shift = (index - (bundle.length - 1) / 2) * 4;
            const [dx, dy] = [-(y2 - y1) / length * shift, (x2 - x1) / length * shift];
            edged(x1 + dx, y1 + dy, x2 + dx, y2 + dy, COLOURS[step.role] || COLOURS.path, step.role === 'nr_leg' ? [3, 4] : [8, 5]);
          });
        }
        // The handovers, from cell to cell; those between the same two cells (back and forth) each in a lane of its own.
        const moves = [];
        for (let index = 1; index < path.length; index += 1) {
          const before = path[index - 1], after = path[index];
          if (!before.site || !after.site) continue;
          const [x1, y1] = cellPoint(before), [x2, y2] = cellPoint(after);
          const pair = [`${Math.round(x1)}|${Math.round(y1)}`, `${Math.round(x2)}|${Math.round(y2)}`].sort().join('>');
          moves.push({before, after, x1, y1, x2, y2, pair});
        }
        const lanes = new Map();
        moves.forEach((move) => lanes.set(move.pair, [...(lanes.get(move.pair) || []), move]));
        for (const lane of lanes.values()) {
          lane.forEach((move, index) => {
            const {x1, y1, x2, y2} = move;
            const length = Math.hypot(x2 - x1, y2 - y1);
            const shift = (index - (lane.length - 1) / 2) * 6;
            if (length < 3) {
              // (Two cells drawn at one point: only its number, beside it.)
              handoverBadges.push({move, x: x2 + 13 + index * 17, y: y2 - 13});
              return;
            }
            // The lanes keep one side whatever the direction of each arrow.
            const forward = `${Math.round(x1)}|${Math.round(y1)}` <= `${Math.round(x2)}|${Math.round(y2)}` ? 1 : -1;
            const [ux, uy] = [(x2 - x1) / length, (y2 - y1) / length];
            const [dx, dy] = [-uy * shift * forward, ux * shift * forward];
            const [ax, ay, bx, by] = [x1 + dx, y1 + dy, x2 + dx, y2 + dy];
            const head = Math.min(10, length / 3);
            edged(ax, ay, bx - ux * head * .6, by - uy * head * .6, COLOURS.handover, []);
            context.beginPath();
            context.moveTo(bx, by);
            context.lineTo(bx - ux * head - uy * head * .55, by - uy * head + ux * head * .55);
            context.lineTo(bx - ux * head + uy * head * .55, by - uy * head - ux * head * .55);
            context.closePath();
            context.fillStyle = COLOURS.handover;
            context.fill();
            context.lineWidth = 1.4;
            context.strokeStyle = '#fff';
            context.stroke();
            // (Its number along its lane, each lane at another height, so the numbers of a bundle never overlap.)
            const along = lane.length > 1 ? .22 + .56 * index / (lane.length - 1) : .45;
            handoverBadges.push({move, x: ax + (bx - ax) * along, y: ay + (by - ay) * along});
          });
        }
      }
      // The sites: a triangle in the colour of their vendor, the serving site ringed, the order of the cells of the call
      // beside the sites that served it.
      for (const site of sites) {
        const [x, y] = project(site.latitude, site.longitude);
        if (x < -20 || y < -20 || x > width + 20 || y > height + 20) continue;
        const onPath = layers.path && site.roles.length;
        const ends = site.ends || [];
        const size = site.serving || onPath || ends.length ? 8 : zoom >= 12 ? 6 : 4.5;
        // Where the call ended (red, where it failed) and where it started (green, outside when both are this site); dashed
        // when the site is only the nearest to it (its cell is not in the Network Inventory).
        for (const end of [...ends].sort((a, b) => (a.role === 'end' ? -1 : 1) - (b.role === 'end' ? -1 : 1))) {
          context.beginPath();
          context.arc(x, y, size + (end.role === 'start' && ends.length > 1 ? 10 : 6), 0, Math.PI * 2);
          context.strokeStyle = end.role === 'start' ? COLOURS.start : COLOURS.call;
          context.lineWidth = 2.5;
          context.setLineDash(end.estimated ? [4, 3] : []);
          context.stroke();
          context.setLineDash([]);
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
        if (ends.length || (zoom >= LABELS_FROM_ZOOM && (zoom >= LABELS_FROM_ZOOM + 1 || onPath || site.serving))) {
          label(context, site.site_id, x, y + size + (ends.length > 1 ? 13 : 9), '#2d1520', 'center');
        }
      }
      // The number of each handover, above the sites (hovering it tells the cells and sites it joins).
      for (const {move, x, y} of handoverBadges) {
        const text = String(move.after.order);
        context.font = '800 10px "IBM Plex Sans", system-ui, sans-serif';
        const radius = Math.max(8, context.measureText(text).width / 2 + 4);
        context.beginPath();
        context.arc(x, y, radius, 0, Math.PI * 2);
        context.fillStyle = COLOURS.handover;
        context.fill();
        context.lineWidth = 1.6;
        context.strokeStyle = '#fff';
        context.stroke();
        context.fillStyle = '#fff';
        context.textAlign = 'center';
        context.textBaseline = 'middle';
        context.fillText(text, x, y + .5);
        hits.push({x, y, r: radius + 2, kind: 'handover', item: move, priority: 4.5});
      }
      // The way of the car through the tests of its drive (15 minutes before and after, those a car could have driven between):
      // faint grey winding roads from test to test, each with an arrow towards where it was heading, joined to the road of
      // the call: the one from its test before it ends where the call started, and the one to its next test starts where it
      // ended (past the tests its simulated way goes by, which the road of the call takes).
      const {route, anchor, next} = carStretches(data);
      const carRoad = (from, to, item) => {
        const road = windingRoad([project(from[0], from[1]), project(to[0], to[1])]);
        if (road.length < 3) return;
        const reach = Math.hypot(road.at(-1)[0] - road[0][0], road.at(-1)[1] - road[0][1]);
        paintRoad(context, road, {colour: COLOURS.route, alpha: .85, arrow: reach >= 30 ? .5 : null});
        const [mx, my] = road[Math.floor(road.length / 2)];
        hits.push({x: mx, y: my, r: 9, kind: 'car_road', item: {...item, metres: geodesic([from[1], from[0]], [to[1], to[0]]).metres}, priority: 4.6});
      };
      route.forEach((point, index) => {
        const last = route[index - 1];
        if (!routeShown || !index || (index > anchor && index < next)) return;
        if (anchor >= 0 && index === anchor) carRoad(last, start || point, {from: last[2], to: 'start'});
        else if (anchor >= 0 && index === next) carRoad(call.way ? call.way.points.at(-1) : route[anchor], point, {from: call.way ? 'end' : 'start', to: point[2]});
        else carRoad(last, point, {from: last[2], to: point[2]});
      });
      // The way of the call as a winding road (its bends a sketch, not its streets): from where it started to where it ended
      // (a Voice call), else, for a Data test (the CDR gives only where it started and how far it went), its way simulated
      // along the way of its car with an arrow where it ended. A Data test without the way of its car shows the zone it can
      // have been in instead.
      // With Layer 3 - DT Logs, the real way of the UE (from its GPS) replaces the sketch.
      const realWay = window.L3Layers?.wayOf(shared.l3) || null;
      const base = realWay ? realWay.map(([latitude, longitude]) => project(latitude, longitude))
        : (call.way?.points || []).length > 1 ? call.way.points.map(([latitude, longitude]) => project(latitude, longitude)) : null;
      const way = base ? (realWay ? base : windingRoad(base)) : null;
      if (!routeShown) {
        // Route off in the layers: no way drawn.
      } else if (way && realWay) {
        paintRoad(context, way, {arrow: 'end', colour: window.L3Layers.ROUTE_COLOUR});
        const [mx, my] = way[Math.floor(way.length / 2)];
        hits.push({x: mx, y: my, r: 9, kind: 'l3_way', item: {points: realWay.length}, priority: 4.7});
      } else if (way) {
        // Between where it started and ended, the arrow goes where no handover place hides it.
        const shares = (call.handovers || []).map((point) => point.fraction ?? -1);
        const [clear] = [.7, .55, .4, .85, .25].reduce((best, share) => {
          const gap = Math.min(1, ...shares.map((fraction) => Math.abs(fraction - share)));
          return gap > best[1] ? [share, gap] : best;
        }, [.7, -1]);
        paintRoad(context, way, {arrow: call.way.by === 'ends' ? clear : 'end'});
        const [ex, ey] = way.at(-1), [mx, my] = way[Math.floor(way.length / 2)];
        if (call.way.by !== 'ends') hits.push({x: ex, y: ey, r: 12, kind: 'way', item: call.way, priority: 4.8});
        hits.push({x: mx, y: my, r: 9, kind: 'way', item: call.way, priority: 4.7});
      } else if (start && !call.end && call.travelled_m) {
        const [x, y] = project(start[0], start[1]);
        const reach = call.travelled_m / metresPerPixel;
        if (reach >= 4) {
          context.beginPath();
          context.arc(x, y, reach, 0, Math.PI * 2);
          context.fillStyle = 'rgba(61, 24, 36, .07)';
          context.fill();
          context.setLineDash([5, 4]);
          context.lineWidth = 2;
          context.strokeStyle = COLOURS.path;
          context.stroke();
          context.setLineDash([]);
        }
      }
      // NQ Maps: the route of each session of the Layer 3 - DT Logs in time order (its switch in their card), a gap of more
      // than 20 s cutting it.
      if (data.area) {
        for (const route of window.L3Layers?.routesOf(shared.l3) || []) {
          const pieces = [[]];
          route.points.forEach((point, index) => {
            if (index && point[0] - route.points[index - 1][0] > 20000) pieces.push([]);
            pieces.at(-1).push(project(point[1], point[2]));
          });
          paintPieces(pieces, window.L3Layers.ROUTE_COLOUR, 'l3_route', route, 2);
        }
      }
      // The points of the layers of its Layer 3 - DT Logs that are on.
      if (window.L3Layers?.state.around) window.L3Layers.draw(context, shared.l3Around, {project, hits, zoom, width, height, faded: true});
      window.L3Layers?.draw(context, shared.l3, {project, hits, zoom, width, height});
      window.L3Layers?.drawHighlight(context, shared.l3Hover, project);
      // The moment of the cursor of the signalling timeline: where each UE was and its signalling just before.
      window.L3Layers?.drawCursor(context, shared.l3Focus || shared.l3, project);
      // The other Non-Qualified Calls, over the routes and the layers of the logs: those of its groups (hotspot, cluster,
      // time-window issue) and of its site, then the others. The calls on one point make one mark with how many they are (the
      // most related gives its colour); with Per Group, an outline of its shape for each group of the call they are of (and
      // switched on), its cluster innermost, then its time window and its hotspot.
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
          // Larger than the points of the layers, with a shadow, so that they stand out (larger still close in); larger on the
          // map of a call than on NQ Maps, where they are many.
          const size = data.area ? 8 + (zoom >= 15 ? 1.5 : 0) : 11.5 + (zoom >= 15 ? 2 : 0);
          // On NQ Maps those without Layer 3 - DT Logs are hollow, in their colour.
          const hollow = data.area && !items.some((item) => item.l3_log);
          context.save();
          context.shadowColor = 'rgba(30, 10, 20, .45)';
          context.shadowBlur = 5;
          context.shadowOffsetY = 1;
          diamond(context, x, y, size);
          context.fillStyle = hollow ? '#fff' : shared.failureColour(failure);
          context.fill();
          context.restore();
          diamond(context, x, y, size);
          context.lineWidth = hollow ? 2.6 : 2;
          context.strokeStyle = hollow ? shared.failureColour(failure) : '#fff';
          context.stroke();
          // Per Group: an outline of its shape for each group of the call the calls on the point are of, each over a white one.
          const groups = data.area ? [] : ['cluster', 'run', 'hotspot'].filter((kind) => items.some((item) => shared.failureGroups(item).includes(kind)));
          groups.forEach((kind, index) => {
            diamond(context, x, y, size + 4.6 + index * 4.6);
            context.lineJoin = 'miter';
            context.lineWidth = 4.6;
            context.strokeStyle = 'rgba(255, 255, 255, .9)';
            context.stroke();
            context.lineWidth = 2.6;
            context.strokeStyle = GROUP_COLOURS[kind];
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
          hits.push({x, y, r: size + 3 + groups.length * 4.6, kind: 'failure', item: failure, priority: 4, stack: items.length});
        }
      }
      // The order of the failures of each time window, in a blue badge at the top left of each (beyond its circles).
      context.font = '800 10px "IBM Plex Sans", system-ui, sans-serif';
      context.textAlign = 'center';
      context.textBaseline = 'middle';
      const badgeOffset = data.area ? 11 : 20;
      for (const [px, py, number] of pathNumbers) {
        const [bx, by] = [px - badgeOffset, py - badgeOffset];
        context.beginPath();
        context.arc(bx, by, 7.5, 0, Math.PI * 2);
        context.fillStyle = COLOURS.run;
        context.fill();
        context.lineWidth = 1.5;
        context.strokeStyle = '#fff';
        context.stroke();
        context.fillStyle = '#fff';
        context.fillText(String(number), bx, by + .5);
      }
      // Where the call started (when the CDR gives where it ended too).
      if (start && call.end && !realWay) {
        const [x1, y1] = project(start[0], start[1]);
        context.beginPath();
        context.arc(x1, y1, 6, 0, Math.PI * 2);
        context.fillStyle = COLOURS.start;
        context.fill();
        context.lineWidth = 2;
        context.strokeStyle = '#fff';
        context.stroke();
        hits.push({x: x1, y: y1, r: 9, kind: 'start', item: call, priority: 5});
      }
      // Where each handover took place on its way, an estimate (by the time on each band of the call, else evenly in their
      // order): a ring numbered as its arrow, dashed, on the road of its way (at the share of its way behind it).
      if (layers.path && !realWay) {
        for (const point of call.handovers || []) {
          const [x, y] = way && way !== base && point.fraction !== undefined ? way[Math.round(point.fraction * (way.length - 1))] : project(point.latitude, point.longitude);
          context.beginPath();
          context.arc(x, y, 8, 0, Math.PI * 2);
          context.fillStyle = '#fff';
          context.fill();
          context.setLineDash([3, 2]);
          context.lineWidth = 2.2;
          context.strokeStyle = COLOURS.handover;
          context.stroke();
          context.setLineDash([]);
          context.font = '800 10px "IBM Plex Sans", system-ui, sans-serif';
          context.fillStyle = COLOURS.handover;
          context.textAlign = 'center';
          context.textBaseline = 'middle';
          context.fillText(String(point.order), x, y + .5);
          hits.push({x, y, r: 10, kind: 'handover_point', item: point, priority: 5.5});
        }
      }
      if (!data.area) {
        const [px, py] = project(failurePoint[0], failurePoint[1]);
        pin(context, px, py, 10, COLOURS.call);
        hits.push({x: px, y: py - 15, r: 13, kind: 'call', item: call, priority: 6});
      }
      // START and END where the call started and ended (where its simulated way ended, for a Data test): beside them on the
      // side away from its road, beside the head of the pin where the pin stands.
      const tag = (text, colour, [x, y], [ux, uy], pinned, clearance) => {
        context.font = '800 10px "IBM Plex Sans", system-ui, sans-serif';
        const width = context.measureText(text).width + 12, height = 16;
        const reach = clearance + Math.abs(ux) * width / 2 + Math.abs(uy) * height / 2;
        const [cx, cy] = pinned ? [x + (ux >= 0 ? 1 : -1) * (14 + width / 2), y - 15] : [x + ux * reach, y + uy * reach];
        context.beginPath();
        context.roundRect?.(cx - width / 2, cy - height / 2, width, height, 8);
        if (!context.roundRect) context.rect(cx - width / 2, cy - height / 2, width, height);
        context.fillStyle = colour;
        context.fill();
        context.lineWidth = 1.5;
        context.strokeStyle = '#fff';
        context.stroke();
        context.fillStyle = '#fff';
        context.textAlign = 'center';
        context.textBaseline = 'middle';
        context.fillText(text, cx, cy + .5);
      };
      const heading = (from, to) => {
        const length = Math.hypot(to[0] - from[0], to[1] - from[1]);
        return length ? [(to[0] - from[0]) / length, (to[1] - from[1]) / length] : [1, 0];
      };
      const [sx, sy] = way ? heading(way[0], way[Math.min(3, way.length - 1)]) : [-1, 0];
      if (!routeShown) {
        // Route off: neither START nor END.
      } else if (realWay) {
        // Where the log of the UE starts and ends.
        tag('START', COLOURS.start, way[0], [-sx, -sy], false, 10);
        tag('END', COLOURS.end, way.at(-1), heading(way[Math.max(0, way.length - 4)], way.at(-1)), false, 14);
      } else {
        if (start) tag('START', COLOURS.start, project(start[0], start[1]), [-sx, -sy], !call.end, 10);
        if (call.end) tag('END', COLOURS.end, project(call.end[0], call.end[1]), way ? heading(way[Math.max(0, way.length - 4)], way.at(-1)) : [1, 0], true, 0);
        else if (way) tag('END', COLOURS.end, way.at(-1), heading(way[Math.max(0, way.length - 4)], way.at(-1)), false, 14);
      }
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
      // The area shown (south, west, north, east) and its zoom, for a map that reads what it draws by area.
      if (onViewChange) {
        const [west, north] = toLonLat(view.x - width / 2 * view.resolution, view.y - height / 2 * view.resolution);
        const [east, south] = toLonLat(view.x + width / 2 * view.resolution, view.y + height / 2 * view.resolution);
        onViewChange({bbox: [south, west, north, east], zoom: REFERENCE_ZOOM - Math.log2(view.resolution)});
      }
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
      // The point of the elevation profile under the pointer.
      if (measure.hover) {
        const [hx, hy] = project(measure.hover.latitude, measure.hover.longitude);
        const mark = svg('circle');
        mark.setAttribute('cx', hx); mark.setAttribute('cy', hy); mark.setAttribute('r', 6); mark.setAttribute('class', 'nq-map-measure-hover');
        ruler.append(mark);
      }
    };
    // The elevation profile of the distance measured: read once it is drawn (a new one replaces it), cleared with the ×; a
    // click anywhere on its header folds it to its figures or unfolds it.
    let profileToken = 0, profileOpen = true, lastProfile = null;
    const renderProfile = (profile) => {
      lastProfile = profile;
      profileBox.replaceChildren();
      profileBox.hidden = !measure;
      if (!measure) return;
      const head = node('header', undefined, 'nq-map-profile-head');
      head.addEventListener('click', () => { profileOpen = !profileOpen; renderProfile(lastProfile); });
      const fold = node('button', undefined, 'nq-map-profile-title');
      fold.type = 'button';
      fold.setAttribute('aria-expanded', String(profileOpen));
      fold.append(node('strong', 'Elevation profile'), node('span', profileOpen ? '▾' : '▸', 'nq-l3-chevron'));
      const close = node('button', '×', 'nq-map-info-close');
      close.type = 'button';
      close.title = 'Clear the distance and its elevation profile';
      close.setAttribute('aria-label', 'Clear the distance and its elevation profile');
      close.addEventListener('click', (event) => { event.stopPropagation(); clearMeasure(); });
      const {metres, bearing} = geodesic(measure.from, measure.to);
      head.append(fold, node('span', `${metresText(metres)} · ${Math.round(bearing)}°`, 'nq-map-profile-span'));
      profileBox.append(head);
      if (!profile) {
        head.append(close);
        if (profileOpen) profileBox.append(node('p', 'Reading the elevation of the ground…', 'nq-map-profile-note'));
        return;
      }
      const known = profile.points.filter((point) => point.elevation !== null && Number.isFinite(point.elevation));
      if (known.length < 2) {
        head.append(close);
        if (profileOpen) profileBox.append(node('p', 'The elevation of the ground could not be read here.', 'nq-map-profile-note'));
        return;
      }
      const values = known.map((point) => point.elevation);
      const low = Math.min(...values), high = Math.max(...values);
      let gain = 0, loss = 0, slope = 0;
      known.forEach((point, index) => {
        if (!index) return;
        const rise = point.elevation - known[index - 1].elevation, run = point.metres - known[index - 1].metres;
        if (rise > 0) gain += rise; else loss -= rise;
        if (run > 0) slope = Math.max(slope, Math.abs(rise) / run);
      });
      const stats = node('div', undefined, 'nq-map-profile-stats');
      for (const [name, value] of [['Start', known[0].elevation], ['End', known.at(-1).elevation], ['Min', low], ['Max', high]]) {
        stats.append(node('span', `${name} ${Math.round(value)} m`));
      }
      stats.append(node('span', `↑ ${Math.round(gain)} m`), node('span', `↓ ${Math.round(loss)} m`), node('span', `Max slope ${(slope * 100).toFixed(1)} %`));
      head.append(stats, close);
      if (!profileOpen) return;
      // The ground as an area over the distance, with its scale; under the pointer, its point (also on the map).
      const width = Math.max(320, Math.round(profileBox.clientWidth || card.clientWidth || 600) - 24), height = 118;
      const left = 44, right = 10, top = 8, bottom = 20;
      const span = Math.max(1, high - low), floor = low - span * .08, ceiling = high + span * .12;
      const x = (share) => left + share * (width - left - right);
      const y = (value) => top + (1 - (value - floor) / (ceiling - floor)) * (height - top - bottom);
      const svgNode = (tag, attributes = {}) => {
        const element = document.createElementNS('http://www.w3.org/2000/svg', tag);
        for (const [name, value] of Object.entries(attributes)) element.setAttribute(name, String(value));
        return element;
      };
      const chart = svgNode('svg', {viewBox: `0 0 ${width} ${height}`, width, height, class: 'nq-map-profile-chart', role: 'img',
        'aria-label': `Elevation profile: from ${Math.round(known[0].elevation)} m to ${Math.round(known.at(-1).elevation)} m, between ${Math.round(low)} and ${Math.round(high)} m`});
      const line = known.map((point) => `${x(point.share).toFixed(1)},${y(point.elevation).toFixed(1)}`).join(' ');
      chart.append(svgNode('polygon', {points: `${x(known[0].share).toFixed(1)},${height - bottom} ${line} ${x(known.at(-1).share).toFixed(1)},${height - bottom}`,
        class: 'nq-map-profile-area'}), svgNode('polyline', {points: line, class: 'nq-map-profile-line'}));
      for (const value of [low, high]) {
        chart.append(svgNode('line', {x1: left, x2: width - right, y1: y(value), y2: y(value), class: 'nq-map-profile-grid'}));
        const label = svgNode('text', {x: left - 5, y: y(value) + 3, class: 'nq-map-profile-axis', 'text-anchor': 'end'});
        label.textContent = `${Math.round(value)} m`;
        chart.append(label);
      }
      for (const share of [0, .25, .5, .75, 1]) {
        const label = svgNode('text', {x: x(share), y: height - 6, class: 'nq-map-profile-axis', 'text-anchor': share === 0 ? 'start' : share === 1 ? 'end' : 'middle'});
        label.textContent = metresText(metres * share);
        chart.append(label);
      }
      const cursor = svgNode('line', {y1: top, y2: height - bottom, class: 'nq-map-profile-cursor'});
      const dot = svgNode('circle', {r: 4, class: 'nq-map-profile-dot'});
      const readout = node('span', '', 'nq-map-profile-readout');
      cursor.style.display = dot.style.display = 'none';
      chart.append(cursor, dot);
      chart.addEventListener('pointermove', (event) => {
        const bounds = chart.getBoundingClientRect();
        const share = clamp(((event.clientX - bounds.left) * width / bounds.width - left) / (width - left - right), 0, 1);
        const point = known.reduce((best, item) => (Math.abs(item.share - share) < Math.abs(best.share - share) ? item : best), known[0]);
        const index = known.indexOf(point), before = known[Math.max(0, index - 1)], after = known[Math.min(known.length - 1, index + 1)];
        const grade = after.metres > before.metres ? (after.elevation - before.elevation) / (after.metres - before.metres) * 100 : 0;
        cursor.setAttribute('x1', x(point.share)); cursor.setAttribute('x2', x(point.share));
        dot.setAttribute('cx', x(point.share)); dot.setAttribute('cy', y(point.elevation));
        cursor.style.display = dot.style.display = '';
        readout.textContent = `${metresText(point.metres)} · ${Math.round(point.elevation)} m · slope ${grade.toFixed(1)} %`;
        measure.hover = point;
        drawMeasure();
      });
      chart.addEventListener('pointerleave', () => {
        cursor.style.display = dot.style.display = 'none';
        readout.textContent = '';
        if (measure) { measure.hover = null; drawMeasure(); }
      });
      profileBox.append(chart, node('p', undefined, 'nq-map-profile-note'));
      profileBox.lastChild.append(readout, node('span', TERRAIN_ATTRIBUTION, 'nq-map-profile-source'));
    };
    const readProfile = async () => {
      const token = ++profileToken;
      renderProfile(null);
      const profile = await elevationProfile(measure.from, measure.to);
      if (token === profileToken && measure) renderProfile(profile);
    };
    const clearMeasure = () => { if (measure) { measure = null; profileToken += 1; drawMeasure(); renderProfile(null); } };
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
        if (hit.wedge) {
          const turn = Math.PI * 2;
          const angle = ((Math.atan2(y - hit.y, x - hit.x) - hit.wedge[0]) % turn + turn) % turn;
          if (angle > ((hit.wedge[1] - hit.wedge[0]) % turn + turn) % turn) continue;
        }
        if (!best || hit.priority > best.hit.priority || (hit.priority === best.hit.priority && distance < best.distance)) best = {hit, distance};
      }
      return best?.hit || null;
    };
    const showTooltip = (hit, event) => {
      if (!hit) { tooltip.hidden = true; canvas.classList.remove('is-pointing'); return; }
      canvas.classList.add('is-pointing');
      const {title, rows} = shared.describe(hit.kind, hit.item);
      tooltip.replaceChildren(node('strong', title));
      const filled = rows.filter(([, value]) => value !== '' && value !== null && value !== undefined);
      for (const [name, value] of [...(hit.stack > 1 ? [['At this point', `${hit.stack} NQ calls`]] : []), ...filled.slice(0, 18)]) {
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
    // In the panel a double-click opens the larger map; in the larger map it zooms in. A touch screen sends no double-click
    // for a double tap (its pointerdown is taken to move the map): two taps close in time and place do the same (see stopDrag).
    let lastTap = null, doubleTapped = 0;
    const doubleClick = (event) => {
      if (expanded || !onExpand) zoomBy(.5, ...pointerOffset(event));
      else onExpand();
    };
    canvas.addEventListener('dblclick', (event) => {
      event.preventDefault();
      event.stopPropagation();
      // The double-click a browser may still send after a double tap.
      if (performance.now() - doubleTapped < 700) return;
      doubleClick(event);
    });
    // On a touch screen two fingers zoom the map (a pinch) towards their middle, which also moves it; one finger moves it.
    const touches = new Map();
    let pinch = null;
    const pinchNow = () => {
      const [first, second] = [...touches.values()];
      const [x, y] = pointerOffset({clientX: (first.x + second.x) / 2, clientY: (first.y + second.y) / 2});
      return {distance: Math.max(1, Math.hypot(first.x - second.x, first.y - second.y)), x, y};
    };
    // Whether a touch belongs to a pinch, which then takes it from the mouse handlers below.
    const pinchTouch = (event) => {
      if (event.pointerType !== 'touch' || !view) return false;
      if (event.type === 'pointerdown') {
        touches.set(event.pointerId, {x: event.clientX, y: event.clientY});
        if (touches.size < 2) return false;
        pinch = {...pinchNow(), view: {...view}};
        // The finger down first stops moving the map.
        drag = null;
        selectionBox.hidden = true;
        tooltip.hidden = true;
        canvas.classList.remove('is-panning', 'is-selecting', 'is-measuring');
        try { canvas.setPointerCapture?.(event.pointerId); } catch (_error) { /* A pointer that is gone already. */ }
        event.preventDefault();
        return true;
      }
      if (!touches.has(event.pointerId)) return false;
      if (event.type === 'pointermove') {
        touches.set(event.pointerId, {x: event.clientX, y: event.clientY});
        if (!pinch || touches.size < 2) return false;
        const now = pinchNow();
        const resolution = clamp(pinch.view.resolution * pinch.distance / now.distance, MIN_RESOLUTION, MAX_RESOLUTION);
        // The place under the middle of the fingers when they touched stays under their middle.
        view = {x: pinch.view.x + pinch.x * pinch.view.resolution - now.x * resolution,
          y: pinch.view.y + pinch.y * pinch.view.resolution - now.y * resolution, resolution};
        redraw();
        return true;
      }
      // A finger lifted: after a pinch, the one left neither moves the map nor chooses an element.
      touches.delete(event.pointerId);
      if (!pinch) return false;
      if (touches.size < 2) pinch = null;
      return true;
    };
    canvas.addEventListener('pointerdown', (event) => {
      if (pinchTouch(event)) return;
      if ((event.button !== 0 && event.button !== 1) || !view) return;
      modifierKeys(event);
      const measuring = event.button === 0 && event.altKey;
      const pan = !measuring && (event.button === 1 || !(event.ctrlKey || event.metaKey));
      drag = {id: event.pointerId, pan, measuring, startX: event.clientX, startY: event.clientY, x: event.clientX, y: event.clientY};
      try { canvas.setPointerCapture?.(event.pointerId); } catch (_error) { /* A pointer that is gone already. */ }
      canvas.classList.add(measuring ? 'is-measuring' : pan ? 'is-panning' : 'is-selecting');
      tooltip.hidden = true;
      if (measuring) {
        // A new distance: the profile of the last one goes until this one is drawn.
        profileToken += 1;
        profileBox.hidden = true;
        measure = {from: placeAt(event), to: placeAt(event)};
        drawMeasure();
      }
      event.preventDefault();
    });
    canvas.addEventListener('pointermove', (event) => {
      if (pinchTouch(event)) return;
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
      if (pinchTouch(event)) return;
      if (!drag || event.pointerId !== drag.id) return;
      const finished = drag;
      drag = null;
      selectionBox.hidden = true;
      try { canvas.releasePointerCapture?.(event.pointerId); } catch (_error) { /* Released already. */ }
      canvas.classList.remove('is-panning', 'is-selecting', 'is-measuring');
      const moved = Math.hypot(event.clientX - finished.startX, event.clientY - finished.startY) >= 4;
      if (finished.measuring) {
        if (!moved) clearMeasure();
        else readProfile();
        return;
      }
      if (finished.pan && !moved && event.type === 'pointerup') {
        if (event.pointerType !== 'mouse') {
          const now = performance.now();
          if (lastTap && now - lastTap.time < 400 && Math.hypot(event.clientX - lastTap.x, event.clientY - lastTap.y) < 30) {
            lastTap = null;
            doubleTapped = now;
            doubleClick(event);
            return;
          }
          lastTap = {time: now, x: event.clientX, y: event.clientY};
        }
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
    const resizer = new ResizeObserver(() => { nameBasemaps(); redraw(); });
    resizer.observe(card);

    // The legend: the levels of the measure chosen and the marks of the map.
    const renderLegend = () => {
      const data = shared.data, settings = shared.settings;
      legend.replaceChildren();
      renderSamples();
      if (!data) return;
      fitButton.title = data.area ? 'Show every NQ call of the filters with Layer 3 - DT Logs' : FIT_TITLE;
      fitButton.setAttribute('aria-label', fitButton.title);
      const paths = visibleRings(data).some((ring) => ring.path && ring.path.length > 1);
      const layers = shownLayers(settings);
      const pathsShown = layers.paths !== false;
      const routeShown = layers.route !== false;
      // Two boxes, as the cards on the map: From CDR (its groups below) and From Logs (l3_layers.js legend).
      const cdrBox = node('div', undefined, 'nq-map-legend-box');
      cdrBox.append(node('p', 'From CDR', 'nq-map-legend-box-title'));
      const finish = (l3Route = '') => {
        if (cdrBox.children.length > 1) legend.append(cdrBox);
        const l3Legend = window.L3Layers?.legend(shared.l3, {route: l3Route});
        if (l3Legend) legend.append(l3Legend);
      };
      let list = null;
      const group = (title) => {
        list = node('ul');
        list.append(node('li', title, 'nq-map-legend-title'));
        cdrBox.append(list);
      };
      const item = (mark, text, colour, extra = '') => {
        const entry = node('li');
        const swatch = node('span', undefined, `nq-map-mark is-${mark}${extra ? ` ${extra}` : ''}`);
        swatch.style.setProperty('--mark', colour);
        entry.append(swatch, node('span', text));
        list.append(entry);
      };
      // The levels of each measure of the samples shown.
      for (const key of shownMeasures(settings)) {
        const metric = METRICS[key];
        const mark = SAMPLE_MARKS[SAMPLE_SHAPES[key]], extra = key.startsWith('nr_') ? 'is-nr' : '';
        group(`RSRP / SINR (from CDR samples) · ${metric.label}`);
        if (key === 'result') {
          item(mark, 'Completed', COLOURS.completed);
          item(mark, 'Not completed', COLOURS.failed);
        } else {
          const levels = data.classes[metric.classes] || [];
          levels.forEach((levelItem, index) => {
            const upper = index ? levels[index - 1].lower : null;
            const range = levelItem.lower === null ? `< ${upper}` : upper === null ? `≥ ${levelItem.lower}` : `${levelItem.lower} to ${upper}`;
            item(mark, `${levelItem.label} (${range} ${metric.unit})`, levelItem.colour, extra);
          });
          item(mark, 'No value', COLOURS.noValue, extra);
        }
      }
      if (data.area) {
        // NQ Maps: its NQ calls as on the map of a call (without its groups), the route of each session and the sites
        // of the area shown.
        if (layers.failures) {
          group(`NQ calls · by ${AREA_FAILURE_COLOURS[settings.failureColour].toLowerCase()}`);
          shared.failureLegend().forEach(([text, colour, extra]) => item('diamond', text, colour, extra));
          if (data.failures.some((failure) => !failure.l3_log)) item('diamond', 'Hollow: without Layer 3 - DT Logs', '#495057', 'is-outlined');
          item('count', 'NQ calls at one point (how many)', '#2d1520');
        }
        const routes = (window.L3Layers?.routesOf(shared.l3) || []).length, sites = layers.sites !== false && data.sites.length;
        const drives = routeShown && data.tests.rows.length;
        if (sites || drives) group('Routes and sites');
        if (drives) item('road', 'Route: the drive of each CDR between its tests (in time order)', COLOURS.route);
        if (sites) item('triangle', 'Site (colour of its vendor), with its cells once close enough', '#868e96');
        l3Tree?.render();
        finish(routes ? 'The GPS of each session' : '');
        return;
      }
      group('This call');
      // A Data test gives only where it started: its pin marks that place, and its way where it went (and failed).
      item('pin', data.call.end ? 'This call (where it failed)' : 'This test (where it started; it failed on its way)', COLOURS.call);
      if (data.call.end) item('dot', 'Where it started', COLOURS.start);
      if (!routeShown || window.L3Layers?.wayOf(shared.l3)) { /* Its route hidden, or the real way of its log (below). */ }
      else if (data.call.way?.by === 'ends') item('road', 'Its way, from where it started to where it ended (arrow: its direction; the bends are a sketch, not its streets)', COLOURS.path);
      else if (data.call.way) item('road', `Its way, simulated: its ${distanceText(data.call.travelled_m / 1000)} from where it started, towards where its car was heading (arrow: where it ended; the bends are a sketch)`, COLOURS.path);
      else if (!data.call.end && data.call.travelled_m) item('ring', `Where the test went: within ${distanceText(data.call.travelled_m / 1000)} of where it started (the distance it travelled)`, COLOURS.path, 'is-dashed');
      if (routeShown && carStretches(data).route.length > 1) {
        item('road', `The way of its car: its tests ${data.drive.minutes} minutes before and after, joined to where the call started and ended (arrows: where it was heading; the bends are a sketch)`, COLOURS.route);
      }
      item('line', `Radius ${distanceText(data.radius_km)}`, COLOURS.radius, 'is-dashed');
      // The NQ calls around as on NQ Maps: a colour for each value of Colour NQ calls by, with the outlines of Per Group.
      if (layers.failures) {
        group(focusKind() ? `NQ calls · only its ${groupFocus.label} (filtering the list)` : `NQ calls · by ${FAILURE_COLOURS[settings.failureColour].toLowerCase()}`);
        shared.failureLegend().forEach(([text, colour, extra, mark]) => item(mark || 'diamond', text, colour, extra));
        item('count', 'NQ calls at one point (how many)', '#2d1520');
      }
      // The shapes of its groups switched on: its own one by one, those of the other calls of its hotspot by kind, then its zone.
      const all = visibleRings(data), rings = all.filter((ring) => layers[ring.kind] !== false);
      const zone = hotspotShown(data) && layers.hotspot !== false;
      if (rings.length || zone || (pathsShown && paths)) {
        group('Groups of the call');
        rings.filter((ring) => ring.own).forEach((ring) => item('ring', ring.label, GROUP_COLOURS[ring.kind]));
        [['cluster', 'Other clusters of its hotspot'], ['run', 'Other time windows of its hotspot']].forEach(([kind, text]) => {
          const count = rings.filter((ring) => !ring.own && ring.kind === kind).length;
          if (count) item('ring', `${text} (${count})`, GROUP_COLOURS[kind]);
        });
        if (pathsShown && paths) item('line', 'Time window: its failures in their order (numbered)', COLOURS.run, 'is-dashed');
        if (zone) {
          item('zone', data.hotspot_join === 'and' && all.some((ring) => ring.kind === 'run') && all.some((ring) => ring.kind !== 'run')
            ? 'Hotspot (AND): where its clusters and time windows meet' : 'Hotspot (OR): its clusters and time windows together', COLOURS.hotZone);
        }
      }
      const located = data.trace.some((step) => step.site);
      if ((layers.sites && data.sites.length) || (layers.path && located) || data.sites.some((site) => site.ends?.length)) {
        group('Sites and cells');
        item('triangle', 'Site (colour of its vendor)', '#868e96');
        const ends = data.sites.flatMap((site) => site.ends || []);
        for (const [role, text, colour] of [['start', 'where it started', COLOURS.start], ['end', 'where it ended (failed)', COLOURS.call]]) {
          if (ends.some((end) => end.role === role && !end.estimated)) item('ring', `Site of the cell that served ${role === 'start' ? 'its start' : 'its end'}: ${text}`, colour);
          // The nearest site is only an estimate: the call started or ended on a cell (such as a GSM one) the inventory does not hold.
          const technology = data.call.ends?.[role]?.estimated ? data.call.ends[role].technology : '';
          if (ends.some((end) => end.role === role && end.estimated)) {
            item('ring', `Nearest site to ${text}: an estimate, as the call ${role === 'start' ? 'started' : 'ended'} on a ${technology ? `${technology} ` : ''}`
              + 'cell that is not in the Network Inventory', colour, 'is-dashed');
          }
        }
      }
      // Only the roles the cells of the call have on the map (a call served by one cell has neither start nor handovers).
      if (layers.path && located) {
        const roles = new Set(data.trace.filter((step) => step.site).map((step) => step.role));
        if (roles.has('both')) item('line', 'Cell that served the whole call', COLOURS.both);
        if (roles.has('start')) item('line', 'Cell that served the start', COLOURS.start);
        if (roles.has('handover')) item('line', 'Handover: an arrow from cell to cell, numbered as the cells of the call', COLOURS.handover);
        if ((data.call.handovers || []).length) item('ring', 'Where each handover took place on its way (an estimate, numbered as its arrow)', COLOURS.handover, 'is-dashed');
        if (roles.has('end')) item('line', 'Cell that served the end', COLOURS.end);
        if (roles.has('nr_leg')) item('line', 'NR leg (by PCI)', COLOURS.nr_leg, 'is-dotted');
      }
      if (layers.sites && data.sites.some((site) => site.cells.some((cell) => cell.same_pci))) {
        item('line', 'Same PCI and channel as a cell of the call', COLOURS.samePci, 'is-dashed');
      }
      l3Tree?.render();
      finish(window.L3Layers?.wayOf(shared.l3) ? 'The real way of the UE (GPS of its log), from START to END' : '');
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
      // Its cards folded again (the map shows another call).
      collapseCards: () => { samplesOpen = false; renderSamples(); l3Tree?.collapse(); },
      // A panel over the bottom of the map, below the elevation profile (the signalling timeline of the larger map).
      overlay: (element) => bottomStack.append(element),
      // Moved (not zoomed) so that a place stays on the map: centred on it once it leaves the middle 80 % of the map.
      keepInView: (latitude, longitude) => {
        const width = canvas.clientWidth, height = canvas.clientHeight;
        if (!view || !width || !height) return;
        const [x, y] = project(latitude, longitude);
        if (x >= width * .1 && x <= width * .9 && y >= height * .1 && y <= height * .9) return;
        [view.x, view.y] = toWorld(latitude, longitude);
        redraw();
      },
      destroy: () => { resizer.disconnect(); document.removeEventListener('keydown', onKey); basemapViews.delete(basemapChanged); l3Tree?.destroy(); },
    };
  }

  // -- the map panel of the call in the drawer, and its larger view ----------------------------------------------
  // groupFilter: the group of the call shown that filters the list of calls ({filter, key, label}), or null.
  function mount({panel, expandDialog, api, toast, openCall, useRootCause = null, canEdit = () => false, campaignLabel, cdrTime, number,
    groupFilter = () => null, filters = () => ({})}) {
    const stored = readSettings();
    const settings = {
      // Each call opens with the radius of its hotspot and cluster (or 1 km); the radius chosen holds while it stays open.
      radius_km: 1, tests: stored.tests === 'campaign' ? 'campaign' : 'selected',
      // The measures of the samples shown (none until some are switched on, so the map shows the call, its cells and the
      // sites first).
      measures: storedMeasures(stored),
      operators: ['all', 'focus'].includes(stored.operators) ? stored.operators : 'own',
      // The Non-Qualified Calls around drawn: those of the campaigns chosen in the filters until another choice.
      failures: FAILURE_SCOPES[stored.failures] ? stored.failures : 'selected',
      failureColour: FAILURE_COLOURS[stored.failureColour] ? stored.failureColour : 'site',
      // Per Group: a circle around each NQ call of the groups of the call, in the colour of each group.
      perGroup: stored.perGroup !== false,
      // The layers of From CDR (``cdr`` the whole card).
      layers: {cdr: true, failures: true, cluster: true, run: true, hotspot: true, sites: true, path: true, route: true, paths: true, ...(stored.layers || {})},
    };
    delete settings.layers.tests;
    const save = () => storeSettings({tests: settings.tests, measures: settings.measures, operators: settings.operators, failures: settings.failures,
      failureColour: settings.failureColour, perGroup: settings.perGroup, layers: settings.layers});
    let callKey = '', loadedKey = '', controller = null, expandedView = null, expandedTimeline = null, expandedToolbar = null;
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
    const timelineHost = node('div', undefined, 'nq-l3-timeline-host');
    mapWrap.insertBefore(timelineHost, selected);
    panel.replaceChildren(toolbar, status, mapWrap, node('p', PANEL_HINT, 'form-note nq-map-hint'), cards);

    // ``l3``: the Layer 3 - DT Logs of the call shown, ready to draw (l3_layers.js), or null.
    const shared = {data: null, settings, selection: null, l3: null};
    // The Non-Qualified Calls around that the map and its list show: those of the CDR, the campaign (and NR Mode) or every
    // campaign chosen, of its operator or of every operator (its repetitions and its hotspot whatever the operators chosen).
    // The campaigns and NR Modes chosen in the filters of the page (read again at most every second): every one while none is.
    let chosen = null, chosenAt = 0;
    const selectedCampaign = (failure) => {
      if (!chosen || performance.now() - chosenAt > 1000) {
        const current = filters() || {};
        chosen = {campaigns: current.campaign?.length ? new Set(current.campaign) : null, modes: current.nr_mode?.length ? new Set(current.nr_mode) : null};
        chosenAt = performance.now();
      }
      return (!chosen.campaigns || chosen.campaigns.has(failure.campaign)) && (!chosen.modes || chosen.modes.has(failure.nr_mode));
    };
    shared.showsFailure = (failure) => {
      const call = shared.data?.call;
      if (!call || failure.self) return true;
      if (settings.failures === 'campaign' && (failure.campaign !== call.campaign || failure.nr_mode !== call.nr_mode)) return false;
      if (settings.failures === 'selected' && !selectedCampaign(failure)) return false;
      if (hiddenByFocus(failure)) return false;
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
    // A layer of From CDR (or the whole card) and a measure of its samples switched on or off.
    shared.cdrLayers = ['failures', 'cluster', 'run', 'paths', 'hotspot', 'sites', 'path', 'route'];
    shared.setLayer = (key, on) => { settings.layers[key] = on; save(); redrawAll(); renderFailures(); };
    shared.setMeasure = (key, on) => {
      settings.measures = Object.keys(METRICS).filter((name) => (name === key ? on : settings.measures.includes(name)));
      save();
      redrawAll();
    };
    // The CDRs of the tests around the call (its samples, Radio around the call, Diagnosis hints and drive), chosen in the
    // card From CDR as NQ calls from chooses those of the NQ calls: the campaigns chosen in the filters, or that of the call.
    shared.samplesScope = {
      options: () => Object.entries(shared.data?.tests_scopes || {selected: 'Selected campaigns', campaign: 'Call campaign'}),
      value: () => settings.tests,
      set: (value) => { settings.tests = value; save(); load(); },
      title: 'The CDRs of the tests around the call (its RSRP / SINR samples, the Radio around the call, the Diagnosis hints and its drive): every CDR of the campaigns and NR Modes chosen in the filters of the page (of every campaign while none is chosen), or every CDR of the campaign and NR Mode of the call (Voice, Speech and Data together)',
    };
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
    // The colour of an NQ call by the choice of Colour NQ calls by, and the lines of the legend that explain it: one for each
    // value shown, then, with Per Group, the outline of each group of the call.
    // The site of the call (that of its CDR), found once for each call: its NQ calls burgundy when coloured by site.
    let ownSiteData = null, ownSiteKey = '';
    const ownSite = () => {
      if (ownSiteData !== shared.data) {
        ownSiteData = shared.data;
        ownSiteKey = siteOf(shared.data?.failures.find((failure) => failure.self))?.key || '';
      }
      return ownSiteKey;
    };
    shared.failureColour = (failure) => failureColourBy(settings.failureColour, failure, ownSite());
    // The groups of the call an NQ call is of, as Per Group outlines it (those switched on in From CDR): its cluster
    // innermost, then its time window and its hotspot.
    shared.failureGroups = (failure) => (settings.perGroup ? ['cluster', 'run', 'hotspot']
      .filter((kind) => shownLayers(settings)[kind] !== false && groupsOf(failure).includes(kind)) : []);
    shared.failureLegend = () => {
      const data = shared.data;
      const shown = data.failures.filter((failure) => !failure.self && failure.latitude !== null && shared.showsFailure(failure));
      const lines = failureLegendBy(settings.failureColour, shown, {campaignText, ownSite: ownSite()});
      const names = {cluster: 'Outlined: of a cluster of the call', run: 'Outlined: of a time window of the call', hotspot: 'Outlined: of its hotspot'};
      ['cluster', 'run', 'hotspot'].filter((kind) => shown.some((failure) => shared.failureGroups(failure).includes(kind)))
        .forEach((kind) => lines.push([names[kind], GROUP_COLOURS[kind], 'is-outlined']));
      return lines;
    };
    // Whether the call is of a group (a hotspot, cluster or time window with other NQ calls): Per Group shows then.
    const hasGroups = () => Boolean(shared.data?.failures.some((failure) => !failure.self && memberships(failure).length));
    // The cells of a call: its start and end cells (its serving cell when one served all of it), its handover cells on a
    // line of their own and the NR cell of an NSA call.
    const cellRows = (cells = []) => {
      const path = cells.filter((cell) => cell.role !== 'nr_leg');
      const rows = path.length === 1 ? [['Serving cell', path[0].label]]
        : path.length ? [['Start cell', path[0].label], ['End cell', path[path.length - 1].label]] : [];
      const handovers = path.slice(1, -1).map((cell) => cell.label);
      if (handovers.length) rows.push([handovers.length === 1 ? 'Handover cell' : 'Handover cells', handovers.join(' → ')]);
      const leg = cells.find((cell) => cell.role === 'nr_leg');
      if (leg) rows.push(['NR cell (NSA)', leg.label]);
      return rows;
    };
    // The site where a call started or ended, and whether it is only the nearest one to it.
    const endText = (end) => (end ? `${end.site_id} (${end.host_network || end.network})${end.estimated
      ? ` · nearest, ${distanceText(end.distance_km)} away (an estimate: its ${end.technology ? `${end.technology} ` : ''}cell is not in the Network Inventory)` : ''}` : '');
    const siteName = (site) => `Site ${site.site_id} · ${site.network}${site.host_network && site.host_network !== site.network ? ` on ${site.host_network}` : ''}`;
    shared.describe = (kind, item) => {
      const data = shared.data;
      // A point of the Layer 3 - DT Logs of the call (l3_layers.js), and the real way of its UE.
      if (kind === 'l3') return window.L3Layers.describe(item, shared.l3);
      if (kind === 'l3_way') {
        const sessions = Object.values(shared.l3?.sessions || {});
        return {title: 'Real way of the UE', rows: [['From', 'The GPS positions of the Layer 3 - DT Logs of the call'],
          ['Positions', item.points], ['UEs', sessions.map((session) => session.ue).join(', ')],
          ['Dataset', sessions.map((session) => session.dataset_name).filter(Boolean)[0] || '']]};
      }
      if (kind === 'call' || kind === 'start') {
        return {title: kind === 'start' ? 'Where the call started' : 'This call', rows: [
          ['Call type', KIND_LABELS[item.kind] || item.service_label], ['JOIN_ID', item.join_id], ['Operator', item.operator], ['Campaign', campaignText(item.campaign, item.nr_mode)],
          ['Result', item.result], ['Failure', failureText(item)], ['Phase', item.failure_phase],
          ['Technology', item.technology], ['Started', cdrTime(item.start_time)], ['Ended', item.end_time ? cdrTime(item.end_time) : ''],
          // Where it started and ended, then the cells that served it (start, end, handovers).
          ['Start site', endText(item.ends?.start)], ['End site', endText(item.ends?.end)], ...cellRows(item.cells),
          ['Serving distance', item.serving_distance_km !== null && item.serving_distance_km !== undefined ? distanceText(item.serving_distance_km) : ''],
        ]};
      }
      if (kind === 'failure') {
        // Its groups: those of the call, else a cluster or a time window of its hotspot; joining both when it is of both.
        const inCluster = !item.same_cluster && Boolean(item.repeat_key) && ringKeys.cluster.has(item.repeat_key);
        const inWindow = !item.same_run && Boolean(item.consecutive_key) && ringKeys.run.has(item.consecutive_key);
        const flags = [item.same_hotspot ? 'Same hotspot' : '', item.same_cluster ? 'Same cluster' : '', item.same_run ? 'Same time window' : '',
          inCluster ? 'A cluster of its hotspot' : '', inWindow ? 'A time window of its hotspot' : '',
          memberships(item).includes('cluster') && memberships(item).includes('run') ? 'Joins a cluster and a time window' : '',
          item.same_place ? 'Same site' : ''].filter(Boolean).join(' · ');
        return {title: `NQ call · ${item.operator}`, rows: [
          ['Call type', kindLabel(item)], ['Operator', item.operator], ['Campaign', campaignText(item.campaign, item.nr_mode)],
          ['Relation', flags], ['JOIN_ID', item.join_id],
          ['Result', item.result], ['Failure', failureText(item)], ['Test', item.test_name], ['Started', cdrTime(item.start_time)],
          ['Status', item.status], ['Root cause', [item.root_category, item.root_cause].filter(Boolean).join(' · ')],
          // How far it is, where it started and ended (the place of its repetitions when its last cell is not placed), then its
          // cells, as the call shows them.
          ['Distance', distanceText(item.distance_km)], ['Start site', endText(item.ends?.start)],
          ['End site', endText(item.ends?.end) || String(item.place_label || '').replace(/^Site /, '')], ...cellRows(item.cells),
        ]};
      }
      if (kind === 'way') {
        const [first, last] = [item.points[0], item.points.at(-1)];
        return {title: item.by === 'ends' ? 'Its way' : 'Its way (simulated)', rows: [
          ['Travelled', item.by === 'ends' ? `${distanceText(geodesic([first[1], first[0]], [last[1], last[0]]).metres / 1000)} apart` : distanceText(data.call.travelled_m / 1000)],
          ['Lasted', data.call.travelled_s ? `${Math.round(data.call.travelled_s)} s` : ''],
          ['Direction', item.by === 'ends' ? 'From where it started to where it ended' : item.by === 'after'
            ? 'Towards the tests its car made after it (where it was heading)' : 'On from the test its car made before it (where it came from)'],
          ['Shape', item.by === 'ends' ? 'The CDR gives where it started and ended, not the streets between them: its bends are a sketch'
            : 'Simulated: the CDR gives only where it started and how far it went, so its bends are not the streets it took'],
        ]};
      }
      if (kind === 'car_road') {
        // A stretch of the way of its car: between two of its tests, or from one to where the call started or from where it
        // ended (``from`` and ``to``: seconds from the call, or start and end).
        const place = (value) => {
          if (value === 'start') return 'Where the call started';
          if (value === 'end') return data.call.way?.by && data.call.way.by !== 'ends' ? 'Where the call ended (simulated)' : 'Where the call ended';
          const seconds = Math.abs(value), when = seconds >= 60 ? `${Math.floor(seconds / 60)} min ${seconds % 60} s` : `${seconds} s`;
          return `Its test ${when} ${value > 0 ? 'after' : 'before'} it`;
        };
        return {title: typeof item.to === 'number' && item.to > 0 ? 'Its car after the call' : 'Its car before the call', rows: [
          ['From', place(item.from)], ['To', place(item.to)], ['Distance', distanceText(item.metres / 1000)],
          ['Shape', 'Its bends are a sketch, not the streets it took'],
        ]};
      }
      if (kind === 'handover_point') {
        const step = data.trace.find((entry) => entry.order === item.order && entry.role !== 'nr_leg');
        return {title: `Handover ${item.order}: where it took place`, rows: [
          ['To cell', step ? [step.inventory?.name || step.cell, [step.technology, step.band].filter(Boolean).join(' ')].filter(Boolean).join(' · ') : ''],
          ['To site', step?.site_id ? `${step.site_id}${step.host_network || step.network ? ` (${step.host_network || step.network})` : ''}` : ''],
          ['Estimate', `${item.by === 'time' ? 'By the time the call spent on each band (its RAT timeline), at an even speed'
            : 'Spread evenly along its way, in their order (the CDR gives no time per band that matches its cells)'}${
            data.call.way && data.call.way.by !== 'ends' ? ', on its simulated way' : ''}`],
        ]};
      }
      if (kind === 'handover') {
        // A handover: from the cell before it to the cell after it (numbered with the order of that cell).
        const cellText = (step) => [step.inventory?.name || step.cell, [step.technology, step.band].filter(Boolean).join(' '), step.pci ? `PCI ${step.pci}` : '']
          .filter(Boolean).join(' · ');
        const siteText = (step) => (step.site_id ? `${step.site_id}${step.host_network || step.network ? ` (${step.host_network || step.network})` : ''}` : '');
        return {title: `Handover ${item.after.order}`, rows: [
          ['From cell', cellText(item.before)], ['From site', siteText(item.before)], ['To cell', cellText(item.after)], ['To site', siteText(item.after)],
          ['Sites apart', item.before.site === item.after.site ? 'Same site' : (item.before.latitude !== undefined && item.after.latitude !== undefined
            ? distanceText(geodesic([item.before.longitude, item.before.latitude], [item.after.longitude, item.after.latitude]).metres / 1000) : '')],
        ]};
      }
      if (kind === 'cell') {
        const site = data.sites.find((entry) => entry.cells.includes(item));
        const step = site && data.trace.find((entry) => entry.site === site.key && entry.cell === item.identity);
        return {title: `Cell ${item.name || item.identity}`, rows: [
          ['Role', step ? step.role_label : ''], ['Site', site ? siteName(site) : ''], ['Identity', item.identity],
          ['Technology', [item.technology, item.band].filter(Boolean).join(' ')], ['Channel', item.channel], ['PCI', item.pci],
          ['Azimuth', item.azimuth === null || item.azimuth === undefined ? 'Omni' : `${item.azimuth}°`],
          ['Beamwidth', item.beamwidth ? `${item.beamwidth}°` : ''], ['Height', item.height ? `${item.height} m` : ''],
          ['State', item.state], ['Vendor', item.vendor], ['Same PCI and channel', item.same_pci],
        ]};
      }
      if (kind === 'site') {
        const technologies = [...new Set(item.cells.map((cell) => `${cell.technology} ${cell.band}`.trim()))].join(', ');
        return {title: siteName(item), rows: [
          ['Role', [...item.roles, ...(item.ends || []).filter((end) => end.estimated)
            .map((end) => `Nearest site to where it ${end.role === 'start' ? 'started' : 'failed'} (estimate)`)].join(', ')
            || (item.serving ? 'Serving site' : '')], ['Vendor', item.vendors.join(', ')],
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
      if (choice.kind === 'l3' && choice.item.point.row !== undefined && choice.item.point.dataset) {
        // Every value of the record of the log behind the point, read when asked for.
        const more = node('button', 'All the fields of this record', 'nq-secondary-action');
        more.type = 'button';
        more.addEventListener('click', async () => {
          more.disabled = true;
          try {
            const query = new URLSearchParams({dataset_id: String(choice.item.point.dataset), row: String(choice.item.point.row)});
            const {record} = await api(`/api/non-qualified-calls/calls/${encodeURIComponent(callKey)}/l3/record?${query}`);
            const fields = definitionList(Object.entries(record || {}).filter(([name]) => name !== 'IMSI'));
            fields.classList.add('nq-l3-record');
            more.replaceWith(fields);
          } catch (error) {
            more.disabled = false;
            toast(error.message, 'error');
          }
        });
        content.append(more);
      }
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
      const campaignsChosen = Boolean(filters()?.campaign?.length || filters()?.nr_mode?.length);
      const scope = settings.failures === 'campaign' ? ' · of its campaign' : campaignsChosen ? ' · of the selected campaigns' : '';
      // Each count takes the call itself too: in its hotspot, cluster or run (of 2 calls or more), at its site, within the radius.
      const own = data.failures.find((item) => item.self);
      const groups = data.groups || {};
      const count = (test, itself) => number(shown.filter(test).length + (itself ? 1 : 0));
      const within = (item) => item.distance_km !== null && item.distance_km <= data.radius_km;
      // Every NQ call of its campaign comes, and the nearest ones of the other campaigns up to a maximum.
      const cut = settings.failures === 'selected' && data.failures_left_out
        ? ` · of the other campaigns, the ${number(data.failures_max)} nearest (${number(data.failures_left_out)} more left out)` : '';
      failuresCard.replaceChildren(cardHead('Non-Qualified Calls around',
        `${count((item) => item.same_hotspot, groups.hotspot >= 2)} in its hotspot · ${count((item) => item.same_cluster, groups.cluster >= 2)} in its cluster · `
        + `${count((item) => item.same_run, groups.run >= 2)} in its time window · ${count((item) => item.same_place, groups.site)} at its site · `
        + `${count(within, own && within(own))} within ${distanceText(data.radius_km)}${scope}${cut}`));
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
        const tags = [item.same_hotspot ? 'Hotspot' : '', item.same_cluster ? 'Cluster' : '', item.same_run ? 'Time Window' : '',
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
        // A hint of the Layer 3 - DT Logs points at its moment of the log: the point of that UE nearest in time.
        const logPoint = () => {
          if (!check.at || !shared.l3) return null;
          const candidates = shared.l3.points.filter((point) => (!check.at.ue || point.ue === check.at.ue) && point.lat !== null && Number.isFinite(point.ms));
          return candidates.reduce((best, point) => (!best || Math.abs(point.ms - check.at.ms) < Math.abs(best.ms - check.at.ms) ? point : best), null);
        };
        if (check.source === 'l3') entry.classList.add('is-l3');
        if (site) {
          entry.classList.add('is-linked');
          entry.tabIndex = 0;
          entry.title = 'Show the site on the map';
          const choose = () => { shared.select({kind: 'site', item: site}); panelView.centreOn(site.latitude, site.longitude); };
          entry.addEventListener('click', choose);
          entry.addEventListener('keydown', (event) => { if (event.key === 'Enter') choose(); });
        } else if (check.at) {
          entry.classList.add('is-linked');
          entry.tabIndex = 0;
          entry.title = 'Show its moment of the Layer 3 - DT Logs on the map';
          const choose = () => {
            const point = logPoint();
            if (!point) return;
            const layer = point.kind === 'event' || point.kind === 'l3' ? point.kind : `${point.kind}:rsrp`;
            shared.select({kind: 'l3', item: {layer: window.L3Layers?.LAYERS.some((item) => item.key === layer) ? layer : 'ran', point}});
            views().forEach((view) => view.centreOn(point.lat, point.lon));
          };
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
        driveCard.append(node('p', 'No test of its operator in the minutes around the call (the CDRs chosen may give no time).', 'nq-map-empty'));
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
        siteCard.append(node('p', health ? 'No call of the indexed CDRs started on its serving site.'
          : 'The call has no serving site: its cells are not in the Network Inventory of the networks that serve its operator.', 'nq-map-empty'));
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
      // (The other toolbar, above the larger map or below it, follows.)
      element.addEventListener('change', () => { onChange(element.value); renderToolbar(); });
      wrapper.append(element);
      return wrapper;
    };
    // The controls above the map, also above the larger map (``expandedToolbar``) while it is open.
    const renderToolbar = () => {
      for (const host of [toolbar, expandedToolbar].filter(Boolean)) host.replaceChildren(...toolbarControls());
    };
    const toolbarControls = () => {
      const data = shared.data;
      const radii = data?.radii_km || [0.5, 1, 2, 5, 10];
      // Per Group, a switch beside the colour: an outline of the shape of each NQ call for each group of the call it is of
      // (only when the call is of one).
      const perGroup = node('label', undefined, 'nq-map-control nq-map-check');
      perGroup.title = 'An outline around each NQ call for each group of the call it is of, in the colour of the group: its cluster innermost, then its time window and its hotspot (over the colour chosen; each group has its switch in From CDR)';
      const perGroupSwitch = node('span', undefined, 'nq-l3-switch');
      const perGroupBox = node('input');
      perGroupBox.type = 'checkbox';
      perGroupBox.setAttribute('role', 'switch');
      perGroupBox.checked = settings.perGroup;
      perGroupBox.addEventListener('change', () => { settings.perGroup = perGroupBox.checked; save(); redrawAll(); renderToolbar(); });
      perGroupSwitch.append(perGroupBox, node('span', undefined, 'nq-l3-switch-track'));
      perGroup.append(perGroupSwitch, node('span', 'Per Group'));
      perGroup.hidden = !hasGroups();
      // The layers of the map are switched in its cards (From CDR, From Logs).
      return [
        select('Radius', 'radius', radii.map((value) => [String(value), `${distanceText(value)}${value === data?.group_radius_km ? ' (groups)' : ''}`]),
          String(settings.radius_km), (value) => {
            settings.radius_km = Number(value); load();
          }, 'The area around where the call failed: its sites, Non-Qualified Calls and tests. A call opens with the radius that holds every NQ call of its hotspot and cluster, else with 1 km'),
        select('NQ calls from', 'failures', Object.entries(data?.failure_scopes || FAILURE_SCOPES), settings.failures, (value) => {
          settings.failures = value; save(); redrawAll(); renderFailures();
        }, 'The Non-Qualified Calls around that the map and its list show: those of the campaigns (and NR Modes) chosen in the filters of the page, every campaign while none is chosen, or those of the campaign and NR Mode of the call (the Diagnosis hints and the Decisions at its place count those of every campaign)'),
        select('Colour NQ calls by', 'failure-colour', Object.entries(FAILURE_COLOURS), settings.failureColour, (value) => {
          settings.failureColour = value; save(); redrawAll(); renderFailures();
        }, 'What the colour of the Non-Qualified Calls around tells, as on NQ Maps: the site of their CDR, their call type, the domain of their root cause (the one decided, else that of the DT Analyzer RCA), their campaign or their operator'),
        perGroup,
        select('Operators', 'operators', [['own', `${data?.call.operator || 'Its operator'} only`],
          ...(focusNames.size ? [['focus', 'Focus operators only']] : []), ['all', 'Every operator']], shared.operatorChoice(), (value) => {
          settings.operators = value; save(); redrawAll(); renderFailures();
        }, 'The samples and Non-Qualified Calls of the operator of the call, of the Focus operators of the Operator Maps'
          + `${data?.focus_labels?.length ? ` (${data.focus_labels.join(', ')})` : ''} or of every operator (its repetitions and hotspot always show)`)];
    };

    // -- loading the map of a call -------------------------------------------------------------------------------
    let request = null, l3Request = null, l3Key = '';
    // The logs of the NQ calls around the call (its groups and its area), when asked for in its layer panel: the same layers
    // as NQ Maps, faded below those of the call.
    let aroundRequest = null, aroundKey = '';
    const loadAround = async (key) => {
      if (!window.L3Layers?.state.around || !shared.l3 || aroundKey === key) return;
      const joinIds = [...new Set((shared.data?.failures || []).filter((failure) => failure.join_id && !failure.self).map((failure) => failure.join_id))];
      aroundRequest?.abort();
      shared.l3Around = null;
      if (!joinIds.length) { aroundKey = key; return; }
      const controllerAbort = new AbortController();
      aroundRequest = controllerAbort;
      try {
        const payload = await api('/api/non-qualified-calls/l3-maps', {method: 'POST', signal: controllerAbort.signal, body: JSON.stringify({
          join_ids: joinIds, exclude: shared.data.call.join_id || '', zoom: 18, layers: [...window.L3Layers.state.on]})});
        if (aroundRequest !== controllerAbort || key !== callKey) return;
        shared.l3Around = window.L3Layers.prepare(payload);
        aroundKey = key;
        redrawAll();
      } catch (error) {
        if (error.name !== 'AbortError') toast(error.message, 'error');
      }
    };
    window.L3Layers?.onChange(() => {
      if (!window.L3Layers.state.around) return;
      // A layer switched on needs its points: they are read again.
      aroundKey = '';
      if (callKey && shared.l3) loadAround(callKey);
    });
    // The Layer 3 - DT Logs of the call, when the workspace has a session of it (after its map, without delaying it).
    const loadL3 = async (key) => {
      if (!window.L3Layers || l3Key === key) return;
      l3Request?.abort();
      shared.l3 = null;
      shared.l3Hover = null;
      shared.l3Around = null;
      l3Key = '';
      aroundKey = '';
      window.L3Layers.refresh();
      if (!shared.data?.call?.l3_log) { redrawAll(); return; }
      const controllerAbort = new AbortController();
      l3Request = controllerAbort;
      try {
        const payload = await api(`/api/non-qualified-calls/calls/${encodeURIComponent(key)}/l3`, {signal: controllerAbort.signal});
        if (l3Request !== controllerAbort || key !== callKey) return;
        shared.l3 = window.L3Layers.prepare(payload);
        shared.l3Hover = null;
        l3Key = key;
        if (shared.l3) shared.l3.aroundCount = (shared.data?.failures || []).filter((failure) => failure.join_id && !failure.self).length;
        panelView.fit();
        expandedView?.fit();
        window.L3Layers.refresh();
        redrawAll();
        loadAround(key);
      } catch (error) {
        if (error.name !== 'AbortError') toast(error.message, 'error');
      }
    };
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
        // Selected campaigns: the campaigns and NR Modes of the filters of the page.
        if (settings.tests === 'selected') {
          const chosen = filters() || {};
          (chosen.campaign || []).forEach((value) => query.append('campaigns', value));
          (chosen.nr_mode || []).forEach((value) => query.append('nr_modes', value));
        }
        if (loadedKey === key) query.set('radius_km', String(settings.radius_km));
        const data = await api(`/api/non-qualified-calls/calls/${encodeURIComponent(key)}/map?${query}`, {signal: controllerAbort.signal});
        if (request !== controllerAbort || key !== callKey) return false;
        const sameCall = loadedKey === key;
        shared.data = data;
        // The Layer 3 - DT Logs colour their RSRP and SINR by the levels of the samples of the CDRs.
        window.L3Layers?.setClasses(data.classes);
        setRings(data.rings);
        groupFocus = groupFilter();
        focusNames = new Set((data.focus_operators || []).map((name) => String(name).trim().toLowerCase()).filter(Boolean));
        settings.radius_km = data.radius_km;
        // The samples are coloured by the RSRP of the radio of the call (NR in SA) until another measure is chosen.
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
        if (!sameCall) { shared.l3 = null; l3Key = ''; }
        renderToolbar();
        renderCards();
        panelView.setView(null);
        if (expandedView) expandedView.setView(null);
        redrawAll();
        loadL3(key);
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
      const timeline = node('div', undefined, 'nq-l3-timeline-host');
      // The controls of the map above it too.
      expandedToolbar = node('div', undefined, 'nq-map-toolbar nq-map-expand-toolbar');
      wrap.append(large, legendHost, floating);
      // (Outside what its images take, so that their buttons stand over the map.)
      expandContent.replaceChildren(expandedToolbar, wrap);
      renderToolbar();
      if (!expandDialog.open) expandDialog.showModal();
      expandedView = createView(large, shared, {expanded: true, legendHost});
      // Its signalling timeline over the bottom of the map, as the elevation profile.
      expandedView.overlay(timeline);
      expandedTimeline?.destroy();
      expandedTimeline = window.L3Layers?.createTimeline(timeline, () => shared.l3, timelineEvents) || null;
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
      expandedTimeline?.destroy();
      expandedTimeline = null;
      expandedToolbar = null;
      expandContent.replaceChildren();
      panelView.redraw();
    });

    const panelView = createView(card, shared, {onExpand: openExpanded, legendHost: mapLegend});
    // The signalling timeline of the Layer 3 - DT Logs of the call: hovering a message rings its point on the maps, a click
    // centres them on it and shows its values.
    const timelineEvents = {
      onHover: (point) => { shared.l3Hover = point; views().forEach((view) => view.redraw()); },
      // Its cursor dragged: the maps follow where the UE was (moved when it leaves them) and its signalling of that moment.
      onCursor: (moment) => views().forEach((view) => {
        if (moment?.cars.length) view.keepInView(moment.cars[0].lat, moment.cars[0].lon);
        view.redraw();
      }),
      onPick: (item) => {
        shared.select({kind: 'l3', item});
        if (item.point.lat !== null && item.point.lat !== undefined) views().forEach((view) => view.centreOn(item.point.lat, item.point.lon));
      },
    };
    window.L3Layers?.createTimeline(timelineHost, () => shared.l3, timelineEvents);
    renderToolbar();
    setWaiting('');

    // The larger map opened at once (the Map buttons of Failure Details and Call Details), while its map is prepared.
    const openLarge = async (key) => {
      if (!key) return;
      callKey = key;
      if (loadedKey !== key || !shared.data) {
        panelView.collapseCards();
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
        // Another call: the cards over its map open folded.
        panelView.collapseCards();
        load();
      },
      hide() {
        request?.abort();
        request = null;
        callKey = '';
        setWaiting('');
        if (expandDialog.open) expandDialog.close();
      },
      // The list of calls filtered by another group (or by none): the map paints the group that filters it again.
      refresh() {
        groupFocus = groupFilter();
        if (!shared.data) return;
        redrawAll();
        renderFailures();
      },
      title: () => {
        const call = shared.data?.call;
        return call ? ['Call Area Map', call.operator, call.join_id].filter(Boolean).join(' · ') : 'Call Area Map';
      },
      details: () => ({section: 'Call Area Map', context: {call_key: shared.data?.call.call_key || '', join_id: shared.data?.call.join_id || '',
        radius_km: String(shared.data?.radius_km ?? ''), tests: settings.tests, failures: settings.failures, failure_colour: settings.failureColour,
        measures: settings.measures.join(', ')}}),
    };
    return controller;
  }

  // -- NQ Maps: the Layer 3 - DT Logs of every NQ call of the filters, on the same map as that of a call ----------------
  // From the whole country (a grid of the average of the metric chosen, the NQ calls by their call type and
  // the route of each session) down to a single site or call: the events from the zoom of EVENT_ZOOM, the sites from that of
  // the sites, and the points of the layers on and the RSRP / SINR samples of the CDRs in the area shown from that of the
  // points, as on the map of a call (the server sends these zoom levels). ``filters`` gives the filters of the page; a
  // click on an NQ call opens it; a double-click opens the map larger, in ``expandDialog``.
  const AREA_SETTINGS_KEY = 'nq-l3-maps-settings';
  // Where the map of NQ Maps was left (its centre and zoom), shown again when the page opens.
  const AREA_VIEW_KEY = 'nq-maps-view';
  function mountArea({panel, expandDialog = null, api, toast, openCall, filters = () => ({}), campaignLabel = (value) => value,
    cdrTime = (value) => String(value || '').replace('T', ' ').slice(0, 19), number = (value) => Number(value).toLocaleString('en-GB')}) {
    let stored = {};
    try { stored = JSON.parse(localStorage.getItem(AREA_SETTINGS_KEY) || '{}') || {}; } catch (_error) { stored = {}; }
    // Besides the Layer 3 - DT Logs, as on the map of a call (without its groups): the NQ calls, the sites and the route of
    // each session (shown until switched off), the RSRP / SINR samples of the CDRs (hidden until switched on), what colours
    // the NQ calls and the operators shown.
    // (The route from the CDR, a sketch between its tests, is off until switched on: the GPS of the logs is the real one.)
    const settings = {layers: {cdr: stored.layers?.cdr !== false, failures: stored.layers?.failures !== false, sites: stored.layers?.sites !== false,
      path: false, paths: false, route: stored.v >= 2 && stored.layers?.route === true},
    measures: storedMeasures(stored),
    // By call type until another choice (the choices kept before Site came are left for it).
    failureColour: stored.v >= 3 && AREA_FAILURE_COLOURS[stored.failureColour] ? stored.failureColour : 'type',
    operators: stored.operators === 'focus' ? 'focus' : 'all', radius_km: 0, failures: 'every'};
    const save = () => {
      try {
        localStorage.setItem(AREA_SETTINGS_KEY, JSON.stringify({v: 3, layers: {cdr: settings.layers.cdr, failures: settings.layers.failures,
          sites: settings.layers.sites, route: settings.layers.route}, measures: settings.measures, failureColour: settings.failureColour,
        operators: settings.operators}));
      } catch (_error) { /* A private window keeps them for the page. */ }
    };
    // ``calls``: the NQ calls of the filters, read again only when the filters change.
    const shared = {data: null, settings, selection: null, l3: null, calls: null, zoom: 6};
    // The operators shown: every one, or the Focus operators of the Operator Maps (every one while the workspace has none).
    let focusNames = new Set(), focusLabels = [];
    shared.operatorChoice = () => (settings.operators === 'focus' && focusNames.size ? 'focus' : 'all');
    shared.operatorShown = (name) => shared.operatorChoice() === 'all' || focusNames.has(String(name || '').trim().toLowerCase());
    shared.showsFailure = (failure) => shared.operatorShown(failure.operator);
    // The colour of an NQ call (AREA_FAILURE_COLOURS) and the lines of the legend that explain it: only what they show.
    shared.failureColour = (failure) => failureColourBy(settings.failureColour, failure);
    shared.failureLegend = () => failureLegendBy(settings.failureColour,
      (shared.data?.failures || []).filter((failure) => failure.latitude !== null && shared.showsFailure(failure)), {campaignText});
    const status = node('p', '', 'nq-map-status nq-l3-maps-status');
    status.setAttribute('role', 'status');
    const toolbar = node('div', undefined, 'nq-map-toolbar nq-l3-maps-toolbar');
    const card = node('div', undefined, 'nq-l3-maps-card');
    const legendHost = node('div', undefined, 'nq-map-legend-host');
    const selected = node('section', undefined, 'nq-map-info nq-map-selected');
    selected.hidden = true;
    // The signalling timeline of the NQ call chosen on the map (its Layer 3 - DT Logs), as on the map of a call.
    const timelineHost = node('div', undefined, 'nq-l3-timeline-host');
    const wrap = node('div', undefined, 'nq-map-wrap');
    wrap.append(card, legendHost, timelineHost, selected);
    panel.replaceChildren(toolbar, status, wrap, node('p', expandDialog ? PANEL_HINT : HINT, 'form-note nq-map-hint'));
    const zooms = () => shared.l3?.zooms || {};
    let expandedView = null, expandedTimeline = null, floating = null;
    const views = () => [view, expandedView].filter(Boolean);
    const redrawAll = () => views().forEach((item) => { item.renderLegend(); item.redraw(); });

    // -- what the map says of each element ------------------------------------------------------------------------
    const siteName = (site) => `Site ${site.site_id} · ${site.network}${site.host_network && site.host_network !== site.network ? ` on ${site.host_network}` : ''}`;
    const campaignText = (campaign, mode) => {
      const text = campaignLabel(campaign);
      return mode && !new RegExp(`(^|[^A-Z])${mode}([^A-Z]|$)`, 'i').test(text) ? [text, mode].filter(Boolean).join(' · ') : text;
    };
    shared.describe = (kind, item) => {
      const data = shared.data;
      if (kind === 'failure') {
        return {title: `NQ call · ${item.operator}`, rows: [['Call type', KIND_LABELS[item.kind] || item.service_label], ['Operator', item.operator],
          ['Campaign', campaignText(item.campaign, item.nr_mode)], ['JOIN_ID', item.join_id], ['Result', item.result],
          ['Failure', [item.failure_classification, item.failure_category, item.failure_subcategory].filter(Boolean).join(' · ')],
          ['Test', item.test_name], ['Started', cdrTime(item.start_time)], ['Status', item.status],
          ['Root cause', [item.root_domain, item.root_category, item.root_cause].filter(Boolean).join(' · ')],
          ['DT Analyzer RCA', [item.dta_domain, item.dta_category, item.dta_cause].filter(Boolean).join(' · ')],
          ['Layer 3 - DT Logs', item.l3_log || 'None']]};
      }
      if (['l3', 'l3_cell'].includes(kind)) return window.L3Layers.describe(item, shared.l3);
      if (kind === 'l3_focus') return window.L3Layers.describe(item, shared.l3Focus);
      if (kind === 'l3_route') return window.L3Layers.describe({route: item}, shared.l3);
      if (kind === 'cell') {
        const site = data.sites.find((entry) => entry.cells.includes(item));
        return {title: `Cell ${item.name || item.identity}`, rows: [['Site', site ? siteName(site) : ''], ['Identity', item.identity],
          ['Technology', [item.technology, item.band].filter(Boolean).join(' ')], ['Channel', item.channel], ['PCI', item.pci],
          ['Azimuth', item.azimuth === null || item.azimuth === undefined ? 'Omni' : `${item.azimuth}°`],
          ['Beamwidth', item.beamwidth ? `${item.beamwidth}°` : ''], ['Height', item.height ? `${item.height} m` : ''], ['State', item.state], ['Vendor', item.vendor]]};
      }
      if (kind === 'site') {
        const technologies = [...new Set(item.cells.map((cell) => `${cell.technology} ${cell.band}`.trim()))].join(', ');
        return {title: siteName(item), rows: [['Vendor', item.vendors.join(', ')], ['Cells', `${item.cells.length} · ${technologies}`],
          ['Type', item.site_type], ['eMOCN', item.emocn], ['City', item.city]]};
      }
      if (kind === 'test') {
        const operator = data.tests.operators[item[COLUMN.operator]] || '';
        const cdr = data.tests.cdrs?.[item[COLUMN.cdr]];
        return {title: `${SERVICE_LABELS[data.tests.kinds[item[COLUMN.kind]]] || 'Test'} test · ${operator}`, rows: [
          ['Campaign', cdr ? campaignText(cdr.campaign, cdr.nr_mode) : ''],
          ['CDR', cdr ? [SERVICE_LABELS[cdr.kind] || cdr.kind, cdr.stage ? cdr.stage[0].toUpperCase() + cdr.stage.slice(1) : ''].filter(Boolean).join(' · ') : ''],
          ['Test', data.tests.test_names[item[COLUMN.test]]], ['Started', cdrTime(item[COLUMN.start])], ['Result', item[COLUMN.failed] ? 'Not completed' : 'Completed'],
          ['LTE RSRP', dbText(item[COLUMN.lte_rsrp], 'dBm')], ['LTE SINR', dbText(item[COLUMN.lte_sinr], 'dB')],
          ['NR RSRP', dbText(item[COLUMN.nr_rsrp], 'dBm')], ['NR SINR', dbText(item[COLUMN.nr_sinr], 'dB')]]};
      }
      return {title: '', rows: []};
    };
    const facts = (rows) => {
      const list = node('dl', undefined, 'nq-map-facts');
      rows.filter(([, value]) => value !== '' && value !== null && value !== undefined).forEach(([name, value]) => list.append(node('dt', name), node('dd', String(value))));
      return list;
    };
    // The element chosen: below the map, or floating over the larger map while it is open.
    const renderSelected = () => {
      const choice = shared.selection;
      const target = expandDialog?.open && floating ? floating : selected;
      [selected, floating].filter(Boolean).forEach((box) => { box.hidden = true; box.replaceChildren(); });
      if (!choice) return;
      const {title, rows} = shared.describe(choice.kind, choice.item);
      const content = node('div', undefined, 'nq-map-selected-content');
      const head = node('header');
      const close = node('button', '×', 'nq-map-info-close');
      close.type = 'button';
      close.title = 'Clear the selection';
      close.setAttribute('aria-label', 'Clear the selection');
      close.addEventListener('click', () => shared.select(null));
      head.append(node('h4', title), close);
      content.append(head, facts(rows));
      const sameJoin = (joinId) => (shared.calls || []).find((call) => String(call.join_id).toLowerCase() === String(joinId || '').toLowerCase())?.call_key;
      const callKey = choice.kind === 'failure' ? choice.item.call_key
        : choice.kind === 'l3' ? sameJoin(shared.l3?.sessions?.[choice.item.point.ue]?.join_id)
          : choice.kind === 'l3_route' ? sameJoin(choice.item.session?.join_id) : '';
      if (callKey) {
        const open = node('button', 'Open this call', 'nq-secondary-action');
        open.type = 'button';
        open.addEventListener('click', () => { if (expandDialog?.open) expandDialog.close(); openCall(callKey); });
        content.append(open);
      }
      target.replaceChildren(content);
      target.hidden = false;
    };
    // The NQ call of the element chosen (an NQ call, a point or the route of its log): its Layer 3 - DT Logs read for its
    // signalling timeline below the map.
    let focusKey = '', focusRequest = null, focusCall = null;
    const callOf = (choice) => {
      if (!choice) return null;
      const byJoin = (joinId) => (shared.calls || []).find((call) => String(call.join_id).toLowerCase() === String(joinId || '').toLowerCase());
      if (choice.kind === 'failure') return choice.item;
      if (choice.kind === 'l3') return byJoin(shared.l3?.sessions?.[choice.item.point.ue]?.join_id);
      if (choice.kind === 'l3_route') return byJoin(choice.item.session?.join_id);
      return null;
    };
    const loadFocus = async (call) => {
      if (!call?.l3_log || call.call_key === focusKey) return;
      focusKey = call.call_key;
      focusRequest?.abort();
      const controllerAbort = new AbortController();
      focusRequest = controllerAbort;
      try {
        const payload = await api(`/api/non-qualified-calls/calls/${encodeURIComponent(call.call_key)}/l3`, {signal: controllerAbort.signal});
        if (focusRequest !== controllerAbort) return;
        focusCall = call;
        shared.l3Focus = window.L3Layers.prepare(payload);
        window.L3Layers.refresh();
        views().forEach((item) => item.redraw());
      } catch (error) {
        if (error.name === 'AbortError') return;
        focusKey = '';
        toast(error.message, 'error');
      }
    };
    shared.select = (choice) => {
      shared.selection = choice;
      renderSelected();
      loadFocus(callOf(choice));
      // The timeline says what it needs while no call with a log is chosen.
      if (!shared.l3Focus) window.L3Layers?.refresh();
      views().forEach((item) => item.redraw());
    };
    const timelineEvents = {
      onHover: (point) => { shared.l3Hover = point; views().forEach((item) => item.redraw()); },
      onCursor: (moment) => views().forEach((item) => {
        if (moment?.cars.length) item.keepInView(moment.cars[0].lat, moment.cars[0].lon);
        item.redraw();
      }),
      onPick: (item) => {
        shared.selection = {kind: 'l3_focus', item};
        renderSelected();
        if (item.point.lat !== null && item.point.lat !== undefined) views().forEach((entry) => entry.centreOn(item.point.lat, item.point.lon));
      },
      caption: () => (focusCall ? [KIND_LABELS[focusCall.kind] || focusCall.service_label, focusCall.operator, focusCall.join_id].filter(Boolean).join(' · ') : ''),
      // Until a call with a log is chosen: how to choose one.
      empty: () => (callOf(shared.selection) && !callOf(shared.selection).l3_log
        ? 'The NQ call chosen has no Layer 3 - DT Logs (a hollow diamond): choose one with a log to see its signalling timeline here.'
        : 'Choose an NQ call with Layer 3 - DT Logs (a click on it, on a point of its log or on its route) to see its signalling timeline here.'),
    };
    window.L3Layers?.createTimeline(timelineHost, () => shared.l3Focus || null, timelineEvents);

    // -- the RSRP / SINR samples of the CDRs and the layers above the map -----------------------------------------------
    // A layer of From CDR (or the whole card) and a measure of its samples switched on or off: the area is read again when
    // it needs its sites or tests.
    shared.cdrLayers = ['failures', 'sites', 'route'];
    const needs = () => JSON.stringify([shownLayers(settings).sites !== false, shownMeasures(settings).length > 0 || shownLayers(settings).route !== false]);
    shared.setLayer = (key, on) => {
      const before = needs();
      settings.layers[key] = on;
      save();
      redrawAll();
      if (needs() !== before) reload();
    };
    shared.setMeasure = (key, on) => {
      const before = needs();
      settings.measures = Object.keys(METRICS).filter((name) => (name === key ? on : settings.measures.includes(name)));
      save();
      redrawAll();
      if (needs() !== before) reload();
    };
    shared.samplesNote = () => {
      const tests = shared.data?.tests;
      if (shared.zoom < (zooms().tests || 13)) return `From zoom ${zooms().tests || 13}: the tests of the CDRs of the campaigns of the filters in the area shown.`;
      if (!shownMeasures(settings).length || !tests) return 'The tests of the CDRs of the campaigns of the filters in the area shown.';
      return tests.truncated ? `An even sample of ${number(tests.rows.length)} of the ${number(tests.total)} tests of the area shown.`
        : `${number(tests.rows.length)} tests of the CDRs of the campaigns of the filters in the area shown.`;
    };
    const select = (labelText, options, value, onChange, title) => {
      const wrapper = node('label', undefined, 'nq-map-control');
      wrapper.append(node('span', labelText));
      const element = node('select');
      for (const [optionValue, optionText] of options) {
        const option = node('option', optionText);
        option.value = optionValue;
        element.append(option);
      }
      element.value = value;
      wrapper.title = title;
      // (The other toolbar, above the larger map or below it, follows.)
      element.addEventListener('change', () => { onChange(element.value); renderToolbar(); });
      wrapper.append(element);
      return wrapper;
    };
    // The layers of the map are switched in its cards (From CDR, From Logs), as on the map of a call; its controls show
    // above the larger map too (``expandedToolbar``) while it is open.
    let expandedToolbar = null;
    const renderToolbar = () => {
      for (const host of [toolbar, expandedToolbar].filter(Boolean)) host.replaceChildren(...toolbarControls());
    };
    const toolbarControls = () => [
        select('Colour NQ calls by', Object.entries(AREA_FAILURE_COLOURS), settings.failureColour, (value) => {
          settings.failureColour = value; save(); redrawAll();
        }, 'What the colour of the NQ calls tells, as on the map of a call: their call type, the domain of their root cause (the one decided, else that of the DT Analyzer RCA), their campaign, their operator or the site of their CDR'),
        select('Operators', [...(focusNames.size ? [['focus', 'Focus operators only']] : []), ['all', 'Every operator']], shared.operatorChoice(), (value) => {
          settings.operators = value; save(); redrawAll();
        }, `The NQ calls and RSRP / SINR samples of every operator, or of the Focus operators of the Operator Maps${focusLabels.length ? ` (${focusLabels.join(', ')})` : ''}`)];

    // -- reading the area shown -------------------------------------------------------------------------------------
    let request = null, loadedKey = '', pending = 0, lastView = null, fitted = false;
    const keyOf = (info) => {
      if (!info) return '';
      // Its zoom level, the area shown (in steps of a quarter of it) and what it shows.
      const step = Math.max(info.bbox[2] - info.bbox[0], info.bbox[3] - info.bbox[1]) / 4 || 1;
      return JSON.stringify([Math.floor(info.zoom), info.bbox.map((value) => Math.round(value / step)).join(','), window.L3Layers.state.grid,
        [...window.L3Layers.state.on].sort(), window.L3Layers.state.master, needs()]);
    };
    const statusText = (payload) => {
      if (!payload.calls_count) return 'No NQ call matches the filters.';
      const text = `${number(payload.calls_count)} NQ calls of the filters · ${number(payload.calls_with_log)} with Layer 3 - DT Logs (${number(payload.sessions)} sessions)`;
      if (!payload.calls_with_log) return `${text} · Import them in Workspace (Layer 3 - DT Logs).`;
      const sites = payload.sites ? ` · ${number(payload.sites.sites.length)} sites${payload.sites.truncated ? ' (the nearest to the centre)' : ''}` : '';
      return text + sites + (payload.mode === 'grid' ? ` · zoom in: events from zoom ${payload.zooms.events}, sites from ${payload.zooms.sites}, `
        + `points and RSRP / SINR samples from ${payload.zooms.grid}` : '');
    };
    const load = async (info, {force = false} = {}) => {
      const key = keyOf(info);
      if (!force && key === loadedKey) return;
      loadedKey = key;
      request?.abort();
      const controllerAbort = new AbortController();
      request = controllerAbort;
      status.textContent = 'Reading the Layer 3 - DT Logs of the NQ calls…';
      try {
        const body = {filters: filters(), zoom: info ? info.zoom : 6, layers: [...window.L3Layers.state.on], grid: window.L3Layers.state.grid,
          // The routes of the logs (their layer Route), the sites and the tests (for the samples and the route from the CDR).
          route: window.L3Layers.state.master && window.L3Layers.state.on.has('way'), sites: shownLayers(settings).sites !== false,
          tests: shownMeasures(settings).length > 0 || shownLayers(settings).route !== false,
          with_calls: !shared.calls, ...(info ? {bbox: info.bbox} : {})};
        const payload = await api('/api/non-qualified-calls/l3-maps', {method: 'POST', body: JSON.stringify(body), signal: controllerAbort.signal});
        if (request !== controllerAbort) return;
        if (payload.calls) shared.calls = payload.calls;
        payload.calls = shared.calls || [];
        if (!shared.data) {
          shared.data = {area: true, centre: [54.5, -2.5], radius_km: 0, basemap: payload.basemap, call: {}, groups: {},
            tests: {operators: [], rows: [], total: 0}, trace: [], sites: [], failures: [], rings: [], drive: {route: []}, classes: {}, notes: [],
            diagnosis: []};
        }
        shared.zoom = body.zoom;
        if (payload.calls !== shared.data.calls) {
          shared.data.calls = payload.calls;
          shared.data.failures = payload.calls.map((call) => ({...call, self: false, same_operator: false, same_place: false}));
        }
        const focus = new Set((payload.focus_operators || []).map((name) => String(name).trim().toLowerCase()).filter(Boolean));
        if (focus.size !== focusNames.size || [...focus].some((name) => !focusNames.has(name))) {
          focusNames = focus;
          focusLabels = payload.focus_labels || [];
          renderToolbar();
        }
        shared.data.sites = payload.sites?.sites || [];
        shared.data.tests = payload.tests || {operators: [], kinds: [], test_names: [], cdrs: [], rows: [], total: 0};
        shared.data.classes = payload.classes || {};
        window.L3Layers?.setClasses(shared.data.classes);
        shared.l3 = window.L3Layers.prepare(payload);
        status.textContent = statusText(payload);
        if (expandDialog?.open) expandDialog.querySelector('[data-nq-map-expand-meta]').textContent = [status.textContent, HINT].join(' · ');
        if (!fitted) {
          // The place the map was left, else the whole extent of the logs.
          let kept = null;
          try { kept = JSON.parse(localStorage.getItem(AREA_VIEW_KEY) || 'null'); } catch (_error) { kept = null; }
          fitted = Boolean(kept || shared.l3?.extent);
          if (kept && [kept.x, kept.y, kept.resolution].every(Number.isFinite)) view.setView(kept);
          else if (shared.l3?.extent) view.fit();
        }
        window.L3Layers.refresh();
        redrawAll();
      } catch (error) {
        if (error.name === 'AbortError') return;
        loadedKey = '';
        status.textContent = error.message;
        toast(error.message, 'error');
      }
    };
    const reload = () => { if (shared.data && lastView) load(lastView, {force: true}); };
    // The view that reads the area: the larger one while it is open.
    const viewChanged = (info) => {
      lastView = info;
      clearTimeout(pending);
      pending = setTimeout(() => {
        if (!shared.data) return;
        load(info);
        if (!fitted) return;
        try { localStorage.setItem(AREA_VIEW_KEY, JSON.stringify((expandedView || view).view())); } catch (_error) { /* A private window keeps it for the page. */ }
      }, 350);
    };

    // -- the larger map (a double-click on the map): the whole width of the window but 2 % on each side ---------------
    const expandContent = expandDialog?.querySelector('[data-nq-map-expand-content]');
    const openExpanded = () => {
      if (!expandDialog || !shared.data) return;
      expandDialog.querySelector('[data-nq-map-expand-title]').textContent = 'NQ Maps';
      expandDialog.querySelector('[data-nq-map-expand-meta]').textContent = [status.textContent, HINT].filter(Boolean).join(' · ');
      expandedView?.destroy();
      const large = node('div', undefined, 'nq-map-expand-card');
      const largeLegend = node('div', undefined, 'nq-map-legend-host');
      floating = node('aside', undefined, 'nq-map-info nq-map-selected nq-map-selected-float');
      floating.hidden = true;
      const largeTimeline = node('div', undefined, 'nq-l3-timeline-host');
      const largeWrap = node('div', undefined, 'nq-map-expand-wrap');
      expandedToolbar = node('div', undefined, 'nq-map-toolbar nq-map-expand-toolbar');
      largeWrap.append(large, largeLegend, floating);
      // (Outside what its images take, so that their buttons stand over the map.)
      expandContent.replaceChildren(expandedToolbar, largeWrap);
      renderToolbar();
      if (!expandDialog.open) expandDialog.showModal();
      expandedView = createView(large, shared, {expanded: true, legendHost: largeLegend, onViewChange: viewChanged});
      expandedView.overlay(largeTimeline);
      expandedTimeline?.destroy();
      expandedTimeline = window.L3Layers?.createTimeline(largeTimeline, () => shared.l3Focus || null, timelineEvents) || null;
      expandedView.setView(view.view());
      expandedView.renderLegend();
      renderSelected();
    };
    if (expandDialog) {
      expandDialog.querySelector('[data-nq-map-expand-close]').addEventListener('click', () => expandDialog.close());
      expandDialog.addEventListener('click', (event) => { if (event.target === expandDialog) expandDialog.close(); });
      expandDialog.addEventListener('close', () => {
        if (expandDialog.open) return;
        // The map in the page goes where the larger one was left.
        const where = expandedView?.view();
        expandedView?.destroy();
        expandedView = null;
        expandedTimeline?.destroy();
        expandedTimeline = null;
        expandedToolbar = null;
        floating = null;
        expandContent.replaceChildren();
        if (where) view.setView(where); else view.redraw();
        renderSelected();
      });
    }
    const view = createView(card, shared, {legendHost, onExpand: expandDialog ? openExpanded : null,
      onViewChange: (info) => { if (!expandedView) viewChanged(info); }});
    window.L3Layers?.onChange(() => { if (shared.data && lastView) load(lastView); });
    renderToolbar();
    return {
      // The NQ calls of the filters read again (a change of the filters): the map keeps its area.
      load: () => { loadedKey = ''; shared.calls = null; load(lastView, {force: true}); },
    };
  }

  window.NqCallMap = {mount, mountArea};
})();
