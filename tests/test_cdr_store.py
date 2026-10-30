"""The columnar copy of the CDRs: a Parquet file per CDR kept up to date by the triggers of its table, the catalog of
views over the CDRs in combined, and the wait for free disk space."""
import contextlib
import json
import sqlite3
import threading

import duckdb
import pandas as pd
import pytest

import src.DriveTestAnalyzer as core
from src.modules import cdr_store
from src.modules.repository import CDR_ROWS_IN_COPY_MESSAGE, local_now_iso


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
    # Its table holds its rows after the copy.
    core.repository.set_workspace_state(cdr_store.ONLY_COPIES_STATE_KEY, '0')
    copy_everything()

    # A writer of the rows of a CDR whose table holds them holds the CDR (its table is not emptied meanwhile), and its
    # change raises its version.
    with cdr_store.hold(core.repository, data), core.repository.connection() as connection:
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


def test_the_design_columns_of_the_copies_are_those_of_the_combined_table(client, tmp_path):
    import numpy as np
    import sqlite3
    from src.modules import design_column_cache as dcc

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


def test_the_rf_number_and_day_columns_of_the_copies_are_those_sqlite_gives(client, tmp_path, monkeypatch):
    import numpy as np
    import sqlite3
    from src.modules import design_column_cache as dcc
    from src.modules.rf_catalog_source import rf_number_term

    # Numbers with up to 17 digits (kept as they are, not written as text), text with spaces or blank, numbers and text
    # in one column, and times whose day is (or is not) that of their first 10 characters.
    latitudes = [51.5, 51.123456789012344, 0.30000000000000004, 1e-05, 1e15, 100.0, None, -0.5, 0.0001, 123456789012345.0]
    texts = [' a ', '', '  ', 'x', None, 'b ', ' ', 'c', None, '']
    mixed = [7, ' -95.5 ', None, 9.5, 'eight', '', 51.123456789012344, None, 'x\x00y', 3]
    times = ['2026-02-24 10:00:00.052000', '2026-02-24T23:59:59.999', '2026-02-30 10:00:00', '2026-02-24 24:00:00',
             '2026-02-24 10:00:00Z', '2026-02-24', None, '2026-02-24 23:59:59.9999999', 'not a time', '2026-13-01 10:00:00']
    data = add_cdr(tmp_path, 'rf.csv', 'data', pd.DataFrame({
        'Operator': ['EE'] * 10, 'Test_Start_Latitude': latitudes, 'Text_Field': texts, 'Count_Field': list(range(-3, 7)),
        'Local_Time': times, 'event_start_time': ['2026-02-24 10:00:00'] * 10}))
    with core.repository.connection() as connection:
        # A column without a declared type: numbers and text.
        connection.execute(f'ALTER TABLE dataset_rows_{data} ADD COLUMN "Mixed_Field"')
        connection.executemany(f'UPDATE dataset_rows_{data} SET "Mixed_Field" = ? WHERE rowid = ?',
                               [(value, row) for row, value in enumerate(mixed, start=1)])
    requested = ['Operator', 'Test_Start_Latitude', 'Text_Field', 'Count_Field', 'Mixed_Field', 'Local_Time', 'event_start_time']
    core.repository.copy_dataset_rows_to_reporting(data, 'data', requested)
    copy_everything()
    database = core.repository.db_path
    source = dcc.CacheSource('data', 'reporting_rows_data', (), True)

    def number(column: str) -> str:
        return rf_number_term(f'"{column}"')
    expressions = [f'({number("Test_Start_Latitude")})', number('Text_Field'), f'({number("Count_Field")})',
                   number('Mixed_Field'), f'(COALESCE({number("Text_Field")}, {number("Test_Start_Latitude")}))',
                   f'COALESCE({number("Test_Start_Latitude")}, {number("Text_Field")}, {number("Count_Field")})',
                   f'COALESCE({number("Test_Start_Latitude")}, {number("Count_Field")})',
                   'date(CAST(("Local_Time") AS TEXT))', 'date(CAST("Local_Time" AS TEXT))', 'upper(CAST("Local_Time" AS TEXT))']
    cache = dcc.ColumnCache(tmp_path / 'cache', memory_bytes=10 ** 8, disk_bytes=10 ** 8)
    segment = dcc.Segment(source, data, 'v')
    sqlite_parts = cache._build(lambda: sqlite3.connect(database), segment, [dcc.ROWID, dcc.ORDER_DATE, *expressions], None)
    # The copy holds numbers and text as such, and Python works out the text it is certain of (SQLite the other).
    columns = ('Test_Start_Latitude', 'Text_Field', 'Count_Field', 'Mixed_Field', 'Local_Time')
    raw, _length = cdr_store._raw(database, 'data', data, list(columns))
    assert [raw[column][0] for column in columns] == ['real', 'text', 'int', 'object', 'text']
    answers = []
    term_value = dcc._number_term_value
    monkeypatch.setattr(dcc, '_number_term_value', lambda value: answers.append(answer := term_value(value)) or answer)
    copy_parts = dcc.build_from_copies(database, segment, expressions)
    assert dcc._UNKNOWN in answers and 'a' in answers and '-95.5' in answers and 9.5 in answers
    for expression, part in sqlite_parts.items():
        assert copy_parts[expression][0] == part[0], expression
        assert list(dcc.decode_objects(copy_parts[expression], np.arange(dcc.part_length(part)))) == list(
            dcc.decode_objects(part, np.arange(dcc.part_length(part)))), expression
    # The reals are read as they are, with all their digits.
    assert copy_parts[f'({number("Test_Start_Latitude")})'][0] == 'float'
    assert list(dcc.decode_objects(copy_parts[f'({number("Test_Start_Latitude")})'], np.arange(10))) == latitudes


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


