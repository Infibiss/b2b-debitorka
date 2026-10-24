"""Operational audit uses accounting evidence, never invented recoverability."""
import base64
import importlib
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from server.business_time import business_today


@pytest.fixture
def client(tmp_path, monkeypatch):
    for key in ('DATABASE_URL', 'APP_URL', 'RENDER_EXTERNAL_URL', 'MANDATO_INTEGRATIONS_JSON'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('SECURE_COOKIES', 'false')
    monkeypatch.setenv('DATABASE_PATH', str(tmp_path / 'portfolio.db'))
    with TestClient(importlib.import_module('server.main').create_app()) as c:
        register(c)
        yield c


def register(c, email='portfolio@example.ru'):
    response = c.post('/api/auth/register', json={'name': 'Финансовый директор', 'company': 'Поставщик',
        'email': email, 'password': 'Portfolio-testing-2026!'})
    assert response.status_code == 201, response.text
    c.headers['X-CSRF-Token'] = response.json()['csrf_token']


def invoice(c, **changes):
    data = {'company': 'ООО Покупатель', 'inn': '7701234567', 'email': 'buyer@example.ru', 'number': 'PORT-1',
        'issued_on': str(business_today()-timedelta(days=70)), 'due_on': str(business_today()-timedelta(days=40)),
        'amount': 100_000}
    data.update(changes)
    result = c.post('/api/invoices', json=data)
    assert result.status_code == 201, result.text
    return result.json()


def audit(c):
    result = c.post('/api/portfolio/runs', json={})
    assert result.status_code == 201, result.text
    return result.json()


def test_empty_audit_has_no_fabricated_debt_or_probability(client):
    run = audit(client)
    assert run['totals']['outstanding'] == 0
    assert run['items'] == [] and run['findings'] == []
    assert 'recovery_probability' not in str(run)


def test_missing_primary_documents_and_unverified_debtor_are_actionable(client):
    inv = invoice(client)
    run = audit(client)
    item = run['items'][0]
    assert item['invoice_id'] == inv['id'] and item['balance'] == 100_000
    codes = {f['code'] for f in item['findings']}
    assert {'missing_contract', 'missing_performance', 'missing_payment_terms', 'registry_unverified'} <= codes
    assert item['next_action']['code'] in ('check_debtor', 'obtain_documents')
    assert all(f['evidence'] and f['next_step'] for f in item['findings'])
    assert client.get('/api/invoices').json()['items'][0]['balance'] == 100_000


def test_registered_primary_evidence_changes_next_run_without_rewriting_history(client):
    inv = invoice(client)
    first = audit(client)
    for kind in ('contract', 'performance', 'payment_terms'):
        r = client.post(f"/api/portfolio/invoices/{inv['id']}/evidence", json={'kind': kind,
            'reference': f'{kind}: подписанный документ из архива', 'occurred_on': inv['issued_on'],
            'note': 'Проверено бухгалтером по первичному документу'})
        assert r.status_code == 201, r.text
    assert client.get('/api/portfolio').json()['stale'] is True
    second = audit(client)
    assert not {f['code'] for f in second['items'][0]['findings']} & {'missing_contract', 'missing_performance', 'missing_payment_terms'}
    historical = client.get(f"/api/portfolio/runs/{first['id']}").json()
    assert historical['items'][0]['findings'] == first['items'][0]['findings']


def test_uploaded_document_is_private_immutable_and_not_executed(client):
    inv = invoice(client)
    content = b'%PDF-1.4\n% internal test evidence\n%%EOF'
    response = client.post(f"/api/portfolio/invoices/{inv['id']}/evidence", json={'kind': 'contract',
        'reference': 'Договор №1', 'occurred_on': inv['issued_on'], 'filename': 'contract.pdf',
        'content_base64': base64.b64encode(content).decode()})
    assert response.status_code == 201, response.text
    evidence = response.json()
    assert 'content_base64' not in evidence and len(evidence['sha256']) == 64
    download = client.get(evidence['download_url'])
    assert download.content == content and 'attachment' in download.headers['content-disposition']
    register(client, 'other-portfolio@example.ru')
    assert client.get(evidence['download_url']).status_code == 404


def test_stopped_or_disputed_debt_is_not_put_in_contact_queue(client):
    first = invoice(client)
    second = invoice(client, number='PORT-2')
    assert client.post(f"/api/invoices/{first['id']}/status", json={'status': 'disputed', 'notes': 'Возврат товара обсуждается'}).status_code == 200
    assert client.patch(f"/api/finance/counterparties/{second['counterparty_id']}", json={'hold': True, 'hold_reason': 'Ключевой клиент'}).status_code == 200
    run = audit(client)
    assert all(item['next_action']['code'] == 'stop' for item in run['items'])


def test_payment_after_audit_marks_run_stale_and_closed_invoice_no_longer_chased(client):
    inv = invoice(client)
    first = audit(client)
    r = client.post(f"/api/invoices/{inv['id']}/payments", json={'amount': inv['amount'], 'paid_on': str(business_today()), 'reference': 'PAY-1'})
    assert r.status_code == 200, r.text
    assert client.get('/api/portfolio').json()['stale'] is True
    fresh = audit(client)
    assert fresh['items'][0]['next_action']['code'] == 'closed'
    assert fresh['totals']['outstanding'] == 0
    assert client.get(f"/api/portfolio/runs/{first['id']}").json()['totals']['outstanding'] == inv['amount']


def test_long_overdue_debt_prompts_legal_review_without_declaring_limitation_expired(client):
    inv = invoice(client, issued_on=str(business_today()-timedelta(days=1200)), due_on=str(business_today()-timedelta(days=1000)))
    item = audit(client)['items'][0]
    finding = next(f for f in item['findings'] if f['code'] == 'limitation_review')
    assert finding['severity'] == 'urgent'
    assert 'не определяет' in finding['detail']
    assert item['next_action']['code'] == 'lawyer_review'


def test_bank_cash_is_separate_from_ledger_and_no_double_counting(client):
    invoice(client)
    response = client.post('/api/finance/bank-payments', json={'confirmed':True, 'external_id':'PORT-BANK-1',
        'amount': 50_000, 'paid_on': str(business_today()), 'payer_inn':'7701234567', 'payer_name':'Покупатель',
        'reference':'Поручение №1', 'evidence':'Проверено по выписке'})
    assert response.status_code == 201, response.text
    run = audit(client)
    assert run['totals']['unallocated_cash'] == 50_000
    assert run['totals']['outstanding'] == 100_000
    assert any(f['code'] == 'unallocated_cash' for f in run['findings'])


def test_manual_review_deadline_is_evidenced_and_not_silent_automatic_limitation(client):
    inv = invoice(client)
    r = client.post(f"/api/portfolio/invoices/{inv['id']}/deadlines", json={'review_on': str(business_today()+timedelta(days=5)),
        'kind':'limitation_review', 'basis':'Юрист проверяет признание долга и срок по договору №1'})
    assert r.status_code == 201, r.text
    item = audit(client)['items'][0]
    assert any(f['code'] == 'legal_deadline' and f['severity'] == 'urgent' for f in item['findings'])
    assert item['next_action']['code'] == 'lawyer_review'


def test_audit_and_evidence_are_tenant_scoped(client):
    inv = invoice(client)
    run = audit(client)
    register(client, 'isolated-portfolio@example.ru')
    assert client.get('/api/portfolio').json()['latest'] is None
    assert client.get(f"/api/portfolio/runs/{run['id']}").status_code == 404
    assert client.post(f"/api/portfolio/invoices/{inv['id']}/evidence", json={'kind':'contract', 'reference':'Чужое',
        'occurred_on': str(business_today())}).status_code == 404


def test_export_prevents_spreadsheet_formula_injection(client):
    invoice(client, company='=HYPERLINK("https://evil.invalid")')
    run = audit(client)
    exported = client.get(f"/api/portfolio/runs/{run['id']}/export")
    assert exported.status_code == 200
    assert "'=HYPERLINK" in exported.text


def test_aggregate_only_source_is_visible_without_fabricating_invoice(client):
    body={'source_type':'reconciliation_act','source_ref':'Акт сверки №42','as_of':str(business_today()),'format':'csv',
        'content':'Покупатель;ИНН;Дебет;Кредит\nООО Только в ОСВ;7801234567;1000;0\n',
        'mapping':{'company':'Покупатель','inn':'ИНН','ending_debit':'Дебет','ending_credit':'Кредит'}}
    result=client.post('/api/accounting/preview',json=body).json()
    r=client.post(f"/api/accounting/imports/{result['id']}/approve",json={'reason':'Принят для проверки первички','selected_rows':[2]})
    assert r.status_code==200,r.text
    run=audit(client)
    assert any(f['code']=='aggregate_without_documents' for f in run['findings'])
    assert run['items']==[] and run['totals']['outstanding']==0
    assert client.get('/api/portfolio').json()['stale'] is False


def test_missed_first_installment_detected_before_final_promise_date(client,monkeypatch):
    inv=invoice(client)
    later=business_today()+timedelta(days=10)
    r=client.post(f"/api/finance/invoices/{inv['id']}/promise",json={'amount':100000,'date':str(later),
        'idempotency_key':'portfolio-installments','installments':[{'date':str(business_today()),'amount':50000},{'date':str(later),'amount':50000}]})
    assert r.status_code==200,r.text
    from server import portfolio
    tomorrow=business_today()+timedelta(days=1)
    monkeypatch.setattr(portfolio,'business_today',lambda:tomorrow)
    run=audit(client)
    assert any(f['code']=='broken_promise' for f in run['items'][0]['findings'])


def test_paid_invoice_keeps_explicit_court_deadline_until_resolved(client):
    inv=invoice(client)
    d=client.post(f"/api/portfolio/invoices/{inv['id']}/deadlines",json={'kind':'court_review',
        'review_on':str(business_today()+timedelta(days=3)),'basis':'Проверить отказ от требований после добровольной оплаты'}).json()
    assert client.post(f"/api/invoices/{inv['id']}/payments",json={'amount':inv['amount'],'paid_on':str(business_today()),'reference':'CLOSED-LEGAL'}).status_code==200
    run=audit(client)
    assert any(f['code']=='legal_deadline' for f in run['items'][0]['findings'])
    assert run['items'][0]['balance']==0 and run['items'][0]['next_action']['code']=='lawyer_review'
    completed=client.post(f"/api/portfolio/deadlines/{d['id']}/resolve",json={'reason':'Юрист проверил дело и оформил необходимые заявления'})
    assert completed.status_code==200,completed.text
    run=audit(client)
    assert not any(f['code']=='legal_deadline' for f in run['items'][0]['findings'])
    assert run['items'][0]['next_action']['code']=='closed'


def test_small_debt_exposes_deterministic_court_cost_not_invented_recovery_probability(client):
    invoice(client, amount=100000)
    item=audit(client)['items'][0]
    assert item['economics']['claim_duty']==1000000
    assert item['economics']['basis']=='principal_only'
    assert any(f['code']=='court_cost_review' for f in item['findings'])


def prepared_legal_document(client):
    from test_legal_api import case,evidence,document
    inv,item=case(client)
    evidence(client,item['id'],'contract','Договор № П-1','2026-07-01')
    evidence(client,item['id'])
    doc=document(client,item['id'],sanction='none')
    return inv,item,doc


def test_fresh_legal_document_uses_same_snapshot_authority_as_case_api(client):
    inv,case,doc=prepared_legal_document(client)
    assert doc['stale'] is False
    item=next(item for item in audit(client)['items'] if item['invoice_id']==inv['id'])
    assert 'stale_document' not in {finding['code'] for finding in item['findings']}
    assert client.patch('/api/settings',json={'bank_details':'Новые банковские реквизиты для всех исходящих документов'}).status_code==200
    legal=client.get(f"/api/legal/cases/{case['id']}").json()
    assert next(row for row in legal['documents'] if row['id']==doc['id'])['stale'] is True
    assert 'stale_document' in {finding['code'] for finding in audit(client)['items'][0]['findings']}


def test_audit_input_explicitly_contains_sender_snapshot(client):
    from server import portfolio
    from server.database import database
    inv=invoice(client)
    audit(client)
    with database(client.app.state.config,write=True) as c:
        tenant=c.execute('SELECT tenant_id FROM invoices WHERE id=?',(inv['id'],)).fetchone()['tenant_id']
        before=portfolio.inputs(c,tenant)
        # Isolate sender input from the normal PATCH route's invoice revision bump.
        c.execute('UPDATE settings SET sender_name=? WHERE tenant_id=?',('Изменившийся отправитель',tenant))
        after=portfolio.inputs(c,tenant)
        assert before['invoices']==after['invoices']
    assert 'sender' in before and before['sender']!=after['sender']
    assert portfolio.snapshot(before)!=portfolio.snapshot(after)
    assert client.get('/api/portfolio').json()['stale'] is True


def test_paid_invoice_with_older_accounting_balance_is_discrepancy_not_missing_invoice(client):
    inv=invoice(client)
    body={'source_type':'reconciliation_act','source_ref':'Акт до оплаты',
        'as_of':str(business_today()-timedelta(days=1)),'format':'csv',
        'content':'Покупатель;ИНН;Дебет;Кредит\nООО Покупатель;7701234567;1000;0\n',
        'mapping':{'company':'Покупатель','inn':'ИНН','ending_debit':'Дебет','ending_credit':'Кредит'}}
    staged=client.post('/api/accounting/preview',json=body).json()
    approved=client.post(f"/api/accounting/imports/{staged['id']}/approve",json={'reason':'Проверен остаток на дату источника','selected_rows':[2]})
    assert approved.status_code==200,approved.text
    assert client.post(f"/api/invoices/{inv['id']}/payments",json={'amount':inv['amount'],'paid_on':str(business_today()),'reference':'AFTER-SOURCE'}).status_code==200
    run=audit(client)
    assert len(run['items'])==1 and run['items'][0]['balance']==0
    assert 'aggregate_without_documents' not in {finding['code'] for finding in run['findings']}
    finding=next(finding for finding in run['findings'] if finding['code']=='accounting_discrepancy')
    assert finding['evidence'][0]['as_of']==body['as_of']
    assert run['totals']['discrepancies']==1


def test_partial_promise_does_not_silence_remaining_unpromised_debt(client,monkeypatch):
    from server import portfolio
    inv=invoice(client)
    for kind in ('contract','performance','payment_terms'):
        assert client.post(f"/api/portfolio/invoices/{inv['id']}/evidence",json={
            'kind':kind,'reference':'Проверенный первичный документ','occurred_on':inv['issued_on']}).status_code==201
    monkeypatch.setattr(portfolio,'_registry',lambda *args:{inv['inn']:{'status':'completed',
        'checked_at':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
        'provider':'reviewed-fixture','result':{'registration_status':'ACTIVE'}}})
    due=str(business_today()+timedelta(days=7))
    assert client.post(f"/api/finance/invoices/{inv['id']}/promise",json={
        'amount':30000,'date':due,'idempotency_key':'partial-audit'}).status_code==200
    partial=audit(client)['items'][0]
    assert partial['next_action']['code']=='contact'
    assert 'partial_promise' in {finding['code'] for finding in partial['findings']}
    assert client.post(f"/api/finance/invoices/{inv['id']}/promise",json={
        'amount':100000,'date':due,'idempotency_key':'full-audit'}).status_code==200
    full=audit(client)['items'][0]
    assert full['next_action']['code']=='wait_promise'
    assert 'partial_promise' not in {finding['code'] for finding in full['findings']}


def test_portfolio_registry_freshness_matches_twenty_four_hour_connector_limit():
    from datetime import datetime,timezone
    from server.portfolio import _registry_view
    checked=datetime.now(timezone.utc)-timedelta(hours=25)
    result=_registry_view({'status':'completed','checked_at':checked.isoformat(),
        'result':{'registration_status':'ACTIVE'}},business_today())
    assert result['fresh'] is False


def test_each_latest_document_kind_is_audited_and_superseded_versions_are_ignored(client):
    from test_legal_api import document,facts
    inv,case,old_claim=prepared_legal_document(client)
    old_order=document(client,case['id'],kind='court_order',sanction='none')
    changed=client.patch(f"/api/legal/cases/{case['id']}",json={
        'facts':facts(due_basis='Уточнённое основание срока: пункт 3.2 договора')})
    assert changed.status_code==200,changed.text
    fresh_claim=document(client,case['id'],kind='pretrial_claim',sanction='none')
    versions={row['id']:row for row in client.get(f"/api/legal/cases/{case['id']}").json()['documents']}
    assert versions[old_order['id']]['stale'] is True
    assert versions[old_claim['id']]['stale'] is True
    assert versions[fresh_claim['id']]['stale'] is False
    assert 'stale_document' in {finding['code'] for finding in audit(client)['items'][0]['findings']}
    fresh_order=document(client,case['id'],kind='court_order',sanction='none')
    assert fresh_order['stale'] is False
    assert 'stale_document' not in {finding['code'] for finding in audit(client)['items'][0]['findings']}
