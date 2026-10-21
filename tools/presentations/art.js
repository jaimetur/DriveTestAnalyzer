// Illustrations of the deck, drawn as SVG and rasterised with sharp.
const sharp = require('sharp');

// A deterministic pseudo-random generator, so every build draws the same art.
function rng(seed) {
  let s = seed >>> 0;
  return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
}

// Quality classes of a drive-test sample (Ericsson brand accents, deep to light).
const QUALITY = ['0C9B5B', '0FC373', 'FAD22D', 'FF8C0A', 'FF3232'];

// A smooth drive route through the points, sampled every `step` pixels.
function samples(points, step) {
  const out = [];
  for (let i = 0; i < points.length - 1; i += 1) {
    const [x0, y0] = points[i]; const [x1, y1] = points[i + 1];
    const [xm, ym] = points[Math.max(0, i - 1)]; const [xn, yn] = points[Math.min(points.length - 1, i + 2)];
    const length = Math.hypot(x1 - x0, y1 - y0);
    for (let d = 0; d < length; d += step) {
      const t = d / length; const t2 = t * t; const t3 = t2 * t;
      // Catmull-Rom between the neighbours.
      const x = 0.5 * ((2 * x0) + (-xm + x1) * t + (2 * xm - 5 * x0 + 4 * x1 - xn) * t2 + (-xm + 3 * x0 - 3 * x1 + xn) * t3);
      const y = 0.5 * ((2 * y0) + (-ym + y1) * t + (2 * ym - 5 * y0 + 4 * y1 - yn) * t2 + (-ym + 3 * y0 - 3 * y1 + yn) * t3);
      out.push([x, y]);
    }
  }
  return out;
}

