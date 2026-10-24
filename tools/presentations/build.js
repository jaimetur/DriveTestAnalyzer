// The presentations of DriveTest Analyzer shown in the Help, in Ericsson style: the overview deck (which closes with the
// one-slider), the one-slider and the roadmap, plus the status of the adaptation to other benchmarking providers in the
// design of its own deck. The server generates them with the live figures of the workspaces chosen in Super Admin
// (src/modules/presentations.py); `node build.js` writes them with the figures below into static/presentations, the
// copies the Help shows until then, and `python tools/presentations/render.py` renders their slides (see
// help/project-structure.md).
const fs = require('fs');
const os = require('os');
const path = require('path');
const JSZip = require('jszip');
const pptxgen = require('pptxgenjs');
const React = require('react');
const ReactDOMServer = require('react-dom/server');
const sharp = require('sharp');
const tb = require('react-icons/tb');
const art = require('./art.js');

const ROOT = path.resolve(__dirname, '..', '..');
const OUT = path.resolve(process.argv[2] || path.join(ROOT, 'src', 'web_interface', 'static', 'presentations'));
// Arial, which every device has (PowerPoint, Keynote, the previews of phones): the Ericsson theme of the exports uses
// Ericsson Hilda, which a device without it replaces with a serif font.
const HEAD = 'Arial';
const BODY = 'Arial';
const THEME = {
  name: 'Ericsson', headFontFace: HEAD, bodyFontFace: BODY,
  colors: { dk1: '000000', lt1: 'FFFFFF', dk2: '242424', lt2: 'F2F2F2', accent1: '0082F0', accent2: '0068BF', accent3: '0FC373',
    accent4: 'FF8C0A', accent5: 'AF78D2', accent6: 'FF3232', hlink: '0082F0', folHlink: 'AF78D2' },
};

// Ericsson brand: black and white dominate, greys support, blue is the accent.
const K = { black: '000000', ink: '242424', grey: '767676', grey2: 'A0A0A0', line: 'E0E0E0', tint: 'F2F2F2', tint2: 'FAFAFA',
  blue: '0082F0', deep: '0068BF', purple: 'AF78D2', green: '0FC373', orange: 'FF8C0A', red: 'FF3232', yellow: 'FAD22D',
  white: 'FFFFFF' };
// One colour per module, the same on every slide.
const M = {
  scoring: { name: 'Scoring & GAP Analysis', short: 'Scoring & GAP', color: '0068BF', icon: 'TbTrophy', desc: 'Scores & GAP to reference' },
  ni: { name: 'Network Insights', short: 'Network Insights', color: '0C9B5B', icon: 'TbAntennaBars5', desc: 'Coverage, cells & spectrum' },
  nq: { name: 'Non-Qualified Calls', short: 'NQ Calls', color: 'D92B2B', icon: 'TbPhoneX', desc: 'Root cause & follow-up' },
  reporting: { name: 'Reporting', short: 'Reporting', color: '8C60A8', icon: 'TbReportAnalytics', desc: 'Bundle reports, scheduled' },
  tickets: { name: 'Ticket Center', short: 'Ticket Center', color: 'FAD22D', iconColor: '242424', icon: 'TbTicket', desc: 'Bugs & requests, tracked' },
  builders: { name: 'Builders', short: 'Builders', color: '0082F0', icon: 'TbCode', desc: 'Ad-hoc charts & SQL' },
  cdr: { name: 'CDR Analysis', short: 'CDR Analysis', color: '4D4D4D', icon: 'TbFileAnalytics', desc: 'Deep dive into one CDR' },
  dash: { name: 'PPT Dashboards', short: 'PPT Dashboards', color: 'E07800', icon: 'TbPresentationAnalytics', desc: 'Template-driven KPI decks' },
};
// The modules in the order of the tabs of the tool.
const TOOL_ORDER = ['cdr', 'dash', 'scoring', 'ni', 'nq', 'reporting', 'builders', 'tickets'];

const iconCache = new Map();
async function icon(name, color, size = 256) {
  const key = `${name}-${color}`;
  if (!iconCache.has(key)) {
    const svg = ReactDOMServer.renderToStaticMarkup(React.createElement(tb[name], { size, color: `#${color}` }))
      .replace(/currentColor/g, `#${color}`);
    const png = await sharp(Buffer.from(svg)).png().toBuffer();
    iconCache.set(key, `image/png;base64,${png.toString('base64')}`);
  }
  return iconCache.get(key);
}

let objectCount = 0;
const named = (prefix) => `${prefix}-${(objectCount += 1)}`;
const text = (slide, value, options) => slide.addText(value, { isTextBox: true, margin: 0, fontFace: BODY, color: K.ink, objectName: named('text'), ...options });
const shape = (slide, kind, options) => slide.addShape(kind, { objectName: named('shape'), ...options });

// An icon on a filled circle (the motif of the deck).
async function badge(slide, pres, name, x, y, d, fill, iconColor = K.white, ratio = 0.56) {
  shape(slide, pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fill }, line: { color: fill, width: 0 } });
  const s = d * ratio;
  slide.addImage({ data: await icon(name, iconColor), x: x + (d - s) / 2, y: y + (d - s) / 2, w: s, h: s, objectName: named('icon') });
}

// A straight line between two points (pptxgenjs draws lines top-left to bottom-right unless flipped).
function lineBetween(slide, pres, x1, y1, x2, y2, line) {
  const flipV = (x2 > x1) !== (y2 > y1);
  shape(slide, pres.shapes.LINE, { x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.max(Math.abs(x2 - x1), 0.001), h: Math.max(Math.abs(y2 - y1), 0.001),
    flipV: flipV && Math.abs(y2 - y1) > 0.001 && Math.abs(x2 - x1) > 0.001, line });
}

function defineLayouts(pres, logos) {
  pres.layout = 'LAYOUT_WIDE';
  pres.theme = { headFontFace: HEAD, bodyFontFace: BODY };
  pres.defineSlideMaster({ title: 'COVER', background: { color: K.black }, objects: [] });
  // The Ericsson logo at the top right, beside the title.
  const frame = [
    { image: { x: 12.27, y: 0.42, w: 0.53, h: 0.465, path: logos.black } },
    { text: { text: 'DriveTest Analyzer', options: { x: 1.0, y: 7.0, w: 4, h: 0.28, fontSize: 9, fontFace: BODY, color: K.grey, margin: 0 } } },
    { placeholder: { options: { name: 'title', type: 'title', x: 0.6, y: 0.42, w: 11.4, h: 0.72, fontFace: HEAD, fontSize: 30,
      color: K.black, align: 'left', valign: 'middle', margin: 0 }, text: '' } },
  ];
  pres.defineSlideMaster({ title: 'CONTENT', background: { color: K.white }, objects: frame,
    slideNumber: { x: 0.6, y: 7.0, w: 0.4, h: 0.28, fontSize: 9, fontFace: BODY, color: K.grey } });
  // (A deck of a single slide, without its number.)
  pres.defineSlideMaster({ title: 'SINGLE', background: { color: K.white }, objects: frame });
}

// The title of a content slide: the part that tells the slide apart in bold deep blue, as the Ericsson theme; the
// subtitle in grey below it.
function heading(slide, plain, focus, subtitle, size) {
  slide.addText([
    { text: plain, options: {} },
    { text: focus, options: { bold: true, fontFace: BODY, color: K.deep } },
  ], { placeholder: 'title', ...(size ? { fontSize: size } : {}) });
  if (subtitle) text(slide, subtitle, { x: 0.6, y: 1.12, w: 12.1, h: 0.4, fontSize: 15, color: K.grey });
}

// The figures of the slides: those of the workspaces chosen in Super Admin, which the server passes in the JSON
// file named by PRESENTATION_FIGURES when it generates the presentations (src/modules/presentations.py); these otherwise.
const DEFAULT_FIGURES = {
  workspaces: ['UK'], month: 'October 2026', cdr_calls: 3762827, cdrs: 27, campaigns: 9, inventory_rows: 519133,
  mapping_rows: 1095986, nq_calls: 48138, nq_calls_total: 4032603, nq_followed: 2357, nq_rca: 2129, nq_comments: 3371,
  users: 16, roles: { 'super-admin': 2, admin: 1, 'user-editor': 12, 'user-viewer': 1 }, help_chapters: 25, tests: 1895,
  releases: 24, workspace_list: [{ name: 'UK', campaigns: 9 }, { name: 'DE', campaigns: 1 }],
};
const FIGURES = { ...DEFAULT_FIGURES,
  ...(process.env.PRESENTATION_FIGURES ? JSON.parse(fs.readFileSync(process.env.PRESENTATION_FIGURES, 'utf8')) : {}) };
// 7.5 M, 519 k, 48 k; and 48,138.
const compact = (value) => (value >= 1e6 ? `${(value / 1e6).toFixed(1)} M` : value >= 1e4 ? `${Math.round(value / 1e3)} k`
  : value >= 1e3 ? `${(value / 1e3).toFixed(1)} k` : `${value}`);
const exact = (value) => Number(value || 0).toLocaleString('en-US');
const plural = (count, word) => `${exact(count)} ${word}${Number(count) === 1 ? '' : 's'}`;
const names = FIGURES.workspaces.length > 1
  ? `${FIGURES.workspaces.slice(0, -1).join(', ')} and ${FIGURES.workspaces[FIGURES.workspaces.length - 1]}` : FIGURES.workspaces[0] || '';
const STATS = {
  calls: compact(FIGURES.cdr_calls), cdrs: exact(FIGURES.cdrs), campaigns: exact(FIGURES.campaigns), nq: compact(FIGURES.nq_calls),
  nqExact: exact(FIGURES.nq_calls), tracked: exact(FIGURES.nq_followed), rca: exact(FIGURES.nq_rca), comments: exact(FIGURES.nq_comments),
  inventory: compact(FIGURES.inventory_rows), mappings: compact(FIGURES.mapping_rows), users: exact(FIGURES.users),
  tests: exact(FIGURES.tests), releases: exact(FIGURES.releases), chapters: exact(FIGURES.help_chapters),
  // "the UK workspace" or "the UK and DE workspaces".
  where: `the ${names} workspace${FIGURES.workspaces.length === 1 ? '' : 's'}`,
};

// ---------------------------------------------------------------------------------------------------------------- deck
async function cover(pres, files) {
  const slide = pres.addSlide({ masterName: 'COVER', sectionTitle: 'Introduction' });
  slide.addImage({ path: files.cover, x: 6.3, y: 0, w: 7.03, h: 7.5, objectName: 'Cover art' });
  slide.addImage({ path: files.logoWhite, x: 11.92, y: 0.55, w: 0.71, h: 0.62, objectName: 'Ericsson logo' });
  text(slide, 'DRIVE-TEST ANALYTICS PLATFORM', { x: 0.7, y: 2.15, w: 6, h: 0.35, fontSize: 13, bold: true, color: K.blue, charSpacing: 2 });
  text(slide, [
    { text: 'DriveTest', options: { fontFace: HEAD, breakLine: true } },
    { text: 'Analyzer', options: { bold: true, fontFace: BODY, color: K.blue } },
  ], { x: 0.7, y: 2.55, w: 6.2, h: 2.05, fontSize: 64, color: K.white, valign: 'top', lineSpacingMultiple: 0.95 });
  text(slide, 'From drive-test CDRs to network decisions, in one platform', { x: 0.7, y: 4.7, w: 5.6, h: 0.9, fontSize: 20, fontFace: HEAD, color: 'E0E0E0' });
  const chips = ['Benchmarking', 'NQ Calls', 'Troubleshooting', 'Reporting'];
  let x = 0.7;
  for (const label of chips) {
    const w = 0.32 + label.length * 0.105;
    shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x, y: 5.85, w, h: 0.42, rectRadius: 0.21, fill: { color: K.black }, line: { color: '4D4D4D', width: 1 } });
    text(slide, label, { x, y: 5.85, w, h: 0.42, fontSize: 12, color: K.white, align: 'center', valign: 'middle' });
    x += w + 0.14;
  }
  text(slide, FIGURES.month, { x: 0.7, y: 6.75, w: 3, h: 0.3, fontSize: 11, color: K.grey2 });
  slide.addNotes('DriveTest Analyzer turns the drive-test CDRs of every campaign into benchmarking scores, network insights, '
    + 'follow-up of every failed call and ready-to-share reports, for every team, in one web platform.');
}

