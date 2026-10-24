"""Tenant-bound external reads and immutable staged evidence, explicit approval."""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import Field, StrictBool, StrictInt, field_validator, model_validator

from . import bank_exchange as bank
from . import finance as f
from . import finance_imports
from . import integration_providers as providers
from .business_time import business_today
from .models import Input, InvoiceInput, single_line

SCHEMA_SQL='''
CREATE TABLE IF NOT EXISTS integration_runs (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL REFERENCES tenants(id),provider TEXT NOT NULL,
 status TEXT NOT NULL,payload_json TEXT NOT NULL,actor_id TEXT NOT NULL,created_at TEXT NOT NULL,
 selected_json TEXT,result_json TEXT,approved_at TEXT,UNIQUE(id,tenant_id)
);
CREATE INDEX IF NOT EXISTS integration_runs_tenant ON integration_runs(tenant_id,provider,created_at);
CREATE TABLE IF NOT EXISTS integration_source_evidence (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL REFERENCES tenants(id),run_id TEXT NOT NULL,
 provider TEXT NOT NULL,source_id TEXT NOT NULL,source_hash TEXT NOT NULL,payload_json TEXT NOT NULL,
 reason TEXT NOT NULL,actor_id TEXT NOT NULL,created_at TEXT NOT NULL,
 UNIQUE(tenant_id,provider,source_id),FOREIGN KEY(run_id,tenant_id) REFERENCES integration_runs(id,tenant_id)
);
CREATE TABLE IF NOT EXISTS integration_registry_checks (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL REFERENCES tenants(id),inn TEXT NOT NULL,provider TEXT NOT NULL,
 status TEXT NOT NULL,payload_json TEXT NOT NULL,actor_id TEXT NOT NULL,created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS integration_registry_tenant ON integration_registry_checks(tenant_id,inn,created_at);
CREATE TABLE IF NOT EXISTS integration_registry_batches (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL REFERENCES tenants(id),request_json TEXT NOT NULL,
 result_json TEXT NOT NULL,actor_id TEXT NOT NULL,created_at TEXT NOT NULL
);
'''


def initialize_schema(connection):
    for statement in SCHEMA_SQL.split(';'):
        if statement.strip():connection.execute(statement)
    bank.initialize_schema(connection)


class RegistryInput(Input):
    inn:str=Field(min_length=10,max_length=12)
    @field_validator('inn')
    @classmethod
    def valid(cls,value):return providers.exact_inn(value)


class RegistryBatchInput(Input):
    inns:list[str]=Field(min_length=1,max_length=10)
    @field_validator('inns')
    @classmethod
    def valid(cls,values):
        result=[providers.exact_inn(value) for value in values]
        if len(set(result))!=len(result):raise ValueError('ИНН в пакете не должны повторяться')
        return result


class ApprovalInput(Input):
    reason:str=Field(min_length=1,max_length=3000)
    selected_rows:list[StrictInt]=Field(min_length=1,max_length=providers.MAX_ITEMS)
    distinct_confirmed:StrictBool=False
    distinct_reason:str=Field(default='',max_length=3000)


class BankReadInput(Input):
    from_on:date
    to_on:date
    cursor:str|None=Field(default=None,min_length=1,max_length=100)
    @field_validator('cursor')
    @classmethod
    def safe_cursor(cls,value):return single_line(value) if value is not None else None
    @model_validator(mode='after')
    def period(self):
        if not date(2023,6,1)<=self.from_on<self.to_on<=business_today()+timedelta(days=1) or (self.to_on-self.from_on).days>31:raise ValueError('Период выписки — до 31 дня, с июня 2023, окончание не включается')
        return self


class InvoicePreviewInput(Input):
    selected_rows:list[StrictInt]=Field(min_length=1,max_length=providers.MAX_ITEMS)


class SandboxReadInput(Input):
    mode:Literal['sandbox']='sandbox'


def _coverage(provider):
    if provider=='dadata':return dict(providers.REGISTRY_COVERAGE)
    if provider=='tbank':return dict(kind='bank_statement',live_verified=False,ledger_effect='explicit_approval_required')
    return dict(kind='mapped_source_evidence' if provider=='one_c' else 'edi_metadata',live_verified=False,ledger_effect='none')


