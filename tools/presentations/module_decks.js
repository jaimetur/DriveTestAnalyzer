// The presentations of the main modules of DriveTest Analyzer shown in the Help, in the design of the DT Analyzer RCA
// deck: each module has a folder here (workspace/, cdr-analysis/...) whose content.js lists its slides. draw() writes them
// into slides.html, takes a picture of each slide (1920 × 1080) with a headless Chromium browser (Chrome, Chromium, Brave
// or Edge, the one of DRIVETEST_ANALYZER_CHROMIUM first) and writes slides.json (order, sections, titles and notes of the
// slides, and the title and description of the deck) into a folder of its own; it pictures the hand-written slides.html of
// the DT Analyzer RCA the same way. build.js draws them all when the server generates the presentations, and turns them
// into the PowerPoints the Help shows. To look at them, warned of what goes past the footer, out of its box or under the
// logo:
//   node module_decks.js <folder>             every deck, into <folder>/<id>/
//   node module_decks.js <folder> reporting   only the decks named
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const sharp = require('sharp');
const React = require('react');
const ReactDOMServer = require('react-dom/server');
const tb = require('react-icons/tb');

// The decks in the order of the tabs of the tool, Workspace Config after Workspace and the
// administration (Admin and Super Admin) after them, and those drawn from a slides.html.
const DECKS = ['workspace', 'workspace-config', 'cdr-analysis', 'ppt-designer', 'scoring-gap-analysis', 'network-insights', 'non-qualified-calls', 'reporting',
  'builders', 'ticket-center', 'administration'];
const DRAWN = [...DECKS, 'dt-analyzer-rca'];
// The colour of each module, that of its tab (module_labels.MODULE_TABS), for the chips naming the other modules.
const MODULES = {
  'Workspace': '#08736D', 'Workspace Config': '#0369A1', 'CDR Analysis': '#1F6FBF', 'PPT Designer': '#7751B9',
  'Scoring & GAP Analysis': '#176E77', 'Network Insights': '#4F46E5', 'Non-Qualified Calls': '#B0234F', 'Reporting': '#2E8C58',
  'Builders': '#B85B20', 'Ticket Center': '#DC2626', 'DT Analyzer RCA': '#7C3AED', 'Admin': '#B84343',
};
// The Ericsson logo at the top right of every slide, as in the other decks of the Help.
const LOGO = `data:image/png;base64,${fs.readFileSync(path.join(__dirname, '..', '..', 'src', 'web_interface', 'static', 'img', 'ericsson-logo-white.png')).toString('base64')}`;
// The browsers that take the pictures, as those of the charts of the reports (canvas_chart_renderer.mjs).
const BROWSERS = [process.env.DRIVETEST_ANALYZER_CHROMIUM, '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
  '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium', '/usr/bin/chromium-browser'].filter(Boolean);
// The slides taken in one picture, then cut one by one (a browser start for each would take minutes).
const SLIDES_PER_PICTURE = 6;
// How many times the browser is run for one picture before the generation fails, and the pause before trying again.
const BROWSER_ATTEMPTS = 3;
const BROWSER_RETRY_PAUSE_MS = 1500;

// -- colours ---------------------------------------------------------------------------------------------------------
function rgb(hex) {
  const value = hex.replace('#', '');
  return [0, 2, 4].map((index) => parseInt(value.slice(index, index + 2), 16));
}
function mix(hex, other, share) {
  const [a, b] = [rgb(hex), rgb(other)];
  return `#${a.map((value, index) => Math.round(value + (b[index] - value) * share).toString(16).padStart(2, '0')).join('')}`;
}
const INK = '#0b1220';
function palette(accent) {
  return { accent, light: mix(accent, '#ffffff', 0.42), soft: mix(accent, INK, 0.72), deep: mix(accent, INK, 0.45),
    glow: `rgba(${rgb(accent).join(',')},.30)`, series: [accent, mix(accent, '#ffffff', 0.5), '#7d8aa3', '#c3cbd9'] };
}
const escape = (value) => String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

function icon(name, color = '#ffffff', size = 36) {
  const component = tb[name];
  if (!component) throw new Error(`Unknown icon ${name}`);
  return ReactDOMServer.renderToStaticMarkup(React.createElement(component, { size, color }));
}
function badge(name, fill, size = 64, iconSize = 36) {
  return `<div class="icon" style="width:${size}px;height:${size}px;background:${fill}">${icon(name, '#ffffff', iconSize)}</div>`;
}
const chip = (label, fill, color = '#ffffff') => `<span class="chip" style="background:${fill};color:${color}">${escape(label)}</span>`;
const moduleChip = (name) => chip(name, MODULES[name] || '#475569');

// -- the views of Ticket Center as the tool draws them: light cards on a warm page, in the colours of its types,
// statuses and priorities (ticket_center.css) ------------------------------------------------------------------------
const TC = {
  page: '#f7f4f0', card: '#ffffff', line: '#e7e1d9', ink: '#10314a', muted: '#607585', track: '#eef1f4', red: '#dc2626', wine: '#b91c1c',
  type: { bug: '#dc2626', improvement: '#0d9488', feature: '#c026d3' },
  status: { open: '#10314a', new: '#1e61a3', progress: '#7c3aed', waiting: '#b7791f', resolved: '#1f8a5b', closed: '#a3adb5', rejected: '#9f1239' },
  priority: { P1: '#b42318', P2: '#dc6803', P3: '#b7791f', P4: '#1e61a3', P5: '#6b7a86' },
};
// The tickets opened and resolved (or closed) each week since the first ticket, and the rejected ones: the same figures
// in every view, as the tool would count them.
const TC_WEEKS = {
  labels: [[0, '1 Jun'], [4, '29 Jun'], [8, '27 Jul'], [12, '24 Aug'], [16, '21 Sep'], [20, '19 Oct']],
  created: [1, 0, 2, 1, 0, 1, 1, 1, 2, 1, 1, 2, 2, 2, 3, 2, 3, 4, 3, 6, 9, 13],
  resolved: [0, 0, 1, 1, 0, 0, 1, 1, 1, 1, 0, 1, 1, 1, 2, 1, 2, 2, 2, 3, 5, 7],
  rejected: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0, 1, 0, 1],
};
const tcText = (x, y, value, size = 14, fill = TC.ink, weight = 600, anchor = 'start', extra = '') =>
  `<text x="${x}" y="${y}" font-size="${size}" font-weight="${weight}" fill="${fill}" text-anchor="${anchor}"${extra}>${escape(value)}</text>`;
// Lines of text, one below the other (a \n starts another).
const tcLines = (x, y, value, size, fill, weight = 500, lineHeight = size * 1.35) => value.split('\n')
  .map((line, index) => tcText(x, (y + index * lineHeight).toFixed(1), line, size, fill, weight)).join('');
const tcIcon = (name, x, y, colour, size) => `<g transform="translate(${x} ${y})">${icon(name, colour, size)}</g>`;
const tcCard = (x, y, w, h, title = '', note = '', size = 16) => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="14" fill="${TC.card}" stroke="${TC.line}" stroke-width="1.5"/>`
  + (title ? tcText(x + 18, y + 30, title, size, TC.ink, 800) : '') + (note ? tcText(x + w - 18, y + 30, note, 12, TC.muted, 600, 'end') : '');
// A pill about as wide as its label, from x; its width comes back too, to put another one after it.
const tcPill = (x, y, label, fill, color = '#ffffff', size = 12) => {
  const width = Math.round(label.length * size * 0.6 + size * 1.6); const height = Math.round(size * 1.8);
  return { width, svg: `<rect x="${x}" y="${y}" width="${width}" height="${height}" rx="${height / 2}" fill="${fill}"/>${tcText(x + width / 2, (y + height / 2 + size * 0.36).toFixed(1), label, size, color, 800, 'middle')}` };
};
// A bar of a list: its track and the part filled.
const tcBar = (x, y, w, share, fill, h = 8) => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${h / 2}" fill="${TC.track}"/>`
  + `<rect x="${x}" y="${y}" width="${Math.max(h, w * share).toFixed(1)}" height="${h}" rx="${h / 2}" fill="${fill}"/>`;
// A donut of parts [value, colour], from the top and clockwise.
const tcDonut = (cx, cy, r, width, parts) => {
  const total = parts.reduce((sum, [value]) => sum + value, 0); const round = 2 * Math.PI * r; let offset = 0;
  return `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${TC.track}" stroke-width="${width}"/>` + parts.map(([value, colour]) => {
    const length = round * value / total;
    const svg = `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${colour}" stroke-width="${width}" stroke-dasharray="${Math.max(0, length - 2).toFixed(1)} ${(round - length + 2).toFixed(1)}" stroke-dashoffset="${(-offset).toFixed(1)}" transform="rotate(-90 ${cx} ${cy})"/>`;
    offset += length;
    return svg;
  }).join('');
};
// The page of the tool in a browser window with its address: what goes on the page starts below the bar (44 px).
const tcWindow = (width, height, address) => `<rect x="0" y="0" width="${width}" height="${height}" rx="18" fill="${TC.page}"/>`
  + `<path d="M0 18 a18 18 0 0 1 18 -18 H${width - 18} a18 18 0 0 1 18 18 V44 H0 Z" fill="#e4e0da"/>`
  + ['#ff5f57', '#febc2e', '#28c840'].map((colour, index) => `<circle cx="${26 + index * 22}" cy="22" r="7" fill="${colour}"/>`).join('')
  + `<rect x="${width / 2 - 280}" y="10" width="560" height="24" rx="12" fill="#f7f5f2"/>${tcIcon('TbLock', width / 2 - 266, 15, TC.muted, 14)}`
  + tcText(width / 2, 27, address, 13, TC.muted, 600, 'middle');
