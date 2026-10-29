"""Remaining UI audit contracts: authority, financial sources and conversation isolation."""
from datetime import timedelta

from test_finance import client, invoice, bank
from test_negotiation import policy, proposal, mandate
from server.business_time import business_today


def test_recheck_preserves_terms_and_requires_new_review(client):
    item = invoice(client)
    policy(client, auto_accept=True)
    url = f"/api/negotiation/preflight?invoice_id={item['id']}&kind=promise"
    before = client.get(url)
    assert before.status_code == 200, before.text
    assert before.json()['counterparty_id'] == item['counterparty_id']
    assert 'promise_mandate_required' in before.json()['reasons']
    old = proposal(client, item)
    assert old['status'] == 'handoff'
    mandate(client, item)
    assert client.get(url).json()['reasons'] == []
    check = f"/api/negotiation/proposals/{old['id']}/recheck"
    assert client.post(check, json={}).status_code == 422
    result = client.post(check, json=dict(decision='approve', reason='Полномочия проверены, условия покупателя действуют'))
    assert result.status_code == 200, result.text
    new = result.json()
    assert new['id'] == old['id'] and new['terms'] == old['terms']
    assert new['status'] == 'review_required'
    assert new['snapshot_hash'] != old['snapshot_hash']
    assert [e['type'] for e in new['events']] == ['proposed', 'rechecked']
    execute = f"/api/negotiation/proposals/{old['id']}/execute"
    assert client.post(execute, json={}).status_code == 409
    assert client.post(f"/api/negotiation/proposals/{old['id']}/review", json=dict(decision='approve', reason='Подтверждено')).status_code == 200
    assert client.post(execute, json={}).status_code == 200
    assert client.post(check, json=dict(decision='approve', reason='Повтор')).status_code == 409
    assert client.get(f"/api/invoices/{item['id']}").json()['invoice']['balance'] == item['balance']


def test_recheck_does_not_bypass_expiry_or_current_balance(client):
    item = invoice(client)
    policy(client)
    old = proposal(client, item, amount=100000)
    mandate(client, item)
    assert client.post(f"/api/invoices/{item['id']}/payments", json=dict(amount=1000, paid_on=str(business_today()), reference='MANUAL-1')).status_code == 200
    result = client.post(f"/api/negotiation/proposals/{old['id']}/recheck", json=dict(decision='approve', reason='Проверка остатка'))
    assert result.status_code == 200, result.text
    assert result.json()['status'] == 'handoff'
    assert 'amount_outside_current_balance' in result.json()['reasons']
    expired = proposal(client, item, idempotency_key='expired', expires_on=str(business_today()-timedelta(days=1)))
    assert expired['status'] == 'expired'
    assert client.post(f"/api/negotiation/proposals/{expired['id']}/recheck", json=dict(decision='approve', reason='Нельзя продлить молча')).status_code == 409


def test_financial_sources_and_timeline_are_invoice_and_tenant_scoped(client):
    item = invoice(client, paid_amount=20000)
    other = invoice(client, number='OTHER')
    payment = bank(client)
    allocated = client.post(f"/api/finance/bank-payments/{payment['id']}/allocate", json=dict(invoice_id=item['id'], amount=30000, idempotency_key='bank-allocation'))
    assert allocated.status_code == 200, allocated.text
    assert client.post(f"/api/invoices/{item['id']}/payments", json=dict(amount=1000, paid_on=str(business_today()), reference='MANUAL')).status_code == 200
    totals = client.get('/api/overview').json()
    assert totals['historical_paid_amount'] == 20000
    assert totals['bank_confirmed_amount'] == 30000
    assert totals['manual_paid_amount'] == 1000
    assert totals['collected_amount'] == 31000
    policy(client)
    p = proposal(client, item, kind='payment_claim', amount=None, due_on=None, evidence='Мы оплатили, проверьте выписку')
    timeline = client.get(f"/api/workflow/invoices/{item['id']}/timeline")
    assert timeline.status_code == 200, timeline.text
    rows = timeline.json()['items']
    assert any(r['reference'] == p['id'] and r['section'] == 'intelligence' for r in rows)
    assert any(r['title'] == 'Банковская оплата' and r['amount'] == 30000 for r in rows)
    assert any('дата платежа неизвестна' in r['title'] for r in rows)
    other_rows = client.get(f"/api/workflow/invoices/{other['id']}/timeline").json()['items']
    assert not any(r['reference'] == p['id'] for r in other_rows)
    assert client.get(f"/api/workflow/invoices/{item['id']}/timeline?offset=-1").status_code == 422
    registration = client.post('/api/auth/register', json=dict(name='Другой', company='Другая', email='other-audit@example.ru', password='Other-account-password-2026!'))
    assert registration.status_code == 201
    client.headers['X-CSRF-Token'] = registration.json()['csrf_token']
    assert client.get(f"/api/workflow/invoices/{item['id']}/timeline").status_code == 404
    assert client.get(f"/api/negotiation/preflight?invoice_id={item['id']}&kind=promise").status_code == 404
    assert client.post(f"/api/negotiation/proposals/{p['id']}/recheck", json=dict(decision='approve', reason='Чужое')).status_code == 404


def test_incomplete_legal_facts_can_be_saved_but_cannot_generate(client):
    item = invoice(client)
    created = client.post('/api/legal/cases', json=dict(invoice_id=item['id']))
    assert created.status_code == 201, created.text
    case = created.json()
    facts = case['facts']
    facts['contract_number'] = 'PARTIAL-42'
    saved = client.patch(f"/api/legal/cases/{case['id']}", json=dict(facts=facts))
    assert saved.status_code == 200, saved.text
    assert client.get(f"/api/legal/cases/{case['id']}").json()['facts']['contract_number'] == 'PARTIAL-42'
    generated = client.post(f"/api/legal/cases/{case['id']}/documents", json=dict(kind='pretrial_claim', calculation=dict(through_on=str(business_today()), sanction='none')))
    assert generated.status_code == 422, generated.text
