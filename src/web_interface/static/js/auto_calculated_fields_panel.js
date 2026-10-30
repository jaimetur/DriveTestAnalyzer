/* Workspace Config → Auto-calculated Fields: one card per field with the CDR types it applies to and the state of their
   tables, the values it gives in the CDRs, the fields it is worked out from, what it takes when no rule applies and where
   it is used. A card opens its field in the editor of the fields (auto_calculated_fields.js). */
(() => {
  'use strict';

  const host = document.querySelector('[data-acf-panel]');
  if (!host) return;

  const API = '/api/workspace/auto-calculated-fields';
  const STATES = {up_to_date: 'Up to date', updating: 'Updating', pending: 'Waiting for an update'};
  // The values of a field from the one with most rows: the shades of the Auto-calculated Fields, darkest first.
  const SHADES = ['#4b2478', '#62379a', '#7a4fb6', '#9370c8', '#ab92d6', '#c2b0e2', '#d3c5ea', '#e3d9f2'];
  const ICONS = {
    rules: '<path d="M14 4h-1a3 3 0 0 0-3 3v10a3 3 0 0 1-3 3H6M7 11h7"/><path d="m15 13 5 5m0-5-5 5"/>',
    up_to_date: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    updating: '<path d="M20 11a8 8 0 1 0 1.2 5.2M20 4v7h-7"/>',
    pending: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    failed: '<path d="M12 4 2.8 20h18.4zM12 10v4.5M12 17.4v.1"/>',
  };
  const number = new Intl.NumberFormat('en-GB');

  const cardsHost = host.querySelector('[data-acf-panel-cards]');
  const empty = host.querySelector('[data-acf-panel-empty]');
  const search = host.querySelector('[data-acf-panel-search]');
  const typeButtons = [...host.querySelectorAll('[data-acf-panel-type]')];
  const tables = host.querySelector('[data-acf-panel-tables]');
  const count = document.querySelector('[data-acf-panel-count]');
  const more = host.querySelector('[data-acf-panel-more]');
  const menu = host.querySelector('[data-acf-panel-menu]');
  const importForm = host.querySelector('[data-acf-panel-import-form]');
  const rematerialize = host.querySelector('[data-acf-panel-rematerialize]');
  const canEdit = host.hasAttribute('data-can-edit');

  const parse = (text) => { try { return JSON.parse(text || '[]'); } catch (_error) { return []; } };
  let fields = parse(host.dataset.fields);
  let insights = null; // {usage, shares} once read (shares null when the CDRs could not be read)
  let insightsToken = 0;
  let job = {active: false, percent: 0, failed: ''}; // the update of the CDR tables, from /materialization
  let pollTimer = 0;

  const el = (tag, className = '', text = '') => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  };
  const icon = (name, className = '') => {
    const node = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    node.setAttribute('viewBox', '0 0 24 24');
    node.setAttribute('aria-hidden', 'true');
    if (className) node.setAttribute('class', className);
    node.innerHTML = ICONS[name];
    return node;
  };
  const plural = (amount, one, many = `${one}s`) => `${number.format(amount)} ${amount === 1 ? one : many}`;
  const share = (rows, total) => {
    const percent = total ? rows * 100 / total : 0;
    if (percent > 0 && percent < 0.1) return '<0.1%';
    return `${percent >= 10 || percent === 0 ? Math.round(percent) : percent.toFixed(1)}%`;
  };
  // What a field gives when no rule applies: the value of other fields, a fixed value, or nothing.
  const otherwise = (field) => {
    const fixed = field.default ? `“${field.default}”` : '';
    if (field.default_from.length) return `The value of ${field.default_from.join(' or ')}${fixed ? `, else ${fixed}` : ''}`;
    return fixed || 'No value';
  };
  // What decides whether a card is shown again: the definitions, not the state of their tables.
  const definitions = (list) => JSON.stringify(list.map(({state, ...field}) => field));

  // ---- the values a field gives: their rows in all the CDRs of its types, most first
  function valueShares(field) {
    const bySource = insights?.shares?.[field.key];
    if (!bySource || !Object.keys(bySource).length) return null;
    const rows = new Map();
    let total = 0; let tried = 0; let other = 0; let none = 0;
    Object.values(bySource).forEach((source) => {
      total += source.rows; tried += source.tried; other += source.other; none += source.empty;
      source.values.forEach((item) => rows.set(item.value, (rows.get(item.value) || 0) + item.rows));
    });
    const values = [...rows].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
    // A card names as many values as one CDR type does; the rest of every type go together.
    values.slice(SHADES.length).forEach(([, value]) => { other += value; });
    return {total, tried, other, none, values: values.slice(0, SHADES.length)};
  }

  function valuesBlock(field) {
    const block = el('div', 'acf-card-values');
    const shares = valueShares(field);
    if (shares && shares.total) {
      const bar = el('div', 'acf-card-bar');
      const legend = el('ul', 'acf-card-legend');
      const segments = [
        ...shares.values.map(([value, rows], index) => ({label: value, rows, colour: SHADES[index]})),
        ...(shares.other ? [{label: 'Other values', rows: shares.other, className: 'is-other'}] : []),
        ...(shares.none ? [{label: 'No value', rows: shares.none, className: 'is-none'}] : []),
      ];
      segments.forEach((segment) => {
        const part = el('span', segment.className || '');
        part.style.flexGrow = String(segment.rows);
        if (segment.colour) part.style.background = segment.colour;
        part.title = `${segment.label}: ${share(segment.rows, shares.total)} (${number.format(segment.rows)} rows)`;
        bar.append(part);
        const item = el('li', segment.className || '');
        const swatch = el('i');
        if (segment.colour) swatch.style.background = segment.colour;
        item.append(swatch, el('span', 'acf-card-legend-value', segment.label), el('b', '', share(segment.rows, shares.total)));
        item.title = part.title;
        legend.append(item);
      });
      bar.setAttribute('role', 'img');
      bar.setAttribute('aria-label', segments.map((segment) => `${segment.label} ${share(segment.rows, shares.total)}`).join(', '));
      block.title = `Rows of the ${number.format(shares.total)} of its CDRs, worked out on ${number.format(shares.tried)} of them as the editor tries the fields.`;
      block.append(bar, legend);
      return block;
    }
    // Until the values of the CDRs are read (or without CDRs): the values its rules give.
    const chips = el('div', 'acf-card-value-chips');
    field.values.slice(0, 10).forEach((value) => chips.append(el('span', '', value)));
    if (field.values.length > 10) chips.append(el('span', 'is-more', `+${field.values.length - 10}`));
    if (field.values.length) block.append(chips);
    const note = !insights ? 'Reading the values in the CDRs…'
      : insights.shares === null ? 'The values in the CDRs could not be read.'
        : 'No CDR of its types to read its values from yet.';
    block.append(el('p', `acf-card-values-note${insights ? '' : ' is-loading'}`, note));
    return block;
  }

  function usage(field) {
    const foot = el('footer', 'acf-card-foot');
    if (!insights) { foot.append(el('span', 'is-loading', 'Finding where it is used…')); return foot; }
    const places = insights.usage?.[field.key];
    if (!places) return foot;
    const kinds = [['templates', 'PPT Template'], ['designs', 'PPT Design'], ['queries', 'Query', 'Queries'], ['fields', 'Field']];
    const used = kinds.filter(([kind]) => (places[kind] || []).length);
    if (!used.length) { foot.append(el('span', 'is-unused', 'Not used yet')); return foot; }
    foot.append(el('span', 'acf-card-foot-label', 'Used in'));
    used.forEach(([kind, one, many]) => {
      const names = places[kind];
      const badge = el('span', `acf-card-use is-${kind}`, plural(names.length, one, many));
      badge.title = names.join('\n');
      foot.append(badge);
    });
    return foot;
  }

  function card(field) {
    const article = el('article', `acf-card is-${field.state}`);
    article.dataset.acfCard = field.name;
    article.tabIndex = 0;
    article.setAttribute('role', 'button');
    article.setAttribute('aria-label', `${canEdit ? 'Edit' : 'Open'} ${field.name}`);

    const head = el('header', 'acf-card-head');
    head.append(icon('rules', 'acf-card-icon'), el('h3', 'acf-card-name', field.name),
      el('span', 'acf-card-kind', field.kind === 'formula' ? 'Formula' : plural(field.rules, 'rule')));

    const types = el('div', 'acf-card-types');
    types.append(el('span', 'acf-card-label', 'Applies to'));
    const chips = el('div', 'acf-card-type-list');
    field.sources.forEach((source) => {
      const chip = el('span', `acf-type acf-type-${source.slice(4)} is-${field.state}`);
      chip.append(icon(field.state), document.createTextNode(source.toUpperCase()));
      if (field.state === 'updating' && job.active) chip.append(el('b', '', `${job.percent}%`));
      const rows = insights?.shares?.[field.key]?.[source]?.rows;
      chip.title = `${source.toUpperCase()}: ${STATES[field.state]}${rows ? ` · ${number.format(rows)} rows` : ''}`;
      chips.append(chip);
    });
    types.append(chips);

    const facts = el('dl', 'acf-card-facts');
    [['From', field.inputs.join(', ') || 'No CDR field'], ['When no rule applies', otherwise(field)]].forEach(([term, value]) => {
      const row = el('div');
      row.append(el('dt', '', term), el('dd', '', value));
      facts.append(row);
    });

    article.append(head, types, valuesBlock(field), facts, usage(field));
    return article;
  }

  // ---- the panel
  function matches(field) {
    const chosen = typeButtons.filter((item) => item.getAttribute('aria-pressed') === 'true').map((item) => item.dataset.acfPanelType);
    if (chosen.length && !field.sources.some((source) => chosen.includes(source))) return false;
    const words = String(search?.value || '').trim().toLowerCase().split(/\s+/).filter(Boolean);
    const read = Object.values(insights?.shares?.[field.key] || {}).flatMap((source) => source.values.map((item) => item.value));
    const text = [field.name, ...field.values, ...read, ...field.inputs, ...field.default_from, field.default, ...field.sources].join(' ').toLowerCase();
    return words.every((word) => text.includes(word));
  }

  function renderTables() {
    if (!tables) return;
    const updating = fields.filter((field) => field.state === 'updating').length;
    const pending = fields.filter((field) => field.state === 'pending').length;
    const [state, text] = updating || job.active ? ['updating', `Updating CDR tables${job.active ? ` · ${job.percent}%` : ''}`]
      : pending ? ['pending', `${plural(pending, 'field')} waiting for an update`]
        : job.failed ? ['failed', job.failed]
          : ['up_to_date', 'All CDR tables up to date'];
    tables.className = `acf-panel-tables is-${state}`;
    tables.replaceChildren(icon(state), document.createTextNode(text));
    // As in CDR Tables Updates: not while an update of the CDR tables runs.
    if (rematerialize) rematerialize.disabled = job.active;
  }

  function render() {
    const shown = fields.filter(matches);
    cardsHost.replaceChildren(...shown.map(card));
    if (empty) {
      empty.hidden = shown.length > 0;
      empty.textContent = fields.length ? 'No field matches the search or the CDR types chosen.'
        : `This workspace has no Auto-calculated Fields yet.${canEdit ? ' New Field creates the first one.' : ''}`;
    }
    if (count) count.textContent = plural(fields.length, 'field');
    renderTables();
  }

  async function loadInsights() {
    const token = ++insightsToken;
    insights = null;
    render();
    let payload;
    try {
      const response = await fetch(`${API}/insights`, {credentials: 'same-origin', cache: 'no-store'});
      payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || 'The CDRs could not be read.');
    } catch (_error) {
      payload = {usage: null, shares: null};
    }
    if (token !== insightsToken) return;
    insights = payload;
    render();
  }

  async function refreshCards() {
    const response = await fetch(`${API}/cards`, {credentials: 'same-origin', cache: 'no-store'});
    if (!response.ok) return false;
    const next = (await response.json().catch(() => ({}))).fields || [];
    if (JSON.stringify(next) === JSON.stringify(fields)) return false;
    const changed = definitions(next) !== definitions(fields);
    fields = next;
    host.dataset.fields = JSON.stringify(fields);
    if (changed) void loadInsights();
    else render();
    return true;
  }

  // The state of the CDR tables, as CDR Tables Updates in Workspace shows it: often while they are updated.
  async function poll() {
    window.clearTimeout(pollTimer);
    try {
      const response = await fetch(`${API}/materialization`, {credentials: 'same-origin', cache: 'no-store'});
      const payload = await response.json().catch(() => ({}));
      if (response.ok) {
        const jobs = Array.isArray(payload.jobs) && payload.jobs.length ? payload.jobs : [payload];
        const running = jobs.find((item) => item.status === 'processing') || jobs.find((item) => item.status === 'queued');
        const percent = running?.status === 'processing' && Number(running.total) > 0
          ? Math.min(99, Math.round(Number(running.completed || 0) * 100 / Number(running.total))) : 0;
        const next = {
          active: Boolean(running), percent,
          failed: running ? '' : payload.status === 'failed' ? 'The last update of the CDR tables failed'
            : payload.status === 'stopped' ? 'The last update of the CDR tables was stopped' : '',
        };
        const settled = !next.active && !job.active && fields.every((field) => field.state === 'up_to_date');
        const before = JSON.stringify(job);
        job = next;
        const redrawn = settled ? false : await refreshCards();
        if (!redrawn && before !== JSON.stringify(job)) render();
      }
    } catch (_error) {
      // The next poll tries again.
    }
    const busy = job.active || fields.some((field) => field.state !== 'up_to_date');
    pollTimer = window.setTimeout(poll, busy ? 1500 : 8000);
  }

  const openEditor = (focus = '') => window.AutoCalculatedFields?.open({
    focus,
    onChange: () => { void refreshCards().then(() => poll()); },
  });

  cardsHost.addEventListener('click', (event) => {
    const target = event.target instanceof Element ? event.target.closest('[data-acf-card]') : null;
    if (target) openEditor(target.dataset.acfCard);
  });
  cardsHost.addEventListener('keydown', (event) => {
    const target = event.target instanceof Element ? event.target.closest('[data-acf-card]') : null;
    if (target && (event.key === 'Enter' || event.key === ' ')) { event.preventDefault(); openEditor(target.dataset.acfCard); }
  });
  host.querySelector('[data-acf-panel-new]')?.addEventListener('click', () => openEditor('new'));
  search?.addEventListener('input', render);
  typeButtons.forEach((item) => item.addEventListener('click', () => {
    item.setAttribute('aria-pressed', String(item.getAttribute('aria-pressed') !== 'true'));
    render();
  }));

  // ---- More actions: Import JSON, Export All Fields and Re-materialize All Fields
  const setMenu = (open) => {
    if (!menu || !more) return;
    menu.hidden = !open;
    more.setAttribute('aria-expanded', String(open));
    if (open) menu.querySelector('[role="menuitem"]')?.focus();
  };
  more?.addEventListener('click', () => setMenu(Boolean(menu?.hidden)));
  document.addEventListener('click', (event) => {
    if (menu && !menu.hidden && !(event.target instanceof Element && event.target.closest('.acf-panel-more'))) setMenu(false);
  });
  menu?.addEventListener('keydown', (event) => {
    const items = [...menu.querySelectorAll('[role="menuitem"]')];
    const index = items.indexOf(document.activeElement);
    if (event.key === 'Escape') { event.preventDefault(); setMenu(false); more?.focus(); }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      items[(index + (event.key === 'ArrowDown' ? 1 : items.length - 1)) % items.length]?.focus();
    }
  });
  menu?.addEventListener('click', (event) => {
    if (event.target instanceof Element && event.target.closest('[role="menuitem"]')) setMenu(false);
  });

  // The file chosen is checked and confirmed by the import form of app.js before it is sent.
  const fileInput = importForm?.querySelector('input[type="file"]');
  host.querySelector('[data-acf-panel-import]')?.addEventListener('click', () => {
    if (!fileInput) return;
    fileInput.value = '';
    fileInput.click();
  });
  fileInput?.addEventListener('change', () => { if (fileInput.files?.length) importForm.requestSubmit(); });

  rematerialize?.addEventListener('click', async () => {
    const accepted = await window.showConfirmDialog(
      'Every auto-calculated field will be worked out again in every CDR table it applies to. Saving a field already updates its tables: use this only to repair them, for example after an interrupted update. It runs in the background, shown in CDR Tables Updates in Workspace. Continue?',
      {title: 'Re-materialize All Fields', confirmLabel: 'Re-materialize All', tone: 'warning'},
    );
    if (!accepted) return;
    try {
      const response = await fetch(`${API}/rematerialize`, {
        method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json'},
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || 'Unable to re-materialize the Auto-calculated Fields.');
      window.monitorAutoCalculatedFieldJob?.(payload.materialization_status_url, payload.notice);
      await poll();
    } catch (error) {
      window.showInfoDialog(error instanceof Error ? error.message : 'Unable to re-materialize the Auto-calculated Fields.', {
        title: 'Auto-calculated Fields', tone: 'error',
      });
    }
  });

  window.addEventListener('auto-calculated-field-job-status', () => { void poll(); });
  render();
  void loadInsights();
  void poll();
})();
