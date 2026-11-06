"""The Markdown of a text of Ticket Center (a description, a comment) as HTML for an email, read as the tool shows it
(static/js/core/rich_text.js): each line on its own line, headings, titles (a short line ending with a colon, or before
a list), bullets and numbered items nested by their indent, tasks, quotes and cards, code blocks, dividers and the inline
formats (bold, italic, strikethrough, highlight, code, links and the #<number> of the tickets). Every style is written on
its element: email clients drop style sheets."""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

MAX_TITLE_LENGTH = 80
BULLET = re.compile(r'([-*+·•◦▪–])(?:\s+|$)')
ORDERED = re.compile(r'(\d{1,3})([.)])(?:\s+|$)')
OUTLINE = re.compile(r'(\d{1,3}(?:\.\d{1,3})+)([.)])(?:\s+|$)')
ALPHA = re.compile(r'([a-zA-Z])([.)])(?:\s+|$)')
TASK = re.compile(r'\[([ xX])\](?:\s+|$)')
HEADING = re.compile(r'(#{1,6})(?:\s+(.*?))?\s*$')
FENCE = re.compile(r'(`{3,}|~{3,})\s*([^`\s]*)\s*$')
QUOTE = re.compile(r'>(?:\s|$)')
CARD = re.compile(r'\[!([A-Za-z][\w-]*)\][+-]?(?:\s+(.*))?$')
DIVIDER = re.compile(r'[-=_*]{3,}(?:\s*(.*?)\s*[-=_*]{3,})?$')
ESCAPABLE = re.compile(r'[!-/:-@\[-`{-~·•◦▪–]')
WORD = re.compile(r'[^\W_]')
# #7: the number of a ticket, neither inside a word or a number (a#7, #7a, #7.5) nor after another # or & (&#7;).
REFERENCE = re.compile(r'#([1-9]\d{0,8})(?!\w|[.,]\d)')
BEFORE_REFERENCE = re.compile(r'[\w#&]')
GLYPHS = ('•', '◦', '▪')
# Each kind of card: the title it shows when it has none of its own, its colour and its background.
CARDS = {
    'note': ('Note', '#0969da', '#eef5fd'), 'info': ('Info', '#0b7fab', '#ebf7fc'), 'tip': ('Tip', '#1a7f37', '#edf8f0'),
    'success': ('Success', '#157a3c', '#eaf8ef'), 'question': ('Question', '#0e7490', '#ebf8fa'),
    'important': ('Important', '#8250df', '#f5f0fe'), 'warning': ('Warning', '#a8590a', '#fdf5e6'),
    'caution': ('Caution', '#c2410c', '#fdf0e8'), 'error': ('Error', '#c62828', '#fdeded'), 'quote': ('Quote', '#a3b1bc', '#f6f8fa'),
}
CARD_ALIASES = {
    'hint': 'tip', 'check': 'success', 'done': 'success', 'help': 'question', 'faq': 'question', 'attention': 'warning',
    'danger': 'error', 'failure': 'error', 'fail': 'error', 'bug': 'error', 'abstract': 'info', 'summary': 'info', 'tldr': 'info',
    'todo': 'info', 'example': 'note', 'cite': 'quote',
}
ACCENT, HEADING_COLOUR, MUTED, RULE = '#1e61a3', '#10314a', '#7b8994', '#d6dde3'
MONOSPACE = 'font-family:Menlo,Consolas,monospace'
INDENT = 1.45  # em, a level of a list
HEADING_STYLES = {
    1: 'font-size:1.45em;padding-bottom:.2em;border-bottom:1px solid ' + RULE, 2: 'font-size:1.25em', 3: 'font-size:1.1em',
    4: 'font-size:1em', 5: 'font-size:.92em;letter-spacing:.03em;text-transform:uppercase',
    6: f'color:{MUTED};font-size:.85em;letter-spacing:.04em;text-transform:uppercase',
}


@dataclass
class _Links:
    base_url: str = ''
    tickets: Mapping[int, str] = field(default_factory=dict)