// A figure of a view: a label, its value and a line, beside an icon (or a ring) in its colour.
const tcTile = (x, y, w, h, { label, value, line, colour, iconName, ring }) => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="14" fill="${TC.card}" stroke="${TC.line}" stroke-width="1.5"/>`
  + `<rect x="${x + 1}" y="${y + 12}" width="4" height="${h - 24}" rx="2" fill="${colour}"/>`
  + (ring === undefined ? `<circle cx="${x + 38}" cy="${y + h / 2}" r="21" fill="${mix(colour, '#ffffff', 0.86)}"/>${tcIcon(iconName, x + 27, y + h / 2 - 11, colour, 22)}`
    : tcDonut(x + 38, y + h / 2, 17, 7, [[ring, colour], [100 - ring, TC.track]]))
  + tcText(x + 72, y + 24, label.toUpperCase(), 11, TC.muted, 800, 'start', ' letter-spacing="1"')
  + tcText(x + 72, y + 50, value, 24, TC.ink, 800) + tcText(x + 72, y + h - 10, line, 12, TC.muted, 500);
const TC_PERIODS = ['All time', 'This week', 'This month', 'This quarter', 'This year'];
// The Period bar at the top of Dashboard, Statistics and Time Spent.
const tcPeriodBar = (x, y, w, chosen, range) => {
  let out = `<rect x="${x}" y="${y}" width="${w}" height="44" rx="14" fill="${TC.card}" stroke="#f2c4c4" stroke-width="1.5"/>`
    + `<rect x="${x + 10}" y="${y + 8}" width="28" height="28" rx="8" fill="${TC.red}"/>${tcIcon('TbCalendar', x + 15, y + 13, '#ffffff', 18)}`
    + tcText(x + 50, y + 27, 'Period', 15, TC.wine, 800);
  const widths = TC_PERIODS.map((label) => label.length * 7.6 + 26);
  out += `<rect x="${x + 112}" y="${y + 7}" width="${widths.reduce((sum, value) => sum + value + 4, 2)}" height="30" rx="15" fill="#f4f1ee"/>`;
  let left = x + 115;
  TC_PERIODS.forEach((label, index) => {
    if (label === chosen) out += `<rect x="${left}" y="${y + 10}" width="${widths[index]}" height="24" rx="12" fill="${TC.red}"/>`;
    out += tcText((left + widths[index] / 2).toFixed(1), y + 27, label, 13, label === chosen ? '#ffffff' : TC.ink, 700, 'middle');
    left += widths[index] + 4;
  });
  return out + (range ? tcText(x + w - 16, y + 27, range, 13, TC.muted, 600, 'end') : '');
};
// A time in days of 24 hours, hours and minutes, as Ticket Center writes it.
const tcDuration = (days) => (days >= 1 ? `${Math.floor(days)}d ${Math.round((days % 1) * 24)}h` : `${Math.floor(days * 24)}h ${Math.round(((days * 24) % 1) * 60)}m`);

// -- visuals (820 × 560, in the colours of the module) ---------------------------------------------------------------
const VISUALS = {
  // Grouped bars of three operators.
  bars(p, { groups = ['Voice', 'Data', 'Video', 'Speech'], series = ['Operator A', 'Operator B', 'Operator C'] } = {}) {
    const values = [[82, 74, 61], [77, 69, 72], [68, 81, 59], [88, 76, 70]];
    const width = 820; const base = 470; const groupWidth = (width - 120) / groups.length;
    let bars = '';
    groups.forEach((group, g) => {
      series.forEach((_name, s) => {
        const height = values[g % values.length][s % 3] * 4;
        const x = 70 + g * groupWidth + 18 + s * (groupWidth - 36) / series.length;
        bars += `<rect x="${x}" y="${base - height}" width="${(groupWidth - 36) / series.length - 8}" height="${height}" rx="8" fill="${p.series[s]}"/>`;
      });
      bars += `<text x="${70 + g * groupWidth + groupWidth / 2}" y="${base + 40}" text-anchor="middle" font-size="24" fill="#9fb0cc">${escape(group)}</text>`;
    });
    const legend = series.map((name, s) => `<rect x="${70 + s * 230}" y="20" width="22" height="22" rx="6" fill="${p.series[s]}"/><text x="${102 + s * 230}" y="39" font-size="22" fill="#c9d4e6">${escape(name)}</text>`).join('');
    return `<line x1="60" y1="${base}" x2="${width - 30}" y2="${base}" stroke="#2a3a5c" stroke-width="3"/>${[1, 2, 3].map((i) => `<line x1="60" y1="${base - i * 100}" x2="${width - 30}" y2="${base - i * 100}" stroke="#1f2c47" stroke-width="2" stroke-dasharray="6 8"/>`).join('')}${bars}${legend}`;
  },
  // Three cumulative distributions.
  cdf(p) {
    const curve = (median, spread, color) => {
      const points = [];
      for (let x = 0; x <= 700; x += 10) {
        const y = 1 / (1 + Math.exp(-(x - median) / spread));
        points.push(`${70 + x},${470 - y * 400}`);
      }
      return `<polyline points="${points.join(' ')}" fill="none" stroke="${color}" stroke-width="6" stroke-linecap="round"/>`;
    };
    return `<line x1="70" y1="470" x2="790" y2="470" stroke="#2a3a5c" stroke-width="3"/><line x1="70" y1="60" x2="70" y2="470" stroke="#2a3a5c" stroke-width="3"/>`
      + `<line x1="70" y1="270" x2="790" y2="270" stroke="#1f2c47" stroke-width="2" stroke-dasharray="6 8"/><text x="80" y="258" font-size="20" fill="#7d8aa3">P50</text>`
      + curve(260, 48, p.series[2]) + curve(350, 55, p.series[1]) + curve(440, 50, p.accent)
      + `<text x="430" y="520" text-anchor="middle" font-size="22" fill="#9fb0cc">KPI value</text>`;
  },
  // A heat map of an area with its sites and its weakest area.
  map(p) {
    const colours = ['#1f9d55', '#5fbf3f', '#c8d23a', '#f0a830', '#e0533d'];
    let cells = '';
    for (let row = 0; row < 9; row += 1) {
      for (let col = 0; col < 15; col += 1) {
        const value = Math.abs(Math.sin(row * 1.7 + col * 0.9) + Math.cos(col * 0.6 - row)) / 2;
        const shade = colours[Math.min(4, Math.floor(value * 5))];
        cells += `<rect x="${40 + col * 50}" y="${40 + row * 52}" width="46" height="48" rx="6" fill="${shade}" opacity="${0.35 + value * 0.5}"/>`;
      }
    }
    const sites = [[160, 130], [420, 210], [610, 120], [300, 380], [680, 400]].map(([x, y]) => `<path d="M${x} ${y - 22} L${x + 16} ${y + 12} L${x - 16} ${y + 12} Z" fill="#ffffff" stroke="${INK}" stroke-width="3"/>`).join('');
    return cells + sites + `<circle cx="530" cy="300" r="78" fill="none" stroke="${p.light}" stroke-width="5" stroke-dasharray="12 10"/><rect x="440" y="384" width="180" height="40" rx="20" fill="${INK}" opacity=".88"/><text x="530" y="412" text-anchor="middle" font-size="24" font-weight="700" fill="${p.light}">weakest area</text>`;
  },
  // A scorecard: operators, KPIs and their points.
  table(p, { columns = ['Operator A', 'Operator B', 'Operator C'], rows = ['Voice', 'Data', 'Video', 'Browsing', 'Speech'] } = {}) {
    const scores = [[94, 88, 81], [86, 91, 77], [79, 84, 88], [90, 72, 83], [83, 87, 75]];
    let out = `<rect x="20" y="20" width="780" height="70" rx="14" fill="${p.deep}"/><text x="50" y="66" font-size="24" font-weight="700" fill="#ffffff">KPI</text>`;
    columns.forEach((column, c) => { out += `<text x="${330 + c * 160}" y="66" text-anchor="middle" font-size="22" font-weight="700" fill="#ffffff">${escape(column)}</text>`; });
    rows.forEach((row, r) => {
      const y = 104 + r * 88;
      out += `<rect x="20" y="${y}" width="780" height="78" rx="12" fill="#16213a"/><text x="50" y="${y + 48}" font-size="24" fill="#c9d4e6">${escape(row)}</text>`;
      columns.forEach((_column, c) => {
        const value = scores[r % scores.length][c % 3]; const best = Math.max(...scores[r % scores.length]) === value;
        out += `<rect x="${262 + c * 160}" y="${y + 14}" width="136" height="50" rx="10" fill="${best ? p.accent : '#22304f'}"/><text x="${330 + c * 160}" y="${y + 48}" text-anchor="middle" font-size="24" font-weight="700" fill="#ffffff">${value}</text>`;
      });
    });
    return out;
  },
  // GAP of every KPI against the reference operator.
  gap(p) {
    const kpis = [['Call setup', 6], ['Drops', -9], ['Throughput', 12], ['Video', -4], ['Browsing', 8], ['Latency', -12]];
    let out = `<line x1="430" y1="30" x2="430" y2="530" stroke="#9fb0cc" stroke-width="3"/><text x="430" y="22" text-anchor="middle" font-size="20" fill="#9fb0cc">reference</text>`;
    kpis.forEach(([name, value], index) => {
      const y = 60 + index * 78; const width = Math.abs(value) * 18;
      out += `<text x="40" y="${y + 38}" font-size="24" fill="#c9d4e6">${name}</text>`;
      out += `<rect x="${value < 0 ? 430 - width : 430}" y="${y + 6}" width="${width}" height="48" rx="10" fill="${value < 0 ? '#e0533d' : p.accent}"/>`;
      out += `<text x="${value < 0 ? 420 - width : 440 + width}" y="${y + 40}" text-anchor="${value < 0 ? 'end' : 'start'}" font-size="22" font-weight="700" fill="#ffffff">${value > 0 ? '+' : '−'}${Math.abs(value)}</text>`;
    });
    return out;
  },
  // Slides of a presentation, one behind the other.
  slides(p) {
    const frame = (x, y, opacity, chart) => `<g opacity="${opacity}"><rect x="${x}" y="${y}" width="520" height="300" rx="18" fill="#16213a" stroke="#2a3a5c" stroke-width="3"/>`
      + `<rect x="${x + 28}" y="${y + 26}" width="250" height="22" rx="8" fill="${p.light}"/><rect x="${x + 28}" y="${y + 58}" width="160" height="14" rx="6" fill="#3a4d75"/>${chart(x, y)}</g>`;
    const bars = (x, y) => [70, 120, 90, 150, 110].map((h, i) => `<rect x="${x + 40 + i * 90}" y="${y + 270 - h}" width="56" height="${h}" rx="8" fill="${i === 3 ? p.accent : p.series[2]}"/>`).join('');
    const line = (x, y) => `<polyline points="${[0, 1, 2, 3, 4, 5].map((i) => `${x + 40 + i * 88},${y + 250 - [40, 90, 70, 140, 120, 170][i]}`).join(' ')}" fill="none" stroke="${p.accent}" stroke-width="7" stroke-linecap="round"/>`;
    return frame(40, 30, 0.45, line) + frame(150, 130, 0.7, bars) + frame(270, 230, 1, bars);
  },
  // The labels of the Operator Maps: their order, colour, label, role and the names of the CDRs they stand for.
  labels(p) {
    const labels = [['EE', '#00A3AD', 'Focus', '#1f9d55', ['EE', 'EE UK']], ['VF', '#E60000', 'Include', '#c8a21a', ['Vodafone UK', 'VFUK']],
      ['O2', '#0019A5', 'Include', '#c8a21a', ['O2 UK', 'O2-UK']], ['3', '#E8541E', 'Include', '#c8a21a', ['Three', '3 UK']],
      ['Lebara', '#2D8AE6', 'Exclude', '#e0533d', ['Lebara UK']]];
    let out = `<rect x="20" y="20" width="780" height="60" rx="12" fill="${p.deep}"/>`;
    [['Order', 40], ['Label', 190], ['Role', 360], ['Names in the CDRs', 520]].forEach(([name, x]) => { out += `<text x="${x}" y="58" font-size="20" font-weight="700" fill="#ffffff">${name}</text>`; });
    labels.forEach(([label, colour, role, roleColour, names], index) => {
      const y = 94 + index * 84;
      out += `<rect x="20" y="${y}" width="780" height="72" rx="12" fill="#16213a" stroke="#2a3a5c" stroke-width="2"/>`;
      out += `<text x="44" y="${y + 46}" font-size="24" font-weight="700" fill="${p.light}">${index + 1}</text>`;
      out += `<path d="M86 ${y + 30} l10 -12 l10 12 Z" fill="#7d8aa3"/><path d="M86 ${y + 42} l10 12 l10 -12 Z" fill="#7d8aa3"/>`;
      out += `<rect x="134" y="${y + 18}" width="36" height="36" rx="8" fill="${colour}" stroke="#ffffff" stroke-width="2"/>`;
      out += `<text x="190" y="${y + 46}" font-size="26" font-weight="700" fill="#ffffff">${escape(label)}</text>`;
      out += `<rect x="352" y="${y + 18}" width="112" height="36" rx="18" fill="${roleColour}"/><text x="408" y="${y + 43}" text-anchor="middle" font-size="18" font-weight="700" fill="#ffffff">${role}</text>`;
      let x = 512;
      names.forEach((name) => {
        const width = 22 + name.length * 11;
        out += `<rect x="${x}" y="${y + 20}" width="${width}" height="32" rx="16" fill="#22304f"/><text x="${x + width / 2}" y="${y + 42}" text-anchor="middle" font-size="17" fill="#c9d4e6">${escape(name)}</text>`;
        x += width + 10;
      });
    });
    return out;
  },
  // A PPT Template in its editor: a row per chart, the cells of a slide merged, an edited cell and Save Template.
  template(p) {
    const columns = [['Slide', 70], ['Layout', 150], ['Chart type', 150], ['KPI', 190], ['Filters', 200]];
    const rows = [['1', 'Title Page', 'Title Slide', '', ''], ['2', 'Two Charts', 'Bar', 'Call Success Rate', 'Service = Voice'],
      ['', '', 'Line', 'Setup Time', 'Service = Voice'], ['3', 'One Chart', 'CDF', 'DL Throughput', 'Technology = 5G'],
      ['4', 'Two Charts', 'Column', 'MOS', 'Operator in Focus'], ['', '', 'Table', 'POLQA < 1.6', '']];
    let x = 20;
    let out = `<rect x="20" y="20" width="780" height="60" rx="12" fill="${p.deep}"/>`;
    const starts = columns.map(([name, width]) => { const start = x; out += `<text x="${x + 14}" y="58" font-size="20" font-weight="700" fill="#ffffff">${name}</text>`; x += width + 4; return start; });
    rows.forEach((row, r) => {
      const y = 92 + r * 64;
      row.forEach((value, c) => {
        // (The Slide and Layout of a second chart are merged with those of the first one of its slide.)
        if (!value && c < 2 && r > 0 && rows[r][0] === '') return;
        const merged = c < 2 && rows[r + 1] && rows[r + 1][0] === '';
        const edited = r === 3 && c === 3;
        out += `<rect x="${starts[c]}" y="${y}" width="${columns[c][1]}" height="${merged ? 120 : 56}" rx="8" fill="${edited ? '#fff3b0' : '#16213a'}" stroke="${edited ? '#e8c547' : '#2a3a5c'}" stroke-width="2"/>`;
        out += `<text x="${starts[c] + 12}" y="${y + (merged ? 66 : 36)}" font-size="${c === 0 ? 22 : 18}" font-weight="${c === 0 ? 700 : 400}" fill="${edited ? '#1b2234' : '#c9d4e6'}">${escape(value)}</text>`;
      });
    });
    out += `<rect x="560" y="490" width="240" height="54" rx="27" fill="${p.accent}"/><text x="680" y="525" text-anchor="middle" font-size="22" font-weight="700" fill="#ffffff">Save Template</text>`;
    out += `<rect x="20" y="490" width="250" height="54" rx="27" fill="#22304f"/><text x="145" y="525" text-anchor="middle" font-size="20" font-weight="700" fill="#c9d4e6">Find &amp; Replace</text>`;
    return out;
  },
  // The map of a Non-Qualified call: where it failed, its way, its cells at their sites, the sites, calls and tests around.
  callmap(p) {
    let out = '<rect x="0" y="0" width="820" height="560" rx="16" fill="#101a2e"/>';
    // Streets: the drive went along the first two.
    const road = (x) => 300 - (50 * x) / 820;
    const avenue = (y) => 560 + (50 * y) / 560;
    [[0, 300, 820, 250], [560, 0, 610, 560], [0, 120, 820, 170], [0, 450, 820, 400], [210, 0, 260, 560]].forEach(([x1, y1, x2, y2]) => {
      out += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#1d2a45" stroke-width="16" stroke-linecap="round"/>`;
    });
    // The tests of the drive, by their RSRP: weaker near the call.
    const levels = ['#1f9d55', '#5fbf3f', '#c8d23a', '#f0a830', '#e0533d'];
    const call = [455, road(455)];
    const sample = (x, y, index) => {
      const near = Math.hypot(x - call[0], y - call[1]);
      const level = near < 90 ? 3 + (index % 2) : near < 180 ? 2 : index % 2;
      return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="7" fill="${levels[level]}" opacity=".9"/>`;
    };
    for (let x = 40, index = 0; x <= 790; x += 30, index += 1) out += sample(x, road(x) - 14, index);
    for (let y = 30, index = 0; y <= 540; y += 30, index += 1) if (Math.abs(y - road(avenue(y))) > 30) out += sample(avenue(y) + 14, y, index);
    // The radius of the call.
    out += `<circle cx="${call[0]}" cy="${call[1].toFixed(1)}" r="170" fill="none" stroke="${p.light}" stroke-width="3" stroke-dasharray="10 9" opacity=".7"/>`;
    // Sites around, by vendor; the serving site far away, ringed, with its sector towards the call.
    const site = (x, y, fill) => `<path d="M${x} ${y - 18} L${x + 14} ${y + 10} L${x - 14} ${y + 10} Z" fill="${fill}" stroke="${INK}" stroke-width="3"/>`;
    [[80, 190, '#3a7fc1'], [120, 500, '#3a7fc1'], [740, 500, '#e08a1e'], [360, 520, '#3a7fc1'], [430, 80, '#e08a1e']].forEach(([x, y, fill]) => { out += site(x, y, fill); });
    const serving = [730, 380];
    const wedge = [195, 235].map((degrees) => [serving[0] + 120 * Math.cos((degrees * Math.PI) / 180), serving[1] + 120 * Math.sin((degrees * Math.PI) / 180)]);
    out += `<path d="M${serving[0]} ${serving[1]} L${wedge[0][0].toFixed(1)} ${wedge[0][1].toFixed(1)} A120 120 0 0 1 ${wedge[1][0].toFixed(1)} ${wedge[1][1].toFixed(1)} Z" fill="${p.accent}" opacity=".35"/>`;
    out += `<circle cx="${serving[0]}" cy="${serving[1]}" r="30" fill="none" stroke="#ffffff" stroke-width="4"/>${site(serving[0], serving[1], '#e08a1e')}`;
    const start = [170, road(170)];
    out += site(250, 200, '#3a7fc1');
    // Its way, from where it started (a green dot) to where it failed, and its cells joined to their sites.
    out += `<line x1="${start[0]}" y1="${start[1].toFixed(1)}" x2="${call[0]}" y2="${call[1].toFixed(1)}" stroke="#9fe0b5" stroke-width="6" stroke-linecap="round"/>`;
    out += `<line x1="${start[0]}" y1="${start[1].toFixed(1)}" x2="250" y2="200" stroke="#9fe0b5" stroke-width="3" stroke-dasharray="8 7"/>`;
    out += `<line x1="${call[0]}" y1="${call[1].toFixed(1)}" x2="${serving[0]}" y2="${serving[1]}" stroke="${p.light}" stroke-width="3" stroke-dasharray="8 7"/>`;
    out += `<circle cx="${start[0]}" cy="${start[1].toFixed(1)}" r="11" fill="#1f9d55" stroke="#ffffff" stroke-width="3"/>`;
    // Other Non-Qualified Calls around.
    [[400, 200], [520, 330], [350, 360]].forEach(([x, y]) => { out += `<rect x="${x - 9}" y="${y - 9}" width="18" height="18" rx="4" fill="${p.light}" stroke="${INK}" stroke-width="3" transform="rotate(45 ${x} ${y})"/>`; });
    // The call: a pin where it failed.
    const [x, y] = [call[0], call[1].toFixed(1)];
    out += `<path d="M${x} ${y} c-15 -20 -23 -32 -23 -44 a23 23 0 1 1 46 0 c0 12 -8 24 -23 44 Z" fill="${p.accent}" stroke="#ffffff" stroke-width="4"/><circle cx="${x}" cy="${(call[1] - 44).toFixed(1)}" r="8" fill="#ffffff"/>`;
    // A hint of the diagnosis.
    out += `<rect x="500" y="30" width="290" height="50" rx="25" fill="${INK}" opacity=".92"/><circle cx="526" cy="55" r="9" fill="#e0533d"/><text x="544" y="63" font-size="21" font-weight="700" fill="#ffffff">Overshooting · 2.4 × ISD</text>`;
    out += `<rect x="30" y="30" width="200" height="50" rx="25" fill="${INK}" opacity=".92"/><text x="130" y="63" text-anchor="middle" font-size="21" font-weight="700" fill="${p.light}">Radius 1 km</text>`;
    return out;
  },
  // A board of tickets by status.
  kanban(p) {
    const columns = [['New', 3], ['In Progress', 2], ['Resolved', 3]];
    const types = ['#dc2626', '#2563eb', '#16a34a'];
    let out = '';
    columns.forEach(([name, count], c) => {
      const x = 20 + c * 270;
      out += `<rect x="${x}" y="20" width="250" height="520" rx="18" fill="#131d33" stroke="#2a3a5c" stroke-width="2"/><text x="${x + 24}" y="64" font-size="24" font-weight="700" fill="#ffffff">${name}</text>`;
      for (let i = 0; i < count; i += 1) {
        const y = 92 + i * 140;
        out += `<rect x="${x + 18}" y="${y}" width="214" height="120" rx="14" fill="#1a2742"/><rect x="${x + 18}" y="${y}" width="10" height="120" rx="5" fill="${types[(c + i) % 3]}"/>`
          + `<rect x="${x + 44}" y="${y + 24}" width="150" height="16" rx="6" fill="#c9d4e6"/><rect x="${x + 44}" y="${y + 54}" width="110" height="12" rx="6" fill="#3a4d75"/>`
          + `<rect x="${x + 44}" y="${y + 82}" width="70" height="22" rx="11" fill="${c === 2 ? p.accent : '#2a3a5c'}"/>`;
      }
    });
    return out;
  },
  // The runs of a week and their emails.
  schedule(p) {
    const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    let out = '';
    days.forEach((day, d) => {
      out += `<text x="${80 + d * 104}" y="50" text-anchor="middle" font-size="22" fill="#9fb0cc">${day}</text>`;
      for (let w = 0; w < 4; w += 1) {
        const run = (d === 0 && w < 4) || (d === 3 && w % 2 === 0) || (d === 6 && w === 3);
        out += `<rect x="${38 + d * 104}" y="${74 + w * 112}" width="86" height="96" rx="14" fill="${run ? p.soft : '#131d33'}" stroke="${run ? p.accent : '#22304f'}" stroke-width="3"/>`;
        if (run) out += `<circle cx="${81 + d * 104}" cy="${122 + w * 112}" r="16" fill="${p.accent}"/>`;
      }
    });
    return out;
  },
  // A query and its result.
  sql(p) {
    const lines = [[['SELECT', p.light], [' operator, AVG(throughput_mbps)', '#e8eef7']], [['FROM', p.light], [' cdr_data', '#e8eef7']],
      [['WHERE', p.light], [" campaign = '2026-Q3'", '#9fe0b5']], [['GROUP BY', p.light], [' operator', '#e8eef7']]];
    let out = `<rect x="20" y="20" width="780" height="250" rx="18" fill="#0f172a" stroke="#2a3a5c" stroke-width="2"/>`;
    lines.forEach((parts, index) => {
      let x = 50;
      parts.forEach(([value, colour]) => { out += `<text x="${x}" y="${78 + index * 50}" font-family="Menlo, monospace" font-size="26" fill="${colour}" xml:space="preserve">${escape(value)}</text>`; x += value.length * 15.6; });
    });
    [['Operator', 'Mbit/s'], ['Operator A', '182.4'], ['Operator B', '164.9'], ['Operator C', '131.2']].forEach(([a, b], r) => {
      const y = 300 + r * 60;
      out += `<rect x="20" y="${y}" width="780" height="52" rx="10" fill="${r === 0 ? p.deep : '#16213a'}"/><text x="50" y="${y + 35}" font-size="23" fill="#ffffff" font-weight="${r === 0 ? 700 : 400}">${a}</text><text x="770" y="${y + 35}" text-anchor="end" font-size="23" fill="#ffffff" font-weight="${r === 0 ? 700 : 400}">${b}</text>`;
    });
    return out;
  },
  // Files of every type into the tables of the workspace.
  pipeline(p) {
    const files = [['CSV', '#2e8b57'], ['XLSX', '#1f6fbf'], ['KMZ', '#e08a1e'], ['GeoJSON', '#7c3aed']];
    let out = '';
    files.forEach(([name, colour], index) => {
      const y = 40 + index * 124;
      out += `<rect x="20" y="${y}" width="170" height="100" rx="16" fill="#16213a" stroke="${colour}" stroke-width="3"/><text x="105" y="${y + 60}" text-anchor="middle" font-size="24" font-weight="700" fill="#ffffff">${name}</text>`;
      out += `<path d="M190 ${y + 50} C260 ${y + 50} 260 280 330 280" fill="none" stroke="#3a4d75" stroke-width="4"/>`;
    });
    out += `<circle cx="400" cy="280" r="70" fill="${p.accent}"/><g transform="translate(360 240)">${icon('TbSettingsAutomation', '#ffffff', 80)}</g>`;
    out += `<path d="M470 280 H548" stroke="${p.light}" stroke-width="5"/><path d="M546 266 L566 280 L546 294 Z" fill="${p.light}"/>`;
    ['CDR-Data', 'CDR-Voice', 'CDR-Speech', 'Inventories'].forEach((name, index) => {
      const y = 70 + index * 110;
      out += `<rect x="580" y="${y}" width="220" height="86" rx="14" fill="${index < 3 ? p.soft : '#16213a'}" stroke="${p.accent}" stroke-width="2"/><text x="690" y="${y + 52}" text-anchor="middle" font-size="23" font-weight="700" fill="#ffffff">${name}</text>`;
    });
    return out;
  },
  // The columnar store: every CDR a Parquet copy that DuckDB reads for every module and, through PostgreSQL, for Tableau,
  // and the workspace database kept light.
  columnar(p) {
    let out = '';
    [['Data', '#1f6fbf'], ['Voice', '#2e8b57'], ['Speech', '#7c3aed']].forEach(([name, colour], index) => {
      const y = 64 + index * 118;
      out += `<rect x="12" y="${y}" width="146" height="92" rx="16" fill="#16213a" stroke="${colour}" stroke-width="3"/>`;
      out += `<text x="85" y="${y + 38}" text-anchor="middle" font-size="16" font-weight="700" fill="#9fb0cc" letter-spacing="2">CDR</text>`;
      out += `<text x="85" y="${y + 68}" text-anchor="middle" font-size="25" font-weight="800" fill="#ffffff">${name}</text>`;
      out += `<path d="M158 ${y + 46} C 208 ${y + 46}, 206 214, 246 214" fill="none" stroke="#3a4d75" stroke-width="4"/>`;
    });
    // The copies: a stack of Parquet files.
    for (let layer = 2; layer >= 0; layer -= 1) {
      const top = 128 + layer * 52;
      out += `<path d="M250 ${top} v40 a100 22 0 0 0 200 0 v-40" fill="${layer ? p.deep : p.accent}" stroke="${p.light}" stroke-width="3"/>`;
      out += `<ellipse cx="350" cy="${top}" rx="100" ry="22" fill="${layer ? p.accent : p.light}" stroke="${p.light}" stroke-width="3"/>`;
    }
    out += `<g transform="translate(330 104)">${icon('TbBolt', '#101a2e', 40)}</g>`;
    out += `<text x="350" y="322" text-anchor="middle" font-size="25" font-weight="800" fill="#ffffff">Parquet copies</text>`;
    out += pill(350, 364, 'DuckDB', '#f2c94c', '#101a2e', 21);
    // The workspace database: the schema and indexes, without the rows.
    out += `<rect x="236" y="412" width="228" height="118" rx="16" fill="#101a2e" stroke="#55627c" stroke-width="2.5" stroke-dasharray="9 7"/>`;
    out += `<text x="350" y="446" text-anchor="middle" font-size="19" font-weight="800" fill="#c9d4e6">Workspace DB</text>`;
    out += `<text x="350" y="474" text-anchor="middle" font-size="15" fill="#9fb0cc">schema · indexes · no rows</text>`;
    out += `<text x="350" y="510" text-anchor="middle" font-size="22" font-weight="800" fill="${p.light}">51 GB → 5 GB</text>`;
    // Every module, and Tableau through PostgreSQL.
    out += `<path d="M452 196 C 492 196, 484 132, 520 132" fill="none" stroke="${p.light}" stroke-width="4"/>`;
    out += `<path d="M452 236 C 492 236, 484 412, 520 412" fill="none" stroke="${p.light}" stroke-width="4"/>`;
    out += `<rect x="522" y="14" width="288" height="262" rx="18" fill="#16213a" stroke="${p.accent}" stroke-width="3"/>`;
    out += `<text x="546" y="50" font-size="17" font-weight="800" fill="${p.light}" letter-spacing="2">EVERY MODULE</text>`;
    ['PPT Designer', 'Scoring & GAP', 'Network Insights', 'Non-Qualified Calls', 'Query Builder'].forEach((name, index) => {
      out += `<rect x="544" y="${66 + index * 40}" width="244" height="32" rx="10" fill="${p.soft}"/><circle cx="562" cy="${82 + index * 40}" r="6" fill="${p.light}"/>`;
      out += `<text x="578" y="${89 + index * 40}" font-size="18" font-weight="700" fill="#ffffff">${name}</text>`;
    });
    out += `<rect x="522" y="300" width="288" height="230" rx="18" fill="#16213a" stroke="#336791" stroke-width="3"/>`;
    out += `<text x="546" y="336" font-size="15" font-weight="800" fill="#7fb2dd" letter-spacing="1">POSTGRESQL · PG_DUCKDB</text>`;
    ['cdr_data', 'cdr_voice', 'cdr_speech'].forEach((name, index) => {
      out += `<text x="548" y="${370 + index * 30}" font-size="18" fill="#c9d4e6" class="mono">${name}</text>`;
    });
    out += `<path d="M700 396 H736" stroke="#7fb2dd" stroke-width="4"/><path d="M734 386 L750 396 L734 406 Z" fill="#7fb2dd"/>`;
    out += `<g transform="translate(752 370)">${icon('TbChartBar', '#ffffff', 46)}</g>`;
    out += `<text x="666" y="500" text-anchor="middle" font-size="24" font-weight="800" fill="#ffffff">Tableau, live</text>`;
    return out;
  },
  // A donut of shares.
  donut(p, { parts = [['RF', 42, '#3a7fc1'], ['RAN', 23, '#e08a1e'], ['Core', 14, '#7b52c0'], ['Protocol', 12, '#138597'], ['Other', 9, '#7b8790']] } = {}) {
    let angle = -Math.PI / 2; let out = '';
    parts.forEach(([name, share, colour], index) => {
      const end = angle + share / 100 * Math.PI * 2;
      const large = end - angle > Math.PI ? 1 : 0;
      const point = (a, r) => `${280 + Math.cos(a) * r},${280 + Math.sin(a) * r}`;
      out += `<path d="M${point(angle, 230)} A230 230 0 ${large} 1 ${point(end, 230)} L${point(end, 130)} A130 130 0 ${large} 0 ${point(angle, 130)} Z" fill="${colour}"/>`;
      out += `<rect x="580" y="${80 + index * 84}" width="30" height="30" rx="8" fill="${colour}"/><text x="626" y="${104 + index * 84}" font-size="26" fill="#e8eef7">${name}</text><text x="800" y="${104 + index * 84}" text-anchor="end" font-size="26" font-weight="700" fill="#ffffff">${share}%</text>`;
      angle = end;
    });
    return out + `<text x="280" y="292" text-anchor="middle" font-size="30" font-weight="800" fill="#ffffff">root causes</text>`;
  },
  // The phases of a follow-up.
  phases(p, { steps = ['General', 'RCA', 'Failure Details', 'Analysis', 'Implementation', 'Planning'] } = {}) {
    let out = '';
    steps.forEach((name, index) => {
      const x = 40 + (index % 3) * 260; const y = 60 + Math.floor(index / 3) * 250;
      out += `<rect x="${x}" y="${y}" width="230" height="170" rx="22" fill="${index < 3 ? p.soft : '#16213a'}" stroke="${index < 3 ? p.accent : '#2a3a5c'}" stroke-width="3"/>`
        + `<circle cx="${x + 46}" cy="${y + 50}" r="26" fill="${index < 3 ? p.accent : '#2a3a5c'}"/><text x="${x + 46}" y="${y + 59}" text-anchor="middle" font-size="24" font-weight="800" fill="#ffffff">${index + 1}</text>`
        + `<text x="${x + 24}" y="${y + 128}" font-size="25" font-weight="700" fill="#ffffff">${escape(name)}</text>`;
    });
    return out;
  },
  // A chart and the fields that build it.
  builder(p) {
    let out = '';
    [['Rows', ['Operator', 'City']], ['Columns', ['Campaign']], ['Values', ['Throughput · P90']]].forEach(([title, fields], index) => {
      const y = 30 + index * 120;
      out += `<text x="30" y="${y + 30}" font-size="22" fill="#9fb0cc">${title}</text>`;
      fields.forEach((field, f) => { out += `<rect x="${30 + f * 180}" y="${y + 46}" width="${field.length * 13 + 40}" height="48" rx="24" fill="${f ? '#2a3a5c' : p.accent}"/><text x="${50 + f * 180}" y="${y + 78}" font-size="22" font-weight="700" fill="#ffffff">${escape(field)}</text>`; });
    });
    out += `<rect x="430" y="30" width="370" height="500" rx="18" fill="#16213a" stroke="#2a3a5c" stroke-width="2"/>`;
    [190, 280, 150, 330, 240].forEach((h, i) => { out += `<rect x="${470 + i * 64}" y="${480 - h}" width="44" height="${h}" rx="8" fill="${i === 3 ? p.accent : p.series[1]}"/>`; });
    return out + `<rect x="30" y="400" width="370" height="130" rx="18" fill="#16213a" stroke="#2a3a5c" stroke-width="2"/><text x="56" y="444" font-size="22" fill="#9fb0cc">Filters</text><text x="56" y="480" font-size="24" fill="#ffffff" font-weight="700">Operator = A, B</text><text x="56" y="512" font-size="24" fill="#ffffff" font-weight="700">NR Mode = SA</text>`;
  },
  // The Designer on screen: the slides at the left, a slide of two charts above and one as wide as both below, the chart
  // chosen with its Chart Type tab and the chart types open, and the panel with the shelves and what the type needs.
  studio(p) {
    const card = (x, y, w, h, fill = '#16213a', stroke = '#2a3a5c', radius = 12) => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${radius}" fill="${fill}" stroke="${stroke}" stroke-width="2"/>`;
    const text = (x, y, value, size = 15, fill = '#c9d4e6', weight = 600, anchor = 'start') => `<text x="${x}" y="${y}" font-size="${size}" font-weight="${weight}" fill="${fill}" text-anchor="${anchor}">${escape(value)}</text>`;
    const green = '#3cb371', orange = '#e8833a';
    const cdf = (x, y, w, h) => `<path d="M${x + 8} ${y + h - 8} H${x + w - 6} M${x + 8} ${y + 6} V${y + h - 8}" stroke="#3a4d75" stroke-width="2" fill="none"/>`
      + [[p.accent, 0], [green, 14]].map(([colour, shift]) => `<path d="M${x + 10} ${y + h - 10} C${x + w * 0.3 + shift} ${y + h - 12}, ${x + w * 0.35 + shift} ${y + 14}, ${x + w - 8} ${y + 12 + shift / 2}" stroke="${colour}" stroke-width="4" fill="none" stroke-linecap="round"/>`).join('');
    const bars = (x, y, w, h, mean = false) => [0.55, 0.8, 0.45, 0.9, 0.65, 0.75].map((share, i) => `<rect x="${x + 12 + i * (w - 24) / 6}" y="${y + h - 8 - share * (h - 22)}" width="${(w - 24) / 6 - 8}" height="${share * (h - 22)}" rx="3" fill="${i % 2 ? green : p.accent}"/>`).join('')
      + (mean ? `<path d="M${x + 10} ${y + h * 0.42} H${x + w - 10}" stroke="${orange}" stroke-width="3" stroke-dasharray="7 5"/>` : '');
    const stacked = (x, y, w, h) => [0, 1, 2, 3, 4, 5, 6, 7].map((i) => { const bx = x + 14 + i * (w - 28) / 8, bw = (w - 28) / 8 - 10, top = y + 12, height = h - 22;
      return `<rect x="${bx}" y="${top}" width="${bw}" height="${height * 0.5}" rx="2" fill="${p.accent}"/><rect x="${bx}" y="${top + height * 0.5}" width="${bw}" height="${height * 0.3}" fill="${green}"/><rect x="${bx}" y="${top + height * 0.8}" width="${bw}" height="${height * 0.2}" rx="2" fill="${orange}"/>`; }).join('');
    let out = '';
    // The slides of the Design, in small.
    [0, 1, 2, 3].forEach((i) => {
      const y = 20 + i * 92;
      out += card(16, y, 112, 66, i === 1 ? '#22304f' : '#16213a', i === 1 ? p.accent : '#2a3a5c', 8);
      if (i === 0) out += `<rect x="18" y="${y + 2}" width="108" height="62" rx="7" fill="${p.deep}"/>` + text(72, y + 38, 'Cover', 13, '#ffffff', 700, 'middle');
      else out += [[24, 10, 46, 22], [74, 10, 46, 22], [24, 36, 96, 24]].map(([dx, dy, w, h]) => `<rect x="${dx}" y="${y + dy}" width="${w}" height="${h}" rx="3" fill="#2a3a5c"/>`).join('');
    });
    out += `<rect x="16" y="390" width="112" height="40" rx="10" fill="none" stroke="#3a4d75" stroke-width="2" stroke-dasharray="6 5"/>` + text(72, 416, '+ New slide', 14, '#9fb0cc', 700, 'middle');
    // The slide: two charts above and one as wide as both below, the one chosen with the Chart Type tab on its edge.
    out += card(146, 20, 470, 300, '#ffffff', '#ffffff', 14);
    out += text(166, 52, 'Throughput by operator', 20, '#1b2234', 800);
    out += `<rect x="166" y="66" width="208" height="104" rx="8" fill="#f4f1fa"/>${cdf(166, 66, 208, 104)}`;
    out += `<rect x="388" y="66" width="208" height="104" rx="8" fill="#f4f1fa"/>${stacked(388, 66, 208, 104)}`;
    out += `<rect x="166" y="184" width="430" height="120" rx="8" fill="#f4f1fa" stroke="${p.accent}" stroke-width="4"/>${bars(166, 184, 400, 120, true)}`;
    out += `<rect x="568" y="196" width="28" height="96" rx="7" fill="${p.accent}"/><path d="M575 214 v8 M582 210 v12 M589 206 v16" stroke="#ffffff" stroke-width="3" stroke-linecap="round"/>`
      + `<text transform="translate(582 256) rotate(90)" font-size="11" font-weight="800" fill="#ffffff" text-anchor="middle">Chart Type</text>`;
    // Chart Type open beside it: the types by what they show, those the shelves cannot draw greyed.
    out += card(146, 336, 470, 204, '#0f1a30', p.accent, 14) + text(166, 364, 'Chart Type', 18, '#ffffff', 800);
    // (Small pictures of their own: the bars of the slide are drawn for wider places.)
    const miniBars = (x, y) => [0.5, 0.85, 0.4, 0.95].map((share, i) => `<rect x="${x + 10 + i * 14}" y="${y + 44 - share * 34}" width="10" height="${share * 34}" rx="2" fill="${i % 2 ? green : p.accent}"/>`).join('')
      + `<path d="M${x + 6} ${y + 24} H${x + 66}" stroke="${orange}" stroke-width="2.5" stroke-dasharray="5 4"/>`;
    const miniStacked = (x, y) => [0, 1, 2, 3].map((i) => `<rect x="${x + 10 + i * 14}" y="${y + 8}" width="10" height="18" rx="2" fill="${p.accent}"/><rect x="${x + 10 + i * 14}" y="${y + 26}" width="10" height="11" fill="${green}"/><rect x="${x + 10 + i * 14}" y="${y + 37}" width="10" height="7" rx="2" fill="${orange}"/>`).join('');
    const types = [['CDF', cdf, true], ['Bars', miniBars, true], ['Stacked', miniStacked, true], ['Scatter', null, false], ['Map', null, false]];
    types.forEach(([name, draw, ready], i) => {
      const x = 166 + i * 88, y = 378;
      out += card(x, y, 78, 74, i === 1 ? '#22304f' : '#16213a', i === 1 ? p.light : '#2a3a5c', 10);
      out += draw ? `<g opacity="${ready ? 1 : 0.35}">${draw(x + 4, y + 4, 70, 48)}</g>`
        : name === 'Scatter' ? [[18, 40], [30, 30], [40, 34], [52, 20], [62, 16]].map(([dx, dy]) => `<circle cx="${x + dx}" cy="${y + dy}" r="4" fill="#5a6a8a"/>`).join('')
          : `<path d="M${x + 39} ${y + 46} c0 -10 12 -16 12 -26 a12 12 0 0 0 -24 0 c0 10 12 16 12 26z" fill="#5a6a8a"/>`;
      out += text(x + 39, y + 68, name, 12, ready ? '#ffffff' : '#6b7a99', 700, 'middle');
    });
    out += `<rect x="166" y="466" width="430" height="58" rx="10" fill="#16213a"/>` + text(184, 492, 'Average Vertical Bars · ready with these fields', 15, '#ffffff', 700)
      + text(184, 512, 'Choosing a type closes the window', 13, '#9fb0cc', 500);
    // The panel: the shelves of the chart and what its type needs.
    out += card(632, 20, 172, 520, '#16213a', '#2a3a5c', 14);
    out += `<rect x="644" y="34" width="72" height="30" rx="8" fill="${p.accent}"/>` + text(680, 54, 'Data', 14, '#ffffff', 800, 'middle') + text(752, 54, 'Format', 14, '#9fb0cc', 700, 'middle');
    out += `<rect x="644" y="78" width="148" height="44" rx="8" fill="#183b2c"/><circle cx="660" cy="100" r="8" fill="${green}"/><path d="M656 100 l3 3 l6 -6" stroke="#ffffff" stroke-width="2" fill="none"/>`
      + text(674, 96, 'Average Bars', 12, '#ffffff', 800) + text(674, 112, 'needs a measure + split', 11, '#a8d5b9', 500);
    [['Measure', 'Data Rate', green], ['Rows', 'Operator', '#2D6FD1'], ['Columns', 'Campaign', '#2D6FD1'], ['Legend', 'Operator', '#2D6FD1']].forEach(([shelf, field, colour], i) => {
      const y = 140 + i * 64;
      out += text(646, y + 14, shelf.toUpperCase(), 11, '#9fb0cc', 800) + `<rect x="644" y="${y + 22}" width="148" height="30" rx="15" fill="${colour}"/>` + text(718, y + 42, field, 13, '#ffffff', 700, 'middle');
    });
    out += text(646, 412, 'FIELDS', 11, '#9fb0cc', 800);
    [['# Data Rate', green], ['Abc Operator', '#2D6FD1'], ['Abc City', '#2D6FD1'], ['# RSRP', green]].forEach(([field, colour], i) => {
      out += `<rect x="644" y="${422 + i * 28}" width="148" height="22" rx="6" fill="#22304f"/><rect x="644" y="${422 + i * 28}" width="5" height="22" rx="2" fill="${colour}"/>` + text(656, 438 + i * 28, field, 12, '#c9d4e6', 600);
    });
    return out;
  },
  // A PPT Template and the PPT Designs that follow it: each keeps only what it changes, a change of the template reaches
  // them all, and its parameters give a PPT per value in a Reporting Job.
  inheritance(p) {
    const card = (x, y, w, h, fill = '#16213a', stroke = '#2a3a5c', radius = 14) => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${radius}" fill="${fill}" stroke="${stroke}" stroke-width="2"/>`;
    const text = (x, y, value, size = 15, fill = '#c9d4e6', weight = 600, anchor = 'start') => `<text x="${x}" y="${y}" font-size="${size}" font-weight="${weight}" fill="${fill}" text-anchor="${anchor}">${escape(value)}</text>`;
    const pill = (x, y, label, fill, color = '#ffffff') => { const w = 18 + label.length * 8.2; return `<rect x="${x}" y="${y}" width="${w}" height="26" rx="13" fill="${fill}"/>${text(x + w / 2, y + 18, label, 13, color, 700, 'middle')}`; };
    const minis = (x, y, count, scale = 1) => [...Array(count).keys()].map((i) => {
      const sx = x + i * 66 * scale;
      return `<rect x="${sx}" y="${y}" width="${58 * scale}" height="${34 * scale}" rx="4" fill="${i === 0 ? p.deep : '#ffffff'}"/>`
        + (i ? [[4, 4, 23, 12], [30, 4, 24, 12], [4, 19, 50, 12]].map(([dx, dy, w, h]) => `<rect x="${sx + dx * scale}" y="${y + dy * scale}" width="${w * scale}" height="${h * scale}" rx="2" fill="${i === 2 ? '#d9cdf0' : '#e8e2f3'}"/>`).join('') : '');
    }).join('');
    let out = '';
    // The template.
    out += card(230, 16, 360, 150, '#22304f', p.accent, 16) + text(252, 46, 'PPT TEMPLATE', 13, p.light, 800) + text(252, 72, 'NetCheck CDR Report', 22, '#ffffff', 800);
    out += minis(252, 88, 5) + pill(252, 132, '{City}  parameter', p.deep);
    out += `<g transform="translate(470 132)">${pill(0, 0, 'Edited once', '#e8833a')}</g>`;
    // The Designs that follow it.
    const designs = [['NSA', 'Follows the template', '#1f9d55', []], ['SA', '+1 slide · 1 hidden', '#2D6FD1', ['A filter more']], ['Main Cities', 'City = London, Bristol', '#7b52c0', ['Its own values']]];
    designs.forEach(([name, change, colour, notes], i) => {
      const x = 20 + i * 268, y = 236;
      out += `<path d="M410 166 C410 200, ${x + 120} 200, ${x + 120} ${y}" fill="none" stroke="${p.light}" stroke-width="3" stroke-dasharray="8 6"/><path d="M${x + 112} ${y - 10} l8 10 l8 -10" fill="none" stroke="${p.light}" stroke-width="3"/>`;
      out += card(x, y, 240, 164) + text(x + 18, y + 30, 'PPT DESIGN', 12, '#9fb0cc', 800) + text(x + 18, y + 56, name, 21, '#ffffff', 800);
      out += minis(x + 18, y + 70, 3, 0.95) + pill(x + 18, y + 120, change, colour);
      notes.forEach((label) => { out += text(x + 222, y + 30, label, 12, '#c9d4e6', 600, 'end'); });
    });
    // A Reporting Job: One PPT per value of a parameter.
    out += card(20, 424, 780, 116, '#0f1a30', '#2a3a5c', 16) + text(42, 456, 'REPORTING JOB', 12, '#9fb0cc', 800) + text(42, 482, 'One PPT per City', 20, '#ffffff', 800)
      + text(42, 506, 'Each value of the parameter, its own PowerPoint', 14, '#9fb0cc', 500);
    [['London', 0], ['Bristol', 1], ['Cardiff', 2], ['Belfast', 3]].forEach(([city, i]) => {
      const x = 420 + i * 94;
      out += `<rect x="${x}" y="446" width="80" height="74" rx="10" fill="#ffffff"/><rect x="${x}" y="496" width="80" height="24" rx="0" fill="#d35230"/>`
        + `<path d="M${x} 506 v4 a10 10 0 0 0 10 10 h60 a10 10 0 0 0 10 -10 v-4" fill="#d35230"/>` + text(x + 40, 513, 'PPT', 13, '#ffffff', 800, 'middle') + text(x + 40, 478, city, 13, '#1b2234', 800, 'middle');
    });
    return out;
  },
  // Jobs and their status.
  jobs(p) {
    const rows = [['Q3 Voice report', 'Completed', p.accent], ['Q3 Data report', 'Completed', p.accent], ['PPT Design · London', 'Running', '#e0a020'], ['Q2 Speech report', 'Queued', '#3a4d75']];
    return rows.map(([name, status, colour], index) => {
      const y = 40 + index * 124;
      return `<rect x="20" y="${y}" width="780" height="100" rx="18" fill="#16213a" stroke="#2a3a5c" stroke-width="2"/><g transform="translate(46 ${y + 28})">${icon('TbFileTypePpt', p.light, 44)}</g>`
        + `<text x="116" y="${y + 60}" font-size="26" font-weight="700" fill="#ffffff">${name}</text><rect x="600" y="${y + 28}" width="170" height="44" rx="22" fill="${colour}"/><text x="685" y="${y + 58}" text-anchor="middle" font-size="22" font-weight="700" fill="#ffffff">${status}</text>`;
    }).join('');
  },
  // CDR files of every kind into one combined table, with its fixed and derived fields.
  tables(p) {
    let out = '';
    [['Final', 0], ['Weekly', 1], ['Daily', 2]].forEach(([name, index]) => {
      const y = 40 + index * 150;
      out += `<rect x="20" y="${y}" width="200" height="120" rx="16" fill="#16213a" stroke="#2a3a5c" stroke-width="2"/><text x="44" y="${y + 40}" font-size="22" font-weight="700" fill="#ffffff">${name}</text>`;
      for (let row = 0; row < 3; row += 1) out += `<rect x="44" y="${y + 58 + row * 18}" width="${140 - row * 24}" height="10" rx="5" fill="#3a4d75"/>`;
      out += `<path d="M228 ${y + 60} C 270 ${y + 60}, 270 280, 300 280" fill="none" stroke="${p.light}" stroke-width="4" opacity=".75"/>`;
    });
    out += `<rect x="300" y="60" width="500" height="440" rx="20" fill="#16213a" stroke="${p.accent}" stroke-width="3"/>`;
    out += `<text x="330" y="104" font-size="24" font-weight="800" fill="#ffffff">Combined CDR table</text>`;
    const columns = [['Campaign', false], ['Operator', false], ['RSRP', false], ['Region', true], ['Vendor', true]];
    columns.forEach(([name, derived], index) => {
      const x = 322 + index * 94;
      out += `<rect x="${x}" y="126" width="86" height="40" rx="8" fill="${derived ? p.accent : p.deep}"/><text x="${x + 43}" y="152" text-anchor="middle" font-size="16" font-weight="700" fill="#ffffff">${name}</text>`;
      for (let row = 0; row < 7; row += 1) out += `<rect x="${x + 8}" y="${182 + row * 36}" width="${70 - ((row + index) % 3) * 14}" height="14" rx="7" fill="${derived ? p.light : '#3a4d75'}" opacity="${derived ? 0.75 : 1}"/>`;
    });
    out += `<rect x="560" y="450" width="220" height="38" rx="19" fill="${p.accent}"/><text x="670" y="476" text-anchor="middle" font-size="18" font-weight="700" fill="#ffffff">Derived fields</text>`;
    return out;
  },
  // Campaign names into their labels, and the vendors in their colours and order.
  campaigns(p) {
    const rows = [['UK_Q1_2026', '2026-Q1', 'Assigned'], ['UK_Q2_SA_2026', '2026-Q2-SA', 'Assigned'], ['UK_Q3_2026', '2026-Q3', 'Assigned'],
      ['Drive_Extra_Leeds', 'Leeds Extra', 'Exception']];
    let out = `<text x="30" y="44" font-size="20" fill="#9fb0cc">In the CDRs</text><text x="470" y="44" font-size="20" fill="#9fb0cc">Label</text>`;
    rows.forEach(([name, label, status], index) => {
      const y = 64 + index * 78;
      out += `<rect x="20" y="${y}" width="330" height="58" rx="14" fill="#16213a" stroke="#2a3a5c" stroke-width="2"/><text x="44" y="${y + 37}" font-size="22" fill="#c9d4e6" class="mono">${name}</text>`;
      out += `<path d="M360 ${y + 29} H440" stroke="${p.light}" stroke-width="4"/><path d="M432 ${y + 20} l12 9 l-12 9" fill="none" stroke="${p.light}" stroke-width="4"/>`;
      out += `<rect x="460" y="${y}" width="200" height="58" rx="14" fill="${status === 'Exception' ? '#e0a020' : p.accent}"/><text x="560" y="${y + 37}" text-anchor="middle" font-size="22" font-weight="800" fill="#ffffff">${label}</text>`;
    });
    out += `<text x="30" y="420" font-size="20" fill="#9fb0cc">Vendors, in their order</text>`;
    [['Ericsson', '#0255AD'], ['Nokia', '#8C00FF'], ['Huawei', '#FBBD00'], ['Samsung', '#008521']].forEach(([name, colour], index) => {
      const x = 20 + index * 196;
      out += `<rect x="${x}" y="440" width="182" height="96" rx="16" fill="#16213a" stroke="#2a3a5c" stroke-width="2"/><rect x="${x + 18}" y="458" width="40" height="40" rx="10" fill="${colour}"/>`
        + `<text x="${x + 72}" y="486" font-size="22" font-weight="700" fill="#ffffff">${name}</text><text x="${x + 18}" y="522" font-size="18" fill="#9fb0cc">#${index + 1} in every chart</text>`;
    });
    return out;
  },
  // The universes pre-cached in the background, each ready to open at once.
  cache(p) {
    const rows = [['Every campaign', 1], ['Newest campaign', 1], ['Newest 2 campaigns', 1], ['Newest 3 campaigns', 0.7], ['Newest 4 campaigns', 0.35]];
    let out = `<g transform="translate(30 28)">${icon('TbBolt', p.light, 40)}</g><text x="82" y="58" font-size="24" font-weight="800" fill="#ffffff">Pre-cached in the background</text>`;
    rows.forEach(([name, share], index) => {
      const y = 92 + index * 76;
      out += `<rect x="20" y="${y}" width="780" height="60" rx="14" fill="#16213a" stroke="#2a3a5c" stroke-width="2"/><text x="44" y="${y + 38}" font-size="22" fill="#c9d4e6">${name}</text>`;
      out += `<rect x="330" y="${y + 22}" width="360" height="16" rx="8" fill="#22304f"/><rect x="330" y="${y + 22}" width="${360 * share}" height="16" rx="8" fill="${share === 1 ? p.accent : p.light}"/>`;
      out += share === 1 ? `<g transform="translate(724 ${y + 14})">${icon('TbCircleCheckFilled', '#5fbf3f', 32)}</g>` : `<text x="740" y="${y + 38}" text-anchor="middle" font-size="20" font-weight="700" fill="${p.light}">${Math.round(share * 100)}%</text>`;
    });
    out += `<rect x="20" y="482" width="370" height="56" rx="28" fill="#22304f"/><g transform="translate(44 494)">${icon('TbTrash', '#c9d4e6', 32)}</g><text x="92" y="518" font-size="21" font-weight="700" fill="#c9d4e6">Clear cache: results only</text>`;
    out += `<rect x="410" y="482" width="390" height="56" rx="28" fill="${p.accent}"/><g transform="translate(434 494)">${icon('TbPlayerPlayFilled', '#ffffff', 32)}</g><text x="482" y="518" font-size="21" font-weight="700" fill="#ffffff">Presentation mode</text>`;
    return out;
  },
  // A PowerPoint and a Word, fanned, with the job that builds them.
  exports(p, { files = [['TbFileTypePpt', '#d35230', 'PowerPoint'], ['TbFileTypeDocx', '#2b579a', 'Word']], job = 'Generation job', note = 'Template slides, comments and charts kept' } = {}) {
    let out = '';
    const first = (820 - (300 + 210 * (files.length - 1))) / 2;
    files.forEach(([name, colour, label], index) => {
      const x = first + index * 210; const y = 40 + (files.length - 1 - index) * 26; const tilt = (index - (files.length - 1) / 2) * 6;
      out += `<g transform="rotate(${tilt} ${x + 150} ${y + 190})"><rect x="${x}" y="${y}" width="300" height="380" rx="18" fill="#f4f6fb" stroke="#2a3a5c" stroke-width="2"/>`
        + `<rect x="${x}" y="${y}" width="300" height="70" rx="18" fill="${colour}"/><rect x="${x}" y="${y + 50}" width="300" height="20" fill="${colour}"/>`
        + `<g transform="translate(${x + 20} ${y + 14})">${icon(name, '#ffffff', 42)}</g><text x="${x + 74}" y="${y + 46}" font-size="22" font-weight="800" fill="#ffffff">${label}</text>`;
      for (let row = 0; row < 4; row += 1) {
        const top = y + 96 + row * 66;
        out += `<rect x="${x + 22}" y="${top}" width="110" height="52" rx="8" fill="#dfe5ef"/><rect x="${x + 146}" y="${top + 6}" width="${120 - row * 18}" height="12" rx="6" fill="#b8c3d6"/><rect x="${x + 146}" y="${top + 28}" width="${90 - row * 10}" height="10" rx="5" fill="#cfd7e4"/>`;
        out += `<rect x="${x + 30}" y="${top + 30}" width="14" height="16" fill="${colour}"/><rect x="${x + 50}" y="${top + 20}" width="14" height="26" fill="${colour}" opacity=".7"/><rect x="${x + 70}" y="${top + 12}" width="14" height="34" fill="${colour}" opacity=".5"/>`;
      }
      out += '</g>';
    });
    out += `<rect x="20" y="452" width="780" height="88" rx="18" fill="#16213a" stroke="#2a3a5c" stroke-width="2"/><text x="44" y="488" font-size="22" font-weight="700" fill="#ffffff">${escape(job)}</text>`
      + `<text x="776" y="488" text-anchor="end" font-size="19" fill="#9fb0cc">${escape(note)}</text>`
      + `<rect x="44" y="506" width="732" height="14" rx="7" fill="#22304f"/><rect x="44" y="506" width="540" height="14" rx="7" fill="${p.accent}"/>`;
    return out;
  },
  // A methodology: the weight of each KPI in each environment, and the calls it leaves out.
  weights(p) {
    const environments = ['City', 'Towns', 'Roads'];
    const kpis = [['Call success', [30, 26, 22]], ['Setup time', [12, 14, 10]], ['DL throughput', [24, 20, 16]], ['Video MOS', [14, 12, 18]], ['Browsing', [20, 28, 34]]];
    let out = `<rect x="20" y="20" width="250" height="50" rx="25" fill="${p.accent}"/><text x="145" y="53" text-anchor="middle" font-size="22" font-weight="800" fill="#ffffff">NetCheck 2026</text>`;
    environments.forEach((name, index) => { out += `<text x="${400 + index * 140}" y="104" text-anchor="middle" font-size="20" font-weight="700" fill="#9fb0cc">${name}</text>`; });
    kpis.forEach(([name, values], row) => {
      const y = 124 + row * 64;
      out += `<rect x="20" y="${y}" width="780" height="52" rx="12" fill="#16213a"/><text x="40" y="${y + 33}" font-size="21" fill="#c9d4e6">${name}</text>`;
      values.forEach((value, index) => {
        const x = 340 + index * 140;
        out += `<rect x="${x}" y="${y + 18}" width="120" height="16" rx="8" fill="#22304f"/><rect x="${x}" y="${y + 18}" width="${value * 3.4}" height="16" rx="8" fill="${index === 0 ? p.accent : p.light}"/>`;
      });
    });
    out += `<rect x="20" y="460" width="780" height="80" rx="16" fill="#2a1d2a" stroke="#e0533d" stroke-width="2" stroke-dasharray="8 6"/>`
      + `<g transform="translate(40 482)">${icon('TbCircleOff', '#ff8a80', 36)}</g><text x="92" y="508" font-size="22" font-weight="700" fill="#ff8a80">Excluded calls</text>`
      + `<text x="290" y="508" font-size="20" fill="#c9d4e6" class="mono">0x4F21A · 0x8C13E · 0x19B07</text>`;
    return out;
  },
  // The same chart in three themes, and the pills of the GAP.
  themes(p) {
    const themes = [['Ericsson', '#0b1220', ['#0082F0', '#0068BF', '#7DB8F0']], ['NetCheck', '#f4f6fb', ['#00A3AD', '#E4002B', '#7d8aa3']], ['Midnight', '#141a2e', ['#b46be8', '#5fbf3f', '#f0a830']]];
    let out = '';
    themes.forEach(([name, background, colours], index) => {
      const x = 20 + index * 268;
      out += `<rect x="${x}" y="20" width="248" height="300" rx="18" fill="${background}" stroke="#2a3a5c" stroke-width="2"/><text x="${x + 22}" y="58" font-size="22" font-weight="800" fill="${background === '#f4f6fb' ? '#1b2234' : '#ffffff'}">${name}</text>`;
      [120, 170, 90, 200].forEach((height, bar) => { out += `<rect x="${x + 30 + bar * 52}" y="${290 - height}" width="36" height="${height}" rx="6" fill="${colours[bar % 3]}"/>`; });
    });
    out += `<text x="20" y="372" font-size="20" fill="#9fb0cc">GAP pills</text>`;
    [['+3.2', '#1f9d55'], ['−1.4', '#e0533d'], ['+0.6', '#5fbf3f'], ['−4.8', '#c0392b']].forEach(([value, colour], index) => {
      out += `<rect x="${20 + index * 150}" y="392" width="130" height="54" rx="27" fill="${colour}"/><text x="${85 + index * 150}" y="428" text-anchor="middle" font-size="24" font-weight="800" fill="#ffffff">${value}</text>`;
    });
    out += `<rect x="620" y="392" width="180" height="54" rx="27" fill="#22304f"/><g transform="translate(640 403)">${icon('TbStarFilled', '#f0c040', 32)}</g><text x="682" y="428" font-size="21" font-weight="700" fill="#ffffff">Favourites</text>`;
    out += `<rect x="20" y="470" width="780" height="70" rx="16" fill="#16213a" stroke="#2a3a5c" stroke-width="2"/><g transform="translate(40 488)">${icon('TbReportAnalytics', p.light, 36)}</g><text x="92" y="514" font-size="22" font-weight="700" fill="#ffffff">Report scenarios: one click, every export</text>`;
    return out;
  },
  // A serving site, how far it served, and the 5G of its tests.
  serving(p) {
    let out = '<rect x="0" y="0" width="520" height="560" rx="16" fill="#101a2e"/>';
    [220, 150, 80].forEach((radius, index) => { out += `<circle cx="250" cy="300" r="${radius}" fill="none" stroke="#2a3a5c" stroke-width="2" stroke-dasharray="${index ? '8 8' : '0'}"/>`; });
    [['1 km', 80], ['3 km', 150], ['5 km', 220]].forEach(([label, radius]) => { out += `<text x="${250 + radius * 0.72}" y="${300 - radius * 0.72}" font-size="18" fill="#9fb0cc">${label}</text>`; });
    [[0, p.accent], [120, p.light], [240, p.series[2]]].forEach(([angle, colour]) => {
      const start = ((angle - 30) * Math.PI) / 180; const end = ((angle + 30) * Math.PI) / 180;
      out += `<path d="M250 300 L${(250 + 210 * Math.cos(start)).toFixed(1)} ${(300 + 210 * Math.sin(start)).toFixed(1)} A210 210 0 0 1 ${(250 + 210 * Math.cos(end)).toFixed(1)} ${(300 + 210 * Math.sin(end)).toFixed(1)} Z" fill="${colour}" opacity=".22"/>`;
    });
    for (let index = 0; index < 34; index += 1) {
      const angle = index * 2.4; const distance = 40 + ((index * 53) % 190);
      const colour = distance < 90 ? '#1f9d55' : distance < 160 ? '#c8d23a' : '#e0533d';
      out += `<circle cx="${(250 + distance * Math.cos(angle)).toFixed(1)}" cy="${(300 + distance * Math.sin(angle)).toFixed(1)}" r="7" fill="${colour}"/>`;
    }
    out += `<path d="M250 272 L268 314 L232 314 Z" fill="#ffffff" stroke="${INK}" stroke-width="3"/>`;
    const donut = (cx, cy, share, colour) => {
      const angle = share * 2 * Math.PI - Math.PI / 2;
      return `<circle cx="${cx}" cy="${cy}" r="62" fill="none" stroke="#22304f" stroke-width="22"/><path d="M${cx} ${cy - 62} A62 62 0 ${share > 0.5 ? 1 : 0} 1 ${(cx + 62 * Math.cos(angle)).toFixed(1)} ${(cy + 62 * Math.sin(angle)).toFixed(1)}" fill="none" stroke="${colour}" stroke-width="22" stroke-linecap="round"/>`;
    };
    out += `<rect x="540" y="0" width="280" height="270" rx="16" fill="#16213a" stroke="#2a3a5c" stroke-width="2"/>${donut(680, 120, 0.68, p.accent)}<text x="680" y="130" text-anchor="middle" font-size="30" font-weight="800" fill="#ffffff">68%</text><text x="680" y="236" text-anchor="middle" font-size="21" font-weight="700" fill="#c9d4e6">5G availability</text>`;
    out += `<rect x="540" y="290" width="280" height="120" rx="16" fill="#16213a" stroke="#2a3a5c" stroke-width="2"/><text x="562" y="336" font-size="20" fill="#9fb0cc">NR cell · MIMO</text><text x="562" y="384" font-size="34" font-weight="800" fill="#ffffff">n78 · 4×4</text>`;
    out += `<rect x="540" y="430" width="280" height="130" rx="16" fill="#16213a" stroke="#2a3a5c" stroke-width="2"/><text x="562" y="474" font-size="20" fill="#9fb0cc">Host network</text><rect x="562" y="494" width="110" height="40" rx="20" fill="#E60000"/><text x="617" y="521" text-anchor="middle" font-size="20" font-weight="700" fill="#ffffff">VF</text><rect x="684" y="494" width="110" height="40" rx="20" fill="#2D8AE6"/><text x="739" y="521" text-anchor="middle" font-size="20" font-weight="700" fill="#ffffff">3</text>`;
    return out;
  },
  // What an account can do, see and open: its role, its Modules Profile and its workspaces.
  access(p) {
    let out = `<rect x="20" y="20" width="780" height="120" rx="18" fill="#16213a" stroke="#2a3a5c" stroke-width="2"/><text x="44" y="58" font-size="20" fill="#9fb0cc">Role · what it does</text>`;
    [['user-viewer', '#3a4d75'], ['user-editor', p.deep], ['admin', p.light], ['super-admin', p.accent]].forEach(([role, colour], index) => {
      out += `<rect x="${44 + index * 186}" y="76" width="172" height="44" rx="22" fill="${colour}"${index === 2 ? ' stroke="#ffffff" stroke-width="3"' : ''}/><text x="${130 + index * 186}" y="105" text-anchor="middle" font-size="19" font-weight="700" fill="#ffffff">${role}</text>`;
    });
    out += `<rect x="20" y="156" width="780" height="140" rx="18" fill="#16213a" stroke="#2a3a5c" stroke-width="2"/><text x="44" y="194" font-size="20" fill="#9fb0cc">Modules Profile · what it sees</text>`;
    [['Workspace', '#08736D'], ['Scoring & GAP', '#176E77'], ['Network Insights', '#4F46E5'], ['NQ Calls', '#B0234F'], ['Reporting', '#2E8C58'], ['Builders', '#B85B20']].forEach(([name, colour], index) => {
      const x = 44 + (index % 3) * 250; const y = 212 + Math.floor(index / 3) * 40;
      out += `<rect x="${x}" y="${y}" width="236" height="32" rx="10" fill="${colour}"/><text x="${x + 118}" y="${y + 22}" text-anchor="middle" font-size="17" font-weight="700" fill="#ffffff">${name}</text>`;
    });
    out += `<rect x="20" y="312" width="780" height="120" rx="18" fill="#16213a" stroke="#2a3a5c" stroke-width="2"/><text x="44" y="350" font-size="20" fill="#9fb0cc">Workspaces · what it opens</text>`;
    out += `<rect x="44" y="368" width="300" height="44" rx="12" fill="${p.accent}"/><text x="64" y="397" font-size="19" font-weight="700" fill="#ffffff">Group UK: UK · UK-SA</text>`;
    out += `<text x="362" y="398" font-size="28" font-weight="800" fill="${p.light}">+</text><rect x="392" y="368" width="200" height="44" rx="12" fill="#22304f" stroke="${p.light}" stroke-width="2"/><text x="412" y="397" font-size="19" font-weight="700" fill="#ffffff">Individual: DE</text>`;
    out += `<rect x="20" y="452" width="780" height="88" rx="18" fill="#2a2a1d" stroke="#e0a020" stroke-width="2" stroke-dasharray="8 6"/><g transform="translate(42 476)">${icon('TbUserPlus', '#f0c040', 40)}</g>`
      + `<text x="98" y="490" font-size="22" font-weight="800" fill="#ffffff">Access request · EUSER05</text><text x="98" y="520" font-size="19" fill="#c9d4e6">Inactive until a super-admin activates it</text>`;
    return out;
  },
  // A week of scheduled backups, light and full, their folders and what is kept.
  backups(p) {
    const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    let out = `<rect x="20" y="20" width="780" height="210" rx="18" fill="#16213a" stroke="#2a3a5c" stroke-width="2"/><text x="44" y="58" font-size="20" fill="#9fb0cc">Every 4 hours · light, and full on Sunday</text>`;
    days.forEach((day, index) => {
      const x = 60 + index * 104;
      out += `<text x="${x + 30}" y="210" text-anchor="middle" font-size="18" fill="#9fb0cc">${day}</text>`;
      for (let slot = 0; slot < 6; slot += 1) {
        const full = index === 6 && slot === 0;
        out += `<rect x="${x + (slot % 3) * 22}" y="${80 + Math.floor(slot / 3) * 50}" width="${full ? 64 : 16}" height="${full ? 90 : 40}" rx="5" fill="${full ? p.accent : p.light}" opacity="${full ? 1 : 0.6}"/>`;
        if (full) break;
      }
    });
    [['full/', p.accent, 'Full backups', 'databases, Input, Output'], ['light/', p.light, 'Light backups', 'without the databases']].forEach(([folder, colour, title, text], index) => {
      const x = 20 + index * 396;
      out += `<rect x="${x}" y="250" width="384" height="130" rx="18" fill="#16213a" stroke="#2a3a5c" stroke-width="2"/><g transform="translate(${x + 22} 272)">${icon('TbFolderFilled', colour, 52)}</g>`
        + `<text x="${x + 88}" y="300" font-size="24" font-weight="800" fill="#ffffff">${title}</text><text x="${x + 88}" y="330" font-size="19" fill="#c9d4e6">${folder} · ${text}</text>`
        + `<text x="${x + 88}" y="362" font-size="18" fill="#9fb0cc" class="mono">backup_2026-10-25.zip</text>`;
    });
    out += `<rect x="20" y="400" width="780" height="140" rx="18" fill="#16213a" stroke="#2a3a5c" stroke-width="2"/><text x="44" y="438" font-size="20" fill="#9fb0cc">Kept</text>`;
    [['7 days', 0.35], ['4 weeks', 0.6], ['6 months', 1]].forEach(([label, share], index) => {
      out += `<rect x="44" y="${456 + index * 26}" width="${560 * share}" height="16" rx="8" fill="${index === 2 ? p.accent : p.light}"/><text x="${56 + 560 * share}" y="${470 + index * 26}" font-size="18" font-weight="700" fill="#ffffff">${label}</text>`;
    });
    out += `<g transform="translate(700 436)">${icon('TbRestore', p.light, 64)}</g>`;
    return out;
  },
  // A package from one server to another, previewed before it is imported.
  servers(p) {
    const server = (x, title) => `<rect x="${x}" y="40" width="200" height="250" rx="18" fill="#16213a" stroke="#2a3a5c" stroke-width="2"/>`
      + [0, 1, 2].map((row) => `<rect x="${x + 22}" y="${70 + row * 62}" width="156" height="44" rx="10" fill="#22304f"/><circle cx="${x + 44}" cy="${92 + row * 62}" r="7" fill="${row === 0 ? '#5fbf3f' : p.light}"/><rect x="${x + 62}" y="${86 + row * 62}" width="92" height="12" rx="6" fill="#3a4d75"/>`).join('')
      + `<text x="${x + 100}" y="320" text-anchor="middle" font-size="21" font-weight="700" fill="#ffffff">${title}</text>`;
    let out = server(20, 'This server') + server(600, 'Another server');
    out += `<path d="M232 150 H588" stroke="${p.light}" stroke-width="5" stroke-dasharray="12 9"/><path d="M576 138 l14 12 l-14 12" fill="none" stroke="${p.light}" stroke-width="5"/>`;
    out += `<rect x="306" y="104" width="208" height="92" rx="14" fill="${p.accent}"/><g transform="translate(324 124)">${icon('TbFileZip', '#ffffff', 44)}</g><text x="380" y="146" font-size="20" font-weight="800" fill="#ffffff">Package</text><text x="380" y="174" font-size="17" fill="#ffffff">Workspace UK</text>`;
    out += `<text x="410" y="236" text-anchor="middle" font-size="18" fill="#9fb0cc">Super-admins approve it</text>`;
    out += `<rect x="20" y="350" width="780" height="190" rx="18" fill="#16213a" stroke="#2a3a5c" stroke-width="2"/><text x="44" y="388" font-size="20" fill="#9fb0cc">Preview before Import</text>`;
    [['PPT Designs', '3 added · 2 changed', '#1f9d55'], ['PPT Templates', '1 changed', '#f0a830'], ['NQ Call Tracking', 'unchanged', '#7d8aa3']].forEach(([name, change, colour], index) => {
      const y = 404 + index * 42;
      out += `<rect x="44" y="${y}" width="732" height="34" rx="10" fill="#22304f"/><circle cx="64" cy="${y + 17}" r="7" fill="${colour}"/><text x="82" y="${y + 23}" font-size="18" font-weight="700" fill="#ffffff">${name}</text><text x="756" y="${y + 23}" text-anchor="end" font-size="17" fill="#c9d4e6">${change}</text>`;
    });
    return out;
  },
  // App Events: who did what, from where, and the details of each change, with their filters.
  events(p) {
    let out = '';
    [['Date: Today', p.deep], ['Type: Info · Error', p.deep], ['Action: exclude sign-in', '#22304f']].forEach(([label, colour], index) => {
      out += `<rect x="${20 + index * 262}" y="20" width="250" height="44" rx="22" fill="${colour}" stroke="${p.light}" stroke-width="2"/><text x="${145 + index * 262}" y="48" text-anchor="middle" font-size="18" font-weight="700" fill="#ffffff">${label}</text>`;
    });
    const rows = [
      ['14:02', 'super', p.accent, 'Super Admin', 'save_user', 'User EUSER01: role user-viewer → user-editor; Groups +UK', false],
      ['13:55', 'System', '#e0533d', 'Scheduler', 'scheduled_database_backup', 'Light backup of 3 workspaces, 2.1 GB in 48 s', false],
      ['13:40', 'analyst', p.accent, 'NQ Calls', 'nq_call_map', 'Map of 0x4F21A: 2 hints to check, prepared in 1.2 s', false],
      ['13:31', 'System', '#e0533d', 'Background job', 'process_dataset_failed', 'CDR Voice Q3: the column Call_Status is missing', true],
    ];
    rows.forEach(([time, user, colour, module, action, details, error], index) => {
      const y = 84 + index * 116;
      out += `<rect x="20" y="${y}" width="780" height="102" rx="16" fill="${error ? '#2a1d22' : '#16213a'}" stroke="${error ? '#e0533d' : '#2a3a5c'}" stroke-width="2"/>`;
      out += `<text x="42" y="${y + 38}" font-size="20" font-weight="700" fill="#9fb0cc">${time}</text>`;
      out += `<rect x="108" y="${y + 16}" width="${user.length * 12 + 34}" height="32" rx="16" fill="${colour}"/><text x="${125 + user.length * 6}" y="${y + 38}" text-anchor="middle" font-size="17" font-weight="800" fill="#ffffff">${user}</text>`;
      out += `<rect x="${154 + user.length * 12}" y="${y + 16}" width="${module.length * 11 + 30}" height="32" rx="10" fill="#22304f"/><text x="${169 + user.length * 12}" y="${y + 38}" font-size="17" font-weight="700" fill="#c9d4e6">${module}</text>`;
      out += `<text x="776" y="${y + 38}" text-anchor="end" font-size="16" fill="${error ? '#ff8a80' : p.light}" class="mono">${action}</text>`;
      out += `<text x="42" y="${y + 80}" font-size="19" fill="#ffffff">${escape(details)}</text>`;
    });
    return out;
  },
  // The Users table of Super Admin: filters, the bar of the selected users and each account edited in place.
  users(p) {
    let out = `<rect x="20" y="20" width="420" height="44" rx="22" fill="#16213a" stroke="#2a3a5c" stroke-width="2"/><g transform="translate(36 30)">${icon('TbSearch', '#9fb0cc', 24)}</g><text x="70" y="49" font-size="18" fill="#9fb0cc">Search a name or username</text>`
      + `<rect x="452" y="20" width="348" height="44" rx="22" fill="#2a2a1d" stroke="#e0a020" stroke-width="2"/><text x="626" y="49" text-anchor="middle" font-size="18" font-weight="700" fill="#f0c040">Pending access requests · 2</text>`;
    out += `<rect x="20" y="80" width="780" height="54" rx="14" fill="${p.accent}"/><text x="40" y="114" font-size="19" font-weight="800" fill="#ffffff">3 selected</text>`;
    let x = 158;
    ['Modules Profile…', 'Add to group…', 'Role…', 'Activate', 'Deactivate'].forEach((label) => {
      const width = label.length * 9 + 24;
      out += `<rect x="${x}" y="91" width="${width}" height="32" rx="16" fill="#ffffff" opacity=".18"/><text x="${x + width / 2}" y="113" text-anchor="middle" font-size="16" font-weight="700" fill="#ffffff">${label}</text>`;
      x += width + 10;
    });
    const rows = [
      ['User A', 'EUSER01', 'admin', '#B0234F', ['UK', 'DE'], true, true],
      ['User B', 'EUSER02', 'user-editor', '#08736D', ['UK'], true, true],
      ['User C', 'EUSER03', 'user-viewer', '#4F46E5', ['DE'], true, false],
      ['User D', 'EUSER04', 'user-editor', '#08736D', ['UK'], false, false],
    ];
    rows.forEach(([name, username, role, profile, groups, active, selected], index) => {
      const y = 150 + index * 98;
      out += `<rect x="20" y="${y}" width="780" height="86" rx="14" fill="#16213a" stroke="${selected ? p.light : '#2a3a5c'}" stroke-width="2"/>`;
      out += `<rect x="38" y="${y + 30}" width="26" height="26" rx="6" fill="${selected ? p.accent : 'none'}" stroke="${selected ? p.accent : '#7d8aa3'}" stroke-width="2"/>${selected ? `<path d="M44 ${y + 43} l6 6 l10 -12" fill="none" stroke="#ffffff" stroke-width="3"/>` : ''}`;
      out += `<text x="80" y="${y + 40}" font-size="20" font-weight="800" fill="#ffffff">${name}</text><text x="80" y="${y + 66}" font-size="16" fill="#9fb0cc" class="mono">${username}</text>`;
      out += `<rect x="252" y="${y + 26}" width="132" height="34" rx="10" fill="#22304f"/><text x="318" y="${y + 49}" text-anchor="middle" font-size="16" font-weight="700" fill="#ffffff">${role}</text>`;
      out += `<circle cx="412" cy="${y + 43}" r="12" fill="${profile}"/>`;
      groups.forEach((group, g) => { out += `<rect x="${440 + g * 66}" y="${y + 26}" width="56" height="34" rx="10" fill="${p.deep}"/><text x="${468 + g * 66}" y="${y + 49}" text-anchor="middle" font-size="16" font-weight="700" fill="#ffffff">${group}</text>`; });
      out += `<rect x="600" y="${y + 28}" width="58" height="30" rx="15" fill="${active ? '#1f9d55' : '#3a4d75'}"/><circle cx="${active ? 643 : 615}" cy="${y + 43}" r="11" fill="#ffffff"/>`;
      out += `<g transform="translate(690 ${y + 28})">${icon('TbKey', '#c9d4e6', 30)}</g><g transform="translate(740 ${y + 28})">${icon('TbTrash', '#c9d4e6', 30)}</g>`;
    });
    return out;
  },
  // The databases of the application and of each workspace, and the Database Viewer on one of their tables.
  databases(p) {
    const cylinder = (x, y, title, colour, tables) => `<ellipse cx="${x + 110}" cy="${y + 22}" rx="110" ry="22" fill="${colour}"/><rect x="${x}" y="${y + 22}" width="220" height="${36 + tables.length * 36}" fill="${colour}" opacity=".85"/>`
      + `<ellipse cx="${x + 110}" cy="${y + 58 + tables.length * 36}" rx="110" ry="22" fill="${colour}" opacity=".85"/><text x="${x + 110}" y="${y + 50}" text-anchor="middle" font-size="19" font-weight="800" fill="#ffffff">${title}</text>`
      + tables.map((table, index) => `<rect x="${x + 18}" y="${y + 64 + index * 36}" width="184" height="28" rx="8" fill="#0b1220" opacity=".55"/><text x="${x + 110}" y="${y + 83 + index * 36}" text-anchor="middle" font-size="15" fill="#ffffff">${table}</text>`).join('');
    let out = cylinder(20, 20, 'Application', '#5b6b80', ['Users', 'Modules Profiles', 'Workspace Groups', 'Tickets']);
    out += cylinder(20, 300, 'Workspace UK', p.deep, ['Datasets', 'PPT Designs', 'NQ Call Tracking', 'Combined CDR rows']);
    out += `<rect x="270" y="20" width="530" height="520" rx="18" fill="#16213a" stroke="#2a3a5c" stroke-width="2"/><text x="294" y="58" font-size="20" font-weight="800" fill="#ffffff">Database Viewer</text>`;
    out += `<rect x="294" y="74" width="300" height="38" rx="10" fill="#22304f"/><text x="310" y="99" font-size="17" fill="#c9d4e6">Table: Operator Mappings</text><rect x="604" y="74" width="172" height="38" rx="19" fill="${p.accent}"/><text x="690" y="99" text-anchor="middle" font-size="16" font-weight="700" fill="#ffffff">Operator = VF</text>`;
    const columns = ['source_value', 'canonical_value'];
    columns.forEach((name, index) => { out += `<rect x="${294 + index * 244}" y="126" width="236" height="36" rx="8" fill="${p.deep}"/><text x="${306 + index * 244}" y="150" font-size="16" font-weight="700" fill="#ffffff" class="mono">${name}</text>`; });
    [['Vodafone UK', 'VF'], ['VFUK', 'VF'], ['Vodafone', 'VF'], ['Vodafone SA', 'VF SA'], ['Vodafone VoNR', 'VF VoNR']].forEach(([source, label], row) => {
      const y = 172 + row * 50;
      out += `<rect x="294" y="${y}" width="480" height="42" rx="8" fill="${row === 1 ? '#22304f' : '#101a2e'}"/><text x="306" y="${y + 27}" font-size="17" fill="#c9d4e6">${source}</text><text x="550" y="${y + 27}" font-size="17" font-weight="700" fill="#ffffff">${label}</text>`;
      if (row === 1) out += `<g transform="translate(728 ${y + 8})">${icon('TbPencil', p.light, 26)}</g>`;
    });
    out += `<text x="294" y="456" font-size="17" fill="#9fb0cc">100 rows a page</text>`;
    ['First', 'Previous', 'Next', 'Last'].forEach((label, index) => { out += `<rect x="${294 + index * 120}" y="476" width="110" height="40" rx="20" fill="#22304f"/><text x="${349 + index * 120}" y="502" text-anchor="middle" font-size="16" font-weight="700" fill="#c9d4e6">${label}</text>`; });
    return out;
  },
  // The follow-up over the weeks, and the NQ rate of each operator.
  trend(p) {
    const weeks = ['W1', 'W2', 'W3', 'W4', 'W5', 'W6', 'W7', 'W8'];
    const series = [['New', '#e0533d', [60, 52, 44, 40, 30, 24, 18, 12]], ['In progress', '#f0a830', [20, 34, 40, 38, 36, 30, 24, 18]], ['Closed', '#1f9d55', [4, 10, 22, 36, 52, 66, 80, 94]]];
    let out = `<rect x="20" y="20" width="780" height="330" rx="18" fill="#16213a" stroke="#2a3a5c" stroke-width="2"/>`;
    weeks.forEach((week, index) => { out += `<text x="${80 + index * 92}" y="336" text-anchor="middle" font-size="18" fill="#9fb0cc">${week}</text>`; });
    series.forEach(([name, colour, values], index) => {
      out += `<polyline points="${values.map((value, x) => `${80 + x * 92},${310 - value * 2.6}`).join(' ')}" fill="none" stroke="${colour}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>`;
      out += `<circle cx="${80 + 7 * 92}" cy="${310 - values[7] * 2.6}" r="9" fill="${colour}"/><rect x="${44 + index * 200}" y="40" width="20" height="20" rx="5" fill="${colour}"/><text x="${72 + index * 200}" y="57" font-size="20" fill="#c9d4e6">${name}</text>`;
    });
    out += `<text x="20" y="396" font-size="20" fill="#9fb0cc">NQ rate per operator</text>`;
    [['A', 2.1], ['B', 3.4], ['C', 1.6], ['D', 4.2]].forEach(([name, rate], index) => {
      const x = 20 + index * 198;
      out += `<rect x="${x}" y="414" width="180" height="126" rx="16" fill="#16213a" stroke="#2a3a5c" stroke-width="2"/><text x="${x + 20}" y="452" font-size="20" fill="#9fb0cc">Operator ${name}</text>`
        + `<text x="${x + 20}" y="502" font-size="36" font-weight="800" fill="${rate > 3 ? '#ff8a80' : '#ffffff'}">${rate.toFixed(1)}%</text><rect x="${x + 20}" y="516" width="140" height="10" rx="5" fill="#22304f"/><rect x="${x + 20}" y="516" width="${rate * 30}" height="10" rx="5" fill="${rate > 3 ? '#e0533d' : p.accent}"/>`;
    });
    return out;
  },
  // Generated comments: the figures of a chart become facts, the rules (or an LLM writer) write them, every figure is
  // checked and the comment lands on the slide.
  comments(p) {
    const arrow = (x1, y1, x2, y2) => `<path d="M${x1} ${y1} L${x2} ${y2}" stroke="${p.light}" stroke-width="4" stroke-dasharray="9 8"/>`
      + `<circle cx="${x2}" cy="${y2}" r="7" fill="${p.accent}" stroke="#ffffff" stroke-width="3"/>`;
    const curve = (median, color) => {
      const points = [];
      for (let x = 0; x <= 270; x += 6) points.push(`${44 + x},${186 - 118 / (1 + Math.exp(-(x - median) / 22))}`);
      return `<polyline points="${points.join(' ')}" fill="none" stroke="${color}" stroke-width="5" stroke-linecap="round"/>`;
    };
    let out = `<rect x="20" y="20" width="330" height="190" rx="18" fill="#16213a" stroke="#2a3a5c" stroke-width="2"/>`
      + `<text x="44" y="54" font-size="20" font-weight="700" fill="#c9d4e6">NR RSRP · CDF</text>`
      + `<line x1="44" y1="127" x2="326" y2="127" stroke="#2a3a5c" stroke-width="2" stroke-dasharray="6 7"/>`
      + curve(90, p.series[2]) + curve(140, p.series[1]) + curve(190, p.accent);
    out += arrow(350, 115, 382, 115)
      + `<rect x="390" y="20" width="410" height="190" rx="18" fill="#16213a" stroke="#2a3a5c" stroke-width="2"/>`
      + `<text x="414" y="54" font-size="20" font-weight="700" fill="#c9d4e6">Facts from the chart</text>`;
    ['P50 −93.8 dBm', '+3.8 dB vs 2026-Q2', '5.1% below −110 dBm'].forEach((fact, index) => {
      out += `<rect x="414" y="${72 + index * 44}" width="${index === 1 ? 250 : 290}" height="34" rx="17" fill="${index === 1 ? p.accent : '#22304f'}"/>`
        + `<text x="432" y="${95 + index * 44}" font-size="19" font-weight="700" fill="#ffffff">${fact}</text>`;
    });
    out += arrow(205, 210, 205, 236) + arrow(605, 210, 605, 236);
    out += `<rect x="20" y="244" width="370" height="104" rx="18" fill="${p.deep}" stroke="${p.accent}" stroke-width="2"/>`
      + `<g transform="translate(44 272)">${icon('TbListCheck', '#ffffff', 46)}</g>`
      + `<text x="108" y="290" font-size="26" font-weight="800" fill="#ffffff">Rules</text>`
      + `<text x="108" y="322" font-size="19" fill="${p.light}">always on · on the server</text>`;
    out += `<rect x="410" y="244" width="390" height="104" rx="18" fill="#16213a" stroke="${p.light}" stroke-width="2"/>`
      + `<g transform="translate(434 272)">${icon('TbSparkles', p.light, 46)}</g>`
      + `<text x="498" y="290" font-size="26" font-weight="800" fill="#ffffff">LLM writer</text>`
      + `<rect x="498" y="304" width="86" height="28" rx="14" fill="${p.accent}"/><text x="541" y="324" text-anchor="middle" font-size="17" font-weight="800" fill="#ffffff">Kiro</text>`
      + `<rect x="594" y="304" width="96" height="28" rx="14" fill="#22304f"/><text x="642" y="324" text-anchor="middle" font-size="17" font-weight="800" fill="#ffffff">Claude</text>`;
    out += arrow(205, 348, 268, 380) + arrow(605, 348, 552, 380)
      + `<rect x="270" y="364" width="280" height="44" rx="22" fill="#1f9d55"/>`
      + `<g transform="translate(290 372)">${icon('TbShieldCheck', '#ffffff', 28)}</g>`
      + `<text x="328" y="393" font-size="19" font-weight="800" fill="#ffffff">every figure checked</text>`;
    out += arrow(410, 408, 410, 426)
      + `<rect x="20" y="432" width="780" height="110" rx="18" fill="#f4f6fb"/>`
      + `<rect x="44" y="446" width="112" height="26" rx="13" fill="${p.accent}"/><text x="100" y="465" text-anchor="middle" font-size="15" font-weight="800" fill="#ffffff">Generated</text>`
      + `<text x="170" y="465" font-size="16" fill="#5b6478">Slide comments · review, edit, add</text>`;
    ['Operator A median NR RSRP improves by 3.8 dB vs 2026-Q2.', 'Operator B leads; the gap to Operator A narrows from 7.2 to 3.7 dB.'].forEach((line, index) => {
      out += `<circle cx="50" cy="${494 + index * 30}" r="5" fill="${p.accent}"/><text x="66" y="${500 + index * 30}" font-size="19" fill="${INK}">${escape(line)}</text>`;
    });
    return out;
  },
  // The header of Ticket Center (1656 × 560): its tiles and the tabs of its views, each joined to a card that tells what
  // it shows (views: [{ icon, title, text }], a \n in the text starting its second line).
  ticketHeader(p, { views = [] } = {}) {
    let out = `<defs><linearGradient id="ticket-hero" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#7f1d1d"/><stop offset="1" stop-color="#ef4444"/></linearGradient></defs>`
      + `<rect x="0" y="0" width="1656" height="318" rx="24" fill="url(#ticket-hero)"/>`;
    // The ticket drawn faint at its right, as in the tool.
    out += `<g opacity=".2" transform="translate(1250 92)"><path d="M0 14 a14 14 0 0 1 14 -14 H306 a14 14 0 0 1 14 14 V46 a20 20 0 0 0 0 40 V118 a14 14 0 0 1 -14 14 H14 a14 14 0 0 1 -14 -14 V86 a20 20 0 0 0 0 -40 Z" fill="none" stroke="#ffffff" stroke-width="5"/>`
      + `<path d="M64 42 H230 M64 68 H256 M64 94 H190" stroke="#ffffff" stroke-width="8" stroke-linecap="round"/></g>`;
    out += tcText(40, 48, 'TICKET CENTER', 14, '#ffe9e9', 700, 'start', ' letter-spacing="3"')
      + tcText(40, 100, 'Report bugs, suggest improvements and ask for new features', 38, '#ffffff', 800)
      + tcText(40, 136, 'Open a ticket of its type with what happened or what you need, its screenshots and files, and follow it until it is resolved.', 18, '#ffe9e9', 500);
    out += `<rect x="1430" y="26" width="190" height="46" rx="23" fill="#ffffff"/>${tcIcon('TbTicket', 1454, 38, TC.wine, 22)}` + tcText(1486, 56, 'New Ticket', 17, TC.wine, 800);
    [['Open', '22', TC.status.open], ['New', '8', TC.status.new], ['In Progress', '13', TC.status.progress], ['Waiting for Info', '1', TC.status.waiting],
      ['Resolved · 30 days', '21', TC.status.resolved]].forEach(([label, value, colour], index) => {
      const x = 40 + index * 318;
      out += `<rect x="${x}" y="158" width="302" height="74" rx="14" fill="#ffffff"/><rect x="${x}" y="168" width="4" height="54" rx="2" fill="${colour}"/>`
        + tcText(x + 22, 186, label.toUpperCase(), 12, TC.muted, 800, 'start', ' letter-spacing="1.2"') + tcText(x + 22, 218, value, 28, TC.ink, 800);
    });
    // The tabs, Dashboard chosen.
    const tabs = [['TbTicket', 'New Ticket', 158], ['TbTable', 'All Tickets', 178, '60'], ['TbLayoutDashboard', 'Dashboard', 156], ['TbChartBar', 'Statistics', 146], ['TbClock', 'Time Spent', 156]];
    out += `<rect x="40" y="252" width="${tabs.reduce((sum, tab) => sum + tab[2] + 4, 8)}" height="46" rx="14" fill="#ffffff" fill-opacity=".14" stroke="#ffffff" stroke-opacity=".3"/>`;
    const centres = [];
    let left = 46;
    tabs.forEach(([name, label, width, count], index) => {
      const colour = index === 2 ? TC.wine : '#ffffff';
      if (index === 2) out += `<rect x="${left}" y="258" width="${width}" height="34" rx="10" fill="#ffffff"/>`;
      out += tcIcon(name, left + 14, 266, colour, 18) + tcText(left + 40, 281, label, 15, colour, 700);
      if (count) out += `<rect x="${left + width - 40}" y="265" width="30" height="20" rx="10" fill="#ffffff" fill-opacity=".25"/>` + tcText(left + width - 25, 279, count, 12, '#ffffff', 800, 'middle');
      centres.push(left + width / 2);
      left += width + 4;
    });
    views.forEach((_view, index) => {
      const centre = index * 336 + 156;
      out += `<path d="M${centres[index]} 298 C${centres[index]} 344, ${centre} 326, ${centre} 372" fill="none" stroke="${p.light}" stroke-width="3" stroke-dasharray="8 7" opacity=".85"/>`;
    });
    views.forEach((view, index) => {
      const x = index * 336;
      out += `<rect x="${x}" y="372" width="312" height="188" rx="18" fill="#16213a" stroke="${index === 2 ? p.accent : '#2a3a5c'}" stroke-width="2"/>`
        + `<rect x="${x + 22}" y="394" width="52" height="52" rx="14" fill="${p.accent}"/>${tcIcon(view.icon, x + 34, 406, '#ffffff', 28)}`
        + `<text x="${x + 90}" y="428" font-size="22" font-weight="700" fill="${p.light}" class="mono">${String(index + 1).padStart(2, '0')}</text>`
        + tcText(x + 22, 482, view.title, 24, '#ffffff', 800) + tcLines(x + 22, 512, view.text, 17, '#c9d4e6', 500, 23)
        + `<circle cx="${x + 156}" cy="372" r="7" fill="${p.accent}" stroke="#ffffff" stroke-width="3"/><circle cx="${centres[index]}" cy="298" r="5" fill="#ffffff"/>`;
    });
    return out;
  },
  // The form of a new ticket while signed out (820 × 560): dimmed, with its note and Sign in.
  ticketForm() {
    let out = `<rect x="0" y="0" width="820" height="560" rx="16" fill="${TC.page}"/>`;
    const label = (x, y, value) => tcText(x, y, value.toUpperCase(), 11, TC.muted, 800, 'start', ' letter-spacing="1"');
    out += label(16, 104, 'Type') + tcText(62, 104, 'required', 11, TC.red, 700);
    [['TbBug', 'Bug', 'Something does not work as it should', TC.type.bug], ['TbTrendingUp', 'Improvement', 'Something that works could work better', TC.type.improvement],
      ['TbSparkles', 'New Feature', 'Something the tool cannot do yet', TC.type.feature]].forEach(([name, title, text, colour], index) => {
      const x = 16 + index * 268;
      out += `<rect x="${x}" y="112" width="252" height="54" rx="12" fill="${index ? TC.card : mix(colour, '#ffffff', 0.92)}" stroke="${index ? TC.line : colour}" stroke-width="${index ? 1.5 : 2}"/>`
        + tcIcon(name, x + 14, 129, colour, 20) + tcText(x + 44, 136, title, 15, colour, 800) + tcText(x + 44, 154, text, 10.5, TC.muted, 500);
    });
    out += label(16, 190, 'Title') + label(552, 190, 'Module');
    out += `<rect x="16" y="198" width="520" height="36" rx="9" fill="${TC.card}" stroke="${TC.line}" stroke-width="1.5"/>` + tcText(30, 221, 'Map export stops on large CDRs', 14, TC.ink, 500)
      + `<rect x="552" y="198" width="252" height="36" rx="9" fill="${TC.card}" stroke="${TC.line}" stroke-width="1.5"/>` + tcText(566, 221, 'Network Insights', 14, TC.ink, 500)
      + tcIcon('TbChevronDown', 776, 207, TC.muted, 18);
    out += label(16, 258, 'Priority');
    [['P1', 'Critical'], ['P2', 'High'], ['P3', 'Medium'], ['P4', 'Low'], ['P5', 'Trivial']].forEach(([priority, name], index) => {
      const x = 16 + index * 82; const colour = TC.priority[priority]; const chosen = priority === 'P3';
      out += `<rect x="${x}" y="266" width="74" height="42" rx="10" fill="${chosen ? colour : TC.card}" stroke="${chosen ? colour : TC.line}" stroke-width="1.5"/>`
        + tcText(x + 37, 286, priority, 15, chosen ? '#ffffff' : colour, 800, 'middle') + tcText(x + 37, 301, name, 10, chosen ? '#ffffff' : colour, 600, 'middle');
    });
    out += label(16, 332, 'Description');
    out += `<rect x="16" y="340" width="788" height="132" rx="10" fill="${TC.card}" stroke="${TC.line}" stroke-width="1.5"/><path d="M17 370 H803" stroke="${TC.line}" stroke-width="1.5"/>`;
    ['H1', 'H2', 'H3', '|', 'B', 'I', 'S', '<>', '|', '•', '1.', '☐', '|', '#7'].forEach((glyph, index) => {
      out += glyph === '|' ? `<path d="M${36 + index * 34} 348 V362" stroke="${TC.line}" stroke-width="1.5"/>` : tcText(36 + index * 34, 360, glyph, 13, TC.muted, 800, 'middle');
    });
    out += tcText(32, 396, 'Problem:', 14, TC.status.new, 800) + tcText(44, 418, '• Exporting the map of a 2 GB CDR stops at 80%', 13, TC.ink, 500)
      + tcText(32, 442, 'Expected:', 14, TC.status.new, 800) + tcText(44, 462, '• The whole map is exported, as with smaller CDRs', 13, TC.ink, 500);
    out += label(16, 494, 'Screenshots and files');
    out += `<rect x="16" y="502" width="788" height="46" rx="10" fill="${TC.card}" stroke="#c9c2b8" stroke-width="1.5" stroke-dasharray="6 5"/>`
      + tcIcon('TbPaperclip', 32, 514, TC.muted, 22) + tcText(64, 530, 'Paste them with Ctrl+V, drop them here or click to choose them', 13, TC.muted, 500);
    [690, 744].forEach((x, index) => {
      out += `<rect x="${x}" y="509" width="46" height="32" rx="5" fill="#e9eef4" stroke="${TC.line}"/>`
        + [0.5, 0.8, 0.35, 0.65].map((share, bar) => `<rect x="${x + 7 + bar * 9}" y="${535 - share * 20}" width="6" height="${share * 20}" rx="1" fill="${index ? TC.type.improvement : TC.status.new}"/>`).join('');
    });
    // Dimmed while signed out, under its note.
    out += `<rect x="0" y="86" width="820" height="474" rx="16" fill="${TC.page}" opacity=".38"/>`;
    out += `<rect x="16" y="16" width="788" height="58" rx="12" fill="#fdeeee" stroke="#f5c6c6" stroke-width="1.5"/><circle cx="46" cy="45" r="15" fill="${TC.wine}"/>${tcIcon('TbLock', 37, 36, '#ffffff', 18)}`
      + tcText(72, 41, 'Sign in to open a ticket', 16, '#7f1d1d', 800) + tcText(72, 61, 'The form can be filled and sent once you are signed in.', 13, '#9b4a4a', 500)
      + `<rect x="694" y="30" width="96" height="30" rx="15" fill="${TC.wine}"/>` + tcText(742, 50, 'Sign in', 14, '#ffffff', 800, 'middle');
    return out;
  },
  // The Dashboard of Ticket Center (1656 × 560) in a browser window: the period, Created vs resolved, At a glance, the
  // tickets per module, Needs attention and the latest activity.
  ticketDashboard() {
    const { created, resolved } = TC_WEEKS;
    let out = tcWindow(1656, 560, 'drivetest-analyzer / tickets  ·  Dashboard') + tcPeriodBar(18, 56, 1620, 'All time', 'Every ticket, since 3 Jun 2026');
    // Created vs resolved per week, the count over each bar.
    out += tcCard(18, 114, 1042, 210, 'Created vs resolved per week', 'Tickets opened and resolved or closed in each');
    [['Created', TC.status.new, created], ['Resolved', TC.status.resolved, resolved]].forEach(([name, colour, values], index) => {
      out += `<rect x="${36 + index * 120}" y="153" width="12" height="12" rx="3" fill="${colour}"/>` + tcText(54 + index * 120, 164, `${name} ${values.reduce((sum, value) => sum + value, 0)}`, 13, TC.ink, 700);
    });
    const slot = 1000 / created.length; const scale = 104 / Math.max(...created);
    created.forEach((value, index) => {
      const x = 40 + index * slot + (slot - 31) / 2;
      [[value, TC.status.new, 0], [resolved[index], TC.status.resolved, 17]].forEach(([count, colour, shift]) => {
        if (!count) return;
        out += `<rect x="${(x + shift).toFixed(1)}" y="${(296 - count * scale).toFixed(1)}" width="14" height="${(count * scale).toFixed(1)}" rx="3" fill="${colour}"/>`
          + tcText((x + shift + 7).toFixed(1), (290 - count * scale).toFixed(1), String(count), 11, colour, 800, 'middle');
      });
    });
    out += `<path d="M36 296.5 H1042" stroke="${TC.line}" stroke-width="1.5"/>`;
    TC_WEEKS.labels.forEach(([index, name]) => { out += tcText((40 + index * slot + slot / 2).toFixed(1), 314, name, 11, TC.muted, 600, 'middle'); });
    // At a glance.
    out += tcCard(1076, 114, 562, 210, 'At a glance', '60 tickets');
    out += tcDonut(1166, 232, 58, 20, [[22, TC.status.progress], [33, TC.status.resolved], [5, TC.status.rejected]])
      + tcText(1166, 238, '22', 30, TC.ink, 800, 'middle') + tcText(1166, 256, 'OPEN', 11, TC.muted, 800, 'middle', ' letter-spacing="1"');
    [['Open', 22, '37%', TC.status.progress], ['Resolved or closed', 33, '55%', TC.status.resolved], ['Rejected', 5, '8%', TC.status.rejected]].forEach(([name, count, share, colour], index) => {
      const y = 176 + index * 26;
      out += `<circle cx="1268" cy="${y - 4}" r="5" fill="${colour}"/>` + tcText(1282, y, name, 14, TC.ink, 700) + tcText(1570, y, String(count), 14, TC.ink, 800, 'end') + tcText(1618, y, share, 12, TC.muted, 600, 'end');
    });
    [['149 days', 'oldest open ticket', 1262], ['5', 'open unassigned', 1446]].forEach(([value, name, x]) => {
      out += `<rect x="${x}" y="256" width="174" height="54" rx="10" fill="#f5f7f9"/>` + tcText(x + 14, 280, value, 18, TC.ink, 800) + tcText(x + 14, 299, name, 12, TC.muted, 600);
    });
    // Tickets per module: its open ones out of every ticket.
    out += tcCard(18, 338, 462, 208, 'Tickets per module', 'Open of every ticket');
    [['Network Insights', '#4F46E5', 6, 11], ['General', '#5b6b7b', 4, 8], ['Scoring & GAP Analysis', '#176E77', 3, 10], ['PPT Designer', '#7751B9', 3, 7],
      ['Non-Qualified Calls', '#B0234F', 2, 9], ['Reporting', '#2E8C58', 1, 5]].forEach(([name, colour, open, total], index) => {
      const y = 396 + index * 25;
      out += `<circle cx="38" cy="${y - 4}" r="5" fill="${colour}"/>` + tcText(50, y, name, 13, TC.ink, 700)
        + `<rect x="226" y="${y - 9}" width="180" height="8" rx="4" fill="${TC.track}"/><rect x="226" y="${y - 9}" width="${180 * total / 11}" height="8" rx="4" fill="${mix(colour, '#ffffff', 0.7)}"/>`
        + `<rect x="226" y="${y - 9}" width="${180 * open / 11}" height="8" rx="4" fill="${colour}"/>` + tcText(462, y, `${open}/${total}`, 13, TC.ink, 800, 'end');
    });
    // Needs attention: the most urgent open tickets, then the oldest.
    out += tcCard(496, 338, 684, 208, 'Needs attention', '22 open · the most urgent and oldest first');
    [['P1', 'Critical', 'TbBug', TC.type.bug, '#54 Map export stops on large CDRs', 'New', TC.status.new, '', 'Unassigned', '149 days', TC.priority.P1, 1],
      ['P1', 'Critical', 'TbBug', TC.type.bug, '#25 Statistics slow on All time', 'In Progress', TC.status.progress, 'UA', 'User A', '76 days', TC.priority.P1, 0.55],
      ['P2', 'High', 'TbTrendingUp', TC.type.improvement, '#34 Filter the calls by cluster', 'In Progress', TC.status.progress, 'UB', 'User B', '30 days', TC.status.waiting, 0.3],
      ['P2', 'High', 'TbSparkles', TC.type.feature, '#41 Export the timeline to Excel', 'New', TC.status.new, '', 'Unassigned', '6 days', TC.status.resolved, 0.1],
    ].forEach(([priority, name, typeIcon, typeColour, title, status, statusColour, initials, assignee, age, ageColour, share], index) => {
      const y = 384 + index * 40;
      out += `<rect x="508" y="${y}" width="660" height="34" rx="9" fill="#fbf9f7" stroke="#efe9e2"/>`
        + `<rect x="516" y="${y + 7}" width="86" height="20" rx="6" fill="${TC.priority[priority]}"/>` + tcText(559, y + 21, `${priority} ${name}`, 11, '#ffffff', 800, 'middle')
        + tcIcon(typeIcon, 612, y + 9, typeColour, 16) + tcText(634, y + 22, title, 13, TC.ink, 700)
        + `<rect x="892" y="${y + 8}" width="80" height="18" rx="9" fill="${mix(statusColour, '#ffffff', 0.88)}"/>` + tcText(932, y + 21, status, 11, statusColour, 800, 'middle')
        + `<circle cx="992" cy="${y + 17}" r="10" fill="#e6ecf2"/>` + tcText(992, y + 21, initials || '?', 9, TC.muted, 800, 'middle')
        + tcText(1008, y + 21, assignee, 12, initials ? TC.ink : TC.muted, 600)
        + tcText(1158, y + 16, age, 12, ageColour, 800, 'end') + tcBar(1098, y + 22, 60, share, ageColour, 4);
    });
    // Latest activity.
    out += tcCard(1196, 338, 442, 208, 'Latest activity', 'The newest first') + `<path d="M1222 384 V510" stroke="${TC.line}" stroke-width="2"/>`;
    [['User A', 'moved to', 'Resolved', TC.status.resolved, '#59', '6 h ago', 'TbCheck'], ['User B', 'commented', '', TC.status.waiting, '#57', '7 h ago', 'TbMessage'],
      ['User A', 'moved to', 'In Progress', TC.status.progress, '#55', '1 d ago', 'TbProgress'], ['User C', 'opened', '', TC.status.new, '#60', '1 d ago', 'TbPlus'],
      ['User D', 'commented', '', TC.status.waiting, '#54', '2 d ago', 'TbMessage']].forEach(([who, verb, status, colour, ticket, ago, kind], index) => {
      const y = 386 + index * 31;
      out += `<circle cx="1222" cy="${y}" r="11" fill="${colour}"/>${tcIcon(kind, 1215, y - 7, '#ffffff', 14)}` + tcText(1242, y + 5, who, 13, TC.ink, 800)
        + tcText(1292, y + 5, verb, 13, TC.muted, 500);
      let left = 1292 + verb.length * 7.6 + 8;
      if (status) {
        const pill = tcPill(left, y - 8, status, mix(colour, '#ffffff', 0.86), colour, 11);
        out += pill.svg;
        left += pill.width + 6;
      }
      out += tcText(left.toFixed(1), y + 5, ticket, 13, TC.ink, 800) + tcText(1620, y + 5, ago, 12, TC.muted, 600, 'end');
    });
    return out;
  },
  // The periods of Ticket Center (1656 × 560): how each one draws its charts and calendar of activity, and which
  // tickets each part of the views counts.
  ticketPeriods(p) {
    const level = (seed) => Math.floor(Math.abs(Math.sin(seed * 12.9898) * 43758.5453) % 1 * 5);
    const shades = ['#1d2a45', '#1e3a66', '#2a5aa0', '#3f7fd6', '#7fb2f0'];
    // A small calendar of a month: its first weekday (Monday 0), its days, the last day with activity and the first one.
    const month = (x, y, cell, first, days, { until = days, from = 1, seed = 0, quiet = false } = {}) => {
      let out = '';
      for (let day = 1; day <= days; day += 1) {
        const position = first + day - 1; const cx = x + (position % 7) * cell; const cy = y + Math.floor(position / 7) * cell;
        const future = day > until; const weekend = position % 7 >= 5;
        const shade = quiet || day < from ? shades[0] : shades[Math.max(0, level(seed + day) - (weekend ? 2 : 0))];
        out += `<rect x="${cx.toFixed(1)}" y="${cy.toFixed(1)}" width="${(cell * 0.82).toFixed(1)}" height="${(cell * 0.82).toFixed(1)}" rx="${(cell * 0.2).toFixed(1)}" fill="${future ? 'none' : shade}"${future ? ' stroke="#2a3a5c" stroke-width="1"' : ''}/>`;
      }
      return out;
    };
    const periods = [
      { name: 'All time', unit: 'Since the first ticket · by week', compare: 'No period before', bars: [2, 1, 3, 2, 4, 3, 2, 5, 4, 6, 5, 9, 12, 14], labels: [[0, 'Jun'], [4, 'Jul'], [9, 'Sep'], [13, 'Oct']],
        calendar: (x, y) => ['Jun', 'Jul', 'Aug', 'Sep', 'Oct'].map((name, index) => tcText(x + index * 56, y + 8, name, 11, '#9fb0cc', 700)
          + month(x + index * 56, y + 16, 7.2, [0, 2, 5, 1, 3][index], [30, 31, 31, 30, 31][index], { until: index === 4 ? 30 : 31, from: index ? 1 : 3, seed: index * 40 })).join('') },
      { name: 'This week', unit: 'From Monday · by day', compare: 'vs last week', bars: [5, 7, 4, 8, 6, 1, 0], weekend: (index) => index >= 5, labels: 'MTWTFSS'.split('').map((day, index) => [index, day]),
        calendar: (x, y) => [26, 27, 28, 29, 30, 31, 1].map((day, index) => `<rect x="${x + index * 38}" y="${y + 6}" width="32" height="32" rx="7" fill="${index > 4 ? 'none' : shades[[2, 3, 2, 4, 3][index]]}"${index > 4 ? ' stroke="#2a3a5c"' : ''}/>`
          + tcText(x + index * 38 + 16, y + 27, String(day), 13, index > 4 ? '#55627c' : '#ffffff', 700, 'middle') + (index >= 5 ? `<rect x="${x + index * 38 + 4}" y="${y + 43}" width="24" height="3" rx="1.5" fill="#9fb0cc"/>` : '')).join('') },
      { name: 'This month', unit: 'By day', compare: 'vs last month', bars: [3, 5, 2, 0, 1, 6, 4, 7, 5, 3, 0, 1, 5, 8, 6, 4, 9, 1, 0, 7, 6, 10, 8, 5, 2, 1, 9, 12, 7, 11, 0],
        weekend: (index) => (3 + index) % 7 >= 5, future: (index) => index >= 30, labels: [[0, '1'], [7, '8'], [14, '15'], [21, '22'], [28, '29']],
        calendar: (x, y) => month(x, y + 2, 13, 3, 31, { until: 30, seed: 160 }) + tcText(x + 112, y + 34, 'A box per day,', 13, '#9fb0cc', 600) + tcText(x + 112, y + 52, 'darker the busier', 13, '#9fb0cc', 600) },
      { name: 'This quarter', unit: 'By week', compare: 'vs last quarter', bars: [6, 9, 7, 11, 13, 0, 0, 0, 0, 0, 0, 0, 0], future: (index) => index >= 5, labels: [[0, 'Oct'], [5, 'Nov'], [9, 'Dec']],
        calendar: (x, y) => ['Oct', 'Nov', 'Dec'].map((name, index) => `<rect x="${x + index * 92 - 4}" y="${y - 4}" width="84" height="72" rx="8" fill="#16213a" stroke="#2a3a5c"/>`
          + tcText(x + index * 92 + 2, y + 10, name, 11, '#9fb0cc', 700) + month(x + index * 92 + 6, y + 16, 8.6, [3, 6, 1][index], [31, 30, 31][index], { until: index ? 0 : 30, seed: 160 })).join('') },
      { name: 'This year', unit: 'By month', compare: 'vs last year', bars: [0, 0, 0, 0, 0, 4, 6, 9, 13, 28, 0, 0], future: (index) => index >= 10, labels: 'JFMAMJJASOND'.split('').map((name, index) => [index, name]),
        calendar: (x, y) => [3, 6, 6, 2, 4, 0, 2, 5, 1, 3, 6, 1].map((first, index) => `<rect x="${x + (index % 6) * 46 - 3}" y="${y + Math.floor(index / 6) * 36 - 2}" width="42" height="33" rx="5" fill="#16213a" stroke="#2a3a5c"/>`
          + month(x + (index % 6) * 46, y + Math.floor(index / 6) * 36, 5.4, first, [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][index], { until: index > 9 ? 0 : index === 9 ? 30 : 31, quiet: index < 5, from: index === 5 ? 3 : 1, seed: index * 31 })).join('') },
    ];
    let out = '';
    periods.forEach((period, column) => {
      const x = column * 336; const chosen = column === 0;
      out += `<rect x="${x}" y="0" width="312" height="326" rx="20" fill="#131d33" stroke="${chosen ? p.accent : '#2a3a5c'}" stroke-width="${chosen ? 2.5 : 2}"/>`;
      const width = period.name.length * 10.4 + 36;
      out += `<rect x="${x + 20}" y="20" width="${width}" height="38" rx="19" fill="${chosen ? p.accent : '#22304f'}"/>` + tcText(x + 20 + width / 2, 45, period.name, 18, '#ffffff', 800, 'middle');
      if (chosen) out += tcText(x + 292, 44, 'DEFAULT', 13, p.light, 800, 'end', ' letter-spacing="2"');
      out += tcText(x + 20, 86, period.unit, 15, '#c9d4e6', 600) + tcText(x + 20, 108, period.compare, 14, chosen ? '#9fb0cc' : p.light, 700);
      // The chart, a bar per day, week or month: the weekends shaded, the time still to come faint.
      const slot = 272 / period.bars.length; const width2 = Math.min(26, slot * 0.66); const top = Math.max(...period.bars);
      period.bars.forEach((value, index) => {
        const bx = x + 20 + index * slot;
        if (period.weekend && period.weekend(index)) out += `<rect x="${bx.toFixed(1)}" y="122" width="${slot.toFixed(1)}" height="86" fill="#ffffff" opacity=".06"/>`;
        if (period.future && period.future(index)) out += `<rect x="${(bx + (slot - width2) / 2).toFixed(1)}" y="203" width="${width2.toFixed(1)}" height="4" rx="2" fill="#2a3a5c"/>`;
        else if (value) out += `<rect x="${(bx + (slot - width2) / 2).toFixed(1)}" y="${(207 - value / top * 80).toFixed(1)}" width="${width2.toFixed(1)}" height="${(value / top * 80).toFixed(1)}" rx="${Math.min(4, width2 / 3).toFixed(1)}" fill="${period.weekend && period.weekend(index) ? '#7d8aa3' : p.accent}"/>`;
      });
      out += `<path d="M${x + 20} 207.5 H${x + 292}" stroke="#2a3a5c" stroke-width="2"/>`;
      period.labels.forEach(([index, name]) => { out += tcText((x + 20 + index * slot + slot / 2).toFixed(1), 226, name, 12, period.weekend && period.weekend(index) ? '#7d8aa3' : '#9fb0cc', 600, 'middle'); });
      out += `<path d="M${x + 20} 240 H${x + 292}" stroke="#22304f" stroke-width="1.5" stroke-dasharray="4 5"/>` + period.calendar(x + 22, 252);
    });
    // Which tickets each part counts.
    [{ icon: 'TbTicket', colour: TC.status.new, title: 'Opened in the period', text: 'What came in', chips: ['At a glance', 'Type & status', 'Tickets per module', 'Every ticket', 'People', 'Needs attention'] },
      { icon: 'TbChecks', colour: TC.status.resolved, title: 'Resolved or closed in it', text: 'What went out', chips: ['Time to resolve', 'Fixed in version', 'Time Spent', 'Resolved last'] },
      { icon: 'TbArrowsDiff', colour: p.accent, title: 'Against the one before', text: 'Last week, month, quarter or year', chips: [['18% faster', TC.status.resolved], ['+12 tickets', TC.status.new], ['All time: none', '#55627c']] },
    ].forEach((lane, index) => {
      const x = index * 560;
      out += `<rect x="${x}" y="350" width="536" height="210" rx="20" fill="#131d33" stroke="#2a3a5c" stroke-width="2"/>`
        + `<rect x="${x + 24}" y="374" width="56" height="56" rx="16" fill="${lane.colour}"/>${tcIcon(lane.icon, x + 37, 387, '#ffffff', 30)}`
        + tcText(x + 96, 400, lane.title, 24, '#ffffff', 800) + tcText(x + 96, 424, lane.text, 16, '#9fb0cc', 500);
      let left = x + 24; let top = 452;
      lane.chips.forEach((chip) => {
        const [name, colour] = Array.isArray(chip) ? chip : [chip, mix(lane.colour, '#131d33', 0.45)];
        const width = Math.round(name.length * 15 * 0.58 + 28);
        if (left + width > x + 512) { left = x + 24; top += 44; }
        out += `<rect x="${left}" y="${top}" width="${width}" height="34" rx="17" fill="${colour}"/>` + tcText(left + width / 2, top + 22, name, 15, '#ffffff', 700, 'middle');
        left += width + 10;
      });
    });
    return out;
  },
  // The Statistics of Ticket Center (1656 × 560) in a browser window: its figures, every ticket by type, status and
  // priority, the backlog, the time to resolve, the versions and the activity.
  ticketStatistics() {
    const { created, resolved, rejected } = TC_WEEKS;
    let out = tcWindow(1656, 560, 'drivetest-analyzer / tickets  ·  Statistics');
    [{ label: 'Resolution rate', value: '55%', line: '33 of the 60 tickets opened resolved or closed', colour: TC.status.resolved, ring: 55 },
      { label: 'Time to resolve', value: '6d 6h', line: 'Median of 33 tickets resolved or closed', colour: TC.status.progress, iconName: 'TbClockHour4' },
      { label: 'Tickets opened', value: '60', line: 'Since the first ticket', colour: TC.status.new, iconName: 'TbTicket' },
      { label: 'Comments per ticket', value: '1.9', line: '0.4 attachments per ticket', colour: TC.status.waiting, iconName: 'TbMessages' }].forEach((tile, index) => {
      out += tcTile(18 + index * 409, 56, 393, 74, tile);
    });
    // Every ticket: a donut by type, status and priority.
    out += tcCard(18, 144, 682, 196, 'Every ticket', 'By type, status and priority');
    [['By type', [['Bug', 30, TC.type.bug], ['Improvement', 18, TC.type.improvement], ['New Feature', 12, TC.type.feature]]],
      ['By status', [['New', 8, TC.status.new], ['In Progress', 13, TC.status.progress], ['Waiting', 1, TC.status.waiting], ['Rejected', 5, TC.status.rejected], ['Closed', 3, TC.status.closed], ['Resolved', 30, TC.status.resolved]]],
      ['By priority', [['P1 · Critical', 5, TC.priority.P1], ['P2 · High', 12, TC.priority.P2], ['P3 · Medium', 28, TC.priority.P3], ['P4 · Low', 12, TC.priority.P4], ['P5 · Trivial', 3, TC.priority.P5]]],
    ].forEach(([name, parts], index) => {
      const x = 34 + index * 222; const cy = 246;
      out += tcDonut(x + 54, cy, 42, 16, parts.map(([, count, colour]) => [count, colour])) + tcText(x + 54, cy + 4, '60', 20, TC.ink, 800, 'middle')
        + tcText(x + 54, cy + 18, 'TICKETS', 9, TC.muted, 800, 'middle') + tcText(x + 54, 324, name, 13, TC.muted, 700, 'middle');
      parts.forEach(([label, count, colour], row) => {
        const y = cy - (parts.length - 1) * 9.5 + row * 19 + 4;
        out += `<circle cx="${x + 116}" cy="${y - 4}" r="4.5" fill="${colour}"/>` + tcText(x + 126, y, label, 11, TC.ink, 600) + tcText(x + 218, y, String(count), 11, TC.ink, 800, 'end');
      });
    });
    // The backlog by the end of each week.
    out += tcCard(716, 144, 922, 196, 'Backlog per week', 'Totals by the end of each');
    [['Created 60', TC.status.new], ['Resolved 33', TC.status.resolved], ['Open 22', TC.status.progress]].forEach(([name, colour], index) => {
      out += `<rect x="${734 + index * 124}" y="183" width="12" height="12" rx="3" fill="${colour}"/>` + tcText(752 + index * 124, 194, name, 13, TC.ink, 700);
    });
    const sums = (values) => values.reduce((all, value) => [...all, (all.at(-1) || 0) + value], []);
    const [totalCreated, totalResolved, totalRejected] = [sums(created), sums(resolved), sums(rejected)];
    const point = (values) => values.map((value, index) => `${(740 + index * 874 / 21).toFixed(1)},${(310 - value * 1.5).toFixed(1)}`).join(' ');
    out += `<polygon points="740,310 ${point(totalCreated)} 1614,310" fill="rgba(30,97,163,.12)"/><polygon points="740,310 ${point(totalResolved)} 1614,310" fill="rgba(31,138,91,.18)"/>`
      + `<polyline points="${point(totalCreated)}" fill="none" stroke="${TC.status.new}" stroke-width="3"/><polyline points="${point(totalResolved)}" fill="none" stroke="${TC.status.resolved}" stroke-width="3"/>`
      + `<polyline points="${point(totalCreated.map((value, index) => value - totalResolved[index] - totalRejected[index]))}" fill="none" stroke="${TC.status.progress}" stroke-width="3" stroke-dasharray="7 5"/>`
      + `<path d="M736 310.5 H1618" stroke="${TC.line}" stroke-width="1.5"/>`;
    TC_WEEKS.labels.forEach(([index, name]) => { out += tcText((740 + index * 874 / 21).toFixed(1), 328, name, 11, TC.muted, 600, 'middle'); });
    // Two views of a card, the first one chosen.
    const toggle = (x, y, first, second) => {
      const [a, b] = [first.length * 7 + 22, second.length * 7 + 22];
      return `<rect x="${x - a - b - 6}" y="${y}" width="${a + b + 6}" height="26" rx="13" fill="#f1f3f5"/><rect x="${x - a - b - 3}" y="${y + 3}" width="${a}" height="20" rx="10" fill="#ffffff" stroke="${TC.line}"/>`
        + tcText(x - b - 3 - a / 2, y + 17, first, 12, TC.ink, 800, 'middle') + tcText(x - 3 - b / 2, y + 17, second, 12, TC.muted, 700, 'middle');
    };
    // Bars stacked by type, the count over each one.
    const stacked = (x0, width, base, height, groups, labels, size = 12) => {
      const slot = width / groups.length; const top = Math.max(...groups.map((group) => group.reduce((sum, value) => sum + value, 0)));
      let svg = '';
      groups.forEach((group, index) => {
        let y = base; const bx = x0 + index * slot + (slot - 30) / 2;
        group.forEach((value, part) => {
          if (!value) return;
          const h = value / top * height;
          svg += `<rect x="${bx.toFixed(1)}" y="${(y - h).toFixed(1)}" width="30" height="${h.toFixed(1)}" fill="${[TC.type.bug, TC.type.improvement, TC.type.feature][part]}"/>`;
          y -= h;
        });
        svg += tcText((bx + 15).toFixed(1), (y - 5).toFixed(1), String(group.reduce((sum, value) => sum + value, 0)), 12, TC.ink, 800, 'middle')
          + tcText((bx + 15).toFixed(1), base + 18, labels[index], size, TC.muted, 600, 'middle');
      });
      return `${svg}<path d="M${x0} ${base + 0.5} H${x0 + width}" stroke="${TC.line}" stroke-width="1.5"/>`;
    };
    out += tcCard(18, 354, 522, 192, 'Time to resolve') + toggle(522, 364, 'Resolved', 'Open')
      + stacked(30, 498, 512, 92, [[2, 1, 0], [5, 2, 1], [4, 2, 2], [4, 2, 1], [3, 1, 1], [1, 1, 0], [0, 0, 0]], ['< 1 day', '1–3 d', '3–7 d', '1–2 w', '2–4 w', '1–3 m', '> 3 m']);
    out += tcCard(556, 354, 544, 192, 'Tickets fixed in each version') + toggle(1082, 364, 'Fixed in', 'Opened with')
      + stacked(566, 524, 512, 92, [[1, 0, 0], [0, 0, 0], [0, 0, 0], [1, 1, 1], [1, 0, 0], [0, 0, 0], [2, 1, 0], [1, 1, 1], [3, 1, 1], [8, 5, 4]],
        ['v0.8.0', 'v0.8.1', 'v0.8.2', 'v0.9.0', 'v0.9.1', 'v0.9.2', 'v0.9.3', 'v0.9.4', 'v0.10.0', 'v0.10.1'], 10.5);
    // The activity: a small calendar of each month, darker the busier, the weekends underlined.
    out += tcCard(1116, 354, 522, 192, 'Activity', 'Opened, comments and changes');
    const blues = ['#eef2f6', '#c9d9ec', '#94b4da', '#5a86bf', '#2f5fa0'];
    ['Jun', 'Jul', 'Aug', 'Sep', 'Oct'].forEach((name, index) => {
      const x = 1132 + index * 100; const first = [0, 2, 5, 1, 3][index]; const days = [30, 31, 31, 30, 31][index];
      out += `<rect x="${x}" y="392" width="92" height="112" rx="9" fill="#fbfcfd" stroke="${TC.line}"/>` + tcText(x + 8, 408, `${name} 2026`, 11, TC.ink, 800);
      'MTWTFSS'.split('').forEach((day, column) => { out += tcText(x + 11 + column * 11.4, 421, day, 7.5, column >= 5 ? TC.ink : TC.muted, 700, 'middle'); });
      for (let day = 1; day <= days; day += 1) {
        const position = first + day - 1; const column = position % 7;
        const busy = (index === 0 && day < 3) || (index === 4 && day > 30) ? -1 : Math.min(4, Math.floor(Math.abs(Math.sin((index * 31 + day) * 3.7)) * (2.2 + index * 0.6)) - (column >= 5 ? 1 : 0));
        out += `<rect x="${x + 6 + column * 11.4}" y="${426 + Math.floor(position / 7) * 11.4}" width="9.6" height="9.6" rx="2" fill="${busy < 0 ? '#ffffff' : blues[Math.max(0, busy)]}"${busy < 0 ? ` stroke="${TC.line}"` : ''}/>`;
      }
    });
    out += tcText(1134, 530, '60 opened  ·  112 comments  ·  55 changes  ·  33 resolved', 12, TC.ink, 700);
    return out;
  },
  // The Time Spent of Ticket Center (1656 × 560) in a browser window: how it is measured, its figures, where the time
  // goes, the time per week and by module, type, priority, assignee, reporter and version.
  ticketTime() {
    let out = `<defs><linearGradient id="ticket-time-bar" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ef4444"/><stop offset="1" stop-color="#991b1b"/></linearGradient>`
      + `<clipPath id="ticket-where"><rect x="36" y="242" width="586" height="22" rx="7"/></clipPath></defs>` + tcWindow(1656, 560, 'drivetest-analyzer / tickets  ·  Time Spent');
    out += `<rect x="18" y="56" width="1620" height="40" rx="12" fill="#eef5fc" stroke="#cfe0f2" stroke-width="1.5"/><circle cx="40" cy="76" r="11" fill="${TC.status.new}"/>`
      + tcText(40, 81, 'i', 14, '#ffffff', 800, 'middle') + tcText(62, 81, 'How it is measured', 14, TC.ink, 800)
      + tcText(206, 81, 'Calendar time from opened to resolved or closed, 24 hours a day  ·  only the tickets resolved or closed in the period  ·  d = days of 24 h, h = hours, m = minutes', 14, TC.ink, 500);
    [{ label: 'Time spent in all', value: '313d 17h', line: 'All tickets, added up', colour: TC.status.progress, iconName: 'TbClockHour4' },
      { label: 'Tickets resolved', value: '33', line: 'Or closed, in the period', colour: TC.status.resolved, iconName: 'TbTicket' },
      { label: 'Average per ticket', value: '9d 12h', line: 'Time in all ÷ tickets', colour: TC.status.new, iconName: 'TbGauge' },
      { label: 'Median per ticket', value: '6d 15h', line: 'Half of them took less', colour: TC.status.waiting, iconName: 'TbChartBar' },
      { label: 'The longest', value: '37d 17h', line: '#22 Statistics slow on All time', colour: TC.priority.P1, iconName: 'TbHourglass' }].forEach((tile, index) => {
      out += tcTile(18 + index * 327, 108, 311, 74, tile);
    });
    // Where the time goes: the time of those tickets in each open status.
    const where = [['New', '128d 13h', 41, '3d 21h', TC.status.new], ['In Progress', '144d 7h', 46, '4d 9h', TC.status.progress], ['Waiting for Info', '40d 21h', 13, '1d 6h', TC.status.waiting]];
    out += tcCard(18, 196, 622, 158, 'Where the time goes', 'By status, until resolved') + `<g clip-path="url(#ticket-where)">`;
    let left = 36;
    where.forEach(([, , share, , colour]) => {
      out += `<rect x="${left.toFixed(1)}" y="242" width="${(586 * share / 100 - 2).toFixed(1)}" height="22" fill="${colour}"/>`;
      left += 586 * share / 100;
    });
    out += '</g>';
    where.forEach(([name, total, share, average, colour], index) => {
      const x = 36 + index * 200;
      out += `<circle cx="${x + 5}" cy="${291}" r="5" fill="${colour}"/>` + tcText(x + 16, 296, name, 13, TC.ink, 800) + tcText(x, 322, total, 20, TC.ink, 800)
        + tcText(x, 342, `${share}% · ${average} per ticket`, 12, TC.muted, 600);
    });
    // The time of the tickets resolved in each week, over its column.
    const weeks = [0, 0, 1.2, 3.5, 0, 0, 0.9, 2.1, 4.2, 6.4, 0, 1.5, 0.4, 7.8, 12.3, 5.1, 9.6, 20.2, 14.4, 31.5, 77.3, 115.3];
    out += tcCard(656, 196, 982, 158, 'Time spent per week', 'The tickets resolved or closed in each');
    const slot = 946 / weeks.length;
    weeks.forEach((days, index) => {
      if (!days) return;
      const x = 674 + index * slot + (slot - 26) / 2; const h = Math.max(3, days / 115.3 * 72);
      out += `<rect x="${x.toFixed(1)}" y="${(328 - h).toFixed(1)}" width="26" height="${h.toFixed(1)}" rx="3" fill="url(#ticket-time-bar)"/>`
        + tcText((x + 13).toFixed(1), (322 - h).toFixed(1), tcDuration(days), 10, '#991b1b', 800, 'middle');
    });
    out += `<path d="M670 328.5 H1624" stroke="${TC.line}" stroke-width="1.5"/>`;
    TC_WEEKS.labels.forEach(([index, name]) => { out += tcText((674 + index * slot + slot / 2).toFixed(1), 346, name, 11, TC.muted, 600, 'middle'); });
    // By module, type and priority, then by assignee, reporter and the version that fixed them.
    [['By module', [['Non-Qualified Calls', 60.9, '#B0234F'], ['Workspace', 48.04, '#08736D'], ['Network Insights', 47.5, '#4F46E5'], ['General', 45.2, '#5b6b7b']]],
      ['By type', [['Bug', 134.5, TC.type.bug], ['Improvement', 156.7, TC.type.improvement], ['New Feature', 22.5, TC.type.feature]]],
      ['By priority', [['P1 · Critical', 34.25, TC.priority.P1], ['P2 · High', 104.6, TC.priority.P2], ['P3 · Medium', 110.8, TC.priority.P3], ['P4 · Low', 59.3, TC.priority.P4]]],
      ['By assignee', [['User A', 213.3, TC.status.new], ['User B', 75.04, TC.status.new], ['User C', 25.3, TC.status.new]]],
      ['By reporter', [['User C', 125.25, TC.status.new], ['User A', 105.3, TC.status.new], ['User B', 61.96, TC.status.new], ['User D', 19.9, TC.status.new]]],
      ['By version that fixed them', [['v0.10.1', 117.04, TC.priority.P1], ['v0.10.0', 60.6, TC.priority.P1], ['v0.9.1', 50.95, TC.priority.P1], ['v0.9.0', 33.2, TC.priority.P1]]],
    ].forEach(([title, rows], index) => {
      const x = 18 + index * 272; const most = Math.max(...rows.map(([, days]) => days));
      out += tcCard(x, 368, 258, 178, title, '', 14);
      rows.forEach(([name, days, colour], row) => {
        const y = 424 + row * 30;
        out += tcText(x + 16, y, name, 12, TC.ink, 700) + tcText(x + 242, y, tcDuration(days), 12, TC.ink, 800, 'end') + tcBar(x + 16, y + 7, 226, days / most, colour, 6);
      });
    });
    return out;
  },
};

