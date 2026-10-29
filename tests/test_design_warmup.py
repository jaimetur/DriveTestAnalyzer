import copy
import json
import time
from pathlib import Path

import src.DriveTestAnalyzer as core
import src.modules.ppt_designer as designs_module
from src.modules import ppt_design_cache
from tests.test_design_slides import logged, setup


class InlineThread:
    """Thread stand-in: the warm-up runs when it is started, in the test's own thread (or later, with ``held``)."""
    held = []
    hold = False

    def __init__(self, target=None, args=(), **_kwargs):
        self.target, self.args = target, args

    def start(self):
        if InlineThread.hold:
            InlineThread.held.append(self)
        else:
            self.target(*self.args)


def workspace_path():
    return str(Path(core.active_workspace.database_path).resolve())


def ready(client):
    setup(client)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and (core.repository.get_dataset(1)['status'] != 'ready'
                                           or not core.BACKGROUND_TASK_SCHEDULER.is_idle):
        time.sleep(0.05)


def stored_models():
    charts = ppt_design_cache.root_of(workspace_path()) / 'charts'
    return {path.name for path in charts.glob('*/*.json.gz')}


def test_the_warm_up_keeps_every_design_and_template_and_works_out_only_what_changed(client, monkeypatch):
    monkeypatch.setattr(designs_module, 'Thread', InlineThread)
    monkeypatch.setattr(InlineThread, 'hold', False)
    ready(client)
    # (Entering the Designer gives the template slide ids of its own, which change its charts: done before.)
    assert client.get('/api/ppt-designer/design-a/slides?edit=1').status_code == 200
    assert stored_models() == set()

    core.ppt_design_warm_up_now()
    job = core.ppt_design_warmup_task(workspace_path())
    # Every Design and every template (as PPT Templates → Edit opens it) is prepared and its charts kept; the charts a
    # selection cannot draw are left to the viewer, and the Designs without CDRs of their selection are skipped.
    assert job['status'] == 'ready', job
    designs = json.loads(core.repository.get_workspace_state('ppt_designs_v2'))
    assert job['total'] == len(designs) + len(core.repository.list_report_templates()) == job['done']
    assert job['computed'] > 0
    assert all(ppt_design_cache.has_preparation(workspace_path(), design_id) for design_id in ('design-a', 'design-b'))
    kept = stored_models()
    assert len(kept) >= job['computed']
    assert logged('design_warmup_finished')[0]['status'] == 'ready'
    # Opening a Design as the viewer does finds its preparation and every chart it can draw already kept.
    listed = client.get('/api/ppt-designer').json()['design-a']
    opened = client.post('/api/ppt-designer/prefetched/design-a', json=listed)
    assert opened.status_code == 200, opened.text
    charts = [chart for slide in opened.json()['slides'] for chart in slide['charts'] if chart.get('available')]
    assert charts and all(client.get(f"/api/ppt-designer/chart/{opened.json()['token']}/{chart['index']}").status_code == 200
                          for chart in charts)
    assert len(stored_models()) == len(kept)

    # Nothing changed: the next idle period has nothing to do.
    core.ppt_design_warm_up_now()
    assert core.ppt_design_warmup_task(workspace_path())['id'] == job['id']

    # One chart of design-a changes: only it is worked out again.
    body = client.get('/api/ppt-designer/design-a/slides?edit=1').json()
    edited = copy.deepcopy(body['slide_set'])
    edited['slides'][0]['elements'][0]['chart_title'] = 'Rate in the warm-up'
    assert client.put('/api/ppt-designer/design-a/slides', json={'slide_set': edited}).status_code == 200
    core.ppt_design_warm_up_now()
    again = core.ppt_design_warmup_task(workspace_path())
    assert again['id'] != job['id'] and again['status'] == 'ready', again
    assert again['computed'] == 1 and again['reused'] == job['computed'] + job['reused'] - 1
    assert len(stored_models()) == len(kept) + 1
    # A template opened from PPT Templates → Edit (the defaults of the page) finds its charts kept too.
    item = {'name': 'Design test', 'template': 'Design test', 'nr_mode': 'NSA', 'scope': 'single', 'auto_cdrs': True,
            'filters': {'Campaign': ['@latest-2-campaigns']}, 'sa_campaigns': [], 'custom_fields': [], 'hidden_filters': [],
            'date_from': 'Oldest', 'date_to': 'Newest'}
    preview = client.put('/api/ppt-designer/template-preview', json=item).json()
    prepared = client.post(f"/api/ppt-designer/prepare?design_id={preview['id']}", json=preview['definition']).json()
    for chart in (chart for slide in prepared['slides'] for chart in slide['charts'] if chart.get('available')):
        assert client.get(f"/api/ppt-designer/chart/{prepared['token']}/{chart['index']}").status_code == 200
    assert len(stored_models()) == len(kept) + 1


def test_the_warm_up_pauses_for_other_work_stops_from_its_card_and_goes_on_later(client, monkeypatch):
    monkeypatch.setattr(designs_module, 'Thread', InlineThread)
    monkeypatch.setattr(InlineThread, 'hold', False)
    ready(client)

    # Other background work runs: it pauses at once, and says so in its card for a moment.
    monkeypatch.setattr(type(core.BACKGROUND_TASK_SCHEDULER), 'is_idle', property(lambda _self: False))
    core.ppt_design_warm_up_now()
    job = core.ppt_design_warmup_task(workspace_path())
    assert (job['status'], job['pause_reason']) == ('paused', 'background work')
    card = next(task for task in core._workspace_background_tasks(core.active_workspace) if task['id'].startswith('design-warmup:'))
    assert card['status'] == 'paused' and 'Paused while other background work runs' in card['detail']
    assert 'stop_url' not in card
    monkeypatch.undo()
    monkeypatch.setattr(designs_module, 'Thread', InlineThread)

    # Stopped from its card while it runs: it stops, and goes on (from where it was) the next time the server is idle.
    monkeypatch.setattr(InlineThread, 'hold', True)
    monkeypatch.setattr(InlineThread, 'held', [])
    core.ppt_design_warm_up_now()
    job = core.ppt_design_warmup_task(workspace_path())
    card = next(task for task in core._workspace_background_tasks(core.active_workspace) if task['id'].startswith('design-warmup:'))
    assert card['label'] == 'Warming up PPT Designs' and card['stop_task_id'] == f"design-warmup:{job['id']}"
    stopped = client.post(card['stop_url'], data={'task_id': card['stop_task_id']})
    assert stopped.status_code == 200, stopped.text
    held = InlineThread.held.pop()
    held.target(*held.args)
    assert core.ppt_design_warmup_task(workspace_path())['status'] == 'stopped'
    assert logged('stop_design_warmup')[-1] == {'task_id': job['id']}
    assert client.post(card['stop_url'], data={'task_id': card['stop_task_id']}).status_code == 409

    monkeypatch.setattr(InlineThread, 'hold', False)
    core.ppt_design_warm_up_now()
    resumed = core.ppt_design_warmup_task(workspace_path())
    assert resumed['status'] == 'ready' and resumed['done'] == resumed['total']
    assert resumed['resumed'] is True and any(event['resumed'] for event in logged('design_warmup_started'))
