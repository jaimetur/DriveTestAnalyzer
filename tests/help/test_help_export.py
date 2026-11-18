import json
import re
from io import BytesIO

from docx import Document

import src.DriveTestAnalyzer as core
from src.modules.help import help_export
from src.modules.reporting import pptx_to_docx


def document_text(content: bytes) -> tuple[list[str], list[str], int]:
    """The heading texts, every paragraph and the number of tables of a Word document."""
    document = Document(BytesIO(content))
    headings = [paragraph.text for paragraph in document.paragraphs if paragraph.style.name.startswith('Heading')]
    return headings, [paragraph.text for paragraph in document.paragraphs], len(document.tables)


def export_events():
    return [row for row in core.repository.list_logs() if row['action'] == 'help_exported']


def test_a_guide_exports_to_word_with_numbered_headings_a_contents_and_tables(client):
    response = client.get('/api/help/export', params={'scope': 'guide', 'doc': 'reporting.md', 'format': 'docx'})
    assert response.status_code == 200
    assert 'DriveTest%20Analyzer%20-%20Help%20-%20Reporting.docx' in response.headers['content-disposition']
    headings, paragraphs, tables = document_text(response.content)
    assert headings[0] == 'Reporting'
    assert '1  Reports' in headings and '2  The report editor' in headings and '2.1  Campaigns of each module' in headings
    # The index of the chapter is left out (and unnumbered); the document has its own table of contents.
    assert not any('in this guide' in heading.lower() for heading in headings)
    # Each entry of the contents ends with its page (a PAGEREF field after a right tab), the contents end with a page break,
    # and the footer numbers the pages.
    # A cover first (the chapter in its title), then the contents.
    assert 'DriveTest Analyzer — Help\nReporting' in paragraphs
    contents = paragraphs.index('Contents')
    assert 'Reporting\t' in paragraphs[contents + 1:contents + 3] and '1  Reports\t' in paragraphs[contents + 1:contents + 6]
    document = Document(BytesIO(response.content))
    xml = document.element.xml
    assert 'PAGEREF' in xml and 'w:updateFields' in document.settings.element.xml
    footer = document.sections[0].footer._element.xml
    assert ' PAGE ' in footer and ' NUMPAGES ' in footer
    assert 'Help · Reporting' in document.sections[0].header.paragraphs[0].text
    assert 'Reporting' not in document.sections[0].footer.paragraphs[0].text
    assert tables >= 1
    event = export_events()[0]
    details = json.loads(event['details'])
    assert event['username'] == 'anonymous'
    assert details['scope'] == 'guide' and details['doc'] == 'reporting.md' and details['format'] == 'docx'
    assert details['cached'] == 'no' and details['size_bytes'] == len(response.content)


def test_index_sections_are_left_out_under_their_old_and_new_heading():
    content = ('# Guide\n\n## Main topics in this guide\n\n| Task | Go to |\n| --- | --- |\n| A | [First](#first) |\n\n'
               '## First\n\nText with **bold**, *italic*, `code` and <kbd>Esc</kbd>.\n\n### Detail\n\n- one\n  - nested\n\n'
               '> [!TIP]\n> A tip.\n\n## In this guide\n\nOld index.\n\n## Second\n\n```text\ncode\n```\n')
    headings, paragraphs, _ = document_text(help_export.chapter_docx(help_export.Chapter('guide.md', 'Guide', content), '1.0'))
    assert headings == ['Guide', '1  First', '1.1  Detail', '2  Second']
    assert 'Old index.' not in paragraphs
    assert help_export.section_numbers(content) == {'first': '1', 'detail': '1.1', 'second': '2'}


def test_the_whole_documentation_has_every_chapter_in_navigation_order_and_is_cached(client):
    response = client.get('/api/help/export', params={'scope': 'all', 'format': 'docx'})
    assert response.status_code == 200
    assert 'DriveTest%20Analyzer%20-%20Documentation.docx' in response.headers['content-disposition']
    headings, _, _ = document_text(response.content)
    # The chapters are numbered, their sections as in the Help.
    # Each chapter opens with its sub-cover: its number above its title, on a page of its own.
    chapters = [heading.split('\n', 1) for heading in headings if re.match(r'\d+\n', heading)]
    assert [number for number, _ in chapters[:4]] == ['1', '2', '3', '4']
    titles = [title for _, title in chapters if title in {'Product Overview', 'Workspace Management', 'Reporting', 'Super Admin'}]
    assert titles == ['Product Overview', 'Workspace Management', 'Reporting', 'Super Admin']
    assert not any(heading.endswith('Help Home') for heading in headings)
    # Without the presentations, which a document cannot play.
    assert not any(heading.endswith('Product Presentations') for heading in headings)
    assert not any(heading.endswith(('  Presentation', '  Presentations')) for heading in headings)

    again = client.get('/api/help/export', params={'scope': 'all', 'format': 'docx'})
    assert again.status_code == 200 and again.content == response.content
    assert [json.loads(row['details'])['cached'] for row in export_events()] == ['yes', 'no']
    assert len(list((core.settings.data_dir / 'help-exports').glob('all-docx-*.docx'))) == 1


