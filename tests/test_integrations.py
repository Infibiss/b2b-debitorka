import json
import os
import sqlite3
from datetime import datetime, timezone
from datetime import timedelta
from decimal import Decimal

import pytest

from test_bank_exchange import client, OWN, OTHER, preview, approve
from test_storage_pg import postgres_client, postgres_config
from server.business_time import business_today


def binding(client,monkeypatch,provider='dadata',**extra):
    with sqlite3.connect(os.environ['DATABASE_PATH']) as connection:
        tenant=connection.execute('SELECT tenant_id FROM users WHERE id=?',(client.get('/api/auth/me').json()['user']['id'],)).fetchone()[0]
    monkeypatch.setenv('MANDATO_INTEGRATIONS_JSON',json.dumps([{'tenant_id':tenant,'provider':provider,'token':'SECRET-provider-token',**extra}]))
    return tenant


def test_public_account_never_inherits_operator_credentials(client,monkeypatch):
    monkeypatch.setenv('MANDATO_INTEGRATIONS_JSON',json.dumps([{'tenant_id':'another-tenant','provider':'dadata','token':'SECRET'}]))
    response=client.post('/api/integrations/registry/check',json={'inn':'7707083893'})
    assert response.status_code==200 and response.json()['status']=='unconfigured'
    assert 'SECRET' not in response.text
    assert response.json()['coverage']['fssp']=='unverified'


def test_registry_exact_identity_no_match_and_failures_are_not_clean(client,monkeypatch):
    from server import integration_providers as p
    binding(client,monkeypatch)
    monkeypatch.setattr(p,'request_json',lambda *a,**k:{'suggestions':[{'value':'Другая','data':{'inn':'7801234567','state':{'status':'ACTIVE'}}}]})
    response=client.post('/api/integrations/registry/check',json={'inn':'7707083893'})
    assert response.json()['status']=='unavailable' and 'SECRET' not in response.text
    monkeypatch.setattr(p,'request_json',lambda *a,**k:{'suggestions':[]})
    assert client.post('/api/integrations/registry/check',json={'inn':'7707083893'}).json()['status']=='no_match'
    def broken(*a,**k):raise p.ProviderUnavailable('SECRET-provider-token')
    monkeypatch.setattr(p,'request_json',broken)
    response=client.post('/api/integrations/registry/check',json={'inn':'7707083893'})
    assert response.json()['status']=='unavailable' and 'SECRET' not in response.text


def test_registry_keeps_provider_record_change_date_and_coverage(client,monkeypatch):
    from server import integration_providers as p
    binding(client,monkeypatch)
    snapshot=int(datetime.now(timezone.utc).timestamp()*1000)
    monkeypatch.setattr(p,'request_json',lambda *a,**k:{'suggestions':[{'value':'ПАО Сбербанк','data':{'inn':'7707083893','ogrn':'1027700132195','state':{'status':'ACTIVE','actuality_date':snapshot}}}]})
    result=client.post('/api/integrations/registry/check',json={'inn':'7707083893'}).json()
    assert result['status']=='completed' and result['result']['inn']=='7707083893'
    assert result['result']['provider_record_date'] and result['coverage']['court_cases']=='unverified'
    assert 'risk_free' not in json.dumps(result)
    assert client.post('/api/integrations/registry/check',json={'inn':'7707083894'}).status_code==422


def test_one_c_stages_normalized_evidence_then_explicit_approval(client,monkeypatch):
    from server import integration_providers as p
    binding(client,monkeypatch,'one_c',base_url='https://erp.example.ru/base/odata/standard.odata',username='reader',password='SECRET-password',entity='Document_Invoice',mapping={'source_id':'Ref_Key','company':'Company','inn':'INN','number':'Number','amount':'Total'})
    calls=[]
    def read(*args,**kwargs):
        calls.append((args,kwargs));return {'value':[{'Ref_Key':'source-guid','Company':'ООО Берёзка','INN':'7707083893','Number':'42','Total':'100.01','Password':'DO-NOT-PERSIST'}]}
    monkeypatch.setattr(p,'request_json',read)
    response=client.post('/api/integrations/one_c/read')
    assert response.status_code==200,response.text
    result=response.json();assert result['status']=='completed' and result['items'][0]['amount']==10001
    assert 'SECRET' not in response.text and 'DO-NOT-PERSIST' not in response.text
    assert client.get('/api/invoices').json()['items']==[]
    approved=client.post('/api/integrations/runs/'+result['id']+'/approve',json={'reason':'Сверено с первичным документом','selected_rows':[1]})
    assert approved.status_code==200 and approved.json()['imported']==1
    assert client.get('/api/invoices').json()['items']==[]
    assert len(calls)==1


