/* Browser painter for report-faithful PPT Designer chart models. */
(() => {
  'use strict';

  const LOGICAL_WIDTH = 1600;
  const LOGICAL_HEIGHT = 900;
  const FONT_FAMILY = 'Arial, sans-serif';
  const AGGREGATION_TITLE_SIZE = 26;
  const LEGEND_TEXT_SIZE = 26;
  const LEGEND_MARKER_SIZE = 30;
  const models = new WeakMap();
  const views = new WeakMap();
  const cameraStates = new WeakMap();
  const nativeFillTexts = new WeakMap();
  const renderStates = new WeakMap();
  // Legend items a viewer hid by clicking them, per canvas.
  const hiddenLegendItems = new WeakMap();
  // The render state and transform that legend hit regions are recorded in.
  let legendHitTarget = null;
  const tableDragStates = new WeakMap();
  const observed = new WeakSet();
  const mapTiles = new Map();
  const mapWaits = new WeakMap();
  let resizeFrame = 0;

  const finite = value => Number.isFinite(Number(value));
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const font = (context, size, bold = false) => { context.font = `${bold ? '700 ' : ''}${size}px ${FONT_FAMILY}`; };
  const labelSize = (size, format = {}) => Math.max(9, Math.round(size * ({Small: .82, Medium: 1.08, Large: 1.28}[format.size] || 1)));
  const labelMaximumSize = (width, height, currentSize, format = {}) => {
    if (!format.has_size) return 26;
    // A Large label is the readable target for the available bar area. The
    // other choices remain proportions of that target, rather than fixed
    // point sizes, so the same template remains legible in dense slides.
    const largeTarget = Math.min(34, Math.max(18, Math.round(Math.min(width, height) * .30)));
    const relative = {Small: .72, Medium: .86, Large: 1}[format.size] || .86;
    return Math.max(currentSize, Math.round(largeTarget * relative));
  };
  const labelFont = (context, size, format = {}, fallbackBold = false, applyScale = true) => {
    const weight = format.bold ? '700 ' : (fallbackBold ? '700 ' : '');
    const actualSize = applyScale ? labelSize(size, format) : size;
    context.font = `${format.italic ? 'italic ' : ''}${weight}${actualSize}px ${format.font || FONT_FAMILY}`;
  };
  // Legend Format controls aggregation and legend furniture independently of
  // Label Format. Medium intentionally preserves the historical default;
  // Small and Large are relative choices around that baseline.
  const legendFormatSize = (size, format = {}, level = 0) => {
    const base = size * ({Small: .82, Medium: 1, Large: 1.20}[format.size] || 1);
    return Math.max(10, Math.round(base * ((5 / 6) ** Math.max(0, Number(level) || 0))));
  };
  // Aggregation headers and members must remain legible after a chart is
  // reduced into a multi-chart Design slide.
  const aggregationSize = (format = {}, level = 0) => {
    return legendFormatSize(AGGREGATION_TITLE_SIZE, format, level);
  };
  const aggregationFont = (context, format = {}, level = 0) => {
    const size = aggregationSize(format, level);
    if (format.configured) { labelFont(context, size, format, false, false); return; }
    context.font = `800 ${size}px ${FONT_FAMILY}`;
  };
  // A dash pattern is drawn for a thin line, so a thick line keeps it in proportion: its dashes and gaps grow with the
  // width, and a pattern of short dashes (dotted) becomes round dots one width apart. A short line, as the sample of a
  // legend, keeps at least two dashes.
  const lineDash = (context, dash, width = 1, length = Infinity) => {
    const pattern = Array.isArray(dash) ? dash.map(Number).filter(value => value > 0) : [];
    const thickness = Number(width) > 0 ? Number(width) : 1;
    if (pattern.length < 2) { context.setLineDash([]); return; }
    if (pattern[0] < pattern[1]) {
      context.lineCap = 'round';
      context.setLineDash([Math.max(0.01, 2 - thickness), Math.min(Math.max(5, thickness * 2), Math.max(length / 2, thickness + 2))]);
      return;
    }
    const period = pattern.reduce((sum, value) => sum + value, 0);
    const scale = Math.max(0.5, Math.min(Math.max(1, thickness / 2.5), length / 2 / period));
    context.setLineDash(pattern.map(value => value * scale));
  };
  const line = (context, x1, y1, x2, y2, colour = '#AEBBC4', width = 1, dash = []) => {
    context.save(); context.strokeStyle = colour; context.lineWidth = width;
    lineDash(context, dash, width, Math.hypot(x2 - x1, y2 - y1));
    context.beginPath(); context.moveTo(x1, y1); context.lineTo(x2, y2); context.stroke(); context.restore();
  };
  const textWidth = (context, value) => context.measureText(String(value)).width;
  const drawLabelText = (context, value, x, y, format = {}) => {
    const text = String(value);
    context.fillText(text, x, y);
    if (!format.underline) return;
    const width = textWidth(context, text);
    const left = context.textAlign === 'center' ? x - width / 2 : (context.textAlign === 'right' || context.textAlign === 'end' ? x - width : x);
    const size = Number.parseFloat(context.font) || 12;
    const underlineY = context.textBaseline === 'bottom' ? y + 2 : (context.textBaseline === 'middle' ? y + size / 2 + 2 : y + size + 2);
    context.save(); context.strokeStyle = context.fillStyle; context.lineWidth = Math.max(1, size / 14);
    context.beginPath(); context.moveTo(left, underlineY); context.lineTo(left + width, underlineY); context.stroke(); context.restore();
  };
  const displayKey = key => (key || []).filter(value => value !== '(all)').join(' · ') || '(all)';
  const percent = (value, digits = 1) => `${(Number(value) * 100).toFixed(digits)}%`;
  const tooltipPercent = value => `${(Number(value) * 100).toFixed(2)}%`;
  const numericLabel = value => {
    const number = Number(value);
    if (!Number.isFinite(number)) return String(value ?? '');
    if (Math.abs(number) >= 1000) return number.toLocaleString('en-US', {useGrouping: false, maximumFractionDigits: 0});
    return number.toFixed(2);
  };
  const transformPoint = (transform, x, y) => ({x: transform.x + x * transform.scale, y: transform.y + y * transform.scale});
  const pushRectangleHit = (state, transform, rectangle, details) => {
    const start = transformPoint(transform, rectangle.x, rectangle.y);
    state.hits.push({kind: 'rectangle', x: start.x, y: start.y, width: rectangle.width * transform.scale, height: rectangle.height * transform.scale, ...details});
  };
  const pushPointHit = (state, transform, x, y, details) => {
    const point = transformPoint(transform, x, y);
    state.hits.push({kind: 'point', x: point.x, y: point.y, ...details});
  };
  // Aggregation labels of an axis (any level): right-clicking one offers the
  // same Keep only / Hide / Show actions as a legend entry.
  const pushAxisHit = (axis, level, value, x, y, width, height) => {
    const text = String(value ?? '');
    if (!legendHitTarget || !text || text === '(all)') return;
    const start = transformPoint(legendHitTarget.transform, x, y), scale = legendHitTarget.transform.scale;
    (legendHitTarget.state.axisHits ||= []).push({axis, level, value: text, x: start.x, y: start.y, width: width * scale, height: height * scale});
  };
  const pushLineHit = (state, transform, points, details) => {
    state.hits.push({kind: 'line', points: points.map(point => ({...point, ...transformPoint(transform, point.x, point.y)})), ...details});
  };

  function osmWorldCoordinates(latitude, longitude, zoom) {
    const boundedLatitude = clamp(Number(latitude), -85.05112878, 85.05112878);
    const scale = 256 * (2 ** Number(zoom));
    const x = (Number(longitude) + 180) / 360 * scale;
    const radians = boundedLatitude * Math.PI / 180;
    const y = (1 - Math.asinh(Math.tan(radians)) / Math.PI) / 2 * scale;
    return [x, y];
  }

  function mapTileRecord(url) {
    if (mapTiles.has(url)) return mapTiles.get(url);
    const image = new Image();
    const record = {image, status: 'loading'};
    record.promise = new Promise(resolve => {
      image.addEventListener('load', () => { record.status = 'ready'; resolve(record); });
      image.addEventListener('error', () => {
        // A tile server that does not allow it is asked again plainly: the map shows, but cannot be saved as an image.
        if (image.crossOrigin) {
          image.removeAttribute('crossorigin');
          image.src = url;
          return;
        }
        record.status = 'error';
        resolve(record);
      });
    });
    image.decoding = 'async';
    // Asked for with CORS, so a map drawn with its tiles can still be saved as an image (see element_image.js).
    image.crossOrigin = 'anonymous';
    image.src = url;
    mapTiles.set(url, record);
    return record;
  }

  function mapTileRecords(canvas, payload) {
    const basemap = payload.basemap, range = basemap?.tile_range;
    if (!basemap || !Array.isArray(range) || range.length !== 4) return [];
    const [left, top, right, bottom] = range.map(Number), records = [];
    for (let y = top; y <= bottom; y += 1) {
      for (let x = left; x <= right; x += 1) {
        const url = String(basemap.url_template || '')
          .replace('{z}', String(basemap.zoom)).replace('{x}', String(x)).replace('{y}', String(y));
        records.push({x, y, ...mapTileRecord(url)});
      }
    }
    const pending = records.filter(record => record.status === 'loading');
    const signature = `${basemap.zoom}:${range.join(':')}`;
    const waiting = mapWaits.get(canvas);
    if (pending.length && (waiting?.signature !== signature || waiting?.payload !== payload)) {
      mapWaits.set(canvas, {signature, payload});
      Promise.all(pending.map(record => record.promise)).then(() => {
        if (mapWaits.get(canvas)?.payload === payload) mapWaits.delete(canvas);
        if (models.get(canvas) === payload) draw(canvas, payload);
      });
    }
    return records;
  }

  function cameraFor(canvas) {
    let camera = cameraStates.get(canvas);
    if (!camera) {
      camera = {zoom: 1, panX: 0, panY: 0};
      cameraStates.set(canvas, camera);
    }
    return camera;
  }

  function constrainCamera(camera) {
    camera.zoom = clamp(Number(camera.zoom) || 1, 1, 4);
    if (camera.zoom === 1) {
      camera.panX = 0;
      camera.panY = 0;
      return camera;
    }
    const maximumX = LOGICAL_WIDTH * (camera.zoom - 1) / 2;
    const maximumY = LOGICAL_HEIGHT * (camera.zoom - 1) / 2;
    camera.panX = clamp(Number(camera.panX) || 0, -maximumX, maximumX);
    camera.panY = clamp(Number(camera.panY) || 0, -maximumY, maximumY);
    return camera;
  }

  function prepareCanvas(canvas) {
    const bounds = canvas.getBoundingClientRect();
    const cssWidth = Math.max(1, bounds.width || canvas.parentElement?.clientWidth || 600);
    const cssHeight = Math.max(1, bounds.height || canvas.parentElement?.clientHeight || 360);
    const pixelRatio = Math.min(globalThis.devicePixelRatio || 1, 2);
    const backingWidth = Math.round(cssWidth * pixelRatio), backingHeight = Math.round(cssHeight * pixelRatio);
    if (canvas.width !== backingWidth || canvas.height !== backingHeight) { canvas.width = backingWidth; canvas.height = backingHeight; }
    const context = canvas.getContext('2d');
    context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0); context.clearRect(0, 0, cssWidth, cssHeight);
    context.fillStyle = '#FFFFFF'; context.fillRect(0, 0, cssWidth, cssHeight);
    const scaleX = cssWidth / LOGICAL_WIDTH, scaleY = cssHeight / LOGICAL_HEIGHT;
    const camera = cameraFor(canvas);
    constrainCamera(camera);
    const originX = (1 - camera.zoom) * LOGICAL_WIDTH / 2 + camera.panX;
    const originY = (1 - camera.zoom) * LOGICAL_HEIGHT / 2 + camera.panY;
    context.setTransform(
      pixelRatio * scaleX * camera.zoom, 0, 0, pixelRatio * scaleY * camera.zoom,
      pixelRatio * scaleX * originX, pixelRatio * scaleY * originY,
    );
    let nativeFillText = nativeFillTexts.get(context);
    if (!nativeFillText) {
      nativeFillText = context.fillText.bind(context);
      nativeFillTexts.set(context, nativeFillText);
    }
    context.fillText = (value, x, y, maximumWidth) => {
      const transform = context.getTransform();
      const textScale = Math.min(Math.hypot(transform.a, transform.b), Math.hypot(transform.c, transform.d));
      const pointX = transform.a * x + transform.c * y + transform.e;
      const pointY = transform.b * x + transform.d * y + transform.f;
      const angle = Math.atan2(transform.b, transform.a);
      context.save();
      context.setTransform(textScale * Math.cos(angle), textScale * Math.sin(angle), -textScale * Math.sin(angle), textScale * Math.cos(angle), pointX, pointY);
      if (maximumWidth === undefined) nativeFillText(value, 0, 0);
      else nativeFillText(value, 0, 0, maximumWidth);
      context.restore();
    };
    context.lineJoin = 'round'; context.lineCap = 'round'; context.textBaseline = 'top';
    views.set(canvas, {scaleX, scaleY, zoom: camera.zoom, originX, originY});
    return context;
  }

  function drawTitle(context, title) {
    const view = views.get(context.canvas) || {scaleX: 1, scaleY: 1, zoom: 1, originX: 0, originY: 0};
    const zoom = Number(view.zoom) || 1;
    const x = 32 / (Math.max(view.scaleX, .0001) * zoom) - Number(view.originX || 0);
    const y = 20 / (Math.max(view.scaleY, .0001) * zoom) - Number(view.originY || 0);
    context.fillStyle = '#1D3345'; context.textAlign = 'left'; context.textBaseline = 'top'; font(context, 40, true);
    context.fillText(String(title || ''), x, y);
  }

  function fittedText(context, value, width) {
    const full = String(value ?? '');
    if (textWidth(context, full) <= width) return full;
    let result = '';
    for (const character of full) { if (textWidth(context, result + character + '…') > width) break; result += character; }
    return `${result.trimEnd()}…`;
  }

  function hierarchyRowLabelSize() {
    return AGGREGATION_TITLE_SIZE;
  }

  function drawFullHierarchyLabel(context, value, x, y, width, size, colour = '#405765', format = {}, level = 0) {
    const label = String(value ?? '');
    context.fillStyle = format.configured && format.color ? format.color : colour; context.textAlign = 'left'; context.textBaseline = 'top'; aggregationFont(context, format, level);
    const measured = textWidth(context, label);
    if (measured <= width) { context.fillText(label, x, y); return; }
    // Preserve the complete aggregation value in its own pane when even the
    // smallest readable font does not fit. Horizontal condensation is only a
    // last resort and avoids silently replacing business labels with an ellipsis.
    context.save(); context.translate(x, y); context.scale(width / measured, 1); context.fillText(label, 0, 0); context.restore();
  }

  function verticalLabel(context, value, centreX, centreY, colour, size, bold = true, format = {}) {
    context.save(); context.translate(centreX, centreY); context.rotate(-Math.PI / 2);
    context.fillStyle = colour; context.textAlign = 'center'; context.textBaseline = 'middle'; labelFont(context, size, format, bold);
    context.fillText(String(value), 0, 0); context.restore();
  }

  function expandedBarLabelSize(context, value, width, height, size, maximum = 26, format = {}) {
    labelFont(context, size, format, false, false);
    const labelWidth = textWidth(context, String(value));
    const scale = Math.min((width - 8) / Math.max(labelWidth, 1), (height - 8) / size);
    return scale > 1 ? Math.min(maximum, Math.floor(size * scale)) : size;
  }

  function drawInsideBarLabel(context, value, x, y, width, height, colour, size, format = {}) {
    size = labelSize(size, format); const label = String(value); labelFont(context, size, format, false, false); const labelWidth = textWidth(context, label);
    if (labelWidth + 8 <= width && size + 8 <= height) {
      const fittedSize = expandedBarLabelSize(context, label, width, height, size, labelMaximumSize(width, height, size, format), format); labelFont(context, fittedSize, format, false, false);
      context.fillStyle = colour; context.textAlign = 'center'; context.textBaseline = 'middle'; drawLabelText(context, label, x + width / 2, y + height / 2, format); context.textBaseline = 'top'; return true;
    }
    if (size + 8 <= width && labelWidth + 8 <= height) {
      verticalLabel(context, label, x + width / 2, y + height / 2, colour, size, false, format); return true;
    }
    return false;
  }

  function drawInsideHorizontalBarLabel(context, value, x, y, width, height, colour, size, format = {}) {
    size = labelSize(size, format); const label = String(value); labelFont(context, size, format, false, false); const labelWidth = textWidth(context, label);
    if (labelWidth + 8 > width || size + 8 > height) return false;
    const fittedSize = expandedBarLabelSize(context, label, width, height, size, labelMaximumSize(width, height, size, format), format); labelFont(context, fittedSize, format, false, false);
    context.fillStyle = colour; context.textAlign = 'center'; context.textBaseline = 'middle';
    drawLabelText(context, label, x + width / 2, y + height / 2, format); context.textBaseline = 'top'; return true;
  }

  function stackedChartLabelColour(series, cells) {
    const totals = Array(series.length).fill(0);
    const collect = values => Array.isArray(values) && values.forEach((value, index) => { totals[index] += Number(value) || 0; });
    (cells || []).forEach(cell => Array.isArray(cell?.[0]) ? cell.forEach(collect) : collect(cell));
    const dominant = series[totals.indexOf(Math.max(...totals))]?.colour || '#405765';
    const hex = String(dominant).replace('#', '');
    if (!/^[0-9a-f]{6}$/i.test(hex)) return '#FFFFFF';
    const [red, green, blue] = [0, 2, 4].map(offset => parseInt(hex.slice(offset, offset + 2), 16));
    return (red * 299 + green * 587 + blue * 114) / 1000 > 156 ? '#111111' : '#FFFFFF';
  }

  function drawOutsideBarLabel(context, value, x, y, colour, size = 12, format = {}) {
    const label = String(value);
    context.save();
    labelFont(context, size, format);
    context.textAlign = 'left';
    context.textBaseline = 'top';
    const width = textWidth(context, label);
    context.fillStyle = 'rgba(255, 255, 255, 0.94)';
    context.fillRect(x - 3, y - 2, width + 6, size + 5);
    context.fillStyle = colour;
    drawLabelText(context, label, x, y, format);
    context.restore();
  }

  function drawAdjacentStackLabel(context, value, x, y, width, height, barTop, barBottom, sideSpace, colour, occupied, size = 10, format = {}) {
    context.save(); labelFont(context, size, format);
    const label = String(value), baseWidth = textWidth(context, label);
    size = Math.min(16, Math.max(size, Math.floor(size * (sideSpace - 6) / Math.max(baseWidth, 1))));
    labelFont(context, size, format); const labelWidth = textWidth(context, label);
    const centreY = Math.max(barTop + size / 2, Math.min(barBottom - size / 2, y + height / 2));
    if (labelWidth + 6 > sideSpace || occupied.some(existing => Math.abs(existing - centreY) < size + 3)) { context.restore(); return false; }
    context.fillStyle = colour; context.textAlign = 'left'; context.textBaseline = 'middle';
    drawLabelText(context, label, x + width + 4, centreY, format);
    context.restore(); return true;
  }

  function drawConfiguredBarLabel(context, value, x, y, width, height, colour, size, position, orientation, automatic, format = {}) {
    const placement = String(position || '').toLowerCase();
    if (!placement) { automatic?.(); return; }
    if (placement === 'none') return;
    const horizontal = orientation === 'horizontal';
    const configuredColour = format.color || colour;
    context.save(); labelFont(context, size, format);
    if (placement === 'top') {
      if (horizontal) drawOutsideBarLabel(context, value, x + width + 5, y + Math.max(0, (height - size) / 2), configuredColour, size, format);
      else { context.fillStyle = configuredColour; context.textAlign = 'center'; context.textBaseline = 'bottom'; drawLabelText(context, value, x + width / 2, y - 4, format); }
    } else {
      context.fillStyle = format.color || '#FFFFFF'; context.textBaseline = 'middle';
      if (horizontal) {
        context.textAlign = placement === 'up' ? 'right' : (placement === 'down' ? 'left' : 'center');
        const labelX = placement === 'up' ? x + width - 4 : (placement === 'down' ? x + 4 : x + width / 2);
        drawLabelText(context, value, labelX, y + height / 2, format);
      } else {
        const labelWidth = textWidth(context, value);
        if (labelWidth + 8 > width && size + 8 <= width && labelWidth + 8 <= height) {
          const centreY = placement === 'up'
            ? y + labelWidth / 2 + 4
            : (placement === 'down' ? y + height - labelWidth / 2 - 4 : y + height / 2);
          verticalLabel(context, value, x + width / 2, centreY, format.color || '#FFFFFF', size, false, format);
          context.restore();
          return;
        }
        context.textAlign = 'center';
        const labelY = placement === 'up' ? y + size / 2 + 4 : (placement === 'down' ? y + height - size / 2 - 4 : y + height / 2);
        drawLabelText(context, value, x + width / 2, labelY, format);
      }
    }
    context.restore();
  }

  function drawConfiguredPointLabel(context, value, x, y, colour, position, size = 15, format = {}) {
    const placement = String(position || '').toLowerCase();
    if (!placement || placement === 'none') return;
    const offsets = {
      top: [0, -9, 'center', 'bottom'],
      up: [8, -7, 'left', 'bottom'],
      middle: [9, 0, 'left', 'middle'],
      down: [8, 7, 'left', 'top'],
    };
    const [offsetX, offsetY, align, baseline] = offsets[placement] || offsets.middle;
    context.save(); labelFont(context, size, format); context.textAlign = align; context.textBaseline = baseline;
    const label = String(value ?? ''), labelWidth = textWidth(context, label);
    const labelX = x + offsetX, labelY = y + offsetY;
    context.fillStyle = 'rgba(255, 255, 255, 0.9)';
    const boxX = align === 'center' ? labelX - labelWidth / 2 - 2 : labelX - 2;
    const boxY = baseline === 'bottom' ? labelY - size - 2 : (baseline === 'middle' ? labelY - size / 2 - 2 : labelY - 2);
    context.fillRect(boxX, boxY, labelWidth + 4, size + 4);
    context.fillStyle = format.color || colour; drawLabelText(context, label, labelX, labelY, format); context.restore();
  }

  function dashedVertical(context, x, top, bottom) {
    context.save(); context.setLineDash([8, 6]); line(context, x, top, x, bottom, '#AEBBC4', 1); context.restore();
  }

  function dashedHorizontal(context, y, left, right) {
    context.save(); context.setLineDash([8, 6]); line(context, left, y, right, y, '#AEBBC4', 1); context.restore();
  }

  function hierarchySpans(keys, level) {
    const spans = []; let start = 0;
    while (start < keys.length) {
      let end = start + 1; const prefix = keys[start].slice(0, level + 1).join('\u001f');
      while (end < keys.length && keys[end].slice(0, level + 1).join('\u001f') === prefix) end += 1;
      spans.push([start, end, String(keys[start][level] ?? '')]); start = end;
    }
    return spans;
  }

  function drawTopColumnSeparators(context, keys, axisColumns, left, width, top, bottom, axis = null) {
    if (keys.length < 2) return;
    // The x-axis can begin with row aggregation fields. They are still visible
    // header levels in bar charts, so the first hierarchy field is the outer
    // boundary and each child boundary begins below its parent header.
    const outerLevel = 0, headerTop = axis ? top - axis.headerHeight : top - 30 * (keys[0]?.length || 1) - 8;
    const levelTop = level => headerTop + (axis
      ? axis.headers.slice(0, level).reduce((sum, header) => sum + header.height, 0)
      : level * 30);
    for (let index = 1; index < keys.length; index += 1) {
      let changed = keys[index - 1].findIndex((value, level) => String(value) !== String(keys[index][level]));
      if (changed < 0) continue;
      const x = left + index * width / keys.length;
      if (changed === outerLevel) line(context, x, headerTop, x, bottom, '#AEBBC4', 2);
      else dashedVertical(context, x, levelTop(changed), bottom);
    }
  }

  // Axis labels: the canvas scales geometry separately along x and y but
  // paints text with the smaller scale. Measured text widths are converted
  // into logical units along each axis before deciding how a label fits.
  function textRatios(context) {
    const transform = context.getTransform();
    const horizontal = Math.hypot(transform.a, transform.b) || 1, vertical = Math.hypot(transform.c, transform.d) || 1;
    const text = Math.min(horizontal, vertical);
    return {x: text / horizontal, y: text / vertical};
  }

  const AXIS_LABEL_MINIMUM_SIZE = 12;
  const AXIS_LINE_HEIGHT = 1.15;

  function axisFont(context, format = {}, size = AGGREGATION_TITLE_SIZE) {
    if (format.configured) labelFont(context, size, format, false, false);
    else context.font = `800 ${size}px ${FONT_FAMILY}`;
  }

  // A label on one line, or on two lines broken near its middle at a space,
  // " - " or "-" (for example "Mixed / Vendor" or "2026- / Q1").
  function axisLabelLines(value) {
    const text = String(value ?? '');
    const options = [[text]];
    const breaks = [...text.matchAll(/ - | · | |-/g)];
    if (breaks.length) {
      const middle = text.length / 2;
      const best = breaks.sort((left, right) => Math.abs(left.index - middle) - Math.abs(right.index - middle))[0];
      const separator = best[0];
      const first = (separator === '-' || separator === ' - ' ? text.slice(0, best.index + separator.trimEnd().length + (separator === ' - ' ? 1 : 0)) : text.slice(0, best.index)).trim();
      const second = text.slice(best.index + separator.length).trim();
      if (first && second) options.push([first, second]);
    }
    return options;
  }

  // One plan for every label of an axis level, so they share a size: one
  // line, then two lines, then a smaller font, then vertical text, and as a
  // last resort the smallest font condensed to its column. Never truncated.
  function axisLevelPlan(context, entries, maximumHeight, format = {}, level = 0) {
    const ratios = textRatios(context), base = aggregationSize(format, level);
    const minimum = Math.min(base, Math.max(AXIS_LABEL_MINIMUM_SIZE, Math.round(base * .5)));
    const labels = entries.map(entry => ({value: String(entry.value ?? ''), width: Math.max(1, Number(entry.width) || 1)})).filter(entry => entry.value);
    const lineHeight = size => size * AXIS_LINE_HEIGHT * ratios.y;
    const widthOf = (text, size) => { axisFont(context, format, size); return textWidth(context, text) * ratios.x; };
    const plan = (mode, size, lines) => ({
      mode, size, lines,
      height: mode === 'vertical'
        ? Math.max(0, ...labels.map(label => { axisFont(context, format, size); return textWidth(context, label.value) * ratios.y; })) + 6
        : Math.max(1, ...[...lines.values()].map(item => item.length)) * lineHeight(size) + 4,
    });
    if (!labels.length) return plan('horizontal', base, new Map());
    const horizontalAt = (size, maximumLines) => {
      const lines = new Map();
      for (const label of labels) {
        const option = axisLabelLines(label.value).find(candidate => candidate.length <= maximumLines
          && candidate.every(line => widthOf(line, size) <= label.width - 6)
          && candidate.length * lineHeight(size) <= maximumHeight);
        if (!option) return null;
        lines.set(label.value, option);
      }
      return lines;
    };
    const readable = Math.max(minimum, Math.round(base * .7));
    for (let size = base; size >= readable; size -= 1) {
      for (const maximumLines of [1, 2]) {
        const lines = horizontalAt(size, maximumLines);
        if (lines) return plan('horizontal', size, lines);
      }
    }
    for (let size = base; size >= minimum; size -= 1) {
      const fits = labels.every(label => { axisFont(context, format, size); return textWidth(context, label.value) * ratios.y <= maximumHeight - 6 && lineHeight(size) * ratios.x / ratios.y <= label.width; });
      if (fits) return plan('vertical', size, new Map(labels.map(label => [label.value, [label.value]])));
    }
    for (let size = readable - 1; size >= minimum; size -= 1) {
      const lines = horizontalAt(size, 2);
      if (lines) return plan('horizontal', size, lines);
    }
    return plan('condensed', minimum, new Map(labels.map(label => [label.value, [label.value]])));
  }

  // Draw one planned label centred on centreX, starting at topY.
  function drawAxisLabel(context, plan, value, centreX, topY, width, colour, format = {}) {
    const text = String(value ?? '');
    if (!text) return;
    const ratios = textRatios(context);
    context.save();
    axisFont(context, format, plan.size);
    context.fillStyle = format.configured && format.color ? format.color : colour;
    if (plan.mode === 'vertical') {
      const length = textWidth(context, text) * ratios.y;
      context.translate(centreX, topY + length); context.rotate(-Math.PI / 2);
      context.textAlign = 'left'; context.textBaseline = 'middle'; context.fillText(text, 0, 0);
    } else {
      context.textAlign = 'center'; context.textBaseline = 'top';
      (plan.lines.get(text) || [text]).forEach((line, index) => {
        const y = topY + index * plan.size * AXIS_LINE_HEIGHT * ratios.y, measured = textWidth(context, line) * ratios.x, available = Math.max(width - 6, 1);
        if (measured <= available) { context.fillText(line, centreX, y); return; }
        context.save(); context.translate(centreX, y); context.scale(available / measured, 1); context.fillText(line, 0, 0); context.restore();
      });
    }
    context.restore();
  }

  // Label plans and reserved heights of a column hierarchy: the upper levels
  // above the plot and the leaf level below it.
  function hierarchicalAxisPlans(context, keys, width, format = {}) {
    const levels = keys[0]?.length || 0, itemWidth = width / Math.max(keys.length, 1);
    const headers = [];
    for (let level = 0; level < Math.max(levels - 1, 0); level += 1) {
      const plan = axisLevelPlan(context, hierarchySpans(keys, level).map(([start, end, value]) => ({value, width: (end - start) * itemWidth})), 64, format, level);
      headers.push({plan, height: Math.max(30, plan.height + 8)});
    }
    const leaf = axisLevelPlan(context, keys.map(key => ({value: key.at(-1), width: itemWidth})), 150, format);
    return {headers, leaf, headerHeight: headers.reduce((sum, header) => sum + header.height, 0) + 38, leafHeight: Math.max(46, leaf.height + 16)};
  }

  function drawHierarchicalAxisLabels(context, keys, left, width, top, bottom, format = {}, axis = hierarchicalAxisPlans(context, keys, width, format)) {
    if (!keys.length) return;
    const levels = keys[0].length, itemWidth = width / keys.length;
    let y = top - axis.headerHeight + 8;
    axis.headers.forEach(({plan, height}, level) => {
      for (const [start, end, value] of hierarchySpans(keys, level)) {
        const available = (end - start) * itemWidth;
        drawAxisLabel(context, plan, value, left + (start + end) / 2 * itemWidth, y + Math.max(0, (height - 6 - plan.height) / 2), available, '#566A78', format);
        line(context, left + start * itemWidth, y + height - 6, left + end * itemWidth, y + height - 6, '#CDD7DE', 1);
        pushAxisHit('column', level, value, left + start * itemWidth, y - 4, available, height);
      }
      y += height;
    });
    keys.forEach((key, index) => {
      drawAxisLabel(context, axis.leaf, key.at(-1), left + (index + .5) * itemWidth, bottom + 11, itemWidth, '#62727E', format);
      pushAxisHit('column', levels - 1, key.at(-1), left + index * itemWidth, bottom + 4, itemWidth, axis.leaf.height + 10);
    });
  }

  function legendLayout(legend, fontSize = LEGEND_TEXT_SIZE) {
    const items = legend?.items || [];
    let position = items.length ? String(legend?.position || 'none').toLowerCase() : 'none';
    if (!['none', 'top', 'bottom', 'left', 'right'].includes(position)) position = 'top';
    const format = legend?.format || {};
    const size = format.configured ? legendFormatSize(LEGEND_TEXT_SIZE, format) : Math.max(Number(fontSize || LEGEND_TEXT_SIZE), LEGEND_TEXT_SIZE);
    const lineMarkers = Boolean(legend?.line_markers);
    const markerWidth = lineMarkers ? 43 : 32;
    const longestLabel = items.reduce((length, item) => Math.max(length, String(item?.label || '').slice(0, 28).length), 0);
    const estimatedItemWidth = Math.max(120, markerWidth + longestLabel * size * .62 + 24);
    const sideLegendWidth = Math.min(380, Math.max(170, estimatedItemWidth + 20));
    const maximumColumns = lineMarkers ? 6 : 5;
    const columns = ['top', 'bottom'].includes(position)
      ? Math.max(1, Math.min(items.length || 1, maximumColumns, Math.floor(1400 / estimatedItemWidth)))
      : maximumColumns;
    const rows = Math.max(1, Math.ceil(items.length / columns));
    const rowHeight = size + 12;
    return {
      position,
      hasLegend: position !== 'none',
      left: position === 'left' ? sideLegendWidth + 20 : 70,
      right: position === 'right' ? LOGICAL_WIDTH - sideLegendWidth - 20 : 1540,
      top: position === 'top' ? 80 + rows * rowHeight + 18 : 82,
      bottom: position === 'bottom' ? 900 - rows * rowHeight - 22 : 860,
      sideX: position === 'right' ? LOGICAL_WIDTH - sideLegendWidth + 4 : 26,
      size,
      columns,
      rows,
      rowHeight,
    };
  }

  // An upright triangle, the mark of an inventory site: no measurement point is drawn with it.
  function drawSiteMark(context, x, y, size, colour) {
    context.beginPath(); context.moveTo(x, y - size); context.lineTo(x + size * .9, y + size * .62); context.lineTo(x - size * .9, y + size * .62); context.closePath();
    context.fillStyle = colour; context.fill();
    context.strokeStyle = '#FFFFFF'; context.lineWidth = 2.4; context.stroke();
    context.strokeStyle = '#1E1B4B'; context.lineWidth = 1.1; context.stroke();
  }

  function drawLegend(context, legend, options = {}) {
    const items = legend?.items || [], layout = legendLayout(legend, options.fontSize);
    const {position, size, columns, rowHeight} = layout;
    if (!layout.hasLegend) return;
    const lineMarkers = Boolean(legend.line_markers), markerSize = LEGEND_MARKER_SIZE, format = legend?.format || {};
    const legendLineWidth = width => Math.max(Number(width) > 1 ? Number(width) + 2 : Number(width), 3);
    const drawItem = (item, x, y, maximumLength) => {
      const textOnly = !item.colour, textX = textOnly ? x : x + (lineMarkers ? 43 : 32), text = String(item.label).slice(0, maximumLength);
      // A hidden series keeps a faded, struck-through entry to show it again.
      const alpha = context.globalAlpha;
      if (item.hidden) context.globalAlpha = alpha * .35;
      if (lineMarkers && !textOnly) line(context, x, y + 11, x + 34, y + 11, item.colour, legendLineWidth(item.width), item.dash);
      else if (!textOnly && item.marker === 'triangle') drawSiteMark(context, x + markerSize / 2, y + markerSize / 2 + 1, markerSize * .62, item.colour);
      else if (!textOnly && (item.marker === 'ring' || item.marker === 'ring-dashed')) {
        // The ring of sites with flagged cells: solid, or dashed for sites not on air yet.
        context.save(); context.beginPath(); context.arc(x + markerSize / 2, y + markerSize / 2, markerSize / 2 - 1, 0, Math.PI * 2);
        context.setLineDash(item.marker === 'ring-dashed' ? [4, 3] : []); context.strokeStyle = item.colour; context.lineWidth = 2.4; context.stroke(); context.restore();
      }
      else if (!textOnly) { context.fillStyle = item.colour; context.fillRect(x, y, markerSize, markerSize); }
      context.fillStyle = format.configured && format.color ? format.color : '#263B4A'; context.textAlign = 'left'; context.textBaseline = 'top'; if (format.configured) labelFont(context, size, format, false, false); else font(context, size, true);
      context.fillText(text, textX, y - 1);
      const width = textWidth(context, text);
      if (item.hidden) line(context, textX, y + size / 2, textX + width, y + size / 2, context.fillStyle, Math.max(1.5, size / 12));
      context.globalAlpha = alpha;
      if (!textOnly && legendHitTarget) {
        const start = transformPoint(legendHitTarget.transform, x - 4, y - 6), scale = legendHitTarget.transform.scale;
        (legendHitTarget.state.legendHits ||= []).push({
          label: String(item.label), x: start.x, y: start.y, width: (textX - x + width + 8) * scale, height: (size + 12) * scale,
        });
      }
    };
    if (position === 'top' || position === 'bottom') {
      const startY = position === 'top' ? 80 : 900 - layout.rows * rowHeight - 8;
      items.forEach((item, index) => {
        drawItem(item, 100 + (index % columns) * (1400 / columns), startY + Math.floor(index / columns) * rowHeight, 28);
      });
      return;
    }
    const x = options.sideX ?? layout.sideX;
    items.forEach((item, index) => drawItem(item, x, 112 + index * (size + 14), 24));
  }

  // Hidden legend state of a canvas: hidden labels or aggregation values, and
  // labels explicitly shown although one of their levels is hidden.
  const emptyLegendState = () => ({hidden: new Set(), shown: new Set()});
  const legendStateMatchers = state => {
    const hidden = state?.hidden || new Set(), shown = state?.shown || new Set();
    const valueHidden = value => hidden.has(value) && !shown.has(value);
    // "VF_SA" hides every series or category with VF_SA at any level, such
    // as "VF_SA · 2026-Q1" or "London · VF_SA · 2026-Q2".
    const labelHidden = label => {
      const text = String(label ?? '');
      return !shown.has(text) && (valueHidden(text) || text.split(' · ').some(valueHidden));
    };
    const keyHidden = key => {
      const parts = (Array.isArray(key) ? key : [key]).map(value => String(value ?? '')).filter(Boolean);
      const joined = parts.join(' · ');
      return Boolean(parts.length) && !shown.has(joined) && (labelHidden(joined) || parts.some(valueHidden));
    };
    return {hidden, labelHidden, keyHidden};
  };

  // Remove the series, categories, bars or stacked segments of hidden legend
  // entries and aggregation values, so the chart closes the gaps. A legend
  // entry controls the data elements with its label; otherwise the element in
  // the same position, or the elements drawn in its colour.
  function legendHiddenPayload(payload, state) {
    const {hidden, labelHidden, keyHidden} = legendStateMatchers(state);
    if (!payload || !hidden.size) return payload;
    const result = {...payload};
    if (Array.isArray(payload.panels)) result.panels = payload.panels.map(panel => legendHiddenPayload(panel, state));
    // Map site entries (triangles and state rings) hide the sites, not the series of the same colour.
    const siteMarks = new Set(['triangle', 'ring', 'ring-dashed']);
    const items = (payload.legend?.items || []).filter(item => item.colour && !siteMarks.has(item.marker));
    const hiddenItems = items.filter(item => labelHidden(item.label));
    if (Array.isArray(payload.sectors)) {
      // A hidden vendor drops its cells (and the sites left without cells); a hidden state drops its ring, and the
      // sites only drawn for that state (not on air yet).
      const siteItems = (payload.legend?.items || []).filter(item => siteMarks.has(item.marker) && labelHidden(item.label));
      const hiddenColours = new Set(siteItems.filter(item => item.marker === 'triangle').map(item => String(item.colour).toUpperCase()));
      const hiddenRings = new Set(siteItems.filter(item => item.marker !== 'triangle').map(item => (item.marker === 'ring' ? 'outage' : 'pipeline')));
      if (hiddenColours.size || hiddenRings.size) {
        result.sectors = payload.sectors.flatMap(site => {
          const cells = (site.cells || []).filter(cell => !hiddenColours.has(String(cell[2] || '').toUpperCase()));
          const ring = site.ring && !hiddenRings.has(site.ring) ? site.ring : undefined;
          if ((site.cells || []).length ? !cells.length : !ring) return [];
          return [{...site, cells, ring}];
        });
      }
    }
    if (payload.legend?.items) {
      result.legend = {...payload.legend, items: payload.legend.items.map(item => (
        item.colour && labelHidden(item.label) ? {...item, hidden: true} : item
      ))};
    }
    const hiddenIndexes = (elements, name) => {
      const names = elements.map(element => String(name(element) ?? ''));
      const indexes = new Set(names.map((value, index) => (value && labelHidden(value) ? index : -1)).filter(index => index >= 0));
      items.forEach((item, itemIndex) => {
        const label = String(item.label);
        if (!labelHidden(label) || names.includes(label)) return;
        if (elements.length === items.length) indexes.add(itemIndex);
        else elements.forEach((element, index) => {
          if (element?.colour === item.colour && (element.width === undefined || Number(element.width) === Number(item.width))) indexes.add(index);
        });
      });
      return indexes;
    };
    const pick = (values, indexes) => indexes.map(index => values?.[index]);
    if (Array.isArray(payload.series)) {
      const indexes = hiddenIndexes(payload.series, series => series.name ?? series.legend_name);
      result.series = payload.series.filter((series, index) => !indexes.has(index) && !(series.key && keyHidden(series.key)));
    }
    if (Array.isArray(payload.bars)) {
      const indexes = hiddenIndexes(payload.bars, bar => bar.legend);
      result.bars = payload.bars.filter((bar, index) => !indexes.has(index) && !keyHidden(bar.key));
    }
    // Row/column hierarchies (100% bars, failures, grouped averages) drop every
    // row and column with a hidden value at any of their levels.
    if (Array.isArray(payload.row_keys) && Array.isArray(payload.column_keys) && Array.isArray(payload.cells)) {
      let rows = payload.row_keys.map((_key, index) => index).filter(index => !keyHidden(payload.row_keys[index]));
      let columns = payload.column_keys.map((_key, index) => index).filter(index => !keyHidden(payload.column_keys[index]));
      let cellHidden = () => false;
      if (payload.type === 'mean_bar') {
        // Average bars are coloured by legend entry, which may not be a level.
        cellHidden = (row, column) => hiddenItems.some(item => payload.cell_colours?.[row]?.[column] === item.colour
          || [...(payload.row_keys[row] || []), ...(payload.column_keys[column] || [])].map(String).includes(String(item.label)));
        columns = columns.filter(column => rows.some(row => !cellHidden(row, column)));
        rows = rows.filter(row => columns.some(column => !cellHidden(row, column)));
      }
      result.row_keys = pick(payload.row_keys, rows);
      result.column_keys = pick(payload.column_keys, columns);
      result.cells = rows.map(row => columns.map(column => (cellHidden(row, column) ? Number.NaN : payload.cells[row]?.[column])));
      if (Array.isArray(payload.cell_colours)) result.cell_colours = rows.map(row => pick(payload.cell_colours[row], columns));
    } else if (Array.isArray(payload.categories) && Array.isArray(payload.cells)) {
      const kept = payload.categories.map((_category, index) => index).filter(index => !keyHidden(payload.categories[index]));
      result.categories = pick(payload.categories, kept);
      result.cells = pick(payload.cells, kept);
    } else if (Array.isArray(payload.keys) && Array.isArray(payload.cells)) {
      const kept = payload.keys.map((_key, index) => index).filter(index => !keyHidden(payload.keys[index]));
      result.keys = pick(payload.keys, kept);
      result.cells = pick(payload.cells, kept);
    }
    // Tables drop the rows and value columns labelled with a hidden value.
    if (payload.type === 'table' && Array.isArray(payload.rows)) {
      const rowDimensions = Math.max(1, Number(payload.row_dimension_count) || 1);
      const headers = payload.headers || [];
      const hiddenColumns = new Set(headers.map((header, index) => index >= rowDimensions && keyHidden(String(header).split(' · ')) ? index : -1).filter(index => index >= 0));
      result.rows = payload.rows
        .filter(row => !row.slice(0, rowDimensions).some(value => keyHidden(String(value ?? '').split(' · '))))
        .map(row => row.filter((_value, index) => !hiddenColumns.has(index)));
      if (hiddenColumns.size) {
        result.headers = headers.filter((_header, index) => !hiddenColumns.has(index));
        if (Array.isArray(payload.column_keys)) result.column_keys = payload.column_keys.filter((_key, index) => !hiddenColumns.has(index + rowDimensions));
      }
    }
    // Stacked charts drop the hidden segments of the remaining categories.
    const segments = Array.isArray(payload.states) ? payload.states : (Array.isArray(payload.buckets) ? payload.buckets : null);
    if (segments && Array.isArray(result.cells)) {
      const indexes = hiddenIndexes(segments, segment => segment?.name ?? segment?.label ?? segment);
      const clear = values => {
        if (!Array.isArray(values)) return values;
        if (values.some(Array.isArray)) return values.map(clear);
        return values.map((value, index) => indexes.has(index) ? 0 : value);
      };
      if (indexes.size) result.cells = clear(result.cells);
    }
    return result;
  }

  function drawStatus(context, payload, state, transform) {
    const states = payload.states || [];
    const stackLabelColour = payload.label_format?.color || stackedChartLabelColour(states, payload.cells);
    if (payload.mode === 'flat') {
      const categories = payload.categories || [], layout = legendLayout(payload.legend, 16);
      const left = layout.left, top = layout.top, width = layout.right - left, slotWidth = width / Math.max(categories.length, 1);
      const categoryPlan = axisLevelPlan(context, categories.map(category => ({value: category, width: slotWidth})), 150, payload.legend_format);
      const height = Math.max(180, layout.bottom - top - Math.max(60, categoryPlan.height + 16));
      const yDomain = expandedDomain(payload.domain?.y), ySpan = yDomain[1] - yDomain[0];
      const barWidth = Math.max(24, Math.min(220, Math.floor(width / Math.max(categories.length * 1.25, 1))));
      categories.forEach((category, index) => {
        const ratios = payload.cells[index] || [], x = left + index * width / categories.length + 12; let running = 0;
        const sideLabels = [];
        states.forEach((series, seriesIndex) => {
          const ratio = Number(ratios[seriesIndex] || 0), segmentLow = running, segmentHigh = running + ratio;
          const visibleLow = Math.max(segmentLow, yDomain[0]), visibleHigh = Math.min(segmentHigh, yDomain[1]);
          const segmentHeight = Math.max(0, visibleHigh - visibleLow) / ySpan * height, y = top + (yDomain[1] - visibleHigh) / ySpan * height;
          context.fillStyle = series.colour; context.fillRect(x, y, barWidth, segmentHeight);
          const label = percent(ratio, 2);
          drawConfiguredBarLabel(context, label, x, y, barWidth, segmentHeight, series.colour, 20, payload.label_position, 'vertical', () => {
            if (drawInsideHorizontalBarLabel(context, label, x, y, barWidth, segmentHeight, stackLabelColour, 15, payload.label_format)) return;
            if (ratio > 0) drawAdjacentStackLabel(context, label, x, y, barWidth, segmentHeight, top, top + height, width / categories.length - barWidth - 18, series.colour, sideLabels, 10, payload.label_format);
          }, payload.label_format);
          if (segmentHeight > 0) pushRectangleHit(state, transform, {x, y, width: barWidth, height: segmentHeight}, {label: category, series: series.name, value: tooltipPercent(ratio)});
          running += ratio;
        });
        pushAxisHit('column', 0, category, x - 12, top + height + 4, slotWidth, categoryPlan.height + 10);
        drawAxisLabel(context, categoryPlan, category, x + barWidth / 2, top + height + 8, slotWidth, '#5A6B78', payload.legend_format);
      });
      for (let tick = 0; tick <= 5; tick += 1) {
        const value = yDomain[0] + ySpan * tick / 5, y = top + height - tick / 5 * height; line(context, left - 20, y, left + width, y, '#E4E9ED');
        context.fillStyle = '#4E6271'; context.textAlign = 'right'; font(context, 18, true); context.fillText(`${(value * 100).toFixed(0)}%`, left - 14, y - 10);
      }
      drawLegend(context, payload.legend, {fontSize: 16}); return;
    }

    const rowKeys = payload.row_keys || [[]], columnKeys = payload.column_keys || [];
    // Prefer widening the row-hierarchy gutter to horizontally condensing a
    // business label. Dense column layouts still retain a useful plot area.
    const rowLabelSize = aggregationSize(payload.legend_format);
    font(context, rowLabelSize, true);
    const rowLabelWidths = (rowKeys[0] || []).map((_value, level) => Math.max(...rowKeys.map(key => textWidth(context, String(key[level] ?? ''))), 0) + 12);
    const upperLevels = Math.max((columnKeys[0]?.length || 1) - 1, 0), headerBandHeight = Math.min(32, 112 / Math.max(upperLevels, 1));
    const layout = legendLayout(payload.legend), rowOrigin = layout.position === 'left' ? layout.left : 24;
    const chartLeft = Math.max(rowOrigin + 121, Math.min(rowOrigin + 696, rowOrigin + Math.min(rowLabelWidths.reduce((sum, value) => sum + value, 0), 600) + 68));
    const chartRight = layout.right - 10, chartWidth = chartRight - chartLeft, columnWidth = chartWidth / Math.max(columnKeys.length, 1);
    // Column labels get the room they need: wrapped, smaller or vertical, never cut.
    const headerPlans = Array.from({length: upperLevels}, (_value, level) => {
      const plan = axisLevelPlan(context, hierarchySpans(columnKeys, level).map(([start, end, value]) => ({value, width: (end - start) * columnWidth})), 64, payload.legend_format, level);
      return {plan, height: Math.max(headerBandHeight, plan.height + 6)};
    });
    const headerOffset = level => headerPlans.slice(0, level).reduce((sum, header) => sum + header.height, 0);
    const leafPlan = payload.single_column ? null : axisLevelPlan(context, columnKeys.map(key => ({value: key.at(-1), width: columnWidth})), 150, payload.legend_format);
    const chartTop = layout.top + headerOffset(upperLevels) + 8;
    const chartHeight = Math.max(180, layout.bottom - chartTop - (leafPlan ? Math.max(60, leafPlan.height + 16) : 60));
    const rowHeight = chartHeight / rowKeys.length, barWidth = Math.max(18, Math.min(250, columnWidth * .72));
    const yDomain = expandedDomain(payload.domain?.y), ySpan = yDomain[1] - yDomain[0];
    const headerTop = chartTop - headerOffset(upperLevels) - 8;
    const rowLabelTotal = Math.max(rowLabelWidths.reduce((sum, value) => sum + value, 0), 1);
    const rowLabelFactor = Math.min((chartLeft - rowOrigin - 68) / rowLabelTotal, 1);
    const nestedRowStart = level => rowOrigin + rowLabelWidths.slice(0, level).reduce((sum, value) => sum + value * rowLabelFactor, 0);
    headerPlans.forEach(({plan, height}, level) => {
      const bandTop = headerTop + headerOffset(level);
      hierarchySpans(columnKeys, level).forEach(([start, end, value]) => {
        const left = chartLeft + start * columnWidth, right = chartLeft + end * columnWidth;
        drawAxisLabel(context, plan, value, (left + right) / 2, bandTop + Math.max(2, (height - 4 - plan.height) / 2), right - left, '#405765', payload.legend_format);
        line(context, left, bandTop + height - 3, right, bandTop + height - 3, '#BCC8D0');
        pushAxisHit('column', level, value, left, bandTop, right - left, height);
      });
    });
    for (let index = 1; index < columnKeys.length; index += 1) {
      let changed = columnKeys[index - 1].findIndex((value, level) => value !== columnKeys[index][level]);
      if (changed < 0) changed = columnKeys[index].length - 1;
      const x = chartLeft + index * columnWidth, lineTop = headerTop + headerOffset(Math.min(changed, upperLevels));
      if (changed === 0) line(context, x, lineTop, x, chartTop + chartHeight, '#AEBBC4', 2); else dashedVertical(context, x, lineTop, chartTop + chartHeight);
    }
    rowKeys.forEach((rowKey, rowIndex) => {
      const paneTop = chartTop + rowIndex * rowHeight, paneBottom = paneTop + rowHeight, next = rowKeys[rowIndex + 1];
      const changed = next ? rowKey.findIndex((value, level) => value !== next[level]) : 0;
      if (!next || changed === 0) line(context, rowOrigin, paneBottom, chartLeft + chartWidth, paneBottom, '#AEBBC4', 2);
      else dashedHorizontal(context, paneBottom, nestedRowStart(changed), chartLeft + chartWidth);
      (rowIndex === rowKeys.length - 1 ? [0, .5, 1] : [.5, 1]).forEach(fraction => {
        const value = yDomain[0] + ySpan * fraction, y = paneBottom - fraction * rowHeight; line(context, chartLeft, y, chartLeft + chartWidth, y, '#E8ECEF');
        context.fillStyle = '#566A78'; context.textAlign = 'left'; font(context, 15, true); context.fillText(`${(value * 100).toFixed(0)}%`, chartLeft - 50, y - 9);
      });
      columnKeys.forEach((columnKey, columnIndex) => {
        const ratios = payload.cells[rowIndex]?.[columnIndex], centreX = chartLeft + (columnIndex + .5) * columnWidth;
        if (!ratios) { context.fillStyle = '#B5C0C8'; context.textAlign = 'center'; font(context, 14); context.fillText('—', centreX, paneTop + rowHeight / 2 - 7); return; }
        const x = chartLeft + columnIndex * columnWidth + (columnWidth - barWidth) / 2; let running = 0;
        const sideLabels = [];
        states.forEach((series, seriesIndex) => {
          const ratio = Number(ratios[seriesIndex] || 0), segmentLow = running, segmentHigh = running + ratio;
          const visibleLow = Math.max(segmentLow, yDomain[0]), visibleHigh = Math.min(segmentHigh, yDomain[1]);
          const segmentHeight = Math.max(0, visibleHigh - visibleLow) / ySpan * rowHeight, y = paneTop + (yDomain[1] - visibleHigh) / ySpan * rowHeight;
          context.fillStyle = series.colour; context.fillRect(x, y, barWidth, segmentHeight);
          const label = percent(ratio, 2);
          drawConfiguredBarLabel(context, label, x, y, barWidth, segmentHeight, series.colour, 21, payload.label_position, 'vertical', () => {
            if (drawInsideHorizontalBarLabel(context, label, x, y, barWidth, segmentHeight, stackLabelColour, 15, payload.label_format)) return;
            if (ratio > 0) drawAdjacentStackLabel(context, label, x, y, barWidth, segmentHeight, paneTop, paneBottom, (columnWidth - barWidth) / 2 - 6, series.colour, sideLabels, 10, payload.label_format);
          }, payload.label_format);
          if (segmentHeight > 0) pushRectangleHit(state, transform, {x, y, width: barWidth, height: segmentHeight}, {label: displayKey([...rowKey, ...columnKey]), series: series.name, value: tooltipPercent(ratio)});
          running += ratio;
        });
      });
    });
    if (rowKeys[0]?.length) {
      const factor = rowLabelFactor; let x = rowOrigin;
      rowLabelWidths.forEach((width, level) => {
        const visible = width * factor;
        hierarchySpans(rowKeys, level).forEach(([start, end, value]) => {
          drawFullHierarchyLabel(context, value, x + 4, chartTop + (start + end) / 2 * rowHeight - aggregationSize(payload.legend_format, level) / 2, visible - 8, rowLabelSize, '#405765', payload.legend_format, level);
          pushAxisHit('row', level, value, x, chartTop + start * rowHeight, visible, (end - start) * rowHeight);
        });
        x += visible; line(context, x, chartTop, x, chartTop + chartHeight, '#D7DEE3');
      });
    }
    if (leafPlan) {
      columnKeys.forEach((key, index) => {
        const centre = chartLeft + (index + .5) * columnWidth;
        drawAxisLabel(context, leafPlan, key.at(-1), centre, chartTop + chartHeight + 10, columnWidth, '#4E6271', payload.legend_format);
        pushAxisHit('column', key.length - 1, key.at(-1), centre - columnWidth / 2, chartTop + chartHeight + 4, columnWidth, leafPlan.height + 10);
      });
    }
    drawLegend(context, payload.legend);
  }

  function drawFailure(context, payload, state, transform) {
    const states = payload.states || [];
    if (payload.mode === 'flat') {
      const layout = legendLayout(payload.legend, 13), rowOrigin = layout.position === 'left' ? layout.left : 28;
      const barLeft = rowOrigin + 362, maximumBarWidth = Math.max(220, layout.right - barLeft - 20);
      const xDomain = expandedDomain(payload.domain?.x), xSpan = xDomain[1] - xDomain[0];
      (payload.rows || []).forEach((row, index) => {
        const y = layout.top + 28 + index * 42; let running = 0;
        context.fillStyle = '#263B4A'; context.textAlign = 'left'; font(context, 17, true); context.fillText(displayKey(row.key).slice(0, 42), rowOrigin, y + 4);
        states.forEach((series, seriesIndex) => {
          const value = Number(row.values?.[seriesIndex] || 0), segmentLow = running, segmentHigh = running + value;
          const visibleLow = Math.max(segmentLow, xDomain[0]), visibleHigh = Math.min(segmentHigh, xDomain[1]);
          const x = barLeft + (visibleLow - xDomain[0]) / xSpan * maximumBarWidth, width = Math.max(0, visibleHigh - visibleLow) / xSpan * maximumBarWidth;
          if (width) { context.fillStyle = series.colour; context.fillRect(x, y, width, 30); drawConfiguredBarLabel(context, String(value), x, y, width, 30, series.colour, 20, payload.label_position, 'horizontal', () => drawInsideBarLabel(context, String(value), x, y, width, 30, payload.label_format?.color || '#FFFFFF', 20, payload.label_format), payload.label_format); pushRectangleHit(state, transform, {x, y, width, height: 30}, {label: displayKey(row.key), series: series.name, value: String(value)}); }
          running = segmentHigh;
        });
      });
      drawLegend(context, payload.legend, {fontSize: 13}); context.fillStyle = '#4E6271'; context.textAlign = 'left'; font(context, 19, true); context.fillText('# of failed / dropped sessions', barLeft, layout.bottom - 20); return;
    }
    const rowKeys = payload.row_keys || [[]], columnKeys = payload.column_keys || [];
    if (!columnKeys.length) return;
    const upperLevels = Math.max((columnKeys[0]?.length || 1) - 1, 0), headerBandHeight = upperLevels ? Math.min(34, 120 / upperLevels) : 0;
    const layout = legendLayout(payload.legend, 13), rowOrigin = layout.position === 'left' ? layout.left : 20;
    const rowLevels = rowKeys[0]?.length || 0;
    const rowLabelSize = aggregationSize(payload.legend_format);
    font(context, rowLabelSize, true);
    const rowLabelWidths = Array.from({length: rowLevels}, (_value, level) => Math.max(
      ...rowKeys.map(key => textWidth(context, String(key[level] ?? ''))), 0,
    ) + 14);
    const rowLabelGap = rowLevels > 1 ? 20 : 0;
    const rowLabelTotal = Math.max(rowLabelWidths.reduce((sum, value) => sum + value, 0), 1);
    // Keep hierarchy levels in separate panes. The previous fixed 110px
    // gutter caused long parent labels to enter the first chart column.
    const rowLabelArea = rowLevels ? Math.min(440, Math.max(230, rowLabelTotal + rowLabelGap * (rowLevels - 1))) : 0;
    const rowLabelFactor = Math.min((rowLabelArea - rowLabelGap * (rowLevels - 1)) / rowLabelTotal, 1);
    const chartLeft = rowOrigin + rowLabelArea + (rowLevels ? 56 : 110);
    const chartWidth = layout.right - chartLeft - 10, columnWidth = chartWidth / columnKeys.length;
    // Column labels get the room they need: wrapped, smaller or vertical, never cut.
    const headerPlans = Array.from({length: upperLevels}, (_value, level) => {
      const plan = axisLevelPlan(context, hierarchySpans(columnKeys, level).map(([start, end, value]) => ({value, width: (end - start) * columnWidth})), 64, payload.legend_format, level);
      return {plan, height: Math.max(headerBandHeight, plan.height + 8)};
    });
    const headerOffset = level => headerPlans.slice(0, level).reduce((sum, header) => sum + header.height, 0);
    const leafPlan = axisLevelPlan(context, columnKeys.map(key => ({value: key.at(-1), width: columnWidth})), 120, payload.legend_format, upperLevels);
    const headerTop = layout.top, baseChartTop = headerTop + headerOffset(upperLevels) + 8;
    const leafHeaderHeight = Math.max(34, leafPlan.height + 10);
    const chartTop = baseChartTop + leafHeaderHeight;
    const chartHeight = Math.max(180, layout.bottom - chartTop - 40);
    const xDomain = expandedDomain(payload.domain?.x), xSpan = xDomain[1] - xDomain[0];
    const leafLabelY = baseChartTop + Math.max(0, (leafHeaderHeight - 8 - leafPlan.height) / 2), rowHeight = chartHeight / rowKeys.length;
    headerPlans.forEach(({plan, height}, level) => {
      const y = headerTop + headerOffset(level);
      hierarchySpans(columnKeys, level).forEach(([start, end, value]) => {
        const centre = chartLeft + (start + end) / 2 * columnWidth;
        drawAxisLabel(context, plan, value, centre, y + Math.max(0, (height - 6 - plan.height) / 2), (end - start) * columnWidth, '#566A78', payload.legend_format);
        pushAxisHit('column', level, value, chartLeft + start * columnWidth, y, (end - start) * columnWidth, height);
        line(context, chartLeft + start * columnWidth, y + height - 4, chartLeft + end * columnWidth, y + height - 4, '#C8D2D9');
      });
    });
    columnKeys.forEach((key, index) => {
      const centre = chartLeft + (index + .5) * columnWidth, cellLeft = chartLeft + index * columnWidth;
      drawAxisLabel(context, leafPlan, key.at(-1), centre, leafLabelY, columnWidth, '#4E6271', payload.legend_format);
      pushAxisHit('column', key.length - 1, key.at(-1), cellLeft, leafLabelY - 4, columnWidth, leafPlan.height + 8);
      if (index) { let changed = columnKeys[index - 1].findIndex((value, level) => value !== key[level]); if (changed < 0) changed = key.length - 1; const lineTop = changed === 0 ? headerTop : headerTop + headerOffset(Math.min(changed, upperLevels)); if (changed === 0) line(context, cellLeft, lineTop, cellLeft, chartTop + chartHeight + 25, '#AEBBC4', 2); else dashedVertical(context, cellLeft, lineTop, chartTop + chartHeight + 25); } else line(context, cellLeft, headerTop, cellLeft, chartTop + chartHeight + 25, '#AEBBC4', 2);
      context.fillStyle = '#566A78'; context.textAlign = 'left'; font(context, 13, true); context.fillText(numericLabel(xDomain[0]), cellLeft + 3, chartTop + chartHeight + 7); context.textAlign = 'right'; context.fillText(numericLabel(xDomain[1]), cellLeft + columnWidth - 3, chartTop + chartHeight + 7);
    });
    const nestedRowStart = level => rowOrigin + rowLabelWidths.slice(0, level).reduce((sum, width) => sum + width * rowLabelFactor + rowLabelGap, 0);
    for (let level = 0; level < rowLevels; level += 1) {
      const labelLeft = nestedRowStart(level), labelWidth = rowLabelWidths[level] * rowLabelFactor;
      hierarchySpans(rowKeys, level).forEach(([start, end, value]) => {
        drawFullHierarchyLabel(context, value, labelLeft + 3, chartTop + (start + end) / 2 * rowHeight - aggregationSize(payload.legend_format, level) / 2, labelWidth - 6, rowLabelSize, '#405765', payload.legend_format, level);
        pushAxisHit('row', level, value, labelLeft, chartTop + start * rowHeight, labelWidth, (end - start) * rowHeight);
      });
      if (level < rowLevels - 1) line(context, labelLeft + labelWidth + rowLabelGap / 2, chartTop, labelLeft + labelWidth + rowLabelGap / 2, chartTop + chartHeight, '#D7DEE3');
    }
    rowKeys.forEach((rowKey, rowIndex) => {
      const rowTop = chartTop + rowIndex * rowHeight, rowBottom = rowTop + rowHeight, next = rowKeys[rowIndex + 1];
      const changed = next ? rowKey.findIndex((value, level) => value !== next[level]) : 0;
      if (next && changed > 0) dashedHorizontal(context, rowBottom, nestedRowStart(changed), chartLeft + chartWidth); else line(context, rowOrigin, rowBottom, chartLeft + chartWidth, rowBottom, '#AEBBC4', 2);
      columnKeys.forEach((columnKey, columnIndex) => {
        const values = payload.cells[rowIndex]?.[columnIndex] || [], cellLeft = chartLeft + columnIndex * columnWidth, available = Math.max(columnWidth - 10, 1); let running = 0, lastSegmentEnd = cellLeft + 4;
        const barHeight = Math.max(16, Math.min(26, rowHeight * .84)), y = rowTop + (rowHeight - barHeight) / 2, outside = [];
        states.forEach((series, seriesIndex) => { const value = Number(values[seriesIndex] || 0), segmentLow = running, segmentHigh = running + value, visibleLow = Math.max(segmentLow, xDomain[0]), visibleHigh = Math.min(segmentHigh, xDomain[1]), x = cellLeft + 4 + (visibleLow - xDomain[0]) / xSpan * available, segmentWidth = Math.max(0, visibleHigh - visibleLow) / xSpan * available; if (segmentWidth) { lastSegmentEnd = Math.max(lastSegmentEnd, x + segmentWidth); context.fillStyle = series.colour; context.fillRect(x, y, segmentWidth, barHeight); drawConfiguredBarLabel(context, String(value), x, y, segmentWidth, barHeight, series.colour, 16, payload.label_position, 'horizontal', () => { if (!drawInsideBarLabel(context, String(value), x, y, segmentWidth, barHeight, payload.label_format?.color || '#FFFFFF', 16, payload.label_format)) outside.push(String(value)); }, payload.label_format); pushRectangleHit(state, transform, {x, y, width: segmentWidth, height: barHeight}, {label: displayKey([...rowKey, ...columnKey]), series: series.name, value: String(value)}); } running = segmentHigh; });
        if (outside.length) { const label = outside.join(' / '), labelX = lastSegmentEnd + 3; context.fillStyle = '#34495A'; context.textAlign = 'left'; context.textBaseline = 'top'; font(context, 16, true); if (labelX + textWidth(context, label) <= cellLeft + columnWidth - 3) context.fillText(label, labelX, y + 1); }
      });
    });
    line(context, chartLeft + chartWidth, headerTop, chartLeft + chartWidth, chartTop + chartHeight + 25, '#AEBBC4', 2); drawLegend(context, payload.legend, {fontSize: 13, sideX: layout.position === 'right' ? chartLeft + chartWidth + 18 : undefined});
  }

  function drawDistribution(context, payload, state, transform) {
    const keys = payload.keys || [], buckets = payload.buckets || [];
    const stackLabelColour = payload.label_format?.color || stackedChartLabelColour(buckets, payload.cells);
    const layout = legendLayout(payload.legend), left = layout.left, width = layout.right - left;
    const axis = hierarchicalAxisPlans(context, keys, width, payload.legend_format);
    const top = layout.top + axis.headerHeight;
    const usableBottom = layout.position === 'bottom' ? layout.bottom : 884;
    const height = Math.max(180, usableBottom - top - axis.leafHeight);
    const yDomain = expandedDomain(payload.domain?.y), ySpan = yDomain[1] - yDomain[0];
    const barWidth = Math.max(24, Math.min(220, Math.floor(width / Math.max(keys.length * 1.25, 1))));
    for (let tick = 0; tick <= 5; tick += 1) {
      const value = yDomain[0] + ySpan * tick / 5, y = top + height - tick / 5 * height;
      line(context, left, y, left + width, y, '#E4E9ED');
      context.fillStyle = '#4E6271'; context.textAlign = 'right'; font(context, 16, true);
      context.fillText(`${(value * 100).toFixed(0)}%`, left - 12, y - 8);
    }
    line(context, left, top, left, top + height, '#AEBBC4', 2);
    keys.forEach((key, index) => {
      const ratios = payload.cells[index] || [], x = left + index * width / keys.length + 10; let running = 0;
      const sideLabels = [];
      buckets.forEach((bucket, bucketIndex) => {
        const ratio = Number(ratios[bucketIndex] || 0), segmentLow = running, segmentHigh = running + ratio;
        const visibleLow = Math.max(segmentLow, yDomain[0]), visibleHigh = Math.min(segmentHigh, yDomain[1]);
        const segmentHeight = Math.max(0, visibleHigh - visibleLow) / ySpan * height, y = top + (yDomain[1] - visibleHigh) / ySpan * height;
        context.fillStyle = bucket.colour; context.fillRect(x, y, barWidth, segmentHeight);
        const label = percent(ratio, 2); font(context, 17, true);
        const labelWidth = textWidth(context, label);
        drawConfiguredBarLabel(context, label, x, y, barWidth, segmentHeight, bucket.colour, 17, payload.label_position, 'vertical', () => {
          if (drawInsideHorizontalBarLabel(context, label, x, y, barWidth, segmentHeight, stackLabelColour, 14, payload.label_format)) return;
          if (ratio > 0) drawAdjacentStackLabel(context, label, x, y, barWidth, segmentHeight, top, top + height, width / keys.length - barWidth - 16, bucket.colour, sideLabels, 10, payload.label_format);
        }, payload.label_format);
        if (segmentHeight > 0) pushRectangleHit(state, transform, {x, y, width: barWidth, height: segmentHeight}, {label: displayKey(key), series: bucket.name, value: tooltipPercent(ratio)});
        running += ratio;
      });
    });
    drawTopColumnSeparators(context, keys, payload.axis_columns || [], left, width, top, top + height, axis);
    drawHierarchicalAxisLabels(context, keys, left, width, top, top + height, payload.legend_format, axis); drawLegend(context, payload.legend);
  }

  function cdfGeometry(legend) {
    const layout = legendLayout(legend, 11);
    return {left: layout.left, top: layout.top, width: layout.right - layout.left, height: Math.max(180, layout.bottom - layout.top - 42)};
  }

  function drawCdf(context, payload, state, transform) {
    const plot = cdfGeometry(payload.legend), xLow = Number(payload.domain?.x?.[0] ?? 0), xHigh = Number(payload.domain?.x?.[1] ?? 1);
    const yLow = Number(payload.domain?.y?.[0] ?? 0), yHigh = Number(payload.domain?.y?.[1] ?? 1);
    const endpointLabels = [];
    context.save(); context.beginPath(); context.rect(plot.left, plot.top, plot.width, plot.height); context.clip();
    (payload.quality_bands || []).forEach(band => {
      const low = Math.max(xLow, Number(band.low)), high = Math.min(xHigh, Number(band.high));
      if (high <= low) return;
      context.fillStyle = band.colour; context.globalAlpha = .10;
      context.fillRect(plot.left + (low - xLow) / (xHigh - xLow) * plot.width, plot.top,
        (high - low) / (xHigh - xLow) * plot.width, plot.height);
      context.globalAlpha = 1;
    });
    if (payload.histogram_bars) {
      const series = payload.series || [];
      series.forEach((item, seriesIndex) => {
        (item.bin_ratios || []).forEach((ratio, binIndex) => {
          const left = Number(item.bin_edges[binIndex]), right = Number(item.bin_edges[binIndex + 1]);
          const binWidth = (right - left) / (xHigh - xLow) * plot.width;
          const width = binWidth * .85 / series.length;
          const x = plot.left + (left - xLow) / (xHigh - xLow) * plot.width + binWidth * .075 + seriesIndex * width;
          const height = Math.max(0, (ratio - yLow) / (yHigh - yLow) * plot.height);
          const y = plot.top + plot.height - height;
          context.fillStyle = item.colour; context.fillRect(x, y, width, height);
          pushRectangleHit(state, transform, {x, y, width, height}, {label: `${left}–${right}`, series: item.name, value: tooltipPercent(ratio)});
        });
      });
    } else {
    (payload.series || []).forEach(series => {
      const points = [];
      (series.x || []).forEach((value, index) => {
        const cumulative = Number(series.y?.[index]); if (!finite(value) || !finite(cumulative)) return;
        points.push({x: plot.left + (Number(value) - xLow) / (xHigh - xLow || 1) * plot.width, y: plot.top + plot.height - (cumulative - yLow) / (yHigh - yLow || 1) * plot.height, value: Number(value), cumulative});
      });
      if (points.length) {
        context.strokeStyle = series.colour; context.lineWidth = Number(series.width || 1); context.lineJoin = 'round'; context.beginPath();
        lineDash(context, series.dash, context.lineWidth);
        points.forEach((point, index) => index ? context.lineTo(point.x, point.y) : context.moveTo(point.x, point.y)); context.stroke();
        context.setLineDash([]); context.lineCap = 'butt'; context.lineJoin = 'miter';
        pushLineHit(state, transform, points, {label: payload.metric, series: series.name || series.legend_name});
        const endpoint = points.at(-1);
        if (!payload.histogram) endpointLabels.push({x: endpoint.x, y: endpoint.y, label: series.name || series.legend_name, colour: series.colour});
      }
    });
    }
    context.restore();
    endpointLabels.forEach(item => drawConfiguredPointLabel(
      context, item.label, item.x, item.y, item.colour, payload.label_position, 13, payload.label_format,
    ));
    for (let tick = 0; tick <= 4; tick += 1) {
      const cumulative = yLow + (yHigh - yLow) * tick / 4;
      const y = plot.top + plot.height - tick / 4 * plot.height; line(context, plot.left, y, plot.left + plot.width, y, '#E4E9ED');
      context.fillStyle = '#4E6271'; context.textAlign = 'right'; font(context, 18, true); context.fillText(`${(cumulative * 100).toFixed(0)}%`, plot.left - 14, y - 10);
    }
    for (let tick = 0; tick <= 5; tick += 1) {
      const value = xLow + (xHigh - xLow) * tick / 5, x = plot.left + plot.width * tick / 5;
      line(context, x, plot.top + plot.height, x, plot.top + plot.height + 7, '#62727E');
      context.fillStyle = '#4E6271'; context.textAlign = 'center'; font(context, 16, true); context.fillText(value.toFixed(Number.isInteger(payload.x_decimals) ? payload.x_decimals : 1), x, plot.top + plot.height + 7);
    }
    context.fillStyle = '#405765'; context.textAlign = 'center'; font(context, 20, true); context.fillText(String(payload.metric || ''), plot.left + plot.width / 2, plot.top + plot.height + 31);
    if (payload.y_label) verticalLabel(context, payload.y_label, Math.max(18, plot.left - 65), plot.top + plot.height / 2, '#405765', 18);
    // The numeric axes, for the range of the Designer: the values of the X axis (KPI units, from the lowest to
    // the highest value of the series) and the percentages of the Y axis.
    const values = (payload.series || []).flatMap(series => [...(series.x || []), ...(series.bin_edges || [])]).map(Number).filter(finite);
    const extent = values.length ? [Math.min(...values), Math.max(...values)] : [xLow, xHigh];
    const xStart = transformPoint(transform, plot.left, plot.top + plot.height), yStart = transformPoint(transform, plot.left - 80, plot.top);
    (state.numericAxes ||= []).push(
      {axis: 'x', domain: [xLow, xHigh], extent, x: xStart.x, y: xStart.y, width: plot.width * transform.scale, height: 60 * transform.scale},
      {axis: 'y', domain: [yLow * 100, yHigh * 100], extent: [0, 100], percent: true, x: yStart.x, y: yStart.y, width: 80 * transform.scale, height: plot.height * transform.scale},
    );
    drawLegend(context, payload.legend, {fontSize: 11, sideX: legendLayout(payload.legend, 11).position === 'right' ? plot.left + plot.width + 25 : undefined});
  }

  function drawMultiCdf(context, payload, state, transform) {
    const panels = payload.panels || [], columns = panels.length > 1 ? 2 : 1, rows = Math.max(1, Math.ceil(panels.length / columns));
    const cellWidth = LOGICAL_WIDTH / columns, cellHeight = (LOGICAL_HEIGHT - 80) / rows;
    panels.forEach((panel, index) => {
      const scale = Math.min((cellWidth - 18) / LOGICAL_WIDTH, (cellHeight - 10) / LOGICAL_HEIGHT);
      const width = LOGICAL_WIDTH * scale, height = LOGICAL_HEIGHT * scale;
      const x = index % columns * cellWidth + (cellWidth - width) / 2, y = 80 + Math.floor(index / columns) * cellHeight + (cellHeight - height) / 2;
      context.save(); context.translate(x, y); context.scale(scale, scale); context.fillStyle = '#FFFFFF'; context.fillRect(0, 0, LOGICAL_WIDTH, LOGICAL_HEIGHT);
      drawPayload(context, panel, state, {x: transform.x + x * transform.scale, y: transform.y + y * transform.scale, scale: transform.scale * scale}); context.restore();
    });
  }

  function drawMeanBars(context, payload, state, transform) {
    if (payload.mode === 'hierarchy') {
      const rowKeys = payload.row_keys || [[]], columnKeys = payload.column_keys || [[]];
      const layout = legendLayout(payload.legend), rowOrigin = layout.position === 'left' ? layout.left : 24;
      const rowLevels = rowKeys[0]?.length || 0, labelWidth = rowLevels ? Math.min(140, Math.max(72, (layout.right - rowOrigin) / (rowLevels + 5))) : 0;
      const chartLeft = rowOrigin + rowLevels * labelWidth + 56, chartRight = layout.right - 12, chartWidth = chartRight - chartLeft;
      const columnWidth = chartWidth / Math.max(columnKeys.length, 1);
      const upperLevels = Math.max((columnKeys[0]?.length || 1) - 1, 0);
      // Column labels get the room they need: wrapped, smaller or vertical, never cut.
      const headerPlans = Array.from({length: upperLevels}, (_value, level) => {
        const plan = axisLevelPlan(context, hierarchySpans(columnKeys, level).map(([start, end, value]) => ({value, width: (end - start) * columnWidth})), 64, payload.legend_format, level);
        return {plan, height: Math.max(28, plan.height + 6)};
      });
      const headerOffset = level => headerPlans.slice(0, level).reduce((sum, header) => sum + header.height, 0);
      const leafPlan = axisLevelPlan(context, columnKeys.map(key => ({value: key.at(-1), width: columnWidth})), 150, payload.legend_format);
      const chartTop = layout.top + headerOffset(upperLevels) + 8, chartHeight = Math.max(180, layout.bottom - chartTop - Math.max(30, leafPlan.height + 10));
      const rowHeight = chartHeight / Math.max(rowKeys.length, 1);
      const yDomain = expandedDomain(payload.domain?.y), ySpan = yDomain[1] - yDomain[0];
      headerPlans.forEach(({plan, height}, level) => hierarchySpans(columnKeys, level).forEach(([start, end, value]) => {
        const left = chartLeft + start * columnWidth, right = chartLeft + end * columnWidth, bandTop = layout.top + headerOffset(level);
        drawAxisLabel(context, plan, value, (left + right) / 2, bandTop + Math.max(0, (height - 4 - plan.height) / 2), right - left, '#405765', payload.legend_format);
        line(context, left, bandTop + height - 3, right, bandTop + height - 3, '#C8D2D9');
        pushAxisHit('column', level, value, left, bandTop - 2, right - left, height);
      }));
      for (let columnIndex = 0; columnIndex < columnKeys.length; columnIndex += 1) {
        const cellLeft = chartLeft + columnIndex * columnWidth;
        if (!columnIndex) {
          line(context, cellLeft, layout.top, cellLeft, chartTop + chartHeight + 22, '#AEBBC4', 2);
          continue;
        }
        let changed = columnKeys[columnIndex - 1].findIndex((value, level) => value !== columnKeys[columnIndex][level]);
        if (changed < 0) changed = columnKeys[columnIndex].length - 1;
        const lineTop = layout.top + headerOffset(Math.min(changed, upperLevels));
        if (changed === 0) line(context, cellLeft, lineTop, cellLeft, chartTop + chartHeight + 22, '#AEBBC4', 2);
        else dashedVertical(context, cellLeft, lineTop, chartTop + chartHeight + 22);
      }
      line(context, chartLeft + chartWidth, layout.top, chartLeft + chartWidth, chartTop + chartHeight + 22, '#AEBBC4', 2);
      rowKeys.forEach((rowKey, rowIndex) => {
        const top = chartTop + rowIndex * rowHeight, bottom = top + rowHeight, next = rowKeys[rowIndex + 1];
        const changed = next ? rowKey.findIndex((value, level) => value !== next[level]) : 0;
        if (next && changed > 0) dashedHorizontal(context, bottom, rowOrigin + changed * labelWidth, chartRight); else line(context, rowOrigin, bottom, chartRight, bottom, '#AEBBC4', 2);
        rowKey.forEach((value, level) => { context.fillStyle = payload.legend_format?.configured && payload.legend_format.color ? payload.legend_format.color : '#405765'; context.textAlign = 'left'; aggregationFont(context, payload.legend_format, level); context.fillText(fittedText(context, value, labelWidth - 8), rowOrigin + level * labelWidth + 4, top + rowHeight / 2 - 8); pushAxisHit('row', level, value, rowOrigin + level * labelWidth, top, labelWidth, rowHeight); });
        columnKeys.forEach((columnKey, columnIndex) => {
          // A combination without valid samples has no bar, not a zero bar.
          const raw = payload.cells?.[rowIndex]?.[columnIndex]; if (raw === null || raw === undefined) return;
          const value = Number(raw); if (!Number.isFinite(value)) return;
          const cellLeft = chartLeft + columnIndex * columnWidth, plotTop = top + 4, plotBottom = bottom - 10, plotHeight = Math.max(1, plotBottom - plotTop);
          const valueY = plotBottom - (value - yDomain[0]) / ySpan * plotHeight, zeroY = plotBottom - (clamp(0, yDomain[0], yDomain[1]) - yDomain[0]) / ySpan * plotHeight;
          const width = Math.max(14, Math.min(columnWidth * .68, 110)), x = cellLeft + (columnWidth - width) / 2, y = Math.max(plotTop, Math.min(valueY, zeroY)), height = Math.max(0, Math.min(plotBottom, Math.max(valueY, zeroY)) - y);
          const colour = payload.cell_colours?.[rowIndex]?.[columnIndex] || '#4E79A7';
          context.fillStyle = colour; context.fillRect(x, y, width, height); const label = value.toFixed(2);
          drawConfiguredBarLabel(context, label, x, y, width, height, colour, 19, payload.label_position, 'vertical', () => { if (!(height >= 36 && drawInsideBarLabel(context, label, x, y, width, height, payload.label_format?.color || '#FFFFFF', 19, payload.label_format))) { context.fillStyle = payload.label_format?.color || colour; context.textAlign = 'center'; labelFont(context, 18, payload.label_format); context.fillText(label, x + width / 2, Math.max(top + 2, y - 22)); } }, payload.label_format);
          pushRectangleHit(state, transform, {x, y, width, height}, {label: displayKey([...rowKey, ...columnKey]), series: payload.aggregation || 'mean', value: label});
        });
      });
      columnKeys.forEach((columnKey, columnIndex) => {
        drawAxisLabel(context, leafPlan, columnKey.at(-1), chartLeft + (columnIndex + .5) * columnWidth, chartTop + chartHeight + 4, columnWidth, '#4E6271', payload.legend_format);
        pushAxisHit('column', columnKey.length - 1, columnKey.at(-1), chartLeft + columnIndex * columnWidth, chartTop + chartHeight + 2, columnWidth, leafPlan.height + 6);
      });
      drawLegend(context, payload.legend); return;
    }
    const bars = payload.bars || [], keys = bars.map(bar => bar.key);
    const layout = legendLayout(payload.legend), left = Math.max(105, layout.left), width = layout.right - left;
    const axis = hierarchicalAxisPlans(context, keys, width, payload.legend_format);
    const top = layout.top + axis.headerHeight, usableBottom = layout.position === 'bottom' ? layout.bottom : 884;
    const baseline = Math.max(top + 180, usableBottom - axis.leafHeight);
    const yDomain = expandedDomain(payload.domain?.y), ySpan = yDomain[1] - yDomain[0], plotHeight = baseline - top;
    const zeroY = baseline - (clamp(0, yDomain[0], yDomain[1]) - yDomain[0]) / ySpan * plotHeight;
    const barWidth = Math.min(260, Math.max(32, width / Math.max(bars.length * 1.22, 1)));
    bars.forEach((bar, index) => {
      if (bar.hidden) return;
      const valueY = baseline - (Number(bar.value) - yDomain[0]) / ySpan * plotHeight, x = left + (index + .5) * width / bars.length - barWidth / 2;
      const y = Math.max(top, Math.min(valueY, zeroY)), height = Math.max(0, Math.min(baseline, Math.max(valueY, zeroY)) - y);
      context.fillStyle = bar.colour; context.fillRect(x, y, barWidth, height);
      const label = Number(bar.value).toFixed(2);
      drawConfiguredBarLabel(context, label, x, y, barWidth, height, bar.colour, 24, payload.label_position, 'vertical', () => {
        if (height >= 46 && drawInsideBarLabel(context, label, x, y, barWidth, height, payload.label_format?.color || '#FFFFFF', 24, payload.label_format)) {} else {
          context.fillStyle = payload.label_format?.color || bar.colour; context.textAlign = 'center'; labelFont(context, 24, payload.label_format); context.fillText(label, x + barWidth / 2, y - 25);
        }
      }, payload.label_format);
      pushRectangleHit(state, transform, {x, y, width: barWidth, height}, {label: displayKey(bar.key), series: bar.legend, value: Number(bar.value).toFixed(2)});
    });
    drawTopColumnSeparators(context, keys, payload.axis_columns || [], left, width, top, baseline, axis);
    drawHierarchicalAxisLabels(context, keys, left, width, top, baseline, payload.legend_format, axis); verticalLabel(context, payload.metric || '', layout.position === 'left' ? left - 28 : 42, (top + baseline) / 2, '#405765', 21); drawLegend(context, payload.legend, {sideX: layout.position === 'right' ? left + width + 25 : undefined});
  }

  function expandedDomain(domain) {
    let low = Number(domain?.[0] ?? 0), high = Number(domain?.[1] ?? 1); if (low === high) high = low + 1; return [low, high];
  }

  function drawScatter(context, payload, state, transform) {
    const layout = legendLayout(payload.legend, 14), left = layout.left, top = layout.top;
    const width = layout.right - left, height = Math.max(180, layout.bottom - top - 42), xDomain = expandedDomain(payload.domain?.x), yDomain = expandedDomain(payload.domain?.y);
    (payload.series || []).forEach(series => (series.points || []).forEach(point => {
      if (Number(point[0]) < xDomain[0] || Number(point[0]) > xDomain[1] || Number(point[1]) < yDomain[0] || Number(point[1]) > yDomain[1]) return;
      const x = left + (Number(point[0]) - xDomain[0]) / (xDomain[1] - xDomain[0]) * width, y = top + height - (Number(point[1]) - yDomain[0]) / (yDomain[1] - yDomain[0]) * height;
      context.fillStyle = series.colour; context.beginPath(); context.arc(x, y, 4, 0, Math.PI * 2); context.fill();
      drawConfiguredPointLabel(context, series.name, x, y, series.colour, payload.label_position, 13, payload.label_format);
      pushPointHit(state, transform, x, y, {label: series.name, series: `${payload.x_label} / ${payload.y_label}`, value: `${numericLabel(point[0])} / ${numericLabel(point[1])}`});
    }));
    for (let tick = 0; tick <= 5; tick += 1) {
      const x = left + width * tick / 5, y = top + height - height * tick / 5;
      const xValue = xDomain[0] + (xDomain[1] - xDomain[0]) * tick / 5, yValue = yDomain[0] + (yDomain[1] - yDomain[0]) * tick / 5;
      line(context, x, top + height, x, top + height + 7, '#62727E'); line(context, left - 7, y, left, y, '#62727E');
      context.fillStyle = '#4E6271'; context.textAlign = 'center'; font(context, 16, true); context.fillText(xValue.toFixed(0), x, top + height + 7);
      context.textAlign = 'right'; context.fillText(yValue.toFixed(1), left - 12, y - 9);
    }
    context.fillStyle = '#405765'; context.textAlign = 'center'; font(context, 20, true); context.fillText(payload.x_label || '', left + width / 2, top + height + 30);
    context.textAlign = 'left'; context.fillText(payload.y_label || '', layout.position === 'left' ? left - 28 : 28, top - 5); drawLegend(context, payload.legend, {fontSize: 14, sideX: layout.position === 'right' ? left + width + 25 : undefined});
  }

  function drawMap(context, payload, state, transform) {
    const layout = legendLayout(payload.legend, 13), left = layout.left, top = layout.top;
    const width = layout.right - left, height = Math.max(180, layout.bottom - top - 24), rawX = expandedDomain(payload.domain?.x), rawY = expandedDomain(payload.domain?.y);
    const xPad = Math.max((rawX[1] - rawX[0]) * .06, .004), yPad = Math.max((rawY[1] - rawY[0]) * .06, .004);
    const xDomain = [rawX[0] - xPad, rawX[1] + xPad], yDomain = [rawY[0] - yPad, rawY[1] + yPad];
    context.fillStyle = '#EDF4F0'; context.fillRect(left, top, width, height);
    for (const fraction of [.2, .4, .6, .8]) { line(context, left + width * fraction, top, left + width * fraction, top + height, '#D8E5DF'); line(context, left, top + height * fraction, left + width, top + height * fraction, '#D8E5DF'); }
    const basemap = payload.basemap, worldBounds = basemap?.world_bounds;
    // The plot and its tiles, to turn a position on the canvas into a place (see getCanvasMapView).
    state.mapGeometry = {left, top, width, height, worldBounds: Array.isArray(worldBounds) ? worldBounds.map(Number) : null, zoom: Number(basemap?.zoom)};
    const tileRecords = mapTileRecords(state.canvas, payload);
    if (Array.isArray(worldBounds) && worldBounds.length === 4) {
      const [worldLeft, worldTop, worldRight, worldBottom] = worldBounds.map(Number);
      const sourceWidth = worldRight - worldLeft, sourceHeight = worldBottom - worldTop;
      if (sourceWidth > 0 && sourceHeight > 0) {
        const tileSize = Number(basemap.tile_size || 256);
        context.save(); context.beginPath(); context.rect(left, top, width, height); context.clip();
        tileRecords.filter(record => record.status === 'ready').forEach(record => {
          const x = left + (record.x * tileSize - worldLeft) / sourceWidth * width;
          const y = top + (record.y * tileSize - worldTop) / sourceHeight * height;
          context.drawImage(record.image, x, y, tileSize / sourceWidth * width + .5, tileSize / sourceHeight * height + .5);
        });
        context.restore();
      }
    }
    context.strokeStyle = '#B9CDC4'; context.lineWidth = 2; context.strokeRect(left, top, width, height);
    const pointRadius = Math.max(1, Number(payload.point_radius) || 4);
    const project = (longitude, latitude) => {
      if (Array.isArray(worldBounds) && worldBounds.length === 4) {
        const [worldLeft, worldTop, worldRight, worldBottom] = worldBounds.map(Number);
        const projected = osmWorldCoordinates(latitude, longitude, basemap.zoom);
        return [left + (projected[0] - worldLeft) / (worldRight - worldLeft) * width, top + (projected[1] - worldTop) / (worldBottom - worldTop) * height];
      }
      return [left + (longitude - xDomain[0]) / (xDomain[1] - xDomain[0]) * width, top + height - (latitude - yDomain[0]) / (yDomain[1] - yDomain[0]) * height];
    };
    // Optional sites drawn with the grid: one wedge per cell (azimuth from north, beamwidth, vendor colour) under the
    // samples, and the mark of each site over them.
    const sites = (Array.isArray(payload.sectors) ? payload.sectors : []).filter(site => {
      const longitude = Number(site.lon), latitude = Number(site.lat);
      return longitude >= xDomain[0] && longitude <= xDomain[1] && latitude >= yDomain[0] && latitude <= yDomain[1];
    }).map(site => ({site, position: project(Number(site.lon), Number(site.lat))}));
    const radius = Number(payload.sector_radius) > 0 ? Number(payload.sector_radius) : Math.max(10, pointRadius * 2.6);
    // Wedges only once the map is zoomed in (larger points, or as the map says); the whole area shows one triangle
    // per site in the colour of its first cell's vendor, so the sites never hide the grid squares nor read as measurements.
    const wedges = typeof payload.sector_wedges === 'boolean' ? payload.sector_wedges : pointRadius >= 10;
    if (wedges && sites.length) {
      context.save(); context.beginPath(); context.rect(left, top, width, height); context.clip();
      sites.forEach(({site, position: [x, y]}) => (site.cells || []).forEach(cell => {
        const azimuth = Number(cell[0]), beam = Math.max(24, Math.min(140, Number(cell[1]) || 65));
        context.beginPath();
        if (cell[0] === null || !Number.isFinite(azimuth)) context.arc(x, y, radius * .45, 0, Math.PI * 2);
        else { context.moveTo(x, y); context.arc(x, y, radius, (azimuth - beam / 2 - 90) * Math.PI / 180, (azimuth + beam / 2 - 90) * Math.PI / 180); context.closePath(); }
        context.globalAlpha = .16; context.fillStyle = cell[2] || '#868E96'; context.fill();
        context.globalAlpha = .6; context.setLineDash([]); context.strokeStyle = cell[2] || '#868E96'; context.lineWidth = 1.4; context.stroke();
        context.globalAlpha = 1;
      }));
      context.restore();
    }
    // Samples are squares when the map asks for them (grid squares), circles otherwise.
    const squares = payload.point_shape === 'square';
    (payload.series || []).forEach(series => (series.points || []).forEach(point => {
      if (Number(point[0]) < rawX[0] || Number(point[0]) > rawX[1] || Number(point[1]) < rawY[0] || Number(point[1]) > rawY[1]) return;
      let x, y;
      if (Array.isArray(worldBounds) && worldBounds.length === 4) {
        const [worldLeft, worldTop, worldRight, worldBottom] = worldBounds.map(Number);
        const projected = osmWorldCoordinates(point[1], point[0], basemap.zoom);
        x = left + (projected[0] - worldLeft) / (worldRight - worldLeft) * width;
        y = top + (projected[1] - worldTop) / (worldBottom - worldTop) * height;
      } else {
        x = left + (Number(point[0]) - xDomain[0]) / (xDomain[1] - xDomain[0]) * width;
        y = top + height - (Number(point[1]) - yDomain[0]) / (yDomain[1] - yDomain[0]) * height;
      }
      context.fillStyle = series.colour; context.strokeStyle = '#FFFFFF'; context.lineWidth = 1; context.beginPath();
      if (squares) context.rect(x - pointRadius, y - pointRadius, pointRadius * 2, pointRadius * 2);
      else context.arc(x, y, pointRadius, 0, Math.PI * 2);
      context.fill(); context.stroke();
      drawConfiguredPointLabel(context, series.name, x, y, series.colour, payload.label_position, 13, payload.label_format);
      pushPointHit(state, transform, x, y, {label: series.name, series: `${payload.y_label} / ${payload.x_label}`, value: `${numericLabel(point[1])} / ${numericLabel(point[0])}`});
    }));
    if (sites.length) {
      context.save(); context.beginPath(); context.rect(left, top, width, height); context.clip();
      sites.forEach(({site, position: [x, y]}) => {
        // Sites with cells the inventory flags carry a ring: solid for locked, halted or disabled cells, dashed
        // for sites not on air yet or with planned or in-progress cells.
        const drawRing = size => {
          if (site.ring !== 'outage' && site.ring !== 'pipeline') return;
          context.save(); context.beginPath(); context.arc(x, y, size, 0, Math.PI * 2);
          context.setLineDash(site.ring === 'pipeline' ? [4, 3] : []);
          context.strokeStyle = '#FFFFFF'; context.lineWidth = 4.4; context.stroke();
          context.strokeStyle = site.ring === 'pipeline' ? '#495057' : '#212529'; context.lineWidth = 2.2; context.stroke();
          context.restore();
        };
        drawSiteMark(context, x, y, wedges ? 6 : 7, site.cells?.[0]?.[2] || '#868E96');
        drawRing(wedges && site.cells?.length ? radius + 3 : 11);
        pushPointHit(state, transform, x, y, {label: String(site.label || 'Site'), series: String(site.series || 'Inventory site'), value: String(site.detail || '')});
      });
      context.restore();
    }
    drawLegend(context, payload.legend, {fontSize: 13, sideX: layout.position === 'right' ? left + width + 25 : undefined});
    // A map can leave out its axis titles (the basemap already shows where it is): the Latitude title sits on the chart title's line.
    if (payload.axis_labels !== false) { context.fillStyle = '#405765'; context.textAlign = 'left'; font(context, 17, true); context.fillText(payload.x_label || '', left, top + height + 16); context.fillText(payload.y_label || '', layout.position === 'left' ? left - 28 : 26, top - 25); }
    context.textAlign = 'left';
    if (basemap?.attribution) {
      context.fillStyle = '#FFFFFF'; context.fillRect(left + width - 210, top + height - 25, 206, 21);
      context.fillStyle = '#405765'; font(context, 11); context.fillText(String(basemap.attribution), left + width - 204, top + height - 22);
    }
  }

  function drawTable(context, payload, state) {
    const headers = payload.headers || [], rows = payload.rows || []; if (!headers.length) return;
    const layout = legendLayout(payload.legend), left = layout.left, top = layout.top;
    const columnWidth = Math.floor((layout.right - left) / Math.max(headers.length, 1)), availableHeight = layout.bottom - top;
    const dynamic = Boolean(payload.dynamic), rowDimensionCount = Math.max(0, Number(payload.row_dimension_count) || 0);
    const columnHeading = String(payload.column_heading || ''), headerBands = dynamic && columnHeading ? 2 : 1;
    // Rows share the available height (up to a comfortable maximum) and the
    // text scales with them, so wide placeholders stay legible once the
    // canvas is fitted to its card or PPT placeholder.
    const rowHeight = dynamic
      ? Math.max(8, Math.min(92, Math.floor(availableHeight / Math.max(rows.length + headerBands, 1))))
      : Math.max(8, Math.min(100, Math.floor(availableHeight / Math.max(rows.length + 1, 1))));
    // Text is painted with the smaller of the horizontal and vertical scales;
    // convert its measured width into the table's horizontal logical units.
    const transform = context.getTransform();
    const horizontalScale = Math.max(Math.hypot(transform.a, transform.b), .0001);
    const textWidthRatio = Math.min(horizontalScale, Math.hypot(transform.c, transform.d)) / horizontalScale;
    const textWidth = text => context.measureText(text).width * textWidthRatio;
    // The text size is the smaller of what the row height allows and what
    // lets every heading and value fit its column, so a table reads well in
    // a wide Design card, a PPT placeholder and the expanded chart view.
    // Headings always fit whole; a few exceptionally long values may still
    // be shortened with an ellipsis instead of shrinking the whole table.
    const widestAtSize = (texts, bold, share = 1) => {
      font(context, 100, bold);
      const widths = texts.map(text => textWidth(String(text ?? ''))).sort((a, b) => a - b);
      return Math.max(1, widths[Math.min(widths.length - 1, Math.floor((widths.length - 1) * share))] || 0);
    };
    const columnTextRoom = Math.max(1, columnWidth - 16);
    const widthFit = (texts, bold, share) => Math.floor(100 * columnTextRoom / widestAtSize(texts, bold, share));
    const cellTexts = rows.flatMap(row => row.map(value => value));
    const fontRatio = rowHeight < 30 ? .74 : .58;
    const headerFont = Math.max(8, Math.min(28, Math.round(rowHeight * (fontRatio + .02)), widthFit(headers, true)));
    const cellFont = Math.max(8, Math.min(26, Math.round(rowHeight * fontRatio), widthFit(cellTexts, dynamic, .95)));
    const fitText = (value, maxWidth) => {
      const text = String(value ?? '');
      if (textWidth(text) <= maxWidth) return text;
      let end = text.length;
      while (end > 0 && textWidth(`${text.slice(0, end)}…`) > maxWidth) end -= 1;
      return end ? `${text.slice(0, end)}…` : '';
    };
    const headerTop = top + (headerBands - 1) * rowHeight; context.textBaseline = 'middle';
    state.table = dynamic ? {
      left, top, right: layout.right, bottom: layout.bottom, columnWidth, rowHeight,
      headerTop, headerBands, rowDimensionCount, headerCount: headers.length, rowCount: rows.length,
    } : null;
    if (dynamic && columnHeading) {
      const pivotLeft = left + rowDimensionCount * columnWidth;
      context.fillStyle = '#23384A'; context.fillRect(pivotLeft, top, Math.max(columnWidth, layout.right - pivotLeft), rowHeight);
      const pivotWidth = Math.max(columnWidth, layout.right - pivotLeft);
      context.fillStyle = '#FFFFFF'; context.textAlign = 'center'; font(context, headerFont, true);
      context.fillText(fitText(columnHeading, pivotWidth - 16), pivotLeft + pivotWidth / 2, top + rowHeight / 2);
    }
    headers.forEach((header, column) => {
      const x = left + column * columnWidth; context.fillStyle = '#23384A'; context.fillRect(x, headerTop, columnWidth, rowHeight);
      context.fillStyle = '#FFFFFF'; context.textAlign = 'left'; font(context, headerFont, true);
      context.fillText(fitText(header, columnWidth - 16), x + 8, headerTop + rowHeight / 2);
    });
    rows.forEach((row, rowIndex) => row.forEach((value, column) => {
      const x = left + column * columnWidth, y = top + (rowIndex + headerBands) * rowHeight;
      const repeatedHierarchyValue = dynamic && column < rowDimensionCount && rowIndex > 0
        && Array.from({length: column + 1}, (_item, index) => String(rows[rowIndex - 1]?.[index] ?? '') === String(row[index] ?? '')).every(Boolean);
      const displayValue = repeatedHierarchyValue ? '' : value;
      context.fillStyle = rowIndex % 2 ? '#FFFFFF' : '#F4F7F9'; context.fillRect(x, y, columnWidth, rowHeight);
      context.strokeStyle = '#D9E1E6'; context.lineWidth = 1; context.strokeRect(x, y, columnWidth, rowHeight);
      context.fillStyle = '#34495A'; context.textAlign = column >= rowDimensionCount && dynamic ? 'right' : 'left'; font(context, cellFont, dynamic && column < rowDimensionCount);
      const text = fitText(displayValue, columnWidth - 16); const textX = column >= rowDimensionCount && dynamic ? x + columnWidth - 8 : x + 8;
      context.fillText(text, textX, y + rowHeight / 2);
    }));
    if (dynamic) {
      const tableBottom = top + (rows.length + headerBands) * rowHeight;
      const boundaryStyle = (level, levels) => {
        const relativeDepth = level / Math.max(levels - 1, 1);
        if (level === 0) return {colour: '#607887', width: 4};
        if (relativeDepth <= .5) return {colour: '#8296A3', width: 3};
        return {colour: '#A8B7C0', width: 2};
      };
      for (let rowIndex = 1; rowIndex < rows.length; rowIndex += 1) {
        const previous = rows[rowIndex - 1] || [], current = rows[rowIndex] || [];
        const changedLevel = Array.from({length: rowDimensionCount}, (_item, level) => level)
          .find(level => String(previous[level] ?? '') !== String(current[level] ?? ''));
        if (changedLevel === undefined) continue;
        const style = boundaryStyle(changedLevel, rowDimensionCount);
        const y = top + (rowIndex + headerBands) * rowHeight;
        line(context, left + changedLevel * columnWidth, y, layout.right, y, style.colour, style.width);
      }
      const columnKeys = Array.isArray(payload.column_keys) ? payload.column_keys : [];
      const columnLevels = Math.max(1, columnKeys[0]?.length || 0);
      for (let columnIndex = 1; columnIndex < columnKeys.length; columnIndex += 1) {
        const previous = columnKeys[columnIndex - 1] || [], current = columnKeys[columnIndex] || [];
        let changedLevel = previous.findIndex((value, level) => String(value ?? '') !== String(current[level] ?? ''));
        if (changedLevel < 0) changedLevel = columnLevels - 1;
        const style = boundaryStyle(changedLevel, columnLevels);
        const x = left + (rowDimensionCount + columnIndex) * columnWidth;
        const lineTop = changedLevel === 0 ? top : headerTop;
        line(context, x, lineTop, x, tableBottom, style.colour, style.width);
      }
      if (columnKeys.length) {
        const pivotLeft = left + rowDimensionCount * columnWidth;
        line(context, pivotLeft, top, pivotLeft, tableBottom, '#607887', 4);
      }
    }
    const drag = tableDragStates.get(state.canvas);
    if (dynamic && drag?.targetIndex !== undefined) {
      context.save();
      context.strokeStyle = '#7C4DCC'; context.lineWidth = 5;
      if (drag.mode === 'column') {
        const boundary = drag.targetIndex + (drag.after ? 1 : 0);
        const x = left + boundary * columnWidth;
        context.beginPath(); context.moveTo(x, headerTop); context.lineTo(x, top + (rows.length + headerBands) * rowHeight); context.stroke();
      } else {
        const boundary = drag.targetBoundary;
        const y = top + (headerBands + boundary) * rowHeight;
        context.beginPath(); context.moveTo(left, y); context.lineTo(layout.right, y); context.stroke();
      }
      context.restore();
    }
    drawLegend(context, payload.legend);
  }

  function drawPayload(context, payload, state, transform) {
    if (payload?.spacer) return;
    const previousLegendTarget = legendHitTarget;
    legendHitTarget = {state, transform};
    try { drawPayloadContent(context, payload, state, transform); } finally { legendHitTarget = previousLegendTarget; }
  }

  function drawPayloadContent(context, payload, state, transform) {
    // Small grid cells show their title outside the chart at a readable size.
    if (!payload?.hide_title) drawTitle(context, payload?.title || '');
    if (!payload || payload.type === 'empty') {
      context.fillStyle = '#61727D'; context.textAlign = 'left'; context.textBaseline = 'top'; font(context, 24);
      context.fillText(payload?.message || 'No chart data available', 50, 440); return;
    }
    if (payload.type === 'status_100') drawStatus(context, payload, state, transform);
    else if (payload.type === 'failure_count') drawFailure(context, payload, state, transform);
    else if (payload.type === 'distribution') drawDistribution(context, payload, state, transform);
    else if (payload.type === 'cdf') drawCdf(context, payload, state, transform);
    else if (payload.type === 'multi_cdf') drawMultiCdf(context, payload, state, transform);
    else if (payload.type === 'mean_bar') drawMeanBars(context, payload, state, transform);
    else if (payload.type === 'scatter') drawScatter(context, payload, state, transform);
    else if (payload.type === 'map') drawMap(context, payload, state, transform);
    else if (payload.type === 'table') drawTable(context, payload, state);
    else if (payload.type === 'kpi') drawKpi(context, payload, state, transform);
  }

  // KPI cards (Designer): the figure of the latest campaign, its samples, its change against the comparison
  // (green when it improves, red when it worsens), the colour of its band and its trend over the campaigns.
  const KPI_BANDS = {good: '#237A4B', fair: '#B25F00', poor: '#B3262E'};
  function roundedRect(context, x, y, width, height, radius) {
    context.beginPath();
    context.moveTo(x + radius, y); context.lineTo(x + width - radius, y); context.quadraticCurveTo(x + width, y, x + width, y + radius);
    context.lineTo(x + width, y + height - radius); context.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
    context.lineTo(x + radius, y + height); context.quadraticCurveTo(x, y + height, x, y + height - radius);
    context.lineTo(x, y + radius); context.quadraticCurveTo(x, y, x + radius, y); context.closePath();
  }
  function drawKpi(context, payload, state, transform) {
    const cards = payload.cards || [];
    // A missing figure (null) is not a zero.
    const known = value => value !== null && value !== undefined && value !== '' && finite(value);
    if (!cards.length) return;
    const columns = cards.length <= 4 ? cards.length : cards.length <= 6 ? 3 : 4;
    const rows = Math.ceil(cards.length / columns);
    const area = {left: 40, top: payload.hide_title ? 30 : 95, right: 1560, bottom: 875};
    const gap = 26;
    const width = (area.right - area.left - gap * (columns - 1)) / columns;
    const height = (area.bottom - area.top - gap * (rows - 1)) / rows;
    const decimals = Number.isInteger(payload.decimals) ? payload.decimals : 2;
    const unit = payload.unit ? (payload.share ? '%' : ` ${payload.unit}`) : '';
    const number = value => (known(value) ? Number(value).toFixed(decimals) : '–');
    // A field name read as words (Mean_Data_Rate: Mean Data Rate).
    const readable = text => String(text || '').replace(/_+/g, ' ').trim();
    cards.forEach((card, index) => {
      const x = area.left + (index % columns) * (width + gap), y = area.top + Math.floor(index / columns) * (height + gap);
      const accent = KPI_BANDS[card.band] || '#5B35A0';
      const scale = Math.min(1.25, height / 340, width / 420);
      context.save();
      context.shadowColor = 'rgba(36, 22, 61, 0.10)'; context.shadowBlur = 18 * scale; context.shadowOffsetY = 4 * scale;
      roundedRect(context, x, y, width, height, 22 * scale);
      context.fillStyle = '#FFFFFF'; context.fill();
      context.restore();
      context.save();
      roundedRect(context, x, y, width, height, 22 * scale);
      context.strokeStyle = '#E4DDEE'; context.lineWidth = 2; context.stroke();
      context.restore();
      // Wide cards keep the figures at the left and the trend at the right; tall ones stack them.
      const trend = (card.trend || []).map(value => (known(value) ? Number(value) : null));
      const hasTrend = trend.filter(known).length > 1;
      const wide = hasTrend && width / height > 1.55;
      const pad = 34 * scale;
      const text = {left: x + pad, right: wide ? x + width * .52 : x + width - pad};
      let line = y + pad;
      context.textAlign = 'left'; context.textBaseline = 'top';
      context.fillStyle = accent; context.beginPath(); context.arc(text.left + 7 * scale, line + 13 * scale, 7 * scale, 0, Math.PI * 2); context.fill();
      context.fillStyle = '#5E5470'; font(context, Math.max(16, 26 * scale), true);
      context.fillText(fittedText(context, readable(card.label || payload.metric), text.right - text.left - 24 * scale), text.left + 24 * scale, line);
      line += 46 * scale;
      const valueText = `${number(card.value)}${known(card.value) ? unit : ''}`;
      let size = Math.max(36, Math.min(150 * scale, height * (wide ? .36 : .3), (text.right - text.left) / Math.max(3, valueText.length * .6)));
      context.fillStyle = card.band ? accent : '#1D1530'; font(context, size, true);
      while (size > 28 && textWidth(context, valueText) > text.right - text.left) { size -= 4; font(context, size, true); }
      context.fillText(valueText, text.left, line);
      pushRectangleHit(state, transform, {x, y, width, height}, {label: readable(card.label || payload.metric), series: card.campaign || '', value: `${valueText} · n = ${card.n}`});
      line += size + 16 * scale;
      if (known(card.delta)) {
        const up = Number(card.delta) > 0, flat = card.improves === null || card.improves === undefined;
        const tone = flat ? {fill: '#EEF0F3', ink: '#5B6876'} : card.improves ? {fill: '#E3F3EA', ink: '#1E6B42'} : {fill: '#FBE6E7', ink: '#9E2230'};
        const deltaUnit = payload.share ? ' pp' : unit;
        const deltaText = `${up ? '▲' : Number(card.delta) < 0 ? '▼' : '='} ${up ? '+' : ''}${Number(card.delta).toFixed(decimals)}${deltaUnit}`;
        const versus = card.comparison_label ? `vs ${card.comparison_label}` : '';
        font(context, Math.max(15, 22 * scale), true);
        const pillWidth = textWidth(context, deltaText) + 28 * scale, pillHeight = 36 * scale;
        roundedRect(context, text.left, line, pillWidth, pillHeight, pillHeight / 2);
        context.fillStyle = tone.fill; context.fill();
        context.fillStyle = tone.ink; context.textBaseline = 'middle';
        context.fillText(deltaText, text.left + 14 * scale, line + pillHeight / 2);
        if (versus) {
          context.fillStyle = '#7A6F8A'; font(context, Math.max(14, 20 * scale));
          context.fillText(fittedText(context, versus, Math.max(0, text.right - text.left - pillWidth - 12 * scale)), text.left + pillWidth + 12 * scale, line + pillHeight / 2);
        }
        context.textBaseline = 'top';
        line += pillHeight + 14 * scale;
      }
      context.fillStyle = '#8A8098'; font(context, Math.max(14, 19 * scale));
      context.fillText(`n = ${Number(card.n || 0).toLocaleString()}${card.campaign ? ` · ${card.campaign}` : ''}`, text.left, line);
      line += 30 * scale;
      if (!hasTrend) return;
      // The trend over the campaigns: an area under its line, its points and the campaigns at its ends.
      const box = wide
        ? {left: x + width * .58, right: x + width - pad, top: y + pad + 30 * scale, bottom: y + height - pad - 26 * scale}
        : {left: x + pad, right: x + width - pad, top: Math.max(line + 10 * scale, y + height * .62), bottom: y + height - pad - 22 * scale};
      if (box.bottom - box.top < 24) return;
      // The scale of the trend spans at least a fifth of its level: a small change looks small.
      const values = trend.filter(known), middle = (Math.min(...values) + Math.max(...values)) / 2;
      const span = Math.max(Math.max(...values) - Math.min(...values), Math.abs(middle) * .2, 1e-9);
      const low = middle - span / 2;
      const points = trend.map((value, position) => (known(value) ? {
        x: box.left + position / Math.max(1, trend.length - 1) * (box.right - box.left),
        y: box.bottom - (value - low) / span * (box.bottom - box.top),
      } : null)).filter(Boolean);
      const gradient = context.createLinearGradient(0, box.top, 0, box.bottom);
      gradient.addColorStop(0, withAlpha(accent, .22)); gradient.addColorStop(1, withAlpha(accent, 0));
      context.beginPath();
      points.forEach((point, position) => (position ? context.lineTo(point.x, point.y) : context.moveTo(point.x, point.y)));
      context.lineTo(points.at(-1).x, box.bottom); context.lineTo(points[0].x, box.bottom); context.closePath();
      context.fillStyle = gradient; context.fill();
      context.strokeStyle = accent; context.lineWidth = 4 * Math.max(.75, scale); context.lineJoin = 'round'; context.lineCap = 'round'; context.beginPath();
      points.forEach((point, position) => (position ? context.lineTo(point.x, point.y) : context.moveTo(point.x, point.y)));
      context.stroke();
      points.forEach((point, position) => {
        const last = position === points.length - 1;
        context.beginPath(); context.arc(point.x, point.y, (last ? 8 : 4.5) * Math.max(.75, scale), 0, Math.PI * 2);
        context.fillStyle = last ? accent : '#FFFFFF'; context.fill();
        context.strokeStyle = accent; context.lineWidth = 2.5; context.stroke();
      });
      const labels = card.trend_labels || [];
      if (labels.length > 1) {
        context.fillStyle = '#8A8098'; font(context, Math.max(13, 17 * scale)); context.textBaseline = 'top';
        context.textAlign = 'left'; context.fillText(String(labels[0]), box.left, box.bottom + 8 * scale);
        context.textAlign = 'right'; context.fillText(String(labels.at(-1)), box.right, box.bottom + 8 * scale);
        context.textAlign = 'left';
      }
    });
  }

  // The colour theme of a chart (its model's style, or the page's: scoring_themes.canvas_chart_style): its font and
  // its colours instead of the renderer's greys. Series, operator, vendor and threshold colours stay as they are.
  const styledContexts = new WeakMap();
  const renderedCanvases = new Set();
  function applyStyle(context, style) {
    let styled = styledContexts.get(context);
    if (!styled) {
      styled = {style: null};
      const descriptor = name => {
        for (let proto = Object.getPrototypeOf(context); proto; proto = Object.getPrototypeOf(proto)) {
          const found = Object.getOwnPropertyDescriptor(proto, name);
          if (found) return found;
        }
        return null;
      };
      const translate = value => {
        const style = styled.style;
        if (!style || typeof value !== 'string') return value;
        const key = value.toUpperCase();
        // A dark theme paints the white of the canvas, its panels and separators in its background.
        if (style.background && (key === '#FFFFFF' || key === '#FFF')) return style.background;
        return style.colours?.[key] || value;
      };
      ['fillStyle', 'strokeStyle'].forEach(name => {
        const base = descriptor(name);
        if (!base?.set) return;
        if (name === 'fillStyle') styled.setFill = value => base.set.call(context, value);
        Object.defineProperty(context, name, {
          configurable: true, get() { return base.get.call(context); },
          set(value) { if (name === 'fillStyle') styled.rawFill = value; base.set.call(context, translate(value)); },
        });
      });
      const fontBase = descriptor('font');
      if (fontBase?.set) {
        Object.defineProperty(context, 'font', {
          configurable: true, get() { return fontBase.get.call(context); },
          set(value) {
            const family = styled.style?.font;
            fontBase.set.call(context, family ? String(value).replace(FONT_FAMILY, family) : value);
          },
        });
      }
      styledContexts.set(context, styled);
    }
    styled.style = style && typeof style === 'object' ? style : null;
    if (styled.style?.background) {
      // White text (on headers and bars) stays white on a dark background.
      const drawText = context.fillText;
      context.fillText = (...args) => {
        const raw = String(styled.rawFill || '').toUpperCase();
        if (raw !== '#FFFFFF' && raw !== '#FFF') { drawText(...args); return; }
        const current = context.fillStyle;
        styled.setFill?.('#FFFFFF'); drawText(...args); styled.setFill?.(current);
      };
    }
  }

  // A colour as #RRGGBBAA with an opacity (the series of a Design drawn lighter).
  function withAlpha(colour, opacity) {
    const value = String(colour || '').trim();
    const hex = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(value)?.[1];
    if (!hex) return value;
    const full = hex.length === 3 ? hex.split('').map(digit => digit + digit).join('') : hex;
    return `#${full}${Math.round(clamp(opacity, 0, 1) * 255).toString(16).padStart(2, '0')}`.toUpperCase();
  }
  const DASHES = {dashed: [10, 6], dotted: [2, 5], solid: []};
  // The format the Designer gives a chart (the style of its template row, see design_slides) over its model:
  // the colour of a series replaced wherever it is drawn (bars, lines, points and legend), its line width and dash, the
  // place and size of the legend, the place and text of the labels, the axis titles and decimals, and the title. The PPT
  // export draws the same model with this renderer, so it shows the same format.
  function formattedPayload(payload) {
    const format = payload?.format_overrides;
    if (!format || typeof format !== 'object' || payload?.type === 'empty') return {payload, colours: null};
    const copy = structuredClone(payload);
    const colours = {};
    const items = copy.legend?.items || [];
    const named = name => (copy.series || []).filter(entry => String(entry.name ?? entry.legend_name ?? '') === name);
    for (const [name, series] of Object.entries(format.series || {})) {
      if (!series || typeof series !== 'object') continue;
      const item = items.find(entry => String(entry.label) === name);
      const original = item?.colour || named(name)[0]?.colour;
      let colour = series.colour || original;
      if (colour && Number.isFinite(Number(series.opacity)) && Number(series.opacity) < 1) colour = withAlpha(colour, Number(series.opacity));
      if (original && colour && String(colour).toUpperCase() !== String(original).toUpperCase()) colours[String(original).toUpperCase()] = colour;
      for (const entry of [...named(name), ...(item ? [item] : [])]) {
        if (Number(series.width) > 0) entry.width = Number(series.width);
        if (series.dash && DASHES[series.dash]) entry.dash = DASHES[series.dash];
      }
    }
    if (copy.legend && format.legend?.position) copy.legend.position = format.legend.position;
    // The text of the legend: its size and colour, bold as it is drawn by default unless turned off.
    if (copy.legend && format.legend && (format.legend.size || format.legend.colour || format.legend.bold === false)) {
      copy.legend.format = {...(copy.legend.format || {}), configured: true, bold: format.legend.bold !== false,
        ...(format.legend.size ? {size: format.legend.size} : {}), ...(format.legend.colour ? {color: format.legend.colour} : {})};
    }
    if (format.labels && typeof format.labels === 'object') {
      if (format.labels.position) copy.label_position = format.labels.position;
      const label = {...(copy.label_format || {})};
      if (format.labels.colour) label.color = format.labels.colour;
      if (format.labels.size) label.size = format.labels.size;
      if (format.labels.bold !== undefined) label.bold = Boolean(format.labels.bold);
      if (Object.keys(label).length) copy.label_format = {...label, configured: true};
    }
    const xTitle = format.axes?.x?.title, yTitle = format.axes?.y?.title;
    if (xTitle) { if (['cdf', 'multi_cdf'].includes(copy.type)) copy.metric = xTitle; else copy.x_label = xTitle; }
    if (yTitle) { if (copy.type === 'mean_bar') copy.metric = yTitle; else copy.y_label = yTitle; }
    if (Number.isInteger(format.axes?.x?.decimals)) copy.x_decimals = format.axes.x.decimals;
    if (Number.isInteger(format.axes?.y?.decimals)) copy.y_decimals = format.axes.y.decimals;
    if (format.title) copy.title = format.title;
    return {payload: copy, colours: Object.keys(colours).length ? colours : null};
  }

  function draw(canvas, payload) {
    const context = prepareCanvas(canvas), state = {canvas, hits: []};
    const formatted = formattedPayload(payload);
    payload = formatted.payload;
    const theme = payload?.style || globalThis.canvasChartStyle || null;
    applyStyle(context, formatted.colours ? {...(theme || {}), colours: {...(theme?.colours || {}), ...formatted.colours}} : theme);
    renderedCanvases.add(canvas);
    context.fillStyle = '#FFFFFF'; context.fillRect(0, 0, LOGICAL_WIDTH, LOGICAL_HEIGHT);
    const visible = legendHiddenPayload(payload, hiddenLegendItems.get(canvas));
    state.drawnPayload = visible;
    drawPayload(context, visible, state, {x: 0, y: 0, scale: 1}); renderStates.set(canvas, state);
    const view = views.get(canvas);
    const titleHeight = 40 * Math.min(view?.scaleX || 1, view?.scaleY || 1) * (view?.zoom || 1);
    canvas.dispatchEvent(new CustomEvent('designchartlayout', {detail: {titleTop: 20, titleHeight}}));
  }

  function closestHit(hits, x, y) {
    let closest = null, distance = Infinity;
    for (const hit of hits) {
      if (hit.kind === 'rectangle') { if (x >= hit.x && x <= hit.x + hit.width && y >= hit.y && y <= hit.y + hit.height) return {...hit, distance: 0}; continue; }
      if (hit.kind === 'point') { const candidate = Math.hypot(x - hit.x, y - hit.y); if (candidate < distance) { closest = hit; distance = candidate; } continue; }
      if (hit.kind === 'line') {
        for (const point of hit.points) { const candidate = Math.hypot(x - point.x, y - point.y); if (candidate < distance) { closest = {...hit, point}; distance = candidate; } }
      }
    }
    return closest && distance <= 22 ? {...closest, distance} : null;
  }

  function tooltipFor(canvas) {
    let tooltip = canvas.parentElement?.querySelector(':scope > .ds-live-chart-tooltip');
    if (!tooltip && canvas.parentElement) { tooltip = document.createElement('div'); tooltip.className = 'ds-live-chart-tooltip'; tooltip.hidden = true; canvas.parentElement.append(tooltip); }
    return tooltip;
  }

  function attachTooltip(canvas) {
    if (canvas.dataset.tooltipReady) return; canvas.dataset.tooltipReady = 'true';
    canvas.addEventListener('pointermove', event => {
      const view = views.get(canvas), state = renderStates.get(canvas), tooltip = tooltipFor(canvas); if (!view || !state || !tooltip) return;
      if (canvas.classList.contains('is-panning') || canvas.classList.contains('is-selecting')) { tooltip.hidden = true; return; }
      const bounds = canvas.getBoundingClientRect();
      const x = ((event.clientX - bounds.left) / view.scaleX - view.originX) / view.zoom;
      const y = ((event.clientY - bounds.top) / view.scaleY - view.originY) / view.zoom;
      const hit = closestHit(state.hits, x, y); if (!hit) { tooltip.hidden = true; return; }
      const point = hit.point, lines = [hit.label, hit.series, hit.value || (point ? numericLabel(point.value) : '')].filter(Boolean);
      if (point && finite(point.cumulative)) lines.push(tooltipPercent(point.cumulative));
      tooltip.replaceChildren(...lines.map((value, index) => { const element = document.createElement(index === 0 ? 'strong' : 'span'); element.textContent = value; return element; }));
      tooltip.hidden = false;
      const parentBounds = canvas.parentElement.getBoundingClientRect(), left = event.clientX - parentBounds.left + 14, top = event.clientY - parentBounds.top + 14;
      tooltip.style.left = `${clamp(left, 8, Math.max(8, parentBounds.width - tooltip.offsetWidth - 8))}px`;
      tooltip.style.top = `${clamp(top, 8, Math.max(8, parentBounds.height - tooltip.offsetHeight - 8))}px`;
    });
    canvas.addEventListener('pointerleave', () => { const tooltip = tooltipFor(canvas); if (tooltip) tooltip.hidden = true; });
  }

  function tableLogicalPoint(canvas, event) {
    const view = views.get(canvas), bounds = canvas.getBoundingClientRect();
    if (!view) return null;
    return {
      x: ((event.clientX - bounds.left) / view.scaleX - view.originX) / view.zoom,
      y: ((event.clientY - bounds.top) / view.scaleY - view.originY) / view.zoom,
    };
  }

  function tableCellAt(canvas, event) {
    const state = renderStates.get(canvas), table = state?.table, point = tableLogicalPoint(canvas, event);
    if (!table || !point || point.x < table.left || point.x >= table.right) return null;
    const column = Math.max(0, Math.min(table.headerCount - 1, Math.floor((point.x - table.left) / table.columnWidth)));
    if (point.y >= table.headerTop && point.y < table.headerTop + table.rowHeight) return {kind: 'header', column, point, table};
    const bodyTop = table.top + table.headerBands * table.rowHeight;
    if (point.y < bodyTop || point.y >= bodyTop + table.rowCount * table.rowHeight) return null;
    return {
      kind: 'row', column,
      row: Math.max(0, Math.min(table.rowCount - 1, Math.floor((point.y - bodyTop) / table.rowHeight))),
      point, table,
    };
  }

  function hierarchyRange(rows, rowIndex, depth) {
    const prefix = rows[rowIndex].slice(0, depth + 1).map(String);
    const matches = row => prefix.every((value, index) => String(row[index]) === value);
    let start = rowIndex, end = rowIndex + 1;
    while (start > 0 && matches(rows[start - 1])) start -= 1;
    while (end < rows.length && matches(rows[end])) end += 1;
    return {start, end};
  }

  function moveArrayItem(values, from, to) {
    const [item] = values.splice(from, 1);
    values.splice(to > from ? to - 1 : to, 0, item);
  }

  function sameImmediateHierarchyParent(left, right) {
    const leftKey = Array.isArray(left) ? left.map(String) : [];
    const rightKey = Array.isArray(right) ? right.map(String) : [];
    const parentDepth = Math.max(0, Math.min(leftKey.length, rightKey.length) - 1);
    return Array.from({length: parentDepth}, (_item, index) => leftKey[index] === rightKey[index]).every(Boolean);
  }

  function attachTableReordering(canvas) {
    if (canvas.dataset.tableReorderReady) return;
    canvas.dataset.tableReorderReady = 'true';
    let drag = null;
    const stopEvent = event => { event.preventDefault(); event.stopImmediatePropagation(); };
    canvas.addEventListener('pointerdown', event => {
      if (event.button !== 0 || cameraFor(canvas).zoom !== 1) return;
      const payload = models.get(canvas), cell = tableCellAt(canvas, event);
      if (!payload?.dynamic || !cell) return;
      if (cell.kind === 'header' && cell.column >= cell.table.rowDimensionCount) {
        const sourceKeyIndex = cell.column - cell.table.rowDimensionCount;
        drag = {
          mode: 'column', pointerId: event.pointerId, sourceIndex: cell.column,
          sourceKeyIndex, sourceKey: payload.column_keys?.[sourceKeyIndex] || [],
          targetIndex: cell.column, after: false,
        };
      } else if (cell.kind === 'row') {
        const depth = Math.min(cell.column, Math.max(0, cell.table.rowDimensionCount - 1));
        const source = hierarchyRange(payload.rows, cell.row, depth);
        const parent = depth > 0 ? hierarchyRange(payload.rows, cell.row, depth - 1) : {start: 0, end: payload.rows.length};
        drag = {mode: 'row', pointerId: event.pointerId, depth, source, parent, targetIndex: cell.row, targetBoundary: source.start};
      } else return;
      tableDragStates.set(canvas, drag);
      canvas.classList.add('is-table-reordering');
      canvas.style.cursor = 'grabbing';
      canvas.setPointerCapture?.(event.pointerId);
      const tooltip = tooltipFor(canvas); if (tooltip) tooltip.hidden = true;
      stopEvent(event);
    });
    canvas.addEventListener('pointermove', event => {
      if (!drag) {
        const payload = models.get(canvas), cell = tableCellAt(canvas, event);
        const draggable = payload?.dynamic && cell && (cell.kind === 'row' || cell.column >= cell.table.rowDimensionCount);
        canvas.style.cursor = draggable ? 'grab' : '';
        return;
      }
      if (event.pointerId !== drag.pointerId) return;
      const payload = models.get(canvas), cell = tableCellAt(canvas, event);
      if (!payload?.dynamic || !cell) { stopEvent(event); return; }
      if (drag.mode === 'column' && cell.kind === 'header' && cell.column >= cell.table.rowDimensionCount) {
        const targetKey = payload.column_keys?.[cell.column - cell.table.rowDimensionCount] || [];
        if (sameImmediateHierarchyParent(drag.sourceKey, targetKey)) {
          drag.targetIndex = cell.column;
          const cellLeft = cell.table.left + cell.column * cell.table.columnWidth;
          drag.after = cell.point.x >= cellLeft + cell.table.columnWidth / 2;
        }
      } else if (drag.mode === 'row' && cell.kind === 'row') {
        if (cell.row >= drag.parent.start && cell.row < drag.parent.end) {
          drag.targetIndex = cell.row;
          const target = hierarchyRange(payload.rows, cell.row, drag.depth);
          const bodyTop = cell.table.top + cell.table.headerBands * cell.table.rowHeight;
          const after = cell.point.y >= bodyTop + cell.row * cell.table.rowHeight + cell.table.rowHeight / 2;
          drag.targetBoundary = after ? Math.min(target.end, drag.parent.end) : Math.max(target.start, drag.parent.start);
        }
      }
      draw(canvas, payload);
      stopEvent(event);
    });
    const finish = event => {
      if (!drag || event.pointerId !== drag.pointerId) return;
      const payload = models.get(canvas), completed = drag;
      drag = null;
      tableDragStates.delete(canvas);
      canvas.releasePointerCapture?.(event.pointerId);
      canvas.classList.remove('is-table-reordering');
      canvas.style.cursor = '';
      if (event.type === 'pointerup' && payload?.dynamic) {
        if (completed.mode === 'column') {
          const destination = completed.targetIndex + (completed.after ? 1 : 0);
          if (destination !== completed.sourceIndex && destination !== completed.sourceIndex + 1) {
            moveArrayItem(payload.headers, completed.sourceIndex, destination);
            payload.rows.forEach(row => moveArrayItem(row, completed.sourceIndex, destination));
            if (Array.isArray(payload.column_keys) && payload.column_keys.length) {
              moveArrayItem(payload.column_keys, completed.sourceKeyIndex, destination - completed.sourceIndex + completed.sourceKeyIndex);
            }
          }
        } else {
          const insideSource = completed.targetBoundary >= completed.source.start
            && completed.targetBoundary <= completed.source.end;
          if (!insideSource) {
            const moved = payload.rows.splice(completed.source.start, completed.source.end - completed.source.start);
            let destination = completed.targetBoundary;
            if (destination > completed.source.start) destination -= moved.length;
            payload.rows.splice(Math.max(0, destination), 0, ...moved);
          }
        }
        canvas.dispatchEvent(new CustomEvent('designtableorderchange', {detail: {
          headers: [...payload.headers], rows: payload.rows.map(row => [...row]),
        }}));
      }
      draw(canvas, payload);
      stopEvent(event);
    };
    canvas.addEventListener('pointerup', finish);
    canvas.addEventListener('pointercancel', finish);
    canvas.addEventListener('pointerleave', () => { if (!drag) canvas.style.cursor = ''; });
  }

  function setChartZoom(canvas, requestedZoom) {
    const camera = cameraFor(canvas);
    camera.zoom = requestedZoom;
    constrainCamera(camera);
    canvas.classList.toggle('ds-chart-zoomed', camera.zoom > 1);
    if (camera.zoom > 1) canvas.classList.remove('ds-chart-selection-blocked');
    const payload = models.get(canvas);
    if (payload) draw(canvas, payload);
    canvas.dispatchEvent(new CustomEvent('designchartzoom', {detail: {zoom: camera.zoom}}));
    return camera.zoom;
  }

  // Zoom keeping the point under the pointer in its place (Ctrl/Cmd+wheel in the viewer of PPT Designer).
  function zoomChartAt(canvas, requestedZoom, clientX, clientY) {
    const camera = constrainCamera(cameraFor(canvas)), bounds = canvas.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return setChartZoom(canvas, requestedZoom);
    const screenX = (clientX - bounds.left) / bounds.width * LOGICAL_WIDTH, screenY = (clientY - bounds.top) / bounds.height * LOGICAL_HEIGHT;
    const pointX = (screenX - (1 - camera.zoom) * LOGICAL_WIDTH / 2 - camera.panX) / camera.zoom;
    const pointY = (screenY - (1 - camera.zoom) * LOGICAL_HEIGHT / 2 - camera.panY) / camera.zoom;
    const zoom = clamp(Number(requestedZoom) || 1, 1, 4);
    camera.panX = screenX - zoom * pointX - (1 - zoom) * LOGICAL_WIDTH / 2;
    camera.panY = screenY - zoom * pointY - (1 - zoom) * LOGICAL_HEIGHT / 2;
    return setChartZoom(canvas, zoom);
  }

  function chartPanState(canvas) {
    const camera = constrainCamera(cameraFor(canvas));
    const maximumX = LOGICAL_WIDTH * (camera.zoom - 1) / 2;
    const maximumY = LOGICAL_HEIGHT * (camera.zoom - 1) / 2;
    return {
      zoom: camera.zoom,
      canPanLeft: camera.zoom > 1 && camera.panX < maximumX - 0.5,
      canPanRight: camera.zoom > 1 && camera.panX > -maximumX + 0.5,
      canPanUp: camera.zoom > 1 && camera.panY < maximumY - 0.5,
      canPanDown: camera.zoom > 1 && camera.panY > -maximumY + 0.5,
    };
  }

  function panChart(canvas, direction) {
    const camera = cameraFor(canvas);
    if (camera.zoom <= 1 || !['left', 'right', 'up', 'down'].includes(direction)) return chartPanState(canvas);
    if (direction === 'left') camera.panX += LOGICAL_WIDTH * 0.16;
    if (direction === 'right') camera.panX -= LOGICAL_WIDTH * 0.16;
    if (direction === 'up') camera.panY += LOGICAL_HEIGHT * 0.16;
    if (direction === 'down') camera.panY -= LOGICAL_HEIGHT * 0.16;
    constrainCamera(camera);
    const payload = models.get(canvas);
    if (payload) draw(canvas, payload);
    const state = chartPanState(canvas);
    canvas.dispatchEvent(new CustomEvent('designchartpan', {detail: state}));
    return state;
  }

  function selectionOverlayFor(canvas) {
    let overlay = canvas.parentElement?.querySelector(':scope > .ds-chart-zoom-selection');
    if (!overlay && canvas.parentElement) {
      overlay = document.createElement('div');
      overlay.className = 'ds-chart-zoom-selection';
      overlay.hidden = true;
      canvas.parentElement.append(overlay);
    }
    return overlay;
  }

  function zoomToSelection(canvas, selection) {
    const bounds = canvas.getBoundingClientRect();
    const left = clamp(Math.min(selection.startX, selection.endX) - bounds.left, 0, bounds.width);
    const top = clamp(Math.min(selection.startY, selection.endY) - bounds.top, 0, bounds.height);
    const right = clamp(Math.max(selection.startX, selection.endX) - bounds.left, 0, bounds.width);
    const bottom = clamp(Math.max(selection.startY, selection.endY) - bounds.top, 0, bounds.height);
    const width = right - left;
    const height = bottom - top;
    if (width < 12 || height < 12) return;
    const selectedWidth = width / bounds.width * LOGICAL_WIDTH;
    const selectedHeight = height / bounds.height * LOGICAL_HEIGHT;
    const zoom = Math.min(4, LOGICAL_WIDTH / selectedWidth, LOGICAL_HEIGHT / selectedHeight);
    if (zoom <= 1) return;
    const centreX = (left + width / 2) / bounds.width * LOGICAL_WIDTH;
    const centreY = (top + height / 2) / bounds.height * LOGICAL_HEIGHT;
    const camera = cameraFor(canvas);
    camera.zoom = zoom;
    camera.panX = zoom * (LOGICAL_WIDTH / 2 - centreX);
    camera.panY = zoom * (LOGICAL_HEIGHT / 2 - centreY);
    constrainCamera(camera);
    canvas.classList.toggle('ds-chart-zoomed', camera.zoom > 1);
    if (camera.zoom > 1) canvas.classList.remove('ds-chart-selection-blocked');
    const payload = models.get(canvas);
    if (payload) draw(canvas, payload);
    canvas.dispatchEvent(new CustomEvent('designchartzoom', {detail: {zoom: camera.zoom}}));
  }

  function legendItemAt(canvas, event) {
    const view = views.get(canvas), state = renderStates.get(canvas), bounds = canvas.getBoundingClientRect();
    if (!view || !state?.legendHits?.length || !bounds.width) return null;
    const x = ((event.clientX - bounds.left) / view.scaleX - view.originX) / view.zoom;
    const y = ((event.clientY - bounds.top) / view.scaleY - view.originY) / view.zoom;
    return state.legendHits.find(hit => x >= hit.x && x <= hit.x + hit.width && y >= hit.y && y <= hit.y + hit.height) || null;
  }

  const legendLabels = canvas => [...new Set((renderStates.get(canvas)?.legendHits || []).map(hit => hit.label))];
  const hiddenLegendLabels = canvas => {
    const {labelHidden} = legendStateMatchers(hiddenLegendItems.get(canvas));
    return legendLabels(canvas).filter(labelHidden);
  };

  function setHiddenLegendItems(canvas, hidden, shown = []) {
    hiddenLegendItems.set(canvas, {hidden: new Set((hidden || []).map(String)), shown: new Set((shown || []).map(String))});
    const payload = models.get(canvas); if (payload) draw(canvas, payload);
  }

  function axisItemAt(canvas, event) {
    const view = views.get(canvas), state = renderStates.get(canvas), bounds = canvas.getBoundingClientRect();
    if (!view || !bounds.width) return null;
    const x = ((event.clientX - bounds.left) / view.scaleX - view.originX) / view.zoom;
    const y = ((event.clientY - bounds.top) / view.scaleY - view.originY) / view.zoom;
    const hit = (state?.axisHits || []).find(item => x >= item.x && x <= item.x + item.width && y >= item.y && y <= item.y + item.height);
    if (hit) return hit;
    // Table headers and row labels are aggregation values too.
    const cell = tableCellAt(canvas, event), drawn = state?.drawnPayload;
    if (!cell || !drawn) return null;
    const rowDimensions = Math.max(1, Number(drawn.row_dimension_count) || 1);
    if (cell.kind === 'header' && cell.column >= rowDimensions) return {axis: 'table-column', level: 0, value: String(drawn.headers?.[cell.column] ?? '')};
    if (cell.kind === 'row' && cell.column < rowDimensions) return {axis: 'table-row', level: cell.column, value: String(drawn.rows?.[cell.row]?.[cell.column] ?? '')};
    return null;
  }

  // Every value of one axis level in the complete model, hidden ones included,
  // so Keep only, Hide All and Show All cover the whole level.
  function axisLevelValues(payload, axis, level) {
    const unique = values => [...new Set(values.map(value => String(value ?? '')).filter(value => value && value !== '(all)'))];
    if (!payload) return [];
    if (axis === 'row') return unique((payload.row_keys || []).map(key => key?.[level]));
    if (axis === 'table-row') return unique((payload.rows || []).map(row => row?.[level]));
    if (axis === 'table-column') return unique((payload.headers || []).slice(Math.max(1, Number(payload.row_dimension_count) || 1)));
    if (Array.isArray(payload.column_keys)) return unique(payload.column_keys.map(key => key?.[level]));
    if (Array.isArray(payload.keys)) return unique(payload.keys.map(key => key?.[level]));
    if (Array.isArray(payload.categories)) return unique(payload.categories);
    return unique((payload.bars || []).map(bar => bar.key?.[level]));
  }

  function attachLegendToggle(canvas) {
    if (canvas.dataset.legendToggleReady) return; canvas.dataset.legendToggleReady = 'true';
    canvas.addEventListener('click', event => {
      const hit = legendItemAt(canvas, event); if (!hit) return;
      event.preventDefault(); event.stopPropagation();
      const current = hiddenLegendItems.get(canvas) || emptyLegendState();
      const hidden = new Set(current.hidden), shown = new Set(current.shown);
      const wasHidden = legendStateMatchers(current).labelHidden(hit.label);
      if (wasHidden) {
        hidden.delete(hit.label);
        // Shown explicitly when another level of it remains hidden.
        if (legendStateMatchers({hidden, shown}).labelHidden(hit.label)) shown.add(hit.label);
      } else {
        shown.delete(hit.label);
        hidden.add(hit.label);
      }
      setHiddenLegendItems(canvas, [...hidden], [...shown]);
      canvas.dispatchEvent(new CustomEvent('designchartlegend', {detail: {
        label: hit.label, labelHidden: !wasHidden, labels: legendLabels(canvas), hiddenLabels: hiddenLegendLabels(canvas),
      }}));
    });
    // Hosts that offer legend actions (Keep only, Exclude...) opt in with
    // data-legend-menu; elsewhere the browser keeps its own context menu.
    canvas.addEventListener('contextmenu', event => {
      if (canvas.dataset.legendMenu !== 'true') return;
      const hit = legendItemAt(canvas, event), axis = hit ? null : axisItemAt(canvas, event);
      if (!hit && !axis?.value) return;
      event.preventDefault(); event.stopPropagation();
      const {labelHidden} = legendStateMatchers(hiddenLegendItems.get(canvas));
      const label = hit ? hit.label : axis.value;
      const labels = hit ? legendLabels(canvas) : axisLevelValues(models.get(canvas), axis.axis, axis.level);
      const hiddenLabels = labels.filter(labelHidden);
      canvas.dispatchEvent(new CustomEvent('designchartlegendmenu', {detail: {
        label, labelHidden: labelHidden(label), labels, hiddenLabels, axis: axis?.axis || 'legend', level: axis?.level ?? null,
        clientX: event.clientX, clientY: event.clientY,
      }}));
    });
    // Toggling an item twice must not open the expanded chart.
    canvas.addEventListener('dblclick', event => { if (legendItemAt(canvas, event)) event.stopPropagation(); });
    canvas.addEventListener('pointermove', event => {
      const overLegend = Boolean(legendItemAt(canvas, event));
      const overAxis = !overLegend && canvas.dataset.legendMenu === 'true' && Boolean((renderStates.get(canvas)?.axisHits || []).length) && Boolean(axisItemAt(canvas, event));
      canvas.classList.toggle('ds-chart-legend-hover', overLegend);
      canvas.style.cursor = overLegend ? 'pointer' : (overAxis ? 'context-menu' : '');
    });
  }

  function selectionStartAllowed(canvas, event) {
    const view = views.get(canvas);
    const bounds = canvas.getBoundingClientRect();
    if (!view || !bounds.height) return false;
    if (legendItemAt(canvas, event)) return false;
    const logicalY = (event.clientY - bounds.top) / view.scaleY;
    // The chart title occupies the top band. Selection zoom starts only in
    // the plot and data-label area, never under titles or floating controls.
    return logicalY >= 90;
  }

  function attachPan(canvas) {
    if (canvas.dataset.panReady) return;
    canvas.dataset.panReady = 'true';
    let drag = null, pendingX = 0, pendingY = 0, panFrame = 0;
    const paintPan = () => {
      panFrame = 0;
      const view = views.get(canvas), payload = models.get(canvas);
      if (!view || !payload || (!pendingX && !pendingY)) return;
      const camera = cameraFor(canvas);
      camera.panX += pendingX / view.scaleX;
      camera.panY += pendingY / view.scaleY;
      pendingX = 0; pendingY = 0;
      constrainCamera(camera);
      draw(canvas, payload);
      canvas.dispatchEvent(new CustomEvent('designchartpan', {detail: chartPanState(canvas)}));
    };
    canvas.addEventListener('pointerdown', event => {
      // A map that navigates itself (geo_navigation) moves with its own drag instead.
      if (event.button !== 0 || models.get(canvas)?.geo_navigation) return;
      const selecting = cameraFor(canvas).zoom <= 1 && event.pointerType === 'mouse' && selectionStartAllowed(canvas, event);
      if (!selecting && cameraFor(canvas).zoom <= 1) return;
      drag = {pointerId: event.pointerId, x: event.clientX, y: event.clientY, selecting, startX: event.clientX, startY: event.clientY};
      canvas.classList.add(selecting ? 'is-selecting' : 'is-panning');
      canvas.setPointerCapture?.(event.pointerId);
      const tooltip = tooltipFor(canvas); if (tooltip) tooltip.hidden = true;
      if (!selecting) event.preventDefault();
    });
    canvas.addEventListener('pointermove', event => {
      if (!drag && cameraFor(canvas).zoom <= 1) {
        canvas.classList.toggle('ds-chart-selection-blocked', !selectionStartAllowed(canvas, event));
      }
      if (!drag || event.pointerId !== drag.pointerId) return;
      if (drag.selecting) {
        drag.endX = event.clientX; drag.endY = event.clientY;
        const bounds = canvas.getBoundingClientRect(), parentBounds = canvas.parentElement.getBoundingClientRect();
        const overlay = selectionOverlayFor(canvas);
        if (overlay) {
          const left = clamp(Math.min(drag.startX, drag.endX), bounds.left, bounds.right);
          const top = clamp(Math.min(drag.startY, drag.endY), bounds.top, bounds.bottom);
          const right = clamp(Math.max(drag.startX, drag.endX), bounds.left, bounds.right);
          const bottom = clamp(Math.max(drag.startY, drag.endY), bounds.top, bounds.bottom);
          overlay.style.left = `${left - parentBounds.left}px`; overlay.style.top = `${top - parentBounds.top}px`;
          overlay.style.width = `${right - left}px`; overlay.style.height = `${bottom - top}px`; overlay.hidden = false;
        }
        event.preventDefault();
        return;
      }
      pendingX += event.clientX - drag.x; pendingY += event.clientY - drag.y;
      drag.x = event.clientX; drag.y = event.clientY;
      if (!panFrame) panFrame = requestAnimationFrame(paintPan);
      event.preventDefault();
    });
    const stopPan = event => {
      if (!drag || event.pointerId !== drag.pointerId) return;
      const completedDrag = drag;
      if (completedDrag.selecting) {
        completedDrag.endX ??= event.clientX; completedDrag.endY ??= event.clientY;
        const overlay = selectionOverlayFor(canvas); if (overlay) overlay.hidden = true;
        if (event.type === 'pointerup') zoomToSelection(canvas, completedDrag);
      } else if (panFrame) { cancelAnimationFrame(panFrame); paintPan(); }
      canvas.releasePointerCapture?.(event.pointerId);
      canvas.classList.remove('is-panning', 'is-selecting');
      drag = null;
      if (cameraFor(canvas).zoom <= 1) canvas.classList.toggle('ds-chart-selection-blocked', !selectionStartAllowed(canvas, event));
    };
    canvas.addEventListener('pointerup', stopPan);
    canvas.addEventListener('pointercancel', stopPan);
  }

  const resizeObserver = 'ResizeObserver' in globalThis ? new ResizeObserver(entries => {
    cancelAnimationFrame(resizeFrame);
    resizeFrame = requestAnimationFrame(() => entries.forEach(entry => { const payload = models.get(entry.target); if (payload) draw(entry.target, payload); }));
  }) : null;

  globalThis.renderCanvasChart = (canvas, payload) => {
    // A model can carry the legend entries to show hidden (PPT exports).
    if (Array.isArray(payload?.hidden_legend_items)) {
      hiddenLegendItems.set(canvas, {
        hidden: new Set(payload.hidden_legend_items.map(String)),
        shown: new Set((payload.shown_legend_items || []).map(String)),
      });
    }
    models.set(canvas, payload); draw(canvas, payload); attachTooltip(canvas); attachTableReordering(canvas); attachPan(canvas); attachLegendToggle(canvas);
    if (resizeObserver && !observed.has(canvas)) { observed.add(canvas); resizeObserver.observe(canvas); }
  };
  // Another page theme (globalThis.canvasChartStyle) redraws the charts on the page at once.
  globalThis.redrawCanvasCharts = () => {
    renderedCanvases.forEach(canvas => {
      if (!canvas.isConnected) { renderedCanvases.delete(canvas); return; }
      const payload = models.get(canvas); if (payload) draw(canvas, payload);
    });
  };
  globalThis.getCanvasChartHits = canvas => structuredClone(renderStates.get(canvas)?.hits || []);
  globalThis.getCanvasChartLegendHits = canvas => structuredClone(renderStates.get(canvas)?.legendHits || []);
  globalThis.getCanvasChartHiddenLegendItems = hiddenLegendLabels;
  globalThis.setCanvasChartHiddenLegendItems = setHiddenLegendItems;
  globalThis.getCanvasChartLegendLabels = legendLabels;
  // The entries of the legend of a chart as its model has them (label and colour, before any format of the Designer), and the
  // entry under a pointer: the Designer formats a series from them.
  globalThis.getCanvasChartLegendItems = canvas => {
    const model = models.get(canvas) || {};
    const legend = (model.legend?.items || []).filter(item => item.colour).map(item => ({label: String(item.label), colour: item.colour}));
    if (legend.length) return legend;
    // A chart without a legend: its series, by name.
    const seen = new Set();
    return (model.series || []).map(item => ({label: String(item.name ?? item.legend_name ?? ''), colour: item.colour || ''}))
      .filter(item => item.label && item.colour && !seen.has(item.label) && seen.add(item.label));
  };
  globalThis.getCanvasChartLegendItemAt = (canvas, event) => legendItemAt(canvas, event);
  // The axis under a pointer (Designer): a numeric axis with its range and the range of its values, or a level
  // of a category axis with its field and every value it has (hidden ones included).
  globalThis.getCanvasChartAxisAt = (canvas, event) => {
    const view = views.get(canvas), state = renderStates.get(canvas), bounds = canvas.getBoundingClientRect();
    if (!view || !state || !bounds.width) return null;
    const x = ((event.clientX - bounds.left) / view.scaleX - view.originX) / view.zoom;
    const y = ((event.clientY - bounds.top) / view.scaleY - view.originY) / view.zoom;
    const numeric = (state.numericAxes || []).find(item => x >= item.x && x <= item.x + item.width && y >= item.y && y <= item.y + item.height);
    if (numeric) return {kind: 'numeric', axis: numeric.axis, domain: numeric.domain, extent: numeric.extent, percent: Boolean(numeric.percent)};
    const hit = axisItemAt(canvas, event);
    if (!hit) return null;
    const model = models.get(canvas) || {};
    // The dimensions of a model list the levels of its rows first, then those of its columns.
    const rowLevels = Array.isArray(model.row_keys) ? Math.max(0, ...model.row_keys.map(key => (Array.isArray(key) ? key.length : 1)))
      : Number(model.row_dimension_count) || 0;
    const onColumns = hit.axis !== 'row' && hit.axis !== 'table-row' && (Array.isArray(model.row_keys) || hit.axis === 'table-column');
    const dimension = model.dimensions?.[onColumns ? rowLevels + hit.level : hit.level]?.[0];
    return {kind: 'category', axis: hit.axis, level: hit.level, value: hit.value, values: axisLevelValues(model, hit.axis, hit.level),
      dimension: String(dimension || '')};
  };
  globalThis.setCanvasChartZoom = setChartZoom;
  globalThis.getCanvasChartZoom = canvas => cameraFor(canvas).zoom;
  globalThis.zoomCanvasChartAt = zoomChartAt;
  globalThis.panCanvasChart = panChart;
  globalThis.getCanvasChartPanState = chartPanState;
  // The plot of the last drawn map and the canvas scale, to turn a pointer position into a place.
  globalThis.getCanvasMapView = canvas => {
    const geometry = renderStates.get(canvas)?.mapGeometry, view = views.get(canvas);
    return geometry && view ? {...geometry, scaleX: view.scaleX, scaleY: view.scaleY, originX: view.originX, originY: view.originY, cameraZoom: view.zoom} : null;
  };
})();
