/* Presentations of the Help: a ```presentations block of a Help chapter lists the presentations (by id, one per line) that
   the server generates (/api/presentations). Each one shows as a card that opens it in a slide viewer, as the preview of a
   Bundle Report Template: its sections and slides on the left, the chosen slide on the right (the wheel and the arrow keys
   go through the slides; Ctrl/Cmd+wheel, a rectangle or the buttons zoom it), the slides gone through below it, and its
   PowerPoint to download. Slideshow plays it full screen, slide after slide with a transition, as the presentation mode
   of PPT Dashboards. */
(function () {
  // The server tells where the presentations it generated are, whether it is generating them and, when it cannot, why.
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
  // (A slide of the full presentation is the picture of that slide in the presentation its section names.)
  const slideUrl = (presentation, index, thumb = false) => {
    const slide = slidesOf(presentation)[index] || {};
    const [folder, number] = slide.source ? [slide.source, slide.position] : [presentation.id, index];
    return versioned(`${base}/${folder}/${thumb ? 'thumb' : 'slide'}-${pad(number + 1)}.png`);
  };
  const fileUrl = (presentation) => versioned(`${base}/${presentation.file}`);
  // Every slide with its number (from 0) and section, and the presentation it comes from with its number there.
  const slidesOf = (presentation) => {
    let index = 0;
    return presentation.sections.flatMap((section) => section.slides.map((title, position) => (
      {index: index++, title, section: section.title, source: section.presentation, position})));
  };
  const count = (total) => `${total} slide${total === 1 ? '' : 's'}`;
  // The direct link of a presentation (at a slide other than the first): this page, which opens it in the slide viewer.
  const linkOf = (presentation, index = 0) => {
    const url = new URL(window.location.pathname, window.location.origin);
    url.searchParams.set('presentation', presentation.id);
    if (index > 0) url.searchParams.set('slide', String(index + 1));
    return url.href;
  };
  // The presentation and slide (from 0) a link asks for.
  const linked = () => {
    const query = new URLSearchParams(window.location.search);
    return {id: query.get('presentation') || '', index: Math.max(0, (Number.parseInt(query.get('slide') || '1', 10) || 1) - 1)};
  };
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
    if (!copied) throw new Error('The browser did not let the page copy the link.');
  };
  // The link copied by a button, which says so for a moment; where the browser refuses it, the link is shown to copy.
  const copyLink = async (button, link) => {
    const label = button.innerHTML;
    try {
      await copyText(link);
      button.textContent = 'Link copied';
      button.classList.add('is-copied');
      window.setTimeout(() => { button.innerHTML = label; button.classList.remove('is-copied'); }, 1600);
    } catch (_error) {
      window.prompt('Copy the link of the presentation:', link);
    }
  };
  // The transition effects of the slideshow, as those of the presentation mode of PPT Dashboards.
  const EFFECTS = [['none', 'None'], ['random', 'Random'], ['blinds', 'Blinds'], ['blur', 'Blur'], ['bounce', 'Bounce'], ['curtain', 'Curtain'],
    ['fade', 'Fade'], ['flip', 'Flip'], ['mosaic', 'Mosaic'], ['rise', 'Rise'], ['slide-left', 'Slide from left'], ['slide', 'Slide from right'],
    ['rotate', 'Soft rotate'], ['wipe', 'Wipe'], ['zoom', 'Zoom']];
  const RANDOM_EFFECTS = EFFECTS.map(([value]) => value).filter((value) => !['none', 'random'].includes(value));
  // The icons of the slideshow, drawn the same on every device (the ▶ character is an emoji on some phones).
  const ICONS = {
    play: '<svg class="presentation-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M8 5.14v13.72a1 1 0 0 0 1.52.85l11.1-6.86a1 1 0 0 0 0-1.7L9.52 4.29A1 1 0 0 0 8 5.14Z" fill="currentColor"/></svg>',
    pause: '<svg class="presentation-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><rect x="6" y="4.5" width="4.2" height="15" rx="1.4" fill="currentColor"/><rect x="13.8" y="4.5" width="4.2" height="15" rx="1.4" fill="currentColor"/></svg>',
    previous: '<svg class="presentation-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="m14.5 6-6 6 6 6" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    next: '<svg class="presentation-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="m9.5 6 6 6-6 6" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    stop: '<svg class="presentation-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M7 7l10 10M17 7 7 17" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"/></svg>',
  };

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
    const actions = node('div', undefined, 'presentation-card-actions');
    const download = node('a', 'Download PowerPoint', 'presentation-card-download');
    download.href = fileUrl(presentation);
    download.download = presentation.download;
    const share = node('button', 'Copy link', 'presentation-card-link');
    share.type = 'button';
    share.title = 'Copy the direct link of this presentation: it opens it in the slide viewer';
    share.addEventListener('click', () => copyLink(share, linkOf(presentation)));
    actions.append(download, share);
    item.append(open, actions);
    return item;
  }

  // The cards of the presentations `ids` and, while the server generates them, a note for those not there yet.
  function gallery(ids, data) {
    const block = node('div', undefined, 'presentation-block');
    block.dataset.presentationIds = ids.join(' ');
    const found = ids.map((id) => (data.presentations || []).find((item) => item.id === id)).filter(Boolean);
    const missing = ids.length - found.length;
    if (found.length) {
      const cards = node('div', undefined, 'presentation-gallery');
      found.forEach((presentation) => cards.append(card(presentation)));
      block.append(cards);
    }
    if (!found.length) {
      const why = data.updating ? 'The server is generating the presentations: they show here in a minute.'
        : data.unavailable ? `The presentations cannot be generated on this server: ${data.unavailable}` : 'The presentations have not been generated yet.';
      block.append(node('p', why, data.unavailable && !data.updating ? 'presentation-error' : 'presentation-updating'));
    } else if (missing && data.updating) {
      block.append(node('p', `The server is generating ${missing === 1 ? 'one more presentation' : `${missing} more presentations`}: ${missing === 1 ? 'it shows' : 'they show'} here in a minute.`, 'presentation-updating'));
    }
    return block;
  }

  // While the server generates them, the cards follow once they are ready.
  function follow(container) {
    const timer = setInterval(async () => {
      manifest = null;
      let data;
      try {
        data = await load();
      } catch (error) {
        clearInterval(timer);
        return;
      }
      if (data.updating) return;
      clearInterval(timer);
      container.querySelectorAll('[data-presentations-updating]').forEach((note) => note.remove());
      container.querySelectorAll('[data-presentation-ids]').forEach((block) => block.replaceWith(gallery(block.dataset.presentationIds.split(' '), data)));
      openLinked(data);
    }, 10000);
  }

  // The presentation of a direct link, opened in the slide viewer once (when it is there).
  let linkOpened = false;
  function openLinked(data) {
    const {id, index} = linked();
    const presentation = id && !linkOpened && (data.presentations || []).find((item) => item.id === id);
    if (!presentation) return;
    linkOpened = true;
    openViewer(presentation, index);
  }

  // Each ```presentations block of the chapter becomes the cards of its presentations; a direct link opens its
  // presentation in the slide viewer.
  async function enhance(container) {
    const blocks = [...container.querySelectorAll('pre > code.language-presentations')];
    if (!blocks.length && !linked().id) return;
    let data;
    try {
      data = await load();
    } catch (error) {
      blocks.forEach((code) => code.parentElement.replaceWith(node('p', error.message, 'presentation-error')));
      return;
    }
    blocks.forEach((code, position) => {
      // (While they are generated again, the last presentations show.)
      if (data.updating && position === 0 && (data.presentations || []).length) {
        const note = node('p', 'Updating the presentations: they show the last ones until then.', 'presentation-updating');
        note.dataset.presentationsUpdating = '';
        code.parentElement.before(note);
      }
      code.parentElement.replaceWith(gallery(code.textContent.split(/\s+/).filter(Boolean), data));
    });
    openLinked(data);
    if (data.updating) follow(container);
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
          <p class="presentation-hint">Wheel or ↑ ↓ to change slide · Ctrl/Cmd+wheel to zoom at the pointer · drag a rectangle to zoom into it · Shift+drag or the middle button to move · double-click for the whole slide</p>
          <div class="presentation-stage"><img alt="" draggable="false"></div>
        </section>
      </div>
      <div class="presentation-show" data-presentation-show-layer tabindex="-1" hidden>
        <img class="presentation-show-back" alt="" draggable="false">
        <img class="presentation-show-front" alt="" draggable="false">
        <div class="presentation-show-progress" aria-hidden="true"><span></span></div>
        <div class="presentation-show-controls" role="group" aria-label="Slideshow">
          <button type="button" data-presentation-show="previous" title="Previous slide (← or ↑)" aria-label="Previous slide">${ICONS.previous}</button>
          <button type="button" data-presentation-show="toggle" title="Pause (Space)" aria-label="Pause">${ICONS.pause}</button>
          <button type="button" data-presentation-show="next" title="Next slide (→ or ↓)" aria-label="Next slide">${ICONS.next}</button>
          <span class="presentation-show-counter" aria-live="polite"></span>
          <button type="button" data-presentation-show="stop" title="Stop the slideshow (Esc)" aria-label="Stop the slideshow">${ICONS.stop}</button>
        </div>
      </div>
      <footer class="presentation-dialog-actions">
        <div class="presentation-tools">
          <button type="button" data-presentation-viewer="zoom-in" title="Zoom in (+)" aria-label="Zoom in">+</button>
          <button type="button" data-presentation-viewer="zoom-out" title="Zoom out (−)" aria-label="Zoom out">−</button>
          <button type="button" data-presentation-viewer="reset" title="Whole slide (0 or double-click)" aria-label="Whole slide">⤢</button>
          <span class="presentation-separator" aria-hidden="true"></span>
          <div class="presentation-show-menu">
            <button type="button" class="presentation-show-button" data-presentation-show-open aria-expanded="false" title="Present the slides full screen, one after the other, with a transition" aria-label="Slideshow">${ICONS.play}<span class="presentation-word">Slideshow</span></button>
            <form class="presentation-show-settings" data-presentation-show-settings hidden aria-label="Slideshow settings">
              <p class="presentation-show-heading">Automatic slide show</p>
              <label>Seconds per slide<input name="delay" type="number" min="1" max="300" step="1" value="8" inputmode="numeric"></label>
              <label>Transition duration (seconds)<input name="duration" type="number" min="0.1" max="10" step="0.1" value="1" inputmode="decimal"></label>
              <label>Transition effect<select name="effect">${EFFECTS.map(([value, label]) => `<option value="${value}"${value === 'flip' ? ' selected' : ''}>${label}</option>`).join('')}</select></label>
              <label class="presentation-show-check"><input name="loop" type="checkbox"> Start again after the last slide</label>
              <div class="presentation-show-actions">
                <button type="button" class="presentation-secondary" data-presentation-show-cancel>Cancel</button>
                <button type="submit" class="presentation-show-start">${ICONS.play}Start slideshow</button>
              </div>
            </form>
          </div>
        </div>
        <div class="presentation-steps" role="group" aria-label="Slides">
          <button type="button" class="presentation-step presentation-step-previous" data-presentation-viewer="previous" title="Previous slide (← or ↑)" aria-label="Previous slide"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M19 12H5"/><path d="m11 18-6-6 6-6"/></svg></button>
          <span class="presentation-page-label" aria-live="polite">1 / 1</span>
          <button type="button" class="presentation-step presentation-step-next" data-presentation-viewer="next" title="Next slide (→ or ↓)" aria-label="Next slide"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M5 12h14"/><path d="m13 6 6 6-6 6"/></svg></button>
        </div>
        <div class="presentation-dialog-buttons">
          <button type="button" class="presentation-secondary" data-presentation-link title="Copy the direct link of this slide: it opens the presentation in the slide viewer" aria-label="Copy link"><span class="presentation-word">Copy </span>link</button>
          <button type="button" class="presentation-secondary" data-presentation-close>Close</button>
          <a class="presentation-download" href="#" download title="Download PowerPoint" aria-label="Download PowerPoint">Download<span class="presentation-download-format">PowerPoint</span></a>
        </div>
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
    const share = dialog.querySelector('[data-presentation-link]');
    share.addEventListener('click', () => copyLink(share, linkOf(current, viewerIndex)));
    // Closed, the page has its own address again.
    dialog.addEventListener('close', () => {
      const url = new URL(window.location.href);
      url.searchParams.delete('presentation');
      url.searchParams.delete('slide');
      window.history.replaceState(window.history.state, '', url.href);
    });
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
    // While it is open, the address of the page is the direct link of the slide shown (with the anchor of the page).
    window.history.replaceState(window.history.state, '', `${linkOf(current, viewerIndex)}${window.location.hash}`);
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
    toggle.innerHTML = show.running ? ICONS.pause : ICONS.play;
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
    // A click on the slide goes to the next one, and a swipe of a touch screen to the next or previous one; the controls
    // show while the pointer moves.
    let swipe = null;
    let swiped = false;
    layer.addEventListener('pointerdown', (event) => { if (event.pointerType === 'touch') swipe = {x: event.clientX, y: event.clientY}; });
    layer.addEventListener('pointerup', (event) => {
      if (!swipe || event.pointerType !== 'touch') return;
      const dx = event.clientX - swipe.x, dy = event.clientY - swipe.y;
      swipe = null;
      if (Math.abs(dx) > 50 && Math.abs(dx) > 1.5 * Math.abs(dy)) {
        swiped = true;
        moveShow(dx < 0 ? 1 : -1);
        revealShowControls();
      }
    });
    layer.addEventListener('click', (event) => {
      if (swiped) {
        swiped = false;
        return;
      }
      if (!event.target.closest('.presentation-show-controls')) moveShow(1);
    });
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
    // The wheel goes through the slides, one per turn of the wheel or swipe of the touchpad; with Ctrl or Cmd (or a pinch of
    // the touchpad, which comes with Ctrl) it zooms at the pointer.
    let wheelTravel = 0;
    let wheelTurnedAt = 0;
    stage.addEventListener('wheel', (event) => {
      if (!image.naturalWidth) return;
      event.preventDefault();
      if (event.ctrlKey || event.metaKey) {
        const point = local(event);
        zoomView(Math.exp(-event.deltaY * 0.0015), point.x, point.y);
        return;
      }
      const now = Date.now();
      if (now - wheelTurnedAt < 350) return;
      wheelTravel = Math.sign(wheelTravel) === Math.sign(event.deltaY) ? wheelTravel + event.deltaY : event.deltaY;
      if (Math.abs(wheelTravel) < 40) return;
      showSlide(viewerIndex + Math.sign(wheelTravel));
      wheelTravel = 0;
      wheelTurnedAt = now;
    }, {passive: false});
    let drag = null;
    // On a touch screen one finger swipes from slide to slide (or moves the slide once zoomed), two fingers pinch to zoom and
    // a double tap shows the whole slide.
    const touches = new Map();
    let pinch = null;
    let tappedAt = 0;
    stage.addEventListener('pointerdown', (event) => {
      if (event.pointerType === 'touch') {
        if (!image.naturalWidth) return;
        event.preventDefault();
        touches.set(event.pointerId, local(event));
        try { stage.setPointerCapture(event.pointerId); } catch { /* (The pointer may be gone already.) */ }
        if (touches.size === 2) {
          const [a, b] = [...touches.values()];
          pinch = {distance: Math.hypot(a.x - b.x, a.y - b.y) || 1};
          drag = null;
        } else if (touches.size === 1) {
          drag = {start: local(event), pan: view.scale > view.fit * 1.001, touch: true, rectangle: null, x: view.x, y: view.y};
        }
        return;
      }
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
      if (event.pointerType === 'touch' && touches.has(event.pointerId)) {
        touches.set(event.pointerId, local(event));
        if (pinch && touches.size === 2) {
          const [a, b] = [...touches.values()];
          const distance = Math.hypot(a.x - b.x, a.y - b.y) || 1;
          zoomView(distance / pinch.distance, (a.x + b.x) / 2, (a.y + b.y) / 2);
          pinch.distance = distance;
          return;
        }
      }
      if (!drag) return;
      const point = local(event);
      if (drag.pan) {
        view.x = drag.x + point.x - drag.start.x;
        view.y = drag.y + point.y - drag.start.y;
        clampView();
        renderView();
        return;
      }
      if (!drag.rectangle) return;
      Object.assign(drag.rectangle.style, {
        left: `${Math.min(drag.start.x, point.x)}px`, top: `${Math.min(drag.start.y, point.y)}px`,
        width: `${Math.abs(point.x - drag.start.x)}px`, height: `${Math.abs(point.y - drag.start.y)}px`,
      });
    });
    const releaseTouch = (event) => {
      touches.delete(event.pointerId);
      if (touches.size < 2) pinch = null;
    };
    const endDrag = (event) => {
      if (event?.pointerType === 'touch') releaseTouch(event);
      if (!drag) return;
      const {start, pan, rectangle, touch} = drag;
      drag = null;
      if (touch && event) {
        const point = local(event);
        const dx = point.x - start.x, dy = point.y - start.y;
        if (!pan && Math.abs(dx) > 50 && Math.abs(dx) > 1.5 * Math.abs(dy)) showSlide(viewerIndex + (dx < 0 ? 1 : -1));
        else if (Math.abs(dx) < 8 && Math.abs(dy) < 8) {
          if (Date.now() - tappedAt < 320) fitView();
          tappedAt = Date.now();
        }
        return;
      }
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
    stage.addEventListener('pointercancel', (event) => {
      if (event.pointerType === 'touch') releaseTouch(event);
      endDrag(null);
    });
    stage.addEventListener('dblclick', fitView);
    dialog.addEventListener('keydown', (event) => {
      if (event.target.closest?.('input, select, textarea')) return;
      if (show.active) {
        if (['ArrowLeft', 'ArrowUp', 'PageUp'].includes(event.key)) moveShow(-1);
        else if (['ArrowRight', 'ArrowDown', 'PageDown', 'Enter'].includes(event.key)) moveShow(1);
        else if (event.key === ' ' || event.key === 'k') toggleShow();
        else if (event.key === 'Home') moveShow(-Number.MAX_SAFE_INTEGER);
        else if (event.key === 'End') moveShow(Number.MAX_SAFE_INTEGER);
        else return;
        revealShowControls();
        event.preventDefault();
        return;
      }
      if (['ArrowLeft', 'ArrowUp', 'PageUp'].includes(event.key)) showSlide(viewerIndex - 1);
      else if (['ArrowRight', 'ArrowDown', 'PageDown', ' '].includes(event.key)) showSlide(viewerIndex + 1);
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
