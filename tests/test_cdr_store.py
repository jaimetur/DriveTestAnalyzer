"""The columnar copy of the CDRs: a Parquet file per CDR kept up to date by the triggers of its table, the catalog of
views over the CDRs in combined, and the wait for free disk space."""
import json
import sqlite3
import threading

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


def test_a_filtered_read_of_a_cdr_gives_the_rows_and_order_of_sqlite(client, tmp_path):
    rows = pd.DataFrame({
        'Operator': ['EE', ' ee ', 'O2', 'Vodafone UK', 'EE', 'O2'],
        'status': ['Failed', 'Completed', 'Completed', 'Dropped', 'Completed', 'Failed'],
        'event_start_time': ['2026-02-24 10:00:00', '2026-02-25 10:00:00', '2026-02-26 11:00:00', None,
                             '2026-02-23 09:00:00', '2026-02-24 12:00:00'],
        'JOIN_ID': ['a', 'b', 'c', 'd', 'e', 'f'],
        'Mean_Data_Rate': [1.5, 2.0, None, 4.0, 5.5, 6.0],
    })
    data = add_cdr(tmp_path, 'data.csv', 'data', rows)
    table = f'dataset_rows_{data}'
    with core.repository.connection() as connection:
        # The expression indexes the CDR tables have, and a table a WHERE reads beside the rows (as the Excluded Calls).
        connection.execute(f'CREATE INDEX IF NOT EXISTS "idx_{table}_status_norm" ON "{table}" (LOWER(TRIM(CAST("status" AS TEXT))))')
        connection.execute(f'CREATE INDEX IF NOT EXISTS "idx_{table}_operator_norm" ON "{table}" (LOWER(TRIM(CAST("Operator" AS TEXT))))')
        connection.execute('CREATE TABLE excluded_calls_test (join_id TEXT)')
        connection.execute("INSERT INTO excluded_calls_test VALUES ('c')")
    copy_everything()
    selected = [('Operator', 'Operator'), ('Rate', 'Mean_Data_Rate'), ('JOIN_ID', 'JOIN_ID')]
    cases = [
        ('', [], []),
        ("LOWER(TRIM(CAST(\"status\" AS TEXT))) IN (?, ?)", ['completed', 'failed'], ['status']),
        ("LOWER(TRIM(CAST(\"Operator\" AS TEXT))) IN (?) AND \"JOIN_ID\" NOT IN (SELECT join_id FROM excluded_calls_test)",
         ['ee'], ['Operator', 'JOIN_ID']),
        ("date(CAST(\"event_start_time\" AS TEXT)) >= date(?) AND \"Mean_Data_Rate\" > ?", ['2026-02-24', 1], ['event_start_time', 'Mean_Data_Rate']),
        ("LOWER(TRIM(CAST(\"status\" AS TEXT))) IN (?)", ['nothing'], ['status']),
    ]
    for where, params, filters in cases:
        query = f'SELECT "Operator" AS "Operator", "Mean_Data_Rate" AS "Rate", "JOIN_ID" AS "JOIN_ID" FROM "{table}"' + (
            f' WHERE {where}' if where else '')
        with core.repository.connection() as connection:
            expected = pd.read_sql_query(query, connection, params=params)
        frame = cdr_store.query_cdr(core.repository.db_path, 'data', data, selected, where, params, filters)
        pd.testing.assert_frame_equal(frame, expected, check_exact=True)
    # The rows of an index come in its order, as SQLite gives them.
    with core.repository.connection() as connection:
        assert connection.execute(f'EXPLAIN QUERY PLAN SELECT 1 FROM "{table}" WHERE {cases[1][0]}', cases[1][1]).fetchall()
    assert cdr_store.query_cdr(core.repository.db_path, 'data', data, selected, cases[1][0], cases[1][1], ['status'])['JOIN_ID'].tolist() == [
        'b', 'c', 'e', 'a', 'f']


