"""The correspondence between the former Root Categories and Root Causes and the current ones (ticket #139).

Up to v0.12.4 a Root Category joined the problem with its technology and direction (Poor Coverage LTE, DL Interference
NR…) and some Root Causes repeated it (Coverage, DL interference). The current catalog has generic categories, specific
causes and the technology of the call as a value of its own. ``translate`` turns a former pair into the current
(category, cause, technology); the one-time migration of the workspaces, the imports and transfers of a former catalog
or decisions and the restores of former backups all use it, so a former value always lands on the same current one.
"""
from __future__ import annotations

from typing import Any

from src.modules.nq import nq_catalog

# Former Root Category -> (current Root Category, technology, the cause it implies when the decision has none). A current
# category of None splits the former one by the cause of the decision (its category in the current catalog), the name
# after it is the category when the cause says nothing.
_SPLIT = None
_TECHNOLOGIES = (('LTE', 'LTE'), ('NR', 'NR'), ('2G/3G', ''))
CATEGORY_MAP: dict[str, tuple[str | None, str, str, str]] = {
    **{f'Poor Coverage {suffix}': ('Coverage', '', technology, '') for suffix, technology in _TECHNOLOGIES},
    **{f'DL Interference {suffix}': ('Interference', '', technology, 'DL interference') for suffix, technology in _TECHNOLOGIES},
    **{f'UL Interference {suffix}': ('Interference', '', technology, 'UL interference') for suffix, technology in _TECHNOLOGIES},
    'BLER LTE': ('Radio Link Quality', '', 'LTE', 'High DL BLER'),
    'BLER NR': ('Radio Link Quality', '', 'NR', 'High DL BLER'),
    'Mobility LTE': ('Mobility', '', 'LTE', ''),
    'Mobility NR': ('Mobility', '', 'NR', ''),
    'UE / Test Setup Issue': ('Device & Test Setup', '', '', ''),
    'Unclear': ('Validation', '', '', 'Unclear'),
    'UNKNOWN': ('Validation', '', '', 'Unclear'),
    'Operational': ('Network Operations', '', '', ''),
    'Invalidated': ('Validation', '', '', 'Invalidated'),
    'Procedure Overlap': ('Configuration & Planning', '', '', 'Procedure overlap'),
    'Radio Configuration Inconsistency': ('Configuration & Planning', '', '', 'Radio configuration inconsistency'),
    'RAN Planning & Design': ('Configuration & Planning', '', '', ''),
    'High PRB Utilization': ('Capacity', '', '', 'Cell overload'),
    'No Failure/ Drop': ('Validation', '', '', 'Normal release'),
    'IMSI Issue': ('Registration & Authentication', '', '', 'Subscriber identity (IMSI)'),
    'VONR not Enabled in Source/Neighbor Site': ('Configuration & Planning', '', 'NR', 'VoNR not enabled in source/neighbor site'),
    'EPS Fallback': ('Fallback & Legacy', '', '', 'EPS fallback failure'),
    'RAN Capacity': (_SPLIT, 'Capacity', '', ''),
    'Protocol / Server': (_SPLIT, 'Server & Protocol', '', ''),
    'RAN Performance': (_SPLIT, 'Radio Signalling', '', ''),
    'Core Network': (_SPLIT, 'Session & Mobility Management', '', ''),
    'Authentication & Registration': (_SPLIT, 'Registration & Authentication', '', ''),
    'IMS / VoLTE': (_SPLIT, 'Voice Core (IMS)', '', ''),
    'E2E': (_SPLIT, 'End-to-End', '', ''),
    # The categories a workspace made of the Ericsson RCA values without a cause and of the analyses still open.
    **{f'Additional Investigation {suffix}': ('Validation', '', technology, 'Further investigation required')
       for suffix, technology in (('LTE', 'LTE'), ('NR', 'NR'), ('UMTS/GSM', ''))},
    **{f'Other {suffix}': ('Validation', '', technology, 'Unclear') for suffix, technology in (('LTE', 'LTE'), ('NR', 'NR'), ('GSM', '2G'))},
}
# Former Root Cause -> current one (the others keep their name).
CAUSE_MAP = {
    'Coverage': 'DL coverage',
    'BLER': 'High DL BLER',
    'RRC layer': 'Radio link failure',
}
_CATEGORIES = {key.casefold(): value for key, value in CATEGORY_MAP.items()}
_CAUSES = {key.casefold(): value for key, value in CAUSE_MAP.items()}
_CURRENT_CATEGORIES = {name.casefold(): name for name, _domain, _keywords in nq_catalog.DEFAULT_CATEGORIES}
_CAUSE_CATEGORIES = {name.casefold(): category for name, category in nq_catalog.DEFAULT_CAUSE_CATEGORIES.items()}
# The former names that are no longer in the catalog: a workspace drops them (and keeps the names of its own).
FORMER_CATEGORIES = frozenset(_CATEGORIES)
FORMER_CAUSES = frozenset(_CAUSES)