def test_network_rejects_private_destination_and_insecure_scheme(monkeypatch):
    from server import integration_providers as p
    monkeypatch.setattr(p.socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('127.0.0.1',443))])
    with pytest.raises(p.ProviderUnavailable):p.request_json('https://suggestions.dadata.ru/test',{})
    with pytest.raises(p.ProviderUnavailable):p.request_json('http://localhost/test',{})


@pytest.mark.parametrize('status,length,body',[(302,None,b'{}'),(200,'2000001',b'{}'),(200,None,b'not-json'),(200,None,b'{"token":"SECRET"')])
def test_network_rejects_redirects_oversize_and_malformed_bodies(monkeypatch,status,length,body):
    from server import integration_providers as p
    class Response:
        def __init__(self):self.status=status;self.sent=False
        def getheader(self,key,default=None):return length if key=='Content-Length' else default
        def read1(self,size):
            if self.sent:return b''
            self.sent=True;return body
    class Connection:
        def __init__(self,*a,**k):self.sock=None
        def connect(self):pass
        def request(self,*a,**k):pass
        def getresponse(self):return Response()
        def close(self):pass
    monkeypatch.setattr(p.socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('8.8.8.8',443))])
    monkeypatch.setattr(p.http.client,'HTTPSConnection',Connection)
    with pytest.raises(p.ProviderUnavailable):p.request_json('https://suggestions.dadata.ru/test',{'Authorization':'Token SECRET'})


def test_diadoc_uses_documented_page_size_and_never_stores_content_or_signs(client,monkeypatch):
    from server import integration_providers as p
    binding(client,monkeypatch,'diadoc',box_id='tenant-box-guid')
    calls=[]
    def read(url,headers,**kwargs):
        calls.append(url)
        assert 'count=100' in url and 'filterCategory=Any.Inbound' in url
        return {'TotalCount':101,'Documents':[{'MessageId':'message-1','EntityId':'entity-1','DocumentNumber':'42','DocumentDate':'01.10.2026','FileName':'Акт.xml','DocumentType':'UniversalTransferDocument','Content':{'Data':'SECRET-CONTENT'}}]}
    monkeypatch.setattr(p,'request_json',read)
    response=client.post('/api/integrations/diadoc/read')
    assert response.status_code==200,response.text
    data=response.json()
    assert data['coverage']['complete'] is False and data['coverage']['signature_verified'] is False
    assert 'SECRET' not in response.text
    approval=client.post('/api/integrations/runs/'+data['id']+'/approve',json={'reason':'Сверено','selected_rows':[1]})
    assert approval.status_code==200 and approval.json()['ledger_effect']=='none'
    assert len(calls)==1 and client.get('/api/invoices').json()['items']==[]


def test_direct_bank_statement_requires_approval_shares_file_identity_and_detects_source_changes(client,monkeypatch):
    from server import integration_providers as p
    binding(client,monkeypatch,'tbank',account_number=OWN)
    today=business_today();stamp=today.isoformat()+'T00:00:00Z'
    operation={'operationId':'operation-1','operationDate':stamp,'docDate':stamp,'operationStatus':'Transaction','accountNumber':OWN,'accountCurrencyDigitalCode':'643','typeOfOperation':'Credit','payVo':'payment-order','documentNumber':'42','accountAmount':Decimal('1234.56'),'payPurpose':'Оплата по счету 42','payer':{'acct':OTHER,'inn':'7707083893','name':'ООО Берёзка'},'receiver':{'acct':OWN}}
    def read(url,headers,**kwargs):
        assert url.startswith('https://business.tbank.ru/openapi/api/v1/statement?')
        # Provider I/O occurs before opening a write transaction.
        with sqlite3.connect(os.environ['DATABASE_PATH'],timeout=0) as connection:connection.execute('BEGIN IMMEDIATE');connection.rollback()
        return {'operations':[operation],'nextCursor':'remaining-page'}
    monkeypatch.setattr(p,'request_json',read)
    request={'from_on':today.isoformat(),'to_on':(today+timedelta(days=1)).isoformat()}
    result=client.post('/api/integrations/tbank/read',json=request)
    assert result.status_code==200,result.text
    data=result.json();assert data['items'][0]['amount']==123456 and data['coverage']['complete'] is False
    assert client.get('/api/finance/bank-payments').json()['items']==[]
    url='/api/integrations/runs/'+data['id']+'/approve';body={'reason':'Поступление проверено','selected_rows':[1]}
    assert client.post(url,json=body).json()['imported']==1
    assert client.post(url,json=body).json()['imported']==1
    assert approve(client,preview(client)).json()['skipped']==1
    assert len(client.get('/api/finance/bank-payments').json()['items'])==1
    operation['accountAmount']=Decimal('2')
    changed=client.post('/api/integrations/tbank/read',json=request).json()
    assert client.post('/api/integrations/runs/'+changed['id']+'/approve',json=body).status_code==409


