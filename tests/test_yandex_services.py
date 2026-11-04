"""No paid requests: provider contract doubles exercise the real adapters/routes."""
import base64
import json
import sqlite3
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

TENANT = '11111111-1111-4111-8111-111111111111'
OTHER = '22222222-2222-4222-8222-222222222222'
# Valid PNG signature / IHDR dimensions; validation deliberately does not decode pixels.
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00\x00\x00\rIHDR' + (1).to_bytes(4, 'big') * 2 + b'\x08\x02\x00\x00\x00' + b'\x00' * 4

def encoded(value): return base64.b64encode(value).decode()

@pytest.fixture
def service(tmp_path, monkeypatch):
    from server import yandex_services as y
    path = tmp_path / 'yandex.sqlite'
    @contextmanager
    def db(config, write=False):
        c = sqlite3.connect(path); c.row_factory = sqlite3.Row
        c.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        try: yield c; c.commit()
        except BaseException: c.rollback(); raise
        finally: c.close()
    with db(None, write=True) as c:
        c.execute('CREATE TABLE tenants(id TEXT PRIMARY KEY)')
        c.execute('INSERT INTO tenants VALUES(?)', (TENANT,))
        c.execute('CREATE TABLE invoices(id TEXT,tenant_id TEXT,company TEXT,number TEXT,amount INTEGER,paid_amount INTEGER,status TEXT,due_on TEXT)')
        c.execute('INSERT INTO invoices VALUES(?,?,?,?,?,?,?,?)', ('invoice',TENANT,'ООО Липа','42',10000,2000,'open','2026-10-20'))
        y.initialize_schema(c)
    user = {'id':'actor','tenant_id':TENANT}
    def problem(code, message): raise HTTPException(code, message)
    ctx = SimpleNamespace(config=None,database=db,get_user=lambda:user,problem=problem)
    app = FastAPI(); app.include_router(y.create_router(ctx))
    monkeypatch.delenv('YANDEX_MODEL',raising=False)
    monkeypatch.delenv('YANDEX_AGENT_MODEL',raising=False)
    monkeypatch.setenv('YANDEX_API_KEY', 'SECRET-test')
    monkeypatch.setenv('YANDEX_AGENT_TENANT_IDS', TENANT)
    monkeypatch.setenv('YANDEX_OCR_ENABLED','true')
    monkeypatch.setenv('YANDEX_VOICE_ENABLED','true')
    return TestClient(app), y, user, db


def test_document_cached_original_and_edited_acceptance_never_write_ledger(service,monkeypatch):
    client,y,user,db=service; calls=[]
    def provider(kind, body, **kwargs):
        calls.append((kind,body,kwargs))
        return {'result':{'textAnnotation':{'fullText':'Счёт № 42\nСумма 100,00'}}}
    monkeypatch.setattr(y,'_request',provider)
    body={'content':encoded(PNG),'mime_type':'image/png','filename':'invoice.png','invoice_id':'invoice'}
    first=client.post('/api/yandex/documents',json=body)
    assert first.status_code==200,first.text
    result=first.json(); assert result['text'].startswith('Счёт') and result['status']=='completed'
    assert client.post('/api/yandex/documents',json=body).json()['id']==result['id']
    assert len(calls)==1 and calls[0][0]=='ocr'
    assert calls[0][1]['mimeType']=='PNG'
    original=client.get('/api/yandex/documents/'+result['id']+'/original')
    assert original.content==PNG and original.headers['content-type']=='image/png'
    accepted=client.post('/api/yandex/documents/'+result['id']+'/accept',json={'text':'Исправленный текст','fields':{'number':'42'},'reason':'Сверено с оригиналом'})
    assert accepted.status_code==200 and accepted.json()['acceptance']['text']=='Исправленный текст'
    with db(None) as c: assert c.execute('SELECT paid_amount FROM invoices').fetchone()[0]==2000
    user['tenant_id']=OTHER
    assert client.get('/api/yandex/documents/'+result['id']).status_code==404
    assert client.get('/api/yandex/documents/'+result['id']+'/original').status_code==404


