"""The CDR Field Dictionary of a workspace: the CDR columns each module reads for every field.

The field profile of the workspace's CDR type (see cdr_field_profiles) lists, for every field, the CDR columns that can
hold it in order of preference. Workspace Config shows them as the CDR Field Dictionary and lets the workspace change the
columns of any field (a provider renames a column, or an export carries the value in another one). Only the changed
fields are saved; they apply wherever the modules read the workspace's field profile and travel with the Mappings &
Reference Data of the workspace (Export / Import, transfers, backup and restore).
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from typing import Any

from src.modules.cdr_field_profiles import CdrFieldProfile
from src.modules.column_names import column_identity

STATE_KEY = 'cdr_field_dictionary'
FORMAT = 'drivetest-analyzer-cdr-field-dictionary'
MAX_COLUMNS = 20
MAX_COLUMN_LENGTH = 200
KIND_LABELS = {'data': 'Data', 'voice': 'Voice', 'speech': 'Speech'}

# The sections of the dictionary: the profile attribute, its title and what its fields are for. An attribute is a
# list of columns, a field → columns dictionary, or a field → CDR type (Data, Voice, Speech) → columns dictionary.
SECTIONS: tuple[tuple[str, str, str], ...] = (
    ('normalised_sources', 'Processing', 'The fields every CDR row gains when it is processed (its result, times, KPIs).'),
    ('fixed_sources', 'CDR-Main fields', 'The main fields added to every CDR (Campaign, Operator, Test Name...).'),
    ('nq_field_sources', 'Non-Qualified Calls', 'The fields of every call of Non-Qualified Calls.'),
    ('nq_qualification_sources', 'Non-Qualified Calls', 'The qualification of a call: it is Non-Qualified when it does not '
                                                       'hold the qualified value of the CDR type.'),
    ('nq_identifier_sources', 'Non-Qualified Calls', 'The identifier of a call or test, so it keeps its follow-up.'),
    ('nq_sample_sources', 'Non-Qualified Calls', 'A Speech sample inside its call.'),
    ('nq_rca_sources', 'DT Analyzer RCA', 'The values of every call the DT Analyzer RCA rules read.'),
    ('rf_field_aliases', 'Network Insights', 'The radio, position and test fields of each CDR type.'),
    ('dimension_aliases', 'Network Insights', 'The dimensions the analyses are split by.'),
    ('cell_columns', 'Vendor Mapping', 'The serving cells of every sample (the first and the last are mapped).'),
    ('time_columns', 'Vendor Mapping', 'When the samples were measured, for the inventory snapshot closest to the CDR.'),
)
_LABELS = {
    'nq_qualification_sources': 'Qualification', 'nq_sample_sources': 'Speech sample', 'cell_columns': 'Serving cells',
    'time_columns': 'Measurement time', 'setup_time_seconds': 'Setup time (s)', 'duration_seconds': 'Duration (s)',
    'throughput_mbps': 'Throughput (Mbit/s)', 'latency_ms': 'Latency (ms)', 'event_start_time': 'Start time',
    'event_end_time': 'End time', 'technology_primary': 'Technology', 'technology_secondary': 'Technology (second side)',
    'packet_loss_pct': 'Packet loss (%)', 'jitter_ms': 'Jitter (ms)', 'lte_rsrp': 'LTE RSRP', 'nr_rsrp': 'NR RSRP',
    'lte_sinr': 'LTE SINR', 'nr_sinr': 'NR SINR', 'earfcn': 'EARFCN', 'nr_pci': 'NR PCI', 'nr_arfcn': 'NR ARFCN',
    'rtt_median': 'RTT (median)', 'cell_id': 'Cell ID', 'site_id': 'Site ID',
}


def _label(key: str, attribute: str = '') -> str:
    """The name of a field: the name of the value of the DT Analyzer RCA, a known name, else its key in words."""
    from src.modules import nq_dta_rca

    if attribute == 'nq_rca_sources' and key in nq_dta_rca.INPUTS:
        return nq_dta_rca.INPUTS[key][0]
    if key in _LABELS:
        return _LABELS[key]
    return re.sub(r'\s+', ' ', key.replace('_', ' ')).strip().capitalize()


def entries(profile: CdrFieldProfile) -> list[dict[str, Any]]:
    """Every field of the dictionary with the columns the profile reads for it, in the order of the sections."""
    rows: list[dict[str, Any]] = []
    for attribute, section, description in SECTIONS:
        value = getattr(profile, attribute)
        base = {'section': section, 'description': description}
        if isinstance(value, tuple):
            rows.append({**base, 'key': attribute, 'label': _label(attribute), 'kind': '', 'defaults': list(value)})
            continue
        for field, sources in value.items():
            if isinstance(sources, dict):
                for kind, columns in sources.items():
                    rows.append({**base, 'key': f'{attribute}.{field}.{kind}', 'label': _label(field, attribute),
                                 'kind': KIND_LABELS.get(kind, kind), 'defaults': list(columns)})
            else:
                rows.append({**base, 'key': f'{attribute}.{field}', 'label': _label(field, attribute), 'kind': '',
                             'defaults': list(sources)})
    return rows


def _columns(values: Any) -> list[str]:
    """The columns of a field, trimmed and without repeats (of the same column regardless of case and separators)."""
    if isinstance(values, str):
        values = values.split(';')
    if not isinstance(values, (list, tuple)):
        raise ValueError('The columns of a field are a list of column names.')
    columns: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = re.sub(r'\s+', ' ', str(value or '')).strip()
        if not text:
            continue
        if len(text) > MAX_COLUMN_LENGTH:
            raise ValueError(f'A column name has at most {MAX_COLUMN_LENGTH} characters.')
        if (identity := column_identity(text) or text.casefold()) not in seen:
            seen.add(identity)
            columns.append(text)
    if len(columns) > MAX_COLUMNS:
        raise ValueError(f'A field reads at most {MAX_COLUMNS} columns.')
    return columns


def normalize_overrides(value: Any, profile: CdrFieldProfile) -> dict[str, list[str]]:
    """The changed fields of a dictionary: known fields only, each with the columns that differ from the profile's."""
    if not isinstance(value, dict):
        return {}
    defaults = {row['key']: row['defaults'] for row in entries(profile)}
    overrides: dict[str, list[str]] = {}
    for key, columns in value.items():
        if str(key) not in defaults:
            continue
        cleaned = _columns(columns)
        if cleaned and cleaned != defaults[str(key)]:
            overrides[str(key)] = cleaned
    return dict(sorted(overrides.items()))


