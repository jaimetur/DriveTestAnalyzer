from pathlib import Path
import html
import io
import json
import re
import sqlite3
import zipfile

import pytest

from src.modules.repository import Repository
from src.modules.workspaces import WorkspaceRegistry
import src.DriveTestAnalyzer as app_module


def test_new_workspaces_have_empty_independent_template_libraries(tmp_path):
    legacy = tmp_path / 'shared'
    legacy.mkdir()
    registry = WorkspaceRegistry(tmp_path / 'data/workspaces/registry.db', tmp_path / 'data', legacy)
    registry.initialize()
    first = registry.get('default')
    second = registry.create('Second')
    assert first.slides_templates_dir != legacy
    assert first.slides_templates_dir != second.slides_templates_dir
    assert not list(first.slides_templates_dir.rglob('*.csv'))
    assert not list(second.slides_templates_dir.rglob('*.csv'))
    for workspace in (first, second):
        repo = Repository(workspace.database_path, tmp_path / 'application.db')
        repo.initialize()
        assert repo.list_report_templates() == []


def test_report_template_migration_canonicalizes_existing_csv_layouts(tmp_path):
    database = tmp_path / 'workspace.db'
    repo = Repository(database, tmp_path / 'application.db')
    repo.initialize()
    legacy = (
        'Slide,Layout,Dynamic Field\n'
        '1,Title and 2 columns and 2 rows + Comments right,\n'
        '2,Title + dynamic rows + 2 columns + comments down,Vendor\n'
        '3,Title + 2 rows + dynamic columns + comments right,Operator\n'
    ).encode('utf-8')
    with repo.connection() as conn:
        conn.execute(
            "INSERT INTO report_templates (name, content, is_default) VALUES ('Legacy', ?, 0)",
            (legacy,),
        )

    repo.initialize()

    migrated = repo.report_template_content('Legacy').decode('utf-8')
    assert 'Title + 2 rows + 2 columns + comments right' in migrated
    assert 'Dynamic Rows Field,Dynamic Columns Field' in migrated
    assert '2,Title + dynamic rows + 2 columns + comments down,Vendor,' in migrated
    assert '3,Title + 2 rows + dynamic columns + comments right,,Operator' in migrated


def test_legacy_library_migration_is_independent_and_idempotent(tmp_path):
    legacy = tmp_path / 'shared'
    template = legacy / 'library/nsa/Existing.csv'
    template.parent.mkdir(parents=True)
    template.write_text('original')
    registry = WorkspaceRegistry(tmp_path / 'data/workspaces/registry.db', tmp_path / 'data', legacy)
    registry.initialize()
    original = registry.get('default')
    local = original.slides_templates_dir / 'library/nsa/Existing.csv'
    assert local.read_text() == 'original'
    assert not legacy.exists()
    local.write_text('workspace edit')
    registry.initialize()
    assert local.read_text() == 'workspace edit'
    assert registry.get('default').database_path == original.database_path


def test_template_registry_is_workspace_owned(tmp_path):
    first = Repository(tmp_path / 'a.db', tmp_path / 'app.db')
    second = Repository(tmp_path / 'b.db', tmp_path / 'app.db')
    first.initialize()
    second.initialize()
    first.add_report_template('Only A', is_default=True)
    assert len(first.list_report_templates()) == 1
    assert second.list_report_templates() == []
    first.initialize()
    assert first.list_report_templates()[0]['name'] == 'Only A'


def test_template_package_matches_source_and_imports_to_multiple_workspaces(client, tmp_path):
    source = app_module.active_workspace
    package, _name = app_module.build_export_archive('ppt-templates')
    manifest = app_module.read_import_manifest(package)
    assert manifest['source_workspace']['name'] == source.name
    other = app_module.workspace_registry.create('Other')
    obsolete_directory = other.database_path.parent / 'slides-templates'
    obsolete_directory.mkdir(parents=True)
    (obsolete_directory / 'old.csv').write_text('obsolete', encoding='utf-8')
    repo = Repository(other.database_path, app_module.repository.global_db_path)
    repo.initialize()
    assert repo.list_report_templates() == []
    archive_path = tmp_path / 'templates.zip'
    archive_path.write_bytes(package)
    assert app_module.matching_template_workspaces(manifest, [other, source]) == [source.id]
    app_module._apply_import_archive(archive_path, manifest, destination_workspace_ids=[source.id, other.id])
    copied = next(row for row in repo.list_report_templates() if row['is_default'])
    source_content = app_module.reporting_catalog_content()
    assert bytes(copied['content']) == source_content
    repo.set_report_template_content(str(copied['name']), b'independent')
    assert app_module.reporting_catalog_content() == source_content
    assert repo.list_datasets() == []
    assert not obsolete_directory.exists()
    assert not other.slides_templates_dir.exists()


