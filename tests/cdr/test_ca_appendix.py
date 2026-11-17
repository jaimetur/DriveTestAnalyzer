"""The CA Appendix: read as it streams, kept as Parquet, its fields written in the columnar copy of the CDR tests with
its JOIN_IDs, and read by Network Insights."""
import json
import math

import duckdb
import openpyxl
import pandas as pd
import pytest

import src.DriveTestAnalyzer as core
from src.modules.cdr import ca_appendix, cdr_store
from src.modules.core.repository import local_now_iso
from src.modules.network_insights import network_insights as ni


@pytest.fixture(autouse=True)
def plenty_of_disk_space(monkeypatch):
    monkeypatch.setattr(cdr_store, 'free_space', lambda path: 1024 ** 4)


HEADER = ['Validity', 'JOIN_ID', 'TestId', 'Test_Status', 'HomeOperator', 'Main_Total_Bandwidth_DL',
          'Main_Bands_Combination', 'Main_Total_Number_carrier_DL', 'NR_PCC_Main_PCI', 'LTE_PCC_Main_Band',
          'LTE_PCC_Main_DL_EARFCN', 'LTE_PCC_Main_Bandwidth', 'LTE_PCC_Main_PCI', 'NR_PCC_Main_Band',
          'NR_SCC4_Main_Band', 'Total_Bandwidth_DL_Timeline', 'eNodeB_gNodeB_Result_Changes']


def appendix_rows(bandwidth: float = 70):
    return [
        [1, '0xAA01', 11, 'Completed', 'EE', f'{bandwidth:g}(4.6)', 'LTE E-UTRA 7/NR BAND 78', '[2](1.0)->[4](3.5)',
         '[44](2.298)', 'LTE E-UTRA 7', 2850, 20, 207, 78, None, '[20](0.15)->[70](2.52)', '4G:548710 -> 4G:505868, 5G:17029'],
        [1, '0xAA02', 12, 'Failed', 'O2 (UK)', '20(2.18)', 'LTE E-UTRA 3', '1(2.18)', None, 'LTE E-UTRA 3', 1392, 20, 284,
         None, None, '[20](2.18)', '4G:8125'],
        # A test of no CDR of the workspace.
        [1, '0xFF99', 13, 'Completed', 'EE', '15(3.64)', 'LTE E-UTRA 20', '1(3.64)', None, 'LTE E-UTRA 20', 6300, 15, 4,
         None, None, '[15](3.64)', '4G:10051'],
    ]


def write_csv(path, rows):
    pd.DataFrame(rows, columns=HEADER).to_csv(path, index=False)
    return path


def add_appendix(tmp_path, name, rows):
    (tmp_path / 'input').mkdir(exist_ok=True)
    source = write_csv(tmp_path / 'input' / f'{name}.csv', rows)
    dataset_id, _created = core.repository.add_dataset(name, str(source), 'super')
    core.repository.update_dataset_profile(dataset_id, status='processing', dataset_kind=ca_appendix.KIND)
    result = ca_appendix.process_delivery(core.repository, dataset_id, source)
    return dataset_id, result


def add_data_cdr(tmp_path):
    source = tmp_path / 'data.csv'
    source.write_text('test source', encoding='utf-8')
    rows = pd.DataFrame({'JOIN_ID': ['0xaa01', '0xAA02', '0xBB03'], 'Operator': ['EE', 'O2', 'EE'],
                         'Campaign': ['UK_Q3_2026'] * 3})
    dataset_id, _created = core.repository.add_dataset('data.csv', str(source), 'super')
    core.repository.replace_dataset_rows(dataset_id, rows)
    core.repository.update_dataset_profile(dataset_id, status='ready', progress=100, dataset_kind='data', nr_mode='NSA',
                                           row_count=len(rows), column_count=len(rows.columns), processed_at=local_now_iso())
    core.repository.set_workspace_state(cdr_store.ONLY_COPIES_STATE_KEY, '1')
    repository = core.Repository(core.active_workspace.database_path, global_db_path=core.repository.global_db_path)
    cdr_store.start_store_sync(repository, lambda run: run(), lambda: cdr_store.included_cdrs(repository))
    assert dataset_id in cdr_store.shadow_ids(core.repository.db_path)
    return dataset_id


def ca_fields(dataset_id, columns):
    return cdr_store.read_cdr(core.repository.db_path, 'data', dataset_id, columns)


def test_a_workbook_is_read_as_it_streams_with_the_values_of_its_cells(tmp_path):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(HEADER)
    for row in appendix_rows():
        sheet.append(row)
    # A text with XML characters and a cell left empty in the middle of a row.
    sheet.append([1, '0xCC<&>', 14, 'Completed', 'Three & Co'] + [None] * (len(HEADER) - 6) + ['5G:1'])
    workbook.save(tmp_path / 'appendix.xlsx')

    rows = ca_appendix.xlsx_to_csv(tmp_path / 'appendix.xlsx', tmp_path / 'appendix.csv')

    assert rows == 5
    read = pd.read_csv(tmp_path / 'appendix.csv', dtype=str, keep_default_na=False)
    expected = pd.read_excel(tmp_path / 'appendix.xlsx', dtype=str).fillna('')
    assert list(read.columns) == HEADER
    assert read.to_dict('records') == expected.to_dict('records')


