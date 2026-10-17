import json
import zipfile
from io import BytesIO

import src.DriveTestAnalyzer as core
from src.modules import network_insights_favourites as favourites

SELECTION = {
    'controls': {'ni-nr-mode': 'SA', 'ni-technology': 'nr', 'ni-group': ['operator', 'campaign'], 'ni-coverage-threshold': '-105',
                 'not-a-control': 'dropped'},
    'filters': {'ni-campaigns': ['@latest-campaign'], 'ni-operators': ['VF', 'EE'], 'ni-cities': 'not a list'},
    'map_group': 'VF',
}


def login(client, username='super', password='super123'):
    client.cookies.clear()
    response = client.post('/login', data={'username': username, 'password': password}, follow_redirects=False)
    assert response.status_code == 303


def test_selections_keep_the_controls_and_filters_of_the_page():
    selection = favourites.normalize_selection(SELECTION)
    assert selection == {
        'controls': {'ni-nr-mode': 'SA', 'ni-technology': 'nr', 'ni-group': ['operator', 'campaign'], 'ni-coverage-threshold': '-105'},
        'filters': {'ni-campaigns': ['@latest-campaign'], 'ni-operators': ['VF', 'EE']},
        'map_group': 'VF',
    }


def test_favourites_are_saved_opened_and_deleted_with_app_events(client):
    login(client)
    created = client.post('/api/network-insights/favourites', json={'name': 'SA NR latest', 'selection': SELECTION})
    assert created.status_code == 200, created.text
    favourite = created.json()['favourite']
    assert favourite['selection']['controls']['ni-nr-mode'] == 'SA'
    assert client.post('/api/network-insights/favourites', json={'name': 'sa nr LATEST', 'selection': SELECTION}).status_code == 400
    renamed = client.put(f"/api/network-insights/favourites/{favourite['id']}", json={'name': 'SA NR', 'selection': SELECTION})
    assert renamed.status_code == 200 and renamed.json()['favourite']['name'] == 'SA NR'
    assert client.post(f"/api/network-insights/favourites/{favourite['id']}/open").json()['favourite']['name'] == 'SA NR'
    # The page lists them for the selector.
    page = client.get('/network-insights')
    assert page.status_code == 200 and 'SA NR' in page.text and 'ni-favourite' in page.text
    assert client.delete(f"/api/network-insights/favourites/{favourite['id']}").status_code == 200
    assert client.get('/api/network-insights/favourites').json()['favourites'] == []
    actions = [row['action'] for row in core.repository.list_logs(limit=20)]
    assert {'network_insights_favourite_saved', 'network_insights_favourite_opened', 'network_insights_favourite_deleted'} <= set(actions)


def test_favourites_travel_with_their_element_and_full_workspaces(client):
    login(client)
    favourites.save_favourite(core.repository, None, 'Weekly', SELECTION, 'super')
    document = json.loads(favourites.export_document(core.repository))
    assert document['format'] == favourites.FAVOURITES_FORMAT and [item['name'] for item in document['favourites']] == ['Weekly']
    # Imports add new favourites and replace those with the same name.
    document['favourites'].append({'name': 'Monthly', 'selection': SELECTION})
    document['favourites'][0]['selection'] = {'controls': {'ni-nr-mode': 'NSA'}}
    assert core._restore_workspace_network_insights_favourites(core.active_workspace, json.dumps(document).encode(), 'super') == 2
    stored = {item['name']: item for item in favourites.list_favourites(core.repository)}
    assert set(stored) == {'Weekly', 'Monthly'} and stored['Weekly']['selection']['controls'] == {'ni-nr-mode': 'NSA'}
    # The element and the workspace packages carry them.
    assert 'network-insights-favourites' in core.WORKSPACE_ELEMENT_EXPORT_TARGETS
    assert core.archive_workspace_components_for_target('network-insights-favourites') == ['network_insights_favourites']
    output = BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        core._archive_workspace_network_insights_favourites(archive, core.active_workspace, 'workspaces/Default')
    names = zipfile.ZipFile(BytesIO(output.getvalue())).namelist()
    assert names == [f'workspaces/Default/{core.NI_FAVOURITES_ARCHIVE_NAME}']
    page = client.get('/admin')
    assert 'Network Insights Favourites (from active workspace)' in page.text
