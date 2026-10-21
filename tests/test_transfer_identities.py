"""Import / Export and Transfer: the items of a package replace those of the destination with the same identity (or
else name) and add the others, an item renamed on the source server is renamed in the destination, and each imported
item belongs to its creator when that user is active in the destination, otherwise to the user who imports it."""
from __future__ import annotations

import json
from pathlib import Path

import src.DriveTestAnalyzer as core
from src.modules import bundle_report_templates as brt
from src.modules import network_insights_favourites as ni_favourites
from src.modules.deletion_rights import (
    AUTO_CALCULATED_FIELDS, PPT_DASHBOARDS, SCORING_METHODOLOGIES, SCORING_REPORT_CONFIGURATIONS, creators, set_creator,
)
from src.modules.repository import Repository
from src.modules.scoring_reports import default_report_configuration, load_report_state, save_named_configuration
from src.modules.transfer_identities import (
    SCORING_REPORT_CONFIGURATIONS as REPORT_IDENTITIES, ItemMatcher, identities, imported_creator, move_identity,
)


def _workspace(name: str):
    workspace = core.workspace_registry.create(name)
    repository = Repository(workspace.database_path, core.repository.global_db_path, core.workspace_registry.registry_path)
    repository.initialize()
    return workspace, repository


def _transfer(target: str, source, destination, tmp_path: Path, importing_user: str = 'super') -> str:
    package = tmp_path / f'{target}.zip'
    core.build_export_archive_file(target, package, [source.id])
    return core._apply_import_archive(package, core.read_import_manifest(package), destination_workspace_ids=[destination.id],
                                      importing_user=importing_user)


def _dashboards(repository: Repository) -> dict:
    return json.loads(repository.get_workspace_state(core.DASHBOARD_STATE_KEY) or '{}')


def test_items_are_found_by_identity_then_name_and_keep_their_names_unique():
    matcher = ItemMatcher([(1, 'Alpha', 'u1'), (2, 'Beta', 'u2'), (3, 'Gamma', '')])
    # Its identity finds it, renamed; the name it takes belongs to another item, so it is told apart.
    assert matcher.match('u1', 'Beta') == (1, 'Beta (2)')
    # Without its identity, the name finds it.
    assert matcher.match('other', 'beta') == (2, 'beta')
    assert matcher.match('', 'New') == (None, 'New')
    assert matcher.match('u2', 'Gamma') == (3, 'Gamma')
    assert matcher.summary() == ['"Alpha" renamed "Beta (2)"', '"Beta" kept as "Beta (2)" because another item has its name']
    # Matched again, an item that kept another name is not renamed again.
    again = ItemMatcher([(1, 'Beta', ''), (2, 'Beta (2)', 'u1')])
    assert again.match('u1', 'Beta') == (2, 'Beta (2)') and again.summary() == []


def test_imported_items_belong_to_their_creator_when_active_here():
    exists = {'ana'}.__contains__
    assert imported_creator('ana', 'bob', 'importer', exists) == 'ana'
    assert imported_creator('ghost', 'bob', 'importer', exists) == 'importer'
    # Packages of earlier versions do not say: a replaced item keeps its creator, a new one is the importer's.
    assert imported_creator('', 'bob', 'importer', exists) == 'bob'
    # Items of the application (``system``) have no creator to keep either.
    assert imported_creator('system', 'bob', 'importer', exists) == 'bob'
    assert imported_creator(None, '', 'importer', exists) == 'importer'


