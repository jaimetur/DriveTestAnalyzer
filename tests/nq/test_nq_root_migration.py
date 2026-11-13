"""The move of the root cause catalog to generic Root Categories, specific Root Causes and the Root Technology (ticket
#139): the translation of the former values, the one-time migration of a workspace (V47) and the import of a tracking
document written with the former catalog."""

import json

import pytest

import src.DriveTestAnalyzer as core
from src.modules.nq import non_qualified_calls as nq
from src.modules.nq import nq_catalog, nq_dta_rca, nq_root_migration
from tests.nq.test_nq_analysis_center import setup_calls


@pytest.fixture(autouse=True)
def indexing_runs_at_once(monkeypatch):
    monkeypatch.setattr(core, 'submit_background_task', lambda callback, *args: callback(*args))


@pytest.mark.parametrize(('category', 'cause', 'technology', 'expected'), [
    # A category with a technology gives the generic category and the technology; a former cause is renamed.
    ('Poor Coverage LTE', 'Coverage', '', ('Coverage', 'DL coverage', '4G - LTE')),
    ('Poor Coverage NR', 'LOS but weak signal', '', ('Coverage', 'LOS but weak signal', '5G - NR')),
    # A category that implied a cause gives it when the decision has none.
    ('DL Interference LTE', '', '', ('Interference', 'DL interference', '4G - LTE')),
    ('UL Interference 2G/3G', '', '', ('Interference', 'UL interference', '')),
    ('BLER NR', 'BLER', '', ('Radio Link Quality', 'High DL BLER', '5G - NR')),
    ('Other GSM', '', '', ('Indeterminate', 'Unclear', '2G - GSM')),
    ('Additional Investigation LTE', '', '', ('Indeterminate', 'Further investigation required', '4G - LTE')),
    ('Invalidated', '', '', ('Invalid', 'Invalid', '')),
    # The Validation category of the first step of ticket #139: the category of its cause.
    ('Validation', 'Invalidated', '', ('Invalid', 'Invalid', '')),
    ('Validation', 'Unclear', '', ('Indeterminate', 'Unclear', '')),
    ('Validation', '', '', ('Indeterminate', '', '')),
    # A category split by the cause of the decision: the category of the cause, else the fallback.
    ('IMS / VoLTE', 'No QCI1 established', '', ('Voice Core (IMS)', 'No QCI1 established', '')),
    ('Core Network', 'Insufficient resources', '', ('Session & Mobility Management', 'Insufficient resources', '')),
    ('Core Network', '', '', ('Session & Mobility Management', '', '')),
    ('RAN Performance', 'RRC layer', '', ('Radio Signalling', 'Radio link failure', '')),
    ('RAN Capacity', 'Access rejected (no resources)', '', ('Capacity', 'Access rejected (no resources)', '')),
    ('Protocol / Server', 'DNS', '', ('Server & Protocol', 'DNS', '')),
    ('Authentication & Registration', 'TAU reject', '', ('Session & Mobility Management', 'TAU reject', '')),
    ('E2E', '', '', ('End-to-End', '', '')),
    # A technology given is kept; the case of the former name does not matter.
    ('poor coverage lte', '', 'NR', ('Coverage', '', '5G - NR')),
    # The category of a cause of the catalog wins over the one the former category gives.
    ('Poor Coverage LTE', 'Lack of dominant cell', '', ('Interference', 'Lack of dominant cell', '4G - LTE')),
    ('Invalidated', 'Overshooting or excessive cell overlap', '', ('Interference', 'Overshooting or excessive cell overlap', '')),
    # Current values and a workspace's own ones stay as they are.
    ('Coverage', 'DL coverage', 'NR', ('Coverage', 'DL coverage', '5G - NR')),
    ('My category', 'My cause', '', ('My category', 'My cause', '')),
])
def test_former_pairs_translate_onto_the_current_catalog(category, cause, technology, expected):
    found = nq_root_migration.translate(category, cause, technology)
    assert (found['category'], found['cause'], found['technology']) == expected
    # Every current category it gives is a category of the catalog.
    if found['category'] not in {'My category'}:
        assert found['category'] in {name for name, _domain, _keywords in nq_catalog.DEFAULT_CATEGORIES}


