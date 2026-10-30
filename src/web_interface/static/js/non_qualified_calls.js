/* Non-Qualified Calls: executive summary, drill-down table, follow-up and shared comments. */
(() => {
  'use strict';

  const root = document.getElementById('non-qualified-calls');
  // On a phone the introduction of the hero shows its first lines: More shows it whole (with or without a workspace).
  root?.querySelector('[data-nq-hero-more]')?.addEventListener('click', (event) => {
    const more = event.currentTarget;
    const open = more.closest('.nq-hero').classList.toggle('is-open');
    more.setAttribute('aria-expanded', String(open));
    more.textContent = open ? 'Less' : 'More';
  });
  if (!root || !document.getElementById('nq-table')) return;

  const $ = (id) => document.getElementById(id);
  // The provider of the CDRs of the workspace and its RCA, the source of the CDR (NetCheck and the NetCheck RCA in a
  // NetCheck workspace).
  const PROVIDER = (() => {
    try { return JSON.parse(root.dataset.nqProvider || '{}') || {}; } catch (_error) { return {}; }
  })();
  const PROVIDER_NAME = PROVIDER.name || 'NetCheck';
  const PROVIDER_RCA = PROVIDER.rca || 'NetCheck RCA';
  const node = (tag, text, className) => {
    const element = document.createElement(tag);
    if (text !== undefined && text !== null) element.textContent = text;
    if (className) element.className = className;
    return element;
  };
  const SERVICE_LABELS = {voice: 'Voice', speech: 'Speech', data: 'Data'};
  const FIELD_LABELS = {
    service: 'Service', campaign: 'Campaign', operator: 'Operator', operator_vendor: 'Operator_Vendor', vendor_operator: 'Vendor_Operator', vendor: 'Vendor',
    region: 'Region', cluster: 'Cluster', city: 'City', dataset_id: 'CDR', join_id: 'Join ID',
    technology: 'Technology', test_name: 'Test Name', result: 'Result', failure_classification: 'Failure Classification',
    failure_category: 'Failure Category', status: 'Global Status', team: 'Team', assignee: 'Assignee', datasets: 'CDR',
    root_domain: 'Root Domain', root_category: 'Root Category', root_cause: 'Root Cause', status_mode: 'Status Set',
    nr_mode: 'NR Mode', call_type: 'Call Type', period: 'Period',
    age: 'Age of Open Calls', root_pair: 'Root Domain · Cause', effective_domain: 'Root Domain (with suggestions)',
    effective_cause: 'Root Domain · Cause (with suggestions)', node: 'eNB / gNB', place: 'Repetition Place', hotspot: 'Hotspot',
    consecutive_issue: 'Time-Window Issue', clustered_issue: 'Clustered Issue', state: 'Follow-up',
    rca_state: 'Root Cause',
    netcheck_domain: `Root Domain (${PROVIDER_RCA})`, netcheck_category: `Root Domain · Category (${PROVIDER_RCA})`,
    netcheck_cause: `Root Domain · Cause (${PROVIDER_RCA})`, script_domain: 'Root Domain (Ericsson RCA)',
    script_category: 'Root Domain · Category (Ericsson RCA)', script_cause: 'Root Domain · Cause (Ericsson RCA)',
    dta_domain: 'Root Domain (DT Analyzer RCA)', dta_category: 'Root Domain · Category (DT Analyzer RCA)',
    dta_cause: 'Root Domain · Cause (DT Analyzer RCA)',
    dta_raw: 'Category · Cause (DT Analyzer RCA)', netcheck_raw: `Category · Cause (${PROVIDER_RCA})`,
    script_raw: 'Category · Cause (Ericsson RCA)',
    version: 'CDR Version',
  };
  // How the CDRs see a call; "current" is the latest version with nothing to tell.
  const VERSION_HINTS = {
    changed: 'Its result or failure is different in another CDR',
    newer: 'A more recent CDR that is not chosen in the CDRs filter has this call',
    not_in_final: 'Only in Weekly or Daily CDRs, while a Final CDR covers its campaign',
    qualified: 'Completed in a more recent CDR',
  };
  const STATE_LABELS = {closed: 'Closed', attended: 'Attended', not_attended: 'Not attended', with_team: 'With team',
    assigned: 'Assigned', commented: 'Commented', labelled: 'With a root cause', suggested: 'Suggested root cause',
    identified: 'RCA identified', not_identified: 'RCA not identified', open: 'Open', stalled: 'Stalled'};
  // Filters set by clicking the Progress View and the Root Cause Analysis; they have no select of their own.
  // NR Mode has its own filter, the first of the General Filters.
  const EXTRA_FILTERS = ['call_type', 'period', 'age', 'root_pair', 'effective_domain', 'effective_cause', 'node',
    'netcheck_domain', 'netcheck_category', 'netcheck_cause', 'script_domain', 'script_category', 'script_cause',
    'dta_domain', 'dta_category', 'dta_cause', 'dta_raw', 'netcheck_raw', 'script_raw', 'rca_state', 'place', 'hotspot', 'consecutive_issue', 'clustered_issue'];
  // The filters of the groups of the NQ Prioritization: one at a time, the group chosen replaces the one filtered before.
  const GROUP_FILTERS = ['hotspot', 'consecutive_issue', 'clustered_issue'];
  // What each group of a call is, as the map of the call names the one that filters the list.
  const GROUP_LABELS = {hotspot: 'hotspot', cluster: 'cluster', cluster_all: 'cluster of every NR Mode', run: 'time window'};
  // The map of the open call paints the group that filters the list (set once the map is mounted).
  let refreshCallMap = () => {};
  // The values of the Follow-up filter (also set by the indicator cards), in their order.
  const FOLLOW_UP_STATES = ['attended', 'not_attended', 'open', 'stalled', 'closed', 'with_team', 'assigned', 'commented', 'labelled',
    'identified', 'not_identified'];
  const HISTORY_LABELS = {status: 'Status', status_auto: 'Status (automatic)', status_mode: 'Status Set', team: 'Team',
    assignee: 'Assignee', root_domain: 'Root Domain', root_category: 'Root Category', root_cause: 'Root Cause'};
  // The label of a changed field: a follow-up field or a catalog field ("field:key").
  const historyLabel = (field) => (field.startsWith('field:')
    ? (state.fields.find((item) => item.key === field.slice(6))?.label || field.slice(6)) : (HISTORY_LABELS[field] || field));
  const NOT_CLASSIFIED = 'Not classified';
  const NO_CAUSE = 'No cause';
  // Whether the NQ Call Status follows the Status Rules or was chosen by hand.
  const STATUS_MODE_LABELS = {auto: 'Automatic', manual: 'By hand'};
  // The status selects offer this value to give the status back to the Status Rules.
  const AUTO_STATUS = '__auto__';
  // Where a catalog field takes its value from, as a short tag.
  const SOURCE_TAGS = {user: 'Analyst', tracking: 'Follow-up', cdr: 'CDR', rca: 'Ericsson RCA', dta: 'DT Analyzer RCA', derived: 'Derived'};
  const CONFIDENCE_LABELS = {high: 'High confidence', medium: 'Medium confidence', low: 'Low confidence'};
  // The sections whose first list field is a phase of the follow-up.
  const PHASE_SECTIONS = ['analysis', 'implementation', 'planning'];
  // Campaigns as the workspace Campaign Maps show them (campaign_labels.js); filters keep the full value.
  const campaignLabel = (value) => (globalThis.campaignLabel ? globalThis.campaignLabel(value) : String(value ?? ''));
  // A field value travels in the bulk select as "key||value".
  const ROOT_SEPARATOR = '||';
  const REFRESH_INTERVAL_MS = 60000;

  const state = {
    options: {statuses: [], teams: []}, rootCauses: {domains: [], categories: [], causes: [], require_to_close: false}, users: [], userNames: {},
    defaultUsers: [],
    user: {username: '', can_edit: false, can_moderate: false},
    unassigned: '__unassigned__', datasets: [], mainCities: [], sort: 'start_time', direction: 'desc', page: 1, pageSize: 10,
    result: null, selected: new Set(), detail: null, requestToken: 0, busy: false, extraFilters: {}, stale: new Set(),
    // The name of each hotspot and time-window issue the NQ Prioritization listed (its operator, site and time), for
    // the Hotspot and Time-Window Issue filters.
    hotspotLabels: {},
    fields: [], fieldTypes: {}, tableColumns: {builtin: [], cdr: []}, optionalColumns: {}, cdrColumns: [], versionLabels: {},
    // The table layouts: that of the workspace, that of the user and which one they see; ``layout`` is the one shown.
    layouts: null, layout: {builtin: [], cdr: [], export_cdr: [], fields: [], excel_fields: [], known_fields: [], order: []},
    rateService: '', failureService: '', sections: [], statusRules: [], conditionFields: {}, ruleOperators: {}, fieldSources: {}, trackingRefs: {},
    rcaRefs: {}, dtaRefs: {}, dtaRca: {}, callFields: [], rcaResults: {}, rcaSources: {}, matrixSource: 'dta',
    // The values each filter offers among the calls of the other filters (null until known: every value).
    available: null, availableSignature: '',
  };

  // -- helpers --------------------------------------------------------------
  const api = async (url, init = {}) => {
    const response = await fetch(url, {credentials: 'same-origin', ...init,
      headers: init.body ? {'Content-Type': 'application/json', ...(init.headers || {})} : init.headers});
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(typeof payload.detail === 'string' ? payload.detail : 'The request failed.');
      error.status = response.status;
      throw error;
    }
    return payload;
  };
  const toast = (message, tone = 'done') => {
    const element = node('div', message, `nq-toast is-${tone}`);
    element.setAttribute('role', tone === 'error' ? 'alert' : 'status');
    document.body.append(element);
    window.setTimeout(() => element.classList.add('is-leaving'), 3600);
    window.setTimeout(() => element.remove(), 4000);
  };
  const debounce = (callback, delay) => {
    let timer = null;
    return (...args) => { window.clearTimeout(timer); timer = window.setTimeout(() => callback(...args), delay); };
  };
  const parseTime = (value) => {
    if (!value) return null;
    const parsed = new Date(String(value).replace(' ', 'T'));
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  };
  const exactTime = (value) => {
    const parsed = parseTime(value);
    return parsed ? parsed.toLocaleString(undefined, {dateStyle: 'medium', timeStyle: 'short'}) : (value || '—');
  };
  const relativeTime = (value) => {
    const parsed = parseTime(value);
    if (!parsed) return value || '';
    const seconds = Math.round((Date.now() - parsed.getTime()) / 1000);
    if (seconds < 45) return 'just now';
    if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
    if (seconds < 86400) return `${Math.round(seconds / 3600)} h ago`;
    if (seconds < 7 * 86400) return `${Math.round(seconds / 86400)} d ago`;
    return parsed.toLocaleDateString(undefined, {dateStyle: 'medium'});
  };
  const cdrTime = (value) => (value ? String(value).replace('T', ' ').replace(/\.\d+$/, '') : '—');
  const percent = (part, total) => (total ? `${Math.round((part / total) * 100)}%` : '0%');
  // Numbers read as in English, the language of the app, whatever the browser's: a comma between thousands (also
  // in four-digit numbers) and a point before decimals.
  const numberFormat = new Intl.NumberFormat('en-US');
  const number = (value) => numberFormat.format(Number(value || 0));
  // When the first or last call of a group started: 20 Nov 16:18 (the day, the month in letters and the time; the year, which
  // the campaign tells, left out), and the period of a group from its first to its last call (the time alone on the same day).
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const momentText = (value) => {
    const match = String(value || '').match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/);
    return match ? `${match[3]} ${MONTHS[Number(match[2]) - 1]} ${match[4]}:${match[5]}` : '';
  };
  const groupPeriod = (item) => {
    const first = momentText(item.first);
    const last = momentText(item.last);
    if (!first) return '';
    if (!last || last === first) return first;
    return String(item.first).slice(0, 10) === String(item.last).slice(0, 10) ? `${first}–${last.slice(-5)}` : `${first}–${last}`;
  };
  // Readable text on any option colour.
  const contrastText = (hex) => {
    const match = /^#?([0-9a-f]{6})$/i.exec(hex || '');
    if (!match) return '#fff';
    const value = parseInt(match[1], 16);
    const channel = (shift) => {
      const c = ((value >> shift) & 255) / 255;
      return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    };
    const luminance = 0.2126 * channel(16) + 0.7152 * channel(8) + 0.0722 * channel(0);
    return luminance > 0.45 ? '#2a1a20' : '#fff';
  };
  // A Root Category or Root Cause of the catalog, by name.
  const rootItem = (kind, name) => (name ? (kind === 'root_category' ? state.rootCauses.categories : state.rootCauses.causes)
    .find((item) => item.name.toLowerCase() === String(name).toLowerCase()) : null);
  const domainColor = (name) => state.rootCauses.domains.find((item) => item.name === name)?.color || '';
  // Root categories or causes grouped by domain, in the catalog order; a preferred domain first, those without one last.
  const rootGroups = (items, preferred = '') => {
    const names = state.rootCauses.domains.map((domain) => domain.name);
    const order = [...(preferred && names.includes(preferred) ? [preferred] : []), ...names.filter((name) => name !== preferred), ''];
    return order.map((domain) => [domain, items.filter((item) => (names.includes(item.domain) ? item.domain : '') === domain)])
      .filter(([, group]) => group.length);
  };
  // Root categories and causes take the colour of their domain.
  const optionColor = (kind, name) => {
    if (kind === 'root_domain') return domainColor(name);
    if (kind === 'root_category' || kind === 'root_cause') return rootItem(kind, name)?.color || '';
    const list = kind === 'status' ? state.options.statuses : state.options.teams;
    return list.find((item) => item.name === name)?.color || '';
  };
  const sectionOf = (key) => state.sections.find((section) => section.key === key) || {key, label: key, color: '#7b8790'};
  const paintPill = (element, color) => {
    if (color) {
      element.style.setProperty('--nq-pill', color);
      element.style.setProperty('--nq-pill-text', contrastText(color));
      element.classList.add('is-colored');
    } else {
      element.style.removeProperty('--nq-pill');
      element.style.removeProperty('--nq-pill-text');
      element.classList.remove('is-colored');
    }
  };
  // A root cause is outlined in the colour of its domain, so it reads apart from its category.
  const outlinePill = (element, color) => {
    paintPill(element, '');
    if (color) element.style.setProperty('--nq-outline', color);
    else element.style.removeProperty('--nq-outline');
    element.classList.toggle('is-outlined', Boolean(color));
  };
  // The users are shown by their first and last name (their username when they have none), the default users of the
  // application (super, admin and demo) first, tagged, with a line before the others.
  const userName = (username) => state.userNames[username] || username;
  const userOrder = (username) => {
    const index = state.defaultUsers.findIndex((name) => name.toLowerCase() === String(username).toLowerCase());
    return index < 0 ? state.defaultUsers.length : index;
  };
  const isDefaultUser = (username) => userOrder(username) < state.defaultUsers.length;
  const byUserName = (left, right) => userOrder(left) - userOrder(right) || userName(left).localeCompare(userName(right));
  const DEFAULT_USER_TAG = 'default user';
  // The labels of a list of users ([element, username]): the tag of the default users and the line after them.
  const tagUsers = (entries) => {
    let afterDefault = false;
    entries.forEach(([label, username]) => {
      const tagged = isDefaultUser(username);
      if (tagged && !label.querySelector('.nq-user-tag')) label.append(node('span', DEFAULT_USER_TAG, 'nq-user-tag'));
      label.classList.toggle('nq-user-divider', afterDefault && !tagged && username !== state.unassigned);
      if (username !== state.unassigned) afterDefault = tagged;
    });
  };
  // The users of a native list: the default users marked, and a line before the others.
  const userOptions = (users) => {
    const sorted = [...users].sort(byUserName);
    return sorted.flatMap((username, index) => {
      const option = node('option', isDefaultUser(username) ? `${userName(username)} · ${DEFAULT_USER_TAG}` : userName(username));
      option.value = username;
      return index && isDefaultUser(sorted[index - 1]) && !isDefaultUser(username) ? [node('hr'), option] : [option];
    });
  };
  const pill = (kind, name, emptyLabel = 'Unassigned') => {
    const element = node('span', (kind === 'assignee' && name ? userName(name) : name) || emptyLabel, `nq-pill nq-pill-${kind}`);
    if (kind === 'root_cause') outlinePill(element, optionColor(kind, name));
    else paintPill(element, kind === 'assignee' ? '' : optionColor(kind, name));
    if (!name) element.classList.add('is-empty');
    return element;
  };
  // A small tag in the colour of a section (or of a source).
  const sectionTag = (key) => {
    const section = sectionOf(key);
    const tag = node('span', section.label, 'nq-section-tag');
    tag.style.setProperty('--nq-section', section.color);
    return tag;
  };
  const initials = (name) => String(name || '?').split(/[\s._-]+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join('').toUpperCase() || '?';
  const avatar = (name) => {
    let hash = 0;
    for (const character of String(name || '')) hash = (hash * 31 + character.charCodeAt(0)) % 360;
    const element = node('span', initials(name), 'nq-avatar');
    element.style.background = `hsl(${hash} 52% 42%)`;
    element.title = name;
    return element;
  };
  const resultClass = (result) => {
    const value = String(result || '').toLowerCase();
    return ['failed', 'dropped', 'cutoff'].includes(value) ? `is-${value}` : 'is-other';
  };
  const canChangeComment = (comment) => state.user.can_edit && !comment.deleted_at
    && (state.user.can_moderate || comment.created_by.toLowerCase() === state.user.username.toLowerCase());

  // -- filters --------------------------------------------------------------
  // The list and Yes / No fields chosen among their values: entered by the analysts, derived from the call or given by the
  // NQ Prioritization; and the people of the calls (Analyst, Reviewer), chosen among the names they hold.
  const filterableFields = () => state.fields.filter((field) => (['list', 'yes_no'].includes(field.type)
    || (state.valueFilterFields || []).includes(field.key)) && ['user', 'derived', 'priority'].includes(field.source));
  const filterSelects = () => [...root.querySelectorAll('[data-nq-filter]')];
  // The filters of the CDR and the follow-up that are fields of the catalog (source:reference), among its fields.
  const CATALOG_FILTERS = {
    failure_classification: 'cdr:failure_classification', failure_category: 'cdr:failure_category',
    root_domain: 'tracking:root_category', root_category: 'tracking:root_category', root_cause: 'tracking:root_cause',
    status: 'tracking:status', status_mode: 'tracking:status', state: 'tracking:status', team: 'tracking:team',
    assignee: 'tracking:assignee',
  };
  const fillSelect = (select, entries) => {
    const previous = new Set([...select.selectedOptions].map((option) => option.value));
    select.dataset.multiselectNoValuesLabel = 'No values available';
    select.replaceChildren(...entries.map(([value, label]) => {
      const option = node('option', label);
      option.value = value;
      option.selected = previous.has(value);
      return option;
    }));
    select.dispatchEvent(new Event('multiselect:options-updated'));
  };
  const fillFilters = (payload) => {
    const values = payload.filter_options || {};
    const unassigned = [state.unassigned, 'Unassigned'];
    const entries = {
      datasets: state.datasets.map((dataset) => [String(dataset.id), `${dataset.name} (${number(dataset.calls)})`]),
      nr_mode: (values.nr_mode || []).map((value) => [value, value]),
      service: ['voice', 'speech', 'data'].filter((value) => (values.service || []).includes(value)).map((value) => [value, SERVICE_LABELS[value]]),
      status: state.options.statuses.map((item) => [item.name, item.name]),
      team: [unassigned, ...state.options.teams.map((item) => [item.name, item.name])],
      assignee: [unassigned, ...[...new Set([...(values.assignee || []), ...state.users])].sort(byUserName).map((name) => [name, userName(name)])],
      root_domain: [[state.unassigned, NOT_CLASSIFIED], ...state.rootCauses.domains.map((item) => [item.name, item.name])],
      root_category: [[state.unassigned, NOT_CLASSIFIED], ...state.rootCauses.categories.map((item) => [item.name, item.name])],
      root_cause: [[state.unassigned, NO_CAUSE], ...state.rootCauses.causes.map((item) => [item.name, item.name])],
      status_mode: Object.entries(STATUS_MODE_LABELS),
      state: FOLLOW_UP_STATES.map((value) => [value, STATE_LABELS[value]]),
      version: Object.entries(state.versionLabels),
    };
    // A filter for every list and Yes / No field of the catalog (and Analyst and Reviewer), beside those of the CDR and
    // the follow-up that are fields of the catalog too.
    const fieldHost = $('nq-field-filters');
    const filterable = filterableFields();
    const present = new Set(filterable.map((field) => `field:${field.key}`));
    fieldHost.querySelectorAll('[data-nq-filter^="field:"]').forEach((select) => {
      if (!present.has(select.dataset.nqFilter)) select.closest('label').remove();
    });
    filterable.forEach((field) => {
      const name = `field:${field.key}`;
      const listed = (field.options || []).map((option) => option.name);
      const choices = {yes_no: ['Yes', 'No'], list: listed.length ? listed : null}[field.type] || values[name] || [];
      entries[name] = [[state.unassigned, 'Empty'], ...choices.map((value) => [value, value])];
      if (fieldHost.querySelector(`[data-nq-filter="${CSS.escape(name)}"]`)) return;
      const label = node('label', field.label);
      const select = node('select');
      select.multiple = true;
      select.size = 1;
      select.dataset.nqFilter = name;
      select.dataset.multiselectNoValuesLabel = 'No values available';
      select.dataset.multiselectEmptyLabel = 'All values';
      select.setAttribute('aria-label', field.label);
      label.append(select);
      fieldHost.append(label);
    });
    // In the order of Fields & Sections (the filters of the CDR and the follow-up at the place of their field).
    const position = new Map();
    state.fields.forEach((field, index) => {
      position.set(`field:${field.key}`, index);
      position.set(`${field.source}:${field.source_ref}`, index);
    });
    [...fieldHost.children].map((label, order) => {
      const name = label.querySelector('[data-nq-filter]')?.dataset.nqFilter || '';
      return [position.get(CATALOG_FILTERS[name] || name) ?? -1, order, label];
    }).sort((a, b) => a[0] - b[0] || a[1] - b[1]).forEach(([, , label]) => fieldHost.append(label));
    fieldHost.hidden = !fieldHost.querySelector('[data-nq-filter]');
    $('nq-field-filters-title').hidden = fieldHost.hidden;
    fieldHost.closest('.nq-filter-card').hidden = fieldHost.hidden;
    // A filter for every optional and CDR column of the table (Region, Cluster and CDR have theirs).
    const columnHost = $('nq-column-filters');
    const cdrColumnHost = $('nq-cdr-column-filters');
    const columns = columnFilters();
    const wanted = new Set(columns.map((column) => column.filter));
    [columnHost, cdrColumnHost].forEach((host) => host.querySelectorAll('[data-nq-filter]').forEach((select) => {
      if (!wanted.has(select.dataset.nqFilter)) select.closest('label').remove();
    }));
    columns.forEach((column) => {
      if (column.filter !== 'datasets') entries[column.filter] = [[state.unassigned, 'Empty'], ...(values[column.filter] || []).map((value) => [value, value])];
      // CDR columns add no filter to the panel: they filter from their header only.
      const host = column.filter.startsWith('column:cdr:') ? cdrColumnHost : columnHost;
      if (host.querySelector(`[data-nq-filter="${CSS.escape(column.filter)}"]`)) return;
      const label = node('label', column.label);
      const select = node('select');
      select.multiple = true;
      select.size = 1;
      select.dataset.nqFilter = column.filter;
      select.dataset.multiselectNoValuesLabel = 'No values available';
      select.dataset.multiselectEmptyLabel = 'All values';
      select.setAttribute('aria-label', column.label);
      label.append(select);
      host.append(label);
    });
    columnHost.hidden = !columnHost.querySelector('[data-nq-filter]');
    $('nq-column-filters-title').hidden = columnHost.hidden;
    columnHost.closest('.nq-filter-card').hidden = columnHost.hidden;
    // New selects get the checkbox menu of every multi-select of the page.
    if (typeof globalThis.setupCustomMultiSelects === 'function') globalThis.setupCustomMultiSelects();
    filterSelects().forEach((select) => {
      const field = select.dataset.nqFilter;
      if (field === 'city') {
        const present = new Set((values.city || []).map((value) => value.toLocaleLowerCase()));
        select.dataset.multiselectPresetValues = state.mainCities.filter((city) => present.has(city.toLocaleLowerCase())).join('|');
      }
      fillSelect(select, entries[field] || (values[field] || []).map((value) => [value, field === 'campaign' ? campaignLabel(value) : value]));
    });
  };
  const currentFilters = () => {
    const filters = {};
    filterSelects().forEach((select) => {
      const enabled = [...select.options];
      const chosen = enabled.filter((option) => option.selected).map((option) => option.value);
      // Every value or none means no restriction.
      if (!chosen.length || chosen.length >= enabled.length) return;
      const field = select.dataset.nqFilter;
      // Analysis fields travel together: {fields: {key: [values]}}; so do the table columns: {columns: {key: [values]}}.
      if (field.startsWith('field:')) (filters.fields ||= {})[field.slice(6)] = chosen;
      else if (field.startsWith('column:')) (filters.columns ||= {})[field.slice(7)] = chosen;
      else filters[field] = chosen;
    });
    root.querySelectorAll('[data-nq-flag]').forEach((box) => { if (box.checked) filters[box.dataset.nqFlag] = true; });
    Object.entries(state.extraFilters).forEach(([field, values]) => { if (values.length) filters[field] = [...values]; });
    // The typed filters (Join ID): values separated by commas, spaces or lines.
    root.querySelectorAll('[data-nq-typed-filter]').forEach((input) => {
      const values = [...new Set(input.value.split(/[\s,;]+/).map((value) => value.trim()).filter(Boolean))];
      if (values.length) filters[input.dataset.nqTypedFilter] = values;
    });
    const search = $('nq-search').value.trim();
    if (search) filters.search = search;
    return filters;
  };
  // The selection is shared by every user of the workspace and restored in every session.
  // The values of a filter, including the analysis fields ("field:key").
  const filterValues = (filters, field) => (field.startsWith('field:') ? (filters.fields || {})[field.slice(6)]
    : field.startsWith('column:') ? (filters.columns || {})[field.slice(7)] : filters[field]);
  const applySavedFilters = (saved) => {
    filterSelects().forEach((select) => {
      const values = new Set(filterValues(saved, select.dataset.nqFilter) || []);
      [...select.options].forEach((option) => { option.selected = values.has(option.value); });
      select.dispatchEvent(new Event('multiselect:options-updated'));
    });
    root.querySelectorAll('[data-nq-flag]').forEach((box) => { box.checked = saved[box.dataset.nqFlag] === true; });
    state.extraFilters = Object.fromEntries(EXTRA_FILTERS.filter((field) => (saved[field] || []).length).map((field) => [field, [...saved[field]]]));
    root.querySelectorAll('[data-nq-typed-filter]').forEach((input) => { input.value = (saved[input.dataset.nqTypedFilter] || []).join(', '); });
    $('nq-search').value = saved.search || '';
    state.savedFilters = JSON.stringify(currentFilters());
  };
  const saveFilters = debounce((filters) => {
    const serialized = JSON.stringify(filters);
    if (serialized === state.savedFilters) return;
    state.savedFilters = serialized;
    api('/api/non-qualified-calls/filters', {method: 'PUT', body: JSON.stringify({filters})}).catch(() => { state.savedFilters = null; });
  }, 800);
  // Each filter lists only the values of the calls the other filters leave, and those chosen in it. The lists keep
  // every value, so choosing all of them (Select All / None) or none still means no restriction: the others are
  // only hidden when the list opens.
  const offered = (field, value) => {
    const values = state.available?.[field];
    return !values || values.has(value === state.unassigned ? '' : value);
  };
  const markAvailable = (select) => {
    const shell = select.nextElementSibling;
    if (!shell?.classList.contains('multiselect-shell')) return;
    const options = new Map([...select.options].map((option) => [option.value, option]));
    const labels = [...shell.querySelectorAll('.multiselect-option')].map((label) => {
      const option = options.get(label.querySelector('[data-option-value]')?.getAttribute('data-option-value'));
      label.classList.toggle('nq-unavailable', Boolean(option) && !option.selected && !offered(select.dataset.nqFilter, option.value));
      return [label, option?.value];
    });
    if (select.dataset.nqFilter === 'assignee') tagUsers(labels.filter(([label]) => !label.classList.contains('nq-unavailable')));
  };
  const loadAvailable = async (filters, quiet) => {
    const signature = JSON.stringify(filters);
    // The same filters offer the same values, but a refresh may bring new ones.
    if (!quiet && signature === state.availableSignature) return;
    state.availableSignature = signature;
    try {
      const {values} = await api('/api/non-qualified-calls/filters/values', {method: 'POST', body: JSON.stringify({filters}),
        ...(quiet ? {headers: {'X-Background-Refresh': '1'}} : {})});
      if (signature !== state.availableSignature) return;
      state.available = Object.fromEntries(Object.entries(values).map(([field, list]) => [field, new Set(list)]));
      // A list already open follows at once.
      filterSelects().forEach((select) => { if (select.nextElementSibling?.querySelector('.multiselect-menu:not([hidden])')) markAvailable(select); });
    } catch (_error) {
      state.availableSignature = '';
    }
  };
  root.addEventListener('click', (event) => {
    const select = event.target.closest?.('.multiselect-trigger')?.parentElement?.previousElementSibling;
    if (select?.matches('[data-nq-filter]')) markAvailable(select);
  }, true);
  const selectOnly = (field, value) => {
    if (field === 'dataset_id') field = 'datasets';
    const select = root.querySelector(`[data-nq-filter="${field}"]`);
    if (!select) return;
    const target = ['team', 'assignee', 'root_domain', 'root_category', 'root_cause'].includes(field) ? (value || state.unassigned) : value;
    const chosen = [...select.selectedOptions].map((option) => option.value);
    const toggleOff = chosen.length === 1 && chosen[0] === target;
    [...select.options].forEach((option) => { option.selected = !toggleOff && option.value === target; });
    select.dispatchEvent(new Event('change', {bubbles: true}));
  };
  // The values of a filter at once (the status of Not Attended); choosing the same ones again removes them.
  const manySelected = (field, values) => {
    const chosen = filterValues(currentFilters(), field) || [];
    return chosen.length === values.length && values.every((value) => chosen.includes(value));
  };
  const selectMany = (field, values) => {
    const select = root.querySelector(`[data-nq-filter="${field}"]`);
    if (!select) return;
    const same = manySelected(field, values);
    [...select.options].forEach((option) => { option.selected = !same && values.includes(option.value); });
    select.dispatchEvent(new Event('change', {bubbles: true}));
  };
  // Drill-down from a chart or table value: each [field, value] becomes the only value of its
  // filter (a select of the Filters panel, a flag or one of the extra filters); clicking the
  // same value again removes those filters.
  const drill = (pairs) => {
    const filters = currentFilters();
    const active = pairs.every(([field, value]) => (field === 'open_only' ? filters[field] === true
      : (filterValues(filters, field) || []).length === 1 && filterValues(filters, field)[0] === value));
    pairs.forEach(([field, value]) => {
      if (field === 'open_only') {
        // A pair made only of this flag toggles it; with other values it is only switched on.
        const flag = root.querySelector('[data-nq-flag="open_only"]');
        flag.checked = pairs.length === 1 ? !active : flag.checked || !active;
        return;
      }
      if (EXTRA_FILTERS.includes(field)) {
        if (active) delete state.extraFilters[field];
        else {
          if (GROUP_FILTERS.includes(field)) GROUP_FILTERS.forEach((other) => { delete state.extraFilters[other]; });
          state.extraFilters[field] = [value];
        }
        return;
      }
      const select = root.querySelector(`[data-nq-filter="${field}"]`);
      if (!select) return;
      [...select.options].forEach((option) => { option.selected = !active && option.value === value; });
      select.dispatchEvent(new Event('multiselect:options-updated'));
    });
    scheduleLoad();
  };
  const isDrilled = (pairs) => {
    const filters = currentFilters();
    return pairs.every(([field, value]) => (field === 'open_only' ? filters[field] === true
      : (filterValues(filters, field) || []).length === 1 && filterValues(filters, field)[0] === value));
  };
  // The total cards remove the filters their sibling cards set.
  const CARD_FILTERS = ['state', 'rca_state', 'open_only'];
  const clearDrill = (fields) => {
    fields.forEach((field) => {
      if (field === 'open_only') root.querySelector('[data-nq-flag="open_only"]').checked = false;
      else if (EXTRA_FILTERS.includes(field)) delete state.extraFilters[field];
      else {
        const select = root.querySelector(`[data-nq-filter="${field}"]`);
        if (!select) return;
        [...select.options].forEach((option) => { option.selected = false; });
        select.dispatchEvent(new Event('multiselect:options-updated'));
      }
    });
    scheduleLoad();
  };
  // An indicator card that filters the calls (pairs) or clears its panel's card filters (clear).
  const drillCard = (card, {pairs = null, clear = null, many = null} = {}) => {
    if (!pairs && !clear && !many) return card;
    card.classList.add('nq-drill-card');
    card.tabIndex = 0;
    card.setAttribute('role', 'button');
    const active = pairs ? isDrilled(pairs) : many ? manySelected(...many) : false;
    card.classList.toggle('is-active', active);
    card.title = clear ? 'Show every call of the other filters' : active ? 'Remove this filter' : 'Show only these calls';
    const act = () => (pairs ? drill(pairs) : many ? selectMany(...many) : clearDrill(clear));
    card.addEventListener('click', act);
    card.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); act(); } });
    return card;
  };
  const extraLabel = (field, value) => {
    if (value === state.unassigned) return NOT_CLASSIFIED;
    if (field === 'period') return value.split(':').slice(1).join(':');
    if (field === 'state' || field === 'rca_state') return STATE_LABELS[value] || value;
    // A hotspot or a time-window issue by its operator, site and time, as the NQ Prioritization last listed it.
    if (field === 'hotspot') return state.hotspotLabels[value] || 'Hotspot of the NQ Prioritization';
    if (field === 'consecutive_issue') return state.hotspotLabels[value] || 'Time-window issue of the NQ Prioritization';
    if (field === 'clustered_issue') return state.hotspotLabels[value] || 'Clustered issue of the NQ Prioritization';
    return value.replace(/\|\|$/, '').replace('||', ' · ');
  };
  const clearFilter = (field) => {
    if (field === 'search') { $('nq-search').value = ''; scheduleLoad(); return; }
    const typed = root.querySelector(`[data-nq-typed-filter="${field}"]`);
    if (typed) { typed.value = ''; scheduleLoad(); return; }
    if (EXTRA_FILTERS.includes(field)) { delete state.extraFilters[field]; scheduleLoad(); return; }
    const box = root.querySelector(`[data-nq-flag="${field}"]`);
    if (box) { box.checked = false; scheduleLoad(); return; }
    const select = root.querySelector(`[data-nq-filter="${field}"]`);
    if (!select) return;
    [...select.options].forEach((option) => { option.selected = false; });
    select.dispatchEvent(new Event('change', {bubbles: true}));
  };
  // The filters with a value applied stand out in the Filters panel, as their chips list them.
  const markActiveFilters = (active) => {
    const mark = (element, field) => element?.closest('label')?.classList.toggle('is-filtered', active.has(field));
    root.querySelectorAll('[data-nq-filter]').forEach((select) => mark(select, select.dataset.nqFilter));
    root.querySelectorAll('[data-nq-typed-filter]').forEach((input) => mark(input, input.dataset.nqTypedFilter));
    root.querySelectorAll('[data-nq-flag]').forEach((box) => mark(box, box.dataset.nqFlag));
    mark($('nq-search'), 'search');
  };
  // The group of the open call that filters the list of calls (its filter, key and name), for the map of the call.
  const filteringGroup = () => {
    const group = (state.detail?.call.groups || []).find((item) => (state.extraFilters[item.filter] || []).length === 1
      && state.extraFilters[item.filter][0] === item.key);
    return group ? {filter: group.filter, key: group.key, label: `${GROUP_LABELS[group.kind]} ${group.id}`} : null;
  };
  // The groups in the header of the open call that filter the list (and the map of the call, painted again).
  const markGroupChips = () => {
    $('nq-drawer-groups-list')?.querySelectorAll('.nq-drawer-group').forEach((chip) => {
      const active = (state.extraFilters[chip.dataset.filter] || []).length === 1 && state.extraFilters[chip.dataset.filter][0] === chip.dataset.key;
      chip.classList.toggle('is-active', active);
      chip.setAttribute('aria-pressed', String(active));
    });
    refreshCallMap();
  };
  // The filters applied, as chips that remove them, at the top of every panel; the NQ Rate panel dims those it ignores.
  const renderActiveFilters = (filters) => {
    const chips = [];
    const flagLabels = {open_only: 'Open calls only', mine: 'Assigned to me', without_comments: 'Without comments', in_scope: 'NQ Calls in Scope Only'};
    const entries = Object.entries(filters).filter(([field]) => !['fields', 'columns'].includes(field));
    Object.entries(filters.fields || {}).forEach(([key, values]) => entries.push([`field:${key}`, values]));
    Object.entries(filters.columns || {}).forEach(([key, values]) => entries.push([`column:${key}`, values]));
    markActiveFilters(new Set(entries.map(([field]) => field)));
    markGroupChips();
    entries.forEach(([field, value]) => {
      let text;
      if (field === 'search') text = `Search: “${value}”`;
      else if (flagLabels[field]) text = flagLabels[field];
      else {
        const select = root.querySelector(`[data-nq-filter="${field}"]`);
        const labels = value.map((item) => (EXTRA_FILTERS.includes(field) ? extraLabel(field, item)
          : [...(select?.options || [])].find((option) => option.value === item)?.textContent || item));
        const name = field.startsWith('field:') ? historyLabel(field)
          : field.startsWith('column:') ? (select?.getAttribute('aria-label') || field.slice(7)) : (FIELD_LABELS[field] || field);
        text = `${name}: ${labels.length > 3 ? `${labels.slice(0, 3).join(', ')} +${labels.length - 3}` : labels.join(', ')}`;
      }
      // NQ Calls in Scope Only always leads the chips, as its switch stands above the filters.
      chips[field === 'in_scope' ? 'unshift' : 'push']({field, text});
    });
    root.querySelectorAll('[data-nq-active-filters]').forEach((host) => {
      const rates = host.dataset.nqActiveFilters === 'rates';
      host.replaceChildren(...chips.map(({field, text}) => {
        const chip = node('button', text, 'nq-filter-chip');
        chip.type = 'button';
        const ignored = rates && !RATE_FILTER_KEYS.includes(field);
        chip.classList.toggle('is-ignored', ignored);
        chip.classList.toggle('is-scope', field === 'in_scope');
        chip.title = ignored ? 'This panel does not use this filter\nClick to remove it' : 'Remove this filter';
        chip.append(node('span', '×', 'nq-filter-chip-x'));
        chip.addEventListener('click', () => clearFilter(field));
        return chip;
      }));
      host.hidden = !chips.length;
    });
  };

  // -- summary ----------------------------------------------------------------
  const renderSummary = (result) => {
    const summary = result.summary;
    const cards = [
      ['Non-Qualified Calls', number(summary.total), 'Calls and tests that did not complete', 'total', {clear: CARD_FILTERS}],
      ['Open', number(summary.open), `${percent(summary.open, summary.total)} still under follow-up`, 'open', {pairs: [['open_only', true]]}],
      ['Closed', number(summary.closed), `${percent(summary.closed, summary.total)} resolved or not applicable`, 'closed', {pairs: [['state', 'closed']]}],
      ['Attended', number(summary.attended), `${percent(summary.attended, summary.total)} followed up or commented`, 'attended', {pairs: [['state', 'attended']]}],
      ['With Team', number(summary.with_team), `${percent(summary.with_team, summary.total)} have a responsible team`, 'team', {pairs: [['state', 'with_team']]}],
      ['Commented', number(summary.commented), `${percent(summary.commented, summary.total)} have comments`, 'commented', {pairs: [['state', 'commented']]}],
    ];
    $('nq-kpis').replaceChildren(...cards.map(([label, value, note, kind, drillTarget]) => {
      const card = node('article', undefined, `nq-kpi nq-kpi-${kind}`);
      card.append(node('span', label, 'nq-kpi-label'), node('strong', value), node('span', note, 'nq-kpi-note'));
      return drillCard(card, drillTarget);
    }));
    const filters = currentFilters();
    $('nq-breakdowns').replaceChildren(...result.breakdowns.map((breakdown) => {
      const card = node('section', undefined, 'nq-breakdown');
      card.append(node('h3', breakdown.label));
      const max = Math.max(1, ...breakdown.items.map((item) => item.count));
      if (!breakdown.items.length) card.append(node('p', 'No calls.', 'form-note'));
      breakdown.items.forEach((item, index) => {
        const field = breakdown.field;
        const label = field === 'service' ? (SERVICE_LABELS[item.value] || item.value)
          : field === 'campaign' && item.value ? campaignLabel(item.value)
            : item.label || item.value || (field === 'team' ? 'Unassigned' : field.startsWith('field:') ? 'Empty'
              : field === 'root_cause' ? NO_CAUSE : NOT_CLASSIFIED);
        const row = node('button', undefined, 'nq-bar');
        row.type = 'button';
        const isField = field.startsWith('field:');
        // Only the fields with a filter of their own (lists and Yes / No of the analysts or derived) drill down.
        const fieldFilter = isField && root.querySelector(`[data-nq-filter="${CSS.escape(field)}"]`);
        const blankable = ['team', 'assignee', 'root_domain', 'root_category', 'root_cause'];
        const filterValue = ((blankable.includes(field) || isField) && !item.value) ? state.unassigned : item.value;
        const chosen = filterValues(filters, field) || [];
        const active = chosen.length === 1 && chosen[0] === filterValue;
        row.classList.toggle('is-active', active);
        row.title = isField && !fieldFilter ? label : active ? `Remove the ${FIELD_LABELS[field] || historyLabel(field)} filter` : `Show only ${label}`;
        const track = node('span', undefined, 'nq-bar-track');
        const fill = node('span', undefined, 'nq-bar-fill');
        fill.style.width = `${Math.max(2, (item.count / max) * 100)}%`;
        // The colours of the PowerPoint and Word: the status, team or domain colour, else the palette in order.
        const color = (['status', 'team', 'root_domain', 'root_category', 'root_cause'].includes(field) ? optionColor(field, item.value) : '')
          || breakdown.colors?.[item.value] || PALETTE[index % PALETTE.length];
        fill.style.background = color;
        track.append(fill);
        row.append(node('span', label, 'nq-bar-label'), track, node('span', number(item.count), 'nq-bar-count'));
        row.addEventListener('click', () => {
          if (isField && !fieldFilter) return;
          if (!item.value && !blankable.includes(field) && !isField) return;
          selectOnly(field, isField ? filterValue : item.value);
        });
        card.append(row);
      });
      return card;
    }));
  };

  // -- column filters ---------------------------------------------------------------
  // Each header name with data-filter opens the values of its filter, the same selection
  // as the Filters panel.
  let columnFilter = null;
  let columnFilterAnchor = null;
  const closeColumnFilter = () => { columnFilter?.remove(); columnFilter = null; columnFilterAnchor = null; };
  // The popover follows its header button while the page or the table scrolls.
  const placeColumnFilter = () => {
    if (!columnFilter || !columnFilterAnchor) return;
    // Below the whole header row, starting at the header name.
    const rect = columnFilterAnchor.getBoundingClientRect();
    const header = (columnFilterAnchor.closest('th') || columnFilterAnchor).getBoundingClientRect();
    if (header.bottom < 0 || header.top > window.innerHeight || !columnFilterAnchor.isConnected) { closeColumnFilter(); return; }
    const width = columnFilter.offsetWidth;
    const label = columnFilterAnchor.previousElementSibling?.getBoundingClientRect() || rect;
    columnFilter.style.left = `${Math.max(8, Math.min(label.left, window.innerWidth - width - 8))}px`;
    columnFilter.style.top = `${header.bottom + 4}px`;
    columnFilter.style.maxHeight = `${Math.max(160, window.innerHeight - header.bottom - 16)}px`;
  };
  const openColumnFilter = (button, field) => {
    closeColumnFilter();
    const select = root.querySelector(`[data-nq-filter="${field}"]`);
    if (!select) return;
    // The values of the calls the other filters leave, and those chosen.
    const options = [...select.options].filter((option) => option.selected || offered(field, option.value));
    const popover = node('div', undefined, 'nq-column-filter');
    popover.setAttribute('role', 'dialog');
    popover.setAttribute('aria-label', `Filter by ${field.startsWith('field:') ? historyLabel(field) : (FIELD_LABELS[field] || field)}`);
    popover.dataset.field = field;
    popover.addEventListener('click', (event) => event.stopPropagation());
    const search = node('input');
    search.type = 'search';
    search.placeholder = 'Search values…';
    // Select All / None applies to the values shown by the search.
    const allLabel = node('label', undefined, 'nq-toggle nq-column-filter-all');
    const all = node('input');
    all.type = 'checkbox';
    allLabel.append(all, ' Select All / None');
    const list = node('div', undefined, 'nq-column-filter-list');
    const checkbox = (option) => {
      const label = node('label', undefined, 'nq-toggle');
      const box = node('input');
      box.type = 'checkbox';
      box.value = option.value;
      box.checked = option.selected;
      label.append(box, ` ${option.textContent}`);
      list.append(label);
      return [label, box, option];
    };
    let boxes;
    let headings = [];
    if (field === 'root_cause' || field === 'root_category') {
      // The empty value first, then the categories or causes under their domain.
      const byValue = new Map(options.map((option) => [option.value, option]));
      boxes = byValue.has(state.unassigned) ? [checkbox(byValue.get(state.unassigned))] : [];
      rootGroups(field === 'root_category' ? state.rootCauses.categories : state.rootCauses.causes).forEach(([domain, items]) => {
        const group = items.map((item) => byValue.get(item.name)).filter(Boolean);
        if (!group.length) return;
        const heading = node('p', domain || 'Other', 'nq-column-filter-group');
        heading.style.setProperty('--nq-group', domainColor(domain) || '#b8c0c6');
        list.append(heading);
        const entries = group.map(checkbox);
        headings.push([heading, entries]);
        boxes.push(...entries);
      });
    } else {
      boxes = options.map(checkbox);
    }
    if (field === 'assignee') tagUsers(boxes.map(([label, , option]) => [label, option.value]));
    if (!boxes.length) list.append(node('p', 'No values.', 'nq-muted'));
    const syncAll = () => {
      const shown = boxes.filter(([label]) => !label.hidden);
      const checked = shown.filter(([, box]) => box.checked).length;
      all.checked = shown.length > 0 && checked === shown.length;
      all.indeterminate = checked > 0 && checked < shown.length;
    };
    // Select All without a search chooses every value, also those hidden: no restriction, as in the Filters panel.
    let everyValue = false;
    all.addEventListener('change', () => {
      boxes.forEach(([label, box]) => { if (!label.hidden) box.checked = all.checked; });
      everyValue = all.checked && !search.value.trim();
      syncAll();
    });
    list.addEventListener('change', () => { everyValue = false; syncAll(); });
    search.addEventListener('input', () => {
      const text = search.value.trim().toLowerCase();
      boxes.forEach(([label, , option]) => { label.hidden = Boolean(text) && !option.textContent.toLowerCase().includes(text); });
      headings.forEach(([heading, group]) => { heading.hidden = group.every(([label]) => label.hidden); });
      syncAll();
    });
    syncAll();
    const actions = node('div', undefined, 'nq-column-filter-actions');
    const apply = node('button', 'Apply', 'nq-primary-action');
    apply.type = 'button';
    apply.addEventListener('click', () => {
      if (everyValue) [...select.options].forEach((option) => { option.selected = true; });
      else boxes.forEach(([, box, option]) => { option.selected = box.checked; });
      select.dispatchEvent(new Event('multiselect:options-updated'));
      select.dispatchEvent(new Event('change', {bubbles: true}));
      closeColumnFilter();
    });
    actions.append(apply);
    popover.append(search, allLabel, list, actions);
    document.body.append(popover);
    columnFilter = popover;
    columnFilterAnchor = button;
    placeColumnFilter();
    search.focus({preventScroll: true});
  };
  window.addEventListener('scroll', () => { if (columnFilter) window.requestAnimationFrame(placeColumnFilter); }, {passive: true, capture: true});
  const renderColumnFilters = () => {
    const filters = currentFilters();
    $('nq-table').querySelectorAll('[data-filter]').forEach((label) => {
      if (!root.querySelector(`[data-nq-filter="${label.dataset.filter}"]`)) return;
      let button = label.nextElementSibling?.classList.contains('nq-column-filter-button') ? label.nextElementSibling : null;
      if (!button) {
        button = node('button', undefined, 'nq-column-filter-button');
        button.type = 'button';
        button.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16l-6 7v6l-4 2v-8z"/></svg>';
        button.addEventListener('click', (event) => {
          event.stopPropagation();
          if (columnFilter?.dataset.field === label.dataset.filter) { closeColumnFilter(); return; }
          openColumnFilter(button, label.dataset.filter);
        });
        // A word joiner keeps the funnel on the line of the end of the name.
        label.after('\u2060', button);
      }
      const active = Boolean(filterValues(filters, label.dataset.filter));
      button.classList.toggle('is-active', active);
      const name = label.dataset.filter.startsWith('field:') ? historyLabel(label.dataset.filter) : (FIELD_LABELS[label.dataset.filter] || label.textContent);
      button.title = active ? `${name}: filtered — change the filter` : `Filter by ${name}`;
      button.setAttribute('aria-label', button.title);
    });
  };
  document.addEventListener('click', (event) => { if (columnFilter && !columnFilter.contains(event.target)) closeColumnFilter(); });
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && columnFilter) { event.stopPropagation(); closeColumnFilter(); } }, true);
  window.addEventListener('resize', closeColumnFilter);

  // -- table ------------------------------------------------------------------
  // Saves follow-up changes of one call and shows the call again.
  const patchCall = async (call, changes, control, message) => {
    if (control) control.disabled = true;
    try {
      const detail = await api(`/api/non-qualified-calls/calls/${encodeURIComponent(call.call_key)}`, {
        method: 'PATCH', body: JSON.stringify({changes, version: call.version}),
      });
      Object.assign(call, detail.call);
      if (state.detail?.call.call_key === call.call_key) renderDetail(detail);
      toast(message);
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      if (control) control.disabled = false;
      loadCalls({quiet: true});
    }
  };
  const statusModeText = (call) => (call.status_mode === 'manual' ? 'Set by hand' : 'Automatic');
  const trackingSelect = (kind, call) => {
    const items = kind === 'status' ? state.options.statuses.map((item) => ({value: item.name, label: item.name, color: item.color}))
      : kind === 'team' ? [{value: '', label: 'Unassigned'}, ...state.options.teams.map((item) => ({value: item.name, label: item.name, color: item.color}))]
        : [{value: '', label: 'Unassigned'}, ...[...assignableUsers(call.team)].sort(byUserName).map((name, index, users) => ({
          value: name, label: userName(name), tag: isDefaultUser(name) ? DEFAULT_USER_TAG : '',
          divider: index > 0 && isDefaultUser(users[index - 1]) && !isDefaultUser(name)}))];
    const current = call[kind] || '';
    if (current && !items.some((item) => item.value === current)) items.push({value: current, label: kind === 'assignee' ? userName(current) : current});
    // A status set by hand can go back to the Status Rules.
    if (kind === 'status' && call.status_mode === 'manual') items.push({value: AUTO_STATUS, label: '↺ Back to automatic', action: true});
    const control = choiceControl({
      items, value: current, empty: 'Unassigned', label: `${HISTORY_LABELS[kind]} of the call`,
      title: (value) => (kind === 'status' ? `Status: ${value} (${statusModeText(call).toLowerCase()})` : `${HISTORY_LABELS[kind]}: ${value || 'Unassigned'}`),
      onChange: (value) => patchCall(call, value === AUTO_STATUS ? {status_mode: 'auto'} : {[kind]: value}, control,
        value === AUTO_STATUS ? 'The status follows the Status Rules again.' : `${HISTORY_LABELS[kind]} updated.`),
    });
    control.classList.add(`nq-pill-${kind}`);
    return control;
  };
  // Whether the status follows the Status Rules (Auto) or was chosen by hand.
  const statusModeBadge = (call) => {
    const manual = call.status_mode === 'manual';
    const badge = node('span', manual ? 'By hand' : 'Auto', `nq-status-mode${manual ? ' is-manual' : ''}`);
    badge.title = manual ? 'Chosen by hand: the Status Rules do not change it until it goes back to automatic'
      : 'Set by the Status Rules from the fields of the call';
    return badge;
  };
  const rootLabel = (category, cause) => [category, cause].filter(Boolean).join(' · ') || NOT_CLASSIFIED;
  const recommendationOf = (call) => call.rca_recommendation?.recommendation || null;
  const sourceNames = (names) => (names || []).map((name) => state.rcaSources[name] || name).join(', ');
  // Root category and cause pickers: the catalog values grouped by domain, with the values the RCA
  // sources propose first, then the causes mapped to the chosen category (or the category of the chosen
  // cause) and, for a cause, the causes of the domain of the chosen category.
  let rootPicker = null;
  const closeRootPicker = () => {
    rootPicker?.popover.remove();
    rootPicker = null;
  };
  const placeRootPicker = () => {
    if (!rootPicker) return;
    const rect = rootPicker.anchor.getBoundingClientRect();
    if (!rootPicker.anchor.isConnected || rect.bottom < 0 || rect.top > window.innerHeight) { closeRootPicker(); return; }
    const {popover} = rootPicker;
    const below = window.innerHeight - rect.bottom - 16;
    const above = rect.top - 16;
    // Open downwards, or upwards when there is clearly more room above.
    const up = below < 260 && above > below;
    popover.style.maxHeight = `${Math.max(180, up ? above : below)}px`;
    popover.style.left = `${Math.max(8, Math.min(rect.left, window.innerWidth - popover.offsetWidth - 8))}px`;
    popover.style.top = up ? `${Math.max(8, rect.top - 4 - popover.offsetHeight)}px` : `${rect.bottom + 4}px`;
  };
  // The values the RCA sources of a call propose for a root category or cause, the recommended one first.
  const proposedValues = (call, kind) => {
    const key = kind === 'root_category' ? 'category' : 'cause';
    const recommendation = recommendationOf(call);
    const names = [recommendation?.[key], ...(call.rca_recommendation?.sources || []).map((source) => source[key])].filter(Boolean);
    return [...new Set(names)];
  };
  const openRootPicker = (anchor, kind, call, choose) => {
    closeRootPicker();
    const items = kind === 'root_category' ? state.rootCauses.categories : state.rootCauses.causes;
    const current = call[kind] || '';
    const popover = node('div', undefined, 'nq-column-filter nq-cause-picker');
    popover.setAttribute('role', 'listbox');
    popover.setAttribute('aria-label', FIELD_LABELS[kind]);
    popover.addEventListener('click', (event) => event.stopPropagation());
    const search = node('input');
    search.type = 'search';
    search.placeholder = kind === 'root_category' ? 'Search root categories…' : 'Search root causes…';
    const list = node('div', undefined, 'nq-column-filter-list');
    const options = [];
    const option = (name, text, group) => {
      const button = node('button', text, 'nq-cause-option');
      button.type = 'button';
      button.setAttribute('role', 'option');
      const selected = name.toLowerCase() === current.toLowerCase();
      button.classList.toggle('is-selected', selected);
      button.classList.toggle('is-empty', !name);
      button.setAttribute('aria-selected', String(selected));
      button.addEventListener('click', () => {
        closeRootPicker();
        if (!selected) choose(name);
      });
      list.append(button);
      options.push([button, text, group]);
      return button;
    };
    const groups = [];
    const heading = (text, color, extra = '') => {
      const element = node('p', text, `nq-column-filter-group${extra}`);
      element.style.setProperty('--nq-group', color || '#b8c0c6');
      list.append(element);
      return element;
    };
    option('', kind === 'root_category' ? 'No root category' : 'No root cause', '');
    const proposed = proposedValues(call, kind).map((name) => rootItem(kind, name)).filter(Boolean);
    if (proposed.length) {
      const element = heading('Proposed by the RCA sources', '#b0234f', ' is-proposed');
      groups.push([element, proposed.map((item) => option(item.name, item.name, 'proposed'))]);
    }
    // The causes mapped to the chosen category, or the category the chosen cause is mapped to.
    const mapped = kind === 'root_cause'
      ? (call.root_category ? items.filter((item) => (item.category || '').toLowerCase() === call.root_category.toLowerCase()) : [])
      : [rootItem('root_category', rootItem('root_cause', call.root_cause)?.category)].filter(Boolean);
    if (mapped.length) {
      const element = heading(kind === 'root_cause' ? `Causes of ${call.root_category}` : `Category of ${call.root_cause}`,
        domainColor(mapped[0].domain), ' is-proposed');
      groups.push([element, mapped.map((item) => option(item.name, item.name, 'mapped'))]);
    }
    // A cause follows the domain of the chosen category; a category the domain of the chosen cause.
    const affinity = kind === 'root_cause' ? rootItem('root_category', call.root_category)?.domain
      : rootItem('root_cause', call.root_cause)?.domain;
    rootGroups(items, affinity || '').forEach(([domain, group]) => {
      const title = domain ? `${domain}${domain === affinity ? ' · same domain' : ''}` : 'Without a domain';
      const element = heading(title, domainColor(domain));
      groups.push([element, group.map((item) => option(item.name, item.name, domain))]);
    });
    search.addEventListener('input', () => {
      const text = search.value.trim().toLowerCase();
      options.forEach(([button, label, group]) => {
        button.hidden = Boolean(text) && !`${group} ${label}`.toLowerCase().includes(text);
      });
      groups.forEach(([element, buttons]) => { element.hidden = buttons.every((button) => button.hidden); });
    });
    search.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        list.querySelector('.nq-cause-option:not([hidden]):not(.is-empty)')?.click();
      }
    });
    popover.append(search, list);
    document.body.append(popover);
    rootPicker = {popover, anchor};
    placeRootPicker();
    // Show the current value; only the list scrolls (scrollIntoView would also scroll the page).
    const selected = list.querySelector('.is-selected');
    if (selected) list.scrollTop = selected.offsetTop - list.clientHeight / 2;
    search.focus({preventScroll: true});
  };
  document.addEventListener('click', (event) => { if (rootPicker && !rootPicker.popover.contains(event.target)) closeRootPicker(); });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && rootPicker) { event.stopPropagation(); rootPicker.anchor.focus(); closeRootPicker(); }
  }, true);
  window.addEventListener('scroll', (event) => {
    if (rootPicker && !rootPicker.popover.contains(event.target)) window.requestAnimationFrame(placeRootPicker);
  }, {passive: true, capture: true});
  window.addEventListener('resize', closeRootPicker);
  // A modern dropdown: the value as a pill in its colour, and every choice in its colour in a popover (with a search
  // for long lists). Items are {value, label, color, action}; an action (Back to automatic) is not a value. With
  // ``add``, a value typed in the search that the list lacks is offered first, to add to the list and choose.
  const openChoicePicker = (anchor, items, current, choose, label, add = null) => {
    closeRootPicker();
    const popover = node('div', undefined, 'nq-column-filter nq-cause-picker nq-choice-picker');
    popover.setAttribute('role', 'listbox');
    popover.setAttribute('aria-label', label);
    popover.addEventListener('click', (event) => event.stopPropagation());
    const list = node('div', undefined, 'nq-column-filter-list');
    const options = items.map((item) => {
      const option = node('button', undefined, `nq-choice-option${item.action ? ' is-action' : ''}`);
      option.type = 'button';
      option.setAttribute('role', 'option');
      const selected = !item.action && item.value === current;
      option.classList.toggle('is-selected', selected);
      option.setAttribute('aria-selected', String(selected));
      const chip = node('span', item.label, 'nq-pill');
      if (item.color) paintPill(chip, item.color);
      else if (!item.value || item.action) chip.classList.add('is-empty');
      option.append(chip);
      if (item.tag) option.append(node('span', item.tag, 'nq-user-tag'));
      option.classList.toggle('nq-user-divider', Boolean(item.divider));
      option.addEventListener('click', () => {
        closeRootPicker();
        if (!selected) choose(item);
      });
      list.append(option);
      return [option, item.label];
    });
    let search = null;
    if (items.length > 10 || add) {
      search = node('input');
      search.type = 'search';
      search.placeholder = add ? 'Search or type a new value…' : 'Search…';
      const typed = () => search.value.trim().replace(/\s+/g, ' ');
      let addOption = null;
      if (add) {
        addOption = node('button', undefined, 'nq-choice-option is-action nq-choice-add');
        addOption.type = 'button';
        addOption.hidden = true;
        addOption.addEventListener('click', async () => {
          const name = typed();
          closeRootPicker();
          try {
            const value = await add(name);
            choose({value, label: value});
          } catch (error) {
            toast(error.message, 'error');
          }
        });
        list.prepend(addOption);
      }
      search.addEventListener('input', () => {
        const query = search.value.trim().toLowerCase();
        options.forEach(([option, text]) => { option.hidden = Boolean(query) && !text.toLowerCase().includes(query); });
        if (addOption) {
          const name = typed();
          addOption.hidden = !name || items.some((item) => !item.action && item.value.toLowerCase() === name.toLowerCase());
          addOption.replaceChildren(node('span', `+ Add “${name}”`, 'nq-pill'));
          addOption.title = `Add ${name} to the values of ${label.replace(/ of the call$/, '')} and choose it`;
        }
      });
      // Enter chooses the first value found, else adds the value typed.
      search.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
          event.preventDefault();
          (list.querySelector('.nq-choice-option:not([hidden]):not(.nq-choice-add)') || list.querySelector('.nq-choice-add:not([hidden])'))?.click();
        }
      });
      popover.append(search);
    }
    popover.append(list);
    document.body.append(popover);
    rootPicker = {popover, anchor};
    placeRootPicker();
    const selected = list.querySelector('.is-selected');
    if (selected) list.scrollTop = selected.offsetTop - list.clientHeight / 2;
    (search || selected || list.querySelector('.nq-choice-option'))?.focus({preventScroll: true});
  };
  // The arrows move between the choices of an open picker.
  document.addEventListener('keydown', (event) => {
    if (!rootPicker || !['ArrowDown', 'ArrowUp'].includes(event.key)) return;
    const options = [...rootPicker.popover.querySelectorAll('.nq-choice-option:not([hidden]), .nq-cause-option:not([hidden])')];
    if (!options.length) return;
    event.preventDefault();
    const index = options.indexOf(document.activeElement);
    const next = event.key === 'ArrowDown' ? Math.min(options.length - 1, index + 1) : Math.max(0, index - 1);
    options[next].focus();
  });
  const choiceControl = ({items, value, empty = '—', label, onChange, title = null, onAdd = null}) => {
    const button = node('button', undefined, 'nq-pill-select nq-cause-picker-button nq-choice');
    button.type = 'button';
    button.setAttribute('aria-haspopup', 'listbox');
    button.setAttribute('aria-label', label);
    let current = value || '';
    const paint = () => {
      const item = items.find((entry) => !entry.action && entry.value === current);
      button.textContent = item ? item.label : (current || empty);
      paintPill(button, item?.color || '');
      button.classList.toggle('is-empty', !current);
      button.title = title ? title(current) : `${label}: ${current || empty}`;
    };
    paint();
    button.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (rootPicker?.anchor === button) { closeRootPicker(); return; }
      openChoicePicker(button, items, current, (item) => {
        if (!item.action) {
          current = item.value;
          paint();
        }
        onChange(item.value, item);
      }, label, onAdd && (async (name) => {
        const added = await onAdd(name);
        if (!items.some((item) => !item.action && item.value === added.value)) items.push(added);
        return added.value;
      }));
    });
    button.setValue = (chosen) => { current = chosen || ''; paint(); };
    return button;
  };
  // Yes and No in their colours.
  const YES_NO_COLORS = {Yes: '#245a96', No: '#9aa5ad'};
  const fieldChoices = (field, value = '') => {
    const names = field.type === 'yes_no' ? ['Yes', 'No'] : field.options.map((option) => option.name);
    if (value && !names.includes(value)) names.push(value);
    return [{value: '', label: '—'}, ...names.map((name) => ({value: name, label: name,
      color: field.type === 'yes_no' ? YES_NO_COLORS[name] : optionColorOf(field, name)}))];
  };
  // A list field of the analysts takes a new value typed in its list (user-editor and above, as in Fields & Sections):
  // it joins the values of the field (the Planned FY writes a year as a fiscal year: 2030 is FY30).
  const listAdder = (field) => (field.type === 'list' && field.source === 'user' && state.user.can_edit ? async (name) => {
    const {field: saved, value, added} = await api(`/api/non-qualified-calls/fields/${encodeURIComponent(field.key)}/options`,
      {method: 'POST', body: JSON.stringify({name})});
    state.fields = state.fields.map((item) => (item.key === saved.key ? saved : item));
    if (added) toast(`${value} added to the values of ${saved.label}.`);
    return {value, label: value, color: optionColorOf(saved, value)};
  } : null);
  // A picker button for the root category (filled with its domain colour) or cause (outlined).
  const rootPickerButton = (kind, call) => {
    const value = call[kind] || '';
    const empty = kind === 'root_category' ? 'Root category…' : 'Root cause…';
    const button = node('button', value || empty, 'nq-pill-select nq-root-select nq-cause-picker-button');
    button.type = 'button';
    button.setAttribute('aria-haspopup', 'listbox');
    button.setAttribute('aria-label', `${FIELD_LABELS[kind]} of the call`);
    if (kind === 'root_category') paintPill(button, optionColor(kind, value));
    else outlinePill(button, optionColor(kind, value));
    button.classList.toggle('is-empty', !value);
    const domain = rootItem(kind, value)?.domain;
    button.title = `${FIELD_LABELS[kind]}: ${value || 'none'}${domain ? ` (${domain})` : ''}`;
    button.addEventListener('click', (event) => {
      event.stopPropagation();
      if (rootPicker?.anchor === button) { closeRootPicker(); return; }
      openRootPicker(button, kind, call, (name) => patchCall(call, {[kind]: name}, button, `${FIELD_LABELS[kind]} updated.`));
    });
    return button;
  };
  // The recommended root category and cause of a call without them, to accept with one click.
  const recommendationChip = (call) => {
    const recommendation = recommendationOf(call);
    if (!recommendation || call.root_category || call.root_cause) return null;
    const text = rootLabel(recommendation.category, recommendation.cause);
    const title = `Recommended: ${text}${recommendation.domain ? ` (${recommendation.domain})` : ''}\n`
      + `${CONFIDENCE_LABELS[recommendation.confidence] || ''} · ${sourceNames(recommendation.sources)}`;
    const chip = node(state.user.can_edit ? 'button' : 'span', undefined, `nq-root-suggestion is-${recommendation.confidence}`);
    // The RCA it comes from above it, small, so that it fits its column (every source in its tooltip).
    const sources = recommendation.sources || [];
    const rcas = sources.filter((name) => ['netcheck', 'script'].includes(name));
    const body = node('span', undefined, 'nq-root-suggestion-body');
    body.append(node('small', sourceNames(rcas.length ? rcas : sources).replace(/, /g, ' + ') || 'Recommended', 'nq-root-suggestion-source'),
      node('span', text, 'nq-root-suggestion-text'));
    chip.append(node('span', '', 'nq-confidence-dot'), body);
    chip.title = state.user.can_edit ? `${title}\nClick to accept it` : title;
    if (state.user.can_edit) {
      chip.type = 'button';
      chip.addEventListener('click', (event) => {
        event.stopPropagation();
        patchCall(call, {root_category: recommendation.category, root_cause: recommendation.cause}, chip, 'Recommendation accepted.');
      });
    }
    return chip;
  };
  // The root cause of a call: its root category above and its root cause below, each in the colour of its
  // domain, and the recommended ones while it has none.
  const rootCauseControl = (call) => {
    const wrapper = node('div', undefined, 'nq-root-cell');
    if (state.user.can_edit) wrapper.append(rootPickerButton('root_category', call), rootPickerButton('root_cause', call));
    else {
      wrapper.append(pill('root_category', call.root_category, NOT_CLASSIFIED));
      if (call.root_cause) wrapper.append(pill('root_cause', call.root_cause, NO_CAUSE));
    }
    const chip = recommendationChip(call);
    if (chip) wrapper.append(chip);
    return wrapper;
  };
  // A team with members is assigned to its members only.
  const assignableUsers = (team) => {
    const members = state.options.teams.find((item) => item.name === team)?.members || [];
    return members.length ? members : state.users;
  };
  // -- optional columns: built-in call columns, CDR columns and analysis fields ---------------
  const optionalColumns = () => [
    ...state.layout.builtin.map((key) => ({key, label: state.optionalColumns[key] || key, sort: key})),
    ...state.layout.cdr.map((name) => ({key: `cdr:${name}`, label: name, sort: `cdr:${name}`})),
  ];
  // The catalog fields shown as columns in the layout; the follow-up ones (status, team, root cause…) have fixed columns.
  const fieldColumns = () => {
    const shown = new Set(state.layout.fields);
    return state.fields.filter((field) => shown.has(field.key) && field.source !== 'tracking');
  };
  // Two fields share a column when both are shown, the first above the second: the Prioritization (Prioritized or Track
  // only) above the Priority of the call.
  const PAIRED_FIELDS = {prioritization: 'priority'};
  // The field columns, each with the field shown below it in the same column (or none).
  const fieldColumnGroups = () => {
    const fields = fieldColumns();
    const byKey = new Map(fields.map((field) => [field.key, field]));
    const below = new Map(Object.entries(PAIRED_FIELDS).filter(([main, second]) => byKey.has(main) && byKey.has(second))
      .map(([main, second]) => [main, byKey.get(second)]));
    const paired = new Set([...below.values()].map((field) => field.key));
    return fields.filter((field) => !paired.has(field.key)).map((field) => ({field, below: below.get(field.key) || null}));
  };
  // The filter of each optional column: CDR filters by the CDRs (the CDR filter of the Additional Columns Filters,
  // shown with the column), the others by their own values. The CDRs of the calls follow NR Mode and Campaign.
  const OWN_COLUMN_FILTERS = {cdr: 'datasets'};
  const columnFilterKey = (column) => OWN_COLUMN_FILTERS[column.key] || `column:${column.key}`;
  const columnFilters = () => optionalColumns().map((column) => ({label: column.label, filter: columnFilterKey(column)}));
  const optionColorOf = (field, value) => field.options?.find((option) => option.name === value)?.color || '';
  const bindSort = (header) => {
    if (header.dataset.sortBound) return;
    header.dataset.sortBound = '1';
    header.tabIndex = 0;
    const sort = () => {
      if (state.sort === header.dataset.sort) state.direction = state.direction === 'asc' ? 'desc' : 'asc';
      else { state.sort = header.dataset.sort; state.direction = header.dataset.sort === 'start_time' ? 'desc' : 'asc'; }
      state.page = 1;
      loadCalls();
    };
    header.addEventListener('click', sort);
    header.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); sort(); } });
  };
  // A name of a header that sorts by its column (and filters by it with a filter key).
  const headerItem = (label, sortKey, filterKey = '') => {
    const item = node('span', undefined, 'nq-header-item');
    const name = node('span', label);
    name.dataset.sort = sortKey;
    if (filterKey) name.dataset.filter = filterKey;
    item.append(name);
    bindSort(name);
    return item;
  };
  const headerCell = (label, sortKey, filterKey = '', section = null) => {
    const cell = node('th', undefined, 'nq-sort-pair nq-dynamic-col');
    cell.append(headerItem(label, sortKey, filterKey));
    // A column shows the colour of its group above its name (the section of its field, or the call).
    if (section) {
      cell.classList.add('nq-section-col');
      cell.style.setProperty('--nq-section', section.color);
      cell.title = `${section.label} · ${label}`;
    }
    return cell;
  };
  // -- column order: a header dragged onto another moves its column, in the layout of the user ----------------
  const STATIC_HEADERS = [...($('nq-table')?.tHead.rows[0].cells || [])];
  // Where each browser kept the order before the layouts: it becomes the order of the user's own layout, once.
  const LEGACY_ORDER_STORAGE = `nq-column-order:${$('nq-table')?.dataset.workspace || ''}`;
  // Columns shown by default before another one: Session Type (CDR) before Test / Technology instead of after Result /
  // Failure, and the Repeated Issue before the Scoring Points Lost.
  const DEFAULT_COLUMN_PLACES = {session_type: 'test_name', 'field:repeated_issue': 'field:scoring_points_lost'};
  // The column keys in the order the rows are built, and in the order they are shown.
  let naturalColumns = [];
  let shownColumns = [];
  let draggedColumn = '';
  const columnKeyOf = (cell) => cell.querySelector('[data-sort]')?.dataset.sort || '';
  const storedColumnOrder = () => [...(state.layout.order || [])];
  const defaultColumnOrder = () => {
    const order = [...naturalColumns];
    Object.entries(DEFAULT_COLUMN_PLACES).forEach(([key, before]) => {
      if (!order.includes(key) || !order.includes(before)) return;
      order.splice(order.indexOf(key), 1);
      order.splice(order.indexOf(before), 0, key);
    });
    return order;
  };
  // The Layout switch shows which layout the user sees; Save for the workspace (admins) shares theirs.
  const paintLayoutSwitch = () => {
    document.querySelectorAll('[data-nq-layout-view]').forEach((button) => {
      button.classList.toggle('is-active', button.dataset.nqLayoutView === state.layouts?.view);
    });
    // The knob on the left for Mine, on the right for Workspace.
    const toggle = document.querySelector('[data-nq-layout-toggle]');
    if (toggle) toggle.setAttribute('aria-checked', String(state.layouts?.view !== 'mine'));
    const mine = document.querySelector('[data-nq-layout-view="mine"]');
    if (mine) mine.title = state.layouts?.mine ? 'Your own columns and order, only for you' : 'Start your own layout from that of the workspace';
    const publish = $('nq-layout-publish');
    if (publish) publish.hidden = state.layouts?.view !== 'mine';
  };
  const applyLayouts = (layouts) => {
    if (!layouts) return;
    state.layouts = layouts;
    state.layout = layouts.effective;
    paintLayoutSwitch();
  };
  // A change made while the workspace layout is shown makes it the user's own, replacing the one they had once they agree.
  const confirmOwnLayout = async () => {
    if (state.layouts?.view !== 'workspace' || !state.layouts?.mine) return true;
    const message = 'You are seeing the workspace layout: this change makes it your own layout and replaces the one you had. Continue?';
    return typeof window.showConfirmDialog === 'function'
      ? window.showConfirmDialog(message, {title: 'Your Layout', confirmLabel: 'Replace'}) : window.confirm(message);
  };
  // Saves the layout the user sees with these changes as their own (only for them); false when they cancel.
  const saveLayout = async (changes, reason = 'changed', {reload = false} = {}) => {
    if (!await confirmOwnLayout()) return false;
    const base = state.layout;
    const result = await api('/api/non-qualified-calls/table-layout/mine', {method: 'PUT', body: JSON.stringify({
      builtin: base.builtin, cdr: base.cdr, export_cdr: base.export_cdr, fields: base.fields, excel_fields: base.excel_fields,
      known_fields: state.fields.map((field) => field.key), order: base.order, ...changes, reason,
    })});
    applyLayouts(result.table_layout);
    if (reload) await loadState();
    return true;
  };
  const saveColumnOrder = async (order) => {
    const reset = order.join('|') === defaultColumnOrder().join('|');
    try {
      return await saveLayout({order: reset ? [] : order}, reset ? 'default_order' : 'order');
    } catch (error) {
      toast(error.message, 'error');
      return false;
    }
  };
  // The order a browser kept before the layouts becomes that of the user's own layout (unless they have one).
  let browserOrderMoved = false;
  const moveBrowserOrder = async () => {
    browserOrderMoved = true;
    let order = [];
    try {
      order = JSON.parse(localStorage.getItem(LEGACY_ORDER_STORAGE) || '[]');
      localStorage.removeItem(LEGACY_ORDER_STORAGE);
    } catch (_error) {
      return;
    }
    if (!Array.isArray(order) || !order.length || state.layouts?.mine) return;
    try {
      await saveLayout({order: order.map(String)}, 'order');
    } catch (_error) {
      // The default order stays.
    }
  };
  const clearDropMarks = () => $('nq-table').tHead.querySelectorAll('.is-drop-before, .is-drop-after')
    .forEach((cell) => cell.classList.remove('is-drop-before', 'is-drop-after'));
  const moveColumn = async (key, target, after) => {
    const order = shownColumns.filter((item) => item !== key);
    order.splice(order.indexOf(target) + (after ? 1 : 0), 0, key);
    applyColumnOrder(order);
    if (state.result) renderRows(state.result);
    // Back to the order of the layout when the change is cancelled or fails.
    if (!await saveColumnOrder(order)) {
      applyColumnOrder();
      if (state.result) renderRows(state.result);
    }
  };
  const bindColumnDrag = (cell) => {
    if (cell.dataset.dragBound) return;
    cell.dataset.dragBound = '1';
    cell.draggable = true;
    cell.addEventListener('dragstart', (event) => {
      draggedColumn = columnKeyOf(cell);
      event.dataTransfer.effectAllowed = 'move';
      event.dataTransfer.setData('text/plain', draggedColumn);
      cell.classList.add('is-dragging');
    });
    cell.addEventListener('dragend', () => {
      draggedColumn = '';
      cell.classList.remove('is-dragging');
      clearDropMarks();
    });
    cell.addEventListener('dragover', (event) => {
      if (!draggedColumn || draggedColumn === columnKeyOf(cell)) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = 'move';
      const box = cell.getBoundingClientRect();
      const after = event.clientX > box.left + box.width / 2;
      clearDropMarks();
      cell.classList.add(after ? 'is-drop-after' : 'is-drop-before');
    });
    cell.addEventListener('dragleave', (event) => {
      if (!cell.contains(event.relatedTarget)) cell.classList.remove('is-drop-before', 'is-drop-after');
    });
    cell.addEventListener('drop', (event) => {
      event.preventDefault();
      const target = columnKeyOf(cell);
      const after = cell.classList.contains('is-drop-after');
      clearDropMarks();
      if (draggedColumn && draggedColumn !== target) moveColumn(draggedColumn, target, after);
    });
  };
  // Shows the header in the stored order; columns missing from it (newly added) keep their default place.
  const applyColumnOrder = (stored = storedColumnOrder()) => {
    const row = $('nq-table').tHead.rows[0];
    const movable = [...row.cells].filter((cell) => columnKeyOf(cell));
    const defaults = defaultColumnOrder();
    const order = stored.filter((key) => naturalColumns.includes(key));
    defaults.forEach((key, index) => {
      if (order.includes(key)) return;
      const previous = defaults.slice(0, index).reverse().find((item) => order.includes(item));
      order.splice(previous ? order.indexOf(previous) + 1 : 0, 0, key);
    });
    shownColumns = order;
    const byKey = new Map(movable.map((cell) => [columnKeyOf(cell), cell]));
    row.append(...order.map((key) => byKey.get(key)));
    movable.forEach(bindColumnDrag);
    $('nq-column-order-reset').hidden = order.join('|') === defaults.join('|');
  };
  // The cells of a row, built in the natural order, are shown in the order of the header.
  const orderRowCells = (row) => {
    if (!shownColumns.length) return;
    const cells = [...row.cells].slice(row.cells.length - naturalColumns.length);
    if (cells.length !== naturalColumns.length) return;
    row.append(...shownColumns.map((key) => cells[naturalColumns.indexOf(key)]));
  };
  // Every column shows the colour of its group above its name, as the Excel export: the call columns that of the call,
  // the follow-up columns (status, team and assignee, root category and cause, comments) that of the section of their field.
  const callSection = () => state.callSection || {key: 'call', label: 'Call', color: '#5e6b75'};
  const trackingSection = (ref) => sectionOf(state.fields.find((field) => field.source === 'tracking' && field.source_ref === ref)?.section || 'general');
  const FOLLOW_UP_HEADERS = {team: 'team', root_category: 'root_category', status: 'status', comments: 'comments'};
  const paintHeader = (cell, section) => {
    cell.classList.add('nq-section-col');
    cell.style.setProperty('--nq-section', section.color);
  };
  // The optional columns follow Result / Failure, the analysis fields follow the root cause; then the column order applies.
  const renderDynamicHeaders = () => {
    const row = $('nq-table').tHead.rows[0];
    row.querySelectorAll('.nq-dynamic-col').forEach((cell) => cell.remove());
    // The fixed columns go back to the order of the page before the others are placed.
    row.append(...STATIC_HEADERS);
    STATIC_HEADERS.forEach((cell) => {
      const key = columnKeyOf(cell);
      if (key) paintHeader(cell, FOLLOW_UP_HEADERS[key] ? trackingSection(FOLLOW_UP_HEADERS[key]) : callSection());
    });
    const after = (sortKey) => row.querySelector(`[data-sort="${sortKey}"]`)?.closest('th');
    let anchor = after('result');
    optionalColumns().forEach((column) => {
      const cell = headerCell(column.label, column.sort, columnFilterKey(column), callSection());
      anchor.after(cell);
      anchor = cell;
    });
    // The RCA fields come before the root category and cause they lead to, the other fields after them.
    const rootHeader = after('root_category');
    const filterable = new Set(filterableFields().map((field) => field.key));
    anchor = rootHeader;
    fieldColumnGroups().forEach(({field, below}) => {
      const cell = headerCell(field.label, `field:${field.key}`, filterable.has(field.key) ? `field:${field.key}` : '', sectionOf(field.section));
      // The field shown below, in the same column, sorts and filters by its own name.
      if (below) {
        cell.append(headerItem(below.label, `field:${below.key}`, filterable.has(below.key) ? `field:${below.key}` : ''));
        cell.title = `${cell.title} · ${below.label}`;
      }
      if ([field, below].some((item) => item && ['list', 'yes_no'].includes(item.type))) cell.classList.add('nq-choice-col');
      if (field.section === 'rca') rootHeader.before(cell);
      else { anchor.after(cell); anchor = cell; }
    });
    naturalColumns = [...row.cells].map(columnKeyOf).filter(Boolean);
    applyColumnOrder();
  };
  const saveFieldValue = (call, key, value, control) => patchCall(call, {fields: {[key]: value}}, control,
    `${historyLabel(`field:${key}`)} updated.`);
  // A list or Yes / No field of the analysts is chosen in the row; the other fields are shown here and
  // edited in the call; fields from the CDR, the Ericsson RCA or derived are read only.
  // The cause columns of the RCA sources show, for a call whose source gives a category without a cause (most results
  // of the Ericsson RCA), that category, marked as such.
  const CAUSE_FALLBACKS = {rca_suggested_cause: 'rca_suggested_category', netcheck_suggested_cause: 'netcheck_suggested_category'};
  // A value of the Prioritization Rule field (Final 3 · SA Voice · Medium impact) shown as what its step takes, then the
  // list of the step (Weekly for list 1, Final for list 2) and its number in tags of their own; the whole value on hover.
  const STEP_RULE = /^(Campaign|Final)(?: (\d+))? · (.+)$/;
  const isRuleField = (field) => field.source === 'priority' && field.source_ref === 'priority_rule';
  const ruleValue = (field, value) => {
    const element = node('span', undefined, 'nq-rule-value');
    const match = STEP_RULE.exec(value);
    const label = node('span', match ? match[3] : value, 'nq-pill');
    paintPill(label, optionColorOf(field, value));
    element.append(label);
    if (match) {
      // The list and the step of the rule together, always below it.
      const list = match[1] === 'Final' ? 'final' : 'weekly';
      const tags = node('span', undefined, 'nq-rule-tags');
      tags.append(node('span', list === 'final' ? 'Final' : 'Weekly', `nq-rule-tag is-${list}`));
      if (match[2]) tags.append(node('span', `Step ${match[2]}`, 'nq-rule-tag is-step'));
      element.append(tags);
    }
    element.title = value;
    return element;
  };
  const fieldCell = (call, field) => {
    const cell = node('td', undefined, 'nq-tracking-cell nq-field-cell');
    const value = String((field.source === 'user' ? call.fields?.[field.key] : call.values?.[field.key]) ?? '');
    if (['list', 'yes_no'].includes(field.type) && field.source === 'user' && state.user.can_edit) {
      const picker = choiceControl({items: fieldChoices(field, value), value, label: `${field.label} of the call`,
        onChange: (chosen) => saveFieldValue(call, field.key, chosen, picker), onAdd: listAdder(field)});
      picker.classList.add('nq-field-select');
      cell.append(picker);
      return cell;
    }
    if (isRuleField(field) && value) {
      cell.append(ruleValue(field, value));
    } else if (['list', 'yes_no'].includes(field.type) && value) {
      const element = node('span', value, 'nq-pill');
      paintPill(element, field.type === 'yes_no' ? YES_NO_COLORS[value] || '' : optionColorOf(field, value));
      cell.append(element);
    } else {
      const fallbackKey = value ? '' : CAUSE_FALLBACKS[field.key];
      const fallback = fallbackKey ? String(call.values?.[fallbackKey] ?? '') : '';
      if (fallback) {
        const category = state.fields.find((item) => item.key === fallbackKey)?.label || 'Category';
        const text = node('span', fallback, 'nq-field-text nq-field-fallback');
        text.title = `${fallback}: ${category} (no ${field.label})`;
        cell.append(text, node('span', category, 'nq-field-fallback-label'));
        return cell;
      }
      const text = node('span', field.type === 'date' ? value : value || '—', value ? 'nq-field-text' : 'nq-muted');
      if (value) text.title = value;
      cell.append(text);
    }
    return cell;
  };
  const optionalCell = (call, column) => {
    let value;
    if (column.key.startsWith('cdr:')) value = call.extra?.[column.key.slice(4)] || '';
    else if (column.key === 'end_time') value = call.end_time ? cdrTime(call.end_time) : '';
    else if (column.key === 'cdr') value = call.dataset_name || '';
    else value = call[column.key] ?? '';
    const cell = node('td', String(value || '—'), `nq-optional-cell${value ? '' : ' nq-muted'}`);
    if (value) cell.title = `${column.label}: ${value}`;
    return cell;
  };
  const versionBadge = (call) => {
    if (!call.version_state) return null;
    const label = state.versionLabels[call.version_state] || call.version_state;
    const badge = node('span', label, `nq-version is-${call.version_state.replace(/_/g, '-')}`);
    const latest = call.latest_dataset_name && call.latest_dataset_name !== call.dataset_name ? `\nLatest CDR: ${call.latest_dataset_name}` : '';
    badge.title = `${VERSION_HINTS[call.version_state] || label}.\nShown from: ${call.dataset_name || '—'}${latest}`;
    return badge;
  };

  const renderRows = (result) => {
    const body = $('nq-rows');
    const columns = $('nq-table').tHead.rows[0].cells.length;
    if (!result.calls.length) {
      const cell = node('td', result.total === 0 && !Object.keys(currentFilters()).length
        ? 'No Non-Qualified Calls in the ready CDRs of this workspace.' : 'No calls match the filters.', 'nq-empty');
      cell.colSpan = columns;
      const row = node('tr');
      row.append(cell);
      body.replaceChildren(row);
      return;
    }
    body.replaceChildren(...result.calls.map((call) => {
      const row = node('tr');
      row.dataset.callKey = call.call_key;
      row.classList.toggle('is-selected', state.selected.has(call.call_key));
      if (state.user.can_edit) {
        const box = node('input');
        box.type = 'checkbox';
        box.checked = state.selected.has(call.call_key);
        box.setAttribute('aria-label', 'Select this call');
        box.addEventListener('click', (event) => event.stopPropagation());
        box.addEventListener('change', () => {
          if (box.checked) state.selected.add(call.call_key); else state.selected.delete(call.call_key);
          row.classList.toggle('is-selected', box.checked);
          renderBulk();
        });
        const cell = node('td', undefined, 'nq-select-cell');
        cell.append(box);
        row.append(cell);
      }
      // Start time with the service below it.
      const start = node('td', undefined, 'nq-start-cell');
      // The minute is enough in the row, below the date so the column stays narrow; the whole time shows on hover.
      const [day, ...clock] = cdrTime(call.start_time).replace(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}):\d{2}$/, '$1').split(' ');
      [day, clock.join(' ')].filter(Boolean).forEach((text) => {
        const part = node('span', text, 'nq-nowrap');
        part.title = cdrTime(call.start_time);
        start.append(part);
      });
      start.append(node('span', call.service_label, `nq-service nq-service-${call.service}`));
      if (call.service === 'speech' && Number(call.nq_samples) > 1) {
        const samples = node('span', `${number(call.nq_samples)} NQ samples`, 'nq-samples-badge');
        samples.title = 'Non-Qualified samples of this Speech call: open the call to follow each one up';
        start.append(samples);
      }
      // The result pill before the failure classification and category.
      const failure = node('td', undefined, 'nq-failure');
      failure.append(node('span', call.result || '—', `nq-result ${resultClass(call.result)}`));
      if (call.failure_classification || call.failure_category) {
        failure.append(node('strong', call.failure_classification || call.failure_category));
        if (call.failure_classification && call.failure_category) failure.append(node('span', call.failure_category));
        failure.title = [call.failure_subcategory, call.failure_comment].filter(Boolean).join('\n');
      } else {
        failure.append(node('span', 'Not classified', 'nq-muted'));
      }
      const badge = versionBadge(call);
      if (badge) failure.append(badge);
      const tracking = (...kinds) => {
        const cell = node('td', undefined, `nq-tracking-cell${kinds.length > 1 ? ' nq-tracking-stack' : ''}`);
        kinds.forEach((kind) => cell.append(state.user.can_edit ? trackingSelect(kind, call) : pill(kind, call[kind])));
        return cell;
      };
      // The status with the time (and author) of the last change of the call's follow-up.
      const status = tracking('status');
      status.classList.add('nq-tracking-stack');
      const updated = node('span', undefined, 'nq-status-updated');
      updated.append(statusModeBadge(call), ` ${call.updated_at ? `Updated ${relativeTime(call.updated_at)}${call.updated_by ? ` by ${call.updated_by}` : ''}` : 'Not followed up yet'}`);
      updated.title = call.updated_at ? `Last follow-up by ${call.updated_by || '—'} · ${exactTime(call.updated_at)}` : 'Nobody has changed this call yet';
      status.append(updated);
      const comments = node('td', undefined, 'nq-comments-cell');
      const commentButton = node('button', undefined, 'nq-comment-button');
      commentButton.type = 'button';
      const bubble = node('span', String(call.comment_count || 0), `nq-comment-count${call.comment_count ? '' : ' is-empty'}`);
      commentButton.append(bubble);
      if (call.last_comment) {
        const preview = node('span', undefined, 'nq-comment-preview');
        // The comment without its Markdown.
        const words = window.RichText.toPlainText(call.last_comment.body);
        preview.append(node('strong', call.last_comment.created_by), node('span', words));
        commentButton.append(preview);
        commentButton.title = `${call.last_comment.created_by} · ${exactTime(call.last_comment.created_at)}\n${words}`;
      } else {
        // Without comments, the count alone keeps the column narrow; what a click does shows on hover.
        commentButton.title = state.user.can_edit ? 'Add a comment' : 'No comments';
      }
      commentButton.addEventListener('click', (event) => {
        event.stopPropagation();
        openDetail(call.call_key, {focusComposer: true});
      });
      const openButton = node('button', '›', 'nq-open-button');
      openButton.type = 'button';
      openButton.setAttribute('aria-label', 'Open the call details and activity');
      const commentActions = node('div', undefined, 'nq-comment-actions-cell');
      commentActions.append(commentButton, openButton);
      comments.append(commentActions);
      // Two related values share a cell: the main one first, the other below it.
      const stacked = (main, secondary) => {
        const cell = node('td', undefined, 'nq-stacked');
        cell.append(node('strong', main || '—'));
        if (secondary) cell.append(node('span', secondary));
        cell.title = [main, secondary].filter(Boolean).join(' · ');
        return cell;
      };
      const root = node('td', undefined, 'nq-tracking-cell');
      root.append(rootCauseControl(call));
      // A pair of fields shares a cell: the first above the second.
      const fieldGroupCell = ({field, below}) => {
        const cell = fieldCell(call, field);
        if (!below) return cell;
        const top = node('div');
        top.append(...cell.childNodes);
        const bottom = node('div');
        bottom.append(...fieldCell(call, below).childNodes);
        const pair = node('div', undefined, 'nq-field-pair');
        pair.append(top, bottom);
        cell.append(pair);
        return cell;
      };
      const groups = fieldColumnGroups();
      row.append(
        start, stacked(call.operator, call.vendor), stacked(call.region, call.cluster), stacked(call.city, campaignLabel(call.campaign)),
        stacked(call.test_name, call.technology), failure, ...optionalColumns().map((column) => optionalCell(call, column)),
        ...groups.filter((group) => group.field.section === 'rca').map(fieldGroupCell),
        root, ...groups.filter((group) => group.field.section !== 'rca').map(fieldGroupCell), status,
        tracking('team', 'assignee'), comments,
      );
      orderRowCells(row);
      row.addEventListener('click', (event) => {
        if (event.target.closest('select, input, a')) return;
        openDetail(call.call_key);
      });
      return row;
    }));
  };
  const renderSortHeaders = () => {
    $('nq-table').querySelectorAll('[data-sort]').forEach((header) => {
      const active = header.dataset.sort === state.sort;
      header.classList.toggle('is-sorted', active);
      header.dataset.direction = active ? state.direction : '';
      header.setAttribute('aria-sort', active ? (state.direction === 'asc' ? 'ascending' : 'descending') : 'none');
    });
  };
  const pagerArrow = (name, path, disabled, onClick) => {
    const element = node('button');
    element.type = 'button';
    element.disabled = disabled;
    element.setAttribute('aria-label', `${name} page`);
    element.title = `${name} page`;
    element.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${path}"/></svg>`;
    element.addEventListener('click', onClick);
    return element;
  };
  const ARROWS = {First: 'M5 5v14M18 6l-6 6 6 6M12 6l-6 6 6 6', Previous: 'M15 6l-6 6 6 6', Next: 'M9 6l6 6-6 6',
    Last: 'M19 5v14M6 6l6 6-6 6M12 6l6 6-6 6'};
  const renderPagination = (result) => {
    const host = $('nq-pagination');
    if (result.pages <= 1) { host.replaceChildren(); return; }
    const button = (label, page, disabled = false, current = false) => {
      const element = node('button', label, current ? 'is-current nq-page-number' : 'nq-page-number');
      element.type = 'button';
      element.disabled = disabled;
      if (current) element.setAttribute('aria-current', 'page');
      element.addEventListener('click', () => { state.page = page; loadCalls(); });
      return element;
    };
    const go = (page) => () => { state.page = page; loadCalls(); };
    const pages = new Set([1, result.pages, result.page - 1, result.page, result.page + 1]);
    const items = [pagerArrow('First', ARROWS.First, result.page <= 1, go(1)),
      pagerArrow('Previous', ARROWS.Previous, result.page <= 1, go(result.page - 1))];
    let previous = 0;
    [...pages].filter((page) => page >= 1 && page <= result.pages).sort((a, b) => a - b).forEach((page) => {
      if (page - previous > 1) items.push(node('span', '…', 'nq-ellipsis'));
      items.push(button(String(page), page, false, page === result.page));
      previous = page;
    });
    items.push(pagerArrow('Next', ARROWS.Next, result.page >= result.pages, go(result.page + 1)),
      pagerArrow('Last', ARROWS.Last, result.page >= result.pages, go(result.pages)));
    host.replaceChildren(...items);
  };
  // The actions of the selected calls cover the toolbar right above the table, so the table
  // does not move, and stay at the top of the window while the table is scrolled.
  const placeBulk = () => {
    const bulk = $('nq-bulk');
    if (!bulk || bulk.hidden) return;
    const toolbar = root.querySelector('.nq-toolbar');
    const table = $('nq-table').closest('.nq-table-wrap').getBoundingClientRect();
    const anchor = toolbar.getBoundingClientRect();
    const top = Math.min(Math.max(12, anchor.top), Math.max(12, table.bottom - bulk.offsetHeight));
    bulk.style.top = `${top}px`;
    bulk.style.left = `${table.left}px`;
    bulk.style.width = `${table.width}px`;
    bulk.classList.toggle('is-floating', anchor.top < 12);
  };
  let placeFrame = 0;
  const schedulePlaceBulk = () => {
    if (placeFrame) return;
    placeFrame = window.requestAnimationFrame(() => { placeFrame = 0; placeBulk(); });
  };
  window.addEventListener('scroll', schedulePlaceBulk, {passive: true});
  window.addEventListener('resize', schedulePlaceBulk);
  const renderBulk = () => {
    const bulk = $('nq-bulk');
    if (!bulk) return;
    // The actions of the selected calls go with the table.
    bulk.hidden = !state.selected.size || Boolean(panelOf('calls')?.hidden);
    placeBulk();
    $('nq-bulk-count').textContent = `${number(state.selected.size)} selected`;
    const pageBox = $('nq-select-page');
    if (pageBox && state.result) {
      const keys = state.result.calls.map((call) => call.call_key);
      const chosen = keys.filter((key) => state.selected.has(key)).length;
      pageBox.checked = keys.length > 0 && chosen === keys.length;
      pageBox.indeterminate = chosen > 0 && chosen < keys.length;
    }
  };
  const fillBulkSelects = () => {
    const fill = (id, placeholder, entries) => {
      const select = $(id);
      if (!select) return;
      select.replaceChildren(node('option', placeholder), ...entries.map(([value, label]) => {
        const option = node('option', label);
        option.value = value;
        return option;
      }));
      select.options[0].value = '';
    };
    fill('nq-bulk-status', 'Set status…', [...state.options.statuses.map((item) => [item.name, item.name]),
      [AUTO_STATUS, '↺ Back to automatic']]);
    fill('nq-bulk-team', 'Set team…', [[state.unassigned, 'Unassigned'], ...state.options.teams.map((item) => [item.name, item.name])]);
    fill('nq-bulk-assignee', 'Assign to…', [[state.unassigned, 'Unassigned']]);
    $('nq-bulk-assignee')?.append(...userOptions(state.users));
    // Root categories and causes under their domain.
    [['nq-bulk-category', 'Set root category…', NOT_CLASSIFIED, state.rootCauses.categories],
      ['nq-bulk-root', 'Set root cause…', NO_CAUSE, state.rootCauses.causes]].forEach(([id, placeholder, empty, items]) => {
      const select = $(id);
      if (!select) return;
      select.replaceChildren(node('option', placeholder), node('option', empty));
      select.options[0].value = '';
      select.options[1].value = state.unassigned;
      rootGroups(items).forEach(([domain, group]) => {
        const optgroup = node('optgroup');
        optgroup.label = domain || 'Without a domain';
        optgroup.append(...group.map((item) => {
          const option = node('option', item.name);
          option.value = item.name;
          return option;
        }));
        select.append(optgroup);
      });
    });
    const fieldSelect = $('nq-bulk-field');
    if (fieldSelect) {
      const choosable = state.fields.filter((field) => ['list', 'yes_no'].includes(field.type) && field.source === 'user');
      fieldSelect.hidden = !choosable.length;
      fieldSelect.replaceChildren(node('option', 'Set field…'));
      fieldSelect.options[0].value = '';
      choosable.forEach((field) => {
        const group = node('optgroup');
        group.label = field.label;
        const values = field.type === 'yes_no' ? ['Yes', 'No'] : field.options.map((option) => option.name);
        group.append(...[...values, ''].map((value) => {
          const option = node('option', value || `${field.label}: empty`);
          option.value = `${field.key}${ROOT_SEPARATOR}${value}`;
          return option;
        }));
        fieldSelect.append(group);
      });
    }
  };

  // -- views and panels on screen ---------------------------------------------------------
  // The panels calculated on their own after each change of the calls (the Summary comes with the calls).
  const panelOf = (name) => root.querySelector(`[data-nq-loader="${name}"]`);
  // While a panel waits for its data it shows an animated bar below its filters, as Scoring & GAP Analysis while it
  // calculates, and its previous content is dimmed.
  const loadingBars = new Map();
  const showPanelLoading = (panel) => {
    const body = panel?.querySelector(':scope > .collapsible-panel-body');
    if (!body || loadingBars.has(panel)) return;
    const bar = node('div', undefined, 'nq-panel-loading');
    bar.setAttribute('role', 'status');
    bar.append(node('p', `Loading ${panel.querySelector('h2')?.textContent.trim() || 'the panel'}…`, 'nq-panel-loading-title'));
    const track = node('div', undefined, 'nq-panel-loading-bar');
    track.append(node('span', undefined, 'nq-panel-loading-fill'));
    bar.append(track);
    const chips = body.querySelector(':scope > [data-nq-active-filters]');
    if (chips) chips.after(bar);
    else body.prepend(bar);
    panel.classList.add('is-awaiting-data');
    loadingBars.set(panel, bar);
  };
  const hidePanelLoading = (panel) => {
    loadingBars.get(panel)?.remove();
    loadingBars.delete(panel);
    panel?.classList.remove('is-awaiting-data');
  };
  // The panels whose own data is being read.
  const panelsLoading = new Set();
  const withLoadingBar = (name, load) => async (...args) => {
    const panel = panelOf(name);
    showPanelLoading(panel);
    panelsLoading.add(panel);
    try {
      return await load(...args);
    } finally {
      panelsLoading.delete(panel);
      hidePanelLoading(panel);
    }
  };
  // The hotspots, time-window and clustered issues come with the NQ Prioritization: either panel unfolded reads both.
  const PANEL_LOADERS = Object.fromEntries(Object.entries({prioritization: loadPrioritization, clusters: loadPrioritization, rates: loadRates, failures: loadFailures,
    progress: loadProgress, lifecycle: loadLifecycle, root: loadRootCauses, sources: loadSources, l3maps: loadL3Maps})
    .map(([name, load]) => [name, withLoadingBar(name, load)]));
  const panelShown = (name) => {
    const panel = panelOf(name);
    return Boolean(panel && !panel.hidden && panel.open);
  };
  // The panels left out of the last filter change, calculated once they are shown.
  const refreshStale = () => {
    if (state.stale.has('summary') && panelShown('summary')) { loadCalls({quiet: true}); return; }
    Object.entries(PANEL_LOADERS).forEach(([name, load]) => {
      if (state.stale.has(name) && panelShown(name)) {
        state.stale.delete(name);
        void load();
      }
    });
  };
  // Every panel shows, in a badge below its Collapse button, how many calls match the filters.
  const panelCounts = [...root.querySelectorAll('details.panel > summary.collapsible-summary')].map((summary) => {
    const chip = summary.querySelector(':scope > .collapse-chip');
    if (!chip) return null;
    const corner = node('span', undefined, 'nq-panel-corner');
    const badge = node('span', '…', 'nq-panel-count');
    badge.title = 'Non-Qualified Calls that match the current filters';
    chip.replaceWith(corner);
    corner.append(chip, badge);
    return badge;
  }).filter(Boolean);
  const renderPanelCounts = (total) => panelCounts.forEach((badge) => {
    badge.replaceChildren(node('strong', number(total)), total === 1 ? 'Filtered Call' : 'Filtered Calls');
  });
  root.querySelectorAll('[data-nq-loader]').forEach((panel) => panel.addEventListener('toggle', () => { if (panel.open) refreshStale(); }));

  // -- loading ----------------------------------------------------------------
  // The indexing runs in the background (when the server is idle, the first time, or on Reindex): the badge says
  // so, and the page follows it with a light status request, then reloads its calls.
  let indexWatch = null;
  const watchIndexing = () => {
    if (indexWatch) return;
    indexWatch = window.setTimeout(async function check() {
      try {
        const {sync} = await api('/api/non-qualified-calls/index-status');
        if (sync.indexing) {
          renderSync(sync, {watch: false});
          indexWatch = window.setTimeout(check, 4000);
          return;
        }
        indexWatch = null;
        await loadState();
      } catch (_error) {
        indexWatch = window.setTimeout(check, 8000);
      }
    }, 4000);
  };
  const renderSync = (sync, {watch = true} = {}) => {
    if (!sync) return;
    const when = sync.synced_at ? ` · indexed ${relativeTime(sync.synced_at)}` : '';
    const pending = sync.indexing ? (sync.reindexing ? ' · reindexing every CDR…' : ' · indexing…')
      : sync.pending ? ` · ${number(sync.pending)} CDR${sync.pending === 1 ? '' : 's'} waiting to be indexed` : '';
    $('nq-sync').textContent = `${number(sync.calls)} Non-Qualified Calls in ${number(sync.datasets)} CDRs${when}${pending}`;
    $('nq-sync').title = [sync.synced_at ? `CDRs last indexed ${exactTime(sync.synced_at)}` : '',
      sync.pending && !sync.indexing ? 'New or changed CDRs are indexed once the server is idle, or now with Reindex' : '',
      sync.error ? `The last indexing failed: ${sync.error}` : ''].filter(Boolean).join('\n');
    $('nq-refresh').disabled = Boolean(sync.indexing);
    if (sync.indexing && watch) watchIndexing();
  };
  async function loadCalls({quiet = false} = {}) {
    const token = ++state.requestToken;
    // What is in use or being read stays where it is while the panels are drawn again.
    if (!quiet) keepViewWhileLoading();
    const filters = currentFilters();
    if (state.filtersRestored) saveFilters(filters);
    loadAvailable(filters, quiet);
    // The filters are shown on every panel at once, before their data arrives.
    renderActiveFilters(filters);
    // The panels on screen wait for the calls and then for their own data.
    const waiting = quiet ? [] : ['calls', 'summary', ...Object.keys(PANEL_LOADERS)].map(panelOf).filter((panel) => panel && !panel.hidden && panel.open);
    waiting.forEach(showPanelLoading);
    if (!quiet) {
      $('nq-count').textContent = 'Loading calls…';
      root.classList.add('is-loading');
    }
    try {
      // The breakdowns of the Summary are only asked for while it is shown.
      const breakdowns = panelShown('summary');
      const result = await api('/api/non-qualified-calls/calls', {
        method: 'POST',
        body: JSON.stringify({filters, sort: state.sort, direction: state.direction, page: state.page, page_size: state.pageSize, breakdowns,
          locate: state.locate || ''}),
        // A quiet reload is the page keeping itself current, not someone using the application.
        ...(quiet ? {headers: {'X-Background-Refresh': '1'}} : {}),
      });
      if (token !== state.requestToken) return;
      state.result = result;
      state.page = result.page;
      state.locate = '';
      renderSync(result.sync);
      renderActiveFilters(filters);
      renderColumnFilters();
      if (breakdowns) {
        renderSummary(result);
        state.stale.delete('summary');
      } else {
        state.stale.add('summary');
      }
      renderRows(result);
      renderSortHeaders();
      renderPagination(result);
      renderBulk();
      if (state.detail) renderDetailNav();
      $('nq-view-count').textContent = number(result.total);
      renderPanelCounts(result.total);
      // Only the panels on screen (shown and unfolded) are calculated; the others when they are opened.
      Object.entries(PANEL_LOADERS).forEach(([name, load]) => {
        if (panelShown(name)) {
          state.stale.delete(name);
          void load();
        } else {
          state.stale.add(name);
        }
      });
      const first = result.total ? (result.page - 1) * result.page_size + 1 : 0;
      const last = Math.min(result.total, result.page * result.page_size);
      $('nq-count').textContent = result.total ? `Showing ${number(first)}–${number(last)} of ${number(result.total)} calls` : 'No calls';
    } catch (error) {
      if (token !== state.requestToken) return;
      $('nq-count').textContent = error.message;
      if (!quiet) toast(error.message, 'error');
    } finally {
      // A newer request keeps the bars; otherwise the calls and the Summary have arrived (or failed), and the other
      // panels keep their bar only while their own data is read.
      if (token === state.requestToken) {
        waiting.forEach((panel) => { if (!panelsLoading.has(panel)) hidePanelLoading(panel); });
        root.classList.remove('is-loading');
      }
    }
  }
  // The filters changed: the first page, or the page that holds the call open beside the list (so that its arrows keep going
  // through the calls of the filters).
  const scheduleLoad = debounce(() => {
    state.page = 1;
    state.locate = $('nq-drawer')?.getAttribute('aria-hidden') === 'false' ? state.detail?.call.call_key || '' : '';
    loadCalls();
  }, 300);

  // -- progress view --------------------------------------------------------------
  const PALETTE = ['#b0234f', '#0f6f7d', '#e08a1e', '#6a63c9', '#2e8b57', '#245a96', '#b85b20', '#7b8790', '#5b6b2e', '#c8365f'];
  const GRANULARITY_LABELS = {week: 'Week', month: 'Month', quarter: 'Quarter', year: 'Year'};
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const svgNode = (tag, attributes = {}) => {
    const element = document.createElementNS(SVG_NS, tag);
    Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
    return element;
  };
  const kpiCard = (label, value, note, kind = '') => {
    const card = node('article', undefined, `nq-kpi${kind ? ` nq-kpi-${kind}` : ''}`);
    card.append(node('span', label, 'nq-kpi-label'), node('strong', value), node('span', note, 'nq-kpi-note'));
    return card;
  };
  const days = (value) => (value === null || value === undefined ? '—' : `${Number(value).toFixed(1)} d`);
  // One floating tooltip for the Progress View charts; it follows the pointer and hides when it leaves the chart.
  const chartTooltip = (() => {
    const tip = node('div', undefined, 'nq-chart-tooltip');
    tip.hidden = true;
    tip.setAttribute('role', 'tooltip');
    document.body.append(tip);
    const show = (event, title, rows) => {
      const heading = node('strong', title);
      const list = node('div', undefined, 'nq-chart-tooltip-rows');
      rows.forEach(([label, value, color]) => {
        const line = node('div');
        const swatch = node('span', '', 'nq-swatch');
        swatch.style.background = color || 'transparent';
        line.append(swatch, node('span', label), node('b', value));
        list.append(line);
      });
      tip.replaceChildren(heading, list);
      tip.hidden = false;
      const gap = 14;
      const box = tip.getBoundingClientRect();
      const x = event.clientX + gap + box.width > window.innerWidth ? event.clientX - gap - box.width : event.clientX + gap;
      const y = Math.min(window.innerHeight - box.height - 8, Math.max(8, event.clientY - box.height / 2));
      tip.style.left = `${x}px`;
      tip.style.top = `${y}px`;
    };
    const hide = () => { tip.hidden = true; };
    window.addEventListener('scroll', hide, true);
    window.addEventListener('blur', hide);
    return {show, hide};
  })();
  // A donut chart with its legend; a click on a slice filters the calls.
  const donut = (distribution) => {
    const card = node('section', undefined, 'nq-pie');
    card.append(node('h3', distribution.label));
    const items = distribution.items.slice(0, 10);
    const total = items.reduce((sum, item) => sum + item.count, 0);
    const colorFor = (item, index) => (distribution.field === 'status' ? optionColor('status', item.value)
      : distribution.field === 'team' ? optionColor('team', item.value) : '') || PALETTE[index % PALETTE.length];
    const svg = svgNode('svg', {viewBox: '0 0 120 120', class: 'nq-pie-chart', role: 'img', 'aria-label': distribution.label});
    const radius = 46;
    const circumference = 2 * Math.PI * radius;
    let offset = 0;
    svg.append(svgNode('circle', {cx: 60, cy: 60, r: radius, fill: 'none', stroke: '#f3dfe6', 'stroke-width': 18}));
    items.forEach((item, index) => {
      const length = total ? (item.count / total) * circumference : 0;
      const slice = svgNode('circle', {
        cx: 60, cy: 60, r: radius, fill: 'none', stroke: colorFor(item, index), 'stroke-width': 18,
        'stroke-dasharray': `${length} ${circumference - length}`, 'stroke-dashoffset': -offset, transform: 'rotate(-90 60 60)',
      });
      slice.classList.add('nq-pie-slice');
      slice.addEventListener('pointermove', (event) => chartTooltip.show(event, distribution.label,
        [[item.value, `${number(item.count)} · ${percent(item.count, total)}`, colorFor(item, index)]]));
      slice.addEventListener('pointerleave', chartTooltip.hide);
      slice.addEventListener('click', () => {
        chartTooltip.hide();
        const field = {status: 'status', team: 'team', assignee: 'assignee', service: 'service', result: 'result'}[distribution.field];
        if (field) selectOnly(field, item.filter ?? (['Unassigned', '—'].includes(item.value) ? '' : item.value));
      });
      svg.append(slice);
      offset += length;
    });
    const centre = svgNode('text', {x: 60, y: 64, 'text-anchor': 'middle', class: 'nq-pie-total'});
    centre.textContent = number(total);
    svg.append(centre);
    const legend = node('ul', undefined, 'nq-pie-legend');
    items.forEach((item, index) => {
      const row = node('li');
      const button = node('button', undefined, 'nq-pie-item');
      button.type = 'button';
      const swatch = node('span', '', 'nq-swatch');
      swatch.style.background = colorFor(item, index);
      button.append(swatch, node('span', item.value, 'nq-pie-label'), node('strong', `${number(item.count)} · ${percent(item.count, total)}`));
      const filterField = {status: 'status', team: 'team', assignee: 'assignee', service: 'service', result: 'result'}[distribution.field];
      button.title = `Show only ${item.value}`;
      button.addEventListener('click', () => {
        const value = item.filter ?? (['Unassigned', '—'].includes(item.value) ? '' : item.value);
        selectOnly(filterField, value);
      });
      row.append(button);
      legend.append(row);
    });
    if (!items.length) legend.append(node('li', 'No calls.', 'nq-muted'));
    card.append(svg, legend);
    return card;
  };
  const statsTable = (table, columns, rows, {drillRow = null} = {}) => {
    const head = node('thead');
    const headRow = node('tr');
    columns.forEach((column) => headRow.append(node('th', column)));
    head.append(headRow);
    const body = node('tbody');
    rows.forEach((values, rowIndex) => {
      const row = node('tr');
      values.forEach((value, index) => row.append(node('td', value, index ? 'nq-number' : '')));
      const pairs = drillRow?.(rowIndex);
      if (pairs) {
        row.classList.add('nq-drill-row');
        row.classList.toggle('is-active', isDrilled(pairs));
        row.tabIndex = 0;
        row.title = 'Show only these calls; click again to remove the filter';
        row.addEventListener('click', () => drill(pairs));
        row.addEventListener('keydown', (event) => { if (event.key === 'Enter') drill(pairs); });
      }
      body.append(row);
    });
    if (!rows.length) {
      const row = node('tr');
      const cell = node('td', 'No data for this selection.', 'nq-empty');
      cell.colSpan = columns.length;
      row.append(cell);
      body.append(row);
    }
    table.replaceChildren(head, body);
  };
  // Detected, attended and closed calls per period, with the open backlog as a line.
  const timelineChart = (periods) => {
    const host = $('nq-timeline-chart');
    const shown = periods.slice(-24);
    if (!shown.length) { host.replaceChildren(node('p', 'No dated activity for this selection.', 'nq-muted')); return; }
    const series = [['detected', 'Detected', '#8a6b76'], ['attended', 'Attended', '#e08a1e'], ['closed', 'Closed', '#2e8b57']];
    const width = Math.max(640, shown.length * 64);
    const height = 240;
    const top = 16;
    const bottom = 40;
    const left = 40;
    const plot = height - top - bottom;
    const maximum = Math.max(1, ...shown.flatMap((period) => [...series.map(([key]) => period[key]), period.open_backlog]));
    const svg = svgNode('svg', {viewBox: `0 0 ${width + left} ${height}`, class: 'nq-timeline-svg', role: 'img', 'aria-label': 'Progress per period'});
    [0, 0.25, 0.5, 0.75, 1].forEach((share) => {
      const y = top + plot * (1 - share);
      svg.append(svgNode('line', {x1: left, x2: width + left, y1: y, y2: y, class: 'nq-grid-line'}));
      const label = svgNode('text', {x: left - 6, y: y + 4, 'text-anchor': 'end', class: 'nq-axis-label'});
      label.textContent = number(Math.round(maximum * share));
      svg.append(label);
    });
    const slot = width / shown.length;
    const bar = Math.min(16, (slot - 12) / series.length);
    const points = [];
    const zones = [];
    shown.forEach((period, index) => {
      const x = left + index * slot + (slot - bar * series.length) / 2;
      series.forEach(([key, label, color], position) => {
        const value = period[key];
        const barHeight = (value / maximum) * plot;
        svg.append(svgNode('rect', {x: x + position * bar, y: top + plot - barHeight, width: bar - 2, height: barHeight, rx: 2, fill: color}));
      });
      // The whole period column answers the pointer with every value of the period.
      const zone = svgNode('rect', {x: left + index * slot, y: top, width: slot, height: plot, class: 'nq-timeline-zone'});
      const rows = [...series.map(([key, label, color]) => [label, number(period[key]), color]), ['Open backlog', number(period.open_backlog), '#b0234f']];
      zone.addEventListener('pointermove', (event) => chartTooltip.show(event, period.period, rows));
      zone.addEventListener('pointerleave', chartTooltip.hide);
      zone.addEventListener('click', () => { chartTooltip.hide(); drill([['period', `${$('nq-granularity').value}:${period.period}`]]); });
      zones.push(zone);
      points.push(`${left + index * slot + slot / 2},${top + plot - (period.open_backlog / maximum) * plot}`);
      const caption = svgNode('text', {x: left + index * slot + slot / 2, y: height - bottom + 16, 'text-anchor': 'middle', class: 'nq-axis-label'});
      caption.textContent = period.period;
      svg.append(caption);
    });
    svg.append(svgNode('polyline', {points: points.join(' '), class: 'nq-backlog-line'}));
    points.forEach((point) => {
      const [cx, cy] = point.split(',');
      svg.append(svgNode('circle', {cx, cy, r: 3.5, class: 'nq-backlog-point'}));
    });
    svg.append(...zones);
    svg.addEventListener('pointerleave', chartTooltip.hide);
    const legend = node('div', undefined, 'nq-chart-legend');
    [...series, ['open_backlog', 'Open backlog', '#b0234f']].forEach(([, label, color]) => {
      const item = node('span');
      const swatch = node('span', '', 'nq-swatch');
      swatch.style.background = color;
      item.append(swatch, label);
      legend.append(item);
    });
    const scroller = node('div', undefined, 'nq-chart-scroll');
    scroller.append(svg);
    host.replaceChildren(legend, scroller);
    scroller.scrollLeft = scroller.scrollWidth;
  };
  const renderProgress = (progress) => {
    const summary = progress.summary;
    $('nq-progress-kpis').replaceChildren(
      drillCard(kpiCard('Attended', number(summary.attended), `${percent(summary.attended, summary.total)} have a follow-up`, 'open'), {pairs: [['state', 'attended']]}),
      drillCard(kpiCard('Not Attended', number(summary.not_attended), 'No change or comment yet', 'total'), {pairs: [['state', 'not_attended']]}),
      drillCard(kpiCard('Closure Rate', `${summary.closure_rate.toFixed(1)}%`, `${number(summary.closed)} of ${number(summary.total)} closed`, 'closed'), {pairs: [['state', 'closed']]}),
      drillCard(kpiCard('First Follow-up', days(summary.avg_days_to_first_follow_up), 'Average from the call', 'team'), {pairs: [['state', 'attended']]}),
      drillCard(kpiCard('Time to Close', days(summary.avg_days_to_close), 'Average from the call', 'commented'), {pairs: [['state', 'closed']]}),
      drillCard(kpiCard('Activity', number(summary.comments + summary.changes), `${number(summary.comments)} comments · ${number(summary.changes)} changes · ${number(summary.contributors)} users`), {pairs: [['state', 'attended']]}),
    );
    $('nq-pies').replaceChildren(...progress.distributions.map(donut));
    const label = GRANULARITY_LABELS[progress.granularity] || 'Week';
    $('nq-timeline-title').textContent = `Progress per ${label}`;
    timelineChart(progress.periods);
    const periods = [...progress.periods].reverse();
    statsTable($('nq-timeline-table'), [label, 'Detected', 'Attended', 'Comments', ...progress.statuses.map((status) => `→ ${status}`),
      'Closed', 'Reopened', 'Open Backlog', 'Avg Days to Close'],
    periods.map((period) => [period.period, number(period.detected), number(period.attended), number(period.comments),
      ...progress.statuses.map((status) => number(period.statuses[status] || 0)), number(period.closed), number(period.reopened),
      number(period.open_backlog), period.avg_days_to_close === null ? '—' : period.avg_days_to_close.toFixed(1)]),
    {drillRow: (index) => [['period', `${progress.granularity}:${periods[index].period}`]]});
    const agingTotal = progress.aging.reduce((sum, item) => sum + item.count, 0);
    const maxAge = Math.max(1, ...progress.aging.map((item) => item.count));
    $('nq-aging').replaceChildren(...progress.aging.map((item) => {
      const pairs = [['age', item.value], ['open_only', true]];
      const row = node('button', undefined, 'nq-bar');
      row.type = 'button';
      row.classList.toggle('is-active', isDrilled([pairs[0]]));
      row.title = `Show only the open calls ${item.value.toLowerCase()} old`;
      row.addEventListener('click', () => drill(pairs));
      const track = node('span', undefined, 'nq-bar-track');
      const fill = node('span', undefined, 'nq-bar-fill');
      fill.style.width = `${Math.max(2, (item.count / maxAge) * 100)}%`;
      track.append(fill);
      row.append(node('span', item.value, 'nq-bar-label'), track, node('span', `${number(item.count)} · ${percent(item.count, agingTotal)}`, 'nq-bar-count'));
      return row;
    }));
    const workload = (rows) => rows.map((row) => [row.name, number(row.open), number(row.closed), number(row.total)]);
    const person = (name) => (name === 'Unassigned' ? state.unassigned : name);
    statsTable($('nq-team-workload'), ['Team', 'Open', 'Closed', 'Total'], workload(progress.teams),
      {drillRow: (index) => [['team', person(progress.teams[index].name)]]});
    statsTable($('nq-assignee-workload'), ['Assignee', 'Open', 'Closed', 'Total'],
      workload(progress.assignees.map((row) => ({...row, name: row.name === 'Unassigned' ? row.name : userName(row.name)}))),
      {drillRow: (index) => [['assignee', person(progress.assignees[index].name)]]});
    statsTable($('nq-activity'), ['User', 'Changes', 'Comments', 'Calls Closed'],
      progress.activity.map((row) => [row.name, number(row.changes), number(row.comments), number(row.closed)]));
  };
  let progressToken = 0;
  async function loadProgress() {
    const token = ++progressToken;
    try {
      const progress = await api('/api/non-qualified-calls/progress', {
        method: 'POST', body: JSON.stringify({filters: currentFilters(), granularity: $('nq-granularity').value}),
      });
      if (token === progressToken) renderProgress(progress);
    } catch (error) {
      if (token === progressToken) $('nq-progress-kpis').replaceChildren(node('p', error.message, 'nq-muted'));
    }
  }
  $('nq-granularity').addEventListener('change', () => loadProgress());

  // -- root cause analysis ----------------------------------------------------------
  const staticBars = (title, items) => {
    // Items with drill pairs are buttons that filter the calls.
    const card = node('section', undefined, 'nq-breakdown');
    card.append(node('h3', title));
    const max = Math.max(1, ...items.map((item) => item.count));
    const total = items.reduce((sum, item) => sum + item.count, 0);
    if (!items.length) card.append(node('p', 'No calls.', 'form-note'));
    items.slice(0, 15).forEach((item) => {
      const row = node(item.pairs ? 'button' : 'div', undefined, item.pairs ? 'nq-bar' : 'nq-bar nq-static-bar');
      if (item.pairs) {
        row.type = 'button';
        row.classList.toggle('is-active', isDrilled(item.pairs));
        row.addEventListener('click', () => drill(item.pairs));
      }
      const track = node('span', undefined, 'nq-bar-track');
      const fill = node('span', undefined, 'nq-bar-fill');
      fill.style.width = `${Math.max(2, (item.count / max) * 100)}%`;
      if (item.color) fill.style.background = item.color;
      track.append(fill);
      row.title = item.pairs ? `${item.label}: show only these calls; click again to remove the filter` : item.label;
      row.append(node('span', item.label, 'nq-bar-label'), track, node('span', `${number(item.count)} · ${percent(item.count, total)}`, 'nq-bar-count'));
      card.append(row);
    });
    return card;
  };
  // The root causes the panel counts: those the analysts chose, or what the DT Analyzer RCA, the NetCheck RCA or the
  // Ericsson RCA gives each call on the catalog; a domain, domain·category or domain·cause filters the calls of
  // that source.
  // The panel opens on its first tab, the DT Analyzer RCA.
  state.rootSource = 'dta';
  const ROOT_SOURCE_NAMES = {analysts: 'the analysts', netcheck: `the ${PROVIDER_RCA}`, script: 'the Ericsson RCA',
    dta: 'the DT Analyzer RCA'};
  const domainPair = (domain) => [state.rootSource === 'analysts' ? 'root_domain' : `${state.rootSource}_domain`,
    domain === NOT_CLASSIFIED ? state.unassigned : domain];
  const causePair = (domain, cause) => [state.rootSource === 'analysts' ? 'root_pair' : `${state.rootSource}_cause`, `${domain}||${cause}`];
  const categoryPairs = (domain, category) => (state.rootSource === 'analysts'
    ? [domainPair(domain), ['root_category', category || state.unassigned]] : [[`${state.rootSource}_category`, `${domain}||${category}`]]);
  const ROOT_FILTERS = ['rca_state', 'state', 'effective_domain', 'effective_cause', 'root_pair', 'netcheck_domain', 'netcheck_category',
    'netcheck_cause', 'script_domain', 'script_category', 'script_cause', 'dta_raw', 'netcheck_raw', 'script_raw'];
  // Calls of every group per root domain: a bar per group split in the colours of its domains, with the count of each
  // wide enough part and, below it, the count of every domain; the group filters its calls, and each part or count
  // the calls of its domain.
  const readableText = (color) => {
    const hex = /^#([0-9a-f]{6})$/i.exec(color || '');
    if (!hex) return '#fff';
    const [r, g, b] = [0, 2, 4].map((index) => parseInt(hex[1].slice(index, index + 2), 16));
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.62 ? 'var(--nq-dark)' : '#fff';
  };
  const drillable = (element, pairs, title) => {
    element.title = pairs ? `${title}: show only these calls; click again to remove the filter` : title;
    if (!pairs) return element;
    element.classList.add('is-drill');
    element.classList.toggle('is-active', isDrilled(pairs));
    element.tabIndex = 0;
    element.setAttribute('role', 'button');
    element.addEventListener('click', () => drill(pairs));
    element.addEventListener('keydown', (event) => { if (event.key === 'Enter') drill(pairs); });
    return element;
  };
  // The root domains in their colours, above the charts that split the calls by them.
  const domainLegend = (legend, columns, colors) => {
    legend.replaceChildren(...columns.map((column) => {
      const swatch = node('span', '', 'nq-swatch');
      swatch.style.background = colors[column] || '#b8c0c6';
      const item = node('span', undefined, 'nq-stack-key');
      item.append(swatch, column);
      return item;
    }));
    return legend;
  };
  // One bar per group split in the colours of its root domains, with their legend above.
  const domainBars = (container, rows, columns, colors, groupPair = null) => {
    const legend = domainLegend(node('div', undefined, 'nq-stack-legend'), columns, colors);
    const lines = rows.map((row) => {
      const group = groupPair?.(row.name);
      const line = node('div', undefined, 'nq-stack-row');
      const track = node('div', undefined, 'nq-stack-track');
      columns.filter((column) => row.counts[column]).forEach((column) => {
        const count = row.counts[column];
        const share = (count / Math.max(1, row.total)) * 100;
        const title = `${row.name} · ${column}: ${number(count)} · ${percent(count, row.total)}`;
        const part = node('span', share >= 9 ? number(count) : '', 'nq-stack-part');
        part.style.flexBasis = `${share}%`;
        part.style.background = colors[column] || '#b8c0c6';
        part.style.color = readableText(colors[column] || '#b8c0c6');
        track.append(drillable(part, group ? [group, domainPair(column)] : null, title));
      });
      line.append(drillable(node('span', row.name, 'nq-stack-name'), group ? [group] : null, row.name), track,
        node('span', number(row.total), 'nq-stack-total'));
      return line;
    });
    container.replaceChildren(legend, ...(lines.length ? lines : [node('p', 'No data for this selection.', 'form-note')]));
  };
  // One donut per group (call type, NR mode) split in the colours of its root domains, under the legend they share:
  // each slice shows its calls when it is long enough for them, and all of them on hover.
  const domainDonuts = (container, rows, columns, colors, groupPair) => {
    // The groups share the row by their number of donuts, so every donut gets the same width.
    container.parentElement.style.setProperty('--nq-donuts', Math.max(1, rows.length));
    const radius = 44;
    const band = 26;
    const circumference = 2 * Math.PI * radius;
    const point = (distance, angle) => `${60 + distance * Math.cos(angle)} ${60 + distance * Math.sin(angle)}`;
    // Each slice is a filled ring sector: a dashed stroke leaves a spike where the circle closes on some browsers.
    const sector = (start, end) => {
      const outer = radius + band / 2;
      const inner = radius - band / 2;
      const large = end - start > Math.PI ? 1 : 0;
      return `M ${point(outer, start)} A ${outer} ${outer} 0 ${large} 1 ${point(outer, end)} L ${point(inner, end)} `
        + `A ${inner} ${inner} 0 ${large} 0 ${point(inner, start)} Z`;
    };
    const cards = rows.map((row) => {
      const group = groupPair(row.name);
      const label = `${row.name} · ${number(row.total)} calls`;
      const svg = svgNode('svg', {viewBox: '0 0 120 120', class: 'nq-domain-donut-chart', role: 'img', 'aria-label': label});
      svg.append(svgNode('circle', {cx: 60, cy: 60, r: radius, fill: 'none', stroke: '#f3dfe6', 'stroke-width': band}));
      const values = [];
      let offset = 0;
      columns.filter((column) => row.counts[column]).forEach((column) => {
        const count = row.counts[column];
        const length = (count / Math.max(1, row.total)) * circumference;
        const color = colors[column] || '#b8c0c6';
        const pairs = [group, domainPair(column)];
        const start = (offset / circumference) * 2 * Math.PI - Math.PI / 2;
        // A whole ring stops a hair short of its start, as an arc cannot end where it begins.
        const slice = svgNode('path', {d: sector(start, start + Math.min(length / radius, 2 * Math.PI - 0.0005)), fill: color});
        slice.classList.add('nq-domain-donut-slice');
        slice.classList.toggle('is-active', isDrilled(pairs));
        slice.addEventListener('pointermove', (event) => chartTooltip.show(event, label,
          [[column, `${number(count)} · ${percent(count, row.total)}`, color]]));
        slice.addEventListener('pointerleave', chartTooltip.hide);
        slice.addEventListener('click', () => {
          chartTooltip.hide();
          drill(pairs);
        });
        svg.append(slice);
        const text = number(count);
        if (length >= text.length * 4.6 + 6) {
          const angle = ((offset + length / 2) / circumference) * 2 * Math.PI - Math.PI / 2;
          const value = svgNode('text', {x: 60 + radius * Math.cos(angle), y: 60 + radius * Math.sin(angle),
            'text-anchor': 'middle', 'dominant-baseline': 'central', class: 'nq-domain-donut-value'});
          value.textContent = text;
          value.style.fill = readableText(color);
          // A small donut writes its values larger: those too long for their slice then wait for the hover.
          value.classList.toggle('is-tight', length < text.length * 6.4 + 6);
          values.push(value);
        }
        offset += length;
      });
      const centre = svgNode('text', {x: 60, y: 64, 'text-anchor': 'middle', class: 'nq-pie-total'});
      centre.textContent = number(row.total);
      svg.append(...values, centre);
      const card = node('div', undefined, 'nq-domain-donut');
      card.append(drillable(node('h4', label), [group], row.name), svg);
      return card;
    });
    container.replaceChildren(...(cards.length ? cards : [node('p', 'No data for this selection.', 'form-note')]));
  };
  const renderRootCauses = (stats) => {
    state.rootStats = stats;
    const summary = stats.summary;
    const source = ROOT_SOURCE_NAMES[stats.source] || ROOT_SOURCE_NAMES.analysts;
    // Without Not classified, the charts share the calls the source gives a root cause among their root domains.
    const showUnclassified = $('nq-root-show-unclassified').checked;
    const classified = (item) => showUnclassified || (item.value !== NOT_CLASSIFIED && item.domain !== NOT_CLASSIFIED);
    const columns = showUnclassified ? stats.columns : stats.columns.filter((column) => column !== NOT_CLASSIFIED);
    const groups = (rows, sorted = false) => {
      if (showUnclassified) return rows;
      const kept = rows.map((row) => ({...row, total: columns.reduce((sum, column) => sum + (row.counts[column] || 0), 0)}))
        .filter((row) => row.total);
      return sorted ? kept.sort((a, b) => b.total - a.total) : kept;
    };
    $('nq-root-kpis').replaceChildren(
      drillCard(kpiCard('Calls', number(summary.total), 'Selected Non-Qualified Calls', 'total'), {clear: ROOT_FILTERS}),
      stats.source === 'analysts'
        ? drillCard(kpiCard('Labelled', number(summary.labelled), `${percent(summary.labelled, summary.total)} have a root cause chosen by the analysts`, 'closed'), {pairs: [['state', 'labelled']]})
        : kpiCard('With a Root Cause', number(summary.labelled), `${percent(summary.labelled, summary.total)} mapped onto the catalog by ${source}`, 'closed'),
      drillCard(kpiCard(NOT_CLASSIFIED, number(summary.unclassified), `${percent(summary.unclassified, summary.total)} without a root cause from ${source}`, 'open'), {pairs: [domainPair(NOT_CLASSIFIED)]}),
    );
    $('nq-root-breakdowns').replaceChildren(
      staticBars('By Root Domain', stats.domains.filter(classified).map((item) => ({label: item.value, count: item.count, color: item.color,
        pairs: [domainPair(item.value)]}))),
      staticBars('By Root Category', (stats.categories || []).filter(classified).map((item) => ({label: `${item.domain} · ${item.category}`,
        count: item.count, color: item.color, pairs: categoryPairs(item.domain, item.value ?? '')}))),
      staticBars('By Root Cause', stats.causes.filter(classified).map((item) => ({label: `${item.domain} · ${item.cause}`, count: item.count,
        color: item.color, pairs: [causePair(item.domain, item.value ?? '')]}))),
    );
    const colors = Object.fromEntries(stats.domains.map((item) => [item.value, item.color]));
    domainLegend($('nq-root-donut-legend'), columns, colors);
    domainDonuts($('nq-root-call-types'), groups(stats.call_types), columns, colors, (name) => ['call_type', name]);
    domainDonuts($('nq-root-nr-modes'), groups(stats.nr_modes), columns, colors, (name) => ['nr_mode', name === 'Unknown' ? state.unassigned : name]);
    // Technologies are a filter of the Filters panel; calls without a technology cannot be selected there.
    domainBars($('nq-root-technologies'), groups(stats.technologies, true), columns, colors,
      (name) => (name === 'Unknown' ? null : ['technology', name]));
    statsTable($('nq-root-nodes'), ['eNB / gNB', 'Operator', 'Site', 'Host', 'Vendor', 'Calls', 'Main Domain'],
      stats.nodes.map((row) => [row.node, row.operator, row.site || '—', row.host || '—', row.vendor || '—', number(row.calls), row.top_domain || '—']),
      {drillRow: (index) => [['node', `${stats.nodes[index].operator}||${stats.nodes[index].node}`]]});
    // Only the call count is a number: the other columns are names.
    $('nq-root-nodes').querySelectorAll('tbody td.nq-number').forEach((cell) => {
      if (cell.cellIndex !== 5) cell.classList.remove('nq-number');
    });
  };
  $('nq-root-show-unclassified').addEventListener('change', () => { if (state.rootStats) renderRootCauses(state.rootStats); });
  let rootToken = 0;
  async function loadRootCauses() {
    const token = ++rootToken;
    try {
      const stats = await api('/api/non-qualified-calls/root-causes/stats', {
        method: 'POST', body: JSON.stringify({filters: currentFilters(), include_suggestions: false, source: state.rootSource}),
      });
      if (token === rootToken) renderRootCauses(stats);
    } catch (error) {
      if (token === rootToken) $('nq-root-kpis').replaceChildren(node('p', error.message, 'nq-muted'));
    }
  }
  $('nq-root-source').querySelectorAll('[data-nq-root-source]').forEach((tab) => tab.addEventListener('click', () => {
    state.rootSource = tab.dataset.nqRootSource;
    $('nq-root-source').querySelectorAll('[data-nq-root-source]').forEach((other) => {
      other.classList.toggle('is-active', other === tab);
      other.setAttribute('aria-selected', String(other === tab));
    });
    loadRootCauses();
  }));

  // -- lifecycle & phases (Analysis Center) ---------------------------------------------------
  // A Status Rule in words: "Analysis Status is Finished and Planned Status is not Planned".
  const conditionText = (condition) => {
    const label = state.conditionFields[condition.field]?.label || condition.field;
    const values = condition.values || [];
    if (condition.op === 'empty') return `${label} is empty`;
    if (condition.op === 'not_empty') return `${label} is not empty`;
    const verb = condition.op === 'not_in' ? (values.length > 1 ? 'is not one of' : 'is not') : (values.length > 1 ? 'is one of' : 'is');
    return `${label} ${verb} ${values.join(', ')}`;
  };
  // The calls that meet a Status Rule: each condition becomes the filter of its field.
  const CONDITION_FILTERS = {'@team': 'team', '@assignee': 'assignee', '@root_category': 'root_category', '@root_cause': 'root_cause'};
  const applyRuleFilters = (rule, index) => {
    rule.conditions.forEach((condition) => {
      if (condition.field === '@attended') {
        const value = condition.values.includes('Yes') === (condition.op === 'in') ? 'attended' : 'not_attended';
        const select = root.querySelector('[data-nq-filter="state"]');
        [...select.options].forEach((option) => { option.selected = option.value === value; });
        select.dispatchEvent(new Event('multiselect:options-updated'));
        return;
      }
      const select = root.querySelector(`[data-nq-filter="${CSS.escape(CONDITION_FILTERS[condition.field] || `field:${condition.field}`)}"]`);
      if (!select) return;
      const values = new Set(condition.values);
      [...select.options].forEach((option) => {
        const empty = option.value === state.unassigned;
        option.selected = condition.op === 'in' ? values.has(option.value) : condition.op === 'not_in' ? !values.has(option.value)
          : condition.op === 'empty' ? empty : !empty;
      });
      select.dispatchEvent(new Event('multiselect:options-updated'));
    });
    toast(`Showing the calls that meet rule ${index + 1}.`);
    scheduleLoad();
  };
  // What moves a call to a status: each rule as chips, the field name and its values in their colours.
  const ruleTriggers = (status, rules) => {
    const host = node('div', undefined, 'nq-triggers');
    rules.forEach((rule, index) => {
      if (rule.status !== status) return;
      const trigger = node('button', undefined, 'nq-trigger');
      trigger.type = 'button';
      trigger.title = `Rule ${index + 1} of the Status Rules (tried in this order): ${rule.conditions.map(conditionText).join(' and ')}.\n`
        + 'Click to show the calls that meet it.';
      trigger.addEventListener('click', (event) => {
        event.stopPropagation();
        applyRuleFilters(rule, index);
      });
      trigger.append(node('span', `Rule ${index + 1}`, 'nq-rule-number'));
      rule.conditions.forEach((condition, position) => {
        if (position) trigger.append(node('span', '+', 'nq-trigger-and'));
        const label = state.conditionFields[condition.field]?.label || condition.field;
        if (condition.field === '@attended') {
          trigger.append(node('span', condition.values.includes('No') && condition.op === 'in' ? 'Not attended' : 'Attended', 'nq-trigger-field'));
          return;
        }
        trigger.append(node('span', label, 'nq-trigger-field'));
        if (condition.op === 'empty' || condition.op === 'not_empty') {
          trigger.append(node('span', condition.op === 'empty' ? 'empty' : 'set', 'nq-trigger-op'));
          return;
        }
        if (condition.op === 'not_in') trigger.append(node('span', 'not', 'nq-trigger-op'));
        condition.values.forEach((value) => {
          const chip = node('span', value, 'nq-pill nq-trigger-value');
          paintPill(chip, conditionColor(condition.field, value));
          trigger.append(chip);
        });
      });
      host.append(trigger);
    });
    if (status === state.options.statuses[0]?.name) host.append(node('div', 'When no rule applies', 'nq-trigger is-fallback'));
    return host.childElementCount ? host : null;
  };
  // A bar split in the share of each value, in its colour.
  const stackedBar = (items, total) => {
    const bar = node('div', undefined, 'nq-stacked-bar');
    items.filter((item) => item.count).forEach((item) => {
      const part = node('span');
      part.style.flexGrow = String(item.count);
      part.style.background = item.color || '#d9cfd3';
      part.title = `${item.label}: ${number(item.count)} · ${percent(item.count, total)}`;
      bar.append(part);
    });
    if (!total) bar.classList.add('is-empty');
    return bar;
  };
  // A phase field with more values goes in a row of its own (as WIDE_PHASE_VALUES in the reports).
  const WIDE_PHASE_VALUES = 12;
  // The calls in the first status, in its colour: a click shows only them.
  const notAttendedCard = (waiting, total) => {
    const card = kpiCard(waiting.status, number(waiting.count), `${percent(waiting.count, total)} not followed up yet`);
    if (waiting.color) card.style.borderTopColor = waiting.color;
    return drillCard(card, {many: ['status', [waiting.status]]});
  };
  const renderLifecycle = (life) => {
    state.life = life;
    const total = life.total;
    const closed = life.pipeline.filter((item) => item.closed).reduce((sum, item) => sum + item.count, 0);
    $('nq-life-kpis').replaceChildren(
      drillCard(kpiCard('Calls', number(total), 'Selected Non-Qualified Calls', 'total'), {clear: ['status_mode']}),
      drillCard(kpiCard('Automatic Status', number(life.modes.auto), `${percent(life.modes.auto, total)} follow the Status Rules`, 'team'),
        {pairs: [['status_mode', 'auto']]}),
      drillCard(kpiCard('Status by Hand', number(life.modes.manual), `${percent(life.modes.manual, total)} chosen by an analyst`, 'commented'),
        {pairs: [['status_mode', 'manual']]}),
      ...(life.not_attended ? [notAttendedCard(life.not_attended, total)] : []),
      drillCard(kpiCard('Open', number(life.open), `${percent(life.open, total)} attended and not closed`, 'open'),
        {pairs: [['state', 'open']]}),
      drillCard(kpiCard('Closed', number(closed), `${percent(closed, total)} closed`, 'closed'), {pairs: [['state', 'closed']]}),
      drillCard(kpiCard('Stalled', number(life.stalled_total), `Open, no change for ${life.stalled_days}+ days`, 'attended'),
        {pairs: [['state', 'stalled']]}),
    );
    // The pipeline: the calls not attended, Open (the phase statuses an attended call goes through, its total being
    // theirs), then the closed statuses.
    const steps = [...life.pipeline.filter((item) => !item.closed), ...life.pipeline.filter((item) => item.closed)];
    const pipeline = $('nq-life-pipeline');
    pipeline.replaceChildren(stackedBar(steps.map((item) => ({label: item.status, count: item.count, color: item.color})), total));
    const flow = node('div', undefined, 'nq-pipeline-steps');
    const openNames = life.open_statuses || [];
    let group = null;
    steps.forEach((item, index) => {
      const inOpen = openNames.includes(item.status);
      if (inOpen && !group) {
        flow.append(node('span', '→', 'nq-pipeline-arrow'));
        group = node('div', undefined, 'nq-pipeline-group');
        const head = drillCard(node('div', undefined, 'nq-pipeline-group-head'), {pairs: [['state', 'open']]});
        head.append(node('span', 'Open', 'nq-pipeline-name'), node('strong', number(life.open)),
          node('span', `${percent(life.open, total)} · attended and not closed: ${openNames.join(' + ')}`, 'nq-kpi-note'));
        group.append(head, node('div', undefined, 'nq-pipeline-group-steps'));
        flow.append(group);
      }
      const host = inOpen ? group.lastChild : flow;
      if (index && !item.closed && (!inOpen || host.childElementCount)) host.append(node('span', '→', 'nq-pipeline-arrow'));
      if (item.closed && !steps[index - 1]?.closed && index) flow.append(node('span', '⇒', 'nq-pipeline-arrow is-closing'));
      const step = node('button', undefined, `nq-pipeline-step${item.closed ? ' is-closed' : ''}`);
      step.type = 'button';
      step.style.setProperty('--nq-step', item.color || '#b8c0c6');
      const filters = currentFilters();
      step.classList.toggle('is-active', (filters.status || []).length === 1 && filters.status[0] === item.status);
      // The status, its calls and their age, as tall in every card, so that the rules start on one line.
      const top = node('div', undefined, 'nq-pipeline-head');
      top.append(node('span', item.status, 'nq-pipeline-name'), node('strong', number(item.count)),
        node('span', `${percent(item.count, total)}${item.avg_age_days === null ? '' : ` · ${item.avg_age_days} d old on average`}`, 'nq-kpi-note'));
      step.append(top);
      const triggers = ruleTriggers(item.status, life.rules || []);
      if (triggers) step.append(triggers);
      step.title = `Show only the calls ${item.status}`;
      step.addEventListener('click', () => selectOnly('status', item.status));
      host.append(step);
    });
    pipeline.append(flow);
    // RCA Identification, then one card per phase field: how its values split the calls.
    const rcaPhase = life.rca && state.sections.some((section) => section.key === 'rca') ? [{
      key: '', label: 'RCA Identification', section: 'rca', empty: 0, drill: 'state',
      items: [{value: 'Identified', count: life.rca.identified, color: '#2e8b57', filter: 'identified'},
        {value: 'Not identified', count: life.rca.not_identified, color: '#e7dde1', filter: 'not_identified'}],
    }] : [];
    // Every phase card in one row; a field with many values goes below, across the panel, its values in columns from
    // the most frequent.
    const phases = [...rcaPhase, ...life.phases];
    const isWide = (phase) => phase.items.length > WIDE_PHASE_VALUES;
    $('nq-life-phases').style.setProperty('--nq-phase-count', String(phases.filter((phase) => !isWide(phase)).length || 1));
    $('nq-life-phases').replaceChildren(...[...phases.filter((phase) => !isWide(phase)), ...phases.filter(isWide)].map((phase) => {
      const section = sectionOf(phase.section);
      const card = node('section', undefined, `nq-phase-card${isWide(phase) ? ' is-wide' : ''}`);
      card.style.setProperty('--nq-section', section.color);
      const head = node('header');
      head.append(sectionTag(phase.section), node('h3', phase.label));
      // Without Empty, the values share the calls that have one.
      const showEmpty = $('nq-life-show-empty').checked;
      // The values of a wide card from the most frequent, each in the colour of its value.
      const values = isWide(phase) ? [...phase.items].sort((one, other) => other.count - one.count) : phase.items;
      const items = phase.drill ? values.map((item) => ({label: item.value, value: item.filter, count: item.count, color: item.color}))
        : [...values.map((item) => ({label: item.value, value: item.value, count: item.count, color: item.color})),
          ...(showEmpty ? [{label: 'Empty', value: '', count: phase.empty, color: '#e7dde1'}] : [])];
      const base = phase.drill || showEmpty ? total : items.reduce((sum, item) => sum + item.count, 0);
      if (base !== total) head.append(node('span', `${number(base)} of ${number(total)} calls with a value`, 'nq-muted nq-phase-base'));
      const field = phase.drill || `field:${phase.key}`;
      const rows = node('div', undefined, 'nq-phase-values');
      items.forEach((item) => {
        const pairs = [[field, item.value || state.unassigned]];
        const row = node('button', undefined, 'nq-phase-value');
        row.type = 'button';
        row.classList.toggle('is-active', isDrilled(pairs));
        const swatch = node('span', '', 'nq-swatch');
        swatch.style.background = item.color || '#d9cfd3';
        row.append(swatch, node('span', item.label, 'nq-bar-label'), node('strong', number(item.count)),
          node('span', percent(item.count, base), 'nq-muted'));
        row.title = `Show only the calls with ${phase.label}: ${item.label}`;
        row.addEventListener('click', () => drill(pairs));
        rows.append(row);
      });
      card.append(head, stackedBar(items, base), rows);
      return card;
    }));
    if (!life.phases.length) $('nq-life-phases').append(node('p', 'No list field in the Analysis, Implementation or Planning sections.', 'nq-muted'));
    statsTable($('nq-life-times'), ['Status', 'Average Days', 'Calls Moved Out'],
      life.time_in_status.map((item) => [item.status, item.avg_days.toFixed(1), number(item.moves)]),
      {drillRow: (index) => [['status', life.time_in_status[index].status]]});
    statsTable($('nq-life-moves'), ['From', 'To', 'Times'], life.moves.map((item) => [item.from, item.to, number(item.count)]));
    $('nq-life-moves').querySelectorAll('tbody td:nth-child(2)').forEach((cell) => cell.classList.remove('nq-number'));
    $('nq-life-stalled-title').textContent = `Stalled Open Calls · no change for ${life.stalled_days}+ days (${number(life.stalled_total)})`;
    statsTable($('nq-life-stalled'), ['Status', 'Operator', 'Campaign', 'City', 'Days Without Change', 'Followed Up'],
      life.stalled.map((item) => [item.status, item.operator || '—', campaignLabel(item.campaign) || '—', item.city || '—',
        number(item.days), item.followed_up ? 'Yes' : 'Not yet']));
    // Each stalled call opens on a click.
    [...$('nq-life-stalled').tBodies[0].rows].forEach((row, index) => {
      const item = life.stalled[index];
      if (!item) return;
      [...row.cells].forEach((cell, position) => { if (position && position !== 4) cell.classList.remove('nq-number'); });
      row.classList.add('nq-drill-row');
      row.tabIndex = 0;
      row.title = 'Open this call';
      row.addEventListener('click', () => openDetail(item.call_key));
      row.addEventListener('keydown', (event) => { if (event.key === 'Enter') openDetail(item.call_key); });
    });
  };
  $('nq-life-show-empty').addEventListener('change', () => { if (state.life) renderLifecycle(state.life); });
  let lifeToken = 0;
  async function loadLifecycle() {
    const token = ++lifeToken;
    try {
      const life = await api('/api/non-qualified-calls/lifecycle', {method: 'POST', body: JSON.stringify({filters: currentFilters()})});
      if (token === lifeToken) renderLifecycle(life);
    } catch (error) {
      if (token === lifeToken) $('nq-life-kpis').replaceChildren(node('p', error.message, 'nq-muted'));
    }
  }

  // -- root cause sources (Analysis Center) ---------------------------------------------------
  // A category → cause tree of one source (selected: the analysts' choices): a category, a cause or the root domain of a
  // category filters the calls; those of an RCA source by its own category or category·cause and its root domain.
  const hierarchyCard = (title, note, groups, source) => {
    const selected = source === 'selected';
    const card = node('section', undefined, 'nq-breakdown nq-hierarchy');
    card.append(node('h3', title), node('p', note, 'nq-muted nq-hierarchy-note'));
    const max = Math.max(1, ...groups.map((group) => group.count));
    if (!groups.length) card.append(node('p', 'No calls.', 'form-note'));
    const domainField = selected ? 'root_domain' : `${source}_domain`;
    groups.forEach((group) => {
      const category = group.category === '—' ? '' : group.category;
      const color = selected ? optionColor('root_category', category) : '';
      const pairs = selected ? [['root_category', category || state.unassigned]] : [[`${source}_raw`, category]];
      card.append(hierarchyRow(group.category === '—' ? (selected ? NOT_CLASSIFIED : 'No category') : group.category,
        group.count, max, color, pairs, 'is-category', group.domains || [], domainField));
      group.causes.forEach((item) => {
        const cause = item.cause === '—' ? '' : item.cause;
        const causePairs = selected ? [...pairs, ['root_cause', cause || state.unassigned]] : [[`${source}_raw`, `${category}||${cause}`]];
        card.append(hierarchyRow(item.cause === '—' ? NO_CAUSE : item.cause, item.count, max, color, causePairs, 'is-cause'));
      });
    });
    return card;
  };
  const hierarchyRow = (label, count, max, color, pairs, kind, domains = [], domainField = '') => {
    const row = node(pairs ? 'button' : 'div', undefined, `nq-bar nq-hierarchy-row ${kind}${pairs ? '' : ' nq-static-bar'}`);
    if (pairs) {
      row.type = 'button';
      row.classList.toggle('is-active', isDrilled(pairs));
      row.addEventListener('click', () => drill(pairs));
      row.title = `${label}: show only these calls; click again to remove the filter`;
    } else {
      row.title = label;
    }
    const track = node('span', undefined, 'nq-bar-track');
    const fill = node('span', undefined, 'nq-bar-fill');
    fill.style.width = `${Math.max(2, (count / max) * 100)}%`;
    if (color) fill.style.background = color;
    track.append(fill);
    const name = node('span', undefined, 'nq-bar-label nq-hierarchy-label');
    name.append(node('span', label, 'nq-hierarchy-name'));
    // The root domain the calls of a category fall in, in its colour; when they fall in several, the main one and how
    // many more, all of them on hover.
    if (domains.length) {
      const tag = node('span', domains.length > 1 ? `${domains[0].domain} +${domains.length - 1}` : domains[0].domain, 'nq-category-domain');
      tag.style.background = domains[0].color || '#b8c0c6';
      tag.style.color = readableText(domains[0].color || '#b8c0c6');
      tag.title = `Root domain: ${domains.map((item) => `${item.domain} ${number(item.count)}`).join(' · ')}`;
      // The tag filters the calls of its root domain (the main one); inside a row button it is not a button itself.
      if (domainField && domains[0].domain !== NOT_CLASSIFIED) {
        const domainPairs = [[domainField, domains[0].domain]];
        tag.classList.add('is-drill');
        tag.classList.toggle('is-active', isDrilled(domainPairs));
        tag.setAttribute('role', 'button');
        tag.tabIndex = 0;
        tag.title += ` · click: show only the calls of ${domains[0].domain}; again to remove the filter`;
        const act = (event) => { event.preventDefault(); event.stopPropagation(); drill(domainPairs); };
        tag.addEventListener('click', act);
        tag.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') act(event); });
      }
      name.append(tag);
    }
    row.append(name, track, node('span', number(count), 'nq-bar-count'));
    return row;
  };
  // How the categories one RCA source maps to relate to the Root Categories the analysts selected.
  const MATRIX_SOURCES = {dta: 'DT Analyzer RCA', netcheck: PROVIDER_RCA, script: 'Ericsson RCA'};
  const renderMatrix = (insights) => {
    const matrix = insights.confusion[state.matrixSource] || {rows: [], columns: [], cells: []};
    const tabs = $('nq-sources-matrix-tabs');
    tabs.replaceChildren(...Object.entries(MATRIX_SOURCES).map(([source, label]) => {
      const tab = node('button', label, 'nq-rate-tab');
      tab.type = 'button';
      tab.setAttribute('role', 'tab');
      tab.setAttribute('aria-selected', String(source === state.matrixSource));
      tab.classList.toggle('is-active', source === state.matrixSource);
      tab.addEventListener('click', () => { state.matrixSource = source; renderMatrix(insights); });
      return tab;
    }));
    const table = $('nq-sources-matrix');
    const head = node('thead');
    const headRow = node('tr');
    headRow.append(node('th', `${MATRIX_SOURCES[state.matrixSource] || 'DT Analyzer RCA'} ↓ · Selected →`));
    matrix.columns.forEach((column) => headRow.append(node('th', column)));
    head.append(headRow);
    const body = node('tbody');
    const highest = Math.max(1, ...matrix.cells.flat());
    matrix.rows.forEach((name, rowIndex) => {
      const row = node('tr');
      row.append(node('th', name));
      matrix.columns.forEach((column, columnIndex) => {
        const count = matrix.cells[rowIndex][columnIndex];
        const cell = node('td', count ? number(count) : '·', `nq-number nq-matrix-cell${name === column ? ' is-match' : ''}`);
        if (count) cell.style.background = heat(count, highest)[0];
        cell.title = `${name} → ${column}: ${number(count)} calls${name === column ? ' (the analysts agree)' : ''}`;
        row.append(cell);
      });
      body.append(row);
    });
    if (!matrix.rows.length) {
      const row = node('tr');
      const cell = node('td', 'No call has both a proposal of this source and a selected root category yet.', 'nq-empty');
      cell.colSpan = Math.max(2, matrix.columns.length + 1);
      row.append(cell);
      body.append(row);
    }
    table.replaceChildren(head, body);
  };
  const renderSources = (insights) => {
    const {coverage, agreement} = insights;
    const results = insights.rca_results || {};
    $('nq-sources-results').textContent = results.total
      ? `${number(results.total)} Ericsson RCA results · ${number(results.matched)} match calls` : 'No Ericsson RCA results imported yet';
    const rate = (item) => (item.rate === null ? '—' : `${item.rate.toFixed(1)}%`);
    // Three lines: the calls each source covers, the analysts' choices and how each RCA agrees with them, and how each pair of
    // RCAs agrees; the DT Analyzer RCA first, then the RCA of the CDR and the Ericsson RCA.
    const line = (...cards) => {
      const row = node('div', undefined, 'nq-kpis');
      row.append(...cards);
      return row;
    };
    $('nq-sources-kpis').replaceChildren(line(
      kpiCard('Calls', number(coverage.total), 'Selected Non-Qualified Calls', 'total'),
      kpiCard('DT Analyzer RCA', number(coverage.dta), `${percent(coverage.dta, coverage.total)} calculated from the data of the CDR`, 'dta'),
      kpiCard(PROVIDER_RCA, number(coverage.netcheck), `${percent(coverage.netcheck, coverage.total)} classified by ${PROVIDER_NAME}`, 'team'),
      kpiCard('Ericsson RCA', number(coverage.script), `${percent(coverage.script, coverage.total)} have Ericsson RCA results`, 'attended'),
    ), line(
      kpiCard('Selected Cause', number(coverage.selected), `${percent(coverage.selected, coverage.total)} have a root category or cause`, 'closed'),
      kpiCard('Selected Cause ↔ DT Analyzer RCA', rate(agreement.selected_dta), `${number(agreement.selected_dta.agree)} of ${number(agreement.selected_dta.compared)} calls agree`, 'commented'),
      kpiCard(`Selected Cause ↔ ${PROVIDER_RCA}`, rate(agreement.selected_netcheck), `${number(agreement.selected_netcheck.agree)} of ${number(agreement.selected_netcheck.compared)} calls agree`, 'commented'),
      kpiCard('Selected Cause ↔ Ericsson RCA', rate(agreement.selected_script), `${number(agreement.selected_script.agree)} of ${number(agreement.selected_script.compared)} calls agree`, 'commented'),
    ), line(
      kpiCard(`DT Analyzer RCA ↔ ${PROVIDER_RCA}`, rate(agreement.netcheck_dta), `${number(agreement.netcheck_dta.agree)} of ${number(agreement.netcheck_dta.compared)} calls agree`, 'open'),
      kpiCard('DT Analyzer RCA ↔ Ericsson RCA', rate(agreement.script_dta), `${number(agreement.script_dta.agree)} of ${number(agreement.script_dta.compared)} calls agree`, 'open'),
      kpiCard(`${PROVIDER_RCA} ↔ Ericsson RCA`, rate(agreement.netcheck_script), `${number(agreement.netcheck_script.agree)} of ${number(agreement.netcheck_script.compared)} calls agree`, 'open'),
    ));
    $('nq-sources-hierarchies').replaceChildren(
      hierarchyCard('DT Analyzer RCA → Root Cause', 'Root Category → Root Cause it finds from the data of the CDR; click to drill down', insights.hierarchies.dta, 'dta'),
      hierarchyCard(`${PROVIDER_RCA} → Root Cause`, 'Failure Category → Subcategory of the CDR; click to drill down', insights.hierarchies.netcheck, 'netcheck'),
      hierarchyCard('Ericsson RCA → Root Cause', 'Suggested Category → Cause of the Ericsson RCA; click to drill down', insights.hierarchies.script, 'script'),
      hierarchyCard('Selected Root Cause', 'Root Category → Root Cause the analysts chose; click to drill down', insights.hierarchies.selected, 'selected'),
    );
    // What each source proposes translated onto the Root Cause Catalog; a category shows the calls the source puts in it.
    const catalogCard = (title, note, source, filter) => {
      const items = insights.mapped[source] || [];
      const card = node('section', undefined, 'nq-breakdown nq-hierarchy');
      card.append(node('h3', title), node('p', note, 'nq-muted nq-hierarchy-note'));
      if (!items.length) card.append(node('p', 'No calls.', 'form-note'));
      const max = Math.max(1, ...items.map((item) => item.count));
      items.forEach((item) => {
        const known = item.category !== '—';
        const domain = item.domains?.[0]?.domain;
        const pairs = !known ? null : source === 'selected' ? [[filter, item.category]]
          : (domain && domain !== NOT_CLASSIFIED ? [[filter, `${domain}||${item.category}`]] : null);
        card.append(hierarchyRow(known ? item.category : (source === 'selected' ? 'No category' : 'No catalog category'),
          item.count, max, '', pairs, 'is-category', item.domains || []));
      });
      return card;
    };
    $('nq-sources-catalog').replaceChildren(
      catalogCard('DT Analyzer RCA → Root Category', 'The Root Category it finds from the data of the CDR', 'dta', 'dta_category'),
      catalogCard(`${PROVIDER_RCA} → Root Category`, 'Its categories translated onto the Root Cause Catalog', 'netcheck', 'netcheck_category'),
      catalogCard('Ericsson RCA → Root Category', 'Its categories translated onto the Root Cause Catalog', 'script', 'script_category'),
      catalogCard('Selected Root Category', 'The Root Category the analysts chose', 'selected', 'root_category'),
    );
    // The root domains of each source above its hierarchy: a domain shows the calls the source puts in it. The values of
    // the NetCheck RCA or the Ericsson RCA that map onto no domain are Not classified, which their filters cannot tell
    // from the calls without values.
    const domainCard = (title, note, source, filter) => {
      const card = staticBars(title, (insights.domains[source] || []).map((item) => ({
        label: item.domain, count: item.count, color: item.color,
        pairs: item.domain !== NOT_CLASSIFIED ? [[filter, item.domain]] : source === 'selected' ? [[filter, state.unassigned]] : null,
      })));
      card.querySelector('h3').after(node('p', note, 'nq-muted nq-hierarchy-note'));
      return card;
    };
    $('nq-sources-domains').replaceChildren(
      domainCard('DT Analyzer RCA → Root Domain', 'The root domain it finds from the data of the CDR', 'dta', 'dta_domain'),
      domainCard(`${PROVIDER_RCA} → Root Domain`, 'Its categories translated onto the root domains of the catalog', 'netcheck', 'netcheck_domain'),
      domainCard('Ericsson RCA → Root Domain', 'Its categories translated onto the root domains of the catalog', 'script', 'script_domain'),
      domainCard('Selected Root Domain', 'The root domain of the category the analysts chose', 'selected', 'root_domain'),
    );
    renderMatrix(insights);
  };
  let sourcesToken = 0;
  async function loadSources() {
    const token = ++sourcesToken;
    try {
      const insights = await api('/api/non-qualified-calls/rca/insights', {method: 'POST', body: JSON.stringify({filters: currentFilters()})});
      if (token === sourcesToken) renderSources(insights);
    } catch (error) {
      if (token === sourcesToken) $('nq-sources-kpis').replaceChildren(node('p', error.message, 'nq-muted'));
    }
  }

  // What is out of scope, beside NQ Calls in Scope Only: the regions, the operators chosen with their NR Mode and the
  // operators that are not Focus operators.
  function renderScopeSummary() {
    const summary = $('nq-scope-summary');
    if (!summary) return;
    const settings = state.prioritization || {};
    const fixed = [...new Set((state.prioritizationFixedModes || []).map((item) => item.operator))];
    // Each operator out of scope with its NR Mode, or alone when both are.
    const modes = new Map();
    (settings.excluded_modes || []).forEach((item) => modes.set(item.operator, [...(modes.get(item.operator) || []), item.nr_mode]));
    const parts = [...(settings.excluded_regions || []), ...[...modes].map(([name, nrModes]) => (nrModes.length > 1 ? name : `${name} (${nrModes[0]})`)),
      ...(fixed.length ? [`not Focus: ${fixed.join(', ')}`] : [])];
    summary.textContent = parts.length ? `Out of scope: ${parts.join(' · ')}` : 'Nothing is out of scope';
  }
  async function loadState() {
    try {
      const payload = await api('/api/non-qualified-calls/state');
      state.options = payload.options;
      state.rootCauses = payload.root_causes || state.rootCauses;
      state.rootCauseDefaults = payload.root_cause_defaults || {domains: [], categories: [], causes: []};
      state.ruleFields = payload.root_cause_rule_fields || {};
      state.defaultRule = payload.default_root_cause_rule || null;
      state.users = payload.users || [];
      state.userNames = payload.user_names || {};
      state.defaultUsers = payload.default_users || [];
      state.user = payload.user;
      state.unassigned = payload.unassigned || state.unassigned;
      state.datasets = payload.datasets || [];
      state.mainCities = payload.main_cities || [];
      state.fields = payload.fields || [];
      state.defaultFields = payload.default_fields || [];
      state.fieldTypes = payload.field_types || {};
      state.fieldSources = payload.field_sources || {};
      state.trackingRefs = payload.tracking_refs || {};
      state.rcaRefs = payload.rca_refs || {};
      state.dtaRefs = payload.dta_refs || {};
      state.dtaRca = payload.dta_rca || {};
      state.priorityRefs = payload.priority_refs || {};
      state.priorityTypes = payload.priority_types || {};
      state.prioritization = payload.prioritization || null;
      state.defaultPrioritization = payload.default_prioritization || null;
      state.prioritizationStrategies = payload.prioritization_strategies || {};
      state.prioritizationSteps = payload.prioritization_steps || {};
      state.prioritizationStepOperators = payload.prioritization_step_operators || {};
      state.prioritizationFields = payload.prioritization_fields || {};
      state.focusOperators = payload.focus_operators || [];
      state.prioritizationOperators = payload.prioritization_operators || [];
      state.prioritizationFixedModes = payload.prioritization_fixed_modes || [];
      state.prioritizationFixedReason = payload.prioritization_fixed_reason || '';
      state.prioritizationMapModes = payload.prioritization_map_modes || [];
      state.prioritizationMapReason = payload.prioritization_map_reason || '';
      state.prioritizationRegions = payload.prioritization_regions || [];
      renderScopeSummary();
      state.priorityOptions = payload.priority_options || [];
      state.callFields = payload.call_fields || [];
      state.sections = payload.sections || [];
      state.defaultSections = payload.default_sections || [];
      state.statusRules = payload.status_rules || [];
      state.defaultStatusRules = payload.default_status_rules || [];
      state.defaultOptions = payload.default_options || {statuses: [], teams: []};
      state.ruleOperators = payload.rule_operators || {};
      state.conditionFields = payload.condition_fields || {};
      state.rcaResults = payload.rca_results || {};
      state.callSection = payload.call_section || null;
      state.valueFilterFields = payload.value_filter_fields || [];
      state.rcaSources = payload.rca_sources || {};
      buildDrawerTabs();
      state.tableColumns = payload.table_columns || {builtin: [], cdr: []};
      applyLayouts(payload.table_layout);
      if (!browserOrderMoved) await moveBrowserOrder();
      state.optionalColumns = payload.optional_columns || {};
      state.cdrColumns = payload.cdr_columns || [];
      state.maxCdrColumns = payload.max_cdr_columns || 12;
      state.versionLabels = payload.version_labels || {};
      renderDynamicHeaders();
      renderSync(payload.sync);
      fillFilters(payload);
      if (!state.filtersRestored) {
        state.filtersRestored = true;
        applySavedFilters(payload.saved_filters || {});
        // Filters saved before NR Mode cleared the campaigns of the other mode lose them now.
        const nrModeSelect = root.querySelector('[data-nq-filter="nr_mode"]');
        if (nrModeSelect) window.setTimeout(() => { void keepCampaignsOfNrMode(nrModeSelect); }, 0);
      }
      fillBulkSelects();
      if ($('nq-bulk-history')) $('nq-bulk-history').hidden = !state.user.can_moderate;
      await loadCalls();
    } catch (error) {
      $('nq-sync').textContent = error.message;
      $('nq-count').textContent = error.message;
    }
  }

  // -- NQ rate by campaign and operator -------------------------------------------------
  // A pastel colour from soft mint (no NQ calls) through apricot to dusty rose (the highest rate of the matrix).
  const heat = (rate, highest) => {
    if (rate === null || rate === undefined) return ['#f7f2f4', 'var(--nq-muted)'];
    const share = highest > 0 ? Math.min(1, rate / highest) : 0;
    const low = [0xee, 0xf6, 0xef];
    const mid = [0xfb, 0xe0, 0xbd];
    const high = [0xeb, 0x95, 0xaa];
    const [start, end, step] = share < 0.5 ? [low, mid, share * 2] : [mid, high, (share - 0.5) * 2];
    const rgb = start.map((value, index) => Math.round(value + (end[index] - value) * step));
    const luminance = (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255;
    return [`rgb(${rgb.join(', ')})`, luminance < 0.55 ? '#fff' : '#3d1824'];
  };
  const rateText = (cell) => (cell && cell.rate !== null && cell.rate !== undefined ? `${Number(cell.rate).toFixed(1)}%` : '—');
  const renderRates = (rates) => {
    const matrices = rates.matrices || [];
    const tabs = $('nq-rate-tabs');
    if (!matrices.some((matrix) => matrix.service === state.rateService)) {
      state.rateService = (matrices.find((matrix) => matrix.service === 'voice') || matrices[0])?.service || '';
    }
    tabs.replaceChildren(...matrices.map((matrix) => {
      const tab = node('button', matrix.label, 'nq-rate-tab');
      tab.type = 'button';
      tab.setAttribute('role', 'tab');
      tab.setAttribute('aria-selected', String(matrix.service === state.rateService));
      tab.classList.toggle('is-active', matrix.service === state.rateService);
      tab.addEventListener('click', () => { state.rateService = matrix.service; renderRates(rates); });
      return tab;
    }));
    const matrix = matrices.find((item) => item.service === state.rateService);
    const table = $('nq-rate-table');
    if (!matrix || !matrix.campaigns.length) {
      $('nq-rate-overview').replaceChildren(node('p', 'No calls for this selection.', 'nq-muted'));
      table.replaceChildren();
      $('nq-rate-legend').replaceChildren();
      return;
    }
    const total = matrix.total;
    const operatorCards = matrix.operators.map((operator) => {
      const cell = matrix.operator_totals[operator];
      const card = node('article', undefined, 'nq-rate-card');
      // The operator's name in its Operator Maps colour.
      const label = node('span', operator, 'nq-rate-operator');
      if (matrix.operator_colors?.[operator]) label.style.color = matrix.operator_colors[operator];
      card.append(label, node('strong', rateText(cell)),
        node('span', `${number(cell?.nq)} of ${number(cell?.total)} calls`, 'nq-kpi-note'));
      const meter = node('span', undefined, 'nq-rate-meter');
      const fill = node('span');
      fill.style.width = `${Math.min(100, Number(cell?.rate || 0) * (100 / Math.max(1, ...matrix.operators.map((name) => Number(matrix.operator_totals[name]?.rate || 0)))))}%`;
      fill.style.background = heat(cell?.rate, Math.max(...matrix.operators.map((name) => Number(matrix.operator_totals[name]?.rate || 0))))[0];
      meter.append(fill);
      card.append(meter);
      return drillCard(card, {pairs: [['operator', operator]]});
    });
    const overall = node('article', undefined, 'nq-rate-card nq-rate-card-total');
    overall.append(node('span', 'Overall', 'nq-rate-operator'), node('strong', rateText(total)),
      node('span', `${number(total.nq)} Non-Qualified of ${number(total.total)} calls`, 'nq-kpi-note'));
    $('nq-rate-overview').replaceChildren(overall, ...operatorCards);
    const highest = Math.max(0, ...matrix.campaigns.flatMap((campaign) => Object.values(matrix.cells[campaign] || {}).map((cell) => Number(cell.rate || 0))));
    const head = node('thead');
    const headRow = node('tr');
    // Each operator with the bar of its Operator Maps colour below its name, as in the documents.
    const operatorHead = (operator) => {
      const cell = node('th', operator);
      const color = matrix.operator_colors?.[operator];
      if (color) {
        const bar = node('span', '', 'nq-rate-operator-bar');
        bar.style.background = color;
        cell.append(bar);
      }
      return cell;
    };
    headRow.append(node('th', 'Campaign', 'nq-rate-strong-head'), ...matrix.operators.map(operatorHead), node('th', 'Total', 'nq-rate-strong-head'));
    head.append(headRow);
    const body = node('tbody');
    const cellOf = (cell, pairs, title, isTotal = false) => {
      const td = node('td', undefined, `nq-rate-cell${isTotal ? ' is-total' : ''}`);
      const [fill, ink] = heat(cell?.rate, highest);
      const box = node(pairs ? 'button' : 'div', undefined, 'nq-rate-box');
      if (pairs) {
        box.type = 'button';
        box.classList.toggle('is-active', isDrilled(pairs));
        box.addEventListener('click', () => drill(pairs));
      }
      box.style.background = isTotal ? '' : fill;
      box.style.color = isTotal ? '' : ink;
      box.append(node('strong', rateText(cell)), node('span', cell ? `${number(cell.nq)} / ${number(cell.total)}` : 'No calls'));
      box.title = cell ? `${title}: ${number(cell.nq)} Non-Qualified of ${number(cell.total)} calls (${rateText(cell)})` : `${title}: no calls`;
      td.append(box);
      return td;
    };
    matrix.campaigns.forEach((campaign) => {
      const row = node('tr');
      row.append(node('th', campaignLabel(campaign), 'nq-rate-campaign'));
      matrix.operators.forEach((operator) => {
        const cell = matrix.cells[campaign]?.[operator];
        row.append(cellOf(cell, cell ? [['campaign', campaign], ['operator', operator]] : null, `${campaignLabel(campaign)} · ${operator}`));
      });
      row.append(cellOf(matrix.campaign_totals[campaign], [['campaign', campaign]], campaignLabel(campaign), true));
      body.append(row);
    });
    const totals = node('tr', undefined, 'nq-rate-totals');
    totals.append(node('th', 'Total'), ...matrix.operators.map((operator) => cellOf(matrix.operator_totals[operator],
      [['operator', operator]], operator, true)), cellOf(total, null, 'Every call', true));
    body.append(totals);
    table.replaceChildren(head, body);
    const legend = $('nq-rate-legend');
    const scale = node('span', undefined, 'nq-rate-scale');
    scale.style.background = `linear-gradient(90deg, ${heat(0, 1)[0]}, ${heat(0.5, 1)[0]}, ${heat(1, 1)[0]})`;
    legend.replaceChildren(node('span', '0%'), scale, node('span', `${highest.toFixed(1)}% (highest of the table)`),
      node('span', 'Each cell: NQ rate · Non-Qualified / all calls', 'nq-muted'));
  };
  let rateToken = 0;
  // The NQ rate depends only on these filters and on the indexed CDRs: other filter changes keep it.
  const RATE_FILTER_KEYS = ['datasets', 'service', 'campaign', 'operator', 'nr_mode'];
  let rateKey = '';
  // NQ Maps: the Layer 3 - DT Logs of the filtered calls (nq_call_map.js mountArea), mounted when first shown and read
  // again when the filters or the calls change.
  let l3Maps = null, l3MapsKey = '';
  async function loadL3Maps() {
    const host = $('nq-l3-maps');
    if (!host || !window.NqCallMap?.mountArea) return;
    l3Maps = l3Maps || window.NqCallMap.mountArea({panel: host, expandDialog: $('nq-l3-maps-expand'), api, toast, number, campaignLabel, cdrTime,
      filters: () => currentFilters(), openCall: async (callKey) => { if (await leaveDetail()) openDetail(callKey, {keepTab: false}); }});
    const key = JSON.stringify([currentFilters(), state.result?.sync?.synced_at || '']);
    if (key === l3MapsKey) return;
    l3MapsKey = key;
    l3Maps.load();
  }

  async function loadRates() {
    const filters = currentFilters();
    const rateFilters = Object.fromEntries(RATE_FILTER_KEYS.filter((key) => key in filters).map((key) => [key, filters[key]]));
    const key = JSON.stringify([rateFilters, state.result?.sync?.synced_at || '']);
    if (key === rateKey) return;
    rateKey = key;
    const token = ++rateToken;
    try {
      const rates = await api('/api/non-qualified-calls/rates', {method: 'POST', body: JSON.stringify({filters: rateFilters})});
      if (token === rateToken) renderRates(rates);
    } catch (error) {
      if (token === rateToken) {
        rateKey = '';
        $('nq-rate-overview').replaceChildren(node('p', error.message, 'nq-muted'));
      }
    }
  }

  // -- failures by type, technology and serving cell ------------------------------
  // A table of the panel: its headers and rows of cells ({text, title, pairs, heat: [value, highest], className}).
  const failureTable = (headers, rows) => {
    const table = node('table', undefined, 'nq-failure-table');
    const head = node('thead');
    const headRow = node('tr');
    headRow.append(...headers.map((text) => node('th', text)));
    head.append(headRow);
    const body = node('tbody');
    for (const cells of rows) {
      const row = node('tr');
      for (const cell of cells) {
        const item = cell && typeof cell === 'object' ? cell : {text: cell};
        const td = node('td', undefined, item.className || '');
        const content = item.node || (item.pairs || item.action ? node('button', item.text, 'nq-failure-drill') : node('span', item.text));
        if (item.pairs) {
          content.type = 'button';
          content.classList.toggle('is-active', isDrilled(item.pairs));
          content.addEventListener('click', () => {
            // A drill that also takes to a panel (``reveal``, the calls of a group) goes there when it applies its filter.
            const applying = !isDrilled(item.pairs);
            drill(item.pairs);
            if (!item.reveal || !applying) return;
            if (window.location.hash === `#${item.reveal}`) window.openMappingHashTarget?.();
            else window.location.hash = item.reveal;
          });
        } else if (item.action) {
          content.type = 'button';
          content.addEventListener('click', item.action);
        }
        if (item.color) td.style.setProperty('--nq-chip', item.color);
        if (item.heat && item.heat[1]) {
          const [fill, ink] = heat(item.heat[0], item.heat[1]);
          td.style.background = fill;
          td.style.color = ink;
        }
        if (item.title) td.title = item.title;
        // What the Excel-style column filters of the table read: a value, several (the row matches by any) or a day.
        if (item.filterValue !== undefined) td.dataset.filterValue = item.filterValue;
        if (item.filterValues) td.dataset.filterValues = JSON.stringify(item.filterValues);
        if (item.filterDate) td.dataset.filterDate = item.filterDate;
        td.append(content);
        row.append(td);
      }
      body.append(row);
    }
    table.append(head, body);
    const wrap = node('div', undefined, 'nq-table-wrap nq-failure-wrap');
    wrap.append(table);
    return wrap;
  };
  const operatorName = (operator, colors) => {
    const label = node('strong', operator || 'Unassigned', 'nq-failure-operator');
    if (colors?.[operator]) label.style.color = colors[operator];
    return label;
  };
  const renderFailures = (data) => {
    const host = $('nq-failures');
    const services = [...new Set([...data.types, ...data.technology, ...data.serving].map((item) => item.service))];
    if (!services.includes(state.failureService)) state.failureService = services.includes('voice') ? 'voice' : services[0] || '';
    const labels = Object.fromEntries([...data.types, ...data.technology, ...data.serving].map((item) => [item.service, item.label]));
    $('nq-failure-tabs').replaceChildren(...services.map((service) => {
      const tab = node('button', labels[service], 'nq-rate-tab');
      tab.type = 'button';
      tab.setAttribute('role', 'tab');
      tab.setAttribute('aria-selected', String(service === state.failureService));
      tab.classList.toggle('is-active', service === state.failureService);
      tab.addEventListener('click', () => { state.failureService = service; renderFailures(data); });
      return tab;
    }));
    const service = state.failureService;
    const sections = [];
    const section = (title, note, ...content) => {
      const box = node('section', undefined, 'nq-failure-section');
      box.append(node('h3', title, 'nq-failure-title'), ...(note ? [node('p', note, 'nq-hint')] : []), ...content);
      sections.push(box);
    };
    const types = data.types.find((item) => item.service === service);
    if (types) {
      const highest = Math.max(0.01, ...types.rows.flatMap((row) => Object.values(row.rates).map((value) => Number(value || 0))));
      section('Failure type', 'Each result as a share of every call of the operator in the environment (the count under it).',
        failureTable(['Operator', 'Environment', 'Calls', 'Non-Qualified', ...types.results], types.rows.map((row) => [
          {text: row.operator, className: 'nq-failure-name'}, row.environment, number(row.calls), number(row.nq),
          ...types.results.map((result) => (row.counts[result] ? {
            text: `${row.rates[result] === null ? '—' : `${Number(row.rates[result]).toFixed(2)}%`} · ${number(row.counts[result])}`,
            heat: [row.rates[result] || 0, highest], pairs: [['service', service], ['operator', row.operator], ['result', result]],
            title: `${row.operator} · ${row.environment} · ${result}: ${number(row.counts[result])} of ${number(row.calls)} calls`,
          } : {text: '—', className: 'nq-muted'})),
        ])));
    }
    const technology = data.technology.find((item) => item.service === service);
    if (technology) {
      const classes = technology.classes.slice(0, 7);
      const cards = node('div', undefined, 'nq-failure-grid');
      for (const operator of technology.operators) {
        const byName = technology.cells[operator] || {};
        const highest = Math.max(1, ...Object.values(byName).flatMap((counts) => Object.values(counts)));
        const card = node('div', undefined, 'nq-failure-card');
        card.append(operatorName(operator, data.operator_colors), failureTable(['Technology', ...classes, 'Total'],
          technology.technologies.filter((name) => byName[name]).map((name) => {
            const counts = byName[name];
            return [{text: name, className: 'nq-failure-name'}, ...classes.map((label) => (counts[label] ? {
              text: number(counts[label]), heat: [counts[label], highest],
              pairs: [['service', service], ['operator', operator], ['failure_classification', label]],
              title: `${operator} · ${name} · ${label}: ${number(counts[label])} Non-Qualified Calls`,
            } : {text: '—', className: 'nq-muted'})), {text: number(Object.values(counts).reduce((sum, value) => sum + value, 0)), className: 'nq-failure-total'}];
          })));
        cards.append(card);
      }
      section('Technology at the failure and failure classification', `The Non-Qualified Calls by the technology at their failure (else of the call) and their ${PROVIDER_NAME} failure classification (the most frequent ones).`, cards);
    }
    const serving = data.serving.find((item) => item.service === service);
    if (serving) {
      const cards = node('div', undefined, 'nq-failure-grid');
      for (const item of serving.operators) {
        const highest = Math.max(0.01, ...item.rows.map((row) => Number(row.rate || 0)));
        const card = node('div', undefined, 'nq-failure-card');
        card.append(operatorName(item.operator, data.operator_colors), failureTable(['Vendor', 'Host network', 'Calls', 'Share of calls', 'Non-Qualified', 'Share of NQ', 'NQ rate'],
          item.rows.slice(0, 12).map((row) => [
            {text: row.vendor, className: 'nq-failure-name'}, row.host_network, number(row.calls), `${row.calls_share ?? '—'}%`, number(row.nq),
            {text: `${row.nq_share ?? '—'}%`, className: row.nq_share !== null && row.calls_share !== null && row.nq_share > row.calls_share * 1.25 && row.nq_share - row.calls_share > 3 ? 'nq-failure-above' : ''},
            {text: row.rate === null ? '—' : `${Number(row.rate).toFixed(2)}%`, heat: [row.rate || 0, highest]},
          ])));
        cards.append(card);
      }
      section('Vendor and host network of the serving cell', 'The calls and Non-Qualified Calls per Vendor and host network of the cell that served them (the serving-cell Vendor Mapping); in orange, a share of the Non-Qualified Calls well above the share of the calls.', cards);
    }
    if (data.sites.length) {
      const cards = node('div', undefined, 'nq-failure-grid');
      for (const item of data.sites) {
        const highest = Math.max(0.01, ...item.rows.map((row) => Number(row.rate || 0)));
        const card = node('div', undefined, 'nq-failure-card');
        card.append(operatorName(item.operator, data.operator_colors), failureTable(['Site', 'Host network', 'Vendor', 'City or route', 'Calls', 'Non-Qualified', 'NQ rate'],
          item.rows.map((row) => [{text: row.site_id, className: 'nq-failure-name'}, row.host_network || '—', row.vendor || '—', row.city || '—',
            number(row.calls), number(row.nq), {text: `${Number(row.rate).toFixed(2)}%`, heat: [row.rate, highest]}])));
        cards.append(card);
      }
      section('Sites with the most Non-Qualified Calls', `Every service; the serving sites with ${data.min_site_calls} calls or more, the most Non-Qualified Calls first.`, cards);
    }
    host.replaceChildren(...(sections.length ? sections : [node('p', 'No Non-Qualified Calls for this selection.', 'nq-muted')]));
  };
  let failureToken = 0;
  let failureKey = '';
  async function loadFailures() {
    const filters = currentFilters();
    const key = JSON.stringify([filters, state.result?.sync?.synced_at || '']);
    if (key === failureKey) return;
    failureKey = key;
    const token = ++failureToken;
    try {
      const data = await api('/api/non-qualified-calls/failures', {method: 'POST', body: JSON.stringify({filters})});
      if (token === failureToken) renderFailures(data);
    } catch (error) {
      if (token === failureToken) {
        failureKey = '';
        $('nq-failures').replaceChildren(node('p', error.message, 'nq-muted'));
      }
    }
  }

  // -- NQ Prioritization ----------------------------------------------------------------
  // The field of the catalog that shows a value of the NQ Prioritization, to drill down into the calls of one of its values.
  const priorityPairs = (ref, value) => {
    const field = filterableFields().find((item) => item.source === 'priority' && item.source_ref === ref);
    return field ? [[`field:${field.key}`, value]] : null;
  };
  const points = (value) => (value === null || value === undefined ? '—' : Number(value).toFixed(2));
  // Whether the Tracked queue of the panel is unfolded (folded by default).
  let trackedQueueOpen = false;
  // The list whose steps the Strategy subpanel shows (campaign, final or outside; the list with the most calls at first).
  let stepsTab = '';
  const renderPrioritization = (data) => {
    const {totals} = data;
    const status = data.status || {};
    const summary = status.summary || {};
    const waiting = (status.campaigns || []).filter((item) => item.state !== 'scored');
    $('nq-priority-status').textContent = status.running ? 'Calculating…'
      : summary.calculated_at ? `Calculated ${relativeTime(summary.calculated_at)}` : 'Not calculated yet';
    $('nq-priority-status').title = [summary.calculated_at ? `Calculated ${exactTime(summary.calculated_at)}` : '',
      ...waiting.map((item) => `${item.campaign || 'No campaign'} ${item.nr_mode}: ${item.detail}`),
      status.error ? `The last calculation failed: ${status.error}` : ''].filter(Boolean).join('\n');
    $('nq-priority-recalculate').disabled = Boolean(status.running) || !state.user.can_edit;
    // The strategy the module uses, by its name (also the strategies of the admins); left alone while it is being chosen.
    const strategySelect = $('nq-priority-panel-strategy');
    if (strategySelect && document.activeElement !== strategySelect) {
      strategySelect.replaceChildren(...Object.entries(data.strategies || {}).map(([key, label]) => {
        const option = node('option', label);
        option.value = key;
        return option;
      }));
      strategySelect.value = data.strategy.key;
      strategySelect.dataset.current = data.strategy.key;
    }
    if (status.running) watchPrioritization();
    else if (priorityRunning) {
      // The calculation has ended: the calls show their new values.
      loadCalls({quiet: true});
    }
    priorityRunning = Boolean(status.running);
    const share = (count) => (totals.calls ? `${((count / totals.calls) * 100).toFixed(1)}% of the filtered calls` : 'No calls');
    const cards = [
      [kpiCard('Prioritized', number(totals.prioritized), share(totals.prioritized)), priorityPairs('prioritization', 'Prioritized')],
      [kpiCard('Track only', number(totals.tracked), share(totals.tracked)), priorityPairs('prioritization', 'Track only')],
      [kpiCard('High Scoring Impact', number(totals.high), `${Number(totals.points || 0).toFixed(1)} scoring points lost by the filtered calls`),
        priorityPairs('impact_level', 'High')],
      [kpiCard('Repeated Issues', number(totals.repeated), `${number(totals.places)} clusters of repeated failures`), priorityPairs('repeated', 'Yes')],
      [kpiCard('Next to analyse', number(totals.next), (data.queues || []).length
        ? data.queues.map((item) => `${item.name} ${number(item.total)}`).join(' · ') : 'Prioritized, open and not attended yet'), null],
    ];
    $('nq-priority-kpis').replaceChildren(...cards.map(([card, pairs]) => (pairs ? drillCard(card, {pairs}) : card)));
    // Each part of the panel in a subpanel of its own, in this order: the queues, the steps of the strategy and the Scoring
    // Impact (the hotspots, time-window and clustered issues have a panel of their own).
    const sections = {};
    const section = (key, title, note, ...content) => {
      const box = node('section', undefined, 'nq-failure-section nq-progress-section nq-priority-subpanel');
      box.append(node('h3', title, 'nq-failure-title'), ...(note ? [node('p', note, 'nq-hint')] : []), ...content);
      sections[key] = box;
    };
    const notes = [];
    if (totals.waiting) notes.push(`${number(totals.waiting)} of these calls are waiting for their prioritization: it is calculated in the background once the server is idle, or now with Recalculate.`);
    if (waiting.length) notes.push(`Not scored yet: ${waiting.map((item) => `${item.campaign || 'No campaign'} ${item.nr_mode} (${item.detail.replace(/\.$/, '')})`).join('; ')}.`);
    // The steps of each list in a tab of their own (list 1 blue, list 2 purple, as the queues) and the calls out of scope and
    // those no step takes in a third. The tab chosen stays as the panel is drawn again; the first time, the list with the
    // most calls.
    const finalList = data.rules.some((rule) => rule.list === 'final');
    const groupOf = (rule) => (rule.kind === 'step' ? rule.list : 'outside');
    // The conditions of a step as the Prioritization Rules show them: each in its colour, AND, OR and the parentheses in the
    // colour of the module.
    const conditionKeys = Object.fromEntries(Object.values(state.prioritizationFields?.conditions || {})
      .flatMap((conditions) => Object.entries(conditions).map(([key, label]) => [label, key])));
    const conditionNode = (text) => {
      const element = node('span', undefined, 'nq-step-condition-text');
      String(text || '').split(/(\bAND\b|\bOR\b|[()])/).map((part) => part.trim()).filter(Boolean)
        .forEach((part) => element.append(['AND', 'OR', '(', ')'].includes(part) ? node('strong', part, 'nq-step-join')
          : node('span', part, conditionKeys[part] ? `nq-condition-value is-cond-${conditionKeys[part]}` : '')));
      return element;
    };
    // The follow-up of the calls of a step in a stacked bar over its own calls: waiting (open and not attended yet), in
    // progress (attended, still open) and closed, the calls waiting beside it.
    const followUpBar = (rule) => {
      const progress = Math.max(0, rule.open - rule.waiting);
      const closed = Math.max(0, rule.calls - rule.open);
      const element = node('span', undefined, 'nq-step-bar');
      const track = node('span', undefined, 'nq-step-bar-track');
      const bar = node('span', undefined, 'nq-step-flow');
      bar.style.width = rule.calls ? '100%' : '0';
      [['waiting', rule.waiting], ['progress', progress], ['closed', closed]].forEach(([kind, count]) => {
        if (!count) return;
        const part = node('span', undefined, `is-${kind}`);
        part.style.flexGrow = String(count);
        bar.append(part);
      });
      track.append(bar);
      element.append(track, node('span', number(rule.waiting), `nq-step-bar-value${rule.waiting ? ' is-waiting' : ''}`));
      element.title = `${number(rule.calls)} calls: ${number(rule.waiting)} waiting, ${number(progress)} in progress and ${number(closed)} closed`;
      return element;
    };
    // The scoring points the calls of a step lose, in a bar against the step that loses the most in the tab.
    const pointsBar = (value, most) => {
      const element = node('span', undefined, 'nq-step-bar');
      const track = node('span', undefined, 'nq-step-bar-track');
      const bar = node('span', undefined, 'nq-step-points');
      bar.style.width = most && value ? `${Math.max(3, (value / most) * 100)}%` : '0';
      track.append(bar);
      element.append(track, node('span', points(value), 'nq-step-bar-value'));
      return element;
    };
    // Each step as the table of the Prioritization Rules shows it, in its colours (what it takes in full on hover), its filtered
    // calls in the place of #Calls, their follow-up and the points they lose in bars, and its queue last.
    const stepRow = (rule, most) => {
      const rulePairs = rule.name ? priorityPairs('priority_rule', rule.name) : null;
      const bars = [{node: followUpBar(rule), className: 'nq-step-bar-cell'},
        {node: pointsBar(rule.points, most.points), className: 'nq-step-bar-cell'}];
      if (rule.kind !== 'step') {
        return ['—', {text: rule.kind === 'out_of_scope' ? 'Out of scope' : 'No step', className: 'nq-failure-name', pairs: rulePairs, title: rule.label},
          '—', '—', '—', '—', {text: rule.label, className: 'nq-step-condition', title: rule.conditions}, number(rule.calls),
          ...bars, rule.criterion || '—'];
      }
      const queue = String(rule.queue || 'Tracked').toLowerCase();
      return [{text: rule.priority, className: `nq-queue-priority is-${String(rule.priority).toLowerCase()}`},
        {text: String(rule.number), className: 'nq-step-number', pairs: rulePairs, title: rule.name},
        {text: rule.nr_mode === 'any' ? 'Any' : rule.nr_mode, className: `nq-step-mode is-${String(rule.nr_mode).toLowerCase()}`},
        rule.operators || '—', {text: rule.call_type, className: `nq-step-type is-${queue}`}, rule.area,
        {node: conditionNode(rule.condition), className: 'nq-step-condition', title: rule.conditions}, number(rule.calls),
        ...bars, {text: rule.queue, className: `nq-step-queue is-${queue}`}];
    };
    const columns = ['Priority', 'Step', 'NR Mode', 'Operators', 'Call Type', 'Area', 'Condition', 'Calls', 'Follow-up', 'Points lost', 'Queue'];
    const tabs = [
      ['campaign', finalList ? 'List 1 · Weekly CDRs' : 'List 1 · Weekly & Final CDRs',
        finalList ? 'While the Final CDR of the campaign is not scored.' : 'The only list of the strategy: before and after the Final CDR of the campaign is scored.'],
      ['final', 'List 2 · Final CDRs', 'Once the Final CDR of the campaign is scored.'],
      ['outside', 'Outside the lists', 'The calls out of scope and those no step takes: no queue and not tracked.'],
    ].filter(([key]) => data.rules.some((rule) => groupOf(rule) === key));
    const callsOf = (key) => data.rules.filter((rule) => groupOf(rule) === key).reduce((sum, rule) => sum + Number(rule.calls || 0), 0);
    if (!tabs.some(([key]) => key === stepsTab)) {
      const lists = tabs.filter(([key]) => key !== 'outside');
      stepsTab = (lists.reduce((best, tab) => (callsOf(tab[0]) > callsOf(best[0]) ? tab : best), lists[0] || tabs[0]) || [''])[0];
    }
    const tabBar = node('div', undefined, 'nq-rate-tabs nq-step-tabs');
    tabBar.setAttribute('role', 'tablist');
    tabBar.setAttribute('aria-label', 'Lists of the strategy');
    const tabPanel = node('div', undefined, 'nq-step-tab-panel');
    const showTab = (key) => {
      stepsTab = key;
      tabBar.querySelectorAll('.nq-rate-tab').forEach((tab) => {
        tab.classList.toggle('is-active', tab.dataset.list === key);
        tab.setAttribute('aria-selected', String(tab.dataset.list === key));
      });
      const rows = data.rules.filter((rule) => groupOf(rule) === key);
      const most = {points: Math.max(0, ...rows.map((rule) => Number(rule.points || 0)))};
      const table = failureTable(columns, rows.map((rule) => stepRow(rule, most)));
      table.classList.add('nq-priority-steps-summary');
      table.querySelector('th:nth-child(9)').title = 'The calls of the step: waiting (open and not attended yet), in progress (attended, still open) and closed, over the calls of the step; the number tells those waiting';
      const legend = node('p', undefined, 'nq-step-legend');
      legend.append(...[['waiting', 'Waiting'], ['progress', 'In progress'], ['closed', 'Closed']].map(([kind, text]) => {
        const item = node('span', undefined, 'nq-step-legend-item');
        item.append(node('i', '', `is-${kind}`), text);
        return item;
      }));
      const head = node('div', undefined, 'nq-step-tab-head');
      head.append(node('p', tabs.find(([item]) => item === key)?.[2] || '', 'nq-hint nq-step-tab-note'), legend);
      tabPanel.replaceChildren(head, table);
    };
    tabBar.append(...tabs.map(([key, label]) => {
      const tab = node('button', label, `nq-rate-tab is-${key}`);
      tab.type = 'button';
      tab.dataset.list = key;
      tab.setAttribute('role', 'tab');
      tab.append(node('span', number(callsOf(key)), 'nq-step-tab-count'));
      tab.title = `${number(callsOf(key))} filtered calls`;
      tab.addEventListener('click', () => showTab(key));
      return tab;
    }));
    if (tabs.length) showTab(stepsTab);
    section('steps', `Strategy: ${data.strategy.label}`,
      'The filtered calls each step took, a tab per list, with their follow-up (Waiting: open and not attended yet, as in the queues) and the points they lose. Hover a step for what it takes; click it for its calls.',
      ...notes.map((text) => node('p', text, 'nq-hint nq-priority-note')), tabBar, tabPanel);
    const grid = node('div', undefined, 'nq-failure-grid');
    const levelsCard = node('div', undefined, 'nq-failure-card');
    levelsCard.append(node('strong', 'Scoring Impact', 'nq-failure-operator'), failureTable(['Scoring Impact', 'Calls'], data.levels.map((item) => [
      {text: item.value, className: 'nq-failure-name nq-priority-level', color: item.color, pairs: item.value === 'Waiting' ? null : priorityPairs('impact_level', item.value)},
      number(item.count)])));
    const kpiCardBox = node('div', undefined, 'nq-failure-card');
    kpiCardBox.append(node('strong', 'Scoring points lost by KPI', 'nq-failure-operator'), data.kpis.length
      ? failureTable(['KPI', 'Category', 'Environment', 'Calls', 'Points lost'], data.kpis.map((item) => [
        {text: item.kpi, className: 'nq-failure-name', title: item.code}, item.category || '—', item.environment, number(item.calls),
        points(item.points)]))
      : node('p', 'The filtered calls lose no points of a scored campaign.', 'nq-muted'));
    grid.append(levelsCard, kpiCardBox);
    section('impact', 'Scoring Impact', `The points of the scoring of its campaign each call loses: in every KPI that counts tests it misses, the points the operator loses in the environment of the call shared among the tests that miss the KPI. High: the calls that hold the first ${data.settings.high_share}% of the points their campaign, operator and service lose; Medium: up to ${data.settings.medium_share}%.`, grid);
    // Every hotspot among the filtered calls (2+ failures of an operator, NR Mode and campaign close to each other in time and
    // distance, whatever their call type), the most calls first: its calls of each call type in a stacked bar (Voice blue,
    // WhatsApp aqua green, Data darker green) and their numbers; a click on its site shows its calls.
    const HOTSPOT_KINDS = ['Voice', 'WhatsApp', 'Data'];
    const kindsBar = (item) => {
      const element = node('span', undefined, 'nq-step-bar nq-hotspot-kinds');
      const track = node('span', undefined, 'nq-step-bar-track');
      const bar = node('span', undefined, 'nq-step-flow');
      bar.style.width = item.calls ? '100%' : '0';
      HOTSPOT_KINDS.forEach((kind) => {
        const count = item.kinds[kind] || 0;
        if (!count) return;
        const part = node('span', undefined, `is-${kind.toLowerCase()}`);
        part.style.flexGrow = String(count);
        bar.append(part);
      });
      track.append(bar);
      element.append(track, node('span', HOTSPOT_KINDS.map((kind) => number(item.kinds[kind] || 0)).join(' / '), 'nq-step-bar-value nq-hotspot-kinds-value'));
      element.title = HOTSPOT_KINDS.map((kind) => `${kind} ${number(item.kinds[kind] || 0)}`).join(' · ');
      return element;
    };
    // When the first or last call of a group started, in its own column (the same in every table, the full date on hover).
    // The day and the month never apart: the time goes below them when the column is narrow.
    const momentCell = (value) => {
      const text = momentText(value).replace(' ', '\u00a0');
      return text ? {text, title: String(value).slice(0, 16), className: 'nq-group-time', filterDate: String(value).slice(0, 10)}
        : {text: '—', className: 'nq-group-time'};
    };
    // What identifies a group beside its ID: its sites (spatial groups), its period (temporal groups) or both (hotspots).
    const groupSites = (item) => `${item.place || 'No site'}${item.places > 1 ? ` +${number(item.places - 1)}` : ''}`;
    const spots = data.hotspots || [];
    const runs = data.consecutive || [];
    // The filters of the groups name each by its ID and what identifies it.
    spots.forEach((item) => { state.hotspotLabels[item.key] = `${item.id} · ${groupSites(item)} · ${groupPeriod(item)}`; });
    runs.forEach((item) => { state.hotspotLabels[item.key] = `${item.id} · ${groupPeriod(item)}`; });
    data.issues.forEach((item) => { state.hotspotLabels[item.key] = `${item.id} · ${groupSites(item)}`; });
    const settings = data.settings;
    const joinWord = settings.hotspot_join === 'and' ? 'AND' : 'OR';
    const hotspotNote = `Failures of the same operator, NR Mode and campaign, whatever their call type (the Ping tests and the calls out of scope apart), each within ${joinWord === 'OR' ? 'the Time window in the same drive OR' : 'the Time window AND'} the Cluster distance (or at the site where it ended) of another one of them: every hotspot with the filtered calls of each, the most calls first (${number(spots.length)} hotspot${spots.length === 1 ? '' : 's'}).`;
    // The hotspots and the sites with a repeated issue share their columns and their look: each row with its operator, NR
    // Mode, campaign, site (a click shows its calls), time, calls, their call types, points lost, open calls and main root
    // category, the call types in a legend above them.
    const kindsLegend = () => {
      const legend = node('p', undefined, 'nq-step-legend nq-hotspot-legend');
      HOTSPOT_KINDS.forEach((kind) => {
        const item = node('span', undefined, 'nq-step-legend-item');
        item.append(node('i', undefined, `is-${kind.toLowerCase()}`), document.createTextNode(kind));
        legend.append(item);
      });
      return legend;
    };
    // The NR Modes and campaigns of a group, with their calls when there are several.
    const shares = (entries) => (entries.length > 1 ? entries.map(([name, count]) => `${name} ${number(count)}`).join(' · ') : (entries[0]?.[0] || '—'));
    // Each group: its ID (a click shows its calls) with what identifies it in parentheses (``describe``), its NR Modes,
    // campaigns, sites (the site of most of its calls, +N when they are at more) and when its first and last call started.
    const groupTable = (items, filter, noun, idLabel, describe) => {
      const table = failureTable([idLabel, 'Operator', 'NR Mode', 'Campaign', 'Site(s)', 'From', 'To', 'Calls', 'Voice / WhatsApp / Data', 'Points lost', 'Open', 'Main Root Category'],
        items.map((item) => {
          // Its ID and what identifies it: the sites on its first line, the period on the next (both for a hotspot).
          const id = node('button', undefined, 'nq-failure-drill nq-group-id');
          const [first, ...more] = describe(item);
          const line = node('span', undefined, 'nq-group-id-line');
          line.append(node('strong', item.id), node('span', ` · ${first}`, 'nq-group-id-what'));
          id.append(line, ...more.map((text) => node('span', text, 'nq-group-id-line nq-group-id-what nq-group-id-period')));
          // A click filters the list by the group and takes the page to its calls.
          return [{node: id, pairs: [[filter, item.key]], reveal: 'section-nq-calls', className: 'nq-failure-name', filterValue: item.id,
            title: `${number(item.calls)} of the ${number(item.size)} calls of the ${noun}: click to see them`},
          {text: item.operator || 'Unassigned'},
          {text: shares(Object.entries(item.nr_modes || {})), filterValues: Object.keys(item.nr_modes || {})},
          {text: shares(Object.entries(item.campaign_names || {})), filterValues: Object.keys(item.campaign_names || {})},
          {text: groupSites(item), title: item.places > 1 ? `${number(item.places)} sites` : '', filterValue: item.place || 'No site'},
          momentCell(item.first), momentCell(item.last), number(item.calls),
          {node: kindsBar(item), className: 'nq-step-bar-cell', filterValues: HOTSPOT_KINDS.filter((kind) => item.kinds[kind])},
          points(item.points), number(item.open), item.category || '—'];
        }));
      table.classList.add('nq-priority-issues-table', 'nq-priority-group-table');
      // Excel-style filters on every column, kept in this browser for each table of the workspace.
      const filters = window.enableExcelColumnFilters?.(table.querySelector('table'), {
        excludeLastColumn: false, persistKey: `nq-group-filters:${$('nq-table')?.dataset.workspace || ''}:${filter}`,
      });
      filters?.apply();
      return table;
    };
    // Each table with its title and what it lists.
    // Each table with its title, the calls it holds in a badge beside it, and what it lists.
    const groupBlock = (title, note, content, items) => {
      const box = node('div', undefined, 'nq-priority-group');
      const head = node('div', undefined, 'nq-priority-group-head');
      const calls = items.reduce((total, item) => total + item.calls, 0);
      head.append(node('h4', title, 'nq-priority-group-title'), node('span', `${number(calls)} call${calls === 1 ? '' : 's'}`, 'nq-priority-group-calls'));
      box.append(head, node('p', note, 'nq-hint'), content);
      return box;
    };
    // A hotspot or a time-window issue: its site (the site of most of its calls, +N when they are at more) filters
    // its calls.
    // The title tells how the failures of a hotspot are joined: Time-Window OR (or AND) Clustered Issues.
    const hotspotBlock = groupBlock(`Hotspots (Time-Window ${joinWord} Clustered Issues)`, hotspotNote,
      spots.length ? groupTable(spots, 'hotspot', 'hotspot', 'Hotspot ID', (item) => [groupSites(item), groupPeriod(item)])
        : node('p', 'No hotspot among the filtered calls.', 'nq-muted'), spots);
    const runNote = `Failures of the same operator, NR Mode, campaign and drive (the car), whatever their call type and wherever they were (the Ping tests and the calls out of scope apart), each within the Time window of the one before: every time-window issue with the filtered calls of each, the most calls first (${number(runs.length)} time-window issue${runs.length === 1 ? '' : 's'}).`;
    const runBlock = groupBlock('Time-Window Issues', runNote,
      runs.length ? groupTable(runs, 'consecutive_issue', 'run', 'Time-Window ID', (item) => [groupPeriod(item)])
        : node('p', 'No time-window issues among the filtered calls.', 'nq-muted'), runs);
    const issueNote = `Clusters of failures of the same operator and ${data.cluster_mode ? `of ${data.cluster_mode} only, the NR Mode of the ${data.cluster_mode_source}` : 'of every NR Mode together'}, whatever their call type (the Ping tests and the calls out of scope apart): calls with at least the Cluster size of Non-Qualified Calls within the Cluster distance of them or at their site, in their campaign and the Cluster period before it, each within the Cluster distance (or at the same site) of another one of the cluster: every cluster with the filtered calls of each, the most calls first (${number(data.issue_count || 0)} cluster${data.issue_count === 1 ? '' : 's'}).`;
    const issueBlock = groupBlock('Clustered Issues', issueNote,
      data.issues.length ? groupTable(data.issues, 'clustered_issue', 'cluster', 'Cluster ID', (item) => [groupSites(item)])
        : node('p', 'No clustered issue among the filtered calls.', 'nq-muted'), data.issues);
    // The three tables in one subpanel: the criteria of the Prioritization Rules that make them on top, the call types, then
    // the more general tables first: with the OR join the hotspots (the time-window and the clustered issues together) before
    // the other two, with AND after them (every failure of a hotspot of AND is in a run and in a cluster). Neither of the
    // consecutive and the clustered issues holds the other: the one with more calls goes first, with the same calls the one
    // that groups them in fewer rows.
    const criteria = node('div', undefined, 'nq-priority-criteria');
    // The clusters count the calls of one NR Mode alone when the NR Mode filter, or the campaigns filtered, choose one; else
    // every NR Mode together.
    const metres = (value) => (value >= 1000 ? `${number(value / 1000)} km` : `${number(value)} m`);
    const byIsd = (isd, city, roads) => `${number(isd)} ISD · without it ${metres(city)} cities, ${metres(roads)} roads`;
    [['Time window', `${number(settings.consecutive_minutes)} min`],
      ['Time-window distance', byIsd(settings.consecutive_isd, settings.consecutive_city_meters, settings.consecutive_road_meters)],
      ['Cluster distance', `${byIsd(settings.cluster_isd, settings.spot_meters, settings.cluster_road_meters)} · or same site`],
      ['Hotspot join', joinWord], ['Cluster size', `${number(settings.min_calls)} calls`],
      ['Cluster period', `${number(settings.previous_quarters)} campaign${settings.previous_quarters === 1 ? '' : 's'} before`],
      ['Cluster NR Mode', data.cluster_mode ? `${data.cluster_mode} only (${data.cluster_mode_source})` : 'every NR Mode together']].forEach(([name, value]) => {
      const chip = node('span', undefined, 'nq-priority-criterion');
      chip.append(node('span', name), node('strong', value));
      criteria.append(chip);
    });
    const calls = (items) => items.reduce((total, item) => total + item.calls, 0);
    const others = [[runBlock, runs], [issueBlock, data.issues]]
      .sort(([, a], [, b]) => calls(b) - calls(a) || a.length - b.length).map(([block]) => block);
    // In a panel of their own, below the NQ Prioritization & Queues.
    $('nq-clusters').replaceChildren(node('p', `With the criteria of the Prioritization Rules below, the more general tables first: with the OR join the hotspots, which hold the time-window and the clustered issues together; with AND the time-window and the clustered issues, as every failure of a hotspot of AND is in a time-window issue and in a cluster. Between these two, the one with more calls goes first (with the same calls, the one in fewer rows).`, 'nq-hint'),
      criteria, kindsLegend(), ...(joinWord === 'OR' ? [hotspotBlock, ...others] : [...others, hotspotBlock]));
    // The step tells the NR Mode and the kind of call, so the queue keeps to the columns that tell the calls apart: the
    // Priority and the step in pills (the step of list 1, Weekly, or list 2, Final; what it takes on hover), the campaign
    // as the Campaign Maps name it and the Scoring Impact in its colour.
    const levelColors = Object.fromEntries((data.levels || []).map((item) => [item.value, item.color]));
    // Each queue fits its card without scrolling sideways (the JOIN_ID on one line, the other columns wrap when needed).
    const withClass = (element, className) => { element.classList.add(className); return element; };
    const queueTable = (rows) => withClass(failureTable(['#', 'JOIN_ID', 'Priority', 'Operator', 'Campaign', 'Step', 'Expected Gain', 'Scoring Impact'],
      rows.map((item) => [{text: number(item.position), className: 'nq-queue-position'},
        {text: item.join_id || item.call_key, className: 'nq-failure-name nq-queue-join', action: () => openDetail(item.call_key)},
        {text: item.priority || '—', className: `nq-queue-priority is-${String(item.priority || '').toLowerCase()}`},
        item.operator || '—', item.campaign || '—',
        {text: item.step ? `Step ${item.step} · ${item.list === 'final' ? 'Final' : 'Weekly'}` : '—', title: item.rule || '',
          className: `nq-queue-step is-${item.list === 'final' ? 'final' : 'weekly'}`},
        {text: points(item.gain), className: 'nq-queue-number',
          title: item.gain_campaign ? `From the Final CDR of ${item.gain_campaign}` : 'No campaign with a Final CDR to tell it: the oldest first'},
        item.level ? {text: item.level, className: 'nq-failure-name nq-priority-level', color: levelColors[item.level]} : '—'])), 'nq-queue-table');
    const queues = node('div', undefined, 'nq-priority-queues');
    queues.append(...(data.queues || []).map((item) => {
      const box = node('div', undefined, 'nq-failure-card');
      box.append(node('strong', `${item.name} queue · ${number(item.total)} waiting`, 'nq-failure-operator'),
        item.rows.length ? queueTable(item.rows) : node('p', 'No call is waiting in this queue.', 'nq-muted'));
      return box;
    }));
    // The tracked calls, which no team takes, folded below the queues (they stay open or folded as the panel is drawn again).
    const content = [queues];
    if (data.tracked) {
      const tracked = node('details', undefined, 'nq-priority-tracked');
      tracked.open = trackedQueueOpen;
      tracked.addEventListener('toggle', () => { trackedQueueOpen = tracked.open; });
      tracked.append(node('summary', `Tracked · ${number(data.tracked.total)} waiting (no team queue: only tracked)`),
        data.tracked.rows.length ? queueTable(data.tracked.rows) : node('p', 'No tracked call is waiting.', 'nq-muted'));
      content.push(tracked);
    }
    section('queues', 'Next to analyse', `The first ${data.settings.capacity} calls of each queue that are open and not attended yet, in the order the analysts of its team take them: Priority, the newest campaign first, the step of its list, the highest Expected Gain, then the oldest; the tracked calls, in no team queue, are folded below them. Click a call to open it.`, ...content);
    $('nq-priority').replaceChildren(...['queues', 'steps', 'impact'].map((key) => sections[key]).filter(Boolean));
  };
  let priorityToken = 0;
  let priorityKey = '';
  let priorityRunning = false;
  let priorityWatch = null;
  // While the prioritization is calculated, the panel follows it.
  const watchPrioritization = () => {
    if (priorityWatch) return;
    priorityWatch = window.setTimeout(() => {
      priorityWatch = null;
      priorityKey = '';
      if (panelShown('prioritization') || panelShown('clusters')) void loadPrioritization();
    }, 5000);
  };
  async function loadPrioritization() {
    const filters = currentFilters();
    // The follow-up of the calls (the Summary of the calls query) changes what waits for its analysis.
    const key = JSON.stringify([filters, state.result?.sync?.synced_at || '', state.result?.summary || null]);
    if (key === priorityKey) return;
    priorityKey = key;
    const token = ++priorityToken;
    try {
      const data = await api('/api/non-qualified-calls/prioritization', {method: 'POST', body: JSON.stringify({filters})});
      if (token === priorityToken) renderPrioritization(data);
    } catch (error) {
      if (token === priorityToken) {
        priorityKey = '';
        $('nq-priority').replaceChildren(node('p', error.message, 'nq-muted'));
        $('nq-clusters').replaceChildren(node('p', error.message, 'nq-muted'));
      }
    }
  }
  // Another strategy for the module, from the panel: every call takes its step, queue and Priority at once, as when the
  // Prioritization Rules are saved (the calls in analysis keep their Priority).
  $('nq-priority-panel-strategy')?.addEventListener('change', async (event) => {
    const select = event.target;
    const previous = select.dataset.current || '';
    const label = select.selectedOptions[0]?.textContent || select.value;
    const message = `Use ${label} for the NQ Prioritization? Every call takes its step, queue and Priority at once; the calls in analysis keep their Priority.`;
    const accepted = typeof window.showConfirmDialog === 'function'
      ? await window.showConfirmDialog(message, {title: 'Change the strategy', confirmLabel: 'Change'})
      : window.confirm(message);
    if (!accepted) {
      select.value = previous;
      return;
    }
    select.disabled = true;
    try {
      const result = await api('/api/non-qualified-calls/prioritization/strategy', {method: 'PUT', body: JSON.stringify({strategy: select.value})});
      state.prioritization = result.settings;
      select.dataset.current = select.value;
      toast(`The NQ Prioritization uses ${label}.`);
      priorityKey = '';
      await loadPrioritization();
      loadCalls({quiet: true});
    } catch (error) {
      select.value = previous;
      toast(error.message, 'error');
    } finally {
      select.disabled = false;
    }
  });
  $('nq-priority-recalculate')?.addEventListener('click', async () => {
    const button = $('nq-priority-recalculate');
    button.disabled = true;
    try {
      await api('/api/non-qualified-calls/prioritization/recalculate', {method: 'POST'});
      toast('The prioritization of the calls is calculated again in the background.');
      priorityKey = '';
      priorityRunning = true;
      await loadPrioritization();
    } catch (error) {
      toast(error.message, 'error');
      button.disabled = false;
    }
  });

  // -- call detail drawer -------------------------------------------------------
  const drawer = $('nq-drawer');
  const backdrop = $('nq-drawer-backdrop');
  // The map of the area where the call failed, shown instead of the tabs with the Map button of the header.
  const callMap = window.NqCallMap?.mount({
    panel: $('nq-map-panel'), expandDialog: $('nq-map-expand'), api, toast, campaignLabel, cdrTime, number,
    // NQ calls from Selected campaigns: those of the campaigns chosen in the filters.
    filters: () => currentFilters(),
    openCall: async (callKey) => { if (callKey !== state.detail?.call.call_key && await leaveDetail()) openDetail(callKey, {keepTab: true}); },
    // Decisions at its place: the Root Category and Cause of other calls there, given to this one.
    canEdit: () => Boolean(state.user?.can_edit),
    useRootCause: (category, cause) => {
      if (state.detail) patchCall(state.detail.call, {root_category: category, root_cause: cause}, null, 'Root cause taken from the decisions at its place.');
    },
    // The group of the call that filters the list, painted red on the map.
    groupFilter: () => filteringGroup(),
  });
  refreshCallMap = () => callMap?.refresh();
  // On a short screen (a laptop) the header, the follow-up fields and the tabs of the call leave the content of its tab too
  // little room: the whole panel then scrolls as one, its tabs stuck at the top (is-scrolling), as on a phone. It is checked
  // when the panel opens and whenever the screen, the zoom or those parts change (another call, the Failure Map...).
  const DRAWER_TAB_ROOM = 320;
  const fitDrawer = () => {
    if (!drawer.classList.contains('is-open')) return;
    const above = ['.nq-drawer-head', '.nq-drawer-tracking', '.nq-drawer-tabs']
      .reduce((height, selector) => height + (drawer.querySelector(selector)?.offsetHeight || 0), 0);
    drawer.classList.toggle('is-scrolling', drawer.clientHeight - above < Math.min(DRAWER_TAB_ROOM, drawer.clientHeight / 2));
  };
  if (typeof ResizeObserver === 'function') {
    const parts = new ResizeObserver(() => window.requestAnimationFrame(fitDrawer));
    [drawer, ...drawer.querySelectorAll('.nq-drawer-head, .nq-drawer-tracking, .nq-drawer-tabs')].forEach((part) => parts.observe(part));
  }
  window.addEventListener('resize', fitDrawer);
  const closeDrawer = () => {
    drawer.classList.remove('is-open');
    drawer.setAttribute('aria-hidden', 'true');
    backdrop.hidden = true;
    state.detail = null;
    callMap?.hide();
  };
  // The tab the Map button of the header returns to.
  let tabBeforeMap = 'general';
  const selectTab = (name) => {
    if (!drawer.querySelector(`[data-nq-tab="${CSS.escape(name)}"]`) && !(name === 'map' && callMap)) name = 'general';
    if (name !== 'map') tabBeforeMap = name;
    const mapButton = $('nq-drawer-map');
    mapButton.classList.toggle('is-active', name === 'map');
    mapButton.setAttribute('aria-pressed', String(name === 'map'));
    // The map takes the height of the follow-up fields, which show again with any tab.
    drawer.classList.toggle('is-map', name === 'map');
    if (name === 'map') callMap.show(state.detail?.call.call_key);
    else callMap?.hide();
    drawer.querySelectorAll('[data-nq-tab]').forEach((tab) => {
      const active = tab.dataset.nqTab === name;
      tab.classList.toggle('is-active', active);
      tab.setAttribute('aria-selected', String(active));
      // Where the tabs scroll sideways (phones), the chosen one comes into view.
      if (active && tab.parentElement.scrollWidth > tab.parentElement.clientWidth) {
        tab.parentElement.scrollLeft = tab.offsetLeft - (tab.parentElement.clientWidth - tab.offsetWidth) / 2;
      }
    });
    drawer.querySelectorAll('[data-nq-panel]').forEach((panel) => { panel.hidden = panel.dataset.nqPanel !== name; });
  };
  // One tab per section of the Analysis Center, in its colour, then the call details; the General
  // tab holds the activity of the call and every other section its own panel of fields.
  // The tabs of a call: the activity (the General section), then one per section, Implementation and Planning together.
  const TAB_GROUPS = [['general'], ['rca'], ['failure_event'], ['analysis'], ['implementation', 'planning']];
  // The call details close the tabs, in grey.
  const CALL_DETAILS_COLOR = '#9aa5ad';
  // The Failure Map (the map of the area where the call failed, nq_call_map.js): a step of its own, without fields, between
  // RCA and Failure Details.
  const FAILURE_MAP = {key: 'map', label: 'Failure Map', color: '#0B7285', sections: []};
  const drawerTabs = () => {
    const known = new Set(state.sections.map((section) => section.key));
    const grouped = new Set(TAB_GROUPS.flat());
    const groups = [...TAB_GROUPS, ...state.sections.filter((section) => !grouped.has(section.key)).map((section) => [section.key])]
      .map((keys) => keys.filter((key) => known.has(key))).filter((keys) => keys.length)
      .map((keys) => ({key: keys[0], sections: keys.map(sectionOf), color: sectionOf(keys[0]).color,
        label: keys[0] === 'general' ? 'Activity' : keys.map((key) => sectionOf(key).label).join(' & ')}));
    if (!callMap) return groups;
    const details = groups.findIndex((group) => group.key === 'failure_event');
    const rca = groups.findIndex((group) => group.key === 'rca');
    const at = details >= 0 ? details : rca >= 0 ? rca + 1 : Math.min(1, groups.length);
    return [...groups.slice(0, at), FAILURE_MAP, ...groups.slice(at)];
  };
  const buildDrawerTabs = () => {
    const tabs = $('nq-drawer-tabs');
    const active = tabs.querySelector('.is-active')?.dataset.nqTab || 'general';
    // The tabs of the sections are the numbered steps of the analysis; the call details are only a reference.
    const tab = (key, label, color, step) => {
      const button = node('button', undefined, `nq-drawer-tab ${step ? 'is-step' : 'is-reference'}`);
      button.type = 'button';
      button.setAttribute('role', 'tab');
      button.dataset.nqTab = key;
      button.title = step ? `Step ${step}: ${label}` : `${label} (reference)`;
      if (color) {
        button.style.setProperty('--nq-section', color);
        button.style.setProperty('--nq-section-text', contrastText(color));
      }
      const marker = node('span', step ? String(step) : 'i', 'nq-tab-step');
      marker.setAttribute('aria-hidden', 'true');
      button.dataset.label = label;
      button.append(marker, node('span', label), node('small', '', 'nq-tab-badge'));
      button.addEventListener('click', () => chooseTab(key));
      return button;
    };
    const groups = state.sections.length ? drawerTabs() : [{key: 'general', label: 'Activity', color: '', sections: []}];
    const separator = node('span', undefined, 'nq-drawer-tabs-separator');
    separator.setAttribute('aria-hidden', 'true');
    tabs.replaceChildren(...groups.map((group, index) => tab(group.key, group.label, group.color, index + 1)),
      separator, tab('details', 'Call Details', CALL_DETAILS_COLOR));
    // The Failure Map shows the map panel of the call; the other steps their fields.
    $('nq-section-panels').replaceChildren(...groups.filter((group) => !['general', FAILURE_MAP.key].includes(group.key)).map((group) => {
      const panel = node('section', undefined, 'nq-section-panel');
      panel.dataset.nqPanel = group.key;
      panel.hidden = true;
      panel.style.setProperty('--nq-section', group.color);
      panel.append(node('div', undefined, 'nq-section-fields'));
      return panel;
    }));
    selectTab(active);
  };
  const timelineChange = (entry) => {
    const item = node('li', undefined, 'nq-event nq-event-change');
    item.append(node('span', '', 'nq-event-dot'));
    const text = node('p');
    const who = node('strong', entry.changed_by);
    if (entry.field === 'comment_edit') text.append(who, ' edited a comment');
    else if (entry.field === 'comment_delete') text.append(who, ' deleted a comment');
    else if (entry.field === 'status_mode') {
      text.append(who, entry.new_value === 'auto' ? ' gave the status back to the Status Rules' : ' set the status by hand');
    } else {
      const kind = entry.field;
      const emptyLabel = kind === 'root_cause' ? NO_CAUSE : kind.startsWith('root_') ? NOT_CLASSIFIED : 'Unassigned';
      const historyPill = (value) => pill(kind === 'status_auto' ? 'status' : kind, value, emptyLabel);
      if (kind === 'status_auto') {
        // The Status Rules moved the call after a change of its fields.
        item.classList.add('is-automatic');
        text.append('The status followed the Status Rules ');
        if (entry.old_value) text.append('from ', historyPill(entry.old_value), ' ');
        text.append('to ', historyPill(entry.new_value), ' after a change by ', who);
      } else if (kind.startsWith('field:')) {
        const field = state.fields.find((item) => item.key === kind.slice(6));
        const fieldPill = (value) => {
          const element = node('span', value || 'empty', `nq-pill${value ? '' : ' is-empty'}`);
          if (field) paintPill(element, field.type === 'yes_no' ? YES_NO_COLORS[value] || '' : optionColorOf(field, value));
          return element;
        };
        text.append(who, ` changed ${historyLabel(kind)} `);
        if (entry.old_value) text.append('from ', fieldPill(entry.old_value), ' ');
        text.append('to ', fieldPill(entry.new_value));
      } else {
        text.append(who, ` changed ${HISTORY_LABELS[kind] || kind} `);
        if (entry.old_value) text.append('from ', historyPill(entry.old_value), ' ');
        text.append('to ', historyPill(entry.new_value));
      }
    }
    const time = node('time', relativeTime(entry.changed_at));
    time.title = exactTime(entry.changed_at);
    text.append(' · ', time);
    item.append(text);
    // Admins and super-admins can delete single history entries.
    if (state.user.can_moderate && entry.id) {
      const remove = node('button', '×', 'nq-history-delete');
      remove.type = 'button';
      remove.title = 'Delete this history entry';
      remove.setAttribute('aria-label', 'Delete this history entry');
      remove.addEventListener('click', () => deleteHistory(
        `/api/non-qualified-calls/history/${entry.id}`, {method: 'DELETE'}, 'Delete this history entry? It cannot be recovered.',
      ));
      item.append(remove);
    }
    return item;
  };
  const confirmDelete = async (message) => (typeof window.showConfirmDialog === 'function'
    ? window.showConfirmDialog(message, {title: 'Delete history', confirmLabel: 'Delete'}) : window.confirm(message));
  const deleteHistory = async (url, init, message) => {
    if (!await confirmDelete(message)) return false;
    try {
      const result = await api(url, init);
      toast(`${number(result.deleted)} history entries deleted.`);
      if (state.detail) await openDetail(state.detail.call.call_key, {keepTab: true});
      loadCalls({quiet: true});
      return true;
    } catch (error) {
      toast(error.message, 'error');
      return false;
    }
  };
  const timelineComment = (comment) => {
    const item = node('li', undefined, `nq-event nq-event-comment${comment.deleted_at ? ' is-deleted' : ''}`);
    item.append(avatar(comment.created_by));
    const bubble = node('div', undefined, 'nq-comment');
    const head = node('header');
    const time = node('time', relativeTime(comment.created_at));
    time.title = exactTime(comment.created_at);
    head.append(node('strong', comment.created_by), time);
    if (comment.edited_at && !comment.deleted_at) {
      const edited = node('span', 'edited', 'nq-edited');
      edited.title = `Edited by ${comment.edited_by} · ${exactTime(comment.edited_at)}`;
      head.append(edited);
    }
    bubble.append(head);
    if (comment.deleted_at) {
      bubble.append(node('p', `Comment deleted by ${comment.deleted_by} · ${exactTime(comment.deleted_at)}`, 'nq-muted'));
    } else {
      const body = window.RichText.render(comment.body, {className: 'nq-comment-body'});
      bubble.append(body);
      if (canChangeComment(comment)) {
        const actions = node('div', undefined, 'nq-comment-actions');
        const edit = node('button', 'Edit', 'nq-link-action');
        const remove = node('button', 'Delete', 'nq-link-action is-danger');
        edit.type = remove.type = 'button';
        edit.addEventListener('click', () => editComment(comment, bubble, body, actions));
        remove.addEventListener('click', () => deleteComment(comment));
        actions.append(edit, remove);
        head.append(actions);
      }
    }
    item.append(bubble);
    return item;
  };
  const editComment = (comment, bubble, body, actions) => {
    actions.hidden = true;
    const editor = node('form', undefined, 'nq-comment-editor');
    const area = node('textarea');
    area.value = comment.body;
    area.rows = Math.min(10, Math.max(3, comment.body.split('\n').length + 1));
    area.maxLength = 5000;
    area.setAttribute('aria-label', 'Comment');
    const save = node('button', 'Save', 'nq-primary-action');
    const cancel = node('button', 'Cancel', 'nq-link-action');
    save.type = 'submit';
    cancel.type = 'button';
    const buttons = node('div', undefined, 'nq-composer-actions');
    buttons.append(cancel, save);
    editor.append(area, buttons);
    body.replaceWith(editor);
    // Edited as it reads (rich_text.js); Ctrl+Enter saves it.
    window.RichText.attach(area, {docClass: 'nq-comment-body', onSubmit: () => editor.requestSubmit()});
    area.focus();
    // The prompt for changes not saved yet saves or discards the edit too.
    editor.isChanged = () => area.value !== comment.body;
    editor.discard = () => { editor.replaceWith(body); actions.hidden = false; };
    editor.save = async () => {
      save.disabled = true;
      try {
        await api(`/api/non-qualified-calls/comments/${comment.id}`, {method: 'PATCH', body: JSON.stringify({body: area.value})});
        toast('Comment updated.');
        await openDetail(commentCallKey(), {keepTab: true});
        loadCalls({quiet: true});
        return true;
      } catch (error) {
        toast(error.message, 'error');
        save.disabled = false;
        return false;
      }
    };
    cancel.addEventListener('click', editor.discard);
    editor.addEventListener('submit', (event) => {
      event.preventDefault();
      editor.save();
    });
  };
  const commentCallKey = () => state.detail?.call.call_key;
  const deleteComment = async (comment) => {
    const accepted = typeof window.showConfirmDialog === 'function'
      ? await window.showConfirmDialog('Delete this comment? It stays in the call history with its author and time.', {title: 'Delete comment', confirmLabel: 'Delete'})
      : window.confirm('Delete this comment?');
    if (!accepted) return;
    try {
      await api(`/api/non-qualified-calls/comments/${comment.id}`, {method: 'DELETE'});
      toast('Comment deleted.');
      await openDetail(commentCallKey(), {keepTab: true});
      loadCalls({quiet: true});
    } catch (error) {
      toast(error.message, 'error');
    }
  };
  // The first list field of a phase section (Analysis, Implementation, Planning) tells the phase of the call.
  // The tab that shows a section.
  const tabOf = (sectionKey) => drawerTabs().find((group) => group.sections.some((section) => section.key === sectionKey))
    || {key: 'general', label: 'Activity'};
  // The fields of the analysts of a section: neither those of the follow-up or the NQ Prioritization nor the Priority, shown at
  // the top of the call.
  const analystFieldsOf = (key) => state.fields.filter((field) => field.section === key && !['tracking', 'priority'].includes(field.source)
    && !(field.key === 'priority' && field.source === 'user' && field.type === 'list'));
  // Shown in the header beside the JOIN_ID: the identifier of the analysis in the workbooks of the previous tool.
  const HEADER_FIELDS = ['unique_id'];
  // The values of the NQ Prioritization about the repeated issue of a call, on a row of their own in Prioritization Info.
  const REPETITION_REFS = ['repeated', 'repetitions', 'repeated_campaigns', 'place_label'];
  // The values of the NQ Prioritization that are the IDs of the groups of a call (Hotspot ID, Time-Window ID and Cluster ID).
  const GROUP_ID_REFS = ['hotspot_id', 'consecutive_id', 'cluster_id'];
  const phaseFields = () => PHASE_SECTIONS.map((key) => state.fields.find((field) => field.section === key && field.type === 'list'
    && ['user', 'derived'].includes(field.source))).filter(Boolean);
  const renderTracking = (call) => {
    const host = $('nq-drawer-tracking');
    const field = (kind, label) => {
      const wrapper = node('label', undefined, 'nq-tracking-field');
      wrapper.append(node('span', label));
      wrapper.append(state.user.can_edit ? trackingSelect(kind, call) : pill(kind, call[kind]));
      return wrapper;
    };
    const status = field('status', 'NQ Call Status');
    status.querySelector('span').append(' ', statusModeBadge(call));
    // The Priority of the call follows its status, chosen there like it.
    const priorityField = state.fields.find((item) => item.key === 'priority' && item.source === 'user' && item.type === 'list');
    let priority = null;
    if (priorityField) {
      const value = String(call.values?.priority || '');
      priority = node('label', undefined, 'nq-tracking-field nq-tracking-priority');
      priority.append(node('span', priorityField.label));
      if (state.user.can_edit) {
        const control = choiceControl({
          items: fieldChoices(priorityField, value), value, empty: 'Not set', label: `${priorityField.label} of the call`,
          onChange: (chosen) => patchCall(call, {fields: {priority: chosen}}, control, `${priorityField.label} updated.`),
          onAdd: listAdder(priorityField),
        });
        priority.append(control);
      } else {
        const shown = node('span', value || 'Not set', 'nq-pill');
        paintPill(shown, optionColorOf(priorityField, value));
        priority.append(shown);
      }
    }
    const updated = node('p', call.updated_by
      ? `Last follow-up by ${call.updated_by} · ${exactTime(call.updated_at)}` : 'Not followed up yet.', 'nq-tracking-note');
    const rootField = node('div', undefined, 'nq-tracking-field nq-tracking-root');
    const domain = call.root_domain ? node('span', call.root_domain, 'nq-domain-tag') : null;
    if (domain) domain.style.setProperty('--nq-section', domainColor(call.root_domain) || '#7b8790');
    const title = node('span', 'Root Category · Root Cause');
    if (domain) title.append(' ', domain);
    rootField.append(title, rootCauseControl(call));
    // The phases of the call, each in the colour of its section; a click opens its tab. The first one, RCA
    // Identification, is done once a root category or cause is selected.
    const phases = node('div', undefined, 'nq-phase-strip');
    const phaseCard = (tab, sectionColor, name, value, color, title, empty) => {
      if (phases.childElementCount) phases.append(node('span', '›', 'nq-phase-arrow'));
      const step = node('button', undefined, `nq-phase-step${value ? '' : ' is-empty'}`);
      step.type = 'button';
      step.style.setProperty('--nq-section', sectionColor);
      const valuePill = node('span', value || empty, 'nq-pill');
      paintPill(valuePill, color);
      if (!value) valuePill.classList.add('is-empty');
      step.append(node('span', name, 'nq-phase-name'), valuePill);
      step.title = `${title}: ${value || empty} — open ${tab.label}`;
      step.addEventListener('click', () => selectTab(tab.key));
      phases.append(step);
    };
    const phaseStep = (sectionKey, name, value, color, title, empty = 'Not started') => (
      phaseCard(tabOf(sectionKey), sectionOf(sectionKey).color, name, value, color, title, empty));
    if (state.sections.some((section) => section.key === 'rca')) {
      const identified = call.root_category || call.root_cause;
      const recommended = !identified && recommendationOf(call);
      phaseStep('rca', 'RCA Identification', identified, optionColor('root_category', call.root_category) || optionColor('root_cause', call.root_cause),
        'RCA Identification', recommended ? 'Recommended' : 'Not started');
    }
    // The Failure Map tells where the call failed (its place and the NQ calls there); Failure Details how many of its
    // fields are filled in.
    if (callMap) {
      const located = call.latitude !== null && call.latitude !== undefined;
      const repeated = Number(call.repetitions) > 1 ? ` (${number(call.repetitions)} Non-Qualified Calls of its operator there)` : '';
      phaseCard(FAILURE_MAP, FAILURE_MAP.color, FAILURE_MAP.label, call.place_label || (located ? 'Located' : ''), FAILURE_MAP.color,
        `Where the call failed${repeated}`, 'No position');
    }
    const detailFields = state.fields.filter((item) => item.section === 'failure_event' && item.source === 'user');
    if (detailFields.length && state.sections.some((section) => section.key === 'failure_event')) {
      const filled = detailFields.filter((item) => call.fields?.[item.key]).length;
      const progress = !filled ? '' : filled < detailFields.length ? `In progress · ${filled}/${detailFields.length}` : `Completed · ${filled}/${filled}`;
      phaseStep('failure_event', sectionOf('failure_event').label, progress, !filled ? '' : filled < detailFields.length ? '#F08A24' : '#2E8B57',
        `${filled} of the ${detailFields.length} fields of ${sectionOf('failure_event').label} filled in`);
    }
    phaseFields().forEach((phase) => {
      const value = String(call.values?.[phase.key] || '');
      phaseStep(phase.section, sectionOf(phase.section).label, value, optionColorOf(phase, value), phase.label);
    });
    // The phases in a subpanel of their own.
    const phasePanel = node('section', undefined, 'nq-phase-panel');
    phasePanel.setAttribute('aria-label', 'Phases of the call');
    phasePanel.append(node('span', 'Phases', 'nq-phase-panel-title'), phases);
    // The values of the NQ Prioritization of the call, read only, in a Prioritization Info subpanel above the phases (not in their tab),
    // but for the IDs of its groups, which its Groups in the header show.
    const infoFields = state.fields.filter((item) => item.source === 'priority' && !GROUP_ID_REFS.includes(item.source_ref));
    const infoPanel = node('section', undefined, 'nq-phase-panel nq-call-info-panel');
    infoPanel.setAttribute('aria-label', 'Prioritization information');
    const infoCard = (item) => {
      // A long value (the step, the KPIs lost) takes two cards' width.
      const value = call.values?.[item.key];
      const cell = node('div', undefined, `nq-call-info-item${String(value ?? '').length > 20 ? ' is-wide' : ''}`);
      if (item.description) cell.title = item.description;
      cell.append(node('span', item.label, 'nq-call-info-label'), readonlyValue(item, value));
      return cell;
    };
    // The repeated issue of the call (Repeated Issue, Repetitions, Repeated Campaigns, Repetition Place) together on a row of
    // its own, below the other values.
    const repeats = infoFields.filter((item) => REPETITION_REFS.includes(item.source_ref));
    const infoGrid = node('div', undefined, 'nq-call-info-grid');
    infoGrid.append(...infoFields.filter((item) => !repeats.includes(item)).map(infoCard));
    const repeatGrid = node('div', undefined, 'nq-call-info-grid nq-call-info-repeats');
    repeatGrid.append(...repeats.map(infoCard));
    infoPanel.append(node('span', 'Prioritization Info', 'nq-phase-panel-title'), ...[infoGrid, repeatGrid].filter((grid) => grid.childElementCount));
    // The fields of the analysts of General (Analyst, Reviewer…) follow the Assignee, saved as soon as they change like it.
    const generalFields = analystFieldsOf('general').filter((item) => !HEADER_FIELDS.includes(item.key)).map((item) => {
      const block = fieldBlock(item, call);
      block.classList.add('nq-tracking-field', 'nq-tracking-general');
      block.addEventListener('change', (event) => {
        const control = event.target.closest('[data-field-key]');
        if (!control || !state.user.can_edit || control.value === control.dataset.original) return;
        patchCall(call, {fields: {[control.dataset.fieldKey]: control.value}}, null, `${item.label} updated.`);
      });
      return block;
    });
    host.replaceChildren(status, ...(priority ? [priority] : []), field('team', 'Team'), field('assignee', 'Assignee'), ...generalFields, rootField,
      ...(infoFields.length ? [infoPanel] : []), ...(phases.childElementCount ? [phasePanel] : []), updated);
  };
  const DETAIL_FIELDS = [
    ['Service', 'service_label'], ['Result', 'result'], ['Operator', 'operator'], ['Vendor', 'vendor'], ['Campaign', 'campaign'],
    ['NR Mode', 'nr_mode'], ['Region', 'region'], ['City', 'city'], ['Technology', 'technology'], ['Test Name', 'test_name'],
    ['Session Type', 'session_type'], ['Direction', 'direction'], ['Start Time', 'start_time'], ['End Time', 'end_time'],
    ['Failure Phase', 'failure_phase'],
    ['Failure Technology', 'failure_technology'], ['Failure Classification', 'failure_classification'],
    ['Failure Category', 'failure_category'], ['Failure Subcategory', 'failure_subcategory'],
    ['Failure Comment', 'failure_comment'], ['Cell ID', 'cell_id'], ['Root Domain', 'root_domain'], ['Root Category', 'root_category'],
    ['Root Cause', 'root_cause'], ['JOIN_ID', 'join_id'], ['CDR', 'dataset_name'],
  ];
  const renderFields = () => {
    const filter = $('nq-field-search').value.trim().toLowerCase();
    const rows = (state.detail?.fields || []).filter(([name, value]) => !filter
      || name.toLowerCase().includes(filter) || String(value).toLowerCase().includes(filter));
    $('nq-fields').replaceChildren(...rows.map(([name, value]) => {
      const row = node('tr');
      row.append(node('th', name), node('td', value));
      return row;
    }));
    if (!rows.length) {
      const row = node('tr');
      const cell = node('td', state.detail?.fields?.length ? 'No field matches.' : 'The CDR row is no longer available.', 'nq-muted');
      cell.colSpan = 2;
      row.append(cell);
      $('nq-fields').append(row);
    }
  };
  // A long text read as bullets (rich_text.js): each line a bullet, nested as deep as it is indented, but for a title
  // (a short line ending with a colon, or followed by a list); and its Markdown: numbered lists, headings, bold,
  // italic, cards, code and dividers (------Jorge------).
  const bulletList = (text) => window.RichText.render(text, {implicitBullets: true, className: 'nq-bullets'});
  // How to write a long text: shown as it reads, in grey, while it is empty; never part of it.
  const LONG_TEXT_GUIDE = [
    'Heading ending with a colon, or followed by a list',
    '- Each line is a bullet',
    '  - Tab nests it in the line above',
    '1. Numbered steps, and 1.1. for their sub-steps',
    '**Bold**, *italic*, ==highlight==, `# heading` and `> [!TIP]` cards',
    '------ A name between dashes divides the text ------',
  ].join('\n');
  // A long text of the analysts is edited as it reads: a click places the caret in it, and its toolbar shows while it
  // has the focus (rich_text.js); the Markdown travels in its text area, saved with the other fields.
  const longTextInput = (field, value) => {
    const wrapper = node('div', undefined, 'nq-long-text');
    wrapper.dataset.longText = field.key;
    const editor = node('textarea');
    editor.rows = 8;
    editor.maxLength = 20000;
    editor.value = value;
    editor.dataset.fieldKey = field.key;
    editor.dataset.original = value;
    editor.setAttribute('aria-label', field.label);
    editor.placeholder = LONG_TEXT_GUIDE;
    if (!state.user.can_edit) {
      editor.hidden = true;
      editor.disabled = true;
      const view = node('div', undefined, 'nq-long-text-view');
      view.append(value.trim() ? bulletList(value) : node('span', '—', 'nq-muted'));
      wrapper.append(view, editor);
      wrapper.setValue = () => {};
      return wrapper;
    }
    wrapper.append(editor);
    const rich = window.RichText.attach(editor, {implicitBullets: true, docClass: 'nq-bullets', toolbar: 'focus', placeholder: LONG_TEXT_GUIDE, label: field.label});
    wrapper.setValue = (text) => {
      rich.setValue(text);
      editor.dispatchEvent(new Event('change', {bubbles: true}));
    };
    return wrapper;
  };
  // A field entered by the analysts, edited in its section and saved with the version of the call.
  const fieldInput = (field, value) => {
    let control;
    if (field.type === 'list' || field.type === 'yes_no') {
      // A list is chosen in the coloured picker; its value travels in a hidden input, saved with the others.
      const wrapper = node('div', undefined, 'nq-choice-field');
      const input = node('input');
      input.type = 'hidden';
      input.value = value;
      input.dataset.fieldKey = field.key;
      input.dataset.original = value;
      const changed = (chosen) => {
        input.value = chosen;
        input.dispatchEvent(new Event('change', {bubbles: true}));
      };
      const picker = choiceControl({items: fieldChoices(field, value), value, label: field.label, onChange: changed, onAdd: listAdder(field)});
      picker.disabled = !state.user.can_edit;
      wrapper.append(picker, input);
      wrapper.setValue = (chosen) => { picker.setValue(chosen); changed(chosen); };
      return wrapper;
    } else if (field.type === 'long_text') {
      return longTextInput(field, value);
    } else {
      control = node('input');
      control.type = field.type === 'number' ? 'number' : field.type === 'date' ? 'date' : 'text';
      if (field.type === 'number') control.step = 'any';
      if (field.type === 'text') control.maxLength = 300;
      control.value = value;
    }
    control.dataset.fieldKey = field.key;
    control.dataset.original = value;
    control.disabled = !state.user.can_edit;
    control.setAttribute('aria-label', field.label);
    return control;
  };
  // A field from the CDR, the Ericsson RCA, the follow-up or derived from the call: shown, never edited.
  const readonlyValue = (field, value) => {
    const box = node('div', undefined, 'nq-readonly-value');
    const text = value === null || value === undefined ? '' : String(value);
    if (isRuleField(field) && text) {
      box.append(ruleValue(field, text));
    } else if (['list', 'yes_no'].includes(field.type) && text) {
      const element = node('span', text, 'nq-pill');
      paintPill(element, field.type === 'yes_no' ? YES_NO_COLORS[text] || '' : optionColorOf(field, text));
      box.append(element);
    } else if (field.type === 'long_text' && text) {
      box.append(bulletList(text));
    } else {
      box.append(node('span', text || '—', text ? '' : 'nq-muted'));
    }
    return box;
  };
  const changedFields = (scope = drawer) => {
    const changes = {};
    scope.querySelectorAll('[data-field-key]').forEach((control) => {
      if (control.value !== control.dataset.original) changes[control.dataset.fieldKey] = control.value;
    });
    return changes;
  };
  // What a tab (or the whole call panel) has not saved yet: its edited fields and, in the Activity tab, the comment
  // being written and the comments being edited.
  const pendingChanges = (scope = drawer) => {
    const composerDraft = $('nq-comment-body');
    return {
      fields: Object.keys(changedFields(scope)).length,
      comment: scope.contains(composerDraft) && Boolean(composerDraft.value.trim()),
      edits: [...scope.querySelectorAll('.nq-comment-editor')].filter((editor) => editor.isChanged?.()),
    };
  };
  const describeChanges = ({fields, comment, edits}) => {
    const parts = [
      fields ? `${fields} field change${fields === 1 ? '' : 's'} not saved` : '',
      comment ? 'a comment not posted' : '',
      edits.length ? `${edits.length === 1 ? 'a comment edit' : `${edits.length} comment edits`} not saved` : '',
    ].filter(Boolean);
    return parts.length > 1 ? `${parts.slice(0, -1).join(', ')} and ${parts.at(-1)}` : parts[0] || '';
  };
  const saveChanges = async (pending) => {
    const call = state.detail?.call;
    if (!call) return false;
    if (pending.fields && !(await saveFields(call))) return false;
    for (const editor of pending.edits) {
      if (!(await editor.save())) return false;
    }
    return !pending.comment || await postComment();
  };
  const discardChanges = (pending) => {
    pending.edits.forEach((editor) => editor.discard());
    if (pending.comment) $('nq-comment-body').value = '';
    if (pending.fields && state.detail) renderSections(state.detail);
  };
  // Leaving a tab, the call or the panel with changes not saved yet asks first: save them, discard them or continue
  // editing (also Escape). True when the panel may go on.
  let settling = false;
  const settleChanges = async (scope, where) => {
    const pending = pendingChanges(scope);
    if (!pending.fields && !pending.comment && !pending.edits.length) return true;
    if (settling) return false;
    settling = true;
    try {
      const message = `${where} has ${describeChanges(pending)}.`;
      const choice = typeof window.showConfirmDialog === 'function'
        ? await window.showConfirmDialog(message, {title: 'Unsaved changes', confirmLabel: 'Save', secondaryLabel: 'Discard', cancelLabel: 'Continue Editing'})
        : (window.confirm(`${message} Discard them?`) ? 'secondary' : null);
      if (choice === 'secondary') {
        discardChanges(pending);
        return true;
      }
      return choice === 'confirm' && await saveChanges(pending);
    } finally {
      settling = false;
    }
  };
  const chooseTab = async (name) => {
    const current = drawer.querySelector('[data-nq-tab].is-active');
    const panel = current && current.dataset.nqTab !== name
      ? drawer.querySelector(`[data-nq-panel="${CSS.escape(current.dataset.nqTab)}"]`) : null;
    if (panel && !(await settleChanges(panel, current.dataset.label || 'This tab'))) return;
    selectTab(name);
  };
  const requestClose = async () => {
    if (await settleChanges(drawer, 'This call')) closeDrawer();
  };
  // Another call opens in the panel once the changes of this one are saved or discarded.
  const leaveDetail = () => settleChanges(drawer, 'This call');
  // Every section tells how many of the fields of the call are still unsaved.
  const syncUnsaved = () => {
    const count = Object.keys(changedFields()).length;
    drawer.querySelectorAll('.nq-section-form .nq-composer-note').forEach((note) => {
      note.textContent = count ? `${count} unsaved change${count === 1 ? '' : 's'} (Save keeps those of every section)` : '';
    });
    drawer.classList.toggle('has-unsaved', count > 0);
  };
  const fieldBlock = (field, call) => {
    const editable = field.source === 'user';
    // A long text is edited in place: a label would send its clicks to the hidden text area.
    const wrapper = node(editable && field.type !== 'long_text' ? 'label' : 'div', undefined, `nq-analysis-field is-${field.type}${editable ? '' : ' is-readonly'}`);
    // The name and its tags on one line (a long name is shortened, whole on hover), so every value of a row lines up.
    const title = node('span', undefined, 'nq-field-title');
    // The fields of the DT Analyzer RCA show their name without the source, which their tag names.
    const prefix = field.source === 'dta' ? `${SOURCE_TAGS.dta} ` : '';
    const name = node('span', prefix && field.label.startsWith(prefix) ? field.label.slice(prefix.length) : field.label, 'nq-field-name');
    name.title = field.label;
    title.append(name);
    if (!editable) title.append(node('small', SOURCE_TAGS[field.source] || field.source, `nq-source-tag is-${field.source}`));
    if (field.required_to_close) title.append(node('small', 'required to close', 'nq-required-tag'));
    if (field.description) wrapper.title = field.description;
    wrapper.append(title);
    if (!editable) {
      wrapper.append(readonlyValue(field, call.values?.[field.key]));
      return wrapper;
    }
    const value = call.fields?.[field.key] || '';
    const control = fieldInput(field, value);
    wrapper.append(control);
    // A value of the CDR proposed for the empty field (a list only proposes one of its values).
    let proposal = call.proposals?.[field.key];
    if (proposal && field.type === 'list') proposal = field.options.find((option) => option.name.toLowerCase() === proposal.toLowerCase())?.name;
    if (proposal && state.user.can_edit && !value) {
      const use = node('button', `Use the CDR value: ${proposal}`, 'nq-proposal');
      use.type = 'button';
      use.title = `Fill ${field.label} with the ${field.suggest_from} of the CDR; Save keeps it`;
      use.addEventListener('click', (event) => {
        event.preventDefault();
        if (control.setValue) control.setValue(proposal);
        else {
          control.value = proposal;
          control.dispatchEvent(new Event('change', {bubbles: true}));
        }
        use.remove();
      });
      wrapper.append(use);
    }
    return wrapper;
  };
  // True once the fields are saved.
  const saveFields = async (call, button) => {
    const changes = changedFields();
    if (!Object.keys(changes).length) { toast('Nothing to save.'); return true; }
    if (button) button.disabled = true;
    try {
      const updated = await api(`/api/non-qualified-calls/calls/${encodeURIComponent(call.call_key)}`, {
        method: 'PATCH', body: JSON.stringify({changes: {fields: changes}, version: call.version}),
      });
      renderDetail(updated);
      toast('Fields saved.');
      loadCalls({quiet: true});
      return true;
    } catch (error) {
      toast(error.message, 'error');
      return false;
    } finally {
      if (button) button.disabled = false;
    }
  };
  // The Root Cause Decision of the RCA section: the selected Root Category and Cause, the recommendation
  // merged from every source, and what each source (NetCheck, Ericsson RCA, DT Analyzer RCA, comments, previous
  // decisions) proposes.
  const rootDecisionCard = (call) => {
    const card = node('section', undefined, 'nq-decision');
    const head = node('header');
    head.append(node('h3', 'Root Cause Decision'), node('p', 'The Root Category and Root Cause of the call, chosen independently from the catalog. Accept the recommendation, use what one source proposes or choose any other value.', 'form-note'));
    const current = node('div', undefined, 'nq-decision-current');
    const pickers = node('div', undefined, 'nq-root-cell');
    if (state.user.can_edit) pickers.append(rootPickerButton('root_category', call), rootPickerButton('root_cause', call));
    else pickers.append(pill('root_category', call.root_category, NOT_CLASSIFIED), pill('root_cause', call.root_cause, NO_CAUSE));
    current.append(node('span', 'Selected', 'nq-decision-label'), pickers);
    if (call.root_domain) {
      const domain = node('span', call.root_domain, 'nq-domain-tag');
      domain.style.setProperty('--nq-section', domainColor(call.root_domain) || '#7b8790');
      domain.title = 'The domain of the root category (else of the root cause)';
      current.append(domain);
    }
    card.append(head, current);
    const recommendation = recommendationOf(call);
    if (recommendation) {
      const chosen = (recommendation.category || '') === (call.root_category || '') && (recommendation.cause || '') === (call.root_cause || '');
      const banner = node('div', undefined, `nq-recommendation is-${recommendation.confidence}${chosen ? ' is-chosen' : ''}`);
      const body = node('div');
      const values = node('p');
      values.append(node('strong', 'Recommended: '), recommendation.category ? pill('root_category', recommendation.category) : '',
        ' ', recommendation.cause ? pill('root_cause', recommendation.cause) : '');
      body.append(values, node('span', `${CONFIDENCE_LABELS[recommendation.confidence] || ''} · ${sourceNames(recommendation.sources)}`, 'nq-muted'));
      banner.append(node('span', '★', 'nq-recommendation-icon'), body);
      if (chosen) banner.append(node('span', 'Selected', 'nq-recommendation-state'));
      else if (state.user.can_edit) {
        const accept = node('button', 'Accept', 'nq-primary-action');
        accept.type = 'button';
        accept.addEventListener('click', () => patchCall(call, {root_category: recommendation.category, root_cause: recommendation.cause},
          accept, 'Recommendation accepted.'));
        banner.append(accept);
      }
      card.append(banner);
    }
    // What each source proposes, the DT Analyzer RCA first (the others keep their order).
    const sources = [...(call.rca_recommendation?.sources || [])].sort((a, b) => Number(b.source === 'dta') - Number(a.source === 'dta'));
    const cards = node('div', undefined, 'nq-source-cards');
    sources.forEach((source) => {
      const item = node('article', undefined, `nq-source-card is-${source.source}`);
      const title = node('header');
      // The names of the workspace (the RCA of the CDR after its provider) before those of the recommendation.
      const label = state.rcaSources[source.source] || source.label || source.source;
      title.append(node('strong', label));
      if (source.count) title.append(node('span', `${number(source.count)} earlier calls`, 'nq-muted'));
      item.append(title);
      if (source.source === 'dta') {
        // Its values are those of the catalog: the rule that found them (or what the analysts decided for its pattern) and why.
        if (source.learned) title.append(node('span', 'Learned from the analysts', 'nq-muted'));
        if (source.raw_category) item.append(node('p', `Rule: ${source.raw_category}`, 'nq-source-raw'));
        if (source.evidence) item.append(node('p', source.evidence, 'nq-source-evidence nq-muted'));
      } else if (source.raw_category || source.raw_cause) {
        item.append(node('p', [source.raw_category, source.raw_cause].filter(Boolean).join(' → '), 'nq-source-raw'));
      }
      const mapped = node('p', undefined, 'nq-source-mapped');
      if (source.category || source.cause) {
        if (source.category) mapped.append(pill('root_category', source.category));
        if (source.cause) mapped.append(' ', pill('root_cause', source.cause));
      } else {
        mapped.append(node('span', source.domain ? `${source.domain} (no category or cause matches)` : 'Not in the catalog yet: add keywords to map it', 'nq-muted'));
      }
      item.append(mapped);
      const changes = {};
      if (source.category) changes.root_category = source.category;
      if (source.cause) changes.root_cause = source.cause;
      const same = Object.entries(changes).every(([key, value]) => (call[key] || '') === value);
      if (state.user.can_edit && Object.keys(changes).length && !same) {
        const use = node('button', 'Use', 'nq-secondary-action');
        use.type = 'button';
        use.title = `Set ${Object.values(changes).join(' · ')}`;
        use.addEventListener('click', () => patchCall(call, changes, use, `${label} applied.`));
        item.append(use);
      }
      cards.append(item);
    });
    if (!sources.length) cards.append(node('p', 'No RCA source proposes a root cause for this call yet: import the Ericsson RCA results or choose the values by hand.', 'form-note'));
    card.append(node('h4', 'What each source proposes'), cards);
    return card;
  };
  // The other columns of the Ericsson RCA file, after the values of the RCA sources.
  const rcaExtrasCard = (call) => {
    const extras = Object.entries(call.rca || {}).filter(([key, value]) => key.startsWith('extra:') && value);
    if (!extras.length) return null;
    const card = node('section', undefined, 'nq-decision nq-rca-extra-card');
    const list = node('dl', undefined, 'nq-detail-grid nq-rca-extra');
    extras.forEach(([key, value]) => list.append(node('dt', key.slice(6)), node('dd', String(value))));
    card.append(node('h4', 'Other Ericsson RCA columns'), list);
    return card;
  };
  // The bar of Failure Details and Call Details that opens the larger map of the call (as the Map button of the header).
  const mapOpenBar = () => {
    const bar = node('div', undefined, 'nq-map-open-bar');
    const button = node('button', undefined, 'nq-secondary-action nq-map-open');
    button.type = 'button';
    button.dataset.nqMapOpen = '';
    button.title = 'Open the larger map of the area where the call failed';
    button.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0c0 5.4-6.5 11-6.5 11z"/><circle cx="12" cy="10" r="2.4"/></svg>';
    button.append(node('span', 'Map of the call'));
    bar.append(button, node('span', 'Its cells and sites, the sites and Non-Qualified Calls around and the RSRP / SINR of the tests around', 'form-note'));
    return bar;
  };
  // The fields of every section, each one in its tab; the tabs count the fields filled in.
  // The fields of every tab; a tab of several sections (Implementation & Planning) shows each one in its own subpanel.
  // The tabs count the fields filled in.
  const renderSections = (detail) => {
    const call = detail.call;
    drawerTabs().forEach((group) => {
      const host = group.key === 'general' ? $('nq-general-fields')
        : drawer.querySelector(`[data-nq-panel="${CSS.escape(group.key)}"] .nq-section-fields`);
      if (!host) return;
      // The fields of General show at the top of the call, beside the follow-up (see renderTracking).
      const ofSection = (key) => (key === 'general' ? [] : analystFieldsOf(key));
      const fields = group.sections.flatMap((section) => ofSection(section.key));
      const editable = fields.filter((field) => field.source === 'user');
      const parts = group.key === 'rca' ? [rootDecisionCard(call)] : [];
      if (fields.length) {
        const form = node('form', undefined, 'nq-analysis-form nq-section-form');
        if (group.key === 'rca') form.append(node('h4', 'Values of the RCA sources'));
        group.sections.forEach((section) => {
          const sectionFields = ofSection(section.key);
          if (!sectionFields.length) return;
          if (group.key === 'rca') {
            // The values of each RCA source (NetCheck, the Ericsson RCA, the analysts) start a row of their own.
            const runs = [];
            sectionFields.forEach((field) => {
              if (runs.at(-1)?.[0].source !== field.source) runs.push([]);
              runs.at(-1).push(field);
            });
            runs.forEach((run) => {
              const grid = node('div', undefined, 'nq-analysis-grid nq-rca-source-grid');
              grid.append(...run.map((field) => fieldBlock(field, call)));
              form.append(grid);
            });
            return;
          }
          const grid = node('div', undefined, 'nq-analysis-grid');
          grid.append(...sectionFields.map((field) => fieldBlock(field, call)));
          if (group.sections.length === 1) { form.append(grid); return; }
          const subpanel = node('section', undefined, 'nq-subpanel');
          subpanel.style.setProperty('--nq-section', section.color);
          subpanel.append(node('h4', section.label), grid);
          form.append(subpanel);
        });
        if (editable.length && state.user.can_edit) {
          const actions = node('div', undefined, 'nq-composer-actions');
          const save = node('button', `Save ${group.key === 'general' ? 'Fields' : group.label}`, 'nq-primary-action');
          save.type = 'submit';
          actions.append(node('span', '', 'nq-composer-note'), save);
          // In the RCA tab, Save closes the last row of values when it has room (beside the Initial Root Category and Cause).
          const lastRow = group.key === 'rca' ? [...form.querySelectorAll(':scope > .nq-rca-source-grid')].at(-1) : null;
          if (lastRow && lastRow.children.length % 4) {
            actions.classList.add('nq-rca-save');
            lastRow.append(actions);
          } else {
            form.append(actions);
          }
          form.onsubmit = (event) => { event.preventDefault(); saveFields(call, save); };
        }
        parts.push(form);
      } else if (!['general', 'rca'].includes(group.key)) {
        parts.push(node('p', state.user.can_edit ? 'No fields in this section yet: add them in NQ Analysis Configuration › Fields & Sections.'
          : 'No fields in this section.', 'form-note'));
      }
      if (group.key === 'rca') parts.push(rcaExtrasCard(call));
      // Failure Details opens the larger map of the area where the call failed.
      if (group.key === 'failure_event' && callMap) parts.unshift(mapOpenBar());
      host.replaceChildren(...parts.filter(Boolean));
      const badge = drawer.querySelector(`[data-nq-tab="${CSS.escape(group.key)}"] .nq-tab-badge`);
      if (!badge) return;
      let text = '';
      let title = '';
      let complete = false;
      if (group.key === 'rca') {
        complete = Boolean(call.root_category || call.root_cause);
        text = complete ? '✓' : recommendationOf(call) ? '★' : '';
        title = complete ? 'A root category or cause is selected' : 'A recommended root category and cause wait to be accepted';
      } else if (editable.length) {
        const filled = editable.filter((field) => call.fields?.[field.key]).length;
        text = `${filled}/${editable.length}`;
        title = `${filled} of the ${editable.length} fields the analysts fill in here have a value`;
        complete = filled === editable.length;
      }
      badge.textContent = text;
      badge.title = title;
      badge.hidden = !text;
      badge.classList.toggle('is-complete', complete);
    });
    syncUnsaved();
  };
  const renderSamples = (detail) => {
    const samples = detail.samples || [];
    $('nq-samples').hidden = !samples.length;
    $('nq-sample-list').replaceChildren(...samples.map((sample) => {
      const item = node('li');
      const button = node('button', undefined, 'nq-sample');
      button.type = 'button';
      button.title = 'Open this sample to follow it up';
      const head = node('span', undefined, 'nq-sample-head');
      head.append(node('strong', cdrTime(sample.start_time)), node('span', sample.result || '—', `nq-result ${resultClass(sample.result)}`));
      const failure = node('span', [sample.failure_classification, sample.failure_category].filter(Boolean).join(' · ') || 'Not classified',
        'nq-sample-failure');
      const tracking = node('span', undefined, 'nq-sample-tracking');
      tracking.append(pill('status', sample.status), node('span', rootLabel(sample.root_category, sample.root_cause), 'nq-muted'),
        node('span', `${number(sample.comment_count)} comments`, 'nq-muted'));
      button.append(head, failure, tracking);
      button.addEventListener('click', async () => { if (await leaveDetail()) openDetail(sample.call_key, {keepTab: false}); });
      item.append(button);
      return item;
    }));
  };
  const renderVersions = (detail) => {
    const versions = detail.versions || [];
    $('nq-versions').hidden = versions.length < 2;
    $('nq-version-list').replaceChildren(...versions.map((version) => {
      const item = node('li', undefined, `nq-version-item${version.dataset_id === Number(detail.call.dataset_id) ? ' is-shown' : ''}`);
      item.append(node('span', version.stage, `nq-stage nq-stage-${version.stage.toLowerCase()}`),
        node('strong', version.name || `CDR ${version.dataset_id}`));
      const facts = [version.data_date ? `Calls until ${cdrTime(version.data_date)}` : '',
        version.non_qualified ? [version.result, version.failure_classification].filter(Boolean).join(' · ') : 'Completed'];
      item.append(node('span', facts.filter(Boolean).join(' · '), 'nq-muted'));
      if (version.latest) item.append(node('span', 'Latest', 'nq-version is-latest'));
      if (version.dataset_id === Number(detail.call.dataset_id)) item.append(node('span', 'Shown', 'nq-version is-shown'));
      return item;
    }));
  };
  // The groups of the open call on one row when they fit (up to four columns); else the clusters start a row of their own,
  // below the hotspot and the run (laid out again whenever the width of the header changes).
  const layoutGroupChips = () => {
    const list = $('nq-drawer-groups-list');
    if (!list) return;
    list.querySelector('.nq-drawer-group-break')?.remove();
    const chips = [...list.querySelectorAll('.nq-drawer-group')];
    if (chips.length < 2 || chips.every((chip) => chip.offsetTop === chips[0].offsetTop)) return;
    const firstCluster = chips.findIndex((chip) => chip.dataset.kind.startsWith('cluster'));
    if (firstCluster > 0) list.insertBefore(node('span', undefined, 'nq-drawer-group-break'), chips[firstCluster]);
  };
  let groupsWidth = 0;
  if (window.ResizeObserver && $('nq-drawer-groups')) {
    new ResizeObserver(([entry]) => {
      const width = Math.round(entry.contentRect.width);
      if (width === groupsWidth) return;
      groupsWidth = width;
      layoutGroupChips();
    }).observe($('nq-drawer-groups'));
  }

  // Filter the list of calls by a group of the open call after confirming it, in place of the group filtered before (if any),
  // or remove its filter when the list already shows it.
  const filterByGroup = async (group, name, label) => {
    const active = (state.extraFilters[group.filter] || []).length === 1 && state.extraFilters[group.filter][0] === group.key;
    const others = GROUP_FILTERS.flatMap((field) => (state.extraFilters[field] || [])
      .filter((value) => !(field === group.filter && value === group.key)).map((value) => extraLabel(field, value)));
    const message = active ? `Remove the filter of ${name} from the list of calls?`
      : `Show in the list only the ${number(group.calls)} calls of ${name}?${others.length ? ` It replaces the filter of ${others.join(', ')}.` : ''}`;
    const accepted = typeof window.showConfirmDialog === 'function'
      ? await window.showConfirmDialog(message, {title: active ? 'Remove the group filter' : 'Filter by this group', confirmLabel: active ? 'Remove filter' : 'Filter'})
      : window.confirm(message);
    if (!accepted) return;
    state.hotspotLabels[group.key] = label;
    GROUP_FILTERS.forEach((field) => { delete state.extraFilters[field]; });
    if (!active) state.extraFilters[group.filter] = [group.key];
    markGroupChips();
    scheduleLoad();
  };

  function renderDetail(detail) {
    state.detail = detail;
    const call = detail.call;
    const eyebrow = [node('span', call.service_label, `nq-service nq-service-${call.service}`), ' ',
      node('span', call.result || '—', `nq-result ${resultClass(call.result)}`)];
    if (call.parent_key) {
      // A Speech sample: back to its call.
      const back = node('button', '‹ Back to the call', 'nq-link-action nq-back-to-call');
      back.type = 'button';
      back.addEventListener('click', async () => { if (await leaveDetail()) openDetail(call.parent_key, {keepTab: false}); });
      eyebrow.push(' ', node('span', `Sample ${call.sample_id || ''}`.trim(), 'nq-samples-badge'), ' ', back);
    }
    const badge = versionBadge(call);
    if (badge) eyebrow.push(' ', badge);
    $('nq-drawer-eyebrow').replaceChildren(...eyebrow);
    $('nq-drawer-title').textContent = [call.operator, call.campaign && campaignLabel(call.campaign)].filter(Boolean).join(' · ') || 'Call details';
    $('nq-drawer-meta').textContent = [cdrTime(call.start_time), call.city, call.technology, call.test_name].filter((value) => value && value !== '—').join(' · ');
    $('nq-drawer-join-id').textContent = call.join_id || '';
    $('nq-drawer-join').hidden = !call.join_id;
    // The Unique ID of the analysis in the workbooks of the previous tool, always beside the JOIN_ID that identifies the call
    // (— when it has none).
    const uniqueField = state.fields.find((item) => item.key === 'unique_id' && item.section === 'general');
    const uniqueId = uniqueField ? String(call.fields?.unique_id || call.values?.unique_id || '') : '';
    $('nq-drawer-unique-label').textContent = uniqueField?.label || 'Unique ID';
    $('nq-drawer-unique-id').textContent = uniqueId || '—';
    $('nq-drawer-unique').hidden = !uniqueField;
    $('nq-drawer-l3-ues').textContent = call.l3_log || '';
    $('nq-drawer-l3').hidden = !call.l3_log;
    // Its groups of 2 calls or more, each with what it is, its NR Mode, its ID in the NQ Hotspots, Time-Window & Clustered Issues
    // panel and its calls, and what it holds: its sites (spatial groups: clusters), its period (temporal groups: runs) or both
    // (hotspots). Its hotspot and its time-window issue keep to its NR Mode and campaign, its cluster to its NR Mode
    // (with the calls of its cluster of every NR Mode together when that holds more, as the panel shows the clusters without
    // one NR Mode filtered).
    // The hotspot and the run first, then the clusters (on a row of their own when they do not all fit on one, see
    // layoutGroupChips).
    const GROUP_ORDER = ['hotspot', 'run', 'cluster', 'cluster_all'];
    const groups = [...(call.groups || [])].sort((a, b) => GROUP_ORDER.indexOf(a.kind) - GROUP_ORDER.indexOf(b.kind));
    const cluster = groups.find((group) => group.kind === 'cluster');
    const mode = call.nr_mode || '';
    const NAMES = {hotspot: 'Hotspot', cluster: 'Cluster', cluster_all: 'Cluster', run: 'Time Window'};
    const TITLES = {
      hotspot: 'Failures of its operator, NR Mode and campaign linked to each other in time or distance',
      cluster: 'Calls of its operator and NR Mode failed close to each other or at the same site, in its campaign and those of the Cluster period',
      cluster_all: 'Its cluster with the calls of every NR Mode together, as the NQ Hotspots, Time-Window & Clustered Issues panel shows the clusters without one NR Mode filtered',
      run: 'Failures of its operator, NR Mode, campaign and drive one after another',
    };
    const chips = [];
    for (const group of groups) {
      const calls = `${number(group.calls)} call${group.calls === 1 ? '' : 's'}`;
      if (group.kind === 'cluster_all' && cluster?.id === group.id) {
        // The same first call: one chip with both counts.
        const chip = chips.find((item) => item.dataset.kind === 'cluster');
        chip.querySelector('.nq-drawer-group-head').append(` · ${number(group.calls)} with every NR Mode`);
        chip.title += `. ${TITLES.cluster_all}: ${calls}`;
        continue;
      }
      const chip = node('button', undefined, `nq-drawer-group is-${group.kind === 'cluster_all' ? 'cluster' : group.kind}`);
      chip.type = 'button';
      chip.dataset.kind = group.kind;
      chip.dataset.filter = group.filter;
      chip.dataset.key = group.key;
      const head = node('span', undefined, 'nq-drawer-group-head');
      head.append(node('b', `${NAMES[group.kind]} ${group.kind === 'cluster_all' ? 'every NR Mode' : mode}`.trim()), node('code', group.id), `· ${calls}`);
      chip.append(head);
      chip.title = `${TITLES[group.kind]}: ${calls}`;
      // Its sites with how many of its calls failed at each, the most first (the first 3, every one on hover), and its period.
      const sites = group.sites || [];
      if (group.kind !== 'run' && sites.length) {
        const shown = sites.slice(0, 3).map((site) => `${number(site.calls)} at ${site.label}`).join(' · ');
        chip.append(node('span', sites.length === 1 ? `At ${sites[0].label}`
          : `${number(sites.length)} sites: ${shown}${sites.length > 3 ? ` · +${number(sites.length - 3)} more` : ''}`, 'nq-drawer-group-line'));
        chip.title += `\n${sites.map((site) => `${site.label}: ${number(site.calls)} call${site.calls === 1 ? '' : 's'}`).join('\n')}`;
      }
      const period = ['hotspot', 'run'].includes(group.kind) ? groupPeriod(group) : '';
      if (period) chip.append(node('span', period, 'nq-drawer-group-line'));
      // A click filters the list of calls by the group (after confirming), as its ID does in the panel.
      const main = sites.length ? `${sites[0].label}${sites.length > 1 ? ` +${number(sites.length - 1)}` : ''}` : '';
      const label = [group.id, group.kind === 'run' ? '' : main, period].filter(Boolean).join(' · ');
      const name = `${NAMES[group.kind]} ${group.kind === 'cluster_all' ? 'of every NR Mode' : mode} ${group.id}`.replace(/\s+/g, ' ');
      chip.title += '\nClick to filter the list of calls by this group';
      chip.addEventListener('click', () => filterByGroup(group, name, label));
      chips.push(chip);
    }
    $('nq-drawer-groups-list').replaceChildren(...chips);
    $('nq-drawer-groups').hidden = !chips.length;
    markGroupChips();
    window.requestAnimationFrame(layoutGroupChips);
    renderDetailNav();
    renderTracking(call);
    renderSections(detail);
    renderSamples(detail);
    renderVersions(detail);
    const events = [
      ...detail.comments.map((comment) => ({time: comment.created_at, item: timelineComment(comment)})),
      ...detail.history.map((entry) => ({time: entry.changed_at, item: timelineChange(entry)})),
    ].sort((a, b) => String(a.time).localeCompare(String(b.time)));
    const timeline = $('nq-timeline');
    timeline.replaceChildren(...events.map((event) => event.item));
    $('nq-history-actions').hidden = !(state.user.can_moderate && detail.history.length);
    if (!events.length) timeline.append(node('li', state.user.can_edit ? 'No activity yet. Start the follow-up with a comment.' : 'No activity yet.', 'nq-empty-timeline'));
    const grid = $('nq-detail-grid');
    grid.replaceChildren();
    DETAIL_FIELDS.forEach(([label, key]) => {
      const value = key.endsWith('_time') ? cdrTime(call[key]) : key === 'campaign' && call[key] ? campaignLabel(call[key]) : call[key];
      if (!value || value === '—') return;
      grid.append(node('dt', label), node('dd', value));
    });
    if (call.latitude != null && call.longitude != null) {
      const link = node('a', `${Number(call.latitude).toFixed(5)}, ${Number(call.longitude).toFixed(5)}`);
      link.href = `https://www.openstreetmap.org/?mlat=${call.latitude}&mlon=${call.longitude}#map=16/${call.latitude}/${call.longitude}`;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      const value = node('dd');
      value.append(link);
      grid.append(node('dt', 'Location'), value);
    }
    renderFields();
    // The map shown follows the call (the arrows, a JOIN_ID or a call opened from the map).
    if ($('nq-drawer-map').classList.contains('is-active')) callMap?.show(call.call_key);
  }
  async function openDetail(callKey, {focusComposer = false, keepTab = false} = {}) {
    if (!callKey) return;
    drawer.classList.add('is-open');
    drawer.setAttribute('aria-hidden', 'false');
    backdrop.hidden = false;
    window.requestAnimationFrame(fitDrawer);
    if (!keepTab) selectTab('general');
    if (state.detail?.call.call_key !== callKey) {
      $('nq-timeline').replaceChildren(node('li', 'Loading…', 'nq-empty-timeline'));
      $('nq-comment-body').value = '';
    }
    try {
      const body = drawer.querySelector('.nq-drawer-body');
      const scroll = body.scrollTop;
      renderDetail(await api(`/api/non-qualified-calls/calls/${encodeURIComponent(callKey)}`));
      // The newest activity is at the bottom, next to the comment box; a panel that scrolls as one starts at its header.
      body.scrollTop = keepTab ? scroll : body.scrollHeight;
      if (!keepTab) drawer.scrollTop = 0;
      if (focusComposer && state.user.can_edit) $('nq-comment-body').focus({preventScroll: true});
    } catch (error) {
      toast(error.message, 'error');
      if (error.status === 404) closeDrawer();
    }
  }

  // The call panel goes through the calls of the list (its page and the pages around it), and to any call by its
  // JOIN_ID; changes not saved yet are confirmed first.
  const detailPlace = () => {
    const calls = state.result?.calls || [];
    return {calls, index: calls.findIndex((call) => call.call_key === state.detail?.call.call_key)};
  };
  function renderDetailNav() {
    const {index} = detailPlace();
    const result = state.result;
    const position = index < 0 ? 0 : (result.page - 1) * result.page_size + index + 1;
    $('nq-drawer-prev').disabled = index < 0 || position <= 1;
    $('nq-drawer-next').disabled = index < 0 || position >= result.total;
    const where = $('nq-drawer-position');
    where.textContent = index < 0 ? 'Not in the list' : `${number(position)} of ${number(result.total)}`;
    where.title = index < 0 ? 'The call is not on the page of the list shown: the arrows go through the calls of the list'
      : 'Position of the call in the list of the filters';
  }
  const stepDetail = async (offset) => {
    let {calls, index} = detailPlace();
    if (index < 0 || !(await leaveDetail())) return;
    let target = index + offset;
    if (target < 0 || target >= calls.length) {
      const page = state.result.page + offset;
      if (page < 1 || page > state.result.pages) return;
      state.page = page;
      await loadCalls({quiet: true});
      calls = state.result?.calls || [];
      target = offset < 0 ? calls.length - 1 : 0;
    }
    if (calls[target]) await openDetail(calls[target].call_key, {keepTab: true});
  };
  // The Map button shows the map of the call (the Failure Map step), and again the tab shown before it.
  $('nq-drawer-map').hidden = !callMap;
  if (callMap) $('nq-call-details-map').replaceChildren(mapOpenBar());
  drawer.addEventListener('click', (event) => {
    if (event.target.closest('[data-nq-map-open]') && state.detail) callMap?.openLarge(state.detail.call.call_key);
  });
  $('nq-drawer-map').addEventListener('click', () => {
    if ($('nq-drawer-map').classList.contains('is-active')) {
      chooseTab(tabBeforeMap);
      return;
    }
    chooseTab('map').then(() => { drawer.querySelector('.nq-drawer-body').scrollTop = 0; });
  });
  $('nq-drawer-prev').addEventListener('click', () => stepDetail(-1));
  $('nq-drawer-next').addEventListener('click', () => stepDetail(1));
  $('nq-drawer-find').addEventListener('submit', async (event) => {
    event.preventDefault();
    const input = $('nq-drawer-find-input');
    const joinId = input.value.trim();
    if (!joinId) return;
    try {
      const {calls} = await api('/api/non-qualified-calls/calls', {method: 'POST', body: JSON.stringify({filters: {join_id: [joinId]}, page_size: 25})});
      if (!calls.length) {
        toast(`No Non-Qualified Call has the JOIN_ID ${joinId}.`, 'error');
        return;
      }
      rememberJoinIds([joinId]);
      if (calls[0].call_key === state.detail?.call.call_key || !(await leaveDetail())) return;
      input.value = '';
      await openDetail(calls[0].call_key, {keepTab: true});
    } catch (error) {
      toast(error.message, 'error');
    }
  });

  // -- statuses and teams dialog --------------------------------------------------
  const optionsDialog = $('nq-options-dialog');
  const optionRow = (kind, item = {name: '', color: kind === 'statuses' ? '#6a63c9' : '#0f6f7d', closed: false}) => {
    const row = node('li', undefined, 'nq-option-row');
    row.dataset.previous = item.name || '';
    const color = node('input');
    color.type = 'color';
    color.value = item.color;
    color.setAttribute('aria-label', 'Colour');
    const name = node('input');
    name.type = 'text';
    name.value = item.name;
    name.maxLength = 60;
    name.placeholder = kind === 'statuses' ? 'Status name' : 'Team name';
    name.setAttribute('aria-label', name.placeholder);
    row.append(color, name);
    if (kind === 'statuses') {
      const closed = node('label', undefined, 'nq-option-closed');
      const box = node('input');
      box.type = 'checkbox';
      box.checked = Boolean(item.closed);
      closed.append(box, ' Closed');
      closed.title = 'Calls with this status count as closed';
      row.append(closed);
    } else {
      // The members of the team are chosen in their own dialog and saved with the statuses and teams.
      row.members = [...(item.members || [])];
      const members = node('button', membersLabel(row.members), 'nq-members-action');
      members.type = 'button';
      members.title = 'Choose the users of this team';
      members.addEventListener('click', () => openMembers(row));
      row.merged = [...(item.merged || [])];
      const merge = node('button', '⤳', 'nq-icon-action');
      merge.type = 'button';
      merge.title = 'Merge into another team: on Save its calls and members move there and it is removed';
      merge.setAttribute('aria-label', 'Merge into another team');
      merge.addEventListener('click', () => chooseMerge(row, merge));
      row.append(members, merge);
    }
    const move = (offset) => {
      const sibling = offset < 0 ? row.previousElementSibling : row.nextElementSibling;
      if (sibling) (offset < 0 ? sibling.before(row) : sibling.after(row));
    };
    [['↑', 'Move up', () => move(-1)], ['↓', 'Move down', () => move(1)], ['×', 'Remove', () => row.remove()]].forEach(([label, title, action]) => {
      const button = node('button', label, 'nq-icon-action');
      button.type = 'button';
      button.title = title;
      button.setAttribute('aria-label', title);
      button.addEventListener('click', action);
      row.append(button);
    });
    return row;
  };
  // The team of the row goes into the chosen one: the calls of a saved team follow it on Save, the members join the
  // target (a target open to everyone stays so) and the row leaves the list.
  const chooseMerge = (row, button) => {
    const nameOf = (other) => other.querySelector('input[type="text"]').value.trim();
    const targets = [...row.parentElement.querySelectorAll('.nq-option-row')].filter((other) => other !== row && nameOf(other));
    if (!targets.length) return;
    const select = node('select', undefined, 'nq-merge-select');
    select.setAttribute('aria-label', `Merge ${nameOf(row) || 'this team'} into`);
    select.append(new Option('Merge into…', ''), ...targets.map((other, index) => new Option(nameOf(other), String(index))));
    const restore = () => { if (select.isConnected) select.replaceWith(button); };
    select.addEventListener('blur', restore);
    select.addEventListener('change', () => {
      const target = targets[Number(select.value)];
      if (!select.value || !target) return restore();
      const name = nameOf(row) || 'The new team';
      target.merged = [...new Set([...(target.merged || []), ...(row.dataset.previous ? [row.dataset.previous] : []), ...(row.merged || [])])];
      if (target.members.length) {
        target.members = [...new Set([...target.members, ...row.members])];
        target.querySelector('.nq-members-action').textContent = membersLabel(target.members);
      }
      row.remove();
      $('nq-options-error').style.color = 'var(--nq-muted)';
      $('nq-options-error').textContent = `${name} will be merged into ${nameOf(target)}: Save moves its calls`
        + (target.members.length ? ' and members' : '') + ' there and removes it.';
    });
    button.replaceWith(select);
    select.focus();
  };
  const membersLabel = (members) => (members.length ? `${members.length} member${members.length === 1 ? '' : 's'}` : 'Everyone');
  const membersDialog = $('nq-members-dialog');
  let membersRow = null;
  const openMembers = (row) => {
    membersRow = row;
    const team = row.querySelector('input[type="text"]').value.trim() || 'the new team';
    $('nq-members-title').textContent = `Members of ${team}`;
    const chosen = new Set(row.members.map((member) => member.toLocaleLowerCase()));
    const users = [...new Set([...state.users, ...row.members])].sort((left, right) => left.localeCompare(right));
    $('nq-members-list').replaceChildren(...users.map((user) => {
      const item = node('li');
      const label = node('label', undefined, 'nq-members-option');
      const box = node('input');
      box.type = 'checkbox';
      box.value = user;
      box.checked = chosen.has(user.toLocaleLowerCase());
      label.append(box, node('span', user));
      item.append(label);
      return item;
    }));
    if (!users.length) $('nq-members-list').append(node('li', 'No users have access to this workspace.', 'form-note'));
    $('nq-members-search').value = '';
    membersDialog.showModal();
    $('nq-members-search').focus();
  };
  const openOptions = () => {
    ['statuses', 'teams'].forEach((kind) => {
      optionsDialog.querySelector(`[data-nq-options="${kind}"]`).replaceChildren(...state.options[kind].map((item) => optionRow(kind, item)));
    });
    $('nq-options-error').style.color = '';
    $('nq-options-error').textContent = '';
    optionsDialog.showModal();
  };
  const collectOptions = (kind) => [...optionsDialog.querySelectorAll(`[data-nq-options="${kind}"] .nq-option-row`)].map((row) => {
    const [color, name] = row.querySelectorAll('input');
    return {name: name.value.trim(), color: color.value, previous: row.dataset.previous,
      closed: Boolean(row.querySelector('.nq-option-closed input')?.checked),
      ...(kind === 'teams' ? {members: row.members || [], merged: row.merged || []} : {})};
  });

  // -- events -------------------------------------------------------------------
  // Each NR Mode has its own campaigns: choosing an NR Mode takes the campaigns of the other one out of Campaign.
  const keepCampaignsOfNrMode = async (nrModeSelect) => {
    const campaignSelect = root.querySelector('[data-nq-filter="campaign"]');
    const modes = [...nrModeSelect.selectedOptions].map((option) => option.value).filter(Boolean);
    if (!campaignSelect?.selectedOptions.length || !modes.length || modes.length === [...nrModeSelect.options].filter((option) => option.value).length) return;
    try {
      const {values} = await api('/api/non-qualified-calls/filters/values', {method: 'POST', body: JSON.stringify({filters: {nr_mode: modes}})});
      const campaigns = new Set(values?.campaign || []);
      const outside = [...campaignSelect.selectedOptions].filter((option) => !campaigns.has(option.value));
      if (!outside.length) return;
      outside.forEach((option) => { option.selected = false; });
      campaignSelect.dispatchEvent(new Event('multiselect:options-updated'));
      campaignSelect.dispatchEvent(new Event('change', {bubbles: true}));
    } catch (_error) { /* The Campaign filter keeps its values. */ }
  };
  root.addEventListener('change', (event) => {
    if (event.target.matches('[data-nq-filter="nr_mode"]')) void keepCampaignsOfNrMode(event.target);
    if (event.target.matches('[data-nq-filter], [data-nq-flag]')) scheduleLoad();
  });
  $('nq-search').addEventListener('input', debounce(() => { state.page = 1; loadCalls(); }, 400));
  root.querySelectorAll('[data-nq-typed-filter]').forEach((input) => input.addEventListener('input', debounce(() => { state.page = 1; loadCalls(); }, 400)));
  // -- the JOIN_IDs used last: both JOIN_ID searches offer the 10 latest below their field (shared, kept in this browser for
  // each workspace), narrowed while typing; a click, or the arrow keys and Enter, chooses one -----------------------------
  const RECENT_JOIN_IDS = `nq-recent-join-ids:${$('nq-table')?.dataset.workspace || ''}`;
  const RECENT_JOIN_LIMIT = 10;
  const joinTokens = (text) => String(text || '').split(/[\s,;]+/).map((value) => value.trim()).filter(Boolean);
  const recentJoinIds = () => {
    try {
      const kept = JSON.parse(window.localStorage.getItem(RECENT_JOIN_IDS) || '[]');
      return Array.isArray(kept) ? kept.filter((value) => typeof value === 'string' && value).slice(0, RECENT_JOIN_LIMIT) : [];
    } catch (_error) {
      return [];
    }
  };
  const rememberJoinIds = (values) => {
    const seen = new Set();
    const list = [...joinTokens(values.join(' ')), ...recentJoinIds()].filter((value) => {
      const key = value.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    }).slice(0, RECENT_JOIN_LIMIT);
    try {
      window.localStorage.setItem(RECENT_JOIN_IDS, JSON.stringify(list));
    } catch (_error) { /* Storage is optional. */ }
  };
  // The list below a JOIN_ID field: with ``multiple`` (several JOIN_IDs in the field) a JOIN_ID chosen takes the place of
  // the one being typed, else of the whole field; ``onPick`` then searches.
  const recentJoinMenu = (input, {multiple = false, onPick}) => {
    const anchor = node('span', undefined, 'nq-recent-joins-anchor');
    const menu = node('div', undefined, 'nq-recent-joins');
    menu.hidden = true;
    menu.setAttribute('role', 'listbox');
    menu.setAttribute('aria-label', 'Recent JOIN_IDs');
    input.replaceWith(anchor);
    anchor.append(input, menu);
    input.setAttribute('aria-autocomplete', 'list');
    let active = -1;
    const typing = () => Boolean(input.value) && !/[\s,;]$/.test(input.value);
    const typed = () => (multiple ? (typing() ? joinTokens(input.value).pop() || '' : '') : input.value.trim());
    const options = () => [...menu.querySelectorAll('.nq-recent-join')];
    const mark = (index) => {
      active = index;
      options().forEach((option, position) => option.classList.toggle('is-active', position === index));
    };
    const pick = (value) => {
      if (multiple) {
        const tokens = joinTokens(input.value);
        if (typing()) tokens.pop();
        input.value = [...tokens, value].join(', ');
      } else input.value = value;
      menu.hidden = true;
      onPick(value);
    };
    const render = () => {
      const term = typed().toLowerCase();
      // (Those already in the field are not offered again.)
      const chosen = new Set(multiple ? joinTokens(input.value).slice(0, typing() ? -1 : undefined).map((value) => value.toLowerCase()) : []);
      const shown = recentJoinIds().filter((value) => !chosen.has(value.toLowerCase()) && (!term || value.toLowerCase().includes(term)));
      menu.replaceChildren(node('p', 'Recent JOIN_IDs', 'nq-recent-joins-title'), ...shown.map((value) => {
        const option = node('button', value, 'nq-recent-join');
        option.type = 'button';
        option.setAttribute('role', 'option');
        option.addEventListener('click', (event) => {
          event.preventDefault();
          event.stopPropagation();
          pick(value);
        });
        return option;
      }));
      menu.hidden = !shown.length;
      active = -1;
    };
    // (A click in the list keeps the focus in the field.)
    menu.addEventListener('mousedown', (event) => event.preventDefault());
    input.addEventListener('focus', render);
    input.addEventListener('input', render);
    input.addEventListener('blur', () => { menu.hidden = true; });
    input.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        menu.hidden = true;
        return;
      }
      if (menu.hidden) {
        if (event.key === 'ArrowDown') render();
        return;
      }
      const count = options().length;
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        mark(event.key === 'ArrowDown' ? (active + 1) % count : (active <= 0 ? count - 1 : active - 1));
      } else if (event.key === 'Enter' && active >= 0) {
        event.preventDefault();
        pick(options()[active].textContent);
      }
    });
  };
  const joinFilter = root.querySelector('[data-nq-typed-filter="join_id"]');
  if (joinFilter) {
    recentJoinMenu(joinFilter, {multiple: true, onPick: () => {
      rememberJoinIds(joinTokens(joinFilter.value));
      state.page = 1;
      loadCalls();
    }});
    // The JOIN_IDs searched (Enter, or leaving the field) are remembered.
    joinFilter.addEventListener('change', () => rememberJoinIds(joinTokens(joinFilter.value)));
  }
  recentJoinMenu($('nq-drawer-find-input'), {onPick: () => $('nq-drawer-find').requestSubmit()});
  // Join ID sits in the title bar of its panel, which folds the panel: using it never folds it.
  root.querySelectorAll('[data-nq-join-search]').forEach((search) => {
    search.addEventListener('click', (event) => {
      event.preventDefault();
      search.querySelector('input')?.focus();
    });
    search.addEventListener('keyup', (event) => { if (event.key === ' ' || event.key === 'Enter') event.preventDefault(); });
  });
  $('nq-reset').addEventListener('click', () => {
    filterSelects().forEach((select) => { [...select.options].forEach((option) => { option.selected = false; }); select.dispatchEvent(new Event('change')); });
    // NQ Calls in Scope Only stays as it is: it chooses the calls of the module, above the filters.
    root.querySelectorAll('[data-nq-flag]:not([data-nq-flag="in_scope"])').forEach((box) => { box.checked = false; });
    root.querySelectorAll('[data-nq-typed-filter]').forEach((input) => { input.value = ''; });
    state.extraFilters = {};
    $('nq-search').value = '';
    scheduleLoad();
  });
  // Reindex: the calls of every CDR are indexed again in the background (their follow-up is kept); the page
  // reloads them once it ends.
  $('nq-refresh').addEventListener('click', async () => {
    $('nq-refresh').disabled = true;
    try {
      const {sync} = await api('/api/non-qualified-calls/reindex', {method: 'POST'});
      renderSync(sync);
    } catch (error) {
      $('nq-sync').textContent = error.message;
      $('nq-refresh').disabled = false;
    }
  });
  // Every page shows the rows of Rows, also the value a browser restores on reload.
  state.pageSize = Number($('nq-page-size').value) || state.pageSize;
  $('nq-page-size').addEventListener('change', (event) => { state.pageSize = Number(event.target.value) || 10; state.page = 1; loadCalls(); });
  // -- scroll position: a reload returns to where the page was being read (page_restore.js) -------------
  const VIEW_STORAGE = window.PageRestore.keyOf('nq-view', $('nq-table')?.dataset.workspace || '');
  let restoreTarget = 0;
  try {
    const stored = JSON.parse(window.sessionStorage.getItem(VIEW_STORAGE) || 'null');
    restoreTarget = window.PageRestore.reloaded() && stored && Number.isFinite(stored.scroll_y) ? stored.scroll_y : 0;
  } catch (_error) {
    restoreTarget = 0;
  }
  // While the page returns to the saved position, that position is kept as it is.
  let restoring = restoreTarget > 0;
  const rememberScroll = () => {
    try {
      window.sessionStorage.setItem(VIEW_STORAGE, JSON.stringify({scroll_y: restoring ? restoreTarget : Math.round(window.scrollY)}));
    } catch (_error) {
      // Without session storage a reload opens the page at its top.
    }
  };
  let scrollSaveTimer = null;
  window.addEventListener('scroll', () => {
    window.clearTimeout(scrollSaveTimer);
    scrollSaveTimer = window.setTimeout(rememberScroll, 120);
  }, {passive: true});
  window.addEventListener('pagehide', () => {
    rememberScroll();
    window.PageRestore.keepSnapshot(VIEW_STORAGE, restoring);
  });
  // Whether the calls or a panel are still being read: a section opened from a menu is kept at the top until they are all
  // drawn (app.js keepSectionInView), as a reload is held at its position (restoreScroll).
  window.pageSectionBusy = () => root.classList.contains('is-loading') || panelsLoading.size > 0;
  // The calls and then each panel on screen fill in, in any order: the page is held at the position until they are all
  // drawn and it stops growing.
  const restoreScroll = () => {
    if (!restoring) return;
    window.PageRestore.follow(restoreTarget, {busy: window.pageSectionBusy, onDone: () => {
      restoring = false;
      rememberScroll();
    }});
  };
  // -- the view kept in place while the calls reload --------------------------------------------------------------------
  // A change of the filters (or of the page, order or rows of the list) draws every panel on screen again: the panels above
  // the one in use grow or shrink, and the page would end up on another section (Safari has no scroll anchoring, and the
  // element Chrome anchors to is often drawn again). What was in use (where the filters were changed: the Join ID, a chip,
  // a card, a value of a chart) or else what was being read (a third of the way down the window) stays where it was until
  // the calls and every panel on screen are drawn, unless the page is scrolled meanwhile; its panel, if it gets shorter,
  // comes down so that no less of it is seen (a JOIN_ID leaves a few rows in the list).
  const VIEW_KEPT_MS = 300000;
  const VIEW_SETTLE_MS = 1200;
  let lastUse = null;
  ['pointerdown', 'focusin', 'input', 'change'].forEach((type) => document.addEventListener(type, (event) => {
    if (event.target instanceof Element && event.target.getClientRects().length) lastUse = {element: event.target, time: Date.now()};
  }, {capture: true, passive: true}));
  // The panel of the page that holds an element (none for the call panel, the dialogs and the lists over the page).
  const pagePanelOf = (element) => {
    let item = element;
    while (item && item.parentElement !== root) item = item.parentElement;
    return item?.matches('.panel') ? item : null;
  };
  // The element and its ancestors up to its panel, from the first that moves with the page: nothing stuck at the top of a
  // table or of the window, nor inside a list that scrolls on its own.
  const anchorChain = (element, panel) => {
    const chain = [];
    for (let item = element; item; item = item.parentElement) {
      const style = getComputedStyle(item);
      if (style.position === 'sticky' || style.position === 'fixed') chain.length = 0;
      else {
        if (['auto', 'scroll'].includes(style.overflowY) && item.scrollHeight > item.clientHeight + 1) chain.length = 0;
        chain.push(item);
      }
      if (item === panel) break;
    }
    return chain;
  };
  const viewAnchor = () => {
    const used = lastUse && Date.now() - lastUse.time < 10000 && lastUse.element.isConnected ? lastUse.element : null;
    if (used && pagePanelOf(used) && used.getClientRects().length) {
      const box = used.getBoundingClientRect();
      if (box.bottom > 0 && box.top < window.innerHeight) return used;
    }
    const area = root.getBoundingClientRect();
    const x = Math.min(Math.max(area.left + area.width / 2, 1), window.innerWidth - 1);
    const y = window.innerHeight / 3;
    return document.elementsFromPoint(x, y).find((element) => pagePanelOf(element))
      || [...root.children].find((element) => element.matches('.panel') && element.getClientRects().length && element.getBoundingClientRect().bottom > y)
      || null;
  };
  let stopKeepingView = null;
  function keepViewWhileLoading() {
    stopKeepingView?.();
    // A reload returning to its position (restoreScroll) and a section chosen in a menu (app.js) are followed instead.
    if (restoring || (typeof sectionKeptInView === 'function' && sectionKeptInView()) || typeof ResizeObserver !== 'function') return;
    const element = viewAnchor();
    const panel = element && pagePanelOf(element);
    if (!panel) return;
    const anchors = anchorChain(element, panel).map((item) => ({item, top: item.getBoundingClientRect().top}));
    if (!anchors.length) return;
    const dock = root.querySelector(':scope > .nq-view-dock');
    // How far down the window the panel reaches, up to the middle: a panel that gets shorter is never shown less.
    const reach = Math.min(window.innerHeight / 2, panel.getBoundingClientRect().bottom);
    let expected = window.scrollY;
    let stopped = false;
    const scrollBy = (top) => {
      window.scrollBy({left: 0, top, behavior: 'auto'});
      expected = window.scrollY;
    };
    const keep = () => {
      if (stopped) return;
      // Scrolled by hand (or to a section chosen meanwhile): the page stays where it is. A page left shorter only goes up to
      // its end.
      if (Math.abs(window.scrollY - expected) > 1) {
        const end = document.documentElement.scrollHeight - window.innerHeight;
        if (window.scrollY > expected || window.scrollY < end - 1) {
          stop();
          return;
        }
        expected = window.scrollY;
      }
      // The deepest element still on the page holds the view: those drawn again are left out.
      const index = anchors.findIndex(({item}) => item.isConnected && item.getClientRects().length);
      if (index < 0) return;
      const moved = anchors[index].item.getBoundingClientRect().top - anchors[index].top;
      if (Math.abs(moved) >= 1) scrollBy(moved);
      // Below the bar of the sections, once it stays at the top of the window.
      const clear = dock ? Math.min(dock.getBoundingClientRect().bottom, (parseFloat(getComputedStyle(dock).top) || 0) + dock.offsetHeight) : 0;
      const box = panel.getBoundingClientRect();
      if (box.top < clear && box.bottom < reach - 1) scrollBy(Math.max(box.top - clear, box.bottom - reach));
      // Its ancestors keep their place from now on, in case it is drawn again too.
      anchors.slice(index).forEach((anchor) => { anchor.top = anchor.item.getBoundingClientRect().top; });
    };
    // The parts above the element (the panels before its own, and what comes before it in its panel) are followed.
    const observer = new ResizeObserver(keep);
    for (let item = anchors[0].item; item && item !== document.body; item = item.parentElement) {
      observer.observe(item);
      for (let sibling = item.previousElementSibling; sibling; sibling = sibling.previousElementSibling) observer.observe(sibling);
    }
    const onScroll = () => { if (Math.abs(window.scrollY - expected) > 1) keep(); };
    const started = Date.now();
    let idleSince = 0;
    let timer = 0;
    // Also checked while the page draws no frames (a tab in the background), until it is drawn.
    const check = () => {
      keep();
      if (stopped) return;
      idleSince = window.pageSectionBusy() ? 0 : idleSince || Date.now();
      if (Date.now() - started > VIEW_KEPT_MS || (idleSince && Date.now() - idleSince > VIEW_SETTLE_MS)) stop();
      else timer = window.setTimeout(check, 250);
    };
    const stop = () => {
      stopped = true;
      observer.disconnect();
      window.clearTimeout(timer);
      window.removeEventListener('scroll', onScroll);
      document.documentElement.style.overflowAnchor = '';
      if (stopKeepingView === stop) stopKeepingView = null;
    };
    stopKeepingView = stop;
    // The browser's own scroll anchoring would move the page too.
    document.documentElement.style.overflowAnchor = 'none';
    window.addEventListener('scroll', onScroll, {passive: true});
    timer = window.setTimeout(check, 250);
  }
  $('nq-column-order-reset').addEventListener('click', async () => {
    if (!await saveColumnOrder(defaultColumnOrder())) return;
    applyColumnOrder();
    if (state.result) renderRows(state.result);
  });
  // Mine or Workspace: the layout the table shows (Mine starts as a copy of the workspace one).
  const showLayout = async (view) => {
    if (!state.layouts || view === state.layouts.view) return;
    try {
      const result = await api('/api/non-qualified-calls/table-layout/view', {method: 'PUT', body: JSON.stringify({view})});
      applyLayouts(result.table_layout);
      toast(view === 'mine' ? 'Your own layout is shown.' : 'The workspace layout is shown.');
      await loadState();
    } catch (error) {
      toast(error.message, 'error');
    }
  };
  document.querySelectorAll('[data-nq-layout-view]').forEach((button) => button.addEventListener('click', () => showLayout(button.dataset.nqLayoutView)));
  document.querySelector('[data-nq-layout-toggle]')?.addEventListener('click', () => showLayout(state.layouts?.view === 'mine' ? 'workspace' : 'mine'));
  $('nq-layout-publish')?.addEventListener('click', async (event) => {
    const button = event.currentTarget;
    const message = 'Save your layout (columns, Excel and column order) for the workspace? Every user who sees the workspace layout gets it.';
    const accepted = typeof window.showConfirmDialog === 'function'
      ? await window.showConfirmDialog(message, {title: 'Save for the Workspace', confirmLabel: 'Save'}) : window.confirm(message);
    if (!accepted) return;
    button.disabled = true;
    try {
      const result = await api('/api/non-qualified-calls/table-layout/publish', {method: 'POST'});
      applyLayouts(result.table_layout);
      toast('Your layout is now the layout of the workspace.');
      await loadState();
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      button.disabled = false;
    }
  });
  $('nq-table').querySelectorAll('[data-sort]').forEach(bindSort);
  $('nq-select-page')?.addEventListener('change', (event) => {
    (state.result?.calls || []).forEach((call) => {
      if (event.target.checked) state.selected.add(call.call_key); else state.selected.delete(call.call_key);
    });
    if (state.result) renderRows(state.result);
    renderBulk();
  });
  $('nq-bulk-clear')?.addEventListener('click', () => {
    state.selected.clear();
    if (state.result) renderRows(state.result);
    renderBulk();
  });
  const confirmBulk = async (message) => (typeof window.showConfirmDialog === 'function'
    ? window.showConfirmDialog(message, {title: 'Change selected calls', confirmLabel: 'Apply'}) : window.confirm(message));
  const bulkChange = async (changes) => {
    try {
      const result = await api('/api/non-qualified-calls/calls/bulk', {
        method: 'POST', body: JSON.stringify({call_keys: [...state.selected], changes}),
      });
      toast(`${number(result.changed)} calls updated.`);
      loadCalls({quiet: true});
    } catch (error) {
      toast(error.message, 'error');
    }
  };
  // Status (or back to the Status Rules), team, assignee, root category and root cause of the selected calls.
  [['nq-bulk-status', 'status'], ['nq-bulk-team', 'team'], ['nq-bulk-assignee', 'assignee'], ['nq-bulk-category', 'root_category'],
    ['nq-bulk-root', 'root_cause']].forEach(([id, kind]) => {
    $(id)?.addEventListener('change', async (event) => {
      const value = event.target.value;
      if (!value) return;
      event.target.value = '';
      const count = number(state.selected.size);
      if (value === AUTO_STATUS) {
        if (!await confirmBulk(`Give the status of the ${count} selected calls back to the Status Rules?`)) return;
        bulkChange({status_mode: 'auto'});
        return;
      }
      const target = value === state.unassigned ? '' : value;
      const empty = kind === 'root_cause' ? NO_CAUSE : kind === 'root_category' ? NOT_CLASSIFIED : 'Unassigned';
      if (!await confirmBulk(`Set ${HISTORY_LABELS[kind]} to “${target || empty}” for ${count} selected calls?`)) return;
      bulkChange({[kind]: target});
    });
  });
  $('nq-bulk-field')?.addEventListener('change', async (event) => {
    const value = event.target.value;
    if (!value) return;
    event.target.value = '';
    const [key, ...rest] = value.split(ROOT_SEPARATOR);
    const target = rest.join(ROOT_SEPARATOR);
    const label = historyLabel(`field:${key}`);
    if (!await confirmBulk(`Set ${label} to “${target || 'empty'}” for ${number(state.selected.size)} selected calls?`)) return;
    bulkChange({fields: {[key]: target}});
  });
  $('nq-history-clear').addEventListener('click', () => {
    const callKey = state.detail?.call.call_key;
    if (!callKey) return;
    deleteHistory('/api/non-qualified-calls/history/clear', {method: 'POST', body: JSON.stringify({call_keys: [callKey]})},
      'Delete the whole history of this call? Its status, team, assignee, root cause and comments stay; the history cannot be recovered.');
  });
  $('nq-bulk-history')?.addEventListener('click', async () => {
    const count = state.selected.size;
    await deleteHistory('/api/non-qualified-calls/history/clear', {method: 'POST', body: JSON.stringify({call_keys: [...state.selected]})},
      `Delete the whole history of the ${number(count)} selected calls? Their follow-up and comments stay; the history cannot be recovered.`);
  });
  $('nq-bulk-suggest')?.addEventListener('click', async () => {
    if (!await confirmBulk(`Give the ${number(state.selected.size)} selected calls without a root category and cause the ones recommended by their RCA sources?`)) return;
    bulkChange({apply_recommendation: true});
  });
  // Executive Summary and Progress Status of the filtered calls, as on the page, in PowerPoint or Word.
  document.querySelectorAll('[data-nq-document-export]').forEach((button) => button.addEventListener('click', async () => {
    const kind = button.dataset.nqDocumentExport;
    const label = kind === 'word' ? 'Word' : 'PowerPoint';
    button.disabled = true;
    globalThis.showLoadingOverlay?.(`Preparing the ${label} document`,
      `Preparing the Non-Qualified Calls ${label} with the Executive Summary, the Progress Status and the Root Cause Analysis of the filtered calls. The document downloads when it is ready.`);
    try {
      const response = await fetch(`/api/non-qualified-calls/export/${kind}`, {
        method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({filters: currentFilters(), granularity: $('nq-granularity').value, include_suggestions: false,
          show_not_classified: $('nq-root-show-unclassified').checked, show_empty: $('nq-life-show-empty').checked}),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(typeof payload.detail === 'string' ? payload.detail : `The ${label} export failed.`);
      }
      const disposition = response.headers.get('Content-Disposition') || '';
      const name = /filename="([^"]+)"/.exec(disposition)?.[1] || `Non-Qualified Calls.${kind === 'word' ? 'docx' : 'pptx'}`;
      const url = URL.createObjectURL(await response.blob());
      const link = node('a');
      link.href = url;
      link.download = name;
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      globalThis.hideLoadingOverlay?.();
      if (typeof globalThis.showInfoDialog === 'function') globalThis.showInfoDialog(error.message, {tone: 'error', title: 'The document could not be generated'});
      else toast(error.message, 'error');
    } finally {
      globalThis.hideLoadingOverlay?.();
      button.disabled = false;
    }
  }));
  $('nq-export').addEventListener('click', async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    const label = button.textContent;
    button.textContent = 'Exporting…';
    try {
      const response = await fetch('/api/non-qualified-calls/export', {
        method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({filters: currentFilters()}),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(typeof payload.detail === 'string' ? payload.detail : 'The export failed.');
      }
      const disposition = response.headers.get('Content-Disposition') || '';
      const name = /filename="([^"]+)"/.exec(disposition)?.[1] || 'non-qualified-calls.xlsx';
      const url = URL.createObjectURL(await response.blob());
      const link = node('a');
      link.href = url;
      link.download = name;
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      button.disabled = false;
      button.textContent = label;
    }
  });
  $('nq-drawer-close').addEventListener('click', requestClose);
  // Copies a text, also where the page is not a secure context (served by address on the network), which has no
  // clipboard API, or where the browser refuses it: a hidden field is selected and copied instead.
  const copyText = async (text) => {
    if (navigator.clipboard && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(text);
        return;
      } catch (_error) {
        // The hidden field below.
      }
    }
    const field = node('textarea');
    field.value = text;
    field.setAttribute('readonly', '');
    field.style.cssText = 'position: fixed; top: 0; left: 0; opacity: 0; font-size: 16px;';
    document.body.append(field);
    field.select();
    field.setSelectionRange(0, text.length);
    const copied = document.execCommand('copy');
    field.remove();
    if (!copied) throw new Error('The browser did not let the page copy the text.');
  };
  $('nq-drawer-join-copy').addEventListener('click', async (event) => {
    const button = event.currentTarget;
    try {
      await copyText($('nq-drawer-join-id').textContent);
      button.classList.add('is-copied');
      toast('JOIN_ID copied.');
      window.setTimeout(() => button.classList.remove('is-copied'), 1500);
    } catch (error) {
      toast(error.message, 'error');
    }
  });
  backdrop.addEventListener('click', requestClose);
  // Escape closes the panel, unless a dialog or the prompt for changes not saved yet is open (Escape closes that one).
  // The prompt opens once this key press is over, or the same Escape would close it.
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && drawer.classList.contains('is-open') && !document.querySelector('dialog[open]')
      && $('confirm-overlay')?.hidden !== false) window.setTimeout(requestClose);
  });
  drawer.querySelectorAll('[data-nq-tab]').forEach((tab) => tab.addEventListener('click', () => chooseTab(tab.dataset.nqTab)));
  ['input', 'change'].forEach((type) => drawer.addEventListener(type, (event) => {
    if (event.target.matches?.('[data-field-key]')) syncUnsaved();
  }));
  $('nq-field-search').addEventListener('input', renderFields);
  const composer = $('nq-composer');
  const composerBody = $('nq-comment-body');
  // True once the comment is posted.
  const postComment = async () => {
    const callKey = state.detail?.call.call_key;
    if (!callKey || !composerBody.value.trim()) return false;
    const submit = composer.querySelector('button[type="submit"]');
    submit.disabled = true;
    try {
      await api(`/api/non-qualified-calls/calls/${encodeURIComponent(callKey)}/comments`, {
        method: 'POST', body: JSON.stringify({body: composerBody.value}),
      });
      composerBody.value = '';
      $('nq-composer-note').textContent = '';
      await openDetail(callKey, {keepTab: true});
      const body = drawer.querySelector('.nq-drawer-body');
      body.scrollTop = body.scrollHeight;
      loadCalls({quiet: true});
      return true;
    } catch (error) {
      toast(error.message, 'error');
      return false;
    } finally {
      submit.disabled = false;
    }
  };
  composer.addEventListener('submit', (event) => { event.preventDefault(); postComment(); });
  // The comment is written as it reads (rich_text.js); Ctrl+Enter posts it.
  window.RichText.attach(composerBody, {docClass: 'nq-comment-body', onSubmit: postComment, label: 'Comment'});
  composerBody.addEventListener('input', () => {
    const length = composerBody.value.length;
    $('nq-composer-note').textContent = length > 4500 ? `${5000 - length} characters left` : '';
  });
  if (optionsDialog) {
    $('nq-options-open').addEventListener('click', openOptions);
    $('nq-options-cancel').addEventListener('click', () => optionsDialog.close());
    // Only the defaults, in their order and colours (a value with the same name keeps its calls and team members); the
    // others are removed on Save, which refuses a team still used or a status still set by hand.
    optionsDialog.querySelectorAll('[data-nq-option-defaults]').forEach((button) => {
      button.addEventListener('click', () => {
        const kind = button.dataset.nqOptionDefaults;
        const list = optionsDialog.querySelector(`[data-nq-options="${kind}"]`);
        const rows = [...list.querySelectorAll('.nq-option-row')];
        const nameOf = (row) => row.querySelector('input[type="text"]').value.trim().toLowerCase();
        const defaults = state.defaultOptions?.[kind] || [];
        let added = 0;
        const ordered = defaults.map((item) => {
          const existing = rows.find((row) => nameOf(row) === item.name.toLowerCase());
          if (!existing) {
            added += 1;
            return optionRow(kind, item);
          }
          existing.querySelector('input[type="text"]').value = item.name;
          existing.querySelector('input[type="color"]').value = item.color;
          const closed = existing.querySelector('.nq-option-closed input');
          if (closed) closed.checked = Boolean(item.closed);
          return existing;
        });
        const removed = rows.filter((row) => !ordered.includes(row)).map((row) => row.querySelector('input[type="text"]').value.trim());
        list.replaceChildren(...ordered);
        const label = kind === 'statuses' ? 'statuses' : 'teams';
        $('nq-options-error').style.color = 'var(--nq-muted)';
        $('nq-options-error').textContent = `The default ${label} are back (${added} added`
          + (removed.length ? `, ${removed.join(', ')} removed` : '') + '). Save to apply'
          + (kind === 'statuses' ? '; the automatic calls follow the Status Rules again (Default Rules in Status Rules puts the default rules back).' : '.');
      });
    });
    optionsDialog.querySelectorAll('[data-nq-option-add]').forEach((button) => {
      button.addEventListener('click', () => {
        const kind = button.dataset.nqOptionAdd;
        const row = optionRow(kind);
        optionsDialog.querySelector(`[data-nq-options="${kind}"]`).append(row);
        row.querySelector('input[type="text"]').focus();
      });
    });
    $('nq-members-search').addEventListener('input', () => {
      const query = $('nq-members-search').value.trim().toLocaleLowerCase();
      $('nq-members-list').querySelectorAll('li').forEach((item) => {
        item.hidden = Boolean(query) && !item.textContent.toLocaleLowerCase().includes(query);
      });
    });
    $('nq-members-toggle').addEventListener('click', () => {
      const listed = [...$('nq-members-list').querySelectorAll('li:not([hidden]) input')];
      const select = listed.some((box) => !box.checked);
      listed.forEach((box) => { box.checked = select; });
    });
    $('nq-members-cancel').addEventListener('click', () => membersDialog.close());
    $('nq-members-form').addEventListener('submit', () => {
      if (!membersRow) return;
      membersRow.members = [...$('nq-members-list').querySelectorAll('input:checked')].map((box) => box.value);
      membersRow.querySelector('.nq-members-action').textContent = membersLabel(membersRow.members);
    });
    $('nq-options-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const save = $('nq-options-save');
      save.disabled = true;
      try {
        const payload = await api('/api/non-qualified-calls/options', {
          method: 'PUT', body: JSON.stringify({statuses: collectOptions('statuses'), teams: collectOptions('teams')}),
        });
        optionsDialog.close();
        toast('Statuses and teams saved.');
        await loadState();
        if (payload && state.detail) openDetail(state.detail.call.call_key, {keepTab: true});
      } catch (error) {
        $('nq-options-error').style.color = '';
        $('nq-options-error').textContent = error.message;
      } finally {
        save.disabled = false;
      }
    });
  }
  // -- root causes dialog ----------------------------------------------------------
  const rootDialog = $('nq-root-dialog');
  // The suggestion rule in words, as configured for the workspace.
  const ruleText = (rule) => {
    const names = (fields) => fields.map((field) => state.ruleFields[field] || field).join(', ') || 'no field';
    const steps = [];
    if (rule.domain_fields.length) steps.push(`a domain keyword in ${names(rule.domain_fields)} chooses the domain`);
    if (rule.cause_fields.length) {
      steps.push(`a cause keyword in ${names(rule.cause_fields)} chooses the cause${rule.domain_fields.length
        ? (rule.causes_in_domain ? ', among the causes of that domain (or of every domain when none matched)' : ', among every cause') : ''}`);
    }
    if (rule.comments) steps.push(`when the cause is still unresolved, the comments of the call are read the same way${rule.comment_domain ? ', and can also choose the domain' : ''}`);
    const order = 'Domains and causes are tried from top to bottom, so their order sets the priority.';
    const match = rule.match === 'text' ? 'Keywords match any part of the text' : 'Keywords match whole words or phrases';
    return `How a root cause is suggested: ${steps.map((step, index) => `${index + 1}) ${step}`).join('; ')}. ${order} ${match}, separated by commas and ignoring case and underscores.`;
  };
  const iconButtons = (row, item, onRemove) => {
    const move = (offset) => {
      const sibling = offset < 0 ? item.previousElementSibling : item.nextElementSibling;
      if (sibling) (offset < 0 ? sibling.before(item) : sibling.after(item));
    };
    [['↑', 'Move up', () => move(-1)], ['↓', 'Move down', () => move(1)], ['×', 'Remove', onRemove]].forEach(([label, title, action]) => {
      const button = node('button', label, 'nq-icon-action');
      button.type = 'button';
      button.title = title;
      button.setAttribute('aria-label', title);
      button.addEventListener('click', action);
      row.append(button);
    });
  };
  const textInput = (value, placeholder, className = '') => {
    const input = node('input', undefined, className);
    input.type = 'text';
    input.value = value || '';
    input.placeholder = placeholder;
    input.setAttribute('aria-label', placeholder);
    return input;
  };
  // The domains of the catalog being edited, with the name each one had when the dialog opened.
  const catalogDomains = () => [...$('nq-root-domains').children].map((row) => ({
    name: row.querySelector('.nq-root-name').value.trim(), color: row.querySelector('input[type="color"]').value,
    keywords: keywordList(row.querySelector('.nq-root-keywords').value),
  })).filter((domain) => domain.name);
  // Keywords as the catalog matches them: lower case, underscores as spaces, whole words, "a+b" needing both.
  const keywordText = (value) => String(value || '').replace(/[_\u00a0]/g, ' ').replace(/\s+/g, ' ').trim().toLowerCase();
  const keywordList = (value) => String(value || '').split(/[,;\n]/).map((keyword) => keyword.split('+').map(keywordText))
    .filter((parts) => parts.every(Boolean)).map((parts) => parts.join('+'));
  const wordFound = (part, text) => text.includes(part)
    && new RegExp(`(?<![a-z0-9])${part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?![a-z0-9])`).test(text);
  const keywordFound = (keywords, text) => Boolean(text) && keywords.some((keyword) => keyword.split('+').every((part) => wordFound(part, text)));
  // The domain of a root category or cause row without a domain chosen by hand: for a cause, that of the root category
  // it is mapped to; else the first domain whose keywords appear in its name or keywords.
  const keywordDomain = (row) => {
    const text = keywordText([row.querySelector('.nq-root-name').value, ...keywordList(row.querySelector('.nq-root-keywords').value)].join(' | '));
    return catalogDomains().find((domain) => keywordFound(domain.keywords, text))?.name || '';
  };
  const categoryRow = (name) => [...$('nq-root-categories').children]
    .find((row) => name && row.querySelector('.nq-root-name').value.trim().toLowerCase() === name.toLowerCase());
  const automaticDomain = (row) => {
    const category = row.closest('#nq-root-causes') ? categoryRow(row.querySelector('.nq-category-select')?.value || '') : null;
    if (category) {
      const domain = category.querySelector('.nq-domain-select').value || keywordDomain(category);
      if (domain) return {domain, from: 'category'};
    }
    const domain = keywordDomain(row);
    return {domain, from: domain ? 'keywords' : ''};
  };
  // A select of the domains, painted in the colour of the domain of the row: the one chosen, or Auto (its automatic one).
  const domainSelect = (current, row) => {
    const select = node('select', undefined, 'nq-domain-select nq-pill-select');
    select.setAttribute('aria-label', 'Domain');
    select.dataset.current = current || '';
    select.source = row;
    const paint = () => {
      const automatic = select.value ? null : automaticDomain(select.source);
      if (automatic) {
        select.options[0].textContent = automatic.domain ? `Auto · ${automatic.domain}` : 'Auto · no domain';
        select.title = automatic.domain ? `Automatic: from the ${automatic.from === 'category' ? 'root category of the cause' : 'keywords of the domains'}`
          : 'Automatic: no domain keyword appears in its name or keywords';
      } else {
        select.options[0].textContent = 'Auto';
        select.title = 'Chosen by hand: the keywords are not used';
      }
      paintPill(select, catalogDomains().find((domain) => domain.name === (select.value || automatic?.domain))?.color || '');
    };
    select.paint = paint;
    select.addEventListener('change', () => { select.dataset.current = select.value; refreshAutomaticDomains(); });
    select.refresh = () => {
      const names = catalogDomains().map((domain) => domain.name);
      const value = select.dataset.current;
      select.replaceChildren(node('option', 'Auto'), ...names.map((name) => {
        const option = node('option', name);
        option.value = name;
        return option;
      }));
      select.options[0].value = '';
      select.value = names.includes(value) ? value : '';
      paint();
    };
    return select;
  };
  // The root category a cause is mapped to.
  const categorySelect = (current) => {
    const select = node('select', undefined, 'nq-category-select nq-pill-select');
    select.setAttribute('aria-label', 'Root category');
    select.dataset.current = current || '';
    select.addEventListener('change', () => { select.dataset.current = select.value; refreshAutomaticDomains(); });
    select.refresh = () => {
      const names = [...$('nq-root-categories').children].map((row) => row.querySelector('.nq-root-name').value.trim()).filter(Boolean);
      const value = select.dataset.current;
      select.replaceChildren(node('option', 'No root category'), ...names.map((name) => {
        const option = node('option', name);
        option.value = name;
        return option;
      }));
      select.options[0].value = '';
      select.value = names.find((name) => name.toLowerCase() === value.toLowerCase()) || '';
      select.dataset.current = select.value;
    };
    return select;
  };
  const refreshAutomaticDomains = () => rootDialog.querySelectorAll('.nq-domain-select').forEach((select) => select.paint?.());
  const refreshDomainSelects = () => {
    rootDialog.querySelectorAll('.nq-category-select').forEach((select) => select.refresh());
    rootDialog.querySelectorAll('.nq-domain-select').forEach((select) => select.refresh());
  };
  // A value the DT Analyzer RCA rules give (state.rootCauses.dta_rules) cannot be removed, nor a root category or cause
  // renamed, until the rules change: the DT tag that replaces its remove button says which rules give it.
  const lockByDtaRules = (row, kind, name) => {
    const key = String(name || '').trim().toLowerCase();
    const rules = Object.entries(state.rootCauses?.dta_rules?.[kind] || {}).find(([value]) => key && value.toLowerCase() === key)?.[1] || [];
    if (!rules.length) return;
    const given = `Given by the DT Analyzer RCA rule${rules.length > 1 ? 's' : ''} ${rules.join(', ')}: change `
      + `${rules.length > 1 ? 'those rules' : 'the rule'} in DT Analyzer RCA Rules to ${kind === 'domains' ? 'remove' : 'rename or remove'} it.`;
    if (kind !== 'domains') {
      const input = row.querySelector('.nq-root-name');
      input.readOnly = true;
      input.title = given;
    }
    const tag = node('span', 'DT', 'nq-source-tag is-dta nq-dta-lock');
    tag.title = given;
    tag.setAttribute('aria-label', given);
    row.querySelector('.nq-icon-action[aria-label="Remove"]').replaceWith(tag);
  };
  const domainRow = (domain = {name: '', color: '#6a63c9', keywords: []}) => {
    const row = node('li', undefined, 'nq-option-row nq-catalog-row');
    row.dataset.previous = domain.name || '';
    row.dataset.current = domain.name || '';
    const color = node('input');
    color.type = 'color';
    color.value = domain.color || '#6a63c9';
    color.setAttribute('aria-label', 'Colour');
    const name = textInput(domain.name, 'Domain name', 'nq-root-name');
    // Renaming a domain renames it in the categories and causes of the dialog.
    name.addEventListener('change', () => {
      const before = row.dataset.current;
      const after = name.value.trim();
      rootDialog.querySelectorAll('.nq-domain-select').forEach((select) => { if (before && select.dataset.current === before) select.dataset.current = after; });
      row.dataset.current = after;
      refreshDomainSelects();
    });
    color.addEventListener('input', refreshDomainSelects);
    row.append(color, name, textInput((domain.keywords || []).join(', '), 'Keywords', 'nq-root-keywords'));
    iconButtons(row, row, () => { row.remove(); refreshDomainSelects(); countCatalog(); });
    lockByDtaRules(row, 'domains', domain.name);
    return row;
  };
  // A root category or cause: its name, its domain (Auto, or chosen by hand) and its keywords; a cause also the root
  // category it is mapped to.
  const entryRow = (kind, item = {name: '', domain: '', keywords: []}) => {
    const row = node('li', undefined, 'nq-option-row nq-catalog-row');
    row.dataset.previous = item.name || '';
    row.dataset.current = item.name || '';
    const name = textInput(item.name, kind === 'categories' ? 'Root category name' : 'Root cause name', 'nq-root-name');
    const select = domainSelect(item.manual_domain ?? item.domain, row);
    if (kind === 'categories') {
      // Renaming a category renames it in the causes mapped to it.
      name.addEventListener('change', () => {
        const before = row.dataset.current;
        const after = name.value.trim();
        rootDialog.querySelectorAll('.nq-category-select').forEach((other) => {
          if (before && other.dataset.current.toLowerCase() === before.toLowerCase()) other.dataset.current = after;
        });
        row.dataset.current = after;
        refreshDomainSelects();
      });
      row.append(name, select);
    } else {
      row.append(name, categorySelect(item.category || ''), select);
    }
    row.append(textInput((item.keywords || []).join(', '), 'Keywords', 'nq-root-keywords'));
    iconButtons(row, row, () => { row.remove(); refreshDomainSelects(); countCatalog(); });
    lockByDtaRules(row, kind, item.name);
    return row;
  };
  // Whether Default Catalog was used since the dialog opened (App Events says so).
  let catalogDefaults = false;
  const saveCatalog = () => api('/api/non-qualified-calls/root-causes', {
    method: 'PUT', body: JSON.stringify({domains: collectCatalogRows('domains'), categories: collectCatalogRows('categories'),
      causes: collectCatalogRows('causes'), require_to_close: $('nq-root-require').checked, defaults: catalogDefaults}),
  });
  // Saves the catalog, then gives the calls with a root cause and no root category the category of their cause.
  const applyCauseCategories = async (button) => {
    const status = $('nq-root-error');
    button.disabled = true;
    try {
      const saved = await saveCatalog();
      state.rootCauses = {...state.rootCauses, ...saved};
      fillCatalog(state.rootCauses);
      renderMapping();
      const preview = await api('/api/non-qualified-calls/root-causes/apply-categories', {method: 'POST', body: JSON.stringify({preview: true})});
      status.style.color = 'var(--nq-muted)';
      if (!preview.calls) {
        status.textContent = 'The catalog is saved; no call has a root cause mapped to a category and no root category.';
        return;
      }
      const one = preview.calls === 1;
      const message = `${number(preview.calls)} call${one ? '' : 's'} with a root cause and no root category will take the category `
        + `of ${one ? 'its' : 'their'} cause. Continue?`;
      const accepted = typeof window.showConfirmDialog === 'function'
        ? await window.showConfirmDialog(message, {title: 'Apply to Calls', confirmLabel: 'Apply'}) : window.confirm(message);
      if (!accepted) {
        status.textContent = 'The catalog is saved; the calls are unchanged.';
        return;
      }
      const result = await api('/api/non-qualified-calls/root-causes/apply-categories', {method: 'POST', body: JSON.stringify({preview: false})});
      status.textContent = `${number(result.calls)} call${result.calls === 1 ? ' took the root category of its' : 's took the root category of their'} cause.`;
      toast(status.textContent);
      await loadState();
    } catch (error) {
      status.style.color = '';
      status.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  };
  const CATALOG_LISTS = {domains: 'nq-root-domains', categories: 'nq-root-categories', causes: 'nq-root-causes', mapping: 'nq-root-mapping'};
  const CATALOG_ADD = {domains: 'Add Domain', categories: 'Add Root Category', causes: 'Add Root Cause', mapping: ''};
  let catalogTab = 'domains';
  const countCatalog = () => rootDialog.querySelectorAll('[data-nq-catalog-tab]').forEach((tab) => {
    const kind = tab.dataset.nqCatalogTab;
    tab.querySelector('small').textContent = kind === 'mapping'
      ? `(${[...$('nq-root-causes').querySelectorAll('.nq-category-select')].filter((select) => select.value).length}/${$('nq-root-causes').children.length})`
      : `(${$(CATALOG_LISTS[kind]).children.length})`;
  });
  // Mapping: one table with every root cause, its root category and its domain, and one with every root category and
  // its domain. Its lists change the rows of the Root Causes and Root Categories tabs.
  const mappingSelect = (source) => {
    const proxy = source.classList.contains('nq-category-select') ? categorySelect(source.dataset.current) : domainSelect(source.dataset.current, source.source);
    proxy.refresh();
    proxy.addEventListener('change', () => {
      source.value = proxy.value;
      source.dataset.current = proxy.value;
      refreshAutomaticDomains();
      countCatalog();
    });
    return proxy;
  };
  const renderMapping = () => {
    const table = (headers, rows) => {
      const element = node('table', undefined, 'nq-mapping-table');
      const head = node('tr');
      headers.forEach((header) => head.append(node('th', header)));
      element.append(node('thead'), node('tbody'));
      element.tHead.append(head);
      rows.forEach((row) => element.tBodies[0].append(row));
      return element;
    };
    const line = (row, controls) => {
      const element = node('tr');
      const name = row.querySelector('.nq-root-name').value.trim();
      element.dataset.name = name;
      element.append(node('td', name || '(no name)', 'nq-mapping-name'), ...controls.map((control) => {
        const cell = node('td');
        cell.append(mappingSelect(control));
        return cell;
      }));
      return element;
    };
    const apply = node('button', 'Apply to Calls', 'nq-secondary-action');
    apply.type = 'button';
    apply.title = 'Save the catalog and give the calls with a root cause and no root category the category of their cause';
    apply.addEventListener('click', () => applyCauseCategories(apply));
    const intro = node('div', undefined, 'nq-mapping-intro');
    intro.append(node('p', 'Map each root cause to its root category and domain. Auto takes, for a cause, the domain of its root category, '
      + 'else the domain whose keywords appear in its name or keywords; a domain chosen here ignores the keywords. Choosing a '
      + 'cause for a call without root category gives it the category of the cause; Apply to Calls gives it to the calls that '
      + 'already have a cause and no category.', 'form-note'), apply);
    $('nq-root-mapping').replaceChildren(
      intro,
      table(['Root Cause', 'Root Category', 'Domain'], [...$('nq-root-causes').children]
        .map((row) => line(row, [row.querySelector('.nq-category-select'), row.querySelector('.nq-domain-select')]))),
      table(['Root Category', 'Domain'], [...$('nq-root-categories').children].map((row) => line(row, [row.querySelector('.nq-domain-select')]))),
    );
    filterCatalog();
  };
  const selectCatalogTab = (name) => {
    catalogTab = name;
    rootDialog.querySelectorAll('[data-nq-catalog-tab]').forEach((tab) => {
      const active = tab.dataset.nqCatalogTab === name;
      tab.classList.toggle('is-active', active);
      tab.setAttribute('aria-selected', String(active));
    });
    Object.entries(CATALOG_LISTS).forEach(([key, id]) => { $(id).hidden = key !== name; });
    $('nq-root-add').textContent = CATALOG_ADD[name];
    $('nq-root-add').hidden = name === 'mapping';
    if (name === 'mapping') renderMapping();
    filterCatalog();
  };
  const filterCatalog = () => {
    const query = $('nq-root-search').value.trim().toLowerCase();
    $(CATALOG_LISTS[catalogTab]).querySelectorAll(':scope > li, tbody > tr').forEach((row) => {
      const text = [row.dataset.name || '', ...[...row.querySelectorAll('input[type="text"], select')]
        .map((control) => control.selectedOptions?.[0]?.textContent || control.value)].join(' ').toLowerCase();
      row.hidden = Boolean(query) && !text.includes(query);
    });
  };
  const collectCatalogRows = (kind) => [...$(CATALOG_LISTS[kind]).children].map((row) => ({
    name: row.querySelector('.nq-root-name').value.trim(), previous: row.dataset.previous,
    keywords: row.querySelector('.nq-root-keywords').value,
    ...(kind === 'domains' ? {color: row.querySelector('input[type="color"]').value}
      : {domain: row.querySelector('.nq-domain-select').value}),
    ...(kind === 'causes' ? {category: row.querySelector('.nq-category-select').value} : {}),
  }));
  const fillCatalog = (catalog) => {
    $('nq-root-domains').replaceChildren(...catalog.domains.map((domain) => domainRow(domain)));
    $('nq-root-categories').replaceChildren(...catalog.categories.map((item) => entryRow('categories', item)));
    $('nq-root-causes').replaceChildren(...catalog.causes.map((item) => entryRow('causes', item)));
    refreshDomainSelects();
    countCatalog();
  };
  if (rootDialog) {
    $('nq-root-open').addEventListener('click', () => {
      $('nq-root-rule-text').textContent = ruleText(state.rootCauses.rule);
      fillCatalog(state.rootCauses);
      $('nq-root-require').checked = Boolean(state.rootCauses.require_to_close);
      catalogDefaults = false;
      $('nq-root-error').textContent = '';
      $('nq-root-search').value = '';
      // Every time it opens, on its first tab: the Domains.
      selectCatalogTab('domains');
      rootDialog.showModal();
    });
    rootDialog.querySelectorAll('[data-nq-catalog-tab]').forEach((tab) => tab.addEventListener('click', () => selectCatalogTab(tab.dataset.nqCatalogTab)));
    $('nq-root-search').addEventListener('input', filterCatalog);
    // The automatic domains follow the names and keywords being typed.
    let pendingAutomatic = 0;
    rootDialog.addEventListener('input', (event) => {
      if (!event.target.matches('.nq-root-name, .nq-root-keywords')) return;
      cancelAnimationFrame(pendingAutomatic);
      pendingAutomatic = requestAnimationFrame(refreshAutomaticDomains);
    });
    $('nq-root-cancel').addEventListener('click', () => rootDialog.close());
    // Adds the default domains, root categories and root causes that are missing; existing ones keep their keywords.
    $('nq-root-defaults').addEventListener('click', () => {
      const defaults = state.rootCauseDefaults || {domains: [], categories: [], causes: []};
      let added = 0;
      Object.entries(CATALOG_LISTS).forEach(([kind, id]) => {
        const list = $(id);
        const names = new Set([...list.querySelectorAll('.nq-root-name')].map((input) => input.value.trim().toLowerCase()));
        (defaults[kind] || []).filter((item) => !names.has(item.name.toLowerCase())).forEach((item) => {
          list.append(kind === 'domains' ? domainRow(item) : entryRow(kind, item));
          added += 1;
        });
      });
      refreshDomainSelects();
      countCatalog();
      filterCatalog();
      $('nq-root-error').style.color = 'var(--nq-muted)';
      $('nq-root-error').textContent = added ? `${added} default values added: review them and Save.` : 'Every default value is already in the catalog.';
    });
    // Only the default domains, root categories and root causes, with their keywords (a value with the same name keeps
    // its calls), and no root category required to close a call; Save refuses to remove a value still used by a call.
    $('nq-root-default-catalog').addEventListener('click', () => {
      const defaults = state.rootCauseDefaults || {domains: [], categories: [], causes: []};
      let added = 0;
      const removed = [];
      ['domains', 'categories', 'causes'].forEach((kind) => {
        const current = [...$(CATALOG_LISTS[kind]).querySelectorAll('.nq-root-name')].map((input) => input.value.trim()).filter(Boolean);
        const names = new Set((defaults[kind] || []).map((item) => item.name.toLowerCase()));
        const kept = new Set(current.map((name) => name.toLowerCase()));
        added += (defaults[kind] || []).filter((item) => !kept.has(item.name.toLowerCase())).length;
        removed.push(...current.filter((name) => !names.has(name.toLowerCase())));
      });
      fillCatalog(defaults);
      $('nq-root-require').checked = false;
      catalogDefaults = true;
      selectCatalogTab(catalogTab);
      $('nq-root-error').style.color = 'var(--nq-muted)';
      $('nq-root-error').textContent = `The default catalog is back (${added} added`
        + (removed.length ? `, ${removed.length} removed: ${removed.slice(0, 8).join(', ')}${removed.length > 8 ? '…' : ''}` : '')
        + '). Save to apply; a value still used by a call cannot be removed.';
    });
    $('nq-root-add').addEventListener('click', () => {
      const row = catalogTab === 'domains' ? domainRow() : entryRow(catalogTab);
      $(CATALOG_LISTS[catalogTab]).append(row);
      refreshDomainSelects();
      countCatalog();
      row.querySelector('.nq-root-name').focus();
    });
    $('nq-root-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const save = $('nq-root-save');
      save.disabled = true;
      try {
        await saveCatalog();
        rootDialog.close();
        toast('Root cause catalog saved.');
        await loadState();
        if (state.detail) openDetail(state.detail.call.call_key, {keepTab: true});
      } catch (error) {
        $('nq-root-error').style.color = '';
        $('nq-root-error').textContent = error.message;
      } finally {
        save.disabled = false;
      }
    });
  }
  // -- fields & sections dialog ---------------------------------------------------------------
  const fieldsDialog = $('nq-fields-dialog');
  let fieldSection = '';
  // Whether Default Fields & Sections was used since the dialog opened (App Events says so).
  let fieldsDefaults = false;
  // The sections as edited in the dialog (name and colour), in their fixed order.
  const editedSections = () => [...$('nq-sections-editor').querySelectorAll('[data-section-key]')].map((row) => ({
    key: row.dataset.sectionKey, label: row.querySelector('input[type="text"]').value.trim() || row.dataset.sectionKey,
    color: row.querySelector('input[type="color"]').value,
  }));
  const editedSection = (key) => editedSections().find((section) => section.key === key) || sectionOf(key);
  const fieldValueRow = (option = {name: '', color: '', keywords: []}, withKeywords = false) => {
    const row = node('li', undefined, 'nq-option-row nq-field-value');
    row.dataset.previous = option.name || '';
    const color = node('input');
    color.type = 'color';
    color.value = /^#[0-9a-f]{6}$/i.test(option.color || '') ? option.color : '#b8c0c6';
    color.dataset.chosen = option.color ? '1' : '';
    color.title = 'Colour of the value';
    color.addEventListener('input', () => { color.dataset.chosen = '1'; });
    row.append(color, textInput(option.name, 'Value', 'nq-root-name'));
    if (withKeywords) {
      const keywords = textInput((option.keywords || []).join(', '), 'Keywords found in the call values', 'nq-root-keywords');
      keywords.title = 'The call gets this value when one of these keywords is in the call values the field reads ("a+b" needs both)';
      row.append(keywords);
    }
    iconButtons(row, row, () => row.remove());
    return row;
  };
  // Moves a field past the next visible one, so a filtered list moves as it is shown.
  const moveVisible = (item, offset) => {
    let sibling = offset < 0 ? item.previousElementSibling : item.nextElementSibling;
    while (sibling && sibling.hidden) sibling = offset < 0 ? sibling.previousElementSibling : sibling.nextElementSibling;
    if (sibling) (offset < 0 ? sibling.before(item) : sibling.after(item));
  };
  const selectOf = (className, label, entries, value) => {
    const select = node('select', undefined, className);
    select.setAttribute('aria-label', label);
    select.append(...entries.map(([key, text]) => {
      const option = node('option', text);
      option.value = key;
      return option;
    }));
    select.value = value;
    return select;
  };
  const flagToggle = (name, label, checked, title) => {
    const wrapper = node('label', undefined, 'nq-toggle nq-flag');
    const box = node('input');
    box.type = 'checkbox';
    box.dataset.flag = name;
    box.checked = Boolean(checked);
    wrapper.title = title;
    wrapper.append(box, ` ${label}`);
    return wrapper;
  };
  // Where a field of each source reads its value: call fields, CDR columns, Ericsson RCA columns or the values of the
  // DT Analyzer RCA.
  const refChoices = (source) => (source === 'rca' ? Object.entries(state.rcaRefs)
    : source === 'dta' ? Object.entries(state.dtaRefs)
    : source === 'priority' ? Object.entries(state.priorityRefs)
      : source === 'cdr' ? [...state.callFields.map((name) => [name, name]), ...state.cdrColumns.map((name) => [`column:${name}`, `CDR column ${name}`])]
        : source === 'derived' ? state.callFields.map((name) => [name, name]) : []);
  const fieldDefinition = (field = {key: '', label: '', type: 'list', source: 'user', source_ref: '', section: fieldSection || 'analysis',
    options: [], in_table: false, in_export: true, in_summary: false, required_to_close: false, suggest_from: '', description: ''}) => {
    const block = node('li', undefined, 'nq-root-domain nq-field-def');
    block.dataset.key = field.key || '';
    // Whether the field is a column of the table and of the Excel of the workspace layout: chosen in Columns, kept here.
    block.dataset.inTable = field.in_table ? '1' : '';
    block.dataset.inExport = field.in_export !== false ? '1' : '';
    const tracking = field.source === 'tracking';
    const row = node('div', undefined, 'nq-option-row');
    const name = textInput(field.label, 'Field name', 'nq-root-name');
    const section = selectOf('nq-field-section nq-pill-select', 'Section', editedSections().map((item) => [item.key, item.label]), field.section);
    const sources = tracking ? [['tracking', `Follow-up: ${state.trackingRefs[field.source_ref] || field.source_ref}`]]
      : Object.entries(state.fieldSources).filter(([key]) => key !== 'tracking');
    const source = selectOf('nq-field-source', 'Source of the value', sources, field.source);
    // A saved field keeps its source; a new one chooses it.
    source.disabled = tracking || Boolean(field.key);
    source.title = source.disabled ? 'Where the value comes from (fixed once the field is saved)' : 'Where the value comes from';
    const type = selectOf('nq-field-type', 'Type', Object.entries(state.fieldTypes), field.type || 'text');
    type.disabled = tracking;
    row.append(name, section, source, type);
    // Every field moves; only the follow-up fields stay.
    [['↑', 'Move up', () => moveVisible(block, -1)], ['↓', 'Move down', () => moveVisible(block, 1)],
      ['×', tracking ? 'The follow-up fields cannot be removed' : 'Remove', () => block.remove()]].forEach(([label, title, action], index) => {
      const button = node('button', label, 'nq-icon-action');
      button.type = 'button';
      button.title = title;
      button.setAttribute('aria-label', title);
      button.disabled = tracking && index === 2;
      button.addEventListener('click', action);
      row.append(button);
    });
    const flags = node('div', undefined, 'nq-field-flags');
    flags.append(
      flagToggle('in_summary', 'Summary breakdown', field.in_summary, 'Count the calls of each value in the Summary (lists and Yes / No)'),
      flagToggle('required_to_close', 'Required to close', field.required_to_close, 'A call cannot move to a closed status while this field is empty'),
    );
    const more = node('details', undefined, 'nq-field-more');
    const summary = node('summary', 'Values and settings');
    const ref = node('label', undefined, 'nq-field-setting nq-field-ref');
    const refInput = textInput(field.source_ref, 'Value from', 'nq-field-ref-input');
    const listId = `nq-ref-list-${Math.random().toString(36).slice(2, 9)}`;
    const datalist = node('datalist');
    datalist.id = listId;
    refInput.setAttribute('list', listId);
    ref.append(node('span', 'Value from'), refInput, datalist);
    const suggest = node('label', undefined, 'nq-field-setting');
    suggest.append(node('span', 'Propose the CDR value of'), selectOf('nq-field-suggest', 'Propose the CDR value of',
      [['', 'Nothing'], ...state.callFields.map((item) => [item, item])], field.suggest_from || ''));
    const values = node('div', undefined, 'nq-field-values');
    const list = node('ul', undefined, 'nq-root-causes');
    const add = node('button', 'Add Value', 'nq-secondary-action');
    add.type = 'button';
    add.addEventListener('click', () => {
      const item = fieldValueRow(undefined, source.value === 'derived');
      list.append(item);
      item.querySelector('.nq-root-name').focus();
    });
    values.append(list, add);
    const description = textInput(field.description, 'Description (shown when hovering the field)', 'nq-field-description');
    more.append(summary, ref, suggest, values, description);
    const sync = () => {
      const kind = source.value;
      if (kind === 'derived') type.value = 'list';
      // A value of the NQ Prioritization has its own type.
      if (kind === 'priority' && state.priorityTypes[refInput.value.trim()]) type.value = state.priorityTypes[refInput.value.trim()];
      type.disabled = tracking || ['derived', 'priority'].includes(kind);
      ref.hidden = tracking || kind === 'user';
      ref.querySelector('span').textContent = kind === 'derived' ? 'Call values read (comma separated)' : kind === 'rca' ? 'Ericsson RCA column'
        : kind === 'dta' ? 'DT Analyzer RCA value' : kind === 'priority' ? 'NQ Prioritization value' : 'CDR value';
      datalist.replaceChildren(...refChoices(kind).map(([value, text]) => {
        const option = node('option', text);
        option.value = value;
        return option;
      }));
      suggest.hidden = kind !== 'user';
      const lists = type.value === 'list' && ['user', 'derived'].includes(kind);
      values.hidden = !lists;
      const keywords = kind === 'derived';
      // The value rows show keywords only for derived lists.
      [...list.children].forEach((item) => {
        if (Boolean(item.querySelector('.nq-root-keywords')) !== keywords) {
          const option = {name: item.querySelector('.nq-root-name').value, keywords: item.querySelector('.nq-root-keywords')?.value.split(',') || [],
            color: item.querySelector('input[type="color"]').dataset.chosen ? item.querySelector('input[type="color"]').value : ''};
          const replacement = fieldValueRow(option, keywords);
          replacement.dataset.previous = item.dataset.previous;
          item.replaceWith(replacement);
        }
      });
      const summaryBox = flags.querySelector('[data-flag="in_summary"]');
      summaryBox.disabled = !['list', 'yes_no'].includes(type.value);
      if (summaryBox.disabled) summaryBox.checked = false;
      const required = flags.querySelector('[data-flag="required_to_close"]');
      required.disabled = kind !== 'user';
      if (required.disabled) required.checked = false;
      const count = list.children.length;
      summary.textContent = lists ? `Values (${count}) and settings` : 'Settings';
      const color = editedSection(section.value).color;
      block.style.setProperty('--nq-section', color);
      paintPill(section, color);
      block.dataset.section = section.value;
      block.dataset.source = kind;
    };
    list.append(...(field.options || []).map((option) => fieldValueRow(option, field.source === 'derived')));
    [type, source, section, refInput].forEach((control) => control.addEventListener('change', () => { sync(); filterFieldDefs(); }));
    list.addEventListener('click', () => window.requestAnimationFrame(sync));
    add.addEventListener('click', () => window.requestAnimationFrame(sync));
    sync();
    // New fields open their settings at once.
    more.open = !field.key;
    block.append(row, flags, more);
    return block;
  };
  const collectFields = () => [...$('nq-field-defs').children].map((block) => ({
    key: block.dataset.key || '',
    label: block.querySelector(':scope > .nq-option-row .nq-root-name').value.trim(),
    section: block.querySelector('.nq-field-section').value,
    source: block.querySelector('.nq-field-source').value,
    source_ref: block.querySelector('.nq-field-ref-input').value.trim(),
    type: block.querySelector('.nq-field-type').value,
    options: [...block.querySelectorAll('.nq-field-value')].map((row) => {
      const color = row.querySelector('input[type="color"]');
      return {name: row.querySelector('.nq-root-name').value.trim(), color: color.dataset.chosen ? color.value : '',
        previous: row.dataset.previous, keywords: row.querySelector('.nq-root-keywords')?.value || ''};
    }).filter((option) => option.name),
    in_table: Boolean(block.dataset.inTable),
    in_export: Boolean(block.dataset.inExport),
    in_summary: block.querySelector('[data-flag="in_summary"]').checked,
    required_to_close: block.querySelector('[data-flag="required_to_close"]').checked,
    suggest_from: block.querySelector('.nq-field-suggest').value,
    description: block.querySelector('.nq-field-description').value.trim(),
  }));
  // The section chips and the text filter show part of the fields; the order stays the order of every field.
  const filterFieldDefs = () => {
    const query = $('nq-field-filter').value.trim().toLowerCase();
    const blocks = [...$('nq-field-defs').children];
    blocks.forEach((block) => {
      const label = block.querySelector('.nq-root-name').value.toLowerCase();
      block.hidden = Boolean(fieldSection && block.dataset.section !== fieldSection) || Boolean(query && !label.includes(query));
    });
    const counts = {};
    blocks.forEach((block) => { counts[block.dataset.section] = (counts[block.dataset.section] || 0) + 1; });
    $('nq-field-section-chips').replaceChildren(...[{key: '', label: 'All', color: ''}, ...editedSections()].map((section) => {
      const chip = node('button', `${section.label} (${section.key ? counts[section.key] || 0 : blocks.length})`, 'nq-section-chip');
      chip.type = 'button';
      chip.setAttribute('role', 'tab');
      chip.setAttribute('aria-selected', String(fieldSection === section.key));
      chip.classList.toggle('is-active', fieldSection === section.key);
      if (section.color) chip.style.setProperty('--nq-section', section.color);
      chip.addEventListener('click', () => { fieldSection = section.key; filterFieldDefs(); });
      return chip;
    }));
  };
  const fillSectionsEditor = (sections) => {
    $('nq-sections-editor').replaceChildren(...sections.map((section) => {
      const row = node('div', undefined, 'nq-option-row nq-section-row');
      row.dataset.sectionKey = section.key;
      const color = node('input');
      color.type = 'color';
      color.value = section.color;
      color.setAttribute('aria-label', `Colour of ${section.label}`);
      const name = textInput(section.label, 'Section name');
      name.maxLength = 40;
      row.append(color, name);
      // Renamed or recoloured sections show at once in the fields.
      [color, name].forEach((control) => control.addEventListener('input', () => {
        $('nq-field-defs').querySelectorAll('.nq-field-section').forEach((select) => {
          const option = [...select.options].find((item) => item.value === section.key);
          if (option) option.textContent = name.value.trim() || section.key;
          select.dispatchEvent(new Event('change'));
        });
        filterFieldDefs();
      }));
      return row;
    }));
  };
  const fillFieldsDialog = () => {
    fillSectionsEditor(state.sections);
    $('nq-field-defs').replaceChildren(...state.fields.map((field) => fieldDefinition(field)));
    $('nq-field-filter').value = '';
    filterFieldDefs();
  };
  // A catalog workbook is previewed first; Import applies it.
  let catalogFile = null;
  const previewList = (label, names) => (names.length ? `${label}: ${names.slice(0, 12).join(', ')}${names.length > 12 ? ` +${names.length - 12}` : ''}` : '');
  const showCatalogPreview = (preview) => {
    const host = $('nq-catalog-preview');
    const lines = [
      `${preview.format === 'meeting' ? 'Field list of the meeting workbook' : 'Catalog workbook'} with ${number(preview.fields)} fields after the import.`,
      previewList('New fields', preview.added), previewList('Changed fields', preview.changed),
      previewList('New domains', preview.root_added.domains), previewList('New root categories', preview.root_added.categories),
      previewList('New root causes', preview.root_added.causes), previewList('New statuses', preview.statuses_added),
      previewList('New teams', preview.teams_added), preview.rules ? `${number(preview.rules)} Status Rules replace the current ones.` : '',
      preview.sections ? 'The section names and colours of the workbook are taken.' : '',
    ].filter(Boolean);
    const list = node('ul');
    list.append(...lines.map((line) => node('li', line)));
    const actions = node('div', undefined, 'nq-composer-actions');
    const cancel = node('button', 'Cancel', 'nq-secondary-action');
    const apply = node('button', 'Import', 'nq-primary-action');
    cancel.type = apply.type = 'button';
    cancel.addEventListener('click', () => { host.hidden = true; catalogFile = null; });
    apply.addEventListener('click', async () => {
      if (!catalogFile) return;
      apply.disabled = true;
      try {
        const body = new FormData();
        body.append('workbook', catalogFile);
        const response = await fetch('/api/non-qualified-calls/catalog/import', {method: 'POST', credentials: 'same-origin', body});
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'The catalog could not be imported.');
        host.hidden = true;
        catalogFile = null;
        toast('Catalog imported.');
        await loadState();
        fillFieldsDialog();
      } catch (error) {
        $('nq-fields-error').style.color = '';
        $('nq-fields-error').textContent = error.message;
      } finally {
        apply.disabled = false;
      }
    });
    actions.append(cancel, apply);
    host.replaceChildren(node('strong', `Import ${catalogFile?.name || 'the workbook'}?`), list, actions);
    host.hidden = false;
  };
  if (fieldsDialog) {
    $('nq-fields-open').addEventListener('click', () => {
      fieldSection = '';
      fieldsDefaults = false;
      fillFieldsDialog();
      $('nq-catalog-preview').hidden = true;
      $('nq-fields-error').textContent = '';
      fieldsDialog.showModal();
    });
    $('nq-fields-cancel').addEventListener('click', () => fieldsDialog.close());
    $('nq-field-filter').addEventListener('input', filterFieldDefs);
    $('nq-field-defs').addEventListener('input', (event) => { if (event.target.matches('.nq-root-name')) filterFieldDefs(); });
    $('nq-fields-add').addEventListener('click', () => {
      const block = fieldDefinition();
      $('nq-field-defs').append(block);
      filterFieldDefs();
      block.querySelector('.nq-root-name').focus();
    });
    // The sections and fields of a new workspace, with their settings and list values: a field keeps its key (a follow-up
    // field, the one of its follow-up value) and a value of the same name its calls; Save refuses to remove a field or
    // value still used by a call.
    $('nq-fields-default').addEventListener('click', () => {
      const current = [...$('nq-field-defs').children].map((block) => ({key: block.dataset.key,
        label: block.querySelector(':scope > .nq-option-row .nq-root-name').value.trim()}));
      const fields = state.defaultFields.map((field) => {
        const existing = state.fields.find((item) => (field.source === 'tracking'
          ? item.source === 'tracking' && item.source_ref === field.source_ref : item.key === field.key));
        return {...field, key: existing?.key || field.key,
          ...(existing ? {in_table: existing.in_table, in_export: existing.in_export} : {})};
      });
      const keys = new Set(fields.map((field) => field.key));
      const shown = new Set(current.map((field) => field.key).filter(Boolean));
      const added = fields.filter((field) => !shown.has(field.key)).length;
      const removed = current.filter((field) => !keys.has(field.key)).map((field) => field.label || 'a new field');
      fillSectionsEditor(state.defaultSections);
      $('nq-field-defs').replaceChildren(...fields.map((field) => fieldDefinition(field)));
      fieldSection = '';
      filterFieldDefs();
      fieldsDefaults = true;
      $('nq-fields-error').style.color = 'var(--nq-muted)';
      $('nq-fields-error').textContent = `The default sections and fields are back (${added} added`
        + (removed.length ? `, ${removed.length} removed: ${removed.slice(0, 8).join(', ')}${removed.length > 8 ? '…' : ''}` : '')
        + '). Save to apply; a field or value still used by a call cannot be removed.';
    });
    $('nq-fields-workbook').addEventListener('change', async (event) => {
      const file = event.target.files?.[0];
      event.target.value = '';
      if (!file) return;
      const message = $('nq-fields-error');
      message.style.color = 'var(--nq-muted)';
      message.textContent = 'Reading the workbook…';
      try {
        const body = new FormData();
        body.append('workbook', file);
        body.append('preview', '1');
        const response = await fetch('/api/non-qualified-calls/catalog/import', {method: 'POST', credentials: 'same-origin', body});
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'The workbook could not be read.');
        catalogFile = file;
        message.textContent = '';
        showCatalogPreview(payload);
      } catch (error) {
        message.style.color = '';
        message.textContent = error.message;
      }
    });
    $('nq-fields-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const save = $('nq-fields-save');
      save.disabled = true;
      try {
        const sections = editedSections();
        if (JSON.stringify(sections) !== JSON.stringify(state.sections.map(({key, label, color}) => ({key, label, color})))) {
          await api('/api/non-qualified-calls/sections', {method: 'PUT', body: JSON.stringify({sections, defaults: fieldsDefaults})});
        }
        await api('/api/non-qualified-calls/fields', {method: 'PUT', body: JSON.stringify({fields: collectFields(), defaults: fieldsDefaults})});
        fieldsDialog.close();
        toast('Fields and sections saved.');
        await loadState();
        if (state.detail) openDetail(state.detail.call.call_key, {keepTab: true});
      } catch (error) {
        $('nq-fields-error').style.color = '';
        $('nq-fields-error').textContent = error.message;
      } finally {
        save.disabled = false;
      }
    });
  }
  // -- table columns dialog: the layout of the user (only for them) ----------------------------------
  const columnsDialog = $('nq-columns-dialog');
  // Why the layout is saved (App Events says so): changed, defaults (Default Columns) or copied (Copy Workspace Layout).
  let columnsReason = 'changed';
  const syncColumnCount = () => {
    const tableBoxes = [...columnsDialog.querySelectorAll('#nq-columns-cdr input[data-target="table"]')];
    const chosen = tableBoxes.filter((box) => box.checked).length;
    // A column of the table is always exported.
    tableBoxes.forEach((box) => {
      const excel = box.closest('.nq-cdr-column-row').querySelector('input[data-target="excel"]');
      if (box.checked) excel.checked = true;
      excel.disabled = box.checked;
      box.disabled = !box.checked && chosen >= state.maxCdrColumns;
    });
    const exported = columnsDialog.querySelectorAll('#nq-columns-cdr input[data-target="excel"]:checked').length;
    $('nq-columns-count').textContent = `(${chosen} of at most ${state.maxCdrColumns} in the table · ${exported} in Excel)`;
  };
  const columnBox = (value, kind, label) => {
    const box = node('input');
    box.type = 'checkbox';
    box.value = value;
    box.dataset.target = kind;
    box.setAttribute('aria-label', `${label} in the ${kind === 'table' ? 'table' : 'Excel export'}`);
    return box;
  };
  // Ticks the call columns, the Table and Excel of each field and the CDR columns of a layout.
  const fillColumnsDialog = (layout) => {
    $('nq-columns-builtin').querySelectorAll('input').forEach((box) => { box.checked = layout.builtin.includes(box.value); });
    const table = new Set(layout.fields);
    const excel = new Set(layout.excel_fields);
    $('nq-columns-fields').querySelectorAll('input[data-target="table"]:not([data-fixed])').forEach((box) => { box.checked = table.has(box.value); });
    $('nq-columns-fields').querySelectorAll('input[data-target="excel"]').forEach((box) => { box.checked = excel.has(box.value); });
    const inTable = new Set(layout.cdr);
    const inExcel = new Set(layout.export_cdr || []);
    $('nq-columns-cdr').querySelectorAll('.nq-cdr-column-row').forEach((row) => {
      row.querySelector('input[data-target="table"]').checked = inTable.has(row.dataset.name);
      row.querySelector('input[data-target="excel"]').checked = inTable.has(row.dataset.name) || inExcel.has(row.dataset.name);
    });
    syncColumnCount();
  };
  if (columnsDialog) {
    $('nq-columns-open').addEventListener('click', () => {
      const layout = state.layout;
      const workspace = state.layouts?.workspace || layout;
      $('nq-columns-builtin').replaceChildren(...Object.entries(state.optionalColumns).map(([key, label]) => {
        const wrapper = node('label', undefined, 'nq-toggle');
        const box = node('input');
        box.type = 'checkbox';
        box.value = key;
        wrapper.append(box, ` ${label}`);
        return wrapper;
      }));
      // The catalog fields under their section, each one as a column of the table and of the Excel; the follow-up
      // fields always have their column.
      $('nq-columns-fields').replaceChildren(...state.sections.map((section) => {
        const fields = state.fields.filter((field) => field.section === section.key);
        if (!fields.length) return null;
        const group = node('div', undefined, 'nq-columns-field-group');
        group.style.setProperty('--nq-section', section.color);
        const head = node('div', undefined, 'nq-columns-field-head');
        head.append(sectionTag(section.key));
        const columns = node('div', undefined, 'nq-cdr-column-head nq-columns-field-columns');
        columns.setAttribute('aria-hidden', 'true');
        columns.append(node('span', 'Field'), node('span', 'Table'), node('span', 'Excel'));
        group.append(head, columns, ...fields.map((field) => {
          const row = node('div', undefined, 'nq-cdr-column-row nq-columns-field-row');
          row.title = `${SOURCE_TAGS[field.source] || field.source} · ${field.description || field.label}`;
          const table = columnBox(field.key, 'table', field.label);
          if (field.source === 'tracking') {
            table.checked = true;
            table.disabled = true;
            table.dataset.fixed = '1';
            table.title = 'Always a column of the table';
          }
          row.append(node('span', field.label), table, columnBox(field.key, 'excel', field.label));
          return row;
        }));
        return group;
      }).filter(Boolean));
      const names = [...new Set([...layout.cdr, ...(layout.export_cdr || []), ...workspace.cdr, ...(workspace.export_cdr || []),
        ...state.cdrColumns])];
      $('nq-columns-cdr').replaceChildren(...names.map((name) => {
        const row = node('div', undefined, 'nq-cdr-column-row');
        row.dataset.name = name;
        row.append(node('span', name), columnBox(name, 'table', name), columnBox(name, 'excel', name));
        return row;
      }));
      if (!names.length) $('nq-columns-cdr').append(node('p', 'No CDR is indexed yet.', 'form-note'));
      fillColumnsDialog(layout);
      // From the workspace layout, Save makes the columns the user's own.
      const scope = $('nq-columns-scope');
      scope.hidden = state.layouts?.view !== 'workspace';
      scope.textContent = state.layouts?.mine
        ? 'You are seeing the workspace layout: Save makes these columns your own layout and replaces the one you had.'
        : 'You are seeing the workspace layout: Save makes these columns your own layout, only for you.';
      $('nq-columns-search').value = '';
      $('nq-columns-error').textContent = '';
      columnsReason = 'changed';
      columnsDialog.showModal();
    });
    $('nq-columns-cdr').addEventListener('change', syncColumnCount);
    // The columns of a new workspace: no call or CDR columns, and the Table and Excel of its fields.
    $('nq-columns-default').addEventListener('click', () => {
      const defaults = new Map(state.defaultFields.map((field) => [field.key, field]));
      fillColumnsDialog({builtin: [], cdr: [], export_cdr: [],
        fields: state.fields.filter((field) => defaults.get(field.key)?.in_table).map((field) => field.key),
        excel_fields: state.fields.filter((field) => defaults.get(field.key)?.in_export ?? true).map((field) => field.key)});
      columnsReason = 'defaults';
      $('nq-columns-error').style.color = 'var(--nq-muted)';
      $('nq-columns-error').textContent = 'The default columns are back: no call or CDR columns, and the Analysis Center fields '
        + 'of a new workspace. Save to apply.';
    });
    // The columns, Excel and order of the workspace layout, to start the user's own again.
    $('nq-columns-copy').addEventListener('click', () => {
      fillColumnsDialog(state.layouts?.workspace || state.layout);
      columnsReason = 'copied';
      $('nq-columns-error').style.color = 'var(--nq-muted)';
      $('nq-columns-error').textContent = 'The columns, Excel and column order of the workspace layout are back. Save to make them your own.';
    });
    $('nq-columns-search').addEventListener('input', () => {
      const query = $('nq-columns-search').value.trim().toLowerCase();
      $('nq-columns-cdr').querySelectorAll('.nq-cdr-column-row').forEach((row) => {
        row.hidden = Boolean(query) && !row.dataset.name.toLowerCase().includes(query);
      });
    });
    $('nq-columns-cancel').addEventListener('click', () => columnsDialog.close());
    $('nq-columns-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const save = $('nq-columns-save');
      const values = (selector) => [...columnsDialog.querySelectorAll(selector)].map((box) => box.value);
      save.disabled = true;
      try {
        const saved = await saveLayout({
          builtin: values('#nq-columns-builtin input:checked'),
          cdr: values('#nq-columns-cdr input[data-target="table"]:checked'),
          export_cdr: [...columnsDialog.querySelectorAll('#nq-columns-cdr input[data-target="excel"]:checked')]
            .filter((box) => !box.closest('.nq-cdr-column-row').querySelector('input[data-target="table"]').checked).map((box) => box.value),
          fields: values('#nq-columns-fields input[data-target="table"]:checked:not([data-fixed])'),
          excel_fields: values('#nq-columns-fields input[data-target="excel"]:checked'),
          ...(columnsReason === 'copied' ? {order: state.layouts?.workspace?.order || []} : {}),
        }, columnsReason, {reload: true});
        if (!saved) return;
        columnsDialog.close();
        toast('Your layout is saved: only you see it.');
      } catch (error) {
        $('nq-columns-error').style.color = '';
        $('nq-columns-error').textContent = error.message;
      } finally {
        save.disabled = false;
      }
    });
  }
  // -- suggestion rule dialog (super-admins) ----------------------------------------------
  const ruleDialog = $('nq-rule-dialog');
  const fillRule = (rule) => {
    ruleDialog.querySelectorAll('[data-nq-rule-fields]').forEach((host) => {
      const chosen = new Set(rule[host.dataset.nqRuleFields] || []);
      host.replaceChildren(...Object.entries(state.ruleFields).map(([field, label]) => {
        const option = node('label', undefined, 'nq-toggle');
        const box = node('input');
        box.type = 'checkbox';
        box.value = field;
        box.checked = chosen.has(field);
        option.append(box, ` ${label}`);
        return option;
      }));
    });
    ruleDialog.querySelectorAll('input[data-nq-rule]').forEach((box) => { box.checked = Boolean(rule[box.dataset.nqRule]); });
    ruleDialog.querySelector('select[data-nq-rule="match"]').value = rule.match || 'words';
    $('nq-rule-error').textContent = '';
    // Everybody sees the rule; only admins and super-admins change it.
    const editable = Boolean(state.user.can_configure_rule);
    ruleDialog.querySelectorAll('input, select').forEach((control) => { control.disabled = !editable; });
    $('nq-rule-save').hidden = !editable;
    $('nq-rule-default').hidden = !editable;
    $('nq-rule-cancel').textContent = editable ? 'Cancel' : 'Close';
    $('nq-rule-readonly').hidden = editable;
  };
  const saveRule = async (rule) => {
    const save = $('nq-rule-save');
    save.disabled = true;
    try {
      const result = await api('/api/non-qualified-calls/root-causes/rule', {method: 'PUT', body: JSON.stringify({rule})});
      state.rootCauses.rule = result.rule;
      $('nq-root-rule-text').textContent = ruleText(result.rule);
      ruleDialog.close();
      toast('Suggestion rule saved.');
      loadCalls({quiet: true});
    } catch (error) {
      $('nq-rule-error').textContent = error.message;
    } finally {
      save.disabled = false;
    }
  };
  if (ruleDialog) {
    document.querySelectorAll('[data-nq-rule-open]').forEach((button) => button.addEventListener('click', () => {
      fillRule(state.rootCauses.rule);
      ruleDialog.showModal();
    }));
    $('nq-rule-cancel').addEventListener('click', () => ruleDialog.close());
    $('nq-rule-default').addEventListener('click', () => { if (state.defaultRule) fillRule(state.defaultRule); });
    $('nq-rule-form').addEventListener('submit', (event) => {
      event.preventDefault();
      const fields = (key) => [...ruleDialog.querySelectorAll(`[data-nq-rule-fields="${key}"] input:checked`)].map((box) => box.value);
      const rule = {domain_fields: fields('domain_fields'), cause_fields: fields('cause_fields'),
        match: ruleDialog.querySelector('select[data-nq-rule="match"]').value};
      ruleDialog.querySelectorAll('input[data-nq-rule]').forEach((box) => { rule[box.dataset.nqRule] = box.checked; });
      saveRule(rule);
    });
  }
  // -- NQ Analysis Configuration menu -------------------------------------------------------------------------------
  // A menu opens where it fits: below its button, or above it near the bottom of the window, scrolling inside if needed,
  // and moved right when the button is too close to the left edge for it. Every entry opens its dialog and closes it.
  const dropdownMenu = (toggle, menu, {hover = false} = {}) => {
    if (!toggle || !menu) return;
    // Opened by the mouse passing over it: a click on the toggle then keeps it open instead of closing it.
    let hovered = false;
    const close = () => {
      hovered = false;
      if (menu.hidden) return;
      menu.hidden = true;
      toggle.setAttribute('aria-expanded', 'false');
    };
    const place = () => {
      const button = toggle.getBoundingClientRect();
      menu.style.maxHeight = '';
      menu.style.right = '';
      menu.classList.remove('is-up');
      const left = menu.getBoundingClientRect().left;
      if (left < 8) menu.style.right = `${left - 8}px`;
      const height = menu.scrollHeight;
      const below = window.innerHeight - button.bottom - 16;
      const above = button.top - 16;
      const up = height > below && above > below;
      menu.classList.toggle('is-up', up);
      menu.style.maxHeight = `${Math.max(160, up ? above : below)}px`;
    };
    toggle.addEventListener('click', () => {
      if (hovered) {
        hovered = false;
        return;
      }
      menu.hidden = !menu.hidden;
      toggle.setAttribute('aria-expanded', String(!menu.hidden));
      if (!menu.hidden) {
        place();
        menu.querySelector('button')?.focus({preventScroll: true});
      }
    });
    // A menu that opens on hover, as the sections menus of the tabs, closes shortly after the mouse leaves it.
    if (hover) {
      let timer = 0;
      const area = toggle.parentElement;
      area.addEventListener('pointerenter', (event) => {
        if (event.pointerType !== 'mouse') return;
        window.clearTimeout(timer);
        if (!menu.hidden) return;
        menu.hidden = false;
        hovered = true;
        toggle.setAttribute('aria-expanded', 'true');
        place();
      });
      area.addEventListener('pointerleave', (event) => {
        if (event.pointerType !== 'mouse') return;
        window.clearTimeout(timer);
        timer = window.setTimeout(close, 220);
      });
    }
    window.addEventListener('resize', () => { if (!menu.hidden) place(); });
    menu.addEventListener('click', () => window.setTimeout(close));
    // Any other click closes it, and a click on the toggle reaches the other dropdowns of the page, which close.
    document.addEventListener('click', (event) => { if (!menu.contains(event.target) && !toggle.contains(event.target)) close(); });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !menu.hidden) { close(); toggle.focus(); }
    });
  };
  dropdownMenu($('nq-config-toggle'), $('nq-config-menu'), {hover: true});

  // -- status rules dialog --------------------------------------------------------------------
  const statusRulesDialog = $('nq-status-rules-dialog');
  // The values a condition chooses among: list values, Yes / No, teams, users, root categories or causes.
  const conditionValues = (field) => {
    if (field === '@team') return state.options.teams.map((item) => item.name);
    if (field === '@assignee') return state.users;
    if (field === '@root_category') return state.rootCauses.categories.map((item) => item.name);
    if (field === '@root_cause') return state.rootCauses.causes.map((item) => item.name);
    return state.conditionFields[field]?.values || [];
  };
  const conditionColor = (field, name) => (field === '@team' ? optionColor('team', name)
    : field === '@root_category' ? optionColor('root_category', name) : field === '@root_cause' ? optionColor('root_cause', name)
      : optionColorOf(state.fields.find((item) => item.key === field) || {}, name));
  const conditionRow = (condition = {field: Object.keys(state.conditionFields)[0] || '', op: 'in', values: []}) => {
    const row = node('li', undefined, 'nq-condition');
    const field = selectOf('nq-condition-field', 'Field', Object.entries(state.conditionFields).map(([key, item]) => [key, item.label]),
      condition.field);
    const op = selectOf('nq-condition-op', 'Condition', Object.entries(state.ruleOperators), condition.op || 'in');
    const values = node('div', undefined, 'nq-condition-values');
    const fill = (chosen) => {
      const selected = new Set(chosen);
      const names = [...new Set([...conditionValues(field.value), ...chosen])];
      values.replaceChildren(...names.map((name) => {
        const label = node('label', undefined, 'nq-toggle nq-condition-value');
        const box = node('input');
        box.type = 'checkbox';
        box.value = name;
        box.checked = selected.has(name);
        const color = conditionColor(field.value, name);
        if (color) label.style.setProperty('--nq-chip', color);
        label.append(box, ` ${name}`);
        return label;
      }));
      if (!names.length) values.append(node('span', 'No values to choose.', 'nq-muted'));
      values.hidden = ['empty', 'not_empty'].includes(op.value);
    };
    field.addEventListener('change', () => fill([]));
    op.addEventListener('change', () => { values.hidden = ['empty', 'not_empty'].includes(op.value); });
    const remove = node('button', '×', 'nq-icon-action');
    remove.type = 'button';
    remove.title = 'Remove this condition';
    remove.setAttribute('aria-label', remove.title);
    remove.addEventListener('click', () => row.remove());
    row.append(field, op, remove, values);
    fill(condition.values || []);
    return row;
  };
  const statusRuleBlock = (rule = {status: state.options.statuses[1]?.name || state.options.statuses[0]?.name || '', conditions: [undefined]}) => {
    const block = node('li', undefined, 'nq-root-domain nq-status-rule');
    const head = node('div', undefined, 'nq-option-row');
    // A default rule whose status was renamed or removed keeps its conditions and asks for the status.
    const known = state.options.statuses.some((item) => item.name === rule.status);
    const entries = state.options.statuses.map((item) => [item.name, item.name]);
    if (!known) entries.unshift(['', 'Choose a status…']);
    const status = selectOf('nq-rule-status nq-pill-select', 'Status', entries, known ? rule.status : '');
    const missing = known ? null : node('p', `The default rule sets ${rule.status}, which is not one of the statuses: choose the status it sets.`,
      'nq-rule-missing');
    const paint = () => {
      paintPill(status, optionColor('status', status.value));
      block.classList.toggle('is-missing', !status.value);
      if (missing) missing.hidden = Boolean(status.value);
    };
    status.addEventListener('change', paint);
    head.append(node('span', 'Set the status', 'nq-rule-word'), status, node('span', 'when every condition holds', 'nq-rule-word'));
    iconButtons(head, block, () => block.remove());
    const conditions = node('ul', undefined, 'nq-conditions');
    conditions.append(...(rule.conditions || []).map((condition) => conditionRow(condition)));
    const add = node('button', 'Add Condition', 'nq-link-action');
    add.type = 'button';
    add.addEventListener('click', () => conditions.append(conditionRow()));
    block.append(head, ...(missing ? [missing] : []), conditions, add);
    paint();
    return block;
  };
  const collectStatusRules = () => [...$('nq-status-rules').children].filter((block) => block.matches('.nq-status-rule')).map((block) => ({
    status: block.querySelector('.nq-rule-status').value,
    conditions: [...block.querySelectorAll('.nq-condition')].map((row) => ({
      field: row.querySelector('.nq-condition-field').value, op: row.querySelector('.nq-condition-op').value,
      values: [...row.querySelectorAll('.nq-condition-values input:checked')].map((box) => box.value),
    })),
  }));
  const fillStatusRules = (rules) => {
    $('nq-status-rules').replaceChildren(...rules.map((rule) => statusRuleBlock(rule)));
  };
  if (statusRulesDialog) {
    document.querySelectorAll('[data-nq-status-rules-open]').forEach((button) => button.addEventListener('click', () => {
      fillStatusRules(state.statusRules);
      $('nq-status-rules-error').textContent = '';
      statusRulesDialog.showModal();
    }));
    $('nq-status-rules-cancel').addEventListener('click', () => statusRulesDialog.close());
    $('nq-status-rules-add').addEventListener('click', () => {
      const block = statusRuleBlock();
      $('nq-status-rules').append(block);
      block.querySelector('select').focus();
    });
    // Every default rule, with the conditions on the fields this workspace still has; a rule whose status is not one of
    // the statuses asks for it.
    $('nq-status-rules-default').addEventListener('click', () => {
      const statuses = new Set(state.options.statuses.map((item) => item.name));
      const rules = (state.defaultStatusRules || [])
        .map((rule) => ({...rule, conditions: rule.conditions.filter((condition) => state.conditionFields[condition.field])}))
        .filter((rule) => rule.conditions.length);
      fillStatusRules(rules);
      const missing = [...new Set(rules.filter((rule) => !statuses.has(rule.status)).map((rule) => rule.status))];
      $('nq-status-rules-error').style.color = missing.length ? '' : 'var(--nq-muted)';
      $('nq-status-rules-error').textContent = missing.length
        ? `The default rules are shown. ${missing.join(', ')} ${missing.length === 1 ? 'is' : 'are'} not among the statuses: choose the status of the marked rules (or put the default statuses back in Statuses & Teams), then Save.`
        : 'The default rules are shown: review them and Save.';
    });
    $('nq-status-rules-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const save = $('nq-status-rules-save');
      save.disabled = true;
      try {
        if (collectStatusRules().some((rule) => !rule.status)) throw new Error('Choose the status of every rule.');
        await api('/api/non-qualified-calls/status-rules', {method: 'PUT', body: JSON.stringify({rules: collectStatusRules()})});
        statusRulesDialog.close();
        toast('Status Rules saved: the automatic statuses follow them.');
        await loadState();
        if (state.detail) openDetail(state.detail.call.call_key, {keepTab: true});
      } catch (error) {
        $('nq-status-rules-error').style.color = '';
        $('nq-status-rules-error').textContent = error.message;
      } finally {
        save.disabled = false;
      }
    });
  }

  // -- DT Analyzer RCA Rules dialog (admins and super-admins change them) ----------------------------
  const dtaRulesDialog = $('nq-dta-rules-dialog');
  // The rules the dialog opened with, the default ones and the Non-Qualified Calls each rule explains (by its name).
  let dtaRules = {rules: [], defaults: [], counts: {}, pending: false};
  // Whether the rules shown are the default ones, untouched since Default Rules (App Events says so).
  let dtaDefaultsShown = false;
  const DTA_VALUELESS = ['empty', 'not_empty'];
  const dtaInput = (key) => (state.dtaRca.inputs || []).find((item) => item.key === key) || {key, label: key, kind: 'text', unit: '', group: ''};
  const dtaConditionRow = (condition = {input: 'failure_text', op: 'contains', value: ''}) => {
    const row = node('li', undefined, 'nq-condition nq-dta-condition');
    const input = selectOf('nq-dta-input', 'Value of the call', (state.dtaRca.inputs || []).map((item) => [item.key,
      `${item.group} · ${item.label}${item.unit ? ` (${item.unit})` : ''}`]), condition.input);
    const op = node('select', undefined, 'nq-dta-op');
    op.setAttribute('aria-label', 'Comparison');
    const value = node('input', undefined, 'nq-dta-value');
    value.setAttribute('aria-label', 'Value it is compared with');
    // The comparisons of the kind of the value (numbers or texts), and a number or text box for what it is compared with.
    const fillOperators = (chosen) => {
      const item = dtaInput(input.value);
      const allowed = (state.dtaRca.kind_operators || {})[item.kind] || [];
      op.replaceChildren(...allowed.map((key) => {
        const option = node('option', (state.dtaRca.operators || {})[key] || key);
        option.value = key;
        return option;
      }));
      op.value = allowed.includes(chosen) ? chosen : allowed[0];
      value.type = item.kind === 'number' ? 'number' : 'text';
      value.step = 'any';
      value.placeholder = item.kind === 'number' ? (item.unit || 'Number') : 'Words, separated by commas';
      value.hidden = DTA_VALUELESS.includes(op.value);
    };
    input.addEventListener('change', () => fillOperators(op.value));
    op.addEventListener('change', () => { value.hidden = DTA_VALUELESS.includes(op.value); });
    fillOperators(condition.op);
    value.value = condition.value ?? '';
    const remove = node('button', '×', 'nq-icon-action');
    remove.type = 'button';
    remove.title = 'Remove this condition';
    remove.setAttribute('aria-label', remove.title);
    remove.addEventListener('click', () => row.remove());
    row.append(input, op, value, remove);
    return row;
  };
  // The Root Categories or Root Causes of the catalog, and the value of a rule the catalog does not have (marked).
  const dtaCatalogEntries = (plural, value, none) => {
    const names = (state.rootCauses[plural] || []).map((item) => item.name);
    const entries = [['', none], ...names.map((name) => [name, name])];
    if (value && !names.includes(value)) entries.push([value, `${value} (not in the catalog)`]);
    return entries;
  };
  const dtaRuleBlock = (rule = {key: '', name: '', enabled: true, services: [], match: 'all', conditions: [{}], category: '', cause: ''}) => {
    const block = node('li', undefined, 'nq-root-domain nq-status-rule nq-dta-rule');
    block.dataset.key = rule.key || '';
    const head = node('div', undefined, 'nq-option-row');
    const enabled = node('input', undefined, 'nq-dta-enabled');
    enabled.type = 'checkbox';
    enabled.checked = rule.enabled !== false;
    enabled.title = 'Whether the rule is used (a disabled rule is skipped)';
    enabled.setAttribute('aria-label', enabled.title);
    const name = textInput(rule.name, 'Rule name', 'nq-root-name nq-dta-name');
    const count = node('span', rule.key ? `${number(dtaRules.counts[rule.name] || 0)} calls` : '', 'nq-dta-count nq-muted');
    count.title = 'The Non-Qualified Calls this rule explains now';
    head.append(enabled, name, count);
    iconButtons(head, block, () => block.remove());
    const scope = node('div', undefined, 'nq-option-row nq-dta-scope');
    scope.append(node('span', 'For', 'nq-rule-word'));
    Object.entries(state.dtaRca.services || {}).forEach(([key, label]) => {
      const toggle = node('label', undefined, 'nq-toggle nq-dta-service');
      const box = node('input');
      box.type = 'checkbox';
      box.value = key;
      box.checked = (rule.services || []).includes(key);
      toggle.append(box, ` ${label}`);
      scope.append(toggle);
    });
    scope.append(node('span', '(none: every service), when', 'nq-rule-word'),
      selectOf('nq-dta-match', 'Conditions that must hold', Object.entries(state.dtaRca.matches || {}), rule.match || 'all'),
      node('span', 'hold', 'nq-rule-word'));
    const conditions = node('ul', undefined, 'nq-conditions');
    conditions.append(...(rule.conditions || []).map((condition) => dtaConditionRow(condition?.input ? condition : undefined)));
    const add = node('button', 'Add Condition', 'nq-link-action');
    add.type = 'button';
    add.addEventListener('click', () => conditions.append(dtaConditionRow()));
    const result = node('div', undefined, 'nq-option-row nq-dta-result');
    const category = selectOf('nq-dta-category nq-pill-select', 'Root Category', dtaCatalogEntries('categories', rule.category, 'No category'), rule.category || '');
    const cause = selectOf('nq-dta-cause nq-pill-select', 'Root Cause', dtaCatalogEntries('causes', rule.cause, 'No cause'), rule.cause || '');
    const paint = () => {
      paintPill(category, optionColor('root_category', category.value));
      paintPill(cause, optionColor('root_cause', cause.value));
    };
    category.addEventListener('change', paint);
    cause.addEventListener('change', paint);
    result.append(node('span', 'gives the Root Category', 'nq-rule-word'), category, node('span', 'and the Root Cause', 'nq-rule-word'), cause);
    block.append(head, scope, conditions, add, result);
    paint();
    return block;
  };
  const collectDtaRules = () => [...$('nq-dta-rules').children].filter((block) => block.matches('.nq-dta-rule')).map((block) => ({
    key: block.dataset.key || '', name: block.querySelector('.nq-dta-name').value.trim(),
    enabled: block.querySelector('.nq-dta-enabled').checked,
    services: [...block.querySelectorAll('.nq-dta-service input:checked')].map((box) => box.value),
    match: block.querySelector('.nq-dta-match').value,
    conditions: [...block.querySelectorAll('.nq-dta-condition')].map((row) => ({
      input: row.querySelector('.nq-dta-input').value, op: row.querySelector('.nq-dta-op').value, value: row.querySelector('.nq-dta-value').value,
    })),
    category: block.querySelector('.nq-dta-category').value, cause: block.querySelector('.nq-dta-cause').value,
  }));
  const fillDtaRules = (rules) => {
    $('nq-dta-rules').replaceChildren(...rules.map((rule) => dtaRuleBlock(rule)));
    const enabled = rules.filter((rule) => rule.enabled !== false).length;
    // The calls of the last rule (Not identified) apart: no rule explains them.
    const last = (dtaRules.rules || []).find((rule) => rule.key === 'not-identified');
    const unexplained = last ? (dtaRules.counts[last.name] || 0) : 0;
    const total = Object.values(dtaRules.counts || {}).reduce((sum, value) => sum + value, 0);
    $('nq-dta-rules-summary').textContent = `${number(rules.length)} rules, ${number(enabled)} enabled · ${number(total - unexplained)} Non-Qualified Calls `
      + `with a root cause found from their CDR, ${number(unexplained)} not identified`
      + `${dtaRules.settings?.learn ? ` · ${number(dtaRules.learned || 0)} learned from the analysts` : ''}`
      + `${dtaRules.pending ? ' · the calls take the rules when the indexing of the CDRs ends' : ''}.`;
  };
  if (dtaRulesDialog) {
    document.querySelectorAll('[data-nq-dta-rules-open]').forEach((button) => button.addEventListener('click', async () => {
      $('nq-dta-rules-error').textContent = '';
      try {
        dtaRules = await api('/api/non-qualified-calls/dta-rca/rules');
      } catch (error) {
        toast(error.message, 'error');
        return;
      }
      dtaDefaultsShown = false;
      $('nq-dta-learn').checked = Boolean(dtaRules.settings?.learn);
      $('nq-dta-learn-min').textContent = String(dtaRules.learning_min_decisions || 2);
      fillDtaRules(dtaRules.rules);
      dtaRulesDialog.showModal();
    }));
    $('nq-dta-rules').addEventListener('input', () => { dtaDefaultsShown = false; });
    $('nq-dta-rules').addEventListener('click', (event) => { if (event.target.closest('button')) dtaDefaultsShown = false; });
    $('nq-dta-rules-cancel').addEventListener('click', () => dtaRulesDialog.close());
    $('nq-dta-rules-add').addEventListener('click', () => {
      const block = dtaRuleBlock();
      $('nq-dta-rules').append(block);
      block.querySelector('.nq-dta-name').focus();
    });
    $('nq-dta-rules-default').addEventListener('click', () => {
      fillDtaRules(dtaRules.defaults || []);
      dtaDefaultsShown = true;
      $('nq-dta-rules-error').style.color = 'var(--nq-muted)';
      $('nq-dta-rules-error').textContent = 'The default rules are shown: review them and Save.';
    });
    $('nq-dta-rules-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const save = $('nq-dta-rules-save');
      save.disabled = true;
      try {
        const saved = await api('/api/non-qualified-calls/dta-rca/rules', {method: 'PUT',
          body: JSON.stringify({rules: collectDtaRules(), defaults: dtaDefaultsShown, learn: $('nq-dta-learn').checked})});
        dtaRulesDialog.close();
        toast(saved.calculated === null || saved.calculated === undefined
          ? 'DT Analyzer RCA Rules saved: the calls take them when the indexing of the CDRs ends.'
          : `DT Analyzer RCA Rules saved: ${number(saved.calculated)} calls calculated again.`);
        await loadState();
        if (state.detail) openDetail(state.detail.call.call_key, {keepTab: true});
      } catch (error) {
        $('nq-dta-rules-error').style.color = '';
        $('nq-dta-rules-error').textContent = error.message;
      } finally {
        save.disabled = false;
      }
    });
  }

  // -- Prioritization Rules dialog (admins and super-admins change them) ---------------------------------
  const priorityDialog = $('nq-priority-dialog');
  const PRIORITY_INPUTS = {high_share: 'nq-priority-high', medium_share: 'nq-priority-medium', min_calls: 'nq-priority-min-calls',
    previous_quarters: 'nq-priority-quarters', cluster_isd: 'nq-priority-cluster-isd', spot_meters: 'nq-priority-spot',
    cluster_road_meters: 'nq-priority-cluster-roads', consecutive_minutes: 'nq-priority-consecutive-minutes',
    consecutive_isd: 'nq-priority-consecutive-isd', consecutive_city_meters: 'nq-priority-consecutive-city',
    consecutive_road_meters: 'nq-priority-consecutive-roads', capacity: 'nq-priority-capacity'};
  // The settings chosen from a list (not numbers).
  const PRIORITY_CHOICES = {hotspot_join: 'nq-priority-hotspot-join'};
  // Every setting of the levels as the dialog holds it.
  const levelSettings = () => ({...Object.fromEntries(Object.entries(PRIORITY_INPUTS).map(([key, id]) => [key, Number($(id).value)])),
    ...Object.fromEntries(Object.entries(PRIORITY_CHOICES).map(([key, id]) => [key, $(id).value]))});
  // Every field of the steps of each strategy while the dialog is open (admins change them).
  let strategySteps = {};
  const FOCUSED = '@focused';
  const EVERY_CALL = 'all';
  const STEP_PRIORITIES = ['P1', 'P2', 'P3', 'P4', 'P5', 'P6', 'P7', 'P8'];
  // The step whose handle takes the focus again once a step moved with the arrow keys is drawn in its new place.
  let focusedStep = '';
  // The Priority whose handle takes the focus once the steps are drawn again (after it moved with the arrow keys).
  let focusedGroup = '';
  // The list of steps the dialog shows: list 1 (Weekly CDRs, during the campaign) or list 2 (once the Final CDR is scored).
  let stepList = 'campaign';
  // Whether each strategy applies its list 2 once the Final CDR is scored, while the dialog is open.
  let strategyFinalLists = {};
  // The strategies of the admins (key and name), and the names they gave those of the application, while the dialog is open.
  let ownStrategies = [];
  let strategyNames = {};
  const ADDED_STEP = /^(campaign|final)-s\d+$/;
  const MAX_LIST_STEPS = 20;
  const STEP_LISTS = {campaign: ['Weekly CDRs', 'List 1 · during the campaign (scoring-based conditions are not stable during the campaign and are not recommended)'],
    final: ['Final CDRs', 'List 2 · once Final CDR of the campaign is scored, the real impact of each call can be measured, so scoring-based conditions are recommended']};
  // A multi-select whose first value stands alone (Every call, Focused Operators): while it is chosen, the other values are
  // cleared and cannot be chosen; else every value chosen shows, joined with &.
  const aloneFirstSelect = (className, label, entries, chosen, emptyLabel, onChange) => {
    const select = node('select', undefined, className);
    select.multiple = true;
    select.setAttribute('aria-label', label);
    select.dataset.multiselectEmptyLabel = emptyLabel;
    select.dataset.multiselectJoiner = ' & ';
    select.append(...entries.map(([value, text, title, shortLabel]) => {
      const option = node('option', text);
      option.value = value;
      option.selected = chosen.includes(value);
      if (title) option.title = title;
      if (shortLabel) option.dataset.shortLabel = shortLabel;
      return option;
    }));
    const sync = () => {
      const alone = select.options[0].selected;
      [...select.options].slice(1).forEach((option) => {
        option.disabled = alone;
        if (alone) option.selected = false;
      });
      onChange([...select.selectedOptions].map((option) => option.value));
    };
    sync();
    select.addEventListener('change', () => {
      sync();
      select.dispatchEvent(new Event('multiselect:options-updated'));
    });
    return select;
  };
  // The operators a step takes: Focused Operators first, then the operators of the workspace (a chosen one the workspace
  // no longer has stays).
  const stepOperators = (chosen, rule) => {
    const focus = state.focusOperators.length ? state.focusOperators.join(', ') : 'every operator, as the workspace has no Focus operator';
    const values = [FOCUSED, ...state.prioritizationOperators, ...chosen.operators.filter((value) => value !== FOCUSED
      && !state.prioritizationOperators.includes(value))];
    return aloneFirstSelect('nq-priority-step-operators', `Operators of ${rule}`,
      values.map((value) => (value === FOCUSED ? [value, 'Focused Operators', `The Focus operators of the Operator Maps: ${focus}`, 'Focused'] : [value, value])),
      chosen.operators, 'No operator', (operators) => { chosen.operators = operators; });
  };
  // The conditions a step of a list can take, whatever its Call Type.
  const stepConditions = (list) => Object.entries((state.prioritizationFields.conditions || {})[list] || {});
  const MAX_CONDITIONS = 6;
  const fitCanvas = document.createElement('canvas').getContext('2d');
  // A select as wide as its chosen value (with its padding and the arrow of the browser, about 24 px), so the conditions
  // of a step share a line.
  const SELECT_ARROW = 24;
  const fitSelect = (select) => {
    const style = getComputedStyle(select);
    fitCanvas.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
    const edges = ['paddingLeft', 'paddingRight', 'borderLeftWidth', 'borderRightWidth'].reduce((sum, name) => sum + (parseFloat(style[name]) || 0), 0);
    select.style.width = `${Math.ceil(fitCanvas.measureText(select.selectedOptions[0]?.textContent || '').width + edges + SELECT_ARROW)}px`;
  };
  // AND ( and OR ( start a group of conditions: one level of parentheses.
  const CONDITION_JOINS = [['and', 'AND'], ['or', 'OR'], ['and_group', 'AND ('], ['or_group', 'OR (']];
  // The conditions of a step, one per line, each joined to the one before by AND or OR (AND first: "Time-Window Issues
  // AND Hotspots OR High impact" takes the time-window issues of a hotspot and the calls with a High impact), the
  // groups opened by AND ( or OR ( marked by a bracket. Every call stands alone: chosen first, it clears the others.
  const stepConditionEditor = (list, chosen, rule) => {
    const box = node('div', undefined, 'nq-priority-conditions');
    const entries = stepConditions(list);
    // A condition added or removed tells the dialog, as a select does when it changes (the #Calls are counted again).
    const iconButton = (text, className, title, action) => {
      const button = node('button', text, `nq-priority-condition-button ${className}`);
      button.type = 'button';
      button.title = title;
      button.setAttribute('aria-label', `${title} (${rule})`);
      button.addEventListener('click', () => {
        action();
        box.dispatchEvent(new Event('change', {bubbles: true}));
      });
      return button;
    };
    const draw = () => {
      chosen.joins = chosen.conditions.slice(1).map((_, index) => (chosen.joins || [])[index] || 'or');
      // The group of each condition; with several groups, each group of several conditions goes in parentheses.
      const groupOf = chosen.conditions.map((_, index) => chosen.joins.slice(0, index).filter((join) => join.endsWith('_group')).length);
      const groups = groupOf[groupOf.length - 1] + 1;
      const paren = (text) => node('span', text, 'nq-priority-condition-paren');
      // Each condition with the operator before it, on one line while they fit in the cell.
      box.replaceChildren(...chosen.conditions.map((key, index) => {
        const term = node('span', undefined, 'nq-priority-condition');
        const grouped = groups > 1 && groupOf.filter((group) => group === groupOf[index]).length > 1;
        if (index) {
          const join = selectOf('nq-priority-condition-join', `Operator before condition ${index + 1} of ${rule}`, CONDITION_JOINS,
            chosen.joins[index - 1]);
          join.title = 'AND ( and OR ( start a group: the conditions from here to the next group go in parentheses';
          join.addEventListener('change', () => {
            chosen.joins[index - 1] = join.value;
            draw();
          });
          term.append(join);
        }
        if (grouped && groupOf[index - 1] !== groupOf[index]) term.append(paren('('));
        const select = selectOf('nq-priority-condition-key', `Condition ${index + 1} of ${rule}`,
          index ? entries.filter(([value]) => value !== EVERY_CALL) : entries, key);
        // Each condition in its colour (see the list of Conditions).
        select.classList.add('nq-condition-value', `is-cond-${key}`);
        // What the condition means, on hover (the list of Conditions beside the table explains them all), and what it is
        // based on, as a tag in its list.
        const help = state.prioritizationFields.condition_help || {};
        const kinds = state.prioritizationFields.condition_kinds || {};
        select.title = help[key] || '';
        [...select.options].forEach((option) => {
          option.title = help[option.value] || '';
          const [tag, kind] = kinds[option.value] || [];
          if (tag) Object.assign(option.dataset, {tag, tagClass: `nq-condition-tag is-${kind}`});
        });
        select.addEventListener('change', () => {
          chosen.conditions[index] = select.value;
          if (select.value === EVERY_CALL) chosen.conditions = [EVERY_CALL];
          draw();
        });
        term.append(select);
        if (grouped && groupOf[index + 1] !== groupOf[index]) term.append(paren(')'));
        if (chosen.conditions.length > 1) {
          term.append(iconButton('×', 'is-remove', 'Remove this condition', () => {
            chosen.conditions.splice(index, 1);
            chosen.joins.splice(index ? index - 1 : 0, 1);
            draw();
          }));
        }
        // Another condition not chosen yet, joined by OR until another operator is chosen.
        const next = entries.find(([value]) => value !== EVERY_CALL && !chosen.conditions.includes(value));
        if (index === chosen.conditions.length - 1 && chosen.conditions[0] !== EVERY_CALL && next && chosen.conditions.length < MAX_CONDITIONS) {
          term.append(iconButton('+', 'is-add', 'Add a condition', () => {
            chosen.conditions.push(next[0]);
            chosen.joins.push('or');
            draw();
          }));
        }
        return term;
      }));
      if (box.isConnected) box.querySelectorAll('select').forEach(fitSelect);
    };
    draw();
    return box;
  };
  // The NR Mode out of scope of each operator chosen in an Out of Scope select of operators: SA, NSA or ALL (both).
  const scopeOperatorModes = new WeakMap();
  const SCOPE_MODES = [['SA', 'SA'], ['NSA', 'NSA'], ['ALL', 'All']];
  // The operators out of scope that cannot be changed here, with their NR Mode: those that are not Focus operators (All)
  // and those whose label in the Operator Maps has no network in an NR Mode (SA · Three), out of scope in every module.
  const fixedScopeModes = () => {
    const modes = new Map();
    (state.prioritizationMapModes || []).forEach((item) => modes.set(item.operator, modes.has(item.operator) ? 'ALL' : item.nr_mode));
    (state.prioritizationFixedModes || []).forEach((item) => modes.set(item.operator, 'ALL'));
    return modes;
  };
  // Under the select, each operator chosen with its NR Mode; those out of scope always (grey) show theirs, with a note that
  // tells why.
  const renderScopeOperatorModes = (select) => {
    const host = document.querySelector(`[data-nq-scope-modes="${select.id}"]`);
    if (!host) return;
    const modes = scopeOperatorModes.get(select) || new Map();
    scopeOperatorModes.set(select, modes);
    const chosen = [...select.selectedOptions];
    host.replaceChildren(...chosen.map((option) => {
      const name = option.value;
      const row = node('span', undefined, 'nq-scope-operator-mode');
      row.classList.toggle('is-fixed', option.disabled);
      row.title = option.disabled ? option.dataset.disabledReason || '' : `The NR Mode of the calls of ${name} out of scope (All: both)`;
      const choice = node('span', undefined, 'nq-scope-mode-choice');
      choice.setAttribute('role', 'radiogroup');
      choice.setAttribute('aria-label', `NR Mode of ${name} out of scope`);
      const current = option.disabled ? fixedScopeModes().get(name) || 'ALL' : modes.get(name) || 'ALL';
      choice.append(...SCOPE_MODES.map(([value, label]) => {
        const item = node('label');
        const input = node('input');
        input.type = 'radio';
        input.name = `${select.id}:${name}`;
        input.value = value;
        input.checked = value === current;
        input.disabled = option.disabled;
        input.addEventListener('change', () => modes.set(name, value));
        item.append(input, label);
        return item;
      }));
      row.append(node('span', name, 'nq-scope-operator-name'), choice);
      return row;
    }));
    const notFocus = new Set((state.prioritizationFixedModes || []).map((item) => item.operator));
    if (chosen.some((option) => option.disabled && notFocus.has(option.value))) {
      host.append(node('p', 'The operators that are not Focus operators of the Operator Maps are always out of scope, in both SA and NSA.', 'nq-scope-fixed-note'));
    }
    if (chosen.some((option) => option.disabled && !notFocus.has(option.value))) {
      host.append(node('p', 'The NR Modes of each label in the Operator Maps leave out its calls of an NR Mode it has no network in (such as SA · Three), in every module.', 'nq-scope-fixed-note'));
    }
    host.hidden = !host.children.length;
  };
  // The NR Mode · operator pairs out of scope chosen with a select of operators (the grey ones are always out of scope).
  const excludedModesOf = (select) => {
    const modes = scopeOperatorModes.get(select) || new Map();
    return [...select.selectedOptions].filter((option) => !option.disabled).flatMap((option) => {
      const mode = modes.get(option.value) || 'ALL';
      return (mode === 'ALL' ? ['SA', 'NSA'] : [mode]).map((nrMode) => ({nr_mode: nrMode, operator: option.value}));
    });
  };
  // The NR Mode · operator pairs out of scope chosen in the dialog.
  const excludedModes = () => excludedModesOf($('nq-priority-modes-out'));
  // #Calls: how many calls each step takes in the latest campaigns with their Final CDR, as the steps are edited.
  let stepCounts = {counts: {}, campaigns: []};
  let stepCountsTimer = null;
  let stepCountsRequest = 0;
  const stepCountText = (id) => (id in stepCounts.counts ? Number(stepCounts.counts[id]).toLocaleString() : '…');
  // An estimate for information, to design the steps and the Voice and Data queues: the calls of the latest closed campaigns.
  const stepCountsTitle = () => (stepCounts.campaigns.length
    ? `Estimate for information: the calls each step would take in ${stepCounts.campaigns.join(' and ')}, the latest campaigns with their Final CDR; ${Number(stepCounts.out_of_scope || 0).toLocaleString()} more are out of scope`
    : 'Estimate for information: the calls each step would take in the latest campaign with its Final CDR');
  // Calls per Queue: a column per Priority of the Voice and Data queues, or of the Unique queue of a strategy of one queue
  // (those of their steps in the list shown), with the calls their steps take from their #Calls, grouped above the queue
  // and its total (the tracked calls only in the note).
  const renderQueueChart = (strategy) => {
    const queues = state.prioritizationFields.queues || {};
    const steps = Object.entries(strategySteps[strategy] || {})
      .filter(([id, step]) => !step.deleted && (id.startsWith('final') ? 'final' : 'campaign') === stepList);
    const counted = steps.every(([id]) => id in stepCounts.counts);
    const totals = Object.fromEntries(Object.keys(queues).map((key) => [key, {}]));
    steps.forEach(([id, step]) => {
      const byPriority = totals[step.queue in totals ? step.queue : ''] || {};
      byPriority[step.priority] = (byPriority[step.priority] || 0) + Number(stepCounts.counts[id] || 0);
    });
    const sum = (byPriority) => Object.values(byPriority).reduce((total, calls) => total + calls, 0);
    const shown = Object.entries(queues).filter(([key]) => key && Object.keys(totals[key]).length);
    const largest = Math.max(1, ...shown.flatMap(([key]) => Object.values(totals[key])));
    $('nq-priority-queue-bars').replaceChildren(...shown.map(([key, label]) => {
      const priorities = STEP_PRIORITIES.filter((priority) => priority in totals[key]);
      const group = node('div', undefined, 'nq-priority-queue-group');
      // The groups share the width by their columns, so that every column is as wide.
      group.style.flexGrow = String(priorities.length);
      const columns = node('div', undefined, 'nq-priority-queue-columns');
      const names = node('div', undefined, 'nq-priority-queue-columns nq-priority-queue-names');
      priorities.forEach((priority) => {
        const calls = totals[key][priority];
        const column = node('span', undefined, 'nq-priority-queue-column');
        column.title = `${label} · ${priority}: ${calls.toLocaleString()} calls`;
        const bar = node('span', undefined, `nq-priority-queue-column-bar is-${priority.toLowerCase()}`);
        bar.style.height = `calc((100% - 1.1rem) * ${calls / largest})`;
        column.append(node('strong', counted ? calls.toLocaleString() : '…', 'nq-priority-queue-column-value'), bar);
        columns.append(column);
        names.append(node('span', priority, 'nq-priority-queue-column-name'));
      });
      group.append(columns, names, node('span', label, `nq-priority-queue-group-name is-${label.toLowerCase()}`),
        node('strong', counted ? sum(totals[key]).toLocaleString() : '…', 'nq-priority-queue-group-total'));
      return group;
    }));
    const notes = [stepList === 'final' ? 'List 2 · once Final CDR is scored' : 'List 1 · as during the campaign'];
    if (stepCounts.campaigns.length) notes.push(`estimate on the latest closed campaign${stepCounts.campaigns.length > 1 ? 's' : ''}: ${stepCounts.campaigns.join(' and ')}`);
    $('nq-priority-queue-chart-note').textContent = notes.join(' · ');
    // The calls of every queue together, in bold (Voice + Data, or the Unique queue of a strategy of one queue).
    $('nq-priority-queue-chart-total').textContent = counted && shown.length
      ? `${shown.map(([, label]) => label).join(' + ')}: ${shown.reduce((calls, [key]) => calls + sum(totals[key]), 0).toLocaleString()} calls` : '';
    renderQueueOutside(counted);
  };
  // The calls outside the Voice and Data queues, in a folded note below the chart (it keeps its state as the counts change):
  // the tracked ones by kind, those no step takes by operator and those out of scope by region or operator without SA.
  const renderQueueOutside = (counted) => {
    const outside = $('nq-priority-queue-outside');
    const detail = (stepCounts.lists || {})[stepList];
    outside.hidden = !counted || !detail;
    if (outside.hidden) return;
    const total = (items) => items.reduce((calls, [, count]) => calls + count, 0);
    // A bullet with its names and calls below it ([name, calls] pairs, or [name, null, pairs] for a group of them).
    const entryList = (entries) => {
      const sub = node('ul');
      sub.append(...entries.map(([name, count, children]) => {
        const entry = node('li', count === null ? name : `${name}: ${count.toLocaleString()}`);
        if (children?.length) entry.append(entryList(children));
        return entry;
      }));
      return sub;
    };
    const item = (title, calls, note, entries) => {
      const line = node('li');
      line.append(node('strong', `${title} · ${calls.toLocaleString()}`), document.createTextNode(note ? ` — ${note}` : ''));
      if (entries.length) line.append(entryList(entries));
      return line;
    };
    const scope = stepCounts.scope || {regions: [], operators: [], modes: []};
    const lines = [];
    // The tracked calls by kind, then by operator with the NR Mode of their campaigns (Three NSA).
    if (detail.tracked.length) {
      lines.push(item('Tracked', total(detail.tracked), 'only a Tracked step takes them', [...detail.tracked,
        ['By operator', null, detail.tracked_operators]]));
    }
    if (detail.untaken.length) lines.push(item('Taken by no step', total(detail.untaken), 'no step takes their operator', detail.untaken));
    if (stepCounts.out_of_scope) {
      lines.push(item('Out of scope', Number(stepCounts.out_of_scope), 'in no queue and not tracked', [
        ...scope.regions.map(([name, count]) => [`Region ${name} (every operator)`, count]),
        ...(scope.operators || []).map(([name, count]) => [`${name} (not a Focus operator)`, count]),
        ...(scope.modes || []).map(([name, count]) => [name, count])]));
    }
    const calls = lines.length ? total(detail.tracked) + total(detail.untaken) + Number(stepCounts.out_of_scope || 0) : 0;
    outside.querySelector('summary').textContent = `Calls outside the Voice and Data queues · ${calls.toLocaleString()}`;
    outside.querySelector('ul').replaceChildren(...lines);
    outside.hidden = !lines.length;
  };
  const scheduleStepCounts = (strategy) => {
    clearTimeout(stepCountsTimer);
    stepCountsTimer = setTimeout(async () => {
      const request = ++stepCountsRequest;
      try {
        // The levels too: the clusters and hotspots are counted again with those being edited.
        const settings = {strategy, steps: strategySteps, strategies: ownStrategies, final_lists: strategyFinalLists,
          excluded_regions: [...$('nq-priority-regions-out').selectedOptions].map((option) => option.value),
          excluded_modes: excludedModes(), ...levelSettings()};
        const result = await api('/api/non-qualified-calls/prioritization/step-counts', {method: 'POST', body: JSON.stringify({settings})});
        if (request !== stepCountsRequest) return;
        stepCounts = result;
        $('nq-priority-steps').querySelectorAll('tr[data-step]').forEach((row) => {
          const cell = row.querySelector('.nq-priority-step-calls');
          if (cell) cell.textContent = stepCountText(row.dataset.step);
        });
        const head = $('nq-priority-steps').querySelector('th.nq-priority-step-calls');
        if (head) head.title = stepCountsTitle();
        renderQueueChart(strategy);
      } catch (error) {
        // Without the counts the column keeps its dots.
      }
    }, 350);
  };
  const renderStrategySteps = (strategy) => {
    const fields = state.prioritizationFields;
    // The steps of the strategy as the dialog holds them: the default ones but those deleted, and those added.
    const steps = Object.keys(strategySteps[strategy] || {}).filter((id) => !strategySteps[strategy][id].deleted)
      .map((id) => ({id, list: id.startsWith('final') ? 'final' : 'campaign'}));
    const rank = (name) => STEP_PRIORITIES.indexOf(name);
    const rerender = () => renderStrategySteps(strategy);
    const table = (list) => {
      const box = node('div', undefined, 'nq-priority-steps-list');
      const grid = node('table', undefined, 'nq-failure-table nq-priority-steps-table');
      const names = ['priority', 'move', 'mode', 'operators', 'type', 'area', 'condition', 'calls', 'queue'];
      const columns = node('colgroup');
      columns.append(...names.map((name) => node('col', undefined, `nq-step-col-${name}`)));
      const head = node('tr');
      head.append(...['Priority', 'Step', 'NR Mode', 'Operators', 'Call Type', 'Area', 'Condition', '#Calls', 'Queue'].map((text) => node('th', text)));
      head.children[1].title = 'The place of the step in its list, from the order of the rows (it names its Prioritization Rule): drag it by ⠿, delete it with ×';
      const callsHead = head.children[7];
      callsHead.className = 'nq-priority-step-calls';
      callsHead.title = stepCountsTitle();
      const body = node('tbody');
      // The steps by Priority, then by number: the steps of one Priority are grouped under it, in the order they are tried.
      const rows = steps.filter((step) => step.list === list).map((step) => ({step, chosen: strategySteps[strategy][step.id]}));
      const byId = new Map(rows.map((item) => [item.step.id, item]));
      const sorted = () => [...rows].sort((a, b) => rank(a.chosen.priority) - rank(b.chosen.priority) || a.chosen.number - b.chosen.number);
      const ordered = sorted();
      // The order of the rows is the order of the steps: they take their numbers from it.
      const renumber = (items) => items.forEach((item, index) => { item.chosen.number = index + 1; });
      // A step moved before or after another takes its Priority and its place; moved onto a Priority without steps, that
      // Priority after the steps of the Priorities before it.
      const place = (moved, target, after, priority) => {
        const items = ordered.filter((item) => item !== moved);
        if (target) {
          items.splice(items.indexOf(target) + (after ? 1 : 0), 0, moved);
          moved.chosen.priority = target.chosen.priority;
        } else {
          moved.chosen.priority = priority;
          const index = items.findIndex((item) => rank(item.chosen.priority) > rank(priority));
          items.splice(index === -1 ? items.length : index, 0, moved);
        }
        renumber(items);
        rerender();
      };
      let dragging = null;
      // The Priority dragged as a block by the handle before it.
      let draggingGroup = '';
      const clearMarks = () => body.querySelectorAll('.is-drop-before, .is-drop-after, .is-drop-into')
        .forEach((element) => element.classList.remove('is-drop-before', 'is-drop-after', 'is-drop-into'));
      // A Priority moved onto another swaps with it: its steps take that Priority and those of the other one take its own
      // (onto a Priority without steps, its steps just take it); the steps keep their order inside each Priority.
      const swapPriorities = (from, to) => {
        if (!to || from === to) return;
        rows.forEach((item) => {
          if (item.chosen.priority === from) item.chosen.priority = to;
          else if (item.chosen.priority === to) item.chosen.priority = from;
        });
        renumber(sorted());
        rerender();
      };
      // The Priority a dragged Priority would swap with: that of the step or of the Priority without steps under the
      // pointer, its whole block marked.
      const groupTarget = (event) => {
        const row = event.target.closest('tr');
        const priority = row && body.contains(row) ? row.dataset.priority : '';
        if (!priority || priority === draggingGroup) return null;
        return {priority, marks: [...body.querySelectorAll(`tr[data-priority="${priority}"]`)]};
      };
      // Where a dragged step would go: before or after the row under the pointer, at the end of the group whose Priority
      // is under it, or onto a Priority without steps.
      const dropTarget = (event) => {
        const groupCell = event.target.closest('td.nq-priority-step-group');
        const row = event.target.closest('tr');
        if (!row || !body.contains(row)) return null;
        if (row.dataset.empty) return {mark: row, priority: row.dataset.priority};
        if (groupCell) {
          const group = ordered.filter((item) => item.chosen.priority === groupCell.dataset.priority);
          return {mark: groupCell, target: group[group.length - 1], after: true};
        }
        const {top, height} = row.getBoundingClientRect();
        const after = event.clientY > top + height / 2;
        return {mark: row, className: after ? 'is-drop-after' : 'is-drop-before', target: byId.get(row.dataset.step), after};
      };
      body.addEventListener('dragover', (event) => {
        const found = dragging ? dropTarget(event) : draggingGroup ? groupTarget(event) : null;
        if (!found) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';
        clearMarks();
        (found.marks || [found.mark]).forEach((element) => element.classList.add(found.className || 'is-drop-into'));
      });
      body.addEventListener('dragleave', (event) => {
        if (!body.contains(event.relatedTarget)) clearMarks();
      });
      body.addEventListener('drop', (event) => {
        const found = dragging ? dropTarget(event) : draggingGroup ? groupTarget(event) : null;
        if (!found) return;
        event.preventDefault();
        if (draggingGroup) {
          const from = draggingGroup;
          draggingGroup = '';
          clearMarks();
          swapPriorities(from, found.priority);
          return;
        }
        const moved = dragging;
        dragging = null;
        clearMarks();
        if (found.target !== moved) place(moved, found.target, found.after, found.priority);
      });
      STEP_PRIORITIES.forEach((name) => {
        const group = ordered.filter((item) => item.chosen.priority === name);
        // A Priority without steps takes a dragged step.
        if (!group.length) {
          const empty = node('tr', undefined, 'nq-priority-step-empty');
          Object.assign(empty.dataset, {empty: 'true', priority: name});
          const hint = node('td', `Drop a step here to give it ${name}`);
          hint.colSpan = names.length - 1;
          empty.append(node('td', name, 'nq-priority-step-group'), hint);
          body.append(empty);
          return;
        }
        group.forEach((item, index) => {
          const {step, chosen} = item;
          const row = node('tr');
          row.dataset.step = step.id;
          row.dataset.priority = name;
          const rule = `${list === 'campaign' ? 'Campaign' : 'Final'} ${chosen.number}`;
          // The Priority of a group moves every step of it.
          if (!index) {
            const cell = node('td', undefined, 'nq-priority-step-group');
            cell.rowSpan = group.length;
            cell.dataset.priority = name;
            const priority = selectOf('nq-priority-step-priority', `Priority of the steps of ${name}`, STEP_PRIORITIES.map((value) => [value, value]), name);
            // Each Priority in its colour, from red (P1) to grey (P8).
            priority.classList.add(`is-${name.toLowerCase()}`);
            priority.addEventListener('change', () => {
              group.forEach((member) => { member.chosen.priority = priority.value; });
              renumber(sorted());
              rerender();
            });
            // The handle before the Priority moves the whole block: dragged onto another Priority, or with the arrow keys
            // onto the one above or below, the two swap.
            const blockHandle = node('button', '⠿', 'nq-priority-step-handle nq-priority-group-handle');
            blockHandle.type = 'button';
            blockHandle.title = `Drag ${name} onto another Priority to swap them (its steps take that Priority and those of the other one take ${name}), or use the arrow keys`;
            blockHandle.setAttribute('aria-label', `Move the steps of ${name}: drag them onto another Priority, or use the arrow keys`);
            blockHandle.addEventListener('pointerdown', () => {
              cell.draggable = true;
              document.addEventListener('pointerup', () => { if (!draggingGroup) cell.draggable = false; }, {once: true});
            });
            blockHandle.addEventListener('keydown', (event) => {
              if (!['ArrowUp', 'ArrowDown'].includes(event.key)) return;
              event.preventDefault();
              const next = STEP_PRIORITIES[STEP_PRIORITIES.indexOf(name) + (event.key === 'ArrowUp' ? -1 : 1)];
              if (!next) return;
              focusedGroup = next;
              swapPriorities(name, next);
            });
            cell.addEventListener('dragstart', (event) => {
              if (!cell.draggable) return;
              draggingGroup = name;
              event.dataTransfer.effectAllowed = 'move';
              event.dataTransfer.setData('text/plain', name);
              body.querySelectorAll(`tr[data-priority="${name}"]`).forEach((member) => member.classList.add('is-dragging'));
              // The Priorities without steps show once the drag has started.
              setTimeout(() => grid.classList.add('is-dragging'));
            });
            cell.addEventListener('dragend', () => {
              draggingGroup = '';
              cell.draggable = false;
              body.querySelectorAll('tr.is-dragging').forEach((member) => member.classList.remove('is-dragging'));
              grid.classList.remove('is-dragging');
              clearMarks();
            });
            const control = node('span', undefined, 'nq-priority-group-control');
            control.append(blockHandle, priority);
            cell.append(control);
            row.classList.add('is-group-start');
            row.append(cell);
          }
          // The handle moves the step: dragged, or one row up or down with the arrow keys (into the next Priority at its
          // edge).
          const move = node('td', undefined, 'nq-priority-step-move');
          const handle = node('button', '⠿', 'nq-priority-step-handle');
          handle.type = 'button';
          handle.title = 'Drag to move this step, or use the arrow keys';
          handle.setAttribute('aria-label', `Move ${rule}: drag it, or use the arrow keys`);
          handle.addEventListener('pointerdown', () => {
            row.draggable = true;
            document.addEventListener('pointerup', () => { if (!dragging) row.draggable = false; }, {once: true});
          });
          handle.addEventListener('keydown', (event) => {
            if (!['ArrowUp', 'ArrowDown'].includes(event.key)) return;
            event.preventDefault();
            const up = event.key === 'ArrowUp';
            const neighbour = ordered[ordered.indexOf(item) + (up ? -1 : 1)];
            if (!neighbour) return;
            focusedStep = step.id;
            const sameGroup = neighbour.chosen.priority === chosen.priority;
            place(item, neighbour, sameGroup ? !up : up);
          });
          // Delete the step (a default step comes back with Default Rules).
          const remove = node('button', '×', 'nq-priority-step-delete');
          remove.type = 'button';
          remove.title = 'Delete this step';
          remove.setAttribute('aria-label', `Delete ${rule}`);
          remove.addEventListener('click', () => {
            if (ADDED_STEP.test(step.id)) delete strategySteps[strategy][step.id];
            else strategySteps[strategy][step.id] = {deleted: true};
            renumber(ordered.filter((other) => other !== item));
            rerender();
          });
          // The step: its place in the list, filled from the order of the rows, between its handle and its ×.
          move.append(handle, node('span', String(chosen.number), 'nq-priority-step-number'), remove);
          row.addEventListener('dragstart', (event) => {
            if (!row.draggable) return;
            dragging = item;
            event.dataTransfer.effectAllowed = 'move';
            event.dataTransfer.setData('text/plain', step.id);
            row.classList.add('is-dragging');
            // The Priorities without steps show once the drag has started.
            setTimeout(() => grid.classList.add('is-dragging'));
          });
          row.addEventListener('dragend', () => {
            dragging = null;
            row.draggable = false;
            row.classList.remove('is-dragging');
            grid.classList.remove('is-dragging');
            clearMarks();
          });
          const mode = node('td');
          const nrMode = selectOf('nq-priority-step-mode', `NR Mode of ${rule}`, Object.entries(fields.nr_modes || {}), chosen.nr_mode);
          // Each NR Mode in its colour: SA purple, NSA green, Any grey.
          const paintMode = () => { nrMode.className = `nq-priority-step-mode is-${String(chosen.nr_mode).toLowerCase()}`; };
          nrMode.addEventListener('change', () => {
            chosen.nr_mode = nrMode.value;
            paintMode();
          });
          paintMode();
          mode.append(nrMode);
          const type = node('td');
          const callType = selectOf('nq-priority-step-type', `Call Type of ${rule}`, Object.entries(fields.call_types || {}), chosen.call_type);
          // The Call Type in the colour of the queue of its step: Voice blue, Data teal, Tracked grey.
          const paintType = () => { callType.className = `nq-priority-step-type is-${(fields.queues[chosen.queue] || 'Tracked').toLowerCase()}`; };
          callType.addEventListener('change', () => {
            chosen.call_type = callType.value;
            paintType();
          });
          paintType();
          type.append(callType);
          // Where the calls failed: Connecting Roads and highways, else Cities (from their environment).
          const area = node('td');
          const areaSelect = selectOf('nq-priority-step-area', `Area of ${rule}`, Object.entries(fields.areas || {}), chosen.area);
          areaSelect.addEventListener('change', () => { chosen.area = areaSelect.value; });
          area.append(areaSelect);
          // The conditions, joined by AND or OR.
          const condition = node('td', undefined, 'nq-priority-step-conditions-cell');
          condition.append(stepConditionEditor(list, chosen, rule));
          const operators = node('td', undefined, 'nq-priority-step-operators-cell');
          operators.append(stepOperators(chosen, rule));
          // The queue as a tag of its colour; Tracked: the calls of the step stay out of the queues.
          const queue = node('td', undefined, 'nq-priority-step-queue');
          const queueSelect = selectOf('nq-priority-step-queue-select', `Queue of ${rule}`, Object.entries(fields.queues || {}), chosen.queue);
          const paint = () => {
            queueSelect.className = `nq-priority-step-queue-select is-${(fields.queues[chosen.queue] || 'Tracked').toLowerCase()}`;
          };
          queueSelect.addEventListener('change', () => {
            chosen.queue = queueSelect.value;
            paint();
            paintType();
          });
          paint();
          queue.append(queueSelect);
          // The calls the step takes in the latest campaigns with their Final CDR (counted on the server as the steps change).
          const calls = node('td', stepCountText(step.id), 'nq-priority-step-calls');
          row.append(move, mode, operators, type, area, condition, calls, queue);
          body.append(row);
        });
      });
      const thead = node('thead');
      thead.append(head);
      grid.append(columns, thead, body);
      // The switch between the two lists, above the table.
      const listHead = node('div', undefined, 'nq-priority-steps-head');
      const switcher = node('span', undefined, 'nq-rate-tabs');
      switcher.setAttribute('role', 'tablist');
      switcher.setAttribute('aria-label', 'List of steps');
      const finalList = strategyFinalLists[strategy] !== false;
      switcher.append(...Object.entries(STEP_LISTS).map(([key, [label, text]]) => {
        const button = node('button', label, `nq-rate-tab${key === list ? ' is-active' : ''}`);
        button.type = 'button';
        button.title = text;
        // Without list 2, list 1 takes every call: the Final CDRs list is not used.
        button.disabled = key === 'final' && !finalList;
        button.setAttribute('role', 'tab');
        button.setAttribute('aria-selected', String(key === list));
        button.addEventListener('click', () => {
          if (stepList === key) return;
          stepList = key;
          rerender();
        });
        return button;
      }));
      // Whether the strategy applies list 2 once the Final CDR of a campaign is scored.
      const toggle = node('label', undefined, 'nq-toggle nq-priority-final-toggle');
      const box2 = node('input');
      box2.type = 'checkbox';
      box2.checked = finalList;
      box2.addEventListener('change', () => {
        strategyFinalLists[strategy] = box2.checked;
        if (!box2.checked) stepList = 'campaign';
        rerender();
      });
      toggle.title = 'Off: list 1 orders every call, also once the Final CDR of its campaign is scored';
      toggle.append(box2, document.createTextNode(' Use List 2 for Final CDRs'));
      listHead.append(switcher, node('strong', list === 'campaign' && !finalList
        ? 'List 1 · used for both (weekly & final) CDRs' : STEP_LISTS[list][1]), toggle);
      // Another step at the end of the list: tracked, every call, until the admins change it.
      const add = node('button', '+ Add step', 'nq-link-action nq-priority-add-step');
      add.type = 'button';
      add.disabled = ordered.length >= MAX_LIST_STEPS;
      add.title = add.disabled ? `A list has at most ${MAX_LIST_STEPS} steps` : 'Add a step at the end of this list';
      add.addEventListener('click', () => {
        const numbers = Object.keys(strategySteps[strategy]).filter((id) => id.startsWith(`${list}-s`)).map((id) => Number(id.split('-s')[1]) || 0);
        strategySteps[strategy][`${list}-s${Math.max(0, ...numbers) + 1}`] = {
          number: ordered.length + 1, priority: 'P8', nr_mode: 'any', call_type: 'any', area: 'any', conditions: [EVERY_CALL], joins: [],
          queue: '', operators: [...(state.prioritizationStepOperators.any || [FOCUSED])]};
        rerender();
      });
      box.append(listHead, grid, add);
      return box;
    };
    // A strategy without list 2 (or with it turned off) shows its list 1, which orders every call.
    if (strategyFinalLists[strategy] === false) stepList = 'campaign';
    $('nq-priority-steps').replaceChildren(table(stepList));
    // What each condition means, in the order of the lists: those based on the scoring and the result start a row of
    // their own, below those of the position and the time.
    const help = fields.condition_help || {};
    const kinds = fields.condition_kinds || {};
    const rowStart = stepConditions(stepList).find(([key]) => (kinds[key] || [])[1] === 'scoring')?.[0];
    $('nq-priority-glossary').replaceChildren(...stepConditions(stepList).map(([key, label]) => {
      const item = node('div', undefined, key === rowStart ? 'is-row-start' : undefined);
      const term = node('dt');
      term.append(node('span', label, `nq-condition-value is-cond-${key}`));
      const [tag, kind] = kinds[key] || [];
      if (tag) term.append(node('span', tag, `nq-condition-tag is-${kind}`));
      item.append(term, node('dd', help[key] || ''));
      return item;
    }));
    $('nq-priority-steps').querySelectorAll('.nq-priority-conditions select').forEach(fitSelect);
    renderQueueChart(strategy);
    // The conditions and operators get the checkbox list of every multi-select of the page.
    if (typeof globalThis.setupCustomMultiSelects === 'function') globalThis.setupCustomMultiSelects();
    scheduleStepCounts(strategy);
    if (focusedGroup) {
      $('nq-priority-steps').querySelector(`td.nq-priority-step-group[data-priority="${focusedGroup}"] .nq-priority-group-handle`)?.focus();
      focusedGroup = '';
    }
    if (focusedStep) {
      $('nq-priority-steps').querySelector(`tr[data-step="${focusedStep}"] .nq-priority-step-handle`)?.focus();
      focusedStep = '';
    }
  };
  const ownStrategy = (key) => ownStrategies.find((item) => item.key === key);
  // The name of a strategy as the dialog holds it.
  const strategyName = (key) => ownStrategy(key)?.name ?? (strategyNames[key] || state.prioritizationStrategies[key] || key);
  // Rename Strategy shows the name of the strategy shown, to change it; the name hides again with another strategy.
  const renameStrategy = () => {
    $('nq-priority-strategy-name-field').hidden = false;
    $('nq-priority-strategy-name').value = strategyName($('nq-priority-strategy').value);
    $('nq-priority-strategy-name').select();
  };
  const showStrategy = (strategy) => {
    // Only the strategies of the admins can be deleted.
    $('nq-priority-strategy-name-field').hidden = true;
    $('nq-priority-strategy-delete').hidden = !ownStrategy(strategy);
    renderStrategySteps(strategy);
  };
  // The strategies of the application, then those of the admins.
  const fillStrategies = (value) => {
    const select = $('nq-priority-strategy');
    select.replaceChildren(...[...Object.keys(state.prioritizationStrategies), ...ownStrategies.map((item) => item.key)].map((key) => [key, strategyName(key)])
      .map(([key, label]) => {
        const option = node('option', label);
        option.value = key;
        return option;
      }));
    select.value = value;
  };
  // The Out of Scope selects (of the Prioritization Rules and of the Out of Scope dialog) as the settings choose them.
  const fillScopeSelects = (regions, modes, settings) => {
    // The regions out of the scope of the team: those of the calls, and those chosen before that no call has now.
    const excluded = settings.excluded_regions || [];
    regions.replaceChildren(...[...state.prioritizationRegions, ...excluded.filter((name) => !state.prioritizationRegions.includes(name))].map((name) => {
      const option = node('option', name);
      option.value = name;
      option.selected = excluded.includes(name);
      return option;
    }));
    regions.dispatchEvent(new Event('multiselect:options-updated'));
    // The operators out of scope, each with its NR Mode (SA, NSA or All), read only: those whose label in the Operator Maps
    // has no network in an NR Mode (out of scope in every module, chosen there) and the operators that are not Focus
    // operators, always out of scope in both NR Modes; chosen and grey with the reason on hover.
    const notFocus = new Set(state.prioritizationFixedModes.map((item) => item.operator));
    const operators = [...fixedScopeModes().keys()].sort((a, b) => Number(notFocus.has(a)) - Number(notFocus.has(b)));
    scopeOperatorModes.set(modes, new Map());
    modes.replaceChildren(...operators.map((name) => {
      const option = node('option', name);
      option.value = name;
      option.disabled = true;
      option.selected = true;
      option.dataset.disabledReason = notFocus.has(name) ? state.prioritizationFixedReason : state.prioritizationMapReason;
      return option;
    }));
    modes.dispatchEvent(new Event('multiselect:options-updated'));
    renderScopeOperatorModes(modes);
  };
  ['nq-priority-modes-out', 'nq-scope-modes'].forEach((id) => $(id)?.addEventListener('change', () => renderScopeOperatorModes($(id))));
  const fillPriorityDialog = (settings) => {
    ownStrategies = JSON.parse(JSON.stringify(settings.strategies || []));
    strategyNames = {...(settings.strategy_names || {})};
    fillStrategies(settings.strategy || 'cities_first');
    const select = $('nq-priority-strategy');
    strategySteps = JSON.parse(JSON.stringify(settings.steps || state.defaultPrioritization.steps || {}));
    stepList = 'campaign';
    strategyFinalLists = {...(settings.final_lists || {})};
    fillScopeSelects($('nq-priority-regions-out'), $('nq-priority-modes-out'), settings);
    Object.entries({...PRIORITY_INPUTS, ...PRIORITY_CHOICES}).forEach(([key, id]) => { $(id).value = settings[key]; });
    $('nq-priority-fill').checked = Boolean(settings.fill_priority);
    showStrategy(select.value);
  };
  let priorityDefaults = false;
  // The settings as the dialog holds them, as they are saved.
  const prioritySettings = () => ({...levelSettings(),
    strategy: $('nq-priority-strategy').value, steps: strategySteps, fill_priority: $('nq-priority-fill').checked,
    excluded_regions: [...$('nq-priority-regions-out').selectedOptions].map((option) => option.value),
    excluded_modes: excludedModes(), final_lists: strategyFinalLists, strategies: ownStrategies, strategy_names: strategyNames});
  // The settings saved (as the dialog showed them once opened or saved): the line below the dialog tells whether the
  // dialog holds changes not saved yet.
  let prioritySaved = '';
  const priorityChanged = () => Boolean(prioritySaved) && JSON.stringify(prioritySettings()) !== prioritySaved;
  // How the strategies work tells the levels as they are set in the dialog.
  const showAboutValues = () => {
    priorityDialog.querySelectorAll('[data-nq-about]').forEach((value) => {
      const input = $(PRIORITY_INPUTS[value.dataset.nqAbout] || PRIORITY_CHOICES[value.dataset.nqAbout]);
      value.textContent = input ? (input.tagName === 'SELECT' ? input.selectedOptions[0]?.textContent || '' : input.value) : '';
    });
  };
  const showSaveState = () => {
    showAboutValues();
    const line = $('nq-priority-save-state');
    if (!line) return;
    const changed = priorityChanged();
    line.textContent = changed ? 'Unsaved changes: Save applies them, with the strategy shown.' : 'The current configuration is saved.';
    line.classList.toggle('is-changed', changed);
  };
  // After the handler of the edit has changed the dialog.
  let saveStateTimer = 0;
  const scheduleSaveState = () => {
    clearTimeout(saveStateTimer);
    saveStateTimer = setTimeout(showSaveState, 0);
  };
  const markPrioritySaved = () => {
    prioritySaved = JSON.stringify(prioritySettings());
    showSaveState();
  };
  // Save the settings and keep the dialog open, on the strategy and the list shown; true once saved.
  const savePriority = async () => {
    const save = $('nq-priority-save');
    save.disabled = true;
    try {
      const settings = prioritySettings();
      const result = await api('/api/non-qualified-calls/prioritization/settings', {method: 'PUT', body: JSON.stringify({settings, defaults: priorityDefaults})});
      state.prioritization = result.settings;
      priorityKey = '';
      const list = stepList;
      fillPriorityDialog(result.settings);
      if (list === 'final' && strategyFinalLists[result.settings.strategy] !== false) {
        stepList = list;
        showStrategy(result.settings.strategy);
      }
      priorityDefaults = false;
      $('nq-priority-error').textContent = '';
      markPrioritySaved();
      await loadState();
      if (state.detail) openDetail(state.detail.call.call_key, {keepTab: true});
      return true;
    } catch (error) {
      $('nq-priority-error').style.color = '';
      $('nq-priority-error').textContent = error.message;
      return false;
    } finally {
      save.disabled = false;
    }
  };
  // Closing the dialog with changes not saved asks first: save them, discard them or continue editing.
  const requestPriorityClose = async () => {
    if (!priorityChanged() || $('nq-priority-save').hidden) {
      priorityDialog.close();
      return;
    }
    const choice = typeof window.showConfirmDialog === 'function'
      ? await window.showConfirmDialog('The Prioritization Rules have changes not saved yet.', {title: 'Unsaved changes', confirmLabel: 'Save',
        secondaryLabel: 'Discard', cancelLabel: 'Continue Editing'})
      : (window.confirm('The Prioritization Rules have changes not saved yet. Discard them?') ? 'secondary' : null);
    if (choice === 'secondary' || (choice === 'confirm' && await savePriority())) priorityDialog.close();
  };
  if (priorityDialog) {
    document.querySelectorAll('[data-nq-prioritization-open]').forEach((button) => button.addEventListener('click', () => {
      if (!state.prioritization) return;
      priorityDefaults = false;
      fillPriorityDialog(state.prioritization);
      $('nq-priority-error').textContent = '';
      priorityDialog.showModal();
      markPrioritySaved();
    }));
    $('nq-priority-cancel').addEventListener('click', requestPriorityClose);
    // Out of Scope, from the button beside NQ Calls in Scope Only: the same regions and NR Mode · Operator pairs as the Out
    // of Scope card above; Save keeps every other setting as it is saved now, and the rules apply at once.
    const scopeDialog = $('nq-scope-dialog');
    const scopeChoice = () => JSON.stringify({regions: [...$('nq-scope-regions').selectedOptions].map((option) => option.value),
      modes: excludedModesOf($('nq-scope-modes'))});
    let scopeSaved = '';
    $('nq-scope-open')?.addEventListener('click', () => {
      if (!state.prioritization || !scopeDialog) return;
      fillScopeSelects($('nq-scope-regions'), $('nq-scope-modes'), state.prioritization);
      $('nq-scope-error').textContent = '';
      scopeDialog.showModal();
      scopeSaved = scopeChoice();
    });
    $('nq-scope-cancel')?.addEventListener('click', () => scopeDialog.close());
    $('nq-scope-form')?.addEventListener('submit', async (event) => {
      event.preventDefault();
      if ($('nq-scope-save').hidden || scopeChoice() === scopeSaved) {
        scopeDialog.close();
        return;
      }
      const save = $('nq-scope-save');
      save.disabled = true;
      try {
        // The other settings as they are saved now (someone may have changed them since the page loaded).
        const current = (await api('/api/non-qualified-calls/prioritization/settings')).settings;
        const settings = {...current, excluded_regions: [...$('nq-scope-regions').selectedOptions].map((option) => option.value),
          excluded_modes: excludedModesOf($('nq-scope-modes'))};
        const result = await api('/api/non-qualified-calls/prioritization/settings', {method: 'PUT', body: JSON.stringify({settings})});
        state.prioritization = result.settings;
        priorityKey = '';
        scopeDialog.close();
        toast('The scope is saved: every call takes it at once.');
        await loadState();
      } catch (error) {
        $('nq-scope-error').textContent = error.message;
      } finally {
        save.disabled = false;
      }
    });
    // Escape asks as Cancel does.
    priorityDialog.addEventListener('cancel', (event) => {
      event.preventDefault();
      void requestPriorityClose();
    });
    // The ⓘ of Out of Scope unfolds (or folds) what the card does, below its row (by click, Enter or Space).
    const scopeInfo = priorityDialog.querySelector('.nq-priority-scope-info');
    const toggleScopeAbout = () => {
      const about = $('nq-priority-scope-about');
      about.hidden = !about.hidden;
      scopeInfo.setAttribute('aria-expanded', String(!about.hidden));
    };
    scopeInfo?.addEventListener('click', toggleScopeAbout);
    scopeInfo?.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        toggleScopeAbout();
      }
    });
    // Every edit tells again whether the dialog holds changes not saved.
    ['input', 'change', 'click', 'drop', 'keyup'].forEach((type) => priorityDialog.addEventListener(type, scheduleSaveState));
    $('nq-priority-strategy').addEventListener('change', (event) => showStrategy(event.target.value));
    priorityDialog.addEventListener('change', (event) => {
      const strategy = $('nq-priority-strategy').value;
      if (!['nq-priority-strategy', 'nq-priority-strategy-name'].includes(event.target.id)) scheduleStepCounts(strategy);
    });
    // A new strategy starts as a copy of the strategy shown.
    $('nq-priority-strategy-new').addEventListener('click', () => {
      const source = $('nq-priority-strategy').value;
      const key = `strategy-${Date.now().toString(36)}`;
      const names = new Set([...Object.keys(state.prioritizationStrategies), ...ownStrategies.map((item) => item.key)].map((name) => strategyName(name).toLowerCase()));
      let index = 1;
      while (names.has(`new strategy ${index}`)) index += 1;
      ownStrategies.push({key, name: `New strategy ${index}`});
      const copy = {};
      ['campaign', 'final'].forEach((list) => {
        Object.entries(strategySteps[source] || {}).filter(([id, chosen]) => !chosen.deleted && id.startsWith(list))
          .sort(([, a], [, b]) => STEP_PRIORITIES.indexOf(a.priority) - STEP_PRIORITIES.indexOf(b.priority) || a.number - b.number)
          .forEach(([, chosen], position) => { copy[`${list}-s${position + 1}`] = JSON.parse(JSON.stringify(chosen)); });
      });
      strategySteps[key] = copy;
      strategyFinalLists[key] = strategyFinalLists[source] !== false;
      fillStrategies(key);
      showStrategy(key);
      renameStrategy();
    });
    $('nq-priority-strategy-rename').addEventListener('click', renameStrategy);
    $('nq-priority-strategy-name').addEventListener('input', (event) => {
      const key = $('nq-priority-strategy').value;
      const own = ownStrategy(key);
      if (own) own.name = event.target.value;
      // A strategy of the application without a name of its own keeps its default name.
      else if (event.target.value.trim()) strategyNames[key] = event.target.value;
      else delete strategyNames[key];
      $('nq-priority-strategy').selectedOptions[0].textContent = strategyName(key).trim() || 'Strategy without a name';
    });
    $('nq-priority-strategy-delete').addEventListener('click', async () => {
      const own = ownStrategy($('nq-priority-strategy').value);
      if (!own) return;
      const message = `Delete the strategy ${own.name}? It goes once you save the Prioritization Rules.`;
      const accepted = typeof window.showConfirmDialog === 'function'
        ? await window.showConfirmDialog(message, {title: 'Delete strategy', confirmLabel: 'Delete'}) : window.confirm(message);
      if (!accepted) return;
      ownStrategies = ownStrategies.filter((item) => item !== own);
      delete strategySteps[own.key];
      delete strategyFinalLists[own.key];
      fillStrategies('cities_first');
      showStrategy('cities_first');
    });
    $('nq-priority-default').addEventListener('click', () => {
      // The strategies of the admins and the names of the strategies stay as they are: Default Rules gives back the steps of
      // those of the application.
      const own = ownStrategies.map((item) => item.key);
      fillPriorityDialog({...state.defaultPrioritization, strategies: ownStrategies, strategy_names: strategyNames,
        steps: {...state.defaultPrioritization.steps, ...Object.fromEntries(own.map((key) => [key, strategySteps[key]]))},
        final_lists: {...state.defaultPrioritization.final_lists, ...Object.fromEntries(own.map((key) => [key, strategyFinalLists[key] !== false]))}});
      priorityDefaults = true;
      $('nq-priority-error').style.color = 'var(--nq-muted)';
      $('nq-priority-error').textContent = 'The default strategy, steps and levels are shown: review them and Save.';
    });
    // Save keeps the dialog open: the line below it tells the configuration is saved.
    $('nq-priority-form').addEventListener('submit', (event) => {
      event.preventDefault();
      void savePriority();
    });
  }

  // -- Previous NQ Analyses dialog (admins and super-admins) -------------------------------------
  // Preview the file, then import it (only after a preview of the same file and option).
  const analysesDialog = $('nq-analyses-dialog');
  if (analysesDialog) {
    const form = analysesDialog.querySelector('[data-nq-analyses-form]');
    const file = form.querySelector('[data-nq-analyses-file]');
    const previewButton = form.querySelector('[data-nq-analyses-preview]');
    const importButton = form.querySelector('[data-nq-analyses-import]');
    const error = form.querySelector('[data-nq-analyses-error]');
    const summary = form.querySelector('[data-nq-analyses-summary]');
    // Import Analyses waits for the preview of the chosen file, and tells why while it is disabled.
    const importReady = (ready, reason = 'Preview the file first: its preview enables the import') => {
      importButton.disabled = !ready;
      importButton.title = ready ? '' : reason;
    };
    const reset = () => {
      importReady(false);
      previewButton.disabled = !file.files.length;
      previewButton.title = file.files.length ? 'Read the file without changing anything' : 'Choose a file first: Preview reads it without changing anything';
      form.querySelector('[data-nq-analyses-equivalences-download]').title = file.files.length
        ? 'Every value of the follow-up and list columns of the chosen file, with what it becomes'
        : 'The equivalences the import uses: the rules of the tool and those of this workspace';
      form.querySelector('[data-nq-analyses-name]').textContent = file.files[0]?.name || 'No file chosen';
      summary.hidden = true;
      error.textContent = '';
    };
    file.addEventListener('change', reset);
    form.querySelectorAll('input[name="overwrite"]').forEach((input) => input.addEventListener('change', reset));
    const list = (title, items) => {
      if (!items.length) return null;
      const block = node('div', undefined, 'nq-analyses-list');
      block.append(node('strong', title), node('span', items.join(', ')));
      return block;
    };
    const count = (value, singular, plural = `${singular}s`) => `${number(value)} ${value === 1 ? singular : plural}`;
    // A folded part of the summary: its title with how many items it has (none for the details), and its content.
    const section = (title, size, content, open = false) => {
      const parts = [content].flat().filter(Boolean);
      if (!parts.length || size === 0) return null;
      const block = node('details', undefined, 'nq-analyses-section');
      block.open = open;
      const head = node('summary');
      head.append(node('span', title));
      if (size !== null) head.append(node('span', number(size), 'nq-analyses-count'));
      block.append(head, ...parts);
      return block;
    };
    const chips = (items) => {
      const box = node('div', undefined, 'nq-analyses-chips');
      items.forEach(([label, extra]) => {
        const chip = node('span', label, 'nq-analyses-chip');
        if (extra) chip.append(node('small', extra));
        box.append(chip);
      });
      return box;
    };
    const group = (title, items) => {
      const block = node('div', undefined, 'nq-analyses-group');
      block.append(node('strong', `${title} (${number(items.length)})`), chips(items));
      return block;
    };
    // The summary of a preview or an import: the numbers that matter first, then what the catalog gets and what stays
    // only in the notes, and the details of the file folded.
    const render = (result) => {
      const kpis = node('div', undefined, 'nq-analyses-kpis');
      [
        ['Calls in the file', result.calls, `${count(result.rows, 'row')} in ${count((result.sheets || []).length, 'sheet')}`],
        ['Found in the workspace', result.matched, `${count(result.changed, 'call')} ${result.dry_run ? 'would change' : 'changed'}`],
        ['Waiting for their CDR', result.pending, 'Shown when their CDR is loaded'],
        ['Comments', result.comments, result.dry_run ? 'Would be added' : 'Added'],
        ['Import notes', result.notes, 'What has no field, one per call'],
      ].forEach(([label, value, note]) => {
        const card = node('div', undefined, 'nq-analyses-kpi');
        card.append(node('span', label), node('strong', number(value)), node('small', note));
        kpis.append(card);
      });
      const headline = node('p', result.dry_run
        ? 'Preview: nothing has changed yet; Import Analyses applies it.'
        : 'Imported: the calls show their analyses.', 'nq-analyses-headline');
      const roots = (items) => (items || []).map((item) => [item.value, `${item.domain || 'Auto domain'} · ${number(item.rows)}`]);
      const byField = {};
      (result.new_options || []).forEach((item) => { (byField[item.field] ||= []).push([item.value, number(item.rows)]); });
      const groups = [
        ['Teams', (result.new_teams || []).map((item) => [item.value, number(item.rows)])],
        ['Root Categories', roots(result.new_categories)],
        ['Root Causes', roots(result.new_causes)],
        ...Object.entries(byField),
      ].filter(([, items]) => items.length);
      const dates = [
        result.dated ? `${count(result.dated, 'call')} with the date of their analysis` : '',
        result.estimated ? `${count(result.estimated, 'call')} with the date of the call a week later` : '',
      ].filter(Boolean);
      const apart = [
        result.skipped ? `${count(result.skipped, 'row')} without JOIN_ID or session` : '',
        result.unplaced ? `${count(result.unplaced, 'call')} not loaded yet whose service the file does not tell` : '',
      ].filter(Boolean);
      summary.replaceChildren(...[
        headline,
        kpis,
        dates.length ? list('Dates of the analyses:', dates) : null,
        apart.length ? list('Left out:', apart) : null,
        section('New values in the catalog', groups.reduce((sum, [, items]) => sum + items.length, 0),
          groups.map(([title, items]) => group(title, items)), true),
        section('Domains that change in the catalog', (result.domain_changes || []).length, chips((result.domain_changes || []).map((item) => [
          `${item.value}: ${item.from || 'no domain'} → ${item.to}`, `${item.kind} · ${number(item.rows)}`]))),
        section('Values kept only in the import note', result.invalid_total,
          chips((result.invalid || []).map((item) => [`${item.column}: ${item.value}`, number(item.rows)]))),
        section('Details of the file', null, [
          list('Sheets read:', (result.sheets || []).map((item) => `${item.sheet} (${count(item.rows, 'row')})`)),
          list('Sheets without a JOIN_ID column, left out:', result.sheets_skipped || []),
          list('Columns imported:', result.columns || []),
          list('Columns kept in the import note:', result.noted || []),
          result.cdr_columns ? list('CDR columns before the analysis (already in the tool):', [count(result.cdr_columns, 'column')]) : null,
          list('Read-only columns left out:', result.read_only || []),
          result.duplicates ? list('Calls in several rows (the first row gives the values, the note keeps the others):',
            [count(result.duplicates, 'call')]) : null,
          list('Calls not loaded yet (first ones):', result.unmatched_ids || []),
          list('Calls that could not be changed:', result.failures || []),
        ]),
      ].filter(Boolean));
      summary.hidden = false;
    };
    // Once imported, a dialog over the import tells what the file brought: where its calls went, what they got and what
    // the catalog gained. See the details leaves the whole summary of the import; Done closes both.
    const doneDialog = $('nq-analyses-done');
    const showImportDone = (result, seconds) => {
      doneDialog.querySelector('[data-nq-analyses-done-file]').textContent = [file.files[0]?.name || 'The file',
        `${count(result.rows, 'row')} in ${count((result.sheets || []).length, 'sheet')}`, `${number(seconds)} s`].join(' · ');
      const segments = [
        ['changed', 'Updated', result.changed, 'In the workspace, with their analysis now'],
        ['same', 'Already up to date', Math.max(0, result.matched - result.changed), 'In the workspace, with these values already'],
        ['pending', 'Imported, not in the workspace yet', result.pending, 'Shown when their CDR is loaded'],
        ['left', 'Left out', result.unplaced, 'Not loaded yet, and the file does not tell their service'],
      ].filter(([, , value]) => value);
      const total = Math.max(1, segments.reduce((sum, [, , value]) => sum + value, 0));
      const calls = node('div', undefined, 'nq-done-calls');
      const head = node('div', undefined, 'nq-done-total');
      head.append(node('strong', number(result.calls)), node('span', `call${result.calls === 1 ? '' : 's'} in the file`),
        node('small', `${number(result.matched)} in the workspace · ${number(result.pending)} imported for later`));
      const bar = node('div', undefined, 'nq-done-bar');
      bar.setAttribute('role', 'img');
      bar.setAttribute('aria-label', segments.map(([, label, value]) => `${label}: ${number(value)}`).join(', '));
      const legend = node('ul', undefined, 'nq-done-legend');
      segments.forEach(([kind, label, value, note]) => {
        const part = node('span', undefined, `nq-done-${kind}`);
        part.style.flexGrow = String(value);
        part.title = `${label}: ${number(value)}`;
        bar.append(part);
        const item = node('li', undefined, `nq-done-${kind}`);
        item.append(node('strong', number(value)), node('span', label), node('small', `${Math.round((value * 100) / total)}% · ${note}`));
        legend.append(item);
      });
      calls.append(head, bar, legend);
      const added = ['new_teams', 'new_categories', 'new_causes', 'new_options'].reduce((sum, key) => sum + (result[key] || []).length, 0);
      const kpis = node('div', undefined, 'nq-analyses-kpis');
      [
        ['Comments added', result.comments, 'From the comment columns'],
        ['Import notes', result.notes, 'What has no field, one per call'],
        ['Dated by their analysis', result.dated, result.estimated ? `${number(result.estimated)} a week after the call` : 'Every call'],
        ['New in the catalog', added, `${count((result.domain_changes || []).length, 'domain')} changed`],
        ['Values only in the note', result.invalid_total, 'Not valid for their field'],
      ].forEach(([label, value, note]) => {
        const card = node('div', undefined, 'nq-analyses-kpi');
        card.append(node('span', label), node('strong', number(value || 0)), node('small', note));
        kpis.append(card);
      });
      const apart = [
        result.skipped ? `${count(result.skipped, 'row')} without JOIN_ID or session` : '',
        (result.failures || []).length ? `${count(result.failures.length, 'call')} that could not be changed` : '',
      ].filter(Boolean);
      doneDialog.querySelector('[data-nq-analyses-done-body]').replaceChildren(...[
        calls, kpis, apart.length ? node('p', `Left out: ${apart.join('; ')}.`, 'nq-done-warning') : null,
      ].filter(Boolean));
      doneDialog.showModal();
    };
    doneDialog.querySelector('[data-nq-analyses-done-details]').addEventListener('click', () => doneDialog.close());
    doneDialog.querySelector('[data-nq-analyses-done-close]').addEventListener('click', () => {
      doneDialog.close();
      analysesDialog.close();
    });
    // While the file is previewed or imported, a panel over the dialog tells the step, how far it is and the time.
    const progressBox = analysesDialog.querySelector('[data-nq-analyses-progress]');
    let busy = false;
    let ticker = 0;
    const setProgress = (step, fraction) => {
      progressBox.querySelector('[data-nq-analyses-progress-step]').textContent = step;
      progressBox.querySelector('[data-nq-analyses-progress-bar]').style.width = `${Math.round(Math.min(1, Math.max(0.03, fraction)) * 100)}%`;
    };
    const showProgress = (title) => {
      busy = true;
      const started = Date.now();
      const time = progressBox.querySelector('[data-nq-analyses-progress-time]');
      progressBox.querySelector('[data-nq-analyses-progress-title]').textContent = title;
      setProgress('Sending the file', 0);
      time.textContent = '0 s';
      ticker = window.setInterval(() => { time.textContent = `${number(Math.round((Date.now() - started) / 1000))} s`; }, 1000);
      progressBox.hidden = false;
    };
    const hideProgress = () => {
      busy = false;
      window.clearInterval(ticker);
      progressBox.hidden = true;
    };
    analysesDialog.addEventListener('cancel', (event) => { if (busy) event.preventDefault(); });
    // The equivalences of the chosen file, downloaded to review and uploaded back.
    const equivalencesStatus = form.querySelector('[data-nq-analyses-equivalences-status]');
    const downloadEquivalences = form.querySelector('[data-nq-analyses-equivalences-download]');
    // With a file, its values; without one, the equivalences the import uses (the rules of the tool and the workspace).
    downloadEquivalences.addEventListener('click', async () => {
      error.textContent = '';
      const body = new FormData();
      if (file.files.length) body.append('file', file.files[0]);
      downloadEquivalences.disabled = true;
      equivalencesStatus.textContent = 'Preparing the equivalences…';
      try {
        const response = await fetch('/api/non-qualified-calls/analyses/equivalences', file.files.length
          ? {method: 'POST', credentials: 'same-origin', body} : {credentials: 'same-origin'});
        if (!response.ok) {
          const result = await response.json().catch(() => ({}));
          throw new Error(typeof result.detail === 'string' ? result.detail : 'The equivalences could not be prepared.');
        }
        const link = node('a');
        link.href = URL.createObjectURL(await response.blob());
        link.download = 'NQ_analyses_equivalences.xlsx';
        link.click();
        URL.revokeObjectURL(link.href);
        equivalencesStatus.textContent = 'Review Maps to and the Domain (each cell lists the values it takes), then upload the workbook.';
      } catch (exc) {
        error.textContent = exc.message;
        equivalencesStatus.textContent = '';
      } finally {
        downloadEquivalences.disabled = false;
      }
    });
    const equivalencesFile = form.querySelector('[data-nq-analyses-equivalences-file]');
    equivalencesFile.addEventListener('change', async () => {
      if (!equivalencesFile.files.length) return;
      error.textContent = '';
      const body = new FormData();
      body.append('file', equivalencesFile.files[0]);
      try {
        const response = await fetch('/api/non-qualified-calls/analyses/equivalences', {method: 'PUT', credentials: 'same-origin', body});
        const result = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'The equivalences could not be saved.');
        equivalencesStatus.textContent = `${count(result.saved, 'equivalence')} saved (${number(result.total)} in the workspace). Preview the file again.`;
        importReady(false, 'Preview the file again: the equivalences changed');
        summary.hidden = true;
      } catch (exc) {
        error.textContent = exc.message;
      } finally {
        equivalencesFile.value = '';
      }
    });
    // Forgets the equivalences uploaded for the workspace: the import uses those of the tool again.
    const resetEquivalences = form.querySelector('[data-nq-analyses-equivalences-reset]');
    resetEquivalences.addEventListener('click', async () => {
      const message = 'Forget the equivalences uploaded for this workspace? The import then uses only the equivalences of the tool.';
      const accepted = typeof window.showConfirmDialog === 'function'
        ? await window.showConfirmDialog(message, {title: 'Default Equivalences', confirmLabel: 'Forget'}) : window.confirm(message);
      if (!accepted) return;
      error.textContent = '';
      resetEquivalences.disabled = true;
      try {
        const result = await api('/api/non-qualified-calls/analyses/equivalences', {method: 'DELETE'});
        if (!result.forgotten) {
          equivalencesStatus.textContent = 'This workspace had no equivalences of its own: the import already uses those of the tool.';
          return;
        }
        equivalencesStatus.textContent = `${count(result.forgotten, 'equivalence')} of this workspace forgotten: the import uses those `
          + 'of the tool. Preview the file again.';
        importReady(false, 'Preview the file again: the equivalences changed');
        summary.hidden = true;
      } catch (exc) {
        error.textContent = exc.message;
      } finally {
        resetEquivalences.disabled = false;
      }
    });
    const send = async (preview) => {
      error.textContent = '';
      const body = new FormData();
      body.append('file', file.files[0]);
      body.append('overwrite', form.querySelector('input[name="overwrite"]:checked').value);
      body.append('stream', '1');
      if (preview) body.append('preview', '1');
      previewButton.disabled = importButton.disabled = true;
      showProgress(preview ? 'Previewing the file' : 'Importing the analyses');
      const started = Date.now();
      let completed = null;
      try {
        const response = await fetch('/api/non-qualified-calls/analyses/import', {method: 'POST', credentials: 'same-origin', body});
        if (!response.ok) {
          const failure = await response.json().catch(() => ({}));
          throw new Error(typeof failure.detail === 'string' ? failure.detail : 'The file could not be imported.');
        }
        // One JSON object per line: the progress while the import runs, then its result or its error.
        let result = null;
        const handle = (line) => {
          if (!line.trim()) return;
          const event = JSON.parse(line);
          if (event.error) throw new Error(event.error);
          if (event.result) result = event.result;
          else if (event.step) setProgress(event.step, event.progress);
        };
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        for (;;) {
          const {value, done} = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, {stream: true});
          const lines = buffer.split('\n');
          buffer = lines.pop();
          lines.forEach(handle);
        }
        handle(buffer);
        if (!result) throw new Error('The import stopped before its end: try it again.');
        render(result);
        importReady(preview && Boolean(result.matched || result.pending), preview ? 'The file has no call to import' : 'Preview the file again to import it again');
        if (!preview) {
          loadState();
          completed = result;
        }
      } catch (exc) {
        error.textContent = exc.message;
      } finally {
        hideProgress();
        previewButton.disabled = !file.files.length;
      }
      if (completed) showImportDone(completed, Math.round((Date.now() - started) / 1000));
    };
    $('nq-analyses-open').addEventListener('click', () => {
      form.reset();
      reset();
      analysesDialog.showModal();
    });
    analysesDialog.querySelector('[data-nq-analyses-close]').addEventListener('click', () => analysesDialog.close());
    previewButton.addEventListener('click', () => send(true));
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const overwrite = form.querySelector('input[name="overwrite"]:checked').value === '1';
      const message = 'Replace the values the calls already have with those of the file?';
      if (overwrite && !(typeof window.showConfirmDialog === 'function'
        ? await window.showConfirmDialog(message, {title: 'Replace values', confirmLabel: 'Replace'}) : window.confirm(message))) return;
      send(false);
    });
  }

  // -- Ericsson RCA results dialog ----------------------------------------------------------------
  const rcaDialog = $('nq-rca-dialog');
  let rcaFile = null;
  // Whether the Ericsson RCA categories and causes missing from the Root Cause Catalog are added with the results.
  let rcaAddToCatalog = true;
  const smallTable = (headers, rows) => {
    const wrap = node('div', undefined, 'nq-table-wrap');
    const table = node('table', undefined, 'nq-table nq-stats-table');
    const head = node('thead');
    const headRow = node('tr');
    headRow.append(...headers.map((header) => node('th', header)));
    head.append(headRow);
    const body = node('tbody');
    rows.forEach((values) => {
      const row = node('tr');
      row.append(...values.map((value) => node('td', value)));
      body.append(row);
    });
    table.append(head, body);
    wrap.append(table);
    return wrap;
  };
  const renderRcaCurrent = (summary) => {
    const files = summary.files || [];
    const host = $('nq-rca-current');
    host.replaceChildren(node('h3', 'Imported results'), node('p', summary.total
      ? `${number(summary.total)} results by JOIN_ID; ${number(summary.matched)} match a Non-Qualified Call of this workspace.`
      : 'No result imported yet.', 'form-note'));
    if (files.length) {
      host.append(smallTable(['File', 'Results', 'Imported', 'By'], files.map((file) => [file.name, number(file.rows), exactTime(file.imported_at), file.imported_by])));
    }
    $('nq-rca-clear').hidden = !summary.total || !state.user.can_configure;
  };
  const renderRcaPreview = (preview) => {
    const host = $('nq-rca-preview');
    const facts = [
      `${number(preview.rows)} results by JOIN_ID: ${number(preview.matched)} match a call of this workspace and ${number(preview.unmatched)} do not (yet).`,
      $('nq-rca-replace').checked ? 'Every result imported before is forgotten.'
        : `${number(preview.new)} of them are new; the others replace the results of their JOIN_ID.`,
      `RCA columns: ${preview.columns.join(', ')}.`,
      preview.extra.length ? `Other columns kept with the call: ${preview.extra.join(', ')}.` : '',
      preview.skipped ? `${number(preview.skipped)} ${preview.skipped === 1 ? 'row' : 'rows'} without a JOIN_ID left out.` : '',
      preview.duplicates ? `${number(preview.duplicates)} JOIN_IDs have several rows (the A and B sides, or several samples): `
        + 'each side fills its own fields, the suggestion is the first one naming a cause and the evidence and other columns keep every row.' : '',
    ].filter(Boolean);
    const list = node('ul');
    list.append(...facts.map((fact) => node('li', fact)));
    const keys = Object.keys(state.rcaRefs).filter((key) => preview.preview.some((row) => row[key]));
    host.replaceChildren(node('h3', `Preview of ${preview.file_name}`), list,
      smallTable(['JOIN_ID', ...keys.map((key) => state.rcaRefs[key])], preview.preview.map((row) => [row.join_id, ...keys.map((key) => row[key] || '—')])));
    // The Ericsson RCA values the catalog cannot map (by name or keywords), to add with the results.
    if (preview.unmapped?.length) {
      const toggle = node('label', undefined, 'nq-toggle');
      const box = node('input');
      box.type = 'checkbox';
      box.checked = rcaAddToCatalog;
      box.addEventListener('change', () => { rcaAddToCatalog = box.checked; });
      toggle.append(box, ' Add them to the Root Cause Catalog with the results');
      host.append(node('h3', 'Not in the Root Cause Catalog'),
        node('p', 'The recommendation cannot use these Ericsson RCA values: no Root Category or Root Cause of the catalog has their name or keywords.', 'form-note'),
        smallTable(['Kind', 'Value', 'Proposed domain', 'Results'], preview.unmapped.map((item) => [
          item.kind === 'category' ? 'Root Category' : 'Root Cause', item.name, item.domain || 'No domain', number(item.results)])),
        toggle);
    }
    host.hidden = false;
  };
  const rcaRequest = async (preview) => {
    const body = new FormData();
    body.append('file', rcaFile);
    if ($('nq-rca-replace').checked) body.append('replace', '1');
    if (preview) body.append('preview', '1');
    if (rcaAddToCatalog) body.append('add_to_catalog', '1');
    const response = await fetch('/api/non-qualified-calls/rca/import', {method: 'POST', credentials: 'same-origin', body});
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'The RCA file could not be read.');
    return payload;
  };
  if (rcaDialog) {
    document.querySelectorAll('[data-nq-rca-open]').forEach((button) => button.addEventListener('click', async () => {
      rcaFile = null;
      rcaAddToCatalog = true;
      $('nq-rca-format').textContent = state.rcaResults.format || '';
      $('nq-rca-preview').hidden = true;
      $('nq-rca-import').disabled = true;
      $('nq-rca-replace').checked = false;
      $('nq-rca-error').textContent = '';
      renderRcaCurrent(state.rcaResults);
      rcaDialog.showModal();
      try {
        state.rcaResults = await api('/api/non-qualified-calls/rca');
        renderRcaCurrent(state.rcaResults);
      } catch (_error) {
        // The summary of the page stays.
      }
    }));
    $('nq-rca-cancel').addEventListener('click', () => rcaDialog.close());
    // The preview tells what replacing the previous results means.
    $('nq-rca-replace').addEventListener('change', async () => {
      if (!rcaFile) return;
      try {
        renderRcaPreview(await rcaRequest(true));
      } catch (error) {
        $('nq-rca-error').textContent = error.message;
      }
    });
    $('nq-rca-file').addEventListener('change', async (event) => {
      rcaFile = event.target.files?.[0] || null;
      event.target.value = '';
      if (!rcaFile) return;
      $('nq-rca-error').style.color = 'var(--nq-muted)';
      $('nq-rca-error').textContent = `Reading ${rcaFile.name}…`;
      $('nq-rca-import').disabled = true;
      try {
        renderRcaPreview(await rcaRequest(true));
        $('nq-rca-error').textContent = '';
        $('nq-rca-import').disabled = false;
      } catch (error) {
        rcaFile = null;
        $('nq-rca-preview').hidden = true;
        $('nq-rca-error').style.color = '';
        $('nq-rca-error').textContent = error.message;
      }
    });
    $('nq-rca-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      if (!rcaFile) return;
      const button = $('nq-rca-import');
      button.disabled = true;
      try {
        const result = await rcaRequest(false);
        const added = result.added_to_catalog?.length ? ` ${number(result.added_to_catalog.length)} values added to the Root Cause Catalog.` : '';
        toast(`${number(result.rows)} RCA results imported; ${number(result.matched)} match calls.${added}`);
        rcaFile = null;
        $('nq-rca-preview').hidden = true;
        state.rcaResults = await api('/api/non-qualified-calls/rca');
        renderRcaCurrent(state.rcaResults);
        // New catalog values reach the root cause pickers with the state of the page.
        if (added) await loadState();
        loadCalls({quiet: true});
        if (state.detail) openDetail(state.detail.call.call_key, {keepTab: true});
      } catch (error) {
        $('nq-rca-error').style.color = '';
        $('nq-rca-error').textContent = error.message;
        button.disabled = false;
      }
    });
    $('nq-rca-clear').addEventListener('click', async () => {
      const message = 'Delete every imported Ericsson RCA result? The calls lose their Ericsson RCA values and recommendations; their selected root cause stays.';
      const accepted = typeof window.showConfirmDialog === 'function'
        ? await window.showConfirmDialog(message, {title: 'Delete RCA results', confirmLabel: 'Delete'}) : window.confirm(message);
      if (!accepted) return;
      try {
        const result = await api('/api/non-qualified-calls/rca', {method: 'DELETE'});
        toast(`${number(result.deleted)} RCA results deleted.`);
        state.rcaResults = result.rca_results;
        renderRcaCurrent(state.rcaResults);
        loadCalls({quiet: true});
      } catch (error) {
        $('nq-rca-error').textContent = error.message;
      }
    });
  }
  // -- Analysts / Reviewers → Asignees dialog ----------------------------------------------------------------
  // The user account chosen for each Analyst or Reviewer becomes the Asignee of the calls they analysed, and their Analyst
  // and Reviewer take the name of the account (New Analyst / Reviewer); the counts follow every choice.
  const assignDialog = $('nq-assign-analysts-dialog');
  if (assignDialog) {
    let assignToken = 0;
    const assignSelects = () => [...$('nq-assign-analysts-rows').querySelectorAll('select[data-person]')];
    const assignRequest = (preview) => api('/api/non-qualified-calls/analysts/assign', {method: 'POST', body: JSON.stringify({
      assignments: Object.fromEntries(assignSelects().filter((select) => select.value).map((select) => [select.dataset.person, select.value])),
      overwrite: $('nq-assign-analysts-overwrite').checked, preview,
    })});
    const plural = (count, one, many) => `${number(count)} ${count === 1 ? one : many}`;
    const assignSummary = (result) => {
      const chosen = assignSelects().some((select) => select.value);
      const joins = result.joins.map((item) => `${userName(item.user)} joins ${item.team}`);
      const named = [result.analyst_names ? plural(result.analyst_names, 'Analyst', 'Analysts') : '',
        result.reviewer_names ? plural(result.reviewer_names, 'Reviewer', 'Reviewers') : ''].filter(Boolean);
      return [
        !chosen ? 'Choose the user account of an Analyst or a Reviewer.' : !result.calls ? 'No call changes with these choices.' : '',
        result.assignees ? `${plural(result.assignees, 'call gets', 'calls get')} a new Asignee.` : '',
        named.length ? `${named.join(' and ')} of the calls take the name of their account.` : '',
        joins.length ? `Team members added: ${joins.join(', ')}.` : '',
        result.waiting ? `${result.waiting === result.calls ? 'They wait' : `${number(result.waiting)} of them ${result.waiting === 1 ? 'waits' : 'wait'}`} for their CDR to be loaded: their imported analysis changes.` : '',
      ].filter(Boolean).join(' ');
    };
    const previewAssign = debounce(async () => {
      const token = ++assignToken;
      const apply = $('nq-assign-analysts-apply');
      apply.disabled = true;
      try {
        const result = await assignRequest(true);
        if (token !== assignToken) return;
        assignSelects().forEach((select) => {
          select.closest('tr').querySelector('[data-analyst-change]').textContent = select.value ? number(result.people[select.dataset.person] || 0) : '—';
        });
        $('nq-assign-analysts-summary').textContent = assignSummary(result);
        $('nq-assign-analysts-error').textContent = '';
        apply.disabled = !result.calls;
      } catch (error) {
        if (token === assignToken) $('nq-assign-analysts-error').textContent = error.message;
      }
    }, 250);
    // The name an Analyst or Reviewer takes with the account chosen: its first and last name (without them, the name stays).
    const showNewName = (select, cell, current) => {
      const name = select.value ? state.userNames?.[select.value] || '' : '';
      cell.textContent = !select.value ? '—' : name || current;
      cell.classList.toggle('is-new-name', Boolean(name) && name !== current);
      cell.title = select.value && !name ? 'The account has no first and last name: the name stays as it is' : '';
    };
    // A row per analyst or reviewer: their name and spellings, the name they take, their calls as Analyst and as Reviewer,
    // the analysed calls without an Asignee, the user account and the calls that change.
    const personRow = (person, users) => {
      const row = node('tr');
      const name = node('td');
      name.append(node('strong', person.name));
      if (person.spellings.length > 1) name.append(node('small', `Also written ${person.spellings.slice(1).join(', ')}`, 'nq-muted'));
      const select = node('select');
      select.dataset.person = person.key;
      select.setAttribute('aria-label', `User account of ${person.name}`);
      select.append(node('option', 'Leave unchanged'), ...userOptions(users));
      select.options[0].value = '';
      select.value = users.includes(person.suggested) ? person.suggested : '';
      const account = node('td');
      account.append(select);
      const newName = node('td');
      showNewName(select, newName, person.name);
      select.addEventListener('change', () => { showNewName(select, newName, person.name); previewAssign(); });
      const change = node('td', '—', 'nq-number');
      change.dataset.analystChange = '';
      row.append(name, newName, node('td', number(person.analyst_calls), 'nq-number'), node('td', number(person.reviewer_calls), 'nq-number'),
        node('td', number(person.unassigned), 'nq-number'), account, change);
      return row;
    };
    const renderAssign = (payload) => {
      $('nq-assign-analysts-rows').replaceChildren(...payload.people.map((person) => personRow(person, payload.users)));
      if (!payload.people.length) {
        const cell = node('td', 'No call of this workspace has an Analyst or a Reviewer.', 'nq-muted');
        cell.colSpan = 7;
        const row = node('tr');
        row.append(cell);
        $('nq-assign-analysts-rows').append(row);
      }
    };
    $('nq-assign-analysts-open').addEventListener('click', async () => {
      $('nq-assign-analysts-overwrite').checked = false;
      $('nq-assign-analysts-error').textContent = '';
      $('nq-assign-analysts-summary').textContent = 'Reading the analysts and reviewers of the calls…';
      $('nq-assign-analysts-rows').replaceChildren();
      $('nq-assign-analysts-apply').disabled = true;
      assignDialog.showModal();
      try {
        const payload = await api('/api/non-qualified-calls/analysts');
        state.userNames = {...state.userNames, ...(payload.user_names || {})};
        renderAssign(payload);
        previewAssign();
      } catch (error) {
        $('nq-assign-analysts-summary').textContent = '';
        $('nq-assign-analysts-error').textContent = error.message;
      }
    });
    $('nq-assign-analysts-overwrite').addEventListener('change', previewAssign);
    $('nq-assign-analysts-cancel').addEventListener('click', () => assignDialog.close());
    $('nq-assign-analysts-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const message = 'Replace the Asignee the calls already have with the user account of their Analyst?';
      if ($('nq-assign-analysts-overwrite').checked && !(typeof window.showConfirmDialog === 'function'
        ? await window.showConfirmDialog(message, {title: 'Replace Asignees', confirmLabel: 'Replace'}) : window.confirm(message))) return;
      const button = $('nq-assign-analysts-apply');
      button.disabled = true;
      try {
        const result = await assignRequest(false);
        toast(`${plural(result.calls, 'call', 'calls')} linked to the accounts of their Analyst and Reviewer.`);
        assignDialog.close();
        // The new team members reach the pickers with the state of the page.
        await loadState();
        loadCalls({quiet: true});
        if (state.detail) openDetail(state.detail.call.call_key, {keepTab: true});
      } catch (error) {
        $('nq-assign-analysts-error').textContent = error.message;
        button.disabled = false;
      }
    });
  }
  // The NQ Analysis Configuration of the sections menu of the module opens its menu, and its options their dialogs (once the
  // page has its state).
  const CENTER_HASHES = {
    'section-nq-analysis-configuration': 'nq-config-toggle', 'fields-and-sections': 'nq-fields-open', 'statuses-and-teams': 'nq-options-open',
    'status-rules': 'nq-status-rules-open', 'prioritization-rules': 'nq-prioritization-open', 'root-cause-catalog': 'nq-root-open',
    'dta-rca-rules': 'nq-dta-rules-open',
    'import-ericsson-rca-results': 'nq-rca-open', 'import-previous-nq-analyses': 'nq-analyses-open',
    'analysts-reviewers-to-asignees': 'nq-assign-analysts-open',
  };
  const openCenterFromHash = () => {
    const opener = CENTER_HASHES[decodeURIComponent(window.location.hash.slice(1))];
    if (!opener) return;
    window.history.replaceState(window.history.state, '', `${window.location.pathname}${window.location.search}`);
    const button = $(opener);
    if (!button || button.getAttribute('aria-disabled') === 'true') {
      toast(button?.title || 'The user-viewer role can read Non-Qualified Calls but cannot change them.', 'error');
      return;
    }
    if (opener !== 'nq-config-toggle') button.click();
    else if ($('nq-config-menu').hidden) window.setTimeout(() => button.click());
  };
  window.addEventListener('hashchange', openCenterFromHash);

  // Keep the shared follow-up current while the page stays open.
  window.setInterval(() => {
    if (document.visibilityState !== 'visible' || state.busy) return;
    const active = document.activeElement;
    if (active && active.closest?.('#nq-table select, #nq-drawer textarea, #nq-drawer select, #nq-drawer input, #nq-drawer [contenteditable="true"], .nq-comment-editor')) return;
    if (Object.keys(changedFields()).length) return;
    if (rootPicker || document.querySelector('dialog[open]')) return;
    loadCalls({quiet: true});
    if (state.detail && !composerBody.value.trim() && !drawer.querySelector('.nq-comment-editor')) openDetail(state.detail.call.call_key, {keepTab: true});
  }, REFRESH_INTERVAL_MS);

  // Floating buttons over each panel and over its charts and tables (on touch screens, a tap shows them) download it as a
  // PNG image, as it is shown, or copy it to the clipboard as a screenshot (image_buttons.js); App Events records each one.
  // A table with its title (a failure card, a progress section) is one image; the tables without one are on their own.
  const imageTables = '.nq-failure-card, .nq-progress-section:has(.nq-table-wrap), .nq-table-wrap:not(.nq-failure-card *, .nq-progress-section *)';
  const imageCharts = '.nq-pie, .nq-root-donut-group, .nq-progress-section';
  const l3MapImages = '.nq-l3-maps .nq-map-wrap, .nq-l3-maps-panel .nq-map-expand-wrap';
  window.attachImageButtons?.({
    root: $('non-qualified-calls'), fallbackName: 'Non-Qualified Calls', module: 'non-qualified-calls',
    // NQ Maps as the map of a call: in the page and larger, without its buttons.
    targets: `details.panel.collapsible-panel, ${imageTables}, ${imageCharts}, .nq-kpis, .nq-rate-overview, .nq-phase-cards, .nq-failure-section, ${l3MapImages}`,
    tables: imageTables, charts: `${imageCharts}, ${l3MapImages}`, obstacles: 'summary .summary-inline-actions, .nq-map-zoom, .nq-map-info-close',
    exclude: '.nq-chart-tooltip, .nq-map-zoom, .nq-map-basemap, .nq-map-expand-toolbar, .nq-map-wheel-hint, .nq-map-tooltip, .nq-map-info-close, .nq-map-selected-content > button',
    // The title of its panel, then its own: that of its section (with the operator of a failure card) or its heading.
    title: target => {
      const text = element => window.imageHeadingText(element);
      const section = target.closest('.nq-failure-section, .nq-progress-section');
      const own = target.matches('details') ? ''
        : target.matches('.nq-failure-card')
          ? [text(section?.querySelector(':scope > h3')), text(target.querySelector('.nq-failure-operator'))].filter(Boolean).join(' · ')
          : text(target.querySelector(':scope > :is(h3, h4), :scope > :is(header, .nq-matrix-head) :is(h3, h4)'))
            || text(section?.querySelector(':scope > :is(h3, h4)'));
      return [...new Set([text(target.closest('details.panel')?.querySelector('summary h2')), own].filter(Boolean))].join(' — ');
    },
    details: target => ({section: window.imageHeadingText(target.closest('details.panel')?.querySelector('summary h2'))}),
  });

  // The map of a call downloads as a PNG image or copies as a screenshot too, in the panel and larger.
  if (callMap) {
    window.attachImageButtons?.({
      root: drawer, targets: '.nq-map-wrap, .nq-map-expand-wrap', charts: '.nq-map-wrap, .nq-map-expand-wrap',
      // The open panels (the element chosen) show in the images; the buttons of the map and of the panels do not.
      exclude: '.nq-map-zoom, .nq-map-basemap, .nq-map-expand-toolbar, .nq-map-wheel-hint, .nq-map-tooltip, .nq-map-waiting, .nq-map-info-close, .nq-map-selected-content > button',
      // (Clear of the zoom buttons and of the × of the element chosen.)
      obstacles: '.nq-map-zoom, .nq-map-info-close', cardOnEdge: false,
      // Below the header and the tabs of the call panel, which its body scrolls under.
      topInset: () => drawer.querySelector('.nq-drawer-body').getBoundingClientRect().top,
      module: 'non-qualified-calls', fallbackName: 'Call Area Map', title: () => callMap.title(), details: () => callMap.details(),
    });
  }

  loadState().then(openCenterFromHash).finally(restoreScroll);
})();