def test_dashboards_are_replaced_by_identity_or_name_and_the_others_kept(client, tmp_path):
    core.repository.create_user('analyst', 'analyst123', 'user-editor')
    source, source_repo = _workspace('Dashboards source')
    destination, destination_repo = _workspace('Dashboards destination')
    source_repo.set_workspace_state(core.DASHBOARD_STATE_KEY, json.dumps({
        'd1': {'name': 'Coverage', 'technology': 'nsa', 'template': 'T'},
        'd2': {'name': 'Speed', 'technology': 'nsa', 'template': 'T'},
    }))
    set_creator(source_repo, PPT_DASHBOARDS, 'd1', 'analyst')
    set_creator(source_repo, PPT_DASHBOARDS, 'd2', 'ghost')
    destination_repo.set_workspace_state(core.DASHBOARD_STATE_KEY, json.dumps({
        'local': {'name': 'Local only', 'technology': 'nsa', 'template': 'T'},
        'x9': {'name': 'Speed', 'technology': 'nsa', 'template': 'Old'},
    }))

    _transfer('dashboards', source, destination, tmp_path)
    stored = _dashboards(destination_repo)
    # Speed replaces the Dashboard of that name, keeping its ID; the Dashboards only the destination has stay.
    assert set(stored) == {'local', 'x9', 'd1'}
    assert stored['x9']['template'] == 'T' and stored['local']['name'] == 'Local only'
    known = creators(destination_repo, PPT_DASHBOARDS)
    assert known['d1'] == 'analyst' and known['x9'] == 'super'

    # Renamed on the source, it is renamed in the destination instead of being added again.
    renamed = _dashboards(source_repo)
    renamed['d1']['name'] = 'Coverage v2'
    renamed['d2']['name'] = 'Speed v2'
    source_repo.set_workspace_state(core.DASHBOARD_STATE_KEY, json.dumps(renamed))
    notice = _transfer('dashboards', source, destination, tmp_path)
    stored = _dashboards(destination_repo)
    assert {key: item['name'] for key, item in stored.items()} == {'local': 'Local only', 'x9': 'Speed v2', 'd1': 'Coverage v2'}
    assert '"Coverage" renamed "Coverage v2"' in notice
    # The summary window gets the message in parts: its headline and a table of the renamed items of each element.
    details = core.import_notice_details(notice)
    [section] = [item for item in details['sections'] if item['title'] == f'Dashboards of "{destination.name}"']
    assert {'label': '', 'from': 'Coverage', 'to': 'Coverage v2'} in section['items']
    assert details['headline'] and details['headline'] in notice

    # A Reporting Job that names the Dashboard by its ID on the source finds the one it replaced.
    assert brt.dashboard_aliases(destination_repo) == {'d2': 'x9'}
    from src.modules.report_tasks import import_tasks_document, list_tasks
    document = {'format': 'drivetest-analyzer-reporting-jobs', 'version': 1, 'reporting_jobs': [{
        'name': 'Weekly', 'enabled': False, 'schedule': {'mode': 'manual'}, 'created_by': 'super',
        'definition': {'dashboards': [{'dashboard_id': 'd2', 'label': 'Speed v2'}]},
    }]}
    import_tasks_document(destination_repo, json.dumps(document), 'super', parse_recipients=core.parse_recipients,
                          invalid_recipients=core.invalid_recipients)
    [job] = list_tasks(destination_repo)
    assert job['definition']['dashboards'][0]['dashboard_id'] == 'x9'


def test_query_builder_queries_follow_their_renames_and_creators(client, tmp_path):
    core.repository.create_user('analyst', 'analyst123', 'user-editor')
    source, source_repo = _workspace('Queries source')
    destination, destination_repo = _workspace('Queries destination')
    source_repo.save_query_builder_query('Top cells', '', 'SELECT 1', [], 'analyst')
    source_repo.save_query_builder_query('Ghost query', '', 'SELECT 2', [], 'ghost')
    destination_repo.save_query_builder_query('Local', '', 'SELECT 3', [], 'super')
    _transfer('query-builder-queries', source, destination, tmp_path, importing_user='admin')
    rows = {str(row['name']): row for row in destination_repo.list_query_builder_queries()}
    assert set(rows) == {'Top cells', 'Ghost query', 'Local'}
    assert rows['Top cells']['created_by'] == 'analyst' and rows['Ghost query']['created_by'] == 'admin'

    query_id = next(int(row['id']) for row in source_repo.list_query_builder_queries() if row['name'] == 'Top cells')
    source_repo.update_query_builder_query(query_id, 'Top cells NR', '', 'SELECT 10', [], 'analyst')
    notice = _transfer('query-builder-queries', source, destination, tmp_path, importing_user='admin')
    rows = {str(row['name']): row for row in destination_repo.list_query_builder_queries()}
    assert set(rows) == {'Top cells NR', 'Ghost query', 'Local'}
    assert rows['Top cells NR']['query_sql'] == 'SELECT 10' and '"Top cells" renamed "Top cells NR"' in notice


