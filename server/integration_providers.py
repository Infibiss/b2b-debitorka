"""Read-only documented provider contracts, bounded transport and operator bindings.

No tenant-controlled URLs and no fallback to another tenant's credentials.
Only normalized allowlisted fields leave this module; provider bodies/errors may
contain secrets and are deliberately never returned to a browser or persisted.
"""
import base64
import hashlib
import http.client
import ipaddress
import json
import os
import queue
import re
import socket
import ssl
import time
import threading
from concurrent.futures import Future, TimeoutError as FutureTimeout
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import quote, urlencode, urlsplit

from .business_time import business_today

MAX_BYTES = 2_000_000
MAX_ITEMS = 500
TIMEOUT = 8
DEADLINE = 20
DNS_WORKERS = 4
DNS_CAPACITY = 8
PROVIDERS = ('one_c','diadoc','dadata','tbank')
TBANK_SANDBOX_URL='https://business.tbank.ru/openapi/sandbox/api/v1/statement'
TBANK_SANDBOX_ACCOUNT='40702810110011000000'
TBANK_SANDBOX_FROM='2024-04-26T21:00:00.000Z'
REGISTRY_COVERAGE = dict(egrul='provider_snapshot',bankruptcy='unverified',court_cases='unverified',fssp='unverified')


class ProviderUnavailable(Exception):
    """Message is private; callers expose a fixed safe explanation."""


class _DNSResolverPool:
    """Fixed daemon workers and a physically bounded pending-work queue.

    Future.cancel() does not remove a work item from ThreadPoolExecutor's
    unbounded queue. Keeping our own bounded queue ensures cancelled lookups
    cannot accumulate without limit while platform DNS calls are blocked.
    """
    def __init__(self,workers,capacity):
        self.pending=queue.Queue(maxsize=capacity)
        self.lock=threading.Lock()
        self.closed=False
        self.cancel_pending=False
        self.threads=[]
        for index in range(workers):
            worker=threading.Thread(target=self._run,name='mandato-dns-'+str(index),daemon=True)
            try:worker.start()
            except RuntimeError:
                self.closed=True;break
            self.threads.append(worker)

    def submit(self,function,*args,**kwargs):
        with self.lock:
            if self.closed:raise RuntimeError('Resolver unavailable')
            future=Future()
            try:self.pending.put_nowait((future,function,args,kwargs))
            except queue.Full:raise RuntimeError('Resolver capacity exhausted') from None
            return future

    def _run(self):
        while True:
            try:future,function,args,kwargs=self.pending.get(timeout=0.1)
            except queue.Empty:
                if self.closed:return
                continue
            try:
                if self.cancel_pending:future.cancel()
                if future.set_running_or_notify_cancel():
                    try:result=function(*args,**kwargs)
                    except BaseException as error:future.set_exception(error)
                    else:future.set_result(result)
            finally:self.pending.task_done()

    def shutdown(self,wait=False,cancel_futures=True):
        with self.lock:
            self.closed=True;self.cancel_pending=cancel_futures
            if cancel_futures:
                while True:
                    try:future,_,_,_=self.pending.get_nowait()
                    except queue.Empty:break
                    future.cancel();self.pending.task_done()
        if wait:
            for worker in self.threads:worker.join()


# Four running DNS calls maximum. Admission slots cover live running/queued
# futures; even cancelled queue entries have a separate physical queue bound.
_DNS_POOL=_DNSResolverPool(workers=DNS_WORKERS,capacity=DNS_CAPACITY)
_DNS_SLOTS=threading.BoundedSemaphore(DNS_CAPACITY)


