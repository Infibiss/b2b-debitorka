"""Recovery tokens, tenant setup requests and unified document archive."""
import hashlib
import smtplib

import pytest
from tests.test_api import client, register, invoice
from server.database import database
from server import account_help


@pytest.fixture(autouse=True)
def no_live_service_mail(monkeypatch):
    for key in ('AUTH_SMTP_HOST', 'AUTH_SMTP_FROM', 'AUTH_SMTP_USER', 'AUTH_SMTP_PASSWORD', 'SUPPORT_EMAIL'):
        monkeypatch.delenv(key, raising=False)


def recovery_service(client, monkeypatch):
    client.app.state.config.app_url = 'https://mandato.example'
    client.headers['Origin'] = 'https://mandato.example'
    monkeypatch.setenv('AUTH_SMTP_HOST', 'mail.example')
    monkeypatch.setenv('AUTH_SMTP_FROM', 'accounts@example.ru')
    mail = []
    monkeypatch.setattr(account_help, 'send_recovery', lambda email, link: mail.append((email, link)))
    return mail


def test_recovery_disabled_is_explicit_and_support_is_placeholder(client):
    assert client.get('/api/auth/help').json() == {'recovery_available': False, 'support_email': ''}
    assert client.post('/api/auth/recovery', json={'email': 'unknown@example.ru'}).status_code == 503


def test_recovery_single_use_revokes_sessions_and_hides_account_existence(client, monkeypatch):
    register(client)
    mail = recovery_service(client, monkeypatch)
    known = client.post('/api/auth/recovery', json={'email': 'finance@example.ru'})
    unknown = client.post('/api/auth/recovery', json={'email': 'unknown@example.ru'})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert len(mail) == 1
    token = mail[0][1].split('#reset=')[1]
    assert token not in known.text
    with database(client.app.state.config) as c:
        row = c.execute('SELECT * FROM password_resets').fetchone()
        assert row['token_hash'] == hashlib.sha256(token.encode()).hexdigest()
    # A rapid repeat does not send another email.
    client.post('/api/auth/recovery', json={'email': 'finance@example.ru'})
    assert len(mail) == 1
    old_cookie = client.cookies.get('mandato_session')
    body = {'token': token, 'password': 'A-new-password-2026!'}
    assert client.post('/api/auth/reset-password', json=body).status_code == 204
    assert client.post('/api/auth/reset-password', json=body).status_code == 400
    client.cookies.set('mandato_session', old_cookie)
    assert client.get('/api/auth/me').status_code == 401
    assert client.post('/api/auth/login', json={'email': 'finance@example.ru', 'password': 'Correct-horse-24!'}).status_code == 401
    assert client.post('/api/auth/login', json={'email': 'finance@example.ru', 'password': body['password']}).status_code == 200


def test_expired_token_and_delivery_failure(client, monkeypatch):
    register(client)
    mail = recovery_service(client, monkeypatch)
    client.post('/api/auth/recovery', json={'email': 'finance@example.ru'})
    token = mail[0][1].split('#reset=')[1]
    with database(client.app.state.config, write=True) as c:
        c.execute("UPDATE password_resets SET expires_at='2000-01-01',created_at='2000-01-01'")
    assert client.post('/api/auth/reset-password', json={'token': token, 'password': 'A-new-password-2026!'}).status_code == 400
    def fail(*args):
        raise smtplib.SMTPException('failed')
    monkeypatch.setattr(account_help, 'send_recovery', fail)
    assert client.post('/api/auth/recovery', json={'email': 'finance@example.ru'}).status_code == 202
    with database(client.app.state.config) as c:
        assert c.execute('SELECT * FROM password_resets').fetchone() is None


def test_recovery_checks_origin_and_limits_attempts(client, monkeypatch):
    recovery_service(client, monkeypatch)
    assert client.post('/api/auth/recovery', headers={'Origin': 'https://other.example'}, json={'email': 'unknown@example.ru'}).status_code == 403
    for _ in range(15):
        assert client.post('/api/auth/recovery', json={'email': 'unknown@example.ru'}).status_code == 202
    assert client.post('/api/auth/recovery', json={'email': 'unknown@example.ru'}).status_code == 429


def test_mail_setup_is_durable_scoped_and_manager_only(client):
    user = register(client)
    body = {'email': 'billing@example.ru'}
    assert client.post('/api/mail/setup', headers={'X-CSRF-Token': ''}, json=body).status_code == 403
    first = client.post('/api/mail/setup', json=body)
    assert first.status_code == 201
    saved = first.json()['request']
    assert saved['status'] == 'pending'
    assert client.get('/api/mail/setup').json()['request']['id'] == saved['id']
    assert client.post('/api/mail/setup', json=body).json()['request']['id'] == saved['id']
    with database(client.app.state.config, write=True) as c:
        c.execute("UPDATE workflow_memberships SET role='accountant' WHERE user_id=?", (user['user']['id'],))
    assert client.post('/api/mail/setup', json=body).status_code == 403
    client.post('/api/auth/logout')
    register(client, 'another@example.ru')
    assert client.get('/api/mail/setup').json()['request'] is None


def test_contract_prefill_archive_and_tenant_isolation(client):
    register(client)
    inv = invoice(client)
    client.post('/api/workflow/contracts', json={'counterparty_id': inv['counterparty_id'], 'number': 'П-12/2026', 'invoice_ids': [inv['id']]})
    case = client.post('/api/legal/cases', json={'invoice_id': inv['id']}).json()
    assert case['facts']['contract_number'] == 'П-12/2026'
    assert not case['facts']['business_debt_confirmed']
    client.post(f"/api/portfolio/invoices/{inv['id']}/evidence", json={'kind': 'contract', 'reference': 'Договор П-12/2026', 'occurred_on': inv['issued_on']})
    client.post(f"/api/legal/cases/{case['id']}/evidence", json={'kind': 'performance', 'title': 'УПД № 10', 'reference': 'УПД № 10', 'occurred_on': inv['issued_on']})
    archive = client.get('/api/portfolio/documents', params={'invoice_id': inv['id']})
    assert archive.status_code == 200, archive.text
    assert {row['source'] for row in archive.json()['items']} == {'Первичный документ', 'Доказательство'}
    client.post('/api/auth/logout')
    register(client, 'another@example.ru')
    assert client.get('/api/portfolio/documents').json()['items'] == []
    assert client.get('/api/portfolio/documents', params={'invoice_id': inv['id']}).status_code == 404