def test_template_import_without_matching_workspace_requires_selection(client, tmp_path):
    staging = tmp_path / 'payload'
    templates = staging / 'report-templates/library/nsa'
    templates.mkdir(parents=True)
    (templates / 'Imported.csv').write_bytes(app_module.catalogue_csv([]))
    with pytest.raises(ValueError, match='Select at least'):
        app_module.import_slides_templates_archive(staging, manifest={'source_workspace': {'name': 'Absent'}})


def test_template_package_replaces_and_adds_templates_without_duplicates(client, tmp_path):
    workspace = app_module.workspace_registry.create('Template destination')
    repo = Repository(workspace.database_path, app_module.repository.global_db_path)
    repo.initialize()
    repo.add_report_template('Old', b'old')
    repo.add_report_template('Same', b'previous')
    repo.add_report_template('Case Name', b'previous case')
    repo.add_report_template('Used', b'keep this', is_default=True)
    repo.set_workspace_state(app_module.DESIGN_STATE_KEY, json.dumps({
        'design-1': {'template_technology': 'nsa', 'template': 'Used'},
    }))
    staging = tmp_path / 'templates'
    library = staging / 'report-templates/library/nsa'
    library.mkdir(parents=True)
    for name, content in (
        ('Same', b'updated'), ('case name', b'updated case'),
        ('used', b'imported but protected'), ('New', b'new'),
    ):
        (library / f'{name}.csv').write_bytes(content)
    (staging / 'report-templates/default/nsa').mkdir(parents=True)
    (staging / 'report-templates/default/nsa/New.csv').write_bytes(b'new')

    for _ in range(2):
        assert app_module.import_slides_templates_archive(staging, [workspace.id], importing_user='super') == 1
    rows = {str(row['name']): row for row in repo.list_report_templates()}
    # The templates only the destination has stay; those of the package replace theirs and take its names.
    assert set(rows) == {'Old', 'Same', 'case name', 'used', 'New'}
    assert bytes(rows['Old']['content']) == b'old'
    assert bytes(rows['Same']['content']) == b'updated'
    assert bytes(rows['case name']['content']) == b'updated case'
    # Used by a Design of the destination: it keeps its definition, and the Design follows its name.
    assert bytes(rows['used']['content']) == b'keep this'
    assert json.loads(repo.get_workspace_state(app_module.DESIGN_STATE_KEY))['design-1']['template'] == 'used'
    # The destination keeps its default template.
    assert rows['used']['is_default'] == 1 and rows['New']['is_default'] == 0
    # Without a creator in the package, a new template belongs to the user who imports it.
    assert rows['New']['created_by'] == 'super'


def test_template_renamed_on_the_source_is_renamed_in_the_destination(client, tmp_path):
    source = app_module.workspace_registry.create('Template source')
    destination = app_module.workspace_registry.create('Template renamed destination')
    source_repo = Repository(source.database_path, app_module.repository.global_db_path)
    destination_repo = Repository(destination.database_path, app_module.repository.global_db_path)
    for repo in (source_repo, destination_repo):
        repo.initialize()
    source_repo.add_report_template('Coverage', b'first', updated_by='super')
    destination_repo.add_report_template('Elsewhere', b'local', updated_by='super')
    package_path = tmp_path / 'templates.zip'
    app_module.build_export_archive_file('ppt-templates', package_path, [source.id])
    app_module._apply_import_archive(package_path, app_module.read_import_manifest(package_path),
                                     destination_workspace_ids=[destination.id], importing_user='super')
    destination_repo.set_workspace_state(app_module.DESIGN_STATE_KEY, json.dumps({
        'design-1': {'template_technology': 'nsa', 'template': 'Coverage', 'name': 'Coverage NSA'},
    }))

    # Renamed and changed on the source, another template of the destination already having its new name.
    source_repo.rename_report_template('Coverage', 'Elsewhere')
    source_repo.set_report_template_content('Elsewhere', b'second')
    app_module.build_export_archive_file('ppt-templates', package_path, [source.id])
    notice = app_module._apply_import_archive(package_path, app_module.read_import_manifest(package_path),
                                              destination_workspace_ids=[destination.id], importing_user='other')
    rows = {str(row['name']): row for row in destination_repo.list_report_templates()}
    assert set(rows) == {'Elsewhere', 'Elsewhere (2)'}
    assert bytes(rows['Elsewhere']['content']) == b'local'
    # A Design of the destination uses it, so it keeps its definition (the package brings no Designs).
    assert bytes(rows['Elsewhere (2)']['content']) == b'first'
    assert '"Coverage" renamed "Elsewhere (2)"' in notice
    design = json.loads(destination_repo.get_workspace_state(app_module.DESIGN_STATE_KEY))['design-1']
    assert design['template'] == 'Elsewhere (2)'
    # Its creator on the source exists here, so it keeps belonging to them.
    assert rows['Elsewhere (2)']['created_by'] == 'super'

    # Without Designs that use it, a template of the package replaces the definition too.
    destination_repo.set_workspace_state(app_module.DESIGN_STATE_KEY, '{}')
    app_module._apply_import_archive(package_path, app_module.read_import_manifest(package_path),
                                     destination_workspace_ids=[destination.id], importing_user='other')
    rows = {str(row['name']): row for row in destination_repo.list_report_templates()}
    assert set(rows) == {'Elsewhere', 'Elsewhere (2)'}
    assert bytes(rows['Elsewhere (2)']['content']) == b'second'


