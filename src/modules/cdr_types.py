"""The CDR file type a workspace handles.

Each workspace processes the CDRs of one provider and keeps it once it has
CDRs, so its modules never mix the field names, values and methodologies of
two providers. NetCheck CDR is supported; Umlaut CDR and P3 CDR files keep
their own field names and are listed as upcoming until their readers and
field profiles (see cdr_field_profiles) are available.
"""
from __future__ import annotations

from typing import Any

CDR_TYPE_STATE_KEY = 'cdr_file_type'
DEFAULT_CDR_TYPE = 'netcheck'
CDR_TYPES: dict[str, dict[str, Any]] = {
    'netcheck': {'label': 'NetCheck CDR', 'supported': True},
    'umlaut': {'label': 'Umlaut CDR', 'supported': False},
    'p3': {'label': 'P3 CDR', 'supported': False},
}
CDR_DATASET_KINDS = frozenset({'data', 'voice', 'speech'})


def cdr_type_options() -> list[dict[str, Any]]:
    """The CDR types for selectors, the supported ones enabled."""
    return [{'value': key, **value} for key, value in CDR_TYPES.items()]


def normalize_cdr_type(value: object) -> str:
    """A supported CDR type; anything else is rejected."""
    key = str(value or DEFAULT_CDR_TYPE).strip().casefold()
    if key not in CDR_TYPES:
        raise ValueError('Choose one of the listed CDR types.')
    if not CDR_TYPES[key]['supported']:
        raise ValueError(f"{CDR_TYPES[key]['label']} files are not supported yet.")
    return key


def workspace_cdr_type(repository: Any) -> str:
    """The CDR type of a workspace; workspaces created before the setting handle NetCheck CDRs."""
    stored = str(repository.get_workspace_state(CDR_TYPE_STATE_KEY) or '').strip().casefold()
    return stored if stored in CDR_TYPES else DEFAULT_CDR_TYPE


def workspace_has_cdrs(repository: Any) -> bool:
    """Whether the workspace holds Data, Voice or Speech CDRs."""
    return any(str(dataset['dataset_kind'] or '').strip().casefold() in CDR_DATASET_KINDS for dataset in repository.list_datasets())


def set_workspace_cdr_type(repository: Any, value: object) -> str:
    """Save the CDR type of a workspace; a workspace with CDRs keeps the type of its CDRs."""
    cdr_type = normalize_cdr_type(value)
    current = workspace_cdr_type(repository)
    if cdr_type != current and workspace_has_cdrs(repository):
        raise ValueError(f"This workspace already has {CDR_TYPES[current]['label']} files, so its CDR type cannot change.")
    repository.set_workspace_state(CDR_TYPE_STATE_KEY, cdr_type)
    return cdr_type
