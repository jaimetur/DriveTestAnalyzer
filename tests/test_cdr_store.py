"""The columnar copy of the CDRs: a Parquet file per CDR kept up to date by the triggers of its table, the catalog of
views over the CDRs in combined, and the wait for free disk space."""
import json

import duckdb
import pandas as pd
import pytest

import src.DriveTestAnalyzer as core
from src.modules import cdr_store
from src.modules.repository import local_now_iso


@pytest.fixture(autouse=True)
def plenty_of_disk_space(monkeypatch):
    """The copies never wait for the disk of the machine running the tests (the test of the wait sets its own)."""
    monkeypatch.setattr(cdr_store, 'free_space', lambda path: 1024 ** 4)


def login(client):
    client.cookies.clear()
    assert client.post('/login', data={'username': 'super', 'password': 'super123'}, follow_redirects=False).status_code == 303


def logged(action):
    return [json.loads(row['details']) for row in core.repository.list_logs() if row['action'] == action]


def add_cdr(tmp_path, name, kind, rows, nr_mode='NSA'):
    source = tmp_path / name
    source.write_text('test source', encoding='utf-8')
    dataset_id, _created = core.repository.add_dataset(name, str(source), 'super')
    core.repository.replace_dataset_rows(dataset_id, rows)
    core.repository.update_dataset_profile(
        dataset_id, status='ready', progress=100, dataset_kind=kind, nr_mode=nr_mode,
        row_count=len(rows), column_count=len(rows.columns), processed_at=local_now_iso(),
    )
    return dataset_id


def data_rows():
    return pd.DataFrame({
        'Operator': ['EE', 'Vodafone UK', 'EE'],
        'Campaign': ['UK_Q1_2026'] * 3,
        'Test_Count': [1, 2, None],
        'Mean_Data_Rate': [44.6, 7.0, None],
        # Numbers and text in one column, as some CDR columns have.
        'NR_DL_SCell3_ARFCN': [372490, '[372490]', None],
    })


def copy_everything():
    """Run the copy of the active workspace at once (each step submits the next)."""
    repository = core.Repository(core.active_workspace.database_path, global_db_path=core.repository.global_db_path)
    return cdr_store.start_store_sync(repository, lambda run: run(), lambda: cdr_store.included_cdrs(repository))


def copy(dataset_id, kind='data'):
    return duckdb.connect().execute(
        f"SELECT * FROM read_parquet('{cdr_store.cdr_parts(cdr_store.store_root(core.repository.db_path), kind, dataset_id)}') "
        'ORDER BY __rowid').df()


def test_every_ready_cdr_is_copied_with_the_values_of_sqlite_and_the_catalog_has_a_view_per_type(client, tmp_path):
    data = add_cdr(tmp_path, 'data.csv', 'data', data_rows())
    voice = add_cdr(tmp_path, 'voice.csv', 'voice', pd.DataFrame({'Operator': ['O2'], 'Call_Status': ['Completed']}), nr_mode='SA')
    # A column without a declared type (as the CDR processing creates them) with an integer among its text values,
    # as the cell lists of some CDRs have.
    with core.repository.connection() as connection:
        connection.execute(f'ALTER TABLE dataset_rows_{data} ADD COLUMN "Cell_List"')
        connection.executemany(f'UPDATE dataset_rows_{data} SET "Cell_List" = ? WHERE rowid = ?',
                               [(372490, 1), ('[372490]', 2), (None, 3)])

    job = copy_everything()

    assert job['status'] == 'ready' and sorted(job['written']) == ['data.csv', 'voice.csv'] and job['catalog']
    rows = copy(data)
    with core.repository.connection() as connection:
        sqlite_rows = connection.execute(f'SELECT rowid, * FROM dataset_rows_{data} ORDER BY rowid').fetchall()
    assert rows['__rowid'].tolist() == [row['rowid'] for row in sqlite_rows]
    assert set(rows['__dataset_id']) == {data} and set(rows['__nr_mode']) == {'NSA'}
    assert rows['Mean_Data_Rate'].tolist()[:2] == [44.6, 7.0] and pd.isna(rows['Mean_Data_Rate'].iloc[2])
    manifest = cdr_store.read_manifest(cdr_store.manifest_file(cdr_store.store_root(core.repository.db_path), 'data', data))
    assert dict(manifest['columns'])['Mean_Data_Rate'] == 'DOUBLE' and manifest['rows'] == 3
    # Read back, the copy gives the frame pandas reads from SQLite: the same values, Python types and dtypes, also for a
    # column with text and numbers (kept apart in the file).
    assert dict(manifest['columns'])['Cell_List'] == 'MIXED:I'
    columns = [*data_rows().columns, 'Cell_List']
    with core.repository.connection() as connection:
        expected = pd.read_sql_query(f'SELECT {", ".join(cdr_store.quote(column) for column in columns)} '
                                     f'FROM dataset_rows_{data} ORDER BY rowid', connection)
    frame = cdr_store.read_cdr(core.repository.db_path, 'data', data, columns)
    pd.testing.assert_frame_equal(frame, expected, check_exact=True)
    assert frame['Cell_List'].tolist() == [372490, '[372490]', None]
    # Some rows only, typed by the values read (as SQLite would give them).
    with core.repository.connection() as connection:
        some = pd.read_sql_query(f'SELECT {", ".join(cdr_store.quote(column) for column in columns)} '
                                 f'FROM dataset_rows_{data} WHERE rowid IN (1, 3) ORDER BY rowid', connection)
    pd.testing.assert_frame_equal(cdr_store.read_cdr(core.repository.db_path, 'data', data, columns, rowids=[3, 1]),
                                  some, check_exact=True)
    # The views of the catalog read the copies, with the dataset, the row id and the NR Mode of each row.
    catalog = duckdb.connect(str(cdr_store.store_root(core.repository.db_path) / cdr_store.CATALOG_FILE), read_only=True)
    assert catalog.execute('SELECT dataset_id, source_row_id, Operator, "NR_Mode" FROM cdr_voice').fetchall() == [(voice, 1, 'O2', 'SA')]
    assert catalog.execute('SELECT COUNT(*), MIN("NR_Mode") FROM cdr_data').fetchone() == (3, 'NSA')
    assert [row[0] for row in catalog.execute('SELECT Cell_List FROM cdr_data ORDER BY source_row_id').fetchall()] == [
        '372490', '[372490]', None]
    assert catalog.execute('SELECT COUNT(*) FROM cdr_speech').fetchone() == (0,)
    assert logged('cdr_store_synced')[0]['written'] == ['data.csv', 'voice.csv']
    # A copy that is up to date is not written again.
    assert cdr_store.store_changes(core.repository.db_path)['pending'] == [] and copy_everything()['written'] == []


