"""The Calculation panel keeps every context filter, each user their own (ticket #114)."""
from __future__ import annotations

import json

from src.modules.scoring.scoring_selection import load_scoring_selection, save_scoring_selection
from tests.scoring.test_scoring_api import scoring_api  # noqa: F401


def _selection(scoring_api, **filters):
    return {
        'dataset_ids': scoring_api['complete_dataset_ids'], 'aggregation_levels': ['Operator', 'Vendor'],
        'nr_mode': 'NSA', 'baseline_operator': 'EE', 'context_filters': filters,
    }


def test_the_panel_keeps_operator_vendor_vendor_operator_and_cluster(client, scoring_api):
    selection = _selection(scoring_api, Region=['North'], Cluster=['North East'], Operator_Vendor=['VF_Ericsson'],
                           Vendor_Operator=['Ericsson_VF'], Vendor=['Ericsson'])
    saved = client.put('/api/scoring/selection', json={'selection': selection})
    assert saved.status_code == 200, saved.text
    assert not saved.json()['warnings']
    filters = client.get('/api/scoring/selection').json()['selection']['context_filters']
    assert filters['Cluster'] == ['North East']
    assert filters['Operator_Vendor'] == ['VF_Ericsson']
    assert filters['Vendor_Operator'] == ['Ericsson_VF']
    assert filters['Vendor'] == ['Ericsson']
    # Unused, they are left out as before.
    client.put('/api/scoring/selection', json={'selection': _selection(scoring_api, Region=['North'])})
    filters = client.get('/api/scoring/selection').json()['selection']['context_filters']
    assert not {'Cluster', 'Operator_Vendor', 'Vendor_Operator'} & set(filters)


def test_each_user_keeps_their_own_panel_selection(scoring_api):
    repository = scoring_api['repository']
    first, _ = load_scoring_selection(repository)
    north = {**first, 'context_filters': {**first['context_filters'], 'Region': ['North']}}
    south = {**first, 'context_filters': {**first['context_filters'], 'Region': ['South']}}
    assert save_scoring_selection(repository, north, username='USERA')
    assert save_scoring_selection(repository, south, username='userb')
    assert load_scoring_selection(repository, 'usera')[0]['context_filters']['Region'] == ['North']
    assert load_scoring_selection(repository, 'USERB')[0]['context_filters']['Region'] == ['South']
    # A user without a selection of their own starts from the latest one saved in the workspace.
    assert load_scoring_selection(repository, 'userc')[0]['context_filters']['Region'] == ['South']
    # Each tab of a user still rejects its own delayed writes.
    assert save_scoring_selection(repository, south, client_id='tab', client_revision=2, username='usera')
    assert not save_scoring_selection(repository, north, client_id='tab', client_revision=1, username='usera')
    assert load_scoring_selection(repository, 'usera')[0]['context_filters']['Region'] == ['South']


def test_the_calculation_event_records_its_filters(client, scoring_api):
    repository = scoring_api['repository']
    response = client.post('/api/scoring/saved-filters', json={
        **_selection(scoring_api, Region=['North'], Operator_Vendor=['VF_Ericsson'], Vendor=[]),
    })
    assert response.status_code == 200, response.text
    [event] = [row for row in repository.list_logs(limit=20) if row['action'] == 'scoring_calculation_requested']
    details = json.loads(event['details'])
    assert details['context_filters'] == {'Region': ['North'], 'Operator_Vendor': ['VF_Ericsson']}
    assert details['aggregation_levels'] == ['Operator', 'Vendor']
    assert details['baseline_operator'] == 'EE'
    assert details['dataset_ids']