def test_unbound_tenant_rejected_even_development(service,monkeypatch):
    client,y,user,_=service
    monkeypatch.delenv('YANDEX_AGENT_TENANT_IDS')
    monkeypatch.setattr(y,'_request',lambda *a,**k:pytest.fail('must not charge'))
    assert client.get('/api/yandex/status').json()['ocr']['status']=='unconfigured'
    assert client.post('/api/yandex/documents',json={'content':encoded(PNG),'mime_type':'image/png','filename':'x.png'}).status_code==403


@pytest.fixture
def call_service(service):
    client,y,user,db=service
    with db(None,write=True) as c:
        c.execute('ALTER TABLE invoices ADD COLUMN counterparty_id TEXT')
        c.execute('ALTER TABLE invoices ADD COLUMN adjustment_amount INTEGER NOT NULL DEFAULT 0')
        c.execute("UPDATE invoices SET counterparty_id='counterparty'")
        c.execute('CREATE TABLE finance_counterparties(id TEXT,tenant_id TEXT,hold INTEGER,contact_allowed INTEGER,mandate_expires_on TEXT)')
        c.execute('INSERT INTO finance_counterparties VALUES(?,?,?,?,?)',('counterparty',TENANT,0,1,None))
    return service


def test_call_readiness_never_confuses_speech_key_with_telephony(service,monkeypatch):
    client,y,_,_=service
    monkeypatch.setenv('SIP_PASSWORD','must-not-unlock-unimplemented-adapter')
    monkeypatch.setattr(y,'_request',lambda *a,**k:pytest.fail('readiness must not charge'))
    response=client.get('/api/yandex/voice/readiness')
    assert response.status_code==200
    result=response.json()
    assert result['speech_configured'] is True
    assert result['telephony']['ready'] is False
    assert result['telephony']['status']=='adapter_required'
    assert result['telephony']['setup_steps'] and result['telephony']['provider'] is None


def test_prepare_call_checks_contact_then_stops_at_connection_without_fake_call(call_service,monkeypatch):
    client,y,_,db=call_service
    monkeypatch.setattr(y,'_request',lambda *a,**k:pytest.fail('preparation must not charge'))
    response=client.post('/api/yandex/voice/calls/prepare',json={'invoice_id':'invoice','phone':'+7 (999) 123-45-67','contact_authorized':True})
    assert response.status_code==200,response.text
    result=response.json()
    assert result['status']=='connection_required' and result['call_started'] is False
    assert result['phone']=='+79991234567' and 'call_id' not in result
    assert result['next_action']=='configure_telephony' and result['checks']['contact_allowed']
    assert '80,00' not in result['opening'] and '42' not in result['opening']
    assert result['dialogue_state']['stage']=='identity'
    assert result['graph_nodes']==['safe_facts','bounded_intent','next_response']
    with db(None) as c:
        assert c.execute('SELECT COUNT(*) FROM yandex_service_requests').fetchone()[0]==0
        assert c.execute('SELECT paid_amount FROM invoices').fetchone()[0]==2000


@pytest.mark.parametrize('changes',[
    {'phone':'123'}, {'phone':'+79991234567 ext 1'},
    {'contact_authorized':False}, {'contact_authorized':'true'},
])
def test_prepare_call_rejects_invalid_number_or_missing_authority(call_service,monkeypatch,changes):
    client,y,_,_=call_service
    monkeypatch.setattr(y,'_request',lambda *a,**k:pytest.fail('must not charge'))
    body={'invoice_id':'invoice','phone':'+79991234567','contact_authorized':True,**changes}
    assert client.post('/api/yandex/voice/calls/prepare',json=body).status_code in (409,422)


@pytest.mark.parametrize('change',[
    "UPDATE invoices SET status='disputed'", "UPDATE invoices SET status='paused'",
    'UPDATE invoices SET paid_amount=amount',
    'UPDATE finance_counterparties SET hold=1',
    'UPDATE finance_counterparties SET contact_allowed=0',
    "UPDATE finance_counterparties SET mandate_expires_on='2000-01-01'",
])
def test_prepare_call_respects_financial_and_contact_guards(call_service,change):
    client,_,_,db=call_service
    with db(None,write=True) as c:c.execute(change)
    response=client.post('/api/yandex/voice/calls/prepare',json={'invoice_id':'invoice','phone':'+79991234567','contact_authorized':True})
    assert response.status_code==409


def test_prepare_call_rejects_foreign_invoice_before_connection(call_service):
    client,_,user,_=call_service
    user['tenant_id']=OTHER
    assert client.post('/api/yandex/voice/calls/prepare',json={'invoice_id':'invoice','phone':'+79991234567','contact_authorized':True}).status_code==404