// Small pictures of the tiles (360 × 150), one per idea, in the colours of the deck.
const MINIS = {
  table: (p) => {
    let out = `<rect x="40" y="16" width="280" height="118" rx="12" fill="#101a2e"/><rect x="40" y="16" width="280" height="28" rx="12" fill="${p.accent}"/><rect x="40" y="32" width="280" height="12" fill="${p.accent}"/>`;
    for (let row = 0; row < 3; row += 1) for (let col = 0; col < 4; col += 1) out += `<rect x="${54 + col * 66}" y="${56 + row * 26}" width="${48 - ((row + col) % 2) * 14}" height="12" rx="6" fill="${row === 1 && col === 2 ? p.light : '#3a4d75'}"/>`;
    return out;
  },
  formula: (p) => `<rect x="40" y="30" width="120" height="90" rx="16" fill="${p.accent}"/><text x="100" y="92" text-anchor="middle" font-size="46" font-weight="800" font-style="italic" fill="#ffffff">fx</text>`
    + `<path d="M172 75 H206" stroke="${p.light}" stroke-width="5"/><path d="M198 64 l12 11 l-12 11" fill="none" stroke="${p.light}" stroke-width="5"/>`
    + `<rect x="222" y="20" width="98" height="110" rx="12" fill="#101a2e"/>${[0, 1, 2, 3].map((row) => `<rect x="236" y="${34 + row * 24}" width="${70 - row * 8}" height="12" rx="6" fill="${p.light}"/>`).join('')}`,
  vendor: (p) => `<path d="M90 30 L110 120 H70 Z" fill="none" stroke="#ffffff" stroke-width="5" stroke-linejoin="round"/><path d="M78 74 H102" stroke="#ffffff" stroke-width="4"/><circle cx="90" cy="28" r="8" fill="${p.light}"/>`
    + [['Ericsson', '#0255AD'], ['Nokia', '#8C00FF'], ['Huawei', '#FBBD00']].map(([name, colour], index) => `<rect x="150" y="${24 + index * 38}" width="170" height="30" rx="15" fill="${colour}"/><text x="235" y="${45 + index * 38}" text-anchor="middle" font-size="17" font-weight="700" fill="#ffffff">${name}</text>`).join(''),
  polygons: (p) => `<path d="M40 40 L130 22 L150 80 L90 112 L50 96 Z" fill="${p.accent}" opacity=".9"/><path d="M130 22 L230 30 L240 90 L150 80 Z" fill="${p.light}" opacity=".7"/><path d="M150 80 L240 90 L250 130 L120 130 L90 112 Z" fill="${p.deep}"/><path d="M230 30 L320 44 L314 120 L250 130 L240 90 Z" fill="${p.accent}" opacity=".55"/>`
    + `<path d="M40 40 L130 22 L230 30 L320 44 L314 120 L250 130 L120 130 L50 96 Z" fill="none" stroke="#ffffff" stroke-width="2.5" opacity=".8"/>`,
  pins: (p) => `<path d="M30 110 C 100 80, 160 130, 230 90 S 320 60, 340 80" fill="none" stroke="#2a3a5c" stroke-width="8"/>`
    + [[90, 70, p.accent], [190, 50, p.light], [280, 84, p.accent]].map(([x, y, colour]) => `<path d="M${x} ${y + 34} c-12 -16 -20 -26 -20 -36 a20 20 0 1 1 40 0 c0 10 -8 20 -20 36 Z" fill="${colour}" stroke="#ffffff" stroke-width="3"/><circle cx="${x}" cy="${y - 2}" r="7" fill="#ffffff"/>`).join(''),
  serving: (p) => [[70, '#E60000'], [290, '#2D8AE6']].map(([x, colour]) => `<path d="M${x} 30 L${x + 18} 110 H${x - 18} Z" fill="none" stroke="${colour}" stroke-width="5" stroke-linejoin="round"/><circle cx="${x}" cy="28" r="8" fill="${colour}"/>`).join('')
    + `<rect x="160" y="60" width="40" height="70" rx="8" fill="#ffffff"/><rect x="168" y="70" width="24" height="44" rx="3" fill="${p.deep}"/>`
    + `<path d="M96 60 C 130 54, 140 70, 154 84" fill="none" stroke="${p.light}" stroke-width="4" stroke-dasharray="7 6"/><path d="M264 60 C 230 54, 220 70, 206 84" fill="none" stroke="${p.light}" stroke-width="4" stroke-dasharray="7 6"/>`,
  bands: (p) => [['Low', 0.45], ['Mid', 0.75], ['High (TDD)', 1]].map(([name, share], index) => `<text x="40" y="${48 + index * 40}" font-size="18" fill="#c9d4e6">${name}</text><rect x="140" y="${33 + index * 40}" width="180" height="20" rx="10" fill="#22304f"/><rect x="140" y="${33 + index * 40}" width="${180 * share}" height="20" rx="10" fill="${index === 2 ? p.accent : p.light}"/>`).join(''),
  gauge: (p) => `<path d="M90 120 A90 90 0 0 1 270 120" fill="none" stroke="#22304f" stroke-width="22"/><path d="M90 120 A90 90 0 0 1 238 56" fill="none" stroke="${p.accent}" stroke-width="22" stroke-linecap="round"/>`
    + `<path d="M180 120 L232 66" stroke="#ffffff" stroke-width="6" stroke-linecap="round"/><circle cx="180" cy="120" r="12" fill="#ffffff"/><text x="180" y="100" text-anchor="middle" font-size="24" font-weight="800" fill="#ffffff">887</text>`,
  grid: (p) => {
    let out = '';
    for (let row = 0; row < 4; row += 1) for (let col = 0; col < 4; col += 1) {
      const edited = row === 2 && col === 2;
      out += `<rect x="${50 + col * 68}" y="${16 + row * 30}" width="62" height="24" rx="6" fill="${row === 0 ? p.accent : edited ? '#fff3b0' : '#16213a'}" stroke="${edited ? '#e8c547' : '#2a3a5c'}" stroke-width="2"/>`;
    }
    return out;
  },
  dictionary: (p) => [['Setup time', 'Call Setup Duration'], ['Throughput', 'DL App Throughput'], ['RSRP', 'LTE RSRP Avg']].map(([field, column], index) => `<rect x="24" y="${18 + index * 40}" width="130" height="30" rx="15" fill="${p.accent}"/><text x="89" y="${39 + index * 40}" text-anchor="middle" font-size="16" font-weight="700" fill="#ffffff">${field}</text>`
    + `<path d="M162 ${33 + index * 40} H186" stroke="${p.light}" stroke-width="3"/><rect x="192" y="${18 + index * 40}" width="148" height="30" rx="8" fill="#101a2e"/><text x="202" y="${38 + index * 40}" font-size="14" fill="#c9d4e6" class="mono">${column}</text>`).join(''),
  kpi: (p) => `<text x="40" y="78" font-size="52" font-weight="800" fill="#ffffff">98.6%</text><text x="44" y="110" font-size="18" fill="#9fb0cc">Call success</text>`
    + `<polyline points="230,110 254,96 278,102 302,76 326,58" fill="none" stroke="${p.light}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/><circle cx="326" cy="58" r="8" fill="${p.accent}"/>`,
  wave: (p) => [0.3, 0.5, 0.7, 0.9, 0.6, 0.8, 0.45].map((share, index) => `<rect x="${44 + index * 42}" y="${126 - share * 100}" width="28" height="${share * 100}" rx="6" fill="${share > 0.75 ? p.accent : share > 0.5 ? p.light : '#e0533d'}"/>`).join('')
    + `<text x="40" y="30" font-size="18" fill="#9fb0cc">RSRP · SINR</text>`,
  funnel: (p) => [[70, 14, '#7d8aa3'], [110, 24, '#e0533d'], [150, 12, p.light], [196, 22, '#7d8aa3'], [238, 14, '#f0a830'], [282, 24, '#7d8aa3']].map(([x, y, colour]) => `<circle cx="${x}" cy="${y}" r="8" fill="${colour}"/>`).join('')
    + `<path d="M60 40 H300 L214 96 V118 H146 V96 Z" fill="${p.deep}" stroke="${p.light}" stroke-width="3" stroke-linejoin="round"/>`
    + `<circle cx="166" cy="138" r="9" fill="${p.accent}"/><circle cx="194" cy="138" r="9" fill="${p.accent}"/>`
    + `<path d="M318 30 L344 56 M344 30 L318 56" stroke="#e0533d" stroke-width="5" stroke-linecap="round"/>`,
  docs: () => [['PPT', '#d35230', 40], ['DOCX', '#2b579a', 140], ['XLSX', '#1f7246', 240]].map(([label, colour, x]) => `<rect x="${x}" y="20" width="84" height="110" rx="10" fill="#f4f6fb"/><path d="M${x + 60} 20 L${x + 84} 44 H${x + 60} Z" fill="#cfd7e4"/><rect x="${x}" y="84" width="84" height="30" fill="${colour}"/><text x="${x + 42}" y="105" text-anchor="middle" font-size="16" font-weight="800" fill="#ffffff">${label}</text>`).join(''),
  calendar: (p) => {
    let out = `<rect x="40" y="18" width="190" height="116" rx="12" fill="#101a2e"/><rect x="40" y="18" width="190" height="26" rx="12" fill="${p.accent}"/><rect x="40" y="32" width="190" height="12" fill="${p.accent}"/>`;
    for (let row = 0; row < 3; row += 1) for (let col = 0; col < 6; col += 1) out += `<rect x="${52 + col * 29}" y="${54 + row * 26}" width="20" height="18" rx="4" fill="${(row * 6 + col) % 7 === 3 ? p.light : '#2a3a5c'}"/>`;
    return out + `<circle cx="290" cy="76" r="44" fill="none" stroke="#ffffff" stroke-width="6"/><path d="M290 76 V48 M290 76 L310 88" stroke="${p.light}" stroke-width="6" stroke-linecap="round"/>`;
  },
  csv: (p) => `<rect x="110" y="14" width="140" height="122" rx="12" fill="#f4f6fb"/><path d="M214 14 L250 50 H214 Z" fill="#cfd7e4"/>`
    + [0, 1, 2, 3].map((row) => `<text x="126" y="${72 + row * 18}" font-size="15" fill="#3a4d75" class="mono">a,b,c,d</text>`).join('') + `<rect x="110" y="24" width="64" height="26" rx="6" fill="${p.accent}"/><text x="142" y="43" text-anchor="middle" font-size="15" font-weight="800" fill="#ffffff">CSV</text>`,
  sliders: (p) => [0.3, 0.7, 0.5].map((share, index) => `<rect x="60" y="${34 + index * 38}" width="240" height="10" rx="5" fill="#22304f"/><rect x="60" y="${34 + index * 38}" width="${240 * share}" height="10" rx="5" fill="${p.accent}"/><circle cx="${60 + 240 * share}" cy="${39 + index * 38}" r="13" fill="#ffffff" stroke="${p.accent}" stroke-width="4"/>`).join(''),
  import: (p) => `<rect x="50" y="20" width="96" height="112" rx="10" fill="#f4f6fb"/><rect x="50" y="88" width="96" height="28" fill="#1f7246"/><text x="98" y="108" text-anchor="middle" font-size="15" font-weight="800" fill="#ffffff">XLSX</text>`
    + `<path d="M160 76 H214" stroke="${p.light}" stroke-width="6"/><path d="M204 62 l14 14 l-14 14" fill="none" stroke="${p.light}" stroke-width="6"/>`
    + `<rect x="230" y="34" width="90" height="84" rx="14" fill="${p.accent}"/><path d="M252 76 l14 14 l26 -30" fill="none" stroke="#ffffff" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>`,
  transfer: (p) => [60, 240].map((x) => `<rect x="${x}" y="30" width="70" height="92" rx="10" fill="#101a2e" stroke="#ffffff" stroke-width="3"/>${[0, 1, 2].map((row) => `<rect x="${x + 12}" y="${44 + row * 24}" width="46" height="12" rx="5" fill="${p.light}"/>`).join('')}`).join('')
    + `<path d="M140 62 H226" stroke="${p.accent}" stroke-width="6"/><path d="M216 50 l12 12 l-12 12" fill="none" stroke="${p.accent}" stroke-width="6"/><path d="M226 96 H140" stroke="${p.light}" stroke-width="6"/><path d="M150 84 l-12 12 l12 12" fill="none" stroke="${p.light}" stroke-width="6"/>`,
  lock: (p) => `<rect x="70" y="64" width="90" height="70" rx="12" fill="${p.accent}"/><path d="M88 64 V46 a27 27 0 0 1 54 0 V64" fill="none" stroke="#ffffff" stroke-width="9"/><circle cx="115" cy="98" r="10" fill="#ffffff"/>`
    + [[220, p.light], [270, '#ffffff'], [320, p.series[2]]].map(([x, colour]) => `<circle cx="${x}" cy="62" r="18" fill="${colour}"/><path d="M${x - 28} 128 a28 28 0 0 1 56 0 Z" fill="${colour}"/>`).join(''),
  backup: (p) => `<circle cx="120" cy="76" r="50" fill="none" stroke="#ffffff" stroke-width="7"/><path d="M120 76 V44 M120 76 L144 90" stroke="${p.light}" stroke-width="7" stroke-linecap="round"/><path d="M62 54 l8 22 l20 -10" fill="none" stroke="${p.accent}" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>`
    + [0, 1, 2].map((index) => `<ellipse cx="270" cy="${46 + index * 30}" rx="56" ry="14" fill="${index === 0 ? p.accent : p.deep}" stroke="#ffffff" stroke-width="2"/>`).join(''),
  hints: () => [['To check', '#e0533d', 'Coverage hole'], ['Worth a look', '#f0a830', 'Overshooting'], ['Fine', '#1f9d55', 'PCI']].map(([label, colour, text], index) => `<circle cx="52" cy="${36 + index * 40}" r="11" fill="${colour}"/><text x="74" y="${42 + index * 40}" font-size="18" font-weight="700" fill="#ffffff">${text}</text><rect x="230" y="${24 + index * 40}" width="110" height="26" rx="13" fill="${colour}" opacity=".85"/><text x="285" y="${42 + index * 40}" text-anchor="middle" font-size="14" font-weight="700" fill="#ffffff">${label}</text>`).join(''),
  compare: (p) => [['Its network', 0.82, '#e0533d', '9.0%'], ['Others', 0.12, p.light, '0.4%']].map(([name, share, colour, value], index) => `<text x="40" y="${52 + index * 56}" font-size="18" fill="#c9d4e6">${name}</text><rect x="150" y="${34 + index * 56}" width="170" height="26" rx="13" fill="#22304f"/><rect x="150" y="${34 + index * 56}" width="${Math.max(14, 170 * share)}" height="26" rx="13" fill="${colour}"/><text x="330" y="${54 + index * 56}" text-anchor="end" font-size="16" font-weight="800" fill="#ffffff">${value}</text>`).join(''),
  tags: (p) => [['P1', '#c0392b'], ['P2', '#e0533d'], ['P3', '#f0a830'], ['Bug', p.accent], ['Feature', p.light]].map(([label, colour], index) => `<rect x="${30 + (index % 3) * 104}" y="${30 + Math.floor(index / 3) * 52}" width="94" height="38" rx="19" fill="${colour}"/><text x="${77 + (index % 3) * 104}" y="${55 + Math.floor(index / 3) * 52}" text-anchor="middle" font-size="18" font-weight="800" fill="#ffffff">${label}</text>`).join(''),
  timeline: (p) => `<path d="M30 80 H330" stroke="#2a3a5c" stroke-width="6" stroke-linecap="round"/>`
    + [[50, '#1f9d55'], [100, '#1f9d55'], [150, '#c8d23a'], [190, '#e0533d'], [240, '#f0a830'], [290, '#1f9d55']].map(([x, colour], index) => `<circle cx="${x}" cy="80" r="${index === 3 ? 16 : 10}" fill="${colour}" stroke="${index === 3 ? '#ffffff' : 'none'}" stroke-width="4"/>`).join('')
    + `<text x="190" y="46" text-anchor="middle" font-size="18" font-weight="700" fill="#ffffff">the call</text><text x="50" y="122" font-size="15" fill="#9fb0cc">−15 min</text><text x="290" y="122" text-anchor="middle" font-size="15" fill="#9fb0cc">+15 min</text>`,
  health: (p) => {
    const angle = 0.72 * 2 * Math.PI - Math.PI / 2;
    return `<circle cx="120" cy="76" r="50" fill="none" stroke="#22304f" stroke-width="18"/><path d="M120 26 A50 50 0 1 1 ${(120 + 50 * Math.cos(angle)).toFixed(1)} ${(76 + 50 * Math.sin(angle)).toFixed(1)}" fill="none" stroke="#f0a830" stroke-width="18" stroke-linecap="round"/>`
      + `<text x="120" y="84" text-anchor="middle" font-size="22" font-weight="800" fill="#ffffff">4.1%</text><text x="200" y="66" font-size="18" fill="#c9d4e6">NQ rate of its site</text><text x="200" y="96" font-size="18" fill="#9fb0cc">× 1.6 its operator</text>`;
  },
  bars: (p) => [40, 76, 58, 104, 88, 120].map((height, index) => `<rect x="${50 + index * 46}" y="${134 - height}" width="32" height="${height}" rx="6" fill="${index === 5 ? p.accent : p.light}" opacity="${index === 5 ? 1 : 0.75}"/>`).join(''),
  density: (p) => {
    let out = '';
    for (let row = 0; row < 4; row += 1) for (let col = 0; col < 7; col += 1) {
      const x = 52 + col * 40 + (row % 2) * 20; const y = 28 + row * 32; const value = (Math.sin(col * 1.3 + row) + 1) / 2;
      out += `<path d="M${x} ${y - 16} l14 8 v16 l-14 8 l-14 -8 v-16 Z" fill="${value > 0.6 ? p.accent : value > 0.3 ? p.light : '#2a3a5c'}" opacity="${0.5 + value / 2}"/>`;
    }
    return out;
  },
  snapshot: (p) => `${MINIS.table(p)}<circle cx="300" cy="112" r="30" fill="${p.deep}" stroke="#ffffff" stroke-width="4"/><path d="M300 112 V96 M300 112 L312 118" stroke="#ffffff" stroke-width="4" stroke-linecap="round"/>`,
  chart: (p) => `<path d="M50 20 V130 H320" fill="none" stroke="#7d8aa3" stroke-width="3"/>` + [50, 80, 64, 100].map((height, index) => `<rect x="${80 + index * 58}" y="${126 - height}" width="38" height="${height}" rx="6" fill="${index === 3 ? p.accent : p.light}"/>`).join(''),
  sql: (p) => [['SELECT', 'operator, avg(mos)'], ['FROM', 'cdr_voice'], ['GROUP BY', 'operator']].map(([keyword, rest], index) => `<text x="36" y="${44 + index * 36}" font-size="19" font-weight="800" fill="${p.light}" class="mono">${keyword}</text><text x="${36 + keyword.length * 12 + 10}" y="${44 + index * 36}" font-size="19" fill="#ffffff" class="mono">${rest}</text>`).join(''),
  cdr: (p) => `${MINIS.table(p)}<circle cx="282" cy="96" r="32" fill="none" stroke="#ffffff" stroke-width="8"/><path d="M304 118 L330 144" stroke="#ffffff" stroke-width="10" stroke-linecap="round"/>`,
  users: (p) => [[90, p.accent, 'Super-admin'], [180, p.light, 'Admin'], [270, p.series[2], 'User']].map(([x, colour, label]) => `<circle cx="${x}" cy="48" r="22" fill="${colour}"/><path d="M${x - 34} 112 a34 34 0 0 1 68 0 Z" fill="${colour}"/><text x="${x}" y="138" text-anchor="middle" font-size="15" font-weight="700" fill="#c9d4e6">${label}</text>`).join(''),
};

