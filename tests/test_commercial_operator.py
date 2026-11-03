"""Private operator queue never sends mail or destroys requested tenant data."""
import json
import os
from pathlib import Path
import subprocess
import sys

from tests.test_api import client, register
from server.database import database

ROOT = Path(__file__).resolve().parents[1]


def command(*args, env=None):
    return subprocess.run([sys.executable, str(ROOT / 'scripts/commercial_requests.py'), *args],
                          env=env, capture_output=True, text=True, timeout=20)


def lead(client, kind='demo', **changes):
    response = client.post('/api/commercial/requests', json={
        'kind': kind, 'name': 'Анна', 'email': 'private@example.ru', 'company': 'Компания',
        'note': 'Нужна встреча\u001b[31m', 'consent': True} | changes)
    assert response.status_code == 201, response.text
    return response.json()


def test_operator_default_queue_redacts_contacts_and_explicit_contact_output_is_safe(client):
    first = lead(client)
    result = command('list')
    assert result.returncode == 0, result.stderr
    items = json.loads(result.stdout)['items']
    assert len(items) == 1 and items[0]['id'] == first['id'] and items[0]['status'] == 'pending'
    assert 'private@example.ru' not in result.stdout and 'email' not in items[0] and 'note' not in items[0]
    detailed = command('list', '--include-contact')
    assert detailed.returncode == 0, detailed.stderr
    contact = json.loads(detailed.stdout)['items'][0]
    assert contact['email'] == 'private@example.ru' and contact['note'] == 'Нужна встреча\u001b[31m'
    assert '\u001b' not in detailed.stdout


def test_operator_handles_exact_request_idempotently_preserving_public_status(client):
    first = lead(client)
    args = ('mark-handled', '--kind', 'demo', '--request', first['id'], '--owner', 'operator-1', '--reference', 'CRM-143')
    result = command(*args)
    assert result.returncode == 0, result.stderr
    handled = json.loads(result.stdout)
    assert handled['status'] == 'handled' and handled['owner'] == 'operator-1' and handled['reference'] == 'CRM-143'
    assert 'email' not in handled
    assert json.loads(command(*args).stdout) == handled
    assert json.loads(command('list').stdout)['items'] == []
    listed = json.loads(command('list', '--state', 'handled').stdout)['items']
    assert listed[0]['id'] == first['id']
    conflict = command(*args[:-1], 'CRM-CHANGED')
    assert conflict.returncode != 0
    with database(client.app.state.config) as c:
        assert c.execute('SELECT status FROM commercial_requests WHERE id=?', (first['id'],)).fetchone()[0] == 'requested'
        assert c.execute('SELECT COUNT(*) FROM commercial_request_handling').fetchone()[0] == 1


def test_operator_kind_scope_limit_and_missing_request_fail_closed(client):
    first = lead(client)
    custom = lead(client, 'custom')
    assert [item['id'] for item in json.loads(command('list', '--kind', 'custom').stdout)['items']] == [custom['id']]
    assert len(json.loads(command('list', '--limit', '1').stdout)['items']) == 1
    base = ('mark-handled', '--owner', 'operator', '--reference', 'CRM-12')
    assert command(*base, '--kind', 'custom', '--request', first['id']).returncode != 0
    assert command(*base, '--kind', 'demo', '--request', '00000000-0000-0000-0000-000000000000').returncode != 0
    assert command(*base, '--kind', 'demo', '--request', "' OR 1=1 --").returncode != 0
    assert command('list', '--limit', '10000').returncode != 0
    assert command(*base, '--kind', 'demo', '--request', first['id'], '--owner', '\u001b').returncode != 0
    with database(client.app.state.config) as c:
        assert c.execute('SELECT COUNT(*) FROM commercial_request_handling').fetchone()[0] == 0


def test_operator_deletion_queue_includes_requester_only_when_explicit_and_does_not_delete(client):
    user = register(client)
    ticket = client.post('/api/commercial/deletion-request', json={'confirmation': 'УДАЛИТЬ', 'consent': True}).json()
    response = command('list', '--kind', 'deletion', '--include-contact')
    assert response.returncode == 0, response.stderr
    item = json.loads(response.stdout)['items'][0]
    assert item['id'] == ticket['id'] and item['email'] == user['user']['email']
    result = command('mark-handled', '--kind', 'deletion', '--request', ticket['id'], '--owner', 'privacy-operator', '--reference', 'PRIVACY-12')
    assert result.returncode == 0, result.stderr
    assert client.get('/api/auth/me').status_code == 200
    assert client.get('/api/commercial/account').json()['deletion_request'] == ticket
    with database(client.app.state.config) as c:
        assert c.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 1


def test_operator_refuses_missing_database_without_creating_files(tmp_path):
    missing = tmp_path / 'missing.sqlite3'
    result = command('list', env=os.environ | {'DATABASE_PATH': str(missing), 'DATABASE_URL': '', 'APP_ENV': 'test'})
    assert result.returncode != 0 and not missing.exists()
    assert 'Traceback' not in result.stderr


def test_operator_schema_error_does_not_dump_traceback_or_initialize_database(tmp_path):
    unrelated = tmp_path / 'unrelated.sqlite3'
    unrelated.write_bytes(b'')
    result = command('list', env=os.environ | {'DATABASE_PATH': str(unrelated), 'DATABASE_URL': '', 'APP_ENV': 'test'})
    assert result.returncode != 0 and 'Traceback' not in result.stderr
    assert 'Queue unavailable' in result.stderr and unrelated.read_bytes() == b''
