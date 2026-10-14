// Bugs Report: the list of bug reports with its filters, the New Bug Report form, and the page of each report
// (its edition, comments, screenshots and the super-admin attention).
(() => {
  const info = (message, title = 'Bugs Report', tone = 'error') => (typeof showInfoDialog === 'function'
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
  document.querySelectorAll('[data-bug-dropzone]').forEach((zone) => {
    const input = zone.querySelector('[data-bug-dropzone-input]');
    const previews = zone.querySelector('[data-bug-dropzone-previews]');
    const maxFiles = Number(zone.dataset.maxFiles) || 10;
    const maxBytes = (Number(zone.dataset.maxMb) || 10) * 1024 * 1024;
    let files = [];
    const sync = () => {
      const transfer = new DataTransfer();
      files.forEach((file) => transfer.items.add(file));
      input.files = transfer.files;
      previews.replaceChildren(...files.map((file, index) => {
        const item = document.createElement('figure');
        item.className = 'bug-dropzone-preview';
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
      zone.dispatchEvent(new CustomEvent('bug-screenshots-change', {bubbles: true, detail: {count: files.length}}));
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

  // The list: filters, search and order of the bug reports, remembered by this browser.
  const table = document.querySelector('[data-bugs-table]');
  if (table) {
    const rows = [...table.querySelectorAll('[data-bug-row]')];
    const body = table.tBodies[0];
    const filters = Object.fromEntries([...document.querySelectorAll('[data-bugs-filter]')].map((control) => [control.dataset.bugsFilter, control]));
    const sort = document.querySelector('[data-bugs-sort]');
    const count = document.querySelector('[data-bugs-count]');
    const empty = document.querySelector('[data-bugs-empty]');
    const storageKey = 'bugs-report:filters';
    try {
      const saved = JSON.parse(window.localStorage.getItem(storageKey) || '{}');
      Object.entries(saved).forEach(([key, value]) => {
        const control = key === 'sort' ? sort : filters[key];
        if (!control) return;
        if (control.type === 'checkbox') control.checked = Boolean(value);
        else if ([...(control.options || [{value}])].some((option) => option.value === value)) control.value = value;
      });
    } catch (_) { /* Filters start at their defaults. */ }
    const priorityRank = {P1: 1, P2: 2, P3: 3, P4: 4, P5: 5};
    const apply = () => {
      const query = filters.search.value.trim().toLowerCase();
      const statusValue = filters.status.value;
      let shown = 0;
      rows.forEach((row) => {
        const visible = (!query || row.dataset.search.includes(query))
          && (statusValue === '' || (statusValue === 'open' ? row.dataset.open === 'true' : row.dataset.status === statusValue))
          && (!filters.priority.value || row.dataset.priority === filters.priority.value)
          && (filters.module.value === '*' || row.dataset.module === filters.module.value)
          && (!filters.mine.checked || row.dataset.mine === 'true');
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
      if (count) count.textContent = `${shown} of ${rows.length} bug report${rows.length === 1 ? '' : 's'}`;
      if (empty && rows.length) empty.hidden = shown > 0;
      try {
        window.localStorage.setItem(storageKey, JSON.stringify({
          status: statusValue, priority: filters.priority.value, module: filters.module.value, mine: filters.mine.checked, sort: sort.value,
        }));
      } catch (_) { /* Not remembered. */ }
    };
    Object.values(filters).forEach((control) => control.addEventListener(control.type === 'search' ? 'input' : 'change', apply));
    sort.addEventListener('change', apply);
    // The counts of the header list their bug reports (every other filter cleared); the count pressed again lists the
    // open ones. The count of the shown status stays pressed.
    const stats = [...document.querySelectorAll('[data-bugs-stat]')];
    const pressedStat = () => {
      if (filters.search.value || filters.priority.value || filters.module.value !== '*') return '';
      if (filters.mine.checked) return filters.status.value === 'open' ? 'mine' : '';
      return filters.status.value;
    };
    const syncStats = () => stats.forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.bugsStat === pressedStat())));
    stats.forEach((button) => button.addEventListener('click', () => {
      const chosen = button.dataset.bugsStat === pressedStat() ? '' : button.dataset.bugsStat;
      filters.search.value = '';
      filters.priority.value = '';
      filters.module.value = '*';
      filters.mine.checked = chosen === 'mine';
      filters.status.value = !chosen || chosen === 'mine' ? 'open' : chosen;
      apply();
      const panel = document.getElementById('section-bug-reports');
      if (panel) {
        panel.open = true;
        panel.scrollIntoView({behavior: 'smooth', block: 'start'});
      }
    }));
    [...Object.values(filters), sort].forEach((control) => control.addEventListener(control.type === 'search' ? 'input' : 'change', syncStats));
    stats.forEach((button) => button.addEventListener('click', syncStats));
    // A click anywhere on a row opens its bug report.
    table.addEventListener('click', (event) => {
      const row = event.target.closest('[data-bug-row]');
      if (!row || event.target.closest('a, button, input, select')) return;
      window.location.href = row.dataset.href;
    });
    apply();
    syncStats();
  }

  // The New Bug Report link opens and shows its panel.
  document.querySelector('[data-bugs-new]')?.addEventListener('click', () => {
    const panel = document.getElementById('section-new-bug-report');
    if (panel) {
      panel.open = true;
      window.setTimeout(() => panel.querySelector('input[name="title"]')?.focus(), 50);
    }
  });

  const createForm = document.querySelector('[data-bugs-create-form]');
  createForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!createForm.title.value.trim()) {
      createForm.title.focus();
      return info('Give the bug a title.');
    }
    busy(createForm, true);
    try {
      const payload = await send('/api/bugs-report', new FormData(createForm));
      window.location.href = payload.url;
    } catch (error) {
      info(error.message);
      busy(createForm, false);
    }
  });

  // The page of a bug report.
  const page = document.querySelector('[data-bug-report]');
  if (!page) return;
  const bugId = page.dataset.bugReport;
  const reload = () => window.location.reload();

  const editForm = page.querySelector('[data-bug-edit-form]');
  const editToggle = page.querySelector('[data-bug-edit-toggle]');
  const showEdit = (open) => {
    if (!editForm) return;
    editForm.hidden = !open;
    editToggle?.setAttribute('aria-expanded', String(open));
    if (open) editForm.title.focus();
  };
  editToggle?.addEventListener('click', () => showEdit(editForm.hidden));
  page.querySelector('[data-bug-edit-cancel]')?.addEventListener('click', () => { editForm.reset(); showEdit(false); });
  editForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    busy(editForm, true);
    try {
      await send(`/api/bugs-report/${bugId}/update`, new FormData(editForm));
      reload();
    } catch (error) {
      info(error.message);
      busy(editForm, false);
    }
  });

  page.querySelector('[data-bug-priority]')?.addEventListener('change', async (event) => {
    const body = new FormData();
    body.append('priority', event.target.value);
    try {
      await send(`/api/bugs-report/${bugId}/update`, body);
      reload();
    } catch (error) { info(error.message); }
  });

  const shotsForm = page.querySelector('[data-bug-shots-form]');
  shotsForm?.addEventListener('bug-screenshots-change', (event) => {
    shotsForm.querySelector('[data-bug-shots-actions]').hidden = !event.detail.count;
  });
  shotsForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    busy(shotsForm, true);
    try {
      await send(`/api/bugs-report/${bugId}/screenshots`, new FormData(shotsForm));
      reload();
    } catch (error) {
      info(error.message);
      busy(shotsForm, false);
    }
  });

  const commentForm = page.querySelector('[data-bug-comment-form]');
  commentForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const zone = commentForm.querySelector('[data-bug-dropzone]');
    if (!commentForm.body.value.trim() && !dropzones.get(zone)?.count()) {
      commentForm.body.focus();
      return info('Write a comment or attach a screenshot.');
    }
    busy(commentForm, true);
    try {
      await send(`/api/bugs-report/${bugId}/comments`, new FormData(commentForm));
      reload();
    } catch (error) {
      info(error.message);
      busy(commentForm, false);
    }
  });

  // Comments: their author edits them in place; the author and the super-admins delete them.
  page.querySelectorAll('[data-bug-comment]').forEach((comment) => {
    const commentId = comment.dataset.bugComment;
    comment.querySelector('[data-bug-comment-edit]')?.addEventListener('click', () => {
      if (comment.querySelector('.bug-comment-editor')) return;
      const text = comment.querySelector('[data-bug-comment-text]');
      const editor = document.createElement('form');
      editor.className = 'bug-comment-editor';
      editor.innerHTML = '<textarea name="body" rows="4" maxlength="20000"></textarea><div class="bugs-form-actions"><button type="button" class="bug-ghost-button">Cancel</button><button type="submit" class="bugs-primary-button">Save</button></div>';
      // The comment as written, not as it reads with its bullets.
      editor.body.value = text ? (text.dataset.raw ?? text.textContent) : '';
      editor.querySelector('.bug-ghost-button').addEventListener('click', () => { editor.remove(); if (text) text.hidden = false; });
      editor.addEventListener('submit', async (event) => {
        event.preventDefault();
        busy(editor, true);
        try {
          await send(`/api/bugs-report/comments/${commentId}/update`, new FormData(editor));
          reload();
        } catch (error) {
          info(error.message);
          busy(editor, false);
        }
      });
      if (text) { text.hidden = true; text.after(editor); } else comment.querySelector('.bug-comment-body header').after(editor);
      editor.body.focus();
    });
    comment.querySelector('[data-bug-comment-delete]')?.addEventListener('click', async () => {
      const accepted = await confirmAction('Delete this comment and its screenshots?', {title: 'Delete comment', confirmLabel: 'Delete comment', tone: 'warning'});
      if (!accepted) return;
      try {
        await send(`/api/bugs-report/comments/${commentId}/delete`, new FormData());
        reload();
      } catch (error) { info(error.message); }
    });
  });

  page.querySelectorAll('[data-bug-shot-delete]').forEach((button) => button.addEventListener('click', async () => {
    const accepted = await confirmAction('Delete this screenshot?', {title: 'Delete screenshot', confirmLabel: 'Delete screenshot', tone: 'warning'});
    if (!accepted) return;
    try {
      await send(`/api/bugs-report/screenshots/${button.dataset.bugShotDelete}/delete`, new FormData());
      reload();
    } catch (error) { info(error.message); }
  }));

  // Super-admins: attend the bug (In Progress, assigned to them), or change its status, assignment and fixed version.
  const manageForm = page.querySelector('[data-bug-manage-form]');
  manageForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    busy(manageForm, true);
    try {
      await send(`/api/bugs-report/${bugId}/manage`, new FormData(manageForm));
      reload();
    } catch (error) {
      info(error.message);
      busy(manageForm, false);
    }
  });
  page.querySelector('[data-bug-attend]')?.addEventListener('click', async (event) => {
    const body = new FormData();
    body.append('status', 'in_progress');
    body.append('assigned_to', event.currentTarget.dataset.username);
    try {
      await send(`/api/bugs-report/${bugId}/manage`, body);
      reload();
    } catch (error) { info(error.message); }
  });
  page.querySelector('[data-bug-delete]')?.addEventListener('click', async () => {
    const accepted = await confirmAction('Delete this bug report with its timeline and screenshots? This cannot be undone.', {title: 'Delete bug report', confirmLabel: 'Delete bug report', tone: 'warning'});
    if (!accepted) return;
    try {
      const payload = await send(`/api/bugs-report/${bugId}/delete`, new FormData());
      window.location.href = payload.url;
    } catch (error) { info(error.message); }
  });

  // Screenshots open full size.
  const lightbox = page.querySelector('[data-bug-lightbox]');
  page.addEventListener('click', (event) => {
    const shot = event.target.closest('[data-bug-shot]');
    if (!shot || !lightbox) return;
    lightbox.querySelector('[data-bug-lightbox-image]').src = shot.dataset.bugShot;
    lightbox.querySelector('[data-bug-lightbox-image]').alt = shot.dataset.bugShotName;
    lightbox.querySelector('[data-bug-lightbox-name]').textContent = shot.dataset.bugShotName;
    lightbox.querySelector('[data-bug-lightbox-link]').href = shot.dataset.bugShot;
    lightbox.showModal();
  });
  lightbox?.querySelector('[data-bug-lightbox-close]')?.addEventListener('click', () => lightbox.close());
  lightbox?.addEventListener('click', (event) => { if (event.target === lightbox) lightbox.close(); });
})();