def test_the_rows_of_a_cdr_with_filters_are_the_same_from_its_copy(client, tmp_path, monkeypatch):
    rows = pd.DataFrame({
        'Operator': ['EE', 'O2', 'EE', 'Vodafone UK'], 'Region': ['North', 'North', 'South', 'North'],
        'event_start_time': ['2026-02-24 10:00:00', '2026-02-25 10:00:00', '2026-03-01 11:00:00', '2026-02-24 12:00:00'],
        'Mean_Data_Rate': [1.5, 2, 3.25, None],
    })
    data = add_cdr(tmp_path, 'data.csv', 'data', rows)
    filters = {'Operator': ['EE', 'Vodafone UK'], 'Region': ['north'], 'date_from': '2026-02-24', 'date_to': '2026-02-28'}
    columns = ['Operator', 'region', 'Mean_Data_Rate', 'Missing column']
    sqlite_rows = core.repository.load_dataset_rows(data, columns, filters)
    copy_everything()
    reads = []
    query_cdr = cdr_store.query_cdr
    # The reads of this test only (the background tasks of the application read the copy too).
    reader = threading.get_ident()
    monkeypatch.setattr(cdr_store, 'query_cdr', lambda *args, **kwargs: (
        threading.get_ident() == reader and reads.append(args[2])) or query_cdr(*args, **kwargs))

    copied_rows = core.repository.load_dataset_rows(data, columns, filters)

    assert reads == [data] and copied_rows['Operator'].tolist() == ['EE', 'Vodafone UK']
    pd.testing.assert_frame_equal(copied_rows, sqlite_rows, check_exact=True)


def test_the_dashboard_columns_of_the_copies_are_those_of_the_combined_table(client, tmp_path):
    import numpy as np
    import sqlite3
    from src.modules import dashboard_column_cache as dcc

    first = add_cdr(tmp_path, 'first.csv', 'data', pd.DataFrame({
        'Operator': ['EE', ' o2 ', 'EE'], 'Call Status': ['Completed', 'Failed', None], 'Mean_Data_Rate': [12.5, None, 3],
        'event_start_time': ['2026-02-24 10:00:00', '2026-02-23 10:00:00', None]}))
    second = add_cdr(tmp_path, 'second.csv', 'data', pd.DataFrame({
        'Operator': ['Vodafone UK'], 'Call_Status': ['Dropped'], 'event_start_time': ['2026-02-22 08:00:00']}), nr_mode='SA')
    requested = ['Operator', 'Call_Status', 'Mean_Data_Rate', 'event_start_time', 'NR_Mode']
    for dataset_id in (first, second):
        core.repository.copy_dataset_rows_to_reporting(dataset_id, 'data', requested)
    copy_everything()
    database = core.repository.db_path
    connect = lambda: sqlite3.connect(database)
    source = dcc.CacheSource('data', 'reporting_rows_data', (), True)
    # The combined table names each column as the first CDR that had it ('Call Status' for both CDRs here).
    status = next(column for column in core.repository.list_reporting_row_columns('data') if column.casefold().startswith('call'))
    expressions = ['"Operator"', f'"{status}"', '"Mean_Data_Rate"', '"NR_Mode"', '"dataset_id"',
                   'LOWER(TRIM(CAST("Operator" AS TEXT)))', 'date(CAST("event_start_time" AS TEXT))']
    cache = dcc.ColumnCache(tmp_path / 'cache', memory_bytes=10 ** 8, disk_bytes=10 ** 8)

    for dataset_id in (first, second):
        segment = dcc.Segment(source, dataset_id, 'v')
        sqlite_parts = cache._build(connect, segment, [dcc.ROWID, dcc.ORDER_DATE, *expressions], None)
        copy_parts = dcc.build_from_copies(database, segment, expressions)
        for expression, part in sqlite_parts.items():
            assert copy_parts[expression][0] == part[0], expression
            assert list(dcc.decode_objects(copy_parts[expression], np.arange(dcc.part_length(part)))) == list(
                dcc.decode_objects(part, np.arange(dcc.part_length(part)))), expression
    # The frames a chart reads, with a filter, in every order, are the same.
    segments = [dcc.Segment(source, dataset_id, 'v') for dataset_id in (first, second)]
    terms = dcc.SelectionTerms(values=(('LOWER(TRIM(CAST("Operator" AS TEXT)))', frozenset({'ee', 'o2', 'vodafone uk'})),))
    columns = [(name, f'"{name}"') for name in ('Operator', status, 'Mean_Data_Rate', 'NR_Mode')]
    for order in dcc.ORDER_MODES:
        from_sqlite = dcc.read_frame(dcc.ColumnCache(tmp_path / f'sqlite-{order}', memory_bytes=10 ** 8, disk_bytes=10 ** 8),
                                     connect, segments, columns, terms, order)
        from_copies = dcc.read_frame(cache, connect, segments, columns, terms, order,
                                     builder=lambda segment, wanted: dcc.build_from_copies(database, segment, wanted))
        pd.testing.assert_frame_equal(from_copies, from_sqlite, check_exact=True)
    assert not (tmp_path / 'cache').exists()
    # A name that is no column of the combined table is read by SQLite (it reads it as a string there).
    assert dcc.build_from_copies(database, segments[0], ['"No such column"']) is None