def load_overrides(repository: Any) -> dict[str, list[str]]:
    """The changed fields of the workspace (none until a field is changed, or when they were made for another CDR
    type)."""
    from src.modules.cdr_types import workspace_cdr_type

    try:
        stored = json.loads(str(repository.get_workspace_state(STATE_KEY) or '') or '{}')
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(stored, dict) or str(stored.get('cdr_type') or '') != workspace_cdr_type(repository):
        return {}
    fields = stored.get('fields')
    return {str(key): [str(column) for column in columns] for key, columns in (fields or {}).items()
            if isinstance(columns, list) and columns}


def save_overrides(repository: Any, value: Any, profile: CdrFieldProfile) -> dict[str, list[str]]:
    """Keep the changed fields of the workspace (a field with its default columns, or none, returns to the default)."""
    overrides = normalize_overrides(value, profile)
    repository.set_workspace_state(STATE_KEY, json.dumps({'cdr_type': profile.cdr_type, 'fields': overrides}, ensure_ascii=False))
    return overrides


def apply_overrides(profile: CdrFieldProfile, overrides: dict[str, list[str]]) -> CdrFieldProfile:
    """The profile with the changed fields of a workspace; without changes, the profile itself."""
    if not overrides:
        return profile
    changes: dict[str, Any] = {}
    for key, columns in overrides.items():
        attribute, _, rest = key.partition('.')
        current = changes.get(attribute, getattr(profile, attribute, None))
        if current is None:
            continue
        sources = tuple(columns)
        if not rest:
            if isinstance(current, tuple):
                changes[attribute] = sources
            continue
        field, _, kind = rest.partition('.')
        if not isinstance(current, dict) or field not in current:
            continue
        if kind:
            if not isinstance(current[field], dict) or kind not in current[field]:
                continue
            changes[attribute] = {**current, field: {**current[field], kind: sources}}
        elif not isinstance(current[field], dict):
            changes[attribute] = {**current, field: sources}
    return dataclasses.replace(profile, **changes) if changes else profile


def fingerprint(overrides: dict[str, list[str]]) -> str:
    """A short signature of the changed fields (empty without changes), so the indexes built on them follow them."""
    if not overrides:
        return ''
    return hashlib.sha1(json.dumps(overrides, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()[:10]


def document(repository: Any) -> dict[str, Any]:
    """The changed fields of the workspace as they are exported (with the CDR type they were made for)."""
    from src.modules.cdr_types import workspace_cdr_type

    return {'format': FORMAT, 'version': 1, 'cdr_type': workspace_cdr_type(repository), 'fields': load_overrides(repository)}


def restore_document(repository: Any, value: Any) -> dict[str, list[str]] | None:
    """Replace the changed fields of the workspace with those of an exported dictionary of the same CDR type.

    A dictionary made for another CDR type is left out (its columns belong to another provider) and returns None."""
    from src.modules.cdr_field_profiles import field_profile
    from src.modules.cdr_types import workspace_cdr_type

    if not isinstance(value, dict) or not isinstance(value.get('fields'), dict):
        raise ValueError('The CDR Field Dictionary is invalid.')
    cdr_type = workspace_cdr_type(repository)
    if str(value.get('cdr_type') or cdr_type).strip().casefold() != cdr_type:
        return None
    return save_overrides(repository, value['fields'], field_profile(cdr_type))


def editor(repository: Any, profile: CdrFieldProfile, source_columns: list[str]) -> dict[str, Any]:
    """The dictionary for Workspace Config: every field with its default and current columns and the column the
    workspace's CDRs have for it (the first one of its columns that they have)."""
    overrides = load_overrides(repository)
    present = {column_identity(column): column for column in source_columns}
    sections: dict[str, dict[str, Any]] = {}
    for row in entries(profile):
        columns = overrides.get(row['key'], row['defaults'])
        found = next((present[identity] for column in columns if (identity := column_identity(column)) in present), '')
        section = sections.setdefault(row['section'], {'title': row['section'], 'descriptions': [], 'rows': []})
        if row['description'] not in section['descriptions']:
            section['descriptions'].append(row['description'])
        section['rows'].append({**row, 'columns': columns, 'changed': row['key'] in overrides, 'found': found})
    return {'cdr_type': profile.cdr_type, 'sections': list(sections.values()), 'changed': len(overrides),
            'has_cdrs': bool(source_columns)}