async function platform(pres) {
  const slide = pres.addSlide({ masterName: 'CONTENT', sectionTitle: 'Introduction' });
  heading(slide, 'One platform, ', 'from CDRs to decisions', 'Ingest once, analyse in every module, report and act, all in the same workspace');
  const stages = [
    ['TbDatabaseImport', 'Ingest', 'Data, Voice & Speech', 'Maps & inventories'],
    ['TbSettingsAutomation', 'Process', 'Normalise, map, enrich', 'Auto-calculated fields'],
    ['TbChartHistogram', 'Analyse', 'Scoring · NI · NQ · KPIs', 'Ad-hoc charts & SQL'],
    ['TbPresentation', 'Report', 'PowerPoint & Word', 'Scheduled & emailed'],
    ['TbTargetArrow', 'Act', 'Root cause & follow-up', 'Tickets to closure'],
  ];
  const shades = ['4DA8F5', '2E96F2', K.blue, K.deep, '004E8F'];
  for (const [index, [name, title, line1, line2]] of stages.entries()) {
    const x = 0.6 + index * 2.52;
    await badge(slide, pres, name, x + 0.55, 1.72, 0.95, shades[index]);
    text(slide, title, { x, y: 2.78, w: 2.05, h: 0.4, fontSize: 18, bold: true, align: 'center' });
    text(slide, [{ text: line1, options: { breakLine: true } }, { text: line2 }], { x, y: 3.2, w: 2.05, h: 0.62, fontSize: 12.5, color: K.grey, align: 'center' });
    if (index < stages.length - 1) {
      shape(slide, pres.shapes.LINE, { x: x + 1.62, y: 2.195, w: 1.38, h: 0, line: { color: K.grey2, width: 1.75, endArrowType: 'triangle' } });
    }
  }
  text(slide, 'DATASETS IT INGESTS', { x: 0.6, y: 4.0, w: 6, h: 0.3, fontSize: 11, bold: true, color: K.grey, charSpacing: 1 });
  const datasets = [
    ['TbFileAnalytics', K.deep, 'CDRs', 'Data, Voice & Speech, NSA & SA, by campaign', STATS.calls, `calls in ${STATS.cdrs} CDRs`],
    ['TbBuildingBroadcastTower', '0C9B5B', 'Network Inventories', 'Cells of any operator, tables or KMZ cell configuration', STATS.inventory, 'inventory rows'],
    ['TbArrowsShuffle', 'E07800', 'Vendor Mappings', 'Multivendor VFUK & 3UK, and vendor polygons', STATS.mappings, 'mapping rows'],
    ['TbPolygon', '8C60A8', 'Geographical', 'Regions & Clusters as polygons, for splits and maps', '2 levels', 'Region & Cluster'],
  ];
  for (const [index, [name, color, title, desc, value, unit]] of datasets.entries()) {
    const x = 0.6 + index * 3.077;
    shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x, y: 4.35, w: 2.9, h: 2.1, rectRadius: 0.12, fill: { color: K.tint }, line: { color: K.tint, width: 0 } });
    await badge(slide, pres, name, x + 0.22, 4.55, 0.5, color);
    text(slide, title, { x: x + 0.85, y: 4.55, w: 1.95, h: 0.5, fontSize: 15, bold: true, valign: 'middle' });
    text(slide, desc, { x: x + 0.22, y: 5.15, w: 2.5, h: 0.6, fontSize: 11.5, color: K.grey, valign: 'top' });
    text(slide, [{ text: `${value} `, options: { fontSize: 22, bold: true, color: K.deep } }, { text: unit, options: { fontSize: 11.5, color: K.grey } }],
      { x: x + 0.22, y: 5.8, w: 2.55, h: 0.5, valign: 'middle' });
  }
  text(slide, `Live figures of ${STATS.where}, ${plural(FIGURES.campaigns, 'campaign')}, ${FIGURES.month}`, { x: 0.6, y: 6.55, w: 9, h: 0.28, fontSize: 10, color: K.grey2 });
  slide.addNotes('Five steps: upload the CDRs once; the platform normalises them, maps vendors and regions and adds calculated '
    + 'fields; every module analyses the same data; reports come out as PowerPoint and Word, on demand or on schedule; and '
    + 'teams act on them with the NQ follow-up and the Ticket Center. It ingests CDRs, Network Inventories, Vendor Mappings '
    + `and Geographical polygons; the figures are live from ${STATS.where}.`);
}

async function modules(pres) {
  const slide = pres.addSlide({ masterName: 'CONTENT', sectionTitle: 'Modules' });
  heading(slide, 'Eight modules, ', 'one shared workspace', 'Every module reads the same processed CDRs, mappings and inventories');
  const cx = 6.67; const cy = 4.35; const rx = 3.5; const ry = 2.05;
  shape(slide, pres.shapes.OVAL, { x: cx - rx, y: cy - ry, w: 2 * rx, h: 2 * ry, fill: { type: 'none' }, line: { color: K.line, width: 1, dashType: 'dash' } });
  const nodes = TOOL_ORDER.map((key, index) => {
    const angle = (-112.5 + index * 45) * Math.PI / 180;
    return { key, x: cx + rx * Math.cos(angle), y: cy + ry * Math.sin(angle), right: Math.cos(angle) > 0 };
  });
  for (const node of nodes) lineBetween(slide, pres, cx, cy, node.x, node.y, { color: K.line, width: 1.5 });
  shape(slide, pres.shapes.OVAL, { x: cx - 0.975, y: cy - 0.975, w: 1.95, h: 1.95, fill: { color: K.black }, line: { color: K.black, width: 0 } });
  text(slide, [
    { text: 'Workspace', options: { fontSize: 17, bold: true, color: K.white, breakLine: true } },
    { text: 'CDRs · maps · inventories', options: { fontSize: 10.5, color: K.grey2 } },
  ], { x: cx - 0.9, y: cy - 0.5, w: 1.8, h: 1.0, align: 'center', valign: 'middle' });
  for (const node of nodes) {
    const module = M[node.key];
    await badge(slide, pres, module.icon, node.x - 0.45, node.y - 0.45, 0.9, module.color, module.iconColor || K.white);
    const x = node.right ? node.x + 0.55 : node.x - 0.55 - 2.25;
    text(slide, [
      { text: node.key === 'scoring' ? 'Scoring & GAP' : module.name, options: { fontSize: 13.5, bold: true, breakLine: true } },
      { text: module.desc, options: { fontSize: 11, color: K.grey } },
    ], { x, y: node.y - 0.4, w: 2.25, h: 0.8, align: node.right ? 'left' : 'right', valign: 'middle' });
  }
  slide.addNotes('Eight modules around one workspace, in the order of the tool: CDR Analysis, the template-driven PPT '
    + 'Dashboards, the scores and GAPs of Scoring & GAP Analysis, the radio and network view of Network Insights, the '
    + 'follow-up of every Non-Qualified Call, Reporting, the Chart and Query Builders and the Ticket Center. They all read '
    + 'the same processed CDRs.');
}

async function teams(pres) {
  const slide = pres.addSlide({ masterName: 'CONTENT', sectionTitle: 'Teams' });
  heading(slide, 'Built for ', 'every team', 'Each team starts where it adds value, on the same data');
  const columns = TOOL_ORDER.filter((key) => key !== 'tickets');
  const rows = [
    ['TbScale', 'Benchmarking', 'Who wins, by how much, city by city', { scoring: 2, dash: 2, reporting: 2, ni: 1, cdr: 1, builders: 1 }],
    ['TbPhoneX', 'NQ Calls', 'Every failed call root-caused and closed', { nq: 2, cdr: 1, reporting: 1, ni: 1, builders: 1 }],
    ['TbStethoscope', 'Troubleshooting', 'Where coverage and cells hurt the KPIs', { ni: 2, cdr: 2, builders: 2, nq: 1, scoring: 1 }],
    ['TbChartDots3', 'Technical reporting', 'Template-driven KPI decks in minutes', { dash: 2, reporting: 2, scoring: 1, ni: 1, cdr: 1 }],
    ['TbBriefcase', 'Executive reporting', 'One scheduled story for the leadership', { reporting: 2, scoring: 2, ni: 1, dash: 1 }],
  ];
  // Legend: core and supporting modules.
  shape(slide, pres.shapes.OVAL, { x: 10.35, y: 1.21, w: 0.2, h: 0.2, fill: { color: K.deep }, line: { color: K.deep, width: 0 } });
  text(slide, 'Core', { x: 10.62, y: 1.16, w: 0.7, h: 0.3, fontSize: 11, color: K.grey });
  shape(slide, pres.shapes.OVAL, { x: 11.35, y: 1.21, w: 0.2, h: 0.2, fill: { color: K.white }, line: { color: K.blue, width: 1.5 } });
  text(slide, 'Supporting', { x: 11.62, y: 1.16, w: 1.1, h: 0.3, fontSize: 11, color: K.grey });
  const colX = (index) => 5.0 + index * 1.1;
  for (const [index, key] of columns.entries()) {
    const module = M[key];
    await badge(slide, pres, module.icon, colX(index) + 0.3, 1.75, 0.5, module.color, module.iconColor || K.white);
    text(slide, module.short, { x: colX(index), y: 2.3, w: 1.1, h: 0.5, fontSize: 10.5, bold: true, align: 'center', valign: 'top' });
  }
  for (const [rowIndex, [iconName, name, value, use]] of rows.entries()) {
    const y = 2.95 + rowIndex * 0.78;
    if (rowIndex % 2 === 0) shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y, w: 12.1, h: 0.74, rectRadius: 0.1, fill: { color: K.tint }, line: { color: K.tint, width: 0 } });
    await badge(slide, pres, iconName, 0.75, y + 0.12, 0.5, K.ink);
    text(slide, name, { x: 1.42, y: y + 0.07, w: 3.5, h: 0.32, fontSize: 15, bold: true });
    text(slide, value, { x: 1.42, y: y + 0.39, w: 3.55, h: 0.28, fontSize: 11, color: K.grey });
    for (const [index, key] of columns.entries()) {
      const level = use[key];
      if (!level) continue;
      const x = colX(index) + 0.41; const cyDot = y + 0.23;
      shape(slide, pres.shapes.OVAL, { x, y: cyDot, w: 0.28, h: 0.28, fill: level === 2 ? { color: K.deep } : { color: K.white },
        line: { color: level === 2 ? K.deep : K.blue, width: 1.5 } });
    }
  }
  slide.addNotes('Benchmarking scores operators with Scoring & GAP Analysis and shares PPT Dashboards and reports; the NQ team '
    + 'follows every failed call; troubleshooting reads coverage, interference and serving cells in Network Insights with CDR '
    + 'Analysis and the Builders; technical and executive reports come from the same modules, scheduled in Reporting.');
}

// The operators of the Scoring slides (illustrative), the reference first: their Voice and Data points of the latest
// campaign and their scores in the last five campaigns.
const CAMPAIGNS = ['25-Q3', '25-Q4', '26-Q1', '26-Q2', '26-Q3'];
const OPERATORS = [
  { name: 'Operator A', letter: 'A', color: '0068BF', voice: 402.1, data: 498.3, trend: [812.4, 839.0, 861.7, 887.8, 900.4] },
  { name: 'Operator B', letter: 'B', color: '8C60A8', voice: 381.4, data: 475.8, trend: [801.3, 826.5, 845.2, 853.1, 857.2] },
  { name: 'Operator C', letter: 'C', color: '0C9B5B', voice: 352.0, data: 451.2, trend: [768.9, 794.6, 820.4, 809.5, 803.2] },
  { name: 'Operator D', letter: 'D', color: 'E07800', voice: 311.7, data: 401.5, trend: [641.7, 668.2, 690.3, 703.4, 713.2] },
];
const total = (operator) => operator.voice + operator.data;
const signed = (value) => `${value < 0 ? '−' : '+'}${Math.abs(value).toFixed(1)}`;

// A light card with its title in small capitals.
function card(slide, pres, x, y, w, h, title, fill = K.tint) {
  shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.12, fill: { color: fill }, line: { color: fill === K.white ? K.line : fill, width: fill === K.white ? 1 : 0 } });
  text(slide, title, { x: x + 0.22, y: y + 0.14, w: w - 0.4, h: 0.26, fontSize: 10.5, bold: true, color: K.grey, charSpacing: 1 });
}

