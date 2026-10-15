"""The Campaign of a CDR: suggested from its file name and NR Mode, shown and changed in the Workspace."""

from pathlib import Path

import pandas as pd
import pytest

import src.DriveTestAnalyzer as core
from src.modules.cdr_campaign import dataset_campaign, infer_campaign, normalize_campaign
from src.modules.repository import local_now_iso


def login(client, username='super', password='super123'):
    client.cookies.clear()
    response = client.post('/login', data={'username': username, 'password': password}, follow_redirects=False)
    assert response.status_code == 303


def add_cdr(tmp_path: Path, name: str, kind: str = 'voice', nr_mode: str | None = None) -> int:
    source = tmp_path / name
    source.write_text('test source', encoding='utf-8')
    dataset_id, _created = core.repository.add_dataset(name, str(source), 'super')
    rows = pd.DataFrame({'Operator': ['EE'], 'Campaign': ['UK_Q3_2026']})
    core.repository.replace_dataset_rows(dataset_id, rows)
    core.repository.update_dataset_profile(
        dataset_id, status='ready', progress=100, dataset_kind=kind, row_count=1, column_count=2,
        processed_at=local_now_iso(), **({'nr_mode': nr_mode} if nr_mode else {}),
    )
    return dataset_id


def test_campaign_is_suggested_from_the_file_name():
    assert infer_campaign('NetCheck_UK_CDR_Data_2026_Q2_SA.xlsx') == '2026-Q2'
    assert infer_campaign('NetCheck_UK_CDR_Voice_2026_Q1.xlsm') == '2026-Q1'
    assert infer_campaign('20260623 Final Data CDR UK Q2 20260512 - 20260613.xlsx') == '2026-Q2'
    assert infer_campaign('20251219_UK Q4 Data CDR 20251110-20251209 FINAL SA.xlsm') == '2025-Q4'
    assert infer_campaign('20260910 Daily Voice CDR UK Q3 NSA 20260901 - 20260909.xlsx') == '2026-Q3'
    assert infer_campaign('20250828_DE_Q3_Data_20250714 - 20250819 Final VDF.xlsm') == '2025-Q3'
    # Exported in January for the Q4 campaign of the year before.
    assert infer_campaign('20260105_UK Q4 Voice CDR 20251110-20251209.xlsx') == '2025-Q4'
    # Without a quarter or a year there is no campaign.
    assert infer_campaign('UK_Voice_CDR_20260921.xlsx') == ''
    assert infer_campaign('UK_Q3_Voice.xlsx') == ''
    assert dataset_campaign('mapping_three', None, 'UK_Q2_2026.xlsx') is None
    assert dataset_campaign('voice', '', 'UK_Q2_2026.xlsx') == ''
    assert dataset_campaign('voice', None, 'UK_Q2_2026.xlsx') == '2026-Q2'
    # Campaigns saved with their mode read as their quarter.
    assert dataset_campaign('voice', '2026-Q2-NSA', 'x.xlsx') == '2026-Q2'


def test_written_campaigns_are_normalised():
    assert normalize_campaign('2026-Q2') == '2026-Q2'
    assert normalize_campaign(' 2026 q3 sa ') == '2026-Q3'
    assert normalize_campaign('UK_Q2_2026_NSA') == '2026-Q2'
    assert normalize_campaign('') == ''
    with pytest.raises(ValueError):
        normalize_campaign('Q3 campaign')


