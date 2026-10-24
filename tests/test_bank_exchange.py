"""Real text exchange fixtures; no live bank or synthetic provider in production."""
import base64
import importlib

import pytest
from fastapi.testclient import TestClient

from server.business_time import business_today

OWN = '40702810000000000001'
OTHER = '40702810000000000002'


@pytest.fixture
def client(tmp_path, monkeypatch):
    for key in ('DATABASE_URL','APP_URL','RENDER_EXTERNAL_URL','SMTP_HOST','SMTP_FROM','MANDATO_INTEGRATIONS_JSON'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('APP_ENV','test'); monkeypatch.setenv('SECURE_COOKIES','false')
    monkeypatch.setenv('DATABASE_PATH',str(tmp_path/'integrations.db'))
    with TestClient(importlib.import_module('server.main').create_app()) as c:
        result=c.post('/api/auth/register',json={'name':'Бухгалтер','company':'Тест','email':'bank-import@example.ru','password':'Bank-import-testing-2026'})
        c.headers['X-CSRF-Token']=result.json()['csrf_token']
        yield c


def statement(amount='1234.56', payer=OTHER, receiver=OWN, number='42', paid=True):
    day=business_today().strftime('%d.%m.%Y')
    return f'''1CClientBankExchange
ВерсияФормата=1.03
Кодировка=Windows
РасчСчет={OWN}
СекцияДокумент=Платежное поручение
Номер={number}
Дата={day}
Сумма={amount}
ПлательщикСчет={payer}
ПлательщикИНН=7707083893
Плательщик=ООО Берёзка
ПолучательСчет={receiver}
ПолучательИНН=7707083893
{('ДатаПоступило='+day) if paid else ''}
НазначениеПлатежа=Оплата по счету 42
КонецДокумента
КонецФайла
'''


def preview(client, content=None, source_ref='Банк октябрь'):
    response=client.post('/api/integrations/bank/preview',json={'content':base64.b64encode((content or statement()).encode('cp1251')).decode(),'own_account':OWN,'source_ref':source_ref})
    assert response.status_code==200,response.text
    return response.json()


def approve(client, data, selected=None):
    return client.post('/api/integrations/bank/imports/'+data['id']+'/approve',json={'reason':'Выписка сверена','selected_rows':selected or [1]})


def test_cp1251_preview_requires_approval_and_never_allocates(client):
    data=preview(client)
    assert data['errors']==[] and data['items'][0]['amount']==123456
    assert data['items'][0]['payer_name']=='ООО Берёзка'
    assert client.get('/api/finance/bank-payments').json()['items']==[]
    first=approve(client,data)
    assert first.status_code==200 and first.json()['imported']==1
    assert approve(client,data).json()==first.json()
    bank=client.get('/api/finance/bank-payments').json()['items'][0]
    assert bank['confirmed']==1 and bank['allocated_amount']==0
    assert bank['external_id'].startswith('1c-bank:')
    assert client.get('/api/invoices').json()['items']==[]


def test_source_identity_survives_filename_and_detects_changed_amount(client):
    assert approve(client,preview(client)).json()['imported']==1
    assert approve(client,preview(client,source_ref='Новое имя файла')).json()['skipped']==1
    changed=preview(client,statement(amount='1234.57'))
    assert approve(client,changed).status_code==409
    assert client.get('/api/finance/bank-payments').json()['items'][0]['amount']==123456


@pytest.mark.parametrize('content',[
    statement(payer=OWN,receiver=OTHER),statement(payer=OWN,receiver=OWN),
    statement(payer=OTHER,receiver='40702810000000000003'),statement(paid=False),
    statement(amount='1.001'),statement(amount='-1'),
    statement().replace('Сумма=1234.56','Сумма=1234.56\nСумма=2'),
])
def test_outgoing_own_transfers_unknown_account_and_invalid_facts_cannot_approve(client,content):
    data=preview(client,content)
    assert data['errors'] or not data['items'][0]['approvable']
    assert approve(client,data).status_code==422
    assert client.get('/api/finance/bank-payments').json()['items']==[]


def test_duplicate_document_is_not_double_booked(client):
    content=statement();section=content[content.index('СекцияДокумент'):content.index('КонецФайла')]
    data=preview(client,content.replace('КонецФайла',section+'КонецФайла'))
    assert data['errors']
    assert approve(client,data,[1,2]).status_code==422


def test_bank_preview_tenant_isolation(client):
    data=preview(client)
    auth=client.post('/api/auth/register',json={'name':'Другой','company':'Другой','email':'other-bank@example.ru','password':'Other-bank-testing-2026'})
    client.headers['X-CSRF-Token']=auth.json()['csrf_token']
    assert approve(client,data).status_code==404


def test_approval_is_atomic_when_later_source_conflicts(client):
    assert approve(client,preview(client)).status_code==200
    first=statement(number='43');second=statement(amount='10')
    body=second[second.index('СекцияДокумент'):second.index('КонецФайла')]
    staged=preview(client,first.replace('КонецФайла',body+'КонецФайла'))
    assert staged['errors']==[]
    assert approve(client,staged,[1,2]).status_code==409
    sources=client.get('/api/finance/bank-payments').json()['items']
    assert len(sources)==1 and sources[0]['reference']=='42'


def test_changed_purpose_is_conflict_even_with_identical_money(client):
    assert approve(client,preview(client)).status_code==200
    changed=preview(client,statement().replace('Оплата по счету 42','Возврат ошибочного платежа'))
    assert approve(client,changed).status_code==409


def test_transfer_between_statement_own_accounts_is_never_external_cash(client):
    content=statement().replace('РасчСчет='+OWN,'РасчСчет='+OWN+'\nРасчСчет='+OTHER)
    data=preview(client,content)
    assert data['errors']==[]
    assert data['items'][0]['direction']=='own_transfer'
    assert data['items'][0]['approvable'] is False
    assert approve(client,data).status_code==422
    assert client.get('/api/finance/bank-payments').json()['items']==[]


def test_numeric_document_leading_zeros_are_same_source(client):
    assert approve(client,preview(client)).json()['imported']==1
    repeated=preview(client,statement(number='000042'))
    assert approve(client,repeated).json()['skipped']==1
    assert len(client.get('/api/finance/bank-payments').json()['items'])==1


def test_existing_manual_source_blocks_ambiguous_file_duplicate(client):
    manual=client.post('/api/finance/bank-payments',json={'external_id':'BANK-DOC42','amount':123456,'paid_on':str(business_today()),'payer_inn':'7707083893','payer_name':'ООО Берёзка','reference':'42','evidence':'Сверено вручную с выпиской','confirmed':True})
    assert manual.status_code==201,manual.text
    source=preview(client)
    result=approve(client,source)
    assert result.status_code==409,result.text
    assert len(client.get('/api/finance/bank-payments').json()['items'])==1


def test_file_source_blocks_manual_duplicate_and_allows_only_evidenced_distinct_order(client):
    assert approve(client,preview(client)).status_code==200
    body={'external_id':'MANUAL-AFTER-FILE','amount':123456,'paid_on':str(business_today()),
        'payer_inn':'7707083893','payer_name':'ООО Берёзка','reference':'000042',
        'evidence':'Сверено по банковскому документу','confirmed':True}
    assert client.post('/api/finance/bank-payments',json=body).status_code==409
    body.update(distinct_confirmed=True,distinct_reason='Проверены разные оригиналы документов')
    assert client.post('/api/finance/bank-payments',json=body).status_code==409
    body['reference']='43'
    body['distinct_confirmed']=False
    assert client.post('/api/finance/bank-payments',json=body).status_code==409
    body['distinct_confirmed']=True
    result=client.post('/api/finance/bank-payments',json=body)
    assert result.status_code==201,result.text
    assert client.post('/api/finance/bank-payments',json=body).status_code==201
    assert len(client.get('/api/finance/bank-payments').json()['items'])==2


def test_two_verified_orders_same_party_amount_day_are_distinct(client):
    first=statement(number='42');second=statement(number='43')
    section=second[second.index('СекцияДокумент'):second.index('КонецФайла')]
    data=preview(client,first.replace('КонецФайла',section+'КонецФайла'))
    response=approve(client,data,[1,2])
    assert response.status_code==200 and response.json()['imported']==2,response.text


def test_distinct_legacy_receipt_requires_explicit_reason_and_journal(client):
    from server.database import database
    manual=client.post('/api/finance/bank-payments',json={'external_id':'MANUAL42','amount':123456,'paid_on':str(business_today()),'payer_inn':'7707083893','payer_name':'ООО Берёзка','reference':'42','evidence':'Ранее сверено вручную','confirmed':True})
    assert manual.status_code==201,manual.text
    data=preview(client,statement(number='43'))
    assert approve(client,data).status_code==409
    url='/api/integrations/bank/imports/'+data['id']+'/approve'
    response=client.post(url,json={'reason':'Проверено','selected_rows':[1],'distinct_confirmed':True,'distinct_reason':'Два разных платежных поручения42 и43 сверены с банковскими оригиналами'})
    assert response.status_code==200 and response.json()['imported']==1,response.text
    with database(client.app.state.config) as c:
        events=c.execute('SELECT * FROM integration_bank_resolution_events').fetchall()
        assert len(events)==1 and events[0]['actor_id']
        assert manual.json()['id'] in events[0]['matched_ids_json']
    duplicate=preview(client,statement(number='000042'))
    response=client.post('/api/integrations/bank/imports/'+duplicate['id']+'/approve',json={'reason':'Дубль','selected_rows':[1],'distinct_confirmed':True,'distinct_reason':'Попытка обойти одинаковый номер'})
    assert response.status_code==409


@pytest.mark.parametrize('codec,label',[('utf-8','UTF-8'),('cp866','DOS')])
def test_declared_utf8_and_dos_are_decoded_without_mojibake(client,codec,label):
    content=base64.b64encode(statement().replace('Кодировка=Windows','Кодировка='+label).encode(codec)).decode()
    response=client.post('/api/integrations/bank/preview',json={'content':content,'own_account':OWN,'source_ref':'Другой формат'})
    assert response.status_code==200 and response.json()['errors']==[]
    assert response.json()['items'][0]['payer_name']=='ООО Берёзка'
