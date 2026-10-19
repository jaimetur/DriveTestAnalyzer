// Ticket Center: its dashboard, the list of tickets with its filters, the New Ticket form, and the page of each ticket
// (its edition, comments, screenshots and the super-admin attention).
(() => {
  // The sections of Bugs Report, as Ticket Center was called, in the links of before.
  const formerSections = {'#section-bug-reports': '#section-tickets', '#section-new-bug-report': '#section-new-ticket'};
  if (formerSections[window.location.hash]) {
    window.history.replaceState(window.history.state, '', `${window.location.pathname}${window.location.search}${formerSections[window.location.hash]}`);
  }
  const moduleTitle = document.querySelector('[data-ticket-center-title]')?.dataset.ticketCenterTitle || 'Ticket Center';
  const info = (message, title = moduleTitle, tone = 'error') => (typeof showInfoDialog === 'function'
    ? showInfoDialog(message, {title, tone})
    : window.alert(message));
  const confirmAction = (message, options) => (typeof showConfirmDialog === 'function'
    ? showConfirmDialog(message, options)
    : Promise.resolve(window.confirm(message)));

  // Sends a form to the server; resolves with its JSON answer or shows why it failed.
  const send = async (url, body) => {
    const response = await fetch(url, {method: 'POST', credentials: 'same-origin', headers: {Accept: 'application/json'}, body});
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || 'The request could not be completed.');
    return payload;
  };
  const busy = (form, value) => form.querySelectorAll('button[type="submit"]').forEach((button) => { button.disabled = value; });

  // Screenshots: chosen, dropped or pasted anywhere in their form, previewed before they are sent.
  const dropzones = new Map();
  document.querySelectorAll('[data-ticket-dropzone]').forEach((zone) => {
    const input = zone.querySelector('[data-ticket-dropzone-input]');
    const previews = zone.querySelector('[data-ticket-dropzone-previews]');
    const maxFiles = Number(zone.dataset.maxFiles) || 10;
    const maxBytes = (Number(zone.dataset.maxMb) || 10) * 1024 * 1024;
    let files = [];
    const sync = () => {
      const transfer = new DataTransfer();
      files.forEach((file) => transfer.items.add(file));
      input.files = transfer.files;
      previews.replaceChildren(...files.map((file, index) => {
        const item = document.createElement('figure');
        item.className = 'ticket-dropzone-preview';
        const image = document.createElement('img');
        image.src = URL.createObjectURL(file);
        image.alt = file.name;
        image.addEventListener('load', () => URL.revokeObjectURL(image.src), {once: true});
        const caption = document.createElement('figcaption');
        caption.textContent = file.name;
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.textContent = '×';
        remove.title = `Remove ${file.name}`;
        remove.addEventListener('click', () => { files.splice(index, 1); sync(); });
        item.append(image, caption, remove);
        return item;
      }));
      zone.classList.toggle('has-files', files.length > 0);
      zone.dispatchEvent(new CustomEvent('ticket-screenshots-change', {bubbles: true, detail: {count: files.length}}));
    };
    const add = (incoming) => {
      const images = [...incoming].filter((file) => /^image\/(png|jpeg|gif|webp)$/.test(file.type));
      if (incoming.length && !images.length) return info('Only PNG, JPEG, GIF or WebP images can be attached.');
      for (const file of images) {
        if (file.size > maxBytes) { info(`"${file.name}" is larger than ${zone.dataset.maxMb} MB.`); continue; }
        if (files.length >= maxFiles) { info(`Attach at most ${maxFiles} screenshots at once.`); break; }
        // A pasted screenshot has no name of its own: it takes the time it was pasted.
        const named = file.name && file.name !== 'image.png' ? file
          : new File([file], `screenshot-${new Date().toISOString().slice(0, 19).replace(/[T:]/g, '-')}-${files.length + 1}.${file.type.split('/')[1].replace('jpeg', 'jpg')}`, {type: file.type});
        files.push(named);
      }
      sync();
    };
    // Choosing files replaces those of the input: they are added to the ones chosen or pasted before.
    input.addEventListener('change', () => add([...input.files]));
    ['dragenter', 'dragover'].forEach((type) => zone.addEventListener(type, (event) => { event.preventDefault(); zone.classList.add('is-dragging'); }));
    ['dragleave', 'drop'].forEach((type) => zone.addEventListener(type, () => zone.classList.remove('is-dragging')));
    zone.addEventListener('drop', (event) => { event.preventDefault(); add(event.dataTransfer?.files || []); });
    zone.closest('form')?.addEventListener('paste', (event) => {
      const pasted = [...(event.clipboardData?.files || [])];
      if (!pasted.length) return;
      event.preventDefault();
      add(pasted);
    });
    dropzones.set(zone, {reset: () => { files = []; sync(); }, count: () => files.length});
  });

  // The list: the chips (type, status, priority, module and assignee), search, reporter and order of the tickets,
  // remembered by this browser. No chip pressed in a group lists every value of it, and the groups add up.
  const table = document.querySelector('[data-tickets-table]');
  if (table) {
    const rows = [...table.querySelectorAll('[data-ticket-row]')];
    const body = table.tBodies[0];
    const filters = Object.fromEntries([...document.querySelectorAll('[data-tickets-filter]')].map((control) => [control.dataset.ticketsFilter, control]));
    const sort = document.querySelector('[data-tickets-sort]');
    const count = document.querySelector('[data-tickets-count]');
    const empty = document.querySelector('[data-tickets-empty]');
    const chips = [...document.querySelectorAll('[data-chip]')];
    const recentChip = document.querySelector('[data-chip-recent]');
    const groups = ['types', 'statuses', 'priorities', 'modules', 'assignees'];
    const openStatuses = ['new', 'in_progress', 'waiting_info'];
    const allowed = Object.fromEntries(groups.map((group) => [group, new Set(chips.filter((chip) => chip.dataset.chip === group).map((chip) => chip.dataset.value))]));
    const state = {types: [], statuses: [...openStatuses], priorities: [], modules: [], assignees: [], recent: false};
    const sameSet = (values, expected) => values.length === expected.length && expected.every((value) => values.includes(value));
    const clear = () => {
      groups.forEach((group) => { state[group] = []; });
      state.recent = false;
      filters.search.value = '';
      filters.reporter.value = '*';
      if (filters.mine) filters.mine.checked = false;
    };
    const storageKey = 'ticket-center:filters';
    try {
      const saved = JSON.parse(window.localStorage.getItem(storageKey) || '{}');
      groups.forEach((group) => { if (Array.isArray(saved[group])) state[group] = saved[group].filter((value) => allowed[group].has(value)); });
      state.recent = Boolean(saved.recent);
      if (saved.reporter && [...filters.reporter.options].some((option) => option.value === saved.reporter)) filters.reporter.value = saved.reporter;
      if (filters.mine) filters.mine.checked = Boolean(saved.mine);
      if (saved.sort && [...sort.options].some((option) => option.value === saved.sort)) sort.value = saved.sort;
    } catch (_) { /* Filters start at their defaults. */ }
    // A link to the tickets of a status or type (?status=new, from the admin notices of the super-admins) lists only them.
    const params = new URLSearchParams(window.location.search);
    const linkedStatus = params.get('status');
    const linkedType = params.get('type');
    if ((linkedStatus && (linkedStatus === 'open' || allowed.statuses.has(linkedStatus))) || (linkedType && allowed.types.has(linkedType))) {
      clear();
      state.statuses = linkedStatus === 'open' ? [...openStatuses] : linkedStatus && allowed.statuses.has(linkedStatus) ? [linkedStatus] : [];
      state.types = linkedType && allowed.types.has(linkedType) ? [linkedType] : [];
      const url = new URL(window.location.href);
      url.searchParams.delete('status');
      url.searchParams.delete('type');
      window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}${url.hash}`);
    }
    const priorityRank = {P1: 1, P2: 2, P3: 3, P4: 4, P5: 5};
    const matches = (group, value) => !state[group].length || state[group].includes(value);
    const apply = () => {
      const query = filters.search.value.trim().toLowerCase();
      let shown = 0;
      rows.forEach((row) => {
        const visible = (!query || row.dataset.search.includes(query))
          && matches('types', row.dataset.type) && matches('statuses', row.dataset.status) && matches('priorities', row.dataset.priority)
          && matches('modules', row.dataset.module) && matches('assignees', row.dataset.assignee)
          && (!state.recent || row.dataset.recent === 'true')
          && (filters.reporter.value === '*' || row.dataset.reporter === filters.reporter.value)
          && (!filters.mine?.checked || row.dataset.mine === 'true');
        row.hidden = !visible;
        shown += visible ? 1 : 0;
      });
      const order = {
        updated: (a, b) => b.dataset.updated.localeCompare(a.dataset.updated),
        created: (a, b) => b.dataset.created.localeCompare(a.dataset.created),
        oldest: (a, b) => a.dataset.created.localeCompare(b.dataset.created),
        priority: (a, b) => priorityRank[a.dataset.priority] - priorityRank[b.dataset.priority] || b.dataset.updated.localeCompare(a.dataset.updated),
      }[sort.value];
      body.append(...rows.sort(order));
      chips.forEach((chip) => chip.setAttribute('aria-pressed', String(state[chip.dataset.chip].includes(chip.dataset.value))));
      if (recentChip) recentChip.hidden = !state.recent;
      if (count) count.textContent = `${shown} of ${rows.length} ticket${rows.length === 1 ? '' : 's'}`;
      if (empty && rows.length) empty.hidden = shown > 0;
      syncStats();
      try {
        window.localStorage.setItem(storageKey, JSON.stringify({
          ...Object.fromEntries(groups.map((group) => [group, state[group]])), recent: state.recent,
          reporter: filters.reporter.value, mine: Boolean(filters.mine?.checked), sort: sort.value,
        }));
      } catch (_) { /* Not remembered. */ }
    };
    chips.forEach((chip) => chip.addEventListener('click', () => {
      const values = state[chip.dataset.chip];
      state[chip.dataset.chip] = values.includes(chip.dataset.value) ? values.filter((value) => value !== chip.dataset.value) : [...values, chip.dataset.value];
      apply();
    }));
    recentChip?.addEventListener('click', () => { state.recent = false; apply(); });
    Object.values(filters).forEach((control) => control.addEventListener(control.type === 'search' ? 'input' : 'change', apply));
    sort.addEventListener('change', apply);
    document.querySelector('[data-tickets-reset]')?.addEventListener('click', () => {
      clear();
      state.statuses = [...openStatuses];
      apply();
    });
    // Lists the tickets the dashboard counted (every other filter cleared) and shows the list.
    const show = ({mine = false, ...chosen}) => {
      clear();
      Object.assign(state, {statuses: [...openStatuses]}, chosen);
      if (filters.mine) filters.mine.checked = mine;
      apply();
      const panel = document.getElementById('section-tickets');
      if (panel) {
        panel.open = true;
        panel.scrollIntoView({behavior: 'smooth', block: 'start'});
      }
    };
    // The tiles of the header list their tickets; the tile pressed again lists the open ones. The tile of the tickets
    // shown stays pressed.
    const stats = [...document.querySelectorAll('[data-tickets-stat]')];
    const tileState = {
      open: {}, new: {statuses: ['new']}, in_progress: {statuses: ['in_progress']}, waiting_info: {statuses: ['waiting_info']},
      recent: {statuses: ['resolved', 'closed'], recent: true}, mine: {mine: true},
    };
    const pressedStat = () => {
      const plain = groups.every((group) => group === 'statuses' || !state[group].length) && !filters.search.value && filters.reporter.value === '*';
      if (!plain) return '';
      if (filters.mine?.checked) return !state.recent && sameSet(state.statuses, openStatuses) ? 'mine' : '';
      if (state.recent) return sameSet(state.statuses, ['resolved', 'closed']) ? 'recent' : '';
      if (sameSet(state.statuses, openStatuses)) return 'open';
      return state.statuses.length === 1 && openStatuses.includes(state.statuses[0]) ? state.statuses[0] : '';
    };
    function syncStats() {
      const pressed = pressedStat();
      stats.forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.ticketsStat === pressed)));
    }
    stats.forEach((button) => button.addEventListener('click', () => {
      const key = button.dataset.ticketsStat;
      show(key === pressedStat() ? {} : tileState[key]);
    }));
    // The counts of the matrix and the bars of each type list their tickets: a type and a status (the totals, every
    // value of the other one); a priority of a type, its open tickets; a module, its open tickets.
    document.querySelectorAll('[data-board-cell]').forEach((cell) => cell.addEventListener('click', () => show({
      types: cell.dataset.type ? [cell.dataset.type] : [], statuses: cell.dataset.status ? [cell.dataset.status] : [],
    })));
    document.querySelectorAll('[data-board-priority]').forEach((cell) => cell.addEventListener('click', () => show({
      types: [cell.dataset.type], priorities: [cell.dataset.priority],
    })));
    document.querySelectorAll('[data-board-module]').forEach((cell) => cell.addEventListener('click', () => show({
      modules: allowed.modules.has(cell.dataset.boardModule) ? [cell.dataset.boardModule] : [],
    })));
    // A click anywhere on a row opens its ticket.
    table.addEventListener('click', (event) => {
      const row = event.target.closest('[data-ticket-row]');
      if (!row || event.target.closest('a, button, input, select')) return;
      window.location.href = row.dataset.href;
    });
    apply();
  }

  // The dashboard tells what each count, bar and week is, over it (data-tip), with the mouse or the keyboard.
  const tip = document.querySelector('[data-board-tip]');
  if (tip) {
    const board = tip.parentElement;
    const place = (target) => {
      tip.textContent = target.dataset.tip;
      tip.hidden = false;
      const box = target.getBoundingClientRect();
      const frame = board.getBoundingClientRect();
      const left = Math.min(Math.max(box.left + box.width / 2 - frame.left - tip.offsetWidth / 2, 4), frame.width - tip.offsetWidth - 4);
      tip.style.left = `${left}px`;
      tip.style.top = `${box.top - frame.top - tip.offsetHeight - 8}px`;
    };
    const hide = () => { tip.hidden = true; };
    board.addEventListener('pointerover', (event) => {
      const target = event.target.closest('[data-tip]');
      if (target && board.contains(target)) place(target);
      else hide();
    });
    board.addEventListener('pointerleave', hide);
    board.addEventListener('focusin', (event) => { const target = event.target.closest('[data-tip]'); if (target) place(target); });
    board.addEventListener('focusout', hide);
  }

  // The New Ticket link opens and shows its panel.
  document.querySelector('[data-tickets-new]')?.addEventListener('click', () => {
    const panel = document.getElementById('section-new-ticket');
    if (panel) {
      panel.open = true;
      window.setTimeout(() => panel.querySelector('input[name="ticket_type"]')?.focus(), 50);
    }
  });

  const createForm = document.querySelector('[data-tickets-create-form]');
  // The description shows the guide of the type chosen.
  createForm?.querySelectorAll('input[name="ticket_type"]').forEach((radio) => radio.addEventListener('change', () => {
    const description = createForm.querySelector('[data-ticket-description]');
    if (description && radio.checked) description.placeholder = radio.dataset.guide;
  }));
  createForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!createForm.querySelector('input[name="ticket_type"]:checked')) {
      createForm.querySelector('input[name="ticket_type"]')?.focus();
      return info('Choose the type of the ticket: Bug, Improvement or New Feature.');
    }
    if (!createForm.title.value.trim()) {
      createForm.title.focus();
      return info('Give the ticket a title.');
    }
    busy(createForm, true);
    try {
      const payload = await send('/api/tickets', new FormData(createForm));
      window.location.href = payload.url;
    } catch (error) {
      info(error.message);
      busy(createForm, false);
    }
  });

  // The page of a ticket.
  const page = document.querySelector('[data-ticket-page]');
  if (!page) return;
  const ticketId = page.dataset.ticketPage;
  const reload = () => window.location.reload();

  const editForm = page.querySelector('[data-ticket-edit-form]');
  const editToggle = page.querySelector('[data-ticket-edit-toggle]');
  const showEdit = (open) => {
    if (!editForm) return;
    editForm.hidden = !open;
    editToggle?.setAttribute('aria-expanded', String(open));
    if (open) editForm.title.focus();
  };
  editToggle?.addEventListener('click', () => showEdit(editForm.hidden));
  page.querySelector('[data-ticket-edit-cancel]')?.addEventListener('click', () => { editForm.reset(); showEdit(false); });
  editForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    busy(editForm, true);
    try {
      await send(`/api/tickets/${ticketId}/update`, new FormData(editForm));
      reload();
    } catch (error) {
      info(error.message);
      busy(editForm, false);
    }
  });

  page.querySelector('[data-ticket-priority]')?.addEventListener('change', async (event) => {
    const body = new FormData();
    body.append('priority', event.target.value);
    try {
      await send(`/api/tickets/${ticketId}/update`, body);
      reload();
    } catch (error) { info(error.message); }
  });

  const shotsForm = page.querySelector('[data-ticket-shots-form]');
  shotsForm?.addEventListener('ticket-screenshots-change', (event) => {
    shotsForm.querySelector('[data-ticket-shots-actions]').hidden = !event.detail.count;
  });
  shotsForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    busy(shotsForm, true);
    try {
      await send(`/api/tickets/${ticketId}/screenshots`, new FormData(shotsForm));
      reload();
    } catch (error) {
      info(error.message);
      busy(shotsForm, false);
    }
  });

  const commentForm = page.querySelector('[data-ticket-comment-form]');
  commentForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const zone = commentForm.querySelector('[data-ticket-dropzone]');
    if (!commentForm.body.value.trim() && !dropzones.get(zone)?.count()) {
      commentForm.body.focus();
      return info('Write a comment or attach a screenshot.');
    }
    busy(commentForm, true);
    try {
      await send(`/api/tickets/${ticketId}/comments`, new FormData(commentForm));
      reload();
    } catch (error) {
      info(error.message);
      busy(commentForm, false);
    }
  });

  // Comments: their author edits them in place; the author and the super-admins delete them.
  page.querySelectorAll('[data-ticket-comment]').forEach((comment) => {
    const commentId = comment.dataset.ticketComment;
    comment.querySelector('[data-ticket-comment-edit]')?.addEventListener('click', () => {
      if (comment.querySelector('.ticket-comment-editor')) return;
      const text = comment.querySelector('[data-ticket-comment-text]');
      const editor = document.createElement('form');
      editor.className = 'ticket-comment-editor';
      editor.innerHTML = '<textarea name="body" rows="4" maxlength="20000"></textarea><div class="tickets-form-actions"><button type="button" class="ticket-ghost-button">Cancel</button><button type="submit" class="tickets-primary-button">Save</button></div>';
      // The comment as written, not as it reads with its bullets.
      editor.body.value = text ? (text.dataset.raw ?? text.textContent) : '';
      editor.querySelector('.ticket-ghost-button').addEventListener('click', () => { editor.remove(); if (text) text.hidden = false; });
      editor.addEventListener('submit', async (event) => {
        event.preventDefault();
        busy(editor, true);
        try {
          await send(`/api/tickets/comments/${commentId}/update`, new FormData(editor));
          reload();
        } catch (error) {
          info(error.message);
          busy(editor, false);
        }
      });
      if (text) { text.hidden = true; text.after(editor); } else comment.querySelector('.ticket-comment-body header').after(editor);
      editor.body.focus();
    });
    comment.querySelector('[data-ticket-comment-delete]')?.addEventListener('click', async () => {
      const accepted = await confirmAction('Delete this comment and its screenshots?', {title: 'Delete comment', confirmLabel: 'Delete comment', tone: 'warning'});
      if (!accepted) return;
      try {
        await send(`/api/tickets/comments/${commentId}/delete`, new FormData());
        reload();
      } catch (error) { info(error.message); }
    });
  });

  page.querySelectorAll('[data-ticket-shot-delete]').forEach((button) => button.addEventListener('click', async () => {
    const accepted = await confirmAction('Delete this screenshot?', {title: 'Delete screenshot', confirmLabel: 'Delete screenshot', tone: 'warning'});
    if (!accepted) return;
    try {
      await send(`/api/tickets/screenshots/${button.dataset.ticketShotDelete}/delete`, new FormData());
      reload();
    } catch (error) { info(error.message); }
  }));

  // Super-admins: attend the ticket (In Progress, assigned to them), or change its status, type, assignment and fixed
  // version.
  const manageForm = page.querySelector('[data-ticket-manage-form]');
  manageForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    busy(manageForm, true);
    try {
      await send(`/api/tickets/${ticketId}/manage`, new FormData(manageForm));
      reload();
    } catch (error) {
      info(error.message);
      busy(manageForm, false);
    }
  });
  page.querySelector('[data-ticket-attend]')?.addEventListener('click', async (event) => {
    const body = new FormData();
    body.append('status', 'in_progress');
    body.append('assigned_to', event.currentTarget.dataset.username);
    try {
      await send(`/api/tickets/${ticketId}/manage`, body);
      reload();
    } catch (error) { info(error.message); }
  });
  page.querySelector('[data-ticket-delete]')?.addEventListener('click', async () => {
    const accepted = await confirmAction('Delete this ticket with its timeline and screenshots? This cannot be undone.', {title: 'Delete ticket', confirmLabel: 'Delete ticket', tone: 'warning'});
    if (!accepted) return;
    try {
      const payload = await send(`/api/tickets/${ticketId}/delete`, new FormData());
      window.location.href = payload.url;
    } catch (error) { info(error.message); }
  });

  // Screenshots open full size.
  const lightbox = page.querySelector('[data-ticket-lightbox]');
  page.addEventListener('click', (event) => {
    const shot = event.target.closest('[data-ticket-shot]');
    if (!shot || !lightbox) return;
    lightbox.querySelector('[data-ticket-lightbox-image]').src = shot.dataset.ticketShot;
    lightbox.querySelector('[data-ticket-lightbox-image]').alt = shot.dataset.ticketShotName;
    lightbox.querySelector('[data-ticket-lightbox-name]').textContent = shot.dataset.ticketShotName;
    lightbox.querySelector('[data-ticket-lightbox-link]').href = shot.dataset.ticketShot;
    lightbox.showModal();
  });
  lightbox?.querySelector('[data-ticket-lightbox-close]')?.addEventListener('click', () => lightbox.close());
  lightbox?.addEventListener('click', (event) => { if (event.target === lightbox) lightbox.close(); });
})();
