"""Final CDRs that look local: the suggestion of a Flex campaign and its Mark as Flex and Not local answers."""

from pathlib import Path

import pandas as pd

import src.DriveTestAnalyzer as core
from src.modules.cdr.cdr_auto_selection import LATEST_CAMPAIGN, is_flex_cdr, resolve_cdrs, cdr_campaigns
from src.modules.cdr.flex_detection import flex_label, flex_suggestions
from src.modules.core.repository import local_now_iso
from src.modules.mapping.campaign_maps import load_campaign_map


def login(client, username='super', password='super123'):
    client.cookies.clear()
    response = client.post('/login', data={'username': username, 'password': password}, follow_redirects=False)
    assert response.status_code == 303


def add_cdr(tmp_path: Path, name: str, rows: pd.DataFrame, stage: str) -> int:
    repository = core.repository
    source = tmp_path / name
    source.write_text('test source', encoding='utf-8')
    dataset_id, _created = repository.add_dataset(name, str(source), 'super')
    repository.replace_dataset_rows(dataset_id, rows)
    repository.update_dataset_profile(
        dataset_id, status='ready', progress=100, dataset_kind='voice', nr_mode='NSA', cdr_stage=stage,
        row_count=len(rows), column_count=len(rows.columns), processed_at=local_now_iso(),
    )
    repository.copy_dataset_rows_to_reporting(dataset_id, 'voice')
    return dataset_id


def calls(points: list[tuple[float, float, str]], campaign: str, prefix: str, day: str = '2026-09-10') -> pd.DataFrame:
    return pd.DataFrame({
        'JOIN_ID': [f'{prefix}{position}' for position in range(len(points))], 'Operator': ['EE'] * len(points),
        'Campaign': [campaign] * len(points), 'Call_Status': ['Completed'] * len(points),
        'Call_Start_Time': [f'{day} 10:00:00'] * len(points),
        'Call_Start_Latitude_A': [lat for lat, _lon, _city in points],
        'Call_Start_Longitude_A': [lon for _lat, lon, _city in points],
        'City': [city for _lat, _lon, city in points],
    })


# The whole country: points a cell apart from Cornwall to Kent and up to Yorkshire, in many cities.
COUNTRY = [(50.1 + 0.3 * row, -5.4 + 0.35 * column, ['Bristol', 'London', 'Leeds', 'Exeter'][(row + column) % 4])
           for row in range(10) for column in range(18)]
LONDON = [(51.45 + 0.02 * step, -0.2 + 0.03 * step, 'London') for step in range(8)]


def test_a_final_cdr_of_a_small_area_is_suggested_as_flex_and_daily_cdrs_never(client, tmp_path):
    login(client)
    country = add_cdr(tmp_path, 'UK_Q3_Voice_Final.xlsx', calls(COUNTRY, 'UK_Q3_2026', 'c'), 'final')
    local = add_cdr(tmp_path, 'UK_Voice_AdHoc_Final.xlsx', calls(LONDON, 'UK_AdHoc_Q4_2026', 'l'), 'final')
    # A Daily CDR holds the calls measured so far: its stage decides, whatever it covers or its name says.
    daily = add_cdr(tmp_path, 'UK_London_Voice_Daily_20261005.xlsx', calls(LONDON, 'UK_Q4_2026', 'd', '2026-10-05'), 'daily')

    suggestions = flex_suggestions(core.repository)
    assert set(suggestions) == {local}
    assert suggestions[local]['reason'] == 'coverage' and suggestions[local]['area'] == 'London'
    assert suggestions[local]['label'] == '26-Q4-London-Flex'
    assert country not in suggestions and daily not in suggestions

    # The Workspace card shows it, with its two answers.
    page = client.get('/workspace').text
    assert 'data-flex-suggestion' in page and '26-Q4-London-Flex' in page and 'Mark as Flex' in page

    marked = client.post(f'/workspace/datasets/{local}/flex', json={'action': 'mark', 'label': '26-Q4-London-Flex'})
    assert marked.status_code == 200 and '26-Q4-London-Flex' in marked.json()['exceptions']
    exceptions = {item['label']: item['sources'] for item in load_campaign_map(core.repository)['exceptions']}
    assert exceptions['26-Q4-London-Flex'] == ['UK_AdHoc_Q4_2026']
    assert is_flex_cdr(cdr_campaigns(core.repository, [local])[local])
    assert flex_suggestions(core.repository) == {}
    # Latest campaign leaves the Flex campaign out: it is used only when checked by hand.
    assert resolve_cdrs(core.repository, 'NSA', [LATEST_CAMPAIGN], ('voice',))['voice'] == [daily]
    events = [row for row in core.repository.list_logs(limit=50) if row['action'] == 'update_dataset_flex']
    assert events and '"action": "mark"' in events[0]['details']


def test_a_file_name_with_an_area_suggests_flex_and_not_local_hides_it(client, tmp_path):
    login(client)
    add_cdr(tmp_path, 'UK_Q3_Voice_Final.xlsx', calls(COUNTRY, 'UK_Q3_2026', 'c'), 'final')
    # Half the country, from Cornwall to the Midlands: not local by its coverage, but its name says Bristol.
    half = [point for point in COUNTRY if point[1] < -2.2]
    named = add_cdr(tmp_path, 'UK_Q4_Bristol_Voice_Final.xlsx', calls(half, 'UK_Bristol_Q4_2026', 'b'), 'final')
    suggestion = flex_suggestions(core.repository)[named]
    assert suggestion['reason'] == 'name' and suggestion['area'] == 'Bristol'
    assert suggestion['label'] == '26-Q4-Bristol-Flex'

    assert client.post(f'/workspace/datasets/{named}/flex', json={'action': 'dismiss'}).status_code == 200
    assert flex_suggestions(core.repository) == {}
    assert client.post(f'/workspace/datasets/{named}/flex', json={'action': 'other'}).status_code == 422
    assert client.post(f'/workspace/datasets/{named}/flex', json={'action': 'mark', 'label': '26-Q4-Bristol'}).status_code == 422


def test_flex_label_keeps_the_name_of_the_campaign():
    assert flex_label(['UK_Q4_2026'], 'South West') == '26-Q4-South-West-Flex'
    assert flex_label([], '') == 'Local-Flex'
