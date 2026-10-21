/* Presentations of the Help: a ```presentations block of a Help chapter lists the presentations (by id, one per line) of
   static/presentations/presentations.json. Each one shows as a card that opens it in a slide viewer, as the preview of a
   Bundle Report Template: its sections and slides on the left, the chosen slide on the right (zoomed with the wheel, a
   rectangle or the buttons) and its PowerPoint to download. Slideshow plays it full screen, slide after slide with a
   transition, as the presentation mode of PPT Dashboards. */
(function () {
  // The server tells where the presentations are (generated with live figures, or those kept with the application) and
  // whether new figures are being drawn.
  let manifest = null;
  let base = '/presentations/files';
  let version = '';
  const load = () => {
    manifest = manifest || fetch('/api/presentations', {cache: 'no-cache', credentials: 'same-origin'}).then((response) => {
      if (!response.ok) throw new Error('The presentations could not be loaded.');
      return response.json();
    }).then((data) => {
      base = data.base || base;
      version = data.key || data.generated_at || '';
      return data;
    });
    return manifest;
  };
  const node = (tag, text, className) => {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (className) element.className = className;
    return element;
  };
  const pad = (number) => String(number).padStart(2, '0');
  const versioned = (url) => (version ? `${url}?v=${encodeURIComponent(version)}` : url);
  const slideUrl = (presentation, index, thumb = false) => versioned(`${base}/${presentation.id}/${thumb ? 'thumb' : 'slide'}-${pad(index + 1)}.png`);
  const fileUrl = (presentation) => versioned(`${base}/${presentation.file}`);
  // Every slide with its number (from 0) and section.
  const slidesOf = (presentation) => {
    let index = 0;
    return presentation.sections.flatMap((section) => section.slides.map((title) => ({index: index++, title, section: section.title})));
  };
  const count = (total) => `${total} slide${total === 1 ? '' : 's'}`;
  // The transition effects of the slideshow, as those of the presentation mode of PPT Dashboards.
  const EFFECTS = [['none', 'None'], ['random', 'Random'], ['blinds', 'Blinds'], ['blur', 'Blur'], ['bounce', 'Bounce'], ['curtain', 'Curtain'],
    ['fade', 'Fade'], ['flip', 'Flip'], ['mosaic', 'Mosaic'], ['rise', 'Rise'], ['slide-left', 'Slide from left'], ['slide', 'Slide from right'],
    ['rotate', 'Soft rotate'], ['wipe', 'Wipe'], ['zoom', 'Zoom']];
  const RANDOM_EFFECTS = EFFECTS.map(([value]) => value).filter((value) => !['none', 'random'].includes(value));

  function card(presentation) {
    const total = slidesOf(presentation).length;
    const item = node('article', undefined, 'presentation-card');
    const open = node('button', undefined, 'presentation-card-open');
    open.type = 'button';
    open.title = `Open ${presentation.title} in the slide viewer`;
    const cover = node('img', undefined, 'presentation-card-cover');
    cover.src = slideUrl(presentation, 0, true);
    cover.alt = '';
    const badge = node('span', count(total), 'presentation-card-badge');
    const body = node('span', undefined, 'presentation-card-body');
    body.append(node('strong', presentation.title, 'presentation-card-title'), node('span', presentation.description, 'presentation-card-description'));
    open.append(cover, badge, body);
    open.addEventListener('click', () => openViewer(presentation, 0));
    const download = node('a', 'Download PowerPoint', 'presentation-card-download');
    download.href = fileUrl(presentation);
    download.download = presentation.download;
    item.append(open, download);
    return item;
  }

  // Each ```presentations block of the chapter becomes the cards of its presentations.
  async function enhance(container) {
    const blocks = [...container.querySelectorAll('pre > code.language-presentations')];
    if (!blocks.length) return;
    let data;
    try {
      data = await load();
    } catch (error) {
      blocks.forEach((code) => code.parentElement.replaceWith(node('p', error.message, 'presentation-error')));
      return;
    }
    blocks.forEach((code, position) => {
      // (While new figures are drawn, the last presentations show.)
      if (data.updating && position === 0) code.parentElement.before(node('p', 'Updating the figures of the presentations: they show the last ones until then.', 'presentation-updating'));
      const gallery = node('div', undefined, 'presentation-gallery');
      code.textContent.split(/\s+/).filter(Boolean).forEach((id) => {
        const presentation = (data.presentations || []).find((item) => item.id === id);
        if (presentation) gallery.append(card(presentation));
      });
      code.parentElement.replaceWith(gallery);
    });
  }

  // -- the viewer --------------------------------------------------------------------------------------------------
  let dialog = null;
  let current = null;
  let viewerIndex = 0;
  let view = {scale: 1, fit: 1, x: 0, y: 0};
  let elements = {};

  function buildDialog() {
    dialog = node('dialog', undefined, 'presentation-dialog');
    dialog.setAttribute('aria-labelledby', 'presentation-dialog-title');
    dialog.innerHTML = `
      <header class="presentation-dialog-head">
        <div><p class="eyebrow" data-presentation-count>Presentation</p><h2 id="presentation-dialog-title"></h2></div>
        <button type="button" class="presentation-dialog-close" data-presentation-close aria-label="Close the presentation">×</button>
      </header>
      <div class="presentation-preview">
        <nav class="presentation-nav" aria-label="Sections and slides of the presentation"></nav>
        <section class="presentation-view" aria-label="Slide">
          <div class="presentation-tools">
            <button type="button" data-presentation-viewer="previous" title="Previous slide (←)" aria-label="Previous slide">‹</button>
            <span class="presentation-page-label" aria-live="polite">1 / 1</span>
            <button type="button" data-presentation-viewer="next" title="Next slide (→)" aria-label="Next slide">›</button>
            <span class="presentation-separator" aria-hidden="true"></span>
            <button type="button" data-presentation-viewer="zoom-in" title="Zoom in (+)" aria-label="Zoom in">+</button>
            <button type="button" data-presentation-viewer="zoom-out" title="Zoom out (−)" aria-label="Zoom out">−</button>
            <button type="button" data-presentation-viewer="reset" title="Whole slide (0 or double-click)" aria-label="Whole slide">⤢</button>
            <span class="presentation-separator" aria-hidden="true"></span>
            <div class="presentation-show-menu">
              <button type="button" class="presentation-show-button" data-presentation-show-open aria-expanded="false" title="Present the slides full screen, one after the other, with a transition">▶ Slideshow</button>
              <form class="presentation-show-settings" data-presentation-show-settings hidden aria-label="Slideshow settings">
                <p class="presentation-show-heading">Automatic slide show</p>
                <label>Seconds per slide<input name="delay" type="number" min="1" max="300" step="1" value="8" inputmode="numeric"></label>
                <label>Transition duration (seconds)<input name="duration" type="number" min="0.1" max="10" step="0.1" value="1" inputmode="decimal"></label>
                <label>Transition effect<select name="effect">${EFFECTS.map(([value, label]) => `<option value="${value}"${value === 'flip' ? ' selected' : ''}>${label}</option>`).join('')}</select></label>
                <label class="presentation-show-check"><input name="loop" type="checkbox"> Start again after the last slide</label>
                <div class="presentation-show-actions">
                  <button type="button" class="presentation-secondary" data-presentation-show-cancel>Cancel</button>
                  <button type="submit" class="presentation-show-start">Start slideshow</button>
                </div>
              </form>
            </div>
            <span class="presentation-hint">Wheel to zoom at the pointer · drag a rectangle to zoom into it · Shift+drag or the middle button to move · double-click for the whole slide</span>
          </div>
          <div class="presentation-stage"><img alt="" draggable="false"></div>
        </section>
      </div>
      <div class="presentation-show" data-presentation-show-layer tabindex="-1" hidden>
        <img class="presentation-show-back" alt="" draggable="false">
        <img class="presentation-show-front" alt="" draggable="false">
        <div class="presentation-show-progress" aria-hidden="true"><span></span></div>
        <div class="presentation-show-controls" role="group" aria-label="Slideshow">
          <button type="button" data-presentation-show="previous" title="Previous slide (←)" aria-label="Previous slide">‹</button>
          <button type="button" data-presentation-show="toggle" title="Pause (Space)" aria-label="Pause">❚❚</button>
          <button type="button" data-presentation-show="next" title="Next slide (→)" aria-label="Next slide">›</button>
          <span class="presentation-show-counter" aria-live="polite"></span>
          <button type="button" data-presentation-show="stop" title="Stop the slideshow (Esc)" aria-label="Stop the slideshow">✕</button>
        </div>
      </div>
      <footer class="presentation-dialog-actions">
        <button type="button" class="presentation-secondary" data-presentation-close>Close</button>
        <a class="presentation-download" href="#" download>Download PowerPoint</a>
      </footer>`;
    document.body.append(dialog);
    elements = {
      title: dialog.querySelector('#presentation-dialog-title'), count: dialog.querySelector('[data-presentation-count]'),
      nav: dialog.querySelector('.presentation-nav'), label: dialog.querySelector('.presentation-page-label'),
      stage: dialog.querySelector('.presentation-stage'), image: dialog.querySelector('.presentation-stage img'),
      download: dialog.querySelector('.presentation-download'),
      showOpen: dialog.querySelector('[data-presentation-show-open]'), settings: dialog.querySelector('[data-presentation-show-settings]'),
      layer: dialog.querySelector('[data-presentation-show-layer]'), back: dialog.querySelector('.presentation-show-back'),
      front: dialog.querySelector('.presentation-show-front'), progress: dialog.querySelector('.presentation-show-progress span'),
      counter: dialog.querySelector('.presentation-show-counter'), toggle: dialog.querySelector('[data-presentation-show="toggle"]'),
    };
    dialog.querySelectorAll('[data-presentation-close]').forEach((button) => button.addEventListener('click', () => dialog.close()));
    // A click on the backdrop closes it too.
    dialog.addEventListener('click', (event) => { if (event.target === dialog) dialog.close(); });
    bindViewer();
    bindSlideshow();
  }

  function renderView() {
    elements.image.style.transform = `translate(${view.x}px, ${view.y}px) scale(${view.scale})`;
    elements.stage.classList.toggle('is-zoomed', view.scale > view.fit * 1.001);
  }
  // The slide keeps covering the stage once larger than it, and stays centred while smaller.
  function clampView() {
    const {stage, image} = elements;
    const width = image.naturalWidth * view.scale, height = image.naturalHeight * view.scale;
    view.x = width <= stage.clientWidth ? (stage.clientWidth - width) / 2 : Math.min(0, Math.max(stage.clientWidth - width, view.x));
    view.y = height <= stage.clientHeight ? (stage.clientHeight - height) / 2 : Math.min(0, Math.max(stage.clientHeight - height, view.y));
  }
  function fitView() {
    const {stage, image} = elements;
    if (!image.naturalWidth || !stage.clientWidth) return;
    view.fit = Math.min(stage.clientWidth / image.naturalWidth, stage.clientHeight / image.naturalHeight);
    view.scale = view.fit;
    clampView();
    renderView();
  }
  function zoomView(factor, centerX = elements.stage.clientWidth / 2, centerY = elements.stage.clientHeight / 2) {
    const next = Math.min(view.fit * 8, Math.max(view.fit, view.scale * factor));
    view.x = centerX - (centerX - view.x) * next / view.scale;
    view.y = centerY - (centerY - view.y) * next / view.scale;
    view.scale = next;
    clampView();
    renderView();
  }

  function showSlide(index) {
    const slides = slidesOf(current);
    viewerIndex = Math.max(0, Math.min(slides.length - 1, index));
    const slide = slides[viewerIndex];
    elements.label.textContent = `Slide ${viewerIndex + 1} / ${slides.length}`;
    elements.image.alt = `Slide ${viewerIndex + 1}: ${slide.title}`;
    elements.stage.classList.add('is-loading');
    elements.image.onload = () => { elements.stage.classList.remove('is-loading'); fitView(); };
    elements.image.src = slideUrl(current, viewerIndex);
    elements.nav.querySelectorAll('.presentation-nav-slide').forEach((button) => {
      const isCurrent = Number(button.dataset.slide) === viewerIndex;
      button.classList.toggle('is-current', isCurrent);
      if (isCurrent) {
        button.setAttribute('aria-current', 'page');
        button.scrollIntoView({block: 'nearest'});
      } else {
        button.removeAttribute('aria-current');
      }
    });
    // The next slide is fetched ahead, so moving through the presentation does not wait for it.
    if (viewerIndex + 1 < slides.length) new Image().src = slideUrl(current, viewerIndex + 1);
  }

  function renderNavigation() {
    const slides = slidesOf(current);
    elements.nav.replaceChildren(...current.sections.map((section) => {
      const group = node('section', undefined, 'presentation-nav-section');
      const sectionSlides = slides.filter((slide) => slide.section === section.title);
      const heading = node('button', section.title, 'presentation-nav-heading');
      heading.type = 'button';
      heading.title = `Go to ${section.title}`;
      heading.addEventListener('click', () => showSlide(sectionSlides[0].index));
      const list = node('ol', undefined, 'presentation-nav-slides');
      sectionSlides.forEach((slide) => {
        const item = node('li');
        const button = node('button', undefined, 'presentation-nav-slide');
        button.type = 'button';
        button.dataset.slide = String(slide.index);
        button.title = slide.title;
        const thumb = node('img', undefined, 'presentation-nav-thumb');
        thumb.src = slideUrl(current, slide.index, true);
        thumb.alt = '';
        thumb.loading = 'lazy';
        const caption = node('span', undefined, 'presentation-nav-caption');
        caption.append(node('span', String(slide.index + 1), 'presentation-nav-number'), node('span', slide.title, 'presentation-nav-title'));
        button.append(thumb, caption);
        button.addEventListener('click', () => showSlide(slide.index));
        item.append(button);
        list.append(item);
      });
      group.append(heading, list);
      return group;
    }));
  }

  // -- the slideshow, as the presentation mode of PPT Dashboards ---------------------------------------------------
  const show = {active: false, running: false, delay: 8000, duration: 1, effect: 'flip', loop: false, timer: 0, lastRandom: '', hideControls: 0};

  function showEffect() {
    if (show.effect !== 'random') return show.effect;
    const choices = RANDOM_EFFECTS.filter((effect) => effect !== show.lastRandom);
    show.lastRandom = choices[Math.floor(Math.random() * choices.length)] || 'fade';
    return show.lastRandom;
  }
  // The new slide enters over the one it replaces with the transition, and the progress line runs while it plays.
  function renderShow() {
    const {front, back, progress, counter, toggle} = elements;
    const total = slidesOf(current).length;
    const url = slideUrl(current, viewerIndex);
    showSlide(viewerIndex);
    counter.textContent = `${viewerIndex + 1} / ${total}`;
    toggle.textContent = show.running ? '❚❚' : '▶';
    toggle.title = show.running ? 'Pause (Space)' : 'Play (Space)';
    toggle.setAttribute('aria-label', show.running ? 'Pause' : 'Play');
    if (front.getAttribute('src') !== url) {
      back.src = front.getAttribute('src') || url;
      front.classList.remove('is-entering');
      front.dataset.effect = showEffect();
      front.onload = () => { void front.offsetWidth; front.classList.add('is-entering'); };
      front.src = url;
    }
    progress.classList.remove('is-running');
    void progress.offsetWidth;
    progress.style.animationDuration = `${show.delay}ms`;
    progress.classList.toggle('is-running', show.running);
    if (viewerIndex + 1 < total) new Image().src = slideUrl(current, viewerIndex + 1);
  }
  function scheduleShow() {
    clearTimeout(show.timer);
    if (show.running) show.timer = setTimeout(advanceShow, show.delay);
  }
  function advanceShow() {
    const last = slidesOf(current).length - 1;
    if (viewerIndex < last) viewerIndex += 1;
    else if (show.loop) viewerIndex = 0;
    // (Without Start again, the slideshow pauses on the last slide.)
    else show.running = false;
    renderShow();
    scheduleShow();
  }
  function moveShow(offset) {
    const last = slidesOf(current).length - 1;
    const next = viewerIndex + offset;
    viewerIndex = show.loop ? (next + last + 1) % (last + 1) : Math.max(0, Math.min(last, next));
    renderShow();
    scheduleShow();
  }
  function toggleShow() {
    show.running = !show.running;
    if (show.running && viewerIndex === slidesOf(current).length - 1 && !show.loop) viewerIndex = 0;
    renderShow();
    scheduleShow();
  }
  function revealShowControls() {
    elements.layer.classList.add('is-pointer');
    clearTimeout(show.hideControls);
    show.hideControls = setTimeout(() => elements.layer.classList.remove('is-pointer'), 2500);
  }
  function startShow() {
    const form = elements.settings;
    const number = (name, fallback, low, high) => {
      const value = Number(form.elements[name].value);
      const clamped = Math.max(low, Math.min(high, Number.isFinite(value) && value > 0 ? value : fallback));
      form.elements[name].value = String(clamped);
      return clamped;
    };
    show.delay = number('delay', 8, 1, 300) * 1000;
    show.duration = number('duration', 1, 0.1, 10);
    show.effect = form.elements.effect.value;
    show.loop = form.elements.loop.checked;
    show.lastRandom = '';
    closeShowSettings();
    const {layer, front, back} = elements;
    layer.style.setProperty('--presentation-transition', `${show.duration}s`);
    front.removeAttribute('src');
    back.removeAttribute('src');
    show.active = true;
    show.running = true;
    layer.hidden = false;
    layer.focus({preventScroll: true});
    // Full screen where the browser allows it; otherwise the layer covers the window.
    layer.requestFullscreen?.()?.catch?.(() => {});
    revealShowControls();
    renderShow();
    scheduleShow();
  }
  function stopShow() {
    if (!show.active) return;
    clearTimeout(show.timer);
    clearTimeout(show.hideControls);
    show.active = false;
    show.running = false;
    elements.layer.hidden = true;
    if (document.fullscreenElement === elements.layer) document.exitFullscreen?.()?.catch?.(() => {});
    showSlide(viewerIndex);
  }
  function closeShowSettings() {
    elements.settings.hidden = true;
    elements.showOpen.setAttribute('aria-expanded', 'false');
  }
  function bindSlideshow() {
    const {showOpen, settings, layer} = elements;
    showOpen.addEventListener('click', () => {
      settings.hidden = !settings.hidden;
      showOpen.setAttribute('aria-expanded', String(!settings.hidden));
      if (!settings.hidden) settings.elements.delay.focus();
    });
    settings.querySelector('[data-presentation-show-cancel]').addEventListener('click', closeShowSettings);
    settings.addEventListener('submit', (event) => { event.preventDefault(); startShow(); });
    // A click on the slide goes to the next one; the controls show while the pointer moves.
    layer.addEventListener('click', (event) => { if (!event.target.closest('.presentation-show-controls')) moveShow(1); });
    layer.addEventListener('pointermove', revealShowControls);
    layer.querySelectorAll('[data-presentation-show]').forEach((button) => button.addEventListener('click', () => {
      const action = button.dataset.presentationShow;
      if (action === 'previous') moveShow(-1);
      else if (action === 'next') moveShow(1);
      else if (action === 'toggle') toggleShow();
      else stopShow();
    }));
    // Leaving full screen (Escape) or closing the viewer ends the slideshow.
    document.addEventListener('fullscreenchange', () => { if (show.active && !document.fullscreenElement) stopShow(); });
    dialog.addEventListener('cancel', (event) => {
      if (show.active) { event.preventDefault(); stopShow(); return; }
      if (!settings.hidden) { event.preventDefault(); closeShowSettings(); }
    });
    dialog.addEventListener('close', stopShow);
  }

  function openViewer(presentation, index) {
    if (!dialog) buildDialog();
    current = presentation;
    const total = slidesOf(presentation).length;
    elements.title.textContent = presentation.title;
    elements.count.textContent = `Presentation · ${count(total)}`;
    elements.download.href = fileUrl(presentation);
    elements.download.download = presentation.download;
    renderNavigation();
    if (!dialog.open) dialog.showModal();
    showSlide(index);
  }

  function bindViewer() {
    const {stage, image} = elements;
    const local = (event) => {
      const bounds = stage.getBoundingClientRect();
      return {x: event.clientX - bounds.left, y: event.clientY - bounds.top};
    };
    stage.addEventListener('wheel', (event) => {
      if (!image.naturalWidth) return;
      event.preventDefault();
      const point = local(event);
      zoomView(Math.exp(-event.deltaY * 0.0015), point.x, point.y);
    }, {passive: false});
    let drag = null;
    stage.addEventListener('pointerdown', (event) => {
      if ((event.button !== 0 && event.button !== 1) || !image.naturalWidth) return;
      event.preventDefault();
      const pan = event.button === 1 || event.shiftKey;
      const rectangle = pan ? null : node('div', undefined, 'presentation-viewer-rect');
      if (rectangle) stage.append(rectangle);
      drag = {start: local(event), pan, rectangle, x: view.x, y: view.y};
      try { stage.setPointerCapture(event.pointerId); } catch { /* (The pointer may be gone already.) */ }
      stage.classList.toggle('is-panning', pan);
    });
    stage.addEventListener('pointermove', (event) => {
      if (!drag) return;
      const point = local(event);
      if (drag.pan) {
        view.x = drag.x + point.x - drag.start.x;
        view.y = drag.y + point.y - drag.start.y;
        clampView();
        renderView();
        return;
      }
      Object.assign(drag.rectangle.style, {
        left: `${Math.min(drag.start.x, point.x)}px`, top: `${Math.min(drag.start.y, point.y)}px`,
        width: `${Math.abs(point.x - drag.start.x)}px`, height: `${Math.abs(point.y - drag.start.y)}px`,
      });
    });
    const endDrag = (event) => {
      if (!drag) return;
      const {start, pan, rectangle} = drag;
      drag = null;
      stage.classList.remove('is-panning');
      if (pan || !rectangle) return;
      rectangle.remove();
      if (!event) return;
      const point = local(event);
      const width = Math.abs(point.x - start.x), height = Math.abs(point.y - start.y);
      // A click (or a tiny rectangle) does not zoom.
      if (width < 8 || height < 8) return;
      const factor = Math.min(stage.clientWidth / width, stage.clientHeight / height);
      const centerX = (start.x + point.x) / 2, centerY = (start.y + point.y) / 2;
      const next = Math.min(view.fit * 8, view.scale * factor);
      view.x = stage.clientWidth / 2 - (centerX - view.x) * next / view.scale;
      view.y = stage.clientHeight / 2 - (centerY - view.y) * next / view.scale;
      view.scale = next;
      clampView();
      renderView();
    };
    stage.addEventListener('pointerup', endDrag);
    stage.addEventListener('pointercancel', () => endDrag(null));
    stage.addEventListener('dblclick', fitView);
    dialog.addEventListener('keydown', (event) => {
      if (event.target.closest?.('input, select, textarea')) return;
      if (show.active) {
        if (event.key === 'ArrowLeft' || event.key === 'PageUp') moveShow(-1);
        else if (event.key === 'ArrowRight' || event.key === 'PageDown' || event.key === 'Enter') moveShow(1);
        else if (event.key === ' ' || event.key === 'k') toggleShow();
        else if (event.key === 'Home') moveShow(-Number.MAX_SAFE_INTEGER);
        else if (event.key === 'End') moveShow(Number.MAX_SAFE_INTEGER);
        else return;
        revealShowControls();
        event.preventDefault();
        return;
      }
      if (event.key === 'ArrowLeft' || event.key === 'PageUp') showSlide(viewerIndex - 1);
      else if (event.key === 'ArrowRight' || event.key === 'PageDown' || event.key === ' ') showSlide(viewerIndex + 1);
      else if (event.key === 'Home') showSlide(0);
      else if (event.key === 'End') showSlide(Number.MAX_SAFE_INTEGER);
      else if (event.key === '+' || event.key === '=') zoomView(1.4);
      else if (event.key === '-') zoomView(1 / 1.4);
      else if (event.key === '0') fitView();
      else return;
      event.preventDefault();
    });
    dialog.querySelectorAll('[data-presentation-viewer]').forEach((button) => button.addEventListener('click', () => {
      const action = button.dataset.presentationViewer;
      if (action === 'previous') showSlide(viewerIndex - 1);
      else if (action === 'next') showSlide(viewerIndex + 1);
      else if (action === 'zoom-in') zoomView(1.4);
      else if (action === 'zoom-out') zoomView(1 / 1.4);
      else fitView();
    }));
    window.addEventListener('resize', () => { if (dialog.open) fitView(); });
  }

  window.PresentationViewer = {enhance};
}());