def test_the_copy_of_a_cdr_keeps_the_sqlite_type_of_every_value(client, tmp_path):
    rows = pd.DataFrame({'Operator': ['EE', 'O2', 'EE', None, 'Three'], 'Rate': [1.0, 2.5, None, 4.0, 5.0],
                         'Count': [1, 2, 3, None, 5], 'Status': ['ok', 'ko', None, 'ok', 'ok']})
    data = add_cdr(tmp_path, 'data.csv', 'data', rows)
    # Its table holds its rows after the copy first.
    core.repository.set_workspace_state(cdr_store.ONLY_COPIES_STATE_KEY, '0')
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

    # Its table emptied, the SQL of the application reads the same rows, row ids and types from the copy.
    core.repository.set_workspace_state(cdr_store.ONLY_COPIES_STATE_KEY, '1')
    assert cdr_store.drop_copied_table(core.repository, data)
    assert _table_state(data)[:3] == before[:3]
    typed = ', '.join(f'typeof({cdr_store.quote(column)}), {cdr_store.quote(column)}' for column in before[2])
    with core.repository.connection() as connection:
        assert [tuple(row) for row in connection.execute(f'SELECT rowid, {typed} FROM dataset_rows_{data} ORDER BY rowid')] == before[3]


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

    # Its rows never go back to its table: held, the table stays empty and SQL cannot write it.
    with cdr_store.hold(core.repository, data) as table_holds_rows:
        assert not table_holds_rows and emptied()
        with pytest.raises(sqlite3.OperationalError, match='columnar copy'):
            with core.repository.connection() as connection:
                connection.execute(f'UPDATE dataset_rows_{data} SET "Operator" = ? WHERE rowid = 2', ('Three',))
    # The change goes to the copy, which stays the store of the CDR: nothing to copy again.
    assert cdr_store.change_copy_columns(core.repository, data, pd.DataFrame({cdr_store.ROWID: [1, 2, 3], 'Operator': ['EE', 'Three', 'EE']}))
    assert copy_everything()['written'] == [] and emptied()
    assert cdr_store.read_cdr(core.repository.db_path, 'data', data, ['Operator'])['Operator'].tolist() == ['EE', 'Three', 'EE']
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
    # SQL cannot write its rows, held or not: they are changed in the copy.
    for held in (False, True):
        with pytest.raises(sqlite3.OperationalError, match='columnar copy'):
            with cdr_store.hold(core.repository, data) if held else contextlib.nullcontext(), core.repository.connection() as connection:
                connection.execute(f'UPDATE "{table}" SET "Operator" = ? WHERE rowid = 1', ('Vodafone UK',))
    assert cdr_store.change_copy_columns(core.repository, data, pd.DataFrame({
        cdr_store.ROWID: [1, 2, 3, 4], 'Operator': ['Vodafone UK', 'O2', 'EE', 'Three']}))
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

    # The same pages, read-only once the copy is the store of the CDR.
    for page in (*after[:2], *before[:2]):
        page['read_only'] = (page.pop('editable'), page.pop('read_only_reason'))
    assert [page.pop('read_only') for page in after[:2]] == [(False, CDR_ROWS_IN_COPY_MESSAGE)] * 2
    assert [page.pop('read_only') for page in before[:2]] == [(True, '')] * 2
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

    def loaded():
        return [core.repository.load_reporting_rows('data', ids, ['Operator', 'call status', 'Rate', 'NR_Mode', 'source_row_id'],
                                                    in_scope_only=scope)
                for ids in ([second], [first, second]) for scope in (False, True)]

    frames = loaded()

    def previews():
        return [core.repository.load_reporting_preview_page('data', ['Operator', 'Rate', 'NR_Mode'], filters, page, 2, 'Operator')
                for filters in ({}, {'Operator': ['ee']}) for page in (0, 1)]

    pages = previews()
    counts = [core.repository.reporting_row_count('data'), core.repository.reporting_row_count('data', second)]
    copy_everything()
    assert cdr_store.empty_combined_table(core.repository, 'data')
    for frame, expected in zip(loaded(), frames, strict=True):
        pd.testing.assert_frame_equal(frame, expected, check_exact=True)
    for (frame, total, options), (expected, expected_total, expected_options) in zip(previews(), pages, strict=True):
        pd.testing.assert_frame_equal(frame, expected, check_exact=True)
        assert (total, options) == (expected_total, expected_options)
    assert [core.repository.reporting_row_count('data'), core.repository.reporting_row_count('data', second)] == counts == [5, 2]

    with core.repository.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM main.reporting_rows_data').fetchone()[0] == 0
        assert connection.execute(f'SELECT COUNT(*) FROM {cdr_store.COMBINED_ROWS_TABLE}').fetchone()[0] == 5
    assert read() == before
    # Writing its rows is the work of the copies.
    with pytest.raises(sqlite3.OperationalError, match='combined data table'):
        with core.repository.connection() as connection:
            connection.execute('DELETE FROM reporting_rows_data WHERE dataset_id = ?', (first,))


