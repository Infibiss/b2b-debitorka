"""Audit regressions: actual financial receipts and cross-organization register isolation.

No external banking calls. Bank evidence is created and allocated through the
same HTTP boundaries as an operator-confirmed statement. Funding has no customer
HTTP transition, so only that operator-owned initial state is seeded in the DB.
"""
from datetime import timedelta

from server.business_time import business_today
from server.database import database
from tests.test_api import client, invoice, register  # noqa: F401


def bank_receipt(client, item, *, external_id, amount, paid_on):
    source = client.post('/api/finance/bank-payments', json={
        'external_id': external_id, 'amount': amount, 'paid_on': str(paid_on),
        'payer_inn': item['inn'], 'reference': external_id,
        'evidence': 'Поступление сверено с банковской выпиской', 'confirmed': True,
    })
    assert source.status_code == 201, source.text
    allocation = client.post(f"/api/finance/bank-payments/{source.json()['id']}/allocate", json={
        'invoice_id': item['id'], 'amount': amount, 'idempotency_key': external_id + '-allocation',
    })
    assert allocation.status_code == 200, allocation.text
    return allocation.json()['payment']['id']


def financing_view(client):
    result = client.get('/api/financing/requests')
    assert result.status_code == 200, result.text
    assert len(result.json()['items']) == 1
    return result.json()['items'][0]


def test_financing_counts_only_allocated_bank_receipts_from_funding_date_and_reverses(client):
    register(client)
    item = invoice(client, amount=50_000_000)
    other = invoice(client, number='OTHER-DEBTOR', inn='7801234567', amount=100_000)
    today = business_today()
    funded_on = today - timedelta(days=3)
    with database(client.app.state.config, write=True) as connection:
        tenant = connection.execute('SELECT tenant_id FROM invoices WHERE id=?', (item['id'],)).fetchone()['tenant_id']
        connection.execute('''INSERT INTO financing_requests
            (id,tenant_id,counterparty_id,product_id,debtor_name,amount,balance_snapshot,status,
             funded_amount,repay_amount,funded_on,consent_at,created_by,created_at,updated_at)
            VALUES('audit-funded',?,?,'factoring','ООО Север',60000,50000000,'funded',60000,70000,?,'x','operator','x','x')''',
            (tenant, item['counterparty_id'], str(funded_on)))

    bank_receipt(client, item, external_id='BEFORE-FUNDING', amount=5000, paid_on=funded_on-timedelta(days=1))
    manual = client.post(f"/api/invoices/{item['id']}/payments", json={
        'amount': 9000, 'paid_on': str(today), 'reference': 'Ручная запись без банковской выписки',
    })
    assert manual.status_code == 200, manual.text
    bank_receipt(client, other, external_id='OTHER-COMPANY', amount=6000, paid_on=today)
    before = financing_view(client)
    assert (before['repaid_amount'], before['remaining_amount'], before['surplus_to_client']) == (0, 70000, 0)

    # The contractual funding date is inclusive. Unallocated bank cash is not a
    # receipt against this debt; allocation is the event that changes repayment.
    bank_receipt(client, item, external_id='ON-FUNDING-DAY', amount=30000, paid_on=funded_on)
    assert financing_view(client)['remaining_amount'] == 40000
    after_payment_id = bank_receipt(client, item, external_id='AFTER-FUNDING', amount=50000, paid_on=today)
    paid = financing_view(client)
    assert (paid['repaid_amount'], paid['remaining_amount'], paid['surplus_to_client']) == (70000, 0, 10000)

    reversal = dict(amount=20000, reason='Исправлена сумма распределения по выписке', kind='correction', idempotency_key='audit-reverse')
    response = client.post(f'/api/finance/payments/{after_payment_id}/reverse', json=reversal)
    assert response.status_code == 200, response.text
    reopened = financing_view(client)
    assert (reopened['repaid_amount'], reopened['remaining_amount'], reopened['surplus_to_client']) == (60000, 10000, 0)
    # Retrying the correction must not deduct it twice.
    retry = client.post(f'/api/finance/payments/{after_payment_id}/reverse', json=reversal)
    assert retry.status_code == 200, retry.text
    assert financing_view(client) == reopened


def test_register_cannot_be_read_changed_or_deleted_from_another_organization(client):
    owner = register(client)
    item = invoice(client)
    key = item['counterparty_id']
    payload = dict(kind='bank_account', on_date=str(business_today()), title='АО Банк', reference='40702810000000000002', amount=100000)
    created = client.post(f'/api/recovery/debtors/{key}/register', json=payload)
    assert created.status_code == 201, created.text
    entry_id = created.json()['id']
    original = client.get(f'/api/recovery/debtors/{key}').json()['register']
    assert len(original) == 1 and original[0]['id'] == entry_id

    assert client.post('/api/auth/logout').status_code == 200
    register(client, email='other-register-owner@example.ru')
    other = invoice(client, number='OTHER-ORG')
    assert client.get(f'/api/recovery/debtors/{key}').status_code == 404
    assert client.post(f'/api/recovery/debtors/{key}/register', json=payload).status_code == 404
    assert client.get(f"/api/recovery/debtors/{other['counterparty_id']}").json()['register'] == []
    # Deletion is intentionally idempotent: foreign and missing IDs both return
    # the same no-op success without exposing whether a foreign record exists.
    denied = client.delete(f'/api/recovery/register/{entry_id}')
    missing = client.delete('/api/recovery/register/nonexistent-audit-entry')
    assert denied.status_code == missing.status_code == 200
    assert denied.json() == missing.json() == {'ok': True}

    assert client.post('/api/auth/logout').status_code == 200
    login = client.post('/api/auth/login', json=dict(email=owner['user']['email'], password='Correct-horse-24!'))
    assert login.status_code == 200, login.text
    client.headers['X-CSRF-Token'] = login.json()['csrf_token']
    assert client.get(f'/api/recovery/debtors/{key}').json()['register'] == original
    assert client.delete(f'/api/recovery/register/{entry_id}').status_code == 200
    assert client.get(f'/api/recovery/debtors/{key}').json()['register'] == []
