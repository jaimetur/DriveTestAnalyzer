"""Colour themes of the Scoring & GAP Analysis and Network Insights charts and tables, on the page and in their
PowerPoint and Word exports.

NetCheck, the default, keeps the colours of the NetCheck reports. Every other theme gives the same tokens its own
colours, and each theme gives the titles and subtitles of the slides its own style (``titles``, see theme_titles). The scoring views and the export code are written in the NetCheck colours; :func:`themed` translates each of
them, and every shade of the NetCheck GAP scale, into the active theme. Operator colours always come from the
Operator Maps, whatever the theme.
"""
from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Any, Iterator

DEFAULT_THEME = 'netcheck'

_NETCHECK = {
    'label': 'NetCheck',
    'description': 'As the NetCheck reports: white lists with thin rules, Excel-like data bars in the colour of each score band, '
                   'GAP bars either side of zero, operators on strips in their colour and blue titles.',
    'font': 'Arial, "Helvetica Neue", Helvetica, sans-serif', 'number_font': 'Arial, "Helvetica Neue", Helvetica, sans-serif',
    # The background of the content slides (slide): white, night blue in the dark theme (Midnight).
    'surface': '#FFFFFF', 'slide': '#FFFFFF', 'ink': '#1F2A37', 'muted': '#8A96A0', 'line': '#E3E8EC', 'value_scale': 1.12,
    'title': '#1450A8', 'title_accent': '#1450A8', 'subtitle': '#245A96', 'accent': '#245E5A',
    'header': '#455B65', 'header_text': '#FFFFFF', 'soft_header': '#EDF2F6', 'soft_header_text': '#344858',
    'weight': '#5B9A44', 'maximum': '#C9483F', 'gap_header': '#F6D55C', 'gap_cell': '#FFF6C2',
    'group': '#E6F0F7', 'group_alt': '#D7E5EE', 'category': '#DCE5E9', 'kpi': '#E7E8E9', 'kpi_alt': '#E6ECFA',
    'total': '#D7E0E5', 'subtotal': '#E3E6E7', 'summary_total': '#D8DFE4', 'row_alt': '#F8FAFC', 'border': '#E2E8ED',
    'bands': {'Low': '#F9DCDA', 'Medium': '#FFF0C7', 'High': '#DDEFD2', 'UltraHigh': '#BDE3E2', 'Unavailable': '#ECEFF1'},
    'band_strong': {'Low': '#E06666', 'Medium': '#E8A33D', 'High': '#6AA84F', 'UltraHigh': '#2E9A98'},
    'gap_negative': '#E06666', 'gap_positive': '#6AA84F', 'gap_neutral': '#FFFFFF', 'gap_names': ['Green', 'Red'],
    'best': '#C6EFCE', 'worst': '#FFC7CE',
    'loss': '#E8414F', 'gain': '#4CA65A', 'loss_text': '#C62835', 'gain_text': '#2E8540',
    'voice': '#F2A900', 'data': '#0E6B66',
    'ranks': ['#2F8A3E', '#7CBF73', '#F0868E', '#E8414F'],
    'stake': ['#A51C30', '#E8414F', '#F4A3AA'],
    'loss_ramp': ['#F9D65C', '#C8102E'],
    'environments': ['#176E77', '#E6A81D', '#C55A11', '#5B9BD5', '#A64D79'],
    'categories': ['#4472C4', '#7030A0', '#C55A11', '#5B9BD5', '#A64D79', '#548235', '#D65F8D', '#8064A2'],
    'kpi_reliable': '#D8EFCA', 'kpi_diff': '#FFF2CC',
    # The five steps of a scale, from the worst to the best class, and the muted colours of a series (the Key Findings
    # of Network Insights).
    'scale': ['#C9483F', '#E8A060', '#F2D06B', '#93C47D', '#3E8E4F'],
    'series': ['#5B7A99', '#A9C4DB', '#8BA88E', '#C9B27C', '#B48C7C', '#8E87A0', '#DADDE0'],
    # The titles and subtitles of the slides: their font (and that of the focus of a title, focus_font), size and
    # weight, the first part of a title in capitals (caps), the colours that replace the title tokens (heading_color,
    # focus_color and subtitle_color; None: title, title_accent and subtitle) and whether the
    # first part of a subtitle (before ' · ') is bold (lead_bold).
    'titles': {'font': 'Montserrat', 'focus_font': None, 'size': 32, 'bold': False, 'focus_bold': True, 'caps': True, 'italic': False,
               'focus_color': None, 'subtitle_font': 'Montserrat', 'subtitle_size': 16, 'subtitle_bold': False,
               'subtitle_italic': False, 'subtitle_color': None, 'lead_bold': True, 'focus_italic': False, 'heading_color': None},
    # The lines between the cells of the PowerPoint tables: white gaps that set the cells apart, never a grid.
    'cell_border': '#FFFFFF', 'cell_border_pt': 1.5,
}