def test_favourites_follow_their_renames_and_creators(client, tmp_path):
    core.repository.create_user('analyst', 'analyst123', 'user-editor')
    source, source_repo = _workspace('Favourites source')
    destination, destination_repo = _workspace('Favourites destination')
    favourite = ni_favourites.save_favourite(source_repo, None, 'Weekly', {'controls': {'ni-nr-mode': 'SA'}}, 'analyst')
    _transfer('network-insights-favourites', source, destination, tmp_path)
    ni_favourites.rename_favourite(source_repo, favourite['id'], 'Weekly SA', 'analyst')
    notice = _transfer('network-insights-favourites', source, destination, tmp_path)
    [stored] = ni_favourites.list_favourites(destination_repo)
    assert stored['name'] == 'Weekly SA' and stored['created_by'] == 'analyst'
    assert '"Weekly" renamed "Weekly SA"' in notice

    bundle = brt.save_favourite(source_repo, None, 'Monthly pack', {}, 'ghost')
    _transfer('bundle-report-template-favourites', source, destination, tmp_path, importing_user='admin')
    brt.save_favourite(source_repo, bundle['id'], 'Monthly pack v2', bundle['definition'], 'ghost')
    _transfer('bundle-report-template-favourites', source, destination, tmp_path, importing_user='admin')
    [stored] = brt.list_favourites(destination_repo)
    assert stored['name'] == 'Monthly pack v2' and stored['created_by'] == 'admin'


def test_scoring_report_templates_follow_their_renames_and_creators(client, tmp_path):
    core.repository.create_user('analyst', 'analyst123', 'user-editor')
    source, source_repo = _workspace('Reports source')
    destination, destination_repo = _workspace('Reports destination')
    save_named_configuration(source_repo, 'Monthly', default_report_configuration())
    set_creator(source_repo, SCORING_REPORT_CONFIGURATIONS, 'Monthly', 'analyst')
    save_named_configuration(destination_repo, 'Local', default_report_configuration())
    _transfer('scoring-report-templates', source, destination, tmp_path)
    assert creators(destination_repo, SCORING_REPORT_CONFIGURATIONS)['monthly'] == 'analyst'

    # Kept with its identity under another name on the source, it takes that name in the destination.
    state = load_report_state(source_repo)
    state['configurations'][0]['name'] = 'Monthly v2'
    from src.modules.scoring_reports import store_configurations
    store_configurations(source_repo, state['configurations'])
    move_identity(source_repo, REPORT_IDENTITIES, 'Monthly', 'Monthly v2')
    _transfer('scoring-report-templates', source, destination, tmp_path)
    assert sorted(item['name'] for item in load_report_state(destination_repo)['configurations']) == ['Local', 'Monthly v2']
    assert 'monthly v2' in identities(destination_repo, REPORT_IDENTITIES)
    assert creators(destination_repo, SCORING_REPORT_CONFIGURATIONS)['monthly v2'] == 'analyst'