def test_workspace_shows_and_changes_the_campaign_of_each_cdr(client, tmp_path):
    login(client)
    named = add_cdr(tmp_path, 'NetCheck_UK_CDR_Voice_2026_Q2_SA.xlsx', nr_mode='SA')
    unnamed = add_cdr(tmp_path, 'UK_Voice_CDR.xlsx', kind='data')
    page = client.get('/workspace').text
    final_card = page.split('data-dataset-card="cdr-final"', 1)[1].split('data-dataset-card="cdr-weekly"', 1)[0]
    header = final_card.split('</thead>', 1)[0]
    assert (header.index('>Dataset<') < header.index('>Campaign<') < header.index('>NR Mode<') < header.index('>CDR<br>Type<')
            < header.index('>CDR Stage<') < header.index('>In Combined?<'))
    assert 'Input Type' not in header
    assert 'value="2026-Q2"' in final_card and 'data-dataset-campaign-input' in final_card
    assert '<option value="voice" selected>CDR-Voice</option>' in final_card and '<option value="data" selected>CDR-Data</option>' in final_card
    assert '<option value="2026-Q2"></option>' in page
    assert 'data-campaign-count title="Campaigns of these CDRs">1 campaign</span>' in final_card
    assert 'data-cdr-count title="CDRs of this card">2 CDRs</span>' in final_card
    assert 'data-datasets-campaign-count title="Campaigns of the Final, Weekly and Daily CDRs">1 campaign</span>' in page
    assert '>2 CDRs</span>' in page and '>0 Network Inventories</span>' in page and '>0 Geographic Datasets</span>' in page
    assert 'data-datasets-size title="Size of the source files of every dataset">0 MB</span>' in page
    # The rows are grouped by campaign and sorted by Campaign, NR Mode and CDR Type in the page.
    script = (Path(__file__).parents[1] / 'src/web_interface/static/js/app.js').read_text(encoding='utf-8')
    assert "header.dataset.campaignGroupRow = key;" in script and "size.dataset.campaignGroupSize = '';" in script and "label.textContent = key || 'No campaign';" in script
    assert "? {key: 'campaign', direction: 'desc'}" in script and "['nr-mode', 'kind'].reduce(" in script

    response = client.post(f'/workspace/datasets/{unnamed}/campaign', json={'campaign': '2026 q3 sa'})
    assert response.status_code == 200 and response.json()['campaign'] == '2026-Q3'
    assert core.repository.get_dataset(unnamed)['campaign'] == '2026-Q3'
    # Blank leaves the CDR without a campaign.
    assert client.post(f'/workspace/datasets/{named}/campaign', json={'campaign': ''}).json()['campaign'] == ''
    status = {item['id']: item for item in client.get('/api/datasets/status').json()['datasets']}
    assert status[named]['campaign'] == '' and status[unnamed]['campaign'] == '2026-Q3'
    assert client.post(f'/workspace/datasets/{named}/campaign', json={'campaign': 'next quarter'}).status_code == 422
    logs = [row for row in core.repository.list_logs(limit=50) if row['action'] == 'update_dataset_campaign']
    assert len(logs) == 2 and '"previous_campaign": "2026-Q2"' in logs[0]['details']


def test_campaign_is_only_for_cdrs(client, tmp_path):
    login(client)
    source = tmp_path / 'inventory.csv'
    source.write_text('a\n1\n', encoding='utf-8')
    dataset_id, _ = core.repository.add_dataset(source.name, str(source), 'super')
    core.repository.update_dataset_profile(dataset_id, status='ready', dataset_kind='network_inventory')
    assert client.post(f'/workspace/datasets/{dataset_id}/campaign', json={'campaign': '2026-Q2-NSA'}).status_code == 400


def test_the_cdr_type_of_a_cdr_can_be_changed_and_reprocesses_it(client, tmp_path, monkeypatch):
    login(client)
    dataset_id = add_cdr(tmp_path, 'UK_Q2_2026_Voice.xlsx', kind='voice')
    core.repository.copy_dataset_rows_to_reporting(dataset_id, 'voice')
    queued = []
    monkeypatch.setattr(core, 'enqueue_dataset_processing', lambda *args, **kwargs: queued.append(args[1]) or object())
    page = client.get('/workspace').text
    assert 'data-dataset-cdr-type-select' in page and '<option value="voice" selected>CDR-Voice</option>' in page
    assert client.post(f'/workspace/datasets/{dataset_id}/cdr-type', json={'cdr_type': 'video'}).status_code == 422
    response = client.post(f'/workspace/datasets/{dataset_id}/cdr-type', json={'cdr_type': 'data'})
    assert response.status_code == 200 and response.json() == {'dataset_id': dataset_id, 'cdr_type': 'data', 'reprocessing': True}
    assert queued == [dataset_id] and core.repository.get_dataset(dataset_id)['dataset_kind'] == 'data'
    with core.repository.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM reporting_rows_voice WHERE dataset_id = ?', (dataset_id,)).fetchone()[0] == 0
    logs = [row for row in core.repository.list_logs(limit=20) if row['action'] == 'update_dataset_cdr_type']
    assert len(logs) == 1 and '"previous_cdr_type": "voice"' in logs[0]['details']