THEMES: dict[str, dict[str, Any]] = {
    'netcheck': _NETCHECK,
    'umlaut': {
        'label': 'Umlaut',
        'description': 'As the umlaut benchmark reports: bold dark titles over a red headline, white tables with thin rules and '
                       'bars in the colour of each band, light grey panels and quality classes from red to green.',
        'font': 'Arial, "Helvetica Neue", Helvetica, sans-serif', 'number_font': 'Arial, "Helvetica Neue", Helvetica, sans-serif',
        'surface': '#FFFFFF', 'slide': '#FFFFFF', 'ink': '#1C1C28', 'muted': '#8C8C99', 'line': '#E4E2E6', 'value_scale': 1,
        'title': '#1C1C28', 'title_accent': '#A6192E', 'subtitle': '#A6192E', 'accent': '#A6192E',
        'header': '#F4F2F4', 'header_text': '#3F3F4C', 'soft_header': '#F4F2F4', 'soft_header_text': '#1C1C28',
        'weight': '#5B7A99', 'maximum': '#A6192E', 'gap_header': '#F2D06B', 'gap_cell': '#FBF3D9',
        'group': '#F4F2F4', 'group_alt': '#EAE7EB', 'category': '#F4F2F4', 'kpi': '#FFFFFF', 'kpi_alt': '#FAF9FA',
        'total': '#EAE7EB', 'subtotal': '#F4F2F4', 'summary_total': '#EAE7EB', 'row_alt': '#F7F6F8', 'border': '#E4E2E6',
        'bands': {'Low': '#F6D5D2', 'Medium': '#FBF0C9', 'High': '#DCEFD6', 'UltraHigh': '#CFE6D4', 'Unavailable': '#EEEDEF'},
        'band_strong': {'Low': '#C9483F', 'Medium': '#E8B94A', 'High': '#5E9E58', 'UltraHigh': '#2F7D4A'},
        'gap_negative': '#C9483F', 'gap_positive': '#5E9E58', 'gap_neutral': '#FFFFFF', 'gap_names': ['Green', 'Red'],
        'best': '#DCEFD6', 'worst': '#F6D5D2',
        'loss': '#C9483F', 'gain': '#5E9E58', 'loss_text': '#A6192E', 'gain_text': '#2F7D4A',
        'voice': '#8E87A0', 'data': '#5B7A99',
        'ranks': ['#2F7D4A', '#93C47D', '#E8A060', '#C9483F'],
        'stake': ['#7E1220', '#C9483F', '#EBA39C'],
        'loss_ramp': ['#F2D06B', '#A6192E'],
        'environments': ['#3F3F4C', '#C9B27C', '#B48C7C', '#A9C4DB', '#6E6A7C'],
        'categories': ['#5B7A99', '#A6192E', '#8BA88E', '#E8A060', '#8E87A0', '#2F7D4A', '#D58A94', '#7C93AE'],
        'kpi_reliable': '#DCEFD6', 'kpi_diff': '#FBF0C9',
        'scale': ['#C9483F', '#E8A060', '#F2D06B', '#93C47D', '#3E8E4F'],
        'series': ['#5B7A99', '#A9C4DB', '#8BA88E', '#C9B27C', '#B48C7C', '#8E87A0', '#DADDE0'],
        'titles': {'font': 'Arial', 'focus_font': None, 'size': 28, 'bold': True, 'focus_bold': True, 'caps': False, 'italic': False,
                   'focus_color': '#1C1C28', 'subtitle_font': 'Arial', 'subtitle_size': 16, 'subtitle_bold': False,
                   'subtitle_italic': False, 'subtitle_color': '#A6192E', 'lead_bold': False, 'focus_italic': False, 'heading_color': None},
        'cell_border': '#FFFFFF', 'cell_border_pt': 1.5,
    },
    'ericsson': {
        'label': 'Ericsson',
        'description': 'The Ericsson brand guide: its greys, table headers and the part of the titles that changes in its deep '
                       'blue, light tints of its colours for the fills and its deep shades for the ends of each scale, each GAP '
                       'with a ▲ or ▼ over a bar.',
        'font': '"Ericsson Hilda", "Helvetica Neue", Helvetica, Arial, sans-serif',
        'number_font': '"Ericsson Hilda", "Helvetica Neue", Helvetica, Arial, sans-serif',
        'surface': '#FFFFFF', 'slide': '#FFFFFF', 'ink': '#242424', 'muted': '#A0A0A0', 'line': '#E0E0E0', 'value_scale': 1,
        'title': '#242424', 'title_accent': '#0068BF', 'subtitle': '#767676', 'accent': '#0068BF',
        'header': '#0068BF', 'header_text': '#FFFFFF', 'soft_header': '#FFFFFF', 'soft_header_text': '#242424',
        'weight': '#767676', 'maximum': '#0068BF', 'gap_header': '#0068BF', 'gap_cell': '#E6F2FD',
        'group': '#F2F2F2', 'group_alt': '#E0E0E0', 'category': '#F2F2F2', 'kpi': '#FFFFFF', 'kpi_alt': '#FAFAFA',
        'total': '#E0E0E0', 'subtotal': '#F2F2F2', 'summary_total': '#E0E0E0', 'row_alt': '#FAFAFA', 'border': '#E0E0E0',
        'bands': {'Low': '#FFC1C1', 'Medium': '#FCF2BF', 'High': '#B7EDD6', 'UltraHigh': '#B2D8F9', 'Unavailable': '#F2F2F2'},
        'band_strong': {'Low': '#CC2828', 'Medium': '#C6A823', 'High': '#0C9B5B', 'UltraHigh': '#0068BF'},
        'gap_negative': '#CC2828', 'gap_positive': '#0C9B5B', 'gap_neutral': '#FFFFFF', 'gap_names': ['Green', 'Red'],
        'best': '#B7EDD6', 'worst': '#FFC1C1',
        'loss': '#FF5B5B', 'gain': '#0C9B5B', 'loss_text': '#CC2828', 'gain_text': '#0C9B5B',
        'voice': '#0068BF', 'data': '#8C60A8',
        'ranks': ['#339BF2', '#66B5F4', '#FDA353', '#FF5B5B'],
        'stake': ['#CC2828', '#FF8484', '#FFC1C1'],
        'loss_ramp': ['#B2D8F9', '#0068BF'],
        'environments': ['#242424', '#A0A0A0', '#0068BF', '#E0E0E0', '#C6A823'],
        'categories': ['#0082F0', '#AF78D2', '#0FC373', '#FF8C0A', '#FAD22D', '#FF3232', '#767676', '#66B5F4'],
        'kpi_reliable': '#B7EDD6', 'kpi_diff': '#FCF2BF',
        'scale': ['#CC2828', '#FEBA7E', '#FCE282', '#70DBAA', '#0C9B5B'],
        'series': ['#0068BF', '#66B5F4', '#8C60A8', '#C6A823', '#CC7007', '#767676', '#E0E0E0'],
        # A black heading of Ericsson Hilda Light, only the part that tells the slide apart in bold Ericsson deep blue, and
        # grey subtitles.
        'titles': {'font': 'Ericsson Hilda Light', 'focus_font': 'Ericsson Hilda', 'size': 32, 'bold': False, 'focus_bold': True,
                   'caps': False, 'italic': False, 'focus_color': '#0068BF', 'subtitle_font': 'Ericsson Hilda', 'subtitle_size': 16,
                   'subtitle_bold': False, 'subtitle_italic': False, 'subtitle_color': '#767676', 'lead_bold': False, 'focus_italic': False,
                   'heading_color': '#000000'},
        'cell_border': '#FFFFFF', 'cell_border_pt': 1.0,
    },
    'vodafone': {
        'label': 'Vodafone',
        'description': 'Bold and rounded: red header bands, rounded cards and every score and GAP as a rounded chip, '
                       'with Vodafone aqua, aubergine and lemon.',
        'font': '"Vodafone Rg", "Avenir Next", "Segoe UI", Arial, sans-serif',
        'number_font': '"Vodafone Rg", "Avenir Next", "Segoe UI", Arial, sans-serif',
        'surface': '#FFFFFF', 'slide': '#FFFFFF', 'ink': '#333333', 'muted': '#9B9B9B', 'line': '#EBEBEB', 'value_scale': 1,
        'title': '#333333', 'title_accent': '#E60000', 'subtitle': '#666666', 'accent': '#E60000',
        'header': '#E60000', 'header_text': '#FFFFFF', 'soft_header': '#F4F4F4', 'soft_header_text': '#333333',
        'weight': '#4A4D4E', 'maximum': '#5E2750', 'gap_header': '#00B0CA', 'gap_cell': '#E6F7FA',
        'group': '#FDF2F2', 'group_alt': '#F7E6E6', 'category': '#F4F4F4', 'kpi': '#FFFFFF', 'kpi_alt': '#F8F8F8',
        'total': '#EBEBEB', 'subtotal': '#F4F4F4', 'summary_total': '#E8E8E8', 'row_alt': '#F8F8F8', 'border': '#EBEBEB',
        'bands': {'Low': '#FFD6D6', 'Medium': '#FFEDB3', 'High': '#DFF0C2', 'UltraHigh': '#CCEFF5', 'Unavailable': '#EEEEEE'},
        'band_strong': {'Low': '#E60000', 'Medium': '#FECB00', 'High': '#A8B400', 'UltraHigh': '#00B0CA'},
        'gap_negative': '#E60000', 'gap_positive': '#00B0CA', 'gap_neutral': '#FFFFFF', 'gap_names': ['Aqua', 'Red'],
        'best': '#CCEFF5', 'worst': '#FFD6D6',
        'loss': '#E60000', 'gain': '#00B0CA', 'loss_text': '#B30000', 'gain_text': '#00788A',
        'voice': '#5E2750', 'data': '#A8B400',
        'ranks': ['#00B0CA', '#7FD8E5', '#F39A9A', '#E60000'],
        'stake': ['#990000', '#E60000', '#FF8A8A'],
        'loss_ramp': ['#FFD6D6', '#990000'],
        'environments': ['#9C9C9C', '#25282B', '#CCCCCC', '#6F7376', '#E8E8E8'],
        'categories': ['#E60000', '#5E2750', '#00B0CA', '#FECB00', '#A8B400', '#EB9700', '#4A4D4E', '#9C2AA0'],
        'kpi_reliable': '#DFF0C2', 'kpi_diff': '#FFEDB3',
        'scale': ['#B30000', '#EB9700', '#FECB00', '#A8B400', '#00B0CA'],
        'series': ['#E60000', '#F39A9A', '#00B0CA', '#FECB00', '#5E2750', '#4A4D4E', '#D9D9D9'],
        'titles': {'font': 'Vodafone Rg', 'focus_font': None, 'size': 30, 'bold': True, 'focus_bold': True, 'caps': False, 'italic': False,
                   'focus_color': None, 'subtitle_font': 'Vodafone Rg', 'subtitle_size': 16, 'subtitle_bold': False,
                   'subtitle_italic': False, 'subtitle_color': '#4A4D4E', 'lead_bold': False, 'focus_italic': False, 'heading_color': None},
        'cell_border': '#FFFFFF', 'cell_border_pt': 2.25,
    },
    'midnight': {
        'label': 'Midnight',
        'description': 'Dark: night-blue slides and cards with light text, a glowing bar for each score band and neon mint and '
                       'pink GAPs.',
        'font': '"SF Pro Display", "Segoe UI", system-ui, sans-serif',
        'number_font': '"SF Mono", Menlo, Consolas, "Liberation Mono", monospace',
        'surface': '#0F1726', 'slide': '#080D18', 'ink': '#DCE6F2', 'muted': '#8094B4', 'line': '#22314A', 'value_scale': 1,
        'title': '#EAF1FA', 'title_accent': '#22C7E8', 'subtitle': '#9FB3CF', 'accent': '#00C2E0',
        'header': '#1F3354', 'header_text': '#FFFFFF', 'soft_header': '#1A2A44', 'soft_header_text': '#CFE0F5',
        'weight': '#9AA8FF', 'maximum': '#00C2E0', 'gap_header': '#6D4BC2', 'gap_cell': '#241B3A',
        'group': '#16233A', 'group_alt': '#1B2B45', 'category': '#18263F', 'kpi': '#0F1726', 'kpi_alt': '#152139',
        'total': '#22324F', 'subtotal': '#1B2942', 'summary_total': '#22324F', 'row_alt': '#152139', 'border': '#2A3B58',
        'bands': {'Low': '#4A1D2B', 'Medium': '#4A3C16', 'High': '#11402F', 'UltraHigh': '#123650', 'Unavailable': '#1E2A3D'},
        'band_strong': {'Low': '#FF4D6D', 'Medium': '#FFC145', 'High': '#2EE6A6', 'UltraHigh': '#3DB9FF'},
        'gap_negative': '#FF4D6D', 'gap_positive': '#2EE6A6', 'gap_neutral': '#0F1726', 'gap_names': ['Mint', 'Pink'],
        'best': '#11402F', 'worst': '#4A1D2B',
        'loss': '#FF4D6D', 'gain': '#14C38E', 'loss_text': '#FF7A93', 'gain_text': '#3BE8B0',
        'voice': '#B47CFF', 'data': '#3DB9FF',
        'ranks': ['#2EE6A6', '#3DB9FF', '#FFC145', '#FF4D6D'],
        'stake': ['#B3123A', '#FF4D6D', '#FF9FB2'],
        'loss_ramp': ['#00E0FF', '#FF2E63'],
        'environments': ['#E6EDF7', '#5C6F8F', '#C9F27B', '#8A9BB8', '#F2E8CF'],
        'categories': ['#3DB9FF', '#B47CFF', '#2EE6A6', '#FFC145', '#FF4D6D', '#00E0FF', '#FF8FAB', '#7B8CFF'],
        'kpi_reliable': '#11402F', 'kpi_diff': '#4A3C16',
        'scale': ['#FF4D6D', '#FF9F45', '#FFC145', '#7EE8C1', '#2EE6A6'],
        'series': ['#3DB9FF', '#9ED8FF', '#2EE6A6', '#FFC145', '#FF8FAB', '#B47CFF', '#5C6F8F'],
        'titles': {'font': 'Segoe UI', 'focus_font': None, 'size': 28, 'bold': True, 'focus_bold': True, 'caps': False, 'italic': False,
                   'focus_color': None, 'subtitle_font': 'Segoe UI', 'subtitle_size': 16, 'subtitle_bold': False,
                   'subtitle_italic': False, 'subtitle_color': '#22C7E8', 'lead_bold': False, 'focus_italic': False, 'heading_color': None},
        'cell_border': '#080D18', 'cell_border_pt': 1.5,
    },
    'paper': {
        'label': 'Paper',
        'description': 'A printed report: serif type, black rules and no fills; each score written in the colour of its '
                       'band and each GAP with ▲ or ▼ in blue or vermilion, readable with any colour vision.',
        'font': 'Georgia, "Times New Roman", Times, serif', 'number_font': 'Georgia, "Times New Roman", Times, serif',
        'surface': '#FFFEFB', 'slide': '#FFFFFF', 'ink': '#1A1A1A', 'muted': '#A39C90', 'line': '#D9D4C7', 'value_scale': 1,
        'title': '#1A1A1A', 'title_accent': '#7A1F1F', 'subtitle': '#555555', 'accent': '#7A1F1F',
        'header': '#F2EFE8', 'header_text': '#1A1A1A', 'soft_header': '#FBFAF7', 'soft_header_text': '#1A1A1A',
        'weight': '#555555', 'maximum': '#7A1F1F', 'gap_header': '#E9E4D8', 'gap_cell': '#F7F4EE',
        'group': '#F7F4EE', 'group_alt': '#EFEAE0', 'category': '#F7F4EE', 'kpi': '#FFFFFF', 'kpi_alt': '#FBFAF7',
        'total': '#EFEAE0', 'subtotal': '#F7F4EE', 'summary_total': '#EFEAE0', 'row_alt': '#FBFAF7', 'border': '#D9D4C7',
        'bands': {'Low': '#F3DEDA', 'Medium': '#F5EDD6', 'High': '#E2EBDA', 'UltraHigh': '#DCE6EF', 'Unavailable': '#EFECE6'},
        'band_strong': {'Low': '#9B2C2C', 'Medium': '#8A6D1A', 'High': '#2F6B3A', 'UltraHigh': '#1F4E79'},
        'gap_negative': '#B23A1E', 'gap_positive': '#1F4E79', 'gap_neutral': '#FFFFFF', 'gap_names': ['Blue', 'Vermilion'],
        'best': '#DCE6EF', 'worst': '#F3DEDA',
        'loss': '#B23A1E', 'gain': '#1F4E79', 'loss_text': '#B23A1E', 'gain_text': '#1F4E79',
        'voice': '#8C7B5A', 'data': '#2F3B4A',
        'ranks': ['#1F4E79', '#6E8FAE', '#C9A27A', '#B23A1E'],
        'stake': ['#6B1D10', '#B23A1E', '#D9A08F'],
        'loss_ramp': ['#EADFC8', '#7A1F1F'],
        'environments': ['#7B2D3B', '#D9A441', '#3E5C5A', '#D8CFC0', '#1A1A1A'],
        'categories': ['#2F3B4A', '#1F4E79', '#8C7B5A', '#6E8FAE', '#B23A1E', '#5F7F4F', '#A0896A', '#4A4A4A'],
        'kpi_reliable': '#E2EBDA', 'kpi_diff': '#F5EDD6',
        'scale': ['#9B2C2C', '#C46A3A', '#C9A227', '#7FA06A', '#2F6B3A'],
        'series': ['#2F3B4A', '#8DA2B8', '#5F7F4F', '#C9A27A', '#8C5A4A', '#7B6F8F', '#D9D4C7'],
        'titles': {'font': 'Georgia', 'focus_font': None, 'size': 30, 'bold': False, 'focus_bold': False, 'caps': False, 'italic': False,
                   'focus_color': None, 'subtitle_font': 'Georgia', 'subtitle_size': 16, 'subtitle_bold': False,
                   'subtitle_italic': True, 'subtitle_color': '#7A1F1F', 'lead_bold': False, 'focus_italic': True, 'heading_color': None},
        'cell_border': '#D9D4C7', 'cell_border_pt': 0.5,
    },
    'heatmap': {
        'label': 'Heatmap',
        'description': 'Light heat tiles: every score a soft tile on the red, amber, green and teal scale of its band and '
                       'every GAP a tile as strong as the GAP, with outlined subtotals and light headers.',
        'font': '"Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
        'number_font': '"Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
        'surface': '#FFFFFF', 'slide': '#FFFFFF', 'ink': '#1F2A37', 'muted': '#8A96A0', 'line': '#E6EAEE', 'value_scale': 1.05,
        'title': '#1F2A37', 'title_accent': '#2A9D8F', 'subtitle': '#5B6B78', 'accent': '#2A9D8F',
        'header': '#E9EEF2', 'header_text': '#1F2A37', 'soft_header': '#F3F5F7', 'soft_header_text': '#1F2A37',
        'weight': '#457B9D', 'maximum': '#E05A4F', 'gap_header': '#FCE6C4', 'gap_cell': '#FEF5E7',
        'group': '#F3F5F7', 'group_alt': '#EAEEF2', 'category': '#F0F3F5', 'kpi': '#F7F9FA', 'kpi_alt': '#EEF4F8',
        'total': '#E9EEF2', 'subtotal': '#F0F3F5', 'summary_total': '#E9EEF2', 'row_alt': '#FAFBFC', 'border': '#FFFFFF',
        'bands': {'Low': '#F9D5D3', 'Medium': '#FCE6C4', 'High': '#D6EDD9', 'UltraHigh': '#CDE9E6', 'Unavailable': '#ECEFF2'},
        'band_strong': {'Low': '#E05A4F', 'Medium': '#E89B2E', 'High': '#5FA35A', 'UltraHigh': '#2A9D8F'},
        'gap_negative': '#E05A4F', 'gap_positive': '#2A9D8F', 'gap_neutral': '#FFFFFF', 'gap_names': ['Teal', 'Red'],
        'best': '#D3EDE4', 'worst': '#F9D5D3',
        'loss': '#E05A4F', 'gain': '#2A9D8F', 'loss_text': '#A63A33', 'gain_text': '#1F6F66',
        'voice': '#E89B2E', 'data': '#2A9D8F',
        'ranks': ['#2A9D8F', '#8AB17D', '#E89B2E', '#E05A4F'],
        'stake': ['#B8463D', '#E05A4F', '#F2A69F'],
        'loss_ramp': ['#CDE9E6', '#E05A4F'],
        'environments': ['#3D405B', '#B5838D', '#A8DADC', '#9C6644', '#CED4DA'],
        'categories': ['#2A9D8F', '#E05A4F', '#457B9D', '#E89B2E', '#8AB17D', '#E9C46A', '#6D597A', '#5FA35A'],
        'kpi_reliable': '#D7EFE9', 'kpi_diff': '#FDE8CF',
        'scale': ['#E05A4F', '#EE9A5B', '#F3C969', '#8CC084', '#2A9D8F'],
        'series': ['#457B9D', '#A8DADC', '#2A9D8F', '#E9C46A', '#E76F51', '#8E7DBE', '#DDE3E8'],
        'titles': {'font': 'Segoe UI', 'focus_font': None, 'size': 28, 'bold': True, 'focus_bold': True, 'caps': False, 'italic': False,
                   'focus_color': None, 'subtitle_font': 'Segoe UI', 'subtitle_size': 16, 'subtitle_bold': False,
                   'subtitle_italic': False, 'subtitle_color': None, 'lead_bold': False, 'focus_italic': False, 'heading_color': None},
        'cell_border': '#FFFFFF', 'cell_border_pt': 2.0,
    },
}

