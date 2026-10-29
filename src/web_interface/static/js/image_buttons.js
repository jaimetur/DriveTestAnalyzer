// Floating buttons over the charts, maps, tables and panels of a page download them as a PNG image, as they are shown,
// or copy them to the clipboard as a screenshot (the button on the left of the download; element_image.js draws them),
// and App Events records each one. Two pairs of buttons for a page: one over the card under the pointer (the outermost
// of its targets), which stays in its place while the pointer moves over the card, and one over the chart or table of
// the card under the pointer, when the card holds several; content drawn again needs nothing of its own.
(() => {
  const ICON = paths => '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" '
    + `stroke-linejoin="round" aria-hidden="true" focusable="false">${paths}</svg>`;
  // The card: a panel with its title bar and the arrow inside it; a chart or table: the arrow into a tray.
  const DOWNLOAD_ICONS = {
    card: ICON('<rect x="2" y="2" width="16" height="16" rx="2.5"/><path d="M2 6.3h16"/><path d="M10 8.8v6.2"/><path d="m7 12.2 3 3 3-3"/>'),
    part: ICON('<path d="M10 3v9"/><path d="m6.5 8.5 3.5 3.5 3.5-3.5"/><path d="M3.5 13v2.5A1.5 1.5 0 0 0 5 17h10a1.5 1.5 0 0 0 1.5-1.5V13"/>'),
  };
  // The screenshot: a camera.
  const CAMERA_ICON = ICON('<path d="M2.5 7A1.5 1.5 0 0 1 4 5.5h2.2l1.3-2h5l1.3 2H16A1.5 1.5 0 0 1 17.5 7v8A1.5 1.5 0 0 1 16 16.5H4'
    + 'A1.5 1.5 0 0 1 2.5 15z"/><circle cx="10" cy="10.8" r="3.1"/>');
  // A dialog, or an overlay of the page that marks itself so, holds the buttons of what it shows (above it).
  const HOSTS = 'dialog[open], [data-image-buttons-host]';
  const TITLES = ':scope > :is(h2, h3, h4, h5, figcaption, caption), :scope > :is(header, summary, .section-head) :is(h2, h3, h4)';

  // A name the file systems accept, from its parts (``Title - Environment.png``).
  function imageFileName(parts, fallback = 'Image') {
    const name = [parts].flat().filter(Boolean).join(' - ').replace(/[\\/:*?"<>|\u0000-\u001f]+/g, ' ')
      .replace(/\s+/g, ' ').trim().slice(0, 150).trim();
    return `${name || fallback}.png`;
  }

  // The text of a heading (without the pills of its scope, which keep it in ``data-title``).
  function headingText(heading) {
    return String(heading?.dataset?.title || heading?.textContent || '').replace(/\s+/g, ' ').trim();
  }

  // The own title of an element: its heading, else the heading just before it.
  function ownTitle(element) {
    const heading = element?.querySelector?.(TITLES);
    if (heading) return headingText(heading);
    const before = element?.previousElementSibling;
    return before?.matches('h2, h3, h4, h5') ? headingText(before) : '';
  }

  // How much of the top of the window the floating section bars of the page hide.
  function floatingBarsBottom() {
    return Math.max(0, ...[...document.querySelectorAll('.section-bar, [data-section-bar]')].map(bar => {
      const box = bar.getBoundingClientRect();
      return box.height && box.top < window.innerHeight / 3 && /sticky|fixed/.test(getComputedStyle(bar).position) ? box.bottom : 0;
    }));
  }

  function recordImageExport(url, details) {
    fetch(url, {
      method: 'POST', credentials: 'same-origin', keepalive: true,
      headers: {Accept: 'application/json', 'Content-Type': 'application/json'}, body: JSON.stringify(details),
    }).catch(() => {});
  }

  // Where the browser does not let the page copy images (an address that is not secure), the screenshot shows in a dialog,
  // to copy it with the menu of the image (a right click, or keeping it pressed) or to download it.
  function showImageToCopy(blob, fileName) {
    const address = URL.createObjectURL(blob);
    const dialog = document.createElement('dialog');
    dialog.className = 'element-image-copy-dialog';
    const eyebrow = document.createElement('p');
    eyebrow.className = 'eyebrow';
    eyebrow.textContent = 'Screenshot';
    const heading = document.createElement('h3');
    heading.textContent = 'Copy the image';
    const strong = document.createElement('strong');
    strong.textContent = 'Copy Image';
    const note = document.createElement('p');
    note.append('This browser lets the page copy images only at a secure address (https, or the application opened on this '
      + 'computer): right-click the image (or keep it pressed) and choose ', strong, '.');
    const image = document.createElement('img');
    image.src = address;
    image.alt = fileName.replace(/\.(png|svg)$/i, '');
    const actions = document.createElement('div');
    actions.className = 'element-image-copy-actions';
    const download = document.createElement('a');
    download.href = address;
    download.download = fileName;
    download.textContent = 'Download';
    const close = document.createElement('button');
    close.type = 'button';
    close.textContent = 'Close';
    close.addEventListener('click', () => dialog.close());
    actions.append(download, close);
    dialog.append(eyebrow, heading, note, image, actions);
    // The page behind does not scroll while it is open.
    const pageOverflow = document.documentElement.style.overflow;
    document.documentElement.style.overflow = 'hidden';
    dialog.addEventListener('close', () => {
      document.documentElement.style.overflow = pageOverflow;
      dialog.remove();
      URL.revokeObjectURL(address);
    });
    // Above any dialog or overlay the image came from.
    (document.querySelector('dialog[open]') || document.body).append(dialog);
    dialog.showModal();
  }

  // ``root``: where the pointer is followed and the buttons live (a dialog or an overlay marked with
  // ``data-image-buttons-host`` holds them while they are over what it shows). ``targets``: the cards and their charts
  // and tables, only those inside ``within``; ``tables`` and ``charts`` tell their kind (else a panel). ``exclude``: what
  // the images leave out; ``obstacles``: the buttons of the page the image buttons keep clear of; ``topInset``: how much
  // of the window the floating bars of the page hide; ``cardOnEdge``: whether those of a card stand on its top edge (else
  // in its corner, as in a dialog); ``singleParts``: the charts or tables that have their buttons also when they are the
  // only one of their card; ``partRow``: the row of buttons of a chart or table that its buttons stand on, at its left
  // (else in its top right corner); ``hiddenCards``: the cards whose buttons the page gives itself (``exportImage`` of
  // the object returned), whose charts and tables keep theirs. ``title(target, card)``, ``fileName(target, title)`` and
  // ``details(target)`` name the image and its App Event; ``record(details)`` records it (by default for ``module``).
  function attachImageButtons({
    root, targets, within = '', tables = '', charts = '', exclude = '', obstacles = '', cardOnEdge = true,
    singleParts = '', partRow = '', hiddenCards = '',
    topInset = floatingBarsBottom,
    title = null, fileName = null, details = () => ({}), module = '', fallbackName = 'Image',
    record = imageDetails => recordImageExport('/api/image-export', {module, ...imageDetails}),
  }) {
    if (!root || !targets) return null;
    const slots = ['card', 'part'].map(level => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'element-image-button';
      button.dataset.imageLevel = level;
      button.hidden = true;
      button.innerHTML = DOWNLOAD_ICONS[level];
      const copy = document.createElement('button');
      copy.type = 'button';
      copy.className = 'element-image-button element-image-copy';
      copy.dataset.imageLevel = level;
      copy.hidden = true;
      copy.innerHTML = CAMERA_ICON;
      root.append(button, copy);
      return {level, button, copy, target: null, hideTimer: 0, inSight: false};
    });
    const [cardSlot] = slots;
    let placeFrame = 0;
    const isImageButton = node => slots.some(slot => slot.button.contains(node) || slot.copy.contains(node));
    const hostOf = target => target.closest(HOSTS) || root;

    // The card under a node (the outermost target) and the chart or table of the card under it.
    function targetsAt(node) {
      const part = node?.closest?.(targets);
      if (!part || !root.contains(part) || (within && !part.closest(within)) || isImageButton(part)) return {card: null, part: null};
      let card = part;
      // (A dialog or overlay starts cards of its own.)
      const host = part.closest(HOSTS);
      for (let outer = card.parentElement?.closest(targets); outer && (!host || host.contains(outer));
        outer = outer.parentElement?.closest(targets)) card = outer;
      // A card that holds a single chart or table has the buttons of the card only (unless it is one of singleParts).
      const parts = [...card.querySelectorAll(targets)].filter(item => item.parentElement.closest(targets) === card);
      const alone = parts.length < 2 && !(singleParts && part.matches(singleParts));
      return {card, part: part === card || alone ? null : part};
    }

    function kindOf(target) {
      return tables && target.matches(tables) ? 'table' : charts && target.matches(charts) ? 'chart' : 'panel';
    }

    // Its own title, after the title of the card it is part of (``Points Lost Map — EE``).
    function titleOf(target) {
      const card = targetsAt(target).card;
      if (title) return title(target, card === target ? null : card) || fallbackName;
      const names = [card && card !== target ? ownTitle(card) : '', ownTitle(target)].filter(Boolean);
      return [...new Set(names)].join(' — ') || headingText(target.querySelector('h2, h3, h4, h5, figcaption')) || fallbackName;
    }

    // The buttons of a card on the page stand on its top edge, at its right (in a dialog, inside its corner); those of a
    // chart or table in its top right corner, the screenshot on the left of the download, clear of the buttons of the
    // page. They stay at the top of their card, chart or table and show only while it is in sight (below the floating
    // bars of the page): they do not follow the scroll down it.
    function place(slot) {
      const {button, copy, target} = slot;
      if (!target?.isConnected || target.closest('[hidden]')) {
        hide(slot);
        return;
      }
      const host = hostOf(target);
      if (button.parentElement !== host) host.append(button, copy);
      button.hidden = false;
      copy.hidden = false;
      const bounds = target.getBoundingClientRect();
      const size = button.getBoundingClientRect();
      const inset = host === root ? topInset() : 0;
      const card = slot === cardSlot;
      const onEdge = card && cardOnEdge && host === root;
      let top = onEdge ? bounds.top - size.height / 2 : bounds.top + 8;
      let right = bounds.right - 8;
      const rowElement = !card && partRow ? target.querySelector(partRow) : null;
      const row = rowElement?.getBoundingClientRect();
      if (row?.width) {
        // On the row of buttons of the chart or table, at its left, where it ends while it slides in as it shows.
        const shift = new DOMMatrixReadOnly(getComputedStyle(rowElement).transform);
        top = row.top - shift.m42 + (row.height - size.height) / 2;
        right = row.left - shift.m41 - 6;
      } else if (!card && cardSlot.inSight && cardSlot.target?.contains(target)) {
        // The buttons of a chart or table at the right side of its card have the right edge of those of the card (below
        // them where they would meet); the others stay in the corner of their chart or table.
        const cardButton = cardSlot.button.getBoundingClientRect();
        if (cardButton.right - right < 48) {
          right = cardButton.right;
          if (top < cardButton.bottom + 6 && top + size.height > cardButton.top - 6) top = cardButton.bottom + 6;
        }
      }
      // Both buttons (the screenshot on the left of the download) keep clear of every button of the page they would cover.
      const span = size.width * 2 + 6;
      const boxes = obstacles ? [...target.querySelectorAll(obstacles)].map(obstacle => obstacle.getBoundingClientRect()) : [];
      for (let moved = true, step = 0; moved && step < boxes.length; step += 1) {
        moved = false;
        for (const box of boxes) {
          if (box.width && box.left < right && box.right > right - span && box.top < top + size.height && box.bottom > top) {
            right = box.left - 6;
            moved = true;
          }
        }
      }
      slot.inSight = top >= inset + 4 && top + size.height <= window.innerHeight;
      for (const [element, left] of [[button, right - size.width], [copy, right - size.width * 2 - 6]]) {
        element.style.visibility = slot.inSight ? '' : 'hidden';
        element.style.left = `${Math.round(left)}px`;
        element.style.top = `${Math.round(top)}px`;
        // An overlay that draws a filter places what it holds from its own corner.
        const shown = element.getBoundingClientRect();
        if (Math.abs(shown.left - left) > 1 || Math.abs(shown.top - top) > 1) {
          element.style.left = `${Math.round(2 * left - shown.left)}px`;
          element.style.top = `${Math.round(2 * top - shown.top)}px`;
        }
      }
    }

    const busy = slot => slot.button.classList.contains('is-busy') || slot.copy.classList.contains('is-busy');

    function show(slot, target) {
      if (busy(slot)) return;
      window.clearTimeout(slot.hideTimer);
      if (target !== slot.target) {
        slot.target = target;
        const kind = kindOf(target);
        for (const [button, label] of [[slot.button, `Download this ${kind} as an image (PNG)`],
          [slot.copy, `Copy this ${kind} to the clipboard as a screenshot, to paste it elsewhere`]]) {
          button.title = label;
          button.setAttribute('aria-label', label);
        }
      }
      place(slot);
    }

    function hide(slot) {
      if (busy(slot)) return;
      window.clearTimeout(slot.hideTimer);
      slot.target = null;
      slot.inSight = false;
      slot.button.hidden = true;
      slot.copy.hidden = true;
    }

    // The buttons of the card and, when the node is in one of its charts or tables, those of that one (the card first, so
    // the others keep clear of them).
    function showAt(node, {hideAfter = 0} = {}) {
      const found = targetsAt(node);
      for (const slot of slots) {
        if (!found[slot.level] || (slot === cardSlot && hiddenCards && found.card.matches(hiddenCards))) {
          hide(slot);
          continue;
        }
        show(slot, found[slot.level]);
        if (hideAfter) slot.hideTimer = window.setTimeout(() => hide(slot), hideAfter);
      }
    }

    // With a mouse the buttons show while the pointer is over a chart or table (or over a button).
    root.addEventListener('pointerover', event => {
      if (event.pointerType !== 'mouse' || isImageButton(event.target)) return;
      showAt(event.target);
    });
    root.addEventListener('pointerout', event => {
      if (event.pointerType !== 'mouse') return;
      const next = event.relatedTarget;
      if (!(next && (isImageButton(next) || targetsAt(next).card))) slots.forEach(hide);
    });
    // On touch screens a tap shows them for a few seconds, until a tap elsewhere.
    root.addEventListener('pointerup', event => {
      if (event.pointerType === 'mouse' || isImageButton(event.target) || !targetsAt(event.target).card) return;
      showAt(event.target, {hideAfter: 5000});
    });
    document.addEventListener('pointerdown', event => {
      if (event.pointerType === 'mouse') return;
      for (const slot of slots) {
        if (!slot.button.hidden && !slot.button.contains(event.target) && !slot.copy.contains(event.target)
          && !slot.target?.contains(event.target)) hide(slot);
      }
    });
    // While the page scrolls they stay at the top of their card, chart or table (hidden while it is out of sight).
    const follow = () => {
      if (slots.every(slot => !slot.target) || placeFrame) return;
      placeFrame = window.requestAnimationFrame(() => {
        placeFrame = 0;
        slots.filter(slot => slot.target).forEach(place);
      });
    };
    window.addEventListener('scroll', follow, {passive: true, capture: true});
    window.addEventListener('resize', follow);

    // Downloads the target of the slot as a PNG, or copies it to the clipboard (as a screenshot): the copy starts within the
    // click, as the clipboard requires; where the browser does not let the page copy images, it shows to copy from it.
    async function exportImage(slot, button, copy, event) {
      // A page that drew its content again meanwhile (one that refreshes itself): the same card, chart or table under the
      // button, as it is now.
      if (!slot.target?.isConnected && event) {
        const under = document.elementsFromPoint(event.clientX, event.clientY).find(node => !isImageButton(node));
        const found = targetsAt(under)[slot.level];
        if (found) slot.target = found;
      }
      const {target} = slot;
      const clipboard = copy && window.isSecureContext && Boolean(navigator.clipboard?.write) && typeof ClipboardItem === 'function';
      const draw = !copy ? window.downloadElementImage : clipboard ? window.copyElementImage : window.drawElementImage;
      if (!target?.isConnected || busy(slot) || typeof draw !== 'function') return;
      const name = titleOf(target);
      const file = fileName ? fileName(target, name) : imageFileName([name], fallbackName);
      const kind = kindOf(target);
      const recorded = {
        kind, title: name, ...details(target),
        ...(copy ? {destination: clipboard ? 'clipboard' : 'copy-dialog'} : {}),
      };
      button.classList.add('is-busy');
      button.setAttribute('aria-busy', 'true');
      try {
        const image = copy ? await draw(target, {exclude}) : await draw(target, file, {exclude});
        const format = image.format || (image.blob ? 'png' : 'svg');
        record({...recorded, file_name: image.fileName || file, format, width: image.width, height: image.height});
        if (copy && !clipboard) {
          showImageToCopy(image.blob || new Blob([image.svg], {type: 'image/svg+xml'}), file.replace(/\.png$/i, `.${format}`));
        } else if (copy) {
          // A moment in green, saying it is in the clipboard.
          button.classList.add('is-copied');
          button.title = 'Copied to the clipboard';
          window.setTimeout(() => {
            button.classList.remove('is-copied');
            button.title = button.getAttribute('aria-label') || '';
          }, 1600);
        }
      } catch (error) {
        const reason = error?.message || String(error);
        record({...recorded, file_name: file, error: reason});
        const message = `The ${kind} could not be ${copy ? 'copied to the clipboard' : 'downloaded'} as an image: ${reason}`;
        if (typeof showInfoDialog === 'function') {
          showInfoDialog(message, {tone: 'error', title: copy ? 'Image not copied' : 'Image not downloaded'});
        } else window.alert(message);
      } finally {
        button.classList.remove('is-busy');
        button.removeAttribute('aria-busy');
        // The pointer may have left while the image was drawn (a button of the page stays).
        if (!slot.own && !slot.button.matches(':hover') && !slot.copy.matches(':hover') && !target.matches(':hover')) hide(slot);
      }
    }
    for (const slot of slots) {
      // (The page under the buttons does not take their clicks: a card that opens on a click, a dialog that closes.)
      for (const [button, copy] of [[slot.button, false], [slot.copy, true]]) {
        button.addEventListener('click', event => {
          event.stopPropagation();
          exportImage(slot, button, copy, event);
        });
      }
    }
    // A button of the page itself downloads (or copies) a target as the floating ones do: named, recorded, in the clipboard.
    const exportWith = (target, button, copy = false) => exportImage({level: 'card', button, copy: button, target, own: true}, button, copy, null);
    return {hide: () => slots.forEach(hide), slots, exportImage: exportWith};
  }

  window.attachImageButtons = attachImageButtons;
  window.recordImageExport = recordImageExport;
  window.imageFileName = imageFileName;
  window.imageHeadingText = headingText;
})();