// Scoring is drawn with shapes and pictures, never native charts, so that every viewer (the iPhone too) shows it.
async function scoring(pres) {
  const slide = pres.addSlide({ masterName: 'CONTENT', sectionTitle: 'Modules' });
  heading(slide, 'Scoring & GAP Analysis — ', 'who wins, and by how much', 'Best Network and Most Reliable scores of every operator, place and campaign, with the GAP to the reference');

  // Where each operator stands: its Voice and Data points of 1,000, its change and its GAP to the reference.
  card(slide, pres, 0.6, 1.75, 6.45, 3.85, 'WHERE EACH OPERATOR STANDS · 26-Q3');
  shape(slide, pres.shapes.RECTANGLE, { x: 5.3, y: 1.94, w: 0.16, h: 0.16, fill: { color: K.ink }, line: { color: K.ink, width: 0 } });
  text(slide, 'Voice', { x: 5.51, y: 1.88, w: 0.55, h: 0.28, fontSize: 10, color: K.grey, valign: 'middle' });
  shape(slide, pres.shapes.RECTANGLE, { x: 6.07, y: 1.94, w: 0.16, h: 0.16, fill: { color: K.ink, transparency: 60 }, line: { color: K.ink, width: 0 } });
  text(slide, 'Data', { x: 6.28, y: 1.88, w: 0.55, h: 0.28, fontSize: 10, color: K.grey, valign: 'middle' });
  const scale = 2.5 / 1000; const barX = 2.95; const reference = total(OPERATORS[0]);
  for (const [index, operator] of OPERATORS.entries()) {
    const y = 2.4 + index * 0.74; const change = operator.trend[4] - operator.trend[3];
    shape(slide, pres.shapes.OVAL, { x: 0.82, y: y + 0.02, w: 0.48, h: 0.48, fill: { color: operator.color }, line: { color: operator.color, width: 0 } });
    text(slide, String(index + 1), { x: 0.82, y: y + 0.02, w: 0.48, h: 0.48, fontSize: 16, bold: true, color: K.white, align: 'center', valign: 'middle' });
    text(slide, operator.name, { x: 1.45, y: y - 0.02, w: 1.45, h: 0.3, fontSize: 13, bold: true });
    text(slide, `${change >= 0 ? '▲' : '▼'} ${Math.abs(change).toFixed(1)} vs 26-Q2`, { x: 1.45, y: y + 0.28, w: 1.45, h: 0.24, fontSize: 10, bold: true, color: change >= 0 ? '0C9B5B' : 'D92B2B' });
    shape(slide, pres.shapes.RECTANGLE, { x: barX, y: y + 0.05, w: 1000 * scale, h: 0.42, fill: { color: K.white }, line: { color: K.line, width: 0.75 } });
    const voiceW = operator.voice * scale; const dataW = operator.data * scale;
    shape(slide, pres.shapes.RECTANGLE, { x: barX, y: y + 0.05, w: voiceW, h: 0.42, fill: { color: operator.color }, line: { color: operator.color, width: 0 } });
    shape(slide, pres.shapes.RECTANGLE, { x: barX + voiceW, y: y + 0.05, w: dataW, h: 0.42, fill: { color: operator.color, transparency: 60 }, line: { color: operator.color, width: 0 } });
    text(slide, operator.voice.toFixed(0), { x: barX, y: y + 0.05, w: voiceW, h: 0.42, fontSize: 10.5, bold: true, color: K.white, align: 'center', valign: 'middle' });
    text(slide, operator.data.toFixed(0), { x: barX + voiceW, y: y + 0.05, w: dataW, h: 0.42, fontSize: 10.5, bold: true, color: K.ink, align: 'center', valign: 'middle' });
    text(slide, total(operator).toFixed(1), { x: 5.52, y: y + 0.03, w: 0.72, h: 0.46, fontSize: 15, bold: true, valign: 'middle' });
    const isReference = index === 0;
    shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x: 6.25, y: y + 0.09, w: 0.66, h: 0.34, rectRadius: 0.17, fill: { color: isReference ? K.ink : 'FDE2E2' }, line: { color: isReference ? K.ink : 'FDE2E2', width: 0 } });
    text(slide, isReference ? 'REF' : signed(total(operator) - reference), { x: 6.25, y: y + 0.09, w: 0.66, h: 0.34, fontSize: 10.5, bold: true, color: isReference ? K.white : 'D92B2B', align: 'center', valign: 'middle' });
  }
  text(slide, 'Illustrative data · points of 1,000 · GAP to Operator A, the reference', { x: 0.82, y: 5.22, w: 6.0, h: 0.26, fontSize: 10, color: K.grey2 });

  // The position of an operator in every environment and service.
  card(slide, pres, 7.3, 1.75, 5.43, 1.95, 'POSITION PER ENVIRONMENT · OPERATOR B');
  for (const [index, label] of ['Voice', 'Data', 'Overall'].entries()) {
    text(slide, label, { x: 9.2 + index * 1.17, y: 2.1, w: 1.07, h: 0.26, fontSize: 10.5, bold: true, color: K.grey, align: 'center' });
  }
  const positions = { 1: ['0C9B5B', K.white], 2: ['8FD9B6', K.ink], 3: ['F8B4B4', K.ink], 4: ['D92B2B', K.white] };
  const matrix = [['Drive - City', [[2, 88], [1, 93], [2, 90]]], ['Connecting Roads', [[4, 74], [2, 85], [3, 81]]], ['All Environments', [[2, 84], [2, 90], [2, 86]]]];
  for (const [row, [label, cells]] of matrix.entries()) {
    const y = 2.42 + row * 0.4;
    text(slide, label, { x: 7.52, y, w: 1.65, h: 0.34, fontSize: 11, bold: row === 2, valign: 'middle' });
    for (const [column, [position, share]] of cells.entries()) {
      const [fill, color] = positions[position]; const x = 9.2 + column * 1.17;
      shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 1.07, h: 0.34, rectRadius: 0.06, fill: { color: fill }, line: { color: fill, width: 0 } });
      text(slide, [{ text: `#${position}  `, options: { bold: true } }, { text: `${share}%` }], { x, y, w: 1.07, h: 0.34, fontSize: 11, color, align: 'center', valign: 'middle' });
    }
  }

  // The scoring trend of the last five campaigns, the reference thicker.
  card(slide, pres, 7.3, 3.85, 5.43, 1.75, 'SCORING TREND · LAST FIVE CAMPAIGNS');
  const plotX = 7.62; const plotW = 3.65; const top = 4.34; const bottom = 5.12; const low = 630; const high = 905;
  const px = (index) => plotX + (index / (CAMPAIGNS.length - 1)) * plotW;
  const py = (value) => bottom - ((value - low) / (high - low)) * (bottom - top);
  for (const [index, campaign] of CAMPAIGNS.entries()) {
    text(slide, campaign, { x: px(index) - 0.35, y: 5.22, w: 0.7, h: 0.22, fontSize: 9.5, color: K.grey, align: 'center' });
  }
  shape(slide, pres.shapes.LINE, { x: plotX, y: bottom + 0.04, w: plotW, h: 0, line: { color: K.line, width: 1 } });
  let labelY = 0;
  for (const [order, operator] of OPERATORS.entries()) {
    for (let index = 1; index < operator.trend.length; index += 1) {
      lineBetween(slide, pres, px(index - 1), py(operator.trend[index - 1]), px(index), py(operator.trend[index]), { color: operator.color, width: order === 0 ? 3.5 : 2.25 });
    }
    const lastY = py(operator.trend[4]);
    shape(slide, pres.shapes.OVAL, { x: px(4) - 0.07, y: lastY - 0.07, w: 0.14, h: 0.14, fill: { color: operator.color }, line: { color: K.white, width: 1 } });
    labelY = Math.max(lastY, labelY + 0.21);
    text(slide, `${operator.letter}  ${operator.trend[4].toFixed(1)}`, { x: 11.42, y: labelY - 0.11, w: 1.2, h: 0.22, fontSize: 10.5, bold: true, color: operator.color, valign: 'middle' });
  }

  // The seven tabs of every result.
  text(slide, 'SEVEN VIEWS OF EVERY RESULT, ALSO IN POWERPOINT AND WORD', { x: 0.6, y: 5.74, w: 9, h: 0.26, fontSize: 10.5, bold: true, color: K.grey, charSpacing: 1 });
  const tabs = [['TbLayoutDashboard', 'Summary'], ['TbChartBar', 'Scoring Charts'], ['TbTable', 'Scoring Tables'], ['TbMap2', 'Geographical Areas'],
    ['TbTrendingUp', 'Scoring Trends'], ['TbScale', 'GAP Analysis'], ['TbTargetArrow', 'Points Lost']];
  for (const [index, [name, label]] of tabs.entries()) {
    const x = 0.6 + index * 1.735;
    shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x, y: 6.06, w: 1.62, h: 0.72, rectRadius: 0.12, fill: { color: K.white }, line: { color: K.line, width: 1 } });
    await badge(slide, pres, name, x + 0.12, 6.21, 0.42, M.scoring.color);
    text(slide, label, { x: x + 0.62, y: 6.06, w: 0.96, h: 0.72, fontSize: 10.5, bold: true, valign: 'middle' });
  }
  slide.addNotes('Scoring & GAP Analysis scores every operator with the NetCheck Best Network methodology, and Most Reliable when '
    + 'the methodology has it, in NSA, SA or NSA vs SA, per environment, city, region and campaign. Each result shows where '
    + 'every operator stands with its Voice and Data points, its change since the previous campaign and its GAP to the '
    + 'reference; its position in every environment and service; and the trend of the last campaigns. Seven views of '
    + 'every result, from the Summary to the Points Lost, all exported to PowerPoint and Word in seven themes. The figures '
    + 'are illustrative.');
}

async function scoringActions(pres, files) {
  const slide = pres.addSlide({ masterName: 'CONTENT', sectionTitle: 'Modules' });
  heading(slide, 'Scoring & GAP Analysis — ', 'where to win the points back', 'Every point lost, traced to its KPI, area, owner and site, with what to fix first');

  // The Points Lost Map of an operator, the area that loses most ringed.
  card(slide, pres, 0.6, 1.75, 4.4, 5.05, 'POINTS LOST MAP · OPERATOR B', 'F7FAFD');
  shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y: 1.75, w: 4.4, h: 5.05, rectRadius: 0.12, fill: { type: 'none' }, line: { color: K.line, width: 1 } });
  slide.addImage({ path: files.lossMap, x: 0.86, y: 2.12, w: 3.88, h: 4.3, objectName: 'Points Lost Map' });
  shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x: 2.62, y: 4.86, w: 1.12, h: 0.32, rectRadius: 0.16, fill: { color: K.deep }, line: { color: K.deep, width: 0 } });
  text(slide, '−38.6 pts', { x: 2.62, y: 4.86, w: 1.12, h: 0.32, fontSize: 11, bold: true, color: K.white, align: 'center', valign: 'middle' });
  text(slide, 'Fewer', { x: 0.85, y: 6.44, w: 0.5, h: 0.24, fontSize: 9.5, color: K.grey, valign: 'middle' });
  for (const [index, color] of art.LOSS.entries()) {
    shape(slide, pres.shapes.RECTANGLE, { x: 1.36 + index * 0.3, y: 6.48, w: 0.3, h: 0.16, fill: { color }, line: { color: K.white, width: 0.5 } });
  }
  text(slide, 'More points lost', { x: 3.22, y: 6.44, w: 1.6, h: 0.24, fontSize: 9.5, color: K.grey, valign: 'middle' });

  // The biggest levers: the KPIs where matching the reference wins most points.
  card(slide, pres, 5.2, 1.75, 3.75, 2.65, 'BIGGEST LEVERS · POINTS TO WIN');
  const levers = [['Call setup success', 4.2], ['DL throughput P10', 3.4], ['POLQA MOS', 2.6], ['Video start time', 1.7], ['Web page load time', 1.1]];
  for (const [index, [label, points]] of levers.entries()) {
    const y = 2.2 + index * 0.42; const w = (points / 4.2) * 0.95;
    text(slide, label, { x: 5.42, y, w: 1.95, h: 0.32, fontSize: 11, valign: 'middle' });
    shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x: 7.38, y: y + 0.05, w, h: 0.22, rectRadius: 0.05, fill: { color: '0C9B5B' }, line: { color: '0C9B5B', width: 0 } });
    text(slide, `+${points.toFixed(1)}`, { x: 7.38 + w + 0.06, y, w: 0.5, h: 0.32, fontSize: 11, bold: true, color: '0C9B5B', valign: 'middle' });
  }

  // Where the points go: how each operator loses them.
  card(slide, pres, 5.2, 4.55, 3.75, 2.25, 'WHERE THE POINTS GO');
  const kinds = [['Failed tests', 'D92B2B', 0.8], ['Below threshold', 'FF8C0A', 1.1], ['Quality shortfall', 'FAD22D', 1.15]];
  let legendX = 5.42;
  for (const [label, color, width] of kinds) {
    shape(slide, pres.shapes.RECTANGLE, { x: legendX, y: 4.98, w: 0.14, h: 0.14, fill: { color }, line: { color, width: 0 } });
    text(slide, label, { x: legendX + 0.18, y: 4.92, w: width, h: 0.26, fontSize: 9.5, color: K.grey, valign: 'middle' });
    legendX += width + 0.22;
  }
  const losses = [['Operator A', [41.2, 33.1, 25.3]], ['Operator B', [63.5, 46.2, 33.1]], ['Operator C', [88.4, 64.2, 44.2]]];
  for (const [index, [label, parts]] of losses.entries()) {
    const y = 5.32 + index * 0.45; let x = 6.38;
    text(slide, label, { x: 5.42, y, w: 0.95, h: 0.32, fontSize: 10.5, bold: true, valign: 'middle' });
    for (const [part, value] of parts.entries()) {
      const w = value * 0.0098;
      shape(slide, pres.shapes.RECTANGLE, { x, y: y + 0.04, w, h: 0.24, fill: { color: kinds[part][1] }, line: { color: K.white, width: 0.75 } });
      x += w;
    }
    text(slide, signed(-parts.reduce((sum, value) => sum + value, 0)), { x: x + 0.06, y, w: 0.6, h: 0.32, fontSize: 10.5, bold: true, color: 'D92B2B', valign: 'middle' });
  }

  // Where to act, by performance owner (the Regions of the CDRs).
  card(slide, pres, 9.15, 1.75, 3.58, 2.65, 'WHERE TO ACT, BY OWNER');
  const owners = [['North', '0068BF', 48.2, 'Voice calls'], ['South', '8C60A8', 39.5, 'Failed data tests'],
    ['Vendor A', '0C9B5B', 31.4, 'Below-par data'], ['Vendor B', 'E07800', 23.7, 'Voice calls']];
  for (const [index, [name, color, points, theme]] of owners.entries()) {
    const x = 9.33 + (index % 2) * 1.67; const y = 2.17 + Math.floor(index / 2) * 1.08;
    shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 1.57, h: 0.98, rectRadius: 0.08, fill: { color: K.white }, line: { color: K.line, width: 0.75 } });
    shape(slide, pres.shapes.RECTANGLE, { x, y: y + 0.12, w: 0.07, h: 0.74, fill: { color }, line: { color, width: 0 } });
    text(slide, name, { x: x + 0.18, y: y + 0.08, w: 1.35, h: 0.26, fontSize: 11, bold: true, color });
    text(slide, [{ text: signed(-points), options: { fontSize: 17, bold: true, color: 'D92B2B' } }, { text: ' pts', options: { fontSize: 10, color: K.grey } }],
      { x: x + 0.18, y: y + 0.33, w: 1.35, h: 0.36, valign: 'middle' });
    text(slide, theme, { x: x + 0.18, y: y + 0.68, w: 1.35, h: 0.24, fontSize: 9.5, color: K.grey });
  }

  // The sites that lose most, with their priority.
  card(slide, pres, 9.15, 4.55, 3.58, 2.25, 'SITES TO REVIEW');
  for (const [index, label] of ['Site', 'Vendor', 'Points', 'Priority'].entries()) {
    text(slide, label, { x: [9.37, 10.27, 11.12, 11.78][index], y: 4.92, w: 0.85, h: 0.24, fontSize: 9.5, bold: true, color: K.grey });
  }
  const sites = [['Site 0421', 'Vendor A', 3.8, 'High', 'D92B2B'], ['Site 1877', 'Vendor B', 2.9, 'High', 'D92B2B'], ['Site 3508', 'Vendor A', 1.6, 'Medium', 'E07800']];
  for (const [index, [site, vendor, points, priority, color]] of sites.entries()) {
    const y = 5.24 + index * 0.4;
    shape(slide, pres.shapes.LINE, { x: 9.37, y: y - 0.04, w: 3.18, h: 0, line: { color: K.line, width: 0.75 } });
    text(slide, site, { x: 9.37, y, w: 0.9, h: 0.32, fontSize: 10.5, bold: true, valign: 'middle' });
    text(slide, vendor, { x: 10.27, y, w: 0.85, h: 0.32, fontSize: 10.5, valign: 'middle' });
    text(slide, signed(-points), { x: 11.12, y, w: 0.6, h: 0.32, fontSize: 10.5, bold: true, color: 'D92B2B', valign: 'middle' });
    shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x: 11.78, y: y + 0.04, w: 0.78, h: 0.24, rectRadius: 0.12, fill: { color }, line: { color, width: 0 } });
    text(slide, priority, { x: 11.78, y: y + 0.04, w: 0.78, h: 0.24, fontSize: 9.5, bold: true, color: K.white, align: 'center', valign: 'middle' });
  }
  text(slide, 'Up to 25 per operator, with earlier campaigns', { x: 9.37, y: 6.43, w: 3.2, h: 0.24, fontSize: 9.5, color: K.grey });
  slide.addNotes('Every point an operator loses is traced: to the KPIs where matching the reference wins most (the biggest '
    + 'levers), to how it is lost (failed tests, tests below a threshold, quality shortfall), to the areas of the Points '
    + 'Lost Map, to the performance owners of Where to act, to the RAN vendor and kind of the serving sites, to the sites to '
    + 'review and to the stretches of each Connecting Roads route. The figures and the map are illustrative.');
}

