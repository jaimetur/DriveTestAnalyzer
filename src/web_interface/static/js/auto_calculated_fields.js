// The Auto-calculated Fields editor of the active workspace (Workspace Management, PPT Designer and the PPT Templates
// editor open the same one): the fields on the left, the one chosen on the right, built from rules (field, operator,
// values) or written as a formula, checked as it is edited, tried on the CDRs and saved one at a time. Saving updates the
// CDR tables in the background: only the column of the field, and those of the fields that read it.
(function () {
  'use strict';

  const API = '/api/workspace/auto-calculated-fields';
  const SOURCES = [['cdr-data', 'Data'], ['cdr-voice', 'Voice'], ['cdr-speech', 'Speech']];
  const KEYWORDS = new Set(['IF', 'THEN', 'ELSEIF', 'ELSE', 'END', 'AND', 'OR', 'NOT', 'IN', 'CONTAINS', 'STARTS', 'ENDS',
    'WITH', 'MATCHES', 'IS', 'EMPTY']);
  const PLAIN_VALUE = /^(?:[+-]?(?:\d+(?:\.\d*)?|\.\d+)|[A-Za-z_][A-Za-z0-9_.\-/]*)$/;
  const FORMULA_EXAMPLE = "IF [RAT] CONTAINS ('NR SA', NE-DC) THEN 'SA'\nELSEIF [RAT] CONTAINS 'EN-DC' THEN 'NSA'\nEND";
  const number = new Intl.NumberFormat('en-GB');

  const el = (tag, className = '', text = '') => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  };
  const button = (label, className = '', title = '') => {
    const node = el('button', className, label);
    node.type = 'button';
    if (title) { node.title = title; node.setAttribute('aria-label', title); }
    return node;
  };
  const identity = (value) => String(value || '').toLocaleLowerCase().replace(/[^a-z0-9]+/g, '');
  const clone = (value) => JSON.parse(JSON.stringify(value));

  // A value as the conditions read it: a number or a single word as it is, anything else quoted (as the server writes it).
  const quote = (value) => {
    const text = String(value ?? '');
    if (PLAIN_VALUE.test(text) && !KEYWORDS.has(text.toUpperCase())) return text;
    return `'${text.replace(/\\/g, '\\\\').replace(/'/g, "\\'")}'`;
  };
  const fieldsText = (fields) => fields.filter(Boolean).map((field) => `[${field}]`).join(' OR ');

  async function request(path, body, signal) {
    const response = await fetch(`${API}${path}`, {
      method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin', cache: 'no-store', signal,
      headers: body === undefined ? {} : {'Content-Type': 'application/json'},
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || `The server answered ${response.status}.`);
    return payload;
  }

  function open(options = {}) {
    const confirmDialog = (message, settings) => (typeof window.showConfirmDialog === 'function'
      ? window.showConfirmDialog(message, settings) : Promise.resolve(window.confirm(message)));
    const infoDialog = (message, settings = {}) => (typeof window.showInfoDialog === 'function'
      ? window.showInfoDialog(message, settings) : window.alert(message));

    let data = {fields: [], columns: {}, operators: [], can_edit: false, workspace: ''};
    let operators = {};
    let current = null; // {original: name | null, position, model, baseline, check, preview}
    let checkTimer = 0; let previewTimer = 0; let checkAbort = null; let previewAbort = null;
    let saving = false; let changed = false;
    const valueCache = new Map();

    // ---- layout
    const overlay = el('div', 'confirm-overlay acf-overlay');
    const panel = el('section', 'confirm-panel acf-dialog');
    panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-modal', 'true'); panel.setAttribute('aria-labelledby', 'acf-title');
    const header = el('header', 'acf-header');
    const heading = el('div');
    const eyebrow = el('p', 'eyebrow', 'Active Workspace');
    const title = el('h3', '', 'Auto-calculated Fields'); title.id = 'acf-title';
    heading.append(eyebrow, title);
    const close = button('×', 'acf-icon-close', 'Close');
    header.append(heading, close);
    const body = el('div', 'acf-body');
    const sidebar = el('aside', 'acf-sidebar');
    const search = el('input', 'acf-search'); search.type = 'search'; search.placeholder = 'Search fields…'; search.setAttribute('aria-label', 'Search fields');
    const addButton = button('+ New field', 'acf-add');
    const list = el('ol', 'acf-field-list');
    const sidebarNote = el('p', 'acf-sidebar-note', 'Fields are worked out from top to bottom: a field can read the fields above it.');
    sidebar.append(addButton, search, list, sidebarNote);
    const editor = el('main', 'acf-editor');
    body.append(sidebar, editor);
    panel.append(header, body);
    overlay.append(panel);
    document.body.append(overlay);
    const suggestions = el('div', 'acf-suggestions'); suggestions.hidden = true; suggestions.setAttribute('role', 'listbox');
    document.body.append(suggestions);

    // ---- model
    const toModel = (field) => {
      const rules = (field.rules || []).map((rule) => (rule.conditions
        ? {join: rule.join || 'AND', conditions: rule.conditions.map((condition) => clone(condition)), value: rule.value}
        : {join: null, text: rule.when, value: rule.value}));
      const fallbackFields = field.default_from_fields || [];
      return {
        name: field.name || '',
        sources: [...(field.sources || [])],
        mode: field.expression ? 'formula' : 'rules',
        rules,
        formula: field.expression || '',
        otherwise: fallbackFields.length
          ? {kind: 'field', fields: [...fallbackFields], value: field.default || ''}
          : {kind: field.default ? 'value' : 'empty', fields: [], value: field.default || ''},
      };
    };
    const conditionText = (condition) => {
      const arity = operators[condition.operator]?.values || 'one';
      const values = (condition.values || []).map(quote);
      const head = `${fieldsText(condition.fields || [])} ${condition.operator}`;
      if (arity === 'none') return head;
      if (arity === 'list' || values.length > 1) return `${head} (${values.join(', ')})`;
      return `${head} ${values[0] ?? ''}`.trimEnd();
    };
    const ruleWhen = (rule) => (rule.conditions
      ? rule.conditions.map(conditionText).join(` ${rule.join || 'AND'} `)
      : String(rule.text || '').trim());
    const toPayload = (model) => ({
      name: model.name.trim(),
      sources: SOURCES.map(([key]) => key).filter((key) => model.sources.includes(key)),
      default: model.otherwise.kind === 'empty' ? '' : model.otherwise.value,
      default_from: model.otherwise.kind === 'field' ? fieldsText(model.otherwise.fields) : '',
      expression: model.mode === 'formula' ? model.formula.trim() : '',
      // A rule not started yet (no field, no result) is left out until it is filled in.
      rules: model.mode === 'rules' ? model.rules
        .filter((rule) => rule.value !== '' || (rule.conditions ? rule.conditions.some((condition) => condition.fields.length) : rule.text.trim()))
        .map((rule) => ({when: ruleWhen(rule), value: rule.value})) : [],
    });
    const signature = (model) => JSON.stringify(toPayload(model));
    const isDirty = () => Boolean(current) && signature(current.model) !== current.baseline;
    const formulaFromRules = (model) => {
      const branches = model.rules.filter((rule) => ruleWhen(rule) && rule.value !== '');
      if (!branches.length) return '';
      return [...branches.map((rule, index) => `${index ? 'ELSEIF' : 'IF'} ${ruleWhen(rule)} THEN ${quote(rule.value)}`), 'END'].join('\n');
    };

    // ---- fields the editor offers
    const indexOf = (name) => data.fields.findIndex((field) => identity(field.name) === identity(name));
    const fieldChoices = () => {
      const sources = current?.model.sources.length ? current.model.sources : SOURCES.map(([key]) => key);
      const cdr = [...new Set(sources.flatMap((source) => data.columns[source] || []))].sort((a, b) => a.localeCompare(b));
      const limit = current?.original ? indexOf(current.original) : (current?.position ?? data.fields.length);
      const auto = data.fields.slice(0, limit < 0 ? data.fields.length : limit)
        .filter((field) => field.sources.some((source) => sources.includes(source))).map((field) => field.name);
      return {cdr, auto};
    };
    const fieldSelect = (value, onChoose, placeholder = 'Choose a field…') => {
      const select = el('select', 'acf-field-select');
      select.setAttribute('aria-label', 'Field');
      const {cdr, auto} = fieldChoices();
      const empty = new Option(placeholder, ''); empty.disabled = true; select.append(empty);
      const group = (label, names) => {
        if (!names.length) return;
        const optgroup = document.createElement('optgroup'); optgroup.label = label;
        names.forEach((name) => optgroup.append(new Option(name, name)));
        select.append(optgroup);
      };
      group('Auto-calculated Fields above', auto);
      group('CDR fields', cdr);
      if (value && ![...auto, ...cdr].some((name) => identity(name) === identity(value))) group('Not in the CDRs of this field', [value]);
      select.value = [...select.options].find((option) => identity(option.value) === identity(value))?.value || '';
      select.addEventListener('change', () => onChoose(select.value));
      return select;
    };

    // ---- suggestions (values of a field, or fields in a formula), below their input
    let suggestionTarget = null;
    const hideSuggestions = () => { suggestions.hidden = true; suggestions.replaceChildren(); suggestionTarget = null; };
    const showSuggestions = (input, items, onPick) => {
      suggestions.replaceChildren();
      if (!items.length) { hideSuggestions(); return; }
      items.slice(0, 80).forEach((item) => {
        const option = button('', 'acf-suggestion');
        option.setAttribute('role', 'option');
        option.append(el('span', '', item.label));
        if (item.count !== undefined) option.append(el('small', '', number.format(item.count)));
        option.addEventListener('pointerdown', (event) => event.preventDefault());
        option.addEventListener('click', () => { onPick(item.value); });
        suggestions.append(option);
      });
      suggestionTarget = input;
      suggestions.hidden = false;
      const bounds = input.getBoundingClientRect();
      suggestions.style.left = `${Math.max(8, Math.min(bounds.left, window.innerWidth - 328))}px`;
      suggestions.style.width = `${Math.max(bounds.width, 260)}px`;
      const below = window.innerHeight - bounds.bottom - 12;
      suggestions.style.maxHeight = `${Math.max(140, Math.min(320, below > 160 ? below : bounds.top - 12))}px`;
      suggestions.style.top = below > 160 ? `${bounds.bottom + 4}px` : '';
      suggestions.style.bottom = below > 160 ? '' : `${window.innerHeight - bounds.top + 4}px`;
    };
    const fieldValues = async (fields) => {
      const sources = current?.model.sources || [];
      const key = `${fields.map(identity).join('|')}::${sources.join('|')}`;
      if (!valueCache.has(key)) {
        valueCache.set(key, request('/values', {fields, sources}).then((payload) => payload.values || []).catch(() => []));
      }
      return valueCache.get(key);
    };
    const suggestValues = async (input, condition, onPick) => {
      if (!condition.fields?.length || condition.operator.includes('MATCHES')) { hideSuggestions(); return; }
      const values = await fieldValues(condition.fields);
      if (document.activeElement !== input) return;
      const typed = input.value.trim().toLocaleLowerCase();
      const taken = new Set((condition.values || []).map((value) => String(value).toLocaleLowerCase()));
      showSuggestions(input, values
        .filter((item) => !taken.has(item.value.toLocaleLowerCase()) && (!typed || item.value.toLocaleLowerCase().includes(typed)))
        .map((item) => ({label: item.value, value: item.value, count: item.count})), onPick);
    };

    // ---- the list of fields
    const fieldSummary = (field) => {
      const parts = [];
      if (field.expression) parts.push('Formula');
      else parts.push(`${field.rules.length} rule${field.rules.length === 1 ? '' : 's'}`);
      if (field.default_from) parts.push(`otherwise ${field.default_from}${field.default ? ` or ${field.default}` : ''}`);
      else if (field.default) parts.push(`otherwise ${field.default}`);
      return parts.join(' · ');
    };
    const renderList = () => {
      list.replaceChildren();
      const query = search.value.trim().toLocaleLowerCase();
      const entries = data.fields.map((field, index) => ({field, index}));
      if (current && !current.original) entries.splice(current.position, 0, {field: null, index: -1});
      entries.forEach(({field, index}) => {
        const name = field ? field.name : (current.model.name.trim() || 'New field');
        if (query && !name.toLocaleLowerCase().includes(query)) return;
        const item = el('li', 'acf-field-item');
        const selected = field ? current?.original && identity(current.original) === identity(field.name) : true;
        item.classList.toggle('is-selected', Boolean(selected));
        const choose = button('', 'acf-field-choose');
        choose.append(el('strong', '', name));
        const sources = field ? field.sources : current.model.sources;
        choose.append(el('span', 'acf-field-sources', SOURCES.filter(([key]) => sources.includes(key)).map(([, label]) => label).join(' · ') || 'No CDR type'));
        choose.append(el('span', 'acf-field-summary', field ? fieldSummary(field) : 'Not saved yet'));
        if (field && selected && isDirty()) choose.append(el('span', 'acf-field-dirty', 'Unsaved changes'));
        choose.addEventListener('click', () => { if (field) void select(field.name); });
        item.append(choose);
        if (field && data.can_edit && !query) {
          const order = el('div', 'acf-field-order');
          const up = button('↑', '', `Move ${field.name} up`); up.disabled = index === 0;
          const down = button('↓', '', `Move ${field.name} down`); down.disabled = index === data.fields.length - 1;
          up.addEventListener('click', () => { void move(index, -1); });
          down.addEventListener('click', () => { void move(index, 1); });
          order.append(up, down);
          item.append(order);
        }
        list.append(item);
      });
      if (!list.children.length) list.append(el('li', 'acf-empty-list', query ? 'No field matches the search.' : 'This workspace has no Auto-calculated Fields yet.'));
    };

    // ---- the editor of the chosen field
    const touch = ({structure = false} = {}) => {
      if (structure) renderEditor();
      renderList();
      updateFooter();
      scheduleCheck();
    };
    const sectionHead = (text, note = '') => {
      const head = el('div', 'acf-section-head');
      head.append(el('h4', '', text));
      if (note) head.append(el('p', 'acf-note', note));
      return head;
    };
    let footer = null; let saveButton = null; let discardButton = null; let statusLine = null; let checkBox = null; let previewBox = null;

    const valueEditor = (condition) => {
      const arity = operators[condition.operator]?.values || 'one';
      const wrap = el('div', 'acf-values');
      if (arity === 'none') { wrap.classList.add('is-none'); return wrap; }
      const many = arity !== 'one';
      const input = el('input', 'acf-value-input');
      input.disabled = !data.can_edit;
      const isPattern = condition.operator.includes('MATCHES');
      input.placeholder = isPattern ? 'Regular expression, such as (^|/)NR(/|$)' : many ? 'Type a value and press Enter' : 'Value';
      input.setAttribute('aria-label', isPattern ? 'Pattern' : 'Value');
      const addValue = (value) => {
        const text = String(value ?? '').trim();
        if (!text) return;
        condition.values = [...(condition.values || []).filter((item) => item !== text), text];
        input.value = '';
        renderChips();
        touch();
        input.focus();
        void suggestValues(input, condition, addValue);
      };
      const chips = el('div', 'acf-chips');
      const renderChips = () => {
        chips.replaceChildren();
        (condition.values || []).forEach((value, index) => {
          const chip = el('span', 'acf-chip');
          chip.append(el('span', '', value));
          if (data.can_edit) {
            const remove = button('×', '', `Remove ${value}`);
            remove.addEventListener('click', () => {
              condition.values.splice(index, 1);
              renderChips(); touch();
            });
            chip.append(remove);
          }
          chips.append(chip);
        });
      };
      if (many) {
        renderChips();
        input.addEventListener('keydown', (event) => {
          if ((event.key === 'Enter' || event.key === ',') && input.value.trim()) { event.preventDefault(); addValue(input.value); }
          else if (event.key === 'Backspace' && !input.value && condition.values?.length) {
            condition.values.pop(); renderChips(); touch();
          }
        });
        input.addEventListener('blur', () => { if (input.value.trim()) addValue(input.value); });
        input.addEventListener('input', () => { void suggestValues(input, condition, addValue); });
        input.addEventListener('focus', () => { void suggestValues(input, condition, addValue); });
        wrap.append(chips, input);
      } else {
        input.value = condition.values?.[0] ?? '';
        const setValue = (value) => {
          input.value = value;
          condition.values = value === '' ? [] : [value];
          hideSuggestions(); touch();
        };
        input.addEventListener('input', () => {
          condition.values = input.value === '' ? [] : [input.value];
          touch();
          void suggestValues(input, {...condition, values: []}, setValue);
        });
        input.addEventListener('focus', () => { void suggestValues(input, {...condition, values: []}, setValue); });
        wrap.append(input);
      }
      input.addEventListener('blur', () => window.setTimeout(() => { if (suggestionTarget === input) hideSuggestions(); }, 120));
      return wrap;
    };

    const conditionRow = (rule, condition, conditionIndex) => {
      const row = el('div', 'acf-condition');
      const fields = el('div', 'acf-condition-fields');
      (condition.fields.length ? condition.fields : ['']).forEach((name, fieldIndex) => {
        if (fieldIndex) fields.append(el('span', 'acf-or', 'or'));
        const select = fieldSelect(name, (value) => {
          condition.fields[fieldIndex] = value;
          condition.fields = condition.fields.filter(Boolean);
          touch({structure: true});
        });
        select.disabled = !data.can_edit;
        fields.append(select);
      });
      if (data.can_edit && condition.fields.length) {
        const alternative = button('+ or', 'acf-alternative', 'Add another spelling of the field: the first one the CDR has is read');
        alternative.addEventListener('click', () => { condition.fields.push(''); renderEditor(); });
        fields.append(alternative);
      }
      const operator = el('select', 'acf-operator');
      operator.setAttribute('aria-label', 'Operator');
      operator.disabled = !data.can_edit;
      data.operators.forEach((item) => {
        const option = new Option(item.label, item.key);
        option.dataset.tag = item.key;
        operator.append(option);
      });
      operator.value = condition.operator;
      operator.addEventListener('change', () => {
        const before = operators[condition.operator]?.values;
        condition.operator = operator.value;
        const after = operators[condition.operator]?.values;
        if (after === 'none') condition.values = [];
        else if (after === 'one' && before !== 'one') condition.values = (condition.values || []).slice(0, 1);
        touch({structure: true});
      });
      const remove = button('×', 'acf-remove', 'Remove this condition');
      remove.hidden = !data.can_edit;
      remove.addEventListener('click', () => {
        rule.conditions.splice(conditionIndex, 1);
        if (!rule.conditions.length) rule.conditions.push({fields: [], operator: '=', values: []});
        touch({structure: true});
      });
      row.append(fields, operator, valueEditor(condition), remove);
      return row;
    };

    const ruleCard = (rule, index, rules) => {
      const card = el('li', 'acf-rule');
      const head = el('div', 'acf-rule-head');
      head.append(el('strong', 'acf-rule-number', `Rule ${index + 1}`));
      if (rule.conditions && rule.conditions.length > 1) {
        const join = el('select', 'acf-join');
        join.setAttribute('aria-label', 'How the conditions combine');
        join.append(new Option('when all the conditions hold (AND)', 'AND'), new Option('when any condition holds (OR)', 'OR'));
        join.value = rule.join;
        join.disabled = !data.can_edit;
        join.addEventListener('change', () => { rule.join = join.value; touch(); });
        head.append(join);
      } else {
        head.append(el('span', 'acf-rule-when', 'when'));
      }
      const actions = el('div', 'acf-rule-actions');
      if (data.can_edit) {
        const up = button('↑', '', 'Move this rule up'); up.disabled = index === 0;
        const down = button('↓', '', 'Move this rule down'); down.disabled = index === rules.length - 1;
        const copy = button('⧉', '', 'Duplicate this rule');
        const remove = button('−', 'acf-danger', 'Delete this rule');
        up.addEventListener('click', () => { [rules[index - 1], rules[index]] = [rules[index], rules[index - 1]]; touch({structure: true}); });
        down.addEventListener('click', () => { [rules[index + 1], rules[index]] = [rules[index], rules[index + 1]]; touch({structure: true}); });
        copy.addEventListener('click', () => { rules.splice(index + 1, 0, clone(rule)); touch({structure: true}); });
        remove.addEventListener('click', () => { rules.splice(index, 1); touch({structure: true}); });
        actions.append(up, down, copy, remove);
      }
      head.append(actions);
      card.append(head);
      if (rule.conditions) {
        const conditions = el('div', 'acf-conditions');
        rule.conditions.forEach((condition, conditionIndex) => {
          if (conditionIndex) conditions.append(el('span', 'acf-join-label', rule.join));
          conditions.append(conditionRow(rule, condition, conditionIndex));
        });
        card.append(conditions);
        if (data.can_edit) {
          const more = button('+ Condition', 'acf-add-condition');
          more.addEventListener('click', () => { rule.conditions.push({fields: [], operator: '=', values: []}); touch({structure: true}); });
          card.append(more);
        }
      } else {
        const text = el('textarea', 'acf-rule-text');
        text.value = rule.text;
        text.rows = 2;
        text.disabled = !data.can_edit;
        text.setAttribute('aria-label', `Condition of rule ${index + 1}`);
        text.addEventListener('input', () => { rule.text = text.value; touch(); });
        attachFieldCompletion(text);
        card.append(text, el('p', 'acf-note', 'This condition mixes AND and OR, so it is edited as text: [Field] operator value, with parentheses to group.'));
      }
      const result = el('label', 'acf-result');
      result.append(el('span', '', 'then the value is'));
      const value = el('input', 'acf-result-input');
      value.value = rule.value;
      value.placeholder = 'Result';
      value.disabled = !data.can_edit;
      value.addEventListener('input', () => { rule.value = value.value; touch(); });
      result.append(value);
      card.append(result);
      return card;
    };

    // [ in a formula or a text condition offers the fields; the choice is written as [Field].
    const attachFieldCompletion = (input) => {
      const refresh = () => {
        const caret = input.selectionStart ?? input.value.length;
        const before = input.value.slice(0, caret);
        const open = before.lastIndexOf('[');
        if (open < 0 || before.slice(open).includes(']') || /[\r\n]/.test(before.slice(open))) { if (suggestionTarget === input) hideSuggestions(); return; }
        const typed = before.slice(open + 1).toLocaleLowerCase();
        const {cdr, auto} = fieldChoices();
        // The fields starting with what is typed first, then those holding it.
        const names = [...auto, ...cdr].filter((name) => name.toLocaleLowerCase().includes(typed))
          .sort((left, right) => Number(!left.toLocaleLowerCase().startsWith(typed)) - Number(!right.toLocaleLowerCase().startsWith(typed)));
        showSuggestions(input, names.map((name) => ({label: name, value: name})), (name) => {
          const after = input.value.slice(caret).replace(/^[^\]\s]*\]?/, '');
          input.value = `${input.value.slice(0, open)}[${name}]${after}`;
          const next = open + name.length + 2;
          input.setSelectionRange(next, next);
          input.dispatchEvent(new Event('input', {bubbles: true}));
          hideSuggestions();
          input.focus();
        });
      };
      input.addEventListener('input', refresh);
      input.addEventListener('click', refresh);
      input.addEventListener('blur', () => window.setTimeout(() => { if (suggestionTarget === input) hideSuggestions(); }, 120));
    };

    const insertAtCaret = (textarea, snippet) => {
      const start = textarea.selectionStart ?? textarea.value.length;
      const end = textarea.selectionEnd ?? start;
      textarea.value = `${textarea.value.slice(0, start)}${snippet}${textarea.value.slice(end)}`;
      const caret = start + snippet.length;
      textarea.focus();
      textarea.setSelectionRange(caret, caret);
      textarea.dispatchEvent(new Event('input', {bubbles: true}));
    };

    const operatorReference = () => {
      const details = el('details', 'acf-reference');
      details.append(el('summary', '', 'Operators and syntax'));
      const table = el('div', 'acf-reference-grid');
      const examples = {
        '=': "[Test_Result] = Completed", '!=': "[Call_Status] != 'Dropped'", IN: "[RAT] IN (LTE, 'NR SA')",
        'NOT IN': "[Operator] NOT IN (EE, Three)", CONTAINS: "[Test_Name] CONTAINS (YouTube, FDFS)",
        'NOT CONTAINS': "[Session_Type] NOT CONTAINS WhatsApp", 'STARTS WITH': "[RAT] STARTS WITH 'NR SA'",
        'NOT STARTS WITH': "[RAT] NOT STARTS WITH EN-DC", 'ENDS WITH': "[RAT] ENDS WITH '/LTE'", 'NOT ENDS WITH': "[RAT] NOT ENDS WITH '/GSM'",
        MATCHES: "[RAT] MATCHES '(^|/)NR(/|$)'", 'NOT MATCHES': "[Test_Name] NOT MATCHES '^FDTT'",
        '>': '[Mean_Data_Rate] > 100', '>=': '[LQ] >= 3.5', '<': '[Call_Setup_Time] < 2', '<=': '[Score] <= 0',
        'IS EMPTY': '[Failure_Category] IS EMPTY', 'IS NOT EMPTY': '[Failure_Category] IS NOT EMPTY',
      };
      data.operators.forEach((item) => {
        table.append(el('code', 'acf-reference-key', item.key), el('span', '', item.label), el('code', '', examples[item.key] || ''));
      });
      details.append(table, el('p', 'acf-note',
        "Fields go in brackets: [RAT]. [RAT] OR [RAT_A] reads the first of them the CDR has. Quote a value with spaces or symbols: 'NR SA' (\\' for a quote). " +
        'Text comparisons ignore case; > and < compare numbers. Join conditions with AND and OR, and group them with parentheses. ' +
        'A formula is IF condition THEN value, any ELSEIF condition THEN value, an optional ELSE value and END; THEN and ELSE can hold another IF … END.'));
      return details;
    };

    const renderEditor = () => {
      hideSuggestions();
      editor.replaceChildren();
      footer = null;
      if (!current) {
        const empty = el('div', 'acf-editor-empty');
        empty.append(el('h4', '', data.fields.length ? 'Choose a field to edit it' : 'Create the first field'),
          el('p', '', 'An Auto-calculated Field gives each CDR row a value from rules on its other fields, such as the NR Mode of each sample from its RAT. It is added to every CDR table of the types it applies to and can be used like any other field in filters, splits and legends.'));
        if (data.can_edit) {
          const create = button('+ New field', 'acf-add');
          create.addEventListener('click', () => { void createField(); });
          empty.append(create);
        }
        editor.append(empty);
        return;
      }
      const model = current.model;
      const form = el('div', 'acf-form');

      // Name and CDR types
      const identityRow = el('div', 'acf-identity');
      const nameLabel = el('label', 'acf-name');
      nameLabel.append(el('span', '', 'Name'));
      const name = el('input');
      name.value = model.name;
      name.placeholder = 'Field name, such as NR_Mode_from_RAT';
      name.maxLength = 64;
      name.disabled = !data.can_edit;
      name.addEventListener('input', () => { model.name = name.value; touch(); });
      nameLabel.append(name);
      const sourcesBox = el('div', 'acf-sources');
      sourcesBox.append(el('span', '', 'Applies to'));
      const toggles = el('div', 'acf-source-toggles');
      SOURCES.forEach(([key, label]) => {
        const toggle = button(`CDR-${label}`, 'acf-source-toggle');
        toggle.setAttribute('aria-pressed', String(model.sources.includes(key)));
        toggle.disabled = !data.can_edit;
        toggle.addEventListener('click', () => {
          model.sources = model.sources.includes(key) ? model.sources.filter((item) => item !== key) : [...model.sources, key];
          valueCache.clear();
          touch({structure: true});
        });
        toggles.append(toggle);
      });
      sourcesBox.append(toggles);
      identityRow.append(nameLabel, sourcesBox);
      form.append(identityRow);

      // Rules or formula
      const tabs = el('div', 'acf-tabs');
      tabs.setAttribute('role', 'tablist');
      const rulesTab = button('Rules', 'acf-tab'); const formulaTab = button('Formula', 'acf-tab');
      [rulesTab, formulaTab].forEach((tab) => tab.setAttribute('role', 'tab'));
      rulesTab.setAttribute('aria-selected', String(model.mode === 'rules'));
      formulaTab.setAttribute('aria-selected', String(model.mode === 'formula'));
      rulesTab.addEventListener('click', () => { void switchMode('rules'); });
      formulaTab.addEventListener('click', () => { void switchMode('formula'); });
      tabs.append(rulesTab, formulaTab);
      const logic = el('section', 'acf-logic');
      logic.append(sectionHead('What value each row gets', model.mode === 'rules'
        ? 'The rules are tried from top to bottom: the first one whose condition holds gives the value.'
        : 'A Tableau-style formula. Type [ to choose a field.'), tabs);
      if (model.mode === 'rules') {
        const rules = el('ol', 'acf-rules');
        model.rules.forEach((rule, index) => rules.append(ruleCard(rule, index, model.rules)));
        logic.append(rules);
        if (data.can_edit) {
          const addRule = button('+ Rule', 'acf-add-rule');
          addRule.addEventListener('click', () => {
            model.rules.push({join: 'AND', conditions: [{fields: [], operator: '=', values: []}], value: ''});
            touch({structure: true});
          });
          logic.append(addRule);
        }
      } else {
        const toolbar = el('div', 'acf-formula-toolbar');
        const formula = el('textarea', 'acf-formula');
        formula.value = model.formula;
        formula.placeholder = FORMULA_EXAMPLE;
        formula.spellcheck = false;
        formula.disabled = !data.can_edit;
        formula.setAttribute('aria-label', 'Formula');
        formula.addEventListener('input', () => { model.formula = formula.value; touch(); });
        formula.addEventListener('keydown', (event) => {
          if (event.key === 'Tab' && !event.shiftKey && suggestions.hidden) { event.preventDefault(); insertAtCaret(formula, '  '); }
        });
        attachFieldCompletion(formula);
        [['IF … END', "IF [Field] = value THEN 'Result'\nEND"], ['ELSEIF', "\nELSEIF [Field] = value THEN 'Result'"], ['ELSE', "\nELSE 'Result'"],
          ['AND', ' AND '], ['OR', ' OR '], ['[Field]', '[']].forEach(([label, snippet]) => {
          const insert = button(label, 'acf-insert', `Insert ${label}`);
          insert.disabled = !data.can_edit;
          insert.addEventListener('click', () => insertAtCaret(formula, snippet));
          toolbar.append(insert);
        });
        const operatorPick = el('select', 'acf-insert-operator');
        operatorPick.setAttribute('aria-label', 'Insert an operator');
        operatorPick.disabled = !data.can_edit;
        operatorPick.append(new Option('Insert operator…', ''));
        data.operators.forEach((item) => { const option = new Option(item.label, item.key); option.dataset.tag = item.key; operatorPick.append(option); });
        operatorPick.addEventListener('change', () => {
          const item = operators[operatorPick.value];
          if (!item) return;
          const values = item.values === 'none' ? '' : item.values === 'list' ? ' (A, B)' : " 'value'";
          insertAtCaret(formula, ` ${operatorPick.value}${values}`);
          operatorPick.value = '';
        });
        toolbar.append(operatorPick);
        logic.append(toolbar, formula);
      }
      logic.append(operatorReference());
      form.append(logic);

      // What the rows no rule gives a value get
      const otherwise = el('section', 'acf-otherwise');
      otherwise.append(sectionHead(model.mode === 'rules' ? 'When no rule gives a value' : 'When the formula gives no value',
        'The rows no rule takes keep this instead.'));
      const choices = el('div', 'acf-otherwise-choices');
      const option = (kind, label) => {
        const choice = el('label', 'acf-otherwise-choice');
        const radio = el('input'); radio.type = 'radio'; radio.name = 'acf-otherwise'; radio.value = kind;
        radio.checked = model.otherwise.kind === kind;
        radio.disabled = !data.can_edit;
        radio.addEventListener('change', () => { model.otherwise.kind = kind; touch({structure: true}); });
        choice.append(radio, el('span', '', label));
        choices.append(choice);
        return choice;
      };
      option('empty', 'Leave it empty');
      const fixed = option('value', 'A fixed value');
      const copied = option('field', 'The value of another field');
      if (model.otherwise.kind === 'value') {
        const value = el('input', 'acf-otherwise-value');
        value.value = model.otherwise.value;
        value.placeholder = 'Others';
        value.disabled = !data.can_edit;
        value.addEventListener('input', () => { model.otherwise.value = value.value; touch(); });
        fixed.append(value);
      }
      if (model.otherwise.kind === 'field') {
        const detail = el('div', 'acf-otherwise-field');
        const fieldsBox = el('div', 'acf-condition-fields');
        (model.otherwise.fields.length ? model.otherwise.fields : ['']).forEach((name, fieldIndex) => {
          if (fieldIndex) fieldsBox.append(el('span', 'acf-or', 'or'));
          const select = fieldSelect(name, (value) => {
            model.otherwise.fields[fieldIndex] = value;
            model.otherwise.fields = model.otherwise.fields.filter(Boolean);
            touch({structure: true});
          });
          select.disabled = !data.can_edit;
          fieldsBox.append(select);
        });
        if (data.can_edit && model.otherwise.fields.length) {
          const alternative = button('+ or', 'acf-alternative', 'Add another spelling of the field: the first one the CDR has is read');
          alternative.addEventListener('click', () => { model.otherwise.fields.push(''); renderEditor(); });
          fieldsBox.append(alternative);
        }
        const empty = el('label', 'acf-otherwise-fallback');
        empty.append(el('span', '', 'and where that field is empty:'));
        const value = el('input', 'acf-otherwise-value');
        value.value = model.otherwise.value;
        value.placeholder = 'leave it empty';
        value.disabled = !data.can_edit;
        value.addEventListener('input', () => { model.otherwise.value = value.value; touch(); });
        empty.append(value);
        detail.append(fieldsBox, empty);
        copied.append(detail);
      }
      otherwise.append(choices);
      form.append(otherwise);

      // Check and try on the CDRs
      checkBox = el('section', 'acf-check');
      previewBox = el('section', 'acf-preview');
      form.append(checkBox, previewBox);
      editor.append(form);

      footer = el('footer', 'acf-footer');
      const left = el('div', 'acf-footer-left');
      if (current.original && data.can_edit) {
        const remove = button('Delete', 'acf-delete');
        remove.addEventListener('click', () => { void deleteField(); });
        const duplicate = button('Duplicate', 'acf-secondary');
        duplicate.addEventListener('click', () => { void duplicateField(); });
        left.append(remove, duplicate);
      }
      statusLine = el('span', 'acf-status');
      const right = el('div', 'acf-footer-right');
      discardButton = button(current.original ? 'Discard changes' : 'Cancel', 'acf-secondary');
      discardButton.addEventListener('click', () => { void discard(); });
      saveButton = button('Save', 'acf-save', 'Save the field and update the CDR tables in the background (Ctrl+S)');
      saveButton.addEventListener('click', () => { void save(); });
      right.append(statusLine, discardButton, saveButton);
      if (!data.can_edit) right.replaceChildren(el('span', 'acf-status', 'Read only: your role cannot change the fields.'));
      footer.append(left, right);
      editor.append(footer);
      renderCheck();
      renderPreview();
      updateFooter();
    };

    const updateFooter = () => {
      if (!footer || !saveButton) return;
      const dirty = isDirty();
      const check = current?.check;
      saveButton.disabled = saving || !dirty || !check || !check.ok || check.pending;
      discardButton.hidden = !dirty && Boolean(current?.original);
      statusLine.textContent = saving ? 'Saving…' : !dirty ? (current?.savedNotice || 'Saved') : check?.pending ? 'Checking…'
        : check && !check.ok ? 'Fix the errors to save' : 'Unsaved changes';
      statusLine.dataset.state = saving ? 'busy' : !dirty ? 'saved' : check && !check.ok ? 'error' : 'dirty';
    };

    const renderCheck = () => {
      if (!checkBox) return;
      checkBox.replaceChildren();
      const check = current?.check;
      if (!check || check.pending) return;
      (check.errors || []).forEach((message) => checkBox.append(el('p', 'acf-message is-error', message)));
      (check.warnings || []).forEach((message) => checkBox.append(el('p', 'acf-message is-warning', message)));
    };

    const percent = (count, rows) => {
      if (!rows) return '';
      const share = count * 100 / rows;
      return share > 0 && share < 0.1 ? '<0.1 %' : `${share.toFixed(share < 10 ? 1 : 0)} %`;
    };
    const renderPreview = () => {
      if (!previewBox) return;
      previewBox.replaceChildren();
      const preview = current?.preview;
      const head = sectionHead('Result on the CDRs', 'Worked out on the CDRs of the workspace as it is now, before saving.');
      const retry = button('Try again', 'acf-secondary acf-preview-retry');
      retry.addEventListener('click', () => { void runPreview(); });
      head.append(retry);
      previewBox.append(head);
      if (!preview) { previewBox.append(el('p', 'acf-note', current?.check?.ok === false ? 'Fix the errors to see the result.' : 'Waiting for the field to be complete…')); return; }
      if (preview.pending) { previewBox.append(el('p', 'acf-note acf-busy', 'Trying the field on the CDRs…')); return; }
      if (preview.error) { previewBox.append(el('p', 'acf-message is-error', preview.error)); return; }
      const sources = Object.entries(preview.sources || {});
      if (!sources.length) { previewBox.append(el('p', 'acf-note', 'Choose the CDR types the field applies to.')); return; }
      const grid = el('div', 'acf-preview-grid');
      sources.forEach(([source, result]) => {
        const card = el('article', 'acf-preview-card');
        const label = SOURCES.find(([key]) => key === source)?.[1] || source;
        const cardHead = el('header');
        cardHead.append(el('strong', '', `CDR-${label}`), el('span', '', result.total_rows
          ? (result.rows < result.total_rows ? `${number.format(result.rows)} of ${number.format(result.total_rows)} rows tried` : `${number.format(result.rows)} rows`)
          : 'No ready CDRs'));
        card.append(cardHead);
        if (result.rows) {
          const bars = el('ul', 'acf-bars');
          result.values.slice(0, 12).forEach((item) => {
            const bar = el('li');
            const name = el('span', 'acf-bar-label', item.value === '' ? '(empty)' : item.value);
            if (item.value === '') name.classList.add('is-empty');
            const track = el('span', 'acf-bar-track');
            const fill = el('span', 'acf-bar-fill'); fill.style.width = `${Math.max(1, item.count * 100 / result.rows)}%`;
            track.append(fill);
            bar.append(name, track, el('span', 'acf-bar-count', `${number.format(item.count)} · ${percent(item.count, result.rows)}`));
            bars.append(bar);
          });
          card.append(bars);
          if (result.distinct > 12) card.append(el('p', 'acf-note', `And ${number.format(result.distinct - 12)} other values.`));
          if (result.rules?.length) {
            const rules = el('ol', 'acf-rule-hits');
            result.rules.forEach((rule, index) => {
              const line = el('li', rule.skipped ? 'is-skipped' : '');
              line.append(el('span', '', `Rule ${index + 1} → ${rule.value}`), el('span', '', rule.skipped ? 'skipped: the CDRs lack its fields' : `${number.format(rule.count)} rows · ${percent(rule.count, result.rows)}`));
              rules.append(line);
            });
            if (result.unmatched !== null && result.unmatched !== undefined) {
              const line = el('li', 'is-otherwise');
              line.append(el('span', '', 'No rule'), el('span', '', `${number.format(result.unmatched)} rows · ${percent(result.unmatched, result.rows)}`));
              rules.append(line);
              // What those rows get, each part with its own count and share of all the rows.
              const empty = result.unmatched - (result.from_field || 0) - (result.from_default || 0);
              const otherwise = current.model.otherwise;
              [[result.from_field, `keep the value of ${fieldsText(otherwise.fields)}`], [result.from_default, `get the value ${otherwise.value}`],
                [(result.from_field || result.from_default) ? empty : 0, 'are left empty']].forEach(([count, label]) => {
                if (!count) return;
                const part = el('li', 'is-otherwise-part');
                part.append(el('span', '', `↳ ${label}`), el('span', '', `${number.format(count)} · ${percent(count, result.rows)}`));
                rules.append(part);
              });
            }
            card.append(rules);
            // Why no rule takes those rows: the values they have in each field the conditions read.
            if (result.unmatched && result.unmatched_fields?.length) {
              const why = el('div', 'acf-unmatched');
              why.append(el('p', 'acf-unmatched-title', 'Values of the rows no rule takes'));
              result.unmatched_fields.forEach((item) => {
                const line = el('div', 'acf-unmatched-field');
                line.append(el('code', '', `[${item.field}]`));
                item.values.forEach((entry) => {
                  const chip = el('span', 'acf-unmatched-value');
                  chip.append(el('span', entry.value === '' ? 'is-empty' : '', entry.value === '' ? '(empty)' : entry.value), el('small', '', number.format(entry.count)));
                  chip.title = `${number.format(entry.count)} rows no rule takes have ${entry.value === '' ? 'no value' : entry.value} in ${item.field}`;
                  line.append(chip);
                });
                if (item.distinct > item.values.length) line.append(el('span', 'acf-note', `+${number.format(item.distinct - item.values.length)} more`));
                why.append(line);
              });
              card.append(why);
            }
          }
        }
        if (result.missing?.length) card.append(el('p', 'acf-message is-warning', `These CDRs have no ${result.missing.join(', ')}.`));
        grid.append(card);
      });
      previewBox.append(grid);
    };

    // ---- checking and trying, a moment after each change
    const scheduleCheck = () => {
      if (!current) return;
      window.clearTimeout(checkTimer);
      window.clearTimeout(previewTimer);
      current.check = {...(current.check || {}), pending: true};
      updateFooter();
      checkTimer = window.setTimeout(() => { void runCheck(); }, 350);
    };
    const runCheck = async () => {
      if (!current) return;
      const target = current;
      checkAbort?.abort();
      checkAbort = new AbortController();
      try {
        const result = await request('/check', {field: toPayload(target.model), original_name: target.original, position: target.position}, checkAbort.signal);
        if (current !== target) return;
        target.check = result;
        target.formulaRules = result.field ? {rules: result.field.formula_rules, otherwise: result.field.formula_else} : target.formulaRules;
      } catch (error) {
        if (error.name === 'AbortError' || current !== target) return;
        target.check = {ok: false, errors: [error.message], warnings: []};
      }
      renderCheck(); updateFooter();
      if (target.check.ok) {
        const key = signature(target.model);
        if (target.preview && target.preview.key === key && !target.preview.error) return;
        previewTimer = window.setTimeout(() => { void runPreview(); }, 600);
      } else if (target.preview && !target.preview.pending) {
        target.preview = null; renderPreview();
      }
    };
    const runPreview = async () => {
      if (!current) return;
      const target = current;
      const key = signature(target.model);
      previewAbort?.abort();
      previewAbort = new AbortController();
      target.preview = {pending: true, key};
      renderPreview();
      try {
        const result = await request('/preview', {field: toPayload(target.model), original_name: target.original, position: target.position}, previewAbort.signal);
        if (current !== target) return;
        target.preview = result.ok ? {...result, key} : {error: (result.errors || []).join(' ') || 'The field could not be tried.', key};
      } catch (error) {
        if (error.name === 'AbortError' || current !== target) return;
        target.preview = {error: error.message, key};
      }
      renderPreview();
    };

    // ---- actions
    const confirmLeave = async () => {
      if (!isDirty()) return true;
      const name = current.model.name.trim() || 'the new field';
      return confirmDialog(`Discard the unsaved changes of ${name}?`, {
        title: 'Unsaved Auto-calculated Field', confirmLabel: 'Discard changes', cancelLabel: 'Keep editing', tone: 'warning',
      });
    };
    const setCurrent = (field, extra = {}) => {
      const model = field ? toModel(field) : extra.model;
      current = {original: field ? field.name : null, position: extra.position ?? data.fields.length, model,
        baseline: field ? signature(model) : '', check: null, preview: null, savedNotice: extra.savedNotice || ''};
      renderEditor();
      renderList();
      if (field || extra.check) scheduleCheck();
    };
    async function select(name) {
      if (current?.original && identity(current.original) === identity(name)) return;
      if (!await confirmLeave()) return;
      const field = data.fields.find((item) => identity(item.name) === identity(name));
      if (field) setCurrent(field);
    }
    async function createField(model = null, position = data.fields.length) {
      if (!data.can_edit || !await confirmLeave()) return;
      setCurrent(null, {position, check: Boolean(model), model: model || {
        name: '', sources: SOURCES.map(([key]) => key), mode: 'rules',
        rules: [{join: 'AND', conditions: [{fields: [], operator: '=', values: []}], value: ''}],
        formula: '', otherwise: {kind: 'empty', fields: [], value: ''},
      }});
      editor.querySelector('.acf-name input')?.focus();
    }
    async function duplicateField() {
      if (!current?.original) return;
      const names = new Set(data.fields.map((field) => identity(field.name)));
      let copyName = `${current.model.name.trim()} Copy`; let suffix = 2;
      while (names.has(identity(copyName))) copyName = `${current.model.name.trim()} Copy ${suffix++}`;
      const model = {...clone(current.model), name: copyName};
      await createField(model, indexOf(current.original) + 1);
    }
    async function switchMode(mode) {
      const model = current.model;
      if (model.mode === mode) return;
      if (mode === 'formula') {
        model.formula = model.formula.trim() || formulaFromRules(model);
        model.mode = 'formula';
      } else {
        const converted = current.formulaRules;
        if (model.formula.trim() && !converted?.rules) {
          infoDialog(converted ? 'This formula has nested IF blocks, so it can only be edited as a formula.' : 'Fix the formula first: it is turned into rules once it is valid.', {title: 'Auto-calculated Fields', tone: 'warning'});
          return;
        }
        if (converted?.rules) {
          model.rules = converted.rules.map((rule) => (rule.conditions
            ? {join: rule.join || 'AND', conditions: clone(rule.conditions), value: rule.value}
            : {join: null, text: rule.when, value: rule.value}));
          if (converted.otherwise !== null && converted.otherwise !== undefined) {
            model.otherwise = {kind: 'value', fields: [], value: converted.otherwise};
          }
        }
        if (!model.rules.length) model.rules.push({join: 'AND', conditions: [{fields: [], operator: '=', values: []}], value: ''});
        model.formula = '';
        model.mode = 'rules';
      }
      touch({structure: true});
    }
    async function discard() {
      if (!current) return;
      if (isDirty() && !await confirmLeave()) return;
      const field = current.original ? data.fields.find((item) => identity(item.name) === identity(current.original)) : null;
      if (field) setCurrent(field); else { current = null; renderEditor(); renderList(); }
    }
    const applySaved = (payload, focusName) => {
      data.fields = payload.fields || data.fields;
      changed = true;
      if (payload.materialization_status_url && typeof window.monitorAutoCalculatedFieldJob === 'function') {
        window.monitorAutoCalculatedFieldJob(payload.materialization_status_url);
      }
      options.onChange?.(data.fields, payload);
      const field = focusName ? data.fields.find((item) => identity(item.name) === identity(focusName)) : null;
      if (field) setCurrent(field, {savedNotice: payload.notice});
      else { current = null; renderEditor(); renderList(); }
    };
    async function save() {
      if (!current || saving || !isDirty() || !current.check?.ok || current.check.pending) return;
      saving = true; updateFooter();
      const target = current;
      try {
        const payload = await request('/save', {field: toPayload(target.model), original_name: target.original, position: target.position});
        saving = false;
        applySaved(payload, payload.field?.name);
      } catch (error) {
        saving = false; updateFooter();
        infoDialog(error.message, {title: 'The field was not saved', tone: 'error'});
      }
    }
    async function deleteField() {
      if (!current?.original) return;
      const name = current.original;
      if (!await confirmDialog(`Delete the Auto-calculated Field ${name}? Its column leaves the CDR tables in the background, and the PPT Templates and Designs that use it lose it.`, {
        title: 'Delete Auto-calculated Field', confirmLabel: 'Delete', tone: 'danger',
      })) return;
      try {
        applySaved(await request('/delete', {name}), null);
      } catch (error) {
        infoDialog(error.message, {title: 'The field was not deleted', tone: 'error'});
      }
    }
    async function move(index, step) {
      const names = data.fields.map((field) => field.name);
      [names[index], names[index + step]] = [names[index + step], names[index]];
      try {
        const payload = await request('/reorder', {names});
        data.fields = payload.fields || data.fields;
        changed = true;
        options.onChange?.(data.fields, payload);
        if (current && !current.original) current.position = Math.min(current.position, data.fields.length);
        renderList();
        if (current) scheduleCheck();
      } catch (error) {
        infoDialog(error.message, {title: 'The fields were not moved', tone: 'error'});
      }
    }
    const finish = () => {
      window.clearTimeout(checkTimer); window.clearTimeout(previewTimer);
      checkAbort?.abort(); previewAbort?.abort();
      document.removeEventListener('keydown', onKeydown, true);
      window.removeEventListener('auto-calculated-field-job-status', onJobStatus);
      window.removeEventListener('resize', hideSuggestions);
      suggestions.remove();
      overlay.remove();
      options.onClose?.(data.fields, changed);
    };
    const requestClose = async () => { if (await confirmLeave()) finish(); };
    // Once the CDR tables hold the saved field, the footer says so.
    const onJobStatus = (event) => {
      if (!current || isDirty() || !['ready', 'completed'].includes(event.detail?.status)) return;
      current.savedNotice = 'Saved. The CDR tables are up to date.';
      updateFooter();
    };
    const onKeydown = (event) => {
      if (!overlay.isConnected || document.querySelector('#confirm-overlay:not([hidden]), .info-overlay:not([hidden])')) return;
      if (event.key === 'Escape') {
        if (!suggestions.hidden) { hideSuggestions(); event.preventDefault(); return; }
        if (document.querySelector('.native-select-menu')) return;
        event.preventDefault(); event.stopImmediatePropagation();
        void requestClose();
      } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
        event.preventDefault();
        void save();
      }
    };
    close.addEventListener('click', () => { void requestClose(); });
    overlay.addEventListener('pointerdown', (event) => { if (event.target === overlay) void requestClose(); });
    addButton.addEventListener('click', () => { void createField(); });
    search.addEventListener('input', renderList);
    document.addEventListener('keydown', onKeydown, true);
    window.addEventListener('auto-calculated-field-job-status', onJobStatus);
    window.addEventListener('resize', hideSuggestions);
    editor.addEventListener('scroll', hideSuggestions, {passive: true});

    // ---- load
    editor.append(el('p', 'acf-note acf-busy', 'Loading the fields…'));
    request('').then((payload) => {
      data = payload;
      operators = Object.fromEntries((payload.operators || []).map((item) => [item.key, item]));
      eyebrow.textContent = payload.workspace ? `Workspace ${payload.workspace}` : 'Active Workspace';
      addButton.hidden = !data.can_edit;
      const focus = options.focus ? data.fields.find((field) => identity(field.name) === identity(options.focus)) : null;
      if (focus) setCurrent(focus);
      else if (options.focus === 'new' && data.can_edit) void createField();
      else if (data.fields.length) setCurrent(data.fields[0]);
      else { renderEditor(); renderList(); }
    }).catch((error) => {
      editor.replaceChildren(el('p', 'acf-message is-error', error.message || 'The fields could not be loaded.'));
    });
    close.focus();
  }

  window.AutoCalculatedFields = {open};
})();
