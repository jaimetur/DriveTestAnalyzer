import json
import time
from pathlib import Path

import pandas as pd

import src.DriveTestAnalyzer as core
from src.modules import presentations
from src.modules.repository import local_now_iso


def login(client, username='super', password='super123'):
    client.cookies.clear()
    response = client.post('/login', data={'username': username, 'password': password}, follow_redirects=False)
    assert response.status_code == 303


def session(client, username, role):
    token = f'presentations-{username}-{role}'
    core.SESSIONS[token] = core.SessionUser(username=username, role=role)
    client.cookies.clear()
    client.cookies.set(core.SESSION_COOKIE, token)


def add_dataset(repository, name: str, kind: str, rows: int, campaign: str | None = None) -> int:
    source = Path(repository.db_path).parent / name
    source.write_text('source', encoding='utf-8')
    dataset_id, _created = repository.add_dataset(name, str(source), 'tester')
    frame = pd.DataFrame({'Operator': ['EE'] * rows, 'Campaign': [campaign or ''] * rows, 'score': [1.0] * rows})
    repository.replace_dataset_rows(dataset_id, frame)
    repository.update_dataset_profile(dataset_id, status='ready', progress=100, dataset_kind=kind, nr_mode='NSA', row_count=rows,
                                      column_count=len(frame.columns), processed_at=local_now_iso())
    if campaign:
        repository.replace_cdr_catalogue(dataset_id, vendors=[], vendors_only=[], regions=[], cities=[], campaigns=[campaign])
    return dataset_id


def wait_until(condition, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.05)
    raise AssertionError('The condition was not met in time.')


def test_figures_of_the_workspaces_are_read_and_added_up(client):
    login(client)
    repository = core.repository
    add_dataset(repository, 'data_q1.csv', 'data', 30, 'UK_Q1_2026')
    add_dataset(repository, 'voice_q1.csv', 'voice', 20, 'UK_Q1_2026')
    add_dataset(repository, 'speech_q2.csv', 'speech', 10, 'UK_Q2_2026')
    add_dataset(repository, 'inventory.csv', 'network_inventory', 7)
    add_dataset(repository, 'vodafone.csv', 'mapping_vodafone', 5)
    figures = presentations.workspace_figures(core.active_workspace.database_path)
    assert (figures['cdrs'], figures['cdr_rows'], figures['inventory_rows'], figures['mapping_rows']) == (3, 60, 7, 5)
    # The calls are those of the Data and Voice CDRs, not of the Speech one.
    assert figures['cdr_calls'] == 50
    assert figures['campaigns'] == ['UK_Q1_2026', 'UK_Q2_2026']
    # With no workspace chosen, the figures are those of the workspace with the most CDR rows.
    totals = presentations.presentation_figures(core)
    assert totals['workspaces'] == [core.active_workspace.name]
    assert (totals['cdrs'], totals['cdr_calls'], totals['campaigns']) == (3, 50, 2)
    assert totals['users'] >= 1 and totals['roles'].get('super-admin', 0) >= 1
    assert totals['help_chapters'] > 20 and totals['releases'] > 1 and totals['tests'] > 100
    # A change of a figure gives another key, which generates them again.
    assert presentations.figures_key(totals) != presentations.figures_key({**totals, 'cdrs': 4})


def test_super_admin_chooses_the_workspaces_and_the_help_shows_the_generated_presentations(client, monkeypatch):
    login(client)
    workspace = core.active_workspace
    generated = []

    def fake_generate(self, figures, key, requested_by):
        # What a generation leaves: the manifest of the presentations and their files, in current.
        current = self.root / 'current'
        current.mkdir(parents=True, exist_ok=True)
        (current / 'overview.pptx').write_bytes(b'deck')
        (current / presentations.MANIFEST).write_text(json.dumps({
            'presentations': [{'id': 'overview', 'title': 'Overview', 'file': 'overview.pptx', 'sections': []}],
            'key': key, 'figures': figures, 'generated_at': '2026-10-21T09:00:00+02:00'}), encoding='utf-8')
        generated.append((figures['workspaces'], requested_by))
        with self.lock:
            self.running = False

    monkeypatch.setattr(presentations.PresentationGenerator, 'unavailable', staticmethod(lambda: ''))
    monkeypatch.setattr(presentations.PresentationGenerator, '_generate', fake_generate)
    # Only super-admins choose the workspaces, in Super Admin (not in Application Config).
    assert 'id="presentations"' in client.get('/super-admin').text
    assert 'id="presentations"' not in client.get('/application-config').text
    response = client.post('/super-admin/presentations', data={'workspace_ids': [workspace.id, 'missing']}, follow_redirects=False)
    assert response.status_code == 303 and response.headers['location'] == '/super-admin#presentations'
    assert presentations.chosen_workspace_ids(core.repository) == [workspace.id]
    wait_until(lambda: generated)
    assert generated[0] == ([workspace.name], 'super')
    log = next(row for row in core.repository.list_logs(limit=50) if row['action'] == 'save_presentation_figures')
    assert json.loads(log['details'])['workspaces'] == [workspace.name]
    # The Help shows the generated presentations, and their files come from them.
    manifest = client.get('/api/presentations').json()
    assert manifest['base'] == '/presentations/files' and manifest['generated_at'] and not manifest['updating']
    assert client.get('/presentations/files/overview.pptx').content == b'deck'
    # Unchanged figures do not generate them again; nothing outside the presentations is served.
    client.get('/api/presentations')
    assert len(generated) == 1
    assert client.get('/presentations/files/..%2F..%2Fpresentations.py').status_code == 404
    session(client, 'editor', 'user-editor')
    assert client.post('/super-admin/presentations', data={'workspace_ids': [workspace.id]}).status_code == 403


def test_the_help_shows_the_presentations_of_the_application_until_they_are_generated(client, monkeypatch):
    monkeypatch.setattr(presentations.PresentationGenerator, 'unavailable', staticmethod(lambda: 'Node.js is not installed on this server.'))
    login(client)
    manifest = client.get('/api/presentations').json()
    assert [item['id'] for item in manifest['presentations']] == ['overview', 'one-slider', 'roadmap']
    assert not manifest['updating']
    assert client.get('/presentations/files/roadmap/slide-01.png').headers['content-type'] == 'image/png'
    # Super Admin tells why they are not generated.
    assert 'Node.js is not installed on this server.' in client.get('/super-admin').text
    # A visitor who has not signed in sees them without starting a generation.
    client.cookies.clear()
    assert client.get('/api/presentations').status_code == 200
