"""Readable App Events: what an event changed, as one sentence."""
from __future__ import annotations

from src.modules.app_event_details import changed_values, describe_app_event


def test_changed_values_keep_only_what_changed() -> None:
    before = {'role': 'user-viewer', 'active': False, 'groups': ['UK', 'DE'], 'first_name': None,
              'labels': {'reporting': {'title': 'Reporting', 'color': '#123456'}}}
    after = {'role': 'user-editor', 'active': True, 'groups': ['DE', 'UK'], 'first_name': '',
             'labels': {'reporting': {'title': 'Reports', 'color': '#123456'}}}
    # Lists compare without their order, a missing value equals an empty one and nested settings one by one.
    assert changed_values(before, after) == {
        'role': ['user-viewer', 'user-editor'], 'active': [False, True], 'labels.reporting.title': ['Reporting', 'Reports']}
    assert changed_values(after, after) == {}


def test_events_read_as_one_sentence_old_and_new() -> None:
    assert describe_app_event('update_user', {
        'user_id': 15, 'username': 'ELUILEY', 'role': 'user-editor', 'active': True, 'password_changed': True,
        'changes': {'role': ['user-viewer', 'user-editor'], 'active': [False, True], 'workspace_groups': [['UK'], ['UK', 'DE']]},
    }) == 'User ELUILEY: role user-viewer → user-editor; activated; Workspace Groups +DE; password changed.'
    assert describe_app_event('update_user', {'user_id': 15, 'username': 'ELUILEY', 'role': 'user-editor', 'active': True,
                                              'changes': {}}) == 'User ELUILEY saved with no changes.'
    # Events recorded before with only the final state say what was saved, and that it is not what changed.
    assert describe_app_event('update_user', {'user_id': 15, 'username': 'ELUILEY', 'role': 'user-editor', 'active': True}) == (
        'User ELUILEY saved (role user-editor, active); earlier versions did not record which fields changed.')
    assert describe_app_event('update_workspace_group', {
        'group_id': 2, 'name': 'DE', 'workspace_ids': ['workspace-5'], 'added_user_ids': [4], 'removed_user_ids': []}) == (
        'Workspace Group DE saved (workspace IDs workspace-5; users +user ID 4); earlier versions did not record which fields changed.')
    # A user created and deleted: the account as it was (never its password).
    account = {'user_id': 3, 'username': 'ANA', 'first_name': 'Ana', 'last_name': 'García', 'role': 'user-editor', 'active': True,
               'modules_profile': 'Analysts', 'workspace_groups': ['UK'], 'workspaces': []}
    assert describe_app_event('create_user', account) == (
        'User ANA created: name Ana García, role user-editor, active, Modules Profile Analysts, Workspace Groups UK.')
    assert describe_app_event('create_user', 'ANA') == 'User ANA created.'
    assert describe_app_event('delete_user', {**account, 'active': False}) == (
        'User ANA deleted (name Ana García, role user-editor, inactive, Modules Profile Analysts, Workspace Groups UK).')
    assert describe_app_event('operator_mapping_assign', {'assignments': [], 'changes': {'Vodafone SM': [None, 'VF SM']}}) == (
        'Operator Maps: Vodafone SM unassigned → VF SM.')
    assert describe_app_event('operator_mapping_assign', [{'value': '3', 'label': '3 UK'}]) == 'Operator Maps assigned: 3 → 3 UK.'
    assert describe_app_event('login', {'success': False, 'result': 'failed', 'reason': 'invalid_credentials',
                                        'username': 'nobody'}) == 'Failed sign-in as nobody (invalid credentials).'
    # Any other action: its name and every recorded value; plain-text details are already a sentence.
    assert describe_app_event('delete_saved_filter', {'filter_id': 9}) == 'Delete saved filter: filter ID 9.'
    assert describe_app_event('bug_report_managed', {'bug_id': 1, 'changes': {'status': ['new', 'resolved']}}) == (
        'Bug report managed: bug ID 1, status new → resolved.')
    assert describe_app_event('nq_call_options', 'Non-Qualified Calls statuses and teams updated.') == (
        'Non-Qualified Calls statuses and teams updated.')


def test_where_an_event_ran_new_and_old() -> None:
    from src.modules.app_event_details import app_event_origin, app_event_origin_parts

    # The server's own work and transfers by their action; the page recorded with the event otherwise.
    assert app_event_origin('process_dataset', {}, 'module:workspace') == 'server:background'
    assert app_event_origin('scheduled_database_backup_completed', {}) == 'server:scheduler'
    assert app_event_origin('reporting_job_run', {'trigger': 'schedule'}) == 'server:scheduler'
    assert app_event_origin('reporting_job_run', {'trigger': 'manual'}) == 'server:background'
    assert app_event_origin('precompute_dashboard_charts', {}) == 'server:idle'
    assert app_event_origin('recover_interrupted_background_jobs', {}) == 'server:startup'
    assert app_event_origin('incoming_server_transfer_offer_received', {'source': 'Lab'}) == 'remote:Lab'
    assert app_event_origin('access_request', {}) == 'public:access-request'
    assert app_event_origin('export_package_completed', {'executed_by': 'system'}, 'module:admin') == 'server:background'
    assert app_event_origin('update_user', {}, 'module:admin') == 'module:admin'
    # Events of earlier versions: by their action, else the server for system's, else not recorded.
    assert app_event_origin('nq_call_update', {}) == 'module:non-qualified-calls'
    assert app_event_origin('something_else', {}, '', 'system') == 'server:background'
    assert app_event_origin('change_password', {}) == 'module:'
    titles = {'workspace': 'Workspace', 'reporting': 'Reports', 'admin': 'Admin'}
    assert app_event_origin_parts('module:reporting', titles) == {'name': 'Reports', 'tag': 'module', 'group': 3, 'order': 1}
    assert app_event_origin_parts('server:idle', titles) == {'name': 'Server', 'tag': 'Idle task', 'group': 0, 'order': 2}
    assert app_event_origin_parts('remote:Lab', titles)['name'] == 'Remote server'
    assert app_event_origin_parts('module:', titles) == {'name': 'Application', 'tag': 'not recorded', 'group': 3, 'order': 3}