def test_the_writers_of_an_emptied_combined_table_keep_its_rows_as_sqlite_would(client, tmp_path):
    first = add_cdr(tmp_path, 'first.csv', 'data', pd.DataFrame({'Operator': ['EE', 'O2'], 'Rate': [1.5, 2]}))
    second = add_cdr(tmp_path, 'second.csv', 'data', pd.DataFrame({'Operator': ['Three'], 'Rate': [3]}), nr_mode='SA')
    for dataset_id in (first, second):
        core.repository.copy_dataset_rows_to_reporting(dataset_id, 'data', ['Operator', 'Rate'])
    copy_everything()
    assert cdr_store.empty_combined_table(core.repository, 'data')

    def rows():
        with core.repository.connection() as connection:
            return [tuple(row) for row in connection.execute(
                'SELECT rowid, dataset_id, source_row_id, "Operator", "Rate", "NR_Mode" FROM reporting_rows_data ORDER BY rowid')]

    assert rows() == [(1, first, 1, 'EE', 1.5, 'NSA'), (2, first, 2, 'O2', 2.0, 'NSA'), (3, second, 1, 'Three', 3.0, 'SA')]
    # A CDR without its copy yet gives the rows of its table, after the others.
    third = add_cdr(tmp_path, 'third.csv', 'data', pd.DataFrame({'Operator': ['Vodafone UK'], 'Rate': [4], 'RSRP': [-90]}))
    assert core.repository.copy_dataset_rows_to_reporting(third, 'data', ['Operator', 'Rate']) == 'rows'
    assert rows()[-1] == (4, third, 1, 'Vodafone UK', 4.0, 'NSA')
    assert core.repository.copy_dataset_rows_to_reporting(third, 'data', ['Operator', 'Rate']) is False
    # A new column is added to it, and its values are those of the CDRs.
    assert core.repository.copy_dataset_rows_to_reporting(third, 'data', ['RSRP']) == 'columns'
    with core.repository.connection() as connection:
        assert [row[0] for row in connection.execute('SELECT "RSRP" FROM reporting_rows_data ORDER BY rowid')] == [None, None, None, -90]
    # The rows of a CDR leave it, and come back after the last one, as SQLite numbers them.
    core.repository.drop_reporting_rows(first, 'data')
    assert core.repository.reporting_dataset_ids('data') == {second, third}
    core.repository.copy_dataset_rows_to_reporting(first, 'data', ['Operator'])
    assert [row[:3] for row in rows()] == [(3, second, 1), (4, third, 1), (5, first, 1), (6, first, 2)]
    # The NR Mode of a CDR is read as it is now.
    core.repository.update_dataset_profile(second, nr_mode='NSA')
    assert core.repository.set_reporting_nr_mode(second, 'data') is True
    assert rows()[0][-1] == 'NSA'


