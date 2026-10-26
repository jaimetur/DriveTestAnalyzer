import io
import json
import os
import stat
import sys
import tarfile
import zipfile
from types import SimpleNamespace

import pytest

import src.DriveTestAnalyzer as core
from src.modules import comment_writers as writers
from src.modules import dashboard_comments as comments
from tests.test_dashboard_comments import prepare_rates_dashboard

FAKE_KIRO = '''#!/bin/sh
if [ "$1" = "--version" ]; then echo "kiro-cli 2.4.0"; exit 0; fi
if [ -z "$KIRO_API_KEY" ]; then echo "not signed in" >&2; exit 1; fi
echo "Thinking..."
cat <<'REPLY'
{reply}
REPLY
'''


def fake_kiro_zip(reply: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        info = zipfile.ZipInfo('kirocli/bin/kiro-cli')
        info.external_attr = (stat.S_IFREG | 0o755) << 16
        archive.writestr(info, FAKE_KIRO.replace('{reply}', json.dumps(reply, ensure_ascii=False)))
        archive.writestr('kirocli/README.txt', 'Kiro CLI')
    return buffer.getvalue()


def fake_kiro_deb() -> bytes:
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode='w:gz') as archive:
        script = FAKE_KIRO.encode()
        info = tarfile.TarInfo('./usr/bin/kiro-cli')
        info.size, info.mode = len(script), 0o755
        archive.addfile(info, io.BytesIO(script))
    members = [('debian-binary', b'2.0\n'), ('control.tar.gz', b''), ('data.tar.gz', data.getvalue())]
    out = io.BytesIO()
    out.write(b'!<arch>\n')
    for name, content in members:
        out.write(f'{name + "/":<16}{0:<12}{0:<6}{0:<6}{100644:<8}{len(content):<10}`\n'.encode())
        out.write(content + (b'\n' if len(content) % 2 else b''))
    return out.getvalue()


RSRP = {'type': 'cdf', 'metric': 'NR RSRP', 'dimensions': [['Operator'], ['Campaign']], 'bucket_edges': [-110, -100, -90, -80], 'series': [
    {'key': [operator, campaign], 'stats': {'n': 900, 'p10': p50 - 12, 'p50': p50, 'p90': p50 + 10, 'mean': p50,
                                            'bucket_shares': [weak, .3, .3, .2, .2 - weak]}}
    for operator, campaign, p50, weak in (('VF', '2026-Q2', -97.6, .094), ('VF', '2026-Q3', -93.8, .051),
                                          ('EE', '2026-Q3', -90.1, .032), ('Three', '2026-Q3', -99.0, .08))]}


def brief(**options):
    return comments.slide_brief([{'index': 0, 'title': 'NR RSRP', 'kpi': 'NR_RSRP', 'model': RSRP, 'hidden': ['Three']}],
                                focus_operators=['VF'], **options)


def test_the_validator_keeps_only_comments_whose_figures_are_facts():
    kept, problems = writers.validate_comments([
        "VF's median NR RSRP is up 3.8 dB vs 2026-Q2 (−97.6 → −93.8 dBm); weak samples fall from 9.4% to 5.1%.",
        'VF improves by 4.4 dB.', 'Three trails the others.', 'x' * 600,
    ], brief())
    assert kept == ["VF's median NR RSRP is up 3.8 dB vs 2026-Q2 (−97.6 → −93.8 dBm); weak samples fall from 9.4% to 5.1%."]
    assert [problem.split(':')[0] for problem in problems] == ['Figures not in the facts (4.4)', 'Names the hidden Three', 'Too long']


