"""Financial workflow: real SQLite/HTTP, no external banking or email."""
import importlib
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from server.business_time import business_today


@pytest.fixture
def client(tmp_path, monkeypatch):
    for key in ("DATABASE_URL", "APP_URL", "RENDER_EXTERNAL_URL", "SMTP_HOST", "SMTP_FROM", "YANDEX_API_KEY", "YANDEX_MODEL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "finance.db"))
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECURE_COOKIES", "false")
    module = importlib.import_module("server.main")
    with TestClient(module.create_app()) as result:
        registered = result.post("/api/auth/register", json={"name": "Финансист", "company": "Поставщик", "email": "finance@example.ru", "password": "Financial-testing-2026"})
        assert registered.status_code == 201
        result.headers["X-CSRF-Token"] = registered.json()["csrf_token"]
        yield result


def invoice(client, **changes):
    fields = dict(company="ООО Берёзка", inn="7701234567", email="ap@example.ru", number="A-1", issued_on=str(business_today()-timedelta(days=30)), due_on=str(business_today()-timedelta(days=10)), amount=100000)
    fields.update(changes)
    response = client.post("/api/invoices", json=fields)
    assert response.status_code == 201, response.text
    return response.json()


def test_stable_inn_identity_and_same_names_different_legal_entities(client):
    first = invoice(client)
    duplicate = client.post("/api/invoices", json={**{k:first[k] for k in ("company","inn","email","number","issued_on","due_on","amount")}, "company":"ООО Берёзка"})
    assert duplicate.status_code == 409
    other = invoice(client, inn="7801234567")
    assert other["counterparty_id"] != first["counterparty_id"]
    assert len(client.get("/api/finance/counterparties").json()["items"]) == 2


def test_opening_balance_and_explicit_reconciliation_approval(client):
    content = "контрагент;инн;номер;дата;срок;сумма;оплачено;остаток\nООО Берёзка;7701234567;A-1;01.10.2026;15.10.2026;1000;400;600\n"
    preview = client.post("/api/finance/imports/preview", json={"content":content})
    assert preview.status_code == 200, preview.text
    assert preview.json()["changes"][0]["action"] == "create"
    approved = client.post(f"/api/finance/imports/{preview.json()['id']}/approve", json={"reason":"Сверка с учётной системой"})
    assert approved.status_code == 200
    item = client.get("/api/invoices").json()["items"][0]
    assert item["balance"] == 60000 and item["paid_amount"] == 40000
    assert client.get("/api/overview").json()["collected_amount"] == 0
    changed = content.replace(";400;600", ";500;500")
    next_preview = client.post("/api/finance/imports/preview", json={"content":changed}).json()
    assert next_preview["changes"][0]["action"] == "update"
    assert client.get(f"/api/invoices/{item['id']}").json()["invoice"]["balance"] == 60000
    assert client.post(f"/api/finance/imports/{next_preview['id']}/approve", json={"reason":"Подтверждена новая выгрузка"}).status_code == 200
    assert client.get(f"/api/invoices/{item['id']}").json()["invoice"]["balance"] == 50000
    assert client.post(f"/api/finance/imports/{next_preview['id']}/approve", json={"reason":"Повтор"}).status_code == 200


def bank(client, amount=60000):
    response=client.post("/api/finance/bank-payments", json={"external_id":"BANK-1", "amount":amount,"paid_on":str(business_today()),"reference":"ПП 1","evidence":"Проверенная банковская выписка","confirmed":True})
    assert response.status_code == 201,response.text
    return response.json()


def test_bank_global_allocation_cap_concurrency_and_reversal(client):
    first, second = invoice(client),invoice(client,number="A-2")
    payment=bank(client)
    def allocate(pair):
        inv,key=pair
        return client.post(f"/api/finance/bank-payments/{payment['id']}/allocate",json={"invoice_id":inv["id"],"amount":40000,"idempotency_key":key})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(allocate,[(first,"a1"),(second,"a2")]))
    assert sorted(r.status_code for r in responses)==[200,422]
    winner=next(r.json() for r in responses if r.status_code==200)
    reversed_payment=client.post(f"/api/finance/payments/{winner['payment']['id']}/reverse",json={"amount":10000,"reason":"Неверное распределение","kind":"correction","idempotency_key":"reverse1"})
    assert reversed_payment.status_code==200,reversed_payment.text
    assert client.post(f"/api/finance/payments/{winner['payment']['id']}/reverse",json={"amount":10000,"reason":"Неверное распределение","kind":"correction","idempotency_key":"reverse1"}).status_code==200
    assert client.get("/api/finance/bank-payments").json()["items"][0]["available_amount"]==30000


