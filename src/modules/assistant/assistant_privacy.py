"""Pseudonymization of the AI Assistant: what leaves the server names no customer.

Before a question, the workspace context or the result of a tool is sent to an AI engine, every name of an operator,
vendor, region, cluster, city, campaign, methodology, workspace or user is replaced by a code (``OP1``, ``VN2``,
``RG3``…), also inside identifiers joined by underscores (``Vodafone_Voice`` is sent as ``OP1_Voice``). The engine
reasons on the codes; the server puts the real names back in its answer and in the arguments of the tools it asks for.
Figures, dates and the words of the question travel as they are.

The codes of a conversation never change: they are kept with it, and a name that appears later takes the next free
code of its kind, so earlier answers keep meaning the same thing.
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any

# The kinds of names and the prefix of their codes.
KINDS: dict[str, str] = {
    'operator': 'OP', 'vendor': 'VN', 'region': 'RG', 'cluster': 'CL', 'city': 'CT', 'campaign': 'CP',
    'methodology': 'MT', 'workspace': 'WS', 'user': 'US',
}
KIND_LABELS = {'operator': 'Operator', 'vendor': 'Vendor', 'region': 'Region', 'cluster': 'Cluster', 'city': 'City',
               'campaign': 'Campaign', 'methodology': 'Methodology', 'workspace': 'Workspace', 'user': 'User'}
# A code stands alone or inside an identifier joined by underscores (OP1_Voice), never inside a word or a number.
CODE = re.compile(r'(?<![A-Za-z0-9])(' + '|'.join(KINDS.values()) + r')(\d{1,5})(?![A-Za-z0-9])')
# Operators and vendors of mobile networks that are masked even when the workspace has no data of them, so a question
# or a glossary entry that names one sends no name either.
WELL_KNOWN = {
    'operator': ('Vodafone', 'Three', 'H3G', 'Hutchison', 'EE', 'O2', 'Telefonica', 'Telefónica', 'Movistar', 'Orange',
                 'Lebara', 'Virgin Media', 'VMO2', 'Sky Mobile', 'BT', 'Deutsche Telekom', 'T-Mobile', 'Swisscom',
                 'Proximus', 'KPN', 'Telia', 'Telenor', 'Tele2', 'Wind Tre', 'Iliad', 'Bouygues', 'SFR', 'Masmovil',
                 'MásMóvil', 'Verizon', 'AT&T'),
    'vendor': ('Ericsson', 'Nokia', 'NSN', 'Nokia Siemens Networks', 'Huawei', 'Samsung', 'ZTE', 'Mavenir', 'Parallel Wireless',
               'NEC', 'Fujitsu', 'Cisco'),
}
# Names that are also common words: masked only when written with a capital (Three, not "three vendors").
CAPITALIZED_ONLY = {'three', 'orange'}
# Words that are never names to mask, whatever list holds them (the vendor of no cell, the groups of the scoring...).
NEVER_MASKED = {'all', 'unknown', 'mixed', 'none', 'other', 'others', 'n/a', 'na', 'total', 'combined', 'overall'}
# User names that are also words of the questions and the Help (generic accounts): their code is only given to the
# values of the user columns (mask_value), never to the words of a text.
ACCOUNT_WORDS = {'admin', 'administrator', 'super', 'superadmin', 'demo', 'guest', 'test', 'tester', 'user', 'users',
                 'system', 'viewer', 'editor', 'analyst', 'reviewer', 'operator', 'manager', 'support', 'service', 'root',
                 'data', 'voice', 'speech', 'team', 'scoring', 'report', 'reports'}
# Vendor groups of the scoring around a vendor name: the name inside is masked, the group stays readable.
_VENDOR_GROUPS = (re.compile(r'^(?P<name>.+?)\s*\(Mixed\)$', re.IGNORECASE),
                  re.compile(r'^Mixed \(non-(?P<name>.+)\)$', re.IGNORECASE))


def vendor_base_name(value: str) -> str:
    """The vendor named in a vendor group (``Ericsson (Mixed)`` and ``Mixed (non-Ericsson)`` name Ericsson)."""
    text = str(value or '').strip()
    for pattern in _VENDOR_GROUPS:
        match = pattern.match(text)
        if match:
            return match.group('name').strip()
    return text


def _written_as_name(found: str) -> bool:
    """Whether a spelling found in a text is the name: two-letter names (EE, VF) only in capitals and the names that are
    also common words (Three) only with a capital, so the words of a question are not taken for them."""
    if len(found) <= 2 and not any(character.isdigit() for character in found):
        return found.isupper()
    if found.casefold() in CAPITALIZED_ONLY:
        return found[:1].isupper()
    return True


# The names of the fields of the documents the tools give (snake_case): never masked, so default_gap_reference keeps its
# name in a workspace called Default. The keys that are values (the operators of a matrix) are masked like any value.
FIELD_KEY = re.compile(r'[a-z][a-z0-9]*(?:_[a-z0-9]+)*')
FIELD_KEYS_IN_JSON = re.compile(r'"[a-z][a-z0-9]*(?:_[a-z0-9]+)*"\s*:')


def _field_key(key: Any) -> bool:
    return isinstance(key, str) and FIELD_KEY.fullmatch(key) is not None


def _name_like_user(username: str) -> bool:
    """Whether a user name can be masked in the texts: not a word of the questions or the Help (super, data)."""
    text = str(username or '').strip()
    return len(text) >= 4 and text.casefold() not in ACCOUNT_WORDS


def _maskable(term: str) -> bool:
    text = str(term or '').strip()
    # Pure numbers (the alias 3 of Three) would mask the figures; single characters mean nothing on their own.
    return len(text) >= 2 and not re.fullmatch(r'[\d\s.,%+-]+', text) and text.casefold() not in NEVER_MASKED


class Pseudonymizer:
    """The codes of the names of one conversation, and the masking and unmasking of texts and documents."""

    def __init__(self, state: dict[str, Any] | None = None) -> None:
        state = state if isinstance(state, dict) else {}
        # code -> {'kind', 'name'}: the name shown for the code (the canonical name of an operator).
        self.codes: dict[str, dict[str, str]] = {
            str(code): {'kind': str(entry.get('kind') or ''), 'name': str(entry.get('name') or '')}
            for code, entry in (state.get('codes') or {}).items() if isinstance(entry, dict) and entry.get('name')
        }
        # spelling (casefold) -> code: every spelling of a name (its aliases too) and the code it takes.
        self.terms: dict[str, str] = {str(term): str(code) for term, code in (state.get('terms') or {}).items()
                                      if str(code) in self.codes}
        # spelling (casefold) -> code: the spellings masked only as values of their kind (mask_value), never in a text:
        # the user names that are also words (super, demo).
        self.quiet: dict[str, str] = {str(term): str(code) for term, code in (state.get('quiet') or {}).items()
                                      if str(code) in self.codes}
        self._pattern: re.Pattern[str] | None = None

    # -- building ---------------------------------------------------------------------------------------------------

    def state(self) -> dict[str, Any]:
        return {'codes': self.codes, 'terms': self.terms, 'quiet': self.quiet}

    def _next_code(self, kind: str) -> str:
        prefix = KINDS[kind]
        used = [int(match.group(2)) for code in self.codes if (match := CODE.fullmatch(code)) and match.group(1) == prefix]
        return f'{prefix}{max(used, default=0) + 1}'

    def _known(self, spelling: str, kind: str) -> str | None:
        for found in (self.terms.get(spelling.casefold()), self.quiet.get(spelling.casefold())):
            if found and self.codes[found]['kind'] == kind:
                return found
        return None

    def add(self, kind: str, name: str, aliases: Iterable[str] = (), quiet: Iterable[str] = ()) -> str | None:
        """The code of a name (a new one when it has none), with its aliases as other spellings of it; the spellings in
        ``quiet`` are masked only as values of their kind (mask_value), not in the texts."""
        name = str(name or '').strip()
        if kind not in KINDS or not _maskable(name):
            return self.terms.get(name.casefold())
        spellings = [name, *(str(alias).strip() for alias in aliases)]
        quiet_spellings = {str(spelling).strip().casefold() for spelling in quiet}
        code = next((found for spelling in spellings if (found := self._known(spelling, kind))), None)
        if code is None:
            code = self._next_code(kind)
            self.codes[code] = {'kind': kind, 'name': name}
        for spelling in spellings:
            key = spelling.casefold()
            if not _maskable(spelling) or key in self.terms:
                continue
            if key in quiet_spellings:
                self.quiet.setdefault(key, code)
            else:
                self.terms[key] = code
                self.quiet.pop(key, None)
                self._pattern = None
        return code

    def add_user(self, username: str, full_name: str = '') -> str | None:
        """A user of the tool: its code shows its user name (the value the columns of the users hold), and its full
        name is another spelling of it. A user name that is also a word (super, demo) is masked only as a value of a user
        column."""
        username, full_name = str(username or '').strip(), re.sub(r'\s+', ' ', str(full_name or '')).strip()
        if not username:
            return None
        aliases = [full_name] if len(full_name.split(' ')) >= 2 else []
        quiet = [] if _name_like_user(username) else [username]
        # The full name of a generic account (Super Admin) is quiet too: its words are words of the Help.
        if aliases and all(word.casefold() in ACCOUNT_WORDS for word in full_name.split(' ')):
            quiet.append(full_name)
        return self.add('user', username, aliases, quiet=quiet)

    def add_vendor(self, value: str) -> str | None:
        """A vendor value of the CDRs or the scoring: its vendor name is masked (groups such as ``Ericsson (Mixed)``
        keep their words around the code)."""
        return self.add('vendor', vendor_base_name(value))

    # -- masking ----------------------------------------------------------------------------------------------------

    def _regex(self) -> re.Pattern[str] | None:
        if self._pattern is None:
            terms = sorted(self.terms, key=len, reverse=True)
            if not terms:
                return None
            # A name stands alone or inside an identifier joined by underscores (Vodafone_Voice), never inside a word.
            self._pattern = re.compile(
                r'(?<![^\W_])(' + '|'.join(re.escape(term) for term in terms) + r')(?![^\W_])', re.IGNORECASE)
        return self._pattern

    def mask_text(self, text: Any) -> str:
        """The text with every known name replaced by its code; two-letter names (EE, O2, VF) only in capitals, as they
        are written, so words of the question are not taken for them."""
        value = '' if text is None else str(text)
        pattern = self._regex()
        if not value or pattern is None:
            return value

        def replace(match: re.Match[str]) -> str:
            found = match.group(1)
            return self.terms.get(found.casefold(), found) if _written_as_name(found) else found
        return pattern.sub(replace, value)

    def mask(self, document: Any) -> Any:
        """A JSON document with every string masked, its keys too, except the names of its fields (see FIELD_KEY)."""
        if isinstance(document, str):
            return self.mask_text(document)
        if isinstance(document, dict):
            return {key if _field_key(key) else self.mask_text(key): self.mask(value) for key, value in document.items()}
        if isinstance(document, (list, tuple)):
            return [self.mask(value) for value in document]
        return document

    def mask_value(self, kind: str, value: Any) -> Any:
        """One value of a known kind (an operator, a vendor…): its code, adding the value when it is new."""
        if value is None or str(value).strip() == '':
            return value
        if kind == 'vendor':
            base = vendor_base_name(str(value))
            code = self.add('vendor', base)
            return str(value).replace(base, code) if code else self.mask_text(value)
        if kind == 'user':
            code = self._known(str(value).strip(), 'user') or self.add_user(str(value))
            return code or value
        code = self.add(kind, str(value)) if kind in KINDS else None
        return code or self.mask_text(value)

    # -- unmasking --------------------------------------------------------------------------------------------------

    def name_of(self, code: str) -> str | None:
        entry = self.codes.get(str(code).strip().upper())
        return entry['name'] if entry else None

    def unmask_text(self, text: Any) -> str:
        """The text with every code replaced by the name it stands for (unknown codes stay)."""
        value = '' if text is None else str(text)
        return CODE.sub(lambda match: (self.codes.get(f'{match.group(1)}{match.group(2)}') or {}).get('name')
                        or match.group(0), value)

    def unmask(self, document: Any) -> Any:
        if isinstance(document, str):
            return self.unmask_text(document)
        if isinstance(document, dict):
            return {key if _field_key(key) else self.unmask_text(key): self.unmask(value) for key, value in document.items()}
        if isinstance(document, (list, tuple)):
            return [self.unmask(value) for value in document]
        return document

    def leaks(self, text: str) -> list[str]:
        """The known names a text still holds (none, once masked): the check before anything is sent."""
        pattern = self._regex()
        if pattern is None:
            return []
        found = []
        # The names of the fields of the JSON documents (default_gap_reference) are the tool's, never a name.
        for match in pattern.finditer(FIELD_KEYS_IN_JSON.sub('"":', text or '')):
            if _written_as_name(match.group(1)):
                found.append(match.group(1))
        return sorted(set(found), key=str.casefold)

    def legend(self) -> list[dict[str, str]]:
        """Every code with its kind and real name, for the page (never sent to the engine)."""
        def order(code: str) -> tuple[int, int]:
            match = CODE.fullmatch(code)
            prefixes = list(KINDS.values())
            return (prefixes.index(match.group(1)), int(match.group(2))) if match else (99, 0)
        return [{'code': code, 'kind': KIND_LABELS.get(entry['kind'], entry['kind']), 'name': entry['name']}
                for code, entry in sorted(self.codes.items(), key=lambda item: order(item[0]))]


def workspace_pseudonymizer(repository: Any, workspace_name: str = '', state: dict[str, Any] | None = None) -> Pseudonymizer:
    """The pseudonymizer of a conversation (``state``: its codes so far) with every name the workspace holds today:
    the operators of its Operator Maps (with their aliases) and of its CDRs, their vendors, regions, clusters, cities
    and campaigns, its scoring methodologies and its own name, the well-known operator and vendor names and the users
    of the tool."""
    pseudonyms = Pseudonymizer(state)
    if workspace_name:
        pseudonyms.add('workspace', workspace_name)
    try:
        groups = repository.list_operator_mapping_groups()
    except Exception:  # noqa: BLE001 - a workspace without Operator Maps
        groups = []
    for group in groups if isinstance(groups, list) else []:
        if isinstance(group, dict) and str(group.get('canonical') or '').strip():
            pseudonyms.add('operator', str(group['canonical']), [str(alias) for alias in group.get('aliases') or []])
    try:
        dataset_ids = [int(row['id']) for row in repository.list_datasets()]
        catalogues = repository.cdr_catalogues_by_dataset(dataset_ids)
    except Exception:  # noqa: BLE001 - no CDR catalogue yet
        catalogues = {}
    fields = (('operators', 'operator'), ('regions', 'region'), ('clusters', 'cluster'), ('cities', 'city'),
              ('campaigns', 'campaign'))
    for catalogue in catalogues.values():
        for field, kind in fields:
            for value in catalogue.get(field) or []:
                pseudonyms.add(kind, value)
    # The vendors as the scoring names them: without the operator of a fallback value (EE - All is no vendor).
    from src.modules.scoring.scoring_vendors import scoring_vendor_names, scoring_vendor_operators
    operators = scoring_vendor_operators(catalogues, groups if isinstance(groups, list) else [])
    for value in scoring_vendor_names([value for catalogue in catalogues.values() for value in catalogue.get('vendors_only') or []],
                                      operators):
        pseudonyms.add_vendor(value)
    for name in methodology_names(repository):
        pseudonyms.add('methodology', name)
    for kind, names in WELL_KNOWN.items():
        for name in names:
            pseudonyms.add(kind, name)
    # The users of the tool (the analysts, assignees and reviewers of the Non-Qualified Calls): their user names and
    # full names.
    try:
        users = repository.list_users()
    except Exception:  # noqa: BLE001 - a repository without the global database
        users = []
    for user in users or []:
        item = dict(user)
        pseudonyms.add_user(str(item.get('username') or ''),
                            f'{str(item.get("first_name") or "").strip()} {str(item.get("last_name") or "").strip()}')
    return pseudonyms


def methodology_names(repository: Any) -> list[str]:
    """The names of the scoring methodologies of the workspace (none before they are imported)."""
    try:
        profiles = repository.get_scoring_profiles()['profiles']
    except (ValueError, KeyError, TypeError):
        return []
    return [str(profile.get('name') or '').strip() for profile in profiles if isinstance(profile, dict)
            and str(profile.get('name') or '').strip()]


def dumps(document: Any) -> str:
    """Compact JSON for the engine."""
    return json.dumps(document, ensure_ascii=False, separators=(',', ':'), default=str)