def test_a_change_of_the_rows_of_a_cdr_copies_it_again(client, tmp_path):
    data = add_cdr(tmp_path, 'data.csv', 'data', data_rows())
    copy_everything()

    # Any writer of the rows (an auto-calculated field, the Map Areas, Database Management) raises its version.
    with core.repository.connection() as connection:
        connection.execute(f'UPDATE dataset_rows_{data} SET "Operator" = ? WHERE rowid = 2', ('Three',))

    assert [cdr['id'] for cdr in cdr_store.store_changes(core.repository.db_path)['pending']] == [data]
    assert copy_everything()['written'] == ['data.csv']
    assert copy(data)['Operator'].tolist() == ['EE', 'Three', 'EE']


def test_the_views_leave_out_the_cdrs_not_in_combined_and_the_copies_of_deleted_cdrs_go(client, tmp_path):
    first = add_cdr(tmp_path, 'first.csv', 'data', data_rows())
    second = add_cdr(tmp_path, 'second.csv', 'data', data_rows())
    copy_everything()
    catalog_path = cdr_store.store_root(core.repository.db_path) / cdr_store.CATALOG_FILE

    def ids():
        with duckdb.connect(str(catalog_path), read_only=True) as catalog:
            return sorted({row[0] for row in catalog.execute('SELECT dataset_id FROM cdr_data').fetchall()})

    assert ids() == [first, second]
    core.repository.update_dataset_profile(second, in_combined='no')
    assert copy_everything()['catalog'] and ids() == [first]

    core.repository.delete_dataset(first)
    job = copy_everything()
    root = cdr_store.store_root(core.repository.db_path)
    assert job['removed'] == 1 and not cdr_store.cdr_folder(root, 'data', first).exists() and ids() == []


def test_the_copy_waits_for_free_disk_space_and_says_so_once(client, tmp_path, monkeypatch):
    add_cdr(tmp_path, 'data.csv', 'data', data_rows())
    monkeypatch.setattr(cdr_store, 'free_space', lambda path: 0)

    job = copy_everything()
    copy_everything()

    assert job['written'] == [] and cdr_store.store_job(core.repository.db_path)['status'] == 'waiting'
    assert [item['file'] for item in logged('cdr_store_waiting_for_space')] == ['data.csv']
    task = cdr_store.store_tasks(core.repository.db_path, 'cdr-store')[0]
    assert task['detail'].startswith('Waiting for free disk space to copy data.csv')

    monkeypatch.setattr(cdr_store, 'free_space', lambda path: 10 * 1024 ** 4)
    assert copy_everything()['written'] == ['data.csv']


def test_database_management_names_the_table_of_the_versions(client, tmp_path):
    add_cdr(tmp_path, 'data.csv', 'data', data_rows())
    copy_everything()
    login(client)

    assert 'CDR Store Versions' in client.get('/super-admin').text


def test_several_cdrs_read_from_their_copies_as_their_combined_table_returns_them(client, tmp_path):
    first = add_cdr(tmp_path, 'first.csv', 'data', pd.DataFrame({
        'Operator': ['EE', 'O2'], 'Call Status': ['Completed', 'Failed'], 'Mean_Data_Rate': [12.5, None]}))
    second = add_cdr(tmp_path, 'second.csv', 'data', pd.DataFrame({
        'Operator': ['Vodafone UK'], 'Call_Status': ['Dropped'], 'RSRP': [-95]}), nr_mode='SA')
    requested = ['Operator', 'Call_Status', 'Mean_Data_Rate', 'RSRP', 'NR_Mode', 'dataset_id', 'source_row_id']
    for dataset_id in (first, second):
        core.repository.copy_dataset_rows_to_reporting(dataset_id, 'data', requested)
    copy_everything()

    combined = core.repository.load_reporting_rows('data', [second, first], requested)
    frame = cdr_store.read_cdrs(core.repository.db_path, 'data', [second, first], requested,
                                existing_columns=core.repository.list_reporting_row_columns('data'))

    pd.testing.assert_frame_equal(frame, combined, check_exact=True)
    assert frame['Call_Status'].tolist() == ['Completed', 'Failed', 'Dropped']
    assert frame['NR_Mode'].tolist() == ['NSA', 'NSA', 'SA'] and frame['dataset_id'].tolist() == [first, first, second]
    assert cdr_store.fresh_copies(core.repository.db_path, [first, second, 999]) == {first, second}