def _status(payload):
    """Expiry is computed on reads; historical source facts remain immutable."""
    result=dict(payload)
    if result.get('status') in ('completed','partial'):
        try:
            if datetime.fromisoformat(result['checked_at'])<datetime.now(timezone.utc)-timedelta(days=1):result['status']='stale'
        except (ValueError,KeyError,TypeError):result['status']='stale'
    return result


def latest_registry_checks(connection,tenant_id):
    rows=connection.execute('SELECT payload_json FROM integration_registry_checks WHERE tenant_id=? ORDER BY created_at DESC,id DESC',(tenant_id,)).fetchall()
    result={}
    for row in rows:
        payload=_status(json.loads(row['payload_json']))
        result.setdefault(payload['inn'],payload)
    return result


def _registry_payload(inn,settings,*,batch_id=None):
    """Pure network stage, shared by single and bounded batch reads; no SQL."""
    result=dict(id=f.uid(),inn=inn,provider='dadata',status='unconfigured',checked_at=f.timestamp(),coverage=dict(providers.REGISTRY_COVERAGE),result={},message='Проверка не выполнена: нужны учётные данные этой организации')
    if batch_id:result['batch_id']=batch_id
    if providers.configured(settings,'dadata'):
        try:
            options={'deadline_seconds':18} if batch_id else {}
            status,facts=providers.read_registry(settings,inn,**options)
            if facts:facts['registration_status']=facts['state']
            result.update(status=status,result=facts,message='Проверены доступные сведения ЕГРЮЛ/ЕГРИП провайдера; суды, ФССП и полный реестр банкротств не проверены')
        except (providers.ProviderUnavailable,KeyError,TypeError,ValueError):
            result.update(status='unavailable',message='Источник недоступен или не подтвердил точный ИНН; проверка не выполнена')
    return result


def _persist_registry(connection,user,result):
    connection.execute('INSERT INTO integration_registry_checks(id,tenant_id,inn,provider,status,payload_json,actor_id,created_at) VALUES(?,?,?,?,?,?,?,?)',(result['id'],user['tenant_id'],result['inn'],'dadata',result['status'],json.dumps(result,ensure_ascii=False),user['id'],result['checked_at']))


def _registry_cache_fresh(result):
    if result.get('status') not in ('completed','no_match'):return False
    try:
        checked=datetime.fromisoformat(result['checked_at'].replace('Z','+00:00'))
        return timedelta(0)<=datetime.now(timezone.utc)-checked<timedelta(hours=24)
    except (KeyError,ValueError,TypeError):return False


def _store_run(ctx,user,provider,payload):
    identifier=f.uid();payload=dict(id=identifier,provider=provider,**payload)
    with ctx.database(ctx.config,write=True) as connection:
        connection.execute('INSERT INTO integration_runs(id,tenant_id,provider,status,payload_json,actor_id,created_at) VALUES(?,?,?,?,?,?,?)',(identifier,user['tenant_id'],provider,payload['status'],json.dumps(payload,ensure_ascii=False),user['id'],payload['checked_at']))
    return payload


def _read(ctx,user,provider,period=None):
    settings=providers.binding(user['tenant_id'],provider)
    payload=dict(status='unconfigured',items=[],coverage=_coverage(provider),checked_at=f.timestamp(),message='Оператор должен подключить учётные данные именно этой организации')
    if providers.configured(settings,provider):
        try:
            if provider=='one_c':items,coverage=providers.read_one_c(settings)
            elif provider=='diadoc':items,coverage=providers.read_diadoc(settings)
            else:items,coverage=providers.read_tbank(settings,period.from_on,period.to_on,cursor=period.cursor)
            status='partial' if provider=='tbank' and not coverage['complete'] else 'completed' if items else 'no_match'
            payload.update(status=status,items=[dict(row=i+1,**item) for i,item in enumerate(items)],coverage=coverage,message='Прочитана часть выписки; следующую страницу нужно запросить отдельно' if status=='partial' else 'Данные прочитаны; перед учётом требуется проверка и согласование')
        except (providers.ProviderUnavailable,KeyError,TypeError,ValueError):
            payload.update(status='unavailable',message='Источник недоступен или ответ не соответствует проверенному контракту; данные не подтверждены')
    # Network access above has completed before a database write transaction.
    if provider=='tbank':payload.update(environment='production',mode='production')
    return _store_run(ctx,user,provider,payload)