// -- the pictures of the terms of an equation slide (460 × 270, in the colour of each term) ------------------------------
const diamond = (x, y, fill, size = 13) => `<rect x="${x - size}" y="${y - size}" width="${size * 2}" height="${size * 2}" rx="4" fill="${fill}" stroke="#ffffff" stroke-width="3.5" transform="rotate(45 ${x} ${y})"/>`;
const pill = (x, y, text, fill, color = '#ffffff', size = 17) => {
  const width = text.length * size * 0.58 + 26;
  return `<rect x="${(x - width / 2).toFixed(1)}" y="${y - size}" width="${width.toFixed(1)}" height="${size * 1.9}" rx="${size * 0.95}" fill="${fill}"/><text x="${x}" y="${(y + size * 0.36).toFixed(1)}" text-anchor="middle" font-size="${size}" font-weight="800" fill="${color}">${escape(text)}</text>`;
};
const MUTED = '#55627c';
const TERMS = {
  // The failures of one car along its drive, each linked to the one before it; the one after a long drive starts another run.
  run(c) {
    let out = `<path d="M18 228 C 120 228, 150 150, 250 150 S 380 120, 446 70" fill="none" stroke="#1d2a45" stroke-width="30" stroke-linecap="round"/>`;
    out += `<path d="M18 228 C 120 228, 150 150, 250 150 S 380 120, 446 70" fill="none" stroke="#2f4066" stroke-width="3" stroke-dasharray="14 12"/>`;
    out += `<g transform="translate(6 176)">${icon('TbCar', '#ffffff', 46)}</g>`;
    const stops = [[96, 216], [168, 176], [246, 151]];
    stops.slice(1).forEach(([x, y], index) => {
      const [px, py] = stops[index];
      out += `<path d="M${px} ${py - 18} Q ${(px + x) / 2} ${Math.min(py, y) - 74} ${x} ${y - 18}" fill="none" stroke="${c}" stroke-width="4" stroke-dasharray="7 6"/>`;
      out += pill((px + x) / 2, Math.min(py, y) - 58, index ? '6 min' : '4 min', c, INK, 15);
    });
    stops.forEach(([x, y]) => { out += diamond(x, y, c); });
    // Too far after the last one: a time-window issue of its own.
    out += `<path d="M262 132 Q 340 60 404 92" fill="none" stroke="${MUTED}" stroke-width="3" stroke-dasharray="5 7"/>`;
    out += `<g transform="translate(320 64)"><circle r="15" fill="${INK}" stroke="#e0533d" stroke-width="3"/><path d="M-6 -6 L6 6 M6 -6 L-6 6" stroke="#e0533d" stroke-width="3.5" stroke-linecap="round"/></g>`;
    out += diamond(408, 96, MUTED, 11);
    out += pill(360, 252, '40 km later: a new one', '#22304f', '#c9d4e6', 15);
    return out;
  },
  // The calls that failed around a site, within half its ISD of each other or at it, linked to each other.
  cluster(c) {
    let out = [[0, 70, 460, 40], [0, 210, 460, 236], [120, 0, 92, 270], [350, 0, 384, 270]].map(([x1, y1, x2, y2]) => `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#1a2742" stroke-width="14" stroke-linecap="round"/>`).join('');
    const [sx, sy] = [232, 140];
    out += `<circle cx="${sx}" cy="${sy}" r="104" fill="${c}" opacity=".10"/><circle cx="${sx}" cy="${sy}" r="104" fill="none" stroke="${c}" stroke-width="3" stroke-dasharray="10 8"/>`;
    [-90, 30, 150].forEach((angle) => {
      const [a, b] = [angle - 28, angle + 28].map((degrees) => [sx + 70 * Math.cos(degrees * Math.PI / 180), sy + 70 * Math.sin(degrees * Math.PI / 180)]);
      out += `<path d="M${sx} ${sy} L${a[0].toFixed(1)} ${a[1].toFixed(1)} A70 70 0 0 1 ${b[0].toFixed(1)} ${b[1].toFixed(1)} Z" fill="${c}" opacity=".28"/>`;
    });
    const calls = [[176, 96], [286, 104], [196, 196], [300, 178], [232, 66], [158, 150]];
    calls.forEach(([x, y]) => { out += `<line x1="${sx}" y1="${sy}" x2="${x}" y2="${y}" stroke="${c}" stroke-width="2.5" opacity=".55"/>`; });
    out += `<path d="M${sx} ${sy - 20} L${sx + 16} ${sy + 12} L${sx - 16} ${sy + 12} Z" fill="#ffffff" stroke="${INK}" stroke-width="3"/>`;
    calls.forEach(([x, y]) => { out += diamond(x, y, c, 11); });
    [[60, 120], [404, 214], [400, 40]].forEach(([x, y]) => { out += diamond(x, y, MUTED, 10); });
    out += pill(sx, 262, '0.5 ISD around the sites', '#22304f', '#c9d4e6', 15);
    out += pill(392, 140, 'same site', c, INK, 14);
    return out;
  },
  // The calls linked in time or in distance, all of them in one hotspot.
  hotspot(c, p, { left = '#15aabf', right = '#2f9e44' } = {}) {
    const [l, r, y, radius] = [172, 288, 132, 96];
    let out = `<circle cx="${l}" cy="${y}" r="${radius + 10}" fill="${c}"/><circle cx="${r}" cy="${y}" r="${radius + 10}" fill="${c}"/>`;
    out += `<circle cx="${l}" cy="${y}" r="${radius + 4}" fill="#131d33"/><circle cx="${r}" cy="${y}" r="${radius + 4}" fill="#131d33"/>`;
    out += `<circle cx="${l}" cy="${y}" r="${radius}" fill="${left}" opacity=".16"/><circle cx="${r}" cy="${y}" r="${radius}" fill="${right}" opacity=".16"/>`;
    out += `<circle cx="${l}" cy="${y}" r="${radius}" fill="none" stroke="${left}" stroke-width="3" stroke-dasharray="9 7"/><circle cx="${r}" cy="${y}" r="${radius}" fill="none" stroke="${right}" stroke-width="3" stroke-dasharray="9 7"/>`;
    [[120, 100], [140, 176], [196, 70], [264, 194], [330, 96], [346, 160], [230, 128]].forEach(([x, cy]) => { out += diamond(x, cy, c, 11); });
    out += pill(230, 132, 'OR', '#ffffff', c, 22);
    out += `<text x="${l - 60}" y="20" font-size="17" font-weight="800" fill="${left}">Time window</text><text x="${r + 60}" y="20" text-anchor="end" font-size="17" font-weight="800" fill="${right}">Cluster</text>`;
    out += pill(230, 260, 'AND: close in time and distance at once', '#22304f', '#c9d4e6', 14);
    return out;
  },
};