// The cover: radio waves from a site in the corner and a drive route coloured by quality.
async function coverArt(file) {
  const W = 1406; const H = 1500; const random = rng(7);
  const arcs = [];
  for (let r = 260; r <= 1900; r += 120) {
    const opacity = Math.max(0.05, 0.42 - r / 5200);
    arcs.push(`<circle cx="1330" cy="1360" r="${r}" fill="none" stroke="url(#wave)" stroke-width="${r < 700 ? 3 : 2}" opacity="${opacity.toFixed(3)}"/>`);
  }
  // (It ends left of the Ericsson logo, at the top right of the cover.)
  const route = samples([[60, 1180], [300, 1010], [430, 1120], [640, 900], [610, 690], [820, 560], [1020, 640], [1150, 470], [1010, 300], [830, 170]], 30);
  // Better close to the site of the waves, worse far from it.
  const dots = route.map(([x, y]) => {
    const distance = Math.hypot(x - 1330, y - 1360);
    const quality = Math.max(0, Math.min(4, Math.floor((distance - 420) / 210 + (random() - 0.5) * 1.4)));
    const radius = 9 + random() * 4;
    return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${radius.toFixed(1)}" fill="#${QUALITY[quality]}" opacity="0.92"/>`;
  });
  const trail = route.map(([x, y], index) => `${index ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
    <defs>
      <linearGradient id="wave" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="#0082F0"/><stop offset="1" stop-color="#AF78D2"/></linearGradient>
      <radialGradient id="glow" cx="0.95" cy="0.9" r="0.8"><stop offset="0" stop-color="#0068BF" stop-opacity="0.55"/><stop offset="1" stop-color="#000000" stop-opacity="0"/></radialGradient>
    </defs>
    <rect width="${W}" height="${H}" fill="url(#glow)"/>
    ${arcs.join('\n')}
    <path d="${trail}" fill="none" stroke="#FFFFFF" stroke-opacity="0.16" stroke-width="22" stroke-linecap="round" stroke-linejoin="round"/>
    ${dots.join('\n')}
    <g transform="translate(1330 1360)"><circle r="34" fill="#0082F0"/><circle r="14" fill="#FFFFFF"/></g>
  </svg>`;
  await sharp(Buffer.from(svg)).png().toFile(file);
}

// Network Insights: a coverage map of hexagons along the drive routes, coloured by RSRP around the sites.
async function coverageMap(file) {
  const W = 1120; const H = 980; const random = rng(11);
  const sites = [[230, 260], [610, 180], [900, 360], [420, 640], [820, 760], [180, 820]];
  const field = (x, y) => sites.reduce((best, [sx, sy]) => Math.max(best, Math.exp(-((x - sx) ** 2 + (y - sy) ** 2) / (2 * 135 ** 2))), 0);
  const roads = [
    [[20, 300], [260, 330], [480, 250], [700, 300], [960, 240], [1100, 300]],
    [[120, 960], [210, 700], [380, 560], [540, 420], [640, 180], [700, 20]],
    [[300, 960], [520, 820], [760, 700], [980, 640], [1100, 540]],
    [[20, 560], [260, 600], [430, 500], [600, 560], [820, 470], [1000, 420]],
    [[860, 960], [900, 760], [880, 560], [940, 360], [1060, 120]],
  ];
  const size = 15; const hexes = new Map();
  const key = (x, y) => { const q = Math.round(x / (size * 1.5)); const r = Math.round((y - (q % 2 ? size * 0.866 : 0)) / (size * 1.732)); return `${q},${r}`; };
  for (const road of roads) {
    for (const [x, y] of samples(road, 8)) {
      for (const [dx, dy] of [[0, 0], [10, 6], [-8, -10]]) {
        const k = key(x + dx, y + dy);
        if (!hexes.has(k)) hexes.set(k, k.split(',').map(Number));
      }
    }
  }
  const polygons = [...hexes.values()].map(([q, r]) => {
    const cx = q * size * 1.5; const cy = r * size * 1.732 + (q % 2 ? size * 0.866 : 0);
    const value = field(cx, cy) + (random() - 0.5) * 0.18;
    const level = value > 0.75 ? 0 : value > 0.52 ? 1 : value > 0.33 ? 2 : value > 0.17 ? 3 : 4;
    const points = [0, 60, 120, 180, 240, 300].map((angle) => {
      const radians = (Math.PI / 180) * angle;
      return `${(cx + (size - 1.2) * Math.cos(radians)).toFixed(1)},${(cy + (size - 1.2) * Math.sin(radians)).toFixed(1)}`;
    }).join(' ');
    return `<polygon points="${points}" fill="#${QUALITY[level]}" opacity="0.95"/>`;
  });
  const blocks = [];
  for (let i = 0; i < 26; i += 1) {
    const x = random() * W; const y = random() * H;
    blocks.push(`<rect x="${x.toFixed(0)}" y="${y.toFixed(0)}" width="${(40 + random() * 110).toFixed(0)}" height="${(30 + random() * 90).toFixed(0)}" rx="6" fill="#E0E0E0" opacity="0.55"/>`);
  }
  const towers = sites.map(([x, y]) => `<g transform="translate(${x} ${y})"><circle r="22" fill="#FFFFFF" opacity="0.9"/><path d="M0,-13 L11,9 L-11,9 Z" fill="#242424"/></g>`);
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
    <rect width="${W}" height="${H}" fill="#F2F2F2"/>
    ${blocks.join('\n')}
    ${polygons.join('\n')}
    ${towers.join('\n')}
  </svg>`;
  await sharp(Buffer.from(svg)).png().toFile(file);
}

// The roadmap on a light slide: a drive-test road through the milestones (``points`` in inches of a 13.33 × 7.5 inch
// slide), with drive-test samples along its edges and a finish flag at its end, over a soft blue glow. ``scale`` narrows
// the road (the small roadmap of the one-slider, without the glow and the flag).
async function roadmapRoad(file, points, { scale = 1, glow = true, flag = true } = {}) {
  const ppi = 150; const W = Math.round(13.333 * ppi); const H = Math.round(7.5 * ppi); const random = rng(5);
  const route = samples(points.map(([x, y]) => [x * ppi, y * ppi]), 6);
  const trail = route.map(([x, y], index) => `${index ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  // Samples on both edges of the road, better at its start (delivered) and mixed further on.
  const dots = [];
  for (let index = 0; index < route.length - 1; index += 7) {
    const [x, y] = route[index]; const [nx, ny] = route[index + 1];
    const length = Math.hypot(nx - x, ny - y) || 1;
    const ox = -(ny - y) / length; const oy = (nx - x) / length;
    for (const side of [-1, 1]) {
      const progress = index / route.length;
      const quality = Math.max(0, Math.min(4, Math.floor(random() * (1 + progress * 3.2))));
      dots.push(`<circle cx="${(x + side * ox * 40 * scale).toFixed(1)}" cy="${(y + side * oy * 40 * scale).toFixed(1)}" r="${((5 + random() * 3) * Math.max(scale, 0.6)).toFixed(1)}" fill="#${QUALITY[quality]}" opacity="0.9"/>`);
    }
  }
  const [fx, fy] = route[route.length - 1];
  const checks = [];
  for (let row = 0; row < 3; row += 1) {
    for (let column = 0; column < 4; column += 1) {
      if ((row + column) % 2 === 0) checks.push(`<rect x="${column * 14}" y="${row * 14}" width="14" height="14" fill="#242424"/>`);
    }
  }
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
    <defs>
      <radialGradient id="glowA" cx="0.85" cy="0.15" r="0.55"><stop offset="0" stop-color="#0082F0" stop-opacity="0.16"/><stop offset="1" stop-color="#0082F0" stop-opacity="0"/></radialGradient>
      <radialGradient id="glowB" cx="0.1" cy="0.95" r="0.5"><stop offset="0" stop-color="#AF78D2" stop-opacity="0.13"/><stop offset="1" stop-color="#AF78D2" stop-opacity="0"/></radialGradient>
    </defs>
    ${glow ? `<rect width="${W}" height="${H}" fill="url(#glowA)"/><rect width="${W}" height="${H}" fill="url(#glowB)"/>` : ''}
    <path d="${trail}" fill="none" stroke="#1A1A1A" stroke-width="${62 * scale}" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="${trail}" fill="none" stroke="#3B3B3B" stroke-width="${52 * scale}" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="${trail}" fill="none" stroke="#FFFFFF" stroke-width="${5 * Math.max(scale, 0.5)}" stroke-dasharray="${26 * scale} ${22 * scale}" stroke-linecap="round" opacity="0.9"/>
    ${dots.join('\n')}
    ${flag ? `<g transform="translate(${(fx - 6).toFixed(1)} ${(fy - 118).toFixed(1)})">
      <rect x="0" y="0" width="6" height="120" rx="3" fill="#242424"/>
      <g transform="translate(6 2)"><rect width="56" height="42" fill="#FFFFFF" stroke="#242424" stroke-width="2"/>${checks.join('')}</g>
    </g>` : ''}
  </svg>`;
  await sharp(Buffer.from(svg)).png().toFile(file);
}

// Points lost, from few (light yellow) to many (deep red), as the Points Lost Map of Scoring colours its areas.
const LOSS = ['FFF3BF', 'FFD966', 'FFA94D', 'FF6B3D', 'E03131', 'A61E1E'];

// Whether the point is inside the polygon (ray casting).
function inside([x, y], polygon) {
  let result = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i, i += 1) {
    const [xi, yi] = polygon[i]; const [xj, yj] = polygon[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) result = !result;
  }
  return result;
}

// Scoring: the Points Lost Map of an operator, its areas coloured by the points lost there, a Connecting Roads route
// with its stretches and the area that loses most ringed.
async function pointsLostMap(file) {
  const W = 920; const H = 1020; const random = rng(23);
  const outline = [[380, 40], [520, 70], [560, 190], [500, 300], [600, 380], [700, 470], [760, 600], [820, 720], [860, 860],
    [760, 950], [560, 975], [380, 960], [230, 990], [150, 900], [260, 820], [210, 700], [120, 600], [200, 500], [300, 420],
    [230, 300], [280, 170], [380, 40]];
  const land = samples(outline, 6);
  const hotspots = [[660, 820, 1], [330, 610, 0.8], [520, 420, 0.55], [300, 900, 0.45]];
  const field = (x, y) => hotspots.reduce((sum, [hx, hy, weight]) => sum + weight * Math.exp(-((x - hx) ** 2 + (y - hy) ** 2) / (2 * 120 ** 2)), 0);
  const size = 30; const areas = [];
  for (let q = 0; q * size * 1.5 < W + size; q += 1) {
    for (let r = 0; r * size * 1.732 < H + size; r += 1) {
      const cx = q * size * 1.5 + (random() - 0.5) * 6; const cy = r * size * 1.732 + (q % 2 ? size * 0.866 : 0) + (random() - 0.5) * 6;
      if (!inside([cx, cy], land)) continue;
      // Areas without tests stay grey.
      const tested = field(cx, cy) > 0.05 || random() > 0.45;
      const value = field(cx, cy) + (random() - 0.5) * 0.22;
      const level = Math.max(0, Math.min(LOSS.length - 1, Math.floor(value * 5.2)));
      const points = [0, 60, 120, 180, 240, 300].map((angle) => {
        const radians = (Math.PI / 180) * angle;
        return `${(cx + size * Math.cos(radians)).toFixed(1)},${(cy + size * Math.sin(radians)).toFixed(1)}`;
      }).join(' ');
      areas.push(`<polygon points="${points}" fill="#${tested ? LOSS[level] : 'E9E9E9'}" stroke="#FFFFFF" stroke-width="2.5"/>`);
    }
  }
  // A Connecting Roads route, its stretches coloured by the points they lose.
  const route = samples([[250, 180], [330, 330], [300, 480], [380, 600], [520, 690], [640, 800], [720, 900]], 8);
  const trail = route.map(([x, y], index) => `${index ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const stretches = [];
  for (let index = 6; index < route.length; index += 12) {
    const [x, y] = route[index];
    const level = Math.max(0, Math.min(LOSS.length - 1, Math.floor(field(x, y) * 5.6)));
    stretches.push(`<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="13" fill="#${LOSS[level]}" stroke="#242424" stroke-width="3"/>`);
  }
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
    <rect width="${W}" height="${H}" fill="#F7FAFD"/>
    <path d="${land.map(([x, y], index) => `${index ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ')} Z" fill="#E9E9E9"/>
    ${areas.join('\n')}
    <path d="${trail}" fill="none" stroke="#242424" stroke-width="9" stroke-linecap="round" stroke-linejoin="round" opacity="0.85"/>
    ${stretches.join('\n')}
    <circle cx="660" cy="820" r="74" fill="none" stroke="#0068BF" stroke-width="7"/>
    <circle cx="660" cy="820" r="92" fill="none" stroke="#0068BF" stroke-width="2.5" stroke-dasharray="10 9" opacity="0.7"/>
  </svg>`;
  await sharp(Buffer.from(svg)).png().toFile(file);
}

// CDR Analysis: the CDF curves of a KPI per operator, over a light grid of quarters (the axes are text of the slide).
async function cdfCurves(file, series) {
  const W = 1200; const H = 760;
  const grid = [0, 0.25, 0.5, 0.75, 1].map((share) => `<line x1="0" x2="${W}" y1="${(H - share * H).toFixed(1)}" y2="${(H - share * H).toFixed(1)}" stroke="#E0E0E0" stroke-width="2"/>`);
  const columns = [0.2, 0.4, 0.6, 0.8].map((share) => `<line y1="0" y2="${H}" x1="${share * W}" x2="${share * W}" stroke="#EDEDED" stroke-width="2"/>`);
  const curves = series.map(({ color, median, spread, width = 7 }) => {
    const points = [];
    for (let step = 0; step <= 200; step += 1) {
      const x = (step / 200) * W; const value = 1 / (1 + Math.exp(-((step / 200) * 250 - median) / spread));
      points.push(`${step ? 'L' : 'M'}${x.toFixed(1)},${(H - value * (H - 8) - 4).toFixed(1)}`);
    }
    return `<path d="${points.join(' ')}" fill="none" stroke="#${color}" stroke-width="${width}" stroke-linecap="round" stroke-linejoin="round"/>`;
  });
  // The median of each operator: where its curve crosses 50 %.
  const medians = series.map(({ color, median }) => `<circle cx="${((median / 250) * W).toFixed(1)}" cy="${(H / 2).toFixed(1)}" r="11" fill="#FFFFFF" stroke="#${color}" stroke-width="6"/>`);
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
    <rect width="${W}" height="${H}" fill="#FFFFFF"/>
    ${columns.join('\n')}${grid.join('\n')}
    <line x1="0" x2="${W}" y1="${H / 2}" y2="${H / 2}" stroke="#A0A0A0" stroke-width="2.5" stroke-dasharray="12 10"/>
    ${curves.join('\n')}${medians.join('\n')}
  </svg>`;
  await sharp(Buffer.from(svg)).png().toFile(file);
}

module.exports = { coverArt, coverageMap, roadmapRoad, pointsLostMap, cdfCurves, LOSS };
