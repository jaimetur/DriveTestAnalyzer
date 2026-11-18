"""The Help chapters as a Word document (and, through LibreOffice, as PDF).

A Help page exports its own chapter or the whole documentation. The Markdown of the chapters is written with the
subset the Help uses: headings numbered as the Help viewer numbers them (doc_view.html, numberHelpSections), paragraphs
with bold, italic, code and links, nested bullet and numbered lists, tables, callouts, blockquotes, code blocks, keys
and images of the application. Anything else is kept as plain text.
"""

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass, field
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

PROJECT_ROOT = Path(__file__).resolve().parents[3]
STATIC_ROOT = PROJECT_ROOT / 'src' / 'web_interface' / 'static'
APP_TITLE = 'DriveTest Analyzer'
# The index of a chapter (its former and current heading): left out of the documents, which have a table of contents.
INDEX_SECTIONS = {'in this guide', 'main topics in this guide'}
PRESENTATION_SECTIONS = {'presentation', 'presentations'}
# The H2 sections the Help viewer leaves without a number (and the subsections below them).
UNNUMBERED_SECTIONS = INDEX_SECTIONS | PRESENTATION_SECTIONS
HELP_HOME_DOCUMENT = 'help.md'
CODE_FONT = 'Consolas'
CALLOUTS = {
    'NOTE': ('Note', 'E8F0FB', '1F5FAD'),
    'TIP': ('Tip', 'E7F5EC', '1E7A3D'),
    'IMPORTANT': ('Important', 'F1EAFB', '6B3FA0'),
    'WARNING': ('Warning', 'FDF3E1', '9A5B00'),
    'CAUTION': ('Caution', 'FBE9E9', 'A61B1B'),
}
QUOTE_FILL = 'F3F3F3'
CODE_FILL = 'F2F2F2'
HEADER_FILL = 'DCE6F2'
PRESENTATIONS_NOTE = 'Presentations: open this chapter in the Help to watch them.'
# Escaped Markdown characters, kept aside while the inline syntax is read.
ESCAPES = {'\\*': '', '\\|': '', '\\_': '', '\\`': '', '\\[': '', '\\]': '',
           '\\<': '', '\\>': '', '\\#': '', '\\\\': ''}
UNESCAPES = {value: key[1] for key, value in ESCAPES.items()}
# Inline HTML the Help writes: dropped, keeping the text inside (the keys and images are handled on their own).
HTML_TAGS = re.compile(r'</?(?:span|p|div|sup|sub|small|b|strong|em|i|u|a|br|font|center|details|summary)\b[^>]*>',
                       re.IGNORECASE)
IMAGE_TAG = re.compile(r'<img\b[^>]*\bsrc=["\']([^"\']+)["\'][^>]*>', re.IGNORECASE)
IMAGE_MARKDOWN = re.compile(r'!\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)')
INLINE = re.compile(
    r'`([^`]+)`'
    r'|<kbd>(.*?)</kbd>'
    r'|\[([^\]]+)\]\(([^)\s]*)(?:\s+"[^"]*")?\)'
    r'|\*\*(.+?)\*\*'
    r'|(?<![\w*])\*(?![\s*])(.+?)(?<![\s*])\*(?![\w*])',
    re.IGNORECASE,
)
LIST_ITEM = re.compile(r'^(\s*)([-*+]|\d+[.)])\s+(.*)$')
HEADING = re.compile(r'^(#{1,6})\s+(.+?)\s*#*\s*$')
TABLE_SEPARATOR = re.compile(r'^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$')
FENCE = re.compile(r'^(\s*)(```+|~~~+)\s*([\w-]*)')
RULE = re.compile(r'^\s*([-*_])(\s*\1){2,}\s*$')


@dataclass
class Chapter:
    """A Help chapter to export: its file, title (as the Help navigation names it) and Markdown."""
    file: str
    title: str
    content: str