def test_the_catalog_gives_the_views_of_the_cdrs_for_postgresql_too(client, tmp_path):
    first = add_cdr(tmp_path, 'first.csv', 'data', data_rows())
    second = add_cdr(tmp_path, 'second.csv', 'data', pd.DataFrame({'Operator': ['O2'], 'RSRP': [-95], 'NR_Mode': ['SA']}))
    with core.repository.connection() as connection:
        # A column without a declared type with text and an integer.
        connection.execute(f'ALTER TABLE dataset_rows_{first} ADD COLUMN "Cell_List"')
        connection.executemany(f'UPDATE dataset_rows_{first} SET "Cell_List" = ? WHERE rowid = ?', [(372490, 1), ('[372490]', 2)])
    copy_everything()
    root = cdr_store.store_root(core.repository.db_path)
    views = json.loads((root / cdr_store.POSTGRES_VIEWS_FILE).read_text(encoding='utf-8'))

    data = views['views']['cdr_data']
    # Every column with one type, the text and numbers of a column together, the files of each CDR under {root}.
    assert data.startswith("SELECT r['__dataset_id']::bigint AS dataset_id, r['__rowid']::bigint AS source_row_id, ")
    assert "r['Mean_Data_Rate']::double precision AS \"Mean_Data_Rate\"" in data
    assert "COALESCE(r['Cell_List']::text, r['__int__Cell_List']::text) AS \"Cell_List\"" in data
    assert "COALESCE(r['NR_Mode']::text, r['__nr_mode']::text) AS \"NR_Mode\"" in data
    assert f"ARRAY['{{root}}/data/{first}/part-*.parquet', '{{root}}/data/{second}/part-*.parquet'], union_by_name := true" in data
    assert views['views']['cdr_voice'].endswith('WHERE false')
    # It changes with the copies.
    signature = views['signature']
    core.repository.update_dataset_profile(second, in_combined='no')
    copy_everything()
    changed = json.loads((root / cdr_store.POSTGRES_VIEWS_FILE).read_text(encoding='utf-8'))
    assert changed['signature'] != signature and f'/data/{second}/' not in changed['views']['cdr_data']


