from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import src.DriveTestAnalyzer as app_module
from src.modules import cdr_facets
from src.modules.cdr_auto_selection import (
    ALL_CAMPAIGNS, LATEST_CAMPAIGN, LATEST_TWO_CAMPAIGNS, NO_PREVIOUS_CAMPAIGN, PREVIOUS_CAMPAIGN, campaign_values,
    complete_campaign_cdrs, expand_campaign_filter, resolve_campaign_filter, resolve_cdrs,
)
from src.modules.cdr_facets import cascading_options, fill_missing_facets, stored_facets
from src.modules.repository import Repository, local_now_iso
from src.modules.value_maps import ValueMapper
from tests.scoring_fixtures import scoring_configuration


def _login(client) -> None:
    response = client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=False)
    assert response.status_code == 303


def _add_cdr(repository: Repository, tmp_path: Path, *, name: str, kind: str, nr_mode: str = 'NSA',
             campaign: str = 'UK_Q2_2026', stage: str = 'final', rows: list[dict] | None = None) -> int:
    source = tmp_path / name
    source.write_text('test source', encoding='utf-8')
    dataset_id, _created = repository.add_dataset(name, str(source), 'admin')
    frame = pd.DataFrame(rows or [
        {'Operator': 'EE', 'Operator_Vendor': 'EE_Nokia', 'Vendor': 'Nokia', 'Campaign': campaign, 'region': 'London', 'city': 'London', 'JOIN_ID': f'{name}-1'},
        {'Operator': 'Vodafone', 'Operator_Vendor': 'Vodafone_Ericsson', 'Vendor': 'Ericsson', 'Campaign': campaign, 'region': 'North', 'city': 'Leeds', 'JOIN_ID': f'{name}-2'},
    ])
    repository.replace_dataset_rows(dataset_id, frame)
    repository.update_dataset_profile(
        dataset_id, status='ready', progress=100, dataset_kind=kind, nr_mode=nr_mode, cdr_stage=stage,
        row_count=len(frame), column_count=len(frame.columns), processed_at=local_now_iso(),
    )
    column = lambda name: frame[name].dropna().astype(str).tolist() if name in frame else []  # noqa: E731
    repository.replace_cdr_catalogue(
        dataset_id, vendors=column('Operator_Vendor'), vendors_only=column('Vendor'), regions=column('region'),
        cities=column('city'), campaigns=sorted(set(column('Campaign'))), operators=column('Operator'), clusters=[],
    )
    return dataset_id


@pytest.fixture()
def workspace(client, tmp_path, monkeypatch):
    _login(client)
    active = app_module.active_workspace
    repository = Repository(active.database_path, global_db_path=app_module.repository.db_path,
                            workspace_registry_db_path=app_module.workspace_registry.registry_path)
    repository.initialize()
    repository.replace_scoring_configuration(scoring_configuration())
    monkeypatch.setattr(app_module, '_submit_workspace_job', lambda *args, **kwargs: None)
    # Facets are read in a background thread when a list first needs them: read them inline in tests.
    monkeypatch.setattr(cdr_facets, 'request_missing_facets', lambda task_repository, ids: fill_missing_facets(task_repository, ids))
    return {'client': client, 'repository': repository, 'add': lambda **kwargs: _add_cdr(repository, tmp_path, **kwargs)}