def test_template_package_with_designs_replaces_referenced_templates(client, tmp_path):
    workspace = app_module.workspace_registry.create('Bundle destination')
    repo = Repository(workspace.database_path, app_module.repository.global_db_path)
    repo.initialize()
    repo.add_report_template('Used', b'old', is_default=True)
    repo.set_workspace_state(app_module.DESIGN_STATE_KEY, json.dumps({
        'design-1': {'template_technology': 'nsa', 'template': 'Used'},
    }))
    staging = tmp_path / 'templates'
    library = staging / 'report-templates/library/nsa'
    library.mkdir(parents=True)
    (library / 'Used.csv').write_bytes(b'new')

    app_module.import_slides_templates_archive(staging, [workspace.id], includes_designs=True)
    rows = repo.list_report_templates()
    assert len(rows) == 1
    assert bytes(rows[0]['content']) == b'new'


def test_template_and_design_bundle_replaces_referenced_template(client, tmp_path):
    source = app_module.active_workspace
    source_repo = Repository(source.database_path, app_module.repository.global_db_path)
    source_repo.add_report_template('Bundle Used', b'imported')
    destination = app_module.workspace_registry.create('Bundle destination')
    destination_repo = Repository(destination.database_path, app_module.repository.global_db_path)
    destination_repo.initialize()
    destination_repo.add_report_template('Bundle Used', b'local')
    destination_repo.set_workspace_state(app_module.DESIGN_STATE_KEY, json.dumps({
        'local-design': {'template_technology': 'nsa', 'template': 'Bundle Used'},
    }))
    package_path = tmp_path / 'bundle.zip'
    app_module.build_export_archive_file(['ppt-templates', 'designs'], package_path)

    phases = []
    app_module._apply_import_archive(
        package_path, app_module.read_import_manifest(package_path),
        progress_callback=lambda phase, _progress: phases.append(phase),
        destination_workspace_ids=[destination.id],
    )
    # The progress names each package being imported, and what each one is doing within its share of the bar.
    assert [phase for phase in phases if phase.startswith('importing package') and ':' not in phase] == [
        'importing package 1 of 2 (PPT Templates)', 'importing package 2 of 2 (PPT Designs)']
    assert 'importing package 1 of 2 (PPT Templates): importing PPT Templates' in phases
    rows = [row for row in destination_repo.list_report_templates() if str(row['name']) == 'Bundle Used']
    assert len(rows) == 1
    assert bytes(rows[0]['content']) == b'imported'
    # The Designs of the bundle (the source's starter Designs) are added to the local ones.
    imported = json.loads(destination_repo.get_workspace_state(app_module.DESIGN_STATE_KEY))
    assert 'local-design' in imported
    assert sorted(item['name'] for key, item in imported.items() if key != 'local-design') == sorted(
        item['name'] for item in json.loads(source_repo.get_workspace_state(app_module.DESIGN_STATE_KEY)).values())