# The colours the export code writes, besides the tokens of the NetCheck theme, with the token each one stands for (pure
# colours such as #FF0000 are left out: an operator may have them).
_EXTRA_SOURCES = {
    '#228B22': 'gain_text', '#CC2424': 'loss_text', '#DDEBE6': 'soft_header', '#E57373': 'gap_negative',
    '#70AD47': 'gap_positive',
}
_LIST_TOKENS = ('ranks', 'stake', 'loss_ramp', 'environments', 'categories')
# Tokens whose NetCheck colour also names another token: the first one listed wins.
_TOKEN_ORDER = ('title', 'subtitle', 'header', 'soft_header', 'soft_header_text', 'weight', 'maximum', 'gap_header',
                'gap_cell', 'group', 'group_alt', 'category', 'kpi', 'kpi_alt', 'total', 'subtotal', 'summary_total',
                'best', 'worst', 'loss', 'gain', 'loss_text', 'gain_text', 'voice', 'data', 'kpi_reliable', 'kpi_diff',
                'accent', 'border', 'row_alt')

_ACTIVE: contextvars.ContextVar[str] = contextvars.ContextVar('scoring_theme', default=DEFAULT_THEME)


def normalize_theme(name: Any) -> str:
    """A known theme id (case and spaces aside), else the default."""
    key = str(name or '').strip().casefold().replace(' ', '').replace('-', '').replace('_', '')
    return key if key in THEMES else DEFAULT_THEME