def create_router(ctx):
    router=APIRouter(prefix='/api/integrations',tags=['integrations'])
    bank.attach_routes(router,ctx)

    @router.get('')
    def connections(user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as connection:
            items=[]
            for provider in providers.PROVIDERS:
                settings=providers.binding(user['tenant_id'],provider);ready=providers.configured(settings,provider)
                table='integration_registry_checks' if provider=='dadata' else 'integration_runs'
                # Table names are fixed application constants, never request data.
                if table=='integration_registry_checks':row=connection.execute('SELECT payload_json FROM integration_registry_checks WHERE tenant_id=? AND provider=? ORDER BY created_at DESC,id DESC LIMIT 1',(user['tenant_id'],provider)).fetchone()
                else:row=connection.execute('SELECT payload_json FROM integration_runs WHERE tenant_id=? AND provider=? ORDER BY created_at DESC,id DESC LIMIT 1',(user['tenant_id'],provider)).fetchone()
                latest=_status(json.loads(row['payload_json'])) if row else {}
                items.append(dict(provider=provider,configured=ready,status=latest.get('status','not_checked') if ready else 'unconfigured',checked_at=latest.get('checked_at'),coverage=latest.get('coverage',_coverage(provider)),message=latest.get('message','Подключение ещё не проверено' if ready else 'Нужны учётные данные этой организации')))
            items.append(dict(provider='bank_exchange',configured=True,status='available',checked_at=None,coverage=dict(kind='file_upload',ledger_effect='explicit_approval_required'),message='Загрузка реальной банковской выписки 1С; требуется согласование поступлений'))
            sandbox_row=connection.execute('SELECT payload_json FROM integration_runs WHERE tenant_id=? AND provider=? ORDER BY created_at DESC,id DESC LIMIT 1',(user['tenant_id'],'tbank_sandbox')).fetchone()
            sandbox_latest=_status(json.loads(sandbox_row['payload_json'])) if sandbox_row else {}
            items.append(dict(provider='tbank_sandbox',configured=True,status=sandbox_latest.get('status','available'),checked_at=sandbox_latest.get('checked_at'),environment='sandbox',mode='sandbox',coverage=sandbox_latest.get('coverage',dict(kind='public_sandbox_contract',synthetic=True,ledger_effect='forbidden',production_verified=False)),message=sandbox_latest.get('message','Бесплатная публичная песочница Т-Банка: тест формата API, без реальных счетов и денег')))
            return dict(items=items)

    @router.post('/one_c/read')
    def read_one_c(user=Depends(ctx.get_user)):return _read(ctx,user,'one_c')

    @router.post('/diadoc/read')
    def read_diadoc(user=Depends(ctx.get_user)):return _read(ctx,user,'diadoc')

    @router.post('/tbank/read')
    def read_bank(data:BankReadInput,user=Depends(ctx.get_user)):return _read(ctx,user,'tbank',data)

    @router.post('/tbank/sandbox/read')
    def read_bank_sandbox(data:SandboxReadInput,user=Depends(ctx.get_user)):
        payload=dict(status='unavailable',environment='sandbox',mode='sandbox',items=[],coverage=dict(kind='public_sandbox_contract',synthetic=True,ledger_effect='forbidden',production_verified=False),checked_at=f.timestamp(),message='Публичная тестовая песочница недоступна; проверка реального банка не выполнена')
        try:
            items,coverage=providers.read_tbank_sandbox()
            payload.update(status='completed',items=[dict(row=i+1,**item) for i,item in enumerate(items)],coverage=coverage,message='Ответ публичной песочницы прочитан. Это тестовые данные провайдера; подтверждать их как деньги запрещено')
        except (providers.ProviderUnavailable,KeyError,TypeError,ValueError):pass
        return _store_run(ctx,user,'tbank_sandbox',payload)

    @router.get('/runs')
    def runs(user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as connection:
            return dict(items=[_status(json.loads(row['payload_json'])) for row in connection.execute('SELECT payload_json FROM integration_runs WHERE tenant_id=? ORDER BY created_at DESC,id DESC LIMIT 100',(user['tenant_id'],))])

    @router.get('/runs/{run_id}')
    def run(run_id:str,user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as connection:
            row=connection.execute('SELECT * FROM integration_runs WHERE id=? AND tenant_id=?',(run_id,user['tenant_id'])).fetchone()
            if not row:f.fail(404,'Источник не найден')
            return dict(**_status(json.loads(row['payload_json'])),approval=json.loads(row['result_json']) if row['result_json'] else None)

    @router.post('/runs/{run_id}/approve')
    def approve(run_id:str,data:ApprovalInput,user=Depends(ctx.get_user)):
        selected=sorted(set(data.selected_rows))
        if len(selected)!=len(data.selected_rows):f.fail(422,'Строки выбора повторяются')
        with ctx.database(ctx.config,write=True) as connection:
            saved=connection.execute('SELECT * FROM integration_runs WHERE id=? AND tenant_id=?',(run_id,user['tenant_id'])).fetchone()
            if not saved:f.fail(404,'Источник не найден')
            if saved['result_json']:
                if json.loads(saved['selected_json'])!=selected:f.fail(409,'Источник уже согласован с другим выбором')
                return json.loads(saved['result_json'])
            payload=_status(json.loads(saved['payload_json']));items={x['row']:x for x in payload['items']}
            if saved['provider']=='tbank_sandbox' or payload.get('environment')=='sandbox':f.fail(422,'Данные публичной песочницы нельзя подтвердить как реальный источник или деньги')
            if payload['status'] not in ('completed','partial') or any(row not in items for row in selected):f.fail(422,'Нужен актуальный успешный предпросмотр и существующие строки')
            result=dict(imported=0,skipped=0,ledger_effect='unallocated_bank_cash' if saved['provider']=='tbank' else 'none')
            for row in selected:
                item=items[row];source=dict(item);source.pop('row',None)
                fingerprint=hashlib.sha256(f._request_json(source).encode()).hexdigest()
                old=connection.execute('SELECT * FROM integration_source_evidence WHERE tenant_id=? AND provider=? AND source_id=?',(user['tenant_id'],saved['provider'],item['source_id'])).fetchone()
                if old:
                    if old['source_hash']!=fingerprint:f.fail(409,'Источник с этим идентификатором изменился; требуется ручная сверка')
                    result['skipped']+=1;continue
                if saved['provider']=='tbank':
                    inserted=bank.approve_bank_item(connection,user['tenant_id'],item,json.dumps(dict(provider='tbank',run_id=run_id,source_id=item['source_id'],purpose=item.get('purpose',''),approved_by=user['id'],reason=data.reason),ensure_ascii=False),distinct_confirmed=data.distinct_confirmed,reason=data.distinct_reason,actor_id=user['id'])
                else:inserted=True
                connection.execute('INSERT INTO integration_source_evidence(id,tenant_id,run_id,provider,source_id,source_hash,payload_json,reason,actor_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(f.uid(),user['tenant_id'],run_id,saved['provider'],item['source_id'],fingerprint,json.dumps(source,ensure_ascii=False),data.reason,user['id'],f.timestamp()))
                result['imported' if inserted else 'skipped']+=1
            connection.execute('UPDATE integration_runs SET selected_json=?,result_json=?,approved_at=? WHERE id=? AND tenant_id=?',(json.dumps(selected),json.dumps(result),f.timestamp(),run_id,user['tenant_id']))
            return result

    @router.post('/runs/{run_id}/invoice-preview')
    def invoice_preview(run_id:str,data:InvoicePreviewInput,user=Depends(ctx.get_user)):
        selected=sorted(set(data.selected_rows))
        if len(selected)!=len(data.selected_rows):f.fail(422,'Строки выбора повторяются')
        with ctx.database(ctx.config,write=True) as connection:
            saved=connection.execute('SELECT * FROM integration_runs WHERE id=? AND tenant_id=?',(run_id,user['tenant_id'])).fetchone()
            if not saved:f.fail(404,'Источник не найден')
            payload=_status(json.loads(saved['payload_json']));coverage=payload['coverage']
            if saved['provider']!='one_c' or payload['status']!='completed' or coverage.get('data_kind')!='receivables' or not coverage.get('invoice_import_supported'):
                f.fail(422,'Нужен источник отдельных документов 1С: оператор должен явно сопоставить номер, дату, срок оплаты, полную сумму и оплачено либо остаток. Агрегаты и метаданные не создают счета')
            rows={item['row']:item for item in payload['items']}
            if any(index not in rows for index in selected):f.fail(422,'Выбраны отсутствующие строки')
            items=[];errors=[]
            for index in selected:
                row=rows[index]
                try:
                    # Absent settlement facts never default to an unpaid bill.
                    paid=row.get('paid_amount')
                    if paid is None:
                        if 'balance' not in row:raise ValueError()
                        paid=row['amount']-row['balance']
                    fields={key:row[key] for key in ('company','number','issued_on','due_on','amount')}
                    item=InvoiceInput(**fields,inn=row.get('inn',''),paid_amount=paid,balance=row.get('balance'),notes='1C source: '+row['source_id']).model_dump(mode='json',exclude={'balance'})
                    if item['issued_on']>str(business_today()):raise ValueError()
                    items.append(item)
                except (ValueError,KeyError,TypeError):errors.append(dict(row=index,message='Документ не содержит согласованных даты, срока, суммы и остатка; исправьте сопоставление источника'))
            changes=finance_imports.preview_changes(connection,user['tenant_id'],items) if not errors else []
            import_id=f.uid();result=dict(items=items,errors=errors,changes=changes,source_run_id=run_id,selected_rows=selected,source_provider='one_c')
            connection.execute('INSERT INTO finance_imports(id,tenant_id,payload_json,created_at,actor_id) VALUES(?,?,?,?,?)',(import_id,user['tenant_id'],json.dumps(result,ensure_ascii=False),f.timestamp(),user['id']))
            return dict(id=import_id,**result)

    @router.post('/registry/check')
    def registry(data:RegistryInput,user=Depends(ctx.get_user)):
        settings=providers.binding(user['tenant_id'],'dadata')
        result=_registry_payload(data.inn,settings)
        with ctx.database(ctx.config,write=True) as connection:
            _persist_registry(connection,user,result)
        return result

    @router.post('/registry/check-batch')
    def registry_batch(data:RegistryBatchInput,user=Depends(ctx.get_user)):
        batch_id=f.uid();requested_at=f.timestamp()
        settings=providers.binding(user['tenant_id'],'dadata')
        with ctx.database(ctx.config) as connection:
            previous={}
            for inn in data.inns:
                saved=connection.execute('SELECT payload_json FROM integration_registry_checks WHERE tenant_id=? AND inn=? ORDER BY created_at DESC,id DESC LIMIT 1',(user['tenant_id'],inn)).fetchone()
                if saved:previous[inn]=_status(json.loads(saved['payload_json']))
        cached={inn:dict(previous[inn],cached=True,batch_id=batch_id) for inn in data.inns if inn in previous and _registry_cache_fresh(previous[inn])}
        pending=[inn for inn in data.inns if inn not in cached]
        # At most four reads in parallel, ten total. Three 18-second request
        # waves leave headroom before a typical 60-second proxy timeout. Workers
        # touch no DB connection; source writes start only after every read ends.
        if pending:
            with ThreadPoolExecutor(max_workers=min(4,len(pending))) as pool:
                fetched=list(pool.map(lambda inn:_registry_payload(inn,settings,batch_id=batch_id),pending))
        else:fetched=[]
        fresh={item['inn']:dict(item,cached=False) for item in fetched}
        result=dict(batch_id=batch_id,provider='dadata',requested_at=requested_at,items=[cached[inn] if inn in cached else fresh[inn] for inn in data.inns],requested_count=len(data.inns),cached_count=len(cached),checked_count=len(fetched),cache_ttl_hours=24,concurrency=4)
        with ctx.database(ctx.config,write=True) as connection:
            for item in fetched:_persist_registry(connection,user,item)
            connection.execute('INSERT INTO integration_registry_batches(id,tenant_id,request_json,result_json,actor_id,created_at) VALUES(?,?,?,?,?,?)',(batch_id,user['tenant_id'],json.dumps(data.model_dump(mode='json')),json.dumps(result,ensure_ascii=False),user['id'],requested_at))
        return result

    @router.get('/registry/batches/{batch_id}')
    def registry_batch_history(batch_id:str,user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as connection:
            saved=connection.execute('SELECT result_json FROM integration_registry_batches WHERE id=? AND tenant_id=?',(batch_id,user['tenant_id'])).fetchone()
            if not saved:f.fail(404,'Пакет проверок не найден')
            return json.loads(saved['result_json'])

    @router.get('/registry/checks')
    def registry_checks(user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as connection:
            return dict(items=list(latest_registry_checks(connection,user['tenant_id']).values()))
    return router
