"""Values detected in the CDRs: their Operator, Vendor and Campaign labels and the warning while some are unassigned."""
import json

import pandas as pd
import pytest

import src.DriveTestAnalyzer as core
from src.modules.mapping_assignments import (assignment_effects, assignment_rows, comment_changes, detected_values,
                                            load_name_comments, unassigned_values, value_campaigns)
from src.modules.mapping_renames import count_saved_filters
from tests.test_non_qualified_calls import add_cdr, login, voice_rows, workspace_user


def test_detected_values_leave_operator_only_identities_out_of_the_vendors():
    catalogues = {
        1: {'operators': ['Vodafone SA', 'EE'], 'vendors_only': ['Ericsson', 'Vodafone SA - All', 'EE'], 'campaigns': ['UK_Q1_2026']},
        2: {'operators': ['vodafone sa'], 'vendors_only': ['Nokia'], 'campaigns': ['Xmas drive']},
    }
    detected = detected_values(catalogues, {1: 'CDR one.xlsx', 2: 'CDR two.xlsx'})
    assert detected['operator'] == {'Vodafone SA': ['CDR one.xlsx', 'CDR two.xlsx'], 'EE': ['CDR one.xlsx']}
    assert detected['vendor'] == {'Ericsson': ['CDR one.xlsx'], 'Nokia': ['CDR two.xlsx']}
    assert set(detected['campaign']) == {'UK_Q1_2026', 'Xmas drive'}


def test_rows_tell_unassigned_and_merged_values():
    detected = {'Vodafone SA': ['a'], 'Vodafone VoNR': ['a'], 'Vodafone UK': ['b'], 'Mystery': ['b']}
    mappings = {'vodafone sa': 'VF_SA', 'vodafone vonr': 'VF_SA', 'vodafone uk': 'VF', 'vf': 'VF', 'vf_sa': 'VF_SA'}
    rows = {row['value']: row for row in assignment_rows('operator', detected, mappings)}
    assert rows['Mystery'] == {'value': 'Mystery', 'cdrs': ['b'], 'label': 'Mystery', 'assigned': False,
                               'canonical': False, 'merged_with': []}
    assert rows['Vodafone SA']['merged_with'] == ['Vodafone VoNR'] and rows['Vodafone UK']['merged_with'] == []
    assert list(rows)[0] == 'Mystery'
    campaigns = assignment_rows('campaign', {'UK_Q2_2026': [], 'Xmas drive': [], 'Pilot run': []}, {},
                                {'format': '{year}-Q{quarter}', 'exceptions': [{'label': 'Pilot', 'sources': ['Pilot run']}]})
    assert unassigned_values({'operator': list(rows.values()), 'campaign': campaigns}) == {
        'operator': ['Mystery'], 'campaign': ['Xmas drive']}


def test_effects_list_merges_moved_values_and_labels_with_underscores():
    mappings = {'vodafone sa': 'VF_SA', 'vf_sa': 'VF_SA', 'vodafone vonr': 'VF_SA', 'vf': 'VF'}
    detected = ['Vodafone SA', 'Vodafone VoNR', 'Vodafone UK']
    effects = assignment_effects('operator', [('Vodafone VoNR', 'VF_VoNR'), ('Vodafone UK', 'vf_sa')], detected,
                                 mappings, ['VF_SA', 'VF'], saved_filters=lambda label: {'VF_SA': 2}.get(label, 0))
    assert effects['merges'] == [{'label': 'VF_SA', 'values': ['Vodafone SA', 'Vodafone UK']}]
    assert effects['moved'] == [{'value': 'Vodafone VoNR', 'from': 'VF_SA', 'to': 'VF_VoNR', 'filters': 2}]
    assert effects['underscores'] == ['VF_VoNR']
    # Renaming a group keeps its values: nothing merges or moves.
    renamed = assignment_effects('operator', [('VF-SA', 'VF-SA'), ('Vodafone SA', 'VF-SA'), ('Vodafone VoNR', 'VF-SA')],
                                 detected, mappings, ['VF_SA', 'VF'], rename=('VF_SA', 'VF-SA'))
    assert renamed == {'merges': [], 'moved': [], 'underscores': []}
    # Taking a source label out of a group leaves the value unassigned.
    removed = assignment_effects('operator', [('VF_SA', 'VF_SA'), ('Vodafone SA', 'VF_SA'), ('Vodafone VoNR', None)],
                                 detected, mappings, ['VF_SA', 'VF'])
    assert removed['moved'] == [{'value': 'Vodafone VoNR', 'from': 'VF_SA', 'to': None, 'filters': 0}]