@pytest.mark.parametrize('change',[{'accountNumber':OTHER},{'accountCurrencyDigitalCode':'840'},{'operationStatus':'Authorization'},{'accountAmount':Decimal('1.001')}])
def test_direct_bank_refuses_wrong_account_currency_unsettled_and_subkopeks(client,monkeypatch,change):
    from server import integration_providers as p
    binding(client,monkeypatch,'tbank',account_number=OWN)
    today=business_today();stamp=today.isoformat()+'T00:00:00Z'
    operation={'operationId':'operation-1','operationDate':stamp,'docDate':stamp,'operationStatus':'Transaction','accountNumber':OWN,'accountCurrencyDigitalCode':'643','typeOfOperation':'Credit','payVo':'payment-order','documentNumber':'42','accountAmount':Decimal('1234.56'),'payer':{'acct':OTHER},'receiver':{'acct':OWN},**change}
    monkeypatch.setattr(p,'request_json',lambda *a,**k:{'operations':[operation]})
    data=client.post('/api/integrations/tbank/read',json={'from_on':today.isoformat(),'to_on':(today+timedelta(days=1)).isoformat()}).json()
    assert data['status']=='unavailable' and data['items']==[]
    assert client.get('/api/finance/bank-payments').json()['items']==[]


def test_integration_runs_and_registry_cannot_cross_tenants(client,monkeypatch):
    from server import integration_providers as p
    binding(client,monkeypatch)
    monkeypatch.setattr(p,'request_json',lambda *a,**k:{'suggestions':[]})
    result=client.post('/api/integrations/registry/check',json={'inn':'7707083893'}).json()
    auth=client.post('/api/auth/register',json={'name':'Другой','company':'Другой','email':'other-integrations@example.ru','password':'Other-integration-2026'})
    client.headers['X-CSRF-Token']=auth.json()['csrf_token']
    assert client.get('/api/integrations/registry/checks').json()['items']==[]
    assert client.get('/api/integrations/runs/'+result['id']).status_code==404


def test_real_postgres_bank_approval_and_registry_use_same_tenant_contract(postgres_client):
    staged=preview(postgres_client)
    response=approve(postgres_client,staged)
    assert response.status_code==200 and response.json()['imported']==1
    assert approve(postgres_client,staged).json()==response.json()
    check=postgres_client.post('/api/integrations/registry/check',json={'inn':'7707083893'})
    assert check.status_code==200 and check.json()['status']=='unconfigured'
    assert postgres_client.get('/api/integrations/registry/checks').json()['items'][0]['inn']=='7707083893'
    batch=postgres_client.post('/api/integrations/registry/check-batch',json={'inns':['7707083893']})
    assert batch.status_code==200 and batch.json()['items'][0]['status']=='unconfigured'
    assert postgres_client.get('/api/integrations/registry/batches/'+batch.json()['batch_id']).json()==batch.json()


def test_one_c_full_page_without_nextlink_does_not_claim_complete(client,monkeypatch):
    from server import integration_providers as p
    binding(client,monkeypatch,'one_c',base_url='https://erp.example.ru/base/odata/standard.odata',username='reader',password='SECRET',entity='Document_Invoice',mapping={'source_id':'Ref_Key','company':'Company'})
    monkeypatch.setattr(p,'request_json',lambda *a,**k:{'value':[{'Ref_Key':str(i),'Company':'Компания '+str(i)} for i in range(500)]})
    data=client.post('/api/integrations/one_c/read').json()
    assert data['status']=='completed' and len(data['items'])==500
    assert data['coverage']['complete'] is False