def test_auto_calculated_fields_are_added_and_renamed_by_identity(client, tmp_path):
    destination, destination_repo = _workspace('Fields destination')
    [field] = core.calculated_dimensions_json(core.parse_calculated_dimensions(core.default_calculated_dimensions()))[:1]
    local = {**field, 'name': 'Local field'}
    destination_repo.replace_calculated_dimensions([local])
    incoming = {**field, 'name': 'Area kind', 'uid': 'field-1', 'created_by': 'ghost'}
    jobs: list = []
    core.import_auto_calculated_fields([incoming], [destination.id], deferred_jobs=jobs, importing_user='admin')
    names = [item['name'] for item in destination_repo.list_calculated_dimensions()]
    assert names == ['Local field', 'Area kind']
    assert creators(destination_repo, AUTO_CALCULATED_FIELDS)[core._normalise_catalogue_dimension_name('Area kind')] == 'admin'
    destination_repo.set_workspace_state(core.DASHBOARD_STATE_KEY, json.dumps({
        'd1': {'name': 'Uses it', 'custom_fields': ['Area kind'], 'filters': {'Area kind': ['A']}},
    }))
    destination_repo.save_query_builder_query('By area', '', 'SELECT "Area kind", COUNT(*) FROM t GROUP BY "Area kind"', [], 'super')

    summary: list[str] = []
    core.import_auto_calculated_fields([{**incoming, 'name': 'Area type'}], [destination.id], deferred_jobs=jobs,
                                       importing_user='admin', summary=summary)
    names = [item['name'] for item in destination_repo.list_calculated_dimensions()]
    assert names == ['Local field', 'Area type']
    dashboard = _dashboards(destination_repo)['d1']
    assert dashboard['custom_fields'] == ['Area type'] and 'Area type' in dashboard['filters']
    # The saved queries use it as a column of the CDR tables: their SQL takes its new name too.
    [query] = destination_repo.list_query_builder_queries()
    assert query['query_sql'] == 'SELECT "Area type", COUNT(*) FROM t GROUP BY "Area type"'
    assert summary and '"Area kind" renamed "Area type"' in summary[0]
    # Its creator moves with it.
    assert creators(destination_repo, AUTO_CALCULATED_FIELDS)[core._normalise_catalogue_dimension_name('Area type')] == 'admin'


def test_methodologies_take_their_creators_and_leave_out_what_earlier_packages_carried(client, tmp_path):
    core.repository.create_user('analyst', 'analyst123', 'user-editor')
    source, source_repo = _workspace('Methodologies source')
    destination, destination_repo = _workspace('Methodologies destination')
    from tests.scoring_fixtures import load_initial_scoring_configuration
    source_repo.replace_scoring_configuration(load_initial_scoring_configuration())
    profiles = source_repo.get_scoring_profiles()
    for profile in profiles['profiles']:
        set_creator(source_repo, SCORING_METHODOLOGIES, profile['id'], 'analyst')
    package = tmp_path / 'methodologies.zip'
    core.build_export_archive_file('scoring-configuration', package, [source.id])
    manifest = core.read_import_manifest(package)
    # A package of an earlier version also carried report configurations, which imports leave out now.
    import zipfile
    legacy = tmp_path / 'legacy.zip'
    with zipfile.ZipFile(package) as original, zipfile.ZipFile(legacy, 'w') as archive:
        for name in original.namelist():
            archive.writestr(name, original.read(name))
        archive.writestr(core._scoring_report_configurations_member(manifest['archive_path']), json.dumps({
            'format': 'drivetest-analyzer-scoring-report-configurations', 'version': 1,
            'configurations': [{'name': 'Legacy', 'configuration': default_report_configuration()}]}))
    core._apply_import_archive(legacy, core.read_import_manifest(legacy), destination_workspace_ids=[destination.id],
                               importing_user='super')
    known = creators(destination_repo, SCORING_METHODOLOGIES)
    assert {known[str(profile['id']).casefold()] for profile in profiles['profiles']} == {'analyst'}
    assert load_report_state(destination_repo)['configurations'] == []


