"""The dialogs of a transfer every open page shows close everywhere once handled in one of them (ticket #105): the
window with the result of a transfer is seen once per user, which the server keeps."""
import json
from pathlib import Path

import src.DriveTestAnalyzer as core

SECRET = 'transfer-dialogs-test-secret-that-is-long-enough'
HEADERS = {'X-Dashboard-Transfer-Secret': SECRET}


def login(client, username='super', password='super123'):
    client.cookies.clear()
    response = client.post('/login', data={'username': username, 'password': password}, follow_redirects=False)
    assert response.status_code == 303


def logged(action):
    return [json.loads(row['details']) for row in core.repository.list_logs(limit=200) if row['action'] == action]


def rejected_transfer(client) -> str:
    """A received transfer rejected after its preview: one that has finished."""
    offer_id = client.post('/api/import-export/transfers/offers', headers=HEADERS, json={
        'source': 'Team server', 'archive_version': 1, 'kind': 'config', 'content': 'config', 'workspaces': []}).json()['offer_id']
    login(client)
    exported = client.get('/admin/import-export/export?export_target=config')
    assert client.post(f'/admin/import-export/transfers/offers/{offer_id}/accept').status_code == 200
    # Its result cannot be seen before it has finished.
    assert client.post(f'/admin/import-export/transfers/offers/{offer_id}/result-seen', json={}).status_code == 409
    assert client.put(f'/api/import-export/transfers/offers/{offer_id}/package', headers={**HEADERS, 'Content-Type': 'application/zip'},
                      content=exported.content).status_code == 200
    assert client.post(f'/admin/import-export/transfers/offers/{offer_id}/preview/reject').status_code == 200
    return offer_id


def test_the_result_of_a_received_transfer_is_seen_once_per_super_admin(client) -> None:
    offer_id = rejected_transfer(client)
    status = client.get(f'/admin/import-export/transfers/offers/{offer_id}').json()
    assert status['status'] == 'rejected' and status['result_seen'] is False
    assert 'result_seen_by' not in status

    seen = client.post(f'/admin/import-export/transfers/offers/{offer_id}/result-seen', json={'title': 'Incoming Transfer Error'})
    assert seen.status_code == 200 and seen.json() == {'result_seen': True}
    assert client.get(f'/admin/import-export/transfers/offers/{offer_id}').json()['result_seen'] is True
    # Closing it again (in another tab that had not closed it yet) records nothing more.
    assert client.post(f'/admin/import-export/transfers/offers/{offer_id}/result-seen', json={'title': 'Incoming Transfer Error'}).status_code == 200
    [event] = [details for details in logged('transfer_result_seen') if details.get('offer_id') == offer_id]
    assert event == {
        'offer_id': offer_id, 'transfer': 'incoming transfer', 'window': 'Incoming Transfer Error', 'source': 'Team server',
        'content': 'config', 'status': 'rejected', 'result': 'The destination super-admin rejected the transfer after its preview.',
    }

    # It is kept on the server: a page of another browser, or opened later, does not show it again.
    core.TRANSFER_OFFERS.clear()
    assert client.get(f'/admin/import-export/transfers/offers/{offer_id}').json()['result_seen'] is True

    # Each super-admin closes it on their own.
    core.repository.create_user('chief', 'secret123', 'super-admin')
    login(client, 'chief', 'secret123')
    assert client.get(f'/admin/import-export/transfers/offers/{offer_id}').json()['result_seen'] is False
    assert client.post(f'/admin/import-export/transfers/offers/{offer_id}/result-seen', json={}).status_code == 200
    assert client.get(f'/admin/import-export/transfers/offers/{offer_id}').json()['result_seen'] is True
    assert client.post('/admin/import-export/transfers/offers/missing-offer/result-seen', json={}).status_code == 404


def test_the_result_of_a_transfer_to_another_server_is_seen_once(client) -> None:
    login(client, 'admin', 'admin123')
    finished = {'id': 'seen-transfer-job', 'owner': 'admin', 'status': 'ready', 'destination': 'https://team.example:8443',
                'targets': ['config'], 'notice': 'Configuration imported successfully.\nDetails.', 'path': '/tmp/unused-transfer.zip'}
    core.TRANSFER_JOBS['seen-transfer-job'] = finished
    core.TRANSFER_JOBS['running-transfer-job'] = {**finished, 'id': 'running-transfer-job', 'status': 'transferring'}
    core.TRANSFER_JOBS['other-transfer-job'] = {**finished, 'id': 'other-transfer-job', 'owner': 'super'}
    try:
        status = client.get('/admin/import-export/transfers/jobs/seen-transfer-job').json()
        assert status['result_seen'] is False and 'result_seen_by' not in status
        assert client.post('/admin/import-export/transfers/jobs/running-transfer-job/result-seen', json={}).status_code == 409
        assert client.post('/admin/import-export/transfers/jobs/other-transfer-job/result-seen', json={}).status_code == 404
        assert client.post('/admin/import-export/transfers/jobs/seen-transfer-job/result-seen',
                           json={'title': 'Server Transfer Complete'}).status_code == 200
        status = client.get('/admin/import-export/transfers/jobs/seen-transfer-job').json()
        assert status['result_seen'] is True and 'result_seen_by' not in status
        assert client.post('/admin/import-export/transfers/jobs/seen-transfer-job/result-seen', json={}).status_code == 200
        [event] = [details for details in logged('transfer_result_seen') if details.get('job_id') == 'seen-transfer-job']
        assert event == {
            'job_id': 'seen-transfer-job', 'transfer': 'outgoing transfer', 'window': 'Server Transfer Complete',
            'destination': 'https://team.example:8443', 'targets': ['config'], 'status': 'ready',
            'result': 'Configuration imported successfully.',
        }
    finally:
        for job_id in ('seen-transfer-job', 'running-transfer-job', 'other-transfer-job'):
            core.TRANSFER_JOBS.pop(job_id, None)


def test_pages_close_the_transfer_dialogs_handled_in_another_tab() -> None:
    script = (Path(__file__).parents[1] / 'src' / 'web_interface' / 'static' / 'js' / 'core' / 'app.js').read_text(encoding='utf-8')

    # One tab tells the others at once; the server state closes them in other browsers.
    assert "new BroadcastChannel(CHANNEL)" in script
    assert "window.addEventListener('storage', (event) => {" in script
    for key in ('offer:${offer.id}', 'request:${transferRequest.id}', 'preview:${offerId}', 'result:${offerId}', 'job-result:${state.job_id}'):
        assert key in script
    assert 'dismissHandledTransferDialogs(payload, sentAt);' in script
    assert "/result-seen" in script
