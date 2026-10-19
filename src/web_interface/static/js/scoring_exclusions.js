// Excluded Calls of Scoring & GAP Analysis: the lists of calls (by JOIN_ID) left out of every scoring of the workspace,
// imported from CSV or Excel files, each switched on or off and assigned to every CDR or to some of them. The calls of
// each list are found in the CDRs in the background (see scoring_exclusions.py), so the panel looks again until then.
(() => {
  const panel = document.querySelector('[data-scoring-exclusions]');
  const dialog = document.querySelector('[data-exclusions-dialog]');
  if (!panel || !dialog) return;
  const API = '/api/scoring/excluded-calls';
  const POLL_MS = 4000;
  const KIND_LABELS = {data: 'Data', voice: 'Voice', speech: 'Speech'};
  const ICONS = {
    edit: 'M15 4l5 5-10 10-6 1 1-6zM13 6l5 5',
    download: 'M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5',
    delete: 'M4 6h16M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7m4-7v7',
  };
  const form = dialog.querySelector('[data-exclusions-form]');
  const fileInput = dialog.querySelector('[data-exclusions-file]');
  const fileRow = dialog.querySelector('[data-exclusions-file-row]');
  const fileName = dialog.querySelector('[data-exclusions-file-name]');
  const formatNote = dialog.querySelector('[data-exclusions-format]');
  const checkNote = dialog.querySelector('[data-exclusions-check]');
  const nameInput = dialog.querySelector('[data-exclusions-name]');
  const reasonInput = dialog.querySelector('[data-exclusions-reason]');
  const cdrSelect = dialog.querySelector('[data-exclusions-cdrs]');
  const errorLine = dialog.querySelector('[data-exclusions-error]');
  const submitButton = dialog.querySelector('[data-exclusions-submit]');
  const importButton = panel.querySelector('[data-exclusions-import]');
  const statusLine = panel.querySelector('[data-exclusions-status]');
  let state = {lists: [], cdrs: [], can_edit: false};
  // The list being edited (null: a new list is imported) and whether the chosen file was read.
  let editing = null;
  let fileChecked = false;
  let pollTimer = null;

  const number = (value) => Number(value || 0).toLocaleString('en-GB');
  const plural = (count, word) => `${number(count)} ${word}${Number(count) === 1 ? '' : 's'}`;
  const when = (value) => String(value || '').slice(0, 16).replace('T', ' ');

  function element(tag, properties = {}, ...children) {
    const node = Object.assign(document.createElement(tag), properties);
    node.append(...children.filter((child) => child !== null && child !== undefined && child !== false));
    return node;
  }

  function icon(name) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('aria-hidden', 'true');
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', ICONS[name]);
    svg.append(path);
    return svg;
  }

  async function request(url, options = {}) {
    const response = await fetch(url, {credentials: 'same-origin', ...options});
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(typeof body.detail === 'string' ? body.detail : `The request failed (${response.status}).`);
    }
    return body;
  }

  function setStatus(message, tone = '') {
    statusLine.textContent = message || '';
    if (tone) statusLine.dataset.tone = tone;
    else delete statusLine.dataset.tone;
  }

  function renderBadge() {
    const badge = panel.querySelector('[data-exclusions-badge]');
    const active = state.lists.filter((item) => item.enabled);
    badge.dataset.active = String(active.length > 0);
    if (!state.lists.length) badge.textContent = 'No calls excluded';
    else if (!active.length) badge.textContent = `${plural(state.lists.length, 'list')}, switched off`;
    else badge.textContent = `${plural(active.length, 'list')} on · ${plural(active.reduce((sum, item) => sum + item.call_count, 0), 'call')}`;
  }

  function cdrCell(item) {
    if (item.all_cdrs) return element('span', {className: 'scoring-exclusions-all', textContent: 'All CDRs'});
    const list = element('ul', {className: 'scoring-exclusions-cdrs'});
    for (const name of item.cdrs) {
      const missing = item.missing_cdrs.includes(name);
      list.append(element('li', {textContent: missing ? `${name} (not in this workspace)` : name,
        title: missing ? 'No CDR of this workspace has this file name: the list leaves no calls out of it.' : ''}));
      if (missing) list.lastChild.dataset.missing = 'true';
    }
    for (const name of item.companions) {
      const companion = element('li', {textContent: `+ ${name}`, title: 'The Speech or Voice CDR of the same campaign and NR Mode'});
      companion.dataset.companion = 'true';
      list.append(companion);
    }
    return list;
  }

  function foundCell(item) {
    const cell = element('div', {className: 'scoring-exclusions-found'});
    if (item.pending_cdrs) {
      cell.append(element('span', {className: 'scoring-exclusions-pending',
        textContent: `Finding the calls in ${plural(item.pending_cdrs, 'CDR')}…`}));
    }
    if (!item.targets.length) {
      cell.append(element('span', {className: 'scoring-exclusions-meta', textContent: 'No CDR of this workspace'}));
      return cell;
    }
    if (!item.pending_cdrs || item.found_calls) {
      cell.append(element('span', {textContent: `${plural(item.found_calls, 'call')} · ${plural(item.found_rows, 'row')}`}));
    }
    if (item.not_found) {
      cell.append(element('a', {href: `${API}/${item.id}/calls?not_found=true`, textContent: `${number(item.not_found)} not found`,
        title: 'Download the JOIN_IDs of the list found in none of its CDRs'}));
    }
    const found = item.targets.filter((target) => target.calls);
    if (found.length) {
      const breakdown = element('details', {className: 'scoring-exclusions-breakdown'}, element('summary', {textContent: 'By CDR'}),
        element('ul', {}, ...found.map((target) => element('li', {
          textContent: `${target.name} (${KIND_LABELS[target.kind] || target.kind}): ${plural(target.calls, 'call')}, ${plural(target.rows, 'row')}`,
        }))));
      cell.append(breakdown);
    }
    return cell;
  }

  function actionButton(action, label, handler) {
    const button = element('button', {type: 'button', title: label}, icon(action));
    button.dataset.action = action;
    button.setAttribute('aria-label', label);
    button.addEventListener('click', handler);
    return button;
  }

  function renderRow(item) {
    const toggle = element('input', {type: 'checkbox', checked: item.enabled, disabled: !state.can_edit});
    toggle.setAttribute('aria-label', `Leave the calls of “${item.name}” out of the scorings`);
    toggle.addEventListener('change', () => saveChanges(item, {enabled: toggle.checked},
      `“${item.name}” ${toggle.checked ? 'switched on: its calls are left out of the scorings' : 'switched off: its calls are scored again'}.`));
    const listCell = element('div', {},
      element('span', {className: 'scoring-exclusions-name', textContent: item.name}),
      item.file_name ? element('span', {className: 'scoring-exclusions-meta', textContent: item.file_name}) : null,
      item.reason ? element('span', {className: 'scoring-exclusions-reason', textContent: item.reason}) : null);
    const changed = item.updated_at && item.updated_at !== item.created_at
      ? element('span', {className: 'scoring-exclusions-meta', textContent: `Changed by ${item.updated_by} on ${when(item.updated_at)}`}) : null;
    const download = element('a', {href: `${API}/${item.id}/calls`, title: 'Download the calls of the list (CSV)'}, icon('download'));
    download.dataset.action = 'download';
    download.setAttribute('aria-label', `Download the calls of “${item.name}”`);
    const actions = element('div', {className: 'scoring-exclusions-actions'},
      state.can_edit ? actionButton('edit', `Edit “${item.name}”`, () => openDialog(item)) : null, download,
      state.can_edit ? actionButton('delete', `Delete “${item.name}”`, () => deleteList(item)) : null);
    const cells = [
      ['On', element('label', {className: 'scoring-exclusions-switch'}, toggle, element('span'))],
      ['List', listCell], ['CDRs', cdrCell(item)], ['Calls', number(item.call_count)], ['Found in the CDRs', foundCell(item)],
      ['Imported', element('div', {},
        element('span', {textContent: `${item.created_by} · ${when(item.created_at)}`}), changed)],
      ['', actions],
    ];
    const row = element('tr', {}, ...cells.map(([label, content], index) => {
      const cell = element('td', {}, content);
      cell.dataset.label = label;
      if (index === 3) cell.className = 'scoring-exclusions-number';
      return cell;
    }));
    row.dataset.enabled = String(item.enabled);
    return row;
  }

  function render() {
    importButton.hidden = !state.can_edit;
    panel.querySelector('[data-exclusions-rows]').replaceChildren(...state.lists.map(renderRow));
    panel.querySelector('[data-exclusions-table]').hidden = !state.lists.length;
    panel.querySelector('[data-exclusions-empty]').hidden = state.lists.length > 0;
    formatNote.textContent = state.format_help || '';
    renderBadge();
    schedulePoll();
  }

  function schedulePoll() {
    window.clearTimeout(pollTimer);
    pollTimer = null;
    // The calls are found in the background: the panel looks again until every list knows its calls.
    if (state.lists.some((item) => item.pending_cdrs)) {
      pollTimer = window.setTimeout(() => (document.hidden ? schedulePoll() : refresh()), POLL_MS);
    }
  }

  async function refresh() {
    try {
      state = await request(API);
      render();
    } catch (error) {
      setStatus(error.message, 'error');
    }
  }

  async function saveChanges(item, changes, message) {
    try {
      state = await request(`${API}/${item.id}`, {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(changes)});
      render();
      setStatus(message);
      return true;
    } catch (error) {
      setStatus(error.message, 'error');
      await refresh();
      return false;
    }
  }

  async function deleteList(item) {
    const message = `Delete “${item.name}” and its ${plural(item.call_count, 'call')}? Its calls are scored again.`;
    const accepted = typeof showConfirmDialog === 'function'
      ? await showConfirmDialog(message, {title: 'Delete Excluded Calls?', confirmLabel: 'Delete'})
      : window.confirm(message);
    if (!accepted) return;
    try {
      state = await request(`${API}/${item.id}`, {method: 'DELETE'});
      render();
      setStatus(`“${item.name}” deleted: its calls are scored again.`);
    } catch (error) {
      setStatus(error.message, 'error');
    }
  }

  // The CDRs of the workspace by type, and the CDRs of the list that it no longer has (kept so they stay chosen).
  function fillCdrOptions(chosen) {
    const groups = Object.entries(KIND_LABELS).map(([kind, label]) => {
      const group = element('optgroup', {label});
      group.append(...state.cdrs.filter((cdr) => cdr.kind === kind).map((cdr) => new Option(
        cdr.name, cdr.name, false, chosen.some((name) => name.toLowerCase() === cdr.name.toLowerCase()))));
      return group;
    }).filter((group) => group.children.length);
    const missing = chosen.filter((name) => !state.cdrs.some((cdr) => cdr.name.toLowerCase() === name.toLowerCase()));
    if (missing.length) {
      const group = element('optgroup', {label: 'Not in this workspace'});
      group.append(...missing.map((name) => new Option(name, name, true, true)));
      groups.push(group);
    }
    cdrSelect.replaceChildren(...groups);
    cdrSelect.dispatchEvent(new Event('multiselect:options-updated'));
  }

  function updateSubmit() {
    submitButton.disabled = !nameInput.value.trim() || (!editing && !fileChecked);
  }

  function openDialog(item = null) {
    editing = item;
    fileChecked = false;
    form.reset();
    errorLine.textContent = '';
    checkNote.hidden = true;
    fileName.textContent = 'No file chosen';
    fileRow.hidden = Boolean(item);
    formatNote.hidden = Boolean(item);
    dialog.querySelector('[data-exclusions-dialog-title]').textContent = item ? 'Edit Excluded Calls' : 'Import Excluded Calls';
    submitButton.textContent = item ? 'Save' : 'Import';
    nameInput.value = item ? item.name : '';
    reasonInput.value = item ? item.reason : '';
    fillCdrOptions(item ? item.cdrs : []);
    updateSubmit();
    dialog.showModal();
    (item ? nameInput : fileRow.querySelector('label')).focus();
  }

  async function checkFile() {
    const file = fileInput.files[0];
    fileChecked = false;
    checkNote.hidden = true;
    errorLine.textContent = '';
    fileName.textContent = file ? file.name : 'No file chosen';
    updateSubmit();
    if (!file) return;
    const body = new FormData();
    body.append('file', file);
    try {
      const read = await request(`${API}/check`, {method: 'POST', body});
      const left = [read.repeated ? `${plural(read.repeated, 'repeated JOIN_ID')}` : '', read.empty ? `${number(read.empty)} empty` : '']
        .filter(Boolean).join(' and ');
      checkNote.textContent = [
        `${plural(read.calls, 'JOIN_ID')} read${read.column ? ` from the ${read.column} column` : ''}`,
        left ? `${left} left out` : '', read.reasons ? `${number(read.reasons)} with a reason` : '',
      ].filter(Boolean).join(' · ') + '.';
      checkNote.hidden = false;
      fileChecked = true;
      if (!nameInput.value.trim()) nameInput.value = file.name.replace(/\.[^.]+$/, '');
    } catch (error) {
      errorLine.textContent = error.message;
    }
    updateSubmit();
  }

  async function submit(event) {
    event.preventDefault();
    errorLine.textContent = '';
    const cdrs = Array.from(cdrSelect.selectedOptions).map((option) => option.value);
    submitButton.disabled = true;
    try {
      if (editing) {
        if (await saveChanges(editing, {name: nameInput.value.trim(), reason: reasonInput.value.trim(), cdrs},
          `“${nameInput.value.trim()}” saved.`)) dialog.close();
        else errorLine.textContent = statusLine.textContent;
        return;
      }
      const body = new FormData();
      body.append('file', fileInput.files[0]);
      body.append('name', nameInput.value.trim());
      body.append('reason', reasonInput.value.trim());
      cdrs.forEach((name) => body.append('cdrs', name));
      state = await request(API, {method: 'POST', body});
      render();
      dialog.close();
      panel.open = true;
      setStatus(`“${state.imported.name}” imported with ${plural(state.imported.call_count, 'call')}: they are being found in its CDRs, and every scoring leaves them out.`);
    } catch (error) {
      errorLine.textContent = error.message;
    } finally {
      updateSubmit();
    }
  }

  // In the dialog the list of CDRs opens above its field when there is no room for it below.
  new MutationObserver((changes) => {
    for (const {target: menu} of changes) {
      if (!menu.classList.contains('multiselect-menu') || menu.hidden) continue;
      menu.classList.remove('scoring-exclusions-menu-above');
      const field = menu.parentElement.getBoundingClientRect();
      if (menu.getBoundingClientRect().bottom > window.innerHeight - 8 && field.top > window.innerHeight - field.bottom) {
        menu.classList.add('scoring-exclusions-menu-above');
      }
    }
  }).observe(dialog, {attributes: true, attributeFilter: ['hidden'], subtree: true});
  importButton.addEventListener('click', () => openDialog());
  fileInput.addEventListener('change', checkFile);
  nameInput.addEventListener('input', updateSubmit);
  form.addEventListener('submit', submit);
  dialog.querySelector('[data-exclusions-cancel]').addEventListener('click', () => dialog.close());
  refresh();
})();