def test_prepare_call_refuses_incomplete_financial_totals(call_service):
    client,_,_,db=call_service
    with db(None,write=True) as c:c.execute('ALTER TABLE invoices DROP COLUMN adjustment_amount')
    response=client.post('/api/yandex/voice/calls/prepare',json={'invoice_id':'invoice','phone':'+79991234567','contact_authorized':True})
    assert response.status_code==409
    assert 'финансов' in response.json()['detail'].lower()


def test_prepare_call_adjusted_balance_closes_and_reopens_after_debit_or_payment_refund(call_service):
    client,_,_,db=call_service
    body={'invoice_id':'invoice','phone':'+79991234567','contact_authorized':True}
    # Canonical totals are maintained atomically by finance.adjust/reverse.
    # A closing credit/return offsets the outstanding 80 rubles.
    with db(None,write=True) as c:c.execute('UPDATE invoices SET adjustment_amount=-8000')
    assert client.post('/api/yandex/voice/calls/prepare',json=body).status_code==409
    # A debit adjustment reopens 10 rubles, then another credit closes it.
    with db(None,write=True) as c:c.execute('UPDATE invoices SET adjustment_amount=-7000')
    assert client.post('/api/yandex/voice/calls/prepare',json=body).json()['status']=='connection_required'
    with db(None,write=True) as c:c.execute('UPDATE invoices SET adjustment_amount=-8000')
    assert client.post('/api/yandex/voice/calls/prepare',json=body).status_code==409
    # Refund/correction of the prior payment reopens the net balance.
    with db(None,write=True) as c:c.execute('UPDATE invoices SET paid_amount=1000')
    assert client.post('/api/yandex/voice/calls/prepare',json=body).json()['status']=='connection_required'


@pytest.mark.parametrize('content,mime',[(b'fake','image/png'),(PNG,'image/jpeg'),(b'x'*1_000_001,'image/png'),(b'%PDF-1.7\ninvalid','application/pdf')],ids=['bad-png','mime-mismatch','oversize','bad-pdf'])
def test_bad_document_rejected_before_provider(service,monkeypatch,content,mime):
    client,y,_,_=service
    monkeypatch.setattr(y,'_request',lambda *a,**k:pytest.fail('must not charge'))
    response=client.post('/api/yandex/documents',json={'content':encoded(content),'mime_type':mime,'filename':'x'})
    assert response.status_code==422


def test_pdf_split_capped_and_cached(service,monkeypatch):
    import io
    from pypdf import PdfReader, PdfWriter
    client,y,_,_=service; calls=[]
    def pdf(count):
        writer=PdfWriter()
        for _ in range(count):writer.add_blank_page(width=100,height=100)
        out=io.BytesIO();writer.write(out);return encoded(out.getvalue())
    def provider(kind,body,**kwargs):
        assert len(PdfReader(io.BytesIO(base64.b64decode(body['content']))).pages)==1
        calls.append(body);return {'result':{'textAnnotation':{'fullText':'Страница'}}}
    monkeypatch.setattr(y,'_request',provider)
    body={'content':pdf(2),'mime_type':'application/pdf','filename':'two.pdf'}
    response=client.post('/api/yandex/documents',json=body)
    assert response.status_code==200,response.text
    assert response.json()['page_count']==2 and len(response.json()['pages'])==2 and len(calls)==2
    client.post('/api/yandex/documents',json=body);assert len(calls)==2
    body['content']=pdf(6)
    assert client.post('/api/yandex/documents',json=body).status_code==422 and len(calls)==2


def test_permission_error_safe_persisted_and_no_automatic_paid_retry(service,monkeypatch):
    client,y,_,_=service; calls=[]
    def provider(*a,**k):calls.append(1);raise y.ServiceError('permission')
    monkeypatch.setattr(y,'_request',provider)
    body={'content':encoded(PNG),'mime_type':'image/png','filename':'x.png'}
    result=client.post('/api/yandex/documents',json=body).json()
    assert result['status']=='unavailable' and result['error_code']=='permission'
    assert 'SECRET' not in json.dumps(result)
    assert client.post('/api/yandex/documents',json=body).json()['id']==result['id'] and len(calls)==1
    assert client.get('/api/yandex/status').json()['ocr']['status']=='permission_required'