def test_counterparty_hold_blocks_all_invoices_and_partial_promise_is_partial(client):
    first,second=invoice(client),invoice(client,number="A-2")
    promise=client.post(f"/api/finance/invoices/{first['id']}/promise",json={"amount":30000,"date":str(business_today()+timedelta(days=3)),"idempotency_key":"promise1"})
    assert promise.status_code==200,promise.text
    assert client.get("/api/overview").json()["promised_amount"]==30000
    assert client.patch(f"/api/finance/counterparties/{first['counterparty_id']}",json={"hold":True,"hold_reason":"Сверка"}).status_code==200
    for inv in (first,second):
        assert client.post(f"/api/invoices/{inv['id']}/draft",json={"tone":"soft"}).status_code==409


def test_adjustments_and_refunds_preserve_ledger_and_invalidate_drafts(client):
    inv=invoice(client)
    message=client.post(f"/api/invoices/{inv['id']}/draft",json={"tone":"soft"}).json()
    client.post(f"/api/messages/{message['id']}/approve")
    adjusted=client.post(f"/api/finance/invoices/{inv['id']}/adjustments",json={"kind":"return","amount":10000,"effective_on":str(business_today()),"reason":"Возврат части товара","idempotency_key":"return1"})
    assert adjusted.status_code==200,adjusted.text
    assert adjusted.json()["balance"]==90000
    assert client.post(f"/api/messages/{message['id']}/approve").status_code==409


def allocate_bank(client,inv,source,amount,key='allocation'):
    return client.post(f"/api/finance/bank-payments/{source['id']}/allocate",json={"invoice_id":inv['id'],"amount":amount,"idempotency_key":key})


def test_bank_idempotency_mismatched_payload_and_refund_do_not_release_returned_cash(client):
    inv=invoice(client);source=bank(client)
    allocation=allocate_bank(client,inv,source,40000).json()
    again=allocate_bank(client,inv,source,40000)
    assert again.status_code==200 and again.json()['payment']['id']==allocation['payment']['id']
    assert allocate_bank(client,inv,source,30000).status_code==409
    reversal={"amount":20000,"reason":"Подтверждён возврат денег","kind":"refund","idempotency_key":"refund"}
    response=client.post(f"/api/finance/payments/{allocation['payment']['id']}/reverse",json=reversal)
    assert response.status_code==200
    source_after=client.get('/api/finance/bank-payments').json()['items'][0]
    assert (source_after['allocated_amount'],source_after['returned_amount'],source_after['available_amount'])==(20000,20000,20000)
    assert allocate_bank(client,inv,source,20001,'too-much').status_code==422
    assert client.post(f"/api/finance/payments/{allocation['payment']['id']}/reverse",json={**reversal,'amount':20001,'idempotency_key':'over-reverse'}).status_code==422
    assert client.get('/api/overview').json()['collected_amount']==20000


def test_payer_inn_mismatch_needs_separate_reconciliation(client):
    inv=invoice(client)
    response=client.post('/api/finance/bank-payments',json={'external_id':'FOREIGN-PAYER','amount':1000,'paid_on':str(business_today()),'payer_inn':'7801234567','reference':'ПП2','evidence':'Банковский документ','confirmed':True})
    assert response.status_code==201
    assert allocate_bank(client,inv,response.json(),1000).status_code==409
    assert client.get('/api/overview').json()['collected_amount']==0


def test_installments_fulfilled_by_actual_payments_and_reopened_by_correction(client):
    inv=invoice(client);today=business_today()
    schedule=[{'date':str(today+timedelta(days=1)),'amount':20000},{'date':str(today+timedelta(days=4)),'amount':30000}]
    response=client.post(f"/api/finance/invoices/{inv['id']}/promise",json={'amount':50000,'date':schedule[-1]['date'],'installments':schedule,'idempotency_key':'schedule'})
    assert response.status_code==200
    paid=client.post(f"/api/invoices/{inv['id']}/payments",json={'amount':25000,'paid_on':str(today),'reference':'MANUAL-1'})
    assert paid.status_code==200 and paid.json()['promised_amount']==25000 and paid.json()['promise_date']==schedule[-1]['date']
    payment=client.get(f"/api/invoices/{inv['id']}").json()['payments'][0]
    reversed_payment=client.post(f"/api/finance/payments/{payment['id']}/reverse",json={'amount':10000,'kind':'correction','reason':'Исправление ручной записи','idempotency_key':'undo-manual'})
    assert reversed_payment.status_code==200
    assert reversed_payment.json()['invoice']['promised_amount']==35000
    assert reversed_payment.json()['invoice']['promise_date']==schedule[0]['date']
    ledger=client.get(f"/api/finance/invoices/{inv['id']}/ledger").json()
    assert sum(e['signed_reduction'] for e in ledger['financial_events'])==15000