def test_cdrs_follow_nr_mode_campaign_and_combined_tables(workspace):
    add = workspace['add']
    repository = workspace['repository']
    q1 = [add(name=f'UK_Q1_2026_{kind}.csv', kind=kind, campaign='UK_Q1_2026') for kind in ('data', 'voice', 'speech')]
    q2_daily = add(name='UK_Voice_20260521.csv', kind='voice', campaign='UK_Q2_2026', stage='daily')
    q2 = [add(name=f'UK_Q2_2026_{kind}.csv', kind=kind, campaign='UK_Q2_2026') for kind in ('data', 'voice', 'speech')]
    sa = add(name='UK_Q2_2026_SA_Data.csv', kind='data', nr_mode='SA', campaign='UK_Q2_SA_2026')

    # The Final CDR of a campaign replaces its Daily CDR; another NR Mode is never chosen.
    chosen = resolve_cdrs(repository, 'NSA', ['UK_Q2_2026'])
    assert sorted(chosen['voice']) == [q2[1]]
    assert q2_daily not in [value for values in chosen.values() for value in values]
    assert sa not in [value for values in resolve_cdrs(repository, 'NSA').values() for value in values]
    # Without a Campaign, every campaign; any spelling of a campaign chooses it.
    assert sorted(value for values in resolve_cdrs(repository, 'NSA').values() for value in values) == sorted(q1 + q2)
    assert sorted(chosen['data']) == sorted(resolve_cdrs(repository, 'NSA', ['2026-Q2'])['data'])
    # The automatic choices follow the newest campaigns.
    assert campaign_values(repository, 'NSA') == ['UK_Q1_2026', 'UK_Q2_2026']
    assert resolve_campaign_filter(repository, 'NSA', [LATEST_CAMPAIGN]) == ['UK_Q2_2026']
    assert resolve_campaign_filter(repository, 'NSA', [LATEST_TWO_CAMPAIGNS]) == ['UK_Q1_2026', 'UK_Q2_2026']
    # Previous campaign is the one before the newest; with a single campaign it chooses none (no CDR, not every one).
    assert resolve_campaign_filter(repository, 'NSA', [PREVIOUS_CAMPAIGN]) == ['UK_Q1_2026']
    assert sorted(value for values in resolve_cdrs(repository, 'NSA', [PREVIOUS_CAMPAIGN]).values() for value in values) == sorted(q1)
    assert expand_campaign_filter([PREVIOUS_CAMPAIGN], ['UK_Q2_2026']) == [NO_PREVIOUS_CAMPAIGN]
    assert expand_campaign_filter([PREVIOUS_CAMPAIGN], []) == []
    assert not any(resolve_cdrs(repository, 'SA', [PREVIOUS_CAMPAIGN]).values())
    # All available campaigns is every campaign of the NR Mode when it is used, also one that arrives later.
    assert resolve_campaign_filter(repository, 'NSA', [ALL_CAMPAIGNS]) == ['UK_Q1_2026', 'UK_Q2_2026']
    q3 = add(name='UK_Q3_2026_Data.csv', kind='data', campaign='UK_Q3_2026')
    assert resolve_campaign_filter(repository, 'NSA', [ALL_CAMPAIGNS]) == ['UK_Q1_2026', 'UK_Q2_2026', 'UK_Q3_2026']
    assert q3 in resolve_cdrs(repository, 'NSA', [ALL_CAMPAIGNS])['data']
    repository.delete_dataset(q3)

    # The In Combined? choice of Workspace decides: a Daily CDR set to Yes is chosen too.
    repository.update_dataset_profile(q2_daily, in_combined='yes')
    assert q2_daily in resolve_cdrs(repository, 'NSA', ['UK_Q2_2026'])['voice']


def test_scoring_leaves_out_campaigns_without_every_type(workspace):
    add = workspace['add']
    complete = [add(name=f'UK_Q1_2026_{kind}.csv', kind=kind, campaign='UK_Q1_2026') for kind in ('data', 'voice', 'speech')]
    add(name='UK_Q2_2026_Data.csv', kind='data', campaign='UK_Q2_2026')
    ids, incomplete = complete_campaign_cdrs(workspace['repository'], 'NSA')
    assert sorted(ids) == sorted(complete)
    assert incomplete == ['2026-Q2']