def test_voice_real_stt_then_grounded_reply_tts_and_idempotency(service,monkeypatch):
    client,y,_,_=service; calls=[]
    def provider(kind,body,**kwargs):
        calls.append((kind,body))
        if kind=='stt':return {'result':'Какой остаток по счёту?'}
        if kind=='tts':return b'OggS'+b'audio'
        pytest.fail('unexpected provider')
    monkeypatch.setattr(y,'_request',provider)
    body={'audio':encoded(b'\0\0'*1600),'invoice_id':'invoice','identity_confirmed':True,'request_id':'turn-1'}
    response=client.post('/api/yandex/voice/turn',json=body)
    assert response.status_code==200,response.text
    result=response.json()
    assert result['transcript'].startswith('Какой') and '80' in result['reply']
    assert result['audio_mime']=='audio/ogg' and result['ledger_effect']=='none'
    assert [c[0] for c in calls]==['stt','tts']
    assert client.post('/api/yandex/voice/turn',json=body).json()['id']==result['id'] and len(calls)==2
    body['audio']=encoded(b'\1\0'*1600)
    assert client.post('/api/yandex/voice/turn',json=body).status_code==409


def test_voice_text_mutation_refused_and_bounds_before_charge(service,monkeypatch):
    client,y,_,db=service
    monkeypatch.setattr(y,'_request',lambda kind,*a,**k: b'OggSaudio')
    result=client.post('/api/yandex/voice/text',json={'text':'Зачисли оплату и спиши долг','invoice_id':'invoice','identity_confirmed':True,'request_id':'typed-1'}).json()
    assert 'не измен' in result['reply'].lower()
    with db(None) as c:assert c.execute('SELECT paid_amount FROM invoices').fetchone()[0]==2000
    monkeypatch.setattr(y,'_request',lambda *a,**k:pytest.fail('must not charge'))
    for audio in [b'\0',b'\0\0'*320001,b'']:
        assert client.post('/api/yandex/voice/turn',json={'audio':encoded(audio),'invoice_id':'invoice','identity_confirmed':True,'request_id':'bad'}).status_code==422
    assert client.post('/api/yandex/voice/text',json={'text':'Привет','invoice_id':'foreign','request_id':'bad'}).status_code==404


def test_daily_quota_counts_failures_and_per_user_limit(service,monkeypatch):
    client,y,_,_=service
    monkeypatch.setattr(y,'USER_DAILY_LIMIT',1)
    monkeypatch.setattr(y,'_request',lambda *a,**k: (_ for _ in ()).throw(y.ServiceError('timeout')))
    body={'content':encoded(PNG),'mime_type':'image/png','filename':'x.png'}
    assert client.post('/api/yandex/documents',json=body).status_code==200
    body['content']=encoded(PNG+b'different')
    assert client.post('/api/yandex/documents',json=body).status_code==429


def test_dialogue_uses_adjusted_amount_not_original_face_value(service,monkeypatch):
    client,y,_,db=service
    with db(None,write=True) as c:
        c.execute('ALTER TABLE invoices ADD COLUMN adjustment_amount INTEGER NOT NULL DEFAULT 0')
        c.execute('UPDATE invoices SET adjustment_amount=-1000')
    monkeypatch.setattr(y,'_request',lambda *a,**k:b'OggSaudio')
    result=client.post('/api/yandex/voice/text',json={'text':'Какой остаток?','invoice_id':'invoice','identity_confirmed':True,'request_id':'adjusted'}).json()
    assert '70,00' in result['reply'] and '90,00' in result['reply']
    assert result['graph_nodes']==['safe_facts','bounded_intent','next_response']


