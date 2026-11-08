"""Explicit registration acceptance is versioned and atomic with the identity."""
from datetime import datetime, timezone

import pytest

from tests.test_api import client
from server.database import database

CURRENT_VERSION = '2026-11-08'


def payload(**changes):
    return {'name': 'Анна', 'company': 'Компания', 'email': 'acceptance@example.ru',
            'password': 'Correct-horse-24!', 'terms_accepted': True,
            'terms_version': CURRENT_VERSION, 'personal_data_consent': True,
            'consent_version': CURRENT_VERSION} | changes


def test_explicit_registration_acceptance_is_durable_scoped_and_never_overwritten(client):
    before = datetime.now(timezone.utc)
    response = client.post('/api/auth/register', json=payload())
    assert response.status_code == 201, response.text
    user = response.json()['user']
    with database(client.app.state.config) as c:
        row = dict(c.execute('SELECT * FROM registration_acceptances WHERE user_id=?', (user['id'],)).fetchone())
        actual_tenant = c.execute('SELECT tenant_id FROM users WHERE id=?', (user['id'],)).fetchone()[0]
    assert row['tenant_id'] == actual_tenant
    assert row['terms_version'] == CURRENT_VERSION
    with database(client.app.state.config) as c:
        consent = dict(c.execute('SELECT * FROM personal_data_consents WHERE user_id=?', (user['id'],)).fetchone())
    assert consent['document_version'] == CURRENT_VERSION and consent['tenant_id'] == actual_tenant
    assert before <= datetime.fromisoformat(row['accepted_at']) <= datetime.now(timezone.utc)
    assert client.post('/api/auth/register', json=payload()).status_code == 409
    assert client.post('/api/auth/login', json={'email': payload()['email'], 'password': payload()['password']}).status_code == 200
    with database(client.app.state.config) as c:
        assert dict(c.execute('SELECT * FROM registration_acceptances WHERE user_id=?', (user['id'],)).fetchone()) == row
        assert c.execute('SELECT COUNT(*) FROM registration_acceptances WHERE user_id=?', (user['id'],)).fetchone()[0] == 1


@pytest.mark.parametrize('fields', [{}, {'terms_accepted': None, 'terms_version': None}])
def test_legacy_registration_without_explicit_acceptance_does_not_invent_consent(client, fields):
    body = {key: value for key, value in payload().items() if key not in ('terms_accepted', 'terms_version', 'personal_data_consent', 'consent_version')} | fields
    response = client.post('/api/auth/register', json=body)
    assert response.status_code == 201, response.text
    with database(client.app.state.config) as c:
        assert c.execute('SELECT COUNT(*) FROM registration_acceptances WHERE user_id=?', (response.json()['user']['id'],)).fetchone()[0] == 0


@pytest.mark.parametrize('fields', [
    {'terms_accepted': False}, {'terms_accepted': 1}, {'terms_accepted': 'true'},
    {'terms_accepted': None}, {'terms_version': None}, {'terms_version': '2026-11-03'},
    {'terms_version': ' 2026-11-04 '}, {'terms_accepted': 'omit'}, {'terms_version': 'omit'},
    {'terms_accepted': None, 'terms_version': 'omit'}, {'terms_accepted': 'omit', 'terms_version': None},
])
def test_registration_rejects_false_coerced_unpaired_or_unknown_version_acceptance(client, fields):
    body = payload() | fields
    body = {key: value for key, value in body.items() if value != 'omit'}
    response = client.post('/api/auth/register', json=body)
    assert response.status_code == 422, response.text
    with database(client.app.state.config) as c:
        assert c.execute('SELECT COUNT(*) FROM users WHERE email=?', (body['email'],)).fetchone()[0] == 0


def test_acceptance_and_registration_rollback_together_on_session_failure(client, monkeypatch):
    from server import main
    with database(client.app.state.config) as c:
        before = {table: c.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                  for table in ('users', 'tenants', 'registration_acceptances', 'sessions')}
    def fail_session(*args, **kwargs):
        raise RuntimeError('Simulated session failure after acceptance insert')
    monkeypatch.setattr(main, 'create_session', fail_session)
    with pytest.raises(RuntimeError, match='Simulated session failure'):
        client.post('/api/auth/register', json=payload())
    with database(client.app.state.config) as c:
        after = {table: c.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                 for table in before}
    assert after == before


@pytest.mark.parametrize('fields', [{'personal_data_consent': None}, {'personal_data_consent': False},
                                    {'personal_data_consent': 1}, {'consent_version': None}])
def test_terms_alone_never_create_an_account_without_personal_data_consent(client, fields):
    assert client.post('/api/auth/register', json=payload(**fields)).status_code == 422