def _resolve(host,port,deadline):
    slots=_DNS_SLOTS
    remaining=deadline-time.monotonic()
    if remaining<=0 or not slots.acquire(blocking=False):raise ProviderUnavailable()
    try:
        # Capture the callable now. No request-spawned worker or unbounded queue,
        # and no context-manager shutdown wait after a caller's deadline expires.
        future=_DNS_POOL.submit(socket.getaddrinfo,host,port,type=socket.SOCK_STREAM)
    except RuntimeError:
        slots.release();raise ProviderUnavailable() from None
    future.add_done_callback(lambda _future:slots.release())
    try:
        remaining=deadline-time.monotonic()
        if remaining<=0:raise FutureTimeout()
        return future.result(timeout=remaining)
    except FutureTimeout:
        # A queued job cancels immediately (callback releases capacity); an
        # already-running resolver keeps its permit until it actually completes.
        future.cancel()
        raise ProviderUnavailable() from None


def exact_inn(value):
    if not isinstance(value,str) or not re.fullmatch(r'(?:[0-9]{10}|[0-9]{12})',value):
        raise ValueError('Укажите точный ИНН из 10 или 12 цифр')
    digits=list(map(int,value))
    def checksum(weights):return sum(a*b for a,b in zip(digits,weights))%11%10
    valid=(checksum([2,4,10,3,5,9,4,6,8])==digits[9]) if len(value)==10 else (checksum([7,2,4,10,3,5,9,4,6,8])==digits[10] and checksum([3,7,2,4,10,3,5,9,4,6,8])==digits[11])
    if not valid:raise ValueError('Контрольные цифры ИНН не совпадают')
    return value


def binding(tenant_id,provider):
    try:
        raw=os.environ.get('MANDATO_INTEGRATIONS_JSON','[]')
        if len(raw)>200_000:return None
        entries=json.loads(raw)
        if not isinstance(entries,list):return None
        matches=[x for x in entries if isinstance(x,dict) and x.get('tenant_id')==tenant_id and x.get('provider')==provider]
        if len(matches)==1:return matches[0]
        # The public registry lookup runs on Mandato's own account unless a client brought its own.
        if provider=='dadata' and not matches and os.environ.get('DADATA_API_KEY'):
            return dict(tenant_id=tenant_id,provider='dadata',token=os.environ['DADATA_API_KEY'])
        return None
    except (ValueError,TypeError):return None


def configured(value,provider):
    if not value:return False
    if provider=='tbank' and value.get('mode','production')!='production':return False
    fields={'one_c':('base_url','username','password','entity','mapping'),'diadoc':('token','box_id'),'dadata':('token',),'tbank':('token','account_number')}
    return all(value.get(key) for key in fields[provider])