# -- Inline formats ----------------------------------------------------------------------------------------------------
def _before(source: str, index: int) -> str:
    return source[index - 1] if index > 0 else ''


def _run_length(source: str, index: int, char: str) -> int:
    end = index
    while end < len(source) and source[end] == char:
        end += 1
    return end - index


def _code_close(source: str, start: int, run: int) -> int:
    position = start
    while position < len(source):
        if source[position] == '`':
            length = _run_length(source, position, '`')
            if length == run:
                return position
            position += length
        else:
            position += 1
    return -1


def _safe_href(href: str) -> bool:
    # Links open pages of the web, mail or pages of the tool; anything else (javascript:…) stays text.
    return bool(re.match(r'(?:https?://|mailto:)\S+$', href, re.I) or re.match(r'/(?!/)\S*$', href) or re.match(r'#\S*$', href))


def _bare_url(source: str, index: int) -> str | None:
    # A web address written as it is: the punctuation after it ends the sentence, not the link.
    match = re.match(r'https?://[^\s<>"]+', source[index:], re.I)
    if not match:
        return None
    url = match.group(0)
    while re.search(r'[.,:;!?\'"*_~=]$', url) or (url.endswith(')') and url.count('(') < url.count(')')):
        url = url[:-1]
    return url if re.match(r'https?://[^/\s]+\.\S', url, re.I) or re.match(r'https?://localhost', url, re.I) else None


def _link_at(source: str, index: int) -> tuple[str, str, int] | None:
    """[label](href) at index: its label, its address and where it ends."""
    depth, position = 0, index
    while position < len(source):
        char = source[position]
        if char == '\\':
            position += 2
            continue
        if char == '[':
            depth += 1
        elif char == ']':
            depth -= 1
            if not depth:
                break
        position += 1
    if position >= len(source) or source[position + 1:position + 2] != '(' or position == index + 1:
        return None
    end, parens = position + 2, 1
    while end < len(source):
        if source[end] == '(':
            parens += 1
        elif source[end] == ')':
            parens -= 1
            if not parens:
                break
        end += 1
    if end >= len(source):
        return None
    href = re.sub(r'^<(.*)>$', r'\1', re.sub(r'\s+"[^"]*"$', '', source[position + 2:end].strip()))
    return (source[index + 1:position], href, end + 1) if _safe_href(href) else None


def _anchor(href: str, label: str, links: _Links) -> str:
    """A link of the email: the pages of the tool at its address; a link inside the page stays text."""
    if href.startswith('#'):
        return label
    if href.startswith('/'):
        if not links.base_url:
            return label
        href = links.base_url + href
    return f'<a href="{html.escape(href, quote=True)}" style="color:{ACCENT}">{label}</a>'


def _formatted(kind: str, inner: str) -> str:
    if kind == 'strong':
        return f'<strong>{inner}</strong>'
    if kind == 'em':
        return f'<em>{inner}</em>'
    if kind == 'both':
        return f'<em><strong>{inner}</strong></em>'
    if kind == 'del':
        return f'<del style="color:{MUTED}">{inner}</del>'
    return f'<mark style="background:#fff1a8;color:inherit;padding:0 .12em">{inner}</mark>'


def _emphasis_at(source: str, index: int, char: str, run: int, links: _Links, references: bool) -> tuple[str, int] | None:
    """**bold**, *italic*, ***both***, ~~strikethrough~~ and ==highlight== (also with _ and __): the closing run of the
    same length, not after a space; _ never opens or closes inside a word."""
    kind = ({2: 'del' if char == '~' else 'mark'} if char in '~=' else {1: 'em', 2: 'strong', 3: 'both'}).get(run)
    after = source[index + run:index + run + 1]
    if not kind or not after or after.isspace() or (char == '_' and WORD.match(_before(source, index))):
        return None
    position = index + run
    while position < len(source):
        current = source[position]
        if current == '\\':
            position += 2
            continue
        if current == '`':
            length = _run_length(source, position, '`')
            close = _code_close(source, position + length, length)
            position = close + length if close >= 0 else position + length
            continue
        if current == char:
            length = _run_length(source, position, char)
            if length == run and not source[position - 1].isspace() and not (
                    char == '_' and WORD.match(source[position + length:position + length + 1])):
                return _formatted(kind, _inline(source[index + run:position], links, references)), position + length
            position += length
            continue
        position += 1
    return None


