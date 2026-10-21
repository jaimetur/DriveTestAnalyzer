// Rich texts: the descriptions and comments of Ticket Center and the long texts and comments of Non-Qualified Calls.
// They are written in Markdown: # headings, bullets and numbered lists nested at any level (1., a), 1.1.), tasks,
// **bold**, *italic*, ~~strikethrough~~, ==highlight==, `code` and links, cards of Notes, Tips, Warnings, Errors and
// the like (> [!TIP]), quotes, code blocks and dividers. A short line ending with a colon, or followed by a list, is the
// title of what follows it.
// Each line of a text is one element, the same on the page and in the editor, styled by rich_text.css, so a text reads
// the same while it is written; the editor saves it back as Markdown in the text area it replaces.
(() => {
  'use strict';

  const INDENT = '  ';
  const MAX_TITLE_LENGTH = 80;
  const BULLET = /^([-*+·•◦▪–])(?:\s+|$)/;
  const ORDERED = /^(\d{1,3})([.)])(?:\s+|$)/;
  const OUTLINE = /^(\d{1,3}(?:\.\d{1,3})+)([.)])(?:\s+|$)/;
  const ALPHA = /^([a-zA-Z])([.)])(?:\s+|$)/;
  const TASK = /^\[([ xX])\](?:\s+|$)/;
  const HEADING = /^(#{1,6})(?:\s+(.*?))?\s*$/;
  const FENCE = /^(`{3,}|~{3,})\s*([^`\s]*)\s*$/;
  const QUOTE = /^>(?:\s|$)/;
  const CARD = /^\[!([A-Za-z][\w-]*)\][+-]?(?:\s+(.*))?$/;
  const DIVIDER = /^[-=_*]{3,}(?:\s*(.*?)\s*[-=_*]{3,})?$/;
  const ESCAPABLE = /[!-/:-@[-`{-~·•◦▪–]/;
  const WORD = /[\p{L}\p{N}]/u;
  const GLYPHS = ['•', '◦', '▪'];
  // The kinds of card, with their title when the card has none of its own, and the names they are also written with.
  const CARDS = {
    note: 'Note', info: 'Info', tip: 'Tip', success: 'Success', question: 'Question', important: 'Important',
    warning: 'Warning', caution: 'Caution', error: 'Error', quote: 'Quote',
  };
  const CARD_ALIASES = {
    hint: 'tip', check: 'success', done: 'success', help: 'question', faq: 'question', attention: 'warning',
    danger: 'error', failure: 'error', fail: 'error', bug: 'error', abstract: 'info', summary: 'info', tldr: 'info',
    todo: 'info', example: 'note', cite: 'quote',
  };
  const LINE_DATA = ['type', 'level', 'list', 'style', 'delim', 'start', 'prefix', 'task', 'heading', 'card', 'lang'];

  // ---------------------------------------------------------------------------------------------------------------
  // Inline formats: [{type: 'text' | 'code', text} | {type: 'strong' | 'em' | 'del' | 'mark', children} |
  // {type: 'link', href, children}].

  const runLength = (source, index, char) => {
    let end = index;
    while (source[end] === char) end += 1;
    return end - index;
  };
  const codeClose = (source, from, run) => {
    let position = from;
    while (position < source.length) {
      if (source[position] === '`') {
        const length = runLength(source, position, '`');
        if (length === run) return position;
        position += length;
      } else position += 1;
    }
    return -1;
  };
  // Links open pages of the web, mail or pages of the tool; anything else (javascript:…) stays text.
  const safeHref = (href) => /^(?:https?:\/\/|mailto:)\S+$/i.test(href) || /^\/(?!\/)\S*$/.test(href) || /^#\S*$/.test(href);
  // A web address written as it is: the punctuation after it ends the sentence, not the link.
  const bareUrl = (source, index) => {
    const match = source.slice(index).match(/^https?:\/\/[^\s<>"]+/i);
    if (!match) return null;
    let url = match[0];
    const opened = (text, char) => (text.match(new RegExp(`\\${char}`, 'g')) || []).length;
    while (/[.,:;!?'"*_~=]$/.test(url) || (url.endsWith(')') && opened(url, '(') < opened(url, ')'))) url = url.slice(0, -1);
    return /^https?:\/\/[^/\s]+\.\S/i.test(url) || /^https?:\/\/localhost/i.test(url) ? url : null;
  };
  const parseLink = (source, index) => {
    let depth = 0;
    let position = index;
    for (; position < source.length; position += 1) {
      const char = source[position];
      if (char === '\\') { position += 1; continue; }
      if (char === '[') depth += 1;
      else if (char === ']') {
        depth -= 1;
        if (!depth) break;
      }
    }
    if (position >= source.length || source[position + 1] !== '(' || position === index + 1) return null;
    let end = position + 2;
    let parens = 1;
    for (; end < source.length; end += 1) {
      if (source[end] === '(') parens += 1;
      else if (source[end] === ')') {
        parens -= 1;
        if (!parens) break;
      }
    }
    if (end >= source.length) return null;
    const href = source.slice(position + 2, end).trim().replace(/\s+"[^"]*"$/, '').replace(/^<(.*)>$/, '$1');
    return safeHref(href) ? {label: source.slice(index + 1, position), href, end: end + 1} : null;
  };
  // **bold**, *italic*, ***both***, ~~strikethrough~~ and ==highlight== (also with _ and __): the closing run of the
  // same length, not after a space; _ never opens or closes inside a word.
  const emphasisAt = (source, index, char, run) => {
    const type = (char === '~' || char === '=') ? {2: char === '~' ? 'del' : 'mark'}[run] : {1: 'em', 2: 'strong', 3: 'both'}[run];
    const after = source[index + run];
    if (!type || !after || /\s/.test(after) || (char === '_' && WORD.test(source[index - 1] || ''))) return null;
    let position = index + run;
    while (position < source.length) {
      const current = source[position];
      if (current === '\\') { position += 2; continue; }
      if (current === '`') {
        const length = runLength(source, position, '`');
        const close = codeClose(source, position + length, length);
        position = close >= 0 ? close + length : position + length;
        continue;
      }
      if (current === char) {
        const length = runLength(source, position, char);
        if (length === run && !/\s/.test(source[position - 1]) && !(char === '_' && WORD.test(source[position + length] || ''))) {
          const children = parseInline(source.slice(index + run, position));
          const token = type === 'both' ? {type: 'em', children: [{type: 'strong', children}]} : {type, children};
          return {token, end: position + length};
        }
        position += length;
        continue;
      }
      position += 1;
    }
    return null;
  };
  function parseInline(text) {
    const source = String(text ?? '');
    const tokens = [];
    let plain = '';
    const flush = () => {
      if (plain) tokens.push({type: 'text', text: plain});
      plain = '';
    };
    let index = 0;
    while (index < source.length) {
      const char = source[index];
      if (char === '\\' && ESCAPABLE.test(source[index + 1] || '')) {
        plain += source[index + 1];
        index += 2;
        continue;
      }
      if (char === '`') {
        const run = runLength(source, index, '`');
        const close = codeClose(source, index + run, run);
        if (close >= 0) {
          flush();
          let code = source.slice(index + run, close);
          if (code.length > 1 && code.startsWith(' ') && code.endsWith(' ') && code.trim()) code = code.slice(1, -1);
          tokens.push({type: 'code', text: code});
          index = close + run;
        } else {
          plain += source.slice(index, index + run);
          index += run;
        }
        continue;
      }
      if (char === '[') {
        const link = parseLink(source, index);
        if (link) {
          flush();
          tokens.push({type: 'link', href: link.href, children: parseInline(link.label)});
          index = link.end;
          continue;
        }
      }
      if (char === '<') {
        const auto = source.slice(index).match(/^<((?:https?:\/\/|mailto:)[^\s<>]+)>/i);
        if (auto) {
          flush();
          tokens.push({type: 'link', href: auto[1], children: [{type: 'text', text: auto[1]}]});
          index += auto[0].length;
          continue;
        }
      }
      if ((char === 'h' || char === 'H') && !WORD.test(source[index - 1] || '')) {
        const url = bareUrl(source, index);
        if (url) {
          flush();
          tokens.push({type: 'link', href: url, children: [{type: 'text', text: url}]});
          index += url.length;
          continue;
        }
      }
      if ('*_~='.includes(char)) {
        const run = runLength(source, index, char);
        const emphasis = emphasisAt(source, index, char, run);
        if (emphasis) {
          flush();
          tokens.push(emphasis.token);
          index = emphasis.end;
        } else {
          plain += source.slice(index, index + run);
          index += run;
        }
        continue;
      }
      plain += char;
      index += 1;
    }
    flush();
    return tokens;
  }
  const tokensText = (tokens) => tokens.map((token) => (token.children ? tokensText(token.children) : token.text)).join('');
  const inlinePlain = (text) => tokensText(parseInline(text));

  // The same formats written in one way: no empty or doubled formats, neighbours of a kind merged, bold inside italic.
  function normalizeTokens(tokens, around = []) {
    const out = [];
    const push = (token) => {
      const last = out[out.length - 1];
      if (last && last.type === token.type && (token.type === 'text' || token.type === 'code')) {
        out[out.length - 1] = {type: token.type, text: last.text + token.text};
      } else if (last && last.type === token.type && token.children && token.type !== 'link') {
        out[out.length - 1] = {type: token.type, children: normalizeTokens([...last.children, ...token.children], around)};
      } else out.push(token);
    };
    tokens.forEach((token) => {
      if (token.type === 'text' || token.type === 'code') {
        if (token.text) push({type: token.type, text: token.text});
        return;
      }
      if (around.includes(token.type)) {
        normalizeTokens(token.children, around).forEach(push);
        return;
      }
      const children = normalizeTokens(token.children, [...around, token.type]);
      if (!children.length) return;
      let next = token.type === 'link' ? {type: 'link', href: token.href, children} : {type: token.type, children};
      if (next.type === 'strong' && children.length === 1 && children[0].type === 'em') {
        next = {type: 'em', children: [{type: 'strong', children: children[0].children}]};
      }
      push(next);
    });
    return out;
  }
  // What a line shows, to compare two ways of writing it: a link whose text is its address reads as that text, and
  // the spaces around the line do not count.
  const signature = (tokens) => {
    const plainLinks = (list) => list.map((token) => {
      if (token.type === 'link' && tokensText(token.children) === token.href) return {type: 'text', text: token.href};
      return token.children ? {...token, children: plainLinks(token.children)} : token;
    });
    const normal = normalizeTokens(plainLinks(tokens));
    if (normal[0]?.type === 'text') normal[0] = {type: 'text', text: normal[0].text.trimStart()};
    const last = normal.length - 1;
    if (normal[last]?.type === 'text') normal[last] = {type: 'text', text: normal[last].text.trimEnd()};
    return JSON.stringify(normal.filter((token) => token.type !== 'text' || token.text));
  };
  const escapeText = (text, everything) => text.replace(
    everything ? /[\\*_`~=[\]<>]/g : /\\(?=[!-/:-@[-`{-~·•◦▪–]|$)/g, (char) => `\\${char}`,
  );
  function tokensToMarkdown(tokens, everything = false) {
    return tokens.map((token) => {
      if (token.type === 'text') return escapeText(token.text, everything);
      if (token.type === 'code') {
        const longest = Math.max(0, ...(token.text.match(/`+/g) || []).map((run) => run.length));
        const fence = '`'.repeat(longest + 1);
        const pad = /^`|`$/.test(token.text) || (/^ .* $/.test(token.text) && token.text.trim()) ? ' ' : '';
        return `${fence}${pad}${token.text}${pad}${fence}`;
      }
      const inner = tokensToMarkdown(token.children, everything);
      if (token.type === 'link') {
        return inner === token.href && bareUrl(token.href, 0) === token.href ? token.href : `[${inner}](${token.href})`;
      }
      const lead = inner.match(/^\s*/)[0];
      const trail = inner.slice(lead.length).match(/\s*$/)[0];
      const core = inner.slice(lead.length, inner.length - trail.length);
      if (!core) return inner;
      let mark = {em: '*', strong: '**', del: '~~', mark: '=='}[token.type];
      if ((token.type === 'em' || token.type === 'strong') && /^\*|\*$/.test(core)) mark = token.type === 'em' ? '_' : '__';
      return `${lead}${mark}${core}${mark}${trail}`;
    }).join('');
  }

  // ---------------------------------------------------------------------------------------------------------------
  // Lines: [{type: 'p' | 'h' | 'li' | 'cont' | 'code' | 'hr' | 'head', text, level, ...}]. A paragraph (p) is a line of
  // text (an empty one a blank line); h a heading; li a list item (list ul or ol, its style, delimiter, first number
  // and, for 1.1., the numbers before its own); cont a line that goes on in the item above it; code a line of a code
  // block; hr a divider; head the first line of a card (its title). The lines of a card or quote have its kind (card).

  // The text of a divider line (----- Text ----- or ---), or null when the line is not one; ***bold*** stays bold.
  const dividerOf = (line) => {
    const match = line.match(DIVIDER);
    if (!match || /^(?:\*{1,3}|_{1,3})[^\s*_]/.test(line)) return null;
    return match[1] || '';
  };
  const listItemOf = (line) => {
    let match = line.match(BULLET);
    if (match) return {list: 'ul', text: line.slice(match[0].length)};
    if ((match = line.match(OUTLINE))) {
      const parts = match[1].split('.');
      const start = Number(parts.pop());
      return {list: 'ol', style: 'outline', delim: match[2], start, prefix: parts.join('.'), depth: parts.length + 1, text: line.slice(match[0].length)};
    }
    if ((match = line.match(ORDERED))) return {list: 'ol', style: 'decimal', delim: match[2], start: Number(match[1]), text: line.slice(match[0].length)};
    if ((match = line.match(ALPHA))) {
      const letter = match[1];
      return {
        list: 'ol', style: letter === letter.toLowerCase() ? 'lower-alpha' : 'upper-alpha', delim: match[2],
        start: letter.toLowerCase().charCodeAt(0) - 96, text: line.slice(match[0].length),
      };
    }
    return null;
  };
  // A title: a short line ending with a colon, or followed by a list.
  const titleText = (text, beforeList) => text.length <= MAX_TITLE_LENGTH && (text.endsWith(':') || beforeList);
  const nextIsItem = (rawLines, index) => {
    const next = (rawLines[index + 1] || '').trim();
    return Boolean(next) && dividerOf(next) === null && Boolean(listItemOf(next));
  };
  const capitalize = (text) => text.charAt(0).toUpperCase() + text.slice(1);

  // implicit: every line without a marker is a bullet too (the long texts of Non-Qualified Calls), nested as deep as
  // it is indented, but for a title, and blank lines do not end the bullets.
  function parseLines(rawLines, implicit) {
    const lines = [];
    let stack = [];
    let itemLevel = -1;
    const closeLists = () => {
      stack = [];
      itemLevel = -1;
    };
    // The level of a list line from its indent: the first open level at that indent, or one more than the deepest
    // under it; a 1.2.1. item is at least as deep as its numbers (stack: the indent of each open level).
    const levelFor = (indent, minimum = 0) => {
      while (stack.length && indent < stack[stack.length - 1]) stack.pop();
      while (stack.length > 1 && stack[stack.length - 2] === indent) stack.pop();
      const level = Math.max(minimum, !stack.length || indent > stack[stack.length - 1] ? stack.length : stack.length - 1);
      stack.length = Math.min(stack.length, level);
      while (stack.length <= level) stack.push(indent);
      return level;
    };
    for (let index = 0; index < rawLines.length; index += 1) {
      const raw = rawLines[index].replace(/\t/g, '    ');
      const content = raw.trim();
      const indent = raw.length - raw.trimStart().length;
      const fence = content.match(FENCE);
      if (fence) {
        const closing = new RegExp(`^\\${fence[1][0]}{${fence[1].length},}\\s*$`);
        let end = index + 1;
        while (end < rawLines.length && !closing.test(rawLines[end].trim())) end += 1;
        const body = rawLines.slice(index + 1, end).map((code) => code.replace(new RegExp(`^ {0,${indent}}`), ''));
        (body.length ? body : ['']).forEach((code, position) => lines.push({type: 'code', text: code, lang: position ? '' : fence[2]}));
        index = end;
        closeLists();
        continue;
      }
      if (QUOTE.test(content)) {
        // A quote, or a card when its first line is [!KIND]: its lines without their >, read as any other text.
        const inner = [];
        let end = index;
        while (end < rawLines.length && QUOTE.test(rawLines[end].trim())) {
          const line = rawLines[end].trim().replace(/^>\s?/, '');
          if (end > index && CARD.test(line.trim())) break;
          inner.push(line);
          end += 1;
        }
        index = end - 1;
        closeLists();
        let kind = 'quote';
        const head = inner[0].trim().match(CARD);
        if (head) {
          const name = head[1].toLowerCase();
          let title = (head[2] || '').trim();
          kind = CARD_ALIASES[name] || name;
          if (!CARDS[kind]) {
            title = title || capitalize(name);
            kind = 'note';
          }
          lines.push({type: 'head', text: title, card: kind});
          inner.shift();
        }
        parseLines(inner, false).forEach((line) => lines.push({...line, card: kind}));
        continue;
      }
      if (!content) {
        lines.push({type: 'p', text: '', level: 0});
        if (!implicit) closeLists();
        continue;
      }
      const heading = content.match(HEADING);
      if (heading) {
        lines.push({type: 'h', heading: heading[1].length, text: (heading[2] || '').replace(/(?:^|\s+)#+$/, '')});
        closeLists();
        continue;
      }
      const divider = dividerOf(content);
      if (divider !== null) {
        lines.push({type: 'hr', text: divider});
        closeLists();
        continue;
      }
      const item = listItemOf(content);
      if (item) {
        const level = levelFor(indent, (item.depth || 1) - 1);
        itemLevel = level;
        const task = item.text.match(TASK);
        lines.push({
          type: 'li', level, list: item.list, style: item.style || '', delim: item.delim || '', start: item.start ?? '',
          prefix: item.prefix || '', task: task ? (task[1] === ' ' ? 'open' : 'done') : '',
          text: task ? item.text.slice(task[0].length) : item.text,
        });
        continue;
      }
      if (implicit) {
        const level = levelFor(indent);
        lines.push({type: 'p', level, text: content});
        if (level === 0 && titleText(inlinePlain(content), nextIsItem(rawLines, index))) closeLists();
        continue;
      }
      if (itemLevel >= 0 && indent > 0) {
        lines.push({type: 'cont', level: itemLevel, text: content});
        continue;
      }
      lines.push({type: 'p', text: content, level: 0});
      closeLists();
    }
    return lines;
  }
  const parse = (text, options = {}) => parseLines(String(text ?? '').replace(/\r\n?/g, '\n').split('\n'), Boolean(options.implicitBullets));

  const letters = (number, upper) => {
    let rest = Math.max(1, number);
    let text = '';
    while (rest > 0) {
      rest -= 1;
      text = String.fromCharCode(97 + (rest % 26)) + text;
      rest = Math.floor(rest / 26);
    }
    return upper ? text.toUpperCase() : text;
  };
  const counterText = (counter) => (counter.style.endsWith('alpha') ? letters(counter.number, counter.style === 'upper-alpha') : String(counter.number));
  const orderedMarker = (line, number, counters, level) => {
    if (line.style === 'outline') {
      const prefix = String(line.prefix || '').split('.').filter(Boolean);
      const parts = [];
      for (let depth = 0; depth < level; depth += 1) {
        if (counters[depth]) parts.push(counterText(counters[depth]));
        else if (prefix[depth] !== undefined) parts.push(prefix[depth]);
      }
      return `${[...parts, number].join('.')}${line.delim}`;
    }
    return `${counterText({style: line.style, number})}${line.delim}`;
  };

  // How each line reads: its level (never deeper than one under the line above it), the marker of its bullet or its
  // number, whether it is a title or (implicit) a line read as a bullet, and where its card or code block begins and
  // ends. Every line has its plain text (plain).
  function layout(lines, options = {}) {
    const implicit = Boolean(options.implicitBullets);
    const single = lines.filter((line) => String(line.plain ?? '').trim()).length <= 1;
    const views = [];
    let context = 0;
    let counters = [];
    let listLevel = -1;
    let paragraph = false;
    const closeLists = () => {
      counters = [];
      listLevel = -1;
    };
    lines.forEach((line, index) => {
      const previous = lines[index - 1];
      const card = line.card || '';
      if (!previous || card !== (previous.card || '') || line.type === 'head') {
        context += 1;
        closeLists();
        paragraph = false;
      }
      const text = String(line.plain ?? '').trim();
      const next = lines[index + 1];
      const beforeList = Boolean(next && next.type === 'li' && (next.card || '') === card);
      const view = {type: line.type || 'p', level: 0, marker: '', number: 0, title: false, implicit: false, empty: !text, card, context};
      const asParagraph = (level) => {
        view.type = 'p';
        if (!text) {
          // An empty line of a long text keeps the level it was given (Tab), to be written at it.
          if (implicit && !card) {
            view.level = Math.max(0, level);
            view.implicit = view.level > 0;
          } else closeLists();
          paragraph = false;
          return;
        }
        if (implicit && !card && !single) {
          view.level = Math.max(0, Math.min(level, listLevel + 1));
          if (view.level === 0 && titleText(text, beforeList)) {
            view.title = true;
            closeLists();
            return;
          }
          view.implicit = true;
          view.marker = GLYPHS[view.level % GLYPHS.length];
          counters.length = Math.min(counters.length, view.level + 1);
          counters[view.level] = null;
          listLevel = view.level;
          return;
        }
        view.title = titleText(text, beforeList) && (text.endsWith(':') || !paragraph);
        paragraph = !view.title;
        closeLists();
      };
      if (view.type === 'li') {
        const depth = line.style === 'outline' ? String(line.prefix || '').split('.').filter(Boolean).length + 1 : 1;
        const level = Math.max(0, Math.min(Number(line.level) || 0, Math.max(listLevel + 1, depth - 1)));
        view.level = level;
        counters.length = Math.min(counters.length, level + 1);
        if (line.list === 'ol') {
          const style = line.style || 'decimal';
          const delim = line.delim || '.';
          const counter = counters[level];
          const start = Number.isFinite(Number(line.start)) && line.start !== '' ? Number(line.start) : 1;
          const number = counter && counter.style === style && counter.delim === delim ? counter.number + 1 : start;
          counters[level] = {style, delim, number};
          view.number = number;
          view.marker = orderedMarker({...line, style, delim}, number, counters, level);
        } else {
          counters[level] = null;
          view.marker = GLYPHS[level % GLYPHS.length];
        }
        listLevel = level;
        view.title = text.endsWith(':') && text.length <= MAX_TITLE_LENGTH;
        paragraph = false;
      } else if (view.type === 'cont') {
        if (listLevel < 0 || (implicit && !card)) asParagraph(implicit ? (Number(line.level) || 0) + 1 : 0);
        else view.level = listLevel;
      } else if (view.type === 'p') {
        asParagraph(Number(line.level) || 0);
      } else {
        closeLists();
        paragraph = false;
      }
      views.push(view);
    });
    // The spacing between a list and the text around it, and the edges of the cards and code blocks.
    const kindOf = (view) => (view.type === 'li' || view.type === 'cont' || view.implicit ? 'list' : view.type === 'p' && !view.empty && !view.title ? 'text' : '');
    views.forEach((view, index) => {
      const previous = views[index - 1];
      const next = views[index + 1];
      view.gap = Boolean(previous && previous.context === view.context && kindOf(view) && kindOf(previous) && kindOf(view) !== kindOf(previous));
      view.codeFirst = view.type === 'code' && !(previous?.type === 'code' && previous.context === view.context);
      view.codeLast = view.type === 'code' && !(next?.type === 'code' && next.context === view.context);
      view.cardFirst = Boolean(view.card) && previous?.context !== view.context;
      view.cardLast = Boolean(view.card) && next?.context !== view.context;
    });
    return views;
  }

  // A text that would start another kind of line (- , 1. , # , > , ``` or ---) is written with a backslash.
  const escapeBlock = (text) => {
    if (!text) return text;
    if (dividerOf(text) !== null || HEADING.test(text) || QUOTE.test(text) || FENCE.test(text) || BULLET.test(text)) return `\\${text}`;
    const ordered = text.match(OUTLINE) || text.match(ORDERED) || text.match(ALPHA);
    return ordered ? `${ordered[1]}\\${text.slice(ordered[1].length)}` : text;
  };
  // The Markdown of a run of lines outside the cards (or of the lines inside one).
  function blockMarkdown(pairs, implicit) {
    const out = [];
    for (let index = 0; index < pairs.length; index += 1) {
      const [line, view] = pairs[index];
      if (view.type === 'code') {
        const group = [];
        while (index < pairs.length && pairs[index][1].type === 'code') {
          group.push(pairs[index][0]);
          index += 1;
        }
        index -= 1;
        const longest = Math.max(2, ...group.map((code) => (String(code.text).trimStart().match(/^`+/) || [''])[0].length));
        const fence = '`'.repeat(longest + 1);
        out.push(`${fence}${group[0].lang || ''}`, ...group.map((code) => code.text), fence);
        continue;
      }
      const inline = String(line.inline ?? '').trim();
      if (view.type === 'h') out.push(`${'#'.repeat(Number(line.heading) || 1)}${inline ? ` ${inline.replace(/#$/, '\\#')}` : ''}`);
      else if (view.type === 'hr') out.push(inline ? `----- ${inline} -----` : '---');
      else if (view.type === 'li') {
        const marker = line.list === 'ol' ? view.marker : '-';
        const task = line.task ? `[${line.task === 'done' ? 'x' : ' '}] ` : '';
        const text = task ? inline : inline.replace(TASK, (match) => `\\${match}`);
        out.push(`${INDENT.repeat(view.level)}${marker} ${task}${text}`.trimEnd());
      } else if (view.type === 'cont') out.push(`${INDENT.repeat(view.level + 1)}${escapeBlock(inline)}`);
      else if (implicit && view.implicit) out.push(`${INDENT.repeat(view.level)}${escapeBlock(inline)}`.trimEnd());
      else out.push(escapeBlock(inline));
    }
    return out;
  }
  // The Markdown of laid out lines (each with its inline Markdown, inline, or its text for code): the cards with their
  // > [!KIND] Title, the lists indented two spaces a level.
  function toMarkdown(lines, views, options = {}) {
    const implicit = Boolean(options.implicitBullets);
    const out = [];
    let index = 0;
    while (index < lines.length) {
      const view = views[index];
      let end = index + 1;
      if (view.card) {
        while (end < lines.length && views[end].context === view.context) end += 1;
        const pairs = lines.slice(index, end).map((line, offset) => [line, views[index + offset]]);
        if (pairs[0][1].type === 'head') {
          const title = String(pairs.shift()[0].inline ?? '').trim();
          out.push(`> [!${view.card.toUpperCase()}]${title ? ` ${title}` : ''}`);
        } else if (view.card !== 'quote') out.push(`> [!${view.card.toUpperCase()}]`);
        blockMarkdown(pairs, false).forEach((text) => out.push(text ? `> ${text}` : '>'));
      } else {
        while (end < lines.length && !views[end].card) end += 1;
        out.push(...blockMarkdown(lines.slice(index, end).map((line, offset) => [line, views[index + offset]]), implicit));
      }
      index = end;
    }
    return out.join('\n').replace(/\n+$/, '');
  }
  const withPlain = (lines) => lines.map((line) => ({...line, plain: line.type === 'code' ? line.text : inlinePlain(line.text)}));
  // A text written the way the editor writes it (to compare with what it saves).
  const normalizeText = (text, options = {}) => {
    const lines = withPlain(parse(text, options));
    return toMarkdown(lines.map((line) => ({...line, inline: line.text})), layout(lines, options), options);
  };
  // A text without its Markdown, as one line or a few (the previews of a list): its markers, numbers and words.
  const toPlainText = (text, options = {}) => {
    const lines = withPlain(parse(text, options));
    const views = layout(lines, options);
    return lines.map((line, index) => {
      const view = views[index];
      const marker = line.task ? (line.task === 'done' ? '☑' : '☐') : view.marker;
      const words = line.type === 'head' && !line.plain.trim() ? CARDS[line.card] || '' : line.plain.trim();
      return `${INDENT.repeat(view.level)}${marker ? `${marker} ` : ''}${words}`.trimEnd();
    }).join('\n').replace(/\n{3,}/g, '\n\n').trim();
  };

  // ---------------------------------------------------------------------------------------------------------------
  // The page: each line one element (div.rt-line), its kind in data-type and the rest of it in data-*.

  const element = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  function tokensToNodes(tokens) {
    return tokens.map((token) => {
      if (token.type === 'text') return document.createTextNode(token.text);
      if (token.type === 'code') return element('code', '', token.text);
      const node = element({strong: 'strong', em: 'em', del: 's', mark: 'mark', link: 'a'}[token.type]);
      if (token.type === 'link') {
        node.setAttribute('href', token.href);
        node.target = '_blank';
        node.rel = 'noopener noreferrer';
      }
      node.append(...tokensToNodes(token.children));
      return node;
    });
  }
  const cleanText = (text) => text.replace(/\u200b/g, '').replace(/\u00a0/g, ' ');
  function nodesToTokens(parent) {
    const tokens = [];
    parent.childNodes.forEach((node) => {
      if (node.nodeType === 3) {
        const text = cleanText(node.data);
        if (text) tokens.push({type: 'text', text});
        return;
      }
      if (node.nodeType !== 1 || node.tagName === 'BR') return;
      if (node.tagName === 'CODE') {
        tokens.push({type: 'code', text: cleanText(node.textContent)});
        return;
      }
      const type = {STRONG: 'strong', B: 'strong', EM: 'em', I: 'em', S: 'del', DEL: 'del', STRIKE: 'del', MARK: 'mark', A: 'link'}[node.tagName];
      const children = nodesToTokens(node);
      if (!type || (type === 'link' && !safeHref(node.getAttribute('href') || ''))) tokens.push(...children);
      else tokens.push(type === 'link' ? {type, href: node.getAttribute('href'), children} : {type, children});
    });
    return tokens;
  }
  const linesOf = (doc) => [...doc.children].filter((child) => child.classList.contains('rt-line'));
  const ensureBreak = (line) => {
    if (!line.textContent && !line.querySelector('br')) line.append(element('br'));
  };
  // Sets the kind of a line: the data given, the rest removed.
  const setLine = (line, data) => {
    LINE_DATA.forEach((name) => {
      const value = data[name];
      if (value === undefined || value === null || value === '' || (name === 'type' && value === 'p')) delete line.dataset[name];
      else line.dataset[name] = String(value);
    });
  };
  function lineElement(line, keepSource = false) {
    const node = element('div', 'rt-line');
    setLine(node, line);
    if (line.type === 'code') node.textContent = line.text || '';
    else {
      node.append(...tokensToNodes(parseInline(line.text || '')));
      // What the line was written as: saved again as it was while the line is not changed.
      if (keepSource) node.dataset.src = line.text || '';
    }
    ensureBreak(node);
    return node;
  }
  const readLine = (line) => {
    const data = line.dataset;
    return {
      type: data.type || 'p', level: Number(data.level) || 0, list: data.list || 'ul', style: data.style || '',
      delim: data.delim || '', start: data.start ?? '', prefix: data.prefix || '', task: data.task || '',
      heading: Number(data.heading) || 1, card: data.card || '', lang: data.lang || '', plain: cleanText(line.textContent),
    };
  };
  // The inline Markdown of a line: as it was written while it reads the same, else written again (escaping its
  // characters when its text would read otherwise).
  const lineInline = (line) => {
    const tokens = nodesToTokens(line);
    const source = line.dataset.src;
    if (source !== undefined && signature(parseInline(source)) === signature(tokens)) return source;
    const normal = normalizeTokens(tokens);
    let markdown = tokensToMarkdown(normal);
    if (signature(parseInline(markdown)) !== signature(tokens)) markdown = tokensToMarkdown(normal, true);
    return markdown.trim();
  };
  // Draws every line as it reads (its level, marker, title, card…): only attributes and classes, never its text.
  function decorate(doc, options = {}) {
    const lines = linesOf(doc);
    const read = lines.map(readLine);
    const views = layout(read, options);
    lines.forEach((line, index) => {
      const view = views[index];
      const data = line.dataset;
      if (view.type !== read[index].type) {
        if (view.type === 'p') delete data.type;
        else data.type = view.type;
      }
      const listed = view.type === 'li' || view.type === 'cont' || view.implicit;
      if (listed || (view.type === 'p' && options.implicitBullets)) data.level = String(view.level);
      else delete data.level;
      if (listed) line.style.setProperty('--rt-level', String(view.level));
      else line.style.removeProperty('--rt-level');
      if (!line.getAttribute('style')) line.removeAttribute('style');
      if (view.marker && !(view.type === 'li' && read[index].task)) data.marker = view.marker;
      else delete data.marker;
      if (view.number) data.number = String(view.number);
      else delete data.number;
      if (view.type === 'head') data.label = CARDS[view.card] || CARDS.note;
      else delete data.label;
      if (view.type === 'h') {
        line.setAttribute('role', 'heading');
        line.setAttribute('aria-level', String(read[index].heading));
      } else if (line.getAttribute('role') === 'heading') {
        line.removeAttribute('role');
        line.removeAttribute('aria-level');
      }
      [['rt-title', view.title], ['rt-implicit', view.implicit], ['is-empty', view.empty], ['rt-gap', view.gap],
        ['rt-code-first', view.codeFirst], ['rt-code-last', view.codeLast], ['rt-card-first', view.cardFirst],
        ['rt-card-last', view.cardLast]].forEach(([name, on]) => line.classList.toggle(name, Boolean(on)));
    });
    return views;
  }
  const serialize = (doc, options = {}) => {
    const lines = linesOf(doc).map((line) => ({
      ...readLine(line), inline: line.dataset.type === 'code' ? '' : lineInline(line), text: cleanText(line.textContent),
    }));
    return toMarkdown(lines, layout(lines, options), options);
  };
  // Shows a text in an element of the page (the element keeps its classes).
  function renderInto(container, text, options = {}) {
    container.classList.add('rt-doc');
    container.replaceChildren(...parse(text, options).map((line) => lineElement(line, options.keepSource)));
    decorate(container, options);
    return container;
  }
  const render = (text, options = {}) => renderInto(element('div', options.className || ''), text, options);

  // ---------------------------------------------------------------------------------------------------------------
  // The editor: the lines of the text, editable, with a toolbar; the text area it replaces stays in its form (hidden)
  // with the Markdown, so the forms and fields that read it go on as before.

  const ICONS = {
    code: '<path d="m8 7-5 5 5 5M16 7l5 5-5 5"/>',
    mark: '<path d="m9 11-6 6v3h9l3-3"/><path d="m22 12-4.6 4.6a2 2 0 0 1-2.8 0l-5.2-5.2a2 2 0 0 1 0-2.8L14 4"/>',
    link: '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/>',
    bullets: '<path d="M9 6h12M9 12h12M9 18h12"/><circle cx="4" cy="6" r="1.3" fill="currentColor" stroke="none"/><circle cx="4" cy="12" r="1.3" fill="currentColor" stroke="none"/><circle cx="4" cy="18" r="1.3" fill="currentColor" stroke="none"/>',
    numbers: '<path d="M10 6h11M10 12h11M10 18h11"/><path d="M4 4.5h1.5V9M3.5 9h3.5"/><path d="M3.5 15h2.8a.9.9 0 0 1 .5 1.6L3.5 19.5h3.6"/>',
    tasks: '<path d="m3 6.5 2 2 3.5-3.5M3 16.5l2 2 3.5-3.5"/><path d="M12 7h9M12 17h9"/>',
    outdent: '<path d="M21 6H11M21 12H11M21 18H11"/><path d="m7 8-4 4 4 4"/>',
    indent: '<path d="M21 6H11M21 12H11M21 18H11"/><path d="m3 8 4 4-4 4"/>',
    card: '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M12 8.5v4"/><path d="M12 15.6h.01"/>',
    codeblock: '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="m10 9.5-2.5 2.5 2.5 2.5M14 14.5l2.5-2.5-2.5-2.5"/>',
    divider: '<path d="M3 12h18"/><path d="M7 6.5h10M7 17.5h10" opacity=".45"/>',
    source: '<path d="M4 6h16M4 12h10M4 18h7"/><path d="m16 15 2.5 2.5L16 20M21 15l-2.5 2.5L21 20" transform="translate(-1 -1)"/>',
    help: '<circle cx="12" cy="12" r="9"/><path d="M9.6 9.2a2.5 2.5 0 0 1 4.8.8c0 1.7-2.4 2.2-2.4 3.6"/><path d="M12 17h.01"/>',
  };
  const isMac = /Mac|iPhone|iPad/.test(typeof navigator === 'undefined' ? '' : navigator.platform || navigator.userAgent || '');
  const MOD = isMac ? '⌘' : 'Ctrl+';
  const TOOLS = [
    ['h1', 'H1', `Heading 1 (${MOD}${isMac ? '⌥' : 'Alt+'}1)`], ['h2', 'H2', `Heading 2 (${MOD}${isMac ? '⌥' : 'Alt+'}2)`],
    ['h3', 'H3', `Heading 3 (${MOD}${isMac ? '⌥' : 'Alt+'}3)`], '|',
    ['bold', 'B', `Bold (${MOD}B)`], ['italic', 'I', `Italic (${MOD}I)`], ['strike', 'S', `Strikethrough (${MOD}${isMac ? '⇧' : 'Shift+'}X)`],
    ['code', ICONS.code, `Inline code (${MOD}E)`], ['mark', ICONS.mark, `Highlight (${MOD}${isMac ? '⇧' : 'Shift+'}H)`],
    ['link', ICONS.link, `Link (${MOD}K)`], '|',
    ['bullets', ICONS.bullets, `Bulleted list (${MOD}${isMac ? '⇧' : 'Shift+'}8)`], ['numbers', ICONS.numbers, `Numbered list (${MOD}${isMac ? '⇧' : 'Shift+'}7)`],
    ['tasks', ICONS.tasks, `Task list (${MOD}${isMac ? '⇧' : 'Shift+'}9)`], ['outdent', ICONS.outdent, 'Decrease the level (Shift+Tab)'],
    ['indent', ICONS.indent, 'Increase the level (Tab)'], '|',
    ['card', ICONS.card, 'Card: Note, Tip, Warning, Error…'], ['codeblock', ICONS.codeblock, 'Code block'],
    ['divider', ICONS.divider, 'Divider'], '>',
    ['source', ICONS.source, 'Edit the Markdown'], ['help', ICONS.help, 'How to write it'],
  ];
  const HELP = [
    ['# Heading, ## Heading, ### Heading', 'Headings of three sizes (up to six #)'],
    ['Title: or a line followed by a list', 'The title of what follows it'],
    ['- item, * item', 'A bullet; Tab or two spaces before it nest it'],
    ['1. item, a) item, 1.1. item', 'A numbered item; Enter goes on with the list at its level'],
    ['- [ ] task, - [x] done', 'A task; a click on its box ticks it'],
    ['**bold**, *italic*, ~~struck~~, ==marked==', 'Bold, italic, strikethrough and highlight'],
    ['`code`, [text](https://…)', 'Inline code and a link'],
    ['> [!TIP] Title', 'A card (NOTE, INFO, TIP, SUCCESS, QUESTION, IMPORTANT, WARNING, CAUTION, ERROR); its lines start with >'],
    ['> text', 'A quote'],
    ['```', 'A code block, up to the next ```'],
    ['--- or ----- Text -----', 'A divider, with its text'],
  ];
  // Markdown typed at the start of a line changes it as soon as its space is typed.
  const LINE_RULES = [
    [/^[-*+•]\s$/, () => ({type: 'li', list: 'ul'})],
    [/^(\d{1,3}(?:\.\d{1,3})+)([.)])\s$/, (match) => {
      const parts = match[1].split('.');
      const start = Number(parts.pop());
      return {type: 'li', list: 'ol', style: 'outline', delim: match[2], start, prefix: parts.join('.'), level: parts.length};
    }],
    [/^(\d{1,3})([.)])\s$/, (match) => ({type: 'li', list: 'ol', style: 'decimal', delim: match[2], start: Number(match[1])})],
    [/^([a-z])([.)])\s$|^([A-Z])(\))\s$/, (match) => {
      const letter = match[1] || match[3];
      return {type: 'li', list: 'ol', style: letter === letter.toLowerCase() ? 'lower-alpha' : 'upper-alpha', delim: match[2] || match[4], start: letter.toLowerCase().charCodeAt(0) - 96};
    }],
    [/^(#{1,6})\s$/, (match) => ({type: 'h', heading: match[1].length})],
  ];
  const TASK_RULE = [/^\[([ xX]?)\]\s$/, (match) => ({type: 'li', list: 'ul', task: match[1].trim() ? 'done' : 'open'})];
  LINE_RULES.push(TASK_RULE);
  const INLINE_RULES = [
    [/`([^`]+)`$/, 'code', 0],
    [/(^|[^*\\])\*\*([^*\s](?:[^*]*[^*\s])?)\*\*$/, 'strong', 1],
    [/(^|[^_\\\p{L}\p{N}])__([^_\s](?:[^_]*[^_\s])?)__$/u, 'strong', 1],
    [/(^|[^~\\])~~([^~\s](?:[^~]*[^~\s])?)~~$/, 's', 1],
    [/(^|[^=\\])==([^=\s](?:[^=]*[^=\s])?)==$/, 'mark', 1],
    [/(^|[^*\\])\*([^*\s](?:[^*]*[^*\s])?)\*$/, 'em', 1],
    [/(^|[^_\\\p{L}\p{N}])_([^_\s](?:[^_]*[^_\s])?)_$/u, 'em', 1],
  ];
  const CARD_ORDER = ['note', 'info', 'tip', 'success', 'question', 'important', 'warning', 'caution', 'error', 'quote'];

  const pointOf = (doc, node, offset) => {
    const lines = linesOf(doc);
    if (node === doc) {
      const line = lines[Math.min(offset, lines.length - 1)];
      return line ? [lines.indexOf(line), offset >= lines.length ? line.textContent.length : 0] : null;
    }
    let line = node?.nodeType === 1 ? node : node?.parentElement;
    while (line && line.parentElement !== doc) line = line.parentElement;
    if (!line || !line.classList.contains('rt-line')) return null;
    const range = document.createRange();
    range.setStart(line, 0);
    range.setEnd(node, offset);
    return [lines.indexOf(line), range.toString().length];
  };
  const positionAt = (line, offset) => {
    const walker = document.createTreeWalker(line, NodeFilter.SHOW_TEXT);
    let rest = offset;
    let last = null;
    let node;
    while ((node = walker.nextNode())) {
      if (rest <= node.data.length) return [node, rest];
      rest -= node.data.length;
      last = node;
    }
    return last ? [last, last.data.length] : [line, 0];
  };
  const saveSelection = (doc) => {
    const selection = document.getSelection();
    if (!selection?.rangeCount || !doc.contains(selection.anchorNode)) return null;
    const anchor = pointOf(doc, selection.anchorNode, selection.anchorOffset);
    const focus = pointOf(doc, selection.focusNode, selection.focusOffset);
    return anchor && focus ? {anchor, focus} : null;
  };
  const restoreSelection = (doc, saved) => {
    const lines = linesOf(doc);
    if (!saved || !lines.length) return;
    const at = ([index, offset]) => positionAt(lines[Math.min(index, lines.length - 1)], offset);
    const [anchorNode, anchorOffset] = at(saved.anchor);
    const [focusNode, focusOffset] = at(saved.focus);
    document.getSelection().setBaseAndExtent(anchorNode, anchorOffset, focusNode, focusOffset);
  };
  const placeCaret = (doc, line, offset = 0) => {
    const [node, position] = positionAt(line, offset);
    document.getSelection().collapse(node, position);
  };
  const BLOCKS = 'div, p, ul, ol, li, h1, h2, h3, h4, h5, h6, blockquote, pre, table, tr, td, th';
  const needsNormalize = (doc) => !doc.firstChild
    || [...doc.childNodes].some((node) => !(node.nodeType === 1 && node.classList.contains('rt-line')))
    || Boolean(doc.querySelector(`.rt-line :is(${BLOCKS}, span, font, u, img, [style], [class])`))
    || linesOf(doc).some((line) => !line.firstChild || (line.dataset.type === 'code' && line.querySelector('*:not(br)')));
  // Every child a line, and nothing in a line but text and its formats (what the browser adds while editing).
  function normalize(doc) {
    let pending = null;
    [...doc.childNodes].forEach((node) => {
      if (node.nodeType === 1 && node.classList.contains('rt-line')) {
        pending = null;
        return;
      }
      if (node.nodeType === 1 && node.matches(BLOCKS)) {
        const line = lineElement({type: 'p', text: ''});
        line.replaceChildren(...node.childNodes);
        node.replaceWith(line);
        pending = null;
        return;
      }
      if (node.nodeType !== 1 && node.nodeType !== 3) {
        node.remove();
        return;
      }
      if (!pending) {
        if (node.nodeType === 3 && !node.data.trim()) {
          node.remove();
          return;
        }
        pending = lineElement({type: 'p', text: ''});
        pending.replaceChildren();
        node.before(pending);
      }
      pending.append(node);
    });
    if (!doc.firstChild) doc.append(lineElement({type: 'p', text: ''}));
    linesOf(doc).forEach((line) => {
      line.querySelectorAll('img').forEach((image) => image.remove());
      line.querySelectorAll(`${BLOCKS}, span, font, u`).forEach((node) => node.replaceWith(...node.childNodes));
      line.querySelectorAll('[style], [class]').forEach((node) => {
        node.removeAttribute('style');
        node.removeAttribute('class');
      });
      if (line.dataset.type === 'code' && line.querySelector('*:not(br)')) line.textContent = line.textContent;
      ensureBreak(line);
    });
  }
  // A card begins with its title line (a quote has none) and a line of a card after another card belongs to it, as
  // the text reads once saved.
  const fixCards = (doc) => {
    let previous = null;
    linesOf(doc).forEach((line) => {
      const data = line.dataset;
      if (data.type === 'head' && !data.card) delete data.type;
      if (data.card && data.type !== 'head') {
        if (previous?.dataset.card) {
          if (previous.dataset.card !== data.card) data.card = previous.dataset.card;
        } else if (data.card !== 'quote') data.card = 'quote';
      }
      previous = line;
    });
  };

  // The editors of the page: one listener of the document for all of them, and an editor taken out of the page (the
  // drawer of a call drawn again) is forgotten.
  const editors = new Set();
  const eachEditor = (callback) => editors.forEach((editor) => {
    if (editor.element.isConnected) {
      editor.seen = true;
      callback(editor);
    } else if (editor.seen) editors.delete(editor);
  });
  let listening = false;
  const listen = () => {
    if (listening) return;
    listening = true;
    document.addEventListener('selectionchange', () => eachEditor((editor) => editor.selectionChanged()));
    document.addEventListener('mousedown', (event) => eachEditor((editor) => editor.pressedOutside(event)));
  };

  function attach(textarea, options = {}) {
    if (textarea.richText) return textarea.richText;
    const implicit = Boolean(options.implicitBullets);
    const layoutOptions = {implicitBullets: implicit};
    const valueProperty = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value');
    const source = () => valueProperty.get.call(textarea);
    const setSource = (value) => valueProperty.set.call(textarea, value);
    // A label would send the clicks of the editor to the hidden text area: it becomes a block that looks the same.
    const label = textarea.closest('label');
    let labelText = options.label || textarea.getAttribute('aria-label') || '';
    if (label) {
      const block = element('div', label.className);
      [...label.attributes].filter((attribute) => attribute.name.startsWith('data-')).forEach((attribute) => block.setAttribute(attribute.name, attribute.value));
      labelText = labelText || [...label.childNodes].filter((node) => node.nodeType === 3).map((node) => node.textContent.trim()).join(' ').trim();
      block.append(...label.childNodes);
      label.replaceWith(block);
    }
    const docClass = options.docClass || '';
    const wrapper = element('div', `rt-editor${options.toolbar === 'focus' ? ' has-focus-toolbar' : ''}`);
    const frame = element('div', 'rt-frame');
    const doc = element('div', `rt-doc ${docClass}`.trim());
    doc.contentEditable = 'true';
    doc.spellcheck = true;
    doc.setAttribute('role', 'textbox');
    doc.setAttribute('aria-multiline', 'true');
    doc.setAttribute('aria-label', labelText || 'Text');
    const placeholder = element('div', `rt-placeholder rt-doc ${docClass}`.trim());
    placeholder.setAttribute('aria-hidden', 'true');
    frame.append(placeholder, doc);
    const toolbar = element('div', 'rt-toolbar');
    toolbar.setAttribute('role', 'toolbar');
    toolbar.setAttribute('aria-label', `Format ${labelText || 'the text'}`);
    textarea.before(wrapper);
    wrapper.append(toolbar, frame, textarea);
    textarea.hidden = true;
    textarea.classList.add('rt-source');

    let mode = 'rich';
    let initialHtml = '';
    let initialSource = '';
    let placeholderText = '';
    let dirty = false;
    let changed = false;
    let syncFrame = 0;
    let savedRange = null;
    let undoStack = [];
    let redoStack = [];
    let lastKind = '';
    let lastTime = 0;

    const updateEmpty = () => {
      const lines = linesOf(doc);
      const empty = lines.length <= 1 && !cleanText(doc.textContent).trim() && !lines[0]?.dataset.type && !lines[0]?.dataset.card;
      wrapper.classList.toggle('is-empty', empty && Boolean(placeholderText));
    };
    const flush = () => {
      if (syncFrame) cancelAnimationFrame(syncFrame);
      syncFrame = 0;
      if (!dirty) return;
      dirty = false;
      const markdown = doc.innerHTML === initialHtml ? initialSource : serialize(doc, layoutOptions);
      if (markdown !== source()) {
        setSource(markdown);
        changed = true;
        textarea.dispatchEvent(new Event('input', {bubbles: true}));
      }
    };
    const scheduleSync = () => {
      dirty = true;
      if (!syncFrame) syncFrame = requestAnimationFrame(() => {
        syncFrame = 0;
        flush();
      });
    };
    const load = (text) => {
      const value = String(text ?? '');
      doc.replaceChildren(...parse(value, layoutOptions).map((line) => lineElement(line, true)));
      decorate(doc, layoutOptions);
      setSource(value);
      initialHtml = doc.innerHTML;
      initialSource = value;
      dirty = false;
      undoStack = [];
      redoStack = [];
      updateEmpty();
    };
    const afterChange = () => {
      if (needsNormalize(doc)) {
        const saved = saveSelection(doc);
        normalize(doc);
        restoreSelection(doc, saved);
      }
      fixCards(doc);
      decorate(doc, layoutOptions);
      updateEmpty();
      scheduleSync();
      updateToolbar();
    };

    // Undo and redo: the lines and the selection before each change (the typing of a second, one change).
    const snapshot = () => ({html: doc.innerHTML, selection: saveSelection(doc)});
    const record = (kind = 'op') => {
      const now = Date.now();
      if (kind === 'typing' && lastKind === 'typing' && now - lastTime < 1000) {
        lastTime = now;
        return;
      }
      undoStack.push(snapshot());
      if (undoStack.length > 200) undoStack.shift();
      redoStack = [];
      lastKind = kind;
      lastTime = now;
    };
    const restore = (state) => {
      doc.innerHTML = state.html;
      restoreSelection(doc, state.selection);
      lastKind = '';
      afterChange();
    };
    const undo = () => {
      if (!undoStack.length) return;
      redoStack.push(snapshot());
      restore(undoStack.pop());
    };
    const redo = () => {
      if (!redoStack.length) return;
      undoStack.push(snapshot());
      restore(redoStack.pop());
    };

    const selection = () => document.getSelection();
    const lineOf = (node) => {
      const point = node && doc.contains(node) ? pointOf(doc, node, 0) : null;
      return point ? linesOf(doc)[point[0]] : null;
    };
    // The selection within the editor, from the start of a line to the end of another.
    const editorRange = () => {
      const current = selection();
      if (!current?.rangeCount || !doc.contains(current.anchorNode)) return null;
      const range = current.getRangeAt(0).cloneRange();
      const lines = linesOf(doc);
      if (range.startContainer === doc) range.setStart(lines[Math.min(range.startOffset, lines.length - 1)], 0);
      if (range.endContainer === doc) {
        const line = lines[Math.max(0, Math.min(range.endOffset, lines.length) - 1)];
        range.setEnd(line, line.childNodes.length);
      }
      return range;
    };
    const rangeLines = (range, keepLastAtStart = false) => {
      if (!range) return [];
      const lines = linesOf(doc);
      const start = lineOf(range.startContainer);
      const end = lineOf(range.endContainer);
      if (!start || !end) return start ? [start] : [];
      let chosen = lines.slice(lines.indexOf(start), lines.indexOf(end) + 1);
      // A selection that ends at the start of a line (a triple click) does not take that line.
      if (!keepLastAtStart && chosen.length > 1 && pointOf(doc, range.endContainer, range.endOffset)?.[1] === 0) chosen = chosen.slice(0, -1);
      return chosen;
    };
    const selectedLines = () => rangeLines(editorRange());
    const currentLine = () => {
      const current = selection();
      const point = current?.rangeCount && doc.contains(current.focusNode) ? pointOf(doc, current.focusNode, current.focusOffset) : null;
      return point ? linesOf(doc)[point[0]] : null;
    };
    const caretOffset = () => {
      const current = selection();
      return pointOf(doc, current.focusNode, current.focusOffset)?.[1] ?? 0;
    };
    const textBefore = (line) => {
      const current = selection();
      const range = document.createRange();
      range.setStart(line, 0);
      range.setEnd(current.focusNode, current.focusOffset);
      return range.toString();
    };
    const lineText = (line) => cleanText(line.textContent);
    // A line of text of a long text of Non-Qualified Calls reads as a bullet (also while it is empty).
    const implicitLine = (line) => implicit && !line.dataset.type && !line.dataset.card;
    const isListed = (line) => line.dataset.type === 'li' || line.dataset.type === 'cont' || implicitLine(line);
    const retype = (line, data) => setLine(line, {card: line.dataset.card, ...data});
    const toParagraph = (line) => retype(line, {type: 'p', level: implicit ? line.dataset.level : ''});
    const cleanEmpty = (line) => {
      line.querySelectorAll('strong, b, em, i, s, del, strike, mark, code, a').forEach((node) => {
        if (!node.textContent && !node.querySelector('br')) node.remove();
      });
      ensureBreak(line);
    };
    const lastOfCard = (line) => {
      const next = line.nextElementSibling;
      return !next || next.dataset.card !== line.dataset.card || next.dataset.type === 'head';
    };
    const cardGroup = (line) => {
      const lines = linesOf(doc);
      let start = lines.indexOf(line);
      while (start > 0 && lines[start].dataset.type !== 'head' && lines[start - 1].dataset.card === line.dataset.card) start -= 1;
      let end = lines.indexOf(line);
      while (end + 1 < lines.length && lines[end + 1].dataset.card === line.dataset.card && lines[end + 1].dataset.type !== 'head') end += 1;
      return lines.slice(start, end + 1);
    };
    // An item that changes level takes the kind of list of the items above it at its new level (1. back among 1., 2.).
    const matchSiblings = (line) => {
      if (line.dataset.type !== 'li') return;
      const level = Number(line.dataset.level) || 0;
      const lines = linesOf(doc);
      for (let index = lines.indexOf(line) - 1; index >= 0; index -= 1) {
        const other = lines[index];
        const type = other.dataset.type || 'p';
        if (type === 'cont' || (implicit && type === 'p' && !lineText(other))) continue;
        if ((type !== 'li' && !other.classList.contains('rt-implicit')) || other.dataset.card !== line.dataset.card) return;
        const otherLevel = Number(other.dataset.level) || 0;
        if (otherLevel < level) return;
        if (otherLevel === level) {
          if (type === 'li') {
            retype(line, {type: 'li', level, list: other.dataset.list, style: other.dataset.style, delim: other.dataset.delim,
              prefix: other.dataset.prefix, start: 1, task: line.dataset.task});
          }
          return;
        }
      }
    };
    const unwrapCard = (line) => cardGroup(line).forEach((member) => {
      delete member.dataset.card;
      if (member.dataset.type === 'head') delete member.dataset.type;
    });

    // Splits the line at the caret: the new line below takes what follows the caret and the kind given.
    const splitLine = (line, data) => {
      const current = selection();
      const tail = document.createRange();
      tail.setStart(current.focusNode, current.focusOffset);
      tail.setEnd(line, line.childNodes.length);
      const next = lineElement({text: '', ...data});
      next.replaceChildren(tail.extractContents());
      line.after(next);
      cleanEmpty(line);
      cleanEmpty(next);
      placeCaret(doc, next, 0);
      return next;
    };
    const mergeLines = (target, source) => {
      const offset = target.textContent.length;
      if (source.textContent) target.querySelectorAll(':scope > br').forEach((node) => node.remove());
      target.append(...[...source.childNodes].filter((node) => !(node.nodeName === 'BR' && target.textContent)));
      source.remove();
      if (target.dataset.type === 'code') target.textContent = target.textContent;
      cleanEmpty(target);
      placeCaret(doc, target, offset);
    };
    const deleteSelection = () => {
      const range = editorRange();
      if (!range || range.collapsed) return;
      const lines = rangeLines(range, true);
      if (lines.length <= 1) {
        range.deleteContents();
        if (lines[0]) cleanEmpty(lines[0]);
        selection().collapse(range.startContainer, range.startOffset);
        return;
      }
      const [first, last] = [lines[0], lines[lines.length - 1]];
      const everything = lines.length === linesOf(doc).length && pointOf(doc, range.startContainer, range.startOffset)?.[1] === 0
        && pointOf(doc, range.endContainer, range.endOffset)?.[1] >= last.textContent.length;
      if (everything) {
        doc.replaceChildren(lineElement({type: 'p', text: ''}));
        placeCaret(doc, doc.firstChild, 0);
        return;
      }
      const offset = pointOf(doc, range.startContainer, range.startOffset)[1];
      const head = document.createRange();
      head.setStart(range.startContainer, range.startOffset);
      head.setEnd(first, first.childNodes.length);
      head.deleteContents();
      const tail = document.createRange();
      tail.setStart(last, 0);
      tail.setEnd(range.endContainer, range.endOffset);
      tail.deleteContents();
      lines.slice(1, -1).forEach((line) => line.remove());
      mergeLines(first, last);
      placeCaret(doc, first, offset);
    };
    const insertNodes = (nodes) => {
      const range = editorRange();
      if (!range || !nodes.length) return;
      range.deleteContents();
      const fragment = document.createDocumentFragment();
      fragment.append(...nodes);
      const last = nodes[nodes.length - 1];
      range.insertNode(fragment);
      if (last.nodeType === 3) selection().collapse(last, last.data.length);
      else {
        const after = document.createRange();
        after.setStartAfter(last);
        after.collapse(true);
        selection().removeAllRanges();
        selection().addRange(after);
      }
    };
    // Pasted or dropped text, read as Markdown: one line goes in the line at the caret, more lines as lines of their own.
    const insertMarkdown = (text) => {
      if (!selection()?.rangeCount) return;
      if (!selection().isCollapsed) deleteSelection();
      let line = currentLine();
      if (!line) {
        line = linesOf(doc).at(-1);
        placeCaret(doc, line, line.textContent.length);
      }
      const card = line.dataset.card || '';
      if (line.dataset.type === 'code') {
        const [first, ...rest] = String(text).replace(/\r\n?/g, '\n').split('\n');
        insertNodes([document.createTextNode(first)]);
        let current = line;
        rest.forEach((code) => {
          current = splitLine(current, {type: 'code', card});
          current.prepend(document.createTextNode(code));
          placeCaret(doc, current, code.length);
        });
        return;
      }
      const parsed = parse(text, layoutOptions);
      while (parsed.length > 1 && parsed[parsed.length - 1].type === 'p' && !parsed[parsed.length - 1].text) parsed.pop();
      if (parsed.length === 1 && parsed[0].type === 'p' && !parsed[0].card) {
        insertNodes(tokensToNodes(parseInline(parsed[0].text)));
        return;
      }
      const elements = parsed.map((item) => lineElement({...item, card: card || item.card}));
      const tail = splitLine(line, {type: 'p', card});
      if (!lineText(line)) line.replaceWith(...elements);
      else {
        if (parsed[0].type === 'p' && !parsed[0].card) {
          line.querySelectorAll(':scope > br').forEach((node) => node.remove());
          line.append(...elements.shift().childNodes);
        }
        line.after(...elements);
      }
      const last = elements[elements.length - 1] || line;
      const offset = last.textContent.length;
      if (lineText(tail) && ['p', 'li', 'cont', 'h', 'head'].includes(last.dataset.type || 'p')) mergeLines(last, tail);
      else if (!lineText(tail)) tail.remove();
      placeCaret(doc, last, offset);
    };

    // Enter: a new line of the same kind (a list item at its level); an empty item goes up a level, then out of the
    // list; an empty last line of a card leaves it. Shift+Enter goes on in the same item.
    const enter = (soft) => {
      if (!selection()?.rangeCount) return;
      record('op');
      if (!selection().isCollapsed) deleteSelection();
      const line = currentLine();
      if (!line) return;
      const data = line.dataset;
      const type = data.type || 'p';
      const text = lineText(line);
      const empty = !text.trim();
      const card = data.card || '';
      const level = Number(data.level) || 0;
      const atEnd = caretOffset() >= line.textContent.length;
      if (type === 'code') {
        if (empty && !soft && lastOfCode(line)) {
          retype(line, {type: 'p'});
          afterChange();
          return;
        }
        const indent = text.match(/^ */)[0];
        const next = splitLine(line, {type: 'code', card});
        if (indent) {
          next.prepend(document.createTextNode(indent));
          placeCaret(doc, next, indent.length);
        }
        afterChange();
        return;
      }
      if (type === 'p' && atEnd && text.trim()) {
        const fence = text.trim().match(FENCE);
        const divider = dividerOf(text.trim());
        if (fence || divider !== null) {
          if (fence) retype(line, {type: 'code', lang: fence[2]});
          else retype(line, {type: 'hr'});
          line.replaceChildren(...(fence || !divider ? [element('br')] : tokensToNodes(parseInline(divider))));
          if (fence) placeCaret(doc, line, 0);
          else {
            const next = lineElement({type: 'p', text: '', card});
            line.after(next);
            placeCaret(doc, next, 0);
          }
          afterChange();
          return;
        }
      }
      if (type === 'hr') {
        const next = lineElement({type: 'p', text: '', card, level: implicit ? level : ''});
        line.after(next);
        placeCaret(doc, next, 0);
        afterChange();
        return;
      }
      if (type === 'li') {
        if (empty && !soft) {
          if (level > 0) {
            data.level = String(level - 1);
            data.start = '1';
            matchSiblings(line);
          } else toParagraph(line);
          afterChange();
          return;
        }
        splitLine(line, soft && !implicit
          ? {type: 'cont', level, card}
          : {type: 'li', level, list: data.list, style: data.style, delim: data.delim, prefix: data.prefix,
            start: (Number(data.number) || 0) + 1, task: data.task ? 'open' : '', card});
        afterChange();
        return;
      }
      if (type === 'cont') {
        const item = [...linesOf(doc)].slice(0, linesOf(doc).indexOf(line)).reverse().find((other) => other.dataset.type === 'li');
        const itemData = item?.dataset || {};
        splitLine(line, soft || !item ? {type: 'cont', level, card}
          : {type: 'li', level, list: itemData.list, style: itemData.style, delim: itemData.delim, prefix: itemData.prefix,
            start: (Number(itemData.number) || 0) + 1, task: itemData.task ? 'open' : '', card});
        afterChange();
        return;
      }
      if (type === 'head') {
        splitLine(line, {type: 'p', card});
        afterChange();
        return;
      }
      if (type === 'h') {
        splitLine(line, atEnd ? {type: 'p', card} : {type: 'h', heading: data.heading, card});
        afterChange();
        return;
      }
      if (empty && !soft && card && lastOfCard(line)) {
        delete data.card;
        afterChange();
        return;
      }
      if (empty && !soft && level > 0 && implicitLine(line)) {
        data.level = String(level - 1);
        afterChange();
        return;
      }
      splitLine(line, {type: 'p', card, level: implicit && !card ? level : ''});
      afterChange();
    };
    const lastOfCode = (line) => line.nextElementSibling?.dataset.type !== 'code';
    // Backspace at the start of a line: a list item goes up a level, then becomes text; a heading, divider or code line
    // becomes text; a card title takes its lines out of the card; else the line joins the one above it.
    const backspace = () => {
      const current = selection();
      if (!current?.rangeCount) return false;
      if (!current.isCollapsed) {
        if (rangeLines(editorRange(), true).length < 2) return false;
        record('op');
        deleteSelection();
        afterChange();
        return true;
      }
      const line = currentLine();
      if (!line || cleanText(textBefore(line))) return false;
      const data = line.dataset;
      const type = data.type || 'p';
      const level = Number(data.level) || 0;
      const previous = line.previousElementSibling;
      record('op');
      if (type === 'li' || (implicitLine(line) && level > 0)) {
        if (level > 0) {
          data.level = String(level - 1);
          data.start = '1';
          matchSiblings(line);
        } else toParagraph(line);
      } else if (type === 'h' || type === 'hr' || (type === 'code' && previous?.dataset.type !== 'code')) retype(line, {type: 'p'});
      else if (type === 'head') unwrapCard(line);
      else if (data.card && previous?.dataset.card !== data.card) delete data.card;
      else if (!previous) {
        undoStack.pop();
        return true;
      } else if (!lineText(previous) && (previous.dataset.type || 'p') !== 'code') {
        previous.remove();
        placeCaret(doc, line, 0);
      } else mergeLines(previous, line);
      afterChange();
      return true;
    };
    const forwardDelete = () => {
      const current = selection();
      if (!current?.rangeCount) return false;
      if (!current.isCollapsed) return backspace();
      const line = currentLine();
      if (!line || caretOffset() < line.textContent.length) return false;
      const next = line.nextElementSibling;
      if (!next) return true;
      record('op');
      if (!lineText(line)) {
        line.remove();
        placeCaret(doc, next, 0);
      } else mergeLines(line, next);
      afterChange();
      return true;
    };
    // Tab and Shift+Tab: the level of the selected list items, or two spaces in a code block.
    const changeLevel = (delta) => {
      const lines = selectedLines();
      const listed = lines.filter(isListed);
      const code = lines.filter((line) => line.dataset.type === 'code');
      if (!listed.length && !code.length) return false;
      record('op');
      listed.forEach((line) => {
        line.dataset.level = String(Math.max(0, (Number(line.dataset.level) || 0) + delta));
        if (line.dataset.list === 'ol') line.dataset.start = '1';
        matchSiblings(line);
      });
      if (code.length && !listed.length) {
        const saved = saveSelection(doc);
        if (delta > 0 && code.length === 1 && selection().isCollapsed) insertNodes([document.createTextNode('  ')]);
        else {
          code.forEach((line) => {
            const text = line.textContent;
            line.textContent = delta > 0 ? `  ${text}` : text.replace(/^ {1,2}/, '');
            ensureBreak(line);
          });
          restoreSelection(doc, saved);
        }
      }
      afterChange();
      return true;
    };

    // Markdown typed as it is written: a marker at the start of a line makes it a list item, heading, quote or card;
    // **text**, *text*, ~~text~~, ==text== and `text` become their formats as soon as they are closed.
    const applyInputRules = (typed) => {
      const current = selection();
      if (!current?.isCollapsed || !typed) return;
      const line = currentLine();
      if (!line) return;
      const type = line.dataset.type || 'p';
      if (type === 'code') return;
      if (typed.endsWith(' ') && (type === 'p' || type === 'li')) {
        const before = textBefore(line).replace(/\u00a0/g, ' ');
        if (before.length <= 12) {
          const quote = type === 'p' && before === '> ';
          const card = line.dataset.card && line.dataset.card === 'quote' && !line.previousElementSibling?.dataset.card
            ? before.match(/^\[!([A-Za-z][\w-]*)\]\s$/) : null;
          const rule = type === 'p' ? LINE_RULES.find(([pattern]) => pattern.test(before)) : TASK_RULE[0].test(before) && !line.dataset.task ? TASK_RULE : null;
          if (quote || card || rule) {
            record('op');
            const remove = document.createRange();
            remove.setStart(line, 0);
            remove.setEnd(current.focusNode, current.focusOffset);
            remove.deleteContents();
            if (quote) line.dataset.card = 'quote';
            else if (card) {
              const name = card[1].toLowerCase();
              const kind = CARDS[CARD_ALIASES[name] || name] ? CARD_ALIASES[name] || name : 'note';
              cardGroup(line).forEach((member) => { member.dataset.card = kind; });
              line.dataset.type = 'head';
            } else if (type === 'li') line.dataset.task = rule[1](before.match(rule[0])).task;
            else {
              const data = rule[1](before.match(rule[0]));
              retype(line, {...data, level: data.level ?? (implicit ? Number(line.dataset.level) || 0 : 0)});
            }
            cleanEmpty(line);
            placeCaret(doc, line, 0);
            return;
          }
        }
      }
      const node = current.focusNode;
      if (node?.nodeType !== 3 || node.parentElement.closest('code')) return;
      const caret = current.focusOffset;
      // The formats closed by the characters typed (several when they were inserted at once), from the last one.
      const limit = Math.max(0, caret - typed.length);
      const inside = (tag) => node.parentElement.closest(tag === 'strong' ? 'strong, b' : tag === 'em' ? 'em, i' : tag);
      let end = caret;
      let caretAt = null;
      while (end > limit) {
        let found = null;
        for (let at = end; at > limit && !found; at -= 1) {
          const before = node.data.slice(0, at);
          for (const [pattern, tag, prefixGroup] of INLINE_RULES) {
            const match = before.match(pattern);
            if (match && !inside(tag)) {
              found = {at, tag, start: match.index + (prefixGroup ? match[1].length : 0), inner: match[prefixGroup ? 2 : 1]};
              break;
            }
          }
        }
        if (!found) break;
        if (!caretAt) record('op');
        const rest = node.splitText(found.at);
        node.data = node.data.slice(0, found.start);
        node.after(element(found.tag, '', found.inner));
        // The caret where it was, out of the format (behind a character of no width, so the browser keeps it there).
        if (!caretAt) {
          rest.data = `\u200b${rest.data}`;
          caretAt = [rest, 1 + caret - found.at];
        }
        end = found.start;
      }
      if (caretAt) selection().collapse(...caretAt);
    };

    // The commands of the toolbar and of the keys.
    const exec = (command) => {
      record('op');
      document.execCommand('styleWithCSS', false, false);
      document.execCommand(command);
      afterChange();
    };
    const toggleInline = (tag) => {
      const range = editorRange();
      if (!range) return;
      const within = (node) => {
        const found = (node.nodeType === 1 ? node : node.parentElement)?.closest(tag);
        return found && doc.contains(found) ? found : null;
      };
      record('op');
      const existing = [within(range.startContainer), within(range.endContainer)].filter(Boolean);
      if (existing.length) {
        const saved = saveSelection(doc);
        new Set(existing).forEach((node) => node.replaceWith(...node.childNodes));
        restoreSelection(doc, saved);
        afterChange();
        return;
      }
      if (range.collapsed) {
        const node = element(tag, '', '\u200b');
        range.insertNode(node);
        selection().collapse(node.firstChild, 1);
        afterChange();
        return;
      }
      const made = [];
      rangeLines(range).forEach((line) => {
        if (line.dataset.type === 'code') return;
        const part = document.createRange();
        part.selectNodeContents(line);
        if (line.contains(range.startContainer)) part.setStart(range.startContainer, range.startOffset);
        if (line.contains(range.endContainer)) part.setEnd(range.endContainer, range.endOffset);
        if (part.collapsed) return;
        const contents = part.extractContents();
        contents.querySelectorAll(tag).forEach((node) => node.replaceWith(...node.childNodes));
        const node = element(tag);
        if (tag === 'code') node.textContent = contents.textContent;
        else node.append(contents);
        part.insertNode(node);
        made.push(node);
      });
      if (made.length) {
        const chosen = document.createRange();
        chosen.setStartBefore(made[0]);
        chosen.setEndAfter(made[made.length - 1]);
        selection().removeAllRanges();
        selection().addRange(chosen);
      }
      afterChange();
    };
    const setHeading = (heading) => {
      const lines = selectedLines().filter((line) => !['code', 'hr', 'head'].includes(line.dataset.type));
      if (!lines.length) return;
      record('op');
      const all = lines.every((line) => line.dataset.type === 'h' && Number(line.dataset.heading) === heading);
      lines.forEach((line) => (all ? retype(line, {type: 'p'}) : retype(line, {type: 'h', heading})));
      afterChange();
    };
    const setList = (kind) => {
      const lines = selectedLines().filter((line) => !['code', 'hr', 'head'].includes(line.dataset.type));
      if (!lines.length) return;
      record('op');
      const matches = (line) => line.dataset.type === 'li' && (kind === 'task' ? Boolean(line.dataset.task) : line.dataset.list === kind && !line.dataset.task);
      const all = lines.every(matches);
      lines.forEach((line) => {
        if (all) {
          toParagraph(line);
          return;
        }
        const level = isListed(line) ? Number(line.dataset.level) || 0 : 0;
        if (kind === 'task') retype(line, {type: 'li', list: line.dataset.list || 'ul', style: line.dataset.style, delim: line.dataset.delim, start: line.dataset.start, prefix: line.dataset.prefix, task: line.dataset.task || 'open', level});
        else if (kind === 'ol') retype(line, {type: 'li', list: 'ol', style: line.dataset.list === 'ol' ? line.dataset.style : 'decimal', delim: line.dataset.list === 'ol' ? line.dataset.delim : '.', start: line.dataset.list === 'ol' ? line.dataset.start : 1, prefix: line.dataset.prefix, level});
        else retype(line, {type: 'li', list: 'ul', level});
      });
      afterChange();
    };
    const setCard = (kind) => {
      const lines = selectedLines();
      if (!lines.length) return;
      record('op');
      const current = lines[0].dataset.card;
      if (current && lines.every((line) => line.dataset.card === current)) {
        const group = cardGroup(lines[0]);
        if (kind === current || kind === 'none') unwrapCard(lines[0]);
        else {
          const head = group[0].dataset.type === 'head' ? group[0] : null;
          if (kind === 'quote' && head) {
            if (lineText(head)) delete head.dataset.type;
            else head.remove();
          } else if (kind !== 'quote' && !head) group[0].before(lineElement({type: 'head', text: '', card: kind}));
          cardGroup(lines[0]).forEach((line) => { line.dataset.card = kind; });
        }
      } else if (kind !== 'none') {
        lines.forEach((line) => {
          if (line.dataset.type === 'head') delete line.dataset.type;
          line.dataset.card = kind;
        });
        if (kind !== 'quote') lines[0].before(lineElement({type: 'head', text: '', card: kind}));
      }
      afterChange();
    };
    const setCode = () => {
      const lines = selectedLines().filter((line) => !['hr', 'head'].includes(line.dataset.type));
      if (!lines.length) return;
      record('op');
      const saved = saveSelection(doc);
      const all = lines.every((line) => line.dataset.type === 'code');
      lines.forEach((line) => {
        if (all) retype(line, {type: 'p'});
        else {
          const text = lineText(line);
          retype(line, {type: 'code'});
          line.textContent = text;
          ensureBreak(line);
        }
      });
      restoreSelection(doc, saved);
      afterChange();
    };
    const insertDivider = () => {
      const line = currentLine() || linesOf(doc).at(-1);
      record('op');
      const card = line.dataset.card || '';
      const divider = lineElement({type: 'hr', text: '', card});
      if (!lineText(line) && !line.dataset.type) line.before(divider);
      else {
        const next = lineElement({type: 'p', text: '', card});
        line.after(divider, next);
        placeCaret(doc, next, 0);
      }
      afterChange();
    };
    const setLink = (href) => {
      const range = editorRange();
      if (!range) return;
      record('op');
      if (!href) document.execCommand('unlink');
      else if (range.collapsed) {
        const link = element('a', '', href);
        link.setAttribute('href', href);
        insertNodes([link, document.createTextNode('\u200b')]);
      } else document.execCommand('createLink', false, href);
      doc.querySelectorAll('a').forEach((link) => {
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
      });
      afterChange();
    };
    const toggleTask = (line) => {
      record('op');
      line.dataset.task = line.dataset.task === 'done' ? 'open' : 'done';
      afterChange();
    };

    // The toolbar: its buttons keep the selection of the editor (a press never takes the focus from it).
    const buttons = {};
    const popover = element('div', 'rt-popover');
    popover.hidden = true;
    const closePopover = () => {
      popover.hidden = true;
      popover.replaceChildren();
      Object.values(buttons).forEach((button) => button.setAttribute('aria-expanded', 'false'));
    };
    const openPopover = (button, content) => {
      const opening = popover.hidden || button.getAttribute('aria-expanded') !== 'true';
      closePopover();
      if (!opening) return;
      popover.replaceChildren(...content);
      popover.classList.toggle('is-help', button === buttons.help);
      popover.hidden = false;
      button.setAttribute('aria-expanded', 'true');
      popover.style.left = `${Math.max(0, Math.min(button.offsetLeft, toolbar.clientWidth - popover.offsetWidth))}px`;
    };
    const keepRange = () => {
      const current = selection();
      if (savedRange && !(current?.rangeCount && doc.contains(current.anchorNode))) {
        doc.focus({preventScroll: true});
        current.removeAllRanges();
        current.addRange(savedRange);
      } else if (!current?.rangeCount || !doc.contains(current.anchorNode)) {
        doc.focus({preventScroll: true});
        const last = linesOf(doc).at(-1);
        placeCaret(doc, last, last.textContent.length);
      }
    };
    const cardMenu = () => {
      const line = currentLine();
      const items = CARD_ORDER.map((kind) => {
        const item = element('button', 'rt-menu-item');
        item.type = 'button';
        item.dataset.card = kind;
        item.append(element('span', 'rt-menu-swatch'), element('span', '', CARDS[kind]));
        if (line?.dataset.card === kind) item.setAttribute('aria-current', 'true');
        item.addEventListener('mousedown', (event) => event.preventDefault());
        item.addEventListener('click', () => {
          keepRange();
          closePopover();
          setCard(kind);
        });
        return item;
      });
      if (line?.dataset.card) {
        const remove = element('button', 'rt-menu-item is-remove', 'Remove the card');
        remove.type = 'button';
        remove.addEventListener('mousedown', (event) => event.preventDefault());
        remove.addEventListener('click', () => {
          keepRange();
          closePopover();
          setCard('none');
        });
        items.push(remove);
      }
      return items;
    };
    const linkForm = () => {
      const range = savedRange;
      const startNode = range?.startContainer;
      const existing = startNode ? (startNode.nodeType === 1 ? startNode : startNode.parentElement)?.closest('a') : null;
      const form = element('form', 'rt-link-form');
      const input = element('input');
      input.type = 'url';
      input.placeholder = 'https://…';
      input.value = existing && doc.contains(existing) ? existing.getAttribute('href') : '';
      input.setAttribute('aria-label', 'Address of the link');
      const apply = element('button', 'rt-link-apply', existing ? 'Update' : 'Add link');
      apply.type = 'submit';
      form.append(input, apply);
      if (existing && doc.contains(existing)) {
        const remove = element('button', 'rt-link-remove', 'Remove');
        remove.type = 'button';
        remove.addEventListener('click', () => {
          keepRange();
          closePopover();
          setLink('');
        });
        form.append(remove);
      }
      form.addEventListener('submit', (event) => {
        event.preventDefault();
        event.stopPropagation();
        let href = input.value.trim();
        if (href && !/^[a-z][\w+.-]*:|^\/|^#/i.test(href)) href = `https://${href}`;
        if (href && !safeHref(href)) {
          input.setCustomValidity('Use a web address (https://…), a mail address (mailto:…) or a page of the tool (/…).');
          input.reportValidity();
          return;
        }
        keepRange();
        closePopover();
        setLink(href);
      });
      input.addEventListener('input', () => input.setCustomValidity(''));
      window.setTimeout(() => input.focus(), 0);
      return [form];
    };
    const helpCard = () => {
      const table = element('table', 'rt-help');
      HELP.forEach(([syntax, meaning]) => {
        const row = element('tr');
        const written = element('td');
        written.append(element('code', '', syntax));
        row.append(written, element('td', '', meaning));
        table.append(row);
      });
      const note = element('p', 'rt-help-note', 'Use the toolbar or type the Markdown: it changes as you write. Ctrl+Z undoes it.');
      return [note, table];
    };
    const commands = {
      h1: () => setHeading(1), h2: () => setHeading(2), h3: () => setHeading(3),
      bold: () => exec('bold'), italic: () => exec('italic'), strike: () => exec('strikeThrough'),
      code: () => toggleInline('code'), mark: () => toggleInline('mark'),
      link: () => openPopover(buttons.link, linkForm()),
      bullets: () => setList('ul'), numbers: () => setList('ol'), tasks: () => setList('task'),
      outdent: () => changeLevel(-1), indent: () => changeLevel(1),
      card: () => openPopover(buttons.card, cardMenu()), codeblock: setCode, divider: insertDivider,
      source: () => setMode(mode === 'rich' ? 'source' : 'rich'), help: () => openPopover(buttons.help, helpCard()),
    };
    TOOLS.forEach((tool) => {
      if (tool === '|' || tool === '>') {
        toolbar.append(element('span', tool === '|' ? 'rt-separator' : 'rt-spacer'));
        return;
      }
      const [name, face, title] = tool;
      const button = element('button', `rt-tool rt-tool-${name}`);
      button.type = 'button';
      button.title = title;
      button.setAttribute('aria-label', title);
      if (face.startsWith('<')) button.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${face}</svg>`;
      else button.textContent = face;
      if (['link', 'card', 'help'].includes(name)) {
        button.setAttribute('aria-haspopup', 'true');
        button.setAttribute('aria-expanded', 'false');
      } else if (name !== 'outdent' && name !== 'indent' && name !== 'divider') button.setAttribute('aria-pressed', 'false');
      button.addEventListener('mousedown', (event) => event.preventDefault());
      button.addEventListener('click', () => {
        if (name !== 'source' && name !== 'help') {
          if (mode === 'source') return;
          keepRange();
        }
        if (!['link', 'card', 'help'].includes(name)) closePopover();
        commands[name]();
      });
      buttons[name] = button;
      toolbar.append(button);
    });
    toolbar.append(popover);
    const press = (name, on) => buttons[name]?.setAttribute('aria-pressed', String(Boolean(on)));
    function updateToolbar() {
      const current = selection();
      if (mode !== 'rich' || !current?.rangeCount || !doc.contains(current.focusNode)) return;
      const data = currentLine()?.dataset || {};
      const node = current.focusNode.nodeType === 1 ? current.focusNode : current.focusNode.parentElement;
      const within = (selector) => {
        const found = node?.closest(selector);
        return Boolean(found && doc.contains(found) && found !== doc);
      };
      [1, 2, 3].forEach((heading) => press(`h${heading}`, data.type === 'h' && Number(data.heading) === heading));
      press('bold', within('strong, b'));
      press('italic', within('em, i'));
      press('strike', within('s, del, strike'));
      press('code', within('code'));
      press('mark', within('mark'));
      press('bullets', data.type === 'li' && data.list !== 'ol' && !data.task);
      press('numbers', data.type === 'li' && data.list === 'ol');
      press('tasks', data.type === 'li' && Boolean(data.task));
      press('codeblock', data.type === 'code');
      buttons.card?.classList.toggle('is-active', Boolean(data.card));
      buttons.link?.classList.toggle('is-active', within('a'));
    }
    // The Markdown itself, in the text area, and back.
    function setMode(next) {
      if (next === mode) return;
      closePopover();
      if (next === 'source') {
        flush();
        frame.hidden = true;
        textarea.hidden = false;
        HTMLElement.prototype.focus.call(textarea);
      } else {
        const text = source();
        const original = initialSource;
        const originalHtml = initialHtml;
        load(text);
        if (text !== original) {
          initialSource = original;
          initialHtml = originalHtml;
          dirty = true;
        }
        textarea.hidden = true;
        frame.hidden = false;
        focusEditor();
      }
      mode = next;
      wrapper.classList.toggle('is-source', mode === 'source');
      press('source', mode === 'source');
      Object.entries(buttons).forEach(([name, button]) => { button.disabled = mode === 'source' && name !== 'source' && name !== 'help'; });
    }
    const focusEditor = (focusOptions) => {
      if (mode === 'source') {
        HTMLElement.prototype.focus.call(textarea, focusOptions);
        return;
      }
      doc.focus(focusOptions);
      const current = selection();
      if (!current?.rangeCount || !doc.contains(current.anchorNode)) {
        const last = linesOf(doc).at(-1);
        placeCaret(doc, last, last.textContent.length);
      }
    };

    doc.addEventListener('keydown', (event) => {
      if (event.isComposing || event.keyCode === 229) return;
      const mod = event.metaKey || event.ctrlKey;
      const key = event.key.toLowerCase();
      if (event.key === 'Escape' && !popover.hidden) {
        closePopover();
        return;
      }
      if (mod && !event.altKey) {
        const shortcut = {
          z: event.shiftKey ? redo : undo, y: event.ctrlKey && !event.metaKey ? redo : null,
          b: !event.shiftKey ? commands.bold : null, i: !event.shiftKey ? commands.italic : null,
          e: !event.shiftKey ? commands.code : null, k: !event.shiftKey ? () => { keepRange(); commands.link(); } : null,
          x: event.shiftKey ? commands.strike : null, h: event.shiftKey ? commands.mark : null,
        }[key] || (event.shiftKey ? {Digit7: commands.numbers, Digit8: commands.bullets, Digit9: commands.tasks}[event.code] : null);
        if (shortcut) {
          event.preventDefault();
          shortcut();
          return;
        }
        if (event.key === 'Enter') {
          event.preventDefault();
          flush();
          if (options.onSubmit) options.onSubmit();
          else textarea.form?.requestSubmit();
          return;
        }
      }
      if (mod && event.altKey && /^Digit[0-3]$/.test(event.code)) {
        event.preventDefault();
        const heading = Number(event.code.slice(-1));
        if (heading) setHeading(heading);
        else {
          record('op');
          selectedLines().filter((line) => line.dataset.type === 'h').forEach((line) => retype(line, {type: 'p'}));
          afterChange();
        }
        return;
      }
      if (event.key === 'Enter' && !mod && !event.altKey) {
        event.preventDefault();
        enter(event.shiftKey);
        return;
      }
      if (event.key === 'Tab' && !mod && !event.altKey) {
        if (changeLevel(event.shiftKey ? -1 : 1)) event.preventDefault();
        return;
      }
      if (event.key === 'Backspace' && !mod && !event.altKey) {
        if (backspace()) event.preventDefault();
        return;
      }
      if (event.key === 'Delete' && !mod && !event.altKey && forwardDelete()) event.preventDefault();
    });
    doc.addEventListener('beforeinput', (event) => {
      const type = event.inputType;
      if (type === 'historyUndo' || type === 'historyRedo') {
        event.preventDefault();
        (type === 'historyUndo' ? undo : redo)();
        return;
      }
      if (type === 'insertParagraph' || type === 'insertLineBreak') {
        event.preventDefault();
        enter(type === 'insertLineBreak');
        return;
      }
      if (type === 'insertFromPaste' || type === 'insertFromDrop' || type === 'deleteByCut') return;
      if (type.startsWith('format')) {
        record('op');
        return;
      }
      if (event.isComposing) return;
      if (rangeLines(editorRange(), true).length > 1) {
        // A selection over several lines is deleted here, so its lines join as the text reads.
        event.preventDefault();
        record('op');
        deleteSelection();
        const text = type.startsWith('insert') ? event.data ?? event.dataTransfer?.getData('text/plain') ?? '' : '';
        if (text) {
          insertNodes([document.createTextNode(text)]);
          applyInputRules(text);
        }
        afterChange();
        return;
      }
      record('typing');
    });
    doc.addEventListener('input', (event) => {
      if (!event.isComposing && event.inputType === 'insertText') applyInputRules(event.data);
      afterChange();
    });
    doc.addEventListener('compositionend', afterChange);
    doc.addEventListener('paste', (event) => {
      const data = event.clipboardData;
      if (!data) return;
      event.preventDefault();
      const text = data.getData('text/plain');
      // The screenshots pasted in a form with them are attached by the form.
      if (!text || (data.files?.length && options.filesHandledByForm)) return;
      record('op');
      insertMarkdown(text);
      afterChange();
    });
    const selectionMarkdown = () => {
      const range = editorRange();
      const lines = rangeLines(range);
      if (lines.length <= 1) {
        const holder = element('div');
        holder.append(range.cloneContents());
        return lines[0]?.dataset.type === 'code' ? cleanText(holder.textContent) : tokensToMarkdown(normalizeTokens(nodesToTokens(holder)));
      }
      const holder = element('div');
      lines.forEach((line, index) => {
        const part = document.createRange();
        part.selectNodeContents(line);
        if (index === 0) part.setStart(range.startContainer, range.startOffset);
        if (index === lines.length - 1 && line.contains(range.endContainer)) part.setEnd(range.endContainer, range.endOffset);
        const copy = line.cloneNode(false);
        delete copy.dataset.src;
        copy.append(part.cloneContents());
        holder.append(copy);
      });
      return serialize(holder, layoutOptions);
    };
    ['copy', 'cut'].forEach((type) => doc.addEventListener(type, (event) => {
      const current = selection();
      if (!current?.rangeCount || current.isCollapsed) return;
      event.preventDefault();
      event.clipboardData.setData('text/plain', selectionMarkdown());
      if (type === 'cut') {
        record('op');
        deleteSelection();
        afterChange();
      }
    }));
    doc.addEventListener('dragstart', (event) => event.preventDefault());
    doc.addEventListener('dragover', (event) => event.preventDefault());
    doc.addEventListener('drop', (event) => {
      event.preventDefault();
      const text = event.dataTransfer?.getData('text/plain');
      if (!text) return;
      const at = document.caretRangeFromPoint?.(event.clientX, event.clientY);
      const position = at || (() => {
        const point = document.caretPositionFromPoint?.(event.clientX, event.clientY);
        if (!point) return null;
        const range = document.createRange();
        range.setStart(point.offsetNode, point.offset);
        return range;
      })();
      if (position && doc.contains(position.startContainer)) {
        selection().removeAllRanges();
        selection().addRange(position);
      }
      record('op');
      insertMarkdown(text);
      afterChange();
    });
    doc.addEventListener('mousedown', (event) => {
      const line = event.target.closest?.('.rt-line[data-task]');
      if (!line || event.target !== line || !doc.contains(line)) return;
      if (event.clientX - line.getBoundingClientRect().left > parseFloat(getComputedStyle(line).paddingLeft)) return;
      event.preventDefault();
      toggleTask(line);
    });
    // A link opens with Ctrl or ⌘ and a click (a plain click places the caret in it).
    doc.addEventListener('click', (event) => {
      const link = event.target.closest?.('a[href]');
      if (!link || !doc.contains(link)) return;
      event.preventDefault();
      if (event.metaKey || event.ctrlKey) window.open(link.href, '_blank', 'noopener');
    });
    frame.addEventListener('mousedown', (event) => {
      // A click under the last line puts the caret at its end.
      if (event.target !== frame) return;
      event.preventDefault();
      focusEditor();
      const last = linesOf(doc).at(-1);
      placeCaret(doc, last, last.textContent.length);
    });
    const selectionChanged = () => {
      const current = selection();
      if (!current?.rangeCount || !doc.contains(current.anchorNode)) return;
      savedRange = current.getRangeAt(0).cloneRange();
      updateToolbar();
    };
    const pressedOutside = (event) => {
      if (!popover.hidden && !wrapper.contains(event.target)) closePopover();
    };
    wrapper.addEventListener('focusout', (event) => {
      if (wrapper.contains(event.relatedTarget)) return;
      flush();
      if (changed) {
        changed = false;
        textarea.dispatchEvent(new Event('change', {bubbles: true}));
      }
      if (!popover.contains(event.relatedTarget)) closePopover();
    });
    textarea.form?.addEventListener('submit', flush, true);
    textarea.form?.addEventListener('formdata', (event) => {
      flush();
      if (textarea.name) event.formData.set(textarea.name, source());
    });
    textarea.form?.addEventListener('reset', () => window.setTimeout(() => load(source())));

    // The text area keeps working for the code that reads it: its value is the Markdown, and setting it shows the text.
    Object.defineProperty(textarea, 'value', {
      configurable: true,
      get() {
        flush();
        return source();
      },
      set(value) {
        load(value);
      },
    });
    textarea.focus = focusEditor;
    const setPlaceholder = (text) => {
      placeholderText = String(text || '');
      if (placeholderText) renderInto(placeholder, placeholderText, layoutOptions);
      else placeholder.replaceChildren();
      updateEmpty();
    };
    setPlaceholder(options.placeholder ?? textarea.placeholder);
    load(source());
    const controller = {
      element: wrapper, doc, textarea, focus: focusEditor, flush, setPlaceholder,
      getValue: () => textarea.value, setValue: (text) => load(text), selectionChanged, pressedOutside,
    };
    textarea.richText = controller;
    editors.add(controller);
    listen();
    return controller;
  }

  // The texts and text areas of the page marked for it: data-rich-text (data-raw, the text) and
  // textarea[data-rich-editor] ("bullets": every line a bullet; data-rich-class, the class of the text).
  function init(root = document) {
    root.querySelectorAll('[data-rich-text]').forEach((node) => {
      if (node.classList.contains('rt-doc')) return;
      renderInto(node, node.dataset.raw ?? node.textContent, {implicitBullets: node.dataset.richText === 'bullets'});
    });
    root.querySelectorAll('textarea[data-rich-editor]').forEach((textarea) => attach(textarea, {
      implicitBullets: textarea.dataset.richEditor === 'bullets', docClass: textarea.dataset.richClass || '',
      toolbar: textarea.dataset.richToolbar || 'always', filesHandledByForm: textarea.dataset.richFiles === 'form',
    }));
  }

  window.RichText = {
    CARDS, parse, parseInline, inlinePlain, layout, toMarkdown, tokensToMarkdown, normalizeTokens, normalizeText,
    toPlainText, withPlain, render, renderInto, attach, init,
  };
  if (typeof document.querySelectorAll === 'function') {
    init();
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => init());
  }
})();
