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


def test_a_reload_keeps_the_favourite_the_page_opens_with():
    import shutil
    import subprocess

    import pytest
    script = (core.PROJECT_ROOT / 'src' / 'web_interface' / 'static' / 'js' / 'network_insights.js').read_text(encoding='utf-8')
    # The favourite just opened, else one with the same choices and filters as the selection the page opens with.
    assert 'const shownFavourite = chosenFavourite || favourites.find(item => sameSelection(item.selection, savedSelection));' in script
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is required for the selection check.')
    start = script.index('  const sameSelection = (favourite, selection) => {')
    function = script[start:script.index('\n  };', start) + len('\n  };')]
    program = function + """
const favourite = %s;
console.log(JSON.stringify([
  sameSelection(favourite, {...favourite, controls: {...favourite.controls, 'ni-overshoot': '5'}, map_group: 'EE'}),
  sameSelection(favourite, {...favourite, filters: {...favourite.filters, 'ni-operators': ['EE', 'VF'], 'ni-cities': []}}),
  sameSelection(favourite, {...favourite, controls: {...favourite.controls, 'ni-coverage-threshold': '-110'}}),
  sameSelection(favourite, {...favourite, filters: {...favourite.filters, 'ni-cities': ['London']}}),
]));
""" % json.dumps(favourites.normalize_selection(SELECTION))
    completed = subprocess.run([node, '-e', program], capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    # A control added since the favourite was saved, the map operator, the order of values and empty filters do not
    # matter; another threshold or filter value does.
    assert json.loads(completed.stdout) == [True, True, False, False]


def test_a_favourite_is_renamed_keeping_its_selection(client):
    login(client)
    first = client.post('/api/network-insights/favourites', json={'name': 'Morning drive', 'selection': SELECTION}).json()['favourite']
    client.post('/api/network-insights/favourites', json={'name': 'Night drive', 'selection': SELECTION})
    # Renaming keeps the selection it saved, whatever the request carries; a name already used, or empty, is refused.
    renamed = client.post(f"/api/network-insights/favourites/{first['id']}/rename",
                          json={'name': 'Evening drive', 'selection': {'controls': {'ni-nr-mode': 'NSA'}}})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()['favourite']['name'] == 'Evening drive' and renamed.json()['favourite']['selection'] == first['selection']
    assert client.post(f"/api/network-insights/favourites/{first['id']}/rename", json={'name': 'night DRIVE'}).status_code == 400
    assert client.post(f"/api/network-insights/favourites/{first['id']}/rename", json={'name': '  '}).status_code == 400
    assert client.post('/api/network-insights/favourites/9999/rename', json={'name': 'Gone'}).status_code == 404
    logged = [json.loads(row['details']) for row in core.repository.list_logs(limit=20) if row['action'] == 'network_insights_favourite_renamed']
    assert logged[0] == {'id': first['id'], 'name': 'Evening drive', 'previous': 'Morning drive'}
    page = client.get('/network-insights').text
    assert 'id="ni-favourite-rename"' in page