@pytest.mark.skipif(sys.platform == 'win32', reason='the fake Kiro CLI is a shell script')
def test_kiro_cli_installs_from_a_package_and_writes_checked_comments(tmp_path):
    good = "VF's median NR RSRP is up 3.8 dB vs 2026-Q2 (−97.6 → −93.8 dBm)."
    installed = writers.install_kiro_cli(tmp_path, 'kirocli-linux.zip', fake_kiro_zip({'comments': [good, 'VF gains 9.9 dB.']}))
    assert installed['version'] == 'kiro-cli 2.4.0'
    assert installed['path'].startswith(str(tmp_path / 'tools' / 'kiro-cli'))
    repository = SimpleNamespace(state={})
    repository.get_application_state = lambda key: repository.state.get(key)
    repository.set_application_state = lambda key, value: repository.state.__setitem__(key, value)
    writers.save_settings(repository, {'enabled': ['kiro_cli'], 'default': 'kiro_cli'})
    writers.save_kiro_cli(repository, installed, 'super')
    assert writers.kiro_cli_status(repository, tmp_path)['version'] == 'kiro-cli 2.4.0'
    without_key = writers.write_comments('kiro_cli', brief(), repository=repository, config_dir=tmp_path, username='ana')
    assert without_key['engine'] == 'rules' and 'Kiro API key in the user menu' in without_key['warning']
    writers.set_user_key(tmp_path, 'kiro_cli', 'Ana', 'ksk_test')
    assert oct(os.stat(tmp_path / writers.CREDENTIALS_FILE).st_mode & 0o777) == '0o600'
    written = writers.write_comments('kiro_cli', brief(), repository=repository, config_dir=tmp_path, username='ana')
    assert written['engine'] == 'kiro_cli' and written['texts'] == [good]
    assert len(written['problems']) == 1 and 'left out' in written['warning']
    # With the key of the server, every user writes with it; without one, Super Admin is asked to save it.
    writers.save_settings(repository, {'enabled': ['kiro_cli'], 'default': 'kiro_cli', 'kiro_key_source': 'server'})
    assert 'Super Admin' in writers.write_comments('kiro_cli', brief(), repository=repository, config_dir=tmp_path, username='ana')['warning']
    writers.set_server_key(tmp_path, 'kiro_cli', 'ksk_server')
    assert writers.write_comments('kiro_cli', brief(), repository=repository, config_dir=tmp_path, username='bob')['engine'] == 'kiro_cli'
    deb = writers.install_kiro_cli(tmp_path, 'kiro-cli.deb', fake_kiro_deb())
    assert deb['version'] == 'kiro-cli 2.4.0'
    with pytest.raises(ValueError, match='no kiro-cli executable'):
        writers.install_kiro_cli(tmp_path, 'other.zip', zipfile_with('other/bin/tool'))


