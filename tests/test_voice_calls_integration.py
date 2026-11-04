"""Full local API guards for call preparation; no telephone or paid API work."""
from tests.test_api import client, invoice, register
from server.business_time import business_today
from server.database import database


def prepare(client, item):
    return client.post('/api/yandex/voice/calls/prepare',json={
        'invoice_id':item['id'],'phone':'+79991234567','contact_authorized':True})


def test_call_preparation_uses_ledger_adjustments_and_refunds(client,monkeypatch):
    from server import yandex_services
    monkeypatch.setattr(yandex_services,'_request',lambda *a,**k: (_ for _ in ()).throw(AssertionError('must not charge')))
    register(client)
    item=invoice(client,amount=10000)
    bank=client.post('/api/finance/bank-payments',json={
        'external_id':'voice-bank','amount':2000,'paid_on':str(business_today()),
        'reference':'ПП1','evidence':'Проверенная выписка','confirmed':True})
    assert bank.status_code==201,bank.text
    allocated=client.post('/api/finance/bank-payments/'+bank.json()['id']+'/allocate',json={
        'invoice_id':item['id'],'amount':2000,'idempotency_key':'voice-payment'})
    assert allocated.status_code==200,allocated.text
    for key,kind,amount,expected_balance in [('close','credit',8000,0),('open','debit',1000,1000),('close-again','return',1000,0)]:
        adjusted=client.post('/api/finance/invoices/'+item['id']+'/adjustments',json={
            'kind':kind,'amount':amount,'effective_on':str(business_today()),
            'reason':'Сверено по первичным документам','idempotency_key':key})
        assert adjusted.status_code==200,adjusted.text
        assert adjusted.json()['balance']==expected_balance
        snapshot=client.get('/api/invoices/'+item['id']).json()['invoice']
        assert prepare(client,item).status_code==(200 if expected_balance else 409)
        assert client.get('/api/invoices/'+item['id']).json()['invoice']==snapshot
    refunded=client.post('/api/finance/payments/'+allocated.json()['payment']['id']+'/reverse',json={
        'amount':1000,'kind':'refund','reason':'Возврат подтверждён выпиской','idempotency_key':'voice-refund'})
    assert refunded.status_code==200,refunded.text
    assert refunded.json()['invoice']['balance']==1000
    result=prepare(client,item)
    assert result.status_code==200,result.text
    assert result.json()['call_started'] is False


def test_call_preparation_requires_session_csrf_and_tenant_ownership(client):
    assert client.get('/api/yandex/voice/readiness').status_code==401
    assert prepare(client,{'id':'missing'}).status_code==401
    register(client)
    item=invoice(client)
    token=client.headers.pop('X-CSRF-Token')
    assert prepare(client,item).status_code==403
    client.headers['X-CSRF-Token']=token
    assert prepare(client,item).status_code==200
    register(client,email='other-voice-tenant@example.ru')
    assert prepare(client,item).status_code==404


def test_accountant_preparation_cannot_override_stored_contact_permission(client):
    register(client)
    item=invoice(client)
    assert client.patch('/api/finance/counterparties/'+item['counterparty_id'],json={'contact_allowed':False}).status_code==200
    with database(client.app.state.config,write=True) as connection:
        connection.execute("UPDATE workflow_memberships SET role='accountant'")
    assert client.get('/api/auth/me').json()['user']['role']=='accountant'
    assert prepare(client,item).status_code==409
    assert client.patch('/api/finance/counterparties/'+item['counterparty_id'],json={'contact_allowed':True}).status_code==403
    assert prepare(client,item).status_code==409
