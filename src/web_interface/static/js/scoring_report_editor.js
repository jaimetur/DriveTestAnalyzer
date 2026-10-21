// Scoring report editor: scenarios with their filters, Split by levels and the
// content of each scoring. Used by the Scoring & GAP Analysis exports and by the
// Scoring artifact of Reporting Jobs. It lists the panels the workspace exports
// (Workspace Config > Scoring Export Panels), each with the operators it exports.
(() => {
  const LEVELS = ['Operator', 'Vendor', 'Region', 'Cluster', 'City', 'Campaign'];
  const FILTERS = ['Operator', 'Operator_Vendor', 'Vendor_Operator', 'Vendor', 'Region', 'Cluster', 'City', 'Campaign'];
  const SCORINGS = [['best_network', 'Best Network'], ['most_reliable', 'Most Reliable Network']];
  // The slides of each scoring, in the groups (and order) of the results tabs.
  const SUMMARY_OPTIONS = [
    ['scope', 'How the measurements ran'], ['act', 'Where to act'], ['owners', 'Where to act, by performance owner'],
    ['standings', 'Standings: where each operator stands'], ['position', 'Position per environment and service'],
    ['levers', 'Biggest levers against the reference'], ['places', 'Cities, Towns, Roads and Railways ranked'],
    ['route', 'The route that loses most: where the points are'],
  ];
  const CHART_OPTIONS = [
    ['service', 'Scoring per Service'], ['category', 'Scoring per Category'],
    ['breakdown', 'Scoring per Category (Breakdown)'],
  ];
  const GEOGRAPHICAL_AREA_OPTIONS = [
    ['cards', 'Scoring Nationwide and per City / Cluster / Region cards'], ['ranking', 'Geographical Areas ranked'],
    ['versus', 'Each operator against the reference per geographical area'],
  ];
  // The Scoring Trends, of the campaigns of the Scoring Trends of the scenario.
  const TREND_OPTIONS = [['trend', 'Scoring Trend (two campaigns or more)'], ['areas', 'National & Geographical Areas Trends']];
  const POINTS_OPTIONS = [
    ['stake', 'Where the points go'], ['kpis', 'Points lost per KPI'], ['map', 'Points lost per City / Region map, by points and per 1,000 tests'], ['vendors', 'Points lost per Vendor'],
    ['site_types', 'Points lost per kind of site'], ['sites', 'Sites to review'], ['stretches', 'Route stretches'],
  ];
  // Options of configurations saved before that are now in another group.
  const MOVED_OPTIONS = {'geographical_areas:cards': ['charts', 'location_cards'], 'points:map': ['gap', 'points_loss_map'],
    'points:kpis': ['gap', 'profile'], 'trends:trend': ['charts', 'trend']};
  const TABLE_OPTIONS = [
    ['summary', 'Category table'], ['breakdown', 'Breakdown table'], ['kpi_values', 'Show KPI values'],
    ['gap_values', 'Show GAP values'], ['campaign_comparison', 'Campaign comparison (two latest campaigns)'],
  ];
  const AREA_BREAKDOWNS = ['None', 'Region', 'Cluster', 'City'];
  // The time split of the National & Geographical Areas Trends: every selected CDR in one value, per campaign or per period.
  const TIME_SPLITS = [['All', 'All selected CDRs'], ['Campaign', 'Campaign'], ['Daily', 'Daily'], ['Weekly', 'Weekly'],
    ['Monthly', 'Monthly'], ['Quarterly', 'Quarterly'], ['Yearly', 'Yearly']];
  // Its campaigns are those of the Scoring Trends of the scenario: All available campaigns by default (none: the
  // campaigns of the scenario). Every scenario has the National & Geographical Areas Trends by default (scored on the whole country).
  const defaultAreaSummary = () => ({enabled: true, time_split: 'Campaign',
    breakdown: 'Region', cities: ['London'], main_cities: false, campaigns: ['@all-campaigns']});
  // The automatic choices of the campaigns of the Scoring Trends, which follow the newest campaigns at each report.
  const TREND_PRESETS = [['@latest-campaign', 'Latest campaign'], ['@latest-2-campaigns', 'Latest 2 campaigns'],
    ['@latest-3-campaigns', 'Latest 3 campaigns'], ['@latest-4-campaigns', 'Latest 4 campaigns'],
    ['@previous-campaign', 'Previous campaign'], ['@all-campaigns', 'All available campaigns']];
  const GAP_OPTIONS = [
    ['all_operators', 'Table comparing all the chosen operators'], ['individual', 'Individual tables against the reference'],
    ['parts', 'GAP by part over the campaigns'], ['profile', 'KPI GAP Profile'],
  ];

  // The panels the workspace exports ({group: {panel: {exportable, operators}}}), once loaded; every panel until then.
  let exportPanels = null;
  const exportable = (group, option) => exportPanels?.[group]?.[option]?.exportable !== false;
  const focusPanel = (group, option) => exportPanels?.[group]?.[option]?.operators === 'focus';

  const clone = (value) => JSON.parse(JSON.stringify(value));
  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  function defaultOptions() {
    return {
      enabled: true, environments: 'all',
      summary: {standings: true, position: true, levers: true, act: true, owners: true, places: true, route: true, scope: true},
      charts: {service: true, category: true, breakdown: true},
      tables: {summary: true, breakdown: true, kpi_values: false, gap_values: false, campaign_comparison: true},
      geographical_areas: {cards: true, ranking: true, versus: true},
      trends: {trend: true, areas: true},
      gap: {all_operators: true, individual: true, parts: true, profile: true},
      points: {stake: true, kpis: true, map: true, vendors: true, site_types: true, sites: true, stretches: true},
    };
  }

  // The options of a scoring with every group, those saved before in another group read from it.
  function completeOptions(options) {
    const defaults = defaultOptions([]);
    // (Geographical Areas was Locations.)
    if (!options.geographical_areas && options.locations && typeof options.locations === 'object') options.geographical_areas = options.locations;
    delete options.locations;
    for (const [group, values] of Object.entries(defaults)) {
      if (typeof values !== 'object' || Array.isArray(values)) continue;
      options[group] = options[group] && typeof options[group] === 'object' ? options[group] : {};
      for (const [option, value] of Object.entries(values)) {
        if (option in options[group]) continue;
        const moved = MOVED_OPTIONS[`${group}:${option}`];
        options[group][option] = moved && options[moved[0]] && moved[1] in options[moved[0]] ? Boolean(options[moved[0]][moved[1]]) : value;
      }
    }
    return options;
  }

  function defaultScenario({name = 'National', filters = {}, levels = ['Operator'], mainCities = false} = {}) {
    const scenario = {
      name, context_filters: clone(filters), main_cities: mainCities,
      // Campaign is always included: a scenario with a single campaign leaves the level out.
      aggregation_levels: ['Operator', ...LEVELS.filter((level) => level !== 'Operator' && (levels.includes(level) || level === 'Campaign'))],
      scorings: Object.fromEntries(SCORINGS.map(([key]) => [key, defaultOptions()])),
    };
    scenario.area_summary = defaultAreaSummary(scenario);
    return scenario;
  }

  function defaultConfiguration(context = {}) {
    return {scenarios: [defaultScenario(context)]};
  }

  function checkbox(label, checked, onChange, title = '') {
    const wrapper = el('label', 'scoring-report-check');
    const input = el('input');
    input.type = 'checkbox';
    input.checked = Boolean(checked);
    input.addEventListener('change', () => onChange(input.checked));
    wrapper.append(input, el('span', '', label));
    if (title) wrapper.title = title;
    return wrapper;
  }

  // A compact multi-value dropdown: an empty selection means every value.
  // Campaigns as the workspace Campaign Maps show and order them (campaign_labels.js); the filter keeps the full value.
  const campaignField = (label) => label === 'Campaign' && typeof globalThis.campaignLabel === 'function';

  document.addEventListener('pointerdown', (event) => {
    document.querySelectorAll('details.scoring-report-picker[open]').forEach((picker) => {
      if (!picker.contains(event.target)) picker.open = false;
    });
  });

  // With ``patterns`` (the Operators), a pattern typed in the filter (VF*, Not Lebara; see valuePatterns in app.js) is
  // added with Enter, listed first; it is resolved when the report is generated.
  function checklist(label, values, selected, onChange, {preset = null, allOption = false, emptyLabel = 'All', patterns = false} = {}) {
    const wrapper = el('details', 'scoring-report-picker');
    // One picker open at a time; it closes when opening another one or clicking outside.
    wrapper.addEventListener('toggle', () => {
      if (!wrapper.open) return;
      document.querySelectorAll('details.scoring-report-picker[open]').forEach((other) => {
        if (other !== wrapper) other.open = false;
      });
    });
    const summary = el('summary');
    const display = (value) => (campaignField(label) ? globalThis.campaignLabel(value) || value : value);
    const isPattern = (value) => patterns && Boolean(globalThis.valuePatterns?.isPattern(value));
    const known = [...new Set([...(values || []), ...(selected || [])])].filter((value) => !isPattern(value));
    if (campaignField(label) && typeof globalThis.campaignCompare === 'function') known.sort(globalThis.campaignCompare);
    const selection = new Set(selected || []);
    // All: no restriction, so every value of the CDRs at generation time is included (also new ones).
    let allMode = allOption && !selection.size && !preset?.checked;
    // A preset (Main Cities) is resolved when the report is generated; its values are shown checked.
    const presetKeys = new Set((preset?.values || []).map((value) => String(value).toLocaleLowerCase()));
    const inPreset = (value) => presetKeys.has(String(value).toLocaleLowerCase());
    const isChecked = (value) => allMode || (preset?.checked ? inPreset(value) : selection.has(value));
    const setPreset = (checked) => {
      if (!preset || preset.checked === checked) return;
      preset.checked = checked;
      preset.onChange(checked);
    };
    const list = el('div', 'scoring-report-picker-list');
    // Typing filters the listed values; presets such as Main Cities stay visible.
    const search = el('input', 'scoring-report-picker-search');
    search.type = 'search';
    search.placeholder = 'Filter values…';
    search.setAttribute('aria-label', `Filter ${label} values`);
    const valueRows = [];
    const valueBoxes = new Map();
    const patternBoxes = new Map();
    let allBox = null;
    let presetBox = null;
    const render = () => {
      if (allBox) allBox.checked = allMode;
      if (presetBox) presetBox.checked = Boolean(preset.checked);
      valueBoxes.forEach((box, value) => { box.checked = isChecked(value); });
      patternBoxes.forEach((box, value) => { box.checked = selection.has(value); });
      // One value is shown by name, several by their number (as the other filters of the application).
      const chosen = [...known.filter((value) => selection.has(value)), ...[...selection].filter((value) => !known.includes(value))].map(display);
      const total = known.length;
      const text = preset?.checked ? `${preset.label} (${known.filter(inPreset).length}/${total})`
        : allMode ? 'All' : !chosen.length ? emptyLabel
          : chosen.length === 1 ? chosen[0] : `${chosen.length}/${total} selected`;
      summary.textContent = `${label}: ${text}`;
      summary.title = preset?.checked || allMode || chosen.length < 2 ? summary.textContent : `${label}: ${chosen.join(', ')}`;
    };
    const commit = () => {
      onChange([...selection]);
      render();
    };
    // Editing single values starts from what is shown checked (All or the preset).
    const materialize = () => {
      const shown = known.filter(isChecked);
      selection.clear();
      shown.forEach((value) => selection.add(value));
      allMode = false;
      setPreset(false);
    };
    search.addEventListener('input', () => {
      const query = search.value.trim().toLocaleLowerCase();
      valueRows.forEach((row) => { row.hidden = Boolean(query) && !row.textContent.toLocaleLowerCase().includes(query); });
    });
    // A pattern, listed first with its tag; unticked, it is left out of the filter.
    const patternRow = (value) => {
      const row = checkbox(value, selection.has(value), (checked) => {
        if (checked) selection.add(value); else selection.delete(value);
        commit();
      });
      row.classList.add('scoring-report-pattern');
      row.append(el('span', 'user-choice-tag user-choice-tag-pattern', globalThis.valuePatterns.tag(value)));
      patternBoxes.set(value, row.querySelector('input'));
      return row;
    };
    const patternAdd = patterns ? el('button', 'multiselect-pattern-add') : null;
    if (patternAdd) {
      patternAdd.type = 'button';
      patternAdd.hidden = true;
      search.placeholder = 'Filter, or type a pattern such as VF* or -Lebara';
      const add = () => {
        const value = search.value.trim();
        if (!isPattern(value)) return;
        // A pattern chooses on its own: every value (All) or the preset give way to it.
        if (allMode || preset?.checked) { selection.clear(); allMode = false; setPreset(false); }
        selection.add(value);
        if (!patternBoxes.has(value)) {
          const row = patternRow(value);
          const after = [...patternBoxes.values()].at(-2)?.closest('label');
          if (after) after.after(row); else patternAdd.after(row);
        }
        search.value = '';
        search.dispatchEvent(new Event('input'));
        commit();
      };
      patternAdd.addEventListener('click', add);
      search.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && isPattern(search.value.trim())) { event.preventDefault(); add(); }
      });
      search.addEventListener('input', () => {
        const value = search.value.trim();
        patternAdd.hidden = !isPattern(value);
        patternAdd.textContent = `＋ Add pattern “${value}” · takes ${isPattern(value) ? known.filter((item) => globalThis.valuePatterns.set([value]).accepts(item)).length : 0} now`;
      });
    }
    wrapper.addEventListener('toggle', () => {
      if (!wrapper.open) return;
      search.value = '';
      valueRows.forEach((row) => { row.hidden = false; });
      if (valueRows.length > 1) search.focus();
    });
    // The patterns come first, below the filter.
    if (patterns) [...selection].filter(isPattern).forEach((value) => list.append(patternRow(value)));
    if (known.length > 1) {
      // Select All / None acts on the listed values (those matching the search).
      const toggle = el('button', 'scoring-report-picker-toggle', 'Select All / None');
      toggle.type = 'button';
      toggle.addEventListener('click', () => {
        const listed = known.filter((value) => !valueRows[known.indexOf(value)].hidden);
        const selectAll = listed.some((value) => !isChecked(value));
        if (listed.length === known.length) {
          selection.clear();
          setPreset(false);
          allMode = selectAll && allOption;
          if (selectAll && !allOption) known.forEach((value) => selection.add(value));
        } else {
          materialize();
          listed.forEach((value) => { if (selectAll) selection.add(value); else selection.delete(value); });
        }
        commit();
      });
      list.append(toggle);
    }
    if (preset) {
      const presetRow = checkbox(preset.label, preset.checked, (checked) => {
        selection.clear();
        setPreset(checked);
        // Without the preset the filter goes back to every value.
        allMode = !checked && allOption;
        commit();
      });
      presetBox = presetRow.querySelector('input');
      list.append(presetRow);
    }
    if (allOption && known.length) {
      const allRow = checkbox('All', allMode, (checked) => {
        selection.clear();
        setPreset(false);
        allMode = checked;
        if (!checked) known.forEach((value) => selection.add(value));
        commit();
      }, 'Every value of the selected CDRs when the report is generated, also values that appear later');
      allRow.classList.add('scoring-report-all');
      allBox = allRow.querySelector('input');
      list.append(allRow);
    }
    if (!known.length) list.append(el('span', 'scoring-report-muted', 'No values in the selected CDRs'));
    for (const value of known) {
      const row = checkbox(display(value), isChecked(value), (checked) => {
        materialize();
        if (checked) selection.add(value); else selection.delete(value);
        commit();
      });
      valueBoxes.set(value, row.querySelector('input'));
      valueRows.push(row);
      list.append(row);
    }
    if (patternAdd) {
      list.prepend(search, el('p', 'multiselect-pattern-help', globalThis.valuePatterns?.help || ''), patternAdd);
    } else if (valueRows.length > 1) {
      list.prepend(search);
    }
    render();
    wrapper.append(summary, list);
    wrapper.knownValues = () => [...known];
    // Replaces the chosen values (none means All) without calling onChange.
    wrapper.setSelection = (values) => {
      selection.clear();
      values.forEach((value) => selection.add(value));
      setPreset(false);
      allMode = allOption && !selection.size;
      render();
    };
    return wrapper;
  }

  // The options of a group of panels: those the workspace exports (``name`` is the group of the panels; the KPI and GAP
  // values of the tables are not panels), the panels of the Focus operators tagged.
  function optionGroup(title, options, values, onChange, diffPrefix, name = '') {
    const group = el('fieldset', 'scoring-report-group');
    group.append(el('legend', '', title));
    const shown = options.filter(([key]) => !name || exportable(name, key));
    for (const [key, label] of shown) {
      const box = checkbox(label, values[key], (checked) => onChange(key, checked));
      box.dataset.diffKey = `${diffPrefix}:${key}`;
      if (name && focusPanel(name, key)) {
        const tag = el('span', 'scoring-report-focus-tag', 'Focus');
        tag.title = 'Exports the Focus operators of the Operator Maps (every operator with Export All Operators in Focus panels)';
        box.append(tag);
      }
      group.append(box);
    }
    group.hidden = !shown.length;
    return group;
  }

  // The comparable value of one setting of a scenario (see markDifferences), or undefined where it does not apply.
  function settingValue(scenario, key) {
    const [kind, name, group, option] = key.split(':');
    if (kind === 'filter') {
      return JSON.stringify([[...(scenario.context_filters[name] || [])].map(String).sort(), name === 'City' && Boolean(scenario.main_cities)]);
    }
    if (kind === 'level') return String(scenario.aggregation_levels.includes(name));
    if (kind === 'area') {
      const summary = scenario.area_summary;
      if (name === 'campaigns') return JSON.stringify([...(summary.campaigns || [])].map(String).sort());
      if (name === 'enabled') return String(Boolean(summary.enabled));
      if (!summary.enabled) return undefined;
      if (name === 'time_split') return summary.time_split || 'Campaign';
      return name === 'breakdown' ? summary.breakdown
        : JSON.stringify([[...summary.cities].map(String).sort(), Boolean(summary.main_cities)]);
    }
    const options = scenario.scorings[name];
    if (group === 'enabled') return String(Boolean(options.enabled));
    if (!options.enabled) return undefined;
    if (group === 'environments') return options.environments;
    return String(Boolean(options[group]?.[option]));
  }

  // Highlights in every scenario the settings whose value is not the same in all of them.
  function markDifferences(list, scenarios) {
    const nodes = [...list.querySelectorAll('[data-diff-key]')];
    const changed = new Set();
    if (scenarios.length > 1) {
      for (const key of new Set(nodes.map((node) => node.dataset.diffKey))) {
        const values = scenarios.map((scenario) => settingValue(scenario, key)).filter((value) => value !== undefined);
        if (new Set(values).size > 1) changed.add(key);
      }
    }
    for (const node of nodes) {
      const scenario = scenarios[Number(node.closest('[data-scenario-index]')?.dataset.scenarioIndex)];
      node.classList.toggle('is-scenario-diff', changed.has(node.dataset.diffKey)
        && Boolean(scenario) && settingValue(scenario, node.dataset.diffKey) !== undefined);
    }
  }

  function scoringPanel(scenario, key, label, operators, rerender) {
    const options = scenario.scorings[key];
    const panel = el('section', `scoring-report-scoring scoring-report-${key}`);
    const head = el('div', 'scoring-report-scoring-head');
    const enabled = checkbox(`${label} scoring`, options.enabled, (checked) => { options.enabled = checked; rerender(); });
    enabled.dataset.diffKey = `scoring:${key}:enabled`;
    head.append(enabled);
    const environments = el('select');
    environments.dataset.diffKey = `scoring:${key}:environments`;
    for (const [value, text] of [['all', 'All Environments only'], ['split', 'All Environments and each environment']]) {
      const option = el('option', '', text);
      option.value = value;
      environments.append(option);
    }
    environments.value = options.environments;
    environments.addEventListener('change', () => { options.environments = environments.value; });
    environments.disabled = !options.enabled;
    head.append(environments);
    panel.append(head);
    if (!options.enabled) return panel;
    completeOptions(options);
    const body = el('div', 'scoring-report-scoring-body');
    const group = (title, list, name) => optionGroup(title, list, options[name], (option, checked) => { options[name][option] = checked; },
      `scoring:${key}:${name}`, name);
    body.append(
      group('Summary', SUMMARY_OPTIONS, 'summary'),
      optionGroup('Scoring Charts', CHART_OPTIONS.map(([option, text]) => [option, text.startsWith('Scoring per') ? `${label} ${text}` : text]),
        options.charts, (option, checked) => { options.charts[option] = checked; }, `scoring:${key}:charts`, 'charts'),
      group('Scoring Tables', TABLE_OPTIONS, 'tables'),
      group('Geographical Areas', GEOGRAPHICAL_AREA_OPTIONS.map(([option, text]) => [option, option === 'cards' ? `${label} ${text}` : text]), 'geographical_areas'),
      group('Scoring Trends', TREND_OPTIONS.map(([option, text]) => [option, `${label} ${text}`]), 'trends'),
    );
    // (The individual GAP comparisons of the PowerPoint and Word are those of the Focus operators of the Operator Maps.)
    const gap = group('GAP Analysis', GAP_OPTIONS, 'gap');
    body.append(gap, group('Points Lost', POINTS_OPTIONS, 'points'));
    panel.append(body);
    return panel;
  }

  function scenarioCard(state, index, context, rerender) {
    const scenario = state.scenarios[index];
    const card = el('article', 'scoring-report-scenario');
    card.dataset.scenarioIndex = String(index);
    const head = el('div', 'scoring-report-scenario-head');
    const name = el('input');
    name.type = 'text';
    name.maxLength = 80;
    name.value = scenario.name;
    name.setAttribute('aria-label', `Name of scenario ${index + 1}`);
    name.addEventListener('input', () => { scenario.name = name.value; });
    head.append(el('strong', 'scoring-report-index', `${index + 1}`), name);
    const actions = el('div', 'scoring-report-actions');
    // Move arrows, Duplicate and Remove each have their own colour; Duplicate and Remove an icon.
    const ICONS = {
      duplicate: '<rect x="7" y="7" width="10" height="10" rx="1.5"/><path d="M13 4.5V4a1 1 0 0 0-1-1H4a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h.5"/>',
      remove: '<path d="M3.5 5.5h13M8 5.5V4a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v1.5M5.5 5.5l.8 10.6a1 1 0 0 0 1 .9h5.4a1 1 0 0 0 1-.9l.8-10.6M8.5 8.5v5.5M11.5 8.5v5.5"/>',
    };
    const action = (text, title, disabled, handler, kind) => {
      const button = el('button', `ghost-link scoring-report-action is-${kind}`);
      if (ICONS[kind]) {
        button.insertAdjacentHTML('beforeend', `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[kind]}</svg>`);
      }
      button.append(el('span', '', text));
      button.type = 'button';
      button.title = title;
      button.setAttribute('aria-label', title);
      button.disabled = disabled;
      button.addEventListener('click', handler);
      actions.append(button);
    };
    action('↑', 'Move up', index === 0, () => { state.scenarios.splice(index - 1, 0, ...state.scenarios.splice(index, 1)); rerender(); }, 'move');
    action('↓', 'Move down', index === state.scenarios.length - 1, () => { state.scenarios.splice(index + 1, 0, ...state.scenarios.splice(index, 1)); rerender(); }, 'move');
    action('Duplicate', 'Duplicate this scenario', state.scenarios.length >= 20, () => {
      const copy = clone(scenario);
      copy.name = `${scenario.name} (copy)`;
      state.scenarios.splice(index + 1, 0, copy);
      rerender();
    }, 'duplicate');
    action('Remove', 'Remove this scenario', state.scenarios.length <= 1, () => { state.scenarios.splice(index, 1); rerender(); }, 'remove');
    head.append(actions);
    // From the page the report is one scenario: no name, order, copies or removal.
    if (!context.pageScope) card.append(head);

    scenario.area_summary = scenario.area_summary || defaultAreaSummary(scenario);
    scenario.area_summary.time_split = scenario.area_summary.time_split || 'Campaign';
    const filters = el('div', 'scoring-report-filters');
    // Operator_Vendor and Vendor_Operator hold the same values the other way round: they stay in sync.
    const pickers = {};
    const PAIRED = {Operator_Vendor: 'Vendor_Operator', Vendor_Operator: 'Operator_Vendor'};
    for (const field of FILTERS) {
      const preset = field === 'City' && (context.mainCities || []).length ? {
        label: 'Main Cities', checked: scenario.main_cities, values: context.mainCities,
        onChange: (checked) => { scenario.main_cities = checked; },
      } : null;
      pickers[field] = checklist(field, context.filterOptions?.[field] || [], scenario.context_filters[field] || [], (values) => {
        if (values.length) scenario.context_filters[field] = values; else delete scenario.context_filters[field];
        const partnerField = PAIRED[field];
        const partner = partnerField && pickers[partnerField];
        if (!partner) return;
        const mirrored = globalThis.operatorVendorPairs.mirrorValues(values, partner.knownValues());
        if (mirrored.length) scenario.context_filters[partnerField] = mirrored; else delete scenario.context_filters[partnerField];
        partner.setSelection(mirrored);
      }, {preset, allOption: true, patterns: field === 'Operator'});
      pickers[field].dataset.diffKey = `filter:${field}`;
      filters.append(pickers[field]);
    }
    const levels = el('div', 'scoring-report-levels');
    levels.append(el('span', 'scoring-report-label', 'Split by:'));
    for (const level of LEVELS) {
      const box = checkbox(level, scenario.aggregation_levels.includes(level), (checked) => {
        scenario.aggregation_levels = LEVELS.filter((item) => item === 'Operator'
          || (item === level ? checked : scenario.aggregation_levels.includes(item)));
      });
      if (level === 'Operator') { box.querySelector('input').disabled = true; box.title = 'Operator is required'; }
      box.dataset.diffKey = `level:${level}`;
      levels.append(box);
    }

    // The Geographical Areas & Scoring Trends, always included and scored on the whole country: the Breakdown and Separate
    // cities of the Geographical Areas and of the trends, then the campaigns (whatever the Campaign filter of the
    // scenario) and time split of the trends.
    // (Saved before the Scoring Trends had campaigns: the default; saved unchecked: included now.)
    scenario.area_summary.campaigns = Array.isArray(scenario.area_summary.campaigns) ? scenario.area_summary.campaigns : ['@all-campaigns'];
    scenario.area_summary.enabled = true;
    const trendsPanel = el('fieldset', 'scoring-report-subpanel scoring-report-trends');
    trendsPanel.title = 'Always the whole country: the Region, Cluster, City and Main Cities filters of the scenario do not apply to '
      + 'Geographical Areas and Scoring Trends';
    trendsPanel.append(el('legend', 'scoring-report-label', 'Geographical Areas & Scoring Trends'));
    const areaPanel = el('fieldset', 'scoring-report-subpanel');
    areaPanel.append(el('legend', 'scoring-report-label', 'Geographical Areas'));
    const areaRow = el('div', 'scoring-report-subpanel-row');
    const breakdown = el('select');
    breakdown.setAttribute('aria-label', 'Breakdown of the Geographical Areas and the National & Geographical Areas Trends');
    for (const value of AREA_BREAKDOWNS) {
      const option = el('option', '', value === 'None' ? 'Breakdown: None' : `Breakdown: ${value}`);
      option.value = value;
      option.title = value === 'None' ? 'Only the Separate cities' : '';
      breakdown.append(option);
    }
    breakdown.value = scenario.area_summary.breakdown;
    breakdown.addEventListener('change', () => { scenario.area_summary.breakdown = breakdown.value; });
    breakdown.dataset.diffKey = 'area:breakdown';
    const cities = checklist('Separate cities', context.filterOptions?.City || [], scenario.area_summary.cities, (values) => {
      scenario.area_summary.cities = values;
      syncBreakdown();
    }, {
      emptyLabel: 'None',
      preset: (context.mainCities || []).length ? {
        label: 'Main Cities', checked: scenario.area_summary.main_cities, values: context.mainCities,
        onChange: (checked) => { scenario.area_summary.main_cities = checked; syncBreakdown(); },
      } : null,
    });
    cities.dataset.diffKey = 'area:cities';
    // Without a Breakdown the Separate cities (or Main Cities) are the only areas: None needs some of them.
    function syncBreakdown() {
      const some = (scenario.area_summary.cities || []).length || scenario.area_summary.main_cities;
      const none = [...breakdown.children].find((option) => option.value === 'None');
      if (none) none.disabled = !some;
      if (!some && breakdown.value === 'None') {
        breakdown.value = 'Region';
        scenario.area_summary.breakdown = 'Region';
      }
    }
    syncBreakdown();
    areaRow.append(breakdown, cities);
    areaPanel.append(areaRow);
    const trendPanel = el('fieldset', 'scoring-report-subpanel');
    trendPanel.append(el('legend', 'scoring-report-label', 'Scoring Trends'));
    const trendRow = el('div', 'scoring-report-subpanel-row');
    const trendChoice = el('select');
    trendChoice.setAttribute('aria-label', 'Campaigns of the Scoring Trends');
    trendChoice.title = 'The campaigns of the Scoring Trend and the National & Geographical Areas Trends, whatever the Campaign filter of the scenario';
    for (const [value, text] of [...TREND_PRESETS, ['', 'Same as the scenario'], ['chosen', 'Chosen campaigns']]) {
      const option = el('option', '', `Campaigns: ${text}`);
      option.value = value;
      trendChoice.append(option);
    }
    const trendValues = scenario.area_summary.campaigns;
    const chosenPreset = TREND_PRESETS.find(([value]) => trendValues.includes(value));
    trendChoice.value = chosenPreset ? chosenPreset[0] : trendValues.length ? 'chosen' : '';
    trendChoice.dataset.diffKey = 'area:campaigns';
    const trendCampaigns = checklist('Campaign', (context.filterOptions?.Campaign || []).filter((value) => !String(value).startsWith('@')),
      trendValues.filter((value) => !String(value).startsWith('@')), (values) => {
        scenario.area_summary.campaigns = values;
      }, {emptyLabel: 'None'});
    const syncTrendCampaigns = () => { trendCampaigns.hidden = trendChoice.value !== 'chosen'; };
    trendChoice.addEventListener('change', () => {
      scenario.area_summary.campaigns = trendChoice.value === 'chosen' ? [] : trendChoice.value ? [trendChoice.value] : [];
      trendCampaigns.setSelection([]);
      syncTrendCampaigns();
    });
    syncTrendCampaigns();
    trendRow.append(trendChoice, trendCampaigns);
    const time = el('select');
    time.setAttribute('aria-label', 'Time split of the National & Geographical Areas Trends');
    time.title = 'Only for the National & Geographical Areas Trends. All selected CDRs aggregates every selected CDR into one value; '
      + 'Campaign splits by campaign; Daily to Yearly split by the period of the start time of each test, '
      + 'whatever the CDRs (daily, weekly or per campaign)';
    for (const [value, text] of TIME_SPLITS) {
      const option = el('option', '', `Time split: ${text}`);
      option.value = value;
      time.append(option);
    }
    time.value = scenario.area_summary.time_split;
    time.addEventListener('change', () => { scenario.area_summary.time_split = time.value; });
    time.dataset.diffKey = 'area:time_split';
    trendRow.append(time);
    trendPanel.append(trendRow);
    // The two subpanels side by side, as on the Scoring & GAP Analysis page.
    const columns = el('div', 'scoring-report-columns');
    columns.append(areaPanel, trendPanel);
    trendsPanel.append(columns);
    const scorings = el('div', 'scoring-report-scorings');
    for (const [key, label] of SCORINGS) scorings.append(scoringPanel(scenario, key, label, context.operators || [], rerender));
    if (context.pageScope) {
      // From the Scoring & GAP Analysis page every scenario takes the filters, Split by and Geographical Areas & Scoring
      // Trends of its Calculation panel (as its GAP reference and methodology): here it chooses its content.
      card.append(el('p', 'scoring-report-muted scoring-report-page-scope',
        'Filters, Split by, Geographical Areas & Scoring Trends, GAP reference and methodology: those of the Calculation panel.'),
      scorings);
      return card;
    }
    card.append(filters, levels, trendsPanel, scorings);
    return card;
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {credentials: 'same-origin', ...options});
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'The request failed.');
    return payload;
  }

  // A small dialog over the editor (the browser prompt and confirm look out of place).
  // With `value` it asks for a name and resolves with it, otherwise with true; null when cancelled.
  function ask(host, {title, copy = '', value = null, confirmLabel = 'Save', danger = false}) {
    return new Promise((resolve) => {
      const dialog = el('dialog', 'scoring-report-ask');
      const form = el('form');
      form.method = 'dialog';
      form.append(el('h3', '', title));
      if (copy) form.append(el('p', 'scoring-report-ask-copy', copy));
      let input = null;
      if (value !== null) {
        input = el('input');
        input.type = 'text';
        input.maxLength = 80;
        input.required = true;
        input.value = value;
        input.setAttribute('aria-label', title);
        form.append(input);
      }
      const actions = el('div', 'scoring-report-ask-actions');
      const cancel = el('button', '', 'Cancel');
      cancel.type = 'button';
      const accept = el('button', danger ? 'danger-button' : 'primary-button', confirmLabel);
      accept.type = 'submit';
      actions.append(cancel, accept);
      form.append(actions);
      dialog.append(form);
      let result = null;
      cancel.addEventListener('click', () => dialog.close());
      form.addEventListener('submit', (event) => {
        if (input && !input.value.trim()) { event.preventDefault(); input.focus(); return; }
        result = input ? input.value.trim() : true;
      });
      dialog.addEventListener('close', () => { dialog.remove(); resolve(result); });
      host.append(dialog);
      dialog.showModal();
      if (input) { input.focus(); input.select(); } else accept.focus();
    });
  }

  // A small dialog with several choices: resolves with the key of the chosen one, or null when closed.
  function choose(host, {title, copy = '', choices}) {
    return new Promise((resolve) => {
      const dialog = el('dialog', 'scoring-report-ask');
      dialog.append(el('h3', '', title));
      if (copy) dialog.append(el('p', 'scoring-report-ask-copy', copy));
      const actions = el('div', 'scoring-report-ask-actions');
      let result = null;
      for (const [key, label, className] of choices) {
        const button = el('button', className || 'ghost-link', label);
        button.type = 'button';
        button.addEventListener('click', () => { result = key; dialog.close(); });
        actions.append(button);
      }
      dialog.append(actions);
      dialog.addEventListener('close', () => { dialog.remove(); resolve(result); });
      host.append(dialog);
      dialog.showModal();
    });
  }

  // Icons of the saved configuration buttons.
  const TOOL_ICONS = {
    save: '<path d="M4 3.5h9.5L16.5 6.5V16a.5.5 0 0 1-.5.5H4a.5.5 0 0 1-.5-.5V4a.5.5 0 0 1 .5-.5z"/><path d="M6.5 3.5v4h6v-4M6.5 16.5v-5h7v5"/>',
    delete: '<path d="M3.5 5.5h13M8 5.5V4a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v1.5M5.5 5.5l.8 10.6a1 1 0 0 0 1 .9h5.4a1 1 0 0 0 1-.9l.8-10.6M8.5 8.5v5.5M11.5 8.5v5.5"/>',
    export: '<path d="M10 3v9M6.5 8.5 10 12l3.5-3.5M4 14v2a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-2"/>',
    import: '<path d="M10 12V3M6.5 6.5 10 3l3.5 3.5M4 14v2a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-2"/>',
  };

  // PowerPoint and Word actions use the colours and icons of the export buttons of every module.
  const DOCUMENT_ACTIONS = {
    ppt: ['document-export-powerpoint', '<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4M7 13l3-3 2 2 4-4"/>'],
    word: ['document-export-word', '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M8.5 12l1.2 5 1.8-4 1.8 4 1.2-5"/>'],
  };

  function actionButton(action, text) {
    const documentAction = DOCUMENT_ACTIONS[action === 'powerpoint' ? 'ppt' : action];
    if (!documentAction) return el('button', 'primary-button', text);
    const node = el('button', `document-export-action ${documentAction[0]}`);
    node.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${documentAction[1]}</svg>`;
    node.append(text);
    return node;
  }

  // Operators are shown and saved with their Operator Maps label: source spellings (for example
  // VF_UK) become their canonical Operator, in the order of the Operator Maps.
  function operatorCanonicalizer(groups = []) {
    const canonical = new Map();
    groups.forEach((group) => {
      const name = String(group.canonical || '').trim();
      if (!name) return;
      [name, ...(group.aliases || [])].forEach((alias) => canonical.set(String(alias).trim().toLocaleLowerCase(), name));
    });
    const order = groups.map((group) => String(group.canonical || '').trim());
    const one = (value) => canonical.get(String(value ?? '').trim().toLocaleLowerCase()) || String(value ?? '').trim();
    const list = (values) => [...new Set((values || []).map(one).filter(Boolean))];
    const sorted = (values) => list(values).sort((left, right) => {
      const a = order.indexOf(left);
      const b = order.indexOf(right);
      return (a < 0 ? order.length : a) - (b < 0 ? order.length : b) || left.localeCompare(right);
    });
    // Saved Operators that the CDRs no longer have (for example a renamed Operator) are left out; patterns (VF*,
    // Not Lebara) stay, as they are resolved when the report is generated.
    const available = (values, known) => {
      const names = list(values);
      return known.length ? names.filter((name) => known.includes(name) || globalThis.valuePatterns?.isPattern(name)) : names;
    };
    const configuration = (config, {filterOperators = []} = {}) => {
      (config?.scenarios || []).forEach((scenario) => {
        if (scenario.context_filters?.Operator) {
          scenario.context_filters.Operator = available(scenario.context_filters.Operator, filterOperators);
          if (!scenario.context_filters.Operator.length) delete scenario.context_filters.Operator;
        }
        Object.values(scenario.scorings || {}).forEach((options) => {
          if (options && typeof options === 'object') completeOptions(options);
          // (Configurations saved before chose the operators of their GAP Analysis: the Operator Maps choose them now.)
          if (options?.gap) delete options.gap.operators;
        });
      });
      return config;
    };
    return {list, sorted, configuration};
  }

  // Opens the editor. Resolves with {configuration, action} or null when cancelled.
  function open({configuration, context: rawContext = {}, actions = [['apply', 'Apply']], title = 'Scoring report'} = {}) {
    return new Promise((resolve) => {
      const operators = operatorCanonicalizer(rawContext.operatorGroups || []);
      const context = {
        ...rawContext,
        operators: operators.sorted(rawContext.operators || []),
        defaults: rawContext.defaults && {...rawContext.defaults, operators: operators.sorted(rawContext.defaults.operators || [])},
        filterOptions: {...(rawContext.filterOptions || {}),
          ...(rawContext.filterOptions?.Operator ? {Operator: operators.sorted(rawContext.filterOptions.Operator)} : {})},
      };
      const knownOperators = {filterOperators: context.filterOptions.Operator || []};
      const state = operators.configuration(clone(configuration || defaultConfiguration(context.defaults)), knownOperators);
      // The configuration it was chosen from, shown in the selector when the editor opens.
      const openedName = String(state.name || '');
      delete state.name;
      // The colour theme of the document: the one of the configuration, else the one chosen on the page.
      const themes = Array.isArray(context.themes) ? context.themes : [];
      const knownTheme = (id) => themes.some((theme) => theme.id === id);
      state.theme = knownTheme(state.theme) ? state.theme : knownTheme(context.theme) ? context.theme : 'netcheck';
      if (context.pageScope) {
        // From the Scoring & GAP Analysis page the report is one scenario with the Calculation panel and the theme of the
        // page: the editor only chooses its content.
        state.scenarios = state.scenarios.slice(0, 1);
        if (knownTheme(context.theme)) state.theme = context.theme;
      }
      // Every operator in the panels that export the Focus operators (configurations saved before: no).
      state.all_operators = Boolean(state.all_operators);
      const dialog = el('dialog', 'scoring-report-dialog');
      const header = el('div', 'scoring-report-header');
      const allOperators = checkbox('Export All Operators in Focus panels', state.all_operators,
        (checked) => { state.all_operators = checked; },
        'Show every operator in the panels that export the Focus operators of the Operator Maps (Workspace Config > Scoring Export Panels)');
      allOperators.classList.add('scoring-report-flag');
      const syncAllOperators = () => { allOperators.querySelector('input').checked = state.all_operators; };
      header.append(el('h2', '', title), allOperators);
      const toolbar = el('div', 'scoring-report-toolbar');
      const saved = el('select');
      saved.setAttribute('aria-label', 'Saved report configurations');
      const status = el('p', 'scoring-report-status');
      const setStatus = (text, tone = '') => { status.textContent = text; status.dataset.tone = tone; };
      let savedConfigurations = [];
      // The Default configuration is always listed after the placeholder and before the saved ones.
      const DEFAULT_NAME = 'Default';
      const DEFAULT_VALUE = '__default__';
      // The selector shows the saved configuration (or Default) whose scenarios are the ones shown, or
      // <Not saved configuration> when none is; lastChosen is the one last loaded or saved (Save as… proposes it).
      let current = '';
      let lastChosen = openedName.toLocaleLowerCase() === DEFAULT_NAME.toLocaleLowerCase() ? '' : openedName;
      // Key order does not matter when comparing configurations.
      const canonical = (value) => JSON.stringify(value, (_key, item) => (item && typeof item === 'object' && !Array.isArray(item)
        ? Object.fromEntries(Object.entries(item).sort(([left], [right]) => left.localeCompare(right))) : item));
      const matchingConfiguration = () => {
        const opened = canonical(state.scenarios);
        const match = savedConfigurations.find((item) => canonical(
          operators.configuration(clone(item.configuration), knownOperators).scenarios) === opened);
        if (match) return match.name;
        return canonical(operators.configuration(defaultConfiguration(context.defaults), knownOperators).scenarios) === opened
          ? DEFAULT_VALUE : '';
      };
      // Scenarios that no saved configuration (nor Default) has are unsaved changes.
      const hasUnsavedChanges = () => !matchingConfiguration();
      // Only admins, super-admins and the user who saved a configuration delete it: Delete is locked for the others.
      let deleteButton = null;
      const syncDelete = () => {
        if (!deleteButton) return;
        const item = savedConfigurations.find((entry) => entry.name === current);
        const deletable = !item || (window.canDeleteShared?.(item.created_by) ?? true);
        deleteButton.disabled = !deletable;
        deleteButton.title = deletable ? 'Delete the chosen saved configuration' : window.sharedDeleteRefusal('report configuration');
      };
      const syncSelector = () => {
        current = matchingConfiguration();
        saved.value = current;
        syncDelete();
      };
      const refreshSaved = (payload) => {
        savedConfigurations = payload?.configurations || [];
        saved.replaceChildren(el('option', '', '<Not saved configuration>'));
        saved.firstChild.value = '';
        const defaultOption = el('option', '', DEFAULT_NAME);
        defaultOption.value = DEFAULT_VALUE;
        saved.append(defaultOption);
        for (const item of savedConfigurations) {
          const option = el('option', '', item.name);
          option.value = item.name;
          saved.append(option);
        }
        syncSelector();
      };
      const button = (text, handler, kind, titleText = '') => {
        const node = el('button', `ghost-link scoring-report-tool is-${kind}`);
        node.insertAdjacentHTML('beforeend', `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${TOOL_ICONS[kind]}</svg>`);
        node.append(el('span', '', text));
        node.type = 'button';
        if (titleText) node.title = titleText;
        node.addEventListener('click', handler);
        toolbar.append(node);
        return node;
      };
      toolbar.append(saved);
      if (themes.length) {
        const themeLabel = el('label', 'scoring-report-theme', 'Theme ');
        themeLabel.title = 'The colours of the charts and tables of the document';
        const themeSelect = el('select');
        themeSelect.setAttribute('aria-label', 'Colour theme of the report');
        for (const theme of themes) {
          const option = el('option', '', theme.label);
          option.value = theme.id;
          option.title = theme.description || '';
          themeSelect.append(option);
        }
        themeSelect.value = state.theme;
        themeSelect.addEventListener('change', () => { state.theme = themeSelect.value; });
        themeLabel.append(themeSelect);
        toolbar.append(themeLabel);
        state.syncTheme = () => { themeSelect.value = state.theme; };
      }
      // Choosing a configuration in the selector loads it (Default included).
      const load = (value) => {
        if (value === DEFAULT_VALUE) {
          state.scenarios = defaultConfiguration(context.defaults).scenarios;
          state.theme = knownTheme(context.theme) ? context.theme : 'netcheck';
          state.all_operators = false;
          setStatus('Default configuration: one scenario with the calculation filters and Split by levels.', 'success');
        } else {
          const item = savedConfigurations.find((entry) => entry.name === value);
          if (!item) return;
          state.scenarios = operators.configuration(clone(item.configuration), knownOperators).scenarios;
          state.theme = knownTheme(item.configuration?.theme) ? item.configuration.theme : 'netcheck';
          state.all_operators = Boolean(item.configuration?.all_operators);
          setStatus(`Loaded “${item.name}”.`, 'success');
        }
        state.syncTheme?.();
        syncAllOperators();
        render();
        lastChosen = value === DEFAULT_VALUE ? '' : value;
        syncSelector();
      };
      const saveAs = async () => {
        const proposed = (current !== DEFAULT_VALUE && current) || lastChosen || state.scenarios[0]?.name || '';
        const name = await ask(dialog, {
          title: 'Save report configuration', value: proposed,
          copy: 'Name of the configuration in this workspace. Saving with the name of a saved configuration replaces it.',
        });
        if (!name) return false;
        if (name.toLocaleLowerCase() === DEFAULT_NAME.toLocaleLowerCase()) {
          setStatus('“Default” is the name of the default configuration: choose another name.', 'error');
          return false;
        }
        try {
          const payload = await api('/api/scoring/report-configurations', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name: name.trim(), configuration: {scenarios: state.scenarios, theme: state.theme,
              all_operators: state.all_operators}}),
          });
          lastChosen = name.trim();
          refreshSaved(payload);
          setStatus(`Saved “${name.trim()}”.`, 'success');
          return true;
        } catch (error) {
          setStatus(error.message, 'error');
          return false;
        }
      };
      saved.addEventListener('change', async () => {
        const wanted = saved.value;
        saved.value = current;
        if (!wanted || wanted === current) return;
        if (hasUnsavedChanges()) {
          const choice = await choose(dialog, {
            title: 'Unsaved changes',
            copy: 'The scenarios have changes that are not saved. Save them before loading another configuration, or discard them?',
            choices: [['cancel', 'Cancel'], ['discard', 'Discard changes', 'danger-button'], ['save', 'Save as…', 'primary-button']],
          });
          if (choice === 'save') { if (!await saveAs()) return; } else if (choice !== 'discard') return;
        }
        load(wanted);
      });
      button('Save as…', saveAs, 'save', 'Save these scenarios with a name in the workspace');
      deleteButton = button('Delete', async () => {
        if (!current) { setStatus('Choose a saved configuration to delete.', 'error'); return; }
        if (current === DEFAULT_VALUE) { setStatus('The Default configuration cannot be deleted.', 'error'); return; }
        if (!await ask(dialog, {title: 'Delete report configuration', copy: `Delete the saved report configuration “${current}”?`,
          confirmLabel: 'Delete', danger: true})) return;
        try {
          refreshSaved(await api(`/api/scoring/report-configurations?name=${encodeURIComponent(current)}`, {method: 'DELETE'}));
          setStatus('Configuration deleted.', 'success');
        } catch (error) { setStatus(error.message, 'error'); }
      }, 'delete', 'Delete the chosen saved configuration');
      syncDelete();
      button('Export JSON', () => { window.location.href = '/api/scoring/report-configurations/export'; }, 'export',
        'Download every saved report configuration');
      const importInput = el('input');
      importInput.type = 'file';
      importInput.accept = 'application/json,.json';
      importInput.hidden = true;
      importInput.addEventListener('change', async () => {
        const file = importInput.files?.[0];
        if (!file) return;
        const form = new FormData();
        form.append('package', file);
        try {
          refreshSaved(await api('/api/scoring/report-configurations/import', {method: 'POST', body: form}));
          setStatus('Report configurations imported.', 'success');
        } catch (error) { setStatus(error.message, 'error'); }
        importInput.value = '';
      });
      toolbar.append(importInput);
      button('Import JSON', () => importInput.click(), 'import', 'Add report configurations from a JSON file');
      // (Without the saved configurations, the theme and the JSON files from the page.)
      if (!context.pageScope) header.append(toolbar);

      const list = el('div', 'scoring-report-scenarios');
      const add = el('button', 'ghost-link scoring-report-add', '+ Add scenario');
      add.type = 'button';
      add.addEventListener('click', () => {
        if (state.scenarios.length >= 20) return;
        state.scenarios.push(defaultScenario({...context.defaults, name: `Scenario ${state.scenarios.length + 1}`}));
        render();
        list.lastElementChild?.scrollIntoView({block: 'nearest'});
      });
      const footer = el('div', 'scoring-report-footer');
      const close = (result) => { dialog.close(); dialog.remove(); resolve(result); };
      const cancel = el('button', 'ghost-link', 'Cancel');
      cancel.type = 'button';
      cancel.addEventListener('click', () => close(null));
      footer.append(status, cancel);
      for (const [action, text] of actions) {
        const node = actionButton(action, text);
        node.type = 'button';
        node.addEventListener('click', () => {
          if (!state.scenarios.some((scenario) => SCORINGS.some(([key]) => scenario.scorings[key].enabled))) {
            setStatus('Include the Best Network or the Most Reliable Network scoring in at least one scenario.', 'error');
            return;
          }
          state.scenarios.forEach((scenario, index) => { scenario.name = scenario.name.trim() || `Scenario ${index + 1}`; });
          // The chosen configuration's name is kept while its scenarios have no unsaved changes.
          const match = matchingConfiguration();
          const chosenName = match === DEFAULT_VALUE ? DEFAULT_NAME : match;
          const {syncTheme: _syncTheme, ...chosen} = state;
          close({configuration: {...clone(chosen), ...(chosenName ? {name: chosenName} : {})}, action});
        });
        footer.append(node);
      }
      function render() {
        list.replaceChildren(...state.scenarios.map((_scenario, index) => scenarioCard(state, index, context, render)));
        add.disabled = state.scenarios.length >= 20;
        markDifferences(list, state.scenarios);
        syncSelector();
      }
      // Settings change without rendering again (checkboxes, selects, names, Select All / None): refresh the
      // highlights and the configuration the selector shows.
      const refreshDifferences = () => queueMicrotask(() => { markDifferences(list, state.scenarios); syncSelector(); });
      list.addEventListener('change', refreshDifferences);
      list.addEventListener('click', refreshDifferences);
      list.addEventListener('input', refreshDifferences);
      render();
      dialog.append(header, list, ...(context.pageScope ? [] : [add]), footer);
      dialog.addEventListener('cancel', (event) => { event.preventDefault(); close(null); });
      document.body.append(dialog);
      dialog.showModal();
      refreshSaved(null);
      api('/api/scoring/report-configurations').then(refreshSaved).catch(() => {});
      // Only the panels the workspace exports.
      api('/api/scoring/export-panels').then((payload) => {
        exportPanels = payload?.panels || null;
        if (dialog.isConnected) render();
      }).catch(() => {});
    });
  }

  window.ScoringReportEditor = {open, defaultConfiguration, defaultScenario, defaultOptions};
})();