def test_scoring_previous_campaign_is_the_complete_campaign_before_the_newest(workspace):
    from src.modules.scoring_selection import expand_scoring_campaigns, scoring_auto_cdrs
    add = workspace['add']
    repository = workspace['repository']
    q1 = [add(name=f'UK_Q1_2026_{kind}.csv', kind=kind, campaign='UK_Q1_2026') for kind in ('data', 'voice', 'speech')]
    # Previous campaign with a single complete campaign chooses none (not every one).
    assert expand_scoring_campaigns(repository, 'NSA', [PREVIOUS_CAMPAIGN]) == [NO_PREVIOUS_CAMPAIGN]
    [add(name=f'UK_Q2_2026_{kind}.csv', kind=kind, campaign='UK_Q2_2026') for kind in ('data', 'voice', 'speech')]
    # A newer campaign without every type is left out: the one before the newest complete one is Q1.
    add(name='UK_Q3_2026_Data.csv', kind='data', campaign='UK_Q3_2026')
    assert expand_scoring_campaigns(repository, 'NSA', [PREVIOUS_CAMPAIGN]) == ['UK_Q1_2026']
    chosen = scoring_auto_cdrs(repository, 'NSA', {'Campaign': [PREVIOUS_CAMPAIGN]})
    assert sorted(chosen['dataset_ids']) == sorted(q1)
    assert list(chosen['campaign_presets']) == [LATEST_CAMPAIGN, PREVIOUS_CAMPAIGN, LATEST_TWO_CAMPAIGNS, ALL_CAMPAIGNS]
    assert chosen['campaign_presets'][PREVIOUS_CAMPAIGN] == ['UK_Q1_2026']


def test_filters_cascade_over_every_cdr_of_the_nr_mode_without_reading_rows(workspace, monkeypatch):
    add = workspace['add']
    repository = workspace['repository']
    ids = [add(name='UK_Q1_2026_Data.csv', kind='data', campaign='UK_Q1_2026'),
           add(name='UK_Q2_2026_Data.csv', kind='data', campaign='UK_Q2_2026', rows=[
               {'Operator': 'Three', 'Operator_Vendor': 'Three_Samsung', 'Vendor': 'Samsung', 'Campaign': 'UK_Q2_2026',
                'region': 'Wales', 'city': 'Cardiff', 'JOIN_ID': 'x'}])]
    mapper = ValueMapper.from_repository(repository)
    every = cascading_options(repository, ids, {})
    assert every['Campaign'] == ['UK_Q1_2026', 'UK_Q2_2026']
    # Vendors carry their Vendor Maps labels.
    assert set(every['Vendor']) == {mapper.map('vendor', value) for value in ('Nokia', 'Ericsson', 'Samsung')}
    # Choosing an Operator leaves only its Vendors, Cities and Campaigns; its own list keeps every Operator.
    vodafone = cascading_options(repository, ids, {'Operator': [mapper.map('operator', 'Vodafone')]})
    assert vodafone['Vendor'] == [mapper.map('vendor', 'Ericsson')]
    assert vodafone['City'] == ['Leeds']
    assert vodafone['Campaign'] == ['UK_Q1_2026']
    assert set(vodafone['Operator']) == set(every['Operator'])
    # Once read, the combinations are kept: no list reads the rows of a CDR again.
    found, missing = stored_facets(repository, ids)
    assert not missing and set(found) == set(ids)
    monkeypatch.setattr(cdr_facets, '_read_combinations', lambda *args: pytest.fail('rows read'), raising=False)
    monkeypatch.setattr(cdr_facets, 'read_facets', lambda *args: pytest.fail('rows read'))
    assert cascading_options(repository, ids, {'Campaign': ['2026-Q2']})['Operator'] == [mapper.map('operator', 'Three')]


def test_cdrs_without_combinations_offer_their_catalogue_without_waiting(workspace, monkeypatch):
    repository = workspace['repository']
    dataset_id = workspace['add'](name='UK_Q1_2026_Data.csv', kind='data', campaign='UK_Q1_2026')
    requested = []
    monkeypatch.setattr(cdr_facets, 'request_missing_facets', lambda task_repository, ids: requested.extend(ids))
    mapper = ValueMapper.from_repository(repository)
    options = cascading_options(repository, [dataset_id], {'Operator': ['EE']})
    assert requested == [dataset_id]
    assert set(options['Vendor']) == {mapper.map('vendor', 'Nokia'), mapper.map('vendor', 'Ericsson')}


