"""The panels of Network Insights in three categories (Summary, Radio Performance, Network & Spectrum) after Launch
Analysis: each category a panel holding its panels, and an entry of the floating section bar and of the sections menu
that opens the list of its panels."""
from __future__ import annotations

import re
from pathlib import Path

from src.modules.module_labels import MODULE_SECTIONS, section_anchor

TEMPLATE = Path(__file__).resolve().parents[1] / 'src' / 'web_interface' / 'templates' / 'network_insights.html'


def test_every_panel_is_a_part_of_its_category() -> None:
    sections = MODULE_SECTIONS['network-insights']
    assert [entry[0] for entry in sections] == ['Launch Analysis', 'Summary', 'Radio Performance', 'Network & Spectrum']
    assert [part[1] for part in sections[2][3]] == ['Coverage & Interference Maps', 'RF Quality', 'Latency & Interactivity',
                                                    'Serving Cells', '5G Availability']
    page = TEMPLATE.read_text(encoding='utf-8')
    for heading, _name, _icon, *parts in sections[1:]:
        # The category panel, with its panels inside it, in the order of the bar.
        category = page.split(f'<h2>{heading.replace("&", "&amp;")}</h2>', 1)[1].split('ni-category-panel', 1)[0]
        anchors = re.findall(r'<details id="(section-[^"]+)" class="panel collapsible-panel ni-panel"', category)
        assert anchors == [part[0] for part in parts[0]], heading
        for anchor, name, _part_icon in parts[0]:
            assert anchor == section_anchor(name)
            assert f'<h2>{name.replace("&", "&amp;")}</h2>' in category