def test_the_coalesced_columns_of_a_cdr_are_those_sqlite_gives(client, tmp_path):
    rows = pd.DataFrame({
        'Start_Lat': [51.5, None, '52.1', None, 53.0], 'End_Lat': [None, 50.2, 9, None, 53.1],
        'Lon': [-0.1, -1.2, -2.0, -3.0, None], 'Operator': ['EE', None, 'O2', 'EE', 'Three'],
        'Rate': [1, 2.5, None, 4, 5], 'Mixed': [7, 'eight', None, 9.5, '10'],
    })
    data = add_cdr(tmp_path, 'coalesced.csv', 'data', rows)
    copy_everything()
    table = core.repository.dataset_rows_table_name(data)
    cases = [
        ([('latitude', ['Start_Lat', 'End_Lat']), ('longitude', ['Lon']), ('operator', ['Operator']), ('rate', ['Rate']),
          ('mixed', ['Mixed', 'Rate']), ('missing', [])], ['latitude', 'longitude']),
        ([('operator', ['Operator']), ('rate', ['Rate'])], []),
        # A value of no column: no row is kept.
        ([('latitude', ['End_Lat']), ('longitude', ['Lon']), ('missing', [])], ['latitude', 'missing']),
    ]

    def sql(columns):
        quoted = [f'"{column}"' for column in columns]
        return 'NULL' if not quoted else quoted[0] if len(quoted) == 1 else f"COALESCE({', '.join(quoted)})"

    for outputs, required in cases:
        expressions = dict(outputs)
        conditions = ' AND '.join(f'{sql(expressions[alias])} IS NOT NULL' for alias in required) or '1'
        with core.repository.connection() as connection:
            expected = pd.read_sql_query(f"SELECT {', '.join(f'{sql(columns)} AS {alias}' for alias, columns in outputs)} "
                                         f'FROM "{table}" WHERE {conditions}', connection)
        found = cdr_store.coalesced_frame(core.repository.db_path, 'data', data, outputs, required)
        pd.testing.assert_frame_equal(found, expected, check_exact=True)
        assert all(found[column].map(type).tolist() == expected[column].map(type).tolist() for column in expected)


