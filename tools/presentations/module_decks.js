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

// The decks in the order of the tabs of the tool (PPT Reporting (old) has none), Workspace Config after Workspace and the
// administration (Admin and Super Admin) after them, and those drawn from a slides.html.
const DECKS = ['workspace', 'workspace-config', 'cdr-analysis', 'ppt-dashboards', 'scoring-gap-analysis', 'network-insights', 'non-qualified-calls', 'reporting',
  'builders', 'ticket-center', 'administration'];
const DRAWN = [...DECKS, 'dt-analyzer-rca'];
// The colour of each module, that of its tab (module_labels.MODULE_TABS), for the chips naming the other modules.
const MODULES = {
  'Workspace': '#08736D', 'Workspace Config': '#0369A1', 'CDR Analysis': '#1F6FBF', 'PPT Dashboards': '#7751B9',
  'Scoring & GAP Analysis': '#176E77', 'Network Insights': '#4F46E5', 'Non-Qualified Calls': '#B0234F', 'Reporting': '#2E8C58',
  'Builders': '#B85B20', 'Ticket Center': '#DC2626', 'DT Analyzer RCA': '#7C3AED', 'Admin': '#B84343',
};
// The Ericsson logo at the top right of every slide, as in the other decks of the Help.
const LOGO = `data:image/png;base64,${fs.readFileSync(path.join(__dirname, '..', '..', 'src', 'web_interface', 'static', 'img', 'ericsson-logo-white.png')).toString('base64')}`;
// The browsers that take the pictures, as those of the charts of the reports (dashboard_canvas_renderer.mjs).
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
  // Jobs and their status.
  jobs(p) {
    const rows = [['Q3 Voice report', 'Completed', p.accent], ['Q3 Data report', 'Completed', p.accent], ['Chart Set · London', 'Running', '#e0a020'], ['Q2 Speech report', 'Queued', '#3a4d75']];
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
    [['Dashboards', '3 added · 2 changed', '#1f9d55'], ['PPT Templates', '1 changed', '#f0a830'], ['NQ Call Tracking', 'unchanged', '#7d8aa3']].forEach(([name, change, colour], index) => {
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
    out += cylinder(20, 300, 'Workspace UK', p.deep, ['Datasets', 'Dashboards', 'NQ Call Tracking', 'Combined CDR rows']);
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
    // Too far after the last one: a run of its own.
    out += `<path d="M262 132 Q 340 60 404 92" fill="none" stroke="${MUTED}" stroke-width="3" stroke-dasharray="5 7"/>`;
    out += `<g transform="translate(320 64)"><circle r="15" fill="${INK}" stroke="#e0533d" stroke-width="3"/><path d="M-6 -6 L6 6 M6 -6 L-6 6" stroke="#e0533d" stroke-width="3.5" stroke-linecap="round"/></g>`;
    out += diamond(408, 96, MUTED, 11);
    out += pill(360, 252, '40 km later: a new run', '#22304f', '#c9d4e6', 15);
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
    out += `<text x="${l - 60}" y="20" font-size="17" font-weight="800" fill="${left}">Consecutive</text><text x="${r + 60}" y="20" text-anchor="end" font-size="17" font-weight="800" fill="${right}">Cluster</text>`;
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
  .fact { display: flex; align-items: center; gap: 14px; padding: 12px 20px 12px 16px; border-radius: 20px; background: #131d33; border: 1px solid var(--line); font-size: 20px; line-height: 1.3; color: var(--soft); }
  .fact svg { flex: none; }`;
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