def test_the_copies_travel_with_the_database_of_their_workspace(client, tmp_path):
    import zipfile

    workspace = core.active_workspace
    data = add_cdr(tmp_path, 'data.csv', 'data', data_rows())
    voice = add_cdr(tmp_path, 'voice.csv', 'voice', pd.DataFrame({'Operator': ['EE', 'O2'], 'Call_Status': ['Completed', 'Dropped']}))
    core.repository.copy_dataset_rows_to_reporting(data, 'data', ['Operator', 'Test_Count', 'NR_Mode'])
    # A backup of an earlier version: the tables hold the rows, without copies.
    earlier = core.create_recurring_database_backup({'components': ['workspace_database'], 'backup_path': str(tmp_path / 'earlier'),
                                                    'workspace_ids': [workspace.id]})

    def rows(database_path):
        """What the SQL of the application reads of the CDRs and the combined table."""
        repository = core.Repository(database_path, global_db_path=core.repository.global_db_path)
        with repository.connection() as connection:
            return [[tuple(row) for row in connection.execute(f'SELECT rowid, * FROM {table} ORDER BY rowid').fetchall()]
                    for table in (f'dataset_rows_{data}', f'dataset_rows_{voice}', 'reporting_rows_data')]

    before = rows(workspace.database_path)
    # The copies are the only store of the Data CDR (its table and the combined table emptied); the Voice CDR changed
    # since its copy, its table holding its rows.
    core.repository.set_workspace_state(cdr_store.ONLY_COPIES_STATE_KEY, '1')
    copy_everything()
    assert cdr_store.empty_combined_table(core.repository, 'data')
    core.repository.replace_dataset_rows(voice, pd.DataFrame({'Operator': ['EE', 'O2'], 'Call_Status': ['Completed', 'Completed']}))
    core.repository.update_dataset_profile(voice, processed_at=local_now_iso())
    with core.repository.connection() as connection:
        assert cdr_store.shadows(connection) == {data} and cdr_store.combined_shadows(connection) == {'data'}
    before = rows(workspace.database_path)
    assert before[1][1][-1] == 'Completed'

    # A workspace package takes the copies its database needs or can use, not the out of date ones nor the catalog.
    package = tmp_path / 'workspace.zip'
    core.build_export_archive_file(f'workspace:{workspace.id}', package)
    prefix = f'workspaces/{workspace.name}/{cdr_store.ARCHIVE_FOLDER}/'
    with zipfile.ZipFile(package) as archive:
        copies = sorted(name[len(prefix):] for name in archive.namelist() if name.startswith(prefix))
    assert copies[0] == f'data/{data}.json' and copies[1:] and all(name.startswith(f'data/{data}/part-') for name in copies[1:])

    # Imported as another workspace, it reads the same rows.
    staging = tmp_path / 'staging'
    with zipfile.ZipFile(package) as archive:
        core._safe_extract_archive_prefix(archive, staging, f'workspaces/{workspace.name}')
    imported = core.import_workspace_archive(staging / 'workspaces' / workspace.name, {'name': 'Imported'})
    assert rows(imported.database_path) == before
    assert cdr_store.fresh_copies(imported.database_path, [data, voice]) == {data}

    # A duplicate too.
    duplicate = core.workspace_registry.duplicate(workspace.id)
    assert rows(duplicate.database_path) == before
    assert cdr_store.fresh_copies(duplicate.database_path, [data, voice]) == {data}

    # Restored, a backup gives the workspace back its database with its copies...
    backup = core.create_recurring_database_backup({'components': ['workspace_database'], 'backup_path': str(tmp_path / 'backups'),
                                                   'workspace_ids': [workspace.id]})
    core.repository.drop_dataset_rows(data)
    core.restore_database_backup(backup, ['workspace_database'])
    assert rows(workspace.database_path) == before
    # ... and one of an earlier version its tables, their copies made again.
    core.restore_database_backup(earlier, ['workspace_database'])
    with core.repository.connection() as connection:
        assert cdr_store.shadows(connection) == set() and cdr_store.combined_shadows(connection) == set()
    assert not cdr_store.store_root(workspace.database_path).exists()
    restored = rows(workspace.database_path)
    assert restored[0] == before[0] and restored[2] == before[2]