def _inline(text: str, links: _Links, references: bool = True) -> str:
    source = str(text or '')
    out: list[str] = []
    plain: list[str] = []

    def flush() -> None:
        if plain:
            out.append(html.escape(''.join(plain)))
            plain.clear()

    index = 0
    while index < len(source):
        char = source[index]
        if char == '\\' and ESCAPABLE.match(source[index + 1:index + 2]):
            plain.append(source[index + 1])
            index += 2
            continue
        if char == '`':
            run = _run_length(source, index, '`')
            close = _code_close(source, index + run, run)
            if close >= 0:
                flush()
                code = source[index + run:close]
                if len(code) > 1 and code.startswith(' ') and code.endswith(' ') and code.strip():
                    code = code[1:-1]
                out.append(f'<code style="padding:.08em .35em;border-radius:5px;background:#f1f4f7;color:#9f1d4b;{MONOSPACE};'
                           f'font-size:.88em">{html.escape(code)}</code>')
                index = close + run
            else:
                plain.append(source[index:index + run])
                index += run
            continue
        if char == '#' and references and links.tickets and links.base_url and not BEFORE_REFERENCE.match(_before(source, index)):
            match = REFERENCE.match(source, index)
            if match and int(match.group(1)) in links.tickets:
                flush()
                number = int(match.group(1))
                out.append(f'<a href="{html.escape(f"{links.base_url}/tickets/{number}", quote=True)}" '
                           f'title="{html.escape(str(links.tickets[number]), quote=True)}" style="color:{ACCENT}">#{number}</a>')
                index = match.end()
                continue
        if char == '[':
            link = _link_at(source, index)
            if link:
                flush()
                # The text of a link is not linked again.
                out.append(_anchor(link[1], _inline(link[0], links, False), links))
                index = link[2]
                continue
        if char == '<':
            auto = re.match(r'<((?:https?://|mailto:)[^\s<>]+)>', source[index:], re.I)
            if auto:
                flush()
                out.append(_anchor(auto.group(1), html.escape(auto.group(1)), links))
                index += len(auto.group(0))
                continue
        if char in 'hH' and not WORD.match(_before(source, index)):
            url = _bare_url(source, index)
            if url:
                flush()
                out.append(_anchor(url, html.escape(url), links))
                index += len(url)
                continue
        if char in '*_~=':
            run = _run_length(source, index, char)
            emphasis = _emphasis_at(source, index, char, run, links, references)
            if emphasis:
                flush()
                out.append(emphasis[0])
                index = emphasis[1]
            else:
                plain.append(source[index:index + run])
                index += run
            continue
        plain.append(char)
        index += 1
    flush()
    return ''.join(out)


def _plain(text: str) -> str:
    return html.unescape(re.sub(r'<[^>]+>', '', _inline(text, _Links(), False)))


# -- Lines -------------------------------------------------------------------------------------------------------------
def _divider(line: str) -> str | None:
    """The text of a divider line (----- Text ----- or ---), or None when the line is not one; ***bold*** stays bold."""
    match = DIVIDER.match(line)
    if not match or re.match(r'(?:\*{1,3}|_{1,3})[^\s*_]', line):
        return None
    return match.group(1) or ''


def _list_item(line: str) -> dict[str, Any] | None:
    if match := BULLET.match(line):
        return {'list': 'ul', 'text': line[match.end():]}
    if match := OUTLINE.match(line):
        parts = match.group(1).split('.')
        start = int(parts.pop())
        return {'list': 'ol', 'style': 'outline', 'delim': match.group(2), 'start': start, 'prefix': '.'.join(parts),
                'depth': len(parts) + 1, 'text': line[match.end():]}
    if match := ORDERED.match(line):
        return {'list': 'ol', 'style': 'decimal', 'delim': match.group(2), 'start': int(match.group(1)), 'text': line[match.end():]}
    if match := ALPHA.match(line):
        letter = match.group(1)
        return {'list': 'ol', 'style': 'lower-alpha' if letter == letter.lower() else 'upper-alpha', 'delim': match.group(2),
                'start': ord(letter.lower()) - 96, 'text': line[match.end():]}
    return None


