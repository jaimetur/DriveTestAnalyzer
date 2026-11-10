"""NR Mode, the NR Mode of the CDR of each row: a pinned field of the tables of rows, though the CDRs do not keep it."""
import csv
from io import BytesIO, StringIO

import src.DriveTestAnalyzer as core


def upload_cdr(client, name):
    client.cookies.clear()
    assert client.post('/login', data={'username': 'super', 'password': 'super123'}, follow_redirects=False).status_code == 303
    response = client.post('/datasets-analysis/upload', data={'dataset_kinds': 'data'}, files={
        'dataset_files': (name, BytesIO(b'Operator,Campaign,Mean_Data_Rate,Test_Name\nA,UK_Q3_2026,10,HTTP DL\nB,UK_Q3_2026,20,HTTP DL\n'), 'text/csv'),
    })
    assert response.status_code == 200, response.text
    return max(int(row['id']) for row in core.repository.list_datasets())


def test_the_preview_of_a_cdr_shows_its_nr_mode_as_a_pinned_derived_field_that_filters_and_exports(client):
    dataset_id = upload_cdr(client, 'Data CDR UK Q3 SA.csv')
    page = client.get(f'/workspace/preview/{dataset_id}')
    assert page.status_code == 200, page.text
    header = next(part for part in page.text.split('<th ')[1:] if 'data-column-name="NR_Mode"' in part)
    assert 'data-column-pinned="true"' in header and 'data-column-kind="Derived"' in header
    # After Campaign, as the main fields go.
    columns = [part.split('"', 1)[0] for part in page.text.split('<th data-column-name="')[1:]]
    assert columns.index('NR_Mode') == columns.index('Campaign') + 1
    data = client.post(f'/api/workspace/preview/{dataset_id}/data', json={'page': 0, 'column_filters': {}})
    assert data.status_code == 200, data.text
    assert {row['NR_Mode'] for row in data.json()['rows']} == {'SA'}
    values = client.post(f'/api/workspace/preview/{dataset_id}/data', json={'page': 0, 'column_filters': {}, 'filter_column': 'NR_Mode'})
    assert values.json()['filter_values'] == ['SA']
    other = client.post(f'/api/workspace/preview/{dataset_id}/data', json={'page': 0, 'column_filters': {'NR_Mode': ['NSA']}})
    assert other.json()['total'] == 0
    export = client.post(f'/api/workspace/preview/{dataset_id}/data', json={'page': 0, 'column_filters': {'NR_Mode': ['SA']}, 'download': True})
    rows = list(csv.DictReader(StringIO(export.text)))
    assert len(rows) == 2 and {row['NR_Mode'] for row in rows} == {'SA'}