def test_selective_template_restore_replaces_and_adds_like_an_import(client, tmp_path):
    repo = app_module.repository
    repo.add_report_template('Backup Template', b'archived')
    archive_path = app_module.create_recurring_database_backup({
        'components': ['report_templates'], 'backup_path': str(tmp_path / 'backups'),
        'max_backups': 30, 'workspace_ids': [app_module.active_workspace.id],
    })
    repo.set_report_template_content('Backup Template', b'local edit')
    repo.add_report_template('Old', b'remove')
    repo.add_report_template('Used', b'preserve')
    repo.set_workspace_state(app_module.DESIGN_STATE_KEY, json.dumps({
        'local-design': {'template_technology': 'nsa', 'template': 'Used'},
    }))

    app_module.restore_database_backup(archive_path, ['report_templates'])
    rows = {str(row['name']): row for row in repo.list_report_templates()}
    # The templates the backup does not have stay, as with an import.
    assert bytes(rows['Old']['content']) == b'remove'
    assert bytes(rows['Backup Template']['content']) == b'archived'
    assert bytes(rows['Used']['content']) == b'preserve'


def test_template_export_pins_source_when_active_workspace_changes(client, tmp_path):
    source = app_module.active_workspace
    other = app_module.workspace_registry.create('Other')
    app_module.activate_workspace(other.id)
    path = tmp_path / 'source.zip'
    app_module.build_export_archive_file('ppt-templates', path, [source.id])
    with zipfile.ZipFile(path) as archive:
        assert json.loads(archive.read('manifest.json'))['source_workspace']['name'] == source.name
        assert any(name.endswith('.csv') for name in archive.namelist())
    # The options are the other workspace's own templates: only the ones every workspace starts with.
    starter = {path.stem for path in (app_module.PROJECT_ROOT / 'assets' / 'ppt-templates').glob('*.csv')}
    assert {item['identifier'] for item in app_module.report_catalogue_options()} == starter


def test_inspection_preselects_only_matching_workspace_and_is_for_super_admins(client, tmp_path, monkeypatch):
    source = app_module.active_workspace
    package, _name = app_module.build_export_archive('ppt-templates')
    other = app_module.workspace_registry.create('Other')
    # Only super-admins import packages.
    client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=False)
    assert client.post('/admin/import-export/inspect/upload', content=package,
                       headers={'Content-Type': 'application/zip'}).status_code == 403
    assert client.post('/admin/import-export/import/jobs', data={'upload_id': 'x', 'confirmed_import': 'true'}).status_code == 403
    client.post('/login', data={'username': 'super', 'password': 'super123'}, follow_redirects=False)
    result = client.post('/admin/import-export/inspect/upload', content=package,
                         headers={'Content-Type': 'application/zip'})
    assert result.status_code == 200, result.text
    assert result.json()['selected_workspace_ids'] == [source.id]
    assert other.id in [item['id'] for item in result.json()['destination_workspaces']]


def test_workspace_archive_and_duplicate_include_templates(client, tmp_path):
    source = app_module.active_workspace
    package, _name = app_module.build_export_archive(f'workspace:{source.id}')
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        assert any(name.startswith('workspaces/Default/report-templates/') and name.endswith('.csv')
                   for name in archive.namelist())
        snapshot = tmp_path / 'snapshot.db'
        snapshot.write_bytes(archive.read('workspaces/Default/database.sqlite'))
    with sqlite3.connect(snapshot) as conn:
        assert conn.execute('SELECT COUNT(*) FROM report_templates').fetchone()[0] > 0
    duplicate = app_module.workspace_registry.duplicate(source.id)
    repo = Repository(duplicate.database_path, app_module.repository.global_db_path)
    repo.initialize()
    assert repo.list_report_templates()
    assert not list(duplicate.slides_templates_dir.rglob('*.csv'))