def test_tbank_operator_known_own_accounts_are_excluded_from_receipts(client,monkeypatch):
    from server import integration_providers as p
    binding(client,monkeypatch,'tbank',account_number=OWN,excluded_own_accounts=[OTHER])
    today=business_today();stamp=today.isoformat()+'T00:00:00Z'
    operation={'operationId':'own-transfer','operationDate':stamp,'docDate':stamp,'operationStatus':'Transaction','accountNumber':OWN,'accountCurrencyDigitalCode':'643','typeOfOperation':'Credit','payVo':'payment-order','documentNumber':'42','accountAmount':Decimal('1234.56'),'payer':{'acct':OTHER},'receiver':{'acct':OWN}}
    monkeypatch.setattr(p,'request_json',lambda *a,**k:{'operations':[operation]})
    data=client.post('/api/integrations/tbank/read',json={'from_on':today.isoformat(),'to_on':(today+timedelta(days=1)).isoformat()}).json()
    assert data['status']=='completed' and data['items'][0]['direction']=='own_transfer'
    assert data['items'][0]['approvable'] is False
    approval=client.post('/api/integrations/runs/'+data['id']+'/approve',json={'reason':'Не внешние деньги','selected_rows':[1]})
    assert approval.status_code==422
    assert client.get('/api/finance/bank-payments').json()['items']==[]


def test_tbank_explicit_cursor_reads_next_bounded_page(client,monkeypatch):
    from server import integration_providers as p
    binding(client,monkeypatch,'tbank',account_number=OWN)
    calls=[]
    def read(url,*args,**kwargs):
        calls.append(url)
        return {'operations':[],'nextCursor':'page/2==' if len(calls)==1 else None}
    monkeypatch.setattr(p,'request_json',read)
    today=business_today();body={'from_on':today.isoformat(),'to_on':(today+timedelta(days=1)).isoformat()}
    first=client.post('/api/integrations/tbank/read',json=body)
    assert first.status_code==200 and first.json()['status']=='partial'
    assert first.json()['coverage']['next_cursor']=='page/2=='
    second=client.post('/api/integrations/tbank/read',json={**body,'cursor':first.json()['coverage']['next_cursor']})
    assert second.status_code==200 and second.json()['coverage']['complete'] is True
    assert 'cursor=page%2F2%3D%3D' in calls[-1]


def test_one_c_receivables_flow_uses_existing_finance_preview_and_explicit_approval(client,monkeypatch):
    from server import integration_providers as p
    today=business_today()
    binding(client,monkeypatch,'one_c',data_kind='receivables',base_url='https://erp.example.ru/base/odata/standard.odata',username='reader',password='SECRET',entity='Document_Invoice',mapping={'source_id':'Ref_Key','company':'Company','inn':'INN','number':'Number','issued_on':'Date','due_on':'Due','amount':'Total','balance':'Balance'})
    monkeypatch.setattr(p,'request_json',lambda *a,**k:{'value':[{'Ref_Key':'invoice-guid','Company':'ООО Берёзка','INN':'7707083893','Number':'42','Date':str(today-timedelta(days=20))+'T00:00:00','Due':str(today-timedelta(days=2))+'T00:00:00','Total':'1000.00','Balance':'600.00'}]})
    read=client.post('/api/integrations/one_c/read').json()
    assert read['status']=='completed'
    source=client.post('/api/integrations/runs/'+read['id']+'/invoice-preview',json={'selected_rows':[1]})
    assert source.status_code==200,source.text
    preview_data=source.json()
    assert preview_data['items'][0]['amount']==100000 and preview_data['items'][0]['paid_amount']==40000
    assert preview_data['source_run_id']==read['id']
    assert client.get('/api/invoices').json()['items']==[]
    approved=client.post('/api/finance/imports/'+preview_data['id']+'/approve',json={'reason':'Срок и сальдо документа сверены'})
    assert approved.status_code==200,approved.text
    invoice=client.get('/api/invoices').json()['items'][0]
    assert invoice['balance']==60000 and invoice['opening_paid_amount']==40000
    assert client.get('/api/finance/bank-payments').json()['items']==[]


