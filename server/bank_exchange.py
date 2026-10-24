"""1C client-bank exchange ingestion. Approval creates unallocated source cash."""
import base64
import binascii
import hashlib
import json
import re
from datetime import datetime

from fastapi import Depends
from pydantic import Field, StrictBool, StrictInt, field_validator

from . import finance as f
from .business_time import business_today
from .integration_providers import money, ProviderUnavailable
from .models import Input, InvoiceInput, single_line

MAX_BYTES=2_000_000
MAX_ROWS=5000
SCHEMA_SQL='''
CREATE TABLE IF NOT EXISTS integration_bank_imports (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL REFERENCES tenants(id),payload_json TEXT NOT NULL,
 selected_json TEXT,result_json TEXT,actor_id TEXT NOT NULL,created_at TEXT NOT NULL,approved_at TEXT
);
CREATE TABLE IF NOT EXISTS integration_bank_resolution_events (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL REFERENCES tenants(id),source_external_id TEXT NOT NULL,
 matched_ids_json TEXT NOT NULL,reason TEXT NOT NULL,actor_id TEXT NOT NULL,created_at TEXT NOT NULL
);
'''


def initialize_schema(connection):
    for statement in SCHEMA_SQL.split(';'):
        if statement.strip():connection.execute(statement)


class PreviewInput(Input):
    content:str=Field(min_length=1,max_length=2_700_000)
    own_account:str=Field(pattern=r'^[0-9]{20}$')
    source_ref:str=Field(min_length=1,max_length=200)
    @field_validator('source_ref')
    @classmethod
    def source(cls,value):return single_line(value)


class ApprovalInput(Input):
    reason:str=Field(min_length=1,max_length=3000)
    selected_rows:list[StrictInt]=Field(min_length=1,max_length=MAX_ROWS)
    distinct_confirmed:StrictBool=False
    distinct_reason:str=Field(default='',max_length=3000)