def test_methodologies_are_merged_keeping_those_only_the_destination_has(client, tmp_path):
    from tests.scoring_fixtures import load_initial_scoring_configuration
    source, source_repo = _workspace('Merge source')
    destination, destination_repo = _workspace('Merge destination')
    for repo in (source_repo, destination_repo):
        repo.replace_scoring_configuration(load_initial_scoring_configuration())
    base = source_repo.get_scoring_profiles()['profiles'][0]
    shared = {**base, 'id': 'shared-2025', 'name': 'Shared 2025'}
    shared.pop('campaigns', None)
    source_repo.replace_scoring_profiles({'active_profile_id': base['id'], 'profiles': [base, shared]})
    local_only = {**shared, 'id': 'local-only', 'name': 'Local only'}
    same_name = {**shared, 'id': 'local-shared', 'name': 'Shared 2025'}
    destination_repo.replace_scoring_profiles({'active_profile_id': 'local-only', 'profiles': [local_only, same_name]})

    _transfer('scoring-configuration', source, destination, tmp_path)
    stored = destination_repo.get_scoring_profiles()
    # The one with the same name is replaced and keeps its ID here; the one only the destination has stays, and so does
    # the default methodology of the destination.
    assert sorted(profile['id'] for profile in stored['profiles']) == sorted(['local-only', 'local-shared', base['id']])
    assert stored['active_profile_id'] == 'local-only'

    # Renamed on the source, it is renamed here instead of being added again.
    renamed = source_repo.get_scoring_profiles()
    renamed['profiles'][1]['name'] = 'Shared 2025 v2'
    source_repo.replace_scoring_profiles(renamed)
    notice = _transfer('scoring-configuration', source, destination, tmp_path)
    names = {profile['id']: profile['name'] for profile in destination_repo.get_scoring_profiles()['profiles']}
    assert names['local-shared'] == 'Shared 2025 v2' and len(names) == 3
    assert '"Shared 2025" renamed "Shared 2025 v2"' in notice


def test_a_restore_adds_and_renames_like_an_import(client, tmp_path):
    workspace, repo = _workspace('Restore workspace')
    repo.set_workspace_state(core.DASHBOARD_STATE_KEY, json.dumps({'d1': {'name': 'Coverage', 'technology': 'nsa', 'template': 'T'}}))
    # Valid templates: a renamed field is renamed in them too.
    saved = (Path(__file__).parent / 'fixtures' / 'NSA Slide Template.csv').read_bytes()
    repo.add_report_template('nsa', 'Coverage', saved, updated_by='super')
    [field] = core.calculated_dimensions_json(core.parse_calculated_dimensions(core.default_calculated_dimensions()))[:1]
    repo.replace_calculated_dimensions([{**field, 'name': 'Area kind'}])
    components = ['dashboards', 'report_templates', 'auto_calculated_fields']
    backup = core.create_recurring_database_backup({'components': components, 'workspace_ids': [workspace.id],
                                                    'backup_path': str(tmp_path / 'backups'), 'max_backups': 5})

    # After the backup, each one is renamed and another is created.
    dashboards = _dashboards(repo)
    dashboards['d1']['name'] = 'Coverage now'
    dashboards['local'] = {'name': 'Local', 'technology': 'nsa', 'template': 'T'}
    repo.set_workspace_state(core.DASHBOARD_STATE_KEY, json.dumps(dashboards))
    repo.rename_report_template('nsa', 'Coverage', 'Coverage now')
    repo.add_report_template('nsa', 'Local', saved)
    previous = core.parse_calculated_dimensions(repo.list_calculated_dimensions())
    current = core.parse_calculated_dimensions([{**field, 'name': 'Area type'}, {**field, 'name': 'Local field'}])
    repo.replace_calculated_dimensions(core.calculated_dimensions_json(current))
    core.keep_calculated_dimension_identities(repo, previous, current, {'Area kind': 'Area type'}, 'super')

    # The restore brings back what the backup has, found by its identity, and keeps what only the workspace has.
    core.restore_database_backup(backup, components, importing_user='super')
    assert {item['name'] for item in _dashboards(repo).values()} == {'Coverage', 'Local'}
    templates = {str(row['name']) for row in repo.list_report_templates('nsa')}
    assert templates == {'Coverage', 'Local'}
    assert [item['name'] for item in repo.list_calculated_dimensions()] == ['Area kind', 'Local field']