def get_theme(name: Any = None) -> dict[str, Any]:
    """The tokens of a theme (the active one without ``name``), with its ``id``."""
    key = normalize_theme(name) if name is not None else _ACTIVE.get()
    return {'id': key, **THEMES[key]}


def active_theme() -> dict[str, Any]:
    return get_theme()


@contextmanager
def use_theme(name: Any) -> Iterator[dict[str, Any]]:
    """Make a theme the active one while a document is exported."""
    token = _ACTIVE.set(normalize_theme(name))
    try:
        yield get_theme()
    finally:
        _ACTIVE.reset(token)


def _hex(color: Any) -> str | None:
    text = str(color or '').strip().lstrip('#').upper()
    return f'#{text}' if len(text) == 6 and all(char in '0123456789ABCDEF' for char in text) else None


def _source_map() -> dict[str, tuple[str, int | str | None]]:
    """Each NetCheck colour with the token (and position or band) it stands for."""
    sources: dict[str, tuple[str, int | str | None]] = {}
    for token in _TOKEN_ORDER:
        sources.setdefault(_hex(_NETCHECK[token]), (token, None))
    for band, color in _NETCHECK['bands'].items():
        sources.setdefault(_hex(color), ('bands', band))
    for token in _LIST_TOKENS:
        for index, color in enumerate(_NETCHECK[token]):
            sources.setdefault(_hex(color), (token, index))
    for color, token in _EXTRA_SOURCES.items():
        sources.setdefault(_hex(color), (token, None))
    return sources