async function nqCalls(pres) {
  const slide = pres.addSlide({ masterName: 'CONTENT', sectionTitle: 'Modules' });
  heading(slide, 'NQ Calls — ', 'every failure, followed to closure', 'The NQ Analysis Center: one shared follow-up of every call and test that did not complete');
  const cards = [[STATS.nqExact, `NQ calls in ${plural(FIGURES.campaigns, 'campaign')}`], [STATS.tracked, 'calls with their follow-up'],
    [STATS.rca, 'Ericsson RCA results imported'], [STATS.comments, 'analyst comments and decisions']];
  for (const [index, [value, label]] of cards.entries()) {
    const x = 0.6 + index * 3.09;
    shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.75, w: 2.85, h: 1.3, rectRadius: 0.12, fill: { color: K.tint }, line: { color: K.tint, width: 0 } });
    text(slide, value, { x: x + 0.25, y: 1.88, w: 2.4, h: 0.62, fontSize: 34, bold: true, color: index === 0 ? M.nq.color : K.deep });
    text(slide, label, { x: x + 0.25, y: 2.52, w: 2.45, h: 0.38, fontSize: 12, color: K.grey });
  }
  const sources = [['TbFileAnalytics', 'NetCheck RCA'], ['TbBuildingBroadcastTower', 'Ericsson RCA'], ['TbUsersGroup', 'Analysts']];
  for (const [index, [name, label]] of sources.entries()) {
    const y = 3.4 + index * 0.65;
    shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y, w: 2.3, h: 0.52, rectRadius: 0.26, fill: { color: K.white }, line: { color: K.line, width: 1 } });
    slide.addImage({ data: await icon(name, K.deep), x: 0.78, y: y + 0.11, w: 0.3, h: 0.3, objectName: named('icon') });
    text(slide, label, { x: 1.18, y, w: 1.65, h: 0.52, fontSize: 13, bold: true, valign: 'middle' });
    lineBetween(slide, pres, 2.9, y + 0.26, 3.6, 4.31, { color: K.grey2, width: 1.5, endArrowType: 'triangle' });
  }
  shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x: 3.62, y: 3.68, w: 2.3, h: 1.25, rectRadius: 0.12, fill: { color: K.deep }, line: { color: K.deep, width: 0 } });
  text(slide, [
    { text: 'Root Category', options: { fontSize: 15, bold: true, breakLine: true } },
    { text: '+ Root Cause', options: { fontSize: 15, bold: true, breakLine: true } },
    { text: 'decided from three sources', options: { fontSize: 11, color: 'CFE6FC' } },
  ], { x: 3.8, y: 3.68, w: 2.0, h: 1.25, color: K.white, valign: 'middle' });
  shape(slide, pres.shapes.LINE, { x: 5.95, y: 4.305, w: 0.4, h: 0, line: { color: K.grey2, width: 1.5, endArrowType: 'triangle' } });
  shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x: 6.4, y: 3.68, w: 2.3, h: 1.25, rectRadius: 0.12, fill: { color: K.tint }, line: { color: K.tint, width: 0 } });
  text(slide, [
    { text: 'Status, Team', options: { fontSize: 15, bold: true, breakLine: true } },
    { text: '& Assignee', options: { fontSize: 15, bold: true, breakLine: true } },
    { text: 'by Status Rules or by hand', options: { fontSize: 11, color: K.grey } },
  ], { x: 6.58, y: 3.68, w: 2.0, h: 1.25, valign: 'middle' });
  const extras = [['TbChartBar', 'Summary by campaign & operator'], ['TbFileSpreadsheet', 'Excel export with your layout'],
    ['TbFileImport', 'Previous analyses imported'], ['TbMessages', 'Comments & full history']];
  for (const [index, [name, label]] of extras.entries()) {
    const y = 3.4 + index * 0.57;
    slide.addImage({ data: await icon(name, M.nq.color), x: 9.15, y: y + 0.08, w: 0.32, h: 0.32, objectName: named('icon') });
    text(slide, label, { x: 9.6, y, w: 3.13, h: 0.48, fontSize: 12.5, valign: 'middle' });
  }
  text(slide, 'Six sections per call', { x: 0.6, y: 5.55, w: 4, h: 0.3, fontSize: 11, color: K.grey });
  const phases = ['General', 'RCA', 'Failure details', 'Analysis', 'Implementation', 'Planning'];
  const fills = ['CFE6FC', '9ACDF8', '4DA8F5', K.blue, K.deep, '004E8F'];
  for (const [index, label] of phases.entries()) {
    const x = 0.6 + index * 2.0;
    shape(slide, index === 0 ? pres.shapes.PENTAGON : pres.shapes.CHEVRON, { x, y: 5.9, w: 2.13, h: 0.7, fill: { color: fills[index] }, line: { color: K.white, width: 1.5 } });
    text(slide, label, { x: x + (index === 0 ? 0.12 : 0.38), y: 5.9, w: 1.55, h: 0.7, fontSize: 12.5, bold: true, color: index < 2 ? K.ink : K.white, align: 'center', valign: 'middle' });
  }
  slide.addNotes(`Every Voice, Speech and Data CDR is indexed in the background: ${STATS.nqExact} Non-Qualified calls in `
    + `${plural(FIGURES.campaigns, 'campaign')} of ${STATS.where}, out of ${compact(FIGURES.nq_calls_total)} calls and tests. Each call`
    + ' keeps its follow-up by its NetCheck JOIN_ID through six sections; the root cause comes from '
    + 'the NetCheck RCA, the Ericsson RCA and the analysts; status, team and assignee follow rules or are set by hand.');
}

async function networkInsights(pres, files) {
  const slide = pres.addSlide({ masterName: 'CONTENT', sectionTitle: 'Modules' });
  heading(slide, 'Network Insights — ', 'the network behind the KPIs', 'Radio quality, serving cells, 5G availability, spectrum and deployment, from the CDRs alone');
  slide.addImage({ path: files.map, x: 0.6, y: 1.8, w: 5.6, h: 4.9, objectName: 'Coverage map' });
  shape(slide, pres.shapes.RECTANGLE, { x: 0.6, y: 1.8, w: 5.6, h: 4.9, fill: { type: 'none' }, line: { color: K.line, width: 1 } });
  shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x: 0.8, y: 6.08, w: 5.2, h: 0.44, rectRadius: 0.22, fill: { color: K.white }, line: { color: K.line, width: 1 } });
  text(slide, 'RSRP', { x: 0.98, y: 6.08, w: 0.6, h: 0.44, fontSize: 11, bold: true, valign: 'middle' });
  const legend = [['0C9B5B', 'Excellent'], ['0FC373', 'Good'], ['FAD22D', 'Fair'], ['FF8C0A', 'Poor'], ['FF3232', 'Bad']];
  for (const [index, [color, label]] of legend.entries()) {
    const x = 1.6 + index * 0.86;
    shape(slide, pres.shapes.OVAL, { x, y: 6.21, w: 0.18, h: 0.18, fill: { color }, line: { color, width: 0 } });
    text(slide, label, { x: x + 0.22, y: 6.08, w: 0.66, h: 0.44, fontSize: 10.5, color: K.grey, valign: 'middle' });
  }
  const groups = [
    ['SUMMARY', [['TbLayoutDashboard', 'Overview'], ['TbSparkles', 'Key Findings']]],
    ['RADIO PERFORMANCE', [['TbMap2', 'Coverage & Interference Maps'], ['TbWaveSine', 'RSRP & SINR Quality'], ['TbClock', 'Latency & Interactivity'],
      ['TbBuildingBroadcastTower', 'Serving Cells'], ['TbAntenna', '5G Availability']]],
    ['NETWORK & SPECTRUM', [['TbTopologyStar3', 'Network Snapshot'], ['TbHierarchy3', 'Deployment: NNS & eMOCN'],
      ['TbChartDots3', 'Cluster Sites Density'], ['TbRadar', 'Spectrum: licensed & observed']]],
  ];
  let y = 1.8;
  for (const [title, tiles] of groups) {
    text(slide, title, { x: 6.6, y, w: 6, h: 0.3, fontSize: 11, bold: true, color: K.grey, charSpacing: 1 });
    y += 0.35;
    for (const [index, [name, label]] of tiles.entries()) {
      const x = 6.6 + (index % 3) * 2.09; const tileY = y + Math.floor(index / 3) * 0.75;
      shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x, y: tileY, w: 1.95, h: 0.62, rectRadius: 0.1, fill: { color: K.tint }, line: { color: K.tint, width: 0 } });
      slide.addImage({ data: await icon(name, M.ni.color), x: x + 0.12, y: tileY + 0.16, w: 0.3, h: 0.3, objectName: named('icon') });
      text(slide, label, { x: x + 0.5, y: tileY, w: 1.4, h: 0.62, fontSize: 11.5, valign: 'middle' });
    }
    y += Math.ceil(tiles.length / 3) * 0.75 + 0.15;
  }
  slide.addNotes('Network Insights shows the network behind the measured performance: RSRP and SINR, weak-coverage and '
    + 'high-interference areas on a map, the serving cells, 5G availability, the network snapshot, NNS and eMOCN deployment '
    + 'and the spectrum. Radio views come from the CDRs alone; inventories, KMZ cell configuration and licensed spectrum '
    + 'complete the rest. The map is an illustration.');
}

async function reporting(pres) {
  const slide = pres.addSlide({ masterName: 'CONTENT', sectionTitle: 'Modules' });
  heading(slide, 'Reporting — ', 'from technical detail to executive story', 'Compose once, generate PowerPoint and Word, schedule and email, automatically');
  const sources = ['cdr', 'dash', 'scoring', 'ni', 'nq'];
  for (const [index, key] of sources.entries()) {
    const y = 1.9 + index * 0.62; const module = M[key];
    shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y, w: 2.75, h: 0.5, rectRadius: 0.25, fill: { color: K.white }, line: { color: K.line, width: 1 } });
    await badge(slide, pres, module.icon, 0.68, y + 0.07, 0.36, module.color, module.iconColor || K.white);
    text(slide, module.name, { x: 1.14, y, w: 2.15, h: 0.5, fontSize: 12.5, bold: true, valign: 'middle' });
    lineBetween(slide, pres, 3.35, y + 0.25, 4.0, 3.39, { color: K.grey2, width: 1.25, endArrowType: 'triangle' });
  }
  shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x: 4.05, y: 1.9, w: 3.05, h: 2.98, rectRadius: 0.14, fill: { color: K.black }, line: { color: K.black, width: 0 } });
  slide.addImage({ data: await icon('TbStack2', K.blue), x: 4.3, y: 2.12, w: 0.48, h: 0.48, objectName: named('icon') });
  text(slide, 'Bundle Report Template', { x: 4.3, y: 2.7, w: 2.7, h: 0.4, fontSize: 16, bold: true, color: K.white });
  text(slide, 'One PowerPoint or Word with the sections you choose, in your order', { x: 4.3, y: 3.1, w: 2.65, h: 0.65, fontSize: 11.5, color: K.grey2 });
  for (const [index, key] of sources.entries()) {
    const x = 4.3 + index * 0.53;
    shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x, y: 4.0, w: 0.44, h: 0.32, rectRadius: 0.05, fill: { color: M[key].color }, line: { color: M[key].color, width: 0 } });
    text(slide, String(index + 1), { x, y: 4.0, w: 0.44, h: 0.32, fontSize: 10, bold: true, color: K.white, align: 'center', valign: 'middle' });
  }
  text(slide, 'Sections, filters and campaigns per report', { x: 4.3, y: 4.42, w: 2.7, h: 0.3, fontSize: 10, color: K.grey2 });
  shape(slide, pres.shapes.LINE, { x: 7.15, y: 3.39, w: 0.36, h: 0, line: { color: K.grey2, width: 1.5, endArrowType: 'triangle' } });
  shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x: 7.55, y: 1.9, w: 2.6, h: 2.98, rectRadius: 0.14, fill: { color: K.tint }, line: { color: K.tint, width: 0 } });
  slide.addImage({ data: await icon('TbCalendarRepeat', M.reporting.color), x: 7.8, y: 2.12, w: 0.48, h: 0.48, objectName: named('icon') });
  text(slide, 'Reporting Jobs', { x: 7.8, y: 2.7, w: 2.25, h: 0.4, fontSize: 16, bold: true });
  const modes = ['On demand', 'Daily', 'Weekly', 'Monthly'];
  for (const [index, label] of modes.entries()) {
    const x = 7.8 + (index % 2) * 1.1; const y = 3.2 + Math.floor(index / 2) * 0.45;
    shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 1.0, h: 0.34, rectRadius: 0.17, fill: { color: K.white }, line: { color: 'C9B6D9', width: 1 } });
    text(slide, label, { x, y, w: 1.0, h: 0.34, fontSize: 10.5, color: M.reporting.color, bold: true, align: 'center', valign: 'middle' });
  }
  text(slide, 'Run History with Stop and Rerun', { x: 7.8, y: 4.2, w: 2.25, h: 0.5, fontSize: 10.5, color: K.grey });
  shape(slide, pres.shapes.LINE, { x: 10.2, y: 3.39, w: 0.32, h: 0, line: { color: K.grey2, width: 1.5, endArrowType: 'triangle' } });
  const outputs = [['TbFileTypePpt', 'PowerPoint', 'D35230'], ['TbFileTypeDocx', 'Word', '2B579A'], ['TbMail', 'Email to recipients', K.deep]];
  for (const [index, [name, label, color]] of outputs.entries()) {
    const y = 2.05 + index * 0.95;
    await badge(slide, pres, name, 10.6, y, 0.62, color);
    text(slide, label, { x: 11.32, y, w: 1.45, h: 0.62, fontSize: 12.5, bold: true, valign: 'middle' });
  }
  text(slide, '7', { x: 0.6, y: 5.2, w: 2.4, h: 0.8, fontSize: 48, bold: true, color: K.deep });
  text(slide, 'themes, one click: from the operator brand to the boardroom', { x: 0.6, y: 6.0, w: 2.4, h: 0.65, fontSize: 11.5, color: K.grey });
  const themes = [
    ['NetCheck', 'FFFFFF', '1450A8', ['245E5A', '5B9A44', 'C9483F']],
    ['Umlaut', 'FFFFFF', 'A6192E', ['5B7A99', '8E87A0', 'A6192E']],
    ['Ericsson', 'FFFFFF', '0068BF', ['0068BF', '8C60A8', '0C9B5B']],
    ['Vodafone', 'FFFFFF', 'E60000', ['E60000', '00B0CA', '5E2750']],
    ['Midnight', '080D18', '22C7E8', ['3DB9FF', 'B47CFF', '2EE6A6']],
    ['Paper', 'FFFEFB', '7A1F1F', ['2F3B4A', '8C7B5A', '7A1F1F']],
    ['Heatmap', 'FFFFFF', '2A9D8F', ['2A9D8F', 'E89B2E', 'E05A4F']],
  ];
  for (const [index, [name, background, titleColor, bars]] of themes.entries()) {
    const x = 3.25 + index * 1.36;
    shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x, y: 5.25, w: 1.22, h: 0.78, rectRadius: 0.06, fill: { color: background }, line: { color: K.line, width: 1 },
      shadow: { type: 'outer', color: '000000', opacity: 0.12, blur: 4, offset: 1.5, angle: 90 } });
    shape(slide, pres.shapes.RECTANGLE, { x: x + 0.1, y: 5.35, w: 0.62, h: 0.07, fill: { color: titleColor }, line: { color: titleColor, width: 0 } });
    for (const [bar, color] of bars.entries()) {
      const h = [0.32, 0.22, 0.4][bar];
      shape(slide, pres.shapes.RECTANGLE, { x: x + 0.14 + bar * 0.33, y: 5.93 - h, w: 0.24, h, fill: { color }, line: { color, width: 0 } });
    }
    text(slide, name, { x: x - 0.05, y: 6.1, w: 1.32, h: 0.3, fontSize: 11, color: K.ink, align: 'center' });
  }
  slide.addNotes('A Bundle Report Template composes one PowerPoint or Word document from the sections of PPT Dashboards, Scoring, '
    + 'Network Insights, NQ Calls and CDR Analysis. Reporting Jobs run it, or any artifact, on demand or on a schedule and '
    + 'email it; the Run History stops, reruns and resumes runs. Seven themes take the same report from the operator brand to '
    + 'the boardroom.');
}