def test_dashboards_follow_their_ppt_template_by_its_identity(client):
    client.post('/login', data={'username': 'super', 'password': 'super123'}, follow_redirects=False)
    repo = core.repository
    template = (Path(__file__).parent / 'fixtures' / 'NSA Slide Template.csv').read_bytes()
    repo.add_report_template('nsa', 'Coverage', template, updated_by='super')
    uid = repo.report_template_uids()[('nsa', 'Coverage')]
    assert uid
    # A Dashboard saved before identities takes that of the template it names.
    repo.set_workspace_state(core.DASHBOARD_STATE_KEY, json.dumps({
        'dash-1': {'name': 'Coverage NSA', 'template': 'Coverage', 'template_technology': 'nsa', 'technology': 'nsa'},
    }))
    listed = client.get('/api/ppt-dashboards').json()
    assert listed['dash-1']['template_uid'] == uid
    # Renamed without telling the Dashboards, the template is still found by its identity.
    repo.rename_report_template('nsa', 'Coverage', 'Coverage v2')
    listed = client.get('/api/ppt-dashboards').json()
    assert listed['dash-1']['template'] == 'Coverage v2' and listed['dash-1']['template_uid'] == uid
    assert _dashboards(repo)['dash-1']['template'] == 'Coverage v2'
    # Its references stay with it: the template used by a Dashboard is protected under its new name.
    assert ('nsa', 'Coverage v2') in core._dashboard_template_references(repo)


def test_reporting_jobs_and_excluded_calls_follow_their_renames(client, tmp_path):
    from src.modules import scoring_exclusions
    from src.modules.report_tasks import list_tasks, save_task

    source, source_repo = _workspace('Jobs source')
    destination, destination_repo = _workspace('Jobs destination')
    job = save_task(source_repo, None, {'name': 'Weekly', 'definition': {'dashboards': [{'dashboard_id': 'd1', 'label': 'X'}]},
                                        'schedule': {'mode': 'manual'}, 'send_email': False, 'recipients': ''}, 'super',
                    parse_recipients=core.parse_recipients, invalid_recipients=core.invalid_recipients)
    excluded = scoring_exclusions.create_list(source_repo, name='Retests', calls=[{'join_id': 'J1'}], username='super')
    for target in ('reporting-jobs', 'scoring-excluded-calls'):
        _transfer(target, source, destination, tmp_path)

    # Renamed on the source, each one is renamed in the destination instead of being added again.
    with source_repo.connection() as connection:
        connection.execute('UPDATE report_tasks SET name = ? WHERE id = ?', ('Weekly v2', job['id']))
        connection.execute(f'UPDATE {scoring_exclusions.LISTS_TABLE} SET name = ? WHERE id = ?', ('Retests Q3', excluded['id']))
    jobs_notice = _transfer('reporting-jobs', source, destination, tmp_path)
    lists_notice = _transfer('scoring-excluded-calls', source, destination, tmp_path)
    assert [task['name'] for task in list_tasks(destination_repo)] == ['Weekly v2']
    [stored] = scoring_exclusions.list_lists(destination_repo)
    assert stored['name'] == 'Retests Q3' and stored['uid'] == excluded['uid']
    assert '"Weekly" renamed "Weekly v2"' in jobs_notice and '"Retests" renamed "Retests Q3"' in lists_notice


def test_workspaces_are_found_by_their_identity(client, tmp_path):
    workspace = core.workspace_registry.create('Alpha')
    other = core.workspace_registry.create('Other')
    assert workspace.uid and workspace.uid != other.uid
    package = tmp_path / 'workspace.zip'
    core.build_export_archive_file(f'workspace:{workspace.id}', package)
    manifest = core.read_import_manifest(package)
    assert manifest['workspace']['uid'] == workspace.uid
    # Renamed since (as if on the other server), the workspace is still found by its identity: it is replaced and
    # takes the name of the package instead of a second workspace being added.
    core.workspace_registry.rename(workspace.id, 'Beta')
    assert core.import_workspace_collisions(manifest) == ['Beta']
    notice = core._apply_import_archive(package, manifest, importing_user='super')
    matching = [item for item in core.workspace_registry.list() if item.uid == workspace.uid]
    assert [(item.id, item.name) for item in matching] == [(workspace.id, 'Alpha')]
    assert '"Beta" renamed "Alpha"' in notice
    # Application Config translates the access of the other server's workspaces by identity, then by name.
    assert core._source_workspace_ids([{'id': 'remote-1', 'name': 'Old name', 'uid': workspace.uid},
                                       {'id': 'remote-2', 'name': 'other'}, {'id': 'remote-3', 'name': 'Gone'}]) == {
        'remote-1': workspace.id, 'remote-2': other.id, 'remote-3': None}


