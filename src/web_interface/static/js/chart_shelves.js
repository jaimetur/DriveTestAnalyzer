/* The chart builder of the Designer (ticket #26, phase 2): the data pane, shelves and Chart Type of a chart.

   A chart is built Tableau-like: the fields of its source (dimensions and measures told apart, grouped by the sections of
   the CDR Field Dictionary) are dragged to its shelves — Measure, Rows, Columns, Legend, Filters and One chart per — and Chart Type
   offers the chart types the shelves can draw, the others greyed with the reason. Each change gives the values of the
   chart as its template row writes them (KPI, Rows Split, Columns Split, Legend, Filters, Chart type, Dynamic Rows/Columns
   Field), so the same engine and renderer draw it. Used by the Designer (designer.js) and by Chart Builder. */
(() => {
  'use strict';
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
  const identity = value => String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, '');

  // The CDRs a chart reads and the NR Mode of those CDRs, with what each choice means.
  const SOURCES = [['CDR-Data', 'Data', 'The CDRs of the data tests'], ['CDR-Voice', 'Voice', 'The CDRs of the voice calls'],
    ['CDR-Speech', 'Speech', 'The CDRs of the speech quality tests'], ['CDR-All', 'RF All', 'The CDRs of every test (Data, Voice and Speech together), for their radio fields']];
  const NR_MODES = [['NSA', 'NSA', 'Only the CDRs of the NSA campaigns'], ['SA', 'SA', 'Only the CDRs of the SA campaigns']];
  // The settings a chart type keeps among its Filters, shown with Chart Type instead of as filters.
  const SETTINGS = ['threshold', 'buckets', 'binsize', 'classcolours', 'histogramoperator', 'nrmode', 'whiskers', 'target', 'datebin', 'direction', 'sort'];
  const AGGREGATIONS = [['', 'As the chart type counts it'], ['AVG', 'Average'], ['MEDIAN', 'Median'], ['SUM', 'Sum'], ['COUNT', 'Count'], ['COUNTD', 'Count distinct'], ['MIN', 'Minimum'], ['MAX', 'Maximum']];
  // Chart Type: each chart type, a small picture of it (A, B and C are the colours of its series) and what its shelves
  // need.
  const A = 'var(--ds-cb-a)', B = 'var(--ds-cb-b)', C = 'var(--ds-cb-c)', G = 'var(--ds-cb-grid)';
  const curve = (colour, d) => `<path d="${d}" fill="none" stroke="${colour}" stroke-width="2.4" stroke-linecap="round"/>`;
  const bar = (colour, x, y, w, h) => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="1" fill="${colour}"/>`;
  const axes = `<path d="M5 4v26h38" fill="none" stroke="${G}" stroke-width="1.4"/>`;
  const PICTURES = {
    'CDF Line': axes + curve(A, 'M6 29C14 29 15 10 22 8S36 5 42 5') + curve(B, 'M6 29C18 29 20 16 26 13S38 9 42 9'),
    'Multi KPI CDF Lines': axes + curve(A, 'M6 29C12 29 13 9 20 7S36 5 42 5') + curve(B, 'M6 29C16 29 18 14 25 11S38 8 42 8') + curve(C, 'M6 29C20 29 24 20 30 17S40 13 42 13'),
    'Average Vertical Bars': axes + bar(A, 8, 14, 5, 16) + bar(B, 14, 9, 5, 21) + bar(A, 24, 17, 5, 13) + bar(B, 30, 11, 5, 19) + `<path d="M7 12h29" stroke="${C}" stroke-width="1.6" stroke-dasharray="3 2"/>`,
    'Median Vertical Bars': axes + bar(A, 8, 12, 5, 18) + bar(B, 14, 16, 5, 14) + bar(A, 24, 8, 5, 22) + bar(B, 30, 14, 5, 16) + `<path d="M7 18h6M14 21h5M24 15h5M30 20h5" stroke="#fff" stroke-width="1.6"/>`,
    '100% Stacked Vertical Bars': axes + [8, 17, 26, 35].map((x, i) => bar(A, x, 5, 6, 14 + i) + bar(B, x, 19 + i, 6, 6 - i) + bar(C, x, 25, 6, 5)).join(''),
    'Count Stacked Horizontal Bars': axes + bar(A, 6, 7, 18, 5) + bar(B, 24, 7, 8, 5) + bar(A, 6, 15, 26, 5) + bar(B, 32, 15, 6, 5) + bar(A, 6, 23, 12, 5) + bar(B, 18, 23, 10, 5),
    'Threshold Stacked Vertical Bars': axes + [8, 17, 26, 35].map((x, i) => bar(B, x, 6, 6, 6 + i * 2) + bar(A, x, 12 + i * 2, 6, 18 - i * 2)).join('') + `<path d="M6 16h37" stroke="${C}" stroke-width="1.6" stroke-dasharray="3 2"/>`,
    'Distribution Stacked Vertical Bars': axes + [8, 17, 26, 35].map((x, i) => bar(A, x, 5, 6, 6 + i) + bar(B, x, 11 + i, 6, 7) + bar(C, x, 18 + i, 6, 12 - i)).join(''),
    'Histogram Bars': axes + [[7, 24], [12, 17], [17, 9], [22, 6], [27, 10], [32, 18], [37, 25]].map(([x, y]) => bar(A, x, y, 4, 30 - y)).join(''),
    'Histogram Line': axes + curve(A, 'M6 29C12 28 14 8 22 7S30 26 42 28') + curve(B, 'M6 29C16 29 20 13 27 12S36 27 42 29'),
    'Scatter': axes + [[10, 24], [14, 19], [17, 22], [21, 15], [25, 17], [29, 11], [33, 13], [37, 7]].map(([x, y], i) => `<circle cx="${x}" cy="${y}" r="2" fill="${i % 2 ? B : A}"/>`).join(''),
    'Table': `<rect x="5" y="5" width="38" height="24" rx="2" fill="none" stroke="${G}" stroke-width="1.4"/>` + bar(A, 5, 5, 38, 6) + `<path d="M5 17h38M5 23h38M17 5v24M30 5v24" stroke="${G}" stroke-width="1.2"/>`,
    'Dynamic Table': `<rect x="5" y="5" width="38" height="24" rx="2" fill="none" stroke="${G}" stroke-width="1.4"/>` + bar(A, 5, 5, 38, 6) + bar(B, 18, 12, 11, 5) + bar(C, 30, 18, 12, 5) + bar(B, 6, 24, 11, 4) + `<path d="M5 17h38M5 23h38M17 5v24M30 5v24" stroke="${G}" stroke-width="1.2"/>`,
    // A scorecard: its figure, the change pill beside it and its trend over the campaigns.
    'KPI Card': `<rect x="5" y="4" width="38" height="26" rx="4" fill="none" stroke="${G}" stroke-width="1.4"/>` + bar(G, 10, 8, 13, 3)
      + bar(A, 10, 13, 17, 7) + `<rect x="30" y="14" width="9" height="5" rx="2.5" fill="${B}"/>`
      + `<path d="M10 26l6-2.5 5 1.5 6-3.5 5 1.5 6-3" fill="none" stroke="${C}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>`,
    'Map': `<path d="M5 9l11-4 15 4 12-4v20l-12 4-15-4-11 4z" fill="none" stroke="${G}" stroke-width="1.4"/>` + [[11, 17], [17, 24], [36, 20]].map(([x, y], i) => `<circle cx="${x}" cy="${y}" r="2.4" fill="${[A, B, A][i]}"/>`).join('') + `<path d="M26 24c0-3.5 4.5-6.5 4.5-10.5a4.5 4.5 0 0 0-9 0c0 4 4.5 7 4.5 10.5z" fill="${C}"/><circle cx="26" cy="13.5" r="1.7" fill="#fff"/>`,
    // The chart types after Tableau's Show Me (ticket #46).
    'Horizontal Bars': `<path d="M7 3v28" stroke="${G}" stroke-width="1.4"/>` + [[5, 32, A], [12, 24, B], [19, 36, A], [26, 18, B]].map(([y, w, c]) => bar(c, 7, y, w, 5)).join(''),
    'Dot Plot': [8, 17, 26].map((y, i) => `<path d="M8 ${y}h34" stroke="${G}" stroke-width="1"/><path d="M${14 + i * 4} ${y}h${12 - i * 2}" stroke="${G}" stroke-width="2.2"/><circle cx="${14 + i * 4}" cy="${y}" r="2.6" fill="${A}"/><circle cx="${26 + i * 2}" cy="${y}" r="2.6" fill="${B}"/>`).join(''),
    'Bullet Graph': [7, 20].map((y, i) => `<rect x="6" y="${y}" width="36" height="8" fill="${G}" opacity=".35"/><rect x="6" y="${y}" width="22" height="8" fill="${G}" opacity=".45"/>` + bar(i ? B : A, 6, y + 2.5, i ? 30 : 25, 3) + `<path d="M${i ? 27 : 31} ${y}v8" stroke="${C}" stroke-width="2"/>`).join(''),
    'Highlight Table': `<rect x="5" y="5" width="38" height="24" rx="2" fill="none" stroke="${G}" stroke-width="1.4"/>` + bar(G, 5, 5, 38, 6) + [[17, 11, A, .25], [30, 11, B, .35], [17, 17, B, .5], [30, 17, A, .6], [17, 23, A, .4], [30, 23, B, .2]].map(([x, y, c, o]) => `<rect x="${x}" y="${y}" width="13" height="6" fill="${c}" opacity="${o}"/>`).join('') + `<path d="M5 17h38M5 23h38M17 5v24M30 5v24" stroke="${G}" stroke-width="1"/>`,
    'Bar Table': `<rect x="5" y="5" width="38" height="24" rx="2" fill="none" stroke="${G}" stroke-width="1.4"/>` + bar(G, 5, 5, 38, 6) + [[18, 12, 9], [31, 12, 6], [18, 18, 5], [31, 18, 10], [18, 24, 11], [31, 24, 4]].map(([x, y, w]) => bar(A, x, y, w, 4)).join('') + `<path d="M17 5v24M30 5v24" stroke="${G}" stroke-width="1"/>`,
    'Heat Map': [[8, 6, 7, A], [20, 6, 5, B], [32, 6, 8, C], [8, 17, 4, B], [20, 17, 8, A], [32, 17, 6, A], [8, 27, 6, C], [20, 27, 3, B], [32, 27, 7, B]].map(([x, y, s, c]) => `<rect x="${x + (9 - s) / 2}" y="${y - 3 + (9 - s) / 2}" width="${s}" height="${s}" fill="${c}"/>`).join(''),
    'Pie': `<path d="M24 17V4a13 13 0 0 1 12.4 17z" fill="${A}"/><path d="M24 17l12.4 4A13 13 0 0 1 14 25.4z" fill="${B}"/><path d="M24 17L14 25.4A13 13 0 0 1 24 4z" fill="${C}"/>`,
    'Donut': `<circle cx="24" cy="17" r="10" fill="none" stroke="${A}" stroke-width="6" stroke-dasharray="28 63" transform="rotate(-90 24 17)"/><circle cx="24" cy="17" r="10" fill="none" stroke="${B}" stroke-width="6" stroke-dasharray="20 63" stroke-dashoffset="-28" transform="rotate(-90 24 17)"/><circle cx="24" cy="17" r="10" fill="none" stroke="${C}" stroke-width="6" stroke-dasharray="15 63" stroke-dashoffset="-48" transform="rotate(-90 24 17)"/>`,
    'Lines': axes + `<path d="M8 22l8-6 8 3 8-9 9 2" fill="none" stroke="${A}" stroke-width="2.2" stroke-linejoin="round"/><path d="M8 27l8-3 8-6 8 2 9-6" fill="none" stroke="${B}" stroke-width="2.2" stroke-linejoin="round"/>` + [[8, 22], [16, 16], [24, 19], [32, 10], [41, 12]].map(([x, y]) => `<circle cx="${x}" cy="${y}" r="1.6" fill="${A}"/>`).join(''),
    'Dual Lines': `<path d="M5 4v26h38V4" fill="none" stroke="${G}" stroke-width="1.4"/><path d="M9 22l8-8 8 4 8-9 7 3" fill="none" stroke="${A}" stroke-width="2.2" stroke-linejoin="round"/><path d="M9 12l8 7 8-2 8 8 7-6" fill="none" stroke="${B}" stroke-width="2.2" stroke-dasharray="3 2"/>`,
    'Areas': axes + `<path d="M6 30V20l9-4 9 3 9-8 9 2v17z" fill="${A}"/><path d="M6 30v-4l9-2 9 1 9-5 9 1v9z" fill="${B}"/>`,
    '100% Stacked Areas': axes + `<path d="M6 30V5h36v25z" fill="${C}"/><path d="M6 30V14l9 2 9-4 9 3 9-2v17z" fill="${A}"/><path d="M6 30v-7l9 1 9-3 9 2 9-1v8z" fill="${B}"/>`,
    'Bars and Line': axes + [[9, 14], [18, 10], [27, 18], [36, 12]].map(([x, y]) => bar(A, x, y, 6, 30 - y)).join('') + `<path d="M12 20l9-12 9 6 9-8" fill="none" stroke="${C}" stroke-width="2.2" stroke-linejoin="round"/>` + [[12, 20], [21, 8], [30, 14], [39, 6]].map(([x, y]) => `<circle cx="${x}" cy="${y}" r="1.8" fill="#fff" stroke="${C}" stroke-width="1.4"/>`).join(''),
    'Box Plot': axes + [[12, 7, 12, 19, 27, A], [24, 5, 9, 15, 22, B], [36, 9, 14, 21, 28, A]].map(([x, top, q3, q1, low, c]) => `<path d="M${x} ${top}v${q3 - top}M${x} ${q1}v${low - q1}M${x - 2} ${top}h4M${x - 2} ${low}h4" stroke="${G}" stroke-width="1.2"/><rect x="${x - 4}" y="${q3}" width="8" height="${q1 - q3}" fill="${c}" opacity=".55" stroke="${c}"/><path d="M${x - 4} ${(q3 + q1) / 2}h8" stroke="${C}" stroke-width="1.6"/>`).join(''),
    'Symbol Map': `<path d="M5 9l11-4 15 4 12-4v20l-12 4-15-4-11 4z" fill="none" stroke="${G}" stroke-width="1.4"/>` + [[13, 15, 5, A], [27, 20, 3, B], [35, 12, 4, A], [19, 25, 2, B]].map(([x, y, r, c]) => `<circle cx="${x}" cy="${y}" r="${r}" fill="${c}" opacity=".75"/>`).join(''),
    'Filled Map': `<path d="M6 8l10-3 4 6-3 7-11 2z" fill="${A}"/><path d="M20 11l-4-6 13 1 3 9-9 3z" fill="${B}"/><path d="M17 18l6 0 9-3 10 4-4 9-13 2-9-5z" fill="${C}"/><path d="M6 20l11-2 3 7-12 3z" fill="${A}" opacity=".55"/>`,
    'Treemap': bar(A, 5, 4, 20, 16) + bar(A, 5, 21, 20, 9) + bar(B, 26, 4, 17, 11) + bar(B, 26, 16, 9, 14) + bar(C, 36, 16, 7, 14),
    'Packed Bubbles': [[17, 15, 9, A], [31, 12, 6, B], [31, 25, 5, C], [20, 27, 3.5, B], [40, 21, 3, A]].map(([x, y, r, c]) => `<circle cx="${x}" cy="${y}" r="${r}" fill="${c}"/>`).join(''),
    'Sankey': bar(A, 5, 4, 4, 12) + bar(B, 5, 18, 4, 12) + bar(C, 39, 4, 4, 16) + bar(G, 39, 22, 4, 8) + `<path d="M9 4C24 4 24 4 39 4v10C24 14 24 10 9 10z" fill="${A}" opacity=".45"/><path d="M9 10C24 10 24 22 39 22v8C24 30 24 16 9 16z" fill="${A}" opacity=".3"/><path d="M9 18C24 18 24 14 39 14v6C24 20 24 30 9 30z" fill="${B}" opacity=".4"/>`,
    'Gantt': `<path d="M5 4v26h38" fill="none" stroke="${G}" stroke-width="1.4"/>` + [[8, 6, 14, A], [24, 6, 12, A], [12, 14, 22, B], [9, 22, 9, C], [22, 22, 18, C]].map(([x, y, w, c]) => bar(c, x, y, w, 5)).join(''),
  };
  // The settings beside a chart type (kept among its filters as `Name = value`): free text, or one of its choices.
  const BUCKETS = {name: 'Buckets', placeholder: '4 limits: -110, -100, -90, -80'};
  const DIRECTION = {name: 'Direction', title: 'Which values the colours show as good', choices: [['', 'From the KPI'], ['Higher is better', 'Higher is better'], ['Lower is better', 'Lower is better'], ['Neutral', 'Neutral (blues)']]};
  const SORT = {name: 'Sort', title: 'The order of the rows', choices: [['', 'As the Rows'], ['Descending', 'Largest first'], ['Ascending', 'Smallest first']]};
  const TARGET = {name: 'Target', placeholder: '20, Previous campaign or Best competitor', title: 'The mark each bar is measured against (a second measure gives it too)'};
  const WHISKERS = {name: 'Whiskers', title: 'Where the whiskers reach', choices: [['', 'P10 – P90'], ['P5-P95', 'P5 – P95'], ['P25-P75', 'P25 – P75'], ['Min-Max', 'Min – Max'], ['1.5 IQR', '1.5 × IQR']]};
  const DATE_BIN = {name: 'Date Bin', title: 'The periods a bar joins', choices: [['', 'Day'], ['Hour', 'Hour'], ['Week', 'Week'], ['Month', 'Month']]};
  // need: true when the shelves draw it, else what it needs; fits: the measures do not rule it out (more fields can still
  // make it drawable), so a chart type chosen before its fields is kept while they are dropped.
  const TYPES = [
    {type: 'CDF Line', need: s => s.numeric === 1 && s.measures === 1 || 'One numeric measure', fits: s => !s.text && s.numeric <= 1},
    {type: 'Multi KPI CDF Lines', need: s => s.numeric >= 2 && s.numeric === s.measures || 'Two numeric measures or more', fits: s => !s.text},
    {type: 'Average Vertical Bars', need: s => s.numeric >= 1 && s.splits >= 1 || 'A numeric measure and a Rows or Columns split', fits: s => !s.text},
    {type: 'Median Vertical Bars', need: s => s.numeric >= 1 && s.splits >= 1 || 'A numeric measure and a Rows or Columns split', fits: s => !s.text},
    {type: '100% Stacked Vertical Bars', need: s => s.text === 1 && s.measures === 1 || 'One dimension as the measure (such as Call_Status)', fits: s => !s.numeric && s.text <= 1},
    {type: 'Count Stacked Horizontal Bars', need: s => s.measures === 1 || 'One measure', fits: s => s.measures <= 1},
    {type: 'Threshold Stacked Vertical Bars', need: s => s.numeric === 1 && s.measures === 1 || 'One numeric measure', settings: [{name: 'Threshold', placeholder: '1.6 or {Threshold}'}], fits: s => !s.text && s.numeric <= 1},
    {type: 'Distribution Stacked Vertical Bars', need: s => s.numeric === 1 && s.measures === 1 || 'One numeric measure', settings: [{name: 'Buckets', placeholder: '1, 5, 10, 20'}], fits: s => !s.text && s.numeric <= 1},
    {type: 'Histogram Bars', need: s => s.numeric === 1 && s.measures === 1 || 'One numeric measure', settings: [{name: 'Bin Size', placeholder: '1'}], fits: s => !s.text && s.numeric <= 1},
    {type: 'Histogram Line', need: s => s.numeric === 1 && s.measures === 1 || 'One numeric measure', settings: [{name: 'Bin Size', placeholder: '1'}], fits: s => !s.text && s.numeric <= 1},
    {type: 'Scatter', need: s => s.numeric === 2 && s.measures === 2 || 'Two numeric measures', fits: s => !s.text && s.numeric <= 2},
    {type: 'Table', need: s => s.measures >= 1 || 'A measure', fits: () => true},
    {type: 'Dynamic Table', need: s => s.measures >= 1 || 'A measure', fits: () => true},
    // (A Map reads its latitude and longitude on Measure; a third measure colours its points.)
    {type: 'Map', need: s => s.geo && s.numeric >= 2 && s.measures <= 3 || 'A latitude and a longitude on Measure', fits: s => s.measures <= 3},
    {type: 'KPI Card', need: s => s.measures === 1 || 'One measure: the field of the card', fits: s => s.measures <= 1},
    {type: 'Horizontal Bars', need: s => s.measures === 1 && s.rows >= 1 || 'A measure and a Rows split (the bars)', fits: s => s.measures <= 1, settings: [SORT]},
    {type: 'Dot Plot', need: s => s.numeric === 1 && s.measures === 1 && s.rows >= 1 || 'A numeric measure and a Rows split (a dot per Columns value)', fits: s => !s.text && s.numeric <= 1},
    {type: 'Bullet Graph', need: s => s.numeric >= 1 && s.numeric === s.measures && s.measures <= 2 && s.splits >= 1 || 'A numeric measure (a second one is its target) and a Rows or Columns split', fits: s => !s.text && s.numeric <= 2, settings: [TARGET, BUCKETS, DIRECTION]},
    {type: 'Highlight Table', need: s => s.measures === 1 && s.splits >= 1 || 'A measure and a Rows or Columns split', fits: s => s.measures <= 1, settings: [DIRECTION, BUCKETS]},
    {type: 'Bar Table', need: s => s.measures === 1 && s.splits >= 1 || 'A measure and a Rows or Columns split', fits: s => s.measures <= 1},
    {type: 'Heat Map', need: s => s.numeric >= 1 && s.numeric === s.measures && s.measures <= 2 && s.rows >= 1 && s.columns >= 1 || 'A numeric measure (a second one sizes the squares), a Rows and a Columns split', fits: s => !s.text && s.numeric <= 2, settings: [DIRECTION, BUCKETS]},
    {type: 'Pie', need: s => s.measures === 1 && (s.text === 1 || s.columns >= 1) || 'A dimension as the measure (its values are the slices), or a measure and a Columns split', fits: s => s.measures <= 1},
    {type: 'Donut', need: s => s.measures === 1 && (s.text === 1 || s.columns >= 1) || 'A dimension as the measure (its values are the slices), or a measure and a Columns split', fits: s => s.measures <= 1},
    {type: 'Lines', need: s => s.numeric === 1 && s.measures === 1 && s.columns >= 1 || 'A numeric measure and a Columns split (the horizontal axis: Campaign, or a date by Day…)', fits: s => !s.text && s.numeric <= 1},
    {type: 'Dual Lines', need: s => s.numeric === 2 && s.measures === 2 && s.columns >= 1 || 'Two numeric measures and a Columns split (the horizontal axis)', fits: s => !s.text && s.numeric <= 2},
    {type: 'Areas', need: s => s.measures === 1 && s.columns >= 1 || 'A measure and a Columns split (the horizontal axis)', fits: s => s.measures <= 1},
    {type: '100% Stacked Areas', need: s => s.measures === 1 && s.columns >= 1 || 'A measure and a Columns split (the horizontal axis)', fits: s => s.measures <= 1},
    {type: 'Bars and Line', need: s => s.measures === 2 && s.columns >= 1 || 'Two measures (the bars, then the line) and a Columns split', fits: s => s.measures <= 2},
    {type: 'Box Plot', need: s => s.numeric === 1 && s.measures === 1 || 'One numeric measure', fits: s => !s.text && s.numeric <= 1, settings: [WHISKERS]},
    {type: 'Symbol Map', need: s => s.geo && s.numeric >= 2 && s.measures <= 3 || 'A latitude and a longitude on Measure (a third measure colours the circles)', fits: s => s.measures <= 3, settings: [BUCKETS, DIRECTION]},
    {type: 'Filled Map', need: s => s.numeric === 1 && s.measures === 1 || 'One numeric measure: the Map Areas of the CDRs are coloured by it', fits: s => !s.text && s.numeric <= 1, settings: [BUCKETS, DIRECTION]},
    {type: 'Treemap', need: s => s.measures >= 1 && s.measures <= 2 && s.splits >= 1 || 'A measure (a second one colours it) and a Rows or Columns split', fits: s => s.measures <= 2, settings: [BUCKETS, DIRECTION]},
    {type: 'Packed Bubbles', need: s => s.measures >= 1 && s.measures <= 2 && s.splits >= 1 || 'A measure (a second one colours it) and a Rows or Columns split', fits: s => s.measures <= 2, settings: [BUCKETS, DIRECTION]},
    {type: 'Sankey', need: s => s.measures === 1 && s.splits >= 2 && s.splits <= 5 || 'A measure and two to five fields on Rows and Columns (its levels)', fits: s => s.measures <= 1},
    {type: 'Gantt', need: s => s.measures >= 1 && s.measures <= 2 && s.times === s.measures && s.rows >= 1 || 'A time on Measure (a second one is its end) and a Rows split', fits: s => s.measures <= 2, settings: [DATE_BIN]},
  ];
  // What a chart type needs, said for a chart without fields (first letter lower case, the names of fields kept).
  const requirement = item => String(item.need({measures: 0, numeric: 0, text: 0, splits: 0, rows: 0, columns: 0, times: 0, geo: false}));
  const lower = text => String(text).charAt(0).toLowerCase() + String(text).slice(1);
  // Chart Type of the Designer: the chart types grouped by what they show.
  const TYPE_GROUPS = [
    ['Distribution', ['CDF Line', 'Multi KPI CDF Lines', 'Histogram Bars', 'Histogram Line', 'Box Plot', 'Dot Plot']],
    ['Comparison', ['Average Vertical Bars', 'Median Vertical Bars', 'Horizontal Bars', 'Bullet Graph', 'Scatter']],
    ['Trends', ['Lines', 'Dual Lines', 'Areas', '100% Stacked Areas', 'Bars and Line', 'Gantt']],
    ['Composition', ['100% Stacked Vertical Bars', 'Count Stacked Horizontal Bars', 'Threshold Stacked Vertical Bars', 'Distribution Stacked Vertical Bars', 'Pie', 'Donut']],
    ['Hierarchies and flows', ['Treemap', 'Packed Bubbles', 'Sankey']],
    ['Tables', ['Table', 'Dynamic Table', 'Highlight Table', 'Bar Table', 'Heat Map']],
    ['Maps', ['Map', 'Symbol Map', 'Filled Map']],
    ['Scorecards', ['KPI Card']],
  ];
  const SHELVES = [
    ['kpi', 'Measure', 'The KPI the chart measures (several for Multi KPI CDF Lines, Scatter or a Table)'],
    ['rows_split', 'Rows', 'Categories or table rows, in order (Operator × Campaign)'],
    ['columns_split', 'Columns', 'Series or table columns, in order'],
    ['legend', 'Legend', 'The fields the legend explains'],
    ['filters', 'Filters', 'Conditions on the rows of the chart'],
    ['repeat', 'One chart per', 'One chart for each value of a field, side by side in the place of this one: drop City for a chart of each city'],
  ];

  // An SVG picture (SVG elements need their own namespace, which innerHTML of an <svg> gives them).
  const picture = type => {
    const holder = document.createElement('span');
    holder.className = 'ds-cb-picture';
    holder.innerHTML = `<svg viewBox="0 0 48 34" aria-hidden="true">${PICTURES[type] || ''}</svg>`;
    return holder;
  };
  // The icon of the Chart Type tab: bars with a line over them, in the colour of the text of the tab.
  const typesIcon = () => {
    const holder = document.createElement('span');
    holder.className = 'ds-design-types-tab-icon';
    holder.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
      + '<path d="M3.5 20.5h17" stroke-width="1.8"/><path d="M6.5 20.5v-5M11 20.5v-8M15.5 20.5v-6M20 20.5v-10" stroke-width="2.8"/>'
      + '<path d="M4.5 10.5l5-4.5 4 3 6.5-5.5" stroke-width="1.8"/></svg>';
    return holder;
  };
  const splitParts = (value, separator) => String(value || '').split(separator).map(part => part.trim()).filter(Boolean);
  const kpiParts = value => splitParts(value, /\s+vs\s+|\s*\|\s*/i);
  const kpiField = part => { const match = /^(SUM|COUNTD|COUNT|AVERAGE|AVG|MEAN|MAX|MIN|MEDIAN)\s*\(\s*(.+?)\s*\)$/i.exec(part); return match ? match[2] : part; };
  const kpiAggregation = part => (/^(SUM|COUNTD|COUNT|AVERAGE|AVG|MEAN|MAX|MIN|MEDIAN)\s*\(/i.exec(part)?.[1] || '').toUpperCase().replace(/^AVERAGE$|^MEAN$/, 'AVG');
  const conditions = value => splitParts(value, /;|\n+/);
  const conditionField = condition => (/^(.+?)\s+(NOT\s+CONTAINS|NOT\s+IN|CONTAINS|IN|>=|<=|!=|=|>|<)\s+/i.exec(condition)?.[1] || condition).trim();
  const isSetting = condition => SETTINGS.includes(identity(conditionField(condition)));
  // A field of dates and times (Test_Start_Time, Test_End_Time…): Gantt measures it, and Rows and Columns can group it by
  // a period (DAY(Test_Start_Time)).
  const isTimeField = name => /(^|_)(time|date|timestamp)$|_time_|_date_/i.test(String(name || '')) && !/duration|_times?_to|time_to|setup_time/i.test(String(name || ''));
  const DATE_BIN_PATTERN = /^(HOUR|DAY|WEEK|MONTH)\((.+)\)$/i;

  // The fields, filters and measures of a chart, as the builder and Chart Type read them.
  function analyse(options) {
    const values = {...options.values};
    const source = String(values.cdr_source || 'CDR-Data');
    const sourceKey = source.toLowerCase();
    const fieldList = [...(options.fields?.[sourceKey] || [])];
    for (const name of options.calculated || []) if (!fieldList.some(item => identity(item.name) === identity(name))) fieldList.push({name, type: 'text', category: 'Auto-calculated Fields'});
    const typeOf = name => fieldList.find(item => identity(item.name) === identity(name))?.type || 'text';
    const change = changes => options.onChange(changes);
    const filterList = conditions(values.filters);
    const settings = filterList.filter(isSetting);
    const plainFilters = filterList.filter(condition => !isSetting(condition));
    const nrMode = (() => {
      const condition = settings.find(item => identity(conditionField(item)) === 'nrmode');
      const match = condition && /\(([^)]*)\)/.exec(condition);
      const modes = match ? match[1].split(',').map(item => item.trim().toUpperCase()) : [];
      return modes.length === 1 ? modes[0] : '';
    })();
    const writeFilters = (plain, kept = settings) => change({filters: [...plain, ...kept].join('; ')});

    // The state the shelves give Chart Type.
    const measures = kpiParts(values.kpi);
    const numeric = measures.filter(part => typeOf(kpiField(part)) === 'number').length;
    const shelfState = {
      measures: measures.length, numeric, text: measures.length - numeric,
      splits: splitParts(values.rows_split, '×').length + splitParts(values.columns_split, '×').length,
      rows: splitParts(values.rows_split, '×').length, columns: splitParts(values.columns_split, '×').length,
      times: measures.filter(part => isTimeField(kpiField(part))).length,
      // A chart without a measure yet (a new one, even with the Campaign rows a KPI card gives it) takes any chart type: the
      // panel then says what it needs.
      empty: !measures.length,
      // (A latitude and a longitude of any name: Latitude, Test_Start_Latitude…)
      geo: fieldList.some(item => identity(item.name).includes('latitude')) && fieldList.some(item => identity(item.name).includes('longitude')),
    };
    return {values, source, fieldList, typeOf, change, settings, plainFilters, nrMode, writeFilters, measures, shelfState};
  }
  const chosenTypeOf = values => TYPES.find(item => item.type.toLowerCase() === String(values.chart_type || '').toLowerCase()) || null;
  // What a chart type needs, as a line ticked once it is given (``verdict`` true, else what is missing): the Chart subpanel,
  // and the form of a KPI card.
  const needsNote = (type, verdict) => {
    const item = TYPES.find(candidate => candidate.type.toLowerCase() === String(type || '').toLowerCase());
    if (!item) return null;
    const ready = verdict === true;
    return h('p', {class: `ds-cb-type-needs ${ready ? 'is-ready' : 'is-missing'}`, role: 'note',
      title: ready ? `${item.type} draws with these fields` : `${item.type} still needs ${lower(verdict)}`},
    h('span', {class: 'ds-cb-type-needs-mark', 'aria-hidden': 'true', text: ready ? '✓' : 'i'}),
    h('span', {}, h('strong', {text: item.type}), ` needs ${lower(requirement(item))}`));
  };
  // Chart Type in a room ``width`` pixels wide: cells as large as fit the widest group (four chart types) on its row, from 80
  // to 168 pixels.
  const TYPES_PER_ROW = Math.max(...TYPE_GROUPS.map(([, names]) => names.length));
  const MINIMUM_TYPE_CELL = 80;
  const fitTypes = (panel, width) => {
    const cell = Math.max(MINIMUM_TYPE_CELL, Math.min(168, Math.floor((width - 40 - (TYPES_PER_ROW - 1) * 4) / TYPES_PER_ROW)));
    panel.style.setProperty('--ds-type-cell', `${cell}px`);
  };
  // The narrowest room beside a chart where Chart Type reads well (cells of 112 pixels); narrower, it takes the slide.
  const typesMinimumWidth = () => TYPES_PER_ROW * 112 + 40 + (TYPES_PER_ROW - 1) * 4;
  const typeButton = (item, {values, shelfState, change}, props = {}) => {
    const verdict = shelfState.empty || item.need(shelfState);
    const active = item.type.toLowerCase() === String(values.chart_type || '').toLowerCase();
    // A chart type the shelves cannot draw is greyed and cannot be chosen: pointing at it says what it needs.
    return h('button', {type: 'button', class: `ds-cb-type-button${active ? ' is-active' : ''}${verdict === true ? '' : ' is-unavailable'}`,
      title: verdict === true ? item.type : `${item.type}: needs ${lower(verdict)}`, 'aria-pressed': String(active), 'aria-disabled': String(verdict !== true),
      dataset: {type: item.type}, onclick: () => { if (verdict === true && !active) change({chart_type: item.type}); }, ...props},
    picture(item.type), h('span', {text: item.type}));
  };
  // The NR Mode of the CDRs a chart reads, kept as the filter NR Mode IN (SA) when the chart keeps one of its own. One button
  // per result: a PPT Design of one NR Mode reads only its CDRs (its NR Mode, the other greyed until NSA & SA is chosen in
  // PPT Filters; a chart that keeps it shows why it is empty), one of NSA & SA both or either; a template (eachPpt) is shared
  // by Designs of any NR Mode, so its chart follows the NR Mode of each one (PPT Mode) or keeps one.
  function nrModeRow({nrMode, settings, plainFilters, writeFilters}, pptNrMode = '', eachPpt = false) {
    const pptMode = String(pptNrMode || '').trim();
    const read = pptMode && !eachPpt ? pptMode.split('&').map(mode => mode.trim().toUpperCase()) : ['NSA', 'SA'];
    const single = read.length === 1;
    const choose = value => {
      const kept = settings.filter(item => identity(conditionField(item)) !== 'nrmode');
      if (value) kept.push(`NR Mode IN (${value})`);
      writeFilters(plainFilters, kept);
    };
    const choices = single
      ? NR_MODES.map(([value, text, title]) => (value === read[0] ? ['', text, `The ${text} CDRs: the PPT Design reads only those`] : [value, text, title]))
      : [['', eachPpt ? 'PPT Mode' : pptMode ? 'NSA & SA' : 'PPT', eachPpt ? 'The NR Mode of each PPT Design that follows the template' : 'The CDRs of both NR Modes, as the PPT Design reads them'], ...NR_MODES];
    const isActive = value => value === nrMode || (single && !value && nrMode === read[0]);
    return h('div', {class: 'ds-cb-source-row', title: 'The NR Mode of the CDRs the chart reads'}, h('span', {class: 'ds-cb-shelf-label', text: 'NR Mode'}),
      h('div', {class: 'ds-cb-segmented', role: 'group', 'aria-label': 'NR Mode of the CDRs the chart reads'}, choices.map(([value, text, title]) => {
        const unread = Boolean(value) && !read.includes(value);
        return h('button', {type: 'button', class: `${isActive(value) ? 'is-active' : ''}${unread ? ' is-unread' : ''}`, 'aria-pressed': String(isActive(value)),
          disabled: unread && !isActive(value), onclick: () => { if (!isActive(value)) choose(value); },
          title: unread ? `The PPT Design reads only the ${pptMode} CDRs: choose NR Mode NSA & SA in PPT Filters to show the ${value} ones` : title}, text);
      })));
  }
  // The settings of the chart type chosen (Threshold, Buckets, Bin Size, Whiskers, Target, Direction, Sort, Date Bin), kept
  // among the filters of the chart: an empty value or the first choice leaves the setting out (its default).
  function settingRow({values, settings, plainFilters, writeFilters}) {
    const chosenType = chosenTypeOf(values);
    if (!chosenType?.settings?.length) return null;
    const rows = chosenType.settings.map(setting => {
      const key = identity(setting.name);
      const current = settings.find(item => identity(conditionField(item)) === key);
      const value = current ? current.replace(/^.+?\s*=\s*/, '') : '';
      const write = text => {
        const kept = settings.filter(item => identity(conditionField(item)) !== key);
        if (String(text || '').trim()) kept.push(`${setting.name} = ${String(text).trim()}`);
        writeFilters(plainFilters, kept);
      };
      const control = setting.choices
        ? h('select', {'aria-label': setting.name, onchange: event => write(event.target.value)},
          setting.choices.map(([choice, label]) => h('option', {value: choice, text: label, selected: identity(choice) === identity(value)})))
        : h('input', {type: 'text', value, placeholder: setting.placeholder || '', 'aria-label': setting.name, onchange: event => write(event.target.value)});
      return h('label', {class: 'ds-cb-row ds-cb-setting', title: setting.title || null}, setting.name, control);
    });
    return rows.length === 1 ? rows[0] : h('div', {class: 'ds-cb-settings'}, rows);
  }

  /** Render Chart Type of one chart into ``host``: its chart types grouped by what they show, the ones the shelves cannot
   *  draw greyed, the setting of the one chosen and what the one pointed at needs. Same options as render(). */
  function renderTypes(host, options) {
    const context = analyse(options);
    const hint = h('p', {class: 'ds-cb-types-hint', 'aria-live': 'polite'});
    const describe = item => {
      if (!item) {
        hint.replaceChildren(context.shelfState.empty ? 'Choose any chart type: the panel then says what it needs.'
          : 'Drop fields on the shelves: the chart types they can draw light up.');
        return;
      }
      const verdict = item.need(context.shelfState);
      hint.replaceChildren(h('strong', {text: item.type}), verdict === true ? ' · ready with these fields' : ` · needs ${lower(verdict)}`);
    };
    const chosen = chosenTypeOf(context.values);
    const point = item => ({onmouseenter: () => describe(item), onfocus: () => describe(item), onmouseleave: () => describe(chosen), onblur: () => describe(chosen)});
    host.replaceChildren(...[
      // A row for each group; a group of one or two chart types goes on the row before it when it fits.
      ...TYPE_GROUPS.flatMap(([label, names], index) => [
        index && names.length > 2 ? h('span', {class: 'ds-cb-type-break', 'aria-hidden': 'true'}) : null,
        h('div', {class: 'ds-cb-type-group', role: 'group', 'aria-label': label},
          h('span', {class: 'ds-cb-type-group-label', text: label}),
          h('div', {class: 'ds-cb-types'}, names.map(name => TYPES.find(item => item.type === name)).filter(Boolean).map(item => typeButton(item, context, point(item)))))]),
      settingRow(context), hint].filter(Boolean));
    describe(chosen);
  }

  /** Render the builder of one chart into ``host``.
   *  options: {values, fields: {source: [{name, type, category}]}, calculated: [names], parameters: [...],
   *            lockedFilters: [labels], onLockedFilter (opens the filters of the PPT, where those change),
   *            fieldValues: async (source, field) => [{value, count}], onChange(changes),
   *            showSource (false: the source and NR Mode are chosen elsewhere, as in Chart Builder), pptNrMode (the NR Mode
   *            of the PPT Design: NSA, SA or NSA & SA), eachPpt (a template chart: each PPT Design keeps its NR Mode),
   *            chartTypes (false: Chart Type is drawn apart, with renderTypes), repeat (One chart per where the source is chosen
   *            elsewhere, as in Chart Builder)} */
  // The groups of fields in the order they are used most: the main fields first, the fields of no section last.
  const GROUP_ORDER = ['CDR-Main fields', 'Normalised fields', 'Network Insights', 'Non-Qualified Calls', 'DT Analyzer RCA', 'Vendor Mapping', 'Auto-calculated Fields'];
  const groupRank = group => (group === 'Other fields' ? 1000 : GROUP_ORDER.includes(group) ? GROUP_ORDER.indexOf(group) : 500);
  function render(host, options) {
    const context = analyse(options);
    const {values, source, fieldList, typeOf, change, settings, plainFilters, writeFilters, measures, shelfState} = context;

    // Data pane
    let query = '';
    const fieldsHost = h('div', {class: 'ds-cb-fields'});
    const paintFields = () => {
      const groups = new Map();
      for (const item of fieldList) {
        if (query && !item.name.toLowerCase().includes(query)) continue;
        const group = item.category || 'Other fields';
        if (!groups.has(group)) groups.set(group, []);
        groups.get(group).push(item);
      }
      fieldsHost.replaceChildren(...[...groups.entries()].sort(([left], [right]) => groupRank(left) - groupRank(right) || left.localeCompare(right)).map(([group, items]) => h('details', {class: 'ds-cb-group', open: Boolean(query)},
        h('summary', {}, group, h('span', {class: 'ds-cb-count', text: String(items.length)})),
        h('div', {class: 'ds-cb-group-fields'}, items.sort((left, right) => (left.type === right.type ? left.name.localeCompare(right.name) : left.type === 'text' ? -1 : 1)).map(fieldPill)))));
      if (!fieldsHost.childElementCount) fieldsHost.append(h('p', {class: 'ds-cb-empty', text: fieldList.length ? 'No field matches.' : 'The fields appear once the Design is prepared.'}));
    };
    const fieldPill = item => {
      const pill = h('button', {type: 'button', class: `ds-cb-field is-${item.type}`, draggable: 'true', title: `${item.name} · ${item.type === 'number' ? 'measure (numbers)' : 'dimension (values)'} · drag it to a shelf, or click to choose one`,
        onclick: event => openMenu(event.currentTarget, SHELVES.map(([key, label]) => [label, () => addToShelf(key, item.name)]))},
      h('span', {class: 'ds-cb-type', text: item.type === 'number' ? '#' : 'Abc'}), item.name);
      pill.addEventListener('dragstart', event => { event.dataTransfer.setData('application/x-ds-field', item.name); event.dataTransfer.effectAllowed = 'copy'; });
      return pill;
    };
    const search = h('input', {type: 'search', class: 'ds-cb-search', placeholder: 'Search fields', 'aria-label': 'Search fields',
      oninput: event => { query = event.target.value.trim().toLowerCase(); paintFields(); }});
    paintFields();

    // Shelves
    function shelfItems(key) {
      if (key === 'kpi') return measures;
      if (key === 'rows_split' || key === 'columns_split') return splitParts(values[key], '×');
      if (key === 'legend') return splitParts(values.legend, ',');
      if (key === 'filters') return plainFilters;
      return values.repeat?.field ? [values.repeat.field] : [];
    }
    function writeShelf(key, items) {
      if (key === 'kpi') change({kpi: items.join(' | ')});
      else if (key === 'rows_split' || key === 'columns_split') change({[key]: items.join(' × ')});
      else if (key === 'legend') change({legend: items.join(', ')});
      else if (key === 'filters') writeFilters(items);
    }
    // A field goes where it is dropped: on a pill it takes its place, before or after one it goes there, and chosen from the
    // menu of the field it goes last (a field already on the shelf moves there).
    function addToShelf(key, field, place = null) {
      if (key === 'filters') { openFilterDialog(field); return; }
      if (key === 'repeat') { change({repeat: {field}}); return; }
      // A time splits the chart by day (its pill changes the period): each time apart would give a split per sample.
      if ((key === 'rows_split' || key === 'columns_split') && isTimeField(field) && !DATE_BIN_PATTERN.test(field)) field = `DAY(${field})`;
      const same = item => identity(key === 'kpi' ? kpiField(item) : item) === identity(field);
      const current = shelfItems(key);
      const at = place ? place.index : current.length;
      const next = current.filter((item, index) => !same(item) || (place?.replace && index === at));
      const position = current.slice(0, at).filter(item => !same(item)).length;
      if (place?.replace && !same(current[at] ?? '')) next.splice(position, 1, field);
      else if (!(place?.replace && same(current[at] ?? ''))) next.splice(position, 0, field);
      const changes = {};
      if (key === 'kpi') changes.kpi = next.join(' | ');
      else if (key === 'legend') changes.legend = next.join(', ');
      else changes[key] = next.join(' × ');
      if (key === 'kpi') Object.assign(changes, suggestType({...shelfState, measures: next.length, numeric: next.filter(part => typeOf(kpiField(part)) === 'number').length, text: next.filter(part => typeOf(kpiField(part)) !== 'number').length}));
      change(changes);
    }
    // Chart Type proposes the chart type the measures call for when the current one cannot draw them.
    function suggestType(state) {
      const current = TYPES.find(item => item.type.toLowerCase() === String(values.chart_type || '').toLowerCase());
      if (current && (current.need(state) === true || current.fits(state))) return {};
      // (Another numeric measure on a CDF gives one line per measure.)
      const cdf = /cdf/i.test(String(values.chart_type || ''));
      const best = state.numeric >= 2 ? (state.numeric === 2 && !cdf ? 'Scatter' : 'Multi KPI CDF Lines')
        : state.text >= 1 ? '100% Stacked Vertical Bars'
          : state.splits ? 'Average Vertical Bars' : 'CDF Line';
      return {chart_type: best};
    }
    const shelf = ([key, label, title]) => {
      const items = shelfItems(key);
      const zone = h('div', {class: `ds-cb-shelf-items${items.length ? '' : ' is-empty'}`, 'aria-label': `${label} shelf`},
        key === 'filters' ? (options.lockedFilters || []).map(text => (options.onLockedFilter
          ? h('button', {type: 'button', class: 'ds-cb-pill is-locked is-editable', title: 'A filter of the PPT: it applies to every chart. Click to change it in PPT Filters', onclick: options.onLockedFilter}, text)
          : h('span', {class: 'ds-cb-pill is-locked', title: 'A filter of the PPT: it applies to every chart', text}))) : null,
        items.map((item, index) => shelfPill(key, item, index, items)),
        items.length ? null : h('span', {class: 'ds-cb-drop-hint', text: key === 'filters' ? 'Drop a field to filter'
          : key === 'repeat' ? 'Drop a field: one chart for each of its values' : 'Drop a field here'}));
      // Where a drop goes: on the middle of a pill a new field takes its place, near its edges it goes before or after it, and
      // elsewhere before the first pill it is in front of, or last. A moved pill goes before or after the pill.
      const pills = () => [...zone.querySelectorAll('.ds-cb-pill[data-index]')];
      const dropPlace = (event, replacing) => {
        const over = event.target.closest?.('.ds-cb-pill[data-index]');
        if (over && zone.contains(over)) {
          const box = over.getBoundingClientRect();
          const share = (event.clientX - box.left) / Math.max(box.width, 1);
          if (replacing && share > .25 && share < .75) return {index: Number(over.dataset.index), replace: true};
          return {index: Number(over.dataset.index) + (share >= .5 ? 1 : 0), replace: false};
        }
        const next = pills().find(pill => { const box = pill.getBoundingClientRect(); return event.clientY < box.top || (event.clientY <= box.bottom && event.clientX < box.left + box.width / 2); });
        return {index: next ? Number(next.dataset.index) : pills().length, replace: false};
      };
      const unmark = () => { zone.classList.remove('is-drop'); pills().forEach(pill => pill.classList.remove('is-drop-replace', 'is-drop-before', 'is-drop-after')); };
      const dragged = event => [...event.dataTransfer.types].some(type => type.startsWith('application/x-ds-'));
      zone.addEventListener('dragover', event => {
        if (!dragged(event)) return;
        event.preventDefault();
        unmark();
        zone.classList.add('is-drop');
        if (key === 'filters' || key === 'repeat') return;
        const place = dropPlace(event, event.dataTransfer.types.includes('application/x-ds-field'));
        const all = pills();
        if (place.replace) all[place.index]?.classList.add('is-drop-replace');
        else if (place.index < all.length) all[place.index].classList.add('is-drop-before');
        else all.at(-1)?.classList.add('is-drop-after');
      });
      zone.addEventListener('dragleave', event => { if (!zone.contains(event.relatedTarget)) unmark(); });
      zone.addEventListener('drop', event => {
        const field = event.dataTransfer.getData('application/x-ds-field');
        const moved = event.dataTransfer.getData('application/x-ds-pill');
        const place = dropPlace(event, Boolean(field));
        unmark();
        event.preventDefault();
        if (field) { addToShelf(key, field, place); return; }
        if (moved) {
          const [fromKey, fromIndex] = JSON.parse(moved);
          movePill(fromKey, Number(fromIndex), key, place.index);
        }
      });
      // The Filters shelf has a subpanel of its own, titled: it needs no label of its own.
      return h('div', {class: `ds-cb-shelf is-${key}${key === 'filters' ? ' is-bare' : ''}`, title},
        key === 'filters' ? null : h('span', {class: 'ds-cb-shelf-label', text: label}), zone);
    };
    // A subpanel of the builder: the chart (its source and shelves), its filters, and the fields to drag to them.
    const card = (kind, title, ...children) => h('section', {class: `ds-cb-card is-${kind}`, 'aria-label': title},
      h('h4', {class: 'ds-cb-card-title', text: title}), ...children);
    function movePill(fromKey, fromIndex, toKey, toIndex) {
      if (fromKey === 'filters' || toKey === 'filters' || fromKey === 'repeat' || toKey === 'repeat') return;
      const source = shelfItems(fromKey);
      const [item] = source.splice(fromIndex, 1);
      if (!item) return;
      const field = fromKey === 'kpi' ? kpiField(item) : item;
      if (fromKey === toKey) {
        // (The place is counted with the pill still in it.)
        source.splice(toIndex === null ? source.length : toIndex - (fromIndex < toIndex ? 1 : 0), 0, item);
        writeShelf(fromKey, source);
        return;
      }
      const target = shelfItems(toKey).filter(existing => identity(toKey === 'kpi' ? kpiField(existing) : existing) !== identity(field));
      target.splice(toIndex ?? target.length, 0, toKey === 'kpi' ? field : field);
      const changes = {};
      for (const [key, items] of [[fromKey, source], [toKey, target]]) {
        if (key === 'kpi') changes.kpi = items.join(' | ');
        else if (key === 'legend') changes.legend = items.join(', ');
        else changes[key] = items.join(' × ');
      }
      change(changes);
    }
    const shelfPill = (key, item, index, items) => {
      const isMeasure = key === 'kpi';
      const field = isMeasure ? kpiField(item) : key === 'filters' ? conditionField(item) : item;
      const aggregation = isMeasure ? kpiAggregation(item) : '';
      const pill = h('span', {class: `ds-cb-pill is-${key === 'filters' ? 'filter' : typeOf(field)}`, draggable: key === 'filters' || key === 'repeat' ? 'false' : 'true', dataset: {shelf: key, index: String(index)}, tabindex: '0'},
        h('button', {type: 'button', class: 'ds-cb-pill-label', title: key === 'filters' ? 'Change the filter' : isMeasure ? 'Aggregation and order' : DATE_BIN_PATTERN.test(field) || isTimeField(field) ? 'Period and order' : 'Order',
          onclick: event => {
            if (key === 'filters') { openFilterDialog(field, item, index); return; }
            if (key === 'repeat') return;
            const actions = [];
            if (isMeasure) actions.push(...AGGREGATIONS.map(([code, label]) => [`${aggregation === code ? '✓ ' : ''}${label}`, () => {
              const next = [...items]; next[index] = code ? `${code}(${field})` : field; writeShelf('kpi', next);
            }]));
            if ((key === 'rows_split' || key === 'columns_split') && (isTimeField(field) || DATE_BIN_PATTERN.test(field))) {
              // A time on Rows or Columns, grouped by a period or as it is.
              const base = DATE_BIN_PATTERN.exec(field)?.[2] || field, period = (DATE_BIN_PATTERN.exec(field)?.[1] || '').toUpperCase();
              actions.push(...[['HOUR', 'By hour'], ['DAY', 'By day'], ['WEEK', 'By week'], ['MONTH', 'By month'], ['', 'Exact time']].map(([code, label]) => [`${period === code ? '✓ ' : ''}${label}`, () => {
                const next = [...items]; next[index] = code ? `${code}(${base})` : base; writeShelf(key, next);
              }]));
            }
            if (index > 0) actions.push(['Move before', () => { const next = [...items]; next.splice(index - 1, 0, next.splice(index, 1)[0]); writeShelf(key, next); }]);
            if (index < items.length - 1) actions.push(['Move after', () => { const next = [...items]; next.splice(index + 1, 0, next.splice(index, 1)[0]); writeShelf(key, next); }]);
            if (actions.length) openMenu(event.currentTarget, actions);
          }},
        isMeasure && aggregation ? `${AGGREGATIONS.find(([code]) => code === aggregation)?.[1] || aggregation} of ${field}` : item),
        h('button', {type: 'button', class: 'ds-cb-pill-remove', 'aria-label': `Remove ${item}`, onclick: () => {
          if (key === 'repeat') change({repeat: null});
          else writeShelf(key, items.filter((_value, position) => position !== index));
        }}, '×'));
      pill.addEventListener('dragstart', event => { event.dataTransfer.setData('application/x-ds-pill', JSON.stringify([key, index])); event.dataTransfer.effectAllowed = 'move'; });
      return pill;
    };

    // Filter dialog: the values of a field with their samples in the Design's selection, or a numeric condition;
    // a parameter of the template can stand for the values.
    function openFilterDialog(field, existing = '', index = -1) {
      closeMenus();
      const numberField = typeOf(field) === 'number';
      const match = existing && /^(.+?)\s+(NOT\s+CONTAINS|NOT\s+IN|CONTAINS|IN|>=|<=|!=|=|>|<)\s+(.+)$/i.exec(existing);
      const operator = (match?.[2] || (numberField ? '<' : 'IN')).toUpperCase().replace(/\s+/g, ' ');
      const raw = match?.[3] || '';
      const listed = raw.replace(/^\(|\)$/g, '').split(',').map(item => item.trim()).filter(Boolean);
      const parameter = /^\(?\{([^}]+)\}\)?$/.exec(raw.trim())?.[1] || '';
      const dialog = h('div', {class: 'ds-design-popover ds-cb-filter', role: 'dialog', 'aria-label': `Filter ${field}`});
      const usable = (options.parameters || []).filter(item => (numberField ? item.type === 'number' : item.type === 'values'));
      const parameterSelect = h('select', {'aria-label': 'Use parameter'}, h('option', {value: '', text: 'No parameter: the values below'}), usable.map(item => h('option', {value: item.name, text: `{${item.name}}`, selected: item.name === parameter})));
      const commit = text => {
        const plain = [...plainFilters];
        if (index >= 0) plain.splice(index, 1, ...(text ? [text] : []));
        else if (text) plain.push(text);
        closeMenus();
        writeFilters(plain);
      };
      dialog.append(h('h4', {text: `Filter · ${field}`}));
      if (usable.length) dialog.append(h('label', {class: 'ds-cb-row'}, 'Use parameter', parameterSelect));
      if (numberField) {
        const operatorSelect = h('select', {'aria-label': 'Condition'}, ['<', '<=', '>', '>=', '=', '!='].map(item => h('option', {value: item, text: item, selected: item === operator})));
        const valueInput = h('input', {type: 'number', step: 'any', value: parameter ? '' : raw, 'aria-label': 'Value'});
        dialog.append(h('div', {class: 'ds-cb-row'}, operatorSelect, valueInput));
        dialog.append(h('div', {class: 'ds-cb-actions'},
          h('button', {type: 'button', onclick: () => commit(parameterSelect.value ? `${field} ${operatorSelect.value} {${parameterSelect.value}}` : valueInput.value === '' ? '' : `${field} ${operatorSelect.value} ${valueInput.value}`)}, 'Keep'),
          index >= 0 ? h('button', {type: 'button', onclick: () => commit('')}, 'Remove') : null));
      } else {
        const modes = [['IN', 'Include'], ['NOT IN', 'Exclude'], ['CONTAINS', 'Contains']];
        const modeSelect = h('select', {'aria-label': 'Condition'}, modes.map(([code, label]) => h('option', {value: code, text: label, selected: code === operator})));
        const listHost = h('div', {class: 'ds-cb-values'}, h('p', {class: 'ds-cb-empty', text: 'Reading the values…'}));
        const searchValues = h('input', {type: 'search', placeholder: 'Search values', 'aria-label': 'Search values'});
        const textInput = h('input', {type: 'text', value: operator === 'CONTAINS' ? listed.join(', ') : '', placeholder: 'Text the values contain', 'aria-label': 'Contains'});
        let all = [];
        const chosen = new Set(operator === 'CONTAINS' || parameter ? [] : listed);
        const paint = () => {
          const query = searchValues.value.trim().toLowerCase();
          listHost.replaceChildren(...all.filter(item => !query || String(item.value).toLowerCase().includes(query)).slice(0, 400).map(item => h('label', {class: 'ds-cb-value'},
            h('input', {type: 'checkbox', checked: chosen.has(String(item.value)), onchange: event => { if (event.target.checked) chosen.add(String(item.value)); else chosen.delete(String(item.value)); }}),
            h('span', {text: String(item.value)}), item.count !== undefined ? h('span', {class: 'ds-cb-count', text: Number(item.count).toLocaleString()}) : null)));
          if (!listHost.childElementCount) listHost.append(h('p', {class: 'ds-cb-empty', text: all.length ? 'No value matches.' : 'No values in the selection.'}));
        };
        searchValues.addEventListener('input', paint);
        const syncMode = () => { textInput.hidden = modeSelect.value !== 'CONTAINS'; listHost.hidden = searchValues.hidden = modeSelect.value === 'CONTAINS'; };
        modeSelect.addEventListener('change', syncMode);
        dialog.append(h('div', {class: 'ds-cb-row'}, modeSelect), searchValues, listHost, textInput,
          h('div', {class: 'ds-cb-actions'},
            h('button', {type: 'button', onclick: () => {
              const mode = modeSelect.value;
              if (parameterSelect.value) { commit(`${field} ${mode === 'CONTAINS' ? 'IN' : mode} ({${parameterSelect.value}})`); return; }
              if (mode === 'CONTAINS') { commit(textInput.value.trim() ? `${field} CONTAINS (${textInput.value.trim()})` : ''); return; }
              commit(chosen.size ? `${field} ${mode} (${[...chosen].join(', ')})` : '');
            }}, 'Keep'),
            index >= 0 ? h('button', {type: 'button', onclick: () => commit('')}, 'Remove') : null));
        syncMode();
        Promise.resolve(options.fieldValues?.(source, field)).then(items => { all = items || []; paint(); }).catch(() => { all = []; paint(); });
      }
      placePopover(dialog, host.querySelector('.ds-cb-shelf.is-filters') || host);
    }

    // Chart Type and the setting of the chart type chosen.
    const chartTypes = options.chartTypes === false ? null : h('div', {class: 'ds-cb-types', role: 'group', 'aria-label': 'Chart Type'}, TYPES.map(item => typeButton(item, context)));

    // What the chart type chosen needs: ticked once the shelves give it.
    const chosen = chosenTypeOf(values);
    const needs = chosen ? needsNote(chosen.type, chosen.need(shelfState)) : null;

    host.replaceChildren(...[
      card('chart', 'Chart', needs,
        options.showSource === false ? null : h('div', {class: 'ds-cb-source'},
          h('div', {class: 'ds-cb-source-row', title: 'The CDRs the chart reads'}, h('span', {class: 'ds-cb-shelf-label', text: 'Source'}),
            h('div', {class: 'ds-cb-segmented', role: 'group', 'aria-label': 'Source: the CDRs the chart reads'}, SOURCES.map(([value, label, title]) => h('button', {type: 'button', class: value === source ? 'is-active' : '', 'aria-pressed': String(value === source), title, onclick: () => change({cdr_source: value})}, label)))),
          nrModeRow(context, options.pptNrMode, options.eachPpt)),
        h('div', {class: 'ds-cb-shelves'}, SHELVES.filter(([key]) => key !== 'filters' && (key !== 'repeat' || options.showSource !== false || options.repeat)).map(shelf))),
      card('filters', 'Filters', shelf(SHELVES.find(([key]) => key === 'filters')),
        // The rows every measure of the chart leaves out.
        h('div', {class: 'ds-cb-exclusions'}, [['exclude_null_empty', 'Leave out empty values', 'Rows whose measure is empty (Null or blank) are left out'],
          ['exclude_zero', 'Leave out zeros', 'Rows whose measure is 0 are left out']].map(([key, label, title]) => h('label', {class: 'ds-design-check', title},
          h('input', {type: 'checkbox', checked: Boolean(values[key]), onchange: event => change({[key]: event.target.checked})}), label)))),
      chartTypes ? h('div', {class: 'ds-cb-chart-types'}, h('span', {class: 'ds-cb-shelf-label', text: 'Chart Type'}), chartTypes, settingRow(context)) : null,
      h('section', {class: 'ds-cb-card is-fields ds-cb-data', 'aria-label': 'Fields'},
        h('h4', {class: 'ds-cb-card-title', text: `Fields · ${SOURCES.find(([value]) => value === source)?.[1] || source}`}), search, fieldsHost),
    ].filter(Boolean));
  }

  // Menus and popovers (the classes of the Designer's).
  function closeMenus() { document.querySelectorAll('.ds-design-popover').forEach(node => node.remove()); }
  function placePopover(popover, anchor) {
    document.body.append(popover);
    const box = anchor.getBoundingClientRect();
    const width = popover.offsetWidth, height = popover.offsetHeight;
    let left = Math.max(8, Math.min(box.left, window.innerWidth - width - 8));
    let top = box.bottom + 4;
    if (top + height > window.innerHeight - 8) top = Math.max(8, box.top - height - 4);
    Object.assign(popover.style, {left: `${left}px`, top: `${top}px`});
    popover.querySelector('input, select, button')?.focus({preventScroll: true});
  }
  function openMenu(anchor, actions) {
    closeMenus();
    const menu = h('div', {class: 'ds-design-popover ds-design-menu', role: 'menu'}, actions.map(([label, action]) => h('button', {
      type: 'button', role: 'menuitem', onclick: () => { closeMenus(); action(); },
    }, label)));
    placePopover(menu, anchor);
  }

  window.ChartShelves = {render, renderTypes, picture, typesIcon, needsNote, fitTypes, typesMinimumWidth, kpiParts, kpiField, groupRank};
})();
