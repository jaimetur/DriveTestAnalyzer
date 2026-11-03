// Methodology Impact of Scoring & GAP Analysis: what a change of methodology does to the results, with the scope of the open
// Saved Filter. The same tests are scored with both methodologies in the background (see scoring_impact.py), so every
// difference comes from the methodology: operators, environments, categories, KPIs, geographical areas, GAPs and points lost.
(() => {
  const POLL_MS = 1500;
  const STORAGE_KEY = 'scoring-methodology-impact';
  const PAGE_ROWS = 12;
  // Differences below this are shown as no change.
  const NO_CHANGE = .005;
  const options = new Map();
  const impacts = new Map();
  const expanded = new Set();
  let areaLevel = null;
  // The operators enabled in the panels drawn, which the documents show.
  let chosenOperators = null;
  let renderToken = 0;
  let pollTimer = null;

  const number = (value, digits = 1) => (Number.isFinite(Number(value)) && value !== null && value !== undefined
    ? Number(value).toLocaleString('en-US', {minimumFractionDigits: digits, maximumFractionDigits: digits}) : 'N/A');
  const signed = (value, digits = 2) => {
    if (!Number.isFinite(Number(value)) || value === null || value === undefined) return 'N/A';
    const text = number(Math.abs(value), digits);
    return Math.abs(value) < 10 ** -digits / 2 ? text : `${value > 0 ? '+' : '−'}${text}`;
  };
  const ordinal = (value) => {
    const rest = value % 100;
    return `${value}${rest >= 11 && rest <= 13 ? 'th' : ({1: 'st', 2: 'nd', 3: 'rd'}[value % 10] || 'th')}`;
  };

  function element(tag, className = '', ...children) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    node.append(...children.filter(child => child !== null && child !== undefined && child !== false).map(child => (child instanceof Node ? child : String(child))));
    return node;
  }

  function readStored() {
    try {
      const stored = JSON.parse(window.sessionStorage.getItem(STORAGE_KEY) || '{}');
      return stored && typeof stored === 'object' ? stored : {};
    } catch (_error) {
      return {};
    }
  }

  function selectionOf(filterId, offered) {
    const stored = readStored()[filterId];
    const selection = {...offered.defaults, ...(stored && typeof stored === 'object' ? stored : {})};
    if (!offered.nr_modes.includes(selection.nr_mode)) selection.nr_mode = offered.defaults.nr_mode;
    // (A campaign or methodology that is no longer there takes the default of its NR Mode.)
    const defaults = offered.by_nr_mode[selection.nr_mode];
    const campaigns = (offered.campaigns[selection.nr_mode] || []).map(entry => entry.value);
    const methodologies = offered.methodologies.map(item => item.id);
    for (const [key, values] of [['campaign_a', campaigns], ['campaign_b', campaigns], ['campaign', campaigns], ['methodology_a', methodologies], ['methodology_b', methodologies]]) {
      if (!values.includes(selection[key])) selection[key] = defaults[key];
    }
    return selection;
  }

  function rememberSelection(filterId, selection) {
    try {
      window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify({...readStored(), [filterId]: selection}));
    } catch (_error) { /* Only a convenience: the selection is the default one after a reload. */ }
  }

  const queryOf = (selection, extra = {}) => new URLSearchParams({...selection, ...extra}).toString();

  // The bar either side of zero of a difference, as long as the difference against the largest of its table.
  function track(delta, scale, tone) {
    const bar = element('span', 'scoring-impact-track');
    const share = Math.abs(Number(delta) || 0) / Math.max(Number(scale) || 0, NO_CHANGE);
    if (share > 0 && tone !== 'flat') {
      const fill = element('i', `is-${delta > 0 ? 'right' : 'left'} is-${tone}`);
      fill.style.width = `${Math.min(share, 1) * 50}%`;
      bar.append(fill);
    }
    return bar;
  }

  function toneOf(delta, inverse = false) {
    if (delta === null || delta === undefined || Math.abs(delta) < NO_CHANGE) return 'flat';
    return (delta > 0) !== inverse ? 'gain' : 'loss';
  }

  // A cell of the impact: its difference with the bar, and the value before and after.
  function shiftCell(cell, scale, {inverse = false, title = '', flip = false, digits = 1} = {}) {
    const box = element('td', 'scoring-impact-cell');
    if (!cell || (cell.before === null && cell.after === null)) {
      box.classList.add('is-empty');
      box.textContent = '—';
      return box;
    }
    const tone = toneOf(cell.delta, inverse);
    box.dataset.tone = tone;
    const head = element('span', 'scoring-impact-head', element('b', `is-${tone}`, signed(cell.delta)));
    if (flip) head.append(element('em', 'scoring-impact-flag', 'Changes side'));
    box.append(head, track(cell.delta, scale, tone),
      element('small', '', `${cell.before === null ? 'none' : number(cell.before, digits)} → ${cell.after === null ? 'none' : number(cell.after, digits)}`));
    if (title) box.title = title;
    return box;
  }

  function operatorHeader(item, safeHexColor) {
    const cell = element('th', 'scoring-impact-operator', `${item.label}${item.is_reference ? ' (reference)' : ''}`);
    const color = safeHexColor(item.color);
    if (color) cell.style.setProperty('--operator-color', color);
    return cell;
  }

  function kpiLabel(row, extra = null) {
    const type = String(row.kpi_type || '').trim().toLocaleLowerCase();
    const name = element('span', 'scoring-kpi-name', row.kpi || row.code);
    const line = element('span', 'scoring-kpi-name-row');
    if (type === 'reliable' || type === 'diff') {
      const badge = element('span', 'scoring-kpi-badge', type === 'reliable' ? 'R' : 'D');
      badge.dataset.kpiType = type;
      badge.title = `${row.kpi_type} KPI`;
      line.append(badge);
    }
    line.append(name);
    return element('div', 'scoring-impact-label', line, extra);
  }

  function kindChips(kinds, labels) {
    const box = element('span', 'scoring-impact-chips');
    for (const kind of kinds || []) {
      const chip = element('span', 'scoring-impact-chip', labels[kind] || kind);
      chip.dataset.kind = kind;
      box.append(chip);
    }
    return box;
  }

  // Rows of a label and a cell per operator, which share the scale of their table.
  function matrix(firstHeader, operators, rows, ctx, {inverse = false, total = null, extraHeaders = [], digits = 1} = {}) {
    const table = element('table', 'scoring-insight-table scoring-impact-matrix');
    const head = table.createTHead().insertRow();
    head.append(element('th', '', firstHeader), ...operators.map(item => operatorHeader(item, ctx.safeHexColor)),
      ...extraHeaders.map(text => element('th', '', text)));
    const body = table.createTBody();
    const cellsOf = row => operators.map(item => row.cells?.[item.operator]);
    const scale = Math.max(0, ...rows.flatMap(row => cellsOf(row).map(cell => Math.abs(Number(cell?.delta) || 0))));
    const addRow = (section, row, rowScale) => {
      const line = section.insertRow();
      if (row.className) line.className = row.className;
      const first = line.insertCell();
      first.className = 'scoring-impact-row-label';
      first.append(row.label);
      for (const item of operators) {
        const cell = row.cells?.[item.operator];
        line.append(shiftCell(cell, rowScale, {inverse, flip: Boolean(cell?.flip), digits, title: row.titleOf ? row.titleOf(item, cell) : ''}));
      }
      for (const extra of row.extra || []) line.insertCell().append(extra);
    };
    for (const row of rows) addRow(body, row, scale);
    if (total) {
      const footer = table.createTFoot();
      const totalScale = Math.max(0, ...cellsOf(total).map(cell => Math.abs(Number(cell?.delta) || 0)));
      addRow(footer, total, totalScale);
    }
    return element('div', 'scoring-insight-table-wrap', table);
  }

  function pagedRows(key, rows, drawRows) {
    const open = expanded.has(key);
    const shown = open || rows.length <= PAGE_ROWS ? rows : rows.slice(0, PAGE_ROWS);
    const box = element('div', 'scoring-impact-paged', drawRows(shown));
    if (rows.length > PAGE_ROWS) {
      const toggle = element('button', 'scoring-impact-more', open ? `Show the first ${PAGE_ROWS}` : `Show all ${rows.length}`);
      toggle.type = 'button';
      toggle.addEventListener('click', () => {
        if (open) expanded.delete(key);
        else expanded.add(key);
        box.replaceWith(pagedRows(key, rows, drawRows));
      });
      box.append(toggle);
    }
    return box;
  }

  function note(text) {
    return element('p', 'scoring-insight-note', text);
  }

  // The share of each category or environment of a methodology, as a stacked bar.
  function allocationBars(groups, doc, palette, field = 'category') {
    const peak = Math.max(1, sum(groups.map(row => row.before)), sum(groups.map(row => row.after)));
    const colorOf = index => palette[index % palette.length];
    const row = (name, side) => {
      const bar = element('span', 'scoring-impact-stack');
      groups.forEach((group, index) => {
        const value = Number(group[side]) || 0;
        if (value <= 0) return;
        const segment = element('i', '', value / peak > .05 ? number(value, 0) : '');
        segment.style.width = `${value / peak * 100}%`;
        segment.style.background = colorOf(index);
        segment.title = `${group[field] ?? group.label}: ${number(value, 2)} points`;
        bar.append(segment);
      });
      return element('div', 'scoring-impact-stack-row', element('strong', '', name), bar);
    };
    const legend = element('div', 'scoring-location-legend');
    groups.forEach((group, index) => {
      const swatch = element('i');
      swatch.style.background = colorOf(index);
      legend.append(element('span', '', swatch, group[field] ?? group.label));
    });
    return element('div', 'scoring-impact-allocation', row(doc.before.profile_name, 'before'), row(doc.after.profile_name, 'after'), legend);
  }

  const sum = values => values.reduce((total, value) => total + (Number(value) || 0), 0);

  // The changes of a KPI, once per change: the environments with the same change are named together.
  function detailLines(details) {
    const groups = new Map();
    for (const item of details || []) {
      const key = JSON.stringify([item.label, item.before, item.after]);
      if (!groups.has(key)) groups.set(key, {...item, environments: []});
      if (item.environment) groups.get(key).environments.push(item.environment);
    }
    const box = element('div', 'scoring-impact-details');
    for (const item of groups.values()) {
      box.append(element('div', '', element('strong', '', `${item.label}${item.environments.length ? ` (${item.environments.join(', ')})` : ''}: `),
        element('code', '', item.before), ' → ', element('code', '', item.after)));
    }
    return box;
  }

  function changesPanel(pane, doc, part, ctx) {
    const changes = part.changes;
    const section = ctx.insightSection(pane, `What changed: ${doc.before.profile_name} → ${doc.after.profile_name}`, 'scoring-impact-changes-card', false);
    if (doc.same_methodology) {
      section.append(note(`Both campaigns are scored with ${doc.before.profile_name}: the methodology does not change between them, so all the difference between them comes from the network.`));
      return;
    }
    if (changes.same) {
      section.append(note('Both methodologies are the same: nothing that scores a test changes between them.'));
      return;
    }
    const tiles = element('div', 'scoring-impact-tiles');
    for (const [kind, label] of [['added', 'New KPIs'], ['removed', 'Removed KPIs'], ['points', 'Other points'], ['thresholds', 'Other thresholds'],
      ['calculation', 'Other formula or filters'], ['scoring', 'Other score mapping'], ['definition', 'Other definition'], ['unchanged', 'Unchanged KPIs']]) {
      const count = changes.counts[kind] || 0;
      if (!count && !['added', 'removed', 'unchanged'].includes(kind)) continue;
      const tile = element('div', 'scoring-impact-tile', element('strong', '', number(count, 0)), element('span', '', label));
      tile.dataset.kind = kind;
      tiles.append(tile);
    }
    section.append(tiles);
    const palette = ctx.theme?.categories || ['#4472C4', '#7030A0', '#C55A11', '#5B9BD5', '#A64D79', '#548235'];
    section.append(element('h5', 'scoring-impact-subtitle', 'Points of each category'), allocationBars(changes.categories, doc, palette));
    const moved = changes.categories.filter(row => Math.abs(row.delta) >= NO_CHANGE);
    section.append(note(moved.length
      ? moved.map(row => `${row.category}: ${number(row.before, 2)} → ${number(row.after, 2)}`).join(' · ')
      : 'Every category keeps its points: a KPI that gives or takes points shares them within its category.'));
    if (changes.environments.some(row => Math.abs(row.delta) >= NO_CHANGE)) {
      section.append(element('h5', 'scoring-impact-subtitle', 'Points of each environment'), allocationBars(changes.environments, doc, palette, 'label'));
    }
    if (changes.settings.length) {
      section.append(element('h5', 'scoring-impact-subtitle', 'General settings'), detailLines(changes.settings));
    }
    if (changes.kpis.length) {
      section.append(element('h5', 'scoring-impact-subtitle', 'The KPIs that change'));
      const table = element('table', 'scoring-insight-table scoring-impact-matrix');
      table.createTHead().insertRow().append(...['KPI', 'Category', 'What changes', 'Points', 'Changes'].map(text => element('th', '', text)));
      const body = table.createTBody();
      for (const row of changes.kpis) {
        const line = body.insertRow();
        line.dataset.status = row.status;
        line.insertCell().append(kpiLabel(row));
        line.insertCell().append(row.category || '');
        line.insertCell().append(kindChips(row.kinds, changes.kinds));
        const points = line.insertCell();
        points.className = 'scoring-insight-number';
        points.textContent = `${number(row.before, 2)} → ${number(row.after, 2)}`;
        line.insertCell().append(detailLines(row.details));
      }
      section.append(element('div', 'scoring-insight-table-wrap', table));
    }
  }

  function scoringPanel(pane, doc, part, chosen, ctx) {
    const section = ctx.insightSection(pane, 'Impact on the scoring: each operator in All Environments and in each environment', 'scoring-impact-scoring-card', false);
    const combined = part.scoring.Combined || part.scoring[part.environments[0]?.name];
    const operators = part.operators.filter(item => chosen.includes(item.operator));
    if (combined) {
      const scale = Math.max(...operators.map(item => Math.abs(Number(combined.operators[item.operator]?.delta) || 0)), 0);
      const cards = element('div', 'scoring-impact-cards');
      const ordered = [...operators].sort((left, right) => (combined.operators[left.operator]?.rank_after ?? 99) - (combined.operators[right.operator]?.rank_after ?? 99));
      for (const item of ordered) {
        const cell = combined.operators[item.operator];
        if (!cell) continue;
        const tone = toneOf(cell.delta);
        const color = ctx.safeHexColor(item.color);
        const moved = (cell.rank_before || 0) - (cell.rank_after || 0);
        const rank = element('span', `scoring-impact-rank is-${moved > 0 ? 'gain' : moved < 0 ? 'loss' : 'flat'}`,
          cell.rank_before && cell.rank_after && moved ? `${ordinal(cell.rank_before)} → ${ordinal(cell.rank_after)}` : (cell.rank_after ? ordinal(cell.rank_after) : ''));
        const card = element('article', 'scoring-impact-card',
          element('header', '', element('strong', '', `${item.label}${item.is_reference ? ' (reference)' : ''}`), rank),
          element('div', `scoring-impact-big is-${tone}`, signed(cell.delta)),
          track(cell.delta, scale, tone),
          element('small', '', `${number(cell.before, 1)} → ${number(cell.after, 1)} of ${number(combined.max_after, 0)} points`));
        if (color) card.style.setProperty('--operator-color', color);
        cards.append(card);
      }
      section.append(element('h5', 'scoring-impact-subtitle', 'All Environments'), cards);
    }
    const environments = part.environments.filter(item => item.name !== 'Combined');
    if (environments.length) {
      section.append(element('h5', 'scoring-impact-subtitle', 'Each environment'));
      const rows = environments.map(item => ({
        label: element('div', 'scoring-impact-label', element('strong', '', item.label),
          element('small', '', `Maximum ${number(part.scoring[item.name]?.max_before, 0)} → ${number(part.scoring[item.name]?.max_after, 0)} points`)),
        cells: part.scoring[item.name]?.operators || {},
      }));
      section.append(matrix('Environment', operators, rows, ctx));
    }
    section.append(note('Each difference is the points of the operator with the second methodology minus those with the first one, on the same tests, so it comes from the methodology alone.'));
  }

  function bridgePanel(pane, doc, part, chosen, environment, ctx) {
    const rows = part.bridge?.[environment];
    if (!rows || !doc.earlier) return;
    const section = ctx.insightSection(pane, `From ${doc.earlier.campaign_label} to ${doc.after.campaign_label}: what the network changed and what the methodology changed`, 'scoring-impact-bridge-card', false);
    const operators = part.operators.filter(item => chosen.includes(item.operator) && rows[item.operator]);
    const scale = Math.max(0, ...operators.flatMap(item => [rows[item.operator].network, rows[item.operator].methodology].map(value => Math.abs(Number(value) || 0))));
    const table = element('table', 'scoring-insight-table scoring-impact-matrix scoring-impact-bridge');
    table.createTHead().insertRow().append(...['Operator', `${doc.earlier.campaign_label} (${doc.before.profile_name})`, 'The network changed', 'The methodology changed', `${doc.after.campaign_label} (${doc.after.profile_name})`, 'Total'].map(text => element('th', '', text)));
    const body = table.createTBody();
    const change = (value) => {
      const box = element('td', 'scoring-impact-cell');
      const tone = toneOf(value);
      box.dataset.tone = tone;
      box.append(element('span', 'scoring-impact-head', element('b', `is-${tone}`, signed(value))), track(value, scale, tone));
      return box;
    };
    for (const item of operators) {
      const row = rows[item.operator];
      const line = body.insertRow();
      const name = element('strong', '', `${item.label}${item.is_reference ? ' (reference)' : ''}`);
      const color = ctx.safeHexColor(item.color);
      if (color) name.style.color = color;
      line.insertCell().append(name);
      const start = line.insertCell();
      start.className = 'scoring-insight-number';
      start.textContent = number(row.earlier, 1);
      line.append(change(row.network), change(row.methodology));
      const end = line.insertCell();
      end.className = 'scoring-insight-number';
      end.textContent = number(row.latest, 1);
      const total = line.insertCell();
      total.className = `scoring-insight-number is-${toneOf(row.total)}`;
      total.textContent = signed(row.total);
    }
    section.append(element('div', 'scoring-insight-table-wrap', table),
      note(`The network: ${doc.after.campaign_label} scored with ${doc.before.profile_name} minus ${doc.earlier.campaign_label} as it was scored. The methodology: ${doc.after.campaign_label} with ${doc.after.profile_name} minus the same tests with ${doc.before.profile_name}.`));
  }

  function categoryPanel(pane, part, chosen, environment, ctx) {
    const rows = part.categories[environment] || [];
    if (!rows.length) return;
    const section = ctx.insightSection(pane, 'Impact per category', 'scoring-impact-category-card', false);
    const operators = part.operators.filter(item => chosen.includes(item.operator));
    const scoring = part.scoring[environment];
    const total = scoring ? {
      label: element('strong', '', 'Total'), cells: scoring.operators,
    } : null;
    section.append(matrix('Category', operators, rows.map(row => ({
      label: element('div', 'scoring-impact-label', element('strong', '', row.category),
        element('small', '', `${row.service} · maximum ${number(row.max_before, 1)} → ${number(row.max_after, 1)}`)),
      cells: row.operators,
    })), ctx, {total}));
    section.append(note('The points of each category with both methodologies; the colour and bar show the difference, against the largest of the table.'));
  }

  function kpiPanel(pane, part, chosen, environment, ctx) {
    const all = part.kpis[environment] || [];
    const rows = all.filter(row => (row.kinds || []).length || row.peak >= NO_CHANGE);
    if (!rows.length) {
      ctx.insightSection(pane, 'KPIs affected', 'scoring-impact-kpi-card', false).append(note('No KPI changes.'));
      return;
    }
    const section = ctx.insightSection(pane, `KPIs affected: ${rows.length} of ${all.length}, those that move most first`, 'scoring-impact-kpi-card', false);
    const operators = part.operators.filter(item => chosen.includes(item.operator));
    const titleOf = (item, cell) => (cell ? `${item.label}\nKPI value: ${number(cell.value_before, 2)} → ${number(cell.value_after, 2)}\nScore: ${number((cell.score_before ?? NaN) * 100, 1)}% → ${number((cell.score_after ?? NaN) * 100, 1)}%` : '');
    section.append(pagedRows(`kpis:${environment}`, rows, shown => matrix('KPI', operators, shown.map(row => ({
      label: kpiLabel(row, element('small', '', `${row.category} · maximum ${number(row.max_before, 1)} → ${number(row.max_after, 1)}`)),
      extra: [kindChips(row.kinds, part.changes.kinds)], cells: row.operators, titleOf,
    })), ctx, {extraHeaders: ['What changes']})));
    section.append(note('A KPI one methodology does not have counts none there. Hover a cell for the value and the score of the KPI with both methodologies.'));
  }

  function areaPanel(pane, part, chosen, environment, ctx) {
    const levels = Object.keys(part.areas || {});
    const section = ctx.insightSection(pane, 'Impact per geographical area', 'scoring-impact-area-card', false);
    if (!levels.length) {
      section.append(note('The CDRs of this campaign have no Region, Cluster or City.'));
      return;
    }
    const level = levels.includes(areaLevel) ? areaLevel : levels[0];
    const selector = element('label', 'scoring-environment-filter scoring-insight-select', 'Area');
    const select = element('select');
    for (const name of levels) {
      const option = element('option', '', name);
      option.value = name;
      select.append(option);
    }
    select.value = level;
    selector.append(select);
    const body = element('div');
    const draw = (name) => {
      const rows = part.areas[name]?.[environment] || [];
      const operators = part.operators.filter(item => chosen.includes(item.operator));
      const swaps = rows.filter(row => row.leader_before !== row.leader_after);
      const labels = Object.fromEntries(part.operators.map(item => [item.operator, item.label]));
      body.replaceChildren(pagedRows(`areas:${name}:${environment}`, rows, shown => matrix(name, operators, shown.map(row => ({
        label: element('strong', '', row.area), cells: row.operators,
        extra: [row.leader_before === row.leader_after ? element('span', 'scoring-impact-leader', labels[row.leader_after] || row.leader_after || '')
          : element('span', 'scoring-impact-leader is-changed', `${labels[row.leader_before] || row.leader_before} → ${labels[row.leader_after] || row.leader_after}`)],
      })), ctx, {extraHeaders: ['Leader']})),
      note(`${rows.length} ${name} areas, those that move most first; the leader changes in ${swaps.length}. They are scored on the whole country, as the Geographical Areas; in All Environments the environments measured in an area are scaled to the full maximum.`));
    };
    select.addEventListener('change', () => {
      areaLevel = select.value;
      draw(areaLevel);
    });
    draw(level);
    section.append(ctx.insightControls(selector), body);
  }

  function gapPanel(pane, part, chosen, environment, ctx) {
    const gap = part.gap[environment];
    if (!gap) return;
    const reference = part.operators.find(item => item.is_reference);
    const section = ctx.insightSection(pane, `Impact on the GAP Analysis against ${reference?.label || part.reference}`, 'scoring-impact-gap-card', false);
    const operators = part.operators.filter(item => chosen.includes(item.operator) && !item.is_reference);
    if (!operators.length) {
      section.append(note('Enable an operator other than the reference to see its GAP.'));
      return;
    }
    const total = {label: element('strong', '', 'Total GAP'), cells: gap.total};
    section.append(matrix('Category', operators, gap.categories.map(row => ({
      label: element('strong', '', row.category), cells: row.operators,
    })), ctx, {total}));
    const kpis = gap.kpis.filter(row => row.peak >= NO_CHANGE);
    if (kpis.length) {
      section.append(element('h5', 'scoring-impact-subtitle', 'The KPIs whose GAP moves most'),
        pagedRows(`gap:${environment}`, kpis, shown => matrix('KPI', operators, shown.map(row => ({
          label: kpiLabel(row, element('small', '', row.category)), cells: row.operators,
        })), ctx)));
    }
    section.append(note('Operator minus reference, before → after; the bar shows how much the GAP moves. Changes side: the operator goes from ahead of the reference to behind it, or the other way round.'));
  }

  function pointsPanel(pane, part, chosen, environment, ctx) {
    const lost = part.points_lost[environment];
    if (!lost) return;
    const section = ctx.insightSection(pane, 'Impact on the Points Lost', 'scoring-impact-points-card', false);
    const operators = part.operators.filter(item => chosen.includes(item.operator) && lost.operators[item.operator]);
    const shown = lost.kinds.filter(kind => (kind.kpis || []).length || operators.some(item => lost.operators[item.operator].parts_before?.[kind.key] || lost.operators[item.operator].parts_after?.[kind.key]));
    const [notCompleted, minimum, below, quality] = ctx.theme?.stake || ['#6e1222', '#a51c30', '#e8414f', '#f4a3aa'];
    const colours = {not_completed: notCompleted, below_minimum: minimum, below_par: below, quality};
    const peak = Math.max(1, ...operators.flatMap(item => [lost.operators[item.operator].before, lost.operators[item.operator].after].map(value => Number(value) || 0)));
    const bar = (parts) => {
      const box = element('span', 'scoring-impact-stack');
      for (const kind of shown) {
        const value = Number(parts?.[kind.key]) || 0;
        if (value <= 0) continue;
        const segment = element('i', '', value / peak > .08 ? number(value, 0) : '');
        segment.style.width = `${value / peak * 100}%`;
        segment.style.background = colours[kind.key];
        segment.title = `${kind.label}: ${number(value, 2)} points`;
        box.append(segment);
      }
      return box;
    };
    const list = element('div', 'scoring-impact-lost');
    for (const item of operators) {
      const row = lost.operators[item.operator];
      const name = element('strong', '', `${item.label}${item.is_reference ? ' (reference)' : ''}`);
      const color = ctx.safeHexColor(item.color);
      if (color) name.style.color = color;
      const tone = toneOf(row.delta, true);
      list.append(element('div', 'scoring-impact-lost-row', name,
        element('div', 'scoring-impact-lost-bars', bar(row.parts_before), bar(row.parts_after)),
        element('div', 'scoring-impact-lost-total', element('b', `is-${tone}`, signed(row.delta)), element('small', '', `${number(row.before, 1)} → ${number(row.after, 1)} lost`))));
    }
    const legend = element('div', 'scoring-location-legend');
    for (const kind of shown) {
      const swatch = element('i');
      swatch.style.background = colours[kind.key];
      legend.append(element('span', '', swatch, kind.label));
    }
    section.append(list, legend, note('In each operator, the upper bar is the first methodology and the lower one the second.'));
    const inScope = part.operators.filter(item => chosen.includes(item.operator));
    section.append(element('h5', 'scoring-impact-subtitle', 'Points lost per category'),
      matrix('Category', inScope, lost.categories.map(row => ({label: element('strong', '', row.category), cells: row.operators})), ctx, {inverse: true}));
    const kpis = lost.kpis.filter(row => row.peak >= NO_CHANGE);
    if (kpis.length) {
      section.append(element('h5', 'scoring-impact-subtitle', 'The KPIs whose points lost move most'),
        pagedRows(`lost:${environment}`, kpis, rows => matrix('KPI', inScope, rows.map(row => ({
          label: kpiLabel(row, element('small', '', row.category)), cells: row.operators,
        })), ctx, {inverse: true})));
    }
    section.append(note('More points lost are shown in the colour of a loss. The points lost of a KPI are its maximum minus the points scored, so they also move when the methodology gives it another maximum.'));
  }

  function comparisonBanner(doc, part) {
    const side = (title, summary) => element('div', 'scoring-impact-side', element('span', '', title), element('strong', '', summary.profile_name));
    const box = element('div', 'scoring-impact-banner', side('First methodology', doc.before), element('span', 'scoring-impact-arrow', '→'), side('Second methodology', doc.after),
      element('div', 'scoring-impact-side', element('span', '', 'Tests scored'), element('strong', '', `${doc.after.campaign_label} · ${doc.nr_mode}`)),
      element('div', 'scoring-impact-side', element('span', '', 'GAP reference'), element('strong', '', part.operators.find(item => item.is_reference)?.label || part.reference)));
    return box;
  }

  function draw(body, doc, ctx) {
    // (A scoring that one of the methodologies does not have is not compared: Best Network is.)
    const scoring = doc.scorings[ctx.scoring] ? ctx.scoring : 'best_network';
    const part = doc.scorings[scoring];
    const environments = part.environments.map(item => item.name);
    const environment = environments.includes(ctx.environment) ? ctx.environment : (environments.includes('Combined') ? 'Combined' : environments[0]);
    body.replaceChildren();
    if (!environment) {
      body.append(element('div', 'scoring-empty', 'These tests have no results in the environments of either methodology.'));
      return;
    }
    const {control, chosen} = ctx.insightOperatorChips('impact-operators', part.operators, {all: true});
    chosenOperators = chosen;
    const head = ctx.insightSection(body, `Methodology Impact${scoring === 'most_reliable' ? ' — Most Reliable Network' : ''}`, 'scoring-impact-head-card', false);
    head.append(comparisonBanner(doc, part));
    if (part.takeaways.length || doc.notes.length) {
      head.append(element('ul', 'scoring-impact-takeaways', ...[...part.takeaways, ...doc.notes].map(text => element('li', '', text))));
    }
    if (scoring !== ctx.scoring) head.append(note('The Most Reliable scoring is not compared: one of the methodologies does not have it. This is the Best Network scoring.'));
    head.append(ctx.insightControls(control));
    changesPanel(body, doc, part, ctx);
    scoringPanel(body, doc, part, chosen, ctx);
    bridgePanel(body, doc, part, chosen, environment, ctx);
    categoryPanel(body, part, chosen, environment, ctx);
    kpiPanel(body, part, chosen, environment, ctx);
    areaPanel(body, part, chosen, environment, ctx);
    gapPanel(body, part, chosen, environment, ctx);
    pointsPanel(body, part, chosen, environment, ctx);
  }

  function progressCard(body, state) {
    const percent = Math.max(2, Math.min(100, Number(state.progress) || 0));
    const fill = element('span');
    fill.style.width = `${percent}%`;
    body.replaceChildren(element('div', 'scoring-impact-progress', element('strong', '', 'Scoring the tests with both methodologies'),
      element('span', 'scoring-impact-progress-bar', fill), element('small', '', state.message || 'Waiting')));
  }

  function controlsBar(offered, selection, ctx, onChange) {
    // Each NR Mode has campaigns of its own.
    const set = (key, value) => onChange({...selection, [key]: value, ...(key === 'nr_mode' ? offered.by_nr_mode[value] : {})});
    const field = (label, key, entries) => {
      const wrapper = element('label', 'scoring-environment-filter scoring-insight-select', label);
      const select = element('select');
      select.dataset.impactField = key;
      for (const [value, text] of entries) {
        const option = element('option', '', text);
        option.value = value;
        select.append(option);
      }
      select.value = selection[key];
      select.addEventListener('change', () => set(key, select.value));
      wrapper.append(select);
      return wrapper;
    };
    const entries = (offered.campaigns[selection.nr_mode] || []).map(entry => [entry.value, `${entry.label} · ${entry.methodology_name}`]);
    const box = element('section', 'scoring-result-card scoring-impact-controls');
    const modes = element('div', 'scoring-impact-mode');
    modes.setAttribute('role', 'group');
    modes.setAttribute('aria-label', 'What to compare');
    for (const [value, text] of [['campaigns', 'Two campaigns'], ['methodologies', 'Two methodologies']]) {
      const button = element('button', '', text);
      button.type = 'button';
      button.setAttribute('aria-pressed', String(selection.mode === value));
      button.addEventListener('click', () => set('mode', value));
      modes.append(button);
    }
    const fields = element('div', 'scoring-loss-controls');
    fields.append(modes);
    if (offered.nr_modes.length > 1) fields.append(field('NR Mode', 'nr_mode', offered.nr_modes.map(mode => [mode, mode])));
    if (selection.mode === 'campaigns') {
      fields.append(field('From campaign', 'campaign_a', entries), field('To campaign', 'campaign_b', entries));
    } else {
      const methodologies = offered.methodologies.map(item => [item.id, item.name]);
      fields.append(field('First methodology', 'methodology_a', methodologies), field('Second methodology', 'methodology_b', methodologies),
        field('Tests of the campaign', 'campaign', entries));
    }
    const exports = element('div', 'scoring-impact-exports');
    for (const [kind, label] of [['csv', 'CSV'], ['ppt', 'PowerPoint'], ['word', 'Word']]) {
      const link = element('a', '', `Export to ${label}`);
      link.href = '#';
      link.dataset.impactExport = kind;
      link.title = `The Methodology Impact shown below as ${label}`;
      link.setAttribute('aria-disabled', 'true');
      link.addEventListener('click', (event) => {
        event.preventDefault();
        if (link.getAttribute('aria-disabled') === 'true') return;
        const extra = {environment: ctx.environment || 'Combined', scoring: ctx.scoring, theme: ctx.theme?.id || ''};
        if (chosenOperators) extra.operators = JSON.stringify(chosenOperators);
        ctx.download(`/scoring/saved-filters/${encodeURIComponent(ctx.savedFilterId)}/impact/export/${kind}?${queryOf(selection, extra)}`, label);
      });
      exports.append(link);
    }
    box.append(fields, exports);
    return box;
  }

  function showError(body, message, retry = null) {
    const box = element('div', 'scoring-empty scoring-impact-error', message);
    if (retry) {
      const button = element('button', 'scoring-impact-more', 'Calculate again');
      button.type = 'button';
      button.addEventListener('click', retry);
      box.append(button);
    }
    body.replaceChildren(box);
  }

  async function load(pane, body, bar, selection, ctx, token, retry = false) {
    window.clearTimeout(pollTimer);
    // (Another Saved Filter is shown, or the results are being calculated again.)
    if (!pane.contains(body)) return;
    const query = queryOf(selection, retry ? {retry: 'true'} : {});
    const cacheKey = `${ctx.savedFilterId}|${queryOf(selection)}`;
    const setExports = (enabled) => bar.querySelectorAll('[data-impact-export]').forEach((link) => {
      link.setAttribute('aria-disabled', String(!enabled));
    });
    const cached = impacts.get(cacheKey);
    if (cached && !retry) {
      setExports(true);
      draw(body, cached, ctx);
    }
    let state;
    try {
      state = await ctx.requestJson(`/api/scoring/saved-filters/${encodeURIComponent(ctx.savedFilterId)}/impact?${query}`);
    } catch (error) {
      if (token === renderToken) showError(body, error.message || 'The Methodology Impact could not be calculated.');
      return;
    }
    if (token !== renderToken || !pane.contains(body)) return;
    if (state.status === 'completed' && state.impact) {
      const same = cached && cached.key === state.impact.key;
      impacts.set(cacheKey, state.impact);
      setExports(true);
      if (!same) draw(body, state.impact, ctx);
      return;
    }
    setExports(false);
    if (state.status === 'failed') {
      showError(body, `The Methodology Impact could not be calculated: ${state.error}`, () => load(pane, body, bar, selection, ctx, token, true));
      return;
    }
    progressCard(body, state);
    if (!pane.hidden) pollTimer = window.setTimeout(() => load(pane, body, bar, selection, ctx, token), POLL_MS);
  }

  async function render(pane, ctx) {
    const token = ++renderToken;
    window.clearTimeout(pollTimer);
    if (!ctx.savedFilterId) {
      pane.replaceChildren(element('div', 'scoring-empty', 'No Saved Filter is selected.'));
      return;
    }
    let offered = options.get(ctx.savedFilterId);
    if (!offered) {
      pane.replaceChildren(element('div', 'scoring-empty', 'Loading the Methodology Impact…'));
      try {
        offered = await ctx.requestJson(`/api/scoring/saved-filters/${encodeURIComponent(ctx.savedFilterId)}/impact/options`);
      } catch (error) {
        if (token === renderToken) pane.replaceChildren(element('div', 'scoring-empty', error.message || 'The Methodology Impact could not be opened.'));
        return;
      }
      if (token !== renderToken) return;
      options.set(ctx.savedFilterId, offered);
    }
    // (Its cards are styled as those of the panes.)
    const body = element('div', 'scoring-impact-body scoring-nr-mode-body');
    const open = (selection) => {
      rememberSelection(ctx.savedFilterId, selection);
      const current = renderToken;
      const bar = controlsBar(offered, selection, ctx, (next) => {
        renderToken += 1;
        open(next);
      });
      pane.replaceChildren(bar, body);
      progressCard(body, {progress: 2, message: 'Looking for this comparison'});
      load(pane, body, bar, selection, ctx, current);
    };
    open(selectionOf(ctx.savedFilterId, offered));
  }

  window.ScoringImpact = {render};
})();