@dataclass
class _Context:
    numbered: bool
    numbers: dict[str, str] = field(default_factory=dict)
    seen: dict[str, int] = field(default_factory=dict)
    chapter: int = 1
    bookmarks: list[int] = field(default_factory=lambda: [0])


def heading_id(text: str) -> str:
    """The id the Help viewer gives a heading (as markdown_heading_id in the application)."""
    base = re.sub(r'<[^>]*>', ' ', str(text or ''))
    base = re.sub(r'`([^`]+)`', r'\1', base)
    base = re.sub(r'\*\*([^*]+)\*\*', r'\1', base)
    base = re.sub(r'\*([^*]+)\*', r'\1', base)
    base = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', base)
    base = re.sub(r'&[a-z]+;', ' ', base, flags=re.IGNORECASE).lower()
    base = re.sub(r'[^a-z0-9\s-]', ' ', base).strip()
    return re.sub(r'-+', '-', re.sub(r'\s+', '-', base)) or 'section'


def plain_text(text: str) -> str:
    """Inline Markdown as its text only."""
    text = _escape(text)
    text = IMAGE_MARKDOWN.sub('', text)
    text = re.sub(r'<kbd>(.*?)</kbd>', r'\1', text, flags=re.IGNORECASE)
    text = HTML_TAGS.sub('', IMAGE_TAG.sub('', text))
    text = re.sub(r'`([^`]+)`', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'(?<![\w*])\*(?![\s*])(.+?)(?<![\s*])\*(?![\w*])', r'\1', text)
    return _unescape(html.unescape(text)).strip()


def _escape(text: str) -> str:
    for key, value in ESCAPES.items():
        text = text.replace(key, value)
    return text


def _unescape(text: str) -> str:
    for key, value in UNESCAPES.items():
        text = text.replace(key, value)
    return text


def section_numbers(content: str, numbered: bool = True) -> dict[str, str]:
    """The number of each section (H2) and subsection (H3) of a chapter by heading id, as the Help viewer shows them."""
    numbers: dict[str, str] = {}
    seen: dict[str, int] = {}
    section = subsection = 0
    numbering = False
    in_code = False
    for line in content.splitlines():
        if FENCE.match(line):
            in_code = not in_code
            continue
        match = None if in_code else HEADING.match(line.strip())
        if not match:
            continue
        level, text = len(match.group(1)), match.group(2)
        base = heading_id(text)
        seen[base] = seen.get(base, 0) + 1
        anchor = base if seen[base] == 1 else f'{base}-{seen[base]}'
        if not numbered:
            continue
        if level == 2:
            numbering = plain_text(text).lower() not in UNNUMBERED_SECTIONS
            if numbering:
                section, subsection = section + 1, 0
                numbers[anchor] = f'{section}'
        elif level == 3 and numbering and section:
            subsection += 1
            numbers[anchor] = f'{section}.{subsection}'
    return numbers


# --- Word helpers -------------------------------------------------------------------------------------------------


def _shade(element: Any, fill: str) -> None:
    properties = element.get_or_add_tcPr() if element.tag == qn('w:tc') else element.get_or_add_rPr()
    shading = OxmlElement('w:shd')
    shading.set(qn('w:val'), 'clear')
    shading.set(qn('w:color'), 'auto')
    shading.set(qn('w:fill'), fill)
    properties.append(shading)


def _box(run: Any) -> None:
    border = OxmlElement('w:bdr')
    for key, value in (('w:val', 'single'), ('w:sz', '4'), ('w:space', '0'), ('w:color', '999999')):
        border.set(qn(key), value)
    run._element.get_or_add_rPr().append(border)


def _code_run(paragraph: Any, text: str, size: float | None = None) -> Any:
    run = paragraph.add_run(text)
    run.font.name = CODE_FONT
    run.font.size = Pt(size or 9)
    _shade(run._element, CODE_FILL)
    return run