def test_metadata_and_missing_due_or_open_balance_cannot_become_invoices(client,monkeypatch):
    from server import integration_providers as p
    binding(client,monkeypatch,'one_c',base_url='https://erp.example.ru/base/odata/standard.odata',username='reader',password='SECRET',entity='Document_Invoice',mapping={'source_id':'Ref_Key','company':'Company'})
    monkeypatch.setattr(p,'request_json',lambda *a,**k:{'value':[{'Ref_Key':'invoice-guid','Company':'ООО Берёзка'}]})
    metadata=client.post('/api/integrations/one_c/read').json()
    url='/api/integrations/runs/'+metadata['id']+'/invoice-preview'
    assert client.post(url,json={'selected_rows':[1]}).status_code==422
    binding(client,monkeypatch,'one_c',data_kind='receivables',base_url='https://erp.example.ru/base/odata/standard.odata',username='reader',password='SECRET',entity='Document_Invoice',mapping={'source_id':'Ref_Key','company':'Company'})
    missing=client.post('/api/integrations/one_c/read').json()
    assert client.post('/api/integrations/runs/'+missing['id']+'/invoice-preview',json={'selected_rows':[1]}).status_code==422
    assert client.get('/api/invoices').json()['items']==[]


def test_public_bank_sandbox_uses_only_documented_fixed_data_and_cannot_approve_cash(client,monkeypatch):
    from server import integration_providers as p
    binding(client,monkeypatch,'tbank',account_number=OWN)
    calls=[]
    def read(url,headers,**kwargs):
        calls.append(url)
        assert url=='https://business.tbank.ru/openapi/sandbox/api/v1/statement?accountNumber=40702810110011000000&from=2024-04-26T21%3A00%3A00.000Z'
        assert headers['Authorization']=='Bearer TBankSandboxToken'
        return {'operations':[{'operationId':'sandbox-fixture-only','operationDate':'2022-02-02T20:07:04Z','accountNumber':'40702810510000710417','accountAmount':Decimal('484.50'),'operationStatus':'Transaction','typeOfOperation':'Credit','documentNumber':'175926'}]}
    monkeypatch.setattr(p,'request_json',read)
    response=client.post('/api/integrations/tbank/sandbox/read',json={'mode':'sandbox'})
    assert response.status_code==200,response.text
    result=response.json()
    assert result['environment']=='sandbox' and result['provider']=='tbank_sandbox'
    assert result['coverage']['ledger_effect']=='forbidden' and result['items'][0]['approvable'] is False
    assert result['items'][0]['source_id'].startswith('sandbox:')
    assert len(calls)==1 and 'SECRET' not in response.text
    assert client.post('/api/integrations/runs/'+result['id']+'/approve',json={'reason':'Не реальные деньги','selected_rows':[1]}).status_code==422
    assert client.post('/api/integrations/runs/'+result['id']+'/invoice-preview',json={'selected_rows':[1]}).status_code==422
    assert client.get('/api/finance/bank-payments').json()['items']==[]
    assert client.post('/api/integrations/tbank/sandbox/read',json={'mode':'production'}).status_code==422
    assert client.post('/api/integrations/tbank/read',json={'mode':'sandbox','from_on':'2026-10-01','to_on':'2026-10-24'}).status_code==422


def test_sandbox_works_without_any_tenant_credentials_and_production_mode_is_bound(client,monkeypatch):
    from server import integration_providers as p
    monkeypatch.setattr(p,'request_json',lambda *a,**k:{'operations':[]})
    assert client.post('/api/integrations/tbank/sandbox/read',json={'mode':'sandbox'}).json()['environment']=='sandbox'
    today=business_today()
    data=client.post('/api/integrations/tbank/read',json={'from_on':today.isoformat(),'to_on':(today+timedelta(days=1)).isoformat()}).json()
    assert data['status']=='unconfigured'
    with pytest.raises(p.ProviderUnavailable):p.read_tbank({'mode':'sandbox','account_number':OWN,'token':'SECRET'},today,today+timedelta(days=1))


def test_fresh_registry_query_old_record_change_date_remains_completed(client,monkeypatch):
    from server import integration_providers as p
    binding(client,monkeypatch)
    changed=int((datetime.now(timezone.utc)-timedelta(days=730)).timestamp()*1000)
    monkeypatch.setattr(p,'request_json',lambda *a,**k:{'suggestions':[{'value':'ПАО Сбербанк','data':{'inn':'7707083893','state':{'status':'ACTIVE','actuality_date':changed}}}]})
    result=client.post('/api/integrations/registry/check',json={'inn':'7707083893'}).json()
    assert result['status']=='completed'
    assert result['result']['provider_record_date'] and result['result']['provider_as_of'] is None
    assert result['coverage']['bankruptcy']=='unverified'