def test_invalid_installment_totals_and_past_dates_leave_no_promise(client):
    inv=invoice(client)
    for body in ({'amount':100001,'date':str(business_today())},{'amount':1000,'date':str(business_today()-timedelta(days=1))},{'amount':1000,'date':str(business_today()),'installments':[{'date':str(business_today()),'amount':999}]}):
        response=client.post(f"/api/finance/invoices/{inv['id']}/promise",json={**body,'idempotency_key':'invalid'})
        assert response.status_code==422
    assert client.get('/api/overview').json()['promised_amount']==0


def test_adjustment_bounds_debit_and_idempotency_keep_cash_separate(client):
    inv=invoice(client)
    body={'kind':'offset','amount':30000,'effective_on':str(business_today()),'reason':'Согласованный взаимозачёт','idempotency_key':'offset'}
    first=client.post(f"/api/finance/invoices/{inv['id']}/adjustments",json=body)
    assert first.status_code==200 and first.json()['amount']==70000
    assert client.post(f"/api/finance/invoices/{inv['id']}/adjustments",json=body).json()==first.json()
    assert client.post(f"/api/finance/invoices/{inv['id']}/adjustments",json={**body,'amount':30001}).status_code==409
    assert client.post(f"/api/finance/invoices/{inv['id']}/adjustments",json={**body,'amount':70001,'idempotency_key':'over-credit'}).status_code==422
    added=client.post(f"/api/finance/invoices/{inv['id']}/adjustments",json={**body,'kind':'debit','amount':10000,'idempotency_key':'debit'})
    assert added.json()['amount']==80000 and added.json()['original_amount']==100000
    assert client.get('/api/overview').json()['collected_amount']==0


def test_import_stale_preview_and_bank_paid_conflicts_never_overwrite(client):
    inv=invoice(client)
    content=f"company,inn,number,issued_on,due_on,amount,paid_amount\n{inv['company']},{inv['inn']},{inv['number']},{inv['issued_on']},{inv['due_on']},1000,100\n"
    preview=client.post('/api/finance/imports/preview',json={'content':content}).json()
    assert preview['changes'][0]['action']=='update'
    client.patch(f"/api/invoices/{inv['id']}/contact",json={'email':'new@example.ru','notes':'Новая запись'})
    assert client.post(f"/api/finance/imports/{preview['id']}/approve",json={'reason':'Сверка'}).status_code==409
    source=bank(client)
    allocate_bank(client,inv,source,20000)
    conflict=client.post('/api/finance/imports/preview',json={'content':content}).json()
    assert conflict['changes'][0]['action']=='conflict'
    assert client.post(f"/api/finance/imports/{conflict['id']}/approve",json={'reason':'Ошибочный источник'}).status_code==422
    assert client.get(f"/api/invoices/{inv['id']}").json()['invoice']['paid_amount']==20000


def test_source_update_requires_explicit_approval_in_legacy_import(client):
    inv=invoice(client)
    content=f"company,inn,number,issued_on,due_on,amount\n{inv['company']},{inv['inn']},{inv['number']},{inv['issued_on']},{inv['due_on']},2000\n"
    assert client.post('/api/invoices/import',json={'content':content}).status_code==409
    assert client.get(f"/api/invoices/{inv['id']}").json()['invoice']['amount']==100000


def test_finance_resources_are_tenant_scoped(client):
    inv=invoice(client);source=bank(client);allocation=allocate_bank(client,inv,source,1000).json()
    content='company,number,issued_on,due_on,amount\nOther,B-1,2026-10-01,2026-10-15,10\n'
    preview=client.post('/api/finance/imports/preview',json={'content':content}).json()
    registered=client.post('/api/auth/register',json={'name':'Другой','company':'Другой поставщик','email':'other-finance@example.ru','password':'Other-financial-testing2026'})
    client.headers['X-CSRF-Token']=registered.json()['csrf_token']
    assert client.get('/api/finance/counterparties').json()['items']==[]
    assert client.get('/api/finance/bank-payments').json()['items']==[]
    assert client.patch(f"/api/finance/counterparties/{inv['counterparty_id']}",json={'hold':True,'hold_reason':'Нельзя'}).status_code==404
    assert client.get(f"/api/finance/invoices/{inv['id']}/ledger").status_code==404
    assert allocate_bank(client,inv,source,1000,'foreign').status_code==404
    assert client.post(f"/api/finance/payments/{allocation['payment']['id']}/reverse",json={'amount':1000,'reason':'Нельзя','idempotency_key':'foreign'}).status_code==404
    assert client.post(f"/api/finance/imports/{preview['id']}/approve",json={'reason':'Нельзя'}).status_code==404