def test_former_catalogs_are_recognised_and_replaced_keeping_the_values_of_the_workspace():
    former = nq_catalog.legacy_root_catalog()
    assert nq_root_migration.is_former_catalog(former) and not nq_root_migration.is_former_catalog(nq_catalog.default_root_catalog())
    former['categories'].append({'name': 'My category', 'domain': 'AAA', 'keywords': []})
    former['causes'].append({'name': 'Backhaul', 'domain': 'Core EPSFB', 'keywords': ['backhaul'], 'category': 'Core Network'})
    translated = nq_root_migration.translate_catalog(former)
    names = [item['name'] for item in translated['categories']]
    assert names[:len(nq_catalog.DEFAULT_CATEGORIES)] == [name for name, _domain, _keywords in nq_catalog.DEFAULT_CATEGORIES]
    assert names[len(nq_catalog.DEFAULT_CATEGORIES):] == ['My category']
    assert {item['name'] for item in translated['domains']} == {name for name, _color, _keywords in nq_catalog.DEFAULT_DOMAINS}
    causes = {item['name']: item for item in translated['causes']}
    assert 'Coverage' not in causes and 'RRC layer' not in causes
    assert (causes['Backhaul']['category'], causes['Backhaul']['domain']) == ('Session & Mobility Management', 'Core')
    assert next(item for item in translated['categories'] if item['name'] == 'My category')['domain'] == 'Core'


def tracking_of(call_keys):
    with core.repository.connection() as connection:
        rows = connection.execute(f'SELECT call_key, root_domain, root_category, root_cause, root_technology FROM {nq.NQ_CALL_TRACKING_TABLE}')
        found = {str(row['call_key']): (row['root_domain'], row['root_category'], row['root_cause'], row['root_technology']) for row in rows}
    return {name: found.get(key) for name, key in call_keys.items()}


def initial_values(call_key):
    with core.repository.connection() as connection:
        return {str(row['field_key']): str(row['value']) for row in connection.execute(
            f'SELECT field_key, value FROM {nq.NQ_FIELD_VALUES_TABLE} WHERE call_key = ?', (call_key,))
            if row['field_key'] in nq.ROOT_TEXT_FIELDS}