def test_dialogue_intent_schema_history_and_mutation_handoff(service,monkeypatch):
    client,y,_,_=service; requests=[]
    monkeypatch.setenv('YANDEX_MODEL','gpt://folder/yandexgpt/latest')
    def provider(kind,body,**kwargs):
        if kind=='tts':return b'OggSaudio'
        requests.append(body)
        return {'result':{'alternatives':[{'message':{'text':'{"intent":"balance"}'}}]}}
    monkeypatch.setattr(y,'_request',provider)
    first=client.post('/api/yandex/voice/text',json={'text':'Проверим сведения','invoice_id':'invoice','identity_confirmed':True,'request_id':'conversation-1'}).json()
    assert first['intent_source']=='yandex' and '80,00' in first['reply']
    second=client.post('/api/yandex/voice/text',json={'text':'Спиши остаток','invoice_id':'invoice','identity_confirmed':True,'request_id':'conversation-2'}).json()
    assert second['intent']=='mutation' and second['graph_nodes'][-1]=='handoff'
    assert len(json.loads(requests[-1]['messages'][-1]['text'])['history'])==1
    assert set(requests[-1]['jsonSchema']['schema']['properties']['intent']['enum'])==set(y.INTENTS)
    assert 'SECRET' not in json.dumps(first)


def test_partial_pdf_failure_retains_completed_page_without_retry(service,monkeypatch):
    import io
    from pypdf import PdfWriter
    client,y,_,_=service;calls=[]
    writer=PdfWriter()
    for _ in range(2):writer.add_blank_page(width=100,height=100)
    out=io.BytesIO();writer.write(out)
    def provider(*a,**k):
        calls.append(1)
        if len(calls)>1:raise y.ServiceError('timeout')
        return {'result':{'textAnnotation':{'fullText':'Сохранённая страница'}}}
    monkeypatch.setattr(y,'_request',provider)
    body={'content':encoded(out.getvalue()),'filename':'partial.pdf','mime_type':'application/pdf'}
    result=client.post('/api/yandex/documents',json=body).json()
    assert result['status']=='unavailable' and len(result['pages'])==1 and result['text']=='Сохранённая страница'
    assert client.post('/api/yandex/documents',json=body).json()['id']==result['id'] and len(calls)==2
    assert client.post('/api/yandex/documents/'+result['id']+'/accept',json={'text':'x','reason':'проверено'}).status_code==409


@pytest.mark.parametrize('status,length,encoding,raw,expected',[
    (302,None,'identity',b'{}','unavailable'),
    (403,None,'identity',b'{"secret":"SECRET"}','permission'),
    (200,'1000001','identity',b'OggS','invalid_response'),
    (200,None,'gzip',b'OggS','invalid_response'),
    (200,None,'identity',b'not Ogg','invalid_response'),
],ids=['redirect','permission','size-header','compression','invalid-ogg'])
def test_binary_transport_rejects_unsafe_responses(service,monkeypatch,status,length,encoding,raw,expected):
    _,y,_,_=service
    monkeypatch.setattr(y.transport,'_resolve',lambda *a:[(2,1,6,'',('84.201.1.1',443))])
    class Sock:
        def settimeout(self,*a):pass
    class Response:
        def __init__(self):self.status=status;self.raw=raw
        def getheader(self,name,default=None):return {'Content-Length':length,'Content-Encoding':encoding}.get(name,default)
        def read1(self,n):chunk=self.raw[:n];self.raw=self.raw[n:];return chunk
    class Connection:
        def __init__(self,*a,**k):self.sock=Sock()
        def connect(self):pass
        def request(self,*a,**k):pass
        def getresponse(self):return Response()
        def close(self):pass
    monkeypatch.setattr(y.http.client,'HTTPSConnection',Connection)
    with pytest.raises(y.ServiceError) as error:y._request('tts',{'text':'Тест'})
    assert error.value.code==expected


def test_binary_transport_sends_pcm_and_form_encoded_tts_no_folder_for_service_key(service,monkeypatch):
    _,y,_,_=service;sent=[]
    monkeypatch.setattr(y.transport,'_resolve',lambda *a:[(2,1,6,'',('84.201.1.1',443))])
    class Sock:
        def settimeout(self,*a):pass
    class Response:
        status=200
        def __init__(self,raw):self.raw=raw
        def getheader(self,name,default=None):return default
        def read1(self,n):chunk=self.raw[:n];self.raw=self.raw[n:];return chunk
    class Connection:
        def __init__(self,*a,**k):self.sock=Sock()
        def connect(self):pass
        def request(self,*a,**k):sent.append((a,k))
        def getresponse(self):return Response(b'{"result":"test"}' if len(sent)==1 else b'OggSaudio')
        def close(self):pass
    monkeypatch.setattr(y.http.client,'HTTPSConnection',Connection)
    assert y._request('stt',b'\0\0')=={'result':'test'}
    assert y._request('tts',{'text':'Привет','format':'oggopus'})==b'OggSaudio'
    assert sent[0][1]['body']==b'\0\0' and 'sampleRateHertz=16000' in sent[0][0][1]
    assert b'folderId' not in sent[1][1]['body'] and b'format=oggopus' in sent[1][1]['body']
    assert sent[1][1]['headers']['x-data-logging-enabled']=='false'