def test_names_of_a_label_only_merge_where_they_coincide_in_a_campaign_and_nr_mode():
    campaign_map = {'format': '{yy}-Q{quarter}{-mode}', 'mode_order': ['', 'NSA', 'SA'], 'modes_in_label': ['SA'], 'exceptions': []}
    catalogues = {
        1: {'operators': ['Vodafone UK', 'EE'], 'campaigns': ['UK_Q3_NSA_2026']},
        2: {'operators': ['Vodafone SM', 'EE'], 'campaigns': ['UK_Q3_SA_2026']},
        3: {'operators': ['Vodafone UK', 'Vodafone SA', 'EE'], 'campaigns': ['UK_Q2_2026']},
        4: {'operators': ['Vodafone UK', 'Vodafone VoNR'], 'campaigns': ['UK_Q2_SA_2026']},
    }
    campaigns = value_campaigns(catalogues, {1: 'NSA', 2: 'SA', 3: 'NSA', 4: 'SA'}, campaign_map)
    # The campaigns as the Campaign Maps show them, in their order, with the NR Mode of their CDR.
    assert campaigns['vodafone uk'] == ['26-Q2 (NSA)', '26-Q2-SA (SA)', '26-Q3 (NSA)']
    assert campaigns['vodafone sm'] == ['26-Q3-SA (SA)']
    detected = {name: ['CDR'] for name in ('Vodafone UK', 'Vodafone SM', 'Vodafone SA', 'Vodafone VoNR', 'EE')}
    mappings = {'vodafone uk': 'VF', 'vodafone sm': 'VF', 'vodafone sa': 'VF', 'vodafone vonr': 'VF VoNR', 'vf': 'VF',
                'vf vonr': 'VF VoNR'}
    rows = {row['value']: row for row in assignment_rows('operator', detected, mappings, campaigns=campaigns)}
    # Vodafone UK and Vodafone SA are in the same NSA CDR of 26-Q2: added up there.
    assert rows['Vodafone UK']['merged_with'] == ['Vodafone SA'] and rows['Vodafone UK']['merged_in'] == ['26-Q2 (NSA)']
    assert rows['Vodafone SA']['merged_with'] == ['Vodafone UK'] and rows['Vodafone SA']['shares_label_with'] == ['Vodafone SM']
    # Vodafone SM is never in a campaign and NR Mode of the others: it only shares the label.
    assert rows['Vodafone SM']['merged_with'] == [] and rows['Vodafone SM']['shares_label_with'] == ['Vodafone SA', 'Vodafone UK']
    assert rows['Vodafone SM']['campaigns'] == ['26-Q3-SA (SA)']
    # Without campaigns (the Vendors) every name of a label merges, as before.
    assert assignment_rows('operator', detected, mappings)[0].get('merged_in') is None

    # Saving: a name that never coincides with the others of its new label merges nothing.
    only_uk = {'vodafone uk': 'VF', 'vf': 'VF'}
    effects = assignment_effects('operator', [('Vodafone SM', 'VF')], list(detected), only_uk, ['VF'], campaigns=campaigns)
    assert effects['merges'] == []
    effects = assignment_effects('operator', [('Vodafone SA', 'VF'), ('Vodafone VoNR', 'VF')], list(detected),
                                 {**only_uk, 'vodafone sm': 'VF'}, ['VF'], campaigns=campaigns)
    assert effects['merges'] == [{'label': 'VF', 'values': ['Vodafone SA', 'Vodafone UK', 'Vodafone VoNR'],
                                  'campaigns': ['26-Q2 (NSA)', '26-Q2-SA (SA)']}]
    # The NSA and SA CDRs of one campaign never coincide.
    split = value_campaigns({1: {'operators': ['A'], 'campaigns': ['UK_Q2_2026']},
                             2: {'operators': ['B'], 'campaigns': ['UK_Q2_2026']}}, {1: 'NSA', 2: 'SA'}, campaign_map)
    assert assignment_effects('operator', [('A', 'X'), ('B', 'X')], ['A', 'B'], {}, [], campaigns=split)['merges'] == []