def test_the_fields_of_a_ca_appendix_are_derived_once_typed_and_keyed_by_join_id(client, tmp_path):
    dataset_id, result = add_appendix(tmp_path, 'Q3 CA Appendix', appendix_rows())

    assert result['records'] == 3 and result['join_ids'] == 3
    dataset = core.repository.get_dataset(dataset_id)
    assert dataset['status'] == 'ready' and dataset['stored_path'].endswith('Q3 CA Appendix.parquet')
    assert not (tmp_path / 'input' / 'Q3 CA Appendix.csv').exists()
    summary = ca_appendix.dataset_summary(dict(dataset))
    assert summary['operators'] == {'EE': 2, 'O2 (UK)': 1} and summary['join_ids'] == 3
    fields = duckdb.connect().execute(
        f"SELECT * FROM read_parquet('{ca_appendix.fields_path(core.repository.db_path, dataset_id)}')").df().set_index(ca_appendix.KEY_COLUMN)
    # The identity of the test is the CDR's; every other column is a CA_ field.
    assert 'CA_JOIN_ID' not in fields and 'CA_HomeOperator' not in fields and 'CA_Test_Status' not in fields
    first = fields.loc['0xaa01']
    # The Main values are the value the test had for longest, as numbers.
    assert first['CA_Main_Total_Bandwidth_DL'] == 70 and first['CA_Main_Total_Number_carrier_DL'] == 4
    assert first['CA_NR_PCC_Main_PCI'] == 44 and first['CA_Main_Bands_Combination'] == 'LTE E-UTRA 7/NR BAND 78'
    assert first['CA_Total_Bandwidth_DL_Timeline'] == '[20](0.15)->[70](2.52)'
    assert (first['CA_eNodeB_ID'], first['CA_eNodeB_Changes'], first['CA_gNodeB_ID'], first['CA_gNodeB_Changes']) == (548710, 1, 17029, 0)
    assert math.isnan(fields.loc['0xaa02', 'CA_gNodeB_ID'])
    # A column without values takes the type of the same field of the other carriers.
    assert str(fields['CA_NR_SCC4_Main_Band'].dtype) == 'float64' and str(fields['CA_LTE_PCC_Main_Band'].dtype) != 'float64'


def test_the_cdr_tests_with_its_join_ids_take_its_fields_in_their_copy_and_lose_them_with_it(client, tmp_path):
    cdr = add_data_cdr(tmp_path)
    # Without a CA Appendix there is nothing to write.
    assert ca_appendix.stale_datasets(core.repository) == []
    first, _result = add_appendix(tmp_path, 'Q3 CA Appendix', appendix_rows())
    assert ca_appendix.stale_datasets(core.repository) == [(cdr, 'data')]

    assert ca_appendix.fill_dataset(core.repository, cdr, 'data') == 2
    assert ca_appendix.stale_datasets(core.repository) == []
    values = ca_fields(cdr, ['JOIN_ID', 'Operator', 'CA_Main_Total_Bandwidth_DL', 'CA_Main_Bands_Combination', 'CA_eNodeB_ID'])
    assert values['CA_Main_Total_Bandwidth_DL'].tolist()[:2] == [70.0, 20.0] and math.isnan(values['CA_Main_Total_Bandwidth_DL'][2])
    assert values['CA_Main_Bands_Combination'].tolist()[:2] == ['LTE E-UTRA 7/NR BAND 78', 'LTE E-UTRA 3']
    # The table of the CDR stays empty, with the new columns; SQL reads them from the copy.
    with core.repository.connection() as connection:
        assert connection.execute(f'SELECT COUNT(*) FROM main.dataset_rows_{cdr}').fetchone()[0] == 0
        assert [tuple(row) for row in connection.execute(f'SELECT "Operator", "CA_Main_Total_Bandwidth_DL" FROM dataset_rows_{cdr} '
                                  'WHERE "CA_Main_Total_Bandwidth_DL" > 50').fetchall()] == [('EE', 70.0)]
    assert ca_appendix.matched_by_appendix(core.repository)['tests'] == 2

    # A newer CA Appendix wins for its JOIN_IDs.
    second, _result = add_appendix(tmp_path, 'Q3 CA Appendix v2', appendix_rows(bandwidth=90)[:1])
    assert ca_appendix.stale_datasets(core.repository) == [(cdr, 'data')]
    assert ca_appendix.fill_dataset(core.repository, cdr, 'data') == 2
    assert ca_fields(cdr, ['CA_Main_Total_Bandwidth_DL'])['CA_Main_Total_Bandwidth_DL'].tolist()[:2] == [90.0, 20.0]

    # Deleted, the CDR loses the fields of both.
    for dataset_id in (first, second):
        core.repository.delete_dataset(dataset_id)
    ca_appendix.forget_datasets(core.repository)
    assert not ca_appendix.fields_path(core.repository.db_path, first).parent.exists()
    assert ca_appendix.stale_datasets(core.repository) == [(cdr, 'data')]
    assert ca_appendix.fill_dataset(core.repository, cdr, 'data') == 0
    assert not [column for column in core.repository.list_dataset_row_columns(cdr) if column.startswith('CA_')]
    assert ca_fields(cdr, ['Operator'])['Operator'].tolist() == ['EE', 'O2', 'EE']