def test_the_query_builder_reads_the_rows_of_an_emptied_table_from_its_copy(client, tmp_path):
    from src.modules import query_builder

    first = add_cdr(tmp_path, 'first.csv', 'data', data_rows())
    second = add_cdr(tmp_path, 'second.csv', 'data', pd.DataFrame({'Operator': ['O2', 'EE'], 'RSRP': [-95, -80]}))
    voice = add_cdr(tmp_path, 'voice.csv', 'voice', pd.DataFrame({'Operator': ['EE', 'O2'], 'Call_Status': ['Completed', 'Dropped']}))
    datasets = [{'id': first, 'kind': 'data', 'name': 'first.csv'}, {'id': second, 'kind': 'data', 'name': 'second.csv'},
                {'id': voice, 'kind': 'voice', 'name': 'voice.csv'}]
    database = core.repository.db_path
    queries = [
        'SELECT * FROM selected_data',
        'SELECT "Operator", COUNT(*) AS tests, SUM("Test_Count") AS total FROM selected_data GROUP BY "Operator" ORDER BY "Operator"',
        'SELECT COUNT(*) FROM selected_data',
        'SELECT d.source_row_id, d."RSRP", v."Call_Status" FROM selected_data d JOIN selected_voice v ON v."Operator" = d."Operator" '
        'ORDER BY 1, 2, 3',
        f'SELECT rowid, "Operator" FROM dataset_rows_{first} WHERE "Operator" = \'EE\'',
    ]

    def results():
        pages = [query_builder.execute_query(database, datasets, query, row_limit=100, include_total=True) for query in queries]
        export = ''.join(query_builder.iter_query_csv(database, datasets, queries[0], column_filters=[{'index': 3, 'values': ['EE']}]))
        values = query_builder.query_column_values(database, datasets, queries[0], 3)
        return pages, export, values

    before = results()
    assert all(page[1] for page in before[0]) and 'Vodafone UK' not in before[1] and before[1].count('EE') == 3
    core.repository.set_workspace_state(cdr_store.ONLY_COPIES_STATE_KEY, '1')
    copy_everything()
    with core.repository.connection() as connection:
        assert cdr_store.shadows(connection) == {first, second, voice}
    assert results() == before


def test_the_copies_become_the_only_store_and_the_database_gives_back_the_room(client, tmp_path, monkeypatch):
    # The workspace of the tests opened as the server started: its copies are the only store of its CDRs.
    assert cdr_store.only_copies(core.repository.db_path)
    core.repository.set_workspace_state(cdr_store.ONLY_COPIES_STATE_KEY, '0')
    data = add_cdr(tmp_path, 'data.csv', 'data', pd.DataFrame({'Operator': ['EE', 'O2'] * 2000, 'Rate': range(4000)}))
    voice = add_cdr(tmp_path, 'voice.csv', 'voice', pd.DataFrame({'Operator': ['EE', 'O2'], 'Call_Status': ['Completed', 'Dropped']}))
    core.repository.copy_dataset_rows_to_reporting(data, 'data', ['Operator', 'Rate', 'NR_Mode'])
    copy_everything()
    with core.repository.connection() as connection:
        before = [[tuple(row) for row in connection.execute(f'SELECT rowid, * FROM {table} ORDER BY rowid').fetchall()]
                  for table in (f'dataset_rows_{data}', f'dataset_rows_{voice}', 'reporting_rows_data')]
    steps = []

    assert cdr_store.move_rows_to_copies(core.repository, lambda done, total: steps.append((done, total))) == {
        'cdr_tables': 2, 'combined_tables': 1}
    assert cdr_store.only_copies(core.repository.db_path) and steps == [(1, 2), (2, 2)]
    with core.repository.connection() as connection:
        assert cdr_store.shadows(connection) == {data, voice}
        assert cdr_store.combined_shadows(connection) == {'data'}
        assert connection.execute(f'SELECT COUNT(*) FROM main.dataset_rows_{data}').fetchone()[0] == 0
    # Nothing left to move.
    assert cdr_store.move_rows_to_copies(core.repository) == {'cdr_tables': 0, 'combined_tables': 0}

    # The room of the rows goes back to the disk once enough of the database is free.
    assert cdr_store.compact_database(core.repository) is None
    monkeypatch.setattr(cdr_store, 'COMPACT_FREE_BYTES', 0)
    monkeypatch.setattr(cdr_store, 'COMPACT_FREE_SHARE', 0.01)
    started = []
    compacted = cdr_store.compact_database(core.repository, lambda: started.append(True))
    assert started and compacted['after'] < compacted['before']
    with core.repository.connection() as connection:
        assert [[tuple(row) for row in connection.execute(f'SELECT rowid, * FROM {table} ORDER BY rowid').fetchall()]
                for table in (f'dataset_rows_{data}', f'dataset_rows_{voice}', 'reporting_rows_data')] == before
    # Without room on the disk it waits for the next start.
    monkeypatch.setattr(cdr_store, 'free_space', lambda path: 0)
    with core.repository.connection() as connection:
        connection.execute('CREATE TABLE filler (value TEXT)')
        connection.executemany('INSERT INTO filler VALUES (?)', [('x' * 1000,)] * 2000)
        connection.execute('DROP TABLE filler')
    assert cdr_store.compact_database(core.repository)['skipped'] == 1