def test_a_copy_without_its_table_is_the_store_of_its_cdr(client, tmp_path):
    data = add_cdr(tmp_path, 'data.csv', 'data', data_rows())
    with core.repository.connection() as connection:
        connection.execute(f'CREATE INDEX "idx_dataset_rows_{data}_operator" ON "dataset_rows_{data}" (LOWER(TRIM(CAST("Operator" AS TEXT))))')
        created = connection.execute("SELECT sql FROM sqlite_master WHERE name = ?", (f'dataset_rows_{data}',)).fetchone()[0]
        expected = pd.read_sql_query(f'SELECT "Operator", "Test_Count", "NR_DL_SCell3_ARFCN" FROM dataset_rows_{data}', connection)
    copy_everything()
    root = cdr_store.store_root(core.repository.db_path)
    manifest = cdr_store.read_manifest(cdr_store.manifest_file(root, 'data', data))
    # The copy knows how the table is made, to make it again.
    assert manifest['schema']['table'] == created
    assert any('LOWER(TRIM(CAST("Operator" AS TEXT)))' in sql for sql in manifest['schema']['indexes'])
    assert not any('cdr_store_' in sql for sql in manifest['schema']['indexes'])

    core.repository.drop_dataset_rows(data)

    # The copy is the store of the CDR: up to date, never copied again nor removed, read and in the catalog.
    changes = cdr_store.store_changes(core.repository.db_path)
    assert changes['pending'] == [] and changes['orphans'] == [] and changes['cdrs'][data]['table'] is False
    assert cdr_store.fresh_copies(core.repository.db_path, [data]) == {data}
    job = copy_everything()
    assert job['removed'] == 0 and cdr_store.cdr_folder(root, 'data', data).is_dir()
    pd.testing.assert_frame_equal(
        cdr_store.read_cdr(core.repository.db_path, 'data', data, ['Operator', 'Test_Count', 'NR_DL_SCell3_ARFCN']), expected,
        check_exact=True)
    with duckdb.connect(str(root / cdr_store.CATALOG_FILE), read_only=True) as catalog:
        assert catalog.execute('SELECT COUNT(*) FROM cdr_data').fetchone() == (3,)
    # Processed again, the CDR keeps its copy until its table follows.
    core.repository.update_dataset_profile(data, status='processing')
    assert copy_everything()['removed'] == 0 and cdr_store.cdr_folder(root, 'data', data).is_dir()
    # Deleted, its copy goes.
    core.repository.delete_dataset(data)
    assert copy_everything()['removed'] == 1 and not cdr_store.cdr_folder(root, 'data', data).exists()