def test_scoring_cdr_selection_endpoint_chooses_cdrs_and_cascades(workspace):
    add = workspace['add']
    client = workspace['client']
    q1 = [add(name=f'UK_Q1_2026_{kind}.csv', kind=kind, campaign='UK_Q1_2026') for kind in ('data', 'voice', 'speech')]
    q2 = [add(name=f'UK_Q2_2026_{kind}.csv', kind=kind, campaign='UK_Q2_2026') for kind in ('data', 'voice', 'speech')]

    response = client.post('/api/scoring/cdr-selection', json={'nr_mode': 'NSA', 'context_filters': {'Campaign': ['UK_Q1_2026']}})
    assert response.status_code == 200
    body = response.json()
    assert sorted(body['dataset_ids']) == sorted(q1)
    assert body['options']['Campaign'] == ['UK_Q1_2026', 'UK_Q2_2026']

    response = client.post('/api/scoring/cdr-selection', json={'nr_mode': 'NSA', 'default_campaign': True})
    # Another NR Mode starts on Latest campaign: the newest campaign with Data, Voice and Speech CDRs.
    assert response.json()['campaign_selection'] == [LATEST_CAMPAIGN]
    assert sorted(response.json()['dataset_ids']) == sorted(q2)

    vendors = client.post('/api/scoring/cdr-selection', json={'nr_mode': 'NSA', 'context_filters': {'Operator': ['EE']}}).json()
    assert vendors['options']['Vendor'] == [ValueMapper.from_repository(workspace['repository']).map('vendor', 'Nokia')]


def test_scoring_selection_chooses_the_newest_complete_campaign_and_migrates_saved_cdrs(workspace):
    add = workspace['add']
    client = workspace['client']
    repository = workspace['repository']
    q1 = [add(name=f'UK_Q1_2026_{kind}.csv', kind=kind, campaign='UK_Q1_2026') for kind in ('data', 'voice', 'speech')]
    q2 = [add(name=f'UK_Q2_2026_{kind}.csv', kind=kind, campaign='UK_Q2_2026') for kind in ('data', 'voice', 'speech')]

    # A new selection is on Latest campaign: the CDRs of the newest complete campaign.
    selection = client.get('/api/scoring/selection').json()['selection']
    assert selection['context_filters']['Campaign'] == [LATEST_CAMPAIGN]
    assert sorted(selection['dataset_ids']) == sorted(q2)
    assert selection['auto_cdrs'] is True

    # A selection saved when CDRs were chosen by hand keeps choosing them through their campaign.
    from src.modules.scoring_selection import SCORING_SELECTION_STATE_KEY, serialize_scoring_selection
    repository.set_workspace_state(SCORING_SELECTION_STATE_KEY, serialize_scoring_selection({
        'dataset_ids': q1, 'nr_mode': 'NSA', 'aggregation_levels': ['Operator'], 'baseline_operator': 'EE',
        'context_filters': {},
    }))
    selection = client.get('/api/scoring/selection').json()['selection']
    assert selection['context_filters']['Campaign'] == ['UK_Q1_2026']
    assert sorted(selection['dataset_ids']) == sorted(q1)

    # The CDRs of an opened Saved Filter are kept while the panel shows it.
    response = client.put('/api/scoring/selection', json={'selection': {
        'dataset_ids': [q1[0], q1[1], q1[2]], 'auto_cdrs': False, 'nr_mode': 'NSA', 'aggregation_levels': ['Operator'],
        'baseline_operator': 'EE', 'context_filters': {'Campaign': []},
    }})
    assert sorted(response.json()['selection']['dataset_ids']) == sorted(q1)
    assert response.json()['selection']['auto_cdrs'] is False


def _nq_voice(join_ids: list[str], day: str, campaign: str = 'UK_Q3_2026', result: str = 'Failed') -> pd.DataFrame:
    return pd.DataFrame({
        'JOIN_ID': join_ids, 'Operator': ['Vodafone'] * len(join_ids), 'Campaign': [campaign] * len(join_ids),
        'Session_ID_A': list(range(1, len(join_ids) + 1)), 'Call_Status': [result] * len(join_ids),
        'status': [result] * len(join_ids), 'Call_Start_Time': [f'{day} 10:00:00'] * len(join_ids),
    })