def test_repository_assigns_values_to_existing_and_new_labels(client):
    repository = core.repository
    repository.replace_operator_mapping_group(None, 'VF_SA', ['Vodafone Lab SA', 'Vodafone Lab VoNR'])
    assert repository.assign_chart_mapping_sources('operator', [('Vodafone Lab VoNR', 'VF_LabVoNR'), ('Mystery', 'ee'),
                                                                ('Vodafone Lab SA', 'VF_SA')]) == 2
    mappings = repository.list_operator_mappings()
    assert mappings['vodafone lab vonr'] == 'VF_LabVoNR' and mappings['vf_labvonr'] == 'VF_LabVoNR'
    assert mappings['mystery'] == 'EE' and mappings['vodafone lab sa'] == 'VF_SA'
    # A new label is a new group at the end of the table.
    assert repository.list_operator_mapping_groups()[-1]['canonical'] == 'VF_LabVoNR'
    with pytest.raises(ValueError, match='also one of the Operator labels'):
        repository.assign_chart_mapping_sources('operator', [('VF_SA', 'VF')])
    with pytest.raises(ValueError, match='name of the CDRs shown as VF'):
        repository.assign_chart_mapping_sources('operator', [('Vodafone Lab SA', 'Vodafone UK')])
    # A refused assignment changes nothing.
    assert repository.list_operator_mappings()['vodafone lab sa'] == 'VF_SA'


def _cdr_with_unassigned_values(tmp_path):
    rows = voice_rows()
    rows['Operator'] = ['Vodafone Lab SA', 'Vodafone Lab VoNR', 'EE']
    rows['Vendor'] = ['Ericsson', 'Ciena', 'Ericsson']
    rows['Campaign'] = ['UK_Q1_2026', 'Xmas drive', 'UK_Q1_2026']
    dataset_id = add_cdr(tmp_path, 'NetCheck_UK_CDR_Voice_2026_Q1.xlsx', 'voice', rows)
    core.cache_cdr_catalogue(dataset_id, rows)
    return dataset_id


def test_unassigned_values_show_a_card_until_they_are_assigned(client, tmp_path):
    _cdr_with_unassigned_values(tmp_path)
    login(client)
    page = client.get('/workspace-config').text
    assert 'data-unassigned-values-card data-can-edit="1"' in page
    unassigned = json.loads(page.split('id="unassigned-mapping-values" type="application/json">')[1].split('</script>')[0])
    assert unassigned == {'operator': ['Vodafone Lab SA', 'Vodafone Lab VoNR'], 'vendor': ['Ciena'], 'campaign': ['Xmas drive']}
    assert 'id="operator-assignments"' in page and 'id="vendor-assignments"' in page
    assert client.get('/api/mapping-assignments/unassigned').json() == {'unassigned': unassigned, 'can_edit': True}

    preview = client.post('/api/workspace-config/operator-mappings/preview', json={'assignments': [
        {'value': 'Vodafone Lab SA', 'label': 'VF_SA'}, {'value': 'Vodafone Lab VoNR', 'label': 'VF_SA'}]}).json()
    # Both names are in the same NSA CDR, with both campaigns.
    assert preview['merges'] == [{'label': 'VF_SA', 'values': ['Vodafone Lab SA', 'Vodafone Lab VoNR'],
                                  'campaigns': ['Xmas drive (NSA)', '26-Q1 (NSA)']}]
    assert preview['underscores'] == ['VF_SA']

    response = client.post('/workspace-config/operator-mappings/assign', data={
        'source': ['Vodafone Lab SA', 'Vodafone Lab VoNR', 'EE'], 'label': ['VF_SA', 'VF_LabVoNR', 'EE']}, follow_redirects=False)
    assert response.status_code == 303 and '2+names+assigned' in response.headers['location']
    client.post('/workspace-config/vendor-mappings/assign', data={'source': ['Ciena'], 'label': ['Ciena']})
    client.put('/api/workspace-config/campaign-map', json={'campaign_map': {
        'format': '{year}-Q{quarter}{-mode}', 'exceptions': [{'label': 'Xmas', 'sources': ['Xmas drive']}]}})
    assert client.get('/api/mapping-assignments/unassigned').json()['unassigned'] == {}
    page = client.get('/workspace-config').text
    assert 'data-unassigned-values-card data-can-edit="1" role="alert" aria-label="Unassigned values in the CDRs" hidden' in page
    # The names of the CDRs stay listed with their label, chosen in a list of the labels.
    assert 'id="operator-assignments"' in page and 'Choose a label…' not in page
    assert '<option value="VF_LabVoNR" data-role="" selected>VF_LabVoNR</option>' in page
    assert '"EE": ["NetCheck_UK_CDR_Voice_2026_Q1.xlsx"]' in page
    # Every module shows the values with their labels: the two Vodafone Operators stay apart.
    settings = core.repository.chart_mapping_settings()
    assert settings['operator_mappings']['vodafone lab sa'] == 'VF_SA' and settings['operator_mappings']['vodafone lab vonr'] == 'VF_LabVoNR'



