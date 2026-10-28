"""Starter content of every workspace: what it needs to show charts as soon as it has CDRs.

New deployments and new workspaces, and existing workspaces once, receive the content shipped in
``assets`` that they do not have yet (matched by name, so nothing of theirs is replaced):

- ``assets/scoring-methodologies/*.json``: Scoring & GAP Analysis methodologies (portable format), each with the
  campaigns it applies to (NetCheck 2025 up to 2026-Q1, NetCheck 2026 for 2026-Q2, NetCheck 2026-Q3 from 2026-Q3;
  NetCheck 2026 is the active one of a new workspace); a methodology added to the folder later reaches every existing
  workspace once too (without its campaigns when they overlap those of one of its methodologies);
- ``assets/ppt-templates/*.csv``: Report Templates, named after their file, each serving the CDRs of any NR Mode (their
  titles name it with ``{NR Mode}`` and ``{NR Mode Name}``);
- ``assets/ppt-designer/*.json``: PPT Designer, which use those templates, each reading the CDRs of its NR Mode
  (``nr_mode``: NSA, SA or NSA+SA for both, whose SA CDRs follow ``sa_campaigns``); the templates and Designs shipped
  later (``LATER_EXAMPLES``, such as the NSA & SA comparison FDFS DL (NSA & SA)) reach every existing workspace once;
- ``assets/autocalculated-fields/default-autocalculated-fields.json``: the Auto-calculated Fields every new
  workspace starts with, which the templates use;
- ``assets/scoring-report-configurations/*.json``: saved Scoring report configurations (``name`` and
  ``configuration``);
- ``assets/query-builder-queries/*.json``: saved Query Builder queries (``name``, ``description`` and
  ``query_sql`` on the ``selected_data``, ``selected_voice`` and ``selected_speech`` views);
- ``assets/reporting-jobs/*.json``: Reporting Jobs, which name their Designs (``design``: ``name``) and carry the report of each Scoring entry (``report``) or name a shipped Scoring report
  configuration (``report_configuration``) and name the favourite Bundle Report Templates they generate; their CDR
  Analysis, Network Insights and module artifacts are kept as they are, and they keep the order of their ``position``;
- ``assets/bundle-report-template-favourites/*.json``: favourite Bundle Report Templates (``name`` and
  ``definition``, as their export carries them), which find the shipped Designs by their name;
- ``assets/scoring-favourites-filters/*.json``: Scoring & GAP Favourites Filters (an entry of their export without its
  CDRs), each with a Campaign choice (Latest campaign…) whose CDRs it takes once the workspace has them.

The Vendor Maps of a new workspace come from ``assets/labels-vendors/default-vendor-maps.json`` (see ``repository``);
the default Campaign Maps from ``assets/labels-campaigns/default-campaign-map.json`` (see ``column_names``).
The content is that of the UK workspace without what only fits it (its regions, London, its cities one by one and its
operators), the comments of the slides, CDRs, email recipients or users; its GAP references are UK operators.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from src.config import PROJECT_ROOT
from src.modules.column_names import column_identity

ASSETS = PROJECT_ROOT / 'assets'
STATE_KEY = 'starter_content_initialized_v2'
DESIGNS_STATE_KEY = 'ppt_designs_v2'
SCORING_STATE_KEY = 'scoring_configuration'
# The shipped methodologies each workspace was given, so a methodology shipped later reaches it once and a
# methodology it deleted is not given again. Workspaces set up before this record received these.
METHODOLOGIES_STATE_KEY = 'starter_methodologies_offered'
METHODOLOGIES_SHIPPED_BEFORE = ('netcheck-2026',)
# The methodology a new workspace starts with as its active one (the others apply to the campaigns they name).
BASE_METHODOLOGY = 'netcheck-2026'
# The Report Templates shipped after workspaces were set up, which reach each of them once with their Designs (those
# of ``assets/ppt-designer`` that use them); a workspace that deleted them is not given them again.
LATER_EXAMPLES_STATE_KEY = 'starter_examples_offered'
LATER_EXAMPLES = ('FDFS DL (NSA & SA)',)


def _json_files(folder: Path) -> list[Path]:
    return sorted(folder.glob('*.json')) if folder.is_dir() else []


def _seed_methodologies(repository: Any) -> int:
    """Add the shipped methodologies not given to the workspace yet (matched by id or name); keep its active one."""
    from src.modules.scoring_config import unwrap_scoring_profiles_payload, validate_scoring_profiles
    from src.modules.scoring_methodologies import check_campaign_overlaps

    stored = repository.get_workspace_state(METHODOLOGIES_STATE_KEY)
    if stored is not None:
        offered = set(json.loads(stored or '[]'))
    else:
        offered = set(METHODOLOGIES_SHIPPED_BEFORE) if repository.get_workspace_state(STATE_KEY) == '1' else set()
    shipped = []
    for path in _json_files(ASSETS / 'scoring-methodologies'):
        payload = unwrap_scoring_profiles_payload(json.loads(path.read_text(encoding='utf-8')))
        shipped.extend(payload['profiles'] if payload else [])
    # The base methodology first: it is the active one of a new workspace.
    shipped = [profile for profile in sorted(shipped, key=lambda item: (item['id'] != BASE_METHODOLOGY, str(item['name']).casefold()))
               if profile['id'] not in offered]
    added = 0
    for profile in shipped:
        raw = repository.get_workspace_state(SCORING_STATE_KEY)
        if raw is None or not raw.strip():
            repository.replace_scoring_profiles(validate_scoring_profiles({'active_profile_id': profile['id'], 'profiles': [profile]}))
            added += 1
        else:
            current = repository.get_scoring_profiles()
            known = {item['id'] for item in current['profiles']} | {item['name'].casefold() for item in current['profiles']}
            if profile['id'] not in known and profile['name'].casefold() not in known:
                try:
                    profiles = validate_scoring_profiles({
                        'active_profile_id': current['active_profile_id'], 'profiles': [*current['profiles'], profile]})
                    check_campaign_overlaps(profiles['profiles'])
                except ValueError:
                    # Its campaigns overlap those of a methodology of the workspace: it is added without them.
                    profiles = validate_scoring_profiles({
                        'active_profile_id': current['active_profile_id'],
                        'profiles': [*current['profiles'], {key: value for key, value in profile.items() if key != 'campaigns'}]})
                repository.replace_scoring_profiles(profiles)
                added += 1
        offered.add(profile['id'])
    if shipped or stored is None:
        repository.set_workspace_state(METHODOLOGIES_STATE_KEY, json.dumps(sorted(offered)))
    return added


def _seed_templates(repository: Any, username: str) -> int:
    added = 0
    existing = {str(row['name']).casefold() for row in repository.list_report_templates()}
    for path in sorted((ASSETS / 'ppt-templates').glob('*.csv')):
        if path.stem.casefold() in existing:
            continue
        repository.add_report_template(path.stem, path.read_bytes(), updated_by=username)
        added += 1
    return added


def _seed_designs(repository: Any) -> int:
    stored = repository.get_workspace_state(DESIGNS_STATE_KEY)
    designs = json.loads(stored) if stored else {}
    if not isinstance(designs, dict):
        return 0
    existing = {str(item.get('name') or '').casefold() for item in designs.values() if isinstance(item, dict)}
    added = 0
    for path in _json_files(ASSETS / 'ppt-designer'):
        definition = json.loads(path.read_text(encoding='utf-8'))
        key = str(definition.get('name') or '').casefold()
        if not key or key in existing:
            continue
        designs[str(uuid.uuid4())] = definition
        existing.add(key)
        added += 1
    if added:
        repository.set_workspace_state(DESIGNS_STATE_KEY, json.dumps(designs))
    return added


def _seed_later_examples(repository: Any, username: str) -> int:
    """Add once the templates of ``LATER_EXAMPLES`` (and their Designs) a workspace was not given yet."""
    stored = repository.get_workspace_state(LATER_EXAMPLES_STATE_KEY)
    offered = set(json.loads(stored or '[]'))
    pending = [name for name in LATER_EXAMPLES if name not in offered]
    if not pending:
        return 0
    templates = {str(row['name']).casefold() for row in repository.list_report_templates()}
    raw = repository.get_workspace_state(DESIGNS_STATE_KEY)
    designs = json.loads(raw) if raw else {}
    names = {str(item.get('name') or '').casefold() for item in designs.values() if isinstance(item, dict)}
    added = 0
    for name in pending:
        path = ASSETS / 'ppt-templates' / f'{name}.csv'
        if path.is_file() and name.casefold() not in templates:
            repository.add_report_template(name, path.read_bytes(), updated_by=username)
            added += 1
        for design_path in _json_files(ASSETS / 'ppt-designer'):
            definition = json.loads(design_path.read_text(encoding='utf-8'))
            key = str(definition.get('name') or '').casefold()
            if definition.get('template') == name and key and key not in names and isinstance(designs, dict):
                designs[str(uuid.uuid4())] = definition
                names.add(key)
                added += 1
        offered.add(name)
    if isinstance(designs, dict) and added:
        repository.set_workspace_state(DESIGNS_STATE_KEY, json.dumps(designs))
    repository.set_workspace_state(LATER_EXAMPLES_STATE_KEY, json.dumps(sorted(offered)))
    return added


def _seed_calculated_dimensions(repository: Any) -> int:
    """Add the shipped Auto-calculated Fields a workspace already set up does not have."""
    if repository.get_workspace_state('calculated_dimensions_initialized') != '1':
        # Not set up yet: it starts from the shipped definitions when it is first used.
        return 0
    path = ASSETS / 'autocalculated-fields' / 'default-autocalculated-fields.json'
    shipped = json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    current = repository.list_calculated_dimensions()
    known = {column_identity(item.get('name', '')) for item in current}
    missing = [item for item in shipped if column_identity(item.get('name', '')) not in known]
    if not missing:
        return 0
    from src.modules.cdr_reporting import calculated_dimensions_json, parse_calculated_dimensions
    # The CDRs get the new fields when the workspace materializes them in the background.
    repository.replace_calculated_dimensions(calculated_dimensions_json(parse_calculated_dimensions([*current, *missing])))
    return len(missing)


def _shipped_report_configurations() -> dict[str, dict[str, Any]]:
    configurations = {}
    for path in _json_files(ASSETS / 'scoring-report-configurations'):
        item = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(item, dict) and str(item.get('name') or '').strip():
            configurations[str(item['name']).strip()] = item['configuration']
    return configurations


def _seed_report_configurations(repository: Any) -> int:
    from src.modules.scoring_reports import load_report_state, save_named_configuration

    existing = {item['name'].casefold() for item in load_report_state(repository)['configurations']}
    added = 0
    for name, configuration in _shipped_report_configurations().items():
        if name.casefold() not in existing:
            save_named_configuration(repository, name, configuration)
            added += 1
    return added


def _seed_queries(repository: Any, username: str) -> int:
    existing = {str(row['name']).casefold() for row in repository.list_query_builder_queries()}
    added = 0
    for path in _json_files(ASSETS / 'query-builder-queries'):
        item = json.loads(path.read_text(encoding='utf-8'))
        name = str(item.get('name') or '').strip()
        if not name or name.casefold() in existing or not str(item.get('query_sql') or '').strip():
            continue
        # No CDRs are chosen: the query runs on the CDRs chosen in Query Builder.
        repository.save_query_builder_query(name, str(item.get('description') or ''), str(item['query_sql']), [], username)
        added += 1
    return added


def _seed_reporting_jobs(repository: Any, username: str) -> int:
    from src.modules import report_tasks
    from src.modules.bundle_report_templates import list_favourites

    stored = repository.get_workspace_state(DESIGNS_STATE_KEY)
    designs = json.loads(stored) if stored else {}
    design_ids = {str(item.get('name') or '').casefold(): key
                     for key, item in (designs.items() if isinstance(designs, dict) else []) if isinstance(item, dict)}
    configurations = {name.casefold(): configuration for name, configuration in _shipped_report_configurations().items()}
    favourite_ids = {item['name'].casefold(): str(item['id']) for item in list_favourites(repository)}
    existing = {task['name'].casefold() for task in report_tasks.list_tasks(repository)}
    shipped = [json.loads(path.read_text(encoding='utf-8')) for path in _json_files(ASSETS / 'reporting-jobs')]
    # In the order of the jobs table they come from (``position``).
    shipped.sort(key=lambda item: (not isinstance(item.get('position'), int), item.get('position') if isinstance(item.get('position'), int) else 0))
    added = 0
    for item in shipped:
        name = str(item.get('name') or '').strip()
        if not name or name.casefold() in existing:
            continue
        definition = dict(item.get('definition') or {})
        entries = []
        for entry in definition.get('designs') or []:
            target = entry.get('design') or {}
            design_id = design_ids.get(str(target.get('name') or '').casefold())
            if design_id:
                entries.append({**{key: value for key, value in entry.items() if key != 'design'}, 'design_id': design_id})
        definition['designs'] = entries
        scoring = []
        for entry in definition.get('scoring') or []:
            if isinstance(entry.get('report'), dict) and entry['report'].get('scenarios'):
                # The report of the entry itself.
                scoring.append({key: value for key, value in entry.items() if key != 'report_configuration'})
                continue
            configuration = configurations.get(str(entry.get('report_configuration') or '').casefold())
            if configuration:
                scoring.append({**{key: value for key, value in entry.items() if key != 'report_configuration'},
                                'report': {**configuration, 'name': entry['report_configuration']}})
        definition['scoring'] = scoring
        # The favourite Bundle Report Templates it generates, named in the asset, are those of this workspace.
        definition = report_tasks._remap_favourites(definition, {}, favourite_ids)
        modules = definition.get('modules') if isinstance(definition.get('modules'), dict) else {}
        if not (entries or scoring or (definition.get('dataset_analysis') or {}).get('enabled') or definition.get('network_insights')
                or any(isinstance(config, dict) and config.get('enabled') for config in modules.values())):
            continue
        report_tasks.save_task(repository, None, {**item, 'definition': definition}, username,
                               parse_recipients=lambda value: [str(address) for address in value or []],
                               invalid_recipients=lambda _addresses: [])
        added += 1
    return added


def _shipped_entries(folder: str, existing: set[str]) -> list[dict[str, Any]]:
    """The shipped items of a folder whose name the workspace does not have yet."""
    entries = []
    for path in _json_files(ASSETS / folder):
        item = json.loads(path.read_text(encoding='utf-8'))
        name = str(item.get('name') or '').strip() if isinstance(item, dict) else ''
        if name and name.casefold() not in existing:
            entries.append(item)
    return entries


def _seed_bundle_report_template_favourites(repository: Any, username: str) -> int:
    from src.modules.bundle_report_templates import import_entries, list_favourites, workspace_designs

    entries = _shipped_entries('bundle-report-template-favourites', {item['name'].casefold() for item in list_favourites(repository)})
    # Each finds the shipped Designs by their name.
    return import_entries(repository, entries, username, workspace_designs(repository)) if entries else 0


def _seed_favourites_filters(repository: Any) -> int:
    from src.modules.saved_filters import SAVED_FILTERS_FORMAT, SAVED_FILTERS_VERSION, import_saved_filters, list_saved_filters

    entries = _shipped_entries('scoring-favourites-filters', {item['name'].casefold() for item in list_saved_filters(repository)})
    if not entries:
        return 0
    return import_saved_filters(repository, {'format': SAVED_FILTERS_FORMAT, 'version': SAVED_FILTERS_VERSION,
                                             'saved_filters': entries})


def seed_starter_content(repository: Any, username: str = 'system') -> dict[str, int] | None:
    """Add the shipped starter content once per workspace; returns what was added, or None when done before.

    Methodologies shipped after the workspace was set up are added to it once too.
    """
    if repository.get_workspace_state(STATE_KEY) == '1':
        added = {'methodologies': _seed_methodologies(repository), 'examples': _seed_later_examples(repository, username)}
        added = {key: value for key, value in added.items() if value}
        if not added:
            return None
        if hasattr(repository, 'try_add_log'):
            repository.try_add_log(username, 'starter_content_added', json.dumps(added))
        return added
    added = {
        'methodologies': _seed_methodologies(repository),
        'report_templates': _seed_templates(repository, username),
        'designs': _seed_designs(repository),
        'auto_calculated_fields': _seed_calculated_dimensions(repository),
        'scoring_report_configurations': _seed_report_configurations(repository),
        'query_builder_queries': _seed_queries(repository, username),
        'favourites_filters': _seed_favourites_filters(repository),
    }
    # After the Designs and the report configurations, which the favourite Bundle Report Templates and the Reporting
    # Jobs name; the Reporting Jobs also name the favourite Bundle Report Templates they generate.
    added['bundle_report_template_favourites'] = _seed_bundle_report_template_favourites(repository, username)
    added['reporting_jobs'] = _seed_reporting_jobs(repository, username)
    # The later examples came with the templates and Designs above.
    repository.set_workspace_state(LATER_EXAMPLES_STATE_KEY, json.dumps(sorted(LATER_EXAMPLES)))
    repository.set_workspace_state(STATE_KEY, '1')
    if any(added.values()) and hasattr(repository, 'try_add_log'):
        repository.try_add_log(username, 'starter_content_added', json.dumps(added))
    return added
