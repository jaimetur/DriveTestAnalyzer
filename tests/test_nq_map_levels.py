"""The Map Levels of Non-Qualified Calls: the levels the maps colour RSRP, RSRQ, SINR and UE Tx Power by."""
from __future__ import annotations

import json

import pytest

import src.DriveTestAnalyzer as core
from src.modules import non_qualified_calls as nq
from src.modules import nq_call_map, nq_map_levels
from tests.test_non_qualified_calls import enable_module, login, workspace_user


def test_the_default_levels_are_those_of_network_insights_and_the_kmz_files():
    levels = nq_map_levels.default_levels()
    assert [(level['label'], level['lower']) for level in levels['rsrp']][-2:] == [('Very poor', -120.0), ('Extremely poor', None)]
    assert [level['lower'] for level in levels['rsrq']] == [-10.0, -14.0, -16.0, -20.0, -24.0, None]
    assert [level['label'] for level in levels['sinr']][-1] == 'Bad'
    assert [level['lower'] for level in levels['tx']] == [24.0, 22.0, 15.0, 5.0, 0.0, -10.0, None]
    assert nq_map_levels.level_text(levels['rsrq'], 1, 'dB') == 'Good (-14 to -10 dB)'
    assert nq_map_levels.level_text(levels['tx'], 6, 'dBm') == '< -10 dBm'


@pytest.mark.parametrize(('levels', 'message'), [
    ([{'label': 'Only', 'colour': '#000000'}], 'from 2 to 10 levels'),
    ([{'label': 'A', 'lower': -10, 'colour': '#000000'}, {'label': 'B', 'lower': -5, 'colour': '#111111'},
      {'label': 'C', 'colour': '#222222'}], 'starts below the one above it'),
    ([{'label': 'A', 'lower': None, 'colour': '#000000'}, {'label': 'B', 'colour': '#111111'}], 'Give the lowest value of level 1'),
    ([{'label': 'A', 'lower': -10, 'colour': 'red'}, {'label': 'B', 'colour': '#111111'}], 'Choose the colour of level 1'),
])
def test_levels_that_cannot_be_saved_tell_why(levels, message):
    with pytest.raises(ValueError, match=message):
        nq_map_levels.normalize_measure('rsrq', levels)


def test_admins_change_the_levels_and_the_maps_take_them(client):
    enable_module()
    login(client)
    payload = client.get('/api/non-qualified-calls/map-levels').json()
    assert [measure['key'] for measure in payload['measures']] == ['rsrp', 'rsrq', 'sinr', 'tx']
    assert payload['levels'] == payload['defaults']
    rsrq = [dict(level) for level in payload['levels']['rsrq']]
    rsrq[1].update(label='Acceptable', lower=-13, colour='#00aa00')
    response = client.put('/api/non-qualified-calls/map-levels', json={'levels': {'rsrq': rsrq}})
    assert response.status_code == 200, response.text
    assert response.json()['levels']['rsrq'][1] == {'label': 'Acceptable', 'lower': -13.0, 'colour': '#00AA00'}
    # The maps (that of a call and NQ Maps) take them; the other measures keep their defaults.
    classes = nq_call_map.sample_classes(core.repository)
    assert classes['rsrq'][1]['label'] == 'Acceptable' and classes['rsrp'] == payload['defaults']['rsrp']
    log = next(row for row in core.repository.list_logs(limit=20) if row['action'] == 'nq_map_levels_saved')
    assert json.loads(log['details'])['changes'][0].startswith('RSRQ: Excellent (≥ -10 dB) #2E8B57, Acceptable (-13 to -10 dB) #00AA00')
    # A level that cannot be saved tells why.
    response = client.put('/api/non-qualified-calls/map-levels', json={'levels': {'sinr': [{'label': 'A', 'colour': '#000000'}]}})
    assert response.status_code == 400 and 'SINR needs from 2 to 10 levels' in response.json()['detail']
    # Only the measures that differ from their defaults are stored: one put back follows its defaults.
    response = client.put('/api/non-qualified-calls/map-levels', json={'levels': {'rsrq': payload['defaults']['rsrq']}})
    assert response.status_code == 200 and json.loads(core.repository.get_workspace_state(nq_map_levels.STATE_KEY)) == {}
    # Every user reads them; only admins and super-admins change them.
    workspace_user('analyst', 'user-editor')
    login(client, 'analyst', 'analyst123')
    assert client.get('/api/non-qualified-calls/map-levels').status_code == 200
    assert client.put('/api/non-qualified-calls/map-levels', json={'levels': {'rsrq': rsrq}}).status_code == 403


def test_the_levels_travel_with_the_nq_calls_configuration(client):
    enable_module()
    login(client)
    tx = [dict(level, label=f'Level {index + 1}') for index, level in enumerate(nq_map_levels.default_levels()['tx'])]
    nq_map_levels.save_levels(core.repository, {'tx': tx})
    document = json.loads(nq.export_configuration_document(core.repository))
    assert document['map_levels']['tx'][0]['label'] == 'Level 1'
    # The preview of an import tells the levels that change, and the import takes them, measure by measure: one that is not
    # valid leaves that of the workspace.
    current = json.loads(nq.export_configuration_document(core.repository))
    defaults = nq_map_levels.default_levels()
    changed = dict(document, map_levels={'tx': defaults['tx'], 'sinr': [{'label': 'Broken', 'colour': '#000000'}]})
    lines = nq.configuration_changes(current, nq.predicted_configuration(current, changed))
    assert [line for line in lines if line.startswith('Map Levels')] == ['Map Levels · UE Tx Power: ≥ 24 dBm #8B0000, 22 to 24 dBm #FF0000, '
                                                                          '15 to 22 dBm #FF8C00, 5 to 15 dBm #FFE600, 0 to 5 dBm #90EE64, '
                                                                          '-10 to 0 dBm #00BFFF, < -10 dBm #0000FF']
    nq.import_configuration_document(core.repository, json.dumps(changed))
    assert nq_map_levels.load_levels(core.repository) == defaults
    # A package exported before the Map Levels leaves those of the workspace.
    nq_map_levels.save_levels(core.repository, {'tx': tx})
    nq.import_configuration_document(core.repository, json.dumps({key: value for key, value in document.items() if key != 'map_levels'}))
    assert nq_map_levels.load_levels(core.repository)['tx'] == tx