def zipfile_with(name: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr(name, 'x')
    return buffer.getvalue()


def test_claude_writes_with_structured_output_and_the_default_fallback(monkeypatch, tmp_path):
    calls = []
    reply = {'comments': ["VF's median NR RSRP is up 3.8 dB vs 2026-Q2 (−97.6 → −93.8 dBm)."]}

    class FakeMessages:
        def create(self, **request):
            calls.append(request)
            return SimpleNamespace(stop_reason='end_turn', model=request['model'],
                                   content=[SimpleNamespace(type='text', text=json.dumps(reply))],
                                   usage=SimpleNamespace(input_tokens=1200, output_tokens=80))

    class FakeClient:
        def __init__(self, **options):
            self.options = options
            self.beta = SimpleNamespace(messages=FakeMessages())

    import anthropic
    monkeypatch.setattr(anthropic, 'Anthropic', FakeClient)
    texts, details = writers.write_with_claude(brief(), {**writers.DEFAULT_SETTINGS, 'claude_effort': 'low'}, 'sk-test')
    assert texts == reply['comments'] and details == {'model': 'claude-opus-5-5', 'input_tokens': 1200, 'output_tokens': 80}
    request = calls[0]
    assert request['model'] == 'claude-opus-5-5' and request['fallbacks'] == 'default'
    assert request['betas'] == ['server-side-fallback-2026-07-01']
    assert request['output_config'] == {'effort': 'low', 'format': {'type': 'json_schema', 'schema': writers.COMMENTS_SCHEMA}}
    assert 'thinking' not in request and 'Three' in request['messages'][0]['content']
    with pytest.raises(writers.WriterError, match='Claude API key in the user menu'):
        writers.write_with_claude(brief(), writers.DEFAULT_SETTINGS, '', 'user')


def test_super_admin_sets_the_writers_and_users_their_keys(client):
    client.post('/login', data={'username': 'super', 'password': 'super123'})
    page = client.get('/super-admin')
    assert page.status_code == 200 and 'AI Comment Writers' in page.text and 'Rules only' in page.text
    saved = client.post('/super-admin/comment-writers', data={
        'enabled': ['kiro_cli', 'kiro_brief', 'claude'], 'default': 'kiro_cli', 'claude_model': 'claude-sonnet-5-5',
        'claude_effort': 'medium', 'timeout_seconds': '90', 'claude_api_key': 'sk-ant-secret',
    }, follow_redirects=False)
    assert saved.status_code == 303
    assert client.get('/api/ppt-dashboards/comment-engines').json() == {
        'engines': [{'id': 'rules', 'label': 'Rules'}, {'id': 'kiro_cli', 'label': 'Kiro CLI'}, {'id': 'claude', 'label': 'Claude'}],
        'default': 'kiro_cli', 'kiro_brief': True,
    }
    # The key is on the server, never in its database nor in the page.
    assert 'sk-ant-secret' not in json.dumps(writers.load_settings(core.repository))
    assert writers.server_key(core.application_config_dir, 'claude') == 'sk-ant-secret'
    page = client.get('/super-admin').text
    assert 'sk-ant-secret' not in page and 'data-api-keys-open' in page
    # Kiro takes each user's key and Claude the server's by default: the user menu asks only for Kiro.
    assert client.get('/account/api-keys').json() == {'providers': [{'id': 'kiro_cli', 'label': 'Kiro CLI', 'saved': False}]}
    assert client.post('/account/api-keys', data={'kiro_cli': 'ksk_mine', 'claude': 'ignored'}).json() == {'saved': ['kiro_cli'], 'removed': []}
    assert writers.user_key(core.application_config_dir, 'kiro_cli', 'super') == 'ksk_mine'
    assert writers.user_key(core.application_config_dir, 'claude', 'super') == ''
    # With Claude on each user's key, the user menu asks for both.
    client.post('/super-admin/comment-writers', data={
        'enabled': ['kiro_cli', 'claude'], 'default': 'claude', 'claude_key_source': 'user', 'kiro_key_source': 'user',
    })
    assert [item['id'] for item in client.get('/account/api-keys').json()['providers']] == ['kiro_cli', 'claude']
    assert client.post('/account/api-keys', data={'claude': 'sk-ant-mine', 'remove': ['kiro_cli']}).json() == {
        'saved': ['claude'], 'removed': ['kiro_cli']}
    assert writers.user_key(core.application_config_dir, 'claude', 'super') == 'sk-ant-mine'
    assert writers.user_key(core.application_config_dir, 'kiro_cli', 'super') == ''
    # The key of the server stays saved while the writer uses those of the users.
    assert writers.server_key(core.application_config_dir, 'claude') == 'sk-ant-secret'
    events = [(row['action'], json.loads(row['details'])) for row in core.repository.list_logs()]
    saved = [details for action, details in events if action == 'save_comment_writers']
    assert saved[-1]['claude_server_key'] == 'replaced' and saved[0]['claude_key_source'] == 'user'
    assert 'sk-ant' not in json.dumps(events) and 'ksk_' not in json.dumps(events)
    assert [details for action, details in events if action == 'save_user_api_keys'][0] == {'saved': ['Claude'], 'removed': ['Kiro CLI']}


@pytest.mark.skipif(sys.platform == 'win32', reason='the fake Kiro CLI is a shell script')
def test_dashboards_write_with_kiro_and_import_a_kiro_brief(client):
    body = prepare_rates_dashboard(client)
    slide = body['slides'][0]
    reply = {'comments': ['A leads the change: median Mean Data Rate up 33% vs 2026-Q2 (41 → 61).']}
    installed = writers.install_kiro_cli(core.application_config_dir, 'kiro.zip', fake_kiro_zip(reply))
    writers.save_kiro_cli(core.repository, installed, 'super')
    client.post('/super-admin/comment-writers', data={'enabled': ['kiro_cli', 'kiro_brief'], 'default': 'kiro_cli'})
    client.post('/account/api-keys', data={'kiro_cli': 'ksk_mine'})

    generated = client.post('/api/ppt-dashboards/rates/comments/generate', json={'token': body['token'], 'slide': slide['number']})
    assert generated.status_code == 200, generated.text
    assert generated.json()['engine'] == 'kiro_cli'
    assert [item['text'] for item in generated.json()['suggestions']] == reply['comments']
    ruled = client.post('/api/ppt-dashboards/rates/comments/generate', json={'token': body['token'], 'slide': slide['number'], 'engine': 'rules'})
    assert ruled.json()['engine'] == 'rules' and len(ruled.json()['suggestions']) > 1

    started = client.post('/api/ppt-dashboards/rates/comments/kiro-brief', json={'token': body['token']})
    assert started.status_code == 202, started.text
    job = client.get(f"/api/ppt-dashboards/comment-jobs/{started.json()['job_id']}").json()
    archive = zipfile.ZipFile(io.BytesIO(client.get(f"/api/ppt-dashboards/comment-briefs/{job['result']['brief_id']}.zip").content))
    assert {'README.md', 'brief.md', '.kiro/steering/drivetest-comments.md', 'facts.json', 'comments.json'} <= set(archive.namelist())
    facts = json.loads(archive.read('facts.json'))
    filled = json.loads(archive.read('comments.json'))
    filled['slides'][slide['comment_key']] = ['A median Mean Data Rate rises to 61 vs 2026-Q2.', 'A gains 99 points.']
    imported = client.post('/api/ppt-dashboards/rates/comments/kiro-import', data={'mode': 'all'}, files=[
        ('files', ('comments.json', json.dumps(filled).encode(), 'application/json')),
        ('files', ('facts.json', json.dumps(facts).encode(), 'application/json')),
    ])
    assert imported.status_code == 200, imported.text
    result = imported.json()
    assert result['slide_comments'][slide['comment_key']] == ['A median Mean Data Rate rises to 61 vs 2026-Q2.']
    assert result['left_out'] == 1 and result['slide_comment_meta'][slide['comment_key']]['engine'] == 'kiro_brief'
    actions = [row['action'] for row in core.repository.list_logs()]
    assert {'export_kiro_comment_brief', 'import_kiro_comments'} <= set(actions)
    generated_events = [json.loads(row['details']) for row in core.repository.list_logs() if row['action'] == 'generate_dashboard_comments']
    assert {event['engine'] for event in generated_events} == {'kiro_cli', 'rules'}