def test_the_background_job_writes_the_cdrs_and_logs_them(client, tmp_path):
    cdr = add_data_cdr(tmp_path)
    add_appendix(tmp_path, 'Q3 CA Appendix', appendix_rows())
    queued = []
    assert ca_appendix.queue_fill(core.repository, queued.append)
    assert not ca_appendix.queue_fill(core.repository, queued.append)
    assert ca_appendix.fill_tasks(core.repository.db_path)[0]['id'] == 'ca-appendix-fill'
    while queued:
        queued.pop(0)()
    assert ca_appendix.fill_tasks(core.repository.db_path) == []
    logged = [json.loads(row['details']) for row in core.repository.list_logs() if row['action'] == 'ca_appendix_fields_filled']
    assert logged and logged[0]['dataset_id'] == cdr and logged[0]['tests_with_ca_fields'] == 2


def test_network_insights_reads_the_carriers_of_the_tests():
    frame = pd.DataFrame({
        'CA_Main_Total_Bandwidth_DL': [70.0, 20.0, 140.0], 'CA_Main_Total_Number_carrier_DL': [4.0, 1.0, 2.0],
        'CA_Main_Total_Number_of_LTE_carrier_DL': [3.0, 1.0, None], 'CA_Main_Total_Number_of_NR_carrier_DL': [1.0, None, 2.0],
        'CA_Main_Bands_Combination': ['LTE E-UTRA 7/NR BAND 78', 'LTE E-UTRA 3', 'NR BAND 78/NR BAND 28'],
        'CA_eNodeB_ID': [548710.0, 8125.0, None], 'CA_eNodeB_Changes': [0.0, 0.0, None],
        'CA_gNodeB_ID': [17029.0, None, 17029.0], 'CA_gNodeB_Changes': [0.0, None, 0.0],
        'CA_LTE_PCC_Main_Band': ['LTE E-UTRA 7', 'LTE E-UTRA 3', None], 'CA_LTE_PCC_Main_DL_EARFCN': [2850.0, 1392.0, None],
        'CA_LTE_PCC_Main_Bandwidth': [20.0, 20.0, None], 'CA_LTE_PCC_Main_PCI': [207.0, 284.0, None],
        'CA_NR_PCC_Main_Band': [78.0, None, 78.0], 'CA_NR_PCC_Main_DL_EARFCN': [628032.0, None, 628032.0],
        'CA_NR_PCC_Main_Bandwidth': [100.0, None, 100.0], 'CA_NR_PCC_Main_PCI': [44.0, None, 45.0],
        'CA_NR_SCC1_Main_Band': [None, None, 28.0], 'CA_NR_SCC1_Main_DL_EARFCN': [None, None, 152690.0],
        'CA_NR_SCC1_Main_Bandwidth': [None, None, 10.0], 'CA_NR_SCC1_Main_PCI': [None, None, 45.0],
        'Operator': ['EE', 'O2', 'EE'],
    })
    columns = ni.resolve_source_columns(frame.columns, 'data')
    columns.update(ni.ca_sample_columns(frame.columns))
    samples = ni.normalise_samples(frame, 'data', columns)

    assert samples['ca_lte_cells'][0] == ('B7|2850|20|207',) and samples['ca_nr_cells'][2] == ('n78|628032|100|45', 'n28|152690|10|45')
    assert ni.total_bandwidth(samples, 'ca').tolist() == [70.0, 20.0, 140.0]
    assert ni.ca_combination_label('LTE E-UTRA 7/NR BAND 78') == 'B7 + n78'
    result = ni.carrier_aggregation(samples, samples['operator'], ['EE', 'O2'])
    ee = result['summary'][0]
    assert ee['with_ca'] == 2 and ee['carrier_counts'] == [0, 1, 0, 1, 0] and ee['median_total_mhz'] == 105.0 and ee['nr_ca_share'] == 50.0
    assert result['combinations'][0]['combinations'][0]['bands'] in {'B7 + n78', 'n78 + n28'}
    nr = next(row for row in result['nodes'] if row['column'] == 'EE' and row['technology'] == 'NR')
    # One gNodeB, seen with two carriers (n78 and n28) and two cells of n78 (PCI 44 and 45).
    assert nr['nodes'] == 1 and nr['mean_carriers'] == 2 and nr['cells'] == 3
    assert [band['band'] for band in nr['bands']] == ['n28', 'n78'] or [band['band'] for band in nr['bands']] == ['n78', 'n28']
    assert ni.carrier_aggregation(samples.assign(ca_total_bandwidth=math.nan, ca_carriers=math.nan), samples['operator'], ['EE']) is None