def test_registry_future_record_date_is_unavailable(client,monkeypatch):
    from server import integration_providers as p
    binding(client,monkeypatch)
    changed=int((datetime.now(timezone.utc)+timedelta(minutes=1)).timestamp()*1000)
    monkeypatch.setattr(p,'request_json',lambda *a,**k:{'suggestions':[{'value':'ПАО Сбербанк','data':{'inn':'7707083893','state':{'status':'ACTIVE','actuality_date':changed}}}]})
    assert client.post('/api/integrations/registry/check',json={'inn':'7707083893'}).json()['status']=='unavailable'


def test_missing_registry_change_date_is_explicit_unknown_metadata(client,monkeypatch):
    from server import integration_providers as p
    binding(client,monkeypatch)
    monkeypatch.setattr(p,'request_json',lambda *a,**k:{'suggestions':[{'value':'ПАО Сбербанк','data':{'inn':'7707083893','state':{'status':'ACTIVE'}}}]})
    result=client.post('/api/integrations/registry/check',json={'inn':'7707083893'}).json()
    assert result['status']=='completed'
    assert result['result']['provider_record_date'] is None and result['result']['provider_record_date_status']=='unknown'
    assert result['result']['provider_as_of'] is None and result['coverage']['fssp']=='unverified'


def fixture_inns(count=10):
    """Checksum-valid identifiers generated for mocked contract tests only."""
    result=[]
    for index in range(count):
        prefix=str(770100000+index)
        check=sum(int(digit)*weight for digit,weight in zip(prefix,[2,4,10,3,5,9,4,6,8]))%11%10
        result.append(prefix+str(check))
    return result


def test_registry_batch_bounds_concurrency_caches_and_releases_database_before_network(client,monkeypatch):
    import threading
    import time
    from server import integration_providers as p
    binding(client,monkeypatch)
    active=peak=calls=0;lock=threading.Lock()
    def read(*args,**kwargs):
        nonlocal active,peak,calls
        with lock:
            active+=1;calls+=1;peak=max(peak,active)
            with sqlite3.connect(os.environ['DATABASE_PATH'],timeout=0) as connection:
                connection.execute('BEGIN IMMEDIATE');connection.rollback()
        time.sleep(0.02)
        with lock:active-=1
        return {'suggestions':[]}
    monkeypatch.setattr(p,'request_json',read)
    inns=fixture_inns()
    response=client.post('/api/integrations/registry/check-batch',json={'inns':inns})
    assert response.status_code==200,response.text
    result=response.json()
    assert [item['inn'] for item in result['items']]==inns
    assert 1<peak<=4 and calls==10
    assert result['checked_count']==10 and result['cached_count']==0 and result['concurrency']==4
    assert all(item['status']=='no_match' and item['cached'] is False and item['batch_id']==result['batch_id'] for item in result['items'])
    repeated=client.post('/api/integrations/registry/check-batch',json={'inns':inns})
    assert repeated.status_code==200 and repeated.json()['cached_count']==10 and repeated.json()['checked_count']==0
    assert calls==10 and all(item['cached'] for item in repeated.json()['items'])
    assert len(client.get('/api/integrations/registry/checks').json()['items'])==10
    assert client.get('/api/integrations/registry/batches/'+result['batch_id']).json()['batch_id']==result['batch_id']


@pytest.mark.parametrize('inns',[[],fixture_inns(11),['7707083893','7707083893'],['7707083894'],[True]])
def test_registry_batch_strict_inn_count_and_duplicates(client,inns):
    assert client.post('/api/integrations/registry/check-batch',json={'inns':inns}).status_code==422


def test_registry_batch_failure_never_reuses_earlier_clean_result(client,monkeypatch):
    from server import integration_providers as p
    binding(client,monkeypatch)
    monkeypatch.setattr(p,'request_json',lambda *a,**k:{'suggestions':[{'value':'Тестовая организация','data':{'inn':'7707083893','state':{'status':'ACTIVE'}}}]})
    assert client.post('/api/integrations/registry/check',json={'inn':'7707083893'}).json()['status']=='completed'
    def unavailable(*args,**kwargs):raise p.ProviderUnavailable('SECRET-never-exposed')
    monkeypatch.setattr(p,'request_json',unavailable)
    assert client.post('/api/integrations/registry/check',json={'inn':'7707083893'}).json()['status']=='unavailable'
    response=client.post('/api/integrations/registry/check-batch',json={'inns':['7707083893']})
    assert response.status_code==200,response.text
    item=response.json()['items'][0]
    assert item['status']=='unavailable' and item['cached'] is False and item['result']=={}
    assert item['coverage']['fssp']=='unverified' and 'SECRET' not in response.text