def test_workspace_duplicate_optionally_copies_generated_designs_and_reports(tmp_path):
    registry = WorkspaceRegistry(tmp_path / 'data/workspaces/registry.db', tmp_path / 'data', tmp_path / 'shared')
    registry.initialize()
    source = registry.get('default')
    assert source is not None
    source_repository = Repository(source.database_path, tmp_path / 'application.db')
    source_repository.initialize()
    design = source.output_dir / 'reports' / 'ppt-designs' / '20260910_120000 - Design' / 'design.pptx'
    design.parent.mkdir(parents=True, exist_ok=True)
    design.write_bytes(b'design')
    # The documents an earlier version wrote in the folders of PPT Reporting (old) are generated outputs too.
    chart = source.output_dir / 'reports' / 'reports-charts-old' / '20260910-120000' / 'chart-1.png'
    chart.parent.mkdir(parents=True, exist_ok=True)
    chart.write_bytes(b'chart')
    with sqlite3.connect(source.database_path) as connection:
        connection.execute('CREATE TABLE IF NOT EXISTS design_ppt_jobs (id INTEGER PRIMARY KEY, output_path TEXT NOT NULL)')
        connection.execute('INSERT INTO design_ppt_jobs (output_path) VALUES (?)', (str(design),))

    copied = registry.duplicate(source.id, include_generated_outputs=True)
    copied_design = copied.output_dir / 'reports' / 'ppt-designs' / '20260910_120000 - Design' / 'design.pptx'
    assert copied_design.read_bytes() == b'design'
    assert (copied.output_dir / 'reports' / 'reports-charts-old' / '20260910-120000' / 'chart-1.png').read_bytes() == b'chart'
    with sqlite3.connect(copied.database_path) as connection:
        copied_path = connection.execute('SELECT output_path FROM design_ppt_jobs').fetchone()[0]
    assert copied_path == str(copied_design)

    without_outputs = registry.duplicate(source.id)
    assert not (without_outputs.output_dir / 'reports' / 'ppt-designs').exists()
    assert not (without_outputs.output_dir / 'reports' / 'reports-charts-old').exists()
    with sqlite3.connect(without_outputs.database_path) as connection:
        assert connection.execute('SELECT COUNT(*) FROM design_ppt_jobs').fetchone()[0] == 0


def test_template_transfer_requires_and_retains_multiple_destinations(client):
    source = app_module.active_workspace
    other = app_module.workspace_registry.create('Second destination')
    headers = {'X-Dashboard-Transfer-Secret': 'template-transfer-secret-with-sufficient-length'}
    offered = client.post('/api/import-export/transfers/offers', headers=headers, json={
        'source': 'Template test source', 'archive_version': 1, 'kind': 'ppt-templates',
        'content': 'PPT Templates', 'workspaces': [source.name],
    })
    assert offered.status_code == 200
    offer_id = offered.json()['offer_id']
    client.post('/login', data={'username': 'super', 'password': 'super123'}, follow_redirects=False)
    try:
        selected = [source.id]
        accepted = client.post(f'/admin/import-export/transfers/offers/{offer_id}/accept', json={})
        assert accepted.status_code == 200
        assert app_module.TRANSFER_OFFERS[offer_id]['destination_workspace_ids'] == selected
    finally:
        client.delete(f'/api/import-export/transfers/offers/{offer_id}', headers=headers)


def test_auto_field_package_preselects_source_workspace(client):
    source = app_module.active_workspace
    other = app_module.workspace_registry.create('Additional destination')
    app_module.repository.grant_all_workspace_access(other.id)
    package, _name = app_module.build_export_archive('auto-calculated-fields')
    client.post('/login', data={'username': 'super', 'password': 'super123'}, follow_redirects=False)
    response = client.post('/admin/import-export/inspect/upload', content=package,
                           headers={'Content-Type': 'application/zip'})
    assert response.status_code == 200
    payload = response.json()
    assert payload['selected_workspace_ids'] == [source.id]
    assert {item['id'] for item in payload['destination_workspaces']} >= {source.id, other.id}


def test_database_management_groups_template_registry_with_workspace_tables(client, monkeypatch):
    import re

    monkeypatch.setattr(app_module, 'asset_version', lambda path: 'test')
    # A legacy global registry must not shadow the new workspace registry.
    with app_module.repository.global_connection() as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS report_templates (name TEXT)')
        conn.execute("INSERT INTO report_templates (name) VALUES ('Legacy global')")
    # Database Management is in Super Admin.
    client.post('/login', data={'username': 'super', 'password': 'super123'}, follow_redirects=False)
    response = client.get('/super-admin')
    assert response.status_code == 200
    groups = dict(re.findall(r'<optgroup label="([^"]+)">(.*?)</optgroup>', response.text, re.S))
    assert 'value="report_templates"' in groups['Workspace Tables']
    assert 'PPT Templates' in groups['Workspace Tables']
    assert 'value="report_templates"' not in groups['Config Tables']


def _template_names(repo):
    return [str(row['name']) for row in repo.list_report_templates()]