def _table_state(dataset_id):
    """Everything SQLite keeps of the table of a CDR: how it and its indexes are made, and each value with its type."""
    table = f'dataset_rows_{dataset_id}'
    with core.repository.connection() as connection:
        made = connection.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()
        indexes = sorted(row[0] for row in connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'index' AND tbl_name = ? AND sql IS NOT NULL", (table,)))
        columns = [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')]
        # The table itself (main), not the rows the application gives its SQL when it is empty.
        values = connection.execute(
            f'SELECT rowid, {", ".join(f"typeof({cdr_store.quote(column)}), {cdr_store.quote(column)}" for column in columns)} '
            f'FROM main."{table}" ORDER BY rowid').fetchall()
    return made and made[0], indexes, columns, [tuple(row) for row in values]


def test_the_table_of_a_cdr_is_made_again_from_its_copy_as_it_was(client, tmp_path):
    rows = pd.DataFrame({'Operator': ['EE', 'O2', 'EE', None, 'Three'], 'Rate': [1.0, 2.5, None, 4.0, 5.0],
                         'Count': [1, 2, 3, None, 5], 'Status': ['ok', 'ko', None, 'ok', 'ok']})
    data = add_cdr(tmp_path, 'data.csv', 'data', rows)
    with core.repository.connection() as connection:
        # Columns without a declared type: text and numbers, integers and reals; rows gone (gaps in the row ids).
        connection.execute(f'ALTER TABLE dataset_rows_{data} ADD COLUMN "Cell_List"')
        connection.execute(f'ALTER TABLE dataset_rows_{data} ADD COLUMN "Mixed_Number"')
        connection.executemany(f'UPDATE dataset_rows_{data} SET "Cell_List" = ?, "Mixed_Number" = ? WHERE rowid = ?',
                               [(372490, 5, 1), ('[372490]', 5.5, 2), (None, None, 3), (7.25, 9007199254740993, 4)])
        connection.execute(f'DELETE FROM dataset_rows_{data} WHERE rowid = 3')
        connection.execute(f'CREATE INDEX "idx_rows_{data}_status" ON "dataset_rows_{data}" (LOWER(TRIM(CAST("Status" AS TEXT))))')
    copy_everything()
    root = cdr_store.store_root(core.repository.db_path)
    manifest = cdr_store.read_manifest(cdr_store.manifest_file(root, 'data', data))
    assert dict(manifest['columns'])['Mixed_Number'] == 'DOUBLE:I' and dict(manifest['columns'])['Cell_List'] == 'MIXED:IR'
    before = _table_state(data)
    # Integers and reals of one column read back with their own types, a big integer exactly.
    assert cdr_store.read_cdr(core.repository.db_path, 'data', data, ['Mixed_Number'])['Mixed_Number'].tolist()[:2] == [5.0, 5.5]
    assert cdr_store.rows_by_rowid(core.repository.db_path, 'data', data, ['Mixed_Number'], [1, 4]) == {
        1: (5,), 4: (9007199254740993,)}

    core.repository.drop_dataset_rows(data)
    assert cdr_store.restore_table(core.repository, data)

    assert _table_state(data) == before
    assert not cdr_store.restore_table(core.repository, data)
    # From its empty table too.
    core.repository.set_workspace_state(cdr_store.ONLY_COPIES_STATE_KEY, '1')
    assert cdr_store.drop_copied_table(core.repository, data)
    assert _table_state(data)[3] == [] and cdr_store.restore_table(core.repository, data)
    assert _table_state(data) == before
    # The copy still holds it: nothing to copy again.
    assert cdr_store.store_changes(core.repository.db_path)['pending'] == []


def test_where_the_copies_are_the_only_store_a_changed_table_is_copied_and_goes(client, tmp_path):
    data = add_cdr(tmp_path, 'data.csv', 'data', data_rows())
    core.repository.set_workspace_state(cdr_store.ONLY_COPIES_STATE_KEY, '1')
    before = _table_state(data)[:3]

    def emptied():
        """Whether the table of the CDR is empty, its copy holding its rows (its columns and indexes kept)."""
        with core.repository.connection() as connection:
            rows = connection.execute(f'SELECT COUNT(*) FROM main.dataset_rows_{data}').fetchone()[0]
            return data in cdr_store.shadows(connection) and not rows and _table_state(data)[:3] == before

    # Once copied, the table is emptied.
    copy_everything()
    assert emptied() and cdr_store.fresh_copies(core.repository.db_path, [data]) == {data}
    assert cdr_store.store_changes(core.repository.db_path)['pending'] == []

    # A writer holds the CDR: its rows come back from the copy, and stay while it is held.
    with cdr_store.hold(core.repository, data):
        assert not emptied()
        with core.repository.connection() as connection:
            connection.execute(f'UPDATE dataset_rows_{data} SET "Operator" = ? WHERE rowid = 2', ('Three',))
        # Its change is copied, but the rows stay while it is held.
        assert copy_everything()['written'] == ['data.csv'] and not emptied()
    # Released, the table is emptied again.
    assert copy_everything()['written'] == [] and emptied()
    assert cdr_store.read_cdr(core.repository.db_path, 'data', data, ['Operator'])['Operator'].tolist() == ['EE', 'Three', 'EE']
    # Rows put back without a change are emptied too, without copying the CDR again.
    with cdr_store.hold(core.repository, data):
        pass
    assert not emptied()
    assert copy_everything()['written'] == [] and emptied()
    # Processed again, its table holds its rows.
    core.repository.replace_dataset_rows(data, data_rows())
    with core.repository.connection() as connection:
        assert data not in cdr_store.shadows(connection)


def test_the_sql_of_the_application_reads_the_rows_of_an_emptied_table_from_its_copy(client, tmp_path):
    rows = pd.DataFrame({'Operator': ['EE', 'O2', 'EE', 'Three'], 'Status': ['Ok', 'ko', 'OK ', None],
                         'Rate': [1.5, 2, None, 4], 'event_start_time': ['2026-02-01 10:00', '2026-02-02 10:00',
                                                                           '2026-02-01 09:00', '2026-02-03 10:00']})
    data = add_cdr(tmp_path, 'data.csv', 'data', rows)
    table = f'dataset_rows_{data}'
    queries = [
        (f'SELECT rowid, * FROM "{table}"', ()),
        (f'SELECT "Operator", "Rate" FROM "{table}" WHERE LOWER(TRIM(CAST("Operator" AS TEXT))) = ?', ('ee',)),
        (f'SELECT COUNT(*), MAX(rowid) FROM "{table}"', ()),
        (f'SELECT 1 FROM "{table}" LIMIT 1', ()),
        (f'SELECT "Operator", COUNT(*) FROM "{table}" GROUP BY "Operator" ORDER BY 2 DESC, 1', ()),
        (f'SELECT "Status" FROM "{table}" WHERE date(CAST(event_start_time AS TEXT)) >= ?', ('2026-02-02',)),
    ]

    def read():
        with core.repository.connection() as connection:
            found = [connection.execute(sql, parameters).fetchall() for sql, parameters in queries]
            frame = pd.read_sql_query(f'SELECT * FROM "{table}" WHERE "Rate" > ?', connection, params=(1.6,))
        return [[tuple(row) for row in rows] for rows in found], frame

    before, frame = read()
    columns = core.repository.list_dataset_row_columns(data)
    filtered = core.repository.load_dataset_rows(data, ['Operator', 'Rate'], {'Operator': ['EE']})
    core.repository.set_workspace_state(cdr_store.ONLY_COPIES_STATE_KEY, '1')
    copy_everything()
    with core.repository.connection() as connection:
        assert connection.execute(f'SELECT COUNT(*) FROM main."{table}"').fetchone()[0] == 0

    after, after_frame = read()
    assert after == before
    pd.testing.assert_frame_equal(after_frame, frame, check_exact=True)
    assert core.repository.list_dataset_row_columns(data) == columns
    pd.testing.assert_frame_equal(core.repository.load_dataset_rows(data, ['Operator', 'Rate'], {'Operator': ['EE']}), filtered,
                                  check_exact=True)
    # SQL that writes elsewhere from its rows runs once, on them.
    with core.repository.connection() as connection:
        connection.execute('CREATE TABLE copied_rows (source INTEGER, operator TEXT, rate REAL, runs INTEGER DEFAULT 0)')
        connection.execute(f'INSERT INTO copied_rows (source, operator) SELECT rowid, "Operator" FROM "{table}" WHERE "Rate" > ?', (1,))
        connection.execute('CREATE TRIGGER copied_rows_runs AFTER UPDATE OF rate ON copied_rows BEGIN '
                           'UPDATE copied_rows SET runs = runs + 1 WHERE rowid = NEW.rowid; END')
        connection.execute(f'UPDATE copied_rows SET rate = (SELECT "Rate" FROM "{table}" WHERE "{table}".rowid = copied_rows.source)')
        assert [tuple(row) for row in connection.execute('SELECT source, operator, rate, runs FROM copied_rows ORDER BY source')] == [
            (1, 'EE', 1.5, 1), (2, 'O2', 2.0, 1), (4, 'Three', 4.0, 1)]
    # Writing its rows needs the CDR held, which puts them back first.
    with pytest.raises(sqlite3.OperationalError, match='columnar copy'):
        with core.repository.connection() as connection:
            connection.execute(f'UPDATE "{table}" SET "Operator" = ? WHERE rowid = 1', ('Vodafone UK',))
    with cdr_store.hold(core.repository, data), core.repository.connection() as connection:
        connection.execute(f'UPDATE "{table}" SET "Operator" = ? WHERE rowid = 1', ('Vodafone UK',))
    copy_everything()
    assert read()[0][0][0][1] == 'Vodafone UK'


def test_the_pages_and_counts_of_an_emptied_table_are_those_of_its_rows(client, tmp_path):
    rows = pd.DataFrame({'Operator': ['EE', 'O2', 'EE', 'Three', 'ee'], 'Region': ['North', 'South', None, 'North', 'North'],
                         'Rate': [1.5, 2, None, 4, 7]})
    data = add_cdr(tmp_path, 'data.csv', 'data', rows)
    table = f'dataset_rows_{data}'

    def pages():
        return (
            core.repository.database_table_page(table, limit=2, offset=1),
            core.repository.database_table_page(table, limit=10, filters={'Operator': ['EE', 'ee']}),
            core.repository.load_dataset_preview_page(data, ['Operator', 'Rate', 'region'], {'Region': ['north']}, 0, 2, 'Operator'),
            core.repository.dataset_row_count(data),
        )

    before = pages()
    core.repository.set_workspace_state(cdr_store.ONLY_COPIES_STATE_KEY, '1')
    copy_everything()
    after = pages()

    assert after[0] == before[0] and after[1] == before[1] and after[3] == before[3] == 5
    pd.testing.assert_frame_equal(after[2][0], before[2][0], check_exact=True)
    assert after[2][1:] == before[2][1:]


def test_an_emptied_combined_table_gives_its_sql_the_rows_of_the_copies(client, tmp_path):
    first = add_cdr(tmp_path, 'first.csv', 'data', pd.DataFrame({
        'Operator': ['EE', 'O2', 'EE'], 'Call Status': ['Completed', 'Failed', None], 'Rate': [12.5, None, 3]}))
    second = add_cdr(tmp_path, 'second.csv', 'data', pd.DataFrame({
        'Operator': ['Vodafone UK', 'ee'], 'Call_Status': ['Dropped', 'Completed'], 'RSRP': [-95, -80]}), nr_mode='SA')
    requested = ['Operator', 'Call_Status', 'Rate', 'RSRP', 'NR_Mode']
    # The second CDR first, so the combined rows are not in the order of the CDRs.
    for dataset_id in (second, first):
        core.repository.copy_dataset_rows_to_reporting(dataset_id, 'data', requested)
    queries = [
        ('SELECT rowid, * FROM reporting_rows_data', ()),
        ('SELECT "Operator", "NR_Mode", dataset_id, source_row_id FROM reporting_rows_data '
         'WHERE LOWER(TRIM(CAST("Operator" AS TEXT))) = ?', ('ee',)),
        ('SELECT dataset_id, COUNT(*), SUM("Rate") FROM reporting_rows_data GROUP BY dataset_id ORDER BY dataset_id', ()),
        ('SELECT rowid, source_row_id FROM reporting_rows_data WHERE dataset_id = ? ORDER BY rowid', (first,)),
    ]

    def read():
        with core.repository.connection() as connection:
            return [[tuple(row) for row in connection.execute(sql, parameters).fetchall()] for sql, parameters in queries]

    before = read()
    copy_everything()
    assert cdr_store.empty_combined_table(core.repository, 'data')

    with core.repository.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM main.reporting_rows_data').fetchone()[0] == 0
        assert connection.execute(f'SELECT COUNT(*) FROM {cdr_store.COMBINED_ROWS_TABLE}').fetchone()[0] == 5
    assert read() == before
    # Writing its rows is the work of the copies.
    with pytest.raises(sqlite3.OperationalError, match='combined data table'):
        with core.repository.connection() as connection:
            connection.execute('DELETE FROM reporting_rows_data WHERE dataset_id = ?', (first,))