_SOURCES = _source_map()


def _rgb(color: str) -> tuple[int, int, int]:
    return tuple(int(color[index:index + 2], 16) for index in (1, 3, 5))


def blend(start: str, end: str, amount: float) -> str:
    amount = max(0.0, min(1.0, amount))
    return '#{:02X}{:02X}{:02X}'.format(*(round(a + (b - a) * amount) for a, b in zip(_rgb(start), _rgb(end))))


def _gradient_amount(color: str, end: str, start: str = '#FFFFFF') -> float | None:
    """How far a colour lies from ``start`` towards ``end``, when it lies on that blend."""
    low, high, value = _rgb(start), _rgb(end), _rgb(color)
    spans = [high[index] - low[index] for index in range(3)]
    axis = max(range(3), key=lambda index: abs(spans[index]))
    if not spans[axis]:
        return None
    amount = (value[axis] - low[axis]) / spans[axis]
    if not 0 < amount <= 1:
        return None
    if all(abs(low[index] + spans[index] * amount - value[index]) <= 2.5 for index in range(3)):
        return amount
    return None


def themed(color: Any, theme: dict[str, Any] | None = None) -> Any:
    """The colour of the active theme (or ``theme``) that stands for a NetCheck colour: a token, a band, a position of
    a palette or a shade of the GAP scale. Other colours, such as those of the operators, are returned as they are."""
    theme = theme or active_theme()
    key = _hex(color)
    if theme['id'] == DEFAULT_THEME or key is None:
        return color
    prefix = '#' if str(color).strip().startswith('#') else ''
    source = _SOURCES.get(key)
    if source is not None:
        token, position = source
        value = theme[token] if position is None else theme[token][position] if token != 'bands' else theme['bands'][position]
        return prefix + value.lstrip('#')
    for netcheck, token in (('gap_negative', 'gap_negative'), ('gap_positive', 'gap_positive')):
        amount = _gradient_amount(key, _NETCHECK[netcheck], _NETCHECK['gap_neutral'])
        if amount is not None:
            return prefix + blend(theme['gap_neutral'], theme[token], amount).lstrip('#')
    return color