def test_mandate_expiration_can_be_cleared_and_agent_policy_is_explicit(client):
    from server import finance
    from server.database import database
    inv=invoice(client)
    endpoint=f"/api/finance/counterparties/{inv['counterparty_id']}"
    expired=str(business_today()-timedelta(days=1))
    assert client.patch(endpoint,json={'mandate_expires_on':expired}).status_code==200
    assert client.post(f"/api/invoices/{inv['id']}/draft",json={'tone':'soft'}).status_code==409
    cleared=client.patch(endpoint,json={'mandate_expires_on':None})
    assert cleared.status_code==200 and cleared.json()['mandate_expires_on'] is None
    assert client.post(f"/api/invoices/{inv['id']}/draft",json={'tone':'soft'}).status_code==201
    with database(client.app.state.config) as c:
        tenant=c.execute('SELECT tenant_id FROM users').fetchone()['tenant_id']
        assert 'promise_mandate_required' in finance.agent_gate(c,tenant,inv['id'],'promise',1000,business_today())
        assert finance.agent_gate(c,tenant,inv['id'],'payment_claim')==[]


def test_financial_snapshot_hash_ignores_daily_aging_but_changes_on_real_ledger_edit(client,monkeypatch):
    from server import finance
    from server.database import database
    inv=invoice(client);config=client.app.state.config
    with database(config) as c:
        tenant=c.execute('SELECT tenant_id FROM users').fetchone()['tenant_id']
        before=finance.financial_snapshot(c,tenant,inv['id'])
        monkeypatch.setattr(finance,'business_today',lambda:business_today()+timedelta(days=1))
        next_day=finance.financial_snapshot(c,tenant,inv['id'])
        assert before['days_overdue']!=next_day['days_overdue']
        assert before['snapshot_hash']==next_day['snapshot_hash']
    client.patch(f"/api/invoices/{inv['id']}/contact",json={'email':'changed@example.ru','notes':'Уточнено'})
    with database(config) as c:assert finance.financial_snapshot(c,tenant,inv['id'])['snapshot_hash']!=before['snapshot_hash']


def test_approved_source_paid_change_fulfills_partial_promise_without_fake_receipt(client):
    inv=invoice(client)
    assert client.post(f"/api/finance/invoices/{inv['id']}/promise",json={'amount':50000,'date':str(business_today()+timedelta(days=3)),'idempotency_key':'source-promise'}).status_code==200
    content=f"company,inn,email,number,issued_on,due_on,amount,paid_amount\n{inv['company']},{inv['inn']},{inv['email']},{inv['number']},{inv['issued_on']},{inv['due_on']},1000,100\n"
    preview=client.post('/api/finance/imports/preview',json={'content':content}).json()
    assert client.post(f"/api/finance/imports/{preview['id']}/approve",json={'reason':'Сверены начальные оплаты'}).status_code==200
    assert client.get(f"/api/invoices/{inv['id']}").json()['invoice']['promised_amount']==40000
    assert client.get('/api/overview').json()['collected_amount']==0
    assert client.get('/api/finance/bank-payments').json()['items']==[]


def test_source_cannot_move_issue_date_after_registered_payment(client):
    inv=invoice(client)
    paid_on=business_today()-timedelta(days=5)
    assert client.post(f"/api/invoices/{inv['id']}/payments",json={'amount':10000,'paid_on':str(paid_on),'reference':'OLD-DATE'}).status_code==200
    content=f"company,inn,number,issued_on,due_on,amount,paid_amount\n{inv['company']},{inv['inn']},{inv['number']},{business_today()-timedelta(days=3)},{business_today()},1000,100\n"
    preview=client.post('/api/finance/imports/preview',json={'content':content}).json()
    assert preview['changes'][0]['action']=='conflict'
    assert client.post(f"/api/finance/imports/{preview['id']}/approve",json={'reason':'Неверные даты'}).status_code==422


