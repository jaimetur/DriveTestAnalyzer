// Downloads an element of the page as an image, as it is shown: a copy of it, given the styles the page gives each of
// its parts, is drawn through an SVG <foreignObject> on a canvas and saved as a PNG. What scrolls sideways inside it
// (a table wider than its box) is shown whole.
(() => {
  const SVG_NS = 'http://www.w3.org/2000/svg';
  // The largest canvas every browser draws (Safari on iOS: about 16.7 million pixels).
  const MAX_PIXELS = 16e6;
  const MAX_SIDE = 16384;
  // The geometry an SVG shape takes from its attributes, copied with them.
  const SVG_GEOMETRY = ['d', 'x', 'y', 'cx', 'cy', 'r', 'rx', 'ry', 'width', 'height', 'transform'];
  // In the copy the HTML parts start from the initial value of each property (not from the browser's own styles, such as
  // the margins of a heading), so a part is given only the values that differ from it or from those of its parent.
  const RESET = '[data-element-image] :where(:not(style, [data-element-image-svg] *)) { all: unset; }';
  const knownStyles = new Map();
  let sandbox = null;

  function sandboxWindow() {
    if (!sandbox?.isConnected) {
      sandbox = document.createElement('iframe');
      sandbox.setAttribute('aria-hidden', 'true');
      sandbox.tabIndex = -1;
      sandbox.style.cssText = 'position:fixed;left:-10000px;top:0;width:10px;height:10px;border:0;visibility:hidden';
      document.body.append(sandbox);
    }
    return sandbox.contentWindow;
  }

  // What a part of the copy has without a value of its own: the initial values for HTML (see RESET), the browser's own
  // styles for the shapes of an SVG.
  function baseStyle(element) {
    const key = element instanceof SVGElement && element.localName !== 'svg' ? element.localName : '';
    if (!knownStyles.has(key)) {
      const view = sandboxWindow();
      const body = view.document.body;
      const holder = body.appendChild(key ? view.document.createElementNS(SVG_NS, 'svg') : view.document.createElement('div'));
      const probe = key ? holder.appendChild(view.document.createElementNS(SVG_NS, key)) : holder;
      if (!key) probe.style.setProperty('all', 'initial');
      const style = view.getComputedStyle(probe);
      const values = {};
      for (const name of style) values[name] = style.getPropertyValue(name);
      knownStyles.set(key, values);
      holder.remove();
    }
    return knownStyles.get(key);
  }

  function copied(name) {
    return !name.startsWith('--') && !name.startsWith('transition') && !name.startsWith('animation');
  }

  // References to the page (url("…/scoring#gradient")) point inside the copy instead.
  function localUrls(value) {
    if (!value.includes('url(')) return value;
    const page = window.location.href.split('#')[0];
    return value.replace(/url\((['"]?)([^'")]*)\1\)/g, (match, quote, address) => {
      const hash = address.indexOf('#');
      return hash > 0 && address.slice(0, hash) === page ? `url("${address.slice(hash)}")` : match;
    });
  }

  // The values of ``style`` that ``parentStyle`` and the base do not give already (every one for the element drawn).
  function declarations(style, base, parentStyle, skipped = []) {
    const values = [];
    for (const name of style) {
      if (!copied(name) || skipped.includes(name)) continue;
      const value = style.getPropertyValue(name);
      if (parentStyle && value === base[name] && value === parentStyle.getPropertyValue(name)) continue;
      values.push([name, localUrls(value)]);
    }
    return values;
  }

  function copyPseudoElements(source, copy, style, context) {
    for (const pseudo of ['::before', '::after']) {
      const pseudoStyle = getComputedStyle(source, pseudo);
      const content = pseudoStyle.getPropertyValue('content');
      if (!content || content === 'none' || content === 'normal') continue;
      const className = `element-image-part-${context.rules.length}`;
      copy.classList.add(className);
      const values = declarations(pseudoStyle, baseStyle(source), style).map(([name, value]) => `${name}: ${value}`);
      context.rules.push(`.${className}${pseudo} { ${values.join('; ')} }`);
    }
  }

  function inlineImage(source, copy, context) {
    const address = source.currentSrc || source.src;
    if (!address || address.startsWith('data:')) return;
    context.images.push(fetch(address).then(response => response.blob()).then(blob => new Promise(resolve => {
      const reader = new FileReader();
      reader.onload = () => { copy.setAttribute('src', reader.result); resolve(); };
      reader.onerror = () => resolve();
      reader.readAsDataURL(blob);
    })).catch(() => {}));
  }

  function copyNode(source, parentStyle, context) {
    if (source.nodeType === Node.TEXT_NODE) {
      // Characters XML does not allow would stop the image from loading.
      return document.createTextNode(source.data.replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, ''));
    }
    if (source.nodeType !== Node.ELEMENT_NODE || source.matches('script, style, template, noscript')
      || (context.exclude && source.matches(context.exclude))) return null;
    let copy;
    if (source instanceof HTMLCanvasElement) {
      copy = document.createElement('img');
      try { copy.src = source.toDataURL(); } catch (error) { /* A canvas the page may not read stays empty. */ }
    } else {
      copy = source.cloneNode(false);
    }
    copy.removeAttribute('style');
    const style = getComputedStyle(source);
    const svgPart = source instanceof SVGElement && source.localName !== 'svg';
    const skipped = svgPart ? SVG_GEOMETRY.filter(name => source.hasAttribute(name)) : [];
    for (const [name, value] of declarations(style, baseStyle(source), parentStyle, skipped)) copy.style.setProperty(name, value);
    if (source instanceof SVGSVGElement && !source.ownerSVGElement) copy.setAttribute('data-element-image-svg', '');
    if (!(source instanceof SVGElement)) copyPseudoElements(source, copy, style, context);
    // What the page has typed or chosen in its fields.
    if (source instanceof HTMLInputElement) {
      if (source.type === 'checkbox' || source.type === 'radio') copy.toggleAttribute('checked', source.checked);
      else copy.setAttribute('value', source.value);
    } else if (source instanceof HTMLOptionElement) {
      copy.toggleAttribute('selected', source.selected);
    } else if (source instanceof HTMLImageElement) {
      inlineImage(source, copy, context);
    }
    if (source instanceof HTMLTextAreaElement) {
      copy.textContent = source.value;
    } else if (style.display !== 'none' && !(source instanceof HTMLCanvasElement)) {
      for (const child of source.childNodes) {
        const childCopy = copyNode(child, style, context);
        if (childCopy) copy.append(childCopy);
      }
    }
    return copy;
  }

  // While the copy is made the element is widened until nothing scrolls sideways inside it (a part scrolled within a
  // narrower column grows with it). It happens between two drawings of the page, so the page is never shown so; the
  // function returned puts the element and the scroll positions back.
  function showScrolledContent(element) {
    const scrollers = [element, ...element.querySelectorAll('*')].filter(node => node instanceof HTMLElement
      && /^(auto|scroll)$/.test(getComputedStyle(node).overflowX));
    const overflow = () => Math.max(0, ...scrollers.filter(node => node.clientWidth > 0)
      .map(node => (node.scrollWidth - node.clientWidth) * element.clientWidth / node.clientWidth));
    let extra = overflow();
    if (extra < 1) return () => {};
    const style = element.getAttribute('style');
    const scrolled = scrollers.map(node => [node, node.scrollLeft, node.scrollTop]);
    const page = [window.scrollX, window.scrollY];
    const width = element.offsetWidth;
    let added = 0;
    for (let step = 0; step < 4 && extra >= 1; step += 1) {
      added += Math.ceil(extra);
      for (const [name, value] of [['box-sizing', 'border-box'], ['width', `${width + added}px`], ['max-width', 'none'],
        ['flex', 'none']]) element.style.setProperty(name, value, 'important');
      const left = overflow();
      // A part that does not grow with the element stays scrolled.
      if (left > extra - .5) break;
      extra = left;
    }
    return () => {
      if (style === null) element.removeAttribute('style');
      else element.setAttribute('style', style);
      for (const [node, left, top] of scrolled) {
        node.scrollLeft = left;
        node.scrollTop = top;
      }
      if (window.scrollX !== page[0] || window.scrollY !== page[1]) window.scrollTo(page[0], page[1]);
    };
  }

  function opaque(color) {
    const alpha = /rgba?\(([^)]+)\)/.exec(color)?.[1].split(/[\s,/]+/).filter(Boolean)[3];
    return color && color !== 'transparent' && (alpha === undefined || Number.parseFloat(alpha) >= 1);
  }

  // The colours behind the element (of the page around it), from the farthest that hides the rest.
  function backdrop(element) {
    const colors = [];
    for (let node = element.parentElement; node; node = node.parentElement) {
      const color = getComputedStyle(node).backgroundColor;
      if (!color || color === 'transparent' || /rgba\([^)]*,\s*0\)$/.test(color)) continue;
      colors.unshift(color);
      if (opaque(color)) return colors;
    }
    return ['#ffffff', ...colors];
  }

  function saveFile(blob, fileName) {
    const address = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = address;
    link.download = fileName;
    link.hidden = true;
    document.body.append(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(address), 60000);
  }

  function loadImage(address) {
    return new Promise((resolve, reject) => {
      const image = new Image();
      image.onload = () => resolve(image);
      image.onerror = () => reject(new Error('The browser could not draw it.'));
      image.src = address;
    });
  }

  // Saves ``element`` as ``fileName`` (a PNG, or an SVG where the browser does not let a page save what it drew), leaving
  // out its parts that match ``exclude``. Resolves to the file saved and its size in pixels of the page.
  async function downloadElementImage(element, fileName, {exclude = ''} = {}) {
    const context = {exclude, rules: [], images: []};
    let copy, width, height;
    const restore = showScrolledContent(element);
    try {
      width = Math.ceil(element.offsetWidth);
      height = Math.ceil(element.offsetHeight);
      copy = copyNode(element, null, context);
    } finally {
      restore();
      sandbox?.remove();
      sandbox = null;
    }
    if (!copy || !width || !height) throw new Error('It is not shown on the page.');
    // The element drawn at the top left corner of the image, without what places it on the page.
    for (const [name, value] of [['margin', '0'], ['inset', 'auto'], ['transform', 'none'], ['translate', 'none'],
      ['scale', 'none'], ['rotate', 'none'], ['float', 'none']]) copy.style.setProperty(name, value);
    if (!['static', 'relative'].includes(copy.style.getPropertyValue('position'))) copy.style.setProperty('position', 'relative');
    const holder = document.createElement('div');
    holder.setAttribute('data-element-image', '');
    holder.style.cssText = `display:block;width:${width}px;height:${height}px;overflow:hidden`;
    const sheet = document.createElement('style');
    sheet.textContent = [RESET, ...context.rules].join('\n');
    holder.append(sheet, copy);
    await Promise.all(context.images);
    const scale = Math.max(.1, Math.min(Math.max(2, window.devicePixelRatio || 1), Math.sqrt(MAX_PIXELS / (width * height)),
      MAX_SIDE / width, MAX_SIDE / height));
    const [imageWidth, imageHeight] = [Math.round(width * scale), Math.round(height * scale)];
    const colors = backdrop(element);
    // Drawn at the size of the image, so the text stays sharp in every browser.
    const svg = `<svg xmlns="${SVG_NS}" width="${imageWidth}" height="${imageHeight}" viewBox="0 0 ${width} ${height}">`
      + colors.map(color => `<rect width="100%" height="100%" fill="${color}"/>`).join('')
      + `<foreignObject x="0" y="0" width="${width}" height="${height}">${new XMLSerializer().serializeToString(holder)}</foreignObject></svg>`;
    const image = await loadImage(`data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`);
    const canvas = document.createElement('canvas');
    canvas.width = imageWidth;
    canvas.height = imageHeight;
    canvas.getContext('2d').drawImage(image, 0, 0, imageWidth, imageHeight);
    let blob = null;
    try {
      blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
    } catch (error) {
      // A browser that does not let a page save what it drew from an SVG saves the SVG itself.
      blob = null;
    }
    const png = Boolean(blob);
    const name = fileName.replace(/\.(png|svg)$/i, '') + (png ? '.png' : '.svg');
    saveFile(blob || new Blob([svg], {type: 'image/svg+xml'}), name);
    return {fileName: name, format: png ? 'png' : 'svg', width, height};
  }

  window.downloadElementImage = downloadElementImage;
})();
