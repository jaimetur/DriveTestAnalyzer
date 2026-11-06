/* Campaign labels and order of the active workspace (Workspace Config → Campaign Maps).
 *
 * The same rules as column_names.format_campaign and campaign_sort_key in Python, so
 * the pages show and order campaigns exactly as the charts, tables and reports built on
 * the server: a label format with markers ({year}, {yy}, {quarter}, {mode}, {market};
 * characters inside the braces are written only when the part exists), the order of the
 * radio modes inside a quarter, the modes shown in the label and exceptions for campaigns that do not follow the
 * pattern. Filters always keep the original campaign values.
 */
(() => {
  'use strict';

  const DEFAULT_MAP = {format: '{yy}-Q{quarter}{-mode}', mode_order: ['', 'NSA', 'SA'], modes_in_label: ['NSA', 'SA'], exceptions: []};
  const MARKER = /\{([^A-Za-z{}]*)(year|yy|quarter|mode|market)([^A-Za-z{}]*)\}/g;

  const readMap = () => {
    try {
      const element = document.getElementById('campaign-map');
      const parsed = element ? JSON.parse(element.textContent || 'null') : null;
      return parsed && typeof parsed === 'object' ? {...DEFAULT_MAP, ...parsed} : DEFAULT_MAP;
    } catch (_error) {
      return DEFAULT_MAP;
    }
  };
  let campaignMap = null;
  const activeMap = () => (campaignMap ||= readMap());

  const clean = (value) => {
    const text = String(value ?? '').trim();
    return ['<na>', 'nan', 'nat', 'none'].includes(text.toLowerCase()) ? '' : text;
  };

  // Year, quarter and SA/NSA mode, as column_names.campaign_parts.
  const campaignParts = (value) => {
    const text = clean(value);
    return {
      year: text.match(/(?<!\d)((?:19|20)\d{2})(?!\d)/)?.[1] || '',
      quarter: text.match(/(?:^|[^A-Z0-9])Q\s*[_\- ]?([1-4])(?=$|[^0-9])/i)?.[1] || '',
      mode: (text.match(/(?:^|[_\- ])(NSA|SA)(?=$|[_\- ])/i)?.[1] || '').toUpperCase(),
    };
  };

  const campaignMarket = (value) => clean(value).split(/[^A-Za-z0-9]+/)
    .find((token) => /^[A-Z]{2,3}$/.test(token) && !['SA', 'NSA'].includes(token)) || '';

  const exceptionFor = (text, map) => {
    const key = text.toLowerCase();
    const index = (map.exceptions || []).findIndex((item) => item.label.toLowerCase() === key
      || (item.sources || []).some((source) => String(source).toLowerCase() === key));
    return index >= 0 ? {index, item: map.exceptions[index]} : null;
  };

  const FORMAT_PART_PATTERNS = {
    year: '(?<!\\d)(?:19|20)\\d{2}(?!\\d)', yy: '(?<!\\d)\\d{2}(?!\\d)', quarter: '[1-4](?!\\d)',
    mode: '(?:NSA|SA)(?![A-Za-z])', market: '[A-Z]{2,3}',
  };
  const escapeRegExp = (text) => String(text).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

  // Year, quarter and mode of an exception label, as column_names._exception_label_parts: read as a campaign, else
  // with the label format of the map (26-Q2-Flex is 2026 Q2 with {yy}-Q{quarter}).
  const exceptionLabelParts = (label, map) => {
    const parts = campaignParts(label);
    if (parts.year && parts.quarter) return parts;
    const format = String(map.format || DEFAULT_MAP.format);
    const kinds = [];
    let pattern = '';
    let position = 0;
    for (const match of format.matchAll(MARKER)) {
      const [, before, kind, after] = match;
      const part = `${escapeRegExp(before)}(${FORMAT_PART_PATTERNS[kind]})${escapeRegExp(after)}`;
      pattern += escapeRegExp(format.slice(position, match.index)) + (['mode', 'market'].includes(kind) ? `(?:${part})?` : part);
      kinds.push(kind);
      position = match.index + match[0].length;
    }
    const found = clean(label).match(new RegExp(pattern + escapeRegExp(format.slice(position)), 'i'));
    const values = {};
    kinds.forEach((kind, index) => { if (found?.[index + 1] && !values[kind]) values[kind] = found[index + 1]; });
    const year = values.year || (values.yy ? `20${values.yy}` : '');
    if (!year || !values.quarter) return parts;
    return {year, quarter: values.quarter, mode: values.mode ? values.mode.toUpperCase() : parts.mode};
  };

  const campaignLabel = (value, map = activeMap()) => {
    const text = clean(value);
    if (!text) return '';
    const exception = exceptionFor(text, map);
    if (exception) return exception.item.label;
    const {year, quarter, mode} = campaignParts(text);
    if (!year || !quarter) return text;
    // {mode} writes only the modes shown in the label.
    const shown = map.modes_in_label || DEFAULT_MAP.modes_in_label;
    const parts = {year, yy: year.slice(-2), quarter, mode: shown.includes(mode) ? mode : '', market: campaignMarket(text)};
    return String(map.format || DEFAULT_MAP.format)
      .replace(MARKER, (_match, before, name, after) => (parts[name] ? `${before}${parts[name]}${after}` : ''));
  };

  // [year, quarter, mode rank, exception position, label]: compare with campaignCompare.
  const campaignSortKey = (value, map = activeMap()) => {
    const text = clean(value);
    const exception = exceptionFor(text, map);
    const label = exception ? exception.item.label : text;
    const {year, quarter, mode} = exception ? exceptionLabelParts(label, map) : campaignParts(label);
    if (!year || !quarter) {
      return [-1, -1, exception ? exception.index : (map.exceptions || []).length, 0, label.toLowerCase()];
    }
    const modes = map.mode_order || DEFAULT_MAP.mode_order;
    const rank = modes.includes(mode) ? modes.indexOf(mode) : modes.length;
    return [Number(year), Number(quarter), rank, exception ? exception.index + 1 : 0, label.toLowerCase()];
  };

  const campaignCompare = (left, right) => {
    const a = campaignSortKey(left);
    const b = campaignSortKey(right);
    for (let index = 0; index < a.length; index += 1) {
      if (a[index] < b[index]) return -1;
      if (a[index] > b[index]) return 1;
    }
    return 0;
  };

  Object.assign(globalThis, {campaignLabel, campaignSortKey, campaignCompare, campaignParts});
  // Workspace Config previews a map being edited, then saves it.
  globalThis.setCampaignMap = (map) => { campaignMap = map ? {...DEFAULT_MAP, ...map} : null; };
})();
