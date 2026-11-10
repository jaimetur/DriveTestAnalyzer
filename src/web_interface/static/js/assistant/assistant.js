// AI Assistant: the chat of the questions of a user about the active workspace.
// A question is answered in the background (POST /api/assistant/ask): the page follows its steps
// (GET /api/assistant/jobs/<id>) and shows the answer with its tables, its charts (drawn by the chart painter of
// PPT Designer, core/canvas_charts.js), follow-up questions, how it was calculated and what was sent to the AI engine.
(() => {
  'use strict';

  const config = JSON.parse(document.getElementById('assistant-config')?.textContent || '{}');
  const elements = {
    list: document.getElementById('assistant-conversations'),
    emptyList: document.getElementById('assistant-empty-list'),
    messages: document.getElementById('assistant-messages'),
    welcome: document.getElementById('assistant-welcome'),
    title: document.getElementById('assistant-title'),
    rename: document.getElementById('assistant-rename'),
    remove: document.getElementById('assistant-delete'),
    composer: document.getElementById('assistant-composer'),
    question: document.getElementById('assistant-question'),
    engine: document.getElementById('assistant-engine'),
    send: document.getElementById('assistant-send'),
    stop: document.getElementById('assistant-stop'),
    status: document.getElementById('assistant-status'),
    newButton: document.getElementById('assistant-new'),
  };
  const state = {conversations: config.conversations || [], current: null, job: null, poll: null};
  const STORAGE_KEY = `assistant:conversation:${config.workspace || ''}`;

  const element = (tag, className = '', text = '') => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  };
  const remember = (id) => { try { if (id) localStorage.setItem(STORAGE_KEY, String(id)); else localStorage.removeItem(STORAGE_KEY); } catch (_error) { /* private mode */ } };
  const remembered = () => { try { return Number(localStorage.getItem(STORAGE_KEY)) || null; } catch (_error) { return null; } };

  async function api(url, options = {}) {
    const response = await fetch(url, {headers: {'Content-Type': 'application/json'}, ...options});
    let body = null;
    try { body = await response.json(); } catch (_error) { body = null; }
    if (!response.ok) {
      const detail = body && (typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail));
      throw new Error(detail || `The request failed (${response.status}).`);
    }
    return body;
  }

  function setStatus(text, error = false) {
    elements.status.textContent = text || '';
    elements.status.classList.toggle('error', Boolean(error));
  }

  function setBusy(busy) {
    elements.send.disabled = busy;
    elements.stop.hidden = !busy;
    elements.question.disabled = false;
  }

  // -- conversations ------------------------------------------------------------------------------------------------

  function renderConversations() {
    elements.list.replaceChildren(...state.conversations.map((conversation) => {
      const item = element('li');
      const button = element('button', 'assistant-conversation', conversation.title || 'Conversation');
      button.type = 'button';
      button.title = `${conversation.title || 'Conversation'} · ${conversation.messages || 0} messages · ${String(conversation.updated_at || '').slice(0, 16).replace('T', ' ')}`;
      button.classList.toggle('active', state.current === conversation.id);
      button.addEventListener('click', () => openConversation(conversation.id));
      item.append(button);
      return item;
    }));
    elements.emptyList.hidden = state.conversations.length > 0;
  }

  async function refreshConversations() {
    const body = await api('/api/assistant/conversations');
    state.conversations = body.conversations || [];
    renderConversations();
  }

  function showHeader(conversation) {
    elements.title.textContent = conversation ? (conversation.title || 'Conversation') : 'New conversation';
    elements.rename.hidden = elements.remove.hidden = !conversation;
  }

  function newConversation() {
    stopPolling();
    state.current = null;
    remember(null);
    showHeader(null);
    elements.messages.replaceChildren(elements.welcome);
    elements.welcome.hidden = false;
    renderConversations();
    setBusy(false);
    setStatus('');
    elements.question.focus();
  }

  async function openConversation(id) {
    stopPolling();
    try {
      const body = await api(`/api/assistant/conversations/${id}`);
      state.current = body.conversation.id;
      remember(state.current);
      showHeader(body.conversation);
      elements.messages.replaceChildren(...body.messages.map(renderMessage));
      renderConversations();
      setStatus('');
      if (body.job) {
        follow(body.job);
      } else {
        setBusy(false);
      }
      scrollToEnd();
    } catch (error) {
      remember(null);
      setStatus(error.message, true);
    }
  }

  // -- messages -----------------------------------------------------------------------------------------------------

  // Figures (with a % or the * of a partial value) are aligned to the right.
  const NUMERIC = /^[−+-]?[\d.,\s]+\s?[%*]?$/;

  // A table as a CSV file (with a BOM, so Excel reads its accents), named after its title.
  function downloadTable(table) {
    const quote = (value) => {
      const text = String(value ?? '');
      return /[",;\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
    };
    const lines = [table.columns || [], ...(table.rows || [])].map((row) => row.map(quote).join(','));
    const blob = new Blob(['\ufeff' + lines.join('\r\n')], {type: 'text/csv;charset=utf-8'});
    const link = element('a');
    link.href = URL.createObjectURL(blob);
    link.download = `${(table.title || 'ai-assistant-table').replace(/[\\/:*?"<>|]+/g, ' ').trim().slice(0, 80) || 'ai-assistant-table'}.csv`;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  }

  function renderTable(table) {
    const box = element('figure', 'assistant-table-box');
    const rows = (table.rows || []).length;
    const caption = element('figcaption', 'assistant-table-caption');
    caption.append(element('span', 'assistant-table-title', table.title || ''));
    const tools = element('span', 'assistant-table-tools');
    tools.append(element('span', 'assistant-table-count', `${rows.toLocaleString()} ${rows === 1 ? 'row' : 'rows'}${table.truncated ? ' (first ones)' : ''}`));
    const download = element('button', 'assistant-link', 'Download CSV');
    download.type = 'button';
    download.addEventListener('click', () => downloadTable(table));
    tools.append(download);
    caption.append(tools);
    box.append(caption);
    const scroller = element('div', `assistant-table-scroll${rows > 15 ? ' long' : ''}`);
    // A query result (its rows given by the tool) keeps each value on one line, its headers aligned as their column.
    const result = Boolean(table.result);
    const grid = element('table', `assistant-table${result ? ' assistant-result-table' : ''}`);
    const numericColumn = (index) => (table.rows || []).some((row) => String(row[index] ?? '').trim())
      && (table.rows || []).every((row) => !String(row[index] ?? '').trim() || NUMERIC.test(String(row[index]).trim()));
    const head = element('thead');
    const headRow = element('tr');
    (table.columns || []).forEach((column, index) => headRow.append(element('th', result && numericColumn(index) ? 'numeric' : '', column)));
    head.append(headRow);
    const body = element('tbody');
    (table.rows || []).forEach((row) => {
      const line = element('tr');
      row.forEach((cell) => {
        const item = element('td', NUMERIC.test(String(cell).trim()) ? 'numeric' : '', cell);
        if (result && String(cell).length > 40) item.title = String(cell);
        line.append(item);
      });
      body.append(line);
    });
    grid.append(head, body);
    scroller.append(grid);
    box.append(scroller);
    return box;
  }

  // -- charts -------------------------------------------------------------------------------------------------------

  const fileName = (title, fallback) => (title || fallback).replace(/[\\/:*?"<>|]+/g, ' ').trim().slice(0, 80) || fallback;

  // The canvas of a chart, drawn once it is on the page (the painter measures its box). In the answer its title is
  // above it (as PPT Designer does for its small charts): drawn in a small chart, it would cover the legend.
  function chartCanvas(chart, className, titled = false) {
    const holder = element('div', className);
    const canvas = element('canvas');
    canvas.setAttribute('role', 'img');
    canvas.setAttribute('aria-label', chart.title || 'Chart');
    holder.append(canvas);
    const draw = () => {
      if (!canvas.isConnected) { requestAnimationFrame(draw); return; }
      if (typeof globalThis.renderCanvasChart !== 'function') {
        holder.replaceChildren(element('p', 'form-note', 'The chart could not be drawn: reload the page.'));
        return;
      }
      try { globalThis.renderCanvasChart(canvas, titled ? chart.model : {...chart.model, hide_title: true}); } catch (error) {
        holder.replaceChildren(element('p', 'form-note', `The chart could not be drawn: ${error.message}`));
      }
    };
    requestAnimationFrame(draw);
    return {holder, canvas};
  }

  function downloadChart(canvas, title) {
    canvas.toBlob((blob) => {
      if (!blob) return;
      const link = element('a');
      link.href = URL.createObjectURL(blob);
      link.download = `${fileName(title, 'ai-assistant-chart')}.png`;
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    }, 'image/png');
  }

  // A chart larger, over the page (Escape or Close closes it).
  function expandChart(chart) {
    const overlay = element('div', 'confirm-overlay assistant-dialog assistant-chart-overlay');
    const panel = element('div', 'confirm-panel assistant-chart-panel');
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-modal', 'true');
    panel.setAttribute('aria-label', chart.title || 'Chart');
    const {holder, canvas} = chartCanvas(chart, 'assistant-chart-canvas assistant-chart-canvas-large', true);
    const actions = element('div', 'confirm-actions');
    const download = element('button', 'secondary', 'Download PNG');
    download.type = 'button';
    download.addEventListener('click', () => downloadChart(canvas, chart.title));
    const close = element('button', '', 'Close');
    close.type = 'button';
    const closeOverlay = () => { overlay.remove(); document.removeEventListener('keydown', onKey); };
    const onKey = (event) => { if (event.key === 'Escape') closeOverlay(); };
    close.addEventListener('click', closeOverlay);
    overlay.addEventListener('click', (event) => { if (event.target === overlay) closeOverlay(); });
    document.addEventListener('keydown', onKey);
    actions.append(download, close);
    panel.append(holder, actions);
    overlay.append(panel);
    document.body.append(overlay);
    close.focus();
  }

  function renderChart(chart) {
    const box = element('figure', 'assistant-table-box assistant-chart-box');
    const caption = element('figcaption', 'assistant-table-caption');
    caption.append(element('span', 'assistant-table-title', chart.title || ''));
    const tools = element('span', 'assistant-table-tools');
    const origin = chart.origin ? `PPT Designer · ${chart.origin}` : '';
    if (origin) tools.append(element('span', 'assistant-table-count', origin));
    // Horizontal bars of many KPIs take a taller box, so their names keep a readable size.
    const rows = chart.model.type === 'hbar' ? (chart.model.row_keys || []).length : 0;
    const {holder, canvas} = chartCanvas(chart, `assistant-chart-canvas${rows > 12 ? ' tall' : ''}`);
    const expand = element('button', 'assistant-link', 'Expand');
    expand.type = 'button';
    expand.addEventListener('click', () => expandChart(chart));
    const download = element('button', 'assistant-link', 'Download PNG');
    download.type = 'button';
    download.addEventListener('click', () => downloadChart(canvas, chart.title));
    tools.append(expand, download);
    caption.append(tools);
    box.append(caption, holder);
    return box;
  }

  function renderText(container, text) {
    if (window.RichText && typeof window.RichText.renderInto === 'function') {
      window.RichText.renderInto(container, text || '');
    } else {
      container.textContent = text || '';
    }
  }

  function renderTrace(trace) {
    const details = element('details', 'assistant-trace');
    details.append(element('summary', '', `How it was calculated (${trace.length} ${trace.length === 1 ? 'step' : 'steps'})`));
    const list = element('ol');
    trace.forEach((entry) => {
      const item = element('li', entry.error ? 'failed' : '');
      item.append(element('strong', '', entry.tool));
      if (entry.summary) item.append(element('span', '', ` — ${entry.summary}`));
      if (entry.error) item.append(element('span', 'assistant-trace-error', ` — ${entry.error}`));
      const code = element('code', 'assistant-trace-arguments', typeof entry.arguments === 'string' ? entry.arguments : JSON.stringify(entry.arguments));
      item.append(element('br'), code, element('span', 'assistant-trace-time', ` ${(Number(entry.duration_ms || 0) / 1000).toFixed(1)} s`));
      list.append(item);
    });
    details.append(list);
    return details;
  }

  function renderMessage(message) {
    if (message.role === 'user') {
      const bubble = element('div', 'assistant-message assistant-user');
      bubble.append(element('div', 'assistant-bubble', message.content));
      return bubble;
    }
    const wrap = element('div', `assistant-message assistant-answer ${message.status !== 'done' ? 'assistant-failed' : ''}`);
    wrap.dataset.messageId = message.id;
    const bubble = element('div', 'assistant-bubble');
    if (message.status !== 'done') {
      bubble.append(element('p', 'assistant-error', message.warning || 'No answer.'));
      wrap.append(bubble);
      return wrap;
    }
    const text = element('div', 'assistant-text');
    renderText(text, message.content);
    bubble.append(text);
    (message.charts || []).forEach((chart) => { if (chart && chart.model) bubble.append(renderChart(chart)); });
    (message.tables || []).forEach((table) => bubble.append(renderTable(table)));
    if (message.warning) bubble.append(element('p', 'assistant-warning', message.warning));
    if ((message.follow_ups || []).length) {
      const chips = element('div', 'assistant-follow-ups');
      message.follow_ups.forEach((question) => {
        const chip = element('button', 'assistant-chip', question);
        chip.type = 'button';
        chip.addEventListener('click', () => ask(question));
        chips.append(chip);
      });
      bubble.append(chips);
    }
    wrap.append(bubble);
    const foot = element('div', 'assistant-foot');
    const seconds = (Number(message.duration_ms || 0) / 1000).toFixed(1);
    const tokens = Number(message.input_tokens || 0) + Number(message.output_tokens || 0);
    foot.append(element('span', 'assistant-meta', [message.engine_label, message.model, `${seconds} s`,
      tokens ? `${tokens.toLocaleString()} tokens` : ''].filter(Boolean).join(' · ')));
    foot.append(feedbackButton(message, 'up', '👍', 'Useful answer'), feedbackButton(message, 'down', '👎', 'Wrong or not useful: tell why'));
    const sent = element('button', 'assistant-link', 'What was sent');
    sent.type = 'button';
    sent.addEventListener('click', () => showSent(message.id));
    const suggest = element('button', 'assistant-link', 'Suggest a glossary term');
    suggest.type = 'button';
    suggest.addEventListener('click', () => openSuggestion(message.id));
    foot.append(sent, suggest);
    wrap.append(foot);
    if ((message.trace || []).length) wrap.append(renderTrace(message.trace));
    if (message.feedback_comment) wrap.append(element('p', 'form-note assistant-feedback-note', `Your feedback: ${message.feedback_comment}`));
    return wrap;
  }

  function feedbackButton(message, value, label, title) {
    const button = element('button', `assistant-feedback ${message.feedback === value ? 'chosen' : ''}`, label);
    button.type = 'button';
    button.title = title;
    button.setAttribute('aria-pressed', String(message.feedback === value));
    const send = async (chosen, comment) => {
      try {
        const body = await api(`/api/assistant/messages/${message.id}/feedback`, {method: 'POST', body: JSON.stringify({value: chosen, comment})});
        document.querySelector(`.assistant-answer[data-message-id="${message.id}"]`)?.replaceWith(renderMessage(body.message));
      } catch (error) {
        setStatus(error.message, true);
      }
    };
    button.addEventListener('click', () => {
      const chosen = message.feedback === value ? '' : value;
      if (chosen !== 'down') {
        send(chosen, '');
        return;
      }
      // What was wrong: optional, it helps to improve the answers and the glossary.
      const wrap = button.closest('.assistant-answer');
      wrap.querySelector('.assistant-feedback-form')?.remove();
      const form = element('form', 'assistant-feedback-form');
      const field = element('textarea');
      field.rows = 2;
      field.maxLength = 2000;
      field.placeholder = 'What was wrong? (optional)';
      field.value = message.feedback_comment || '';
      const submit = element('button', '', 'Send feedback');
      submit.type = 'submit';
      const cancel = element('button', 'secondary', 'Cancel');
      cancel.type = 'button';
      cancel.addEventListener('click', () => form.remove());
      form.append(field, submit, cancel);
      form.addEventListener('submit', (event) => { event.preventDefault(); send('down', field.value); });
      wrap.append(form);
      field.focus();
    });
    return button;
  }

  function scrollToEnd() {
    elements.messages.scrollTop = elements.messages.scrollHeight;
  }

  // -- asking -------------------------------------------------------------------------------------------------------

  function pendingBubble() {
    const wrap = element('div', 'assistant-message assistant-answer assistant-pending');
    const bubble = element('div', 'assistant-bubble');
    bubble.append(element('span', 'assistant-typing', ''), element('ol', 'assistant-steps'));
    wrap.append(bubble);
    return wrap;
  }

  function showSteps(steps) {
    const list = elements.messages.querySelector('.assistant-pending .assistant-steps');
    if (!list) return;
    list.replaceChildren(...(steps || []).map((step, index, all) => element('li', index === all.length - 1 ? 'current' : '', step)));
    scrollToEnd();
  }

  function stopPolling() {
    if (state.poll) clearTimeout(state.poll);
    state.poll = null;
    state.job = null;
  }

  function follow(job) {
    state.job = job;
    setBusy(true);
    if (!elements.messages.querySelector('.assistant-pending')) elements.messages.append(pendingBubble());
    showSteps(job.steps);
    // A check that fails (the network, a restart of the server) is tried again a few times: the answer is still on its way.
    let failedChecks = 0;
    const tick = async () => {
      if (!state.job || state.job.id !== job.id) return;
      try {
        const current = await api(`/api/assistant/jobs/${job.id}`);
        failedChecks = 0;
        showSteps(current.steps);
        if (current.status === 'running') {
          state.poll = setTimeout(tick, 1000);
          return;
        }
        elements.messages.querySelector('.assistant-pending')?.remove();
        if (current.message) elements.messages.append(renderMessage(current.message));
        stopPolling();
        setBusy(false);
        setStatus(current.status === 'done' ? '' : current.error, current.status === 'failed');
        scrollToEnd();
        refreshConversations().catch(() => {});
      } catch (error) {
        failedChecks += 1;
        if (failedChecks < 5) {
          state.poll = setTimeout(tick, 2000);
          return;
        }
        elements.messages.querySelector('.assistant-pending')?.remove();
        stopPolling();
        setBusy(false);
        setStatus(error.message, true);
      }
    };
    state.poll = setTimeout(tick, 800);
  }

  async function ask(text) {
    const question = String(text ?? elements.question.value).trim();
    if (!question || state.job) return;
    elements.welcome.hidden = true;
    const userMessage = renderMessage({role: 'user', content: question});
    elements.messages.append(userMessage);
    elements.question.value = '';
    setBusy(true);
    setStatus('');
    scrollToEnd();
    try {
      const body = await api('/api/assistant/ask', {method: 'POST', body: JSON.stringify({
        question, conversation_id: state.current, engine: elements.engine?.value || '',
      })});
      state.current = body.conversation_id;
      remember(state.current);
      state.conversations = body.conversations || state.conversations;
      showHeader(state.conversations.find((item) => item.id === state.current));
      renderConversations();
      follow(body.job);
    } catch (error) {
      userMessage.remove();
      elements.question.value = question;
      setBusy(false);
      setStatus(error.message, true);
    }
  }

  async function stop() {
    if (!state.job) return;
    elements.stop.disabled = true;
    try {
      await api(`/api/assistant/jobs/${state.job.id}/stop`, {method: 'POST'});
      setStatus('Stopping…');
    } catch (error) {
      setStatus(error.message, true);
    } finally {
      elements.stop.disabled = false;
    }
  }

  // -- dialogs ------------------------------------------------------------------------------------------------------

  async function showSent(messageId) {
    const dialog = document.getElementById('assistant-sent-dialog');
    const steps = document.getElementById('assistant-sent-steps');
    const legend = document.getElementById('assistant-sent-legend');
    steps.replaceChildren(element('p', 'form-note', 'Loading…'));
    legend.replaceChildren();
    dialog.hidden = false;
    try {
      const body = await api(`/api/assistant/messages/${messageId}/sent`);
      legend.replaceChildren(...body.legend.map((item) => {
        const chip = element('span', 'assistant-legend-item');
        chip.append(element('code', '', item.code), element('span', '', ` ${item.name}`));
        chip.title = item.kind;
        return chip;
      }));
      const system = element('details', 'assistant-sent-step');
      system.append(element('summary', '', 'Instructions of the assistant (the same for every question)'), element('pre', '', body.system_prompt));
      steps.replaceChildren(system, ...body.sent.map((item) => {
        const block = element('details', 'assistant-sent-step');
        block.open = item.step === 1;
        block.append(element('summary', '', `Request ${item.step}`), element('h4', '', 'Sent'), element('pre', '', item.sent));
        if (item.received) block.append(element('h4', '', 'Received'), element('pre', '', item.received));
        return block;
      }));
    } catch (error) {
      steps.replaceChildren(element('p', 'form-note error', error.message));
    }
  }

  function openSuggestion(messageId) {
    const dialog = document.getElementById('assistant-suggest-dialog');
    dialog.dataset.messageId = messageId;
    document.getElementById('assistant-suggest-term').value = '';
    document.getElementById('assistant-suggest-meaning').value = '';
    document.getElementById('assistant-suggest-status').textContent = '';
    dialog.hidden = false;
    document.getElementById('assistant-suggest-term').focus();
  }

  document.getElementById('assistant-suggest-form')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const dialog = document.getElementById('assistant-suggest-dialog');
    const status = document.getElementById('assistant-suggest-status');
    try {
      await api(`/api/assistant/messages/${dialog.dataset.messageId}/suggest`, {method: 'POST', body: JSON.stringify({
        term: document.getElementById('assistant-suggest-term').value, meaning: document.getElementById('assistant-suggest-meaning').value,
      })});
      dialog.hidden = true;
      setStatus('Suggestion sent: an editor of Workspace Configuration accepts it in the AI Assistant Glossary.');
    } catch (error) {
      status.textContent = error.message;
    }
  });
  document.getElementById('assistant-suggest-cancel')?.addEventListener('click', () => { document.getElementById('assistant-suggest-dialog').hidden = true; });
  document.getElementById('assistant-sent-close')?.addEventListener('click', () => { document.getElementById('assistant-sent-dialog').hidden = true; });
  document.querySelectorAll('.assistant-dialog').forEach((dialog) => dialog.addEventListener('click', (event) => {
    if (event.target === dialog) dialog.hidden = true;
  }));
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') document.querySelectorAll('.assistant-dialog:not([hidden])').forEach((dialog) => { dialog.hidden = true; });
  });

  // -- header actions -----------------------------------------------------------------------------------------------

  elements.rename.addEventListener('click', () => {
    if (!state.current) return;
    const input = element('input', 'assistant-title-input');
    input.value = elements.title.textContent;
    input.maxLength = 120;
    input.setAttribute('aria-label', 'Name of the conversation');
    elements.title.replaceChildren(input);
    input.focus();
    input.select();
    let done = false;
    const finish = async (save) => {
      if (done) return;
      done = true;
      const title = input.value.trim();
      if (!save || !title) {
        showHeader(state.conversations.find((item) => item.id === state.current));
        return;
      }
      try {
        await api(`/api/assistant/conversations/${state.current}/rename`, {method: 'POST', body: JSON.stringify({title})});
        await refreshConversations();
        showHeader(state.conversations.find((item) => item.id === state.current));
      } catch (error) {
        setStatus(error.message, true);
        showHeader(state.conversations.find((item) => item.id === state.current));
      }
    };
    input.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') { event.preventDefault(); finish(true); }
      if (event.key === 'Escape') finish(false);
    });
    input.addEventListener('blur', () => finish(true));
  });

  elements.remove.addEventListener('click', async () => {
    if (!state.current) return;
    const conversation = state.conversations.find((item) => item.id === state.current);
    const confirmed = typeof window.showConfirmDialog === 'function'
      ? Boolean(await window.showConfirmDialog(`Delete the conversation "${conversation?.title || ''}" and its answers? This cannot be undone.`,
        {title: 'Delete Conversation', confirmLabel: 'Delete', cancelLabel: 'Cancel'}))
      : window.confirm('Delete this conversation and its answers?');
    if (!confirmed) return;
    try {
      await api(`/api/assistant/conversations/${state.current}`, {method: 'DELETE'});
      await refreshConversations();
      newConversation();
    } catch (error) {
      setStatus(error.message, true);
    }
  });

  // -- composer -----------------------------------------------------------------------------------------------------

  elements.composer.addEventListener('submit', (event) => { event.preventDefault(); ask(); });
  elements.question.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      ask();
    }
  });
  elements.stop.addEventListener('click', stop);
  elements.newButton.addEventListener('click', newConversation);
  document.querySelectorAll('[data-example]').forEach((button) => button.addEventListener('click', () => ask(button.dataset.example)));

  const engines = (config.engines && config.engines.engines) || [];
  if (!engines.length) {
    elements.send.disabled = true;
    elements.question.disabled = true;
    setStatus('No AI engine is enabled yet: a super-admin enables Kiro CLI or Claude in Super Admin → AI Comment Writers.', true);
  } else if ((config.engines.missing_user_keys || []).length) {
    setStatus(`Add your API key of ${config.engines.missing_user_keys.join(' or ')} in the user menu (API keys) to ask with it.`);
  }

  renderConversations();
  const last = remembered();
  if (last && state.conversations.some((item) => item.id === last)) openConversation(last);
})();