// -- slides ----------------------------------------------------------------------------------------------------------
function heading(slide) {
  return `<p class="kicker">${escape(slide.kicker || slide.section)}</p><h2>${escape(slide.title)}</h2>${slide.lead ? `<p class="lead">${escape(slide.lead)}</p>` : ''}`;
}

const TEMPLATES = {
  cover(slide, deck, p) {
    const orbit = (slide.icons || []).map((name, index, all) => {
      const angle = -Math.PI / 2 + index * (2 * Math.PI / all.length) + 0.35;
      const x = 1450 + Math.cos(angle) * 300; const y = 520 + Math.sin(angle) * 300;
      return `<line x1="1450" y1="520" x2="${x}" y2="${y}" stroke="#2a3a5c" stroke-width="3"/><circle cx="${x}" cy="${y}" r="58" fill="#16213a" stroke="${p.accent}" stroke-width="3"/><g transform="translate(${x - 30} ${y - 30})">${icon(name, p.light, 60)}</g>`;
    }).join('');
    const words = slide.title.split(' ');
    const title = words.length > 1 ? `${escape(words.slice(0, -1).join(' '))}<br><span style="color:${p.light}">${escape(words.at(-1))}</span>` : `<span style="color:${p.light}">${escape(slide.title)}</span>`;
    return `<svg width="1920" height="1080" viewBox="0 0 1920 1080" style="position:absolute;inset:0" aria-hidden="true">
      <defs><radialGradient id="glow"><stop offset="0" stop-color="${p.accent}" stop-opacity=".75"/><stop offset="1" stop-color="${p.accent}" stop-opacity="0"/></radialGradient></defs>
      <circle cx="1450" cy="520" r="300" fill="none" stroke="#2a3a5c" stroke-width="3" stroke-dasharray="10 14"/>${orbit}
      <circle cx="1450" cy="520" r="230" fill="url(#glow)"/><circle cx="1450" cy="520" r="120" fill="${p.accent}"/>
      <g transform="translate(1380 450)">${icon(slide.icon, '#ffffff', 140)}</g></svg>
      <div style="position:relative;margin-top:150px;max-width:${slide.width || 1000}px">
        <p class="kicker">${escape(slide.kicker)}</p>
        <h1 style="margin-top:26px">${title}</h1>
        <p class="lead" style="font-size:36px;margin-top:34px">${escape(slide.lead)}</p>
        <div style="display:flex;gap:14px;margin-top:46px;flex-wrap:wrap">${(slide.tags || []).map((tag) => `<span class="tag" style="background:${p.soft}"><i style="background:${p.light}"></i>${escape(tag)}</span>`).join('')}</div>
      </div>`;
  },
  cards(slide, deck, p) {
    const columns = slide.columns || Math.min(4, slide.cards.length);
    return `${heading(slide)}<div class="content"><div class="grid" style="grid-template-columns:repeat(${columns},1fr)">${slide.cards.map((card) => `
      <div class="card" style="${card.highlight ? `border-color:${p.accent};` : ''}">${badge(card.icon, card.color || p.accent)}
        <h3 style="margin-top:20px">${escape(card.title)}</h3><p>${escape(card.text)}</p>
        ${card.chips ? `<div class="chips">${card.chips.map((name) => (MODULES[name] ? moduleChip(name) : chip(name, '#22304f'))).join('')}</div>` : ''}</div>`).join('')}</div>
      ${slide.note ? `<p class="note">${escape(slide.note)}</p>` : ''}</div>`;
  },
  steps(slide, deck, p) {
    const count = slide.steps.length;
    return `${heading(slide)}<div class="content"><div style="display:flex;align-items:stretch;gap:0">${slide.steps.map((step, index) => `
      <div class="card" style="flex:1;${index === slide.highlight ? `border-color:${p.accent};` : ''}">
        <div style="display:flex;align-items:center;gap:16px">${badge(step.icon, p.accent, 60, 32)}<span class="mono" style="font-size:30px;color:${p.light};font-weight:700">${String(index + 1).padStart(2, '0')}</span></div>
        <h3 style="margin-top:22px;font-size:32px">${escape(step.title)}</h3><p style="font-size:23px">${escape(step.text)}</p></div>
      ${index < count - 1 ? `<div style="flex:none;width:44px;display:grid;place-items:center">${icon('TbChevronRight', p.light, 40)}</div>` : ''}`).join('')}</div>
      ${slide.note ? `<p class="note">${escape(slide.note)}</p>` : ''}</div>`;
  },
  split(slide, deck, p) {
    const visual = VISUALS[slide.visual](p, slide.options || {});
    return `${heading(slide)}<div class="content"><div style="display:flex;gap:56px;align-items:center">
      <div style="flex:1;display:flex;flex-direction:column;gap:22px">${slide.points.map((point) => `
        <div style="display:flex;gap:22px;align-items:flex-start">${badge(point.icon, point.color || p.accent, 56, 30)}
          <div><h3 style="font-size:30px">${escape(point.title)}</h3><p style="font-size:23px;color:var(--soft);line-height:1.4;margin-top:6px">${escape(point.text)}</p></div></div>`).join('')}</div>
      <div class="card" style="width:860px;flex:none;padding:20px"><svg width="820" height="560" viewBox="0 0 820 560" font-family="Helvetica Neue, Arial, sans-serif">${visual}</svg></div></div></div>`;
  },
  // A visual as wide as the slide (1656 × 560), such as a view of the tool as it looks, framed (bare: on the slide
  // itself), with the facts it shows below it.
  showcase(slide, deck, p) {
    const svg = `<svg width="1656" height="560" viewBox="0 0 1656 560" font-family="Helvetica Neue, Arial, sans-serif">${VISUALS[slide.visual](p, slide.options || {})}</svg>`;
    return `${heading(slide)}<div class="content">${slide.bare ? `<div class="showcase is-bare">${svg}</div>` : `<div class="card showcase" style="box-shadow:0 36px 110px ${p.glow}">${svg}</div>`}
      ${slide.facts ? `<div class="facts" style="grid-template-columns:repeat(${slide.facts.length},1fr)">${slide.facts.map((fact) => `<span class="fact">${icon(fact.icon, p.light, 26)}${escape(fact.text)}</span>`).join('')}</div>` : ''}</div>`;
  },
  // One idea in the middle and its parts around it, joined to it.
  hub(slide, deck, p) {
    const half = Math.ceil(slide.items.length / 2);
    const sides = [slide.items.slice(0, half), slide.items.slice(half)];
    const height = 560; const gap = 22; const width = 1696; const sideWidth = 590;
    const lines = sides.map((items, side) => items.map((_item, index) => {
      const itemHeight = (height - (items.length - 1) * gap) / items.length;
      const y = index * (itemHeight + gap) + itemHeight / 2; const x = side ? width - sideWidth : sideWidth;
      return `<path d="M${width / 2} ${height / 2} L${x} ${y.toFixed(1)}" stroke="${p.light}" stroke-width="3" stroke-dasharray="10 9" opacity=".7"/><circle cx="${x}" cy="${y.toFixed(1)}" r="9" fill="${p.accent}" stroke="#ffffff" stroke-width="3"/>`;
    }).join('')).join('');
    const column = (items) => `<div class="hub-side">${items.map((item) => `<div class="card hub-item">${badge(item.icon, p.accent, 60, 32)}
      <div><h3>${escape(item.title)}</h3><p>${escape(item.text)}</p></div></div>`).join('')}</div>`;
    return `${heading(slide)}<div class="content"><div class="hub" style="grid-template-columns:${sideWidth}px 1fr ${sideWidth}px">
      <svg class="hub-lines" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">${lines}</svg>
      ${column(sides[0])}<div class="hub-core"><div class="hub-circle">${icon(slide.center.icon, '#ffffff', 96)}<span>${escape(slide.center.title)}</span></div></div>${column(sides[1])}</div>
      ${slide.note ? `<p class="note">${escape(slide.note)}</p>` : ''}</div>`;
  },
  // Cards with a small picture each, for the ideas that are best listed.
  tiles(slide, deck, p) {
    const columns = slide.columns || Math.min(4, slide.tiles.length);
    const rows = Math.ceil(slide.tiles.length / columns);
    return `${heading(slide)}<div class="content"><div class="grid" style="grid-template-columns:repeat(${columns},1fr)">${slide.tiles.map((tile) => `
      <div class="card tile"><div class="tile-visual" style="height:${rows > 1 ? 162 : 236}px"><svg viewBox="0 0 360 150" width="100%" height="100%" preserveAspectRatio="xMidYMid meet" font-family="Helvetica Neue, Arial, sans-serif">${MINIS[tile.mini](p)}</svg></div>
        <h3>${escape(tile.title)}</h3><p>${escape(tile.text)}</p></div>`).join('')}</div>
      ${slide.note ? `<p class="note">${escape(slide.note)}</p>` : ''}</div>`;
  },
  // An equation of ideas: terms with a picture each (TERMS), joined by operators (A OR B = C), the last one the result, and
  // the facts they share below.
  equation(slide, deck, p) {
    const parts = slide.terms.map((term, index) => {
      const deep = mix(term.color, INK, 0.55);
      const card = `<div class="card eq-term${index === slide.terms.length - 1 ? ' is-result' : ''}" style="border-top-color:${term.color};${index === slide.terms.length - 1 ? `box-shadow:0 0 0 2px ${term.color},0 0 90px ${mix(term.color, INK, 0.35)}` : ''}">
        <div class="eq-art" style="background:radial-gradient(120% 120% at 50% 0%, ${mix(term.color, '#131d33', 0.72)}, #131d33 72%)"><svg viewBox="0 0 460 270" width="100%" height="100%" preserveAspectRatio="xMidYMid meet" font-family="Helvetica Neue, Arial, sans-serif">${TERMS[term.art](term.color, p, term.options || {})}</svg></div>
        <div class="eq-body"><div class="eq-head">${badge(term.icon, term.color, 52, 30)}<h3>${escape(term.title)}</h3><span class="eq-tag" style="color:${mix(term.color, '#ffffff', 0.35)};border-color:${term.color}">${escape(term.tag)}</span></div>
          <p>${escape(term.text)}</p><div class="chips">${term.rules.map((rule) => chip(rule, deep)).join('')}</div></div></div>`;
      return index ? `<div class="eq-op"><span class="${slide.operators[index - 1].length === 1 ? 'is-symbol' : ''}" style="background:radial-gradient(circle at 30% 28%, ${p.light}, ${p.accent} 60%, ${p.deep});box-shadow:0 0 40px ${p.glow}">${escape(slide.operators[index - 1])}</span></div>${card}` : card;
    });
    return `${heading(slide)}<div class="content" style="padding-top:28px"><div class="eq">${parts.join('')}</div>
      ${slide.facts ? `<div class="facts">${slide.facts.map((fact) => `<span class="fact">${icon(fact.icon, p.light, 26)}${escape(fact.text)}</span>`).join('')}</div>` : ''}</div>`;
  },
  highlights(slide, deck, p) {
    return `${heading(slide)}<div class="content"><div class="grid" style="grid-template-columns:repeat(${slide.items.length},1fr)">${slide.items.map((item) => `
      <div class="card" style="padding:40px 36px"><p style="font-size:84px;font-weight:800;letter-spacing:-2px;color:${p.light};line-height:1">${escape(item.value)}</p>
        <h3 style="margin-top:22px">${escape(item.label)}</h3><p>${escape(item.text)}</p></div>`).join('')}</div>
      ${slide.note ? `<p class="note">${escape(slide.note)}</p>` : ''}</div>`;
  },
  // The figures of a change: each a big multiplier and two bars to scale, before and now.
  impact(slide, deck, p) {
    return `${heading(slide)}<div class="content"><div class="grid" style="grid-template-columns:repeat(${slide.items.length},1fr)">${slide.items.map((item) => {
      const now = Math.max(0.025, item.now / item.before);
      const bar = (label, share, value, fill, strong) => `<div class="impact-row"><span class="impact-label">${escape(label)}</span>
        <div class="impact-track"><div class="impact-bar" style="width:${(share * 100).toFixed(1)}%;background:${fill};${strong ? `box-shadow:0 0 26px ${p.glow}` : ''}"></div></div>
        <span class="impact-value" style="color:${strong ? p.light : 'var(--muted)'}">${escape(value)}</span></div>`;
      return `<div class="card impact" style="border-top:6px solid ${p.accent}">
        <div style="display:flex;align-items:center;gap:16px">${badge(item.icon, p.accent, 54, 30)}<h3>${escape(item.label)}</h3></div>
        <p class="impact-figure" style="background:linear-gradient(120deg, #ffffff, ${p.light});-webkit-background-clip:text;background-clip:text;color:transparent">${escape(item.value)}</p>
        ${bar('Before', 1, item.beforeText, '#55627c', false)}${bar('Now', now, item.nowText, `linear-gradient(90deg, ${p.accent}, ${p.light})`, true)}
        <p style="margin-top:22px">${escape(item.text)}</p></div>`;
    }).join('')}</div>
      ${slide.note ? `<p class="note">${escape(slide.note)}</p>` : ''}</div>`;
  },
  closing(slide, deck, p) {
    return `${heading(slide)}<div class="content"><div style="display:flex;gap:44px">
      <div class="card" style="flex:1.2;padding:38px 42px"><p class="kicker" style="font-size:20px;color:${p.light}">In the Help</p>
        <div style="display:flex;flex-direction:column;gap:18px;margin-top:22px">${slide.links.map((link) => `
          <div style="display:flex;gap:18px;align-items:center">${icon('TbArrowRight', p.light, 30)}<span style="font-size:27px"><b>${escape(link.title)}</b><span style="color:var(--soft)"> · ${escape(link.text)}</span></span></div>`).join('')}</div></div>
      <div class="card" style="flex:1;padding:38px 42px"><p class="kicker" style="font-size:20px;color:${p.light}">Works with</p>
        <div class="chips" style="margin-top:24px;gap:14px">${slide.modules.map((name) => moduleChip(name)).join('')}</div>
        <p style="font-size:25px;color:var(--soft);margin-top:30px;line-height:1.45">${escape(slide.note)}</p></div></div></div>`;
  },
};