def request_json(url,headers,body=None,*,allow_private=False,operator_destination=False,diagnostics=None,deadline_seconds=DEADLINE):
    """Pin the validated DNS result for TCP while retaining TLS SNI/cert checks.

    http.client ignores proxy environment variables. Redirects and compressed
    responses are rejected. All failures have an opaque exception at the boundary.
    """
    connection=None
    try:
        if type(deadline_seconds) not in (int,float) or not 0<deadline_seconds<=DEADLINE:raise ProviderUnavailable()
        deadline=time.monotonic()+deadline_seconds
        parsed=urlsplit(url)
        if parsed.username or parsed.password or parsed.fragment or not parsed.hostname:raise ProviderUnavailable()
        if parsed.scheme!='https' and not (operator_destination and allow_private and parsed.scheme=='http'):raise ProviderUnavailable()
        if allow_private and not operator_destination:raise ProviderUnavailable()
        host=parsed.hostname.encode('idna').decode('ascii');port=parsed.port or (443 if parsed.scheme=='https' else 80)
        addresses=_resolve(host,port,deadline)
        if not addresses:raise ProviderUnavailable()
        ips=[entry[4][0] for entry in addresses]
        if not allow_private and any(not ipaddress.ip_address(ip).is_global for ip in ips):raise ProviderUnavailable()
        family,socket_type,protocol,_,pinned_address=addresses[0]
        if parsed.scheme=='https':connection=http.client.HTTPSConnection(host,port,timeout=TIMEOUT,context=ssl.create_default_context())
        else:connection=http.client.HTTPConnection(host,port,timeout=TIMEOUT)
        # HTTPSConnection.connect retains self.host for SNI/certificate checks.
        # Dial a numeric sockaddr directly; socket.create_connection would run
        # a second unbounded getaddrinfo even for our validated numeric address.
        def pinned_connection(_address,_timeout,source_address=None):
            remaining=deadline-time.monotonic()
            if remaining<=0:raise ProviderUnavailable()
            # HTTPS wraps this same socket with its current timeout. Reserve
            # half the remaining budget for each of TCP and the TLS handshake.
            timeout=min(TIMEOUT,remaining/2 if parsed.scheme=='https' else remaining)
            transport_socket=socket.socket(family,socket_type,protocol)
            try:
                transport_socket.settimeout(timeout)
                if source_address:transport_socket.bind(source_address)
                transport_socket.connect(pinned_address)
                return transport_socket
            except BaseException:
                transport_socket.close();raise
        connection._create_connection=pinned_connection
        def remaining_timeout(response=None):
            remaining=deadline-time.monotonic()
            if remaining<=0:raise ProviderUnavailable()
            transport_socket=connection.sock
            if transport_socket is None and response is not None:
                # HTTPConnection releases its socket reference for a
                # Connection: close response while HTTPResponse still owns it.
                transport_socket=getattr(getattr(getattr(response,'fp',None),'raw',None),'_sock',None)
            if transport_socket:transport_socket.settimeout(min(TIMEOUT,remaining))
        connection.connect()
        remaining_timeout()
        payload=json.dumps(body,ensure_ascii=False).encode('utf-8') if body is not None else None
        request_headers={'Accept':'application/json','Accept-Encoding':'identity',**headers}
        if payload is not None:request_headers['Content-Type']='application/json; charset=utf-8'
        connection.request('POST' if payload is not None else 'GET',(parsed.path or '/')+('?' + parsed.query if parsed.query else ''),body=payload,headers=request_headers)
        remaining_timeout()
        response=connection.getresponse()
        if diagnostics is not None:diagnostics['http_status']=response.status
        if response.status!=200 or response.getheader('Content-Encoding','identity').lower()!='identity':raise ProviderUnavailable()
        length=response.getheader('Content-Length')
        if length and (not length.isdigit() or int(length)>MAX_BYTES):raise ProviderUnavailable()
        chunks=[];size=0
        while True:
            remaining_timeout(response)
            chunk=response.read1(min(65536,MAX_BYTES+1-size))
            if not chunk:break
            chunks.append(chunk);size+=len(chunk)
            if size>MAX_BYTES:raise ProviderUnavailable()
        value=json.loads(b''.join(chunks).decode('utf-8-sig'),parse_float=Decimal)
        if not isinstance(value,dict):raise ProviderUnavailable()
        if diagnostics is not None:diagnostics.update(response_bytes=size,response_keys=sorted(value))
        return value
    except (OSError,ValueError,TypeError,RecursionError,http.client.HTTPException,UnicodeError) as error:
        raise ProviderUnavailable() from error
    finally:
        if connection:connection.close()


def text(value,maximum=300):
    if value is None:return ''
    if not isinstance(value,(str,int)):raise ProviderUnavailable()
    result=str(value)
    if len(result)>maximum or any(ord(c)<32 for c in result):raise ProviderUnavailable()
    return result


def money(value,*,allow_zero=False):
    if isinstance(value,(float,bool)) or value is None:raise ProviderUnavailable()
    try:
        amount=Decimal(str(value))
        if not amount.is_finite() or amount<0 or (amount==0 and not allow_zero) or amount>10_000_000_000_000 or amount*100!=(amount*100).to_integral_value():raise ProviderUnavailable()
        return int(amount*100)
    except (InvalidOperation,ValueError):raise ProviderUnavailable() from None


def bounded_items(value,key):
    rows=value.get(key)
    if not isinstance(rows,list) or len(rows)>MAX_ITEMS or any(not isinstance(x,dict) for x in rows):raise ProviderUnavailable()
    return rows