def test_private_dns_rejected_before_binary_network(service,monkeypatch):
    _,y,_,_=service
    monkeypatch.setattr(y.transport,'_resolve',lambda *a:[(2,1,6,'',('127.0.0.1',443))])
    monkeypatch.setattr(y.http.client,'HTTPSConnection',lambda *a,**k:pytest.fail('private destination'))
    with pytest.raises(y.ServiceError):y._request('stt',b'\0\0')


@pytest.mark.parametrize('provider_result',[{'result':None},{'result':[]},{'result':{'textAnnotation':None}},{'result':{'textAnnotation':{'fullText':17}}}],ids=['null-result','array-result','null-annotation','numeric-text'])
def test_malformed_ocr_envelopes_become_safe_cached_failure(service,monkeypatch,provider_result):
    client,y,_,_=service
    monkeypatch.setattr(y,'_request',lambda *a,**k:provider_result)
    response=client.post('/api/yandex/documents',json={'content':encoded(PNG),'filename':'x.png','mime_type':'image/png'})
    assert response.status_code==200 and response.json()['status']=='unavailable' and response.json()['error_code']=='invalid_response'


def test_same_original_not_recharged_under_different_invoice(service,monkeypatch):
    client,y,_,db=service;calls=[]
    def provider(*a,**k):calls.append(1);return {'result':{'textAnnotation':{'fullText':'Текст'}}}
    monkeypatch.setattr(y,'_request',provider)
    body={'content':encoded(PNG),'filename':'x.png','mime_type':'image/png'}
    assert client.post('/api/yandex/documents',json=body).status_code==200
    body['invoice_id']='invoice'
    assert client.post('/api/yandex/documents',json=body).status_code==409 and len(calls)==1


def test_tenant_quota_applies_across_distinct_users(service,monkeypatch):
    client,y,user,_=service
    monkeypatch.setattr(y,'TENANT_DAILY_LIMIT',1)
    monkeypatch.setattr(y,'_request',lambda *a,**k:{'result':{'textAnnotation':{'fullText':'Текст'}}})
    body={'content':encoded(PNG),'filename':'x.png','mime_type':'image/png'}
    assert client.post('/api/yandex/documents',json=body).status_code==200
    user['id']='another-user'
    assert client.post('/api/yandex/documents',json=body).status_code==429


def test_debtor_identity_gate_never_discloses_invoice_facts(service,monkeypatch):
    client,y,_,_=service
    monkeypatch.setattr(y,'_request',lambda *a,**k:b'OggSaudio')
    result=client.post('/api/yandex/voice/text',json={'text':'Сколько мы должны?','invoice_id':'invoice','request_id':'identity-gate'}).json()
    assert 'представител' in result['reply'].lower()
    assert '42' not in result['reply'] and '80,00' not in result['reply'] and 'Липа' not in result['reply']
    assert result['dialogue_state']['stage']=='identity'


def test_debtor_paid_claim_requests_payment_reference_not_bookkeeper_instruction(service,monkeypatch):
    client,y,_,db=service
    monkeypatch.setattr(y,'_request',lambda *a,**k:b'OggSaudio')
    result=client.post('/api/yandex/voice/text',json={'text':'Мы оплатили вчера','invoice_id':'invoice','request_id':'paid-claim','identity_confirmed':True}).json()
    assert 'номер платёжного' in result['reply'].lower() and 'провер' in result['reply'].lower()
    assert 'откройте' not in result['reply'].lower() and result['intent']=='paid_claim'
    assert result['dialogue_state']['stage']=='payment_reference'
    with db(None) as c:assert c.execute('SELECT paid_amount FROM invoices').fetchone()[0]==2000