def test_registry_batch_expired_cache_requires_new_read(client,monkeypatch):
    from server import integration_providers as p
    from server.database import database
    binding(client,monkeypatch)
    calls=[]
    monkeypatch.setattr(p,'request_json',lambda *a,**k:calls.append(1) or {'suggestions':[]})
    result=client.post('/api/integrations/registry/check',json={'inn':'7707083893'}).json()
    old=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat();result['checked_at']=old
    with database(client.app.state.config,write=True) as c:
        c.execute('UPDATE integration_registry_checks SET payload_json=?,created_at=? WHERE id=?',(json.dumps(result),old,result['id']))
    refreshed=client.post('/api/integrations/registry/check-batch',json={'inns':['7707083893']}).json()
    assert refreshed['cached_count']==0 and refreshed['checked_count']==1 and len(calls)==2


def test_registry_batches_cannot_reuse_owner_credentials_or_cached_results_across_tenants(client,monkeypatch):
    from server import integration_providers as p
    binding(client,monkeypatch)
    calls=[]
    monkeypatch.setattr(p,'request_json',lambda *a,**k:calls.append(1) or {'suggestions':[]})
    first=client.post('/api/integrations/registry/check-batch',json={'inns':['7707083893']}).json()
    auth=client.post('/api/auth/register',json={'name':'Другой','company':'Другой','email':'batch-other@example.ru','password':'Batch-other-testing-2026'})
    client.headers['X-CSRF-Token']=auth.json()['csrf_token']
    assert client.get('/api/integrations/registry/batches/'+first['batch_id']).status_code==404
    second=client.post('/api/integrations/registry/check-batch',json={'inns':['7707083893']}).json()
    assert second['items'][0]['status']=='unconfigured' and second['cached_count']==0
    assert len(calls)==1


@pytest.fixture
def isolated_dns_pool(monkeypatch):
    import threading
    from server import integration_providers as p
    pool=p._DNSResolverPool(workers=4,capacity=8)
    slots=threading.BoundedSemaphore(8)
    monkeypatch.setattr(p,'_DNS_POOL',pool)
    monkeypatch.setattr(p,'_DNS_SLOTS',slots)
    try:yield p,pool,slots
    finally:pool.shutdown(wait=False,cancel_futures=True)


def test_slow_dns_obeys_request_deadline_and_releases_slot_on_actual_completion(monkeypatch,isolated_dns_pool):
    import threading
    import time
    p,pool,slots=isolated_dns_pool
    release=threading.Event();finished=threading.Event();captured=[]
    submit=pool.submit
    def capture(*args,**kwargs):
        future=submit(*args,**kwargs);captured.append(future);return future
    monkeypatch.setattr(pool,'submit',capture)
    def slow(*args,**kwargs):
        release.wait(1)
        return [(2,1,6,'',('8.8.8.8',443))]
    monkeypatch.setattr(p.socket,'getaddrinfo',slow)
    started=time.monotonic()
    try:
        with pytest.raises(p.ProviderUnavailable):p.request_json('https://suggestions.dadata.ru/test',{},deadline_seconds=0.05)
        assert time.monotonic()-started<0.35
        assert len(captured)==1
        # A timed-out running DNS call still consumes exactly one capacity slot.
        for _ in range(7):assert slots.acquire(blocking=False)
        assert slots.acquire(blocking=False) is False
        for _ in range(7):slots.release()
        captured[0].add_done_callback(lambda _:finished.set())
    finally:release.set()
    assert finished.wait(1)
    for _ in range(8):assert slots.acquire(blocking=False)
    for _ in range(8):slots.release()
    monkeypatch.setattr(p.socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('8.8.8.8',443))])
    assert p._resolve('suggestions.dadata.ru',443,time.monotonic()+1)[0][4][0]=='8.8.8.8'