def _parse(raw_lines: list[str]) -> list[dict[str, Any]]:
    """The lines of a text: p (a line of text, an empty one a blank line), h (a heading), li (an item of a list), cont (a
    line that goes on in the item above it), code (a line of a code block), hr (a divider) and head (the title of a
    card). The lines of a quote or card have its kind (card)."""
    lines: list[dict[str, Any]] = []
    stack: list[int] = []  # The indent of each open level of the list.
    item_level = -1

    def level_for(indent: int, minimum: int = 0) -> int:
        while stack and indent < stack[-1]:
            stack.pop()
        while len(stack) > 1 and stack[-2] == indent:
            stack.pop()
        level = max(minimum, len(stack) if not stack or indent > stack[-1] else len(stack) - 1)
        del stack[level:]
        while len(stack) <= level:
            stack.append(indent)
        return level

    index = 0
    while index < len(raw_lines):
        raw = raw_lines[index].replace('\t', '    ')
        content = raw.strip()
        indent = len(raw) - len(raw.lstrip())
        if fence := FENCE.match(content):
            closing = re.compile(rf'{re.escape(fence.group(1)[0])}{{{len(fence.group(1))},}}\s*$')
            end = index + 1
            while end < len(raw_lines) and not closing.match(raw_lines[end].strip()):
                end += 1
            body = [re.sub(rf'^ {{0,{indent}}}', '', code) for code in raw_lines[index + 1:end]]
            lines.extend({'type': 'code', 'text': code, 'lang': '' if position else fence.group(2)}
                         for position, code in enumerate(body or ['']))
            index = end + 1
            stack.clear()
            item_level = -1
            continue
        if QUOTE.match(content):
            # A quote, or a card when its first line is [!KIND]: its lines without their >, read as any other text.
            inner: list[str] = []
            end = index
            while end < len(raw_lines) and QUOTE.match(raw_lines[end].strip()):
                line = re.sub(r'^>\s?', '', raw_lines[end].strip())
                if end > index and CARD.match(line.strip()):
                    break
                inner.append(line)
                end += 1
            index = end
            stack.clear()
            item_level = -1
            kind = 'quote'
            if head := CARD.match(inner[0].strip()):
                name, title = head.group(1).lower(), (head.group(2) or '').strip()
                kind = CARD_ALIASES.get(name, name)
                if kind not in CARDS:
                    title, kind = title or name.capitalize(), 'note'
                lines.append({'type': 'head', 'text': title, 'card': kind})
                inner.pop(0)
            lines.extend({**line, 'card': kind} for line in _parse(inner))
            continue
        index += 1
        if not content:
            lines.append({'type': 'p', 'text': '', 'level': 0})
            stack.clear()
            item_level = -1
            continue
        if heading := HEADING.match(content):
            lines.append({'type': 'h', 'heading': len(heading.group(1)), 'text': re.sub(r'(?:^|\s+)#+$', '', heading.group(2) or '')})
            stack.clear()
            item_level = -1
            continue
        divider = _divider(content)
        if divider is not None:
            lines.append({'type': 'hr', 'text': divider})
            stack.clear()
            item_level = -1
            continue
        if item := _list_item(content):
            level = level_for(indent, item.get('depth', 1) - 1)
            item_level = level
            task = TASK.match(item['text'])
            lines.append({'type': 'li', 'level': level, 'list': item['list'], 'style': item.get('style', ''),
                          'delim': item.get('delim', ''), 'start': item.get('start', ''), 'prefix': item.get('prefix', ''),
                          'task': ('open' if task.group(1) == ' ' else 'done') if task else '',
                          'text': item['text'][task.end():] if task else item['text']})
            continue
        if item_level >= 0 and indent > 0:
            lines.append({'type': 'cont', 'level': item_level, 'text': content})
            continue
        lines.append({'type': 'p', 'text': content, 'level': 0})
        stack.clear()
        item_level = -1
    return lines