async function cdrAnalysis(pres, files) {
  const slide = pres.addSlide({ masterName: 'CONTENT', sectionTitle: 'Modules' });
  heading(slide, 'CDR Analysis — ', 'every KPI of one CDR, in depth', 'On-demand KPI analysis of one processed Data, Voice or Speech CDR, exported to PowerPoint and Word');
  shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y: 1.8, w: 6.6, h: 4.95, rectRadius: 0.12, fill: { color: K.white }, line: { color: K.line, width: 1 } });
  // The distribution of a KPI per operator, as its Global CDF Comparison draws it.
  text(slide, 'Global CDF comparison · DL throughput (Mbps)', { x: 0.85, y: 1.92, w: 6.1, h: 0.3, fontSize: 13, color: K.grey, align: 'center' });
  const plot = { x: 1.35, y: 2.38, w: 5.55, h: 3.52 };
  slide.addImage({ path: files.cdf, ...plot, objectName: 'CDF curves' });
  for (const share of [0, 25, 50, 75, 100]) {
    text(slide, `${share}%`, { x: 0.78, y: plot.y + (1 - share / 100) * plot.h - 0.11, w: 0.5, h: 0.22, fontSize: 10, color: K.grey, align: 'right', valign: 'middle' });
  }
  for (const value of [0, 50, 100, 150, 200, 250]) {
    text(slide, String(value), { x: plot.x + (value / 250) * plot.w - 0.3, y: plot.y + plot.h + 0.06, w: 0.6, h: 0.22, fontSize: 10, color: K.grey, align: 'center' });
  }
  for (const [index, operator] of OPERATORS.slice(0, 3).entries()) {
    const x = 1.35 + index * 1.45;
    shape(slide, pres.shapes.LINE, { x, y: 6.47, w: 0.3, h: 0, line: { color: operator.color, width: 3 } });
    text(slide, operator.name, { x: x + 0.38, y: 6.35, w: 1.05, h: 0.24, fontSize: 10.5, valign: 'middle' });
  }
  text(slide, 'Illustrative data', { x: 5.55, y: 6.35, w: 1.4, h: 0.24, fontSize: 10, color: K.grey2, align: 'right', valign: 'middle' });
  const tiles = [
    ['TbChartLine', 'CDF curves', 'Up to eight, by operator, vendor or city'], ['TbChartBar', 'Group benchmark', 'Bars of the aggregation you choose'],
    ['TbGauge', 'Scorecards', 'Metric cards and percentiles'], ['TbTable', 'Processed metrics', 'Every calculated record, checked'],
  ];
  for (const [index, [name, title, desc]] of tiles.entries()) {
    const x = 7.6 + (index % 2) * 2.65; const y = 1.8 + Math.floor(index / 2) * 1.42;
    shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 2.45, h: 1.27, rectRadius: 0.12, fill: { color: K.tint }, line: { color: K.tint, width: 0 } });
    await badge(slide, pres, name, x + 0.18, y + 0.18, 0.46, M.cdr.color);
    text(slide, title, { x: x + 0.74, y: y + 0.2, w: 1.65, h: 0.4, fontSize: 13.5, bold: true, valign: 'middle' });
    text(slide, desc, { x: x + 0.18, y: y + 0.72, w: 2.2, h: 0.48, fontSize: 10.5, color: K.grey });
  }
  const flow = ['Pick a CDR', 'Metrics & filters', 'Update Analysis', 'Export'];
  shape(slide, pres.shapes.LINE, { x: 8.2, y: 4.86, w: 3.9, h: 0, line: { color: K.line, width: 2 } });
  for (const [index, label] of flow.entries()) {
    const x = 7.6 + index * 1.3;
    shape(slide, pres.shapes.OVAL, { x: x + 0.43, y: 4.65, w: 0.42, h: 0.42, fill: { color: index === 3 ? K.deep : K.white }, line: { color: K.deep, width: 1.5 } });
    text(slide, String(index + 1), { x: x + 0.43, y: 4.65, w: 0.42, h: 0.42, fontSize: 12, bold: true, color: index === 3 ? K.white : K.deep, align: 'center', valign: 'middle' });
    text(slide, label, { x, y: 5.12, w: 1.28, h: 0.45, fontSize: 10.5, bold: true, align: 'center', valign: 'top' });
  }
  text(slide, 'EXPORTS', { x: 7.6, y: 5.85, w: 2, h: 0.26, fontSize: 10.5, bold: true, color: K.grey, charSpacing: 1 });
  await badge(slide, pres, 'TbFileTypePpt', 7.6, 6.18, 0.5, 'D35230');
  await badge(slide, pres, 'TbFileTypeDocx', 8.2, 6.18, 0.5, '2B579A');
  text(slide, 'PowerPoint and Word of the analysis on screen, in seven themes', { x: 8.85, y: 6.13, w: 3.85, h: 0.6, fontSize: 11.5, color: K.grey, valign: 'middle' });
  slide.addNotes('CDR Analysis studies one processed CDR at a time: choose its metrics and filters, update the analysis and read '
    + 'the CDF curves (up to eight, by operator, vendor or city), the group benchmark, the metric cards and percentiles and '
    + 'every processed record; then export it to PowerPoint or Word, in seven themes. The chart uses illustrative data.');
}

async function dashboards(pres) {
  const slide = pres.addSlide({ masterName: 'CONTENT', sectionTitle: 'Modules' });
  heading(slide, 'PPT Dashboards — ', 'the KPI deck, live and in PowerPoint', 'A saved Report Template becomes an interactive Dashboard of every slide, then a PowerPoint in one click');
  const stages = [
    ['1', 'Report Template', 'Slides, charts, KPIs and splits, validated as you edit'],
    ['2', 'Interactive Dashboard', 'Every slide live, with its scope, filters and comments'],
    ['3', 'PowerPoint', 'The whole deck in your template, in one click'],
  ];
  for (const [index, [number, title, desc]] of stages.entries()) {
    const x = 0.6 + index * 4.19;
    shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.8, w: 3.75, h: 3.6, rectRadius: 0.14, fill: { color: K.tint }, line: { color: K.tint, width: 0 } });
    shape(slide, pres.shapes.OVAL, { x: x + 0.22, y: 2.0, w: 0.42, h: 0.42, fill: { color: M.dash.color }, line: { color: M.dash.color, width: 0 } });
    text(slide, number, { x: x + 0.22, y: 2.0, w: 0.42, h: 0.42, fontSize: 13, bold: true, color: K.white, align: 'center', valign: 'middle' });
    text(slide, title, { x: x + 0.78, y: 2.0, w: 2.85, h: 0.42, fontSize: 15, bold: true, valign: 'middle' });
    text(slide, desc, { x: x + 0.22, y: 4.72, w: 3.35, h: 0.55, fontSize: 11, color: K.grey, valign: 'top' });
    if (index < stages.length - 1) {
      shape(slide, pres.shapes.LINE, { x: x + 3.8, y: 3.4, w: 0.34, h: 0, line: { color: K.grey2, width: 1.75, endArrowType: 'triangle' } });
    }
  }
  // 1: the rows of a Report Template.
  slide.addTable([
    ['Slide', 'Chart', 'KPI', 'Split'].map((value) => ({ text: value, options: { bold: true, color: K.white, fill: { color: M.dash.color } } })),
    ['3', 'CDF', 'DL throughput', 'Operator'], ['4', 'Bars', 'Call setup time', 'City'], ['5', 'Map', 'RSRP', 'Region'], ['6', 'Table', 'POLQA LQ', 'Vendor'],
  ], { x: 0.82, y: 2.62, w: 3.31, colW: [0.55, 0.65, 1.21, 0.9], fontSize: 9.5, fontFace: BODY, color: K.ink, rowH: 0.36,
    border: { type: 'solid', color: K.line, pt: 0.75 }, fill: { color: K.white }, margin: 0.04, objectName: 'Report Template rows' });
  // 2: a slide of the Dashboard with its four charts.
  const sx = 5.0; const sy = 2.6;
  shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x: sx, y: sy, w: 3.33, h: 1.95, rectRadius: 0.06, fill: { color: K.white }, line: { color: K.line, width: 1 } });
  shape(slide, pres.shapes.RECTANGLE, { x: sx + 0.15, y: sy + 0.14, w: 1.6, h: 0.08, fill: { color: K.ink }, line: { color: K.ink, width: 0 } });
  for (let chart = 0; chart < 4; chart += 1) {
    const cx = sx + 0.15 + (chart % 2) * 1.58; const cy = sy + 0.36 + Math.floor(chart / 2) * 0.78;
    shape(slide, pres.shapes.RECTANGLE, { x: cx, y: cy, w: 1.45, h: 0.68, fill: { color: K.tint2 }, line: { color: K.line, width: 0.5 } });
    [0.42, 0.3, 0.52, 0.22].forEach((height, bar) => {
      const color = [K.deep, '0C9B5B', 'E07800', K.purple][bar];
      shape(slide, pres.shapes.RECTANGLE, { x: cx + 0.14 + bar * 0.31, y: cy + 0.6 - height, w: 0.2, h: height, fill: { color }, line: { color, width: 0 } });
    });
  }
  // 3: the PowerPoint, slide over slide.
  for (let layer = 2; layer >= 0; layer -= 1) {
    const lx = 9.35 + layer * 0.22; const ly = 2.7 + layer * 0.18;
    shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x: lx, y: ly, w: 2.45, h: 1.38, rectRadius: 0.05, fill: { color: K.white }, line: { color: K.line, width: 1 } });
    shape(slide, pres.shapes.RECTANGLE, { x: lx + 0.14, y: ly + 0.14, w: 1.2, h: 0.07, fill: { color: K.ink }, line: { color: K.ink, width: 0 } });
    if (layer === 0) {
      [0.55, 0.38, 0.7, 0.45, 0.6].forEach((height, bar) => {
        shape(slide, pres.shapes.RECTANGLE, { x: lx + 0.25 + bar * 0.4, y: ly + 1.2 - height, w: 0.26, h: height, fill: { color: M.dash.color }, line: { color: M.dash.color, width: 0 } });
      });
    }
  }
  await badge(slide, pres, 'TbFileTypePpt', 11.8, 3.85, 0.62, 'D35230');
  const chips = [['TbFilter', 'Scope & filters'], ['TbDatabase', 'Cached preparation'], ['TbMessages', 'Slide comments'],
    ['TbPresentation', 'Presentation mode'], ['TbTable', 'Filtered chart data']];
  for (const [index, [name, label]] of chips.entries()) {
    const x = 0.6 + index * 2.457;
    shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x, y: 5.75, w: 2.3, h: 0.55, rectRadius: 0.12, fill: { color: K.white }, line: { color: K.line, width: 1 } });
    slide.addImage({ data: await icon(name, M.dash.color), x: x + 0.15, y: 5.88, w: 0.3, h: 0.3, objectName: named('icon') });
    text(slide, label, { x: x + 0.55, y: 5.75, w: 1.7, h: 0.55, fontSize: 11.5, bold: true, valign: 'middle' });
  }
  slide.addNotes('PPT Dashboards turns a saved Report Template, its slides, charts, KPIs and splits, into an interactive '
    + 'Dashboard of every slide, prepared in the background and cached, with its scope, filters and comments, a presentation '
    + 'mode and the dataset behind every chart; then the whole deck becomes a PowerPoint in one click, in your template.');
}