def test_nq_calls_show_the_version_of_the_cdr_the_combined_tables_include(workspace):
    from src.modules import non_qualified_calls as nq

    repository = workspace['repository']
    add = workspace['add']
    final = add(name='UK_Voice_Q3_Final.csv', kind='voice', stage='final', rows=_nq_voice(['0xA'], '2026-09-30').to_dict('records'))
    daily = add(name='UK_Voice_20260928.csv', kind='voice', stage='daily', rows=_nq_voice(['0xA'], '2026-09-28').to_dict('records'))

    def latest_dataset() -> int:
        nq.sync_nq_calls(repository)
        with repository.connection() as connection:
            rows = connection.execute(f'SELECT call_key, latest_dataset_id FROM {nq.NQ_CALL_VERSIONS_TABLE}').fetchall()
        assert len(rows) == 1, [tuple(row) for row in rows]
        return int(rows[0]['latest_dataset_id'])

    # The Final CDR of the campaign, which the combined tables include, gives the call its version.
    assert latest_dataset() == final
    # Including the Daily CDR and leaving the Final one out by hand (In Combined?) gives the Daily version, without
    # reading the CDRs again.
    repository.update_dataset_profile(final, in_combined='no')
    repository.update_dataset_profile(daily, in_combined='yes')
    assert nq.nq_index_status(repository)['pending'] == 2
    assert latest_dataset() == daily
    assert nq.nq_index_status(repository)['pending'] == 0


def test_nq_workspace_indexed_before_the_combined_versions_is_migrated(workspace):
    from src.modules import non_qualified_calls as nq

    repository = workspace['repository']
    workspace['add'](name='UK_Voice_Q3_Final.csv', kind='voice', rows=_nq_voice(['0xA'], '2026-09-30').to_dict('records'))
    nq.sync_nq_calls(repository)
    # A workspace indexed by the previous version: its sources have no combined rank and its schema state is older.
    with repository.connection() as connection:
        connection.execute(f'ALTER TABLE {nq.NQ_CALL_SOURCES_TABLE} DROP COLUMN combined_rank')
        connection.execute('UPDATE workspace_state SET value = ? WHERE key = ?', ('2026-10-13.12', nq.SCHEMA_STATE_KEY))
    nq.ensure_nq_tables(repository)
    with repository.connection() as connection:
        assert 'combined_rank' in nq._columns_of(connection, nq.NQ_CALL_SOURCES_TABLE)
    assert nq.filter_options(repository)['nr_mode'] == ['NSA']
    assert nq.available_filter_values(repository, {}, 'admin')['campaign'] == ['UK_Q3_2026']
    nq.sync_nq_calls(repository)
    assert nq.nq_index_status(repository)['pending'] == 0


def test_nq_filter_values_offer_the_nr_mode_first_and_each_mode_its_campaigns(workspace):
    from src.modules import non_qualified_calls as nq

    repository = workspace['repository']
    add = workspace['add']
    add(name='UK_Voice_Q3_Final.csv', kind='voice', rows=_nq_voice(['0xA'], '2026-09-30').to_dict('records'))
    add(name='UK_Voice_Q3_SA_Final.csv', kind='voice', nr_mode='SA',
        rows=_nq_voice(['0xB'], '2026-09-30', campaign='UK_Q3_SA_2026').to_dict('records'))
    nq.sync_nq_calls(repository)
    assert nq.filter_options(repository)['nr_mode'] == ['NSA', 'SA']
    values = nq.available_filter_values(repository, {'nr_mode': ['SA']}, 'admin')
    assert values['campaign'] == ['UK_Q3_SA_2026']
    # Its own choice does not narrow the NR Mode list.
    assert values['nr_mode'] == ['NSA', 'SA']


def test_dashboards_follow_the_newest_campaigns_and_need_no_campaign_predicate(workspace):
    add = workspace['add']
    client = workspace['client']
    q1 = add(name='UK_Q1_2026_Data.csv', kind='data', campaign='UK_Q1_2026')
    q2 = add(name='UK_Q2_2026_Data.csv', kind='data', campaign='UK_Q2_2026')
    q3 = add(name='UK_Q3_2026_Data.csv', kind='data', campaign='UK_Q3_2026')
    import src.modules.ppt_dashboards  # noqa: F401 - registers the module
    resolve = core_runtime_definition()
    latest_two = resolve({'name': 'D', 'template': 'T', 'technology': 'nsa', 'auto_cdrs': True,
                          'filters': {'Campaign': ['@latest-2-campaigns'], 'City': ['London']}}, workspace['repository'])
    assert latest_two['datasets']['data'] == [q3, q2]
    # The chosen CDRs hold only chosen campaigns: their rows need no Campaign predicate.
    assert latest_two['filters'] == {'City': ['London']}
    one = resolve({'name': 'D', 'template': 'T', 'technology': 'nsa', 'auto_cdrs': True,
                   'filters': {'Campaign': ['2026-Q1']}}, workspace['repository'])
    assert one['datasets']['data'] == [q1] and one['filters'] == {}
    # A Dashboard saved when CDRs were chosen by hand takes their campaigns.
    migrated = resolve({'name': 'D', 'template': 'T', 'technology': 'nsa', 'datasets': {'data': [q2]}}, workspace['repository'])
    assert migrated['datasets']['data'] == [q2]
    assert client.get('/ppt-dashboards').status_code == 200


