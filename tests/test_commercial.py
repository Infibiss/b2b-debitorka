"""Commercial flows persist tenant-scoped simulated entitlements, never payments."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest

from tests.test_api import client, register
from server.database import database


@pytest.fixture(autouse=True)
def sandbox_only(monkeypatch):
    monkeypatch.delenv('COMMERCIAL_PAYMENT_MODE', raising=False)


def order(client, plan='start', key='checkout-0001'):
    response = client.post('/api/commercial/orders', json={'plan_id': plan, 'consent': True, 'idempotency_key': key})
    assert response.status_code == 201, response.text
    return response.json()


def test_public_catalog_is_authoritative_and_contains_custom(client):
    response = client.get('/api/commercial/plans')
    assert response.status_code == 200
    catalog = response.json()
    assert catalog['trial_days'] == 14 and catalog['payment_mode'] == 'sandbox'
    assert [(p['id'], p['price_monthly'], p['active_invoice_limit'], p['user_limit']) for p in catalog['items']] == [
        ('start', 990000, 100, 2), ('team', 1990000, 500, 5), ('scale', 3990000, 2000, 15), ('custom', None, None, None)]
    assert all(p['currency'] == 'RUB' for p in catalog['items'])


def test_demo_request_is_durable_private_and_validated(client):
    body = {'kind': 'demo', 'name': 'Анна', 'email': 'DEMO@example.ru', 'company': 'Компания', 'note': 'Показать сервис', 'consent': True}
    response = client.post('/api/commercial/requests', json=body)
    assert response.status_code == 201, response.text
    assert response.json()['status'] == 'requested'
    assert 'email' not in response.json() and 'DEMO@example.ru' not in response.text
    with database(client.app.state.config) as c:
        row = c.execute('SELECT * FROM commercial_requests').fetchone()
        assert row['email'] == 'demo@example.ru' and row['consent_at']
    for change in ({'consent': False}, {'consent': 'true'}, {'email': 'bad'}, {'name': '\n'}, {'kind': 'unknown'}, {'amount': 1}):
        assert client.post('/api/commercial/requests', json=body | change).status_code == 422


def test_public_request_origin_and_rate_limit(client):
    client.app.state.config.app_url = 'https://mandato.example'
    body = {'kind': 'custom', 'name': 'Анна', 'email': 'demo@example.ru', 'consent': True}
    assert client.post('/api/commercial/requests', headers={'Origin': 'https://other.example'}, json=body).status_code == 403
    for _ in range(15):
        assert client.post('/api/commercial/requests', headers={'Origin': 'https://mandato.example'}, json=body).status_code == 201
    assert client.post('/api/commercial/requests', headers={'Origin': 'https://mandato.example'}, json=body).status_code == 429


def test_trial_starts_once_for_tenant_and_needs_manager_and_csrf(client):
    assert client.get('/api/commercial/account').status_code == 401
    user = register(client)
    before = client.get('/api/commercial/account').json()
    assert before['status'] == 'none' and before['trial']['available']
    assert client.post('/api/commercial/trial', headers={'X-CSRF-Token': ''}, json={}).status_code == 403
    response = client.post('/api/commercial/trial', json={})
    assert response.status_code == 200, response.text
    started = response.json()
    assert started['status'] == 'trial' and not started['trial']['available']
    assert datetime.fromisoformat(started['trial']['ends_at']) - datetime.fromisoformat(started['trial']['started_at']) == timedelta(days=14)
    assert started['plan']['id'] == 'team'
    assert client.post('/api/commercial/trial', json={}).status_code == 409
    with database(client.app.state.config, write=True) as c:
        c.execute("UPDATE commercial_accounts SET trial_ends_at='2000-01-01T00:00:00+00:00' WHERE tenant_id=(SELECT tenant_id FROM users WHERE id=?)", (user['user']['id'],))
    assert client.get('/api/commercial/account').json()['status'] == 'trial_expired'
    assert client.post('/api/commercial/trial', json={}).status_code == 409
    with database(client.app.state.config, write=True) as c:
        c.execute("UPDATE workflow_memberships SET role='accountant' WHERE user_id=?", (user['user']['id'],))
    assert not client.get('/api/commercial/account').json()['can_manage']
    assert client.post('/api/commercial/trial', json={}).status_code == 403


def test_orders_snapshot_price_idempotency_and_never_call_real_billing(client):
    register(client)
    first = order(client)
    assert first['amount'] == 990000 and first['status'] == 'pending'
    assert first['payment_mode'] == 'sandbox' and first['currency'] == 'RUB'
    assert order(client)['id'] == first['id']
    assert client.post('/api/commercial/orders', json={'plan_id': 'team', 'consent': True, 'idempotency_key': 'checkout-0001'}).status_code == 409
    for change in ({'plan_id': 'custom'}, {'plan_id': 'unknown'}, {'amount': 1}, {'consent': False}, {'consent': 1}, {'idempotency_key': 'x'}):
        response = client.post('/api/commercial/orders', json={'plan_id': 'start', 'consent': True, 'idempotency_key': 'checkout-new1'} | change)
        assert response.status_code == 422, response.text
    response = client.post(f"/api/commercial/orders/{first['id']}/sandbox-confirm", json={})
    assert response.status_code == 200, response.text
    confirmed = response.json()
    assert confirmed['order']['status'] == 'sandbox_confirmed'
    assert confirmed['account']['status'] == 'sandbox_active'
    assert confirmed['account']['subscription']['auto_renew'] is False
    assert confirmed['account']['subscription']['order_id'] == first['id']
    assert client.post(f"/api/commercial/orders/{first['id']}/sandbox-confirm", json={}).json() == confirmed
    assert client.post('/api/commercial/trial', json={}).status_code == 409
    with database(client.app.state.config) as c:
        assert c.execute('SELECT COUNT(*) FROM payments').fetchone()[0] == 0


def test_order_and_account_tenant_isolation_and_permissions(client):
    user = register(client)
    first = order(client)
    with database(client.app.state.config, write=True) as c:
        c.execute("UPDATE workflow_memberships SET role='accountant' WHERE user_id=?", (user['user']['id'],))
    for path, body in (('/orders', {'plan_id': 'start', 'consent': True, 'idempotency_key': 'another-key'}), (f"/orders/{first['id']}/sandbox-confirm", {}), (f"/orders/{first['id']}/cancel", {}), ('/cancel', {'consent': True}), ('/deletion-request', {'confirmation': 'УДАЛИТЬ', 'consent': True})):
        assert client.post('/api/commercial' + path, json=body).status_code == 403
    client.post('/api/auth/logout')
    register(client, 'another@example.ru')
    assert client.get('/api/commercial/account').json()['orders'] == []
    assert client.get('/api/commercial/account').json()['status'] == 'none'
    assert client.post(f"/api/commercial/orders/{first['id']}/sandbox-confirm", json={}).status_code == 404
    assert client.post(f"/api/commercial/orders/{first['id']}/cancel", json={}).status_code == 404
    assert order(client)['id'] != first['id']


def test_cancel_is_idempotent_and_prevents_order_reactivation(client):
    register(client)
    first = order(client)
    second = order(client, 'team', 'checkout-0002')
    confirmation = client.post(f"/api/commercial/orders/{second['id']}/sandbox-confirm", json={})
    assert confirmation.status_code == 200
    assert client.post(f"/api/commercial/orders/{first['id']}/sandbox-confirm", json={}).status_code == 409
    assert client.post(f"/api/commercial/orders/{second['id']}/cancel", json={}).status_code == 409
    assert client.post('/api/commercial/cancel', json={'consent': False}).status_code == 422
    canceled = client.post('/api/commercial/cancel', json={'consent': True})
    assert canceled.status_code == 200, canceled.text
    assert canceled.json()['status'] == 'canceled'
    assert client.post('/api/commercial/cancel', json={'consent': True}).json() == canceled.json()
    repeated = client.post(f"/api/commercial/orders/{second['id']}/sandbox-confirm", json={})
    assert repeated.status_code == 200 and repeated.json()['account']['status'] == 'canceled'
    assert client.post('/api/commercial/trial', json={}).status_code == 409
    third = order(client, 'scale', 'checkout-0003')
    assert client.post(f"/api/commercial/orders/{third['id']}/cancel", json={}).json()['status'] == 'canceled'
    assert client.post(f"/api/commercial/orders/{third['id']}/sandbox-confirm", json={}).status_code == 409


def test_trial_cancel_cannot_restart_and_subscription_expiry_is_explicit(client):
    user = register(client)
    client.post('/api/commercial/trial', json={})
    assert client.post('/api/commercial/cancel', json={'consent': True}).json()['status'] == 'canceled'
    assert client.post('/api/commercial/trial', json={}).status_code == 409
    first = order(client)
    client.post(f"/api/commercial/orders/{first['id']}/sandbox-confirm", json={})
    with database(client.app.state.config, write=True) as c:
        c.execute("UPDATE commercial_accounts SET subscription_ends_at='2000-01-01T00:00:00+00:00' WHERE tenant_id=(SELECT tenant_id FROM users WHERE id=?)", (user['user']['id'],))
    account = client.get('/api/commercial/account').json()
    assert account['status'] == account['subscription']['status'] == 'sandbox_expired'


def test_deletion_request_requires_confirmation_is_durable_and_non_destructive(client):
    register(client)
    assert client.post('/api/commercial/deletion-request', json={'confirmation': 'yes', 'consent': True}).status_code == 422
    body = {'confirmation': 'УДАЛИТЬ', 'consent': True}
    response = client.post('/api/commercial/deletion-request', json=body)
    assert response.status_code == 201, response.text
    assert response.json()['status'] == 'requested'
    assert client.post('/api/commercial/deletion-request', json=body).json() == response.json()
    assert client.get('/api/commercial/account').json()['deletion_request'] == response.json()
    assert client.get('/api/auth/me').status_code == 200
    with database(client.app.state.config) as c:
        assert c.execute('SELECT COUNT(*) FROM tenants').fetchone()[0] == 1


def test_simultaneous_trial_and_checkout_retries_are_serialized(client):
    register(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: client.post('/api/commercial/trial', json={}).status_code, range(2)))
    assert sorted(results) == [200, 409]
    with ThreadPoolExecutor(max_workers=2) as pool:
        orders = list(pool.map(lambda _: order(client), range(2)))
    assert orders[0]['id'] == orders[1]['id']
    with ThreadPoolExecutor(max_workers=2) as pool:
        confirmations = list(pool.map(lambda _: client.post(f"/api/commercial/orders/{orders[0]['id']}/sandbox-confirm", json={}), range(2)))
    assert all(r.status_code == 200 for r in confirmations)
    assert confirmations[0].json() == confirmations[1].json()


def test_unimplemented_payment_mode_fails_closed_without_state_change(client, monkeypatch):
    register(client)
    first = order(client)
    monkeypatch.setenv('COMMERCIAL_PAYMENT_MODE', 'real')
    body = {'plan_id': 'team', 'consent': True, 'idempotency_key': 'checkout-new1'}
    assert client.post('/api/commercial/orders', json=body).status_code == 503
    assert client.post(f"/api/commercial/orders/{first['id']}/sandbox-confirm", json={}).status_code == 503
    account = client.get('/api/commercial/account').json()
    assert account['status'] == 'none' and len(account['orders']) == 1 and account['orders'][0]['status'] == 'pending'


def test_existing_order_keeps_catalog_snapshot_on_price_change(client, monkeypatch):
    from server import commercial
    register(client)
    first = order(client)
    monkeypatch.setitem(commercial.PLANS, 'start', commercial.PLANS['start'] | {'price_monthly': 5000000, 'user_limit': 25})
    assert order(client) == first
    confirmed = client.post(f"/api/commercial/orders/{first['id']}/sandbox-confirm", json={}).json()
    assert confirmed['account']['plan']['price_monthly'] == 990000
    assert confirmed['account']['plan']['user_limit'] == 2
    assert order(client, key='checkout-new1')['amount'] == 5000000


@pytest.mark.parametrize(('start', 'end'), [
    ('2026-01-31T12:00:00.000000+00:00', '2026-02-28T12:00:00.000000+00:00'),
    ('2028-01-31T12:00:00.000000+00:00', '2028-02-29T12:00:00.000000+00:00'),
    ('2026-12-20T12:00:00.000000+00:00', '2027-01-20T12:00:00.000000+00:00'),
])
def test_subscription_month_handles_month_ends_and_leap_years(start, end):
    from server.commercial import next_month
    assert next_month(start) == end