function css(p) {
  return `
  :root { --ink: ${INK}; --panel: #131d33; --panel2: #1a2742; --line: #2a3a5c; --text: #eef2f9; --muted: #9fb0cc; --soft: #c9d4e6; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { background: var(--ink); }
  body { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; color: var(--text); }
  .slide { width: 1920px; height: 1080px; position: relative; overflow: hidden; padding: 96px 112px 0;
    background: radial-gradient(1200px 700px at 88% -10%, ${p.glow}, transparent 60%),
                radial-gradient(900px 600px at -10% 110%, rgba(19, 133, 151, .16), transparent 60%), var(--ink); }
  .slide + .slide { margin-top: 40px; }
  .slide { display: flex; flex-direction: column; }
  .slide::before { content: ''; position: absolute; top: 40px; right: 112px; width: 80px; height: 70px; z-index: 2;
    background: url(${LOGO}) center / contain no-repeat; }
  .content { flex: 1; display: flex; flex-direction: column; justify-content: center; padding: 36px 0 110px; }
  .kicker { font-size: 24px; letter-spacing: 4px; text-transform: uppercase; color: ${p.light}; font-weight: 700; }
  h1 { font-size: 124px; line-height: .98; font-weight: 800; letter-spacing: -3px; }
  h2 { font-size: 66px; line-height: 1.05; font-weight: 800; letter-spacing: -1.5px; margin-top: 14px; }
  .lead { font-size: 30px; line-height: 1.38; color: var(--soft); max-width: 1560px; margin-top: 22px; }
  .note { font-size: 24px; color: var(--muted); margin-top: 30px; max-width: 1640px; line-height: 1.4; }
  .foot { position: absolute; left: 112px; right: 112px; bottom: 44px; display: flex; justify-content: space-between; font-size: 20px; color: var(--muted); }
  .foot b { color: ${p.light}; font-weight: 700; }
  .card { background: linear-gradient(180deg, var(--panel2), var(--panel)); border: 1px solid var(--line); border-radius: 26px; padding: 32px 34px; }
  .card h3, h3 { font-size: 34px; font-weight: 800; letter-spacing: -.5px; }
  .card p { font-size: 24px; line-height: 1.42; color: var(--soft); margin-top: 12px; }
  .grid { display: grid; gap: 26px; }
  .icon { border-radius: 18px; display: grid; place-items: center; flex: none; }
  .tag { display: inline-flex; align-items: center; gap: 10px; border-radius: 999px; padding: 8px 18px; font-size: 22px; font-weight: 700; color: #fff; }
  .tag i { width: 12px; height: 12px; border-radius: 50%; display: inline-block; }
  .chips { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 18px; }
  .chip { font-size: 20px; font-weight: 700; padding: 7px 15px; border-radius: 12px; }
  .mono { font-family: Menlo, 'SF Mono', Consolas, monospace; }
  .hub { position: relative; display: grid; height: 560px; }
  .hub-lines { position: absolute; left: 0; top: 0; z-index: 0; }
  .hub-side { position: relative; z-index: 1; display: flex; flex-direction: column; gap: 22px; height: 560px; }
  .hub-item { flex: 1; display: flex; gap: 22px; align-items: center; padding: 22px 28px; }
  .hub-item h3 { font-size: 30px; }
  .hub-item p { font-size: 22px; margin-top: 8px; }
  .hub-core { position: relative; z-index: 1; display: grid; place-items: center; }
  .hub-circle { width: 300px; height: 300px; border-radius: 50%; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px;
    background: radial-gradient(circle at 32% 28%, ${p.light}, ${p.accent} 58%, ${p.deep}); box-shadow: 0 0 90px ${p.glow}, 0 0 0 14px ${p.glow}; }
  .hub-circle span { font-size: 28px; font-weight: 800; text-align: center; max-width: 230px; line-height: 1.15; }
  .tile { padding: 0 0 28px; overflow: hidden; }
  .tile-visual { padding: 12px 14px; margin-bottom: 24px; border-bottom: 1px solid var(--line);
    background: radial-gradient(120% 140% at 0% 0%, ${p.soft}, var(--panel) 70%); }
  .tile h3, .tile p { padding: 0 30px; }
  .tile h3 { font-size: 30px; }
  .tile p { font-size: 22px; }
  .eq { display: grid; grid-template-columns: 1fr 92px 1fr 92px 1fr; align-items: stretch; }
  .eq-term { padding: 0; overflow: hidden; border-top: 6px solid; box-shadow: 0 30px 70px rgba(0, 0, 0, .35); }
  .eq-art { height: 270px; border-bottom: 1px solid var(--line); }
  .eq-body { padding: 22px 28px 26px; }
  .eq-head { display: flex; align-items: center; gap: 16px; }
  .eq-head h3 { font-size: 34px; flex: 1; }
  .eq-tag { font-size: 17px; font-weight: 800; letter-spacing: 1.5px; text-transform: uppercase; border: 2px solid; border-radius: 999px; padding: 5px 12px; white-space: nowrap; }
  .eq-term p { font-size: 22px; margin-top: 14px; }
  .eq-term .chips { margin-top: 16px; }
  .eq-term .chip { font-size: 18px; }
  .eq-op { display: grid; place-items: center; }
  .eq-op span { width: 76px; height: 76px; border-radius: 50%; display: grid; place-items: center; font-size: 26px; font-weight: 900; color: #fff; letter-spacing: 1px; }
  .eq-op span.is-symbol { font-size: 40px; }
  .facts { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-top: 24px; }
  .impact { padding: 34px 32px 32px; box-shadow: 0 30px 70px rgba(0, 0, 0, .35); }
  .impact h3 { font-size: 30px; }
  .impact .impact-figure { font-size: 112px; font-weight: 900; letter-spacing: -4px; line-height: 1.05; margin: 22px 0 18px; }
  .impact-row { display: grid; grid-template-columns: 98px 1fr 96px; align-items: center; gap: 12px; margin-top: 14px; }
  .impact-label { font-size: 18px; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase; color: var(--muted); }
  .impact-track { height: 22px; border-radius: 11px; background: #0f1830; overflow: hidden; }
  .impact-bar { height: 100%; border-radius: 11px; }
  .impact-value { font-size: 21px; font-weight: 800; text-align: right; }
  .fact { display: flex; align-items: center; gap: 14px; padding: 12px 20px 12px 16px; border-radius: 20px; background: #131d33; border: 1px solid var(--line); font-size: 20px; line-height: 1.3; color: var(--soft); }
  .fact svg { flex: none; }
  .showcase { flex: none; padding: 18px; }
  .showcase.is-bare { padding: 0 20px; }
  .showcase svg { display: block; }`;
}