def test_dashboards_saved_with_main_cities_use_the_main_cities_of_the_workspace(workspace):
    import json

    import src.modules.ppt_dashboards  # noqa: F401 - registers the module
    repository = workspace['repository']
    workspace['add'](name='UK_Q1_2026_Data.csv', kind='data', campaign='UK_Q1_2026')
    resolve = core_runtime_definition()
    dashboard = {'name': 'D', 'template': 'T', 'technology': 'nsa', 'auto_cdrs': True,
                 'filters': {'City': ['@main-cities'], 'Campaign': ['UK_Q1_2026']}}
    # Without Main Cities, every city; then the Main Cities of the workspace whenever the Dashboard is used.
    assert 'City' not in resolve(dashboard, repository)['filters']
    repository.set_main_cities(['London', 'Leeds'])
    assert resolve(dashboard, repository)['filters']['City'] == ['London', 'Leeds']
    repository.set_main_cities(['Bristol'])
    assert resolve(dashboard, repository)['filters']['City'] == ['Bristol']
    # A Dashboard saved before with exactly the Main Cities of then gets the Main Cities choice, once.
    repository.set_workspace_state('ppt_dashboards_v2', json.dumps({
        'a': {**dashboard, 'filters': {'City': ['bristol']}}, 'b': {**dashboard, 'filters': {'City': ['Bristol', 'Leeds']}}}))
    repository.set_workspace_state('ppt_dashboard_main_cities_reference_v1', '0')
    stored = app_module.dashboard_reporting.list_dashboards(repository)
    assert stored['a']['filters']['City'] == ['@main-cities'] and stored['b']['filters']['City'] == ['Bristol', 'Leeds']
    assert repository.get_workspace_state('ppt_dashboard_main_cities_reference_v1') == '1'


def core_runtime_definition():
    """The Dashboards' runtime_dashboard_definition, reached through a registered route closure."""
    for route in app_module.app.routes:
        endpoint = getattr(route, 'endpoint', None)
        if getattr(endpoint, '__name__', '') == 'prefetched_dashboard':
            closure = {name: cell.cell_contents for name, cell in zip(endpoint.__code__.co_freevars, endpoint.__closure__ or ())}
            return closure['runtime_dashboard_definition']
    raise AssertionError('The PPT Dashboards routes are not registered.')