def read_one_c(settings):
    base=settings['base_url'].rstrip('/');parsed=urlsplit(base)
    if parsed.query or parsed.fragment or not parsed.path.endswith('/odata/standard.odata'):raise ProviderUnavailable()
    entity=settings['entity'];mapping=settings['mapping']
    if not isinstance(entity,str) or not re.fullmatch(r'(?:Catalog|Document|InformationRegister|AccountingRegister|AccumulationRegister)_[\w]+',entity):raise ProviderUnavailable()
    allowed={'source_id','company','inn','number','issued_on','due_on','amount','paid_amount','balance'}
    if not isinstance(mapping,dict) or set(mapping)-allowed or not {'source_id','company'}.issubset(mapping):raise ProviderUnavailable()
    if any(not isinstance(v,str) or not re.fullmatch(r'\w+',v) for v in mapping.values()):raise ProviderUnavailable()
    auth=base64.b64encode((settings['username']+':'+settings['password']).encode()).decode()
    url=base+'/'+quote(entity,safe='')+'?'+urlencode({'$format':'json','$top':MAX_ITEMS,'$select':','.join(dict.fromkeys(mapping.values()))})
    response=request_json(url,{'Authorization':'Basic '+auth},allow_private=settings.get('allow_private') is True,operator_destination=True)
    scope=hashlib.sha256((base+'/'+entity).encode()).hexdigest()[:24]
    items=[];seen=set()
    for row in bounded_items(response,'value'):
        item={key:text(row.get(field),200) for key,field in mapping.items() if key not in ('amount','paid_amount','balance')}
        if not item.get('source_id') or not item.get('company') or item['source_id'] in seen:raise ProviderUnavailable()
        seen.add(item['source_id'])
        if item.get('inn') and not re.fullmatch(r'[0-9]{10}|[0-9]{12}',item['inn']):raise ProviderUnavailable()
        for key in ('amount','paid_amount','balance'):
            if key in mapping:item[key]=money(row.get(mapping[key]),allow_zero=key!='amount')
        for key in ('issued_on','due_on'):
            if item.get(key):
                try:item[key]=datetime.fromisoformat(item[key].replace('Z','+00:00')).date().isoformat()
                except ValueError:raise ProviderUnavailable() from None
        item['source_id']=scope+':'+item['source_id'];items.append(item)
    # A continuation is retained as a coverage flag, never followed as a URL.
    data_kind=settings.get('data_kind','metadata')
    if data_kind not in ('metadata','receivables','balances'):raise ProviderUnavailable()
    invoice_supported=data_kind=='receivables' and {'company','number','issued_on','due_on','amount'}.issubset(mapping) and bool({'paid_amount','balance'}.intersection(mapping))
    return items,dict(kind='operator_mapped_odata_evidence',data_kind=data_kind,invoice_import_supported=invoice_supported,complete=len(items)<MAX_ITEMS and not bool(response.get('odata.nextLink') or response.get('@odata.nextLink')),limit=MAX_ITEMS,ledger_effect='explicit_invoice_preview_required' if invoice_supported else 'none')


def read_diadoc(settings):
    box=text(settings['box_id'],200)
    response=request_json('https://diadoc-api.kontur.ru/V3/GetDocuments?'+urlencode({'boxId':box,'filterCategory':'Any.Inbound','count':100,'sortDirection':'Descending'}),{'Authorization':'Bearer '+settings['token']})
    items=[];seen=set()
    rows=bounded_items(response,'Documents')
    if len(rows)>100:raise ProviderUnavailable()
    for row in rows:
        message=text(row.get('MessageId'),200);entity=text(row.get('EntityId'),200)
        if not message or not entity:raise ProviderUnavailable()
        identity=hashlib.sha256(box.encode()).hexdigest()[:24]+':'+message+':'+entity
        if identity in seen:raise ProviderUnavailable()
        seen.add(identity)
        item=dict(source_id=identity,message_id=message,entity_id=entity,number=text(row.get('DocumentNumber'),200),issued_on=text(row.get('DocumentDate'),100),title=text(row.get('Title') or row.get('FileName'),300),document_type=text(row.get('DocumentType'),100),counteragent_box_id=text(row.get('CounteragentBoxId'),200))
        items.append(item)
    total=response.get('TotalCount')
    return items,dict(kind='edi_metadata',content_downloaded=False,signature_verified=False,complete=isinstance(total,int) and total<=len(items),limit=100,ledger_effect='none')


