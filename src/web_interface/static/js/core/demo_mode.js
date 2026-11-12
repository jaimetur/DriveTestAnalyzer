// Demo Mode (see src/modules/core/demo_mode.py): the platform kept for the users of a demo while it lasts.
// Every page polls /api/demo-mode/heartbeat with its unsaved changes (window.unsavedChanges, base.html). The users
// without access are warned and signed out (at once when they have nothing to save, after saving otherwise); the
// admins and super-admins of the demo get its pill in the app bar and are asked to extend or end it when its time is up.
(() => {
  let info = {};
  try { info = JSON.parse(document.getElementById('demo-mode-info')?.textContent || '{}') || {}; } catch (_error) { info = {}; }
  const signedIn = Boolean(document.querySelector('[data-user-menu-trigger]'));
  const SIGNED_OUT_URL = '/login?demo=signed-out';
  const NORMAL_POLL = 20000;
  const FAST_POLL = 5000;

  const el = (tag, attributes = {}, ...children) => {
    const node = document.createElement(tag);
    Object.entries(attributes).forEach(([key, value]) => {
      if (value === false || value === null || value === undefined) return;
      if (key === 'class') node.className = value;
      else if (key === 'text') node.textContent = value;
      else if (key.startsWith('on') && typeof value === 'function') node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value === true ? '' : value);
    });
    children.flat().forEach((child) => { if (child !== null && child !== undefined && child !== false) node.append(child); });
    return node;
  };
  const icon = (paths) => {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('aria-hidden', 'true');
    svg.innerHTML = paths;
    return svg;
  };
  const ICONS = {
    demo: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4M10 8l4 2-4 2z"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    save: '<path d="M5 4h11l3 3v13H5z"/><path d="M8 4v5h7V4M8 20v-6h8v6"/>',
    users: '<circle cx="9" cy="8" r="3"/><path d="M3 20c0-3 3-5 6-5s6 2 6 5M16 5a3 3 0 0 1 0 6M21 20c0-2-1-4-3-4.6"/>',
    stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
  };
  const personName = (username, name) => name || (typeof window.personName === 'function' ? window.personName(username) : username) || username;

  // -- times ----------------------------------------------------------------------------------------------------
  const sameDay = (a, b) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  const formatTime = (iso) => {
    const moment = new Date(iso);
    if (Number.isNaN(moment.getTime())) return iso || '';
    const time = moment.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
    return sameDay(moment, new Date()) ? time : `${moment.toLocaleDateString([], {day: 'numeric', month: 'short'})} ${time}`;
  };
  const formatDuration = (seconds) => {
    const minutes = Math.max(0, Math.round(seconds / 60));
    if (minutes < 60) return `${minutes} min`;
    return `${Math.floor(minutes / 60)} h${minutes % 60 ? ` ${minutes % 60} min` : ''}`;
  };
  const formatCountdown = (seconds) => `${Math.floor(Math.max(0, seconds) / 60)}:${String(Math.max(0, Math.round(seconds)) % 60).padStart(2, '0')}`;
  const fillTimes = (root = document) => root.querySelectorAll('time[data-demo-mode-time]').forEach((node) => {
    node.textContent = formatTime(node.getAttribute('datetime'));
  });
  const localValue = (date) => {
    const pad = (value) => String(value).padStart(2, '0');
    return {date: `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`, time: `${pad(date.getHours())}:${pad(date.getMinutes())}`};
  };

  async function request(url, payload = null, background = false) {
    const response = await fetch(url, {
      method: payload ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store',
      headers: {...(payload ? {'Content-Type': 'application/json'} : {}), ...(background ? {'X-Background-Refresh': '1'} : {}), Accept: 'application/json'},
      body: payload ? JSON.stringify(payload) : undefined,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `The request failed (${response.status}).`);
    return data;
  }

  // -- the sign-in page -----------------------------------------------------------------------------------------
  function loginNotice() {
    const notice = document.querySelector('[data-demo-login-notice]');
    if (!notice) return;
    fillTimes(notice);
    const signedOut = notice.classList.contains('is-signed-out');
    const refresh = async () => {
      try {
        const demo = await request('/api/demo-mode/public', null, true);
        const text = notice.querySelector('[data-demo-login-text]');
        const message = notice.querySelector('[data-demo-login-message]');
        if (demo.active) {
          notice.hidden = false;
          text.replaceChildren(
            `${demo.started_by_name || demo.started_by} is using DriveTest Analyzer for a demo. `,
            demo.overdue ? 'The demo is taking longer than expected (it was expected to end at ' : 'It is expected to be available again at about ',
            el('time', {'data-demo-mode-time': true, datetime: demo.expected_end, text: formatTime(demo.expected_end)}),
            demo.overdue ? '); only the users of the demo can sign in until it is over.' : '; only the users of the demo can sign in until then.',
          );
          message.textContent = demo.message || '';
          message.hidden = !demo.message;
        } else if (signedOut) {
          notice.classList.add('is-over');
          notice.querySelector('[data-demo-login-title]').textContent = 'The demo is over';
          text.textContent = 'You can sign in again.';
          message.hidden = true;
        } else {
          notice.hidden = true;
        }
      } catch (_error) { /* The server is busy or restarting: try again later. */ }
    };
    refresh();
    window.setInterval(refresh, 30000);
  }

  if (!signedIn) {
    loginNotice();
    return;
  }
  // A page shown inside another (an embedded editor or preview) does not poll: the page around it tells its changes.
  let embedded = false;
  try { embedded = window.top !== window; } catch (_error) { embedded = true; }
  if (embedded) return;

  // -- the page and its unsaved changes -------------------------------------------------------------------------
  let tab = '';
  try {
    tab = window.sessionStorage.getItem('drivetest-analyzer:demo-tab') || '';
    if (!tab) { tab = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`; window.sessionStorage.setItem('drivetest-analyzer:demo-tab', tab); }
  } catch (_error) { tab = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`; }
  const unsavedChanges = () => {
    const items = typeof window.unsavedChanges === 'function' ? window.unsavedChanges() : [];
    document.querySelectorAll('iframe').forEach((frame) => {
      try {
        (frame.contentWindow?.unsavedChanges?.() || []).forEach((item) => { if (!items.includes(item)) items.push(item); });
      } catch (_error) { /* A page of another origin. */ }
    });
    const mappings = document.querySelectorAll('.mapping-row-unsaved').length;
    if (mappings) items.push(`${mappings} Operator or Vendor Map ${mappings === 1 ? 'label' : 'labels'}`);
    return items;
  };

  const topnav = document.querySelector('.topnav');
  const startButton = document.querySelector('[data-demo-mode-start]');
  let state = {active: Boolean(info.active), manage: Boolean(info.can_manage)};
  let pollTimer = 0;
  let leaving = null;
  let leavingCountdown = 0;
  let timeUpOpen = false;

  // -- the pill of the app bar ----------------------------------------------------------------------------------
  let pill = null;
  let pillMenu = null;
  function ensurePill() {
    if (!state.active || leaving || !topnav) {
      pill?.remove(); pillMenu?.remove(); pill = null; pillMenu = null;
      if (startButton) startButton.hidden = Boolean(state.active);
      return;
    }
    if (startButton) startButton.hidden = true;
    if (!pill) {
      pill = el('button', {type: 'button', class: 'topnav-link topnav-demo-pill', title: 'Demo Mode is on', 'data-demo-mode-pill': true},
        el('span', {class: 'topnav-demo-dot', 'aria-hidden': 'true'}),
        el('span', {}, 'DEMO MODE · until ', el('time', {'data-demo-mode-time': true})),
        el('span', {class: 'topnav-demo-waiting', 'data-demo-mode-waiting': true, hidden: true}));
      topnav.prepend(pill);
    }
    const time = pill.querySelector('time');
    time.setAttribute('datetime', state.expected_end || '');
    time.textContent = formatTime(state.expected_end);
    pill.classList.toggle('is-overdue', Boolean(state.overdue));
    if (state.manage && !pillMenu) {
      pillMenu = el('nav', {id: 'topnav-demo-options', class: 'module-config-options topnav-user-options topnav-demo-options', 'aria-label': 'Demo Mode', popover: 'auto'},
        el('div', {class: 'topnav-demo-departures', 'data-demo-mode-departures': true, hidden: true}),
        el('button', {type: 'button', onclick: () => { pillMenu.hidePopover?.(); openDialog('end'); }}, icon(ICONS.clock), el('span', {text: 'Change end time…'})),
        el('button', {type: 'button', onclick: () => { pillMenu.hidePopover?.(); openDialog('users'); }}, icon(ICONS.users), el('span', {text: 'Users and message…'})),
        el('button', {type: 'button', class: 'topnav-demo-end', onclick: () => { pillMenu.hidePopover?.(); endDemo(); }}, icon(ICONS.stop), el('span', {text: 'End Demo Mode now'})));
      pill.after(pillMenu);
      // Below the pill, inside the window (as the user menu).
      pillMenu.addEventListener('toggle', () => {
        if (!pillMenu.matches(':popover-open')) return;
        const anchor = pill.getBoundingClientRect();
        const bounds = pillMenu.getBoundingClientRect();
        const below = anchor.bottom + 5;
        Object.assign(pillMenu.style, {
          right: 'auto', bottom: 'auto', left: `${Math.max(8, Math.min(anchor.left, window.innerWidth - bounds.width - 8))}px`,
          top: `${below + bounds.height <= window.innerHeight - 8 ? below : Math.max(8, anchor.top - bounds.height - 5)}px`,
        });
      });
      pill.setAttribute('popovertarget', 'topnav-demo-options');
      pill.setAttribute('aria-haspopup', 'true');
    }
    const departures = state.departures || [];
    const waiting = pill.querySelector('[data-demo-mode-waiting]');
    const saving = departures.filter((item) => item.unsaved?.length).length;
    waiting.hidden = !departures.length;
    waiting.textContent = saving ? `${saving} saving` : `${departures.length} leaving`;
    waiting.title = `${departures.length} ${departures.length === 1 ? 'user is' : 'users are'} still being signed out`;
    const list = pillMenu?.querySelector('[data-demo-mode-departures]');
    if (list) {
      list.hidden = !departures.length;
      list.replaceChildren(el('p', {class: 'topnav-demo-section', text: 'Still being signed out'}), ...departures.map((item) => el('div', {class: 'topnav-demo-departure'},
        el('span', {class: `demo-tag ${item.unsaved?.length ? 'demo-tag-unsaved' : 'demo-tag-online'}`, text: item.unsaved?.length ? 'saving' : `${formatCountdown(item.seconds_left || 0)} left`}),
        el('span', {class: 'topnav-demo-departure-name', text: personName(item.username, item.name)}),
        el('small', {text: item.unsaved?.length ? item.unsaved.join(', ') : 'no unsaved changes'}))));
    }
  }

  // -- dialogs --------------------------------------------------------------------------------------------------
  function modal(className, labelledBy) {
    const backdrop = el('div', {class: `demo-mode-backdrop ${className}`});
    const dialog = el('section', {class: 'demo-mode-dialog', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': labelledBy});
    backdrop.append(dialog);
    document.body.append(backdrop);
    return {backdrop, dialog, close: () => backdrop.remove()};
  }
  const header = (id, iconName, title, text, tone = '') => el('header', {class: `demo-mode-dialog-header${tone ? ` is-${tone}` : ''}`},
    el('span', {class: 'demo-mode-dialog-badge'}, icon(ICONS[iconName])),
    el('div', {}, el('h2', {id, text: title}), text ? el('p', {text}) : null));

  async function openDialog(focus = 'start') {
    let data;
    try { data = await request('/api/demo-mode/users'); } catch (error) { window.alert(error.message); return; }
    const editing = Boolean(data.demo);
    const {dialog, close} = modal('demo-mode-setup', 'demo-mode-setup-title');
    const end = editing ? new Date(data.demo.expected_end) : new Date(Math.ceil((Date.now() + 3600000) / 300000) * 300000);
    const initial = localValue(end);
    const date = el('input', {type: 'date', value: initial.date, 'aria-label': 'Date of the expected end', 'data-native-select': true});
    const time = el('input', {type: 'time', value: initial.time, 'aria-label': 'Time of the expected end'});
    const chosenEnd = () => new Date(`${date.value}T${time.value}`);
    const shift = (minutes) => {
      const base = editing ? Math.max(Date.now(), new Date(data.demo.expected_end).getTime()) : Date.now();
      const next = localValue(new Date(Math.ceil((base + minutes * 60000) / 60000) * 60000));
      date.value = next.date; time.value = next.time; summary();
    };
    const message = el('textarea', {rows: '4', maxlength: '1000', 'aria-label': 'Message for the users'});
    message.value = editing ? data.demo.message : data.default_message;
    const search = el('input', {type: 'search', class: 'demo-mode-search', placeholder: 'Search users…', 'aria-label': 'Search users', autocomplete: 'off'});
    const rows = data.users.map((user) => {
      const box = el('input', {type: 'checkbox', checked: user.selected, disabled: user.locked, 'aria-label': `Access of ${user.username} during the demo`});
      const detail = [user.name, user.you ? (editing ? 'you' : 'you start the demo') : '', user.started && !user.you ? 'started the demo' : '',
        user.unsaved.length ? `unsaved: ${user.unsaved.join(', ')}` : ''].filter(Boolean).join(' · ');
      const row = el('label', {class: `demo-mode-user${user.locked ? ' is-locked' : ''}`},
        box, el('span', {class: `demo-mode-presence${user.online ? ' is-online' : ''}`, title: user.online ? 'Online now' : 'Not online', 'aria-label': user.online ? 'Online now' : 'Not online'}),
        el('span', {class: 'demo-mode-user-name'}, el('strong', {text: user.username}), detail ? el('small', {text: detail}) : null),
        user.you ? el('span', {class: 'demo-tag demo-tag-you', text: 'you'}) : null,
        user.unsaved.length ? el('span', {class: 'demo-tag demo-tag-unsaved', text: 'unsaved changes'}) : null,
        el('span', {class: `demo-tag demo-tag-role demo-tag-${user.role}`, text: user.role === 'super-admin' && user.locked && !user.you ? 'super-admin · always' : user.role}));
      box.addEventListener('change', () => summary());
      return {user, box, row};
    });
    const list = el('div', {class: 'demo-mode-users'}, rows.map((item) => item.row));
    search.addEventListener('input', () => {
      const text = search.value.trim().toLowerCase();
      rows.forEach(({user, row}) => { row.hidden = Boolean(text) && !`${user.username} ${user.name} ${user.role}`.toLowerCase().includes(text); });
    });
    const summaryBox = el('div', {class: 'demo-mode-summary', role: 'status'});
    const error = el('p', {class: 'demo-mode-error', role: 'alert', hidden: true});
    function summary() {
      const kept = rows.filter((item) => item.box.checked);
      const out = rows.filter((item) => !item.box.checked);
      const online = out.filter((item) => item.user.online && !item.user.unsaved.length);
      const saving = out.filter((item) => item.user.unsaved.length);
      const names = (items) => items.map((item) => item.user.username).join(', ');
      const items = [];
      if (online.length) items.push(`${online.length} online ${online.length === 1 ? 'user' : 'users'} (${names(online)}) ${online.length === 1 ? 'is' : 'are'} warned and signed out within 5 minutes at most.`);
      if (saving.length) items.push(`${saving.length} online ${saving.length === 1 ? 'user' : 'users'} (${names(saving)}) ${saving.length === 1 ? 'has' : 'have'} unsaved changes: asked to save them, and signed out once saved.`);
      items.push('The other users are signed out at once and cannot sign in until the demo is over; nobody being signed out can start new changes.');
      summaryBox.replaceChildren(el('strong', {text: `${kept.length} ${kept.length === 1 ? 'user keeps' : 'users keep'} access.`}), el('ul', {}, items.map((text) => el('li', {text}))));
    }
    summary();
    [date, time].forEach((input) => input.addEventListener('change', summary));
    const submit = el('button', {type: 'submit', class: 'demo-mode-primary', text: editing ? 'Save changes' : 'Start Demo Mode'});
    const form = el('form', {class: 'demo-mode-form', novalidate: true},
      el('div', {class: 'demo-mode-dialog-body'},
        el('div', {class: 'demo-mode-field', 'data-demo-focus': 'end'},
          el('span', {class: 'demo-mode-label', text: 'Expected end of the demo'}),
          el('div', {class: 'demo-mode-row'}, date, time,
            ...[[30, '+30 min'], [60, '+1 h'], [120, '+2 h']].map(([minutes, label]) => el('button', {type: 'button', class: 'demo-mode-chip', text: label, onclick: () => shift(minutes)}))),
          el('small', {text: 'Demo Mode never ends by itself: at this time you are asked to extend it or end it.'})),
        el('label', {class: 'demo-mode-field'}, el('span', {class: 'demo-mode-label', text: 'Message for the users'}), message,
          el('small', {text: 'A proposed text: change it if you want. The users also see who started the demo and its expected end.'})),
        el('div', {class: 'demo-mode-field', 'data-demo-focus': 'users'},
          el('span', {class: 'demo-mode-label', text: 'Users with access during the demo'}), search, list,
          el('small', {text: data.role === 'super-admin'
            ? 'You always keep access. You can leave the other super-admins out.'
            : 'You always keep access, and so does every super-admin when an admin starts or changes the demo.'})),
        summaryBox, error),
      el('footer', {class: 'demo-mode-dialog-footer'}, el('button', {type: 'button', class: 'demo-mode-secondary', text: 'Cancel', onclick: close}), submit));
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const moment = chosenEnd();
      if (Number.isNaN(moment.getTime()) || moment.getTime() <= Date.now()) {
        error.textContent = 'The expected end of the demo must be later than now.'; error.hidden = false; return;
      }
      submit.disabled = true; error.hidden = true;
      const payload = {expected_end: moment.toISOString(), message: message.value, users: rows.filter((item) => item.box.checked).map((item) => item.user.username)};
      try {
        await request(editing ? '/api/demo-mode/update' : '/api/demo-mode/start', payload);
        close();
        await poll();
      } catch (exc) {
        error.textContent = exc.message; error.hidden = false; submit.disabled = false;
      }
    });
    dialog.append(header('demo-mode-setup-title', 'demo', editing ? 'Change Demo Mode' : 'Start Demo Mode',
      editing ? 'Change the expected end, the message or the users who keep access.' : 'Everyone else is signed out and cannot sign in until you end the demo.'), form);
    (focus === 'users' ? search : focus === 'end' ? time : date).focus?.();
    dialog.querySelector(`[data-demo-focus="${focus}"]`)?.scrollIntoView?.({block: 'nearest'});
  }

  async function endDemo() {
    const confirmed = typeof window.showConfirmDialog === 'function' || typeof showConfirmDialog === 'function'
      ? await (window.showConfirmDialog || showConfirmDialog)('End Demo Mode now? Everybody can sign in again.', {title: 'End Demo Mode', confirmLabel: 'End Demo Mode', cancelLabel: 'Keep it on'})
      : window.confirm('End Demo Mode now? Everybody can sign in again.');
    if (!confirmed) return;
    try { await request('/api/demo-mode/end', {}); } catch (error) { window.alert(error.message); }
    await poll();
  }

  function timeUp() {
    if (timeUpOpen) return;
    timeUpOpen = true;
    const {dialog, close} = modal('demo-mode-time-up', 'demo-mode-time-up-title');
    const done = () => { timeUpOpen = false; close(); poll(); };
    const act = async (payload, url = '/api/demo-mode/update') => {
      try { await request(url, payload); done(); } catch (error) { window.alert(error.message); }
    };
    dialog.append(
      header('demo-mode-time-up-title', 'clock', 'The demo time is up', `Demo Mode was expected to end at ${formatTime(state.expected_end)}. It stays on until you decide.`, 'overdue'),
      el('div', {class: 'demo-mode-dialog-body'},
        el('div', {class: 'demo-mode-field'}, el('span', {class: 'demo-mode-label', text: 'Extend the demo by'}),
          el('div', {class: 'demo-mode-extend'}, (state.extend_minutes || [5, 15, 30, 45, 60]).map((minutes) => el('button', {
            type: 'button', class: 'demo-mode-extend-button', text: `${minutes} min`, onclick: () => act({extend_minutes: minutes}),
          }))),
          el('small', {text: 'The users being kept out see the new expected end.'}))),
      el('footer', {class: 'demo-mode-dialog-footer'},
        el('button', {type: 'button', class: 'demo-mode-secondary', text: 'Remind me in 5 min', onclick: () => act({remind_minutes: 5})}),
        el('button', {type: 'button', class: 'demo-mode-danger', text: 'End Demo Mode now', onclick: () => act({}, '/api/demo-mode/end')})));
  }

  // -- the users being signed out -------------------------------------------------------------------------------
  let leavingView = null;
  let leavingBanner = null;
  let savePromptShown = false;
  const quote = (text) => (text ? el('p', {class: 'demo-mode-message', text: `“${text}”`}) : null);
  function showLeaving(reply) {
    const unsaved = reply.leaving.unsaved || [];
    const started = personName(reply.started_by, reply.started_by_name);
    if (!unsaved.length) {
      leavingBanner?.remove(); leavingBanner = null;
      document.documentElement.classList.remove('demo-mode-saving');
      leavingCountdown = Date.now() + (reply.leaving.seconds_left || 0) * 1000;
      if (!leavingView || !leavingView.backdrop.isConnected || leavingView.kind !== 'countdown') {
        leavingView?.close();
        const {backdrop, dialog, close} = modal('demo-mode-leaving', 'demo-mode-leaving-title');
        const timer = el('span', {class: 'demo-mode-timer', 'data-demo-mode-countdown': true});
        const signOut = el('button', {type: 'button', class: 'demo-mode-secondary', text: 'Sign out now', onclick: async () => {
          signOut.disabled = true;
          await poll({leave: true});
        }});
        dialog.append(el('div', {class: 'demo-mode-notice'},
          el('span', {class: 'demo-mode-notice-icon'}, icon(ICONS.demo)),
          el('h2', {id: 'demo-mode-leaving-title', text: 'A demo is about to start'}),
          el('p', {text: `${started} started Demo Mode. DriveTest Analyzer will be unavailable until about`}),
          el('p', {class: 'demo-mode-until'}, el('time', {'data-demo-mode-time': true, datetime: reply.expected_end, text: formatTime(reply.expected_end)})),
          quote(reply.message),
          el('p', {}, 'You have no unsaved changes. You will be signed out in ', timer),
          signOut));
        leavingView = {backdrop, close, kind: 'countdown'};
      }
      return;
    }
    // Unsaved changes: asked once to save them, then a banner stays on top until they are saved.
    document.documentElement.classList.add('demo-mode-saving');
    if (!savePromptShown) {
      savePromptShown = true;
      leavingView?.close();
      const {backdrop, dialog, close} = modal('demo-mode-leaving', 'demo-mode-save-title');
      dialog.append(el('div', {class: 'demo-mode-notice'},
        el('span', {class: 'demo-mode-notice-icon is-save'}, icon(ICONS.save)),
        el('h2', {id: 'demo-mode-save-title', text: 'Save your changes: a demo is about to start'}),
        el('p', {}, `${started} started Demo Mode. The platform will be unavailable until about `,
          el('strong', {}, el('time', {'data-demo-mode-time': true, datetime: reply.expected_end, text: formatTime(reply.expected_end)})), '.'),
        quote(reply.message),
        el('div', {class: 'demo-mode-pending'}, el('strong', {text: 'Unsaved changes'}), el('ul', {}, unsaved.map((item) => el('li', {text: item})))),
        el('p', {text: 'Save them now (or discard them): you are signed out as soon as nothing is left to save. Meanwhile no new changes can be started.'}),
        el('button', {type: 'button', class: 'demo-mode-save', text: 'Close and save my changes', onclick: () => close()})));
      leavingView = {backdrop, close, kind: 'save'};
    }
    if (!leavingBanner) {
      leavingBanner = el('div', {class: 'demo-mode-banner', role: 'status'});
      document.body.append(leavingBanner);
    }
    leavingBanner.replaceChildren(icon(ICONS.demo), el('span', {},
      el('strong', {text: 'Demo Mode: save your changes. '}),
      `You are signed out as soon as they are saved (${unsaved.join(', ')}); the platform is unavailable until about `,
      el('time', {'data-demo-mode-time': true, datetime: reply.expected_end, text: formatTime(reply.expected_end)}), '.'));
  }

  // While a user is being signed out it starts no new changes: the buttons that would start one are refused.
  const STARTS_CHANGES = /^\s*\+?\s*(new|create|add|edit|duplicate|copy|clone|import|upload|rename|generate|reprocess|recalculate|calculate|run|take|assign|transfer)\b/i;
  document.addEventListener('click', (event) => {
    if (!leaving) return;
    const control = event.target instanceof Element ? event.target.closest('button, a[role="button"], input[type="button"], input[type="submit"], summary') : null;
    if (!control || control.closest('.demo-mode-backdrop, .demo-mode-banner')) return;
    const label = `${control.getAttribute('aria-label') || ''} ${control.textContent || control.value || ''} ${control.getAttribute('title') || ''}`.trim();
    if (!STARTS_CHANGES.test(control.textContent?.trim() || control.value || '') && !STARTS_CHANGES.test(control.getAttribute('aria-label') || '') && !STARTS_CHANGES.test(control.getAttribute('title') || '')) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const note = el('div', {class: 'demo-mode-refused', role: 'alert', text: 'Not available: you are being signed out for a demo. Save or discard your changes.'});
    note.title = label;
    document.body.append(note);
    window.setTimeout(() => note.remove(), 4000);
  }, true);

  window.setInterval(() => {
    document.querySelectorAll('[data-demo-mode-countdown]').forEach((node) => {
      const seconds = Math.max(0, Math.round((leavingCountdown - Date.now()) / 1000));
      node.textContent = formatCountdown(seconds);
      if (!seconds && !node.dataset.asked) { node.dataset.asked = '1'; poll(); }
    });
  }, 1000);

  // -- the poll -------------------------------------------------------------------------------------------------
  async function poll(options = {}) {
    window.clearTimeout(pollTimer);
    let reply = null;
    try {
      reply = await request('/api/demo-mode/heartbeat', {tab, unsaved: unsavedChanges(), leave: Boolean(options.leave)}, true);
    } catch (_error) {
      reply = null;
    }
    if (reply) {
      if (reply.signed_out || (reply.authenticated === false && (leaving || reply.active))) {
        window.location.assign(SIGNED_OUT_URL);
        return;
      }
      state = {...reply, manage: Boolean(reply.manage)};
      leaving = reply.active && reply.leaving ? reply.leaving : null;
      if (leaving) showLeaving(reply);
      else {
        leavingView?.close(); leavingView = null; leavingBanner?.remove(); leavingBanner = null; savePromptShown = false;
        document.documentElement.classList.remove('demo-mode-saving');
      }
      ensurePill();
      if (reply.time_up) timeUp();
      fillTimes();
    }
    const fast = leaving || (state.active && state.manage);
    pollTimer = window.setTimeout(poll, fast ? FAST_POLL : NORMAL_POLL);
  }

  startButton?.addEventListener('click', () => {
    document.getElementById('topnav-user-options')?.hidePopover?.();
    openDialog('start');
  });
  ensurePill();
  poll();
})();
