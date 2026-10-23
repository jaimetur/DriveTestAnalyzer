// A reload (or Back and Forward) returns to where a page was being read; opening a module starts at its top. The pages
// whose panels fill in after they open (Scoring & GAP Analysis, Non-Qualified Calls) use it in three steps:
// - begin(), at the top of their content, before it is drawn: the page is made as tall as the saved position needs and
//   opened there, with what was in view when the page was left (keepSnapshot) shown as it was, dimmed under a gradient
//   with a notice in the middle, while the page fills;
// - follow(), once the page draws its content: the page is kept at the position until its content reaches it and stops
//   growing, then shown and given back its height;
// - keepSnapshot(), when the page is left: a copy of what is in view, for the next begin().
// Every page keeps its position under its own key of the session storage, as {scroll_y}.
(() => {
  const NOTICE = '[data-page-restore-notice]';
  // The key of a page: its view, the user and the workspace.
  const keyOf = (view, workspaceId) => ['drivetest-analyzer', view,
    encodeURIComponent(document.body.dataset.authenticatedUser || 'anonymous'), encodeURIComponent(workspaceId || 'unknown')].join(':');
  // Only a reload (or Back and Forward) returns to the saved position; a section chosen in a menu (#section-…) opens the
  // page there instead.
  const reloaded = () => !window.location.hash
    && ['reload', 'back_forward'].includes(window.performance.getEntriesByType?.('navigation')?.[0]?.type);

  function begin({key, notice, theme = ''}) {
    try {
      if (!reloaded()) return 0;
      const stored = JSON.parse(window.sessionStorage.getItem(key) || 'null');
      const snapshot = JSON.parse(window.sessionStorage.getItem(`${key}:snapshot`) || 'null');
      window.sessionStorage.removeItem(`${key}:snapshot`);
      const top = stored && Number.isFinite(stored.scroll_y) && stored.scroll_y > 0 ? stored.scroll_y : 0;
      if (!top) return 0;
      if ('scrollRestoration' in window.history) window.history.scrollRestoration = 'manual';
      document.documentElement.style.overflowAnchor = 'none';
      document.documentElement.style.minHeight = `${top + window.innerHeight}px`;
      window.scrollTo(0, top);
      const overlay = document.createElement('div');
      overlay.className = `page-restore-overlay${theme ? ` is-${theme}` : ''}`;
      overlay.dataset.pageRestoreNotice = '';
      if (snapshot && typeof snapshot.html === 'string' && snapshot.width === window.innerWidth) {
        // The copy of what was in view, without scripts, scrolled to where it was.
        const frame = document.createElement('iframe');
        frame.className = 'page-restore-snapshot';
        frame.setAttribute('aria-hidden', 'true');
        frame.setAttribute('sandbox', 'allow-same-origin');
        frame.tabIndex = -1;
        frame.addEventListener('load', () => {
          try {
            frame.contentWindow.scrollTo(0, snapshot.scroll_y);
            frame.contentDocument.querySelectorAll('[data-snapshot-scroll-top]').forEach((element) => {
              element.scrollTop = Number(element.dataset.snapshotScrollTop) || 0;
            });
            frame.classList.add('is-ready');
          } catch (_error) {
            // Without it, the gradient alone.
          }
        }, {once: true});
        frame.srcdoc = snapshot.html;
        overlay.append(frame);
      }
      const message = document.createElement('div');
      message.className = 'page-restore-notice';
      message.setAttribute('role', 'status');
      message.textContent = notice;
      overlay.append(message);
      document.body.append(overlay);
      window.setTimeout(() => overlay.remove(), 25000);
      return top;
    } catch (_error) {
      // Optional: without the session storage the page opens at its top.
      return 0;
    }
  }

  // Follows the page as it grows, until the saved position is reached, the user scrolls or twenty seconds pass; busy()
  // tells while the page is still reading parts of its content.
  function follow(target, {busy = null, onDone = null} = {}) {
    let interacted = false;
    const stop = () => { interacted = true; };
    const interactions = ['wheel', 'touchstart', 'keydown', 'pointerdown'];
    interactions.forEach(type => window.addEventListener(type, stop, {passive: true}));
    const deadline = window.performance.now() + 20000;
    // The browser would keep the content in view as the page grows above it; the saved position
    // already refers to the complete page, so it is kept until the page stops growing.
    document.documentElement.style.overflowAnchor = 'none';
    let height = -1;
    let stableSince = window.performance.now();
    const step = () => {
      const now = window.performance.now();
      // The height of the content: meanwhile the page keeps the height the saved position needs (begin), so it stays
      // there instead of going up while it fills.
      const pageHeight = document.body.scrollHeight;
      if (pageHeight !== height) {
        height = pageHeight;
        stableSince = now;
      }
      const maximum = Math.max(0, pageHeight - window.innerHeight);
      if (!interacted) window.scrollTo({left: window.scrollX, top: target, behavior: 'auto'});
      // The dimmed page of the reload shows again once its content reaches the position, or the user takes over.
      const reading = typeof busy === 'function' && busy();
      if ((maximum >= target && !reading) || interacted) document.querySelector(NOTICE)?.remove();
      // Until the content reaches the position and stops growing; content that stays shorter is waited for a while.
      if (!interacted && now < deadline && (reading || now - stableSince < (maximum < target ? 4000 : 1200))) {
        window.setTimeout(step, 120);
        return;
      }
      interactions.forEach(type => window.removeEventListener(type, stop));
      document.documentElement.style.overflowAnchor = '';
      document.documentElement.style.minHeight = '';
      document.querySelector(NOTICE)?.remove();
      if (typeof onDone === 'function') onDone();
    };
    window.requestAnimationFrame(() => window.requestAnimationFrame(step));
  }

  // What is in view when the page is left: a copy of the page without its scripts, with only the parts in view (the
  // others keep their place, empty), its fields as they are, the scroll of its lists and its canvases as images.
  function snapshot() {
    const viewportHeight = window.innerHeight;
    const copyOf = (node) => {
      if (node.nodeType === Node.TEXT_NODE) return node.cloneNode(false);
      if (node.nodeType !== Node.ELEMENT_NODE) return null;
      const tag = node.tagName.toUpperCase();
      if (['SCRIPT', 'NOSCRIPT', 'TEMPLATE', 'IFRAME'].includes(tag) || node.matches(NOTICE)) return null;
      // Styles, drawings and lists of options whole.
      if (['STYLE', 'LINK', 'SVG', 'SELECT'].includes(tag)) {
        const copy = node.cloneNode(true);
        if (tag === 'SELECT') [...node.options].forEach((option, index) => copy.options[index]?.toggleAttribute('selected', option.selected));
        return copy;
      }
      const copy = node.cloneNode(false);
      const box = node.getBoundingClientRect();
      if (!box.width && !box.height && getComputedStyle(node).display !== 'contents') return copy;
      if (box.bottom < 0 || box.top > viewportHeight) {
        copy.style.height = `${box.height}px`;
        copy.style.minHeight = '0';
        copy.style.boxSizing = 'border-box';
        copy.style.overflow = 'hidden';
        return copy;
      }
      if (tag === 'CANVAS') {
        try {
          const image = document.createElement('img');
          image.src = node.toDataURL();
          image.className = node.className;
          image.style.cssText = node.style.cssText;
          image.style.width = `${box.width}px`;
          image.style.height = `${box.height}px`;
          return image;
        } catch (_error) {
          return copy;
        }
      }
      if (tag === 'INPUT') {
        if (['checkbox', 'radio'].includes(node.type)) copy.toggleAttribute('checked', node.checked);
        else copy.setAttribute('value', node.value);
      }
      if (tag === 'TEXTAREA') {
        copy.textContent = node.value;
        return copy;
      }
      if (node.scrollTop) copy.dataset.snapshotScrollTop = String(Math.round(node.scrollTop));
      node.childNodes.forEach((child) => {
        const childCopy = copyOf(child);
        if (childCopy) copy.append(childCopy);
      });
      return copy;
    };
    const attributes = (element) => [...element.attributes].filter(attribute => attribute.name !== 'style')
      .map(attribute => ` ${attribute.name}="${attribute.value.replace(/&/g, '&amp;').replace(/"/g, '&quot;')}"`).join('');
    const head = [...document.head.children].filter(element => element.matches('meta[charset], link[rel="stylesheet"], style'))
      .map(element => element.outerHTML).join('');
    return `<!doctype html><html${attributes(document.documentElement)}><head>${head}</head>${copyOf(document.body).outerHTML}</html>`;
  }

  // Keeps the copy of what is in view when the page is left; not while the page is still returning to a saved position
  // (what is in view is not the page yet).
  function keepSnapshot(key, restoring) {
    const snapshotKey = `${key}:snapshot`;
    try {
      window.sessionStorage.removeItem(snapshotKey);
      if (restoring || !window.scrollY) return;
      const html = snapshot();
      if (html.length > 3000000) return;
      window.sessionStorage.setItem(snapshotKey, JSON.stringify({scroll_y: Math.round(window.scrollY), width: window.innerWidth, html}));
    } catch (_error) {
      // Optional (too large for the session storage…): the reload shows the gradient alone.
      try { window.sessionStorage.removeItem(snapshotKey); } catch (_ignored) { /* Nothing to remove. */ }
    }
  }

  window.PageRestore = {keyOf, reloaded, begin, follow, snapshot, keepSnapshot};
})();
