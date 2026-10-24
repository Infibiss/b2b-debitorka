"""Forecast contract tests use labelled historical ledger fixtures, never model training data."""
from datetime import timedelta

from test_finance import client, invoice
from server.business_time import business_today
from server.database import database


def forecast(client):
    response = client.get('/api/forecast')
    assert response.status_code == 200, response.text
    return response.json()


def history(client, count=5, receipt=50000, start_age=200):
    """Historical records were available at issue/receipt, with unpaid cohort members."""
    today = business_today()
    result = []
    for index in range(count):
        due = today - timedelta(days=start_age - index * 10)
        item = invoice(client, number=f'H-{index}', issued_on=str(due-timedelta(days=10)), due_on=str(due))
        paid = due + timedelta(days=5)
        source = client.post('/api/finance/bank-payments', json=dict(external_id=f'H-{index}', amount=receipt,
            paid_on=str(paid), reference=f'Historical fixture {index}', evidence='Test fixture bank statement', confirmed=True)).json()
        allocation = client.post(f"/api/finance/bank-payments/{source['id']}/allocate", json=dict(invoice_id=item['id'], amount=receipt, idempotency_key=f'H-{index}')).json()
        with database(client.app.state.config, write=True) as c:
            c.execute('UPDATE invoices SET created_at=? WHERE id=?', (str(due-timedelta(days=10))+'T00:00:00+00:00', item['id']))
            for table, key in [('payments', allocation['payment']['id']), ('finance_bank_payments', source['id'])]:
                c.execute(f'UPDATE {table} SET created_at=? WHERE id=?', (str(paid)+'T00:00:00+00:00', key))
        result.append((item, allocation['payment']))
    return result


def test_empty_and_opening_paid_abstain(client):
    assert forecast(client)['status'] == 'abstained'
    invoice(client, paid_amount=40000)
    data = forecast(client)
    assert data['status'] == 'abstained'
    assert all(row['expected_amount'] is None for row in data['horizons'])
    assert data['coverage']['bank_allocations'] == 0


def test_partial_receipts_are_amount_weighted_and_do_not_assume_full_payment(client):
    history(client)
    item = invoice(client, number='CURRENT', issued_on=str(business_today()-timedelta(days=10)), due_on=str(business_today()))
    data = forecast(client)
    assert data['status'] == 'available'
    assert data['method'] == 'empirical_due_cohort_v1'
    assert data['coverage']['covered_balance'] == item['balance']
    assert [row['expected_amount'] for row in data['horizons']] == [50000,50000,50000]
    assert data['horizons'][0]['low_scenario'] <= 50000 <= data['horizons'][0]['high_scenario']


def test_unpaid_mature_invoices_are_in_denominator(client):
    history(client)
    due = business_today()-timedelta(days=180)
    unpaid = invoice(client, number='UNPAID', issued_on=str(due-timedelta(days=10)), due_on=str(due))
    with database(client.app.state.config, write=True) as c:
        c.execute('UPDATE invoices SET created_at=? WHERE id=?', (str(due-timedelta(days=10)),unpaid['id']))
    invoice(client, number='CURRENT', issued_on=str(business_today()-timedelta(days=10)), due_on=str(business_today()))
    data = forecast(client)
    assert data['horizons'][0]['expected_amount'] == 41666


def test_returned_partial_payment_changes_net_receipts(client):
    rows = history(client)
    for item,payment in rows:
        response = client.post(f"/api/finance/payments/{payment['id']}/reverse", json=dict(amount=10000,kind='refund',reason='Test return',idempotency_key='return-'+item['id']))
        assert response.status_code == 200, response.text
        with database(client.app.state.config, write=True) as c:
            refund_day = str(business_today()-timedelta(days=120))
            c.execute('UPDATE finance_reversals SET effective_on=?,created_at=? WHERE payment_id=?', (refund_day,refund_day+'T00:00:00+00:00',payment['id']))
    invoice(client, number='CURRENT', issued_on=str(business_today()-timedelta(days=10)), due_on=str(business_today()))
    data = forecast(client)
    # Refunds after the sixty-day label window must not retroactively reduce its receipt.
    assert data['horizons'][0]['expected_amount'] == 50000
    assert data['horizons'][2]['expected_amount'] == 44000


def test_future_effective_and_future_known_history_cannot_change_forecast(client):
    rows = history(client)
    invoice(client, number='CURRENT', issued_on=str(business_today()-timedelta(days=10)), due_on=str(business_today()))
    before = forecast(client)
    with database(client.app.state.config, write=True) as c:
        c.execute('UPDATE payments SET paid_on=? WHERE id=?', (str(business_today()+timedelta(days=1)),rows[0][1]['id']))
        c.execute('UPDATE payments SET created_at=? WHERE id=?', (str(business_today()+timedelta(days=1)),rows[1][1]['id']))
    after = forecast(client)
    assert after['coverage']['bank_allocations'] == before['coverage']['bank_allocations']-2
    assert after['horizons'][0]['expected_amount'] < before['horizons'][0]['expected_amount']
    assert client.get('/api/forecast?as_of=2099-01-01').status_code == 422


def test_history_is_tenant_scoped(client):
    history(client)
    registration = client.post('/api/auth/register', json=dict(name='Другой',company='Другой',email='forecast-other@example.ru',password='Forecast-testing2026'))
    client.headers['X-CSRF-Token'] = registration.json()['csrf_token']
    data = forecast(client)
    assert data['status'] == 'abstained' and data['coverage']['bank_allocations'] == 0


def test_future_current_payment_cannot_leak_through_materialized_balance(client):
    history(client)
    item = invoice(client, number='CURRENT', issued_on=str(business_today()-timedelta(days=10)), due_on=str(business_today()))
    source = client.post('/api/finance/bank-payments',json=dict(external_id='current-fixture',amount=50000,paid_on=str(business_today()),reference='Current fixture',evidence='Test fixture',confirmed=True)).json()
    allocation = client.post(f"/api/finance/bank-payments/{source['id']}/allocate",json=dict(invoice_id=item['id'],amount=50000,idempotency_key='current-fixture')).json()
    with database(client.app.state.config,write=True) as c:
        c.execute('UPDATE payments SET created_at=? WHERE id=?',(str(business_today()+timedelta(days=1)),allocation['payment']['id']))
    data = forecast(client)
    assert data['status'] == 'abstained'
    current = next(row for row in data['invoices'] if row['invoice_id']==item['id'])
    assert 'temporal_history_unavailable' in current['reasons']


def test_backfilled_invoice_and_manual_history_cannot_enter_historical_features(client):
    rows = history(client)
    invoice(client, number='CURRENT', issued_on=str(business_today()-timedelta(days=10)), due_on=str(business_today()))
    with database(client.app.state.config,write=True) as c:
        c.execute('UPDATE invoices SET created_at=? WHERE id=?',(str(business_today()),rows[0][0]['id']))
    assert forecast(client)['status'] == 'abstained'


def test_label_window_ending_today_is_not_yet_fully_observed(client):
    history(client, start_age=100)
    invoice(client, number='CURRENT', issued_on=str(business_today()-timedelta(days=10)), due_on=str(business_today()))
    # The fifth label window ends tonight. Only four have completely elapsed.
    data = forecast(client)
    assert data['status'] == 'abstained'
    current = next(row for row in data['invoices'] if row['status'] == 'abstained' and row.get('training_invoices') == 4)
    assert current['training_invoices'] == 4
