"""Rich texts (rich_text.js): the Markdown of the descriptions and comments of Ticket Center and of the long texts and
comments of Non-Qualified Calls, read the same on the page and in the editor and written back as Markdown."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / 'src/web_interface/static/js/rich_text.js'
NQ_SCRIPT = PROJECT_ROOT / 'src/web_interface/static/js/non_qualified_calls.js'


def run(program: str):
    """Runs a program with window.RichText (as RT) and returns what it prints as JSON."""
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is required to run rich_text.js.')
    source = f"""
global.window = global; global.document = {{}};
require({json.dumps(str(SCRIPT))});
const RT = window.RichText;
// Each line as it reads: its kind, level, marker, title or bullet of a long text, and its text.
const read = (text, options = {{}}) => {{
  const lines = RT.withPlain(RT.parse(text, options));
  const views = RT.layout(lines, options);
  return lines.map((line, index) => {{
    const view = views[index];
    return [view.type + (line.card ? `[${{line.card}}]` : ''), view.level, view.marker + (line.task ? `[${{line.task}}]` : ''),
      view.title ? 'title' : view.implicit ? 'bullet' : '', line.type === 'h' ? line.heading : '', line.plain].join('|');
  }});
}};
console.log(JSON.stringify((() => {{ {program} }})()));
"""
    completed = subprocess.run([node, '-e', source], capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_texts_of_before_read_as_they_did():
    lines = run(r"""return read('Problem:\n- item1\n  - Item2\n    * item3\n- item4:\n  · under\n  goes on\n\nA plain line - not a bullet\nResolution: done.\n<b>x</b>');""")
    assert lines == [
        'p|0||title||Problem:', 'li|0|•|||item1', 'li|1|◦|||Item2', 'li|2|▪|||item3', 'li|0|•|title||item4:',
        'li|1|◦|||under', 'cont|1||||goes on', 'p|0||||', 'p|0||||A plain line - not a bullet',
        'p|0||||Resolution: done.', 'p|0||||<b>x</b>',
    ]


def test_a_line_followed_by_a_list_is_its_title():
    lines = run(r"""return [
      read('Steps to reproduce\n1. Open\n2. Click\nWhat happens\n- It fails'),
      read('First line of a paragraph\nits last line\n- a'),
      read('A sentence much longer than a title, that goes on and on well beyond the eighty characters\n- a'),
    ];""")
    assert lines[0] == ['p|0||title||Steps to reproduce', 'li|0|1.|||Open', 'li|0|2.|||Click', 'p|0||title||What happens', 'li|0|•|||It fails']
    # A line of a paragraph, or a long one, is not.
    assert lines[1][:2] == ['p|0||||First line of a paragraph', 'p|0||||its last line']
    assert lines[2][0].endswith('||||A sentence much longer than a title, that goes on and on well beyond the eighty characters')


def test_numbered_lists_at_any_level():
    lines = run(r"""return [
      read('1. One\n2. Two\n   a) First\n   b) Second\n3. Three\n  - bullet\n    1. deep\n    2. deeper'),
      read('1. Intro\n1.1. Scope\n1.2. Goals\n1.2.1. Deep\n2. Next\n2.1. Sub'),
      read('3. Starts at three\n4) other delimiter\nA) Upper\nB) Upper'),
    ];""")
    assert [line.split('|')[1:3] for line in lines[0]] == [
        ['0', '1.'], ['0', '2.'], ['1', 'a)'], ['1', 'b)'], ['0', '3.'], ['1', '◦'], ['2', '1.'], ['2', '2.'],
    ]
    assert [line.split('|')[1:3] for line in lines[1]] == [['0', '1.'], ['1', '1.1.'], ['1', '1.2.'], ['2', '1.2.1.'], ['0', '2.'], ['1', '2.1.']]
    # A list starts at the number of its first item; another delimiter starts another list.
    assert [line.split('|')[2] for line in lines[2]] == ['3.', '4)', 'A)', 'B)']


def test_headings_inline_formats_and_links():
    result = run(r"""return {
      headings: read('# One\n## Two #\n###### Six\n#hashtag\n####### seven'),
      tokens: RT.parseInline('**bold *it* x** _a_ ***both*** ~~s~~ ==m== `c` snake_case [t](https://a.b/c) https://x.com/p. [bad](javascript:alert(1)) \\*not\\*'),
    };""")
    assert result['headings'] == ['h|0|||1|One', 'h|0|||2|Two', 'h|0|||6|Six', 'p|0||||#hashtag', 'p|0||||####### seven']
    assert result['tokens'] == [
        {'type': 'strong', 'children': [{'type': 'text', 'text': 'bold '}, {'type': 'em', 'children': [{'type': 'text', 'text': 'it'}]}, {'type': 'text', 'text': ' x'}]},
        {'type': 'text', 'text': ' '}, {'type': 'em', 'children': [{'type': 'text', 'text': 'a'}]}, {'type': 'text', 'text': ' '},
        {'type': 'em', 'children': [{'type': 'strong', 'children': [{'type': 'text', 'text': 'both'}]}]}, {'type': 'text', 'text': ' '},
        {'type': 'del', 'children': [{'type': 'text', 'text': 's'}]}, {'type': 'text', 'text': ' '},
        {'type': 'mark', 'children': [{'type': 'text', 'text': 'm'}]}, {'type': 'text', 'text': ' '}, {'type': 'code', 'text': 'c'},
        {'type': 'text', 'text': ' snake_case '}, {'type': 'link', 'href': 'https://a.b/c', 'children': [{'type': 'text', 'text': 't'}]},
        {'type': 'text', 'text': ' '}, {'type': 'link', 'href': 'https://x.com/p', 'children': [{'type': 'text', 'text': 'https://x.com/p'}]},
        {'type': 'text', 'text': '. [bad](javascript:alert(1)) *not*'},
    ]


def test_cards_quotes_code_dividers_and_tasks():
    lines = run(r"""return read('> [!TIP]\n> Use it\n> - a bullet\n> [!danger] Careful\n> text\n\n> [!foo]\n> plain\n\n> a quote\n```js\nconst a = 1;\n  b\n```\n---\n----- Notes -----\n***bold italic***\n- [ ] todo\n- [x] done');""")
    assert lines == [
        'head[tip]|0||||', 'p[tip]|0||title||Use it', 'li[tip]|0|•|||a bullet', 'head[error]|0||||Careful', 'p[error]|0||||text',
        'p|0||||', 'head[note]|0||||Foo', 'p[note]|0||||plain', 'p|0||||', 'p[quote]|0||||a quote', 'code|0||||const a = 1;',
        'code|0||||  b', 'hr|0||||', 'hr|0||||Notes', 'p|0||title||bold italic', 'li|0|•[open]|||todo', 'li|0|•[done]|||done',
    ]


def test_long_texts_of_non_qualified_calls_read_every_line_as_a_bullet():
    lines = run(r"""const options = {implicitBullets: true}; return [
      read('Problem Statement:\nline one\n  nested\n    deeper\nTitle\n- explicit\n------Jorge------\nafter', options),
      read('just one line', options),
      read('- a\n\n  - b', options),
      read('> [!NOTE]\n> inside a card', options),
    ];""")
    assert lines[0] == [
        'p|0||title||Problem Statement:', 'p|0|•|bullet||line one', 'p|1|◦|bullet||nested', 'p|2|▪|bullet||deeper',
        'p|0||title||Title', 'li|0|•|||explicit', 'hr|0||||Jorge', 'p|0|•|bullet||after',
    ]
    assert lines[1] == ['p|0||||just one line']
    # The blank lines do not end the bullets; the lines of a card are text.
    assert lines[2][2] == 'li|1|◦|||b'
    assert lines[3] == ['head[note]|0||||', 'p[note]|0||||inside a card']


def test_the_markdown_written_again_reads_the_same_and_stays_the_same():
    texts = [
        'Problem:\n- item1\n  - Item2\n    * item3\n- item4:\n  · under\n  goes on\n\nA plain line\nResolution: done.',
        'Steps\n1) one\n   a. sub\n10. ten\n1.1. outline\n  - bullet\n    continuation',
        '# Title\n**bold** _it_ ~~s~~ ==m== `c` [l](https://a.b) https://x.y/z.\n> [!WARNING] Careful\n> - in a card\n>\n> ```\n> code\n> ```',
        '\\- not a bullet\n1\\. not numbered\n\\# not a heading\n\\> not a quote\n\\*not italic\\*\n- \\[ ] not a task',
        '```\n```inner\n````\nafter',
    ]
    result = run(f"""const texts = {json.dumps(texts)};
      return texts.flatMap((text) => [{{}}, {{implicitBullets: true}}].map((options) => {{
        const once = RT.normalizeText(text, options);
        const strip = (lines) => lines.map((line) => line.split('|').slice(0, 5).join('|') + '|' + line.split('|')[5].trim());
        return {{same: JSON.stringify(strip(read(once, options))) === JSON.stringify(strip(read(text, options))),
          stable: RT.normalizeText(once, options) === once, once}};
      }}));""")
    for item in result:
        assert item['same'] and item['stable'], item
    assert result[0]['once'] == 'Problem:\n- item1\n  - Item2\n    - item3\n- item4:\n  - under\n    goes on\n\nA plain line\nResolution: done.'
    assert result[6]['once'].startswith('\\- not a bullet\n1\\. not numbered\n\\# not a heading\n\\> not a quote\n\\*not italic\\*\n- \\[ ] not a task')


def test_numbers_link_their_items_only_with_the_references_of_the_page():
    result = run(r"""const refs = {href: '/tickets/{id}', titles: {7: 'Prioritize NQ calls · Resolved', 12: 'Three SA · New'}};
      return {
        tokens: RT.parseInline('See #7, (#12) and **#7**; not #99, a#7, #7a, #7.5, ##7, &#7;, \\#7, `#7`, [#7](/x) or https://a.b/c#7', refs),
        without: RT.parseInline('See #7'),
        markdown: RT.tokensToMarkdown(RT.normalizeTokens(RT.parseInline('See **#7** and #12.', refs))),
        every: RT.parseInline('#7', {href: '/tickets/{id}'}),
        unsafe: RT.parseInline('#7', {href: 'javascript:alert({id})'}),
      };""")
    ref = lambda number, title: {'type': 'ref', 'text': f'#{number}', 'href': f'/tickets/{number}', 'title': title}
    assert result['tokens'] == [
        {'type': 'text', 'text': 'See '}, ref(7, 'Prioritize NQ calls · Resolved'), {'type': 'text', 'text': ', ('},
        ref(12, 'Three SA · New'), {'type': 'text', 'text': ') and '}, {'type': 'strong', 'children': [ref(7, 'Prioritize NQ calls · Resolved')]},
        # A number of no item, inside a word or a number, escaped, in code, in a link or a web address stays text.
        {'type': 'text', 'text': '; not #99, a#7, #7a, #7.5, ##7, &#7;, #7, '}, {'type': 'code', 'text': '#7'}, {'type': 'text', 'text': ', '},
        {'type': 'link', 'href': '/x', 'children': [{'type': 'text', 'text': '#7'}]}, {'type': 'text', 'text': ' or '},
        {'type': 'link', 'href': 'https://a.b/c#7', 'children': [{'type': 'text', 'text': 'https://a.b/c#7'}]},
    ]
    # The texts of a page without references (Non-Qualified Calls) keep their numbers as text; a reference is written
    # back as it was.
    assert result['without'] == [{'type': 'text', 'text': 'See #7'}]
    assert result['markdown'] == 'See **#7** and #12.'
    # Without titles every number links; an address that is no page of the tool links none.
    assert result['every'] == [ref(7, '')]
    assert result['unsafe'] == [{'type': 'text', 'text': '#7'}]


def test_plain_text_for_previews():
    text = run(r"""return RT.toPlainText('Title\n- **a**\n  1. b\n> [!TIP]\n> hey\n- [x] done');""")
    assert text == 'Title\n• a\n  1. b\nTip\nhey\n☑ done'


def test_non_qualified_calls_show_and_edit_their_texts_with_it():
    script = NQ_SCRIPT.read_text(encoding='utf-8')
    template = (PROJECT_ROOT / 'src/web_interface/templates/non_qualified_calls.html').read_text(encoding='utf-8')
    assert template.index('js/rich_text.js') < template.index('js/non_qualified_calls.js') and 'css/rich_text.css' in template
    # Long texts: every line a bullet, edited in place (a label would send the clicks to the hidden text area).
    assert "window.RichText.render(text, {implicitBullets: true, className: 'nq-bullets'})" in script
    assert "window.RichText.attach(editor, {implicitBullets: true, docClass: 'nq-bullets', toolbar: 'focus'" in script
    assert "node(editable && field.type !== 'long_text' ? 'label' : 'div'" in script
    # Comments: written and edited as they read, Ctrl+Enter posts them, and the list previews them without Markdown.
    assert "window.RichText.attach(composerBody, {docClass: 'nq-comment-body', onSubmit: postComment" in script
    assert "window.RichText.render(comment.body, {className: 'nq-comment-body'})" in script
    assert 'window.RichText.toPlainText(call.last_comment.body)' in script
    # The refresh of the open call waits while a text is being edited.
    assert '#nq-drawer [contenteditable="true"]' in script
