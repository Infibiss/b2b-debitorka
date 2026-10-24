"""Mapped accounting aggregates are evidence for reconciliation, never invoices.

The source's as-of date is retained. Comparison always uses the CURRENT ledger;
this module does not reconstruct a historical balance from an aggregate export.
"""
import base64
import binascii
import csv
import hashlib
import io
import json
import re
import zipfile
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import Field, StrictInt, field_validator

from . import finance as f
from .business_time import business_today
from .csv_import import rubles_to_kopeks
from .models import Input, InvoiceInput, single_line

MAX_ROWS = 5000
MAX_COLUMNS = 100
MONEY_FIELDS = ('opening_debit','opening_credit','debit_turnover','credit_turnover','ending_debit','ending_credit')
ALLOWED_FIELDS = {'company','inn',*MONEY_FIELDS}
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS accounting_imports (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL REFERENCES tenants(id),payload_json TEXT NOT NULL,
 result_json TEXT,selected_json TEXT,actor_id TEXT NOT NULL,created_at TEXT NOT NULL,approved_at TEXT
);
CREATE TABLE IF NOT EXISTS accounting_reconciliations (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL REFERENCES tenants(id),counterparty_id TEXT NOT NULL,
 import_id TEXT NOT NULL REFERENCES accounting_imports(id),source_type TEXT NOT NULL,source_ref TEXT NOT NULL,
 as_of TEXT NOT NULL,source_hash TEXT NOT NULL,source_json TEXT NOT NULL,source_balance INTEGER NOT NULL,
 ledger_current_balance INTEGER NOT NULL,discrepancy INTEGER NOT NULL,requires_review INTEGER NOT NULL,
 comparison_basis TEXT NOT NULL DEFAULT 'current_ledger',reason TEXT NOT NULL,actor_id TEXT NOT NULL,created_at TEXT NOT NULL,
 UNIQUE(tenant_id,source_type,source_ref,as_of,counterparty_id),
 FOREIGN KEY(counterparty_id,tenant_id) REFERENCES finance_counterparties(id,tenant_id)
);
CREATE INDEX IF NOT EXISTS accounting_reconciliations_tenant ON accounting_reconciliations(tenant_id,as_of);
"""


def initialize_schema(connection):
    for statement in SCHEMA_SQL.split(';'):
        if statement.strip():connection.execute(statement)


class PreviewInput(Input):
    source_type:Literal['osv62','reconciliation_act']
    source_ref:str=Field(min_length=1,max_length=300)
    as_of:date
    format:Literal['csv','xlsx']='csv'
    content:str=Field(min_length=1,max_length=1_500_000)
    mapping:dict[str,str]=Field(default_factory=dict,max_length=20)
    header_row:StrictInt=Field(default=1,ge=1,le=1000)
    sheet:str|None=Field(default=None,max_length=100)
    @field_validator('as_of')
    @classmethod
    def source_date(cls,value):
        if value>business_today():raise ValueError('Дата источника не может быть в будущем')
        return value
    @field_validator('source_ref')
    @classmethod
    def safe_source_ref(cls,value):return single_line(value)


class ApprovalInput(Input):
    reason:str=Field(min_length=1,max_length=3000)
    selected_rows:list[StrictInt]=Field(min_length=1,max_length=MAX_ROWS)


def _xlsx_rows(content,sheet_name):
    try:
        data=base64.b64decode(content,validate=True)
    except (ValueError,binascii.Error) as error:raise ValueError('XLSX должен быть передан в base64') from error
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries=archive.infolist()
            if (len(entries)>500 or len({entry.filename for entry in entries})!=len(entries)
                or sum(entry.file_size for entry in entries)>20_000_000
                or any(entry.file_size>8_000_000 or entry.flag_bits&1 for entry in entries)
                or any('vbaproject' in entry.filename.casefold() or '/externallinks/' in entry.filename.casefold() for entry in entries)):
                raise ValueError('XLSX превышает ограничения или содержит макросы/внешние связи')
            # Defense in depth even if another library disabled openpyxl's default
            # defusedxml integration. Bound the archive before XML parsing.
            from defusedxml.ElementTree import fromstring
            for entry in entries:
                if entry.filename.endswith(('.xml','.rels')):fromstring(archive.read(entry))
        from openpyxl import load_workbook
        workbook=load_workbook(io.BytesIO(data),read_only=True,data_only=False,keep_links=False)
        try:
            if sheet_name and sheet_name not in workbook.sheetnames:raise ValueError('Лист XLSX не найден')
            sheet=workbook[sheet_name] if sheet_name else workbook.worksheets[0]
            if sheet.max_row and sheet.max_row>MAX_ROWS+1000:raise ValueError('Не более 5 000 строк данных')
            if sheet.max_column and sheet.max_column>MAX_COLUMNS:raise ValueError('Не более 100 столбцов')
            rows=[]
            for index,row in enumerate(sheet.iter_rows(),1):
                if index>MAX_ROWS+1000:raise ValueError('Не более 5 000 строк данных')
                if len(row)>MAX_COLUMNS:raise ValueError('Не более 100 столбцов')
                if any(cell.data_type=='f' for cell in row):raise ValueError('Замените формулы XLSX проверенными значениями перед импортом')
                rows.append(['' if cell.value is None else str(cell.value) for cell in row])
            return rows
        finally:workbook.close()
    except ValueError:raise
    except Exception as error:
        # Parser errors must not expose source contents or library internals.
        raise ValueError('Не удалось прочитать безопасный XLSX: сохраните выгрузку без макросов и формул') from error


def source_rows(data):
    if data.format=='xlsx':return _xlsx_rows(data.content,data.sheet)
    content=data.content.lstrip('\ufeff')
    first=content.splitlines()[data.header_row-1] if len(content.splitlines())>=data.header_row else ''
    delimiter=';' if first.count(';')>=first.count(',') else ','
    try:
        rows=[]
        for index,row in enumerate(csv.reader(io.StringIO(content),delimiter=delimiter,strict=True),1):
            if index>MAX_ROWS+1000:raise ValueError('Не более 5 000 строк данных')
            if len(row)>MAX_COLUMNS:raise ValueError('Не более 100 столбцов')
            rows.append(row)
        return rows
    except csv.Error as error:raise ValueError('Некорректное экранирование CSV') from error


def ledger_comparison(c,tenant_id,company,inn):
    cp=c.execute('SELECT * FROM finance_counterparties WHERE tenant_id=? AND identity_key=?',(tenant_id,f.identity_key(company,inn))).fetchone()
    rows=c.execute('SELECT id,revision,amount,adjustment_amount,paid_amount FROM invoices WHERE tenant_id=? AND counterparty_id=? ORDER BY id',(tenant_id,cp['id'])).fetchall() if cp else []
    total=sum(row['amount']+row['adjustment_amount']-row['paid_amount'] for row in rows)
    basis=dict(counterparty_id=cp['id'] if cp else None,revision=cp['revision'] if cp else None,invoices=[dict(row) for row in rows])
    return total,hashlib.sha256(f._request_json(basis).encode()).hexdigest()


def build_preview(c,tenant_id,data):
    columns=[];items=[];errors=[]
    try:
        rows=source_rows(data)
        if len(rows)<data.header_row:raise ValueError('Строка заголовка не найдена')
        headers=[str(value).strip() for value in rows[data.header_row-1]]
        columns=[dict(key='column_'+str(i+1),label=header) for i,header in enumerate(headers)]
        if not headers:raise ValueError('Нет столбцов')
        if not data.mapping or set(data.mapping).difference(ALLOWED_FIELDS):raise ValueError('Явно сопоставьте поля контрагента и денежных остатков с заголовками источника')
        required={'company',*MONEY_FIELDS} if data.source_type=='osv62' else {'company'}
        if required.difference(data.mapping) or not {'ending_debit','ending_credit'}.intersection(data.mapping):raise ValueError('Не все обязательные поля источника сопоставлены')
        mapping={}
        for key,value in data.mapping.items():
            if value in [column['key'] for column in columns]:position=int(value.split('_')[1])-1
            else:
                matches=[i for i,header in enumerate(headers) if header==value]
                if len(matches)!=1:raise ValueError('Заголовок не найден или повторяется. Используйте идентификатор column_N')
                position=matches[0]
            if position in mapping.values():raise ValueError('Один столбец сопоставлен нескольким полям')
            mapping[key]=position
        seen={}
        for index,row in enumerate(rows[data.header_row:],data.header_row+1):
            if index-data.header_row>MAX_ROWS:raise ValueError('Не более 5 000 строк данных')
            if not any(str(value).strip() for value in row):continue
            try:
                if len(row)!=len(headers):raise ValueError('Количество ячеек не совпадает с заголовком')
                raw={key:row[position].strip() for key,position in mapping.items()}
                company=single_line(raw['company'])
                if not company or len(company)>200:raise ValueError('Укажите контрагента длиной до 200 символов')
                inn=InvoiceInput.inn_format(raw.get('inn',''))
                if not inn and (re.match(r'^(итого|всего|оборот|сальдо)(?:\s|$)',f.canonical(company)) or re.fullmatch(r'(?:сч[её]т\s*)?62(?:\.\d+)*',f.canonical(company))):raise ValueError('Итоговая строка не является контрагентом: исключите её')
                values={key:rubles_to_kopeks(raw.get(key,'') or '0') for key in MONEY_FIELDS}
                if any(value>1_000_000_000_000_000 for value in values.values()):raise ValueError('Сумма превышает допустимый предел')
                if all(key in raw for key in MONEY_FIELDS):
                    calculated=values['opening_debit']-values['opening_credit']+values['debit_turnover']-values['credit_turnover']
                    if calculated!=values['ending_debit']-values['ending_credit']:raise ValueError('Начальное сальдо и обороты не согласованы с конечным сальдо')
                source_balance=values['ending_debit']-values['ending_credit']
                total,fingerprint=ledger_comparison(c,tenant_id,company,inn)
                item=dict(row=index,company=company,inn=inn,**values,source_balance=source_balance,ledger_current_balance=total,discrepancy=source_balance-total,requires_review=source_balance!=total,comparison_basis='current_ledger',ledger_fingerprint=fingerprint)
                source=dict(company=company,inn=inn,**values)
                item['source_hash']=hashlib.sha256(f._request_json(source).encode()).hexdigest()
                key=f.identity_key(company,inn)
                if key in seen:
                    errors.append(dict(row=index,message='Контрагент повторяется: исключите детализацию и дубли итогов'))
                    if not any(e['row']==seen[key] for e in errors):errors.append(dict(row=seen[key],message='Контрагент повторяется: исключите детализацию и дубли итогов'))
                else:seen[key]=index
                items.append(item)
            except ValueError as error:errors.append(dict(row=index,message=str(error)))
    except ValueError as error:
        errors.append(dict(row=data.header_row,message=str(error)));items=[]
    return dict(columns=columns,items=items,errors=errors,comparison_basis='current_ledger',source_type=data.source_type,source_ref=data.source_ref,as_of=str(data.as_of))


def create_router(ctx):
    router=APIRouter(prefix='/api/accounting',tags=['accounting'])
    @router.post('/preview')
    def preview(data:PreviewInput,user=Depends(ctx.get_user)):
        with ctx.database(ctx.config,write=True) as c:
            result=build_preview(c,user['tenant_id'],data);import_id=f.uid()
            c.execute('INSERT INTO accounting_imports(id,tenant_id,payload_json,actor_id,created_at) VALUES(?,?,?,?,?)',(import_id,user['tenant_id'],json.dumps(result,ensure_ascii=False),user['id'],f.timestamp()))
            return dict(id=import_id,**result)
    @router.post('/imports/{import_id}/approve')
    def approve(import_id:str,data:ApprovalInput,user=Depends(ctx.get_user)):
        selected=sorted(set(data.selected_rows))
        if len(selected)!=len(data.selected_rows):f.fail(422,'Строки выбора повторяются')
        with ctx.database(ctx.config,write=True) as c:
            saved=c.execute('SELECT * FROM accounting_imports WHERE id=? AND tenant_id=?',(import_id,user['tenant_id'])).fetchone()
            if saved is None:f.fail(404,'Предпросмотр источника не найден')
            if saved['result_json']:
                if json.loads(saved['selected_json'])!=selected:f.fail(409,'Предпросмотр уже согласован с другим выбором строк')
                return json.loads(saved['result_json'])
            payload=json.loads(saved['payload_json']);items={item['row']:item for item in payload['items']};invalid={e['row'] for e in payload['errors']}
            if any(row not in items or row in invalid for row in selected):f.fail(422,'Выбраны отсутствующие строки, итоги или строки с ошибками')
            result=dict(imported=0,skipped=0,comparison_basis='current_ledger')
            for row in selected:
                item=items[row]
                cp_id=f.ensure_counterparty(c,user['tenant_id'],item['company'],item['inn'])
                old=c.execute('SELECT * FROM accounting_reconciliations WHERE tenant_id=? AND source_type=? AND source_ref=? AND as_of=? AND counterparty_id=?',(user['tenant_id'],payload['source_type'],payload['source_ref'],payload['as_of'],cp_id)).fetchone()
                if old:
                    if old['source_hash']!=item['source_hash']:f.fail(409,'Источник с этим номером и датой уже сохранён с другими данными')
                    result['skipped']+=1;continue
                total,fingerprint=ledger_comparison(c,user['tenant_id'],item['company'],item['inn'])
                # Creating an empty counterparty is evidence storage only. Its ID
                # cannot change the meaning of a prior zero-invoice comparison.
                previous_total=item['ledger_current_balance']
                no_prior_invoices=c.execute('SELECT id FROM invoices WHERE tenant_id=? AND counterparty_id=? LIMIT 1',(user['tenant_id'],cp_id)).fetchone() is None
                if total!=previous_total or (fingerprint!=item['ledger_fingerprint'] and not no_prior_invoices):f.fail(409,'Реестр изменился после предпросмотра. Сравните источник заново')
                c.execute('''INSERT INTO accounting_reconciliations(id,tenant_id,counterparty_id,import_id,source_type,source_ref,as_of,source_hash,source_json,source_balance,ledger_current_balance,discrepancy,requires_review,reason,actor_id,created_at)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(f.uid(),user['tenant_id'],cp_id,import_id,payload['source_type'],payload['source_ref'],payload['as_of'],item['source_hash'],json.dumps(item,ensure_ascii=False),item['source_balance'],total,item['source_balance']-total,int(item['source_balance']!=total),data.reason,user['id'],f.timestamp()))
                result['imported']+=1
            c.execute('UPDATE accounting_imports SET result_json=?,selected_json=?,approved_at=? WHERE id=? AND tenant_id=?',(json.dumps(result),json.dumps(selected),f.timestamp(),import_id,user['tenant_id']))
            return result
    @router.get('/reconciliations')
    def reconciliations(user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as c:
            result=[]
            for row in c.execute('SELECT * FROM accounting_reconciliations WHERE tenant_id=? ORDER BY created_at DESC',(user['tenant_id'],)):
                source=json.loads(row['source_json']);item=dict(row);item.pop('source_json')
                result.append(dict(source,**item))
            return dict(items=result)
    return router
