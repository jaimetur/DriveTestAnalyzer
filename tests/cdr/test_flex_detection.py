"""CDRs that look local: the suggestion of a Flex campaign, its Mark as Flex and Not local answers, Mark as Flex on any
CDR and the Flex choice of the upload review."""

import time
from io import BytesIO
from pathlib import Path

import pandas as pd

import src.DriveTestAnalyzer as core
from src.modules.cdr.cdr_auto_selection import LATEST_CAMPAIGN, is_flex_cdr, resolve_cdrs, cdr_campaigns
from src.modules.cdr.flex_detection import apply_import_choices, flex_label, flex_suggestions, set_import_choices
from src.modules.core.repository import local_now_iso
from src.modules.mapping.campaign_maps import load_campaign_map


def login(client, username='super', password='super123'):
    client.cookies.clear()
    response = client.post('/login', data={'username': username, 'password': password}, follow_redirects=False)
    assert response.status_code == 303


def add_cdr(tmp_path: Path, name: str, rows: pd.DataFrame, stage: str, mode: str = 'NSA') -> int:
    repository = core.repository
    source = tmp_path / name
    source.write_text('test source', encoding='utf-8')
    dataset_id, _created = repository.add_dataset(name, str(source), 'super')
    repository.replace_dataset_rows(dataset_id, rows)
    repository.update_dataset_profile(
        dataset_id, status='ready', progress=100, dataset_kind='voice', nr_mode=mode, cdr_stage=stage,
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


def test_a_final_cdr_of_a_small_area_is_suggested_as_flex_and_daily_cdrs_only_by_name(client, tmp_path):
    login(client)
    country = add_cdr(tmp_path, 'UK_Q3_Voice_Final.xlsx', calls(COUNTRY, 'UK_Q3_2026', 'c'), 'final')
    local = add_cdr(tmp_path, 'UK_Voice_AdHoc_Final.xlsx', calls(LONDON, 'UK_AdHoc_Q4_2026', 'l'), 'final')
    # A Daily CDR holds the calls measured so far: its coverage says nothing, only an area in its name.
    daily = add_cdr(tmp_path, 'UK_Voice_Daily_20261005.xlsx', calls(LONDON, 'UK_Q4_2026', 'd', '2026-10-05'), 'daily')
    named_daily = add_cdr(tmp_path, '20261112 Daily Voice SA CDR UK London 20261024-20261111.xlsx',
                          calls(LONDON, 'UK_London_SA_2026', 'n', '2026-10-25'), 'daily', 'SA')

    suggestions = flex_suggestions(core.repository)
    assert set(suggestions) == {local, named_daily}
    assert suggestions[local]['reason'] == 'coverage' and suggestions[local]['area'] == 'London'
    assert suggestions[local]['label'] == '26-Q4-London-Flex'
    assert country not in suggestions and daily not in suggestions
    # Its Campaign values have no quarter: the dates of its file name give it, and its NR Mode is shown as the Campaign
    # Maps format does (both modes by default).
    assert suggestions[named_daily]['reason'] == 'name' and suggestions[named_daily]['area'] == 'London'
    assert suggestions[named_daily]['label'] == '26-Q4-SA-London-Flex'

    # The Workspace card shows it, with its two answers.
    page = client.get('/workspace').text
    assert 'data-flex-suggestion' in page and '26-Q4-London-Flex' in page and 'Mark as Flex' in page

    marked = client.post(f'/workspace/datasets/{local}/flex', json={'action': 'mark', 'label': '26-Q4-London-Flex'})
    assert marked.status_code == 200 and '26-Q4-London-Flex' in marked.json()['exceptions']
    exceptions = {item['label']: item['sources'] for item in load_campaign_map(core.repository)['exceptions']}
    assert exceptions['26-Q4-London-Flex'] == ['UK_AdHoc_Q4_2026']
    assert is_flex_cdr(cdr_campaigns(core.repository, [local])[local])
    assert set(flex_suggestions(core.repository)) == {named_daily}
    # Latest campaign leaves the Flex campaign out, and the campaign in progress (Daily CDRs only): they are used only
    # when checked by hand.
    assert resolve_cdrs(core.repository, 'NSA', [LATEST_CAMPAIGN], ('voice',))['voice'] == [country]
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
    config = {'format': '{yy}-Q{quarter}{-mode}', 'modes_in_label': ['SA'], 'exceptions': []}
    name = '20261112 Daily Data NSA CDR UK London 20261024-20261111.xlsx'
    assert flex_label(['UK_London_NSA_2026'], 'London', name, '', config) == '26-Q4-London-Flex'
    assert flex_label(['UK_London_SA_2026'], 'London', name, '', config) == '26-Q4-SA-London-Flex'
    # The Campaign of the CDR in Workspace comes before the dates of its name.
    assert flex_label([], 'Leeds', name, '2026-Q3', config) == '26-Q3-Leeds-Flex'


def test_any_cdr_can_be_marked_as_flex_also_without_campaign_values(client, tmp_path):
    login(client)
    add_cdr(tmp_path, 'UK_Q3_Voice_Final.xlsx', calls(COUNTRY, 'UK_Q3_2026', 'c'), 'final')
    weekly = add_cdr(tmp_path, '20261020 Weekly Voice CDR UK Manchester 20261005-20261018.xlsx',
                     calls(LONDON, 'UK_Manchester_2026', 'w', '2026-10-10'), 'weekly')
    no_campaign = add_cdr(tmp_path, '20261020 Daily Voice CDR UK Leeds 20261012-20261019.xlsx',
                          calls(LONDON, '', 'x', '2026-10-15').drop(columns=['Campaign']), 'daily')
    assert weekly not in flex_suggestions(core.repository)

    # Any CDR card offers Mark as Flex, with the label it would give.
    page = client.get('/workspace').text
    assert 'queue-flex-mark' in page and '26-Q4-Local-Flex' in page

    marked = client.post(f'/workspace/datasets/{weekly}/flex', json={'action': 'mark', 'label': '26-Q4-Manchester-Flex'})
    assert marked.status_code == 200 and '26-Q4-Manchester-Flex' in marked.json()['exceptions']
    assert is_flex_cdr(cdr_campaigns(core.repository, [weekly])[weekly])

    # Without Campaign values the CDR takes the Flex campaign itself.
    marked = client.post(f'/workspace/datasets/{no_campaign}/flex', json={'action': 'mark', 'label': '26-Q4-Leeds-Flex'})
    assert marked.status_code == 200 and marked.json()['campaign'] == '2026-Q4-Leeds-Flex'
    assert core.repository.get_dataset(no_campaign)['campaign'] == '2026-Q4-Leeds-Flex'
    assert is_flex_cdr([], core.repository.get_dataset(no_campaign)['campaign'])


def test_the_flex_choice_of_the_upload_review_is_applied_once_the_cdr_is_ready(client, tmp_path):
    login(client)
    add_cdr(tmp_path, 'UK_Q3_Voice_Final.xlsx', calls(COUNTRY, 'UK_Q3_2026', 'c'), 'final')
    chosen = add_cdr(tmp_path, 'UK_Voice_Daily_20261005.xlsx', calls(LONDON, 'UK_Bath_2026', 'f', '2026-10-05'), 'daily')
    refused = add_cdr(tmp_path, '20261112 Daily Voice CDR UK London 20261024-20261111.xlsx',
                      calls(LONDON, 'UK_London_NSA_2026', 'r', '2026-10-25'), 'daily')
    waiting = add_cdr(tmp_path, 'UK_Voice_Daily_20261006.xlsx', calls(LONDON, 'UK_Bath_2026', 'q', '2026-10-06'), 'daily')
    core.repository.update_dataset_profile(waiting, status='processing')
    assert refused in flex_suggestions(core.repository)

    set_import_choices(core.repository, {chosen: 'flex', refused: 'not_flex', waiting: 'flex'})
    applied = {entry['dataset_id']: entry for entry in apply_import_choices(core.repository, 'super')}
    assert set(applied) == {chosen, refused}
    assert applied[chosen]['label'] == '26-Q4-Local-Flex' and is_flex_cdr(cdr_campaigns(core.repository, [chosen])[chosen])
    # Not Flex hides the suggestion for good, also when the CDR changes.
    core.repository.update_dataset_profile(refused, row_count=7)
    assert refused not in flex_suggestions(core.repository)
    assert not is_flex_cdr(cdr_campaigns(core.repository, [refused])[refused])
    # The CDR still processing keeps its choice.
    assert apply_import_choices(core.repository, 'super') == []


def test_the_upload_review_sends_a_flex_choice_per_file(client, tmp_path):
    login(client)
    page = client.get('/workspace').text
    assert 'data-flex-areas=' in page and "flexSelect.name = 'flex_choices'" in page
    source = (b'JOIN_ID,Operator,Campaign,Call_Status,Call_Start_Time\n'
              b'u1,EE,UK_Bath_2026,Completed,2026-10-05 10:00:00\nu2,EE,UK_Bath_2026,Failed,2026-10-05 11:00:00\n')
    response = client.post(
        '/datasets-analysis/upload',
        data={'dataset_kinds': ['voice'], 'cdr_stages': ['daily'], 'flex_choices': ['flex']},
        files=[('dataset_files', ('20261006 Daily Voice CDR UK Bath 20261005.csv', BytesIO(source), 'text/csv'))],
        follow_redirects=False,
    )
    assert response.status_code == 303
    dataset_id = next(int(row['id']) for row in core.repository.list_datasets())
    for _attempt in range(200):
        if str(core.repository.get_dataset(dataset_id)['status']) in {'ready', 'failed'}:
            break
        time.sleep(0.05)
    assert str(core.repository.get_dataset(dataset_id)['status']) == 'ready'
    core.apply_flex_import_choices(core.repository, 'super')
    assert is_flex_cdr(cdr_campaigns(core.repository, [dataset_id])[dataset_id])
    labels = [item['label'] for item in load_campaign_map(core.repository)['exceptions']]
    assert labels == ['26-Q4-Local-Flex']
    events = [row['action'] for row in core.repository.list_logs(limit=50)]
    assert 'upload_flex_choice' in events and 'update_dataset_flex' in events
    assert client.post('/datasets-analysis/upload', data={'dataset_kinds': 'voice', 'flex_choices': 'maybe'},
                       files={'dataset_files': ('x.csv', BytesIO(b'a\n1\n'), 'text/csv')}).status_code == 422
