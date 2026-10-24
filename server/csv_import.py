"""Validated invoice-source CSV with opening paid/balance reconciliation."""
import csv
import io
import re
from datetime import datetime
from decimal import Decimal,InvalidOperation
from pydantic import ValidationError
from .models import InvoiceInput

HEADERS={
 'контрагент':'company','компания':'company','инн':'inn','email':'email','e-mail':'email',
 'номер':'number','номер счета':'number','номер счёта':'number','дата':'issued_on','дата счета':'issued_on','дата счёта':'issued_on',
 'срок':'due_on','срок оплаты':'due_on','сумма':'amount','примечание':'notes',
 'оплачено':'paid_amount','оплата':'paid_amount','сумма оплаты':'paid_amount','сумма оплат':'paid_amount','сумма оплачено':'paid_amount','paid':'paid_amount','paid amount':'paid_amount','paid_amount':'paid_amount','amount_paid':'paid_amount','payment_amount':'paid_amount',
 'остаток':'balance','остаток долга':'balance','остаток задолженности':'balance','сальдо':'balance','balance_due':'balance','outstanding':'balance','outstanding_amount':'balance','валюта':'currency',
 **{k:k for k in ('company','inn','number','issued_on','due_on','amount','notes','paid_amount','balance','currency')}
}
REQUIRED={'company','number','issued_on','due_on','amount'}
UNSUPPORTED_FINANCIAL_HEADERS={'status','статус'}
def header_key(raw):
    text=' '.join(raw.strip().casefold().split())
    return re.sub(r'[\s,]*(?:\(\s*)?(?:руб\.?|₽|rub)(?:\s*\))?\s*$','',text).strip()
def rubles_to_kopeks(raw):
    text=re.sub(r'[\s\u00a0\u202f]','',raw).replace(',','.')
    if not re.fullmatch(r'[0-9]+(?:\.[0-9]{1,2})?',text):raise ValueError('Сумма должна быть неотрицательной, максимум два десятичных знака')
    try:return int(Decimal(text)*100)
    except InvalidOperation as error:raise ValueError('Некорректная сумма') from error

def parse_date(raw):
    for pattern in ('%Y-%m-%d','%d.%m.%Y','%d/%m/%Y'):
        try:return datetime.strptime(raw.strip(),pattern).date().isoformat()
        except ValueError:pass
    raise ValueError('Дата должна быть ДД.ММ.ГГГГ или ГГГГ-ММ-ДД')

def parse_csv(content):
    content=content.lstrip('\ufeff');first=content.splitlines()[0] if content.splitlines() else ''
    delimiter=';' if first.count(';')>=first.count(',') else ','
    items=[];errors=[]
    try:
        reader=csv.reader(io.StringIO(content),delimiter=delimiter,strict=True)
        headers=[HEADERS.get(header_key(h),header_key(h)) for h in next(reader,[])]
        if any(h not in HEADERS.values() for h in headers):return [],[{'row':1,'message':'Есть неподдерживаемые столбцы. Сопоставьте источник с форматом реестра.'}]
        if len(set(headers))!=len(headers):return [],[{'row':1,'message':'Столбцы повторяются'}]
        if REQUIRED.difference(headers):return [],[{'row':1,'message':'Не хватает столбцов: '+', '.join(sorted(REQUIRED.difference(headers)))}]
        for line,row in enumerate(reader,2):
            if line>10001:errors.append({'row':line,'message':'Не более 10 000 счетов'});break
            if not any(v.strip() for v in row):continue
            if len(row)!=len(headers):errors.append({'row':line,'message':'Количество ячеек не совпадает с заголовком'});continue
            data={k:v.strip() for k,v in zip(headers,row)}
            try:
                currency=data.pop('currency','RUB').casefold()
                if currency not in ('rub','руб','руб.','643','₽'):raise ValueError('Поддержаны только рублёвые счета')
                data['amount']=rubles_to_kopeks(data['amount'])
                if 'paid_amount' in data:data['paid_amount']=rubles_to_kopeks(data['paid_amount'])
                if 'balance' in data:
                    data['balance']=rubles_to_kopeks(data['balance'])
                    if 'paid_amount' not in data:data['paid_amount']=data['amount']-data['balance']
                data['issued_on']=parse_date(data['issued_on']);data['due_on']=parse_date(data['due_on'])
                items.append(InvoiceInput.model_validate(data).model_dump(mode='json'))
            except ValidationError as error:errors.append({'row':line,'message':error.errors()[0]['msg']})
            except (ValueError,KeyError) as error:errors.append({'row':line,'message':str(error)})
    except csv.Error:errors.append({'row':len(items)+2,'message':'Некорректное экранирование CSV'})
    if not items and not errors:errors.append({'row':2,'message':'Нет счетов'})
    return items,errors