def read_registry(settings,inn,*,deadline_seconds=None):
    options={'deadline_seconds':deadline_seconds} if deadline_seconds is not None else {}
    response=request_json('https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party',{'Authorization':'Token '+settings['token']}, {'query':inn,'count':10,'branch_type':'MAIN'},**options)
    rows=bounded_items(response,'suggestions')
    if not rows:return 'no_match',{}
    matching=[r for r in rows if isinstance(r.get('data'),dict) and r['data'].get('inn')==inn]
    if len(matching)!=1 or len(matching)!=len(rows):raise ProviderUnavailable()
    row=matching[0];data=row['data'];state=data.get('state')
    if not isinstance(state,dict):raise ProviderUnavailable()
    status=text(state.get('status'),50)
    if status not in ('ACTIVE','LIQUIDATING','LIQUIDATED','BANKRUPT','REORGANIZING'):raise ProviderUnavailable()
    record_date=None
    stamp=state.get('actuality_date')
    if type(stamp) is int:
        try:
            asof_dt=datetime.fromtimestamp(stamp/1000,timezone.utc)
            if asof_dt>datetime.now(timezone.utc):raise ProviderUnavailable()
            record_date=asof_dt.isoformat()
        except (ValueError,OverflowError,OSError):raise ProviderUnavailable() from None
    # DaData defines actuality_date as the record's LAST CHANGE date, not a
    # verification timestamp. A stable company can legitimately be years old.
    return 'completed',dict(inn=inn,name=text(row.get('value'),300),ogrn=text(data.get('ogrn'),20),state=status,provider_record_date=record_date,provider_as_of=None,provider_record_date_status='available' if record_date else 'unknown')