async function builders(pres) {
  const slide = pres.addSlide({ masterName: 'CONTENT', sectionTitle: 'Modules' });
  heading(slide, 'Builders — ', 'ad-hoc charts and SQL, in seconds', 'Chart Builder and Query Builder explore any KPI or field of the CDRs, without changing a template');
  for (const [index, [name, title, desc]] of [['TbChartBar', 'Chart Builder', 'Any KPI as a chart, split by rows and columns'],
    ['TbCode', 'Query Builder', 'Read-only SQL on the CDRs, assisted or by hand']].entries()) {
    const x = 0.6 + index * 6.18;
    shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.8, w: 5.95, h: 4.95, rectRadius: 0.14, fill: { color: K.tint }, line: { color: K.tint, width: 0 } });
    await badge(slide, pres, name, x + 0.22, 1.98, 0.5, M.builders.color);
    text(slide, title, { x: x + 0.86, y: 1.96, w: 4.9, h: 0.32, fontSize: 16, bold: true });
    text(slide, desc, { x: x + 0.86, y: 2.28, w: 4.9, h: 0.28, fontSize: 11.5, color: K.grey });
  }
  // Chart Builder: a chart of two operators by city.
  text(slide, 'Median DL throughput (Mbps) by city', { x: 0.8, y: 2.72, w: 5.55, h: 0.28, fontSize: 12, color: K.grey, align: 'center' });
  const cities = [['London', 162, 141], ['Leeds', 148, 152], ['Glasgow', 131, 118], ['Cardiff', 139, 126]];
  const baseline = 5.12; const groupW = 5.55 / cities.length;
  shape(slide, pres.shapes.LINE, { x: 0.85, y: baseline, w: 5.45, h: 0, line: { color: K.grey2, width: 1 } });
  for (const [index, [city, ...values]] of cities.entries()) {
    const groupX = 0.8 + index * groupW;
    for (const [series, value] of values.entries()) {
      const h = (value / 180) * 1.8; const x = groupX + groupW / 2 - 0.5 + series * 0.52; const color = OPERATORS[series].color;
      shape(slide, pres.shapes.RECTANGLE, { x, y: baseline - h, w: 0.48, h, fill: { color }, line: { color, width: 0 } });
      text(slide, String(value), { x: x - 0.1, y: baseline - h - 0.26, w: 0.68, h: 0.24, fontSize: 10, bold: true, align: 'center', valign: 'bottom' });
    }
    text(slide, city, { x: groupX, y: baseline + 0.05, w: groupW, h: 0.26, fontSize: 11, align: 'center' });
  }
  for (const [index, operator] of OPERATORS.slice(0, 2).entries()) {
    const x = 0.85 + index * 1.45;
    shape(slide, pres.shapes.RECTANGLE, { x, y: 5.57, w: 0.16, h: 0.16, fill: { color: operator.color }, line: { color: operator.color, width: 0 } });
    text(slide, operator.name, { x: x + 0.22, y: 5.52, w: 1.1, h: 0.26, fontSize: 10.5, valign: 'middle' });
  }
  // Query Builder: its SQL and the first rows of the result.
  shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x: 7.0, y: 2.75, w: 5.5, h: 1.5, rectRadius: 0.08, fill: { color: '1E1E1E' }, line: { color: '1E1E1E', width: 0 } });
  text(slide, [
    { text: 'SELECT ', options: { color: '6CB6FF', breakLine: false } }, { text: 'operator, COUNT(*) AS samples,', options: { color: 'E6E6E6', breakLine: true } },
    { text: '       MEDIAN(dl_throughput) AS median_dl', options: { color: 'E6E6E6', breakLine: true } },
    { text: 'FROM ', options: { color: '6CB6FF' } }, { text: 'cdr_data ', options: { color: 'E6E6E6' } },
    { text: 'WHERE ', options: { color: '6CB6FF' } }, { text: "campaign = 'Q3_2026'", options: { color: 'F2B880', breakLine: true } },
    { text: 'GROUP BY ', options: { color: '6CB6FF' } }, { text: 'operator', options: { color: 'E6E6E6' } },
  ], { x: 7.18, y: 2.85, w: 5.2, h: 1.3, fontFace: 'Courier New', fontSize: 11, valign: 'middle' });
  slide.addTable([
    ['operator', 'samples', 'median_dl'].map((value) => ({ text: value, options: { bold: true, color: K.white, fill: { color: M.builders.color } } })),
    ['Operator A', '41,203', '148.9'], ['Operator B', '39,877', '137.6'], ['Operator C', '38,512', '121.3'],
  ], { x: 7.0, y: 4.38, w: 5.5, colW: [2.1, 1.7, 1.7], fontSize: 10.5, fontFace: 'Courier New', color: K.ink, rowH: 0.3,
    border: { type: 'solid', color: K.line, pt: 0.75 }, fill: { color: K.white }, margin: 0.05, objectName: 'Query Builder results' });
  text(slide, 'Illustrative data', { x: 4.8, y: 5.52, w: 1.5, h: 0.26, fontSize: 10, color: K.grey2, align: 'right', valign: 'middle' });
  const chipRow = async (x, chips) => {
    for (const [index, [name, label]] of chips.entries()) {
      const cx = x + index * 1.88;
      shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x: cx, y: 6.0, w: 1.78, h: 0.5, rectRadius: 0.12, fill: { color: K.white }, line: { color: K.line, width: 1 } });
      slide.addImage({ data: await icon(name, M.builders.color), x: cx + 0.12, y: 6.12, w: 0.26, h: 0.26, objectName: named('icon') });
      text(slide, label, { x: cx + 0.45, y: 6.0, w: 1.3, h: 0.5, fontSize: 10.5, bold: true, valign: 'middle' });
    }
  };
  await chipRow(0.8, [['TbFilter', 'Filter Builder'], ['TbLayoutGrid', 'Rows & columns'], ['TbAdjustments', 'Legend & title']]);
  await chipRow(6.98, [['TbClick', 'Assistance Mode'], ['TbTerminal2', 'SQL Mode'], ['TbBookmark', 'Saved · CSV']]);
  slide.addNotes('The Builders explore the CDRs without changing any template. Chart Builder draws any KPI of the chosen CDRs '
    + 'as a chart, split by rows and columns, with the Filter Builder, its legend and title. Query Builder runs read-only SQL '
    + 'on them, built with Assistance Mode or written in SQL Mode; queries are saved, exported and their results copied or '
    + 'downloaded as CSV. Charts and results use illustrative data.');
}

async function ticketCenter(pres) {
  const slide = pres.addSlide({ masterName: 'CONTENT', sectionTitle: 'Modules' });
  heading(slide, 'Ticket Center — ', 'every bug and idea, tracked to closure', 'Report bugs, improvements and new features with their screenshots, and follow each one until it is resolved');
  const statuses = [['New', K.blue], ['In Progress', K.deep], ['Waiting for Info', 'E07800'], ['Resolved', '0C9B5B']];
  for (const [index, [label, color]] of statuses.entries()) {
    const x = 0.6 + index * 2.6;
    shape(slide, index === 0 ? pres.shapes.PENTAGON : pres.shapes.CHEVRON, { x, y: 1.85, w: 2.72, h: 0.72, fill: { color }, line: { color: K.white, width: 1.5 } });
    text(slide, label, { x: x + (index === 0 ? 0.15 : 0.4), y: 1.85, w: 2.0, h: 0.72, fontSize: 13, bold: true, color: K.white, align: 'center', valign: 'middle' });
  }
  for (const [index, [label, color]] of [['Closed', '767676'], ['Rejected', 'CC2828']].entries()) {
    shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x: 11.3, y: 1.85 + index * 0.4, w: 1.43, h: 0.32, rectRadius: 0.16, fill: { color }, line: { color, width: 0 } });
    text(slide, label, { x: 11.3, y: 1.85 + index * 0.4, w: 1.43, h: 0.32, fontSize: 11, bold: true, color: K.white, align: 'center', valign: 'middle' });
  }
  // Types and priorities, side by side.
  const card = (x, title) => {
    shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x, y: 2.9, w: 5.95, h: 2.45, rectRadius: 0.14, fill: { color: K.tint }, line: { color: K.tint, width: 0 } });
    text(slide, title, { x: x + 0.25, y: 3.02, w: 5, h: 0.3, fontSize: 11, bold: true, color: K.grey, charSpacing: 1 });
  };
  card(0.6, 'TYPES');
  const types = [['TbBug', 'Bug', 'CC2828', 'Something does not work as it should'], ['TbBulb', 'Improvement', '0C9B5B', 'Something that works could work better'],
    ['TbSparkles', 'New Feature', '8C60A8', 'Something the tool cannot do yet']];
  for (const [index, [name, label, color, desc]] of types.entries()) {
    const y = 3.45 + index * 0.62;
    shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x: 0.85, y, w: 1.85, h: 0.46, rectRadius: 0.23, fill: { color }, line: { color, width: 0 } });
    slide.addImage({ data: await icon(name, K.white), x: 0.98, y: y + 0.09, w: 0.28, h: 0.28, objectName: named('icon') });
    text(slide, label, { x: 1.32, y, w: 1.35, h: 0.46, fontSize: 12, bold: true, color: K.white, valign: 'middle' });
    text(slide, desc, { x: 2.85, y, w: 3.55, h: 0.46, fontSize: 11.5, color: K.ink, valign: 'middle' });
  }
  card(6.78, 'PRIORITIES');
  const priorities = [['P1 · Critical', 'CC2828', 1], ['P2 · High', 'E07800', 0.85], ['P3 · Medium', 'FAD22D', 0.7], ['P4 · Low', K.blue, 0.55], ['P5 · Trivial', K.grey2, 0.4]];
  for (const [index, [label, color, share]] of priorities.entries()) {
    const y = 3.42 + index * 0.37;
    shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x: 7.03, y, w: 5.45 * share, h: 0.3, rectRadius: 0.08, fill: { color }, line: { color, width: 0 } });
    text(slide, label, { x: 7.15, y, w: 2.2, h: 0.3, fontSize: 11, bold: true, color: color === 'FAD22D' ? K.ink : K.white, valign: 'middle' });
  }
  const chips = [['TbLayoutGrid', 'Open, resolved & mine tiles'], ['TbCalendarStats', 'Created vs resolved per period'], ['TbHourglass', 'Age of the oldest open ticket'],
    ['TbHistory', 'Timeline of comments & changes'], ['TbPhoto', 'Screenshots in every ticket'], ['TbTag', 'Version it was opened with']];
  for (const [index, [name, label]] of chips.entries()) {
    const x = 0.6 + (index % 3) * 4.09; const y = 5.6 + Math.floor(index / 3) * 0.6;
    shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 3.95, h: 0.48, rectRadius: 0.12, fill: { color: K.white }, line: { color: K.line, width: 1 } });
    slide.addImage({ data: await icon(name, 'B38F00'), x: x + 0.14, y: y + 0.1, w: 0.28, h: 0.28, objectName: named('icon') });
    text(slide, label, { x: x + 0.52, y, w: 3.35, h: 0.48, fontSize: 11.5, bold: true, valign: 'middle' });
  }
  slide.addNotes('The Ticket Center collects the bugs, improvements and new features of the users, with their screenshots and '
    + 'the version they were opened with, from New to Resolved, Closed or Rejected, each with its priority from P1 to P5 and a '
    + 'timeline of comments and changes; its dashboard counts the open tickets, those created and resolved every day, week, month, quarter or year and the '
    + 'age of the oldest one.');
}

async function enterprise(pres) {
  const slide = pres.addSlide({ masterName: 'CONTENT', sectionTitle: 'Platform' });
  heading(slide, 'Enterprise-ready: ', 'secure, governed, backed up', 'Cloud deployment, role-based access, isolated workspaces, automated backups and built-in support');
  const card = (x, y, w, h, fill = K.tint) => shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.14, fill: { color: fill }, line: { color: fill, width: 0 } });
  const cardTitle = async (x, y, name, color, label, w) => {
    slide.addImage({ data: await icon(name, color), x, y, w: 0.36, h: 0.36, objectName: named('icon') });
    text(slide, label, { x: x + 0.46, y: y - 0.02, w, h: 0.4, fontSize: 15, bold: true, valign: 'middle' });
  };
  // Cloud deployment: AWS > Docker > application > isolated workspaces.
  card(0.6, 1.8, 3.35, 4.95);
  await cardTitle(0.82, 1.98, 'TbBrandAws', 'E47911', 'Cloud deployment', 2.6);
  shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x: 0.8, y: 2.55, w: 2.95, h: 4.0, rectRadius: 0.12, fill: { color: K.white }, line: { color: 'E47911', width: 1.25, dashType: 'dash' } });
  text(slide, 'AWS cloud', { x: 0.95, y: 2.62, w: 2.5, h: 0.3, fontSize: 11, bold: true, color: 'B35F0E' });
  shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x: 0.95, y: 2.98, w: 2.65, h: 3.42, rectRadius: 0.1, fill: { color: 'F4F9FE' }, line: { color: K.blue, width: 1.25 } });
  slide.addImage({ data: await icon('TbBrandDocker', K.blue), x: 1.08, y: 3.06, w: 0.28, h: 0.28, objectName: named('icon') });
  text(slide, 'Docker · AMD64 & ARM64', { x: 1.42, y: 3.04, w: 2.1, h: 0.32, fontSize: 10.5, bold: true, color: K.deep, valign: 'middle' });
  shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x: 1.1, y: 3.45, w: 2.35, h: 1.0, rectRadius: 0.08, fill: { color: K.black }, line: { color: K.black, width: 0 } });
  text(slide, [
    { text: 'DriveTest Analyzer', options: { fontSize: 12.5, bold: true, color: K.white, breakLine: true } },
    { text: 'web app + background workers', options: { fontSize: 10, color: K.grey2 } },
  ], { x: 1.22, y: 3.45, w: 2.15, h: 1.0, valign: 'middle' });
  // (The first two workspaces of the server, each with its campaigns.)
  for (const [index, [name, detail]] of FIGURES.workspace_list.slice(0, 2).map((item) => [item.name, plural(item.campaigns, 'campaign')]).entries()) {
    const x = 1.1 + index * 1.25;
    shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x, y: 4.62, w: 1.1, h: 0.95, rectRadius: 0.08, fill: { color: K.white }, line: { color: K.line, width: 1 } });
    slide.addImage({ data: await icon('TbDatabase', K.deep), x: x + 0.38, y: 4.7, w: 0.34, h: 0.34, objectName: named('icon') });
    text(slide, [{ text: name, options: { bold: true, fontSize: 12, breakLine: true } }, { text: detail, options: { fontSize: 9.5, color: K.grey } }],
      { x, y: 5.06, w: 1.1, h: 0.48, align: 'center', valign: 'middle' });
  }
  text(slide, 'Isolated workspaces · persistent volumes', { x: 1.1, y: 5.68, w: 2.4, h: 0.55, fontSize: 10, color: K.grey, align: 'center' });
  // Users, roles & access.
  card(4.15, 1.8, 4.35, 2.4);
  await cardTitle(4.37, 1.98, 'TbUserShield', K.deep, 'Users, roles & access', 3.4);
  const role = (key) => exact(FIGURES.roles[key] || 0);
  const roles = [['Super Admin', role('super-admin'), 1.9, '004E8F'], ['Admin', role('admin'), 2.5, K.deep], ['Editor', role('user-editor'), 3.1, K.blue],
    ['Viewer', role('user-viewer'), 3.7, '4DA8F5']];
  for (const [index, [role, count, w, color]] of roles.entries()) {
    const y = 2.5 + index * 0.37;
    shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x: 6.325 - w / 2, y, w, h: 0.32, rectRadius: 0.06, fill: { color }, line: { color, width: 0 } });
    text(slide, `${role} · ${count}`, { x: 6.325 - w / 2, y, w, h: 0.32, fontSize: 11, bold: true, color: K.white, align: 'center', valign: 'middle' });
  }
  text(slide, 'Modules Profiles · Workspace Groups · access requests', { x: 4.37, y: 3.98, w: 3.95, h: 0.2, fontSize: 10, color: K.grey, align: 'center' });
  // Configuration at every level.
  card(4.15, 4.35, 4.35, 2.4);
  await cardTitle(4.37, 4.53, 'TbAdjustmentsHorizontal', K.deep, 'Configuration at every level', 3.4);
  const levels = [['TbSettings', 'App Config'], ['TbFolders', 'Workspace Config'], ['TbShieldLock', 'Admin'], ['TbKey', 'Super Admin']];
  for (const [index, [name, label]] of levels.entries()) {
    const x = 4.37 + index * 1.0;
    shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x, y: 5.08, w: 0.9, h: 1.05, rectRadius: 0.08, fill: { color: K.white }, line: { color: K.line, width: 1 } });
    slide.addImage({ data: await icon(name, [K.blue, K.blue, K.deep, '004E8F'][index]), x: x + 0.29, y: 5.17, w: 0.32, h: 0.32, objectName: named('icon') });
    text(slide, label, { x: x + 0.03, y: 5.52, w: 0.84, h: 0.55, fontSize: 10, bold: true, align: 'center', valign: 'middle' });
  }
  text(slide, 'Email, themes, templates, mappings, methodologies', { x: 4.37, y: 6.25, w: 3.95, h: 0.3, fontSize: 10, color: K.grey, align: 'center' });
  // Backups, Ticket Center, Help & quality.
  card(8.7, 1.8, 4.03, 1.52);
  await cardTitle(8.92, 1.95, 'TbDatabaseExport', '0C9B5B', 'Automated backups', 3.0);
  const week = ['F', 'L', 'L', 'L', 'L', 'L', 'L'];
  for (const [index, kind] of week.entries()) {
    const x = 8.92 + index * 0.42;
    const fill = kind === 'F' ? '0C9B5B' : 'B7EDD6';
    shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x, y: 2.48, w: 0.34, h: 0.34, rectRadius: 0.05, fill: { color: fill }, line: { color: fill, width: 0 } });
    text(slide, kind, { x, y: 2.48, w: 0.34, h: 0.34, fontSize: 10, bold: true, color: kind === 'F' ? K.white : '0B5E39', align: 'center', valign: 'middle' });
  }
  text(slide, 'Full + Light, hourly to monthly, smart retention', { x: 8.92, y: 2.88, w: 3.65, h: 0.35, fontSize: 10, color: K.grey });
  card(8.7, 3.515, 4.03, 1.52);
  await cardTitle(8.92, 3.665, 'TbTicket', 'B38F00', 'Ticket Center', 3.0);
  const types = [['Bug', 'CC2828'], ['Improvement', '0C9B5B'], ['New Feature', '8C60A8']];
  let typeX = 8.92;
  for (const [label, color] of types) {
    const w = 0.3 + label.length * 0.085;
    shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x: typeX, y: 4.2, w, h: 0.32, rectRadius: 0.16, fill: { color }, line: { color, width: 0 } });
    text(slide, label, { x: typeX, y: 4.2, w, h: 0.32, fontSize: 10, bold: true, color: K.white, align: 'center', valign: 'middle' });
    typeX += w + 0.1;
  }
  text(slide, 'P1 to P5, dashboard of open, resolved and ageing tickets', { x: 8.92, y: 4.6, w: 3.65, h: 0.35, fontSize: 10, color: K.grey });
  card(8.7, 5.23, 4.03, 1.52);
  await cardTitle(8.92, 5.38, 'TbBook2', K.deep, 'Help & quality', 3.0);
  const quality = [[STATS.chapters, 'Help chapters'], [STATS.tests, 'automated tests'], [STATS.releases, 'releases']];
  for (const [index, [value, label]] of quality.entries()) {
    const x = 8.92 + index * 1.25;
    text(slide, value, { x, y: 5.85, w: 1.2, h: 0.45, fontSize: 22, bold: true, color: K.deep });
    text(slide, label, { x, y: 6.3, w: 1.2, h: 0.3, fontSize: 10, color: K.grey });
  }
  slide.addNotes('DriveTest Analyzer runs on AWS as a Docker container, with images for AMD64 and ARM64 and persistent '
    + 'volumes. Each workspace keeps its own database and files. Four roles, Modules Profiles and Workspace Groups decide who '
    + 'sees and changes what, from App Config up to Super Admin. Backups run on a schedule, full and light, with retention by '
    + `day, week and month. The Ticket Center collects bugs, improvements and requests, and the Help has ${STATS.chapters} chapters.`);
}

