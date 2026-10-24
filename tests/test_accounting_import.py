"""Mapped 1C aggregate-source import must never fabricate individual invoices."""
import base64
import importlib
import io
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from server.business_time import business_today


@pytest.fixture
def client(tmp_path,monkeypatch):
    for key in ('DATABASE_URL','APP_URL','RENDER_EXTERNAL_URL','SMTP_HOST','SMTP_FROM'):
        monkeypatch.delenv(key,raising=False)
    monkeypatch.setenv('APP_ENV','test');monkeypatch.setenv('SECURE_COOKIES','false')
    monkeypatch.setenv('DATABASE_PATH',str(tmp_path/'accounting.db'))
    main=importlib.import_module('server.main')
    with TestClient(main.create_app()) as c:
        response=c.post('/api/auth/register',json={'name':'Бухгалтер','company':'Поставщик','email':'accounting@example.ru','password':'Accounting-testing-2026'})
        c.headers['X-CSRF-Token']=response.json()['csrf_token']
        yield c


def payload(content=None,**changes):
    data={'source_type':'osv62','source_ref':'1С: ОСВ62 октябрь','as_of':str(business_today()),'format':'csv','content':content or 'Контрагент;ИНН;НачД;НачК;ОборД;ОборК;КонД;КонК\nООО Берёзка;7701234567;1000;0;200;400;800;0\n','mapping':{'company':'Контрагент','inn':'ИНН','opening_debit':'НачД','opening_credit':'НачК','debit_turnover':'ОборД','credit_turnover':'ОборК','ending_debit':'КонД','ending_credit':'КонК'}}
    data.update(changes);return data


def add_invoice(client,amount=70000):
    response=client.post('/api/invoices',json={'company':'ООО Берёзка','inn':'7701234567','number':'A-1','issued_on':str(business_today()-timedelta(days=20)),'due_on':str(business_today()-timedelta(days=2)),'amount':amount})
    assert response.status_code==201,response.text
    return response.json()


def preview(client,data):
    response=client.post('/api/accounting/preview',json=data)
    assert response.status_code==200,response.text
    return response.json()


def test_osv_mapping_preview_compares_current_ledger_and_stores_source_only_after_approval(client):
    inv=add_invoice(client)
    result=preview(client,payload(as_of=str(business_today()-timedelta(days=5))))
    assert result['errors']==[] and result['comparison_basis']=='current_ledger'
    row=result['items'][0]
    assert (row['source_balance'],row['ledger_current_balance'],row['discrepancy'])==(80000,70000,10000)
    assert row['requires_review'] is True
    assert client.get('/api/accounting/reconciliations').json()['items']==[]
    approved=client.post(f"/api/accounting/imports/{result['id']}/approve",json={'reason':'Согласовано бухгалтером, расхождение изучается','selected_rows':[2]})
    assert approved.status_code==200 and approved.json()['imported']==1
    stored=client.get('/api/accounting/reconciliations').json()['items'][0]
    assert stored['source_ref']==payload()['source_ref'] and stored['comparison_basis']=='current_ledger'
    assert stored['counterparty_id']==inv['counterparty_id']
    assert client.get('/api/invoices').json()['items'][0]['balance']==70000
    assert client.get('/api/overview').json()['invoice_count']==1


def test_reconciliation_act_creates_counterparty_evidence_without_invoice(client):
    data=payload('Покупатель;Идентификатор;Дебет;Кредит\nООО Север;7801234567;600;0\n',source_type='reconciliation_act',source_ref='Акт №7',mapping={'company':'Покупатель','inn':'Идентификатор','ending_debit':'Дебет','ending_credit':'Кредит'})
    result=preview(client,data)
    assert result['errors']==[] and result['items'][0]['ledger_current_balance']==0
    assert client.post(f"/api/accounting/imports/{result['id']}/approve",json={'reason':'Скан акта принят для сверки','selected_rows':[2]}).status_code==200
    assert client.get('/api/finance/counterparties').json()['items'][0]['inn']=='7801234567'
    assert client.get('/api/invoices').json()['items']==[]


def test_duplicate_totals_and_arithmetic_errors_cannot_be_approved(client):
    content='Контрагент;ИНН;НачД;НачК;ОборД;ОборК;КонД;КонК\nООО Север;7801234567;1000;0;0;400;600;0\nИтого;;1000;0;0;400;600;0\nООО Юг;7701234567;1000;0;0;400;900;0\n'
    result=preview(client,payload(content))
    assert {e['row'] for e in result['errors']}=={3,4}
    assert client.post(f"/api/accounting/imports/{result['id']}/approve",json={'reason':'Нельзя учесть итог','selected_rows':[2,3]}).status_code==422
    good=client.post(f"/api/accounting/imports/{result['id']}/approve",json={'reason':'Выбрана строка без итогов','selected_rows':[2]})
    assert good.status_code==200
    assert len(client.get('/api/accounting/reconciliations').json()['items'])==1
    assert client.get('/api/invoices').json()['items']==[]