def test_users_profiles_and_groups_are_found_by_their_identity(client):
    repo = core.repository
    workspace = core.workspace_registry.create('Shared')
    repo.create_user('analyst', 'analyst123', 'user-editor')
    profile_id = repo.save_modules_profile(None, 'Analysts', '', ['scoring'])
    group_id = repo.save_workspace_group(None, 'Field team', '', [workspace.id])
    payload = repo.users_access_payload({workspace.id: workspace.name}, {workspace.id: workspace.uid})
    assert payload['workspace_identities'] == {'Shared': workspace.uid}
    assert all(item['uid'] for key in ('users', 'modules_profiles', 'workspace_groups') for item in payload[key])

    # Renamed on the other server: each one is renamed here, and the renamed workspace is still found by its identity.
    for item in payload['users']:
        item['username'] = 'analyst2' if item['username'] == 'analyst' else item['username']
    next(item for item in payload['modules_profiles'] if item['name'] == 'Analysts')['name'] = 'Analysts v2'
    group = next(item for item in payload['workspace_groups'] if item['name'] == 'Field team')
    group.update(name='Field team v2', workspaces=['Shared (old name)'])
    payload['workspace_identities'] = {'Shared (old name)': workspace.uid}
    summary = repo.merge_users_access(payload, {workspace.name: workspace.id}, protected_username='super',
                                      workspace_ids_by_uid={workspace.uid: workspace.id})
    usernames = [row['username'] for row in repo.list_users()]
    assert 'analyst2' in usernames and 'analyst' not in usernames
    profiles = {item['id']: item['name'] for item in repo.list_modules_profiles()}
    groups = {item['id']: item for item in repo.list_workspace_groups()}
    assert profiles[profile_id] == 'Analysts v2' and groups[group_id]['name'] == 'Field team v2'
    assert groups[group_id]['workspace_ids'] == [workspace.id] and summary['missing_workspaces'] == []
    assert any('renamed "analyst2"' in line for line in summary['renamed'])
    # The account that imports keeps its username.
    for item in payload['users']:
        item['username'] = 'super-renamed' if item['username'] == 'super' else item['username']
    repo.merge_users_access(payload, {workspace.name: workspace.id}, protected_username='super')
    assert 'super' in [row['username'] for row in repo.list_users()]


def test_an_imported_workspace_keeps_the_hashes_of_the_cdr_files_it_placed(client, tmp_path):
    from src.modules.scoring_history import HISTORY_FILES_TABLE, ensure_history_tables, file_sha256

    workspace, repo = _workspace('Hashes')
    placed = workspace.input_dir / 'cdr.xlsx'
    placed.parent.mkdir(parents=True, exist_ok=True)
    placed.write_bytes(b'cdr content')
    dataset_id, _created = repo.add_dataset('cdr.xlsx', str(placed), 'super')
    ensure_history_tables(repo)
    # The hash the package's database knew, of the same file at another place and time.
    with repo.connection() as connection:
        connection.execute(f'INSERT OR REPLACE INTO {HISTORY_FILES_TABLE} (dataset_id, stored_path, file_size, file_mtime, file_sha256) '
                           'VALUES (?, ?, ?, ?, ?)', (dataset_id, '/source/server/cdr.xlsx', placed.stat().st_size, 1.0, 'known-hash'))
    core._carry_cdr_file_hashes(workspace)
    row = next(item for item in repo.list_datasets() if int(item['id']) == dataset_id)
    assert file_sha256(repo, row) == 'known-hash'