def gap_share(color: Any) -> float:
    """How strong a shade of the NetCheck GAP scale is, from 0 (white, no GAP) to 1 (the strongest GAP of its table)."""
    key = _hex(color)
    if key is None:
        return 0.0
    for token in ('gap_negative', 'gap_positive'):
        amount = _gradient_amount(key, _NETCHECK[token], _NETCHECK['gap_neutral'])
        if amount is not None:
            return min(1.0, amount / .85)
    return 0.0


def themed_rgb(color: tuple[int, int, int] | list[int], theme: dict[str, Any] | None = None) -> tuple[int, int, int]:
    """:func:`themed` for an (r, g, b) colour."""
    value = themed('#{:02X}{:02X}{:02X}'.format(*color), theme)
    return _rgb(value) if isinstance(value, str) and value.startswith('#') else tuple(color)


def themes_payload() -> dict[str, Any]:
    """The themes and the NetCheck colours they translate, for the page."""
    sources = [[color, token, position] for color, (token, position) in _SOURCES.items()]
    return {'default': DEFAULT_THEME, 'themes': [{'id': key, **tokens} for key, tokens in THEMES.items()],
            'sources': sources}


# The neutral colours the chart renderer of PPT Dashboards (dashboard_charts.js) draws with, by role: what a theme
# translates (series, operator, vendor and threshold colours stay as they are).
_RENDERER_ROLES = {
    'title': ('#1D3345',),
    'header': ('#23384A',),
    'strong': ('#263B4A', '#34495A'),
    'text': ('#405765', '#4E6271', '#495057', '#566A78', '#5A6B78', '#607887', '#61727D', '#62727E'),
    'soft': ('#868E96', '#8296A3'),
    'axis': ('#AEBBC4', '#A8B7C0', '#B5C0C8', '#BCC8D0'),
    'grid': ('#C8D2D9', '#CDD7DE', '#D7DEE3', '#D9E1E6', '#E4E9ED', '#E8ECEF'),
    'alternate': ('#F4F7F9',),
}