def test_the_query_builder_pages_need_only_the_first_rows_of_the_copies(client, tmp_path, monkeypatch):
    from src.modules import query_builder

    first = add_cdr(tmp_path, 'first.csv', 'data', pd.DataFrame({
        'Operator': (['EE', 'O2', 'EE', 'Three', 'EE', 'O2'] * 5)[:28], 'Rate': range(28)}))
    second = add_cdr(tmp_path, 'second.csv', 'data', pd.DataFrame({
        'Operator': ['O2', 'EE', 'EE', 'O2', 'EE'] * 4, 'Rate': range(100, 120), 'RSRP': range(-90, -110, -1)}))
    datasets = [{'id': first, 'kind': 'data', 'name': 'first.csv'}, {'id': second, 'kind': 'data', 'name': 'second.csv'}]
    database = core.repository.db_path
    queries = ['SELECT * FROM selected_data', 'SELECT * FROM selected_data WHERE "Operator" = \'EE\'',
               'SELECT "Rate" FROM selected_data ORDER BY "Rate" DESC', 'SELECT * FROM selected_data LIMIT 3',
               'SELECT "Operator", SUM("Rate") FROM selected_data GROUP BY 1']

    def pages():
        return [query_builder.execute_query(database, datasets, query, row_limit=2, offset=offset, include_total=True)
                for query in queries for offset in (0, 2, 10, 26, 30, 46, 50)]

    before = pages()
    copy_everything()
    with core.repository.connection() as connection:
        assert cdr_store.shadows(connection) == {first, second}
    given = []
    provide = cdr_store.provide_rows
    monkeypatch.setattr(cdr_store, 'provide_rows', lambda *args, **kwargs: (given.append(kwargs.get('in_part')), provide(*args, **kwargs))[1])
    assert pages() == before
    # The pages read in one pass get every column only for the rows they give (the first 3 for the first page, the
    # EE rows it gives for the filtered one), the column that chooses them for every row; the others every column of
    # every row.
    parts = [(sorted(columns), rows) for columns, rows in filter(None, given)]
    assert (['operator'], [1, 2, 3]) in parts and (['operator'], [1, 3, 5]) in parts and None in given
    # The first rows of the tables first (12 of the 28 rows of the first CDR for its first page), more each time until
    # a page has its rows.
    given.clear()
    monkeypatch.setattr(query_builder, 'FIRST_ROWS_WINDOW', 1)
    assert pages() == before
    # Too many rows to note: every column of every row.
    monkeypatch.setattr(query_builder, 'MAX_SEEN_ROWS', 2)
    assert pages() == before


def test_reading_an_emptied_table_takes_no_write_lock_of_the_workspace(client, tmp_path):
    from src.modules.repository import workspace_read_connection, workspace_write_lock

    data = add_cdr(tmp_path, 'data.csv', 'data', data_rows())
    copy_everything()
    with core.repository.connection() as connection:
        assert data in cdr_store.shadows(connection)
    connection = workspace_read_connection(core.repository.db_path)
    try:
        assert connection.execute(f'SELECT COUNT(*) FROM dataset_rows_{data}').fetchone()[0] == 3
        # The rows were given in TEMP tables only: no transaction left open, and writers of other threads go on.
        assert not connection.in_transaction
        acquired = []

        def write():
            lock = workspace_write_lock(core.repository.db_path)
            acquired.append(lock.acquire(timeout=5))
            if acquired[-1]:
                lock.release()

        writer = threading.Thread(target=write)
        writer.start()
        writer.join()
        assert acquired == [True]
    finally:
        connection.close()