def test_global_dns_pending_capacity_saturates_closed_and_recovers(monkeypatch,isolated_dns_pool):
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor
    p,pool,slots=isolated_dns_pool
    release=threading.Event();submitted=threading.Event();lock=threading.Lock()
    active=peak=count=0
    submit=pool.submit
    def capture(*args,**kwargs):
        nonlocal count
        future=submit(*args,**kwargs)
        with lock:
            count+=1
            if count==8:submitted.set()
        return future
    def slow(*args,**kwargs):
        nonlocal active,peak
        with lock:active+=1;peak=max(peak,active)
        release.wait(2)
        with lock:active-=1
        return [(2,1,6,'',('8.8.8.8',443))]
    monkeypatch.setattr(pool,'submit',capture)
    monkeypatch.setattr(p.socket,'getaddrinfo',slow)
    with ThreadPoolExecutor(max_workers=8) as callers:
        futures=[callers.submit(p._resolve,'suggestions.dadata.ru',443,time.monotonic()+2) for _ in range(8)]
        try:
            assert submitted.wait(1)
            started=time.monotonic()
            with pytest.raises(p.ProviderUnavailable):p.request_json('https://suggestions.dadata.ru/test',{},deadline_seconds=0.1)
            assert time.monotonic()-started<0.25 and count==8
        finally:release.set()
        assert all(future.result(timeout=1) for future in futures)
    assert peak<=4
    assert p._resolve('suggestions.dadata.ru',443,time.monotonic()+1)


def test_tcp_dial_is_numeric_pinned_without_second_dns_and_budgeted_for_tls(monkeypatch,isolated_dns_pool):
    import time
    p,pool,slots=isolated_dns_pool
    calls=[];timeouts=[];dialed=[]
    def resolve(*args,**kwargs):calls.append(1);return [(2,1,6,'',('8.8.8.8',443))]
    class Socket:
        def __init__(self,*args):pass
        def settimeout(self,value):timeouts.append(value)
        def connect(self,address):dialed.append(address)
        def close(self):pass
    class Response:
        status=200
        def __init__(self):self.sent=False
        def getheader(self,key,default=None):return default
        def read1(self,size):
            if self.sent:return b''
            self.sent=True;return b'{}'
    class Connection:
        def __init__(self,host,port,**kwargs):self.host=host;self.port=port;self.sock=None
        def connect(self):self.sock=self._create_connection((self.host,self.port),8,None)
        def request(self,*args,**kwargs):pass
        def getresponse(self):return Response()
        def close(self):self.sock.close()
    monkeypatch.setattr(p.socket,'getaddrinfo',resolve)
    monkeypatch.setattr(p.socket,'socket',Socket)
    monkeypatch.setattr(p.http.client,'HTTPSConnection',Connection)
    assert p.request_json('https://suggestions.dadata.ru/test',{},deadline_seconds=1)=={}
    assert calls==[1] and dialed==[('8.8.8.8',443)]
    assert 0<timeouts[0]<=0.5 and all(0<value<=1 for value in timeouts)


def test_repeated_cancelled_dns_jobs_cannot_grow_physical_queue(monkeypatch,isolated_dns_pool):
    import threading
    import time
    p,pool,slots=isolated_dns_pool
    release=threading.Event();all_running=threading.Event();lock=threading.Lock();running=0;dns_calls=[]
    def block():
        nonlocal running
        with lock:
            running+=1
            if running==4:all_running.set()
        release.wait(2)
    blocked=[pool.submit(block) for _ in range(4)]
    monkeypatch.setattr(p.socket,'getaddrinfo',lambda *a,**k:dns_calls.append(1) or [(2,1,6,'',('8.8.8.8',443))])
    try:
        assert all_running.wait(1)
        started=time.monotonic()
        for _ in range(20):
            with pytest.raises(p.ProviderUnavailable):p._resolve('suggestions.dadata.ru',443,time.monotonic()+0.005)
            assert pool.pending.qsize()<=8
        assert time.monotonic()-started<0.5
        assert pool.pending.qsize()==8 and dns_calls==[]
        # Cancelled queued jobs release admission permits; a physically full
        # queue still rejects new work rather than accumulating cancelled jobs.
        for _ in range(8):assert slots.acquire(blocking=False)
        for _ in range(8):slots.release()
    finally:release.set()
    for future in blocked:future.result(timeout=1)
    # Enqueue a normal task after all cancelled work has drained.
    deadline=time.monotonic()+1
    while pool.pending.qsize() and time.monotonic()<deadline:time.sleep(0.001)
    assert p._resolve('suggestions.dadata.ru',443,time.monotonic()+1)
    assert dns_calls==[1]