def test_a_workspace_with_the_former_catalog_moves_to_the_current_one_once(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    keys = {join_id: call['call_key'] for join_id, call in calls.items()}
    repository = core.repository
    # A workspace of v0.12.4: the former catalog, decisions and Initial Root Category / Cause with its names, a status
    # rule on the root category, DT Analyzer RCA rules of its own and no Selected Root Technology field.
    former_rule = {'key': 'mine', 'name': 'My NR coverage', 'enabled': True, 'services': [], 'match': 'all',
                   'conditions': [{'input': 'failure_text', 'op': 'contains', 'value': 'my failure'}],
                   'category': 'Poor Coverage NR', 'cause': 'Coverage'}
    with repository.connection() as connection:
        nq._write_root_catalog(connection, nq_catalog.normalize_root_catalog(nq_catalog.legacy_root_catalog()))
        for join_id, (domain, category, cause) in {'0xA1': ('RF', 'Poor Coverage LTE', 'Coverage'),
                                                   '0xB2': ('IMS/E2E', 'IMS / VoLTE', 'No QCI1 established'),
                                                   '0xC3': ('RF', 'DL Interference NR', '')}.items():
            connection.execute(
                f"INSERT INTO {nq.NQ_CALL_TRACKING_TABLE} (call_key, status, status_mode, root_domain, root_category, root_cause, version, "
                "updated_by, updated_at) VALUES (?, 'Not Attended', 'auto', ?, ?, ?, 1, 'super', '2026-10-01T10:00:00') "
                "ON CONFLICT(call_key) DO UPDATE SET root_domain = excluded.root_domain, root_category = excluded.root_category, "
                "root_cause = excluded.root_cause", (keys[join_id], domain, category, cause))
        for field_key, value in (('initial_root_category', 'BLER LTE'), ('initial_root_cause', 'BLER')):
            connection.execute(f'INSERT INTO {nq.NQ_FIELD_VALUES_TABLE} (call_key, field_key, value, updated_by, updated_at) '
                               "VALUES (?, ?, ?, 'super', '2026-10-01T10:00:00')", (keys['0xA1'], field_key, value))
    rules = nq.status_rules(repository)
    rules.insert(0, {'status': 'Closed', 'conditions': [{'field': '@root_category', 'op': 'in', 'values': ['Unclear', 'Invalidated']}]})
    repository.set_workspace_state(nq.STATUS_RULES_STATE_KEY, json.dumps(rules))
    repository.set_workspace_state(nq_dta_rca.RULES_STATE_KEY, json.dumps([former_rule, *nq_dta_rca.default_rules()]))
    nq._store_fields(repository, [field for field in nq.list_fields(repository) if field['key'] != 'selected_root_technology'])
    # The backup rows of the migration of the new workspace come first.
    with repository.connection() as connection:
        first = connection.execute(f'SELECT COALESCE(MAX(id), 0) FROM {nq.NQ_ROOT_MIGRATION_TABLE}').fetchone()[0]
    repository.set_workspace_state(nq.ANALYSIS_CENTER_V47_STATE_KEY, '')
    repository.set_workspace_state(nq.SCHEMA_STATE_KEY, '')
    nq.ensure_nq_tables(repository)
    # The decisions, with their technology and the domain of the current catalog.
    assert tracking_of(keys) == {'0xA1': ('RF', 'Coverage', 'DL coverage', '4G - LTE'),
                                 '0xB2': ('IMS/E2E', 'Voice Core (IMS)', 'No QCI1 established', ''),
                                 '0xC3': ('RF', 'Interference', 'DL interference', '5G - NR')}
    assert initial_values(keys['0xA1']) == {'initial_root_category': 'Radio Link Quality', 'initial_root_cause': 'High DL BLER'}
    # The catalog, the status rule and the DT Analyzer RCA rules.
    root = nq.list_root_causes(repository)
    assert [item['name'] for item in root['categories']] == [name for name, _domain, _keywords in nq_catalog.DEFAULT_CATEGORIES]
    assert 'AAA' not in {item['name'] for item in root['domains']}
    assert {'field': '@root_category', 'op': 'in', 'values': ['Indeterminate', 'Invalid']} in nq.status_rules(repository)[0]['conditions']
    mine = next(rule for rule in nq_dta_rca.load_rules(repository) if rule['key'] == 'mine')
    assert (mine['category'], mine['cause'], mine.get('technology')) == ('Coverage', 'DL coverage', '5G - NR')
    assert 'selected_root_technology' in {field['key'] for field in nq.list_fields(repository)}
    # The values they had are kept in the backup table.
    with repository.connection() as connection:
        backup = [dict(row) for row in connection.execute(f'SELECT kind, item_key, value_json FROM {nq.NQ_ROOT_MIGRATION_TABLE} WHERE id > ?', (first,))]
    assert nq.NQ_ROOT_MIGRATION_TABLE == 'nq_root_migration_backup'
    kinds = [row['kind'] for row in backup]
    assert kinds.count('catalog') == 1 and kinds.count('tracking') == 3 and kinds.count('field_value') == 2
    assert {row['item_key'] for row in backup if row['kind'] == 'state'} >= {nq_dta_rca.RULES_STATE_KEY, nq.STATUS_RULES_STATE_KEY}
    tracked = {row['item_key']: json.loads(row['value_json']) for row in backup if row['kind'] == 'tracking'}
    assert (tracked[keys['0xA1']]['root_category'], tracked[keys['0xA1']]['root_cause']) == ('Poor Coverage LTE', 'Coverage')
    catalog = json.loads(next(row['value_json'] for row in backup if row['kind'] == 'catalog'))
    assert 'Poor Coverage LTE' in {item['name'] for item in catalog['categories']}
    assert {json.loads(row['value_json']) for row in backup if row['kind'] == 'field_value'} == {'BLER LTE', 'BLER'}
    # And the App Events tell what was done.
    log = next(row for row in repository.list_logs(limit=50) if row['action'] == 'nq_root_catalog_migrated')
    details = json.loads(log['details'])
    assert details['catalog_replaced'] is True and details['calls_translated'] == 3 and details['initial_values_translated'] == 2
    assert details['dta_rules_translated'] is True and details['backup_table'] == 'nq_root_migration_backup'
    # Once: a later start changes nothing.
    nq.ensure_nq_tables(repository)
    with repository.connection() as connection:
        assert connection.execute(f'SELECT COUNT(*) FROM {nq.NQ_ROOT_MIGRATION_TABLE} WHERE id > ?', (first,)).fetchone()[0] == len(backup)


def test_a_tracking_document_of_the_former_catalog_imports_on_the_current_one(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    keys = {join_id: call['call_key'] for join_id, call in calls.items()}
    response = client.patch(f"/api/non-qualified-calls/calls/{keys['0xA1']}",
                            json={'changes': {'root_category': 'Coverage', 'root_cause': 'DL coverage',
                                              'fields': {'initial_root_category': 'Coverage'}}})
    assert response.status_code == 200, response.text
    document = json.loads(nq.export_tracking_document(core.repository))
    # As v0.12.4 wrote it: the former catalog and its names on the decisions and the Initial Root Category.
    document['root_causes'] = {**document['root_causes'], **nq_catalog.legacy_root_catalog()}
    row = next(item for item in document['tracking'] if item['call_key'] == keys['0xA1'])
    row.update(root_domain='RF', root_category='Poor Coverage NR', root_cause='Coverage')
    row.pop('root_technology', None)
    document['field_values'] = [dict(item, value='DL Interference LTE') if item.get('field_key') == 'initial_root_category' else item
                                for item in document.get('field_values') or []]
    with core.repository.connection() as connection:
        for table in (nq.NQ_CALL_TRACKING_TABLE, nq.NQ_FIELD_VALUES_TABLE):
            connection.execute(f'DELETE FROM {table}')
    assert nq.import_tracking_document(core.repository, json.dumps(document)) >= 1
    assert tracking_of({'0xA1': keys['0xA1']})['0xA1'] == ('RF', 'Coverage', 'DL coverage', '5G - NR')
    assert initial_values(keys['0xA1']) == {'initial_root_category': 'Interference', 'initial_root_cause': 'DL interference'}
    root = nq.list_root_causes(core.repository)
    assert 'Poor Coverage NR' not in {item['name'] for item in root['categories']} and 'Coverage' in {item['name'] for item in root['categories']}


def test_a_workspace_with_the_validation_category_takes_the_indeterminate_and_invalid_domains_once(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    keys = {join_id: call['call_key'] for join_id, call in calls.items()}
    repository = core.repository
    # A workspace the first step of ticket #139 moved: its Validation category of the Operational domain with the cause
    # Invalidated, and decisions on them.
    catalog = nq_catalog.default_root_catalog()
    catalog['domains'] = [item for item in catalog['domains'] if item['name'] not in {'Indeterminate', 'Invalid'}]
    catalog['categories'] = [item for item in catalog['categories'] if item['name'] not in {'Indeterminate', 'Invalid'}]
    catalog['categories'].append({'name': 'Validation', 'domain': 'Operational', 'keywords': []})
    catalog['causes'] = [{**item, 'category': 'Validation', 'domain': ''} if item['category'] in {'Indeterminate', 'Invalid'} else item
                         for item in catalog['causes'] if item['name'] != 'Invalid']
    catalog['causes'].append({'name': 'Invalidated', 'domain': '', 'keywords': ['invalidated'], 'category': 'Validation'})
    with repository.connection() as connection:
        nq._write_root_catalog(connection, nq_catalog.normalize_root_catalog(catalog))
        for join_id, cause in (('0xA1', 'Invalidated'), ('0xB2', 'Unclear'), ('0xC3', '')):
            connection.execute(
                f"INSERT INTO {nq.NQ_CALL_TRACKING_TABLE} (call_key, status, status_mode, root_domain, root_category, root_cause, version, "
                "updated_by, updated_at) VALUES (?, 'Not Attended', 'auto', 'Operational', 'Validation', ?, 1, 'super', '2026-11-13T04:00:00') "
                "ON CONFLICT(call_key) DO UPDATE SET root_domain = excluded.root_domain, root_category = excluded.root_category, "
                "root_cause = excluded.root_cause", (keys[join_id], cause))
    repository.set_workspace_state(nq.ANALYSIS_CENTER_V48_STATE_KEY, '')
    repository.set_workspace_state(nq.SCHEMA_STATE_KEY, '')
    nq.ensure_nq_tables(repository)
    assert tracking_of(keys) == {'0xA1': ('Invalid', 'Invalid', 'Invalid', ''), '0xB2': ('Indeterminate', 'Indeterminate', 'Unclear', ''),
                                 '0xC3': ('Indeterminate', 'Indeterminate', '', '')}
    root = nq.list_root_causes(repository)
    assert {'Indeterminate', 'Invalid'} <= {item['name'] for item in root['domains']}
    assert 'Validation' not in {item['name'] for item in root['categories']}
    causes = {item['name']: item['category'] for item in root['causes']}
    assert 'Invalidated' not in causes and causes['Invalid'] == 'Invalid' and causes['Unclear'] == 'Indeterminate'
