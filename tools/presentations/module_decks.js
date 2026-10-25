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

// The decks in the order of the tabs of the tool (PPT Reporting (old) has none), Workspace Config after Workspace, and
// those drawn from a slides.html.
const DECKS = ['workspace', 'workspace-config', 'cdr-analysis', 'ppt-dashboards', 'scoring-gap-analysis', 'network-insights', 'non-qualified-calls', 'reporting',
  'builders', 'ticket-center'];
const DRAWN = [...DECKS, 'dt-analyzer-rca'];
// The colour of each module, that of its tab (module_labels.MODULE_TABS), for the chips naming the other modules.
const MODULES = {
  'Workspace': '#08736D', 'Workspace Config': '#0369A1', 'CDR Analysis': '#1F6FBF', 'PPT Dashboards': '#7751B9',
  'Scoring & GAP Analysis': '#176E77', 'Network Insights': '#4F46E5', 'Non-Qualified Calls': '#B0234F', 'Reporting': '#2E8C58',
  'Builders': '#B85B20', 'Ticket Center': '#DC2626', 'DT Analyzer RCA': '#7C3AED', 'Admin': '#475569',
};
// The Ericsson logo at the top right of every slide, as in the other decks of the Help.
const LOGO = `data:image/png;base64,${fs.readFileSync(path.join(__dirname, '..', '..', 'src', 'web_interface', 'static', 'img', 'ericsson-logo-white.png')).toString('base64')}`;
// The browsers that take the pictures, as those of the charts of the reports (dashboard_canvas_renderer.mjs).
const BROWSERS = [process.env.DRIVETEST_ANALYZER_CHROMIUM, '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
  '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium', '/usr/bin/chromium-browser'].filter(Boolean);
// The slides taken in one picture, then cut one by one (a browser start for each would take minutes).
const SLIDES_PER_PICTURE = 6;

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
  .mono { font-family: Menlo, 'SF Mono', Consolas, monospace; }`;
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
  // (Without a profile of its own: with one, Brave does not end in headless mode.)
  const run = (args, options = {}) => execFileSync(executable, ['--headless=new', '--disable-gpu', '--disable-dev-shm-usage', '--no-first-run',
    '--no-default-browser-check', '--no-sandbox', '--hide-scrollbars', '--force-device-scale-factor=1', ...args],
  { timeout: 120000, stdio: ['ignore', options.encoding ? 'pipe' : 'ignore', 'ignore'], ...options });
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