def test_correction_undoes_original_date_while_real_refund_has_return_date(client):
    from server.legal import calculate_debt
    inv=invoice(client);old_day=str(business_today()-timedelta(days=7))
    assert client.post(f"/api/invoices/{inv['id']}/payments",json={'amount':30000,'paid_on':old_day,'reference':'WRONG-ALLOCATION'}).status_code==200
    payment=client.get(f"/api/invoices/{inv['id']}").json()['payments'][0]
    assert client.post(f"/api/finance/payments/{payment['id']}/reverse",json={'amount':10000,'kind':'correction','reason':'Часть исторической записи относилась к другому счёту','idempotency_key':'historical-correction'}).status_code==200
    assert client.post(f"/api/finance/payments/{payment['id']}/reverse",json={'amount':5000,'kind':'refund','reason':'Сегодня реально возвращена часть денег','idempotency_key':'today-refund'}).status_code==200
    history=client.get(f"/api/finance/invoices/{inv['id']}/ledger").json()['financial_events']
    correction=next(e for e in history if e['type']=='reversal' and e['kind']=='correction')
    refund=next(e for e in history if e['type']=='reversal' and e['kind']=='refund')
    assert correction['effective_on']==old_day
    assert refund['effective_on']==str(business_today())
    through=str(business_today()-timedelta(days=1))
    result=calculate_debt(principal=inv['original_amount'],due_on=inv['due_on'],through_on=through,reductions=history,sanction='none')
    assert result['principal_amount']==80000  # The mistaken allocation never reduced principal.
    rate=[{'from_on':inv['due_on'],'to_on':through,'annual_percent':'14','source':'Синтетическая ставка regression'}]
    terms=dict(principal=inv['original_amount'],due_on=inv['due_on'],through_on=through,sanction='art395',rate_override=rate,override_reason='Явная тестовая ставка для проверки истории principal')
    actual=calculate_debt(**terms,reductions=history)
    correct=calculate_debt(**terms,reductions=[{'effective_on':old_day,'signed_reduction':20000}])
    delayed=[dict(event,effective_on=str(business_today())) if event.get('kind')=='correction' else event for event in history]
    assert actual['interest_amount']==correct['interest_amount']
    assert actual['interest_amount']>calculate_debt(**terms,reductions=delayed)['interest_amount']
    assert client.get(f"/api/invoices/{inv['id']}").json()['invoice']['balance']==85000


def test_ledger_returns_persisted_installment_dates_amounts_and_fulfillment(client):
    inv=invoice(client);today=business_today()
    schedule=[{'date':str(today+timedelta(days=2)),'amount':20000},{'date':str(today+timedelta(days=5)),'amount':30000}]
    response=client.post(f"/api/finance/invoices/{inv['id']}/promise",json={'amount':50000,'date':schedule[-1]['date'],'installments':schedule,'idempotency_key':'readable-schedule'})
    assert response.status_code==200
    assert client.post(f"/api/invoices/{inv['id']}/payments",json={'amount':25000,'paid_on':str(today),'reference':'SCHEDULE-PAY'}).status_code==200
    promises=client.get(f"/api/finance/invoices/{inv['id']}/ledger").json()['promises']
    saved=next(row for row in promises if row['id']==response.json()['id'])
    assert len(saved['installments'])==2
    assert [(row['due_on'],row['amount'],row['fulfilled_amount']) for row in saved['installments']]==[(schedule[0]['date'],20000,20000),(schedule[1]['date'],30000,5000)]
    assert len({row['id'] for row in saved['installments']})==2
    again=client.get(f"/api/finance/invoices/{inv['id']}/ledger").json()['promises']
    assert next(row for row in again if row['id']==saved['id'])['installments']==saved['installments']


def test_payment_public_display_reference_preserves_real_bank_document_and_internal_idempotency(client):
    inv=invoice(client);source=bank(client)
    allocation=allocate_bank(client,inv,source,1000,'display-reference')
    assert allocation.status_code==200
    detail=client.get(f"/api/invoices/{inv['id']}").json()['payments'][0]
    ledger=client.get(f"/api/finance/invoices/{inv['id']}/ledger").json()['payments'][0]
    for row in (detail,ledger):
        assert row['display_reference']==source['reference']=='ПП 1'
        assert row['reference'].startswith('bank:') and row['reference'].endswith(':display-reference')
    assert client.post(f"/api/invoices/{inv['id']}/payments",json={'amount':1000,'paid_on':str(business_today()),'reference':'Ручное ПП2'}).status_code==200
    manual=next(row for row in client.get(f"/api/invoices/{inv['id']}").json()['payments'] if not row['bank_payment_id'])
    assert manual['display_reference']==manual['reference']=='Ручное ПП2'
    assert allocate_bank(client,inv,source,1000,'display-reference').json()['payment']['id']==allocation.json()['payment']['id']