def test_a_cdr_whose_copy_is_its_only_store_is_changed_in_its_copy_never_put_back_in_its_table(client, tmp_path):
    login(client)
    rows = pd.DataFrame({'Operator': ['EE', 'Vodafone UK', 'EE'], 'Operator_Vendor': ['EE Ericsson', 'Vodafone UK Nokia', None],
                         'source_file': ['data.csv'] * 3, 'Mean_Data_Rate': [44.6, 7.0, None]})
    data = add_cdr(tmp_path, 'data.csv', 'data', rows)
    core.repository.copy_dataset_rows_to_reporting(data, 'data', ['Operator', 'source_file', 'NR_Mode'])
    core.repository.set_workspace_state(cdr_store.ONLY_COPIES_STATE_KEY, '1')
    copy_everything()
    assert cdr_store.empty_combined_table(core.repository, 'data')
    # The same rows in a table, as a CDR not copied yet: what the former path gives.
    reference = add_cdr(tmp_path, 'reference.csv', 'data', rows)
    manifest_file = cdr_store.manifest_file(cdr_store.store_root(core.repository.db_path), 'data', data)
    copied_rows = cdr_store.read_manifest(manifest_file)['rows']

    def in_copy_only():
        """Whether the rows of the CDR are still in its copy alone (its table empty), as many as before."""
        with core.repository.connection() as connection:
            empty = not connection.execute(f'SELECT COUNT(*) FROM main.dataset_rows_{data}').fetchone()[0]
            return empty and data in cdr_store.shadows(connection) and cdr_store.read_manifest(manifest_file)['rows'] == copied_rows

    # Renamed: its source_file column alone is rewritten in its copy, and the emptied combined table reads it from there.
    core.repository.rename_dataset_file(data, 'renamed.csv', str(tmp_path / 'renamed.csv'))
    assert in_copy_only() and core.repository.get_dataset(data)['file_name'] == 'renamed.csv'
    assert copy(data)['source_file'].tolist() == ['renamed.csv'] * 3
    with core.repository.connection() as connection:
        assert [tuple(row) for row in connection.execute('SELECT DISTINCT source_file FROM reporting_rows_data WHERE dataset_id = ?',
                                                         (data,))] == [('renamed.csv',)]
    assert cdr_store.combined_shadow_kinds(core.repository.db_path) == {'data'}

    # Its NR Mode: the NR Mode column of its copy.
    assert client.post(f'/workspace/datasets/{data}/nr-mode', json={'nr_mode': 'SA'}).status_code == 200
    assert in_copy_only() and copy(data)['__nr_mode'].tolist() == ['SA'] * 3
    assert cdr_store.read_cdrs(core.repository.db_path, 'data', [data], ['NR_Mode'])['NR_Mode'].tolist() == ['SA'] * 3

    # Its missing Vendor: worked out from the columns it reads, as in its table.
    core.repository.ensure_vendor_column(data)
    core.repository.ensure_vendor_column(reference)
    assert in_copy_only()
    assert cdr_store.read_cdr(core.repository.db_path, 'data', data, ['Vendor'])['Vendor'].tolist() == \
        core.repository.load_dataset_rows(reference, ['Vendor'], {})['Vendor'].tolist()

    # Database Management shows its rows, and those of the emptied combined table, read-only.
    page = core.repository.database_table_page(f'dataset_rows_{data}')
    assert len(page['rows']) == 3 and not page['editable'] and page['read_only_reason'] == CDR_ROWS_IN_COPY_MESSAGE
    assert not core.repository.database_table_page('reporting_rows_data')['editable']
    with pytest.raises(ValueError, match='read-only'):
        core.repository.update_database_table_row(f'dataset_rows_{data}', 1, {'Operator': 'Three'})
    with pytest.raises(ValueError, match='read-only'):
        core.repository.delete_database_table_row(f'dataset_rows_{data}', 1)
    assert in_copy_only() and core.repository.database_table_page(f'dataset_rows_{reference}')['editable']