def test_reporting_jobs_saved_with_cdrs_choose_them_by_their_campaigns(workspace):
    from src.modules.scoring_reports import default_report_configuration

    add = workspace['add']
    client = workspace['client']
    q1 = add(name='UK_Q1_2026_Voice.csv', kind='voice', campaign='UK_Q1_2026')
    q2 = add(name='UK_Q2_2026_Data.csv', kind='data', campaign='UK_Q2_2026')
    definition = {
        'dashboards': [{'dashboard_id': 'd1', 'datasets': {'voice': [q1]}, 'filters': {'Operator': ['EE']}}],
        'network_insights': [{'cdr_selection': 'newest', 'selection': {'datasets': {'data': [q2]}}}],
        'scoring': [{'nr_mode': 'NSA', 'dataset_ids': [q1, q2], 'report': default_report_configuration()}],
        'modules': {'non_qualified_calls': {'enabled': True, 'formats': ['powerpoint'], 'options': {'filters': {'datasets': [str(q1)]}}}},
    }
    created = client.post('/api/reporting/tasks', json={'name': 'Legacy CDRs', 'schedule': {'mode': 'manual'}, 'definition': definition})
    assert created.status_code == 200, created.text
    task = next(task for task in client.get('/api/reporting/state').json()['tasks'] if task['name'] == 'Legacy CDRs')
    migrated = task['definition']
    assert migrated['dashboards'][0]['filters'] == {'Operator': ['EE'], 'Campaign': ['UK_Q1_2026']}
    assert (migrated['dashboards'][0]['datasets'], migrated['dashboards'][0]['auto_cdrs']) == ({}, True)
    # Network Insights filters its samples by the campaign as the Campaign Maps show it.
    assert migrated['network_insights'][0]['selection']['campaigns'] == ['2026-Q2']
    assert migrated['network_insights'][0]['selection']['datasets'] == {}
    assert migrated['scoring'][0]['campaigns'] == ['UK_Q1_2026', 'UK_Q2_2026']
    assert migrated['scoring'][0]['dataset_ids'] == []
    assert migrated['modules']['non_qualified_calls']['options']['filters'] == {'nr_mode': ['NSA'], 'campaign': ['UK_Q1_2026']}
    # The editor previews the CDRs an entry uses now.
    preview = client.post('/api/reporting/auto-cdrs', json={'nr_mode': 'NSA', 'campaigns': ['UK_Q2_2026']}).json()
    assert preview['cdrs'] == {'data': ['UK_Q2_2026_Data.csv'], 'voice': [], 'speech': []}


def test_a_saved_filter_keeps_its_campaign_choice_and_follows_it(workspace):
    from src.modules import saved_filters
    add = workspace['add']
    client = workspace['client']
    repository = workspace['repository']
    q1 = [add(name=f'UK_Q1_2026_{kind}.csv', kind=kind, campaign='UK_Q1_2026') for kind in ('data', 'voice', 'speech')]
    q2 = [add(name=f'UK_Q2_2026_{kind}.csv', kind=kind, campaign='UK_Q2_2026') for kind in ('data', 'voice', 'speech')]
    selection = {'dataset_ids': q1 + q2, 'aggregation_levels': ['Operator'], 'nr_mode': 'NSA', 'baseline_operator': 'EE',
                 'context_filters': {'Campaign': [ALL_CAMPAIGNS]}}

    saved = client.post('/api/scoring/saved-filters', json=selection).json()['saved_filter']

    # The choice is kept as such (not the campaigns of this moment); its campaigns and CDRs are resolved now.
    stored = saved_filters.get_saved_filter(repository, saved['id'], include_internal_snapshot=True)
    assert stored['context_filters']['Campaign'] == [ALL_CAMPAIGNS]
    assert stored['resolved_campaigns'] == ['UK_Q1_2026', 'UK_Q2_2026']
    assert sorted(stored['dataset_ids']) == sorted(q1 + q2)
    match = client.post('/api/scoring/saved-filters/match', json=selection).json()['saved_filter']
    assert match['id'] == saved['id']
    saved_filters.calculate_saved_filter(repository, saved['id'])

    # A campaign that arrives later is taken when the Saved Filter is opened again: the same Saved Filter.
    q3 = [add(name=f'UK_Q3_2026_{kind}.csv', kind=kind, campaign='UK_Q3_2026') for kind in ('data', 'voice', 'speech')]
    assert saved_filters.refresh_saved_filter(repository, saved['id']) == (True, '')
    followed = saved_filters.get_saved_filter(repository, saved['id'])
    assert followed['selection_key'] == stored['selection_key']
    assert sorted(followed['dataset_ids']) == sorted(q1 + q2 + q3)
    assert followed['resolved_campaigns'] == ['UK_Q1_2026', 'UK_Q2_2026', 'UK_Q3_2026']
    assert [item['id'] for item in saved_filters.list_saved_filters(repository)] == [saved['id']]
    # Previous campaign with a single campaign stands for none: it is not saved as every campaign.
    response = client.post('/api/scoring/saved-filters', json={**selection, 'nr_mode': 'SA', 'dataset_ids': [],
                                                                'context_filters': {'Campaign': [PREVIOUS_CAMPAIGN]}})
    assert response.status_code == 400