# The light panels of the renderer's maps, which only a dark theme recolours.
_RENDERER_DARK_ROLES = {'panel': ('#EDF4F0',), 'panel_line': ('#D8E5DF', '#B9CDC4')}


def dashboard_chart_style(theme: dict[str, Any] | str | None = None) -> dict[str, Any]:
    """The style of a theme for the chart renderer of PPT Dashboards (the ``style`` of a chart model): its font and the
    colours that replace the renderer's greys. On the white slides of a light theme the text is the theme's ink and the
    table headers its header colour (its title colour when that header carries dark text); a dark theme (Midnight)
    paints the charts in its surface (``background``) with its light ink, as its slides."""
    theme = theme if isinstance(theme, dict) else get_theme(theme)
    luminance = lambda color: sum(weight * channel for weight, channel in zip((.299, .587, .114), _rgb(color))) / 255
    header = theme['header'] if luminance(theme['header_text']) > .5 else theme['title']
    if luminance(theme.get('slide') or '#FFFFFF') < .5:
        # A dark theme (Midnight): the charts are cards of its surface with its light ink, as its slides.
        ink, background = theme['ink'], theme['surface']
        colours = {'title': theme['title'], 'header': header, 'strong': ink, 'text': blend(ink, background, .15),
                   'soft': blend(ink, background, .35), 'axis': blend(ink, background, .55), 'grid': blend(ink, background, .82),
                   'alternate': theme['row_alt'], 'panel': theme['row_alt'], 'panel_line': theme['border']}
        roles = {**_RENDERER_ROLES, **_RENDERER_DARK_ROLES}
        return {'theme': theme.get('id'), 'font': theme['font'], 'background': background,
                'colours': {source: colours[role] for role, sources in roles.items() for source in sources}}
    ink = theme['ink']
    colours = {'title': theme['title'], 'header': header, 'strong': ink, 'text': blend(ink, '#FFFFFF', .2), 'soft': blend(ink, '#FFFFFF', .45),
               'axis': blend(ink, '#FFFFFF', .62), 'grid': blend(ink, '#FFFFFF', .86), 'alternate': theme['row_alt']}
    return {'theme': theme['id'] if 'id' in theme else None, 'font': theme['font'],
            'colours': {source: colours[role] for role, sources in _RENDERER_ROLES.items() for source in sources}}


def user_theme_key(username: str, module: str = 'scoring') -> str:
    return f'{module}_theme:{username}'


def load_user_theme(task_repository: Any, username: str, module: str = 'scoring') -> str:
    """The theme the user chose in a module (Scoring & GAP Analysis, or network_insights) in this workspace, else the
    default."""
    return normalize_theme(task_repository.get_workspace_state(user_theme_key(username, module)))


def save_user_theme(task_repository: Any, username: str, name: Any, module: str = 'scoring') -> str:
    theme = normalize_theme(name)
    task_repository.set_workspace_state(user_theme_key(username, module), theme)
    return theme