def test_debtor_dispute_stops_collection_conversation_and_requests_human(service,monkeypatch):
    client,y,_,_=service
    monkeypatch.setattr(y,'_request',lambda *a,**k:b'OggSaudio')
    result=client.post('/api/yandex/voice/text',json={'text':'Мы не согласны с суммой, у нас спор','invoice_id':'invoice','request_id':'debtor-dispute','identity_confirmed':True}).json()
    assert result['handoff_required'] and result['dialogue_state']['stage']=='human_handoff'
    assert 'продолжать напоминания' in result['reply'].lower() and 'сотрудник' in result['reply'].lower()
    assert 'приостановить через карточку' not in result['reply']


def test_debtor_promise_collects_exact_amount_date_across_followups(service,monkeypatch):
    from datetime import timedelta
    from server.business_time import business_today
    client,y,_,db=service
    monkeypatch.setattr(y,'_request',lambda *a,**k:b'OggSaudio')
    def say(text,key):return client.post('/api/yandex/voice/text',json={'text':text,'invoice_id':'invoice','request_id':key,'identity_confirmed':True}).json()
    first=say('Оплатим позже','promise-a')
    assert 'сумму' in first['reply'] and 'дату' in first['reply']
    exact=(business_today()+timedelta(days=2)).isoformat()
    second=say('50 рублей '+exact,'promise-b')
    assert second['dialogue_state']['promise_amount']==5000 and second['dialogue_state']['promise_date']==exact
    assert 'Правильно' in second['reply'] and '50,00' in second['reply']
    third=say('Да, всё верно','promise-c')
    assert third['dialogue_state']['stage']=='promise_noted' and 'стенограмме' in third['reply']
    with db(None) as c:assert c.execute('SELECT paid_amount FROM invoices').fetchone()[0]==2000


def test_debtor_opening_is_business_greeting_and_identity_question(service,monkeypatch):
    client,y,_,_=service
    monkeypatch.setattr(y,'_request',lambda *a,**k:b'OggSaudio')
    result=client.post('/api/yandex/voice/opening',json={'invoice_id':'invoice','request_id':'opening'}).json()
    assert 'Здравствуйте' in result['reply'] and 'Удобно' in result['reply']
    assert result['transcript']=='' and '80,00' not in result['reply']


def test_non_dict_stt_response_is_safe_provider_failure(service,monkeypatch):
    client,y,_,_=service
    monkeypatch.setattr(y,'_request',lambda *a,**k:b'bad-json-envelope')
    response=client.post('/api/yandex/voice/turn',json={'audio':encoded(b'\0\0'*1600),'invoice_id':'invoice','request_id':'bad-stt'})
    assert response.status_code==200 and response.json()['status']=='unavailable'


def test_non_dict_intent_response_uses_safe_dialogue_fallback(service,monkeypatch):
    client,y,_,_=service
    monkeypatch.setenv('YANDEX_MODEL','gpt://folder/yandexgpt/latest')
    monkeypatch.setattr(y,'_request',lambda *a,**k:b'OggSaudio')
    result=client.post('/api/yandex/voice/text',json={'text':'Мы оплатили вчера','invoice_id':'invoice','request_id':'bad-intent','identity_confirmed':True}).json()
    assert result['status']=='completed' and result['intent_source']=='rules_fallback'
    assert result['dialogue_state']['stage']=='payment_reference'


def test_debtor_promise_rejects_negative_amount_and_preserves_no_ledger_changes(service,monkeypatch):
    from datetime import timedelta
    from server.business_time import business_today
    client,y,_,_=service
    monkeypatch.setattr(y,'_request',lambda *a,**k:b'OggSaudio')
    exact=(business_today()+timedelta(days=2)).isoformat()
    result=client.post('/api/yandex/voice/text',json={'text':'Оплатим -10 рублей '+exact,'invoice_id':'invoice','request_id':'negative-promise','identity_confirmed':True}).json()
    assert result['dialogue_state']['stage']=='promise_details' and not result['dialogue_state'].get('promise_amount')


def test_debtor_dispute_remains_handoff_on_followup_without_new_pressure(service,monkeypatch):
    client,y,_,_=service
    monkeypatch.setattr(y,'_request',lambda *a,**k:b'OggSaudio')
    def say(text,key):return client.post('/api/yandex/voice/text',json={'text':text,'invoice_id':'invoice','request_id':key,'identity_confirmed':True}).json()
    say('У нас спор по поставке','persist-dispute-a')
    result=say('Сколько вы хотите?','persist-dispute-b')
    assert result['handoff_required'] and '80,00' not in result['reply'] and result['dialogue_state']['stage']=='human_handoff'
