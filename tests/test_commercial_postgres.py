"""Commercial contract parity against PostgreSQL's serialized write path."""
from test_storage_pg import postgres_config, postgres_client
from tests import test_commercial as contracts
from tests.test_commercial import sandbox_only


def test_postgres_public_request_validation(postgres_client):
    contracts.test_demo_request_is_durable_private_and_validated(postgres_client)


def test_postgres_order_price_snapshot_and_idempotency(postgres_client):
    contracts.test_orders_snapshot_price_idempotency_and_never_call_real_billing(postgres_client)


def test_postgres_order_tenant_isolation_and_permissions(postgres_client):
    contracts.test_order_and_account_tenant_isolation_and_permissions(postgres_client)


def test_postgres_cancellation_state_machine(postgres_client):
    contracts.test_cancel_is_idempotent_and_prevents_order_reactivation(postgres_client)


def test_postgres_trial_and_expiry(postgres_client):
    contracts.test_trial_cancel_cannot_restart_and_subscription_expiry_is_explicit(postgres_client)


def test_postgres_concurrent_trial_and_checkout(postgres_client):
    contracts.test_simultaneous_trial_and_checkout_retries_are_serialized(postgres_client)


def test_postgres_fail_closed_provider(postgres_client, monkeypatch):
    contracts.test_unimplemented_payment_mode_fails_closed_without_state_change(postgres_client, monkeypatch)


def test_postgres_catalog_snapshot(postgres_client, monkeypatch):
    contracts.test_existing_order_keeps_catalog_snapshot_on_price_change(postgres_client, monkeypatch)


def test_postgres_deletion_request_is_non_destructive_and_idempotent(postgres_client):
    body = {'confirmation': 'УДАЛИТЬ', 'consent': True}
    first = postgres_client.post('/api/commercial/deletion-request', json=body)
    assert first.status_code == 201 and first.json()['status'] == 'requested'
    assert postgres_client.post('/api/commercial/deletion-request', json=body).json() == first.json()
    assert postgres_client.get('/api/auth/me').status_code == 200


def test_postgres_operator_queue_is_private_and_separate_from_public_status(postgres_client):
    from scripts.commercial_requests import list_requests, mark_handled
    config = postgres_client.app.state.config
    lead = postgres_client.post('/api/commercial/requests', json={
        'kind': 'demo', 'name': 'Анна', 'email': 'private@example.ru', 'consent': True}).json()
    deletion = postgres_client.post('/api/commercial/deletion-request', json={'confirmation': 'УДАЛИТЬ', 'consent': True}).json()
    queued = list_requests(config)
    assert len(queued['items']) == 2 and all('email' not in item for item in queued['items'])
    assert list_requests(config, kind='demo', include_contact=True)['items'][0]['email'] == 'private@example.ru'
    mark_handled(config, kind='demo', request_id=lead['id'], owner='operator', reference='CRM-123')
    assert [item['id'] for item in list_requests(config)['items']] == [deletion['id']]
    mark_handled(config, kind='deletion', request_id=deletion['id'], owner='privacy-operator', reference='PRIVACY-12')
    assert list_requests(config)['items'] == []
    assert len(list_requests(config, state='handled')['items']) == 2
    assert postgres_client.get('/api/commercial/account').json()['deletion_request'] == deletion
    assert postgres_client.get('/api/auth/me').status_code == 200


def test_postgres_operator_disposition_concurrent_retries_are_idempotent(postgres_client):
    from concurrent.futures import ThreadPoolExecutor
    import pytest
    from scripts.commercial_requests import mark_handled
    config = postgres_client.app.state.config
    lead = postgres_client.post('/api/commercial/requests', json={
        'kind': 'custom', 'name': 'Анна', 'email': 'private@example.ru', 'consent': True}).json()
    def handle(_):
        return mark_handled(config, kind='custom', request_id=lead['id'], owner='operator', reference='CRM-123')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(handle, range(2)))
    assert results[0] == results[1]
    with pytest.raises(ValueError, match='cannot be overwritten'):
        mark_handled(config, kind='custom', request_id=lead['id'], owner='another-operator', reference='CRM-123')