function html(deck) {
  const p = palette(deck.accent);
  const slides = deck.slides.map((slide, index) => `<!-- ${index + 1} · ${escape(slide.title)} -->
<section class="slide" id="s${index + 1}">${TEMPLATES[slide.type](slide, deck, p)}
  <div class="foot"><span><b>${escape(deck.name)}</b> · ${escape(slide.footer || slide.section)}</span><span>${index === 0 ? 'Version 0.9.0' : String(index + 1).padStart(2, '0')}</span></div>
</section>`).join('\n\n');
  return `<!doctype html>
<!-- Drawn by module_decks.js from content.js: change content.js and run it again rather than this file. -->
<html lang="en"><head><meta charset="utf-8"><title>${escape(deck.name)}</title><style>${css(p)}</style></head><body>
${slides}
<script>
  // ?slide=N shows slide N alone, and ?slides=A-B the slides from A to B one below the other, at the top, for their
  // pictures; ?check=1 lists what goes past the footer, out of its box or under the logo.
  const query = new URLSearchParams(location.search);
  const range = query.get('slides') || (query.get('slide') && \`\${query.get('slide')}-\${query.get('slide')}\`);
  if (range) {
    const [first, last] = range.split('-').map(Number);
    document.querySelectorAll('.slide').forEach((slide, index) => { slide.style.display = index + 1 >= first && index + 1 <= last ? '' : 'none'; slide.style.marginTop = '0'; });
  }
  if (query.get('check')) {
    const problems = [];
    document.querySelectorAll('.slide').forEach((slide, index) => {
      const box = slide.getBoundingClientRect(); const foot = slide.querySelector('.foot').getBoundingClientRect();
      slide.querySelectorAll('.content *, h1, h2, .lead').forEach((element) => {
        const rect = element.getBoundingClientRect();
        if (rect.height && rect.bottom > foot.top - 8) problems.push(\`slide \${index + 1}: \${element.tagName.toLowerCase()} reaches the footer (\${Math.round(rect.bottom - box.top)} px)\`);
        if (rect.width && rect.right > box.right - 100) problems.push(\`slide \${index + 1}: \${element.tagName.toLowerCase()} past the right margin\`);
        // (The logo takes the top right: 80 × 70 px, 40 px from the top and 112 px from the right.)
        if (rect.width && rect.height && rect.right > box.right - 192 && rect.left < box.right - 112 && rect.bottom > box.top + 40 && rect.top < box.top + 110) problems.push(\`slide \${index + 1}: \${element.tagName.toLowerCase()} under the logo\`);
        if (element.scrollWidth > element.clientWidth + 2 && getComputedStyle(element).overflow !== 'visible') problems.push(\`slide \${index + 1}: \${element.tagName.toLowerCase()} cut\`);
      });
    });
    const out = document.createElement('pre'); out.id = 'check'; out.textContent = JSON.stringify([...new Set(problems)]); document.body.append(out);
  }
</script></body></html>
`;
}