def test_an_unknown_guide_is_not_found_and_a_bad_request_is_refused(client):
    assert client.get('/api/help/export', params={'scope': 'guide', 'doc': 'missing.md'}).status_code == 404
    assert client.get('/api/help/export', params={'scope': 'guide', 'doc': '../README.md'}).status_code in {400, 404}
    assert client.get('/api/help/export', params={'scope': 'guide', 'doc': 'reporting.md', 'format': 'odt'}).status_code == 400
    assert client.get('/api/help/export', params={'scope': 'some', 'doc': 'reporting.md'}).status_code == 400


def test_pdf_needs_libreoffice_and_is_returned_when_converted(client, monkeypatch):
    monkeypatch.setattr(pptx_to_docx, 'document_pdf', lambda content, suffix, whole=False: None)
    response = client.get('/api/help/export', params={'scope': 'guide', 'doc': 'reporting.md', 'format': 'pdf'})
    assert response.status_code == 503
    assert response.json()['detail'] == 'PDF export needs LibreOffice on the server.'

    calls = []
    monkeypatch.setattr(pptx_to_docx, 'document_pdf',
                        lambda content, suffix, whole=False: calls.append((suffix, whole)) or b'%PDF-1.7 fake')
    response = client.get('/api/help/export', params={'scope': 'guide', 'doc': 'reporting.md', 'format': 'pdf'})
    assert response.status_code == 200 and response.content == b'%PDF-1.7 fake'
    assert response.headers['content-type'] == 'application/pdf'
    assert calls == [('docx', True)]
    assert client.get('/api/help/export', params={'scope': 'guide', 'doc': 'reporting.md', 'format': 'pdf'}).content == b'%PDF-1.7 fake'
    assert len(calls) == 1


def test_help_pages_show_the_export_button(client):
    page = client.get('/documents/view/help/reporting.md')
    assert 'data-help-export-open' in page.text and 'This guide (Reporting)' in page.text
    assert 'data-help-export-open' in client.get('/documents/view/help').text
    assert 'data-help-export-open' not in client.get('/documents/view/readme').text


def test_the_complete_guide_opens_its_pdf_page_by_page_by_chapter(client, monkeypatch):
    import pymupdf

    def fake_pdf(content, suffix, whole=False):
        # A PDF of 4 pages: the cover, the contents and two chapters, with the outline LibreOffice writes.
        document = pymupdf.open()
        for text in ('Cover', 'Contents', 'I  Reporting', '1  Reports'):
            document.new_page().insert_text((72, 72), text)
        document.set_toc([[1, 'I Reporting', 3], [2, '1 Reports', 4]])
        return document.tobytes()

    monkeypatch.setattr(pptx_to_docx, 'document_pdf', fake_pdf)
    response = client.get('/api/help/guide')
    assert response.status_code == 200
    data = response.json()
    assert data['pages'] == 4 and data['downloads']['pdf'] == '/api/help/export?scope=all&format=pdf'
    assert data['sections'] == [
        {'title': 'Cover and contents', 'pages': [{'index': 0, 'title': 'Cover'}, {'index': 1, 'title': 'Contents'}]},
        {'title': 'I Reporting', 'pages': [{'index': 2, 'title': 'I Reporting'}, {'index': 3, 'title': '1 Reports'}]}]
    page = client.get('/api/help/guide/pages/3')
    assert page.status_code == 200 and page.headers['content-type'] == 'image/png' and page.content.startswith(b'\x89PNG')
    assert client.get('/api/help/guide/pages/3', params={'thumb': 'true'}).content.startswith(b'\x89PNG')
    assert client.get('/api/help/guide/pages/9').status_code == 404
    assert any(row['action'] == 'help_guide_opened' for row in core.repository.list_logs())


def test_the_main_sections_follow_on_the_same_page_well_apart():
    content = '# Guide\n\nIntro.\n\n## First\n\nShort.\n\n## Second\n\nShort.\n'
    document = Document(BytesIO(help_export.chapter_docx(help_export.Chapter('guide.md', 'Guide', content), '1.0')))
    sections = [paragraph for paragraph in document.paragraphs if paragraph.style.name == 'Heading 2']
    assert [paragraph.text for paragraph in sections] == ['1  First', '2  Second']
    assert not any(paragraph.paragraph_format.page_break_before for paragraph in sections)
    assert all(paragraph.paragraph_format.space_before == help_export.SECTION_SPACE for paragraph in sections)