def _hyperlink(paragraph: Any, url: str, text: str, bold: bool, italic: bool) -> None:
    relation = paragraph.part.relate_to(url, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
    link = OxmlElement('w:hyperlink')
    link.set(qn('r:id'), relation)
    run = paragraph.add_run(text)
    run.bold, run.italic = bold or None, italic or None
    run.font.color.rgb = RGBColor(0x1F, 0x5F, 0xAD)
    run.font.underline = True
    link.append(run._element)
    paragraph._p.append(link)


def _bookmark(paragraph: Any, name: str, number: int) -> None:
    start = OxmlElement('w:bookmarkStart')
    start.set(qn('w:id'), str(number))
    start.set(qn('w:name'), name)
    end = OxmlElement('w:bookmarkEnd')
    end.set(qn('w:id'), str(number))
    paragraph._p.insert(0, start)
    paragraph._p.append(end)


def _internal_link(paragraph: Any, anchor: str, text: str, bold: bool = False, size: float | None = None) -> None:
    link = OxmlElement('w:hyperlink')
    link.set(qn('w:anchor'), anchor)
    run = paragraph.add_run(text)
    run.font.color.rgb = RGBColor(0x1F, 0x5F, 0xAD)
    run.bold = bold or None
    if size:
        run.font.size = Pt(size)
    link.append(run._element)
    paragraph._p.append(link)


def _add_text(paragraph: Any, text: str, bold: bool, italic: bool) -> None:
    text = _unescape(html.unescape(text))
    if not text:
        return
    run = paragraph.add_run(text)
    if bold:
        run.bold = True
    if italic:
        run.italic = True


def add_inline(paragraph: Any, text: str, context: _Context | None = None, bold: bool = False, italic: bool = False,
               escaped: bool = False) -> None:
    """Inline Markdown into a paragraph: bold, italic, code, keys, links and the text of inline HTML."""
    if not escaped:
        text = HTML_TAGS.sub('', IMAGE_TAG.sub('', IMAGE_MARKDOWN.sub('', _escape(text))))
    position = 0
    for match in INLINE.finditer(text):
        _add_text(paragraph, text[position:match.start()], bold, italic)
        position = match.end()
        code, key, link_text, url, strong, emphasis = match.groups()
        if code is not None:
            _code_run(paragraph, _unescape(code))
        elif key is not None:
            run = _code_run(paragraph, f' {_unescape(html.unescape(key))} ', 8.5)
            _box(run)
        elif link_text is not None:
            if re.match(r'^(https?:|mailto:)', url or '', re.IGNORECASE):
                _hyperlink(paragraph, url, plain_text(_unescape(link_text)), bold, italic)
                continue
            add_inline(paragraph, link_text, context, bold, italic, escaped=True)
        elif strong is not None:
            add_inline(paragraph, strong, context, True, italic, escaped=True)
        else:
            add_inline(paragraph, emphasis, context, bold, True, escaped=True)
    _add_text(paragraph, text[position:], bold, italic)


def _local_image(source: str) -> Path | None:
    normalized = source.strip().replace('\\', '/').lstrip('./')
    for prefix, root in (('src/web_interface/static/', STATIC_ROOT), ('web_interface/static/', STATIC_ROOT),
                         ('static/', STATIC_ROOT), ('/static/', STATIC_ROOT)):
        if normalized.startswith(prefix.lstrip('/')):
            candidate = (root / normalized[len(prefix.lstrip('/')):]).resolve()
            try:
                candidate.relative_to(STATIC_ROOT.resolve())
            except ValueError:
                return None
            return candidate if candidate.is_file() and candidate.suffix.lower() in {'.png', '.jpg', '.jpeg', '.gif'} else None
    return None


# --- Blocks ---------------------------------------------------------------------------------------------------------


class _Writer:
    def __init__(self, document: Any) -> None:
        self.document = document

    def paragraph(self, container: Any, style: str | None = None) -> Any:
        paragraph = container.add_paragraph()
        if style:
            try:
                paragraph.style = self.document.styles[style]
            except KeyError:
                pass
        return paragraph

    def box(self, container: Any, fill: str) -> Any:
        table = container.add_table(rows=1, cols=1) if hasattr(container, 'add_table') else None
        if table is None:
            return container
        try:
            table.style = self.document.styles['Table Grid']
        except KeyError:
            pass
        cell = table.cell(0, 0)
        _shade(cell._tc, fill)
        return cell

    @staticmethod
    def tidy_cell(cell: Any) -> None:
        """A cell without the empty paragraph it starts with, when it holds something else."""
        paragraphs = cell.paragraphs
        if len(cell._tc.xpath('./w:p | ./w:tbl')) > 1 and paragraphs and not paragraphs[0].text and not paragraphs[0].runs:
            paragraphs[0]._element.getparent().remove(paragraphs[0]._element)

    def blocks(self, container: Any, lines: list[str], context: _Context, in_cell: bool = False) -> None:
        index = 0
        while index < len(lines):
            line = lines[index]
            stripped = line.strip()
            if not stripped:
                index += 1
                continue
            fence = FENCE.match(line)
            if fence:
                marker = fence.group(2)
                body: list[str] = []
                index += 1
                while index < len(lines) and not lines[index].strip().startswith(marker[:3]):
                    body.append(lines[index])
                    index += 1
                index += 1
                self.code(container, fence.group(3).lower(), body)
                continue
            heading = HEADING.match(stripped)
            if heading:
                index += 1
                if self.heading(container, len(heading.group(1)), heading.group(2), context, in_cell):
                    index = _section_end(lines, index)
                continue
            if stripped.startswith('|') and index + 1 < len(lines) and TABLE_SEPARATOR.match(lines[index + 1]):
                rows = [stripped]
                index += 2
                while index < len(lines) and lines[index].strip().startswith('|'):
                    rows.append(lines[index].strip())
                    index += 1
                self.table(container, rows, context)
                continue
            if stripped.startswith('>'):
                quoted: list[str] = []
                while index < len(lines) and lines[index].strip().startswith('>'):
                    quoted.append(re.sub(r'^\s*>\s?', '', lines[index]))
                    index += 1
                self.quote(container, quoted, context)
                continue
            if LIST_ITEM.match(line) and not RULE.match(line):
                items: list[tuple[int, str, str]] = []
                while index < len(lines):
                    item = LIST_ITEM.match(lines[index])
                    if item and not RULE.match(lines[index]):
                        items.append((len(item.group(1).expandtabs(4)), item.group(2), item.group(3)))
                    elif not lines[index].strip() and items and self.list_goes_on(lines, index):
                        pass
                    elif lines[index].strip() and items and (lines[index][:1].isspace() or not self.starts_block(lines, index)):
                        indent, marker, text = items[-1]
                        items[-1] = (indent, marker, f'{text} {lines[index].strip()}')
                    else:
                        break
                    index += 1
                self.list(container, items, context)
                continue
            if RULE.match(stripped):
                index += 1
                continue
            text_lines = [stripped]
            index += 1
            while index < len(lines) and lines[index].strip() and not self.starts_block(lines, index):
                text_lines.append(lines[index].strip())
                index += 1
            self.text(container, ' '.join(text_lines), context)

    @staticmethod
    def list_goes_on(lines: list[str], index: int) -> bool:
        """Whether a list goes on after blank lines: its next line is another item of it."""
        following = next((position for position in range(index, len(lines)) if lines[position].strip()), None)
        return following is not None and bool(LIST_ITEM.match(lines[following])) and not RULE.match(lines[following])

    @staticmethod
    def starts_block(lines: list[str], index: int) -> bool:
        line = lines[index]
        stripped = line.strip()
        return bool(FENCE.match(line) or HEADING.match(stripped) or stripped.startswith('>') or LIST_ITEM.match(line)
                    or (stripped.startswith('|') and index + 1 < len(lines) and TABLE_SEPARATOR.match(lines[index + 1])))

    def heading(self, container: Any, level: int, text: str, context: _Context, in_cell: bool) -> bool:
        """A heading, numbered as the Help viewer numbers it; True for the index of the chapter, which is left out."""
        title = plain_text(text)
        anchor = ''
        if not in_cell:
            anchor = _next_anchor(text, context.seen)
            if level == 2 and title.lower() in INDEX_SECTIONS:
                return True
        number = context.numbers.get(anchor) if anchor and level in {2, 3} else None
        label = f'{number}  {title}' if number else title
        if in_cell or not hasattr(container, 'add_heading'):
            paragraph = self.paragraph(container)
            run = paragraph.add_run(label)
            run.bold = True
            return False
        paragraph = container.add_heading(label, level=min(level, 4))
        context.bookmarks[0] += 1
        _bookmark(paragraph, _bookmark_name(context.chapter, anchor), context.bookmarks[0])
        return False

    def text(self, container: Any, text: str, context: _Context) -> None:
        images = [match.group(2) for match in IMAGE_MARKDOWN.finditer(text)] + [match.group(1) for match in IMAGE_TAG.finditer(text)]
        rest = plain_text(text)
        for source in images:
            path = _local_image(source)
            if path is not None:
                try:
                    paragraph = self.paragraph(container)
                    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    paragraph.add_run().add_picture(str(path), width=Cm(6))
                except Exception:  # noqa: BLE001 - an image that cannot be read is left out
                    pass
        if rest:
            add_inline(self.paragraph(container), text, context)

    def code(self, container: Any, language: str, body: list[str]) -> None:
        if language == 'presentations':
            paragraph = self.paragraph(container)
            run = paragraph.add_run(PRESENTATIONS_NOTE)
            run.italic = True
            return
        cell = self.box(container, CODE_FILL)
        paragraph = cell.paragraphs[0] if hasattr(cell, 'paragraphs') and cell.paragraphs else self.paragraph(cell)
        for position, line in enumerate(body or ['']):
            if position:
                paragraph.add_run().add_break(WD_BREAK.LINE)
            run = paragraph.add_run(line.rstrip())
            run.font.name = CODE_FONT
            run.font.size = Pt(8.5)

    def table(self, container: Any, rows: list[str], context: _Context) -> None:
        cells = [[cell.strip() for cell in re.split(r'(?<!\\)\|', row.strip().strip('|'))] if row.strip('|').strip() else []
                 for row in rows]
        cells = [row for row in cells if row]
        columns = max((len(row) for row in cells), default=0)
        if not columns:
            return
        table = container.add_table(rows=len(cells), cols=columns)
        try:
            table.style = self.document.styles['Table Grid']
        except KeyError:
            pass
        for row_index, row in enumerate(cells):
            for column in range(columns):
                cell = table.cell(row_index, column)
                paragraph = cell.paragraphs[0]
                text = row[column] if column < len(row) else ''
                if row_index == 0:
                    _shade(cell._tc, HEADER_FILL)
                    add_inline(paragraph, text, context, bold=True)
                else:
                    add_inline(paragraph, text, context)
        header = table.rows[0]._tr.get_or_add_trPr()
        repeat = OxmlElement('w:tblHeader')
        repeat.set(qn('w:val'), 'true')
        header.append(repeat)
        if hasattr(container, 'add_heading'):
            self.paragraph(container)

    def quote(self, container: Any, lines: list[str], context: _Context) -> None:
        callout = re.match(r'^\s*\[!([A-Za-z]+)\]\s*(.*)$', lines[0]) if lines else None
        kind = callout.group(1).upper() if callout else ''
        label, fill, color = CALLOUTS.get(kind, ('', QUOTE_FILL, '444444'))
        if callout:
            lines = ([callout.group(2)] if callout.group(2).strip() else []) + lines[1:]
        cell = self.box(container, fill)
        if label:
            run = cell.paragraphs[0].add_run(label)
            run.bold = True
            run.font.color.rgb = RGBColor.from_string(color)
        self.blocks(cell, lines, context, in_cell=True)
        if hasattr(cell, '_tc'):
            self.tidy_cell(cell)
        if hasattr(container, 'add_heading'):
            self.paragraph(container)

    def list(self, container: Any, items: list[tuple[int, str, str]], context: _Context) -> None:
        indents: list[int] = []
        counters: list[int] = []
        for indent, marker, text in items:
            while indents and indent < indents[-1]:
                indents.pop()
                counters.pop()
            if not indents or indent > indents[-1]:
                indents.append(indent)
                counters.append(0)
            level = len(indents) - 1
            counters[-1] += 1
            ordered = marker[0].isdigit()
            if ordered and counters[-1] == 1:
                counters[-1] = int(re.sub(r'\D', '', marker) or 1)
            prefix = f'{counters[-1]}.' if ordered else ('•', '◦', '▪')[level % 3]
            paragraph = self.paragraph(container)
            paragraph.paragraph_format.left_indent = Cm(0.65 * (level + 1))
            paragraph.paragraph_format.first_line_indent = Cm(-0.5)
            paragraph.paragraph_format.space_after = Pt(2)
            paragraph.add_run(f'{prefix}\t')
            paragraph.paragraph_format.tab_stops.add_tab_stop(Cm(0.65 * (level + 1)))
            add_inline(paragraph, text, context)


# --- Documents ------------------------------------------------------------------------------------------------------


def _new_document(title: str) -> Any:
    document = Document()
    section = document.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    for side in ('left_margin', 'right_margin'):
        setattr(section, side, Cm(2))
    section.top_margin = section.bottom_margin = Cm(2)
    normal = document.styles['Normal']
    normal.font.name = 'Calibri'
    normal.font.size = Pt(10.5)
    document.core_properties.title = title
    document.core_properties.author = APP_TITLE
    return document


def _footer(document: Any, text: str) -> None:
    paragraph = document.sections[0].footer.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run(text)
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(0x77, 0x77, 0x77)


def _next_anchor(text: str, seen: dict[str, int]) -> str:
    """The id of a heading: repeated headings take the ids the Help viewer gives them (the second one is id-2…)."""
    base = heading_id(text)
    seen[base] = seen.get(base, 0) + 1
    return base if seen[base] == 1 else f'{base}-{seen[base]}'


def _bookmark_name(chapter: int, anchor: str) -> str:
    # (Word bookmarks have up to 40 characters.)
    return f'h{chapter}_{hashlib.sha1(anchor.encode()).hexdigest()[:12]}'


def _section_end(lines: list[str], index: int) -> int:
    """Where the section that starts before ``index`` ends: at the next heading of level 1 or 2, out of code blocks."""
    in_code = False
    while index < len(lines):
        if FENCE.match(lines[index]):
            in_code = not in_code
        elif not in_code:
            heading = HEADING.match(lines[index].strip())
            if heading and len(heading.group(1)) <= 2:
                return index
        index += 1
    return index


def _chapter_lines(chapter: Chapter) -> list[str]:
    """The Markdown of a chapter without its H1 title (the chapter starts with its title as the Help navigation names it)."""
    lines = chapter.content.splitlines()
    first = next((index for index, line in enumerate(lines) if line.strip()), None)
    title_line = HEADING.match(lines[first].strip()) if first is not None else None
    return lines[first + 1:] if title_line and len(title_line.group(1)) == 1 else lines


def chapter_headings(chapter: Chapter, position: int = 1) -> list[tuple[int, str, str]]:
    """The table of contents of a chapter: level, numbered title and bookmark of its title and of every heading, without
    its index and its presentations."""
    numbered = chapter.file != HELP_HOME_DOCUMENT
    numbers = section_numbers(chapter.content, numbered)
    entries = [(1, chapter.title, _bookmark_name(position, ''))]
    seen: dict[str, int] = {}
    lines = _chapter_lines(chapter)
    in_code = skipping = False
    for line in lines:
        if FENCE.match(line):
            in_code = not in_code
            continue
        match = None if in_code else HEADING.match(line.strip())
        if not match:
            continue
        level, text = len(match.group(1)), match.group(2)
        anchor = _next_anchor(text, seen)
        title = plain_text(text)
        if level <= 2:
            skipping = title.lower() in UNNUMBERED_SECTIONS
        if skipping:
            continue
        number = numbers.get(anchor) if level in {2, 3} else None
        entries.append((min(level, 4), f'{number}  {title}' if number else title, _bookmark_name(position, anchor)))
    return entries


def _table_of_contents(document: Any, entries: list[tuple[int, str, str]]) -> None:
    paragraph = document.add_paragraph()
    run = paragraph.add_run('Contents')
    run.bold = True
    run.font.size = Pt(16)
    for level, label, bookmark in entries:
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.left_indent = Cm(0.6 * (level - 1))
        paragraph.paragraph_format.space_after = Pt(4 if level == 1 else 1)
        if level == 1:
            paragraph.paragraph_format.space_before = Pt(6)
        _internal_link(paragraph, bookmark, label, bold=level == 1, size=10.5 if level <= 2 else 9.5)


def _write_title(document: Any, chapter: Chapter, position: int, bookmarks: list[int]) -> None:
    heading = document.add_heading(chapter.title, level=1)
    bookmarks[0] += 1
    _bookmark(heading, _bookmark_name(position, ''), bookmarks[0])


def _write_body(document: Any, chapter: Chapter, position: int, bookmarks: list[int]) -> None:
    numbered = chapter.file != HELP_HOME_DOCUMENT
    context = _Context(numbered=numbered, numbers=section_numbers(chapter.content, numbered), chapter=position,
                       bookmarks=bookmarks)
    _Writer(document).blocks(document, _chapter_lines(chapter), context)


def chapter_docx(chapter: Chapter, version: str) -> bytes:
    """One Help chapter as a Word document: its title, its table of contents and its sections."""
    document = _new_document(f'{APP_TITLE} - Help - {chapter.title}')
    _footer(document, f'{APP_TITLE} {version} · Help · {chapter.title}')
    bookmarks = [0]
    _write_title(document, chapter, 1, bookmarks)
    _table_of_contents(document, chapter_headings(chapter)[1:])
    _write_body(document, chapter, 1, bookmarks)
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def documentation_docx(chapters: list[Chapter], version: str, today: date | None = None) -> bytes:
    """Every Help chapter as one Word document: a cover, the contents and each chapter on a page of its own."""
    today = today or date.today()
    document = _new_document(f'{APP_TITLE} - Documentation')
    _footer(document, f'{APP_TITLE} {version} · Documentation')
    logo = STATIC_ROOT / 'img' / 'brand-mark.png'
    for _ in range(6):
        document.add_paragraph()
    if logo.is_file():
        try:
            paragraph = document.add_paragraph()
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.add_run().add_picture(str(logo), width=Cm(7))
        except Exception:  # noqa: BLE001 - the cover keeps its text without the logo
            pass
    for text, size, bold in ((f'{APP_TITLE} — Documentation', 26, True), (f'Version {version}', 14, False),
                             (today.isoformat(), 12, False)):
        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = paragraph.add_run(text)
        run.bold = bold or None
        run.font.size = Pt(size)
    document.add_page_break()
    _table_of_contents(document, [entry for index, chapter in enumerate(chapters, start=1)
                                  for entry in chapter_headings(chapter, index)])
    bookmarks = [0]
    for index, chapter in enumerate(chapters, start=1):
        document.add_page_break()
        _write_title(document, chapter, index, bookmarks)
        _write_body(document, chapter, index, bookmarks)
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def export_key(chapters: list[Chapter], *parts: str) -> str:
    """What a generated file depends on: the chapters, this module and the request (version, scope, chapter, format)."""
    digest = hashlib.sha256(Path(__file__).read_bytes())
    for chapter in chapters:
        digest.update(b'\0' + chapter.file.encode() + b'\0' + chapter.title.encode() + b'\0' + chapter.content.encode())
    for part in parts:
        digest.update(b'\1' + str(part).encode())
    return digest.hexdigest()[:24]