function browser() {
  const found = BROWSERS.find((candidate) => fs.existsSync(candidate));
  if (!found) throw new Error('A Chromium browser (Chrome, Chromium, Brave or Edge) is needed to take the pictures of the slides.');
  return found;
}

const imageName = (index) => `slide-${String(index + 1).padStart(2, '0')}.png`;

// The deck `id` drawn into the folder `out`: slides.html (for the decks of content.js), a picture of each slide and
// slides.json; with `check`, it warns of what goes past the footer, out of its box or under the logo. Gives what
// slides.json holds and the folder.
async function draw(id, out, { check = false } = {}) {
  const folder = path.join(__dirname, id);
  fs.mkdirSync(out, { recursive: true });
  let page;
  let meta;
  const source = path.join(folder, 'content.js');
  if (fs.existsSync(source)) {
    delete require.cache[require.resolve(source)];
    const deck = require(source);
    page = path.join(out, 'slides.html');
    fs.writeFileSync(page, html(deck));
    meta = { title: `DriveTest Analyzer — ${deck.name}`, name: deck.name, description: deck.description,
      slides: deck.slides.map((slide, index) => ({ id: slide.id, image: imageName(index), section: slide.section, title: slide.title, notes: slide.notes })) };
  } else {
    // (Its slides.html stays where it is, for the pictures it links.)
    page = path.join(folder, 'slides.html');
    meta = JSON.parse(fs.readFileSync(path.join(folder, 'slides.json'), 'utf8'));
  }
  const executable = browser();
  // (Without a profile of its own: with one, Brave does not end in headless mode. Without one, it sometimes exits at once
  // while the user's Brave is open, so a run that fails is tried again after a pause; one that times out is not.)
  const run = (args, options = {}) => {
    for (let attempt = 1; ; attempt += 1) {
      try {
        return execFileSync(executable, ['--headless=new', '--disable-gpu', '--disable-dev-shm-usage', '--no-first-run',
          '--no-default-browser-check', '--no-sandbox', '--hide-scrollbars', '--force-device-scale-factor=1', ...args],
        { timeout: 120000, stdio: ['ignore', options.encoding ? 'pipe' : 'ignore', 'ignore'], ...options });
      } catch (error) {
        if (attempt >= BROWSER_ATTEMPTS || error.code === 'ETIMEDOUT') throw error;
        console.warn(`${id}: the browser failed (${error.status ?? error.signal ?? error.code}), trying again (${attempt + 1} of ${BROWSER_ATTEMPTS})`);
        Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, BROWSER_RETRY_PAUSE_MS * attempt);
      }
    }
  };
  for (const stale of fs.readdirSync(out).filter((name) => /^slide-\d+\.png$/.test(name))) fs.unlinkSync(path.join(out, stale));
  const picture = path.join(out, '.slides.png');
  for (let first = 0; first < meta.slides.length; first += SLIDES_PER_PICTURE) {
    const last = Math.min(first + SLIDES_PER_PICTURE, meta.slides.length);
    run([`--window-size=1920,${1080 * (last - first)}`, `--screenshot=${picture}`, `file://${page}?slides=${first + 1}-${last}`]);
    const taken = fs.readFileSync(picture);
    for (let index = first; index < last; index += 1) {
      await sharp(taken).extract({ left: 0, top: (index - first) * 1080, width: 1920, height: 1080 }).png().toFile(path.join(out, meta.slides[index].image));
    }
    fs.unlinkSync(picture);
  }
  if (check && fs.existsSync(source)) {
    const report = run(['--window-size=1920,1080', '--virtual-time-budget=3000', '--dump-dom', `file://${page}?check=1`], { encoding: 'utf8' });
    const found = /<pre id="check">(.*?)<\/pre>/s.exec(report);
    const problems = found ? JSON.parse(found[1].replace(/&quot;/g, '"').replace(/&gt;/g, '>').replace(/&lt;/g, '<').replace(/&amp;/g, '&')) : ['the check did not run'];
    for (const problem of problems) console.warn(`${id}: ${problem}`);
  }
  fs.writeFileSync(path.join(out, 'slides.json'), `${JSON.stringify(meta, null, 2)}\n`);
  return { dir: out, ...meta };
}

if (require.main === module) {
  const [target, ...wanted] = process.argv.slice(2);
  if (!target) {
    console.error('node module_decks.js <folder> [id…]');
    process.exit(1);
  }
  (async () => {
    for (const id of wanted.length ? wanted : DRAWN) console.log(`${id}: ${(await draw(id, path.resolve(target, id), { check: true })).slides.length} slides`);
  })().catch((error) => { console.error(error); process.exit(1); });
}

module.exports = { DECKS, DRAWN, draw };