def test_repeated_counterparty_rows_are_not_summed_or_approved_twice(client):
    source=payload()['content'];source+=source.splitlines()[1]+'\n'
    result=preview(client,payload(source))
    assert {e['row'] for e in result['errors']}=={2,3}
    assert client.post(f"/api/accounting/imports/{result['id']}/approve",json={'reason':'Дубликаты','selected_rows':[2]}).status_code==422


def test_approval_is_idempotent_but_changed_selection_or_source_cannot_overwrite(client):
    result=preview(client,payload())
    url=f"/api/accounting/imports/{result['id']}/approve";body={'reason':'Сверено','selected_rows':[2]}
    first=client.post(url,json=body)
    assert first.status_code==200 and client.post(url,json=body).json()==first.json()
    assert client.post(url,json={**body,'selected_rows':[]}).status_code==422
    repeated=preview(client,payload())
    assert client.post(f"/api/accounting/imports/{repeated['id']}/approve",json=body).json()['skipped']==1
    changed=preview(client,payload(payload()['content'].replace(';200;400;800;', ';200;300;900;')))
    assert client.post(f"/api/accounting/imports/{changed['id']}/approve",json=body).status_code==409
    assert client.get('/api/accounting/reconciliations').json()['items'][0]['source_balance']==80000


def test_ledger_change_after_preview_requires_new_comparison(client):
    inv=add_invoice(client);result=preview(client,payload())
    client.post(f"/api/invoices/{inv['id']}/payments",json={'amount':1000,'paid_on':str(business_today()),'reference':'NEW'})
    assert client.post(f"/api/accounting/imports/{result['id']}/approve",json={'reason':'Устаревшее сравнение','selected_rows':[2]}).status_code==409
    assert client.get('/api/accounting/reconciliations').json()['items']==[]


def test_mapping_discovery_duplicate_headers_and_unknown_fields_fail_explicitly(client):
    result=preview(client,payload(mapping={}))
    assert result['columns'][0]['label']=='Контрагент' and result['items']==[] and result['errors']
    result=preview(client,payload(mapping={**payload()['mapping'],'unsupported':'ИНН'}))
    assert result['errors'] and result['items']==[]
    duplicate=payload('A;A;Д;К\nБерёзка;7701234567;600;0\n',source_type='reconciliation_act',mapping={'company':'A','inn':'column_2','ending_debit':'Д','ending_credit':'К'})
    assert preview(client,duplicate)['errors']
    duplicate['mapping']['company']='column_1'
    assert preview(client,duplicate)['errors']==[]


def workbook_content(rows):
    from openpyxl import Workbook
    workbook=Workbook();sheet=workbook.active
    for row in rows:sheet.append(row)
    buffer=io.BytesIO();workbook.save(buffer)
    return base64.b64encode(buffer.getvalue()).decode('ascii')


def test_xlsx_real_workbook_uses_same_mapping_and_never_executes_formula(client):
    headers=['Контрагент','ИНН','НачД','НачК','ОборД','ОборК','КонД','КонК']
    rows=[headers,['ООО Берёзка','7701234567',1000,0,200,400,800,0]]
    result=preview(client,payload(workbook_content(rows),format='xlsx'))
    assert result['errors']==[] and result['items'][0]['source_balance']==80000
    rows[1][-2]='=SUM(C2:E2)'
    rejected=preview(client,payload(workbook_content(rows),format='xlsx'))
    assert rejected['errors'] and rejected['items']==[]


@pytest.mark.parametrize('value',['not-base64','UEsDBA=='])
def test_malformed_xlsx_returns_validation_not_server_error(client,value):
    result=preview(client,payload(value,format='xlsx'))
    assert result['errors'] and result['items']==[]


def test_accounting_resources_cannot_cross_tenants(client):
    result=preview(client,payload())
    response=client.post('/api/auth/register',json={'name':'Другой','company':'Другой','email':'other-accounting@example.ru','password':'Accounting-other-2026'})
    client.headers['X-CSRF-Token']=response.json()['csrf_token']
    assert client.post(f"/api/accounting/imports/{result['id']}/approve",json={'reason':'Нельзя','selected_rows':[2]}).status_code==404
    assert client.get('/api/accounting/reconciliations').json()['items']==[]
