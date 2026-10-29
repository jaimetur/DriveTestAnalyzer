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
    history: [], future: [], slide: '', element: '', tab: 'slide', section: 'data', typesOpen: false, panelWidth: 0,
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
  // JSON with the keys of every object in order: the same slide set gives the same text however it was edited.
  const stable = value => JSON.stringify(value ?? null, (_key, item) => (item && typeof item === 'object' && !Array.isArray(item)
    ? Object.fromEntries(Object.keys(item).sort().map(key => [key, item[key]])) : item));
  // A change made back to what is saved (by hand, not only by undo) leaves nothing to save.
  function settleDirty() {
    if (!state.saved) return;
    if (state.templateDirty && stable(state.template) === state.saved.template) state.templateDirty = false;
    if (state.designDirty && !state.templateDirty
        && (state.detached ? stable(state.slide_set) === state.saved.slide_set : stable(state.overrides) === state.saved.overrides)) state.designDirty = false;
  }
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
    // What is saved, to tell a change undone or made back by hand from one to save (see settleDirty).
    state.saved = {template: stable(state.template), overrides: stable(state.overrides), slide_set: stable(state.slide_set)};
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
        settleDirty();
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
    if (!state.active) return;
    const id = viewer().state().activeId;
    // Undone back to what is saved: the draft kept meanwhile goes, so opening the Designer again offers nothing.
    if (!dirty()) {
      if (state.draftStored) { state.draftStored = false; forgetDraft(id, false); }
      return;
    }
    draftTimer = setTimeout(() => {
      if (!state.active || !dirty() || viewer().state().activeId !== id) return;
      api(`/${encodeURIComponent(id)}/slides/draft`, 'PUT', {state: {
        template: state.templateDirty ? state.template : null, slide_set: state.slide_set, overrides: state.overrides,
        templateDirty: state.templateDirty, designDirty: state.designDirty, keepTemplateChanges: state.keepTemplateChanges,
        template_updated_at: state.info?.template?.updated_at || '', scope: state.scope, slide: state.slide,
      }}).then(() => { state.draftStored = true; }).catch(() => undefined);
    }, 1200);
  }
  const forgetDraft = (id, discarded) => api(`/${encodeURIComponent(id)}/slides/draft${discarded ? '?discarded=1' : ''}`, 'DELETE').catch(() => undefined);
  async function offerDraft(id) {
    let result;
    try { result = await api(`/${encodeURIComponent(id)}/slides/draft`); } catch (_error) { return false; }
    const draft = result?.draft;
    if (!draft) return false;
    state.draftStored = true;
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
    lockViewerActions(false);
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
  // A new chart is empty (Duplicate copies one): the source of the chart chosen, no fields and no chart type yet, so any
  // chart type can be chosen; it reads no CDR until its shelves can draw it.
  const newChartElement = (slide_set, place = 0) => {
    const model = shownElement() || editedSlides().flatMap(slide => slide.elements || []).find(element => (element.kind || 'chart') === 'chart');
    return {
      id: randomId('e'), kind: 'chart', place, chart_title: 'New chart', cdr_source: model?.cdr_source || 'CDR-Data', kpi: '', chart_type: '',
      filters: '', rows_split: '', columns_split: '', legend: '', legend_position: '', legend_format: '', label_position: '', label_format: '',
      axis_x_range: '', axis_y_range: '', exclude_null_empty: false, exclude_zero: false, dynamic_rows_field: '', dynamic_columns_field: '',
    };
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
  // A place more on a slide without a free one: a column more on its adjusted places (a place as tall as the grid at the
  // right), else the layout of its kind (its comments) with the fewest places that leaves one free, of its rows when it
  // can. {apply(slide), message} or null when none has room.
  function roomFor(slide) {
    const grid = slide.options?.grid;
    if (grid && Array.isArray(grid.areas) && window.PlacesEditor) {
      const rows = grid.rows.length, columns = grid.columns.length;
      if (columns >= 12) return null;
      const added = [0, columns, rows, 1];
      const areas = [...grid.areas.map(area => [...area]), added].sort((left, right) => left[0] - right[0] || left[1] - right[1]);
      const next = {rows: [...grid.rows], columns: [...grid.columns.map(size => Math.round(size * columns / (columns + 1) * 10000) / 10000), Math.round(10000 / (columns + 1)) / 10000], areas};
      const mapping = window.PlacesEditor.cellMapping(grid.areas, areas);
      return {message: 'A column more on the places of the slide, for the new element.', apply: target => {
        visibleElements(target).forEach((element, index) => { element.place = mapping[placeOf(element, index)] ?? placeOf(element, index); });
        target.options = {...(target.options || {}), grid: next, geometry: window.PlacesEditor.geometry(next)};
      }};
    }
    const current = layoutOf(slide.layout);
    const needed = visibleElements(slide).length + 1;
    const layout = (state.layouts || []).filter(item => item.grid && !item.dynamic && !item.structural && item.places.length >= needed && (item.comments || '') === (current?.comments || ''))
      .sort((left, right) => left.places.length - right.places.length || Number(right.grid[0] === current?.grid?.[0]) - Number(left.grid[0] === current?.grid?.[0]))[0];
    if (!layout) return null;
    return {message: `Layout ${layout.name}, with a place for the new element.`, apply: target => {
      visibleElements(target).forEach((element, index) => { element.place = placeOf(element, index); });
      target.layout = layout.name;
      if (target.options) { delete target.options.geometry; delete target.options.grid; }
    }};
  }
  // An element put on a free place of a slide, which gets a place more when it has none (roomFor): one undo step.
  async function placeNewElement(slideId, make) {
    const slide = findSlide(editableSlideSet(), slideId);
    if (!slide) return;
    const room = freePlaces(slide).length ? null : roomFor(slide);
    if (!freePlaces(slide).length && !room) {
      report(new Error('No layout has room for another element on this slide: adjust its places first.'));
      return;
    }
    await edit(slide_set => {
      const target = findSlide(slide_set, slideId);
      if (!target) return false;
      room?.apply(target);
      const element = make(slide_set, freePlaces(target)[0]);
      if (!element) return false;
      target.elements = [...(target.elements || []), element];
      state.element = element.id;
      state.tab = 'element';
    });
    if (room) viewer().status(room.message);
  }
  // New Chart (the ⋯ menu of an element): a chart of its own on the slide.
  const addChart = slideId => placeNewElement(slideId, (slide_set, place) => newElement(slide_set, place, 'chart'));
  const duplicateElement = elementId => {
    const found = findElement(editableSlideSet(), elementId);
    if (!found) return undefined;
    return placeNewElement(found.slide.id, (slide_set, place) => {
      const source = findElement(slide_set, elementId)?.element;
      if (!source) return null;
      const copy = {...clone(source), id: randomId('e'), place};
      delete copy.origin; delete copy.overridden; delete copy.hidden;
      return copy;
    });
  };
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
  // The icons of the bar of the Designer (stroked, as the icons of the viewer).
  const ICONS = {
    undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
    redo: '<path d="m15 14 5-5-5-5"/><path d="M20 9H9.5a5.5 5.5 0 0 0 0 11H13"/>',
    parameters: '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
    differences: '<path d="M12 3v14M5 10h14M5 21h14"/>',
    slide: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 9h6M7 13h10"/>',
    chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    reset: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>',
    image: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 16-5-5L5 20"/>',
    kpi: '<path d="m3 17 6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
    text: '<path d="M5 6V4h14v2M12 4v16M9 20h6"/>',
    more: '<circle cx="5" cy="12" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="19" cy="12" r="1.2"/>',
  };
  const KINDS = {chart: ['Chart', 'chart'], kpi: ['KPI card', 'kpi'], text: ['Text box', 'text'], image: ['Image', 'image']};
  // The names of the properties a Design changes, as Differences shows them.
  const DIFFERENCE_NAMES = {title: 'Title', subtitle: 'Subtitle', layout: 'Layout', options: 'Places', place: 'Place', style: 'Format', chart_type: 'Chart type',
    chart_title: 'Title', kind: 'Kind', content: 'Content', kpi_card: 'KPI settings', repeat: 'One chart per', cdr_source: 'Source', kpi: 'Measure',
    rows_split: 'Rows', columns_split: 'Columns', legend: 'Legend', legend_position: 'Legend position', axis_x_range: 'X axis range', axis_y_range: 'Y axis range'};
  function icon(name) {
    const holder = document.createElement('span');
    holder.className = 'ds-design-icon';
    holder.setAttribute('aria-hidden', 'true');
    holder.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICONS[name]}</svg>`;
    return holder;
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
          ? (viewer().state().definition?.template === viewer().state().config?.blank_template
            ? h('span', {class: 'ds-design-pill ds-design-pill-detached', title: 'Created blank: its slides are its own and it follows no template', text: 'Blank PPT'})
            : h('span', {class: 'ds-design-pill ds-design-pill-detached', title: `Detached from ${state.info?.template?.name || 'its template'}: it keeps slides of its own`, text: 'Detached'}))
          : templatePreview()
          ? h('span', {class: 'ds-design-pill ds-design-pill-template', title: `Every change goes to the template ${state.info?.template?.name || ''}: ${count} Design${count === 1 ? '' : 's'} follow it`, text: `PPT Template · ${count} Design${count === 1 ? '' : 's'}`})
          : h('div', {class: 'ds-design-scopes', role: 'group', 'aria-label': 'Change'},
            scopeButton('design', 'This Design', 'Changes only this Design: kept as its differences from the template', state.rights.design),
            scopeButton('template', `Template · ${count} Design${count === 1 ? '' : 's'}`, `Changes the template ${state.info?.template?.name || ''}: every Design that follows it`, state.rights.template))),
      h('div', {class: 'ds-design-bar-group'},
        h('button', {type: 'button', class: 'ds-design-tool', title: 'Undo (Ctrl/Cmd+Z)', 'aria-label': 'Undo', disabled: !state.history.length, onclick: guarded(undo)}, icon('undo')),
        h('button', {type: 'button', class: 'ds-design-tool', title: 'Redo (Shift+Ctrl/Cmd+Z)', 'aria-label': 'Redo', disabled: !state.future.length, onclick: guarded(redo)}, icon('redo')),
        h('button', {type: 'button', class: 'ds-design-action ds-design-with-icon', onclick: guarded(openParametersDialog), disabled: state.detached ? false : !state.rights.template && !parameters().length, title: 'The parameters of the template'},
          icon('parameters'), 'Parameters', parameters().length ? h('span', {class: 'ds-design-count', text: String(parameters().length)}) : null),
        state.detached || templatePreview() ? null : h('button', {type: 'button', class: `ds-design-action ds-design-with-icon${changed ? ' has-warning' : ''}`, onclick: guarded(openDifferencesDialog), title: changed ? `What this Design changes of its template; the template changed ${changed} of them` : 'What this Design changes of its template'},
          icon('differences'), 'Differences', h('span', {class: `ds-design-count${changed ? ' is-warning' : ''}`, text: String(differences)}))),
      h('div', {class: 'ds-design-bar-group ds-design-bar-end'},
        h('span', {class: 'ds-design-busy', id: 'ds-design-busy', hidden: state.busy === 0, text: 'Laying out…'}),
        dirty() ? h('span', {class: 'ds-design-pill ds-design-pill-unsaved', text: state.templateDirty ? 'Unsaved template' : 'Unsaved'}) : null,
        h('button', {type: 'button', class: 'ds-design-action ds-design-primary', disabled: !dirty(), onclick: guarded(saveSlides)}, 'Save'),
        h('button', {type: 'button', class: 'ds-design-action', disabled: !dirty(), onclick: guarded(() => discardSlides())}, 'Discard'),
        h('button', {type: 'button', class: 'ds-design-action', 'aria-haspopup': 'menu', onclick: event => openMenu(event.currentTarget, moreActions())}, 'More ▾'),
      ),
    );
  }
  // A PPT Template open as a Design (PPT Templates → Edit) is saved only as a template.
  const templatePreview = () => Boolean(state.info?.template_preview);
  const moreActions = () => templatePreview() ? [
    ['Save as template…', guarded(saveAsTemplate), true],
  ] : [
    ['Save Design as…', guarded(saveAsMyDesign), !state.templateDirty || 'Save or discard the changes of the template first'],
    ['Save as template…', guarded(saveAsTemplate), true],
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
    // The scroll of the list before anything moves: the new items take the thumbnails already drawn out of the old ones,
    // so the list is shorter (and its scroll cut) until they are in it.
    const scrolled = nav.scrollTop;
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
    // The list keeps its scroll when it is drawn again; it moves only to bring the slide shown into sight, by itself (the
    // panels around it stay where they are).
    nav.replaceChildren(...items, add);
    nav.scrollTop = scrolled;
    const current = nav.querySelector('.is-current');
    if (current) {
      const box = current.getBoundingClientRect(), view = nav.getBoundingClientRect();
      if (box.top < view.top) nav.scrollTop -= view.top - box.top;
      else if (box.bottom > view.bottom) nav.scrollTop += box.bottom - view.bottom;
    }
  }
  function slideActions(slide) {
    const template = state.scope === 'template';
    const fromTemplate = isTemplateSlide(slide) && !state.detached;
    const actions = [
      ['New Slide after', guarded(() => { state.slide = slide.id; return addSlide('content'); }), true],
      ['Duplicate Slide', guarded(() => duplicateSlide(slide.id)), true],
    ];
    if (template) {
      actions.push([slide.optional ? 'Make Slide not optional' : 'Make Slide optional (off by default)', guarded(() => setOptional(slide.id, !slide.optional)), Boolean(findSlide(state.template, slide.id))]);
      actions.push(['Delete Slide', guarded(() => deleteSlide(slide.id)), Boolean(findSlide(state.template, slide.id)) || 'Only in this Design: delete it in This Design scope']);
    } else if (fromTemplate) {
      if (slide.optional) actions.push([slide.optional_off ? 'Show Slide in this Design' : 'Leave Slide out of this Design', guarded(() => setOptionalShown(slide.id, Boolean(slide.optional_off))), true]);
      else actions.push([slide.hidden ? 'Show Slide again' : 'Hide Slide in this Design', guarded(() => setSlideHidden(slide.id, !slide.hidden)), true]);
      if (slide.overridden?.length || (slide.elements || []).some(element => element.overridden?.length || element.hidden)) actions.push(['Reset Slide to template', guarded(() => resetSlide(slide.id)), true]);
    } else actions.push(['Delete Slide', guarded(() => deleteSlide(slide.id)), true]);
    if (!template && !state.detached && state.rights.template && (slide.origin === 'design' || slide.overridden?.length || (slide.elements || []).some(element => element.overridden?.length || element.hidden || isLocalElement(element)))) {
      actions.push(['Apply Slide to template', guarded(() => applyToTemplate({slideId: slide.id})), true]);
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
      if (slide && !slide.hidden && !slide.optional_off) {
        state.slide = rendered.source_slide;
        // The element chosen stays on the slide left: the panel shows the slide now shown.
        if (state.element && !(slide.elements || []).some(item => item.id === state.element)) { state.element = ''; state.tab = 'slide'; }
      }
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
    // Chart Type goes on the chart chosen once it is drawn.
    const waiting = placeChartTypes();
    if (waiting.length) $('ds-design-panel')?.append(...waiting);
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
    // Each action names what it acts on: a Chart, a KPI card, a Text box or an Image.
    const noun = KINDS[found.element.kind || 'chart']?.[0] || 'Element';
    const actions = [
      ['New Chart', guarded(() => addChart(found.slide.id)), true],
      [`Duplicate ${noun}`, guarded(() => duplicateElement(elementId)), true],
      [`Copy ${noun}`, () => { state.clipboard = clone(found.element); viewer().status(`${noun} copied: paste it on a free place.`); }, true],
      [`Delete ${noun}`, guarded(() => deleteElement(elementId)), true],
    ];
    const widened = widenedPlaces(found.slide.id, elementId);
    if (widened) actions.push([`Fill the free places beside the ${noun.toLowerCase().replace('kpi', 'KPI')}`, guarded(() => applyPlaces(found.slide.id, widened)), true]);
    if (!template && !state.detached && !isLocalElement(found.element) && found.element.overridden?.length) actions.push([`Reset ${noun} to template`, guarded(() => resetElement(elementId)), true]);
    if (!template && !state.detached && state.rights.template && (isLocalElement(found.element) || found.element.overridden?.length)) actions.push([`Apply ${noun} to template`, guarded(() => applyToTemplate({elementId})), true]);
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

  // The panel: a head that says where it is (the slide, the element chosen on it) and what its changes reach, with the
  // actions in a menu, and below it the form of the slide or element. A chart shows its title, then its Data (source,
  // shelves and fields) or its Format, and opens Chart Type on the edge of the panel, over the slide.
  function renderPanel() {
    const panel = $('ds-design-panel');
    if (!panel || !state.active) return;
    // While a text is being written in the rich text editor of a text box, its panel stays as it is (the caret too).
    const panelKey = `${state.tab}|${state.section}|${state.element}|${state.slide}|${state.scope}`;
    if (panel.dataset.key === panelKey && document.activeElement?.closest?.('#ds-design-panel [contenteditable="true"]')) return;
    panel.dataset.key = panelKey;
    const focused = panel.contains(document.activeElement) && document.activeElement.id ? document.activeElement : null;
    const dataOpen = new Set([...panel.querySelectorAll('.ds-cb-group')].filter(group => group.open).map(group => group.querySelector('summary')?.firstChild?.textContent));
    const typing = focused && 'value' in focused ? {id: focused.id, value: focused.value, start: focused.selectionStart, end: focused.selectionEnd} : null;
    const pointedType = document.activeElement?.closest?.('#ds-design-types') ? document.activeElement.dataset.type || '' : '';
    const slide = shownSlide();
    const element = state.element ? shownElement() : null;
    if (!element && state.tab === 'element') state.tab = 'slide';
    const chosen = state.tab === 'element' && element ? element : null;
    const shown = chosen && (state.scope === 'template' ? findElement(state.template, chosen.id)?.element : chosen);
    const chart = Boolean(shown) && (shown.kind || 'chart') === 'chart';
    const body = h('div', {class: `ds-design-panel-body${chart ? ` is-${state.section}` : ''}`});
    if (chosen) body.append(...elementForm(chosen));
    else if (slide) body.append(...slideForm(slide));
    else body.append(h('p', {class: 'ds-design-empty', text: 'Choose a slide.'}));
    panel.classList.toggle('is-folded', state.folded);
    if (state.panelWidth) panel.style.setProperty('--ds-panel-width', `${Math.max(PANEL_MIN_WIDTH, state.panelWidth)}px`);
    // (A KPI card has Chart Type too: it turns it back into a chart.)
    const typed = chart || (Boolean(shown) && shown.kind === 'kpi');
    chartTypeNodes = chartTypePicker(typed ? chosen : null, typed ? shown : null);
    panel.replaceChildren(panelResizer(panel), panelHead(slide, chosen, shown, chart), body, ...placeChartTypes());
    if (dataOpen.size) panel.querySelectorAll('.ds-cb-group').forEach(group => { group.open = dataOpen.has(group.querySelector('summary')?.firstChild?.textContent); });
    const again = typing && $(typing.id);
    if (again) {
      if (again.value !== typing.value) again.value = typing.value;
      again.focus({preventScroll: true});
      try { if (typing.start !== null && again.setSelectionRange) again.setSelectionRange(typing.start, typing.end); } catch (_error) { /* not a text field */ }
    }
    if (pointedType) panel.querySelector(`#ds-design-types [data-type="${CSS.escape(pointedType)}"]`)?.focus({preventScroll: true});
  }

  function panelHead(slide, element, shown, chart) {
    const kind = slideKind(slide);
    const slideName = !slide ? 'Slide' : kind === 'content' ? `Slide ${editedSlides().findIndex(item => item.id === slide.id) + 1}` : STRUCTURAL[kind];
    const selected = state.element ? shownElement() : null;
    const crumb = (label, active, iconName, onclick) => h('button', {type: 'button', class: `ds-design-crumb${active ? ' is-active' : ''}`, 'aria-current': active ? 'true' : null, title: label, onclick},
      icon(iconName), h('span', {text: label}));
    // The element button lists the elements of the slide to choose one (the one chosen marked); with none chosen it reads
    // Charts.
    const onSlide = slide && slideKind(slide) === 'content' ? visibleElements(slide) : [];
    const chooseElement = event => openMenu(event.currentTarget, onSlide.map((item, index) => [placeOf(item, index), item]).sort(([left], [right]) => left - right)
      .map(([place, item]) => [`${item.id === selected?.id ? '✓ ' : ''}${place + 1} · ${elementLabel(item)}`, () => selectElement(item.id), true]));
    const chooser = onSlide.length || selected ? h('button', {type: 'button', class: `ds-design-crumb${element ? ' is-active' : ''}`, 'aria-haspopup': 'menu',
      'aria-current': element ? 'true' : null, title: 'Choose a chart of this slide', onclick: chooseElement},
    icon(selected ? KINDS[selected.kind || 'chart']?.[1] || 'chart' : 'chart'), h('span', {text: selected ? elementName(selected, slide) : 'Charts'}),
    h('span', {class: 'ds-design-crumb-caret', 'aria-hidden': 'true', text: '▾'})) : null;
    const crumbs = h('nav', {class: 'ds-design-crumbs', 'aria-label': 'What the panel shows'},
      crumb(slideName, !element, 'slide', () => { state.tab = 'slide'; renderPanel(); }),
      chooser ? h('span', {class: 'ds-design-crumb-separator', 'aria-hidden': 'true', text: '›'}) : null,
      chooser);
    const actions = element ? elementActions(element.id) : slide ? slideActions(slide) : [];
    const more = h('button', {type: 'button', class: 'ds-design-more', 'aria-haspopup': 'menu', disabled: !actions.length,
      title: element ? 'Actions of this element' : 'Actions of this slide', 'aria-label': element ? 'Actions of this element' : 'Actions of this slide',
      onclick: event => openMenu(event.currentTarget, actions)}, icon('more'));
    const fold = h('button', {type: 'button', class: 'ds-design-fold', 'aria-expanded': String(!state.folded), title: state.folded ? 'Show the panel' : 'Fold the panel',
      onclick: () => { state.folded = !state.folded; renderPanel(); }}, state.folded ? '▴' : '▾');
    const nodes = [h('div', {class: 'ds-design-panel-top'}, crumbs, more, fold), h('div', {class: 'ds-design-reach'}, scopeBadge(), originBadge(element || slide))];
    if (chart) {
      const title = textInput(shown.chart_title, debounced(value => setElementValues(element.id, {chart_title: value})), {id: 'ds-design-chart-title', placeholder: 'Chart title'});
      title.setAttribute('aria-label', 'Chart title');
      const section = (key, label, mark) => h('button', {type: 'button', role: 'tab', class: state.section === key ? 'is-active' : '', 'aria-selected': String(state.section === key),
        onclick: () => { state.section = key; renderPanel(); }}, label, mark);
      nodes.push(
        h('div', {class: 'ds-design-head-title'}, title, tokenMenuButton(title)),
        h('div', {class: 'ds-design-sections', role: 'tablist', 'aria-label': 'Chart'},
          section('data', 'Data'),
          section('format', 'Format', Object.keys(styleOf(shown)).length ? h('span', {class: 'ds-design-dot', title: 'Formatted'}) : null)));
    }
    return h('div', {class: 'ds-design-panel-head'}, ...nodes);
  }
  const elementName = (element, slide) => {
    const index = visibleElements(slide).findIndex(item => item.id === element.id);
    return `${KINDS[element.kind || 'chart']?.[0] || 'Element'}${index >= 0 ? ` ${placeOf(element, index) + 1}` : ''}`;
  };
  // Where the changes go (the scope of the bar) and how the slide or element shown differs from the template.
  function scopeBadge() {
    const count = designCount();
    const [text, title] = state.detached ? ['Own slides', 'This Design has slides of its own.']
      : state.scope === 'template' ? [`Template · ${count} Design${count === 1 ? '' : 's'}`, `Changes the template: ${count} Design${count === 1 ? '' : 's'} follow it.`]
        : ['This Design', 'Changes only this Design.'];
    return h('span', {class: `ds-design-badge is-scope is-${state.detached ? 'design' : state.scope}`, title}, icon(state.scope === 'template' && !state.detached ? 'differences' : 'slide'), text);
  }
  function originBadge(item) {
    if (state.detached || !item) return null;
    if (item.origin === 'design') return h('span', {class: 'ds-design-badge is-local', text: 'Only in this Design'});
    if (item.overridden?.length) {
      const names = [...new Set(item.overridden.map(name => DIFFERENCE_NAMES[name] || name.replaceAll('_', ' ')))];
      return h('span', {class: 'ds-design-badge is-changed', title: `Changed here: ${names.join(', ')}`, text: `Changed: ${names.join(', ')}`});
    }
    return h('span', {class: 'ds-design-badge is-same', text: 'As the template'});
  }

  // The width of the panel: dragged on its edge (or with the arrow keys there), kept for the next time.
  const PANEL_WIDTH_KEY = 'drivetest-analyzer:ppt-designer:panel-width';
  try { state.panelWidth = Number(localStorage.getItem(PANEL_WIDTH_KEY)) || 0; } catch (_error) { state.panelWidth = 0; }
  let relayoutTimer = 0;
  // The narrowest panel keeps each row on one line (19rem, as the stylesheet).
  const PANEL_MIN_WIDTH = 304;
  function setPanelWidth(panel, width, {final = false} = {}) {
    const max = Math.max(PANEL_MIN_WIDTH, Math.min(720, Math.round(window.innerWidth * 0.6)));
    state.panelWidth = width ? Math.round(Math.max(PANEL_MIN_WIDTH, Math.min(max, width))) : 0;
    if (state.panelWidth) panel.style.setProperty('--ds-panel-width', `${state.panelWidth}px`);
    else panel.style.removeProperty('--ds-panel-width');
    if (!final) return;
    try {
      if (state.panelWidth) localStorage.setItem(PANEL_WIDTH_KEY, String(state.panelWidth));
      else localStorage.removeItem(PANEL_WIDTH_KEY);
    } catch (_error) { /* the width is kept for this page only */ }
    // The charts are drawn again for the width the slide is left.
    clearTimeout(relayoutTimer);
    relayoutTimer = setTimeout(() => viewer().renderSlide(), 120);
  }
  function panelResizer(panel) {
    const handle = h('div', {class: 'ds-design-resize', role: 'separator', 'aria-orientation': 'vertical', 'aria-label': 'Width of the panel', tabindex: '0',
      title: 'Drag to widen or narrow the panel · double-click: its usual width'});
    handle.addEventListener('pointerdown', event => {
      if (event.button !== 0) return;
      event.preventDefault();
      handle.setPointerCapture(event.pointerId);
      const right = panel.getBoundingClientRect().right;
      panel.classList.add('is-resizing');
      const move = moveEvent => setPanelWidth(panel, right - moveEvent.clientX);
      let ended = false;
      const end = () => {
        if (ended) return;
        ended = true;
        handle.removeEventListener('pointermove', move);
        panel.classList.remove('is-resizing');
        setPanelWidth(panel, state.panelWidth || panel.getBoundingClientRect().width, {final: true});
      };
      handle.addEventListener('pointermove', move);
      handle.addEventListener('pointerup', end);
      handle.addEventListener('pointercancel', end);
    });
    handle.addEventListener('dblclick', () => setPanelWidth(panel, 0, {final: true}));
    handle.addEventListener('keydown', event => {
      if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
      // The arrows widen the panel here; they do not go to the other slides.
      event.preventDefault();
      event.stopPropagation();
      setPanelWidth(panel, panel.getBoundingClientRect().width + (event.key === 'ArrowLeft' ? 24 : -24), {final: true});
    });
    return handle;
  }

  // Chart Type: a tab on the right edge of the chart chosen, inside its place on the slide (as in Chart Builder), opens the
  // chart types over the slide beside it; choosing one changes the chart and closes them, as the tab, ×, Esc or a click
  // outside them do. While the chart is not drawn, the tab waits on the edge of the panel.
  let chartTypeNodes = [];
  function placeChartTypes() {
    const stage = $('ds-charts');
    stage?.querySelectorAll('.ds-chart > .ds-design-types-tab, :scope > .ds-design-types').forEach(node => node.remove());
    const [tab, types] = chartTypeNodes;
    const card = tab && stage && [...stage.querySelectorAll('.ds-chart')].find(item => item.dataset.elementId === state.element && !item.dataset.repeated);
    if (!card) return chartTypeNodes;
    card.append(tab);
    if (types) {
      stage.append(types);
      const room = stage.getBoundingClientRect(), chart = card.getBoundingClientRect(), width = tab.offsetWidth;
      // At the left of the tab, or at the right of the chart when there is more room there.
      if (chart.right - width - room.left >= room.right - chart.right) {
        Object.assign(types.style, {left: 'auto', right: `${room.right - chart.right + width + 4}px`, maxWidth: `${Math.max(0, chart.right - width - room.left - 8)}px`});
      } else Object.assign(types.style, {left: `${chart.right - room.left + 4}px`, right: 'auto', maxWidth: `${room.right - chart.right - 8}px`});
    }
    return [];
  }
  // (The tab calls the eye when a chart is chosen: its pulse goes on where it was when the panel is drawn again.)
  const TYPES_CALL_MS = 2200;
  let typesCalled = {id: '', at: 0};
  function chartTypePicker(element, shown) {
    if (!shown) { typesCalled = {id: '', at: 0}; return []; }
    const toggle = () => { state.typesOpen = !state.typesOpen; renderPanel(); };
    const open = state.typesOpen;
    if (typesCalled.id !== element.id) typesCalled = {id: element.id, at: performance.now()};
    const called = performance.now() - typesCalled.at, calling = !open && called < TYPES_CALL_MS;
    const tab = h('button', {type: 'button', class: `ds-design-types-tab${open ? ' is-open' : ''}${calling ? ' is-calling' : ''}`, 'aria-expanded': String(open), 'aria-controls': 'ds-design-types',
      style: calling ? {animationDelay: `-${Math.round(called)}ms`} : null,
      title: open ? 'Close Chart Type' : `Chart Type: ${shown.chart_type || 'choose one'}`, onclick: toggle},
    window.ChartShelves?.typesIcon() || null, h('span', {class: 'ds-design-types-tab-label', text: 'Chart Type'}));
    if (!open) return [tab];
    const host = h('div', {class: 'ds-design-types-body'});
    // Choosing a chart type closes them (a setting of the type chosen, under them, does not).
    const options = shelvesOptions(element, shown);
    window.ChartShelves?.renderTypes(host, {...options, onChange: changes => { if ('chart_type' in changes) state.typesOpen = false; options.onChange(changes); }});
    return [tab, h('section', {class: 'ds-design-types', id: 'ds-design-types', 'aria-label': 'Chart Type'},
      h('div', {class: 'ds-design-types-head'}, h('strong', {text: 'Chart Type'}),
        h('button', {type: 'button', class: 'ds-design-types-close', 'aria-label': 'Close Chart Type', title: 'Close (Esc)', onclick: toggle}, '×')),
      host)];
  }
  const shelvesOptions = (element, shown) => ({
    values: shown, fields: state.fields?.fields, calculated: state.fields?.calculated_fields, parameters: parameters(),
    lockedFilters: lockedFilters(), onLockedFilter: () => $('ds-floating-filters')?.click(), fieldValues, pptNrMode: String(viewer().state().definition?.nr_mode || '').replace('+', ' & '), eachPpt: state.scope === 'template',
    onChange: changes => guarded(() => setElementValues(element.id, typeChanges(shown, changes)))(),
  });
  // Chart Type → KPI Card turns a chart into a KPI card of its first measure, with its source, title and filters (the
  // figure an average for a number, the share of a value otherwise), and another chart type turns a KPI card back into a
  // chart; the settings of the card stay with it for a later return.
  function typeChanges(shown, changes) {
    if (!('chart_type' in changes)) return changes;
    const toKpi = String(changes.chart_type).toLowerCase() === 'kpi card';
    if (toKpi === (shown.kind === 'kpi')) return changes;
    if (!toKpi) return {...changes, kind: 'chart'};
    const part = window.ChartShelves.kpiParts(shown.kpi)[0] || '';
    const field = window.ChartShelves.kpiField(part);
    const number = (state.fields?.fields?.[String(shown.cdr_source || 'CDR-Data').toLowerCase()] || []).find(item => item.name === field)?.type === 'number';
    const measure = !field || number ? (/^MEDIAN\s*\(/i.test(part) ? 'median' : 'average') : 'share_value';
    return {...changes, kind: 'kpi', kpi: field, rows_split: 'Campaign', columns_split: '', legend: '',
      kpi_card: {measure, comparison: 'previous', sparkline: true, ...(shown.kpi_card || {})}};
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
    // Three subpanels: its titles, its layout and its elements.
    const subpanel = (kind, heading, ...children) => h('section', {class: `ds-cb-card ds-design-subpanel is-${kind}`, 'aria-label': heading},
      h('h4', {class: 'ds-cb-card-title', text: heading}), ...children);
    const nodes = [subpanel('titles', 'Titles',
      field('Title', h('div', {class: 'ds-design-input-row'}, title, tokenMenuButton(title))),
      field('Subtitle', h('div', {class: 'ds-design-input-row'}, subtitle, tokenMenuButton(subtitle))))];
    const grid = layoutOf(shownSource.layout)?.grid;
    nodes.push(subpanel('layout', 'Layout',
      h('button', {type: 'button', class: 'ds-design-layout-button', disabled: !editable, 'aria-label': 'Layout', onclick: event => openLayoutGallery(event.currentTarget, slide)}, shownSource.layout || 'Choose a layout'),
      kind === 'content' && grid && window.PlacesEditor ? h('button', {type: 'button', class: 'ds-design-action', disabled: !editable, title: 'Resize the rows and columns of the layout, merge places or split them',
        onclick: () => adjustPlaces(slide.id)}, shownSource.options?.geometry ? 'Adjust places… (adjusted)' : 'Adjust places…') : null,
      state.scope === 'template' && findSlide(state.template, slide.id)
        ? h('label', {class: 'ds-design-check'}, h('input', {type: 'checkbox', checked: Boolean(findSlide(state.template, slide.id).optional), onchange: event => guarded(() => setOptional(slide.id, event.target.checked))()}), 'Optional: off in each Design until it is shown there')
        : null));
    if (kind === 'content') {
      const elements = visibleElements(slide);
      nodes.push(subpanel('elements', `Elements · ${elements.length} of ${placesOf(slide).length || elements.length} places`,
        h('ul', {class: 'ds-design-element-list'}, elements.map((item, index) => h('li', {},
          h('button', {type: 'button', onclick: () => selectElement(item.id)},
            h('span', {class: 'ds-design-place', text: String(placeOf(item, index) + 1)}), elementLabel(item),
            isLocalElement(item) && !state.detached ? h('span', {class: 'ds-design-badge is-local', text: 'This Design'}) : item.overridden?.length ? h('span', {class: 'ds-design-badge is-changed', text: 'Changed'}) : null)))),
        freePlaces(slide).length ? h('button', {type: 'button', class: 'ds-design-action', onclick: guarded(() => addElement(slide.id, freePlaces(slide)[0]))}, '+ Add chart') : null));
    }
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
  // Format of a chart (phase 3): the Format of chart_format.js (Chart Builder has it too), on the elements of the slides
  // being edited.
  // ------------------------------------------------------------------
  const {styleOf, formatSection, openSeriesFormat, openAxisRange, openAxisValues} = window.ChartFormat.editor({
    element: elementId => findElement(editableSlideSet(), elementId)?.element,
    write: (elementId, values) => setElementValues(elementId, values),
    canvas: elementId => [...($('ds-charts')?.querySelectorAll('.ds-chart') || [])].find(card => card.dataset.elementId === elementId)?.querySelector('canvas'),
    status: text => viewer().status(text), report, settled: () => state.queue.catch(() => undefined),
    label: element => elementLabel(element), refresh: () => renderPanel(), debounced,
  });

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
    const upload = guarded(async file => {
      if (!file) return;
      const body = new FormData();
      body.append('file', file);
      const response = await fetch('/api/ppt-designer/images', {method: 'POST', body, credentials: 'same-origin'});
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'The picture could not be kept.');
      await setElementValues(element.id, {content: {...content, image: result.id, name: result.name}});
    });
    const input = h('input', {type: 'file', accept: 'image/png,image/jpeg,image/gif', 'aria-label': 'Picture', hidden: true, onchange: event => upload(event.target.files?.[0])});
    // The picture shown, and a place to drop another one (or choose it).
    const drop = h('div', {class: `ds-design-dropzone${content.image ? ' has-picture' : ''}`,
      ondragover: event => { event.preventDefault(); drop.classList.add('is-over'); }, ondragleave: () => drop.classList.remove('is-over'),
      ondrop: event => { event.preventDefault(); drop.classList.remove('is-over'); upload(event.dataTransfer?.files?.[0]); }},
      content.image ? h('img', {class: 'ds-design-image-preview', src: `/api/ppt-designer/images/${content.image}`, alt: content.name || 'Picture'}) : icon('image'),
      h('button', {type: 'button', class: 'ds-design-action ds-design-primary', onclick: () => input.click()}, content.image ? 'Change the picture' : 'Choose a picture'),
      h('span', {class: 'ds-design-field-note', text: content.image ? (content.name || '') : 'or drop it here'}), input);
    return [
      field('Picture', drop, 'PNG, JPEG or GIF, up to 8 MB (an SVG can be saved as PNG first). It keeps its ratio in its place.'),
      field('Fit', selectInput([['contain', 'Whole picture'], ['cover', 'Fill the place']], content.fit || 'contain', value => guarded(() => setElementValues(element.id, {content: {...content, fit: value}}))())),
    ];
  }

  // The body of the panel of an element: the form of a KPI card, text box or image, or the Data or Format of a chart.
  function elementForm(element) {
    const shown = state.scope === 'template' ? findElement(state.template, element.id)?.element : element;
    if (!shown) return [h('p', {class: 'ds-design-origin is-local', text: 'This element is only in this Design: change it in This Design scope, or apply it to the template.'})];
    const kind = shown.kind || 'chart';
    if (kind !== 'chart') return {kpi: kpiForm, text: textForm, image: imageForm}[kind]?.(element, shown) || [];
    if (state.section === 'format') return [formatSection(element.id, shown)];
    const builder = h('div', {class: 'ds-cb'});
    window.ChartShelves?.render(builder, {...shelvesOptions(element, shown), chartTypes: false});
    return [builder];
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
    // What each place holds now, named on the board.
    const labels = [];
    visibleElements(slide).forEach((element, index) => { labels[placeOf(element, index)] = elementLabel(element); });
    window.PlacesEditor.open({
      title: slide.title || 'Slide', grid: slide.options?.grid || null, rows: grid[0], columns: grid[1], labels,
      onSave: guarded(result => applyPlaces(slideId, result)),
    });
  }
  // The places of a slide given (a result of the places editor, or null for those of its layout): each element keeps its
  // place, else takes a free one, else is removed after asking.
  async function applyPlaces(slideId, result) {
    const slide = findSlide(editableSlideSet(), slideId);
    if (!slide) return;
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
  }
  // A chart takes the free places beside it in its row (else above or below it in its column): the bottom chart of a 2 × 2
  // slide with its neighbour free spans the whole width. The grid of the slide is that of its places, adjusted or not.
  function widenedPlaces(slideId, elementId) {
    const slide = findSlide(editableSlideSet(), slideId);
    const grid = layoutOf(slide?.layout)?.grid;
    if (!slide || !grid || !window.PlacesEditor) return null;
    const spec = slide.options?.grid?.areas ? clone(slide.options.grid) : window.PlacesEditor.gridSpec(grid[0], grid[1]);
    const areas = [...spec.areas].sort((left, right) => left[0] - right[0] || left[1] - right[1]);
    const elements = visibleElements(slide);
    const index = elements.findIndex(element => element.id === elementId);
    const own = areas[placeOf(elements[index], index)];
    if (index < 0 || !own) return null;
    const used = new Set(elements.map((element, position) => placeOf(element, position)));
    const free = areas.filter((_area, place) => !used.has(place));
    const grow = horizontal => {
      let [row, column, rows, columns] = own;
      const taken = [];
      for (let changed = true; changed;) {
        changed = false;
        for (const area of free) {
          if (taken.includes(area)) continue;
          const beside = horizontal
            ? area[0] === row && area[2] === rows && (area[1] + area[3] === column || area[1] === column + columns)
            : area[1] === column && area[3] === columns && (area[0] + area[2] === row || area[0] === row + rows);
          if (!beside) continue;
          if (horizontal) { columns += area[3]; column = Math.min(column, area[1]); } else { rows += area[2]; row = Math.min(row, area[0]); }
          taken.push(area);
          changed = true;
        }
      }
      return taken.length ? {merged: [row, column, rows, columns], taken} : null;
    };
    const grown = grow(true) || grow(false);
    if (!grown) return null;
    const next = {...spec, areas: [...areas.filter(area => area !== own && !grown.taken.includes(area)), grown.merged]};
    // The element goes to the place it grew into; the other places keep theirs.
    const after = [...next.areas].sort((left, right) => left[0] - right[0] || left[1] - right[1]);
    const mapping = areas.map(area => (area === own ? after.indexOf(grown.merged) : grown.taken.includes(area) ? -1 : after.indexOf(area)));
    return {grid: next, geometry: window.PlacesEditor.geometry(next), mapping};
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
  // A field of the CDRs of the Design, chosen from its groups (the sections of the CDR Field Dictionary, as in the Fields of
  // the chart builder) with a search; the chosen field is marked.
  function fieldPicker(value, onChoose, {disabled = false} = {}) {
    const button = h('button', {type: 'button', class: 'ds-design-field-picker', 'aria-haspopup': 'listbox', disabled},
      h('span', {class: 'ds-design-field-picker-value', text: value || 'Choose a field'}), h('span', {class: 'ds-design-field-picker-caret', 'aria-hidden': 'true'}));
    button.onclick = () => {
      closeMenus();
      const groups = new Map(), seen = new Set();
      const put = (name, group) => {
        if (!name || seen.has(name.toLowerCase())) return;
        seen.add(name.toLowerCase());
        if (!groups.has(group)) groups.set(group, []);
        groups.get(group).push(name);
      };
      for (const items of Object.values(state.fields?.fields || {})) for (const item of items || []) put(item.name, item.category || 'Other fields');
      for (const name of state.fields?.calculated_fields || []) put(name, 'Auto-calculated Fields');
      const rank = window.ChartShelves?.groupRank || (() => 0);
      const ordered = [...groups.entries()].sort(([left], [right]) => rank(left) - rank(right) || left.localeCompare(right));
      const search = h('input', {type: 'search', class: 'ds-design-field-picker-search', placeholder: 'Search fields', 'aria-label': 'Search fields'});
      const list = h('div', {class: 'ds-design-field-picker-list', role: 'listbox'});
      const paint = () => {
        const query = search.value.trim().toLowerCase();
        list.replaceChildren(...ordered.map(([group, names]) => {
          const shown = names.filter(name => !query || name.toLowerCase().includes(query)).sort((left, right) => left.localeCompare(right));
          return shown.length ? h('div', {class: 'ds-design-field-picker-group'},
            h('span', {class: 'ds-design-field-picker-group-title'}, group, h('span', {text: String(shown.length)})),
            ...shown.map(name => h('button', {type: 'button', role: 'option', class: name === value ? 'is-chosen' : null, 'aria-selected': String(name === value),
              onclick: () => { closeMenus(); onChoose(name); }}, name))) : null;
        }).filter(Boolean));
        if (!list.childElementCount) list.append(h('p', {class: 'ds-design-empty', text: groups.size ? 'No field matches.' : 'The fields appear once the Design is prepared.'}));
      };
      search.addEventListener('input', paint);
      paint();
      const popover = h('div', {class: 'ds-design-popover ds-design-field-picker-popover'}, search, list);
      popover.style.width = `${Math.max(button.offsetWidth, 300)}px`;
      placePopover(popover, button);
      search.focus({preventScroll: true});
      list.querySelector('.is-chosen')?.scrollIntoView({block: 'center'});
    };
    return button;
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
  });
  // Esc while designing closes a menu, then Chart Type, then leaves the element chosen, before the viewer takes it (to close
  // itself); in a field of the panel it leaves the field. The dialogs, the panels over the viewer and the other fields keep
  // their own Esc.
  const VIEWER_OVERLAYS = ['ds-ppt-filter-overlay', 'ds-chart-expanded-overlay', 'ds-editor-overlay', 'ds-data-overlay', 'ds-filter-overlay'];
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape' || !state.active) return;
    const field = event.target.closest?.('input, textarea, select, [contenteditable="true"]');
    if (field && !field.closest('#ds-design-panel')) return;
    if (document.querySelector('.ds-design-dialog-overlay') || VIEWER_OVERLAYS.some(id => $(id) && !$(id).hidden)) return;
    if (field) field.blur();
    else if (document.querySelector('.ds-design-popover')) closeMenus();
    else if (state.typesOpen && $('ds-design-types')) { state.typesOpen = false; renderPanel(); }
    else if (state.element) { state.element = ''; state.tab = 'slide'; renderDesigner(); }
    else return;
    event.preventDefault();
    event.stopImmediatePropagation();
  }, true);

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
      // Each difference: what it changes (a slide or a chart, by name), which property, and how to take the template back.
      const entries = [];
      const property = name => DIFFERENCE_NAMES[name] || name.replaceAll('_', ' ').replace(/^./, letter => letter.toUpperCase());
      for (const [id, properties] of Object.entries(overrides.slides || {})) for (const name of Object.keys(properties)) entries.push(['Slide', slideName(id), property(name), () => resetSlideProperty(id, name)]);
      for (const [id, properties] of Object.entries(overrides.elements || {})) for (const name of Object.keys(properties)) entries.push(['Chart', elementName(id), property(name), () => resetElementProperty(id, name)]);
      for (const [id, change] of Object.entries(overrides.filters || {})) entries.push(['Chart', elementName(id), `Filters${change.add?.length ? ` + ${change.add.join('; ')}` : ''}${change.remove?.length ? ` − ${change.remove.join('; ')}` : ''}`, () => resetElementProperty(id, 'filters')]);
      for (const id of overrides.hidden_slides || []) entries.push(['Slide', slideName(id), 'Hidden here', () => setSlideHidden(id, false)]);
      for (const id of overrides.shown_optional || []) entries.push(['Slide', slideName(id), 'Optional slide shown', () => setOptionalShown(id, false)]);
      for (const id of overrides.hidden_elements || []) entries.push(['Chart', elementName(id), 'Removed here', () => resetElement(id)]);
      for (const local of overrides.local_slides || []) entries.push(['Slide', local.slide?.title || 'New slide', 'Only in this Design', () => deleteSlideHere(local.slide?.id)]);
      for (const [slideId, elements] of Object.entries(overrides.local_elements || {})) for (const element of elements) entries.push(['Chart', `${elementLabel(element)} · ${slideName(slideId)}`, 'Only in this Design', () => deleteElementHere(element.id)]);
      rows.push(h('div', {class: 'ds-diff-head'}, h('h3', {text: 'Differences from the template'}), h('span', {class: 'ds-design-count', text: String(entries.length)})));
      if (!entries.length) rows.push(h('p', {class: 'form-note', text: 'This Design shows its template as it is.'}));
      // One card per slide or chart, its differences as chips that each take the template back.
      const groups = new Map();
      for (const [kind, name, detail, reset] of entries) {
        const key = `${kind}|${name}`;
        if (!groups.has(key)) groups.set(key, {kind, name, items: []});
        groups.get(key).items.push({detail, reset});
      }
      const resetting = action => guarded(async () => { await action(); refresh(); });
      for (const group of groups.values()) {
        rows.push(h('article', {class: 'ds-diff-card'},
          h('div', {class: 'ds-diff-title'},
            h('span', {class: `ds-diff-icon is-${group.kind.toLowerCase()}`}, icon(group.kind === 'Slide' ? 'slide' : 'chart')),
            h('div', {class: 'ds-diff-name'}, h('span', {class: 'ds-diff-kind', text: group.kind}), h('b', {text: group.name})),
            group.items.length > 1 ? h('button', {type: 'button', class: 'ds-diff-reset-all', disabled: !state.rights.design, title: 'Take the template back for all of them',
              onclick: resetting(async () => { for (const item of group.items) await item.reset(); })}, icon('reset'), 'Reset all') : null),
          h('div', {class: 'ds-diff-chips'}, group.items.map(item => h('span', {class: 'ds-diff-chip'}, h('span', {text: item.detail}),
            h('button', {type: 'button', class: 'ds-diff-chip-reset', disabled: !state.rights.design, title: 'Reset to template', 'aria-label': `Reset ${item.detail} to template`,
              onclick: resetting(item.reset)}, icon('reset')))))));
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

  // Parameters: the questions a template leaves open, each Design of it answering them in PPT Scope & Filters. The list at
  // the left, the parameter chosen at the right with how to use it (and where it is used).
  const PARAMETER_TYPES = {
    values: ['Field values', 'Values of a field each Design chooses (its Cities, its Operators…): used in a chart filter.'],
    number: ['Number', 'A number each Design sets (a threshold, a target): used in a setting or a filter.'],
    text: ['Text', 'A text each Design writes: used in a title or a text box.'],
  };
  const PARAMETER_NAMES = {values: 'Chosen Cities', number: 'Threshold', text: 'Note'};
  function openParametersDialog() {
    const editable = state.detached ? state.rights.design : state.rights.template;
    const scope = state.detached ? 'design' : 'template';
    const slide_set = () => (state.detached ? state.slide_set : state.template);
    const body = h('div', {class: 'ds-design-parameters'});
    let chosen = 0;
    const uses = name => {
      const pattern = new RegExp(`\\{\\s*${name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*\\}`, 'i');
      return (slide_set()?.slides || []).flatMap(slide => [
        ...['title', 'subtitle'].filter(key => pattern.test(slide[key] || '')).map(key => `${slide.title || 'Slide'} · ${key}`),
        ...(slide.elements || []).flatMap(element => Object.entries(element).filter(([, value]) => typeof value === 'string' && pattern.test(value)).map(([key]) => `${elementLabel(element)} · ${key.replaceAll('_', ' ')}`)),
      ]);
    };
    const usage = parameter => (parameter.type === 'values' ? `${parameter.field || 'City'} IN ({${parameter.name}})`
      : parameter.type === 'number' ? `Threshold = {${parameter.name}}` : `{${parameter.name}}`);
    const save = list => edit(target => { target.parameters = list; }, {scope});
    function parameterForm(list, index) {
      const parameter = list[index];
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
      const type = selectInput(Object.entries(PARAMETER_TYPES).map(([value, [label]]) => [value, label]), parameter.type, value => { update({type: value, default: value === 'text' ? '' : null}); commit(); });
      type.disabled = !editable;
      // Each field is kept as soon as it is left (as the other assistance panels of the Designer: no Apply).
      const kept = input => { input.addEventListener('change', commit); return input; };
      const details = [];
      if (parameter.type === 'values') {
        const fieldChoice = fieldPicker(parameter.field, value => { update({field: value}); commit(); }, {disabled: !editable});
        details.push(field('Field', fieldChoice, 'The field whose values each Design chooses.'));
        details.push(h('label', {class: 'ds-design-check'}, h('input', {type: 'checkbox', checked: parameter.multiple !== false, disabled: !editable, onchange: event => { update({multiple: event.target.checked}); commit(); }}), 'Several values'));
        details.push(field('Default values', kept(textInput((parameter.default || []).join(', '), value => update({default: value.split(',').map(item => item.trim()).filter(Boolean)}), {placeholder: 'All'})), 'Separated by commas; empty: All values (the conditions with it are left out).'));
      } else if (parameter.type === 'number') {
        details.push(h('div', {class: 'ds-design-two'}, ...['default', 'min', 'max', 'step'].map(key => field(key[0].toUpperCase() + key.slice(1), kept(h('input', {type: 'number', step: 'any', value: parameter[key] ?? '', disabled: !editable, oninput: event => update({[key]: event.target.value === '' ? null : Number(event.target.value)})}))))));
      } else details.push(field('Default text', kept(textInput(parameter.default, value => update({default: value})))));
      details.push(field('Description', kept(textInput(parameter.description, value => update({description: value}))), 'What Designs read next to it in PPT Scope & Filters.'));
      const used = uses(parameter.name);
      const example = usage(parameter);
      const chart = state.element && shownElement();
      const canFilterChart = editable && parameter.type === 'values' && chart && (chart.kind || 'chart') === 'chart';
      return [
        h('div', {class: 'ds-design-parameter-head'}, field('Name', name), field('Type', type)),
        h('p', {class: 'form-note', text: PARAMETER_TYPES[parameter.type]?.[1] || ''}),
        ...details,
        h('div', {class: 'ds-parameters-howto'},
          h('span', {class: 'ds-design-field-label', text: 'How to use it'}), h('code', {text: example}),
          h('button', {type: 'button', class: 'ds-design-action', onclick: () => navigator.clipboard?.writeText(example).then(() => viewer().status('Copied: paste it in a filter, a setting or a title.')).catch(() => undefined)}, 'Copy'),
          canFilterChart ? h('button', {type: 'button', class: 'ds-design-action', title: `Add ${example} to the filters of ${elementLabel(chart)}`,
            onclick: guarded(async () => {
              const filters = String(chart.filters || '').split(/;\s*/).filter(Boolean);
              if (!filters.some(item => item.replace(/\s+/g, '') === example.replace(/\s+/g, ''))) await setElementValues(state.element, {filters: [...filters, example].join('; ')});
              refresh();
            })}, 'Add to the filters of the chosen chart') : null),
        h('p', {class: 'form-note', text: used.length ? `Used in ${used.length}: ${used.slice(0, 6).join('; ')}${used.length > 6 ? '…' : ''}` : `Not used yet: write {${parameter.name}} in a filter, a setting or a title.`}),
        editable ? h('div', {class: 'ds-design-panel-actions'},
          h('button', {type: 'button', class: 'ds-design-action', disabled: used.length > 0, title: used.length ? 'Remove its uses first' : null,
            onclick: guarded(async () => { list.splice(index, 1); await save(list); refresh(); })}, 'Delete')) : null,
      ];
    }
    const refresh = () => {
      const list = clone(slide_set()?.parameters || []);
      chosen = Math.min(chosen, Math.max(0, list.length - 1));
      const addOf = type => guarded(async () => {
        // Not one of the built-in tokens ({Cities}, {Operators}…), which the PPT fills itself.
        const base = PARAMETER_NAMES[type];
        let index = 1, nameValue = base;
        while (list.some(item => item.name.toLowerCase() === nameValue.toLowerCase())) nameValue = `${base} ${++index}`;
        list.push({id: randomId('p'), name: nameValue, type, ...(type === 'values' ? {field: 'City', multiple: true} : {}), default: type === 'text' ? '' : null, description: ''});
        chosen = list.length - 1;
        await save(list);
        refresh();
      });
      const add = editable ? h('button', {type: 'button', class: 'ds-parameters-add', 'aria-haspopup': 'menu',
        onclick: event => openMenu(event.currentTarget, Object.entries(PARAMETER_TYPES).map(([type, [label]]) => [label, addOf(type), true]))}, '+ Add parameter') : null;
      // Without parameters: what each type is for, each one added from its card.
      const empty = () => [
        h('p', {class: 'ds-parameters-empty-title', text: editable ? 'No parameters yet: add the first one' : 'This template has no parameters.'}),
        editable ? h('div', {class: 'ds-parameters-types'}, Object.entries(PARAMETER_TYPES).map(([type, [label, text]]) => h('button', {type: 'button', class: 'ds-parameters-type', onclick: addOf(type)},
          h('strong', {text: label}), h('span', {text}), h('code', {text: usage({type, name: PARAMETER_NAMES[type], field: 'City'})})))) : null,
      ].filter(Boolean);
      body.replaceChildren(...[
        h('p', {class: 'ds-parameters-intro'}, 'A question the template leaves open: each PPT answers it in PPT Scope & Filters (which Cities, which threshold, which text). Write ',
          h('code', {text: '{Name}'}), ' in a chart filter, a setting or a title.'),
        list.length ? h('div', {class: 'ds-parameters-layout'},
          h('div', {class: 'ds-parameters-list', role: 'list', 'aria-label': 'Parameters'},
            list.map((parameter, index) => {
              const count = uses(parameter.name).length;
              return h('button', {type: 'button', role: 'listitem', class: `ds-parameters-item${index === chosen ? ' is-active' : ''}`, 'aria-current': index === chosen ? 'true' : null,
                onclick: () => { chosen = index; refresh(); }},
              h('strong', {text: parameter.name}), h('span', {class: 'ds-parameters-item-type', text: PARAMETER_TYPES[parameter.type]?.[0] || parameter.type}),
              h('span', {class: 'ds-parameters-uses', text: count ? `Used in ${count}` : 'Not used yet'}));
            }),
            add),
          h('div', {class: 'ds-parameters-detail'}, ...parameterForm(list, chosen))) : h('div', {class: 'ds-parameters-empty'}, ...empty()),
        editable ? null : h('p', {class: 'form-note', text: 'Only the owners of the template change its parameters.'}),
      ].filter(Boolean));
    };
    refresh();
    openDialog('Parameters', `Template ${state.info?.template?.name || ''}`, body, {wide: true});
  }

  // ------------------------------------------------------------------
  // Save Design as, Save as template, Detach
  // ------------------------------------------------------------------
  async function saveAsTemplate() {
    const id = viewer().state().activeId;
    // The template is made of the saved slides: the changes not saved yet are saved first.
    await state.queue.catch(() => undefined);
    if (dirty()) {
      if (!await window.showConfirmDialog('The new template takes the saved slides: save the changes first?', {title: 'Save as template', confirmLabel: 'Save and continue'})) return;
      await saveSlides();
      if (dirty()) return;
    }
    const name = await window.showTextInputDialog('Name of the new template', {title: 'Save as template', value: `${state.info?.name || 'Design'} template`.slice(0, 120), maxLength: 120, confirmLabel: 'Save'});
    if (!name || !String(name).trim()) return;
    const result = await api(`/${encodeURIComponent(id)}/save-as-template`, 'POST', {name: String(name).trim()});
    viewer().status(`Saved the template “${result.template}”: new Designs can use it.`);
    await viewer().refreshTemplatesLibrary?.().catch(() => undefined);
  }
  async function saveAsMyDesign() {
    const {design} = viewer().state();
    if (state.templateDirty) throw new Error('Save or discard the changes of the template first: your Design takes the changes of this one only.');
    const name = await window.showTextInputDialog('Name of your Design', {title: 'Save Design as', value: `${design?.name || 'Design'} (mine)`.slice(0, 120), maxLength: 120, confirmLabel: 'Save'});
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
  // The values of the template parameters, in PPT Scope & Filters
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
    // Opening (Edit Design) counts as open: the viewer already looks as the Designer.
    const open = state.active || opening();
    button.hidden = !rights || !(rights.design || rights.template);
    button.classList.toggle('is-active', open);
    button.textContent = open ? 'Close Designer' : 'Open Designer';
    button.title = open ? 'Close the Designer (it asks about the changes not saved)' : 'Edit the slides and charts of this Design and of its template';
    lockViewerActions(open);
  }
  // While designing, the actions of the viewer that would leave the Designer or bypass what it shows wait for it to close;
  // the filters, the scope and the theme stay, as they change what the slides are laid out on.
  const LOCKED_VIEWER_ACTIONS = ['.ds-viewer-top-auto-fields', '#ds-edit', '#ds-viewer-export-ppt', '#ds-viewer-refresh', '#ds-presentation'];
  function lockViewerActions(active) {
    document.querySelectorAll(LOCKED_VIEWER_ACTIONS.join(', ')).forEach(button => {
      button.classList.toggle('is-design-locked', active);
      if (active) {
        if (button.dataset.unlockedTitle === undefined) button.dataset.unlockedTitle = button.title || '';
        button.setAttribute('aria-disabled', 'true');
        button.title = 'Close the Designer to use it';
      } else if (button.dataset.unlockedTitle !== undefined) {
        button.removeAttribute('aria-disabled');
        button.title = button.dataset.unlockedTitle;
        delete button.dataset.unlockedTitle;
      }
    });
  }
  document.addEventListener('click', event => {
    if ((state.active || opening()) && event.target.closest?.('.is-design-locked')) { event.preventDefault(); event.stopImmediatePropagation(); }
  }, true);
  $('ds-design')?.addEventListener('click', guarded(async () => {
    if (opening() && !state.active) { editWhenReady = ''; clearDesignerOpening(); return; }
    if (state.active) { await exitDesigner(); syncDesignerButton(); return; }
    await enterDesigner();
    syncDesignerButton();
  }));
  document.addEventListener('ds:design-opened', event => {
    if (editWhenReady && editWhenReady !== event.detail.id) { editWhenReady = ''; clearDesignerOpening(); }
    exitDesigner({force: true});
    state.designId = event.detail.id;
    state.info = null;
    parameterOptions.clear();
    syncDesignerButton();
    renderParameterValues();
    loadInfo(event.detail.id);
  });
  document.addEventListener('ds:design-closed', () => {
    editWhenReady = '';
    clearDesignerOpening();
    exitDesigner({force: true});
    state.designId = '';
    state.info = null;
    syncDesignerButton();
    renderParameterValues();
  });
  // Prepared again (filters applied): the slide set not saved yet is laid out on the new selection.
  document.addEventListener('ds:prepared', () => {
    if (!state.active) { guarded(enterWhenReady)(); return; }
    // New data: every slide of the list is drawn again.
    state.generation = (state.generation || 0) + 1;
    if (!dirty()) state.syncedToken = viewer().state().prepared?.token;
    if (dirty()) guarded(() => preview(state.designDirty ? {...previewBody(), slide_set: state.slide_set} : previewBody()))();
    else loadFields(viewer().state().prepared?.token);
  });
  // Edit Design (the table of the Designs) opens the viewer of a Design in the Designer, as soon as the Design is prepared.
  // Meanwhile the viewer already looks as the Designer (its bar and panel say it is opening), so it never shows the PPT
  // first.
  let editWhenReady = '';
  const opening = () => Boolean($('ds-viewer')?.classList.contains('ds-designer-opening'));
  function showDesignerOpening() {
    $('ds-viewer').classList.add('ds-designing', 'ds-designer-opening');
    $('ds-design-bar').hidden = false;
    $('ds-design-bar').replaceChildren(h('span', {class: 'ds-design-bar-label', text: 'Designer'}),
      h('span', {class: 'ds-design-busy', text: 'Opening the Designer as soon as the PPT is prepared…'}));
    $('ds-design-panel').hidden = false;
    $('ds-design-panel').replaceChildren(h('div', {class: 'ds-design-panel-body'},
      h('p', {class: 'ds-design-empty', text: 'The slides and charts of this Design open here as soon as its PPT dataset is prepared.'})));
    syncDesignerButton();
  }
  function clearDesignerOpening() {
    if (!opening()) return;
    $('ds-viewer').classList.remove('ds-designer-opening');
    if (!state.active) {
      $('ds-viewer').classList.remove('ds-designing');
      $('ds-design-bar').hidden = true;
      $('ds-design-bar').replaceChildren();
      $('ds-design-panel').hidden = true;
      $('ds-design-panel').replaceChildren();
    }
    syncDesignerButton();
  }
  async function enterWhenReady() {
    const {activeId, prepared} = viewer().state();
    if (!editWhenReady || editWhenReady !== activeId || !prepared?.token || state.active) return;
    editWhenReady = '';
    try {
      await enterDesigner();
    } finally {
      clearDesignerOpening();
    }
    syncDesignerButton();
  }
  document.addEventListener('ds:edit-design', event => {
    editWhenReady = event.detail.id;
    showDesignerOpening();
    guarded(enterWhenReady)();
  });
  // Chart Type closes on a click outside it (its tab opens and closes it).
  document.addEventListener('pointerdown', event => {
    if (!state.typesOpen || !$('ds-design-types') || event.target.closest?.('#ds-design-types, .ds-design-types-tab')) return;
    state.typesOpen = false;
    renderPanel();
  }, true);
  // A click anywhere in the viewer but on a chart (the slide around its charts, the head of the viewer…) leaves the chart
  // chosen: the panel shows the slide again. The panel, Chart Type, the bar of the Designer, menus and dialogs act on the chart.
  const KEEPS_ELEMENT = '.ds-chart, #ds-design-panel, #ds-design-types, #ds-design-bar, .ds-design-popover, .ds-design-dialog-overlay, .confirm-overlay:not(#ds-viewer)';
  document.addEventListener('click', event => {
    if (!state.active || !state.element || !event.target.closest?.('#ds-viewer') || event.target.closest(KEEPS_ELEMENT)) return;
    state.element = '';
    state.tab = 'slide';
    renderDesigner();
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