def is_former_category(name: Any) -> bool:
    return str(name or '').strip().casefold() in _CATEGORIES


def translate_cause(cause: Any) -> str:
    """The current name of a former Root Cause (the same name when it was kept or is a workspace's own)."""
    text = str(cause or '').strip()
    return _CAUSES.get(text.casefold(), text)


def translate(category: Any, cause: Any, technology: Any = '') -> dict[str, str]:
    """The current Root Category, Root Cause and technology of a former pair; a pair already current (or of the
    workspace's own values) is returned as it is. A technology given is kept."""
    category_text, cause_text = str(category or '').strip(), translate_cause(cause)
    technology_text = str(technology or '').strip()
    found = _CATEGORIES.get(category_text.casefold())
    if found is None:
        # The category of the cause when the catalog maps it to one (a Root Category always follows its Root Cause).
        current = _CAUSE_CATEGORIES.get(cause_text.casefold()) or _CURRENT_CATEGORIES.get(category_text.casefold(), category_text)
        return {'category': current, 'cause': cause_text, 'technology': nq_catalog.canonical_technology(technology_text)}
    target, fallback, implied_technology, implied_cause = found
    cause_text = cause_text or implied_cause
    # The category of the cause when the catalog maps it to one: a Root Category always follows its Root Cause.
    target = _CAUSE_CATEGORIES.get(cause_text.casefold()) or (fallback if target is _SPLIT else target)
    return {'category': target, 'cause': cause_text,
            'technology': nq_catalog.canonical_technology(technology_text or implied_technology)}


def translate_values(values: dict[str, Any], category_key: str = 'root_category', cause_key: str = 'root_cause',
                     technology_key: str = 'root_technology') -> dict[str, Any]:
    """A copy of a record (a decision, an imported row) with its category, cause and technology translated."""
    if category_key not in values and cause_key not in values:
        return dict(values)
    result = translate(values.get(category_key), values.get(cause_key), values.get(technology_key))
    translated = dict(values)
    if category_key in values or result['category']:
        translated[category_key] = result['category']
    if cause_key in values or result['cause']:
        translated[cause_key] = result['cause']
    if result['technology'] or technology_key in values:
        translated[technology_key] = result['technology']
    return translated


def is_former_catalog(catalog: Any) -> bool:
    """Whether a catalog (as exported or transferred) is a former one: it names former categories and none of the
    current generic ones."""
    if not isinstance(catalog, dict):
        return False
    names = {str((item or {}).get('name') or '').strip().casefold() for item in catalog.get('categories') or [] if isinstance(item, dict)}
    return bool(names & FORMER_CATEGORIES) and not names & set(_CURRENT_CATEGORIES)


def translate_catalog(catalog: dict[str, Any]) -> dict[str, Any]:
    """The current catalog for a former one: the current default domains, categories and causes, with the keywords a
    workspace gave the values that keep their name, and its own values (those neither former nor current) after them."""
    defaults = nq_catalog.default_root_catalog()
    current_domains = {item['name'].casefold() for item in defaults['domains']}
    current_categories = {item['name'].casefold() for item in defaults['categories']}
    current_causes = {item['name'].casefold(): item for item in defaults['causes']}
    own_domains = [dict(item) for item in catalog.get('domains') or [] if isinstance(item, dict)
                   and str(item.get('name') or '').casefold() not in current_domains
                   and str(item.get('name') or '').casefold() not in {'core epsfb', 'aaa'}]
    own_categories = [dict(item) for item in catalog.get('categories') or [] if isinstance(item, dict)
                      and str(item.get('name') or '').casefold() not in current_categories and not is_former_category(item.get('name'))]
    own_causes = []
    for item in catalog.get('causes') or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get('name') or '').strip()
        if name.casefold() in current_causes:
            # A cause kept by name keeps the keywords the workspace gave it besides the current ones.
            keywords = list(dict.fromkeys([*current_causes[name.casefold()]['keywords'], *(item.get('keywords') or [])]))
            current_causes[name.casefold()]['keywords'] = keywords
        elif name.casefold() not in FORMER_CAUSES:
            entry = dict(item)
            entry['category'] = translate(entry.get('category'), '')['category'] if entry.get('category') else ''
            if str(entry.get('domain') or '').casefold() in {'core epsfb', 'aaa'}:
                entry['domain'] = 'Core'
            own_causes.append(entry)
    for item in own_categories:
        if str(item.get('domain') or '').casefold() in {'core epsfb', 'aaa'}:
            item['domain'] = 'Core'
    # A domain of its own is kept while a category or cause of its own is in it (the former ones made of the analyses,
    # such as Additional Investigation, leave with them).
    used = {str(item.get('domain') or '').casefold() for item in (*own_categories, *own_causes)}
    own_domains = [item for item in own_domains if str(item.get('name') or '').casefold() in used]
    return {'domains': [*defaults['domains'], *own_domains], 'categories': [*defaults['categories'], *own_categories],
            'causes': [*defaults['causes'], *own_causes]}