// The road of the roadmap through its milestones (inches of the slide); art.roadmapRoad draws it.
const ROAD = [[-0.4, 4.55], [1.95, 4.2], [3.3, 4.45], [4.55, 4.2], [6.0, 3.95], [7.5, 4.15], [9.0, 4.3], [10.65, 4.0], [11.7, 3.15],
  [12.45, 2.2], [12.75, 1.95]];

async function roadmap(pres, files, masterName = 'CONTENT') {
  const slide = pres.addSlide({ masterName, sectionTitle: 'Roadmap' });
  slide.addImage({ path: files.road, x: 0, y: 0, w: 13.333, h: 7.5, objectName: 'Roadmap road' });
  heading(slide, 'Roadmap — ', 'what comes next', 'Intentions, not commitments, shaped by the teams that use the tool');
  // Each phase: its milestone on the road, and a card above or below it with what it brings.
  const phases = [
    { label: 'TODAY', color: '0C9B5B', pin: 'TbCircleCheck', x: 1.95, y: 4.2, card: [0.6, 1.75, 2.75, 1.85], items: [
      ['TbCircleCheck', '8 modules live', `${names}, ${plural(FIGURES.campaigns, 'campaign')}`],
      ['TbFlag', 'Germany pilot', 'First DE test campaign'],
    ] },
    { label: 'NEXT', color: K.blue, pin: 'TbRocket', x: 4.55, y: 4.2, card: [2.85, 4.78, 3.4, 2.3], items: [
      ['TbPlugConnected', 'Umlaut CDR adaptation', 'Ingest & score Umlaut CDRs'],
      ['TbUsersGroup', 'Active Tests community', 'Builds their KPI & Scoring reports'],
      ['TbPhoneCheck', 'NQ Calls out of Alpha', 'From Alpha to every team'],
    ] },
    { label: 'SOON', color: '8C60A8', pin: 'TbArrowsMaximize', x: 7.5, y: 4.15, card: [5.75, 1.75, 3.5, 1.85], items: [
      ['TbArrowsMaximize', 'Scalability on AWS', 'Worker queue, scale-out processing'],
      ['TbBolt', 'Fast at any size', 'Durable analytical caches'],
    ] },
    { label: 'LATER', color: 'E07800', pin: 'TbClock', x: 10.65, y: 4.0, card: [8.9, 4.55, 3.5, 2.3], items: [
      ['TbDatabase', 'PostgreSQL database', 'Hundreds of concurrent users'],
      ['TbHierarchy3', 'Smart Orchestrator Logs', 'A new source and its reports'],
      ['TbHeartbeat', 'Health monitoring', 'Alerts & checks after each deploy'],
    ] },
  ];
  for (const phase of phases) {
    const [x, y, w, h] = phase.card;
    const above = y + h < phase.y;
    // The card, joined to its milestone by a dashed line in the colour of the phase.
    lineBetween(slide, pres, phase.x, above ? y + h : phase.y + 0.31, phase.x, above ? phase.y - 0.31 : y, { color: phase.color, width: 2, dashType: 'dash' });
    shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.14, fill: { color: K.white }, line: { color: K.line, width: 1 },
      shadow: { type: 'outer', color: '000000', opacity: 0.12, blur: 8, offset: 2, angle: 90 } });
    const pillW = 0.3 + phase.label.length * 0.12;
    shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x: x + 0.2, y: y + 0.18, w: pillW, h: 0.3, rectRadius: 0.15, fill: { color: phase.color }, line: { color: phase.color, width: 0 } });
    text(slide, phase.label, { x: x + 0.2, y: y + 0.18, w: pillW, h: 0.3, fontSize: 10.5, bold: true, color: K.white, align: 'center', valign: 'middle', charSpacing: 1.5 });
    for (const [row, [name, title, desc]] of phase.items.entries()) {
      const rowY = y + 0.62 + row * 0.56;
      await badge(slide, pres, name, x + 0.2, rowY + 0.04, 0.42, phase.color);
      text(slide, title, { x: x + 0.74, y: rowY, w: w - 0.9, h: 0.27, fontSize: 13.5, bold: true });
      text(slide, desc, { x: x + 0.74, y: rowY + 0.27, w: w - 0.9, h: 0.24, fontSize: 10.5, color: K.grey });
    }
    // The milestone: the icon of the phase on the road, ringed in white.
    shape(slide, pres.shapes.OVAL, { x: phase.x - 0.34, y: phase.y - 0.34, w: 0.68, h: 0.68, fill: { color: K.white }, line: { color: K.white, width: 0 },
      shadow: { type: 'outer', color: '000000', opacity: 0.25, blur: 6, offset: 1.5, angle: 90 } });
    await badge(slide, pres, phase.pin, phase.x - 0.28, phase.y - 0.28, 0.56, phase.color);
  }
  slide.addNotes(`Today: eight modules in production on ${STATS.where}, and a first pilot campaign in Germany. Next: adapt `
    + 'the ingestion and scoring to Umlaut CDRs, support the Active Tests community, so that the tool builds the KPI and '
    + 'Scoring reports they produce today, and take Non-Qualified Calls out of Alpha. Soon: scale out on AWS with an external '
    + 'worker queue, and durable analytical caches. Later: PostgreSQL instead of SQLite, a database for hundreds of '
    + 'concurrent users, Smart Orchestrator Logs, and health monitoring: alerts on runs that take too long and automatic '
    + 'checks after every deployment. These are intentions, not dated commitments.');
}

// ---------------------------------------------------------------------------------------------------------- one-slider
// The small road of the one-slider and its milestones (inches of the slide).
const MINI_ROAD = [[8.1, 6.42], [8.5, 6.36], [9.1, 6.46], [9.75, 6.42], [10.4, 6.34], [11.0, 6.4], [11.6, 6.48], [12.2, 6.4], [12.75, 6.36]];