def test_an_export_tells_which_part_it_is_archiving(client, tmp_path):
    workspace = core.workspace_registry.create('Phases')
    workspace.input_dir.mkdir(parents=True, exist_ok=True)
    (workspace.input_dir / 'cdr.xlsx').write_bytes(b'cdr')
    events: list[tuple[str, object]] = []
    core.build_export_archive_file('full-environment', tmp_path / 'environment.zip', [workspace.id],
                                   lambda written: events.append(('bytes', written)),
                                   phase_callback=lambda phase: events.append(('phase', phase)))
    phases = [value for kind, value in events if kind == 'phase']
    assert phases[0].startswith('copying the application database (')
    assert any(phase.startswith('workspace 1 of 1 "Phases": copying its database (') for phase in phases)
    assert 'workspace 1 of 1 "Phases": adding its settings and saved items' in phases
    assert any(phase.startswith('workspace 1 of 1 "Phases": adding its Input files (') for phase in phases)
    # The copy of the database counts in the progress once it is made, and then its archiving.
    start = next(index for index, (kind, value) in enumerate(events) if kind == 'phase' and 'copying its database' in str(value))
    end = events.index(('phase', 'workspace 1 of 1 "Phases": adding its settings and saved items'))
    assert len([kind for kind, _value in events[start:end] if kind == 'bytes']) >= 2

    # A selection of several elements names each one by its position.
    phases = []
    core.build_export_archive_file(['dashboards', 'ppt-templates'], tmp_path / 'selection.zip', phase_callback=phases.append)
    assert phases == ['Dashboards (1 of 2)', 'PPT Templates (2 of 2)']


def test_import_summaries_come_in_parts_for_the_summary_window():
    line = core.summary_section('Bundle Report Template Favourites of "UK"', [
        '"Weekly · NSA" renamed "Weekly report · NSA"', '"Daily" kept as "Daily (2)" because another item has its name',
        'user "ana" renamed "ana2"', 'user "bob" left out because another user has that username'])
    assert line == ('Bundle Report Template Favourites of "UK": "Weekly · NSA" renamed "Weekly report · NSA"; "Daily" kept as '
                    '"Daily (2)" because another item has its name; user "ana" renamed "ana2"; user "bob" left out because '
                    'another user has that username.')
    assert line.section['items'] == [
        {'label': '', 'from': 'Weekly · NSA', 'to': 'Weekly report · NSA'},
        {'label': '', 'from': 'Daily', 'to': 'Daily (2)', 'note': 'another item has its name'},
        {'label': 'user', 'from': 'ana', 'to': 'ana2'},
        {'text': 'user "bob" left out because another user has that username'},
    ]
    notice = core.import_notice('Import selection completed (2 packages). ' + line, 'Import selection completed (2 packages).',
                                [line], ['Imported 3 Dashboards into 1 workspaces.', 'PPT Templates imported successfully.'])
    assert json.loads(json.dumps({'notice': notice, 'details': core.import_notice_details(notice)}))['details']['packages'][1] == 'PPT Templates imported successfully.'
    assert core.import_notice_details('Plain message.') is None
    # The incoming and outgoing transfers and the imports open it in a wide window.
    script = (Path(__file__).parents[1] / 'src/web_interface/static/js/app.js').read_text(encoding='utf-8')
    assert "showImportSummary(offer.notice || 'The incoming transfer was imported successfully.', offer.notice_details" in script
    assert "showImportSummary(transfer.notice || 'The destination server received and imported the package successfully.', transfer.notice_details" in script
    assert 'function importSummaryContent(details) {' in script and "infoOverlay.classList.toggle('info-wide', Boolean(options.wide));" in script


def test_the_incoming_transfer_dialog_names_every_element_with_its_title():
    import re

    script = (Path(__file__).parents[1] / 'src/web_interface/static/js/app.js').read_text(encoding='utf-8')
    start = script.index('const transferContentLabels = {')
    labels = set(re.findall(r"^\s*'?([a-z_-]+)'?\s*:", script[start:script.index('};', start)], re.M))
    elements = {*core.STATIC_EXPORT_TARGETS, *core.WORKSPACE_ELEMENT_EXPORT_TARGETS, *core.WORKSPACE_ARCHIVE_COMPONENTS,
                *core.APPLICATION_BACKUP_COMPONENTS}
    assert sorted(element for element in elements if element not in labels) == []
    assert "'ticket-center': 'Ticket Center'," in script and "users_access: 'Users & Access'," in script
