/* The Designer (ticket #26): the Designer of the PPT Designer viewer.

   In the Designer the slides at the left are the slides being edited (hidden and optional ones included), the elements of the
   slide shown can be chosen, moved between the places of its layout and changed in the panel at the right, and every
   change is laid out at once by the server on the CDRs the Design already prepared (POST /slides/preview). Changes go
   to the template (Template scope: every Design that follows it) or to this Design only (This Design scope:
   kept as its differences from the template, see design_slides.py). Nothing is stored until Save. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const viewer = () => window.designViewer;
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
    window.showInfoDialog?.(error.message, {title: 'Designer', tone: 'error'});
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
  // The fields the titles and text boxes can name: the NR Mode and the selection of the Design (design_slides.py).
  const BUILT_IN_TOKENS = ['{NR Mode}', '{NR Mode Name}', '{Design}', '{Scope}', '{Campaigns}', '{Operators}', '{Vendors}', '{Regions}', '{Clusters}', '{Cities}'];
  const DEFAULT_LAYOUT = 'Title + 1 rows + 1 columns + comments down';

  const state = {
    designId: '', info: null, active: false, layouts: null, fields: null,
    template: null, slide_set: null, overrides: null, report: null, summary: null, detached: false,
    rights: {design: false, template: false}, scope: 'design',
    templateDirty: false, designDirty: false, keepTemplateChanges: false,
    history: [], future: [], slide: '', element: '', tab: 'slide',
    queue: Promise.resolve(), busy: 0, clipboard: null, dragSlide: '', dragElement: '',
    // The token of the slides laid out from the slide set shown, and a count of the data prepared (for the slide list).
    syncedToken: '', generation: 0,
    // On a phone the panel floats over the slide: folded until a chart is chosen.
    folded: window.matchMedia?.('(max-width: 900px)').matches || false,
  };

  // ------------------------------------------------------------------
  // The slide set of the open Design
  // ------------------------------------------------------------------
  const dirty = () => state.templateDirty || state.designDirty || state.keepTemplateChanges;
  const editedSlides = () => state.slide_set?.slides || [];
  const templateSlides = () => state.template?.slides || [];
  const findSlide = (slide_set, id) => (slide_set?.slides || []).find(slide => slide.id === id) || null;
  const findElement = (slide_set, id) => {
    for (const slide of slide_set?.slides || []) {
      const element = (slide.elements || []).find(item => item.id === id);
      if (element) return {slide, element};
    }
    return null;
  };
  const shownSlide = () => findSlide(state.slide_set, state.slide);
  const shownElement = () => findElement(state.slide_set, state.element)?.element || null;
  const slideKind = slide => slide?.kind || 'content';
  const isTemplateSlide = slide => Boolean(slide) && slide.origin === 'template' && Boolean(findSlide(state.template, slide.id));
  const isLocalElement = element => element?.origin === 'design';
  const layoutOf = name => (state.layouts || []).find(layout => layout.name === name) || null;
  // The places of a slide: those of its free layout (Adjust places), else those of its layout.
  const placesOf = slide => (Array.isArray(slide?.options?.geometry) && slide.options.geometry.length ? slide.options.geometry : layoutOf(slide?.layout)?.places || []);
  const placeOf = (element, index) => (Number.isInteger(element.place) ? element.place : index);
  const visibleElements = slide => (slide?.elements || []).filter(element => !element.hidden);
  const designCount = () => (state.info?.template?.designs || []).length;
  const editableSlideSet = () => (state.scope === 'template' ? state.template : state.slide_set);
  const parameters = () => (state.active ? state.template?.parameters || state.slide_set?.parameters : state.info?.slide_set?.parameters) || [];

  function loadSlideSet(info) {
    state.info = info;
    state.template = info.template?.slide_set || null;
    state.slide_set = info.slide_set;
    state.overrides = info.overrides;
    state.report = info.report;
    state.summary = info.summary;
    state.detached = Boolean(info.detached);
    state.rights = info.rights || {design: false, template: false};
    state.templateDirty = state.designDirty = state.keepTemplateChanges = false;
    state.history = []; state.future = [];
    if (state.detached || !state.rights.template) state.scope = 'design';
    else if (!state.rights.design) state.scope = 'template';
  }

  async function loadInfo(id) {
    try {
      const info = await api(`/${encodeURIComponent(id)}/slides`);
      if (state.designId !== id || state.active) return;
      state.info = info;
    } catch (_error) {
      if (state.designId === id) state.info = null;
    }
    syncDesignerButton();
    renderParameterValues();
  }

  // ------------------------------------------------------------------
  // Laying out a slide set being edited (the server previews it on the prepared CDRs)
  // ------------------------------------------------------------------
  function preview(body) {
    const run = async () => {
      const token = viewer().state().prepared?.token;
      if (!token) throw new Error('The Design is not prepared yet.');
      setBusy(1);
      try {
        const result = await api('/slides/preview', 'POST', {token, design_id: viewer().state().activeId, ...body});
        state.slide_set = result.slide_set;
        state.overrides = result.overrides;
        state.report = result.report;
        state.summary = result.summary;
        if (!findSlide(state.slide_set, state.slide)) state.slide = editedSlides()[0]?.id || '';
        if (state.element && !findElement(state.slide_set, state.element)) state.element = '';
        viewer().showSlides(result, {sourceSlide: state.slide});
        state.syncedToken = viewer().state().prepared?.token;
        renderDesigner();
        scheduleDraft();
      } finally { setBusy(-1); }
    };
    state.queue = state.queue.catch(() => undefined).then(run);
    state.queue.catch(report);
    return state.queue;
  }
  const previewBody = () => ({
    template_slide_set: state.templateDirty ? state.template : undefined,
    overrides: state.overrides,
  });

  // The unsaved slide set is kept on the server as a draft of this user (Design slide set Drafts), a moment after each change.
  let draftTimer = 0;
  function scheduleDraft() {
    clearTimeout(draftTimer);
    if (!state.active || !dirty()) return;
    const id = viewer().state().activeId;
    draftTimer = setTimeout(() => {
      if (!state.active || !dirty() || viewer().state().activeId !== id) return;
      api(`/${encodeURIComponent(id)}/slides/draft`, 'PUT', {state: {
        template: state.templateDirty ? state.template : null, slide_set: state.slide_set, overrides: state.overrides,
        templateDirty: state.templateDirty, designDirty: state.designDirty, keepTemplateChanges: state.keepTemplateChanges,
        template_updated_at: state.info?.template?.updated_at || '', scope: state.scope, slide: state.slide,
      }}).catch(() => undefined);
    }, 1200);
  }
  const forgetDraft = (id, discarded) => api(`/${encodeURIComponent(id)}/slides/draft${discarded ? '?discarded=1' : ''}`, 'DELETE').catch(() => undefined);
  async function offerDraft(id) {
    let result;
    try { result = await api(`/${encodeURIComponent(id)}/slides/draft`); } catch (_error) { return false; }
    const draft = result?.draft;
    if (!draft) return false;
    const when = result.updated_at ? new Date(result.updated_at).toLocaleString() : 'before';
    const stale = draft.templateDirty && draft.template_updated_at && draft.template_updated_at !== state.info?.template?.updated_at;
    const choice = await window.showConfirmDialog(
      `You have changes in the Designer that were not saved (${when}).${stale ? ' The template changed since: saving them would replace those changes, so the save will ask you to reload first.' : ''}`,
      {title: 'Unsaved changes', confirmLabel: 'Restore', cancelLabel: 'Discard them'});
    if (choice !== true && choice !== 'confirm') { await forgetDraft(id, true); return false; }
    state.history.push(snapshotState());
    if (draft.templateDirty && draft.template) { state.template = draft.template; state.templateDirty = true; state.info.template.updated_at = draft.template_updated_at || state.info.template.updated_at; }
    if (draft.slide_set) state.slide_set = draft.slide_set;
    if (draft.overrides) state.overrides = draft.overrides;
    state.designDirty = Boolean(draft.designDirty);
    state.keepTemplateChanges = Boolean(draft.keepTemplateChanges);
    if (draft.scope && (draft.scope === 'design' ? state.rights.design : state.rights.template && !state.detached)) state.scope = draft.scope;
    if (draft.slide && findSlide(state.slide_set, draft.slide)) state.slide = draft.slide;
    return true;
  }

  const snapshotState = () => ({
    template: clone(state.template), slide_set: clone(state.slide_set), overrides: clone(state.overrides),
    templateDirty: state.templateDirty, designDirty: state.designDirty, keepTemplateChanges: state.keepTemplateChanges,
    slide: state.slide, element: state.element,
  });
  function restoreState(saved) {
    Object.assign(state, {
      template: saved.template, slide_set: saved.slide_set, overrides: saved.overrides, templateDirty: saved.templateDirty,
      designDirty: saved.designDirty, keepTemplateChanges: saved.keepTemplateChanges, slide: saved.slide, element: saved.element,
    });
  }

  // One change of the slide set, in the scope chosen: ``mutate`` changes the slide set given (the template, or the slide set of
  // this Design) and returns false to give up. Changes wait for the one before to be laid out.
  async function edit(mutate, {slide, element, scope} = {}) {
    await state.queue.catch(() => undefined);
    const target = scope || state.scope;
    const before = snapshotState();
    const slide_set = clone(target === 'template' ? state.template : state.slide_set);
    if (!slide_set || mutate(slide_set, target) === false) return;
    if (target === 'template') { state.template = slide_set; state.templateDirty = true; }
    else { state.slide_set = slide_set; state.designDirty = true; }
    state.history.push(before);
    if (state.history.length > 80) state.history.shift();
    state.future = [];
    if (slide !== undefined) state.slide = slide;
    if (element !== undefined) state.element = element;
    renderDesigner();
    try {
      await preview(target === 'template' ? previewBody() : {...previewBody(), slide_set: state.slide_set});
    } catch (_error) {
      // Refused (reported by preview): the slide set goes back to what it was.
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
  // Entering, saving and leaving the Designer
  // ------------------------------------------------------------------
  async function enterDesigner() {
    const {activeId, prepared} = viewer().state();
    if (!activeId) return;
    if (!prepared?.token) throw new Error('Wait until the Design is ready, then open the Designer.');
    setBusy(1);
    try {
      const [info, layouts] = await Promise.all([
        api(`/${encodeURIComponent(activeId)}/slides?edit=1`),
        state.layouts ? Promise.resolve({layouts: state.layouts}) : api('/slides/layouts'),
      ]);
      state.layouts = layouts.layouts;
      loadSlideSet(info);
    } finally { setBusy(-1); }
    if (!state.rights.design && !state.rights.template) throw new Error('You cannot change the slides of this Design or of its template.');
    state.active = true;
    state.syncedToken = prepared.token;
    thumbnails.clear();
    state.slide = prepared.slides?.[viewer().state().slideIndex]?.source_slide || editedSlides()[0]?.id || '';
    state.element = '';
    state.tab = 'slide';
    $('ds-viewer').classList.add('ds-designing');
    $('ds-design-bar').hidden = false;
    $('ds-design-panel').hidden = false;
    renderDesigner();
    loadFields(prepared.token);
    const restored = await offerDraft(activeId);
    // Laid out again with the ids of the slide set (and the draft restored), so each element on the slide is known.
    await preview(restored && state.designDirty ? {...previewBody(), slide_set: state.slide_set} : previewBody());
    viewer().status('Designer: changes are laid out at once and stored when you save them.');
  }

  async function loadFields(token) {
    try { state.fields = await api(`/slides/fields?token=${encodeURIComponent(token)}`); }
    catch (_error) { state.fields = null; }
    if (state.active) renderPanel();
  }

  async function saveSlides() {
    await state.queue.catch(() => undefined);
    if (!dirty()) return;
    clearTimeout(draftTimer);
    const id = viewer().state().activeId;
    if (state.templateDirty) {
      const others = (state.info.template.designs || []).filter(item => item.id !== id);
      const message = others.length
        ? `Save the template “${state.info.template.name}”? It also changes ${others.length} other Design${others.length === 1 ? '' : 's'}: ${others.map(item => item.name).join(', ')}.`
        : `Save the template “${state.info.template.name}”?`;
      if (!await window.showConfirmDialog(message, {title: 'Save template', confirmLabel: 'Save'})) return;
    }
    const body = {};
    if (state.templateDirty) Object.assign(body, {template_slide_set: state.template, template_updated_at: state.info.template.updated_at});
    if (state.detached && state.designDirty) body.slide_set = state.slide_set;
    else if (state.designDirty) body.overrides = state.overrides;
    if (state.keepTemplateChanges) Object.assign(body, {keep_template_changes: true, overrides: state.overrides});
    setBusy(1);
    let info;
    try { info = await api(`/${encodeURIComponent(id)}/slides`, 'PUT', body); } finally { setBusy(-1); }
    const {slide, element} = state;
    loadSlideSet(info);
    state.slide = findSlide(state.slide_set, slide) ? slide : editedSlides()[0]?.id || '';
    state.element = findElement(state.slide_set, element) ? element : '';
    viewer().storeSlides(id, storedSlideFields(info));
    renderDesigner();
    viewer().status('Slides saved.');
  }
  const hasOverrides = overrides => Object.entries(overrides || {}).some(([key, value]) => key !== 'version'
    && (Array.isArray(value) ? value.length : value && typeof value === 'object' && Object.keys(value).length));
  const storedSlideFields = info => ({
    slide_overrides: hasOverrides(info.overrides) ? info.overrides : {},
    own_slides: info.detached ? info.slide_set : null,
  });

  async function discardSlides({ask = true} = {}) {
    await state.queue.catch(() => undefined);
    if (ask && dirty() && !await window.showConfirmDialog('Discard the changes that are not saved?', {title: 'Discard changes', confirmLabel: 'Discard', tone: 'danger'})) return false;
    const id = viewer().state().activeId;
    clearTimeout(draftTimer);
    await forgetDraft(id, true);
    const info = await api(`/${encodeURIComponent(id)}/slides?edit=1`);
    loadSlideSet(info);
    if (!findSlide(state.slide_set, state.slide)) state.slide = editedSlides()[0]?.id || '';
    state.element = '';
    await preview(previewBody());
    return true;
  }

  async function exitDesigner({force = false} = {}) {
    if (!state.active) return true;
    if (!force && dirty()) {
      const choice = await window.showConfirmDialog('The Designer has changes that are not saved.', {
        title: 'Close Designer', confirmLabel: 'Save', secondaryLabel: 'Discard', cancelLabel: 'Keep designing',
      });
      if (choice === 'confirm' || choice === true) await saveSlides();
      else if (choice === 'secondary') await discardSlides({ask: false});
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
      if (state.designId) loadInfo(state.designId);
    }
    return true;
  }

  // ------------------------------------------------------------------
  // Slides
  // ------------------------------------------------------------------
  const newChartElement = (slide_set, place = 0) => {
    const model = shownElement() || editedSlides().flatMap(slide => slide.elements || []).find(element => (element.kind || 'chart') === 'chart');
    const element = model ? clone(model) : {
      kind: 'chart', cdr_source: 'CDR-Data', kpi: 'Mean_Data_Rate', chart_type: 'Average Vertical Bars',
      filters: '', rows_split: 'Operator', columns_split: 'Campaign', legend: '', legend_position: '',
      legend_format: '', label_position: '', label_format: '', axis_x_range: '', axis_y_range: '',
      exclude_null_empty: false, exclude_zero: false, dynamic_rows_field: '', dynamic_columns_field: '',
    };
    for (const mark of ['origin', 'overridden', 'hidden', 'style']) delete element[mark];
    return {...element, id: randomId('e'), kind: 'chart', place, chart_title: 'New chart'};
  };
  function newSlide(slide_set, kind) {
    const slide = {
      id: randomId('s'), kind, title: kind === 'end' ? '' : (kind === 'content' ? 'New slide' : 'New section'),
      subtitle: '', layout: kind === 'content' ? DEFAULT_LAYOUT : STRUCTURAL_LAYOUTS[kind], optional: false, elements: [],
    };
    if (kind !== 'content') slide.chart_type = STRUCTURAL[kind];
    else slide.elements.push(newChartElement(slide_set, 0));
    return slide;
  }
  const insertAfter = (slide_set, slideId, slide) => {
    const index = slide_set.slides.findIndex(item => item.id === slideId);
    slide_set.slides.splice(index < 0 ? slide_set.slides.length : index + 1, 0, slide);
  };
  const addSlide = kind => edit(slide_set => {
    const slide = newSlide(slide_set, kind);
    insertAfter(slide_set, state.slide, slide);
    state.slide = slide.id;
    state.element = slide.elements[0]?.id || '';
  });
  const duplicateSlide = slideId => edit(slide_set => {
    const source = findSlide(slide_set, slideId) || findSlide(state.slide_set, slideId);
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
    insertAfter(slide_set, slideId, copy);
    state.slide = copy.id;
  });
  async function deleteSlide(slideId) {
    const slide = findSlide(editableSlideSet(), slideId);
    if (!slide) return;
    if (state.scope === 'template') {
      const others = designCount();
      if (!await window.showConfirmDialog(`Delete the slide “${slide.title || STRUCTURAL[slideKind(slide)] || 'slide'}” from the template?${others > 1 ? ` The ${others} Designs of the template lose it.` : ''}`, {title: 'Delete slide', confirmLabel: 'Delete', tone: 'danger'})) return;
    }
    await edit(slide_set => {
      const index = slide_set.slides.findIndex(item => item.id === slideId);
      if (index < 0 || slide_set.slides.filter(item => !item.hidden && !item.optional_off).length <= 1) {
        report(new Error('A Design needs at least one slide.'));
        return false;
      }
      slide_set.slides.splice(index, 1);
      state.slide = (slide_set.slides[index] || slide_set.slides[index - 1])?.id || '';
      state.element = '';
    });
  }
  const setSlideHidden = (slideId, hidden) => edit(slide_set => {
    const slide = findSlide(slide_set, slideId);
    if (!slide) return false;
    if (hidden) slide.hidden = true; else delete slide.hidden;
  }, {scope: 'design'});
  const setOptionalShown = (slideId, shown) => edit(slide_set => {
    const slide = findSlide(slide_set, slideId);
    if (!slide) return false;
    if (shown) delete slide.optional_off; else slide.optional_off = true;
  }, {scope: 'design'});
  const setOptional = (slideId, optional) => edit(slide_set => {
    const slide = findSlide(slide_set, slideId);
    if (!slide) return false;
    slide.optional = optional;
  }, {scope: 'template'});
  const moveSlide = (slideId, targetId, after) => edit(slide_set => {
    const index = slide_set.slides.findIndex(item => item.id === slideId);
    if (index < 0 || slideId === targetId) return false;
    const [slide] = slide_set.slides.splice(index, 1);
    const target = slide_set.slides.findIndex(item => item.id === targetId);
    slide_set.slides.splice(target < 0 ? slide_set.slides.length : target + (after ? 1 : 0), 0, slide);
  });
  const canMoveSlide = slide => state.scope === 'template' ? true : !isTemplateSlide(slide) || state.detached;

  // Reset to template: the slide (or element) as the template has it; Apply to template: the template takes it.
  const resetSlide = slideId => edit(slide_set => {
    const original = findSlide(state.template, slideId);
    const index = slide_set.slides.findIndex(item => item.id === slideId);
    if (!original || index < 0) return false;
    const local = (slide_set.slides[index].elements || []).filter(isLocalElement);
    slide_set.slides[index] = {...clone(original), elements: [...clone(original.elements || []), ...local]};
  }, {scope: 'design'});
  const resetElement = elementId => edit(slide_set => {
    const original = findElement(state.template, elementId)?.element;
    const found = findElement(slide_set, elementId);
    if (!original || !found) return false;
    found.slide.elements[found.slide.elements.indexOf(found.element)] = clone(original);
  }, {scope: 'design'});
  async function applyToTemplate({slideId = '', elementId = ''} = {}) {
    if (!state.rights.template) return;
    await state.queue.catch(() => undefined);
    const others = designCount();
    if (!await window.showConfirmDialog(`Make this change part of the template?${others > 1 ? ` The ${others} Designs of the template take it.` : ''}`, {title: 'Apply to template', confirmLabel: 'Apply'})) return;
    const before = snapshotState();
    const template = clone(state.template);
    const clean = item => { const copy = clone(item); for (const mark of ['origin', 'overridden', 'hidden', 'optional_off']) delete copy[mark]; return copy; };
    if (slideId) {
      const shown = findSlide(state.slide_set, slideId);
      if (!shown) return;
      const cleaned = {...clean(shown), elements: (shown.elements || []).filter(element => !element.hidden).map(clean)};
      const index = template.slides.findIndex(item => item.id === slideId);
      if (index >= 0) template.slides[index] = {...cleaned, optional: template.slides[index].optional};
      else {
        // A slide of this Design: after the slide before it, as here.
        const order = editedSlides().map(item => item.id);
        const previous = order.slice(0, order.indexOf(slideId)).reverse().find(id => template.slides.some(item => item.id === id));
        const at = previous ? template.slides.findIndex(item => item.id === previous) + 1 : 0;
        template.slides.splice(at, 0, cleaned);
      }
    } else if (elementId) {
      const found = findElement(state.slide_set, elementId);
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
    state.designDirty = true;
    await preview({...previewBody(), slide_set: state.slide_set});
  }

  // ------------------------------------------------------------------
  // Elements
  // ------------------------------------------------------------------
  const elementLabel = element => element?.chart_title || ({text: 'Text box', image: 'Image', kpi: 'KPI card'}[element?.kind]) || element?.kpi || 'Chart';
  function setElementValues(elementId, values) {
    return edit(slide_set => {
      const found = findElement(slide_set, elementId);
      if (!found) {
        report(new Error('This element is only in this Design: change it in This Design scope, or apply it to the template first.'));
        return false;
      }
      Object.assign(found.element, values);
    });
  }
  // A new element of a kind: a chart (like the one chosen), a KPI card, a text box or a picture.
  function newElement(slide_set, place, kind) {
    const chart = newChartElement(slide_set, place);
    const blank = {cdr_source: '', kpi: '', filters: '', rows_split: '', columns_split: '', legend: '', legend_position: '', legend_format: '',
      label_position: '', label_format: '', axis_x_range: '', axis_y_range: '', exclude_null_empty: false, exclude_zero: false,
      dynamic_rows_field: '', dynamic_columns_field: ''};
    if (kind === 'kpi') {
      return {...chart, kind: 'kpi', chart_type: 'KPI Card', chart_title: 'KPI', rows_split: 'Campaign', columns_split: '', legend: '',
        kpi_card: {measure: 'average', comparison: 'previous', sparkline: true}};
    }
    if (kind === 'text') return {...blank, id: chart.id, kind: 'text', place, chart_type: 'Text Box', chart_title: '', content: {text: 'Write the text of this box.', size: 'medium', align: 'left'}};
    if (kind === 'image') return {...blank, id: chart.id, kind: 'image', place, chart_type: 'Image', chart_title: '', content: {image: '', fit: 'contain'}};
    return chart;
  }
  const addElement = (slideId, place, kind = 'chart') => edit(slide_set => {
    const slide = findSlide(slide_set, slideId);
    if (!slide) return false;
    const element = newElement(slide_set, place, kind);
    slide.elements = [...(slide.elements || []), element];
    state.element = element.id;
    state.tab = 'element';
  });
  async function deleteElement(elementId) {
    await edit(slide_set => {
      const found = findElement(slide_set, elementId);
      if (!found) return false;
      if (visibleElements(found.slide).length <= 1) {
        report(new Error('A slide keeps at least one element: delete the slide instead.'));
        return false;
      }
      if (state.scope === 'design' && !state.detached && !isLocalElement(found.element)) found.element.hidden = true;
      else found.slide.elements.splice(found.slide.elements.indexOf(found.element), 1);
      state.element = '';
    });
  }
  const duplicateElement = elementId => edit(slide_set => {
    const found = findElement(slide_set, elementId);
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
  const pasteElement = (slideId, place) => edit(slide_set => {
    const slide = findSlide(slide_set, slideId);
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
  const moveElement = (elementId, place) => edit(slide_set => {
    const found = findElement(slide_set, elementId);
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
    const slide = findSlide(editableSlideSet(), slideId);
    if (!slide || slide.layout === name) return;
    const capacity = layoutOf(name)?.places?.length || 0;
    const elements = visibleElements(slide);
    if (slideKind(slide) === 'content' && capacity && elements.length > capacity) {
      const extra = elements.length - capacity;
      if (!await window.showConfirmDialog(`The layout ${name} has ${capacity} place${capacity === 1 ? '' : 's'}: the last ${extra} element${extra === 1 ? '' : 's'} of the slide will be removed.`, {title: 'Change layout', confirmLabel: 'Change layout', tone: 'danger'})) return;
    }
    await edit(slide_set => {
      const target = findSlide(slide_set, slideId);
      if (!target) return false;
      target.layout = name;
      // The places adjusted on the layout of before do not apply to another one.
      if (target.options) { delete target.options.geometry; delete target.options.grid; }
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
        // Left out of the layout: removed, or hidden here when it is an element of the template (This Design).
        if (state.scope === 'design' && !state.detached && !isLocalElement(element)) element.hidden = true;
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
    const count = designCount();
    const differences = Object.values(state.summary || {}).reduce((total, value) => total + Number(value || 0), 0);
    const changed = (state.report?.template_changed || []).length;
    bar.replaceChildren(
      h('div', {class: 'ds-design-bar-group'},
        h('span', {class: 'ds-design-bar-label', text: 'Designer'}),
        state.detached
          ? h('span', {class: 'ds-design-pill ds-design-pill-detached', title: `Detached from ${state.info?.template?.name || 'its template'}: it keeps slides of its own`, text: 'Detached'})
          : h('div', {class: 'ds-design-scopes', role: 'group', 'aria-label': 'Change'},
            scopeButton('design', 'This Design', 'Changes only this Design: kept as its differences from the template', state.rights.design),
            scopeButton('template', `Template · ${count} Design${count === 1 ? '' : 's'}`, `Changes the template ${state.info?.template?.name || ''}: every Design that follows it`, state.rights.template))),
      h('div', {class: 'ds-design-bar-group'},
        h('button', {type: 'button', class: 'ds-design-tool', title: 'Undo (Ctrl/Cmd+Z)', 'aria-label': 'Undo', disabled: !state.history.length, onclick: guarded(undo)}, '↶'),
        h('button', {type: 'button', class: 'ds-design-tool', title: 'Redo (Shift+Ctrl/Cmd+Z)', 'aria-label': 'Redo', disabled: !state.future.length, onclick: guarded(redo)}, '↷'),
        h('button', {type: 'button', class: 'ds-design-action', onclick: guarded(openParametersDialog), disabled: state.detached ? false : !state.rights.template && !parameters().length, title: 'The parameters of the template'}, `Parameters${parameters().length ? ` · ${parameters().length}` : ''}`),
        state.detached ? null : h('button', {type: 'button', class: `ds-design-action${changed ? ' has-warning' : ''}`, onclick: guarded(openDifferencesDialog), title: 'What this Design changes of its template'}, `Differences · ${differences}${changed ? ` · ${changed} template changed` : ''}`)),
      h('div', {class: 'ds-design-bar-group ds-design-bar-end'},
        h('span', {class: 'ds-design-busy', id: 'ds-design-busy', hidden: state.busy === 0, text: 'Laying out…'}),
        dirty() ? h('span', {class: 'ds-design-pill ds-design-pill-unsaved', text: state.templateDirty ? 'Unsaved template' : 'Unsaved'}) : null,
        h('button', {type: 'button', class: 'ds-design-action ds-design-primary', disabled: !dirty(), onclick: guarded(saveSlides)}, 'Save'),
        h('button', {type: 'button', class: 'ds-design-action', disabled: !dirty(), onclick: guarded(() => discardSlides())}, 'Discard'),
        h('button', {type: 'button', class: 'ds-design-action', 'aria-haspopup': 'menu', onclick: event => openMenu(event.currentTarget, moreActions())}, 'More ▾'),
        h('button', {type: 'button', class: 'ds-design-action', onclick: guarded(() => exitDesigner())}, 'Close Designer')),
    );
  }
  const moreActions = () => [
    ['Save as template…', guarded(saveAsTemplate), !dirty() || 'Save or discard the changes first'],
    ['Save as my Design…', guarded(saveAsMyDesign), !state.templateDirty || 'Save or discard the changes of the template first'],
    state.detached ? null : ['Detach from template…', guarded(detachDesign), state.rights.design && (!dirty() || 'Save or discard the changes first')],
  ].filter(Boolean);

  // The places of a slide as boxes: its outline while it is not laid out (left out, or a change still being laid out), or
  // the marks of what this Design changes over its picture (outline false).
  function slideBoxes(frame, slide, outline = true) {
    if (slideKind(slide) !== 'content') {
      if (outline) frame.append(h('span', {class: 'ds-design-slide-structural', text: STRUCTURAL[slideKind(slide)] || 'Slide'}));
      return frame;
    }
    const places = placesOf(slide);
    visibleElements(slide).forEach((element, index) => {
      const place = places[placeOf(element, index)];
      const changed = element.overridden?.length, local = isLocalElement(element);
      if (!place || (!outline && !changed && !local)) return;
      const [left, top, width, height] = place;
      frame.append(h('span', {
        class: `ds-design-slide-box${outline ? '' : ' is-mark'}${changed ? ' is-changed' : ''}${local ? ' is-local' : ''}`,
        style: {left: `${left}%`, top: `${top}%`, width: `${width}%`, height: `${height}%`}, title: elementLabel(element),
      }));
    });
    return frame;
  }
  // Each slide of the list in small as the viewer lays it out (charts, KPI cards, text boxes, pictures and covers), drawn
  // when in sight and again only when the slide, the slide set around it or the data change; while a change is still being
  // laid out, the slide keeps its last picture.
  const thumbnails = new Map();
  const thumbnailObserver = 'IntersectionObserver' in window ? new IntersectionObserver(entries => entries.forEach(entry => {
    if (!entry.isIntersecting) return;
    thumbnailObserver.unobserve(entry.target);
    drawThumbnail(entry.target);
  }), {rootMargin: '240px 0px'}) : null;
  function thumbnailKey(slide) {
    const {slides, ...around} = state.slide_set || {};
    const position = editedSlides().findIndex(item => item.id === slide.id);
    return JSON.stringify([slide, position, around, state.overrides?.filters || null, state.generation]);
  }
  function drawThumbnail(frame) {
    const slide = findSlide(state.slide_set, frame.dataset.slideId);
    if (!slide || !frame.isConnected) return;
    if (!viewer().drawThumbnail?.(frame, slide.id)) { frame.replaceChildren(); slideBoxes(frame, slide); return; }
    slideBoxes(frame, slide, false);
  }
  function frameBoxes(slide) {
    const laidOut = viewer().state().prepared?.token === state.syncedToken;
    const cached = thumbnails.get(slide.id);
    const leftOut = slide.hidden || slide.optional_off;
    if (cached && (!laidOut || cached.key === thumbnailKey(slide)) && cached.leftOut === leftOut) return cached.frame;
    const frame = h('span', {class: 'ds-design-slide-frame ds-slide-thumbnail-frame', dataset: {slideId: slide.id}});
    // Left out of this Design, or not laid out yet: its places only (drawn again once laid out).
    if (leftOut || !laidOut) {
      slideBoxes(frame, slide);
      thumbnails.set(slide.id, {key: leftOut && laidOut ? thumbnailKey(slide) : null, frame, leftOut});
      return frame;
    }
    slideBoxes(frame, slide);
    thumbnails.set(slide.id, {key: thumbnailKey(slide), frame, leftOut});
    if (thumbnailObserver) thumbnailObserver.observe(frame); else requestAnimationFrame(() => drawThumbnail(frame));
    return frame;
  }
  function slideBadges(slide) {
    const badges = [];
    if (slide.hidden) badges.push(['Hidden here', 'is-hidden']);
    if (slide.optional && slide.optional_off) badges.push(['Optional · off', 'is-hidden']);
    else if (slide.optional) badges.push(['Optional', 'is-optional']);
    if (slide.origin === 'design' && !state.detached) badges.push(['This Design', 'is-local']);
    if (slide.overridden?.length || (slide.elements || []).some(element => element.overridden?.length || element.hidden || isLocalElement(element))) badges.push(['Changed here', 'is-changed']);
    if ((state.report?.template_changed || []).some(item => item.slide === slide.id || (slide.elements || []).some(element => element.id === item.element))) badges.push(['Template changed', 'is-warning']);
    return badges.length ? h('span', {class: 'ds-design-slide-badges'}, badges.map(([text, kind]) => h('span', {class: `ds-design-badge ${kind}`, text}))) : null;
  }
  function renderSorter() {
    const nav = $('ds-slide-thumbnails');
    if (!nav) return;
    let number = 0;
    const items = editedSlides().map(slide => {
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
      actions.push(['Delete', guarded(() => deleteSlide(slide.id)), Boolean(findSlide(state.template, slide.id)) || 'Only in this Design: delete it in This Design scope']);
    } else if (fromTemplate) {
      if (slide.optional) actions.push([slide.optional_off ? 'Show in this Design' : 'Leave out of this Design', guarded(() => setOptionalShown(slide.id, Boolean(slide.optional_off))), true]);
      else actions.push([slide.hidden ? 'Show again' : 'Hide in this Design', guarded(() => setSlideHidden(slide.id, !slide.hidden)), true]);
      if (slide.overridden?.length || (slide.elements || []).some(element => element.overridden?.length || element.hidden)) actions.push(['Reset to template', guarded(() => resetSlide(slide.id)), true]);
    } else actions.push(['Delete', guarded(() => deleteSlide(slide.id)), true]);
    if (!template && !state.detached && state.rights.template && (slide.origin === 'design' || slide.overridden?.length || (slide.elements || []).some(element => element.overridden?.length || element.hidden || isLocalElement(element)))) {
      actions.push(['Apply to template', guarded(() => applyToTemplate({slideId: slide.id})), true]);
    }
    return actions;
  }

  function selectSlide(slideId) {
    state.slide = slideId;
    state.element = '';
    state.tab = 'slide';
    const index = (viewer().state().prepared?.slides || []).findIndex(slide => slide.source_slide === slideId);
    if (index >= 0 && !(findSlide(state.slide_set, slideId)?.hidden || findSlide(state.slide_set, slideId)?.optional_off)) viewer().goToSlide(index);
    else showLeftOutSlide();
    renderDesigner();
  }
  // A slide the Design leaves out (hidden, or optional and off) is not laid out: the stage says so.
  function showLeftOutSlide() {
    const slide = shownSlide();
    const stage = $('ds-charts');
    if (!slide || !stage) return;
    stage.classList.remove('ds-positioned');
    $('ds-title').textContent = slide.title || STRUCTURAL[slideKind(slide)] || '';
    $('ds-subtitle').textContent = slide.subtitle || '';
    const notice = h('div', {class: 'ds-design-left-out'},
      h('p', {text: slide.hidden ? 'This slide of the template is hidden in this Design.' : 'This optional slide of the template is off in this Design.'}),
      h('button', {type: 'button', class: 'ds-design-action ds-design-primary',
        onclick: guarded(() => (slide.hidden ? setSlideHidden(slide.id, false) : setOptionalShown(slide.id, true)))}, slide.hidden ? 'Show again' : 'Show in this Design'));
    stage.replaceChildren(notice);
  }

  // The slide shown: each element can be chosen and dragged to another place; the free places of its layout take a new one.
  function decorateStage() {
    if (!state.active) return;
    const stage = $('ds-charts');
    const rendered = viewer().state().prepared?.slides?.[viewer().state().slideIndex];
    if (!stage || !rendered) return;
    if (rendered.source_slide && rendered.source_slide !== state.slide) {
      const slide = findSlide(state.slide_set, rendered.source_slide);
      if (slide && !slide.hidden && !slide.optional_off) state.slide = rendered.source_slide;
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
      const found = findElement(state.slide_set, id);
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
        card.querySelector('canvas')?.addEventListener('designchartlayout', () => {
          if (state.active && card.dataset.elementId === state.element && $('ds-design-panel')?.querySelector('.ds-design-series-list .ds-design-empty')) renderPanel();
        });
        // A click on an entry of the legend of the chart chosen formats that series (instead of hiding it).
        card.addEventListener('click', event => {
          if (!state.active || card.dataset.elementId !== state.element || event.target.tagName !== 'CANVAS') return;
          const item = globalThis.getCanvasChartLegendItemAt?.(event.target, event);
          const axis = item ? null : globalThis.getCanvasChartAxisAt?.(event.target, event);
          if (!item && !axis) return;
          event.preventDefault();
          event.stopPropagation();
          if (item) openSeriesFormat(card, card.dataset.elementId, item.label, event);
          else if (axis.kind === 'numeric') openAxisRange(card, card.dataset.elementId, axis, event);
          else openAxisValues(card, card.dataset.elementId, axis, event);
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
          const target = findElement(state.slide_set, card.dataset.elementId);
          if (!target) return;
          const index = visibleElements(target.slide).indexOf(target.element);
          guarded(() => moveElement(state.dragElement, placeOf(target.element, index)))();
        });
      }
      if (!found) return;
      const marks = [];
      if (isLocalElement(found.element) && !state.detached) marks.push(['This Design', 'is-local']);
      else if (found.element.overridden?.length) marks.push(['Changed here', 'is-changed']);
      if ((state.report?.template_changed || []).some(item => item.element === id)) marks.push(['Template changed', 'is-warning']);
      if (marks.length) card.append(h('span', {class: 'ds-design-mark'}, marks.map(([text, kind]) => h('span', {class: `ds-design-badge ${kind}`, text}))));
    });
    // A dynamic layout fills its grid with the cards of one element: it has no free place of its own.
    if (!slide || slideKind(slide) !== 'content' || layoutOf(slide.layout)?.dynamic || !stage.classList.contains('ds-positioned')) return;
    const places = placesOf(slide);
    for (const place of freePlaces(slide)) {
      const [left, top, width, height] = places[place];
      const free = h('div', {class: 'ds-design-free-place', style: {left: `${left}%`, top: `${top}%`, width: `${width}%`, height: `${height}%`}},
        h('button', {type: 'button', class: 'ds-design-add-element', 'aria-haspopup': 'menu', onclick: event => openMenu(event.currentTarget, [
          ['Chart', guarded(() => addElement(slide.id, place, 'chart')), true],
          ['KPI card', guarded(() => addElement(slide.id, place, 'kpi')), true],
          ['Text box', guarded(() => addElement(slide.id, place, 'text')), true],
          ['Image', guarded(() => addElement(slide.id, place, 'image')), true],
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
    if (!findElement(state.slide_set, elementId)) return;
    state.element = elementId;
    state.tab = 'element';
    state.folded = false;
    renderPanel();
    $('ds-charts')?.querySelectorAll('.ds-chart').forEach(card => card.classList.toggle('is-selected', card.dataset.elementId === elementId));
  }
  function elementActions(elementId) {
    const found = findElement(state.slide_set, elementId);
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
  // append: the token goes at the end (a text box, whose editor keeps its own caret).
  function tokenMenuButton(input, {append = false} = {}) {
    return h('button', {type: 'button', class: 'ds-design-token', title: 'Insert a field: NR Mode, the selection of the Design (Campaigns, Operators, Cities…) or a parameter', 'aria-haspopup': 'menu',
      onclick: event => openMenu(event.currentTarget, [...BUILT_IN_TOKENS, ...parameters().map(item => `{${item.name}}`)].map(token => [token, () => {
        const start = append ? input.value.length : input.selectionStart ?? input.value.length;
        const end = append ? input.value.length : input.selectionEnd ?? input.value.length;
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
    // While a text is being written in the rich text editor of a text box, its panel stays as it is (the caret too).
    const panelKey = `${state.tab}|${state.element}|${state.slide}|${state.scope}`;
    if (panel.dataset.key === panelKey && document.activeElement?.closest?.('#ds-design-panel [contenteditable="true"]')) return;
    panel.dataset.key = panelKey;
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
    const scopeNote = state.detached ? 'This Design has slides of its own.'
      : state.scope === 'template' ? `Changes the template: ${designCount()} Design${designCount() === 1 ? '' : 's'} follow it.`
        : 'Changes only this Design.';
    const fold = h('button', {type: 'button', class: 'ds-design-fold', 'aria-expanded': String(!state.folded), title: state.folded ? 'Show the panel' : 'Fold the panel',
      onclick: () => { state.folded = !state.folded; renderPanel(); }}, state.folded ? '▴' : '▾');
    panel.classList.toggle('is-folded', state.folded);
    panel.replaceChildren(h('div', {class: 'ds-design-panel-head'}, h('div', {class: 'ds-design-panel-top'}, tabs, fold), h('p', {class: `ds-design-scope-note is-${state.detached ? 'design' : state.scope}`, text: scopeNote})), body);
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
    if (item.origin === 'design') return h('p', {class: 'ds-design-origin is-local', text: `This ${kind} is only in this Design.`});
    if (item.overridden?.length) return h('p', {class: 'ds-design-origin is-changed', text: `Changed here: ${item.overridden.join(', ').replaceAll('_', ' ')}.`});
    return h('p', {class: 'ds-design-origin', text: `As the template has it.`});
  }

  function slideForm(slide) {
    const kind = slideKind(slide);
    const editable = state.scope === 'design' || Boolean(findSlide(state.template, slide.id));
    const setSlide = values => edit(slide_set => {
      const target = findSlide(slide_set, slide.id);
      if (!target) { report(new Error('This slide is only in this Design: change it in This Design scope.')); return false; }
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
    const grid = layoutOf(shownSource.layout)?.grid;
    if (kind === 'content' && grid && window.PlacesEditor) {
      nodes.push(h('button', {type: 'button', class: 'ds-design-action', disabled: !editable, title: 'Resize the rows and columns of the layout, merge places or split them',
        onclick: () => adjustPlaces(slide.id)}, shownSource.options?.geometry ? 'Adjust places… (adjusted)' : 'Adjust places…'));
    }
    if (state.scope === 'template' && findSlide(state.template, slide.id)) {
      nodes.push(h('label', {class: 'ds-design-check'}, h('input', {type: 'checkbox', checked: Boolean(findSlide(state.template, slide.id).optional), onchange: event => guarded(() => setOptional(slide.id, event.target.checked))()}), 'Optional: off in each Design until it is shown there'));
    }
    if (kind === 'content') {
      const elements = visibleElements(slide);
      nodes.push(h('h4', {class: 'ds-design-subtitle', text: `Elements · ${elements.length} of ${placesOf(slide).length || elements.length} places`}));
      nodes.push(h('ul', {class: 'ds-design-element-list'}, elements.map((item, index) => h('li', {},
        h('button', {type: 'button', onclick: () => selectElement(item.id)},
          h('span', {class: 'ds-design-place', text: String(placeOf(item, index) + 1)}), elementLabel(item),
          isLocalElement(item) && !state.detached ? h('span', {class: 'ds-design-badge is-local', text: 'This Design'}) : item.overridden?.length ? h('span', {class: 'ds-design-badge is-changed', text: 'Changed'}) : null)))));
      if (freePlaces(slide).length) nodes.push(h('button', {type: 'button', class: 'ds-design-action', onclick: guarded(() => addElement(slide.id, freePlaces(slide)[0]))}, '+ Add chart'));
    }
    nodes.push(h('div', {class: 'ds-design-panel-actions'}, slideActions(slide).map(([label, action, enabled]) => h('button', {type: 'button', class: 'ds-design-action', disabled: enabled !== true, title: typeof enabled === 'string' ? enabled : null, onclick: action}, label))));
    return nodes;
  }

  // The values of a field in the Design's selection with their samples, for the filter dialogs (one read each).
  const fieldValueReads = new Map();
  function fieldValues(source, field) {
    const token = viewer().state().prepared?.token;
    const key = `${token}|${source}|${field}`;
    if (!fieldValueReads.has(key)) {
      fieldValueReads.set(key, api(`/slides/values?token=${encodeURIComponent(token)}&source=${encodeURIComponent(source)}&field=${encodeURIComponent(field)}`)
        .then(result => result.values || []).catch(() => []));
    }
    return fieldValueReads.get(key);
  }
  // The filters of the Design apply to every chart: the Filters shelf shows them first, locked.
  function lockedFilters() {
    const definition = viewer().state().definition || {};
    const label = value => String(value).replace(/^@latest-campaign$/, 'Latest campaign').replace(/^@latest-(\d+)-campaigns$/, 'Latest $1 campaigns')
      .replace(/^@previous-campaign$/, 'Previous campaign').replace(/^@main-cities$/, 'Main Cities');
    return Object.entries(definition.filters || {}).filter(([, values]) => Array.isArray(values) && values.length)
      .map(([name, values]) => `${name}: ${values.slice(0, 2).map(label).join(', ')}${values.length > 2 ? ` +${values.length - 2}` : ''}`);
  }

  // ------------------------------------------------------------------
  // Format of a chart (phase 3): series, legend, labels and axes, kept in its style (see formattedPayload in
  // canvas_charts.js). The colours of Operator / Vendor Maps stay unless a series is given one; Default gives it back.
  // ------------------------------------------------------------------
  const SIZES = [['', 'Default'], ['Small', 'Small'], ['Medium', 'Medium'], ['Large', 'Large']];
  const DASH_NAMES = [['', 'Default'], ['solid', 'Solid'], ['dashed', 'Dashed'], ['dotted', 'Dotted']];
  const cardCanvas = elementId => [...($('ds-charts')?.querySelectorAll('.ds-chart') || [])].find(card => card.dataset.elementId === elementId)?.querySelector('canvas');
  const legendItems = elementId => { const canvas = cardCanvas(elementId); return canvas && globalThis.getCanvasChartLegendItems ? globalThis.getCanvasChartLegendItems(canvas) : []; };
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
    const current = findElement(editableSlideSet(), elementId)?.element;
    if (!current) { report(new Error('This element is only in this Design: change it in This Design scope, or apply it to the template first.')); return undefined; }
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
    const element = findElement(editableSlideSet(), elementId)?.element;
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
  // The range of a numeric axis, chosen with a slider of two thumbs (as in Tableau): applied when a thumb is released;
  // Automatic gives the axis its own range back. The Y axis of a CDF is in percent (0–100).
  function openAxisRange(anchor, elementId, axis, event) {
    closeMenus();
    const key = axis.axis === 'y' ? 'axis_y_range' : 'axis_x_range';
    const low = Math.min(axis.extent[0], axis.domain[0]), high = Math.max(axis.extent[1], axis.domain[1]);
    const span = high - low || 1;
    const decimals = axis.percent ? 0 : Math.max(0, Math.min(4, 2 - Math.floor(Math.log10(span))));
    const step = Number((span / 200).toFixed(decimals)) || 10 ** -decimals;
    const round = value => Number(Number(value).toFixed(decimals));
    let start = round(axis.domain[0]), end = round(axis.domain[1]);
    const from = h('input', {type: 'range', min: String(round(low)), max: String(round(high)), step: String(step), value: String(start), 'aria-label': 'Start of the axis'});
    const to = h('input', {type: 'range', min: String(round(low)), max: String(round(high)), step: String(step), value: String(end), 'aria-label': 'End of the axis'});
    const fromNumber = h('input', {type: 'number', step: String(step), value: String(start), 'aria-label': 'Start'});
    const toNumber = h('input', {type: 'number', step: String(step), value: String(end), 'aria-label': 'End'});
    const track = h('span', {class: 'ds-axis-track-fill'});
    const paint = () => {
      track.style.left = `${(start - low) / span * 100}%`;
      track.style.width = `${Math.max(0, end - start) / span * 100}%`;
      fromNumber.value = String(start); toNumber.value = String(end);
    };
    let timer = 0;
    const commit = () => {
      clearTimeout(timer);
      timer = setTimeout(() => guarded(() => setElementValues(elementId, {[key]: `[${start},${end}]`}))(), 150);
    };
    from.addEventListener('input', () => { start = Math.min(round(from.value), end - step); from.value = String(start); paint(); });
    to.addEventListener('input', () => { end = Math.max(round(to.value), start + step); to.value = String(end); paint(); });
    from.addEventListener('change', commit); to.addEventListener('change', commit);
    fromNumber.addEventListener('change', () => { start = Math.min(round(fromNumber.value), end - step); from.value = String(start); paint(); commit(); });
    toNumber.addEventListener('change', () => { end = Math.max(round(toNumber.value), start + step); to.value = String(end); paint(); commit(); });
    const popover = h('div', {class: 'ds-design-popover ds-axis-range', role: 'dialog', 'aria-label': 'Range of the axis'},
      h('h4', {text: `${axis.axis === 'y' ? 'Y' : 'X'} axis range${axis.percent ? ' (%)' : ''}`}),
      h('div', {class: 'ds-axis-slider'}, h('span', {class: 'ds-axis-track'}), track, from, to),
      h('div', {class: 'ds-axis-scale'}, h('span', {text: String(round(low))}), h('span', {text: String(round(high))})),
      h('div', {class: 'ds-axis-inputs'}, h('label', {}, 'Start', fromNumber), h('label', {}, 'End', toNumber)),
      h('div', {class: 'ds-design-format-actions'},
        h('button', {type: 'button', title: 'The range the chart takes from its values', onclick: () => { closeMenus(); guarded(() => setElementValues(elementId, {[key]: ''}))(); }}, 'Automatic'),
        h('button', {type: 'button', onclick: closeMenus}, 'Close')));
    placePopover(popover, anchor, event);
    paint();
  }
  // The values of a category axis (a level of its split): unticked ones are left out of the chart (a filter of the
  // chart on that field, NOT IN), Show all puts them back.
  function openAxisValues(anchor, elementId, axis, event) {
    closeMenus();
    const element = findElement(editableSlideSet(), elementId)?.element;
    const field = axis.dimension;
    if (!element || !field) return;
    const pattern = new RegExp(`^${field.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s+NOT\\s+IN\\s*\\((.*)\\)$`, 'i');
    const conditions = (element.filters || '').split(/;|\n+/).map(item => item.trim()).filter(Boolean);
    const current = conditions.find(item => pattern.test(item));
    const excluded = new Set(current ? pattern.exec(current)[1].split(',').map(item => item.trim()).filter(Boolean) : []);
    const values = [...new Set([...(axis.values || []), ...excluded])];
    const write = () => {
      const kept = conditions.filter(item => !pattern.test(item));
      if (excluded.size) kept.push(`${field} NOT IN (${[...excluded].join(', ')})`);
      guarded(() => setElementValues(elementId, {filters: kept.join('; ')}))();
    };
    const list = h('div', {class: 'ds-axis-values'}, values.map(value => h('label', {class: 'ds-axis-value'},
      h('input', {type: 'checkbox', checked: !excluded.has(value), onchange: event2 => { if (event2.target.checked) excluded.delete(value); else excluded.add(value); write(); }}),
      h('span', {text: value}))));
    const popover = h('div', {class: 'ds-design-popover ds-axis-range', role: 'dialog', 'aria-label': `Values of ${field}`},
      h('h4', {text: `${field} on the axis`}),
      h('p', {class: 'ds-design-field-note', text: 'Untick the values the chart leaves out.'}),
      list,
      h('div', {class: 'ds-design-format-actions'},
        h('button', {type: 'button', onclick: () => { excluded.clear(); values.filter(value => value !== axis.value).forEach(value => excluded.add(value)); closeMenus(); write(); }}, `Only “${axis.value}”`),
        h('button', {type: 'button', disabled: !excluded.size, onclick: () => { excluded.clear(); closeMenus(); write(); }}, 'Show all'),
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

  // The panel of a KPI card: what it measures, against what, and how it looks.
  function kpiForm(element, shown) {
    const settings = {measure: 'average', comparison: 'previous', ...(shown.kpi_card || {})};
    const setKpi = values => setElementValues(element.id, {kpi_card: {...settings, ...values}});
    const setNow = values => guarded(() => setKpi(values))();
    const later = key => debounced(value => setKpi({[key]: value}));
    const source = String(shown.cdr_source || 'CDR-Data');
    const fields = state.fields?.fields?.[source.toLowerCase()] || [];
    const kpiField = selectInput([['', 'Choose a field'], ...fields.map(item => [item.name, `${item.type === 'number' ? '#' : 'Abc'} · ${item.name}`])], shown.kpi,
      value => guarded(() => setElementValues(element.id, {kpi: value}))(), 'ds-design-kpi-field');
    const repeat = settings.repeat || '';
    const title = textInput(shown.chart_title, debounced(value => setElementValues(element.id, {chart_title: value})), {id: 'ds-design-chart-title'});
    const measure = settings.measure;
    return [
      field('Title', h('div', {class: 'ds-design-input-row'}, title, tokenMenuButton(title))),
      h('div', {class: 'ds-design-two'},
        field('Source', selectInput(SOURCES, source, value => guarded(() => setElementValues(element.id, {cdr_source: value}))(), 'ds-design-kpi-source')),
        field('Field', kpiField)),
      h('div', {class: 'ds-design-two'},
        field('Figure', selectInput([['average', 'Average'], ['median', 'Median'], ['percentile', 'Percentile'], ['count', 'Count of samples'],
          ['share_value', 'Share of a value (%)'], ['share_below', 'Share below a threshold (%)'], ['share_above', 'Share above a threshold (%)']], measure, value => setNow({measure: value}))),
        measure === 'share_value' ? field('Value(s)', textInput(settings.value, later('value'), {id: 'ds-design-kpi-value', placeholder: 'Completed'}))
          : measure === 'percentile' ? field('Percentile', textInput(settings.percentile, later('percentile'), {id: 'ds-design-kpi-percentile', placeholder: '90'}))
            : ['share_below', 'share_above'].includes(measure) ? field('Threshold', textInput(settings.threshold, later('threshold'), {id: 'ds-design-kpi-threshold', placeholder: '1.6'}))
              : field('Unit', textInput(settings.unit, later('unit'), {id: 'ds-design-kpi-unit', placeholder: 'Mbit/s'}))),
      h('div', {class: 'ds-design-two'},
        field('Compared with', selectInput([['previous', 'Previous campaign'], ['best', 'Best competitor'], ['target', 'A target'], ['none', 'Nothing']], settings.comparison, value => setNow({comparison: value}))),
        settings.comparison === 'target' ? field('Target', textInput(settings.target, later('target'), {id: 'ds-design-kpi-target'})) : field('Decimals', textInput(settings.decimals, later('decimals'), {id: 'ds-design-kpi-decimals', placeholder: 'Auto'}))),
      h('div', {class: 'ds-design-two'},
        field('One card per', selectInput([['', 'None (one card)'], ['Operator', 'Operator'], ['Vendor', 'Vendor'], ['Region', 'Region'], ['City', 'City']], repeat,
          value => guarded(() => setElementValues(element.id, {kpi_card: {...settings, repeat: value}, rows_split: value ? `${value} × Campaign` : 'Campaign'}))())),
        h('label', {class: 'ds-design-check'}, h('input', {type: 'checkbox', checked: settings.higher_is_better !== false, onchange: event => setNow({higher_is_better: event.target.checked})}), 'Higher is better')),
      h('div', {class: 'ds-design-two'},
        field('Good from', textInput(settings.bands?.good, debounced(value => setKpi({bands: {...(settings.bands || {}), good: value}})), {id: 'ds-design-kpi-good', placeholder: 'No band'})),
        field('Poor from', textInput(settings.bands?.poor, debounced(value => setKpi({bands: {...(settings.bands || {}), poor: value}})), {id: 'ds-design-kpi-poor', placeholder: 'No band'}))),
      h('label', {class: 'ds-design-check'}, h('input', {type: 'checkbox', checked: Boolean(settings.sparkline), onchange: event => setNow({sparkline: event.target.checked})}), 'Trend over the campaigns'),
      field('Filters', textInput((shown.filters || '').split(/;\s*/).filter(Boolean).join('\n'), debounced(value => setElementValues(element.id, {filters: value.split(/\n+/).map(line => line.trim()).filter(Boolean).join('; ')})), {id: 'ds-design-filters', multiline: true, rows: 3, placeholder: 'Call_Family IN (VoLTE)'}), 'One condition per line; a parameter is written {Name}.'),
      h('p', {class: 'ds-design-field-note', text: 'The figure is that of the latest campaign of the Design\'s selection; green when it improves on what it is compared with, red when it worsens.'}),
    ];
  }

  // The panel of a text box (Markdown, with the editor of the tickets and NQ) or of a picture.
  function textForm(element, shown) {
    const content = {...(shown.content || {})};
    const setContent = values => setElementValues(element.id, {content: {...content, ...values}});
    const area = h('textarea', {id: 'ds-design-text', rows: 8, 'aria-label': 'Text of the box', spellcheck: 'true'}, content.text || '');
    area.addEventListener('input', debounced(() => setContent({text: area.value}), 800));
    queueMicrotask(() => { if (window.RichText && area.isConnected) window.RichText.attach(area, {label: 'Text'}); });
    return [
      field('Text', h('div', {class: 'ds-design-input-row'}, area, tokenMenuButton(area, {append: true})),
        'Bold, bullet lists and headings are kept in the PPT; the fields ({Campaigns}, {Cities}…) and parameters are written in the text.'),
      h('div', {class: 'ds-design-two'},
        field('Size', selectInput([['small', 'Small'], ['medium', 'Medium'], ['large', 'Large']], content.size || 'medium', value => guarded(() => setContent({size: value}))())),
        field('Align', selectInput([['left', 'Left'], ['center', 'Centre'], ['right', 'Right']], content.align || 'left', value => guarded(() => setContent({align: value}))()))),
      field('Colour', h('div', {class: 'ds-design-input-row'},
        h('input', {type: 'color', value: content.colour || '#263B4A', 'aria-label': 'Text colour', onchange: event => guarded(() => setContent({colour: event.target.value.toUpperCase()}))()}),
        h('button', {type: 'button', class: 'ds-design-token', title: 'Default colour', onclick: () => guarded(() => setContent({colour: ''}))()}, '↺'))),
    ];
  }
  function imageForm(element, shown) {
    const content = {...(shown.content || {})};
    const input = h('input', {type: 'file', accept: 'image/png,image/jpeg,image/gif', 'aria-label': 'Picture', onchange: guarded(async event => {
      const file = event.target.files?.[0];
      if (!file) return;
      const body = new FormData();
      body.append('file', file);
      const response = await fetch('/api/ppt-designer/images', {method: 'POST', body, credentials: 'same-origin'});
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'The picture could not be kept.');
      await setElementValues(element.id, {content: {...content, image: result.id, name: result.name}});
    })});
    return [
      content.image ? h('img', {class: 'ds-design-image-preview', src: `/api/ppt-designer/images/${content.image}`, alt: content.name || 'Picture'}) : null,
      field(content.image ? 'Change the picture' : 'Picture', input, 'PNG, JPEG or GIF, up to 8 MB (an SVG can be saved as PNG first). It keeps its ratio in its place.'),
      field('Fit', selectInput([['contain', 'Whole picture'], ['cover', 'Fill the place']], content.fit || 'contain', value => guarded(() => setElementValues(element.id, {content: {...content, fit: value}}))())),
    ];
  }

  function elementForm(element) {
    const shown = state.scope === 'template' ? findElement(state.template, element.id)?.element : element;
    const kind = (shown || element).kind || 'chart';
    if (shown && kind !== 'chart') {
      const forms = {kpi: kpiForm, text: textForm, image: imageForm};
      return [
        h('h3', {class: 'ds-design-panel-title', text: {kpi: 'KPI card', text: 'Text box', image: 'Image'}[kind] + (shown.chart_title ? ` · ${shown.chart_title}` : '')}),
        originNote(element, 'element'),
        ...(forms[kind] ? forms[kind](element, shown) : []),
        h('div', {class: 'ds-design-panel-actions'}, elementActions(element.id).map(([label, action, enabled]) => h('button', {type: 'button', class: 'ds-design-action', disabled: enabled !== true, title: typeof enabled === 'string' ? enabled : null, onclick: action}, label))),
      ];
    }
    if (!shown) {
      return [h('h3', {class: 'ds-design-panel-title', text: elementLabel(element)}),
        h('p', {class: 'ds-design-origin is-local', text: 'This element is only in this Design: change it in This Design scope, or apply it to the template.'}),
        h('div', {class: 'ds-design-panel-actions'}, elementActions(element.id).map(([label, action, enabled]) => h('button', {type: 'button', class: 'ds-design-action', disabled: enabled !== true, onclick: action}, label)))];
    }
    const set = (key, delay) => (delay === 0 ? value => guarded(() => setElementValues(element.id, {[key]: value}))() : debounced(value => setElementValues(element.id, {[key]: value}), delay));
    const title = textInput(shown.chart_title, set('chart_title'), {id: 'ds-design-chart-title'});
    const datalist = fieldsDatalist(shown);
    const fieldInput = (key, placeholder) => textInput(shown[key], set(key), {id: `ds-design-${key}`, list: 'ds-design-fields', placeholder});
    const builder = h('div', {class: 'ds-cb'});
    window.ChartShelves?.render(builder, {
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

  // The title and subtitle of the slide shown are edited on the slide itself: a click writes them as the slide set has them
  // (with their tokens), Enter or leaving the field keeps the change, Esc gives it up.
  function editHeading(key) {
    const slide = shownSlide();
    const heading = $(key === 'title' ? 'ds-title' : 'ds-subtitle');
    if (!state.active || !slide || !heading || heading.querySelector('input')) return;
    const source = state.scope === 'template' ? findSlide(state.template, slide.id) : slide;
    if (!source) { report(new Error('This slide is only in this Design: change it in This Design scope.')); return; }
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
      if (keep && value !== (source[key] || '')) guarded(() => edit(slide_set => {
        const target = findSlide(slide_set, slide.id);
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

  // Free layout: the places of the layout of a slide resized, merged or split (places_editor.js). Each element
  // keeps its place (the place it is merged into, else a free one); an element left without a place is removed after
  // asking, as with a smaller layout.
  function adjustPlaces(slideId) {
    const slide = findSlide(editableSlideSet(), slideId);
    const grid = layoutOf(slide?.layout)?.grid;
    if (!slide || !grid) return;
    window.PlacesEditor.open({
      title: slide.title || 'Slide', grid: slide.options?.grid || null, rows: grid[0], columns: grid[1],
      onSave: guarded(async result => {
        const capacity = result ? result.geometry.length : (layoutOf(slide.layout)?.places || []).length;
        const visible = visibleElements(slide);
        // The editor starts from the places as they are (the grid adjusted before, else the layout's in reading order).
        const moved = visible.map((element, index) => {
          const place = placeOf(element, index);
          return result ? (result.mapping[place] ?? -1) : place;
        });
        const homeless = visible.filter((_element, index) => moved[index] < 0 || moved[index] >= capacity).length;
        const free = capacity - new Set(moved.filter(place => place >= 0 && place < capacity)).size;
        if (homeless > free && !await window.showConfirmDialog(`The places now hold ${capacity} element${capacity === 1 ? '' : 's'}: ${homeless - free} element${homeless - free === 1 ? '' : 's'} of the slide will be removed.`, {title: 'Adjust places', confirmLabel: 'Apply', tone: 'danger'})) return;
        await edit(slide_set => {
          const target = findSlide(slide_set, slideId);
          if (!target) return false;
          target.options = {...(target.options || {})};
          if (result) { target.options.grid = result.grid; target.options.geometry = result.geometry; }
          else { delete target.options.grid; delete target.options.geometry; }
          const elements = visibleElements(target);
          const taken = new Set();
          const homes = elements.map((element, index) => {
            const place = moved[index];
            if (place >= 0 && place < capacity && !taken.has(place)) { taken.add(place); return place; }
            return null;
          });
          elements.forEach((element, index) => {
            let place = homes[index];
            if (place === null) place = [...Array(capacity).keys()].find(candidate => !taken.has(candidate));
            if (place === undefined) {
              if (state.scope === 'design' && !state.detached && !isLocalElement(element)) element.hidden = true;
              else target.elements.splice(target.elements.indexOf(element), 1);
              return;
            }
            taken.add(place);
            element.place = place;
          });
          return undefined;
        });
      }),
    });
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
    const overlay = h('div', {class: 'confirm-overlay ds-overlay ds-secondary ppt-designer ds-design-dialog-overlay'});
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
      const slideName = id => findSlide(state.slide_set, id)?.title || findSlide(state.template, id)?.title || id;
      const elementName = id => elementLabel(findElement(state.slide_set, id)?.element || findElement(state.template, id)?.element) || id;
      const changed = state.report?.template_changed || [];
      if (changed.length) {
        rows.push(h('h3', {text: 'Changed in the template since'}));
        rows.push(h('p', {class: 'form-note', text: 'This Design changed these properties, and the template changed them too afterwards.'}));
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
      for (const local of overrides.local_slides || []) entries.push([`Slide “${local.slide?.title || 'New slide'}”`, 'only in this Design', () => deleteSlideHere(local.slide?.id)]);
      for (const [slideId, elements] of Object.entries(overrides.local_elements || {})) for (const element of elements) entries.push([`Chart “${elementLabel(element)}” on “${slideName(slideId)}”`, 'only in this Design', () => deleteElementHere(element.id)]);
      rows.push(h('h3', {text: `Differences from the template · ${entries.length}`}));
      if (!entries.length) rows.push(h('p', {class: 'form-note', text: 'This Design shows its template as it is.'}));
      for (const [what, detail, reset] of entries) {
        rows.push(h('div', {class: 'ds-design-difference'}, h('span', {}, h('b', {text: what}), ` · ${detail}`),
          h('button', {type: 'button', class: 'ds-design-action', disabled: !state.rights.design, onclick: guarded(async () => { await reset(); refresh(); })}, 'Reset to template')));
      }
      const dropped = state.report?.dropped || [];
      if (dropped.length) {
        rows.push(h('h3', {text: 'No longer in the template'}));
        rows.push(h('p', {class: 'form-note', text: `${dropped.length} change${dropped.length === 1 ? '' : 's'} of this Design refer to slides or charts the template deleted: they are left out, and dropped when you save.`}));
      }
      body.replaceChildren(...rows);
    };
    refresh();
    openDialog('Differences', `${state.info?.name || 'Design'} · template ${state.info?.template?.name || ''}`, body, {wide: true});
  }
  const resetSlideProperty = (slideId, name) => edit(slide_set => {
    const slide = findSlide(slide_set, slideId), original = findSlide(state.template, slideId);
    if (!slide || !original) return false;
    slide[name] = clone(original[name]);
  }, {scope: 'design'});
  const resetElementProperty = (elementId, name) => edit(slide_set => {
    const found = findElement(slide_set, elementId), original = findElement(state.template, elementId)?.element;
    if (!found || !original) return false;
    found.element[name] = clone(original[name]);
  }, {scope: 'design'});
  const deleteSlideHere = slideId => edit(slide_set => {
    const index = slide_set.slides.findIndex(item => item.id === slideId);
    if (index < 0) return false;
    slide_set.slides.splice(index, 1);
  }, {scope: 'design'});
  const deleteElementHere = elementId => edit(slide_set => {
    const found = findElement(slide_set, elementId);
    if (!found) return false;
    found.slide.elements.splice(found.slide.elements.indexOf(found.element), 1);
  }, {scope: 'design'});

  function openParametersDialog() {
    const editable = state.detached ? state.rights.design : state.rights.template;
    const scope = state.detached ? 'design' : 'template';
    const slide_set = () => (state.detached ? state.slide_set : state.template);
    const body = h('div', {class: 'ds-design-parameters'});
    const uses = name => {
      const pattern = new RegExp(`\\{\\s*${name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*\\}`, 'i');
      return (slide_set()?.slides || []).flatMap(slide => [
        ...['title', 'subtitle'].filter(key => pattern.test(slide[key] || '')).map(key => `${slide.title || 'Slide'} · ${key}`),
        ...(slide.elements || []).flatMap(element => Object.entries(element).filter(([, value]) => typeof value === 'string' && pattern.test(value)).map(([key]) => `${elementLabel(element)} · ${key.replaceAll('_', ' ')}`)),
      ]);
    };
    const save = list => edit(target => { target.parameters = list; }, {scope});
    const refresh = () => {
      const list = clone(slide_set()?.parameters || []);
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
        h('p', {class: 'form-note', text: 'Each Design of the template chooses the values of its parameters in Design Scope & Filters. Write {Name} in a chart filter (City IN ({City})), a numeric setting (LQ < {Threshold}) or a title.'}),
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
  // Save as template, Save as my Design, Detach
  // ------------------------------------------------------------------
  async function saveAsTemplate() {
    const id = viewer().state().activeId;
    const name = await window.showTextInputDialog('Name of the new template', {title: 'Save as template', value: `${state.info?.name || 'Design'} template`.slice(0, 120), maxLength: 120, confirmLabel: 'Save'});
    if (!name || !String(name).trim()) return;
    const result = await api(`/${encodeURIComponent(id)}/save-as-template`, 'POST', {name: String(name).trim()});
    viewer().status(`Saved the template “${result.template}”: new Designs can use it.`);
  }
  async function saveAsMyDesign() {
    const {design} = viewer().state();
    if (state.templateDirty) throw new Error('Save or discard the changes of the template first: your Design takes the changes of this one only.');
    const name = await window.showTextInputDialog('Name of your Design', {title: 'Save as my Design', value: `${design?.name || 'Design'} (mine)`.slice(0, 120), maxLength: 120, confirmLabel: 'Save'});
    if (!name || !String(name).trim()) return;
    const id = globalThis.crypto?.randomUUID?.() || randomId('design-');
    const definition = {...clone(design), name: String(name).trim(), slide_comments: {}, slide_comment_meta: {},
      slide_overrides: state.detached ? {} : (hasOverrides(state.overrides) ? state.overrides : {}), own_slides: state.detached ? state.slide_set : null};
    delete definition.datasets;
    await api(`/${encodeURIComponent(id)}`, 'PUT', definition);
    // This Design keeps what it had saved; the new one, with the changes shown, opens.
    await exitDesigner({force: true});
    syncDesignerButton();
    await viewer().reloadLibrary();
    await viewer().openDesign(id);
    viewer().status(`Saved “${definition.name}”: your own Design, following the same template with these changes.`);
  }
  async function detachDesign() {
    const id = viewer().state().activeId;
    if (!await window.showConfirmDialog(`Detach this Design from the template “${state.info?.template?.name}”? It keeps the slides it shows as its own and no longer takes the changes of the template.`, {title: 'Detach from template', confirmLabel: 'Detach', tone: 'danger'})) return;
    const info = await api(`/${encodeURIComponent(id)}/detach`, 'POST');
    loadSlideSet(info);
    viewer().storeSlides(id, storedSlideFields(info));
    renderDesigner();
    viewer().status('Detached: this Design keeps slides of its own.');
  }

  // ------------------------------------------------------------------
  // The values of the template parameters, in Design Scope & Filters
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
  // The slide set button and the events of the viewer
  // ------------------------------------------------------------------
  function syncDesignerButton() {
    const button = $('ds-design');
    if (!button) return;
    const rights = state.info?.rights;
    button.hidden = !rights || !(rights.design || rights.template);
    button.classList.toggle('is-active', state.active);
    button.textContent = state.active ? 'Designing' : 'Designer';
  }
  $('ds-design')?.addEventListener('click', guarded(async () => {
    if (state.active) { await exitDesigner(); syncDesignerButton(); return; }
    await enterDesigner();
    syncDesignerButton();
  }));
  document.addEventListener('ds:design-opened', event => {
    exitDesigner({force: true});
    state.designId = event.detail.id;
    state.info = null;
    parameterOptions.clear();
    syncDesignerButton();
    renderParameterValues();
    loadInfo(event.detail.id);
  });
  document.addEventListener('ds:design-closed', () => {
    exitDesigner({force: true});
    state.designId = '';
    state.info = null;
    syncDesignerButton();
    renderParameterValues();
  });
  // Prepared again (filters applied): the slide set not saved yet is laid out on the new selection.
  document.addEventListener('ds:prepared', () => {
    if (!state.active) return;
    // New data: every slide of the list is drawn again.
    state.generation = (state.generation || 0) + 1;
    if (!dirty()) state.syncedToken = viewer().state().prepared?.token;
    if (dirty()) guarded(() => preview(state.designDirty ? {...previewBody(), slide_set: state.slide_set} : previewBody()))();
    else loadFields(viewer().state().prepared?.token);
  });
  document.addEventListener('ds:slide-rendered', () => {
    if (!state.active) return;
    decorateStage();
    renderSorter();
    renderPanel();
  });
  // The viewer closed while designing: slide set closes with it (asking about the changes not saved).
  $('ds-viewer-close')?.addEventListener('click', event => {
    if (!state.active || !dirty()) { exitDesigner({force: true}); syncDesignerButton(); return; }
    event.stopImmediatePropagation();
    guarded(async () => { if (await exitDesigner()) { syncDesignerButton(); $('ds-viewer-close').click(); } })();
  }, true);
  window.addEventListener('beforeunload', event => { if (state.active && dirty()) { event.preventDefault(); event.returnValue = ''; } });
})();