def read_tbank(settings,from_on,to_on,cursor=None):
    from .bank_exchange import document_identity
    if settings.get('mode','production')!='production':raise ProviderUnavailable()
    account=text(settings['account_number'],20)
    if not re.fullmatch(r'[0-9]{20}',account):raise ProviderUnavailable()
    excluded=settings.get('excluded_own_accounts',[])
    if not isinstance(excluded,list) or len(excluded)>100 or any(not isinstance(item,str) or not re.fullmatch(r'[0-9]{20}',item) for item in excluded):raise ProviderUnavailable()
    own_accounts={account,*excluded}
    params={'accountNumber':account,'from':from_on.isoformat()+'T00:00:00Z','to':to_on.isoformat()+'T00:00:00Z','limit':MAX_ITEMS,'operationStatus':'Transaction'}
    if cursor:
        if not isinstance(cursor,str) or len(cursor)>100 or any(ord(c)<32 for c in cursor):raise ProviderUnavailable()
        params['cursor']=cursor
    response=request_json('https://business.tbank.ru/openapi/api/v1/statement?'+urlencode(params),{'Authorization':'Bearer '+settings['token']})
    items=[];seen=set()
    for row in bounded_items(response,'operations'):
        identity=text(row.get('operationId'),200)
        if not identity or identity in seen or row.get('accountNumber')!=account:raise ProviderUnavailable()
        seen.add(identity)
        if row.get('operationStatus')!='Transaction' or row.get('accountCurrencyDigitalCode')!='643':raise ProviderUnavailable()
        kind=row.get('typeOfOperation')
        if kind not in ('Credit','Debit'):raise ProviderUnavailable()
        payer=row.get('payer') or {};receiver=row.get('receiver') or {}
        if not isinstance(payer,dict) or not isinstance(receiver,dict):raise ProviderUnavailable()
        try:
            dt=datetime.fromisoformat(text(row.get('operationDate'),100).replace('Z','+00:00'))
            if not dt.tzinfo or not from_on<=dt.date()<to_on or dt.date()>business_today():raise ProviderUnavailable()
        except ValueError:raise ProviderUnavailable() from None
        if kind=='Credit' and receiver.get('acct')!=account:raise ProviderUnavailable()
        if kind=='Debit' and payer.get('acct')!=account:raise ProviderUnavailable()
        inn=text(payer.get('inn'),12)
        if inn and not re.fullmatch(r'[0-9]{10}|[0-9]{12}',inn):raise ProviderUnavailable()
        own_transfer=payer.get('acct') in own_accounts and receiver.get('acct') in own_accounts
        incoming=kind=='Credit' and not own_transfer
        number=text(row.get('documentNumber'),200)
        payer_account=text(payer.get('acct'),20)
        # Use the same bank-document identity as exchange files. The operation
        # ID remains provenance; importing both representations cannot add cash.
        approvable=incoming and row.get('payVo')=='payment-order' and bool(number) and bool(re.fullmatch(r'[0-9]{20}',payer_account))
        document_date=None
        if approvable:
            try:
                document_dt=datetime.fromisoformat(text(row.get('docDate'),100).replace('Z','+00:00'))
                if not document_dt.tzinfo or document_dt.date()>dt.date():raise ProviderUnavailable()
                document_date=document_dt.date().isoformat()
            except ValueError:raise ProviderUnavailable() from None
        external_id=document_identity(account,payer_account,number,document_date) if approvable else 'tbank:'+identity
        items.append(dict(source_id=hashlib.sha256(account.encode()).hexdigest()[:24]+':'+identity,external_id=external_id,amount=money(row.get('accountAmount')),paid_on=dt.date().isoformat(),payer_inn=inn,payer_name=text(payer.get('name'),200),reference=number or identity,purpose=text(row.get('payPurpose'),2000),document_date=document_date,document_type='Платежное поручение' if row.get('payVo')=='payment-order' else text(row.get('payVo'),100),payer_account=payer_account,direction='incoming' if incoming else 'own_transfer' if own_transfer else 'outgoing',approvable=approvable,account=account))
    next_cursor=text(response.get('nextCursor'),100) or None
    return items,dict(kind='bank_statement',mode='production',environment='production',complete=not bool(next_cursor),next_cursor=next_cursor,request_cursor=cursor,limit=MAX_ITEMS,from_on=from_on.isoformat(),to_on=to_on.isoformat(),currency='RUB',ledger_effect='explicit_approval_required',pagination='Explicit next-page request using next_cursor and same period')


def read_tbank_sandbox(*,diagnostics=None):
    """Public test fixture endpoint; accepts NO tenant account, token or period.

    The official sandbox returns a fixed stub regardless of query values, so its
    records intentionally never pass the production account/date validation or
    become ledger input. This is a network/contract check only.
    """
    url=TBANK_SANDBOX_URL+'?'+urlencode({'accountNumber':TBANK_SANDBOX_ACCOUNT,'from':TBANK_SANDBOX_FROM})
    options={'diagnostics':diagnostics} if diagnostics is not None else {}
    response=request_json(url,{'Authorization':'Bearer TBankSandboxToken'},**options)
    items=[];seen=set()
    for row in bounded_items(response,'operations'):
        identity=text(row.get('operationId'),200)
        if not identity or identity in seen:raise ProviderUnavailable()
        seen.add(identity)
        amount=money(row['accountAmount'],allow_zero=True) if row.get('accountAmount') is not None else None
        items.append(dict(source_id='sandbox:tbank:'+identity,operation_date=text(row.get('operationDate'),100),operation_status=text(row.get('operationStatus'),100),operation_type=text(row.get('typeOfOperation'),100),amount=amount,reference=text(row.get('documentNumber'),200),environment='sandbox',mode='sandbox',approvable=False))
    coverage=dict(kind='public_sandbox_contract',environment='sandbox',mode='sandbox',synthetic=True,complete=False,provider_page_complete=not bool(response.get('nextCursor')),ledger_effect='forbidden',production_verified=False)
    return items,coverage