def test_template_library_keeps_the_order_given_and_adds_new_templates_last(tmp_path):
    repo = Repository(tmp_path / 'a.db', tmp_path / 'app.db')
    repo.initialize()
    for name in ('Beta', 'alpha', 'Gamma'):
        repo.add_report_template(name, b'x')
    # Until it is ordered, the library is sorted by name (and new templates take their place by name).
    assert _template_names(repo) == ['alpha', 'Beta', 'Gamma']
    # Names it does not know are left out and the templates it does not name follow in their order.
    assert repo.reorder_report_templates(['Gamma', 'Missing', 'alpha']) == ['Gamma', 'alpha', 'Beta']
    repo.add_report_template('Delta', b'x')
    repo.rename_report_template('alpha', 'Alpha 2')
    assert _template_names(repo) == ['Gamma', 'Alpha 2', 'Beta', 'Delta']
    repo.delete_report_template('Gamma')
    repo.add_report_template('Epsilon', b'x')
    assert _template_names(repo) == ['Alpha 2', 'Beta', 'Delta', 'Epsilon']


def test_template_order_route_saves_the_order_for_every_list_and_records_it(client):
    client.post('/login', data={'username': 'super', 'password': 'super123'}, follow_redirects=False)
    repo = app_module.repository
    for name in ('Order B', 'Order A'):
        repo.add_report_template(name, b'x')
    names = [str(option['name']) for option in sorted(app_module.report_catalogue_options(),
                                                      key=app_module.report_template_library_key)]
    wanted = [names[-1], *names[:-1]]

    response = client.post('/api/ppt-designer/templates/order', json={'names': wanted})
    assert response.status_code == 200 and response.json() == {'order': wanted}
    assert [option['name'] for option in app_module.report_catalogue_options()] == wanted
    library = client.get('/api/ppt-designer/templates-library').json()
    # The Template of a new PPT Design and the rows of PPT Templates follow it.
    assert [row['name'] for row in library['templates']] == wanted
    rows = re.findall(r'<tr data-template-name="([^"]+)"', library['html'])
    assert [html.unescape(name) for name in rows] == wanted
    [event] = [row for row in repo.list_logs(limit=20) if row['action'] == 'reorder_report_templates']
    assert json.loads(event['details']) == {'previous_order': names, 'order': wanted}

    # The same order again records nothing.
    client.post('/api/ppt-designer/templates/order', json={'names': wanted})
    assert len([row for row in repo.list_logs(limit=20) if row['action'] == 'reorder_report_templates']) == 1


def test_template_package_carries_the_order_of_its_library(client, tmp_path):
    source = app_module.workspace_registry.create('Ordered source')
    destination = app_module.workspace_registry.create('Ordered destination')
    source_repo = Repository(source.database_path, app_module.repository.global_db_path)
    destination_repo = Repository(destination.database_path, app_module.repository.global_db_path)
    for repo in (source_repo, destination_repo):
        repo.initialize()
    for name in ('One', 'Two', 'Three'):
        source_repo.add_report_template(name, name.encode())
    destination_repo.add_report_template('Local', b'local')
    destination_repo.add_report_template('Two', b'previous')
    package_path = tmp_path / 'templates.zip'

    # A library still sorted by name brings no order: the destination stays sorted by name.
    app_module.build_export_archive_file('ppt-templates', package_path, [source.id])
    app_module._apply_import_archive(package_path, app_module.read_import_manifest(package_path),
                                     destination_workspace_ids=[destination.id], importing_user='super')
    assert _template_names(destination_repo) == ['Local', 'One', 'Three', 'Two']

    # An ordered one: its templates keep their order, before those only the destination has.
    source_repo.reorder_report_templates(['Three', 'One', 'Two'])
    app_module.build_export_archive_file('ppt-templates', package_path, [source.id])
    manifest = app_module.read_import_manifest(package_path)
    assert [(item['name'], item['position']) for item in manifest['report_templates']] == [('Three', 1), ('One', 2), ('Two', 3)]
    app_module._apply_import_archive(package_path, manifest, destination_workspace_ids=[destination.id], importing_user='super')
    assert _template_names(destination_repo) == ['Three', 'One', 'Two', 'Local']


def test_template_restore_brings_back_the_order_of_the_backup(client, tmp_path):
    repo = app_module.repository
    for name in ('Restore A', 'Restore B'):
        repo.add_report_template(name, b'x')
    current = _template_names(repo)
    repo.reorder_report_templates(list(reversed(current)))
    archive_path = app_module.create_recurring_database_backup({
        'components': ['report_templates'], 'backup_path': str(tmp_path / 'backups'),
        'max_backups': 30, 'workspace_ids': [app_module.active_workspace.id],
    })
    repo.reorder_report_templates(current)
    repo.add_report_template('After backup', b'x')

    app_module.restore_database_backup(archive_path, ['report_templates'])
    assert _template_names(repo) == [*reversed(current), 'After backup']
