/* The Dashboard Designer (ticket #26): the Design mode of the PPT Dashboard viewer.

   In Design the slides at the left are the slides of the Design (hidden and optional ones included), the elements of the
   slide shown can be chosen, moved between the places of its layout and changed in the panel at the right, and every
   change is laid out at once by the server on the CDRs the Dashboard already prepared (POST /design/preview). Changes go
   to the template (Template scope: every Dashboard that follows it) or to this Dashboard only (This Dashboard scope:
   kept as its differences from the template, see dashboard_design.py). Nothing is stored until Save. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const viewer = () => window.dashboardViewer;
  const api = (path, method = 'GET', body) => viewer().api(path, method, body);
  const clone = value => (value === undefined ? undefined : structuredClone(value));
  const h = (tag, props = {}, ...children) => {
    const element = document.createElement(tag);
    for (const [key, value] of Object.entries(props || {})) {
      if (value === undefined || value === null || value === false) continue;
      if (key === 'class') element.className = value;
      else if (key === 'text') element.textContent = value;
      else if (key === 'dataset') Object.assign(element.dataset, value);
      else if (key === 'style') Object.assign(element.style, value);
      else if (key.startsWith('on') && typeof value === 'function') element.addEventListener(key.slice(2), value);
      else if (typeof value === 'boolean') element.toggleAttribute(key, value);
      else element.setAttribute(key, value);
    }
    element.append(...children.flat().filter(child => child !== null && child !== undefined && child !== false));
    return element;
  };
  const randomId = prefix => `${prefix}${(crypto.randomUUID?.() || `${Date.now()}${Math.random()}`).replace(/[^a-f0-9]/gi, '').slice(0, 10)}`;
  const report = error => {
    if (error?.name === 'AbortError') return;
    viewer()?.status?.(error.message);
    window.showInfoDialog?.(error.message, {title: 'Dashboard Designer', tone: 'error'});
  };
  const guarded = fn => async (...args) => { try { return await fn(...args); } catch (error) { report(error); return undefined; } };

  const SOURCES = [['CDR-Data', 'Data'], ['CDR-Voice', 'Voice'], ['CDR-Speech', 'Speech'], ['CDR-All', 'RF All']];
  const CHART_TYPES = [
    '100% Stacked Vertical Bars', 'Count Stacked Horizontal Bars', 'Distribution Stacked Vertical Bars',
    'Threshold Stacked Vertical Bars', 'Average Vertical Bars', 'Median Vertical Bars', 'CDF Line', 'Multi KPI CDF Lines',
    'Histogram Line', 'Histogram Bars', 'Scatter', 'Table', 'Dynamic Table', 'Map',
  ];
  const LEGEND_POSITIONS = [['', 'Default (Top)'], ['top', 'Top'], ['bottom', 'Bottom'], ['left', 'Left'], ['right', 'Right']];
  const LABEL_POSITIONS = [['', 'Default'], ['none', 'None'], ['top', 'Top'], ['up', 'Up'], ['middle', 'Middle'], ['down', 'Down']];
  const STRUCTURAL = {title: 'Title Slide', transition: 'Transition Slide', end: 'End Slide'};
  const STRUCTURAL_LAYOUTS = {title: 'Title Page', transition: 'Transition', end: 'Black logo end slide'};
  const BUILT_IN_TOKENS = ['{NR Mode}', '{NR Mode Name}'];
  const DEFAULT_LAYOUT = 'Title + 1 rows + 1 columns + comments down';

  const state = {
    dashboardId: '', info: null, active: false, layouts: null, fields: null,
    template: null, design: null, overrides: null, report: null, summary: null, detached: false,
    rights: {dashboard: false, template: false}, scope: 'dashboard',
    templateDirty: false, dashboardDirty: false, keepTemplateChanges: false,
    history: [], future: [], slide: '', element: '', tab: 'slide',
    queue: Promise.resolve(), busy: 0, clipboard: null, dragSlide: '', dragElement: '',
    // On a phone the panel floats over the slide: folded until a chart is chosen.
    folded: window.matchMedia?.('(max-width: 900px)').matches || false,
  };

  // ------------------------------------------------------------------
  // The Design of the open Dashboard
  // ------------------------------------------------------------------
  const dirty = () => state.templateDirty || state.dashboardDirty || state.keepTemplateChanges;
  const designSlides = () => state.design?.slides || [];
  const templateSlides = () => state.template?.slides || [];
  const findSlide = (design, id) => (design?.slides || []).find(slide => slide.id === id) || null;
  const findElement = (design, id) => {
    for (const slide of design?.slides || []) {
      const element = (slide.elements || []).find(item => item.id === id);
      if (element) return {slide, element};
    }
    return null;
  };
  const shownSlide = () => findSlide(state.design, state.slide);
  const shownElement = () => findElement(state.design, state.element)?.element || null;
  const slideKind = slide => slide?.kind || 'content';
  const isTemplateSlide = slide => Boolean(slide) && slide.origin === 'template' && Boolean(findSlide(state.template, slide.id));
  const isLocalElement = element => element?.origin === 'dashboard';
  const layoutOf = name => (state.layouts || []).find(layout => layout.name === name) || null;
  const placesOf = slide => layoutOf(slide?.layout)?.places || [];
  const placeOf = (element, index) => (Number.isInteger(element.place) ? element.place : index);
  const visibleElements = slide => (slide?.elements || []).filter(element => !element.hidden);
  const dashboardCount = () => (state.info?.template?.dashboards || []).length;
  const editableDesign = () => (state.scope === 'template' ? state.template : state.design);
  const parameters = () => (state.active ? state.template?.parameters || state.design?.parameters : state.info?.design?.parameters) || [];

  function loadDesign(info) {
    state.info = info;
    state.template = info.template?.design || null;
    state.design = info.design;
    state.overrides = info.overrides;
    state.report = info.report;
    state.summary = info.summary;
    state.detached = Boolean(info.detached);
    state.rights = info.rights || {dashboard: false, template: false};
    state.templateDirty = state.dashboardDirty = state.keepTemplateChanges = false;
    state.history = []; state.future = [];
    if (state.detached || !state.rights.template) state.scope = 'dashboard';
    else if (!state.rights.dashboard) state.scope = 'template';
  }

  async function loadInfo(id) {
    try {
      const info = await api(`/${encodeURIComponent(id)}/design`);
      if (state.dashboardId !== id || state.active) return;
      state.info = info;
    } catch (_error) {
      if (state.dashboardId === id) state.info = null;
    }
    syncDesignButton();
    renderParameterValues();
  }

  // ------------------------------------------------------------------
  // Laying out a Design being edited (the server previews it on the prepared CDRs)
  // ------------------------------------------------------------------
  function preview(body) {
    const run = async () => {
      const token = viewer().state().prepared?.token;
      if (!token) throw new Error('The Dashboard is not prepared yet.');
      setBusy(1);
      try {
        const result = await api('/design/preview', 'POST', {token, dashboard_id: viewer().state().activeId, ...body});
        state.design = result.design;
        state.overrides = result.overrides;
        state.report = result.report;
        state.summary = result.summary;
        if (!findSlide(state.design, state.slide)) state.slide = designSlides()[0]?.id || '';
        if (state.element && !findElement(state.design, state.element)) state.element = '';
        viewer().showDesign(result, {designSlide: state.slide});
        renderDesigner();
        scheduleDraft();
      } finally { setBusy(-1); }
    };
    state.queue = state.queue.catch(() => undefined).then(run);
    state.queue.catch(report);
    return state.queue;
  }
  const previewBody = () => ({
    template_design: state.templateDirty ? state.template : undefined,
    overrides: state.overrides,
  });

  // The unsaved Design is kept on the server as a draft of this user (Dashboard Design Drafts), a moment after each change.
  let draftTimer = 0;
  function scheduleDraft() {
    clearTimeout(draftTimer);
    if (!state.active || !dirty()) return;
    const id = viewer().state().activeId;
    draftTimer = setTimeout(() => {
      if (!state.active || !dirty() || viewer().state().activeId !== id) return;
      api(`/${encodeURIComponent(id)}/design/draft`, 'PUT', {state: {
        template: state.templateDirty ? state.template : null, design: state.design, overrides: state.overrides,
        templateDirty: state.templateDirty, dashboardDirty: state.dashboardDirty, keepTemplateChanges: state.keepTemplateChanges,
        template_updated_at: state.info?.template?.updated_at || '', scope: state.scope, slide: state.slide,
      }}).catch(() => undefined);
    }, 1200);
  }
  const forgetDraft = (id, discarded) => api(`/${encodeURIComponent(id)}/design/draft${discarded ? '?discarded=1' : ''}`, 'DELETE').catch(() => undefined);
  async function offerDraft(id) {
    let result;
    try { result = await api(`/${encodeURIComponent(id)}/design/draft`); } catch (_error) { return false; }
    const draft = result?.draft;
    if (!draft) return false;
    const when = result.updated_at ? new Date(result.updated_at).toLocaleString() : 'before';
    const stale = draft.templateDirty && draft.template_updated_at && draft.template_updated_at !== state.info?.template?.updated_at;
    const choice = await window.showConfirmDialog(
      `You have changes of this Design that were not saved (${when}).${stale ? ' The template changed since: saving them would replace those changes, so the save will ask you to reload first.' : ''}`,
      {title: 'Unsaved Design', confirmLabel: 'Restore', cancelLabel: 'Discard them'});
    if (choice !== true && choice !== 'confirm') { await forgetDraft(id, true); return false; }
    state.history.push(snapshotState());
    if (draft.templateDirty && draft.template) { state.template = draft.template; state.templateDirty = true; state.info.template.updated_at = draft.template_updated_at || state.info.template.updated_at; }
    if (draft.design) state.design = draft.design;
    if (draft.overrides) state.overrides = draft.overrides;
    state.dashboardDirty = Boolean(draft.dashboardDirty);
    state.keepTemplateChanges = Boolean(draft.keepTemplateChanges);
    if (draft.scope && (draft.scope === 'dashboard' ? state.rights.dashboard : state.rights.template && !state.detached)) state.scope = draft.scope;
    if (draft.slide && findSlide(state.design, draft.slide)) state.slide = draft.slide;
    return true;
  }

  const snapshotState = () => ({
    template: clone(state.template), design: clone(state.design), overrides: clone(state.overrides),
    templateDirty: state.templateDirty, dashboardDirty: state.dashboardDirty, keepTemplateChanges: state.keepTemplateChanges,
    slide: state.slide, element: state.element,
  });
  function restoreState(saved) {
    Object.assign(state, {
      template: saved.template, design: saved.design, overrides: saved.overrides, templateDirty: saved.templateDirty,
      dashboardDirty: saved.dashboardDirty, keepTemplateChanges: saved.keepTemplateChanges, slide: saved.slide, element: saved.element,
    });
  }

  // One change of the Design, in the scope chosen: ``mutate`` changes the Design given (the template, or the Design of
  // this Dashboard) and returns false to give up. Changes wait for the one before to be laid out.
  async function edit(mutate, {slide, element, scope} = {}) {
    await state.queue.catch(() => undefined);
    const target = scope || state.scope;
    const before = snapshotState();
    const design = clone(target === 'template' ? state.template : state.design);
    if (!design || mutate(design, target) === false) return;
    if (target === 'template') { state.template = design; state.templateDirty = true; }
    else { state.design = design; state.dashboardDirty = true; }
    state.history.push(before);
    if (state.history.length > 80) state.history.shift();
    state.future = [];
    if (slide !== undefined) state.slide = slide;
    if (element !== undefined) state.element = element;
    renderDesigner();
    try {
      await preview(target === 'template' ? previewBody() : {...previewBody(), design: state.design});
    } catch (_error) {
      // Refused (reported by preview): the Design goes back to what it was.
      state.history.pop();
      restoreState(before);
      renderDesigner();
    }
  }

  async function undo() {
    await state.queue.catch(() => undefined);
    const previous = state.history.pop();
    if (!previous) return;
    state.future.push(snapshotState());
    restoreState(previous);
    await preview(previewBody());
  }
  async function redo() {
    await state.queue.catch(() => undefined);
    const next = state.future.pop();
    if (!next) return;
    state.history.push(snapshotState());
    restoreState(next);
    await preview(previewBody());
  }

  // ------------------------------------------------------------------
  // Entering, saving and leaving Design
  // ------------------------------------------------------------------
  async function enterDesign() {
    const {activeId, prepared} = viewer().state();
    if (!activeId) return;
    if (!prepared?.token) throw new Error('Wait until the Dashboard is ready, then open Design.');
    setBusy(1);
    try {
      const [info, layouts] = await Promise.all([
        api(`/${encodeURIComponent(activeId)}/design?edit=1`),
        state.layouts ? Promise.resolve({layouts: state.layouts}) : api('/design/layouts'),
      ]);
      state.layouts = layouts.layouts;
      loadDesign(info);
    } finally { setBusy(-1); }
    if (!state.rights.dashboard && !state.rights.template) throw new Error('You cannot change the Design of this Dashboard or of its template.');
    state.active = true;
    state.slide = prepared.slides?.[viewer().state().slideIndex]?.design_slide || designSlides()[0]?.id || '';
    state.element = '';
    state.tab = 'slide';
    $('ds-viewer').classList.add('ds-designing');
    $('ds-design-bar').hidden = false;
    $('ds-design-panel').hidden = false;
    renderDesigner();
    loadFields(prepared.token);
    const restored = await offerDraft(activeId);
    // Laid out again with the ids of the Design (and the draft restored), so each element on the slide is known.
    await preview(restored && state.dashboardDirty ? {...previewBody(), design: state.design} : previewBody());
    viewer().status('Design: changes are laid out at once and stored when you save them.');
  }

  async function loadFields(token) {
    try { state.fields = await api(`/design/fields?token=${encodeURIComponent(token)}`); }
    catch (_error) { state.fields = null; }
    if (state.active) renderPanel();
  }

  async function saveDesign() {
    await state.queue.catch(() => undefined);
    if (!dirty()) return;
    clearTimeout(draftTimer);
    const id = viewer().state().activeId;
    if (state.templateDirty) {
      const others = (state.info.template.dashboards || []).filter(item => item.id !== id);
      const message = others.length
        ? `Save the template “${state.info.template.name}”? It also changes ${others.length} other Dashboard${others.length === 1 ? '' : 's'}: ${others.map(item => item.name).join(', ')}.`
        : `Save the template “${state.info.template.name}”?`;
      if (!await window.showConfirmDialog(message, {title: 'Save template', confirmLabel: 'Save'})) return;
    }
    const body = {};
    if (state.templateDirty) Object.assign(body, {template_design: state.template, template_updated_at: state.info.template.updated_at});
    if (state.detached && state.dashboardDirty) body.design = state.design;
    else if (state.dashboardDirty) body.overrides = state.overrides;
    if (state.keepTemplateChanges) Object.assign(body, {keep_template_changes: true, overrides: state.overrides});
    setBusy(1);
    let info;
    try { info = await api(`/${encodeURIComponent(id)}/design`, 'PUT', body); } finally { setBusy(-1); }
    const {slide, element} = state;
    loadDesign(info);
    state.slide = findSlide(state.design, slide) ? slide : designSlides()[0]?.id || '';
    state.element = findElement(state.design, element) ? element : '';
    viewer().storeDesign(id, storedDesignFields(info));
    renderDesigner();
    viewer().status('Design saved.');
  }
  const hasOverrides = overrides => Object.entries(overrides || {}).some(([key, value]) => key !== 'version'
    && (Array.isArray(value) ? value.length : value && typeof value === 'object' && Object.keys(value).length));
  const storedDesignFields = info => ({
    design_overrides: hasOverrides(info.overrides) ? info.overrides : {},
    design: info.detached ? info.design : null,
  });

  async function discardDesign({ask = true} = {}) {
    await state.queue.catch(() => undefined);
    if (ask && dirty() && !await window.showConfirmDialog('Discard the changes of the Design that are not saved?', {title: 'Discard changes', confirmLabel: 'Discard', tone: 'danger'})) return false;
    const id = viewer().state().activeId;
    clearTimeout(draftTimer);
    await forgetDraft(id, true);
    const info = await api(`/${encodeURIComponent(id)}/design?edit=1`);
    loadDesign(info);
    if (!findSlide(state.design, state.slide)) state.slide = designSlides()[0]?.id || '';
    state.element = '';
    await preview(previewBody());
    return true;
  }

  async function exitDesign({force = false} = {}) {
    if (!state.active) return true;
    if (!force && dirty()) {
      const choice = await window.showConfirmDialog('The Design has changes that are not saved.', {
        title: 'Close Design', confirmLabel: 'Save', secondaryLabel: 'Discard', cancelLabel: 'Keep designing',
      });
      if (choice === 'confirm' || choice === true) await saveDesign();
      else if (choice === 'secondary') await discardDesign({ask: false});
      else return false;
      if (dirty()) return false;
    }
    state.active = false;
    state.element = '';
    $('ds-viewer').classList.remove('ds-designing');
    $('ds-design-bar').hidden = true;
    $('ds-design-panel').hidden = true;
    $('ds-design-bar').replaceChildren();
    $('ds-design-panel').replaceChildren();
    closeMenus();
    if (!force) {
      viewer().renderSlide();
      if (state.dashboardId) loadInfo(state.dashboardId);
    }
    return true;
  }

  // ------------------------------------------------------------------
  // Slides
  // ------------------------------------------------------------------
  const newChartElement = (design, place = 0) => {
    const model = shownElement() || designSlides().flatMap(slide => slide.elements || []).find(element => (element.kind || 'chart') === 'chart');
    const element = model ? clone(model) : {
      kind: 'chart', cdr_source: 'CDR-Data', kpi: 'Mean_Data_Rate', chart_type: 'Average Vertical Bars',
      filters: '', rows_split: 'Operator', columns_split: 'Campaign', legend: '', legend_position: '',
      legend_format: '', label_position: '', label_format: '', axis_x_range: '', axis_y_range: '',
      exclude_null_empty: false, exclude_zero: false, dynamic_rows_field: '', dynamic_columns_field: '',
    };
    for (const mark of ['origin', 'overridden', 'hidden', 'style']) delete element[mark];
    return {...element, id: randomId('e'), kind: 'chart', place, chart_title: 'New chart'};
  };
  function newSlide(design, kind) {
    const slide = {
      id: randomId('s'), kind, title: kind === 'end' ? '' : (kind === 'content' ? 'New slide' : 'New section'),
      subtitle: '', layout: kind === 'content' ? DEFAULT_LAYOUT : STRUCTURAL_LAYOUTS[kind], optional: false, elements: [],
    };
    if (kind !== 'content') slide.chart_type = STRUCTURAL[kind];
    else slide.elements.push(newChartElement(design, 0));
    return slide;
  }
  const insertAfter = (design, slideId, slide) => {
    const index = design.slides.findIndex(item => item.id === slideId);
    design.slides.splice(index < 0 ? design.slides.length : index + 1, 0, slide);
  };
  const addSlide = kind => edit(design => {
    const slide = newSlide(design, kind);
    insertAfter(design, state.slide, slide);
    state.slide = slide.id;
    state.element = slide.elements[0]?.id || '';
  });
  const duplicateSlide = slideId => edit(design => {
    const source = findSlide(design, slideId) || findSlide(state.design, slideId);
    if (!source) return false;
    const copy = clone(source);
    for (const mark of ['origin', 'overridden', 'hidden', 'optional_off']) delete copy[mark];
    copy.id = randomId('s');
    copy.title = copy.title ? `${copy.title} (copy)` : copy.title;
    copy.elements = (copy.elements || []).filter(element => !element.hidden).map(element => {
      const item = {...element, id: randomId('e')};
      delete item.origin; delete item.overridden;
      return item;
    });
    insertAfter(design, slideId, copy);
    state.slide = copy.id;
  });
  async function deleteSlide(slideId) {
    const slide = findSlide(editableDesign(), slideId);
    if (!slide) return;
    if (state.scope === 'template') {
      const others = dashboardCount();
      if (!await window.showConfirmDialog(`Delete the slide “${slide.title || STRUCTURAL[slideKind(slide)] || 'slide'}” from the template?${others > 1 ? ` The ${others} Dashboards of the template lose it.` : ''}`, {title: 'Delete slide', confirmLabel: 'Delete', tone: 'danger'})) return;
    }
    await edit(design => {
      const index = design.slides.findIndex(item => item.id === slideId);
      if (index < 0 || design.slides.filter(item => !item.hidden && !item.optional_off).length <= 1) {
        report(new Error('A Dashboard needs at least one slide.'));
        return false;
      }
      design.slides.splice(index, 1);
      state.slide = (design.slides[index] || design.slides[index - 1])?.id || '';
      state.element = '';
    });
  }
  const setSlideHidden = (slideId, hidden) => edit(design => {
    const slide = findSlide(design, slideId);
    if (!slide) return false;
    if (hidden) slide.hidden = true; else delete slide.hidden;
  }, {scope: 'dashboard'});
  const setOptionalShown = (slideId, shown) => edit(design => {
    const slide = findSlide(design, slideId);
    if (!slide) return false;
    if (shown) delete slide.optional_off; else slide.optional_off = true;
  }, {scope: 'dashboard'});
  const setOptional = (slideId, optional) => edit(design => {
    const slide = findSlide(design, slideId);
    if (!slide) return false;
    slide.optional = optional;
  }, {scope: 'template'});
  const moveSlide = (slideId, targetId, after) => edit(design => {
    const index = design.slides.findIndex(item => item.id === slideId);
    if (index < 0 || slideId === targetId) return false;
    const [slide] = design.slides.splice(index, 1);
    const target = design.slides.findIndex(item => item.id === targetId);
    design.slides.splice(target < 0 ? design.slides.length : target + (after ? 1 : 0), 0, slide);
  });
  const canMoveSlide = slide => state.scope === 'template' ? true : !isTemplateSlide(slide) || state.detached;

  // Reset to template: the slide (or element) as the template has it; Apply to template: the template takes it.
  const resetSlide = slideId => edit(design => {
    const original = findSlide(state.template, slideId);
    const index = design.slides.findIndex(item => item.id === slideId);
    if (!original || index < 0) return false;
    const local = (design.slides[index].elements || []).filter(isLocalElement);
    design.slides[index] = {...clone(original), elements: [...clone(original.elements || []), ...local]};
  }, {scope: 'dashboard'});
  const resetElement = elementId => edit(design => {
    const original = findElement(state.template, elementId)?.element;
    const found = findElement(design, elementId);
    if (!original || !found) return false;
    found.slide.elements[found.slide.elements.indexOf(found.element)] = clone(original);
  }, {scope: 'dashboard'});
  async function applyToTemplate({slideId = '', elementId = ''} = {}) {
    if (!state.rights.template) return;
    await state.queue.catch(() => undefined);
    const others = dashboardCount();
    if (!await window.showConfirmDialog(`Make this change part of the template?${others > 1 ? ` The ${others} Dashboards of the template take it.` : ''}`, {title: 'Apply to template', confirmLabel: 'Apply'})) return;
    const before = snapshotState();
    const template = clone(state.template);
    const clean = item => { const copy = clone(item); for (const mark of ['origin', 'overridden', 'hidden', 'optional_off']) delete copy[mark]; return copy; };
    if (slideId) {
      const shown = findSlide(state.design, slideId);
      if (!shown) return;
      const cleaned = {...clean(shown), elements: (shown.elements || []).filter(element => !element.hidden).map(clean)};
      const index = template.slides.findIndex(item => item.id === slideId);
      if (index >= 0) template.slides[index] = {...cleaned, optional: template.slides[index].optional};
      else {
        // A slide of this Dashboard: after the slide before it, as here.
        const order = designSlides().map(item => item.id);
        const previous = order.slice(0, order.indexOf(slideId)).reverse().find(id => template.slides.some(item => item.id === id));
        const at = previous ? template.slides.findIndex(item => item.id === previous) + 1 : 0;
        template.slides.splice(at, 0, cleaned);
      }
    } else if (elementId) {
      const found = findElement(state.design, elementId);
      const target = found && findSlide(template, found.slide.id);
      if (!target) return;
      const index = (target.elements || []).findIndex(item => item.id === elementId);
      if (found.element.hidden) target.elements.splice(index, 1);
      else if (index >= 0) target.elements[index] = clean(found.element);
      else target.elements.push(clean(found.element));
    }
    state.history.push(before);
    state.future = [];
    state.template = template;
    state.templateDirty = true;
    state.dashboardDirty = true;
    await preview({...previewBody(), design: state.design});
  }

  // ------------------------------------------------------------------
  // Elements
  // ------------------------------------------------------------------
  const elementLabel = element => element?.chart_title || element?.kpi || 'Chart';
  function setElementValues(elementId, values) {
    return edit(design => {
      const found = findElement(design, elementId);
      if (!found) {
        report(new Error('This element is only in this Dashboard: change it in This Dashboard scope, or apply it to the template first.'));
        return false;
      }
      Object.assign(found.element, values);
    });
  }
  const addElement = (slideId, place) => edit(design => {
    const slide = findSlide(design, slideId);
    if (!slide) return false;
    const element = newChartElement(design, place);
    slide.elements = [...(slide.elements || []), element];
    state.element = element.id;
    state.tab = 'element';
  });
  async function deleteElement(elementId) {
    await edit(design => {
      const found = findElement(design, elementId);
      if (!found) return false;
      if (visibleElements(found.slide).length <= 1) {
        report(new Error('A slide keeps at least one element: delete the slide instead.'));
        return false;
      }
      if (state.scope === 'dashboard' && !state.detached && !isLocalElement(found.element)) found.element.hidden = true;
      else found.slide.elements.splice(found.slide.elements.indexOf(found.element), 1);
      state.element = '';
    });
  }
  const duplicateElement = elementId => edit(design => {
    const found = findElement(design, elementId);
    if (!found) return false;
    const free = freePlaces(found.slide);
    if (!free.length) {
      report(new Error('The layout of this slide has no free place: choose a layout with more places first.'));
      return false;
    }
    const copy = {...clone(found.element), id: randomId('e'), place: free[0]};
    delete copy.origin; delete copy.overridden; delete copy.hidden;
    found.slide.elements.push(copy);
    state.element = copy.id;
  });
  const pasteElement = (slideId, place) => edit(design => {
    const slide = findSlide(design, slideId);
    if (!slide || !state.clipboard) return false;
    const copy = {...clone(state.clipboard), id: randomId('e'), place};
    slide.elements = [...(slide.elements || []), copy];
    state.element = copy.id;
  });
  function freePlaces(slide) {
    const capacity = placesOf(slide).length;
    const used = new Set(visibleElements(slide).map(placeOf));
    return [...Array(capacity).keys()].filter(place => !used.has(place));
  }
  // An element dropped on another place of its slide: on a free place it moves there, on another element they swap.
  const moveElement = (elementId, place) => edit(design => {
    const found = findElement(design, elementId);
    if (!found) return false;
    const elements = visibleElements(found.slide);
    const from = placeOf(found.element, elements.indexOf(found.element));
    if (from === place) return false;
    elements.forEach((element, index) => { element.place = placeOf(element, index); });
    const other = elements.find(element => element.place === place);
    if (other) other.place = from;
    found.element.place = place;
  });

  async function setLayout(slideId, name) {
    const slide = findSlide(editableDesign(), slideId);
    if (!slide || slide.layout === name) return;
    const capacity = layoutOf(name)?.places?.length || 0;
    const elements = visibleElements(slide);
    if (slideKind(slide) === 'content' && capacity && elements.length > capacity) {
      const extra = elements.length - capacity;
      if (!await window.showConfirmDialog(`The layout ${name} has ${capacity} place${capacity === 1 ? '' : 's'}: the last ${extra} element${extra === 1 ? '' : 's'} of the slide will be removed.`, {title: 'Change layout', confirmLabel: 'Change layout', tone: 'danger'})) return;
    }
    await edit(design => {
      const target = findSlide(design, slideId);
      if (!target) return false;
      target.layout = name;
      if (slideKind(target) !== 'content' || !capacity) return undefined;
      const shown = visibleElements(target).map((element, index) => [placeOf(element, index), element]).sort((left, right) => left[0] - right[0]);
      const kept = shown.slice(0, capacity).map(([, element]) => element);
      // The elements kept keep their place when the new layout has it; the others take its free places in order.
      const taken = new Set();
      for (const element of kept) {
        if (Number.isInteger(element.place) && element.place < capacity && !taken.has(element.place)) taken.add(element.place);
        else element.place = null;
      }
      for (const element of kept) {
        if (element.place !== null) continue;
        element.place = [...Array(capacity).keys()].find(place => !taken.has(place));
        taken.add(element.place);
      }
      for (const element of shown.slice(capacity).map(([, item]) => item)) {
        // Left out of the layout: removed, or hidden here when it is an element of the template (This Dashboard).
        if (state.scope === 'dashboard' && !state.detached && !isLocalElement(element)) element.hidden = true;
        else target.elements.splice(target.elements.indexOf(element), 1);
      }
      return undefined;
    });
  }

  // ------------------------------------------------------------------
  // Rendering: bar, slide sorter, stage marks and panel
  // ------------------------------------------------------------------
  function setBusy(change) {
    state.busy = Math.max(0, state.busy + change);
    $('ds-viewer')?.classList.toggle('ds-design-busy', state.busy > 0);
    const indicator = $('ds-design-busy');
    if (indicator) indicator.hidden = state.busy === 0;
  }
  function renderDesigner() {
    if (!state.active) return;
    renderBar();
    renderSorter();
    renderPanel();
    decorateStage();
    renderParameterValues();
  }

  function renderBar() {
    const bar = $('ds-design-bar');
    const scopeButton = (scope, label, title, enabled) => h('button', {
      type: 'button', class: `ds-design-scope${state.scope === scope ? ' is-active' : ''}`, 'aria-pressed': String(state.scope === scope),
      title, disabled: !enabled, onclick: () => { state.scope = scope; renderDesigner(); },
    }, label);
    const count = dashboardCount();
    const differences = Object.values(state.summary || {}).reduce((total, value) => total + Number(value || 0), 0);
    const changed = (state.report?.template_changed || []).length;
    bar.replaceChildren(
      h('div', {class: 'ds-design-bar-group'},
        h('span', {class: 'ds-design-bar-label', text: 'Design'}),
        state.detached
          ? h('span', {class: 'ds-design-pill ds-design-pill-detached', title: `Detached from ${state.info?.template?.name || 'its template'}: it keeps a Design of its own`, text: 'Detached'})
          : h('div', {class: 'ds-design-scopes', role: 'group', 'aria-label': 'Change'},
            scopeButton('dashboard', 'This Dashboard', 'Changes only this Dashboard: kept as its differences from the template', state.rights.dashboard),
            scopeButton('template', `Template · ${count} Dashboard${count === 1 ? '' : 's'}`, `Changes the template ${state.info?.template?.name || ''}: every Dashboard that follows it`, state.rights.template))),
      h('div', {class: 'ds-design-bar-group'},
        h('button', {type: 'button', class: 'ds-design-tool', title: 'Undo (Ctrl/Cmd+Z)', 'aria-label': 'Undo', disabled: !state.history.length, onclick: guarded(undo)}, '↶'),
        h('button', {type: 'button', class: 'ds-design-tool', title: 'Redo (Shift+Ctrl/Cmd+Z)', 'aria-label': 'Redo', disabled: !state.future.length, onclick: guarded(redo)}, '↷'),
        h('button', {type: 'button', class: 'ds-design-action', onclick: guarded(openParametersDialog), disabled: state.detached ? false : !state.rights.template && !parameters().length, title: 'The parameters of the template'}, `Parameters${parameters().length ? ` · ${parameters().length}` : ''}`),
        state.detached ? null : h('button', {type: 'button', class: `ds-design-action${changed ? ' has-warning' : ''}`, onclick: guarded(openDifferencesDialog), title: 'What this Dashboard changes of its template'}, `Differences · ${differences}${changed ? ` · ${changed} template changed` : ''}`)),
      h('div', {class: 'ds-design-bar-group ds-design-bar-end'},
        h('span', {class: 'ds-design-busy', id: 'ds-design-busy', hidden: state.busy === 0, text: 'Laying out…'}),
        dirty() ? h('span', {class: 'ds-design-pill ds-design-pill-unsaved', text: state.templateDirty ? 'Unsaved template' : 'Unsaved'}) : null,
        h('button', {type: 'button', class: 'ds-design-action ds-design-primary', disabled: !dirty(), onclick: guarded(saveDesign)}, 'Save'),
        h('button', {type: 'button', class: 'ds-design-action', disabled: !dirty(), onclick: guarded(() => discardDesign())}, 'Discard'),
        h('button', {type: 'button', class: 'ds-design-action', 'aria-haspopup': 'menu', onclick: event => openMenu(event.currentTarget, moreActions())}, 'More ▾'),
        h('button', {type: 'button', class: 'ds-design-action', onclick: guarded(() => exitDesign())}, 'Close Design')),
    );
  }
  const moreActions = () => [
    ['Save as template…', guarded(saveAsTemplate), !dirty() || 'Save or discard the changes first'],
    ['Save as my Dashboard…', guarded(saveAsMyDashboard), !state.templateDirty || 'Save or discard the changes of the template first'],
    state.detached ? null : ['Detach from template…', guarded(detachDashboard), state.rights.dashboard && (!dirty() || 'Save or discard the changes first')],
  ].filter(Boolean);

  function frameBoxes(slide) {
    const frame = h('span', {class: 'ds-design-slide-frame'});
    if (slideKind(slide) !== 'content') {
      frame.append(h('span', {class: 'ds-design-slide-structural', text: STRUCTURAL[slideKind(slide)] || 'Slide'}));
      return frame;
    }
    const places = placesOf(slide);
    visibleElements(slide).forEach((element, index) => {
      const place = places[placeOf(element, index)];
      if (!place) return;
      const [left, top, width, height] = place;
      frame.append(h('span', {
        class: `ds-design-slide-box${element.overridden?.length ? ' is-changed' : ''}${isLocalElement(element) ? ' is-local' : ''}`,
        style: {left: `${left}%`, top: `${top}%`, width: `${width}%`, height: `${height}%`}, title: elementLabel(element),
      }));
    });
    return frame;
  }
  function slideBadges(slide) {
    const badges = [];
    if (slide.hidden) badges.push(['Hidden here', 'is-hidden']);
    if (slide.optional && slide.optional_off) badges.push(['Optional · off', 'is-hidden']);
    else if (slide.optional) badges.push(['Optional', 'is-optional']);
    if (slide.origin === 'dashboard' && !state.detached) badges.push(['This Dashboard', 'is-local']);
    if (slide.overridden?.length || (slide.elements || []).some(element => element.overridden?.length || element.hidden || isLocalElement(element))) badges.push(['Changed here', 'is-changed']);
    if ((state.report?.template_changed || []).some(item => item.slide === slide.id || (slide.elements || []).some(element => element.id === item.element))) badges.push(['Template changed', 'is-warning']);
    return badges.length ? h('span', {class: 'ds-design-slide-badges'}, badges.map(([text, kind]) => h('span', {class: `ds-design-badge ${kind}`, text}))) : null;
  }
  function renderSorter() {
    const nav = $('ds-slide-thumbnails');
    if (!nav) return;
    let number = 0;
    const items = designSlides().map(slide => {
      const shown = !slide.hidden && !slide.optional_off;
      if (shown) number += 1;
      const movable = canMoveSlide(slide);
      const item = h('div', {
        class: `ds-design-slide${slide.id === state.slide ? ' is-current' : ''}${shown ? '' : ' is-off'}`, tabindex: '0', role: 'button',
        draggable: movable ? 'true' : 'false', 'aria-current': slide.id === state.slide ? 'true' : null,
        dataset: {slideId: slide.id}, title: slide.title || STRUCTURAL[slideKind(slide)] || 'Slide',
        onclick: () => selectSlide(slide.id),
        onkeydown: event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); selectSlide(slide.id); } },
        oncontextmenu: event => { event.preventDefault(); openMenu(event.currentTarget, slideActions(slide), event); },
      },
      frameBoxes(slide),
      h('span', {class: 'ds-design-slide-caption'}, h('b', {text: shown ? String(number) : '–'}), slide.title || STRUCTURAL[slideKind(slide)] || 'Slide'),
      slideBadges(slide),
      h('button', {type: 'button', class: 'ds-design-slide-menu', 'aria-label': `Actions of the slide ${slide.title || ''}`, 'aria-haspopup': 'menu',
        onclick: event => { event.stopPropagation(); openMenu(event.currentTarget, slideActions(slide)); }}, '⋯'));
      item.addEventListener('dragstart', event => { state.dragSlide = slide.id; event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/plain', slide.id); item.classList.add('is-dragging'); });
      item.addEventListener('dragend', () => { state.dragSlide = ''; item.classList.remove('is-dragging'); nav.querySelectorAll('.is-drop-before, .is-drop-after').forEach(node => node.classList.remove('is-drop-before', 'is-drop-after')); });
      item.addEventListener('dragover', event => {
        if (!state.dragSlide || state.dragSlide === slide.id) return;
        event.preventDefault();
        const after = event.offsetY > item.offsetHeight / 2;
        item.classList.toggle('is-drop-after', after);
        item.classList.toggle('is-drop-before', !after);
      });
      item.addEventListener('dragleave', () => item.classList.remove('is-drop-before', 'is-drop-after'));
      item.addEventListener('drop', event => {
        if (!state.dragSlide) return;
        event.preventDefault();
        const after = item.classList.contains('is-drop-after');
        item.classList.remove('is-drop-before', 'is-drop-after');
        guarded(() => moveSlide(state.dragSlide, slide.id, after))();
      });
      return item;
    });
    const add = h('button', {type: 'button', class: 'ds-design-add-slide', 'aria-haspopup': 'menu',
      onclick: event => openMenu(event.currentTarget, [
        ['Content slide', guarded(() => addSlide('content')), true],
        ['Title slide', guarded(() => addSlide('title')), true],
        ['Transition slide', guarded(() => addSlide('transition')), true],
        ['End slide', guarded(() => addSlide('end')), true],
      ])}, '+ New slide');
    nav.replaceChildren(...items, add);
    nav.querySelector('.is-current')?.scrollIntoView?.({block: 'nearest'});
  }
  function slideActions(slide) {
    const template = state.scope === 'template';
    const fromTemplate = isTemplateSlide(slide) && !state.detached;
    const actions = [
      ['New slide after', guarded(() => { state.slide = slide.id; return addSlide('content'); }), true],
      ['Duplicate', guarded(() => duplicateSlide(slide.id)), true],
    ];
    if (template) {
      actions.push([slide.optional ? 'Not optional' : 'Optional (off by default)', guarded(() => setOptional(slide.id, !slide.optional)), Boolean(findSlide(state.template, slide.id))]);
      actions.push(['Delete', guarded(() => deleteSlide(slide.id)), Boolean(findSlide(state.template, slide.id)) || 'Only in this Dashboard: delete it in This Dashboard scope']);
    } else if (fromTemplate) {
      if (slide.optional) actions.push([slide.optional_off ? 'Show in this Dashboard' : 'Leave out of this Dashboard', guarded(() => setOptionalShown(slide.id, Boolean(slide.optional_off))), true]);
      else actions.push([slide.hidden ? 'Show again' : 'Hide in this Dashboard', guarded(() => setSlideHidden(slide.id, !slide.hidden)), true]);
      if (slide.overridden?.length || (slide.elements || []).some(element => element.overridden?.length || element.hidden)) actions.push(['Reset to template', guarded(() => resetSlide(slide.id)), true]);
    } else actions.push(['Delete', guarded(() => deleteSlide(slide.id)), true]);
    if (!template && !state.detached && state.rights.template && (slide.origin === 'dashboard' || slide.overridden?.length || (slide.elements || []).some(element => element.overridden?.length || element.hidden || isLocalElement(element)))) {
      actions.push(['Apply to template', guarded(() => applyToTemplate({slideId: slide.id})), true]);
    }
    return actions;
  }

  function selectSlide(slideId) {
    state.slide = slideId;
    state.element = '';
    state.tab = 'slide';
    const index = (viewer().state().prepared?.slides || []).findIndex(slide => slide.design_slide === slideId);
    if (index >= 0 && !(findSlide(state.design, slideId)?.hidden || findSlide(state.design, slideId)?.optional_off)) viewer().goToSlide(index);
    else showLeftOutSlide();
    renderDesigner();
  }
  // A slide the Dashboard leaves out (hidden, or optional and off) is not laid out: the stage says so.
  function showLeftOutSlide() {
    const slide = shownSlide();
    const stage = $('ds-charts');
    if (!slide || !stage) return;
    stage.classList.remove('ds-positioned');
    $('ds-title').textContent = slide.title || STRUCTURAL[slideKind(slide)] || '';
    $('ds-subtitle').textContent = slide.subtitle || '';
    const notice = h('div', {class: 'ds-design-left-out'},
      h('p', {text: slide.hidden ? 'This slide of the template is hidden in this Dashboard.' : 'This optional slide of the template is off in this Dashboard.'}),
      h('button', {type: 'button', class: 'ds-design-action ds-design-primary',
        onclick: guarded(() => (slide.hidden ? setSlideHidden(slide.id, false) : setOptionalShown(slide.id, true)))}, slide.hidden ? 'Show again' : 'Show in this Dashboard'));
    stage.replaceChildren(notice);
  }

  // The slide shown: each element can be chosen and dragged to another place; the free places of its layout take a new one.
  function decorateStage() {
    if (!state.active) return;
    const stage = $('ds-charts');
    const rendered = viewer().state().prepared?.slides?.[viewer().state().slideIndex];
    if (!stage || !rendered) return;
    if (rendered.design_slide && rendered.design_slide !== state.slide) {
      const slide = findSlide(state.design, rendered.design_slide);
      if (slide && !slide.hidden && !slide.optional_off) state.slide = rendered.design_slide;
    }
    const slide = shownSlide();
    if (slide && (slide.hidden || slide.optional_off)) return;
    stage.querySelectorAll('.ds-design-free-place, .ds-design-mark').forEach(node => node.remove());
    const dynamic = new Set();
    stage.querySelectorAll('.ds-chart').forEach(card => {
      const id = card.dataset.elementId;
      if (!id) return;
      if (dynamic.has(id)) card.dataset.repeated = 'true';
      dynamic.add(id);
      const found = findElement(state.design, id);
      card.classList.add('ds-design-card');
      card.classList.toggle('is-selected', id === state.element);
      if (!card.dataset.repeated && !card.querySelector('.ds-design-drag')) {
        const handle = h('span', {class: 'ds-design-drag', draggable: 'true', title: 'Drag to another place of the slide', 'aria-hidden': 'true'}, '⠿');
        handle.addEventListener('dragstart', event => {
          state.dragElement = card.dataset.elementId;
          event.dataTransfer.effectAllowed = 'move';
          event.dataTransfer.setData('text/plain', state.dragElement);
          card.classList.add('is-dragging');
        });
        handle.addEventListener('dragend', () => { state.dragElement = ''; card.classList.remove('is-dragging'); });
        card.append(handle);
      }
      if (!card.dataset.designBound) {
        card.dataset.designBound = 'true';
        card.addEventListener('click', event => {
          if (!state.active || event.target.closest('button, a, input, select, .ds-legend-menu')) return;
          selectElement(card.dataset.elementId);
        });
        // The series of the chart chosen are listed in its Format once it is drawn.
        card.querySelector('canvas')?.addEventListener('dashboardchartlayout', () => {
          if (state.active && card.dataset.elementId === state.element && $('ds-design-panel')?.querySelector('.ds-design-series-list .ds-design-empty')) renderPanel();
        });
        // A click on an entry of the legend of the chart chosen formats that series (instead of hiding it).
        card.addEventListener('click', event => {
          if (!state.active || card.dataset.elementId !== state.element || event.target.tagName !== 'CANVAS') return;
          const item = globalThis.getDashboardChartLegendItemAt?.(event.target, event);
          if (!item) return;
          event.preventDefault();
          event.stopPropagation();
          openSeriesFormat(card, card.dataset.elementId, item.label, event);
        }, true);
        card.addEventListener('contextmenu', event => {
          if (!state.active) return;
          event.preventDefault();
          selectElement(card.dataset.elementId);
          openMenu(card, elementActions(card.dataset.elementId), event);
        });
        card.addEventListener('dragover', event => { if (state.active && state.dragElement && state.dragElement !== card.dataset.elementId) { event.preventDefault(); card.classList.add('is-drop-target'); } });
        card.addEventListener('dragleave', () => card.classList.remove('is-drop-target'));
        card.addEventListener('drop', event => {
          card.classList.remove('is-drop-target');
          if (!state.active || !state.dragElement) return;
          event.preventDefault();
          const target = findElement(state.design, card.dataset.elementId);
          if (!target) return;
          const index = visibleElements(target.slide).indexOf(target.element);
          guarded(() => moveElement(state.dragElement, placeOf(target.element, index)))();
        });
      }
      if (!found) return;
      const marks = [];
      if (isLocalElement(found.element) && !state.detached) marks.push(['This Dashboard', 'is-local']);
      else if (found.element.overridden?.length) marks.push(['Changed here', 'is-changed']);
      if ((state.report?.template_changed || []).some(item => item.element === id)) marks.push(['Template changed', 'is-warning']);
      if (marks.length) card.append(h('span', {class: 'ds-design-mark'}, marks.map(([text, kind]) => h('span', {class: `ds-design-badge ${kind}`, text}))));
    });
    if (!slide || slideKind(slide) !== 'content' || stage.querySelector('[data-repeated]') || !stage.classList.contains('ds-positioned')) return;
    const places = placesOf(slide);
    for (const place of freePlaces(slide)) {
      const [left, top, width, height] = places[place];
      const free = h('div', {class: 'ds-design-free-place', style: {left: `${left}%`, top: `${top}%`, width: `${width}%`, height: `${height}%`}},
        h('button', {type: 'button', class: 'ds-design-add-element', 'aria-haspopup': 'menu', onclick: event => openMenu(event.currentTarget, [
          ['Chart', guarded(() => addElement(slide.id, place)), true],
          ['Paste', guarded(() => pasteElement(slide.id, place)), Boolean(state.clipboard) || 'Copy an element first'],
        ])}, '+ Add'));
      free.addEventListener('dragover', event => { if (state.dragElement) { event.preventDefault(); free.classList.add('is-drop-target'); } });
      free.addEventListener('dragleave', () => free.classList.remove('is-drop-target'));
      free.addEventListener('drop', event => {
        free.classList.remove('is-drop-target');
        if (!state.dragElement) return;
        event.preventDefault();
        guarded(() => moveElement(state.dragElement, place))();
      });
      stage.append(free);
    }
  }
  function selectElement(elementId) {
    if (!findElement(state.design, elementId)) return;
    state.element = elementId;
    state.tab = 'element';
    state.folded = false;
    renderPanel();
    $('ds-charts')?.querySelectorAll('.ds-chart').forEach(card => card.classList.toggle('is-selected', card.dataset.elementId === elementId));
  }
  function elementActions(elementId) {
    const found = findElement(state.design, elementId);
    if (!found) return [];
    const template = state.scope === 'template';
    const actions = [
      ['Duplicate', guarded(() => duplicateElement(elementId)), true],
      ['Copy', () => { state.clipboard = clone(found.element); viewer().status('Element copied: paste it on a free place.'); }, true],
      ['Delete', guarded(() => deleteElement(elementId)), true],
    ];
    if (!template && !state.detached && !isLocalElement(found.element) && found.element.overridden?.length) actions.push(['Reset to template', guarded(() => resetElement(elementId)), true]);
    if (!template && !state.detached && state.rights.template && (isLocalElement(found.element) || found.element.overridden?.length)) actions.push(['Apply to template', guarded(() => applyToTemplate({elementId})), true]);
    return actions;
  }

  // ------------------------------------------------------------------
  // Panel: the slide or the element chosen
  // ------------------------------------------------------------------
  let inputTimer = 0;
  const debounced = (fn, delay = 650) => (...args) => { clearTimeout(inputTimer); inputTimer = setTimeout(() => guarded(fn)(...args), delay); };
  const field = (label, control, note) => h('label', {class: 'ds-design-field'}, h('span', {class: 'ds-design-field-label', text: label}), control, note ? h('span', {class: 'ds-design-field-note', text: note}) : null);
  const selectInput = (options, value, onchange, id) => {
    const select = h('select', {id, onchange: event => onchange(event.target.value)});
    for (const [optionValue, optionLabel] of options) {
      const option = h('option', {value: optionValue, text: optionLabel});
      option.selected = String(optionValue) === String(value ?? '');
      select.append(option);
    }
    if (![...select.options].some(option => option.selected) && value) {
      const option = h('option', {value, text: value}); option.selected = true; select.append(option);
    }
    return select;
  };
  const textInput = (value, oninput, props = {}) => h(props.multiline ? 'textarea' : 'input', {
    ...(props.multiline ? {rows: props.rows || 3} : {type: 'text'}), id: props.id, list: props.list, placeholder: props.placeholder,
    value: props.multiline ? undefined : value ?? '', oninput: event => oninput(event.target.value), spellcheck: 'false',
  }, props.multiline ? value ?? '' : null);
  function tokenMenuButton(input) {
    return h('button', {type: 'button', class: 'ds-design-token', title: 'Insert a field: NR Mode or a parameter', 'aria-haspopup': 'menu',
      onclick: event => openMenu(event.currentTarget, [...BUILT_IN_TOKENS, ...parameters().map(item => `{${item.name}}`)].map(token => [token, () => {
        const start = input.selectionStart ?? input.value.length, end = input.selectionEnd ?? input.value.length;
        input.value = `${input.value.slice(0, start)}${token}${input.value.slice(end)}`;
        input.dispatchEvent(new Event('input'));
        input.focus();
      }, true]))}, '{ }');
  }
  function fieldsDatalist(element) {
    const source = String(element?.cdr_source || 'CDR-Data').toLocaleLowerCase();
    const columns = [...(state.fields?.columns_by_source?.[source] || []), ...(state.fields?.calculated_fields || [])];
    return h('datalist', {id: 'ds-design-fields'}, [...new Set(columns)].map(column => h('option', {value: column})));
  }

  function renderPanel() {
    const panel = $('ds-design-panel');
    if (!panel || !state.active) return;
    const focused = panel.contains(document.activeElement) && document.activeElement.id ? document.activeElement : null;
    const advancedOpen = Boolean(panel.querySelector('.ds-design-advanced')?.open);
    const dataOpen = new Set([...panel.querySelectorAll('.ds-cb-group')].filter(group => group.open).map(group => group.querySelector('summary')?.firstChild?.textContent));
    const typing = focused && 'value' in focused ? {id: focused.id, value: focused.value, start: focused.selectionStart, end: focused.selectionEnd} : null;
    const slide = shownSlide();
    const element = state.element ? shownElement() : null;
    if (!element && state.tab === 'element') state.tab = 'slide';
    const tabs = h('div', {class: 'ds-design-tabs', role: 'tablist'},
      h('button', {type: 'button', role: 'tab', class: state.tab === 'slide' ? 'is-active' : '', 'aria-selected': String(state.tab === 'slide'), onclick: () => { state.tab = 'slide'; renderPanel(); }}, 'Slide'),
      h('button', {type: 'button', role: 'tab', class: state.tab === 'element' ? 'is-active' : '', 'aria-selected': String(state.tab === 'element'), disabled: !element, onclick: () => { state.tab = 'element'; renderPanel(); }}, 'Element'));
    const body = h('div', {class: 'ds-design-panel-body'});
    if (state.tab === 'element' && element) body.append(...elementForm(element));
    else if (slide) body.append(...slideForm(slide));
    else body.append(h('p', {class: 'ds-design-empty', text: 'Choose a slide.'}));
    const scopeNote = state.detached ? 'This Dashboard has a Design of its own.'
      : state.scope === 'template' ? `Changes the template: ${dashboardCount()} Dashboard${dashboardCount() === 1 ? '' : 's'} follow it.`
        : 'Changes only this Dashboard.';
    const fold = h('button', {type: 'button', class: 'ds-design-fold', 'aria-expanded': String(!state.folded), title: state.folded ? 'Show the panel' : 'Fold the panel',
      onclick: () => { state.folded = !state.folded; renderPanel(); }}, state.folded ? '▴' : '▾');
    panel.classList.toggle('is-folded', state.folded);
    panel.replaceChildren(h('div', {class: 'ds-design-panel-head'}, h('div', {class: 'ds-design-panel-top'}, tabs, fold), h('p', {class: `ds-design-scope-note is-${state.detached ? 'dashboard' : state.scope}`, text: scopeNote})), body);
    if (advancedOpen) { const advanced = panel.querySelector('.ds-design-advanced'); if (advanced) advanced.open = true; }
    if (dataOpen.size) panel.querySelectorAll('.ds-cb-group').forEach(group => { group.open = dataOpen.has(group.querySelector('summary')?.firstChild?.textContent); });
    const again = typing && $(typing.id);
    if (again) {
      if (again.value !== typing.value) again.value = typing.value;
      again.focus({preventScroll: true});
      try { if (typing.start !== null && again.setSelectionRange) again.setSelectionRange(typing.start, typing.end); } catch (_error) { /* not a text field */ }
    }
  }

  function originNote(item, kind) {
    if (state.detached) return null;
    if (item.origin === 'dashboard') return h('p', {class: 'ds-design-origin is-local', text: `This ${kind} is only in this Dashboard.`});
    if (item.overridden?.length) return h('p', {class: 'ds-design-origin is-changed', text: `Changed here: ${item.overridden.join(', ').replaceAll('_', ' ')}.`});
    return h('p', {class: 'ds-design-origin', text: `As the template has it.`});
  }

  function slideForm(slide) {
    const kind = slideKind(slide);
    const editable = state.scope === 'dashboard' || Boolean(findSlide(state.template, slide.id));
    const setSlide = values => edit(design => {
      const target = findSlide(design, slide.id);
      if (!target) { report(new Error('This slide is only in this Dashboard: change it in This Dashboard scope.')); return false; }
      Object.assign(target, values);
    });
    const shownSource = state.scope === 'template' ? findSlide(state.template, slide.id) || slide : slide;
    const title = textInput(shownSource.title, debounced(value => setSlide({title: value})), {id: 'ds-design-slide-title'});
    const subtitle = textInput(shownSource.subtitle, debounced(value => setSlide({subtitle: value})), {id: 'ds-design-slide-subtitle'});
    const nodes = [
      h('h3', {class: 'ds-design-panel-title', text: kind === 'content' ? 'Slide' : STRUCTURAL[kind]}),
      originNote(slide, 'slide'),
      field('Title', h('div', {class: 'ds-design-input-row'}, title, tokenMenuButton(title))),
      field('Subtitle', h('div', {class: 'ds-design-input-row'}, subtitle, tokenMenuButton(subtitle))),
      field('Layout', h('button', {type: 'button', class: 'ds-design-layout-button', disabled: !editable, onclick: event => openLayoutGallery(event.currentTarget, slide)}, shownSource.layout || 'Choose a layout')),
    ];
    if (state.scope === 'template' && findSlide(state.template, slide.id)) {
      nodes.push(h('label', {class: 'ds-design-check'}, h('input', {type: 'checkbox', checked: Boolean(findSlide(state.template, slide.id).optional), onchange: event => guarded(() => setOptional(slide.id, event.target.checked))()}), 'Optional: off in each Dashboard until it is shown there'));
    }
    if (kind === 'content') {
      const elements = visibleElements(slide);
      nodes.push(h('h4', {class: 'ds-design-subtitle', text: `Elements · ${elements.length} of ${placesOf(slide).length || elements.length} places`}));
      nodes.push(h('ul', {class: 'ds-design-element-list'}, elements.map((item, index) => h('li', {},
        h('button', {type: 'button', onclick: () => selectElement(item.id)},
          h('span', {class: 'ds-design-place', text: String(placeOf(item, index) + 1)}), elementLabel(item),
          isLocalElement(item) && !state.detached ? h('span', {class: 'ds-design-badge is-local', text: 'This Dashboard'}) : item.overridden?.length ? h('span', {class: 'ds-design-badge is-changed', text: 'Changed'}) : null)))));
      if (freePlaces(slide).length) nodes.push(h('button', {type: 'button', class: 'ds-design-action', onclick: guarded(() => addElement(slide.id, freePlaces(slide)[0]))}, '+ Add chart'));
    }
    nodes.push(h('div', {class: 'ds-design-panel-actions'}, slideActions(slide).map(([label, action, enabled]) => h('button', {type: 'button', class: 'ds-design-action', disabled: enabled !== true, title: typeof enabled === 'string' ? enabled : null, onclick: action}, label))));
    return nodes;
  }

  // The values of a field in the Dashboard's selection with their samples, for the filter dialogs (one read each).
  const fieldValueReads = new Map();
  function fieldValues(source, field) {
    const token = viewer().state().prepared?.token;
    const key = `${token}|${source}|${field}`;
    if (!fieldValueReads.has(key)) {
      fieldValueReads.set(key, api(`/design/values?token=${encodeURIComponent(token)}&source=${encodeURIComponent(source)}&field=${encodeURIComponent(field)}`)
        .then(result => result.values || []).catch(() => []));
    }
    return fieldValueReads.get(key);
  }
  // The filters of the Dashboard apply to every chart: the Filters shelf shows them first, locked.
  function lockedFilters() {
    const definition = viewer().state().definition || {};
    const label = value => String(value).replace(/^@latest-campaign$/, 'Latest campaign').replace(/^@latest-(\d+)-campaigns$/, 'Latest $1 campaigns')
      .replace(/^@previous-campaign$/, 'Previous campaign').replace(/^@main-cities$/, 'Main Cities');
    return Object.entries(definition.filters || {}).filter(([, values]) => Array.isArray(values) && values.length)
      .map(([name, values]) => `${name}: ${values.slice(0, 2).map(label).join(', ')}${values.length > 2 ? ` +${values.length - 2}` : ''}`);
  }

  // ------------------------------------------------------------------
  // Format of a chart (phase 3): series, legend, labels and axes, kept in its style (see formattedPayload in
  // dashboard_charts.js). The colours of Operator / Vendor Maps stay unless a series is given one; Default gives it back.
  // ------------------------------------------------------------------
  const SIZES = [['', 'Default'], ['Small', 'Small'], ['Medium', 'Medium'], ['Large', 'Large']];
  const DASH_NAMES = [['', 'Default'], ['solid', 'Solid'], ['dashed', 'Dashed'], ['dotted', 'Dotted']];
  const cardCanvas = elementId => [...($('ds-charts')?.querySelectorAll('.ds-chart') || [])].find(card => card.dataset.elementId === elementId)?.querySelector('canvas');
  const legendItems = elementId => { const canvas = cardCanvas(elementId); return canvas && globalThis.getDashboardChartLegendItems ? globalThis.getDashboardChartLegendItems(canvas) : []; };
  const styleOf = element => clone(element?.style && typeof element.style === 'object' ? element.style : {});
  const cleanStyle = style => {
    const prune = value => {
      if (!value || typeof value !== 'object' || Array.isArray(value)) return value;
      const result = {};
      for (const [key, item] of Object.entries(value)) {
        const cleaned = prune(item);
        if (cleaned === '' || cleaned === null || cleaned === undefined || (typeof cleaned === 'object' && !Array.isArray(cleaned) && !Object.keys(cleaned).length)) continue;
        result[key] = cleaned;
      }
      return result;
    };
    return prune(style) || {};
  };
  function setStyle(elementId, change) {
    const current = findElement(editableDesign(), elementId)?.element;
    if (!current) { report(new Error('This element is only in this Dashboard: change it in This Dashboard scope, or apply it to the template first.')); return undefined; }
    const style = styleOf(current);
    change(style);
    return setElementValues(elementId, {style: cleanStyle(style)});
  }
  const setSeries = (elementId, name, values) => setStyle(elementId, style => {
    style.series = style.series || {};
    style.series[name] = {...(style.series[name] || {}), ...values};
  });
  function openSeriesFormat(anchor, elementId, name, event) {
    closeMenus();
    const element = findElement(editableDesign(), elementId)?.element;
    const current = styleOf(element).series?.[name] || {};
    const original = legendItems(elementId).find(item => item.label === name)?.colour || '#4B2C82';
    const colour = h('input', {type: 'color', value: /^#[0-9a-f]{6}$/i.test(current.colour || '') ? current.colour : (/^#[0-9a-f]{6}$/i.test(original) ? original : '#4B2C82'), 'aria-label': `Colour of ${name}`,
      onchange: event2 => guarded(() => setSeries(elementId, name, {colour: event2.target.value.toUpperCase()}))()});
    const width = h('input', {type: 'number', min: '1', max: '10', step: '0.5', value: current.width ?? '', placeholder: 'Default', 'aria-label': 'Line width',
      onchange: event2 => guarded(() => setSeries(elementId, name, {width: event2.target.value === '' ? '' : Number(event2.target.value)}))()});
    const dash = selectInput(DASH_NAMES, current.dash || '', value => guarded(() => setSeries(elementId, name, {dash: value}))());
    const opacity = h('input', {type: 'range', min: '0.2', max: '1', step: '0.05', value: current.opacity ?? 1, 'aria-label': 'Opacity',
      onchange: event2 => guarded(() => setSeries(elementId, name, {opacity: Number(event2.target.value) >= 1 ? '' : Number(event2.target.value)}))()});
    const popover = h('div', {class: 'ds-design-popover ds-design-series', role: 'dialog', 'aria-label': `Format of ${name}`},
      h('h4', {text: name}),
      h('label', {class: 'ds-design-format-row'}, 'Colour', colour),
      h('label', {class: 'ds-design-format-row'}, 'Line width', width),
      h('label', {class: 'ds-design-format-row'}, 'Line', dash),
      h('label', {class: 'ds-design-format-row'}, 'Opacity', opacity),
      h('div', {class: 'ds-design-format-actions'},
        h('button', {type: 'button', title: 'The colour of the Operator / Vendor Maps of the workspace, and the default line', onclick: () => { closeMenus(); guarded(() => setStyle(elementId, style => { if (style.series) delete style.series[name]; }))(); }}, 'Default'),
        h('button', {type: 'button', onclick: closeMenus}, 'Close')));
    placePopover(popover, anchor, event);
  }
  function formatSection(elementId, element) {
    const style = styleOf(element);
    const items = legendItems(elementId);
    const series = h('div', {class: 'ds-design-series-list'}, items.length
      ? items.map(item => {
        const own = style.series?.[item.label] || {};
        return h('button', {type: 'button', class: `ds-design-series-item${Object.keys(own).length ? ' is-changed' : ''}`, title: 'Colour, line and opacity of this series', onclick: event => openSeriesFormat(event.currentTarget, elementId, item.label)},
          h('span', {class: 'ds-design-swatch', style: {background: own.colour || item.colour || '#ccc', opacity: own.opacity ?? 1}}), item.label);
      })
      : h('p', {class: 'ds-design-empty', text: 'The series of the chart appear here once it is drawn (its legend).'}));
    const set = (path, value) => guarded(() => setStyle(elementId, target => {
      const keys = path.split('.');
      let node = target;
      keys.slice(0, -1).forEach(key => { node[key] = node[key] && typeof node[key] === 'object' ? node[key] : {}; node = node[key]; });
      node[keys.at(-1)] = value;
    }))();
    const integer = value => (value === '' ? '' : Math.max(0, Math.min(6, Math.round(Number(value)))));
    return h('details', {class: 'ds-design-format', open: true},
      h('summary', {}, 'Format', Object.keys(style).length ? h('span', {class: 'ds-design-badge is-changed', text: 'Formatted'}) : null),
      h('p', {class: 'ds-design-field-note', text: 'Click a series in the legend of the chart, or here, to change its colour, line and opacity.'}),
      series,
      h('div', {class: 'ds-design-format-actions'},
        h('button', {type: 'button', disabled: !style.series || !Object.values(style.series).some(item => item.colour || item.opacity), title: 'The colours of the Operator / Vendor Maps of the workspace for every series',
          onclick: () => guarded(() => setStyle(elementId, target => { for (const item of Object.values(target.series || {})) { delete item.colour; delete item.opacity; } }))()}, 'Default colours'),
        h('button', {type: 'button', title: 'Copy the format of this chart', onclick: () => { state.formatClipboard = {style, legend_position: element.legend_position, label_position: element.label_position, label_format: element.label_format, axis_x_range: element.axis_x_range, axis_y_range: element.axis_y_range}; viewer().status('Format copied: paste it on another chart.'); renderPanel(); }}, 'Copy format'),
        h('button', {type: 'button', disabled: !state.formatClipboard, title: 'Give this chart the format copied', onclick: () => guarded(() => setElementValues(elementId, clone(state.formatClipboard)))()}, 'Paste format')),
      h('div', {class: 'ds-design-two'},
        field('Legend', selectInput([['', 'Default'], ['top', 'Top'], ['bottom', 'Bottom'], ['left', 'Left'], ['right', 'Right'], ['none', 'Hidden']], style.legend?.position || '', value => set('legend.position', value))),
        field('Legend text', selectInput(SIZES, style.legend?.size || '', value => set('legend.size', value)))),
      h('div', {class: 'ds-design-two'},
        field('Labels', selectInput(LABEL_POSITIONS, style.labels?.position || '', value => set('labels.position', value))),
        field('Label text', selectInput(SIZES, style.labels?.size || '', value => set('labels.size', value)))),
      h('div', {class: 'ds-design-two'},
        field('Label colour', h('div', {class: 'ds-design-input-row'},
          h('input', {type: 'color', value: style.labels?.colour || '#263B4A', 'aria-label': 'Label colour', onchange: event => set('labels.colour', event.target.value.toUpperCase())}),
          h('button', {type: 'button', class: 'ds-design-token', title: 'Default label colour', onclick: () => set('labels.colour', '')}, '↺'))),
        h('label', {class: 'ds-design-check'}, h('input', {type: 'checkbox', checked: Boolean(style.labels?.bold), onchange: event => set('labels.bold', event.target.checked || '')}), 'Bold labels')),
      h('div', {class: 'ds-design-two'},
        field('X axis title', textInput(style.axes?.x?.title, debounced(value => setStyle(elementId, target => { target.axes = target.axes || {}; target.axes.x = {...(target.axes.x || {}), title: value}; })), {id: 'ds-design-axis-x-title', placeholder: 'As the chart names it'})),
        field('Y axis title', textInput(style.axes?.y?.title, debounced(value => setStyle(elementId, target => { target.axes = target.axes || {}; target.axes.y = {...(target.axes.y || {}), title: value}; })), {id: 'ds-design-axis-y-title', placeholder: 'As the chart names it'}))),
      field('X axis decimals', h('input', {type: 'number', min: '0', max: '6', step: '1', value: style.axes?.x?.decimals ?? '', placeholder: 'Default',
        onchange: event => set('axes.x.decimals', integer(event.target.value))}), 'The decimals of the values of the X axis of a CDF.'));
  }

  function elementForm(element) {
    const shown = state.scope === 'template' ? findElement(state.template, element.id)?.element : element;
    if (!shown) {
      return [h('h3', {class: 'ds-design-panel-title', text: elementLabel(element)}),
        h('p', {class: 'ds-design-origin is-local', text: 'This element is only in this Dashboard: change it in This Dashboard scope, or apply it to the template.'}),
        h('div', {class: 'ds-design-panel-actions'}, elementActions(element.id).map(([label, action, enabled]) => h('button', {type: 'button', class: 'ds-design-action', disabled: enabled !== true, onclick: action}, label)))];
    }
    const set = (key, delay) => (delay === 0 ? value => guarded(() => setElementValues(element.id, {[key]: value}))() : debounced(value => setElementValues(element.id, {[key]: value}), delay));
    const title = textInput(shown.chart_title, set('chart_title'), {id: 'ds-design-chart-title'});
    const datalist = fieldsDatalist(shown);
    const fieldInput = (key, placeholder) => textInput(shown[key], set(key), {id: `ds-design-${key}`, list: 'ds-design-fields', placeholder});
    const builder = h('div', {class: 'ds-cb'});
    window.DashboardChartBuilder?.render(builder, {
      values: shown, fields: state.fields?.fields, calculated: state.fields?.calculated_fields, parameters: parameters(),
      lockedFilters: lockedFilters(), fieldValues,
      onChange: changes => guarded(() => setElementValues(element.id, changes))(),
    });
    return [
      h('h3', {class: 'ds-design-panel-title', text: elementLabel(shown)}),
      originNote(element, 'element'),
      datalist,
      field('Chart title', h('div', {class: 'ds-design-input-row'}, title, tokenMenuButton(title))),
      builder,
      formatSection(element.id, shown),
      h('details', {class: 'ds-design-advanced'}, h('summary', {text: 'Advanced: the text of each column, legend and label positions, axis ranges'}),
        h('div', {class: 'ds-design-two'},
          field('Source', selectInput(SOURCES, shown.cdr_source, set('cdr_source', 0), 'ds-design-source')),
          field('Chart type', selectInput(CHART_TYPES.map(type => [type, type]), shown.chart_type, set('chart_type', 0), 'ds-design-chart-type'))),
        field('KPI', fieldInput('kpi', 'A field of the source'), 'Several KPIs (Multi KPI CDF Lines, Scatter, Table): separate them with |.'),
        field('Rows Split', fieldInput('rows_split', 'Operator × Campaign')),
        field('Columns Split', fieldInput('columns_split', 'Campaign')),
        field('Legend', fieldInput('legend', 'Operator')),
        field('Filters', textInput((shown.filters || '').split(/;\s*/).filter(Boolean).join('\n'), debounced(value => setElementValues(element.id, {filters: value.split(/\n+/).map(line => line.trim()).filter(Boolean).join('; ')})), {id: 'ds-design-filters', multiline: true, rows: 4, placeholder: 'Call_Status IN (Completed, Dropped)\nThreshold = 1.6'}), 'One condition per line; a parameter is written {Name}.'),
        h('div', {class: 'ds-design-two'},
          field('Legend position', selectInput(LEGEND_POSITIONS, shown.legend_position, set('legend_position', 0), 'ds-design-legend-position')),
          field('Label position', selectInput(LABEL_POSITIONS, shown.label_position, set('label_position', 0), 'ds-design-label-position'))),
        h('div', {class: 'ds-design-two'},
          field('Axis X range', textInput(shown.axis_x_range, set('axis_x_range'), {id: 'ds-design-axis-x', placeholder: '[0,100]'})),
          field('Axis Y range', textInput(shown.axis_y_range, set('axis_y_range'), {id: 'ds-design-axis-y', placeholder: '[0,]'}))),
        h('div', {class: 'ds-design-two'},
          h('label', {class: 'ds-design-check'}, h('input', {type: 'checkbox', checked: Boolean(shown.exclude_null_empty), onchange: event => set('exclude_null_empty', 0)(event.target.checked)}), 'Exclude Null/Empty'),
          h('label', {class: 'ds-design-check'}, h('input', {type: 'checkbox', checked: Boolean(shown.exclude_zero), onchange: event => set('exclude_zero', 0)(event.target.checked)}), 'Exclude Zero'))),
      h('div', {class: 'ds-design-panel-actions'}, elementActions(element.id).map(([label, action, enabled]) => h('button', {type: 'button', class: 'ds-design-action', disabled: enabled !== true, title: typeof enabled === 'string' ? enabled : null, onclick: action}, label))),
    ];
  }

  // The title and subtitle of the slide shown are edited on the slide itself: a click writes them as the Design has them
  // (with their tokens), Enter or leaving the field keeps the change, Esc gives it up.
  function editHeading(key) {
    const slide = shownSlide();
    const heading = $(key === 'title' ? 'ds-title' : 'ds-subtitle');
    if (!state.active || !slide || !heading || heading.querySelector('input')) return;
    const source = state.scope === 'template' ? findSlide(state.template, slide.id) : slide;
    if (!source) { report(new Error('This slide is only in this Dashboard: change it in This Dashboard scope.')); return; }
    const input = h('input', {type: 'text', class: `ds-design-heading-input is-${key}`, value: source[key] || '', 'aria-label': key === 'title' ? 'Slide title' : 'Slide subtitle'});
    const shown = [...heading.childNodes];
    heading.replaceChildren(input);
    input.focus();
    input.select();
    let done = false;
    const finish = keep => {
      if (done) return;
      done = true;
      const value = input.value;
      heading.replaceChildren(...shown);
      if (keep && value !== (source[key] || '')) guarded(() => edit(design => {
        const target = findSlide(design, slide.id);
        if (!target) return false;
        target[key] = value;
      }))();
    };
    input.addEventListener('keydown', event => {
      if (event.key === 'Enter') { event.preventDefault(); finish(true); }
      else if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); finish(false); }
    });
    input.addEventListener('blur', () => finish(true));
  }
  for (const [id, key] of [['ds-title', 'title'], ['ds-subtitle', 'subtitle']]) {
    $(id)?.addEventListener('click', () => { if (state.active && !shownSlide()?.hidden) editHeading(key); });
  }

  // ------------------------------------------------------------------
  // Layout gallery: a grid of places (rows × columns, as Insert Table) and the other layouts of the slide master
  // ------------------------------------------------------------------
  function openLayoutGallery(anchor, slide) {
    closeMenus();
    const kind = slideKind(slide);
    const layouts = state.layouts || [];
    const gallery = h('div', {class: 'ds-design-popover ds-design-layouts', role: 'dialog', 'aria-label': 'Layouts'});
    const choose = name => { closeMenus(); guarded(() => setLayout(slide.id, name))(); };
    if (kind === 'content') {
      let comments = (/comments (down|right)/i.exec(slide.layout || '') || [])[1]?.toLowerCase() ?? 'down';
      const grid = h('div', {class: 'ds-design-grid-picker'});
      const label = h('p', {class: 'ds-design-grid-label', text: 'Rows × columns'});
      const gridName = (rows, columns) => `Title + ${rows} rows + ${columns} columns${comments ? ` + comments ${comments}` : ''}`;
      const available = name => layouts.some(layout => layout.name === name);
      const paint = (rows, columns) => {
        grid.querySelectorAll('button').forEach(cell => cell.classList.toggle('is-on', Number(cell.dataset.row) <= rows && Number(cell.dataset.column) <= columns));
        label.textContent = rows ? `${rows} × ${columns}${available(gridName(rows, columns)) ? '' : ' (not in the slide master)'}` : 'Rows × columns';
      };
      const fill = () => {
        grid.replaceChildren();
        for (let row = 1; row <= 6; row += 1) {
          for (let column = 1; column <= 6; column += 1) {
            const name = gridName(row, column);
            grid.append(h('button', {type: 'button', 'aria-label': `${row} rows, ${column} columns`, disabled: !available(name), dataset: {row: String(row), column: String(column)},
              onmouseenter: () => paint(row, column), onfocus: () => paint(row, column), onclick: () => choose(name)}));
          }
        }
      };
      fill();
      grid.addEventListener('mouseleave', () => paint(0, 0));
      const commentChoice = h('div', {class: 'ds-design-segmented', role: 'group', 'aria-label': 'Comments'}, [['', 'No comments'], ['down', 'Comments down'], ['right', 'Comments right']].map(([value, text]) =>
        h('button', {type: 'button', class: comments === value ? 'is-active' : '', onclick: event => { comments = value; event.currentTarget.parentElement.querySelectorAll('button').forEach(button => button.classList.toggle('is-active', button === event.currentTarget)); fill(); }}, text)));
      gallery.append(h('h4', {text: 'Grid'}), commentChoice, grid, label);
      const others = layouts.filter(layout => !layout.grid && !layout.dynamic && !layout.structural);
      if (others.length) gallery.append(h('h4', {text: 'Other layouts'}), h('div', {class: 'ds-design-layout-list'}, others.map(layout => h('button', {type: 'button', class: layout.name === slide.layout ? 'is-active' : '', onclick: () => choose(layout.name)}, layoutPreview(layout), layout.name))));
      const dynamic = layouts.filter(layout => layout.dynamic);
      if (dynamic.length) gallery.append(h('h4', {text: 'Repeated by a field (dynamic)'}), h('div', {class: 'ds-design-layout-list'}, dynamic.map(layout => h('button', {type: 'button', class: layout.name === slide.layout ? 'is-active' : '', onclick: () => choose(layout.name)}, layout.name))));
    } else {
      gallery.append(h('h4', {text: STRUCTURAL[kind]}), h('div', {class: 'ds-design-layout-list'}, layouts.filter(layout => layout.structural).map(layout => h('button', {type: 'button', class: layout.name === slide.layout ? 'is-active' : '', onclick: () => choose(layout.name)}, layout.name))));
    }
    placePopover(gallery, anchor);
  }
  function layoutPreview(layout) {
    const frame = h('span', {class: 'ds-design-layout-preview'});
    for (const [left, top, width, height] of layout.places || []) frame.append(h('span', {style: {left: `${left}%`, top: `${top}%`, width: `${width}%`, height: `${height}%`}}));
    return frame;
  }

  // ------------------------------------------------------------------
  // Menus and popovers
  // ------------------------------------------------------------------
  function closeMenus() { document.querySelectorAll('.ds-design-popover').forEach(node => node.remove()); }
  function placePopover(popover, anchor, event) {
    document.body.append(popover);
    const box = anchor.getBoundingClientRect();
    const width = popover.offsetWidth, height = popover.offsetHeight;
    let left = event?.clientX ?? box.left, top = event?.clientY ?? box.bottom + 4;
    left = Math.max(8, Math.min(left, window.innerWidth - width - 8));
    if (top + height > window.innerHeight - 8) top = Math.max(8, (event?.clientY ?? box.top) - height - 4);
    Object.assign(popover.style, {left: `${left}px`, top: `${top}px`});
    popover.querySelector('button:not(:disabled)')?.focus({preventScroll: true});
  }
  function openMenu(anchor, actions, event) {
    closeMenus();
    const menu = h('div', {class: 'ds-design-popover ds-design-menu', role: 'menu'}, actions.map(([label, action, enabled]) => h('button', {
      type: 'button', role: 'menuitem', disabled: enabled !== true, title: typeof enabled === 'string' ? enabled : null,
      onclick: () => { closeMenus(); action(); },
    }, label)));
    placePopover(menu, anchor, event);
  }
  document.addEventListener('pointerdown', event => { if (!event.target.closest('.ds-design-popover, [aria-haspopup]')) closeMenus(); }, true);
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && document.querySelector('.ds-design-popover')) { closeMenus(); return; }
    if (!state.active || event.target.closest('input, textarea, select, [contenteditable="true"]')) return;
    const modifier = event.metaKey || event.ctrlKey;
    if (modifier && event.key.toLowerCase() === 'z') { event.preventDefault(); guarded(event.shiftKey ? redo : undo)(); }
    else if (modifier && event.key.toLowerCase() === 'y') { event.preventDefault(); guarded(redo)(); }
    else if ((event.key === 'Delete' || event.key === 'Backspace') && state.element) { event.preventDefault(); guarded(() => deleteElement(state.element))(); }
    else if (event.key === 'Escape' && state.element) { state.element = ''; state.tab = 'slide'; renderDesigner(); }
  });

  // ------------------------------------------------------------------
  // Dialogs: Differences, Parameters
  // ------------------------------------------------------------------
  function openDialog(title, eyebrow, content, {wide = false} = {}) {
    const overlay = h('div', {class: 'confirm-overlay ds-overlay ds-secondary ppt-dashboards ds-design-dialog-overlay'});
    const close = () => overlay.remove();
    const dialog = h('section', {class: `confirm-panel ds-design-dialog${wide ? ' is-wide' : ''}`, role: 'dialog', 'aria-modal': 'true', 'aria-label': title, tabindex: '-1'},
      h('div', {class: 'section-head'}, h('div', {}, h('p', {class: 'eyebrow', text: eyebrow}), h('h2', {text: title})), h('button', {type: 'button', class: 'ds-dialog-close', 'aria-label': 'Close', onclick: close}, '×')),
      content,
      h('div', {class: 'ds-design-dialog-actions'}, h('button', {type: 'button', class: 'ds-design-action', onclick: close}, 'Close')));
    overlay.append(dialog);
    overlay.addEventListener('keydown', event => { if (event.key === 'Escape') { event.stopPropagation(); close(); } });
    $('ds-viewer').append(overlay);
    overlay.hidden = false;
    dialog.focus();
    return {overlay, close};
  }

  function openDifferencesDialog() {
    const body = h('div', {class: 'ds-design-differences'});
    const refresh = () => {
      const rows = [];
      const slideName = id => findSlide(state.design, id)?.title || findSlide(state.template, id)?.title || id;
      const elementName = id => elementLabel(findElement(state.design, id)?.element || findElement(state.template, id)?.element) || id;
      const changed = state.report?.template_changed || [];
      if (changed.length) {
        rows.push(h('h3', {text: 'Changed in the template since'}));
        rows.push(h('p', {class: 'form-note', text: 'This Dashboard changed these properties, and the template changed them too afterwards.'}));
        for (const item of changed) {
          rows.push(h('div', {class: 'ds-design-difference is-warning'},
            h('span', {}, h('b', {text: item.slide ? slideName(item.slide) : elementName(item.element)}), ` · ${item.property.replaceAll('_', ' ')}: template now “${String(item.template ?? '')}”, here “${String(item.value ?? '')}”`),
            h('button', {type: 'button', class: 'ds-design-action', onclick: guarded(async () => { item.slide ? await resetSlideProperty(item.slide, item.property) : await resetElementProperty(item.element, item.property); refresh(); })}, 'Take template')));
        }
        rows.push(h('button', {type: 'button', class: 'ds-design-action', onclick: () => { state.keepTemplateChanges = true; state.report = {...state.report, template_changed: []}; renderDesigner(); refresh(); viewer().status('Kept: save to stop flagging them.'); }}, 'Keep mine for all'));
      }
      const overrides = state.overrides || {};
      const entries = [];
      for (const [id, properties] of Object.entries(overrides.slides || {})) for (const name of Object.keys(properties)) entries.push([`Slide “${slideName(id)}”`, `${name}`, () => resetSlideProperty(id, name)]);
      for (const [id, properties] of Object.entries(overrides.elements || {})) for (const name of Object.keys(properties)) entries.push([`Chart “${elementName(id)}”`, `${name.replaceAll('_', ' ')}`, () => resetElementProperty(id, name)]);
      for (const [id, change] of Object.entries(overrides.filters || {})) entries.push([`Chart “${elementName(id)}”`, `filters${change.add?.length ? ` + ${change.add.join('; ')}` : ''}${change.remove?.length ? ` − ${change.remove.join('; ')}` : ''}`, () => resetElementProperty(id, 'filters')]);
      for (const id of overrides.hidden_slides || []) entries.push([`Slide “${slideName(id)}”`, 'hidden', () => setSlideHidden(id, false)]);
      for (const id of overrides.shown_optional || []) entries.push([`Slide “${slideName(id)}”`, 'optional slide shown', () => setOptionalShown(id, false)]);
      for (const id of overrides.hidden_elements || []) entries.push([`Chart “${elementName(id)}”`, 'removed here', () => resetElement(id)]);
      for (const local of overrides.local_slides || []) entries.push([`Slide “${local.slide?.title || 'New slide'}”`, 'only in this Dashboard', () => deleteSlideHere(local.slide?.id)]);
      for (const [slideId, elements] of Object.entries(overrides.local_elements || {})) for (const element of elements) entries.push([`Chart “${elementLabel(element)}” on “${slideName(slideId)}”`, 'only in this Dashboard', () => deleteElementHere(element.id)]);
      rows.push(h('h3', {text: `Differences from the template · ${entries.length}`}));
      if (!entries.length) rows.push(h('p', {class: 'form-note', text: 'This Dashboard shows its template as it is.'}));
      for (const [what, detail, reset] of entries) {
        rows.push(h('div', {class: 'ds-design-difference'}, h('span', {}, h('b', {text: what}), ` · ${detail}`),
          h('button', {type: 'button', class: 'ds-design-action', disabled: !state.rights.dashboard, onclick: guarded(async () => { await reset(); refresh(); })}, 'Reset to template')));
      }
      const dropped = state.report?.dropped || [];
      if (dropped.length) {
        rows.push(h('h3', {text: 'No longer in the template'}));
        rows.push(h('p', {class: 'form-note', text: `${dropped.length} change${dropped.length === 1 ? '' : 's'} of this Dashboard refer to slides or charts the template deleted: they are left out, and dropped when you save.`}));
      }
      body.replaceChildren(...rows);
    };
    refresh();
    openDialog('Differences', `${state.info?.name || 'Dashboard'} · template ${state.info?.template?.name || ''}`, body, {wide: true});
  }
  const resetSlideProperty = (slideId, name) => edit(design => {
    const slide = findSlide(design, slideId), original = findSlide(state.template, slideId);
    if (!slide || !original) return false;
    slide[name] = clone(original[name]);
  }, {scope: 'dashboard'});
  const resetElementProperty = (elementId, name) => edit(design => {
    const found = findElement(design, elementId), original = findElement(state.template, elementId)?.element;
    if (!found || !original) return false;
    found.element[name] = clone(original[name]);
  }, {scope: 'dashboard'});
  const deleteSlideHere = slideId => edit(design => {
    const index = design.slides.findIndex(item => item.id === slideId);
    if (index < 0) return false;
    design.slides.splice(index, 1);
  }, {scope: 'dashboard'});
  const deleteElementHere = elementId => edit(design => {
    const found = findElement(design, elementId);
    if (!found) return false;
    found.slide.elements.splice(found.slide.elements.indexOf(found.element), 1);
  }, {scope: 'dashboard'});

  function openParametersDialog() {
    const editable = state.detached ? state.rights.dashboard : state.rights.template;
    const scope = state.detached ? 'dashboard' : 'template';
    const design = () => (state.detached ? state.design : state.template);
    const body = h('div', {class: 'ds-design-parameters'});
    const uses = name => {
      const pattern = new RegExp(`\\{\\s*${name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*\\}`, 'i');
      return (design()?.slides || []).flatMap(slide => [
        ...['title', 'subtitle'].filter(key => pattern.test(slide[key] || '')).map(key => `${slide.title || 'Slide'} · ${key}`),
        ...(slide.elements || []).flatMap(element => Object.entries(element).filter(([, value]) => typeof value === 'string' && pattern.test(value)).map(([key]) => `${elementLabel(element)} · ${key.replaceAll('_', ' ')}`)),
      ]);
    };
    const save = list => edit(target => { target.parameters = list; }, {scope});
    const refresh = () => {
      const list = clone(design()?.parameters || []);
      const rows = list.map((parameter, index) => {
        const update = values => { list[index] = {...list[index], ...values}; };
        const commit = guarded(async () => { await save(list); refresh(); });
        const name = h('input', {type: 'text', value: parameter.name, 'aria-label': 'Name', disabled: !editable, onchange: guarded(async event => {
          const previous = parameter.name, next = event.target.value.trim();
          if (!next || next === previous) return;
          update({name: next});
          // Every use of the parameter takes its new name.
          await edit(target => {
            target.parameters = list;
            const pattern = new RegExp(`\\{\\s*${previous.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*\\}`, 'gi');
            for (const slide of target.slides || []) {
              for (const key of ['title', 'subtitle']) if (typeof slide[key] === 'string') slide[key] = slide[key].replace(pattern, `{${next}}`);
              for (const element of slide.elements || []) for (const [key, value] of Object.entries(element)) if (typeof value === 'string') element[key] = value.replace(pattern, `{${next}}`);
            }
          }, {scope});
          refresh();
        })});
        const type = selectInput([['values', 'Field values'], ['number', 'Number'], ['text', 'Text']], parameter.type, value => { update({type: value, default: value === 'values' ? null : value === 'number' ? null : ''}); commit(); });
        type.disabled = !editable;
        const details = [];
        if (parameter.type === 'values') {
          details.push(field('Field', textInput(parameter.field, value => update({field: value}), {list: 'ds-design-fields', placeholder: 'City'})));
          details.push(h('label', {class: 'ds-design-check'}, h('input', {type: 'checkbox', checked: parameter.multiple !== false, disabled: !editable, onchange: event => { update({multiple: event.target.checked}); commit(); }}), 'Several values'));
          details.push(field('Default values', textInput((parameter.default || []).join(', '), value => update({default: value.split(',').map(item => item.trim()).filter(Boolean)}), {placeholder: 'All'}), 'Empty: All values (the conditions with it are left out).'));
        } else if (parameter.type === 'number') {
          details.push(h('div', {class: 'ds-design-two'}, ...['default', 'min', 'max', 'step'].map(key => field(key[0].toUpperCase() + key.slice(1), h('input', {type: 'number', step: 'any', value: parameter[key] ?? '', disabled: !editable, oninput: event => update({[key]: event.target.value === '' ? null : Number(event.target.value)})})))));
        } else details.push(field('Default text', textInput(parameter.default, value => update({default: value}))));
        details.push(field('Description', textInput(parameter.description, value => update({description: value}))));
        const used = uses(parameter.name);
        return h('div', {class: 'ds-design-parameter'},
          h('div', {class: 'ds-design-parameter-head'}, field('Name', name), field('Type', type)),
          ...details,
          h('p', {class: 'form-note', text: used.length ? `Used in ${used.length}: ${used.slice(0, 6).join('; ')}${used.length > 6 ? '…' : ''}` : 'Not used yet: write {' + parameter.name + '} in a filter, title or setting.'}),
          editable ? h('div', {class: 'ds-design-panel-actions'},
            h('button', {type: 'button', class: 'ds-design-action ds-design-primary', onclick: commit}, 'Apply'),
            h('button', {type: 'button', class: 'ds-design-action', disabled: used.length > 0, title: used.length ? 'Remove its uses first' : null, onclick: guarded(async () => { list.splice(index, 1); await save(list); refresh(); })}, 'Delete')) : null);
      });
      body.replaceChildren(
        h('p', {class: 'form-note', text: 'Each Dashboard of the template chooses the values of its parameters in Dashboard Scope & Filters. Write {Name} in a chart filter (City IN ({City})), a numeric setting (LQ < {Threshold}) or a title.'}),
        fieldsDatalist(shownElement()),
        ...rows,
        editable ? h('button', {type: 'button', class: 'ds-design-action', onclick: guarded(async () => {
          let index = list.length + 1, nameValue = `Parameter ${index}`;
          while (list.some(item => item.name.toLowerCase() === nameValue.toLowerCase())) nameValue = `Parameter ${++index}`;
          list.push({id: randomId('p'), name: nameValue, type: 'values', field: 'City', multiple: true, default: null, description: ''});
          await save(list);
          refresh();
        })}, '+ Add parameter') : h('p', {class: 'form-note', text: 'Only the owners of the template change its parameters.'}));
    };
    refresh();
    openDialog('Parameters', `Template ${state.info?.template?.name || ''}`, body, {wide: true});
  }

  // ------------------------------------------------------------------
  // Save as template, Save as my Dashboard, Detach
  // ------------------------------------------------------------------
  async function saveAsTemplate() {
    const id = viewer().state().activeId;
    const name = await window.showTextInputDialog('Name of the new template', {title: 'Save as template', value: `${state.info?.name || 'Dashboard'} template`.slice(0, 120), maxLength: 120, confirmLabel: 'Save'});
    if (!name || !String(name).trim()) return;
    const result = await api(`/${encodeURIComponent(id)}/design/save-as-template`, 'POST', {name: String(name).trim()});
    viewer().status(`Saved the template “${result.template}”: new Dashboards can use it.`);
  }
  async function saveAsMyDashboard() {
    const {dashboard} = viewer().state();
    if (state.templateDirty) throw new Error('Save or discard the changes of the template first: your Dashboard takes the changes of this one only.');
    const name = await window.showTextInputDialog('Name of your Dashboard', {title: 'Save as my Dashboard', value: `${dashboard?.name || 'Dashboard'} (mine)`.slice(0, 120), maxLength: 120, confirmLabel: 'Save'});
    if (!name || !String(name).trim()) return;
    const id = globalThis.crypto?.randomUUID?.() || randomId('dashboard-');
    const definition = {...clone(dashboard), name: String(name).trim(), slide_comments: {}, slide_comment_meta: {},
      design_overrides: state.detached ? {} : (hasOverrides(state.overrides) ? state.overrides : {}), design: state.detached ? state.design : null};
    delete definition.datasets;
    await api(`/${encodeURIComponent(id)}`, 'PUT', definition);
    // This Dashboard keeps what it had saved; the new one, with the changes shown, opens.
    await exitDesign({force: true});
    syncDesignButton();
    await viewer().reloadLibrary();
    await viewer().openDashboard(id);
    viewer().status(`Saved “${definition.name}”: your own Dashboard, following the same template with these changes.`);
  }
  async function detachDashboard() {
    const id = viewer().state().activeId;
    if (!await window.showConfirmDialog(`Detach this Dashboard from the template “${state.info?.template?.name}”? It keeps the Design it shows as its own and no longer takes the changes of the template.`, {title: 'Detach from template', confirmLabel: 'Detach', tone: 'danger'})) return;
    const info = await api(`/${encodeURIComponent(id)}/design/detach`, 'POST');
    loadDesign(info);
    viewer().storeDesign(id, storedDesignFields(info));
    renderDesigner();
    viewer().status('Detached: this Dashboard keeps a Design of its own.');
  }

  // ------------------------------------------------------------------
  // The values of the template parameters, in Dashboard Scope & Filters
  // ------------------------------------------------------------------
  const parameterOptions = new Map();
  async function parameterValues(field) {
    const {definition} = viewer().state();
    const key = `${viewer().state().activeId}:${field}`;
    if (!parameterOptions.has(key)) {
      parameterOptions.set(key, api('/filter-options', 'POST', {definition, field}).then(result => (result.values || []).map(value => (typeof value === 'object' ? String(value.value ?? value.label ?? '') : String(value)))).catch(() => []));
    }
    return parameterOptions.get(key);
  }
  function renderParameterValues() {
    const panel = $('ds-parameters-panel'), host = $('ds-parameters');
    if (!panel || !host) return;
    const list = parameters();
    const definition = viewer()?.state().definition;
    panel.hidden = !list.length || !definition;
    if (panel.hidden) { host.replaceChildren(); return; }
    const values = {...(definition.parameter_values || {})};
    const set = (id, value) => {
      const next = {...(viewer().state().definition?.parameter_values || {})};
      if (value === undefined) delete next[id]; else next[id] = value;
      viewer().setParameterValues(next);
    };
    host.replaceChildren(...list.map(parameter => {
      const current = Object.prototype.hasOwnProperty.call(values, parameter.id) ? values[parameter.id] : parameter.default;
      const label = h('label', {class: 'ds-source-filter ds-parameter-control', title: parameter.description || null}, parameter.name);
      if (parameter.type === 'values') {
        const select = h('select', {multiple: parameter.multiple !== false, 'aria-label': parameter.name});
        if (parameter.multiple === false) select.append(h('option', {value: '', text: 'All'}));
        select.dataset.multiselectAutoClose = '1000';
        const fill = options => {
          const chosen = new Set(Array.isArray(current) ? current.map(String) : []);
          for (const value of [...new Set([...options, ...chosen])]) {
            const option = h('option', {value, text: value});
            option.selected = chosen.has(value);
            select.append(option);
          }
          select.dispatchEvent(new Event('searchable-select:options-updated'));
          window.setupCustomMultiSelects?.();
        };
        parameterValues(parameter.field).then(fill);
        select.addEventListener('change', () => {
          const chosen = [...select.selectedOptions].map(option => option.value).filter(Boolean);
          set(parameter.id, chosen.length ? chosen : null);
        });
        label.append(select, h('span', {class: 'form-note', text: `${parameter.field} · none chosen: All`}));
      } else if (parameter.type === 'number') {
        label.append(h('input', {type: 'number', step: parameter.step ?? 'any', min: parameter.min ?? null, max: parameter.max ?? null, value: current ?? '',
          onchange: event => set(parameter.id, event.target.value === '' ? undefined : Number(event.target.value))}));
      } else {
        label.append(h('input', {type: 'text', value: current ?? '', onchange: event => set(parameter.id, event.target.value)}));
      }
      return label;
    }));
  }

  // ------------------------------------------------------------------
  // The Design button and the events of the viewer
  // ------------------------------------------------------------------
  function syncDesignButton() {
    const button = $('ds-design');
    if (!button) return;
    const rights = state.info?.rights;
    button.hidden = !rights || !(rights.dashboard || rights.template);
    button.classList.toggle('is-active', state.active);
    button.textContent = state.active ? 'Designing' : 'Design';
  }
  $('ds-design')?.addEventListener('click', guarded(async () => {
    if (state.active) { await exitDesign(); syncDesignButton(); return; }
    await enterDesign();
    syncDesignButton();
  }));
  document.addEventListener('ds:dashboard-opened', event => {
    exitDesign({force: true});
    state.dashboardId = event.detail.id;
    state.info = null;
    parameterOptions.clear();
    syncDesignButton();
    renderParameterValues();
    loadInfo(event.detail.id);
  });
  document.addEventListener('ds:dashboard-closed', () => {
    exitDesign({force: true});
    state.dashboardId = '';
    state.info = null;
    syncDesignButton();
    renderParameterValues();
  });
  // Prepared again (filters applied): the Design not saved yet is laid out on the new selection.
  document.addEventListener('ds:prepared', () => {
    if (!state.active) return;
    if (dirty()) guarded(() => preview(state.dashboardDirty ? {...previewBody(), design: state.design} : previewBody()))();
    else loadFields(viewer().state().prepared?.token);
  });
  document.addEventListener('ds:slide-rendered', () => {
    if (!state.active) return;
    decorateStage();
    renderSorter();
    renderPanel();
  });
  // The viewer closed while designing: Design closes with it (asking about the changes not saved).
  $('ds-viewer-close')?.addEventListener('click', event => {
    if (!state.active || !dirty()) { exitDesign({force: true}); syncDesignButton(); return; }
    event.stopImmediatePropagation();
    guarded(async () => { if (await exitDesign()) { syncDesignButton(); $('ds-viewer-close').click(); } })();
  }, true);
  window.addEventListener('beforeunload', event => { if (state.active && dirty()) { event.preventDefault(); event.returnValue = ''; } });
})();