def _letters(number: int, upper: bool) -> str:
    rest, text = max(1, number), ''
    while rest > 0:
        rest -= 1
        text = chr(97 + rest % 26) + text
        rest //= 26
    return text.upper() if upper else text


def _counter_text(counter: dict[str, Any]) -> str:
    style = counter['style']
    return _letters(counter['number'], style == 'upper-alpha') if style.endswith('alpha') else str(counter['number'])


def _layout(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """How each line reads: its level, the marker of its bullet or its number, whether it is a title, its card and the
    spacing between a list and the text around it."""
    views: list[dict[str, Any]] = []
    context, counters, list_level, paragraph = 0, [], -1, False
    for index, line in enumerate(lines):
        previous = lines[index - 1] if index else None
        card = line.get('card', '')
        if previous is None or card != previous.get('card', '') or line['type'] == 'head':
            context, counters, list_level, paragraph = context + 1, [], -1, False
        text = '' if line['type'] == 'code' else _plain(line['text']).strip()
        following = lines[index + 1] if index + 1 < len(lines) else None
        before_list = bool(following and following['type'] == 'li' and following.get('card', '') == card)
        view = {'type': line['type'], 'level': 0, 'marker': '', 'title': False, 'empty': not text, 'card': card, 'context': context}
        kind = line['type']
        if kind == 'cont' and list_level >= 0:
            view['level'] = list_level
        elif kind == 'li':
            depth = len([part for part in str(line['prefix']).split('.') if part]) + 1 if line['style'] == 'outline' else 1
            level = max(0, min(int(line['level']), max(list_level + 1, depth - 1)))
            view['level'] = level
            counters = (counters + [None] * (level + 1))[:level + 1]
            if line['list'] == 'ol':
                style, delim = line['style'] or 'decimal', line['delim'] or '.'
                counter = counters[level]
                start = int(line['start']) if line['start'] != '' else 1
                number = counter['number'] + 1 if counter and counter['style'] == style and counter['delim'] == delim else start
                counters[level] = {'style': style, 'delim': delim, 'number': number}
                if style == 'outline':
                    prefix = [part for part in str(line['prefix']).split('.') if part]
                    parts = [_counter_text(counters[depth]) if counters[depth] else prefix[depth] for depth in range(level)
                             if counters[depth] or depth < len(prefix)]
                    view['marker'] = f"{'.'.join([*parts, str(number)])}{delim}"
                else:
                    view['marker'] = f'{_counter_text(counters[level])}{delim}'
            else:
                view['marker'] = GLYPHS[level % len(GLYPHS)]
            list_level = level
            view['title'] = text.endswith(':') and len(text) <= MAX_TITLE_LENGTH
            paragraph = False
        elif kind in {'p', 'cont'}:
            view['type'] = 'p'
            if text:
                view['title'] = len(text) <= MAX_TITLE_LENGTH and (text.endswith(':') or before_list) and (
                    text.endswith(':') or not paragraph)
                paragraph = not view['title']
            else:
                paragraph = False
            counters, list_level = [], -1
        else:
            counters, list_level, paragraph = [], -1, False
        views.append(view)

    def kind_of(view: dict[str, Any]) -> str:
        if view['type'] in {'li', 'cont'}:
            return 'list'
        return 'text' if view['type'] == 'p' and not view['empty'] and not view['title'] else ''

    for index, view in enumerate(views):
        previous = views[index - 1] if index else None
        view['gap'] = bool(previous and previous['context'] == view['context'] and kind_of(view) and kind_of(previous)
                           and kind_of(view) != kind_of(previous))
    return views


# -- HTML --------------------------------------------------------------------------------------------------------------
def _line_html(line: dict[str, Any], view: dict[str, Any], links: _Links, first: bool) -> str:
    content = _inline(line.get('text', ''), links)
    kind = view['type']
    styles = ['margin-top:.45em'] if view['gap'] else []
    if kind == 'h':
        margin = '0 0 .3em' if first else '.8em 0 .3em'
        return (f'<div style="margin:{margin};color:{HEADING_COLOUR};font-weight:bold;line-height:1.3;'
                f'{HEADING_STYLES[int(line["heading"])]}">{content or "&nbsp;"}</div>')
    if kind == 'hr':
        return (f'<div style="margin:.7em 0;padding-bottom:.2em;border-bottom:1px solid {RULE};color:{MUTED};font-size:.82em;'
                f'font-weight:bold;letter-spacing:.04em;text-transform:uppercase">{content or "&nbsp;"}</div>')
    if kind == 'head':
        return f'<div style="color:{CARDS[view["card"]][1]};font-weight:bold">{content or CARDS[view["card"]][0]}</div>'
    if view['card'] == 'quote':
        styles.append('color:#4b5d6b;font-style:italic')
    if view['title']:
        styles.append(f'color:{ACCENT};font-weight:bold')
        if kind == 'p' and not first:
            styles.append('margin-top:.6em')
    if kind == 'li':
        marker = {'open': '☐', 'done': '☑'}.get(line['task'], view['marker'])
        styles.append(f'padding-left:{(view["level"] + 1) * INDENT:g}em;text-indent:-{INDENT:g}em')
        return (f'<div style="{";".join(styles)}"><span style="display:inline-block;min-width:{INDENT:g}em;text-indent:0;'
                f'color:{ACCENT};font-weight:bold">{marker}&nbsp;</span>{content}</div>')
    if kind == 'cont':
        styles.append(f'padding-left:{(view["level"] + 1) * INDENT:g}em')
    return f'<div style="{";".join(styles)}">{content or "&nbsp;"}</div>' if styles else f'<div>{content or "&nbsp;"}</div>'


def _lines_html(pairs: list[tuple[dict[str, Any], dict[str, Any]]], links: _Links, first: bool) -> str:
    out: list[str] = []
    index = 0
    while index < len(pairs):
        line, view = pairs[index]
        if view['type'] == 'code':
            end = index
            while end < len(pairs) and pairs[end][1]['type'] == 'code' and pairs[end][1]['context'] == view['context']:
                end += 1
            background = '#ffffff' if view['card'] else '#f1f4f7'
            out.append(f'<pre style="margin:.4em 0;padding:.55em .9em;border-radius:9px;background:{background};color:#1f2d3a;'
                       f'{MONOSPACE};font-size:.85em;line-height:1.5;white-space:pre-wrap">'
                       + html.escape('\n'.join(pair[0]['text'] for pair in pairs[index:end])) + '</pre>')
            index = end
        else:
            out.append(_line_html(line, view, links, first and index == 0))
            index += 1
    return ''.join(out)


def markdown_html(text: object, *, base_url: str = '', tickets: Mapping[int, str] | None = None) -> str:
    """The HTML of a Markdown text; ``base_url`` is the address of the tool for its links, and ``tickets`` the title of
    each ticket a #<number> of the text links to."""
    lines = _parse(str(text or '').replace('\r\n', '\n').replace('\r', '\n').split('\n'))
    views = _layout(lines)
    links = _Links(str(base_url or '').rstrip('/'), dict(tickets or {}))
    out: list[str] = []
    index = 0
    while index < len(lines):
        card, context = views[index]['card'], views[index]['context']
        end = index
        while end < len(lines) and views[end]['card'] == card and (not card or views[end]['context'] == context):
            end += 1
        inner = _lines_html(list(zip(lines[index:end], views[index:end])), links, not index and not card)
        if card:
            colour, background = CARDS[card][1:]
            inner = (f'<div style="margin:.4em 0;padding:.45em .9em .45em 1em;border-left:4px solid {colour};'
                     f'background:{background}">{inner}</div>')
        out.append(inner)
        index = end
    return ''.join(out)