// Everything on one slide, to tell the whole story on it: the data that comes in, the eight modules on the shared
// workspace, the teams they serve, the platform and the roadmap.
async function oneSlider(pres, files, masterName = 'SINGLE', sectionTitle = 'DriveTest Analyzer') {
  const slide = pres.addSlide({ masterName, sectionTitle });
  slide.addImage({ path: files.miniRoad, x: 0, y: 0, w: 13.333, h: 7.5, objectName: 'Small roadmap road' });
  heading(slide, 'DriveTest Analyzer — ', 'CDRs to decisions, in one platform',
    'Benchmarking, NQ Calls, troubleshooting and reporting for every team, on the same data', 28);
  const label = (value, x, y, w = 3) => text(slide, value, { x, y, w, h: 0.26, fontSize: 10.5, bold: true, color: K.grey, charSpacing: 1 });
  label('DATA IN', 0.6, 1.62);
  label('BUILT FOR EVERY TEAM', 9.75, 1.62);

  // The data that comes in, with the volumes of the workspaces of the figures.
  const hub = { x: 6.62, y: 3.72 };
  const datasets = [
    ['TbFileAnalytics', K.deep, 'CDRs', STATS.calls, `calls · ${STATS.cdrs} CDRs`],
    ['TbBuildingBroadcastTower', '0C9B5B', 'Network Inventories', STATS.inventory, 'cell rows'],
    ['TbArrowsShuffle', 'E07800', 'Vendor Mappings', STATS.mappings, 'mapping rows'],
    ['TbPolygon', '8C60A8', 'Geographical', '2 levels', 'Region & Cluster'],
  ];
  for (const [index, [name, color, title, value, unit]] of datasets.entries()) {
    const y = 1.95 + index * 0.92;
    lineBetween(slide, pres, 3.45, y + 0.4, 4.25, hub.y, { color: K.grey2, width: 1.25, endArrowType: 'triangle' });
    shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y, w: 2.85, h: 0.8, rectRadius: 0.1, fill: { color: K.tint }, line: { color: K.tint, width: 0 } });
    await badge(slide, pres, name, 0.75, y + 0.17, 0.46, color);
    text(slide, title, { x: 1.32, y: y + 0.08, w: 2.05, h: 0.3, fontSize: 12.5, bold: true });
    text(slide, [{ text: `${value} `, options: { fontSize: 14, bold: true, color: K.deep } }, { text: unit, options: { fontSize: 10, color: K.grey } }],
      { x: 1.32, y: y + 0.4, w: 2.05, h: 0.3, valign: 'middle' });
  }

  // The eight modules around the workspace, each with what it does.
  const modules = [
    ['cdr', 'KPIs per CDR'], ['dash', 'Template KPI decks'], ['scoring', 'Best Network · GAP'], ['ni', 'RSRP · SINR · 5G'],
    ['nq', `${STATS.nq} NQ calls`], ['reporting', 'PPT · Word · email'], ['builders', 'Charts · SQL'], ['tickets', 'Bugs & requests'],
  ];
  // (Turned a half step, no module sits at the ends of the ring: the label of each one goes outside it.)
  const rx = 2.35; const ry = 1.4;
  const nodes = modules.map(([key, detail], index) => {
    const angle = (-112.5 + index * 45) * Math.PI / 180;
    return { key, detail, x: hub.x + rx * Math.cos(angle), y: hub.y + ry * Math.sin(angle) };
  });
  shape(slide, pres.shapes.OVAL, { x: hub.x - rx, y: hub.y - ry, w: 2 * rx, h: 2 * ry, fill: { color: 'F7FAFD' }, line: { color: K.line, width: 1, dashType: 'dash' } });
  for (const node of nodes) lineBetween(slide, pres, hub.x, hub.y, node.x, node.y, { color: K.line, width: 1.25 });
  shape(slide, pres.shapes.OVAL, { x: hub.x - 0.63, y: hub.y - 0.63, w: 1.26, h: 1.26, fill: { color: K.black }, line: { color: K.black, width: 0 } });
  text(slide, [
    { text: 'Workspace', options: { fontSize: 12.5, bold: true, color: K.white, breakLine: true } },
    { text: '8 modules', options: { fontSize: 10, color: K.grey2, breakLine: true } },
    { text: plural(FIGURES.campaigns, 'campaign'), options: { fontSize: 10, color: K.grey2 } },
  ], { x: hub.x - 0.6, y: hub.y - 0.45, w: 1.2, h: 0.9, align: 'center', valign: 'middle' });
  for (const node of nodes) {
    const module = M[node.key];
    await badge(slide, pres, module.icon, node.x - 0.3, node.y - 0.3, 0.6, module.color, module.iconColor || K.white);
    // Above the modules of the upper half, below those of the lower half.
    const above = node.y < hub.y;
    text(slide, [
      { text: module.short, options: { fontSize: 10.5, bold: true, breakLine: true } },
      { text: node.detail, options: { fontSize: 10, color: K.grey } },
    ], { x: node.x - 0.8, y: above ? node.y - 0.76 : node.y + 0.32, w: 1.6, h: 0.44, align: 'center', valign: above ? 'bottom' : 'top' });
  }

  // The teams the modules serve.
  const teams = [
    ['TbScale', 'Benchmarking', 'Scores & GAP to the reference, city by city'],
    ['TbPhoneX', 'NQ Calls', 'Every failed call root-caused and closed'],
    ['TbStethoscope', 'Troubleshooting', 'Coverage, interference & serving cells'],
    ['TbBriefcase', 'Technical & executive', 'PowerPoint & Word in seven themes, scheduled'],
  ];
  for (const [index, [name, title, desc]] of teams.entries()) {
    const y = 1.95 + index * 0.92;
    lineBetween(slide, pres, 8.99, hub.y, 9.72, y + 0.4, { color: K.grey2, width: 1.25, endArrowType: 'triangle' });
    await badge(slide, pres, name, 9.78, y + 0.14, 0.5, K.ink);
    text(slide, title, { x: 10.4, y: y + 0.06, w: 2.35, h: 0.3, fontSize: 12.5, bold: true });
    text(slide, desc, { x: 10.4, y: y + 0.36, w: 2.35, h: 0.42, fontSize: 10, color: K.grey, valign: 'top' });
  }

  // The platform, in two rows of chips.
  label('ENTERPRISE PLATFORM', 0.6, 5.72);
  const chips = [['TbBrandAws', 'AWS · Docker'], ['TbUserShield', `4 roles · ${STATS.users} users`], ['TbAdjustmentsHorizontal', 'Modules Profiles'],
    ['TbFolders', 'Isolated workspaces'], ['TbDatabaseExport', 'Automated backups'], ['TbTicket', 'Ticket Center'],
    ['TbBook2', `${STATS.chapters}-chapter Help`], ['TbTestPipe', `${STATS.tests} tests`]];
  for (const [index, [name, value]] of chips.entries()) {
    const x = 0.6 + (index % 4) * 1.86; const y = 6.02 + Math.floor(index / 4) * 0.45;
    shape(slide, pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 1.76, h: 0.38, rectRadius: 0.1, fill: { color: K.white }, line: { color: K.line, width: 1 } });
    slide.addImage({ data: await icon(name, K.deep), x: x + 0.1, y: y + 0.08, w: 0.22, h: 0.22, objectName: named('icon') });
    text(slide, value, { x: x + 0.38, y, w: 1.35, h: 0.38, fontSize: 10, bold: true, valign: 'middle' });
  }

  // The roadmap on its small road: each milestone with its phase above and what it brings below.
  label('ROADMAP', 8.15, 5.72);
  const milestones = [
    { x: 8.5, y: 6.36, color: '0C9B5B', phase: 'TODAY', pin: 'TbCircleCheck', text: '8 modules live' },
    { x: 9.75, y: 6.42, color: K.blue, phase: 'NEXT', pin: 'TbRocket', text: 'Umlaut CDRs, Active Tests' },
    { x: 11.0, y: 6.4, color: '8C60A8', phase: 'SOON', pin: 'TbArrowsMaximize', text: 'AWS scale-out, speed' },
    { x: 12.2, y: 6.4, color: 'E07800', phase: 'LATER', pin: 'TbClock', text: 'PostgreSQL, health' },
  ];
  for (const milestone of milestones) {
    text(slide, milestone.phase, { x: milestone.x - 0.6, y: 6.0, w: 1.2, h: 0.2, fontSize: 9.5, bold: true, color: milestone.color, align: 'center', charSpacing: 1 });
    shape(slide, pres.shapes.OVAL, { x: milestone.x - 0.2, y: milestone.y - 0.2, w: 0.4, h: 0.4, fill: { color: K.white }, line: { color: K.white, width: 0 } });
    await badge(slide, pres, milestone.pin, milestone.x - 0.16, milestone.y - 0.16, 0.32, milestone.color);
    text(slide, milestone.text, { x: milestone.x - 0.6, y: 6.66, w: 1.2, h: 0.4, fontSize: 10, bold: true, align: 'center', valign: 'top' });
  }
  slide.addNotes(`DriveTest Analyzer in one slide. Data in: CDRs (${STATS.calls} Data and Voice calls in ${STATS.cdrs} CDRs of `
    + `${plural(FIGURES.campaigns, 'campaign')} of ${STATS.where}), network inventories, vendor mappings and regions and clusters. `
    + 'On one shared workspace, eight modules: CDR Analysis, PPT Dashboards, Scoring & GAP Analysis, Network Insights, '
    + `Non-Qualified Calls (${STATS.nqExact} NQ calls), Reporting, the Builders and the Ticket Center. They serve `
    + 'benchmarking, the NQ team, troubleshooting and technical and executive reporting, on an enterprise platform on AWS with '
    + `roles, isolated workspaces, automated backups, a Ticket Center, a ${STATS.chapters}-chapter Help and ${STATS.tests} `
    + 'automated tests. Roadmap: Umlaut CDRs and the Active Tests community next, then scale-out on AWS and speed, then '
    + 'PostgreSQL for hundreds of concurrent users and health monitoring.');
}

// The colours and fonts of the theme of a written deck (pptxgenjs writes Office's own).
async function applyTheme(file, theme) {
  const zip = await JSZip.loadAsync(fs.readFileSync(file));
  for (const name of Object.keys(zip.files).filter((entry) => /^ppt\/theme\/theme\d+\.xml$/.test(entry))) {
    let xml = await zip.file(name).async('string');
    for (const [key, value] of Object.entries(theme.colors)) {
      xml = xml.replace(new RegExp(`<a:${key}>[\\s\\S]*?</a:${key}>`), `<a:${key}><a:srgbClr val="${value}"/></a:${key}>`);
    }
    xml = xml.replace(/(<a:clrScheme name=")[^"]*"/, `$1${theme.name}"`)
      .replace(/(<a:majorFont>\s*<a:latin typeface=")[^"]*"/, `$1${theme.headFontFace}"`)
      .replace(/(<a:minorFont>\s*<a:latin typeface=")[^"]*"/, `$1${theme.bodyFontFace}"`);
    zip.file(name, xml);
  }
  fs.writeFileSync(file, await zip.generateAsync({ type: 'nodebuffer', compression: 'DEFLATE' }));
}

// ------------------------------------------------------------------------------------- benchmarking providers deck
// The adaptation of the tool to the CDRs of benchmarking providers other than NetCheck (Umlaut first, then P3), in the
// design of its own deck: benchmarking-providers/ holds a picture of each slide, with the Ericsson logo at the top right,
// and slides.json their order, section, title and speaker notes.
const PROVIDERS_DECK = path.join(__dirname, 'benchmarking-providers');
const PROVIDERS_SLIDES = JSON.parse(fs.readFileSync(path.join(PROVIDERS_DECK, 'slides.json'), 'utf8'));

function providersSections() {
  const sections = [];
  for (const slide of PROVIDERS_SLIDES.slides) {
    if (sections.at(-1)?.title !== slide.section) sections.push({ title: slide.section, slides: [] });
    sections.at(-1).slides.push(slide.title);
  }
  return sections;
}

function providersDeck(pres) {
  let section;
  for (const slide of PROVIDERS_SLIDES.slides) {
    if (slide.section !== section) { pres.addSection({ title: slide.section }); section = slide.section; }
    const page = pres.addSlide({ sectionTitle: slide.section });
    page.addImage({ path: path.join(PROVIDERS_DECK, slide.image), x: 0, y: 0, w: '100%', h: '100%', objectName: slide.title });
    if (slide.notes) page.addNotes(slide.notes);
  }
}

// The presentations as the Help lists them (static/presentations/presentations.json): their file and the title of each
// slide by section, which the slide viewer shows on its left.
const PRESENTATIONS = [
  { id: 'overview', title: 'DriveTest Analyzer — Overview', file: 'overview.pptx', download: 'DriveTest Analyzer - Overview.pptx',
    description: 'The tool, the teams it serves and its platform, a slide per module in the order of the tool and its roadmap, closing with the one-slider.',
    sections: [
      { title: 'Introduction', slides: ['DriveTest Analyzer', 'One platform, from CDRs to decisions'] },
      { title: 'Teams', slides: ['Built for every team'] },
      { title: 'Platform', slides: ['Enterprise-ready'] },
      { title: 'Modules', slides: ['Eight modules, one shared workspace', 'CDR Analysis', 'PPT Dashboards', 'Scoring & GAP Analysis — who wins',
        'Scoring & GAP Analysis — where to win the points back', 'Network Insights', 'NQ Calls', 'Reporting', 'Builders', 'Ticket Center'] },
      { title: 'Roadmap', slides: ['Roadmap'] },
      { title: 'In one slide', slides: ['DriveTest Analyzer in one slide'] },
    ] },
  { id: 'one-slider', title: 'DriveTest Analyzer — One-slider', file: 'one-slider.pptx', download: 'DriveTest Analyzer - One-slider.pptx',
    description: 'The most important of the tool in a single slide: figures, modules, teams, platform and what comes next.',
    sections: [{ title: 'In one slide', slides: ['DriveTest Analyzer in one slide'] }] },
  { id: 'roadmap', title: 'DriveTest Analyzer — Roadmap', file: 'roadmap.pptx', download: 'DriveTest Analyzer - Roadmap.pptx',
    description: 'What comes next: Umlaut CDRs, the Active Tests community, scale-out and speed on AWS, PostgreSQL and health monitoring.',
    sections: [{ title: 'Roadmap', slides: ['Roadmap — what comes next'] }] },
  { id: 'benchmarking-providers', title: PROVIDERS_SLIDES.title, file: 'benchmarking-providers.pptx',
    download: 'DriveTest Analyzer - Benchmarking Providers Roadmap.pptx',
    description: 'How the tool is being adapted to Umlaut and P3 CDRs and the status of each phase, how it is built inside and how it is deployed in the cloud.',
    sections: providersSections() },
];

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const work = fs.mkdtempSync(path.join(os.tmpdir(), 'drivetest-presentations-'));
  const files = {
    cover: path.join(work, 'cover-art.png'), map: path.join(work, 'ni-map.png'), road: path.join(work, 'roadmap-road.png'), miniRoad: path.join(work, 'mini-road.png'),
    lossMap: path.join(work, 'points-lost-map.png'), cdf: path.join(work, 'cdf-curves.png'),
    logoWhite: path.join(ROOT, 'src', 'web_interface', 'static', 'img', 'ericsson-logo-white.png'), logoBlack: path.join(work, 'ericsson-logo-black.png'),
  };
  await art.coverArt(files.cover); await art.coverageMap(files.map); await art.roadmapRoad(files.road, ROAD);
  await art.roadmapRoad(files.miniRoad, MINI_ROAD, { scale: 0.42, glow: false, flag: false });
  await art.pointsLostMap(files.lossMap);
  await art.cdfCurves(files.cdf, [{ color: OPERATORS[0].color, median: 120, spread: 26 }, { color: OPERATORS[1].color, median: 95, spread: 24 },
    { color: OPERATORS[2].color, median: 70, spread: 22 }]);
  // The black logo of the light slides, from the white one.
  await sharp(files.logoWhite).negate({ alpha: false }).toFile(files.logoBlack);
  const logos = { white: files.logoWhite, black: files.logoBlack };

  const deck = new pptxgen();
  deck.author = 'DriveTest Analyzer'; deck.title = 'DriveTest Analyzer — Overview'; deck.subject = 'DriveTest Analyzer overview';
  defineLayouts(deck, logos);
  deck.addSection({ title: 'Introduction' });
  await cover(deck, files);
  await platform(deck);
  deck.addSection({ title: 'Teams' });
  await teams(deck);
  deck.addSection({ title: 'Platform' });
  await enterprise(deck);
  deck.addSection({ title: 'Modules' });
  await modules(deck);
  await cdrAnalysis(deck, files);
  await dashboards(deck);
  await scoring(deck);
  await scoringActions(deck, files);
  await networkInsights(deck, files);
  await nqCalls(deck);
  await reporting(deck);
  await builders(deck);
  await ticketCenter(deck);
  deck.addSection({ title: 'Roadmap' });
  await roadmap(deck, files);
  deck.addSection({ title: 'In one slide' });
  await oneSlider(deck, files, 'CONTENT', 'In one slide');
  const deckFile = path.join(OUT, 'overview.pptx');
  await deck.writeFile({ fileName: deckFile });
  await applyTheme(deckFile, THEME);

  const single = new pptxgen();
  single.author = 'DriveTest Analyzer'; single.title = 'DriveTest Analyzer — One-slider'; single.subject = 'DriveTest Analyzer at a glance';
  defineLayouts(single, logos);
  single.addSection({ title: 'DriveTest Analyzer' });
  await oneSlider(single, files);
  const singleFile = path.join(OUT, 'one-slider.pptx');
  await single.writeFile({ fileName: singleFile });
  await applyTheme(singleFile, THEME);

  const plan = new pptxgen();
  plan.author = 'DriveTest Analyzer'; plan.title = 'DriveTest Analyzer — Roadmap'; plan.subject = 'DriveTest Analyzer roadmap';
  defineLayouts(plan, logos);
  plan.addSection({ title: 'Roadmap' });
  await roadmap(plan, files, 'SINGLE');
  const planFile = path.join(OUT, 'roadmap.pptx');
  await plan.writeFile({ fileName: planFile });
  await applyTheme(planFile, THEME);

  const providers = new pptxgen();
  providers.author = 'DriveTest Analyzer'; providers.title = PROVIDERS_SLIDES.title;
  providers.subject = 'Adaptation of DriveTest Analyzer to other benchmarking providers';
  providers.layout = 'LAYOUT_WIDE';
  providersDeck(providers);
  const providersFile = path.join(OUT, 'benchmarking-providers.pptx');
  await providers.writeFile({ fileName: providersFile });
  await applyTheme(providersFile, THEME);
  fs.writeFileSync(path.join(OUT, 'presentations.json'), `${JSON.stringify({ presentations: PRESENTATIONS, figures: FIGURES }, null, 2)}\n`);
  fs.rmSync(work, { recursive: true, force: true });
  console.log(deckFile); console.log(singleFile); console.log(planFile); console.log(providersFile);
}

main().catch((error) => { console.error(error); process.exit(1); });