def test_comments_of_the_operator_names_are_saved_logged_and_exported(client, tmp_path):
    _cdr_with_unassigned_values(tmp_path)
    login(client)
    response = client.post('/workspace-config/operator-mappings/assign', data={
        'source': ['Vodafone Lab SA', 'Vodafone Lab VoNR', 'EE'], 'label': ['', '', ''],
        'comment': ['  SA terminal of the NSA drive ', '', '']}, follow_redirects=False)
    assert response.status_code == 303 and 'Comments+of+1+name+saved.' in response.headers['location']
    repository = core.repository
    assert load_name_comments(repository) == {'Vodafone Lab SA': 'SA terminal of the NSA drive'}
    page = client.get('/workspace-config').text
    assert '<th class="mapping-comment-column">Comments' in page
    assert 'data-value="Vodafone Lab SA" aria-label="Comments of Vodafone Lab SA" placeholder="For example: SA terminal of the NSA drive">SA terminal of the NSA drive</textarea>' in page
    event = next(row for row in repository.list_logs() if row['action'] == 'operator_name_comments')
    assert json.loads(event['details']) == {'changes': {'Vodafone Lab SA': ['', 'SA terminal of the NSA drive']}}
    # The comments travel with the Operator Maps; packages without them keep the workspace's own.
    document = json.loads(core._mappings_reference_data_archive_payload(core.active_workspace))
    assert document['operator_name_comments'] == {'Vodafone Lab SA': 'SA terminal of the NSA drive'}
    core._restore_workspace_mappings_reference_data(core.active_workspace, json.dumps(
        {**document, 'operator_name_comments': {'EE': 'Benchmark'}}).encode())
    assert load_name_comments(repository) == {'EE': 'Benchmark'}
    core._restore_workspace_mappings_reference_data(core.active_workspace, json.dumps(
        {key: value for key, value in document.items() if key != 'operator_name_comments'}).encode())
    assert load_name_comments(repository) == {'EE': 'Benchmark'}
    # A blank comment removes it; the comments of names not in the form are kept.
    assert comment_changes({'EE': 'Benchmark', 'Gone': 'Old CDRs'}, [('ee', ' '), ('Three', 'New')]) == (
        {'Gone': 'Old CDRs', 'Three': 'New'}, {'EE': ['Benchmark', ''], 'Three': ['', 'New']})
    # The Vendors have no comments.
    assert 'mapping-name-comment' not in page.split('id="vendor-assignments"')[1].split('</details>')[0]

def test_viewers_see_the_card_without_the_assignment_links(client, tmp_path):
    _cdr_with_unassigned_values(tmp_path)
    workspace_user('viewer', 'user-viewer')
    login(client, 'viewer', 'viewer123')
    page = client.get('/workspace').text
    assert 'data-unassigned-values-card data-can-edit="0"' in page
    assert client.get('/api/mapping-assignments/unassigned').json()['can_edit'] is False
    assert client.post('/workspace-config/operator-mappings/assign',
                       data={'source': ['Vodafone Lab SA'], 'label': ['VF_SA']}).status_code == 403
    assert client.post('/api/workspace-config/operator-mappings/preview', json={'assignments': []}).status_code == 403


def test_moving_a_value_counts_the_saved_filters_of_its_label_without_changing_them(client, tmp_path):
    _cdr_with_unassigned_values(tmp_path)
    core.repository.replace_operator_mapping_group(None, 'VF_SA', ['Vodafone Lab SA', 'Vodafone Lab VoNR'])
    stored = json.dumps({'operator': ['VF_SA']})
    core.repository.set_workspace_state('nq_calls_filters', stored)
    assert count_saved_filters(core.repository, 'operator', 'VF_SA', core.repository.chart_mapping_settings()) == 1
    login(client)
    preview = client.post('/api/workspace-config/operator-mappings/preview', json={'assignments': [
        {'value': 'Vodafone Lab VoNR', 'label': 'VF_LabVoNR'}]}).json()
    assert preview['moved'] == [{'value': 'Vodafone Lab VoNR', 'from': 'VF_SA', 'to': 'VF_LabVoNR', 'filters': 1}]
    assert core.repository.get_workspace_state('nq_calls_filters') == stored
    # The campaign preview tells the unassigned campaigns.
    campaigns = client.post('/api/workspace-config/campaign-map/preview', json={'campaign_map': None}).json()['preview']
    assert {item['campaign']: item['assigned'] for item in campaigns} == {'UK_Q1_2026': True, 'Xmas drive': False}