def document_identity(account,payer_account,number,document_date,document_type='Платежное поручение'):
    values=[account,payer_account,normalize_document_number(number),document_date,document_type]
    return '1c-bank:'+hashlib.sha256(json.dumps(values,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def normalize_document_number(value):
    value=str(value).strip()
    return str(int(value)) if re.fullmatch(r'[0-9]{1,200}',value) else f.canonical(value)


def _document_metadata(item):
    fields={'own_account':item.get('account'),'payer_account':item.get('payer_account'),'number':normalize_document_number(item.get('reference') or ''),'document_date':item.get('document_date'),'document_type':item.get('document_type')}
    return fields if all(fields.values()) else None


def assert_no_duplicate_source(connection,tenant_id,item,*,distinct_confirmed=False,reason='',actor_id=None):
    """Cross-channel ambiguity gate, including legacy/manual source identities.

    Call after the caller's exact external_id retry check and before INSERT.
    An operator must reconcile an apparent duplicate rather than manufacture a
    second receipt by choosing a different external id or document formatting.
    """
    rows=connection.execute('SELECT * FROM finance_bank_payments WHERE tenant_id=? AND amount=? AND paid_on=? AND external_id<>?',(tenant_id,item['amount'],str(item['paid_on']),item['external_id'])).fetchall()
    inn=str(item.get('payer_inn') or '')
    name=f.canonical(str(item.get('payer_name') or ''))
    reference=normalize_document_number(item.get('reference') or '')
    new_document=_document_metadata(item)
    candidates=[]
    for old in rows:
        same_party=(bool(inn) and inn==old['payer_inn']) or (bool(name) and name==f.canonical(old['payer_name']))
        same_reference=bool(reference) and reference==normalize_document_number(old['reference'])
        try:old_document=json.loads(old['evidence']).get('bank_document')
        except (ValueError,AttributeError):old_document=None
        if new_document and isinstance(old_document,dict) and set(old_document)==set(new_document) and all(old_document.values()) and new_document!=old_document:
            continue
        if same_party or same_reference:
            if same_reference or distinct_confirmed is not True or not isinstance(reason,str) or not reason.strip() or not actor_id:
                f.fail(409,'Возможный дубль банковского поступления: сверьте оригиналы; отдельное поступление с другим номером требует явного подтверждения и причины')
            candidates.append(old['id'])
    if candidates:
        connection.execute('INSERT INTO integration_bank_resolution_events(id,tenant_id,source_external_id,matched_ids_json,reason,actor_id,created_at) VALUES(?,?,?,?,?,?,?)',(f.uid(),tenant_id,item['external_id'],json.dumps(candidates),reason.strip(),actor_id,f.timestamp()))
    return candidates


def _date(value):
    try:
        if not re.fullmatch(r'[0-9]{2}\.[0-9]{2}\.[0-9]{4}',value):raise ValueError()
        parsed=datetime.strptime(value,'%d.%m.%Y').date()
        if parsed>business_today():raise ValueError()
        return parsed.isoformat()
    except (TypeError,ValueError):raise ValueError('Некорректная или будущая дата банковского документа') from None


def _decode(content):
    try:raw=base64.b64decode(content,validate=True)
    except (ValueError,binascii.Error):raise ValueError('Выписка должна быть передана в base64') from None
    if len(raw)>MAX_BYTES or b'\x00' in raw:raise ValueError('Выписка превышает предел 2 МБ или содержит двоичные данные')
    for codec,label in (('utf-8-sig','UTF-8'),('cp1251','Windows'),('cp866','DOS')):
        try:
            decoded=raw.decode(codec)
            if 'Кодировка='+label in decoded or (codec=='utf-8-sig' and 'Кодировка=UTF8' in decoded):return decoded,codec,hashlib.sha256(raw).hexdigest()
        except UnicodeDecodeError:pass
    raise ValueError('Поддерживаются объявленные кодировки Windows-1251, DOS-866 и UTF-8')


def parse_exchange(content,own_account,source_ref):
    result=dict(items=[],errors=[],source_ref=source_ref,own_account=own_account,format='1CClientBankExchange')
    try:
        if own_account[5:8] not in ('810','643'):raise ValueError('Импортируются только рублевые счета; валютные суммы требуют отдельного учёта')
        decoded,codec,digest=_decode(content);result.update(encoding=codec,source_hash=digest)
        lines=[line.strip() for line in decoded.splitlines() if line.strip()]
        if not lines or lines[0]!='1CClientBankExchange' or lines[-1]!='КонецФайла':raise ValueError('Нужна полная выписка 1CClientBankExchange с КонецФайла')
        if len(lines)>100_000 or any(len(line)>5000 for line in lines):raise ValueError('Слишком много реквизитов или слишком длинная строка')
        header={};account_section=None;document=None;documents=[];accounts=set();ended=False
        for line in lines[1:]:
            if ended:raise ValueError('Данные после КонецФайла')
            if line=='КонецФайла':
                if document is not None or account_section is not None:raise ValueError('Незакрытая секция')
                ended=True;continue
            if line=='СекцияРасчСчет':
                if document is not None or account_section is not None:raise ValueError('Вложенная секция')
                account_section={};continue
            if line=='КонецРасчСчет':
                if account_section is None:raise ValueError('Неожиданный конец счета')
                accounts.add(account_section.get('РасчСчет',''));account_section=None;continue
            if line.startswith('СекцияДокумент='):
                if document is not None or account_section is not None:raise ValueError('Вложенная секция')
                document={'document_type':line.split('=',1)[1]};continue
            if line=='КонецДокумента':
                if document is None:raise ValueError('Неожиданный конец документа')
                documents.append(document);document=None
                if len(documents)>MAX_ROWS:raise ValueError('Не более 5 000 банковских документов')
                continue
            if '=' not in line:raise ValueError('Реквизит без знака равенства')
            key,value=line.split('=',1)
            target=document if document is not None else account_section if account_section is not None else header
            # Repeated account/document declarations in multi-account headers
            # are part of the format; payment document fields must be unique.
            if key in target:
                if target is header and key in ('РасчСчет','Документ'):
                    if key=='РасчСчет':accounts.add(value)
                    continue
                raise ValueError('Реквизит повторяется: '+key[:80])
            target[key]=value
            if target is header and key=='РасчСчет':accounts.add(value)
        if header.get('ВерсияФормата') not in ('1.01','1.02','1.03'):raise ValueError('Неподдерживаемая версия обмена')
        if own_account not in accounts:raise ValueError('Выбранный собственный счет отсутствует в шапке выписки')
        seen={}
        for index,doc in enumerate(documents,1):
            try:
                payer=doc.get('ПлательщикСчет') or doc.get('ПлательщикРасчСчет','')
                receiver=doc.get('ПолучательСчет') or doc.get('ПолучательРасчСчет','')
                if not re.fullmatch(r'[0-9]{20}',payer) or not re.fullmatch(r'[0-9]{20}',receiver):raise ValueError('Укажите 20-значные счета плательщика и получателя')
                for prefix,account in (('Плательщик',payer),('Получатель',receiver)):
                    alias=doc.get(prefix+'РасчСчет')
                    if alias and alias!=account:raise ValueError('Счета стороны противоречат друг другу')
                if own_account not in (payer,receiver):raise ValueError('Документ относится к другому собственному счету')
                number=single_line(doc.get('Номер',''))
                if not number or len(number)>200:raise ValueError('Нет корректного номера документа')
                document_date=_date(doc.get('Дата',''))
                if not re.fullmatch(r'[0-9]+(?:\.[0-9]{1,2})?',doc.get('Сумма','')):raise ValueError('Сумма банковского документа должна быть записана цифрами в рублях и копейках')
                try:amount=money(doc.get('Сумма'))
                except ProviderUnavailable:raise ValueError('Нужна положительная сумма в рублях с точностью до копейки') from None
                # Every account declared by this same statement belongs to its
                # own-account scope. Transfers between them are not recovery.
                own_transfer=payer in accounts and receiver in accounts
                incoming=receiver==own_account and not own_transfer
                paid_on=_date(doc.get('ДатаПоступило','')) if incoming else document_date
                if paid_on<document_date:raise ValueError('Дата поступления раньше даты документа')
                inn=InvoiceInput.inn_format(doc.get('ПлательщикИНН',''))
                name=single_line(doc.get('Плательщик1') or doc.get('Плательщик',''))
                purpose=single_line(doc.get('НазначениеПлатежа') or ' '.join(doc.get('НазначениеПлатежа'+str(part),'') for part in range(1,7)).strip())
                if len(name)>200 or len(purpose)>2000:raise ValueError('Наименование или назначение платежа слишком длинное')
                identity=document_identity(own_account,payer,number,document_date,doc['document_type'])
                item=dict(row=index,external_id=identity,amount=amount,paid_on=paid_on,payer_inn=inn,payer_name=name,reference=number,purpose=purpose,document_date=document_date,document_type=doc['document_type'],payer_account=payer,account=own_account,direction='incoming' if incoming else 'own_transfer' if own_transfer else 'outgoing',approvable=incoming)
                result['items'].append(item)
                if identity in seen:
                    result['errors'].append(dict(row=index,message='Документ повторяется'))
                    result['errors'].append(dict(row=seen[identity],message='Документ повторяется'))
                else:seen[identity]=index
            except ValueError as error:result['errors'].append(dict(row=index,message=str(error)))
    except ValueError as error:
        result['items']=[];result['errors']=[dict(row=0,message=str(error))]
    return result


def approve_bank_item(connection,tenant_id,item,evidence,*,distinct_confirmed=False,reason='',actor_id=None):
    """Single safe insert boundary shared by file and direct statement approval."""
    if not item.get('approvable') or item.get('direction')!='incoming':f.fail(422,'Можно подтвердить только поступление на собственный счет')
    facts={key:item.get(key,'') for key in ('amount','paid_on','payer_inn','payer_name','reference','purpose','payer_account','document_date','document_type','account')}
    facts['reference']=normalize_document_number(facts['reference'])
    fingerprint=hashlib.sha256(f._request_json(facts).encode()).hexdigest()
    provenance=json.loads(evidence)
    # Keep valid structured provenance within the existing bank-source limit.
    for key in ('purpose','reason','approval_reason'):
        if key in provenance:provenance[key]=str(provenance[key])[:400]
    provenance['source_fingerprint']=fingerprint
    document=_document_metadata(item)
    if document:provenance['bank_document']=document
    data=f.BankInput(external_id=item['external_id'],amount=item['amount'],paid_on=item['paid_on'],payer_inn=item.get('payer_inn',''),payer_name=item.get('payer_name',''),reference=facts['reference'],evidence=json.dumps(provenance,ensure_ascii=False),confirmed=True)
    old=connection.execute('SELECT * FROM finance_bank_payments WHERE tenant_id=? AND external_id=?',(tenant_id,data.external_id)).fetchone()
    values=data.model_dump(mode='json')
    if old:
        # Filename/approval wording is provenance, not monetary identity.
        if any(str(old[key])!=str(values[key]) for key in ('amount','paid_on','payer_inn','payer_name')) or normalize_document_number(old['reference'])!=facts['reference']:f.fail(409,'Банковский документ уже учтён с другими данными; нужна ручная сверка')
        try:old_fingerprint=json.loads(old['evidence']).get('source_fingerprint')
        except (ValueError,AttributeError):old_fingerprint=None
        if old_fingerprint and old_fingerprint!=fingerprint:f.fail(409,'Изменились реквизиты или назначение банковского документа; нужна ручная сверка')
        return False
    assert_no_duplicate_source(connection,tenant_id,dict(item,**values),distinct_confirmed=distinct_confirmed,reason=reason,actor_id=actor_id)
    connection.execute('INSERT INTO finance_bank_payments(id,tenant_id,external_id,amount,paid_on,payer_inn,payer_name,reference,evidence,confirmed,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(f.uid(),tenant_id,data.external_id,data.amount,str(data.paid_on),data.payer_inn,data.payer_name,data.reference,data.evidence,1,f.timestamp()))
    return True


def attach_routes(router,ctx):
    @router.post('/bank/preview')
    def preview(data:PreviewInput,user=Depends(ctx.get_user)):
        payload=parse_exchange(data.content,data.own_account,data.source_ref)
        with ctx.database(ctx.config,write=True) as connection:
            identifier=f.uid()
            connection.execute('INSERT INTO integration_bank_imports(id,tenant_id,payload_json,actor_id,created_at) VALUES(?,?,?,?,?)',(identifier,user['tenant_id'],json.dumps(payload,ensure_ascii=False),user['id'],f.timestamp()))
            return dict(id=identifier,**payload)

    @router.post('/bank/imports/{import_id}/approve')
    def approve(import_id:str,data:ApprovalInput,user=Depends(ctx.get_user)):
        selected=sorted(set(data.selected_rows))
        if len(selected)!=len(data.selected_rows):f.fail(422,'Строки выбора повторяются')
        with ctx.database(ctx.config,write=True) as connection:
            saved=connection.execute('SELECT * FROM integration_bank_imports WHERE id=? AND tenant_id=?',(import_id,user['tenant_id'])).fetchone()
            if not saved:f.fail(404,'Предпросмотр не найден')
            if saved['result_json']:
                if json.loads(saved['selected_json'])!=selected:f.fail(409,'Предпросмотр уже согласован с другим выбором')
                return json.loads(saved['result_json'])
            payload=json.loads(saved['payload_json']);items={x['row']:x for x in payload['items']};invalid={x['row'] for x in payload['errors']}
            if 0 in invalid or any(row not in items or row in invalid or not items[row]['approvable'] for row in selected):f.fail(422,'Выбраны строки с ошибками или исходящие документы')
            result=dict(imported=0,skipped=0)
            for row in selected:
                item=items[row]
                evidence=json.dumps(dict(source='1CClientBankExchange',source_ref=payload['source_ref'],source_hash=payload['source_hash'],own_account=payload['own_account'],purpose=item['purpose'],approval_reason=data.reason,actor_id=user['id']),ensure_ascii=False)
                inserted=approve_bank_item(connection,user['tenant_id'],item,evidence,distinct_confirmed=data.distinct_confirmed,reason=data.distinct_reason,actor_id=user['id'])
                result['imported' if inserted else 'skipped']+=1
            connection.execute('UPDATE integration_bank_imports SET selected_json=?,result_json=?,approved_at=? WHERE id=? AND tenant_id=?',(json.dumps(selected),json.dumps(result),f.timestamp(),import_id,user['tenant_id']))
            return result
