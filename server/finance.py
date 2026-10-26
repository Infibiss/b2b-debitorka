"""Tenant-scoped financial ledger and policy services. Amounts are integer kopeks.

No bank receipt is fabricated: opening balances and manual payments are distinct
from explicitly confirmed bank source documents and their bounded allocations.
"""
import hashlib
import json
import re
import unicodedata
import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, StrictBool, StrictInt, field_validator

from .business_time import business_today
from .models import Input, Money, CSVInput, valid_email, InvoiceInput

COUNTERPARTY_SCHEMA = """
CREATE TABLE IF NOT EXISTS finance_counterparties (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL REFERENCES tenants(id),identity_key TEXT NOT NULL,
 name TEXT NOT NULL,inn TEXT NOT NULL DEFAULT '',email TEXT NOT NULL DEFAULT '',
 hold INTEGER NOT NULL DEFAULT 0,hold_reason TEXT NOT NULL DEFAULT '',contact_allowed INTEGER NOT NULL DEFAULT 1,
 agent_promises_allowed INTEGER NOT NULL DEFAULT 0,max_promise_days INTEGER NOT NULL DEFAULT 30,
 max_installments INTEGER NOT NULL DEFAULT 6,mandate_expires_on TEXT,revision INTEGER NOT NULL DEFAULT 1,
 UNIQUE(tenant_id,identity_key),UNIQUE(id,tenant_id)
);
CREATE TABLE IF NOT EXISTS finance_bank_payments (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL REFERENCES tenants(id),external_id TEXT NOT NULL,
 amount INTEGER NOT NULL CHECK(amount>0),allocated_amount INTEGER NOT NULL DEFAULT 0,
 returned_amount INTEGER NOT NULL DEFAULT 0,paid_on TEXT NOT NULL,payer_inn TEXT NOT NULL DEFAULT '',
 payer_name TEXT NOT NULL DEFAULT '',reference TEXT NOT NULL,evidence TEXT NOT NULL,confirmed INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL,UNIQUE(tenant_id,external_id),UNIQUE(id,tenant_id),
 CHECK(allocated_amount>=0 AND returned_amount>=0 AND allocated_amount+returned_amount<=amount)
);
"""
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS finance_actions (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL REFERENCES tenants(id),action_type TEXT NOT NULL,source_key TEXT NOT NULL,
 request_json TEXT NOT NULL,result_json TEXT NOT NULL,actor_id TEXT NOT NULL,created_at TEXT NOT NULL,
 UNIQUE(tenant_id,action_type,source_key)
);
CREATE TABLE IF NOT EXISTS finance_adjustments (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,invoice_id TEXT NOT NULL,kind TEXT NOT NULL,
 amount INTEGER NOT NULL,signed_amount INTEGER NOT NULL,effective_on TEXT NOT NULL,reason TEXT NOT NULL,
 actor_id TEXT NOT NULL,created_at TEXT NOT NULL,
 FOREIGN KEY(invoice_id,tenant_id) REFERENCES invoices(id,tenant_id)
);
CREATE TABLE IF NOT EXISTS finance_reversals (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,payment_id TEXT NOT NULL,invoice_id TEXT NOT NULL,
 amount INTEGER NOT NULL CHECK(amount>0),kind TEXT NOT NULL,reason TEXT NOT NULL,effective_on TEXT NOT NULL,
 actor_id TEXT NOT NULL,created_at TEXT NOT NULL,
 FOREIGN KEY(invoice_id,tenant_id) REFERENCES invoices(id,tenant_id)
);
CREATE TABLE IF NOT EXISTS finance_promises (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,invoice_id TEXT NOT NULL,amount INTEGER NOT NULL,
 fulfilled_amount INTEGER NOT NULL DEFAULT 0,due_on TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'active',
 source_key TEXT NOT NULL,actor_id TEXT NOT NULL,created_at TEXT NOT NULL,
 UNIQUE(tenant_id,source_key),FOREIGN KEY(invoice_id,tenant_id) REFERENCES invoices(id,tenant_id)
);
CREATE TABLE IF NOT EXISTS finance_installments (
 id TEXT PRIMARY KEY,promise_id TEXT NOT NULL REFERENCES finance_promises(id),due_on TEXT NOT NULL,
 amount INTEGER NOT NULL,fulfilled_amount INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS finance_imports (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL REFERENCES tenants(id),payload_json TEXT NOT NULL,
 result_json TEXT,created_at TEXT NOT NULL,approved_at TEXT,actor_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS finance_identity_conflicts (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,invoice_id TEXT NOT NULL,conflicting_invoice_id TEXT NOT NULL,
 reason TEXT NOT NULL,created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS finance_payments_invoice ON payments(tenant_id,invoice_id);
CREATE INDEX IF NOT EXISTS finance_promises_invoice ON finance_promises(tenant_id,invoice_id);
"""


def uid(): return str(uuid.uuid4())
def timestamp(): return datetime.now(timezone.utc).isoformat(timespec='microseconds')
def fail(status, message): raise HTTPException(status,message)
def canonical(value): return ' '.join(unicodedata.normalize('NFKC',value).casefold().split())
def number_key(value): return canonical(value)
def identity_key(name,inn=''):
    return 'inn:'+''.join(str(unicodedata.digit(c)) for c in inn) if inn else 'name:'+re.sub(r'[^\w]+',' ',canonical(name).replace('ё','е')).strip()
def money(amount): return f'{amount//100:,}'.replace(',', ' ')+f',{amount%100:02d}'
def effective_amount(row): return row['amount'] + row['adjustment_amount']
def balance(row): return effective_amount(row)-row['paid_amount']
def public_row(row): return dict(row)


def initialize_schema(connection):
    for statement in (COUNTERPARTY_SCHEMA+SCHEMA_SQL).split(';'):
        if statement.strip(): connection.execute(statement)


def cp_row(connection,tenant_id,cp_id):
    row=connection.execute('SELECT * FROM finance_counterparties WHERE id=? AND tenant_id=?',(cp_id,tenant_id)).fetchone()
    if row is None: fail(404,'Контрагент не найден')
    return row


def ensure_counterparty(connection,tenant_id,name,inn='',email=''):
    key=identity_key(name,inn)
    row=connection.execute('SELECT * FROM finance_counterparties WHERE tenant_id=? AND identity_key=?',(tenant_id,key)).fetchone()
    if row: return row['id']
    cp_id=uid()
    connection.execute('INSERT INTO finance_counterparties(id,tenant_id,identity_key,name,inn,email) VALUES(?,?,?,?,?,?)',(cp_id,tenant_id,key,name,inn,email))
    return cp_id


def load_invoice(connection,tenant_id,invoice_id):
    row=connection.execute('''SELECT i.*,c.hold AS counterparty_hold,c.contact_allowed AS counterparty_contact_allowed,
      c.mandate_expires_on AS counterparty_mandate_expires_on FROM invoices i
      JOIN finance_counterparties c ON c.id=i.counterparty_id AND c.tenant_id=i.tenant_id
      WHERE i.id=? AND i.tenant_id=?''',(invoice_id,tenant_id)).fetchone()
    if row is None: fail(404,'Счёт не найден')
    return row


def view_invoice(row):
    result={key:row[key] for key in ('id','company','inn','email','number','issued_on','due_on','paid_amount','promise_date','notes','counterparty_id','opening_paid_amount','adjustment_amount','revision','promised_amount')}
    remaining=balance(row); days=max(0,(business_today()-date.fromisoformat(row['due_on'])).days) if remaining else 0
    status='paid' if remaining==0 else row['status']
    if remaining and status=='open' and row['promised_amount']>0: status='promised'
    reasons=[]
    broken=remaining and row['promised_amount']>0 and row['promise_date'] and date.fromisoformat(row['promise_date'])<business_today()
    if days: reasons.append(f'Просрочка {days} дн.')
    if broken: reasons.append('Нарушено обещание оплаты')
    if remaining>=10_000_000 and days: reasons.append('Остаток от 100 000 ₽')
    priority='high' if broken or days>=30 or (remaining>=10_000_000 and days) else 'medium' if days else 'low'
    if status in ('paid','disputed','paused'): priority='low'
    if status=='disputed': reasons.append('Спор: требуется решение сотрудника')
    if status=='paused': reasons.append('Контакт приостановлен')
    result.update(amount=effective_amount(row),original_amount=row['amount'],balance=remaining,days_overdue=days,status=status,priority=priority,priority_reasons=reasons)
    return result


def emit(connection,tenant_id,invoice_id,kind,title,detail=''):
    connection.execute('INSERT INTO events(id,tenant_id,invoice_id,type,title,detail,created_at) VALUES(?,?,?,?,?,?,?)',(uid(),tenant_id,invoice_id,kind,title,detail,timestamp()))


def bump(connection,tenant_id,invoice_id,reason='finance_changed'):
    connection.execute('UPDATE invoices SET revision=revision+1 WHERE id=? AND tenant_id=?',(invoice_id,tenant_id))
    connection.execute("UPDATE messages SET status='draft',invalidation_reason=COALESCE(invalidation_reason,?) WHERE invoice_id=? AND tenant_id=? AND status!='sent'",(reason,invoice_id,tenant_id))


def _request_json(payload): return json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'),default=str)
def existing_action(connection,tenant_id,kind,key,payload):
    row=connection.execute('SELECT * FROM finance_actions WHERE tenant_id=? AND action_type=? AND source_key=?',(tenant_id,kind,key)).fetchone()
    if row:
        if row['request_json']!=_request_json(payload): fail(409,'Ключ операции уже использован с другими данными')
        return json.loads(row['result_json'])
    return None

def save_action(connection,tenant_id,kind,key,payload,result,actor_id):
    connection.execute('INSERT INTO finance_actions VALUES(?,?,?,?,?,?,?,?)',(uid(),tenant_id,kind,key,_request_json(payload),_request_json(result),actor_id,timestamp()))


def sync_promises(connection,tenant_id,invoice_id,payment_delta=0):
    if payment_delta>0:
        rows=connection.execute("SELECT * FROM finance_installments WHERE promise_id IN(SELECT id FROM finance_promises WHERE tenant_id=? AND invoice_id=? AND status='active') ORDER BY due_on,id",(tenant_id,invoice_id)).fetchall()
        for row in rows:
            applied=min(payment_delta,row['amount']-row['fulfilled_amount'])
            connection.execute('UPDATE finance_installments SET fulfilled_amount=fulfilled_amount+? WHERE id=?',(applied,row['id']))
            payment_delta-=applied
            if payment_delta<=0: break
    elif payment_delta<0:
        rows=connection.execute("SELECT s.* FROM finance_installments s JOIN finance_promises p ON p.id=s.promise_id WHERE p.tenant_id=? AND p.invoice_id=? AND p.status IN('active','fulfilled') ORDER BY s.due_on DESC,s.id DESC",(tenant_id,invoice_id)).fetchall()
        for row in rows:
            released=min(-payment_delta,row['fulfilled_amount'])
            connection.execute('UPDATE finance_installments SET fulfilled_amount=fulfilled_amount-? WHERE id=?',(released,row['id']))
            payment_delta+=released
            if payment_delta>=0: break
    promises=connection.execute("SELECT * FROM finance_promises WHERE tenant_id=? AND invoice_id=? AND status IN('active','fulfilled')",(tenant_id,invoice_id)).fetchall()
    for item in promises:
        fulfilled=connection.execute('SELECT COALESCE(SUM(fulfilled_amount),0) AS total FROM finance_installments WHERE promise_id=?',(item['id'],)).fetchone()['total']
        connection.execute('UPDATE finance_promises SET fulfilled_amount=?,status=? WHERE id=?',(fulfilled,'fulfilled' if fulfilled>=item['amount'] else 'active',item['id']))
    sums=connection.execute("SELECT COALESCE(SUM(s.amount-s.fulfilled_amount),0) AS total,MIN(CASE WHEN s.amount>s.fulfilled_amount THEN s.due_on END) AS due FROM finance_installments s JOIN finance_promises p ON p.id=s.promise_id WHERE p.tenant_id=? AND p.invoice_id=? AND p.status='active'",(tenant_id,invoice_id)).fetchone()
    inv=load_invoice(connection,tenant_id,invoice_id)
    promised=min(balance(inv),sums['total'])
    connection.execute('UPDATE invoices SET promised_amount=?,promise_date=? WHERE id=? AND tenant_id=?',(promised,sums['due'] if promised else None,invoice_id,tenant_id))


def record_manual_payment(connection,tenant_id,invoice_id,amount,paid_on,reference,actor_id):
    row=load_invoice(connection,tenant_id,invoice_id)
    old=connection.execute('SELECT * FROM payments WHERE tenant_id=? AND invoice_id=? AND reference=?',(tenant_id,invoice_id,reference)).fetchone()
    if old:
        if old['amount']!=amount or old['paid_on']!=str(paid_on): fail(409,'Такой номер платежа уже зарегистрирован с другими данными')
        return view_invoice(row)
    if amount<=0 or amount>balance(row): fail(422,'Сумма платежа превышает остаток по счёту')
    if str(paid_on)<row['issued_on']: fail(422,'Дата платежа не может быть раньше даты счёта')
    payment_id=uid()
    connection.execute('INSERT INTO payments(id,tenant_id,invoice_id,amount,paid_on,reference,created_at,reversed_amount) VALUES(?,?,?,?,?,?,?,0)',(payment_id,tenant_id,invoice_id,amount,str(paid_on),reference,timestamp()))
    changed=connection.execute('UPDATE invoices SET paid_amount=paid_amount+? WHERE id=? AND tenant_id=? AND amount+adjustment_amount-paid_amount>=?',(amount,invoice_id,tenant_id,amount))
    if changed.rowcount!=1: fail(422,'Сумма платежа превышает остаток по счёту')
    bump(connection,tenant_id,invoice_id); sync_promises(connection,tenant_id,invoice_id,amount)
    emit(connection,tenant_id,invoice_id,'payment_recorded','Зарегистрирована оплата',f'{money(amount)} ₽ · {reference}')
    return view_invoice(load_invoice(connection,tenant_id,invoice_id))


def record_promise(connection,tenant_id,invoice_id,amount,due_date,actor_id,source_key,installments=None):
    payload=dict(invoice_id=invoice_id,amount=amount,date=str(due_date),installments=installments)
    old=existing_action(connection,tenant_id,'promise',source_key,payload)
    if old: return old
    inv=load_invoice(connection,tenant_id,invoice_id)
    if inv['status']=='disputed' or balance(inv)<=0: fail(409,'По закрытому или спорному счёту обещание недоступно')
    if isinstance(amount,bool) or not isinstance(amount,int) or amount<=0 or amount>balance(inv): fail(422,'Обещанная сумма должна быть в пределах остатка')
    if date.fromisoformat(str(due_date))<business_today(): fail(422,'Дата обещания не может быть в прошлом')
    schedule=installments or [{'date':str(due_date),'amount':amount}]
    if not schedule or len(schedule)>60 or sum(item['amount'] for item in schedule)!=amount: fail(422,'Сумма графика должна совпадать с обещанием')
    if any(type(item['amount']) is not int or item['amount']<=0 or date.fromisoformat(str(item['date']))<business_today() for item in schedule): fail(422,'Некорректный платёж в графике')
    if max(str(item['date']) for item in schedule)!=str(due_date): fail(422,'Дата обещания должна совпадать с последним платежом графика')
    connection.execute("UPDATE finance_promises SET status='cancelled' WHERE tenant_id=? AND invoice_id=? AND status='active'",(tenant_id,invoice_id))
    promise_id=uid()
    connection.execute('INSERT INTO finance_promises(id,tenant_id,invoice_id,amount,due_on,source_key,actor_id,created_at) VALUES(?,?,?,?,?,?,?,?)',(promise_id,tenant_id,invoice_id,amount,str(due_date),source_key,actor_id,timestamp()))
    for item in schedule: connection.execute('INSERT INTO finance_installments(id,promise_id,due_on,amount) VALUES(?,?,?,?)',(uid(),promise_id,str(item['date']),item['amount']))
    sync_promises(connection,tenant_id,invoice_id); bump(connection,tenant_id,invoice_id)
    result=dict(id=promise_id,invoice_id=invoice_id,amount=amount,date=str(due_date),installments=schedule,status='active')
    save_action(connection,tenant_id,'promise',source_key,payload,result,actor_id)
    emit(connection,tenant_id,invoice_id,'promise_recorded','Зафиксировано обещание оплаты',f'{money(amount)} ₽ · {due_date}')
    return result


def set_hold(connection,tenant_id,counterparty_id,hold,reason,actor_id,source_key=None):
    if not reason.strip(): fail(422,'Укажите причину изменения')
    cp_row(connection,tenant_id,counterparty_id)
    payload=dict(counterparty_id=counterparty_id,hold=bool(hold),reason=reason)
    if source_key:
        old=existing_action(connection,tenant_id,'hold',source_key,payload)
        if old: return old
    connection.execute('UPDATE finance_counterparties SET hold=?,hold_reason=?,revision=revision+1 WHERE id=? AND tenant_id=?',(int(hold),reason,counterparty_id,tenant_id))
    for inv in connection.execute('SELECT id FROM invoices WHERE tenant_id=? AND counterparty_id=?',(tenant_id,counterparty_id)).fetchall():
        bump(connection,tenant_id,inv['id'],'counterparty_policy_changed')
        emit(connection,tenant_id,inv['id'],'counterparty_hold','Пауза контакта по контрагенту' if hold else 'Пауза контрагента снята',reason)
    result=dict(cp_row(connection,tenant_id,counterparty_id))
    if source_key: save_action(connection,tenant_id,'hold',source_key,payload,result,actor_id)
    return result


def set_dispute(connection,tenant_id,invoice_id,disputed,reason,actor_id,source_key=None):
    inv=load_invoice(connection,tenant_id,invoice_id)
    if balance(inv)<=0: fail(409,'Счёт закрыт')
    payload=dict(invoice_id=invoice_id,disputed=bool(disputed),reason=reason)
    if source_key:
        old=existing_action(connection,tenant_id,'dispute',source_key,payload)
        if old:return old
    connection.execute('UPDATE invoices SET status=? WHERE id=? AND tenant_id=?',('disputed' if disputed else 'open',invoice_id,tenant_id))
    bump(connection,tenant_id,invoice_id)
    emit(connection,tenant_id,invoice_id,'dispute_recorded','Спор по счёту' if disputed else 'Спор разрешён',reason)
    result=view_invoice(load_invoice(connection,tenant_id,invoice_id))
    if source_key:save_action(connection,tenant_id,'dispute',source_key,payload,result,actor_id)
    return result


def payment_history(connection,tenant_id,invoice_id):
    inv=load_invoice(connection,tenant_id,invoice_id)
    result=[]
    if inv['opening_paid_amount']:
        result.append(dict(id='opening:'+invoice_id,type='opening',amount=inv['opening_paid_amount'],signed_reduction=inv['opening_paid_amount'],effective_on=inv['issued_on'],paid_on=inv['issued_on'],confirmed=False,date_basis='assumed_issue_date',verified_date=False))
    for row in connection.execute('SELECT * FROM payments WHERE tenant_id=? AND invoice_id=? ORDER BY paid_on,created_at',(tenant_id,invoice_id)):
        result.append(dict(row)|dict(type='payment',signed_reduction=row['amount'],effective_on=row['paid_on'],confirmed=bool(row['bank_payment_id'])))
    for row in connection.execute('SELECT * FROM finance_reversals WHERE tenant_id=? AND invoice_id=? ORDER BY effective_on,created_at',(tenant_id,invoice_id)):
        result.append(dict(row)|dict(type='reversal',signed_reduction=-row['amount']))
    for row in connection.execute('SELECT * FROM finance_adjustments WHERE tenant_id=? AND invoice_id=? ORDER BY effective_on,created_at',(tenant_id,invoice_id)):
        result.append(dict(row)|dict(type='adjustment',signed_reduction=-row['signed_amount']))
    return sorted(result,key=lambda item:(item['effective_on'],item['id']))


def confirmed_recovery(connection,tenant_id,invoice_id):
    load_invoice(connection,tenant_id,invoice_id)
    rows=connection.execute('''SELECT p.*,b.confirmed FROM payments p JOIN finance_bank_payments b ON b.id=p.bank_payment_id AND b.tenant_id=p.tenant_id WHERE p.tenant_id=? AND p.invoice_id=? AND b.confirmed=1''',(tenant_id,invoice_id)).fetchall()
    return [dict(row)|dict(payment_id=row['id'],original_amount=row['amount'],amount=row['amount']-row['reversed_amount'],confirmed=True,stage=None) for row in rows]


def financial_snapshot(connection,tenant_id,invoice_id):
    inv=load_invoice(connection,tenant_id,invoice_id); view=view_invoice(inv)
    cp=dict(cp_row(connection,tenant_id,inv['counterparty_id']))
    history=payment_history(connection,tenant_id,invoice_id)
    result=dict(view)|dict(invoice=view,counterparty=cp,financial_events=history,payments=history,ledger_revision=inv['revision'])
    # Calendar-derived aging is presentation, not a financial state change.
    facts={key:value for key,value in view.items() if key not in ('days_overdue','priority','priority_reasons')}
    state=dict(invoice=facts,counterparty=cp,financial_events=history,ledger_revision=inv['revision'])
    result['snapshot_hash']=hashlib.sha256(_request_json(state).encode()).hexdigest()
    return result
invoice_snapshot=financial_snapshot


def agent_gate(connection,tenant_id,invoice_id,intent,amount=None,due_date=None):
    inv=load_invoice(connection,tenant_id,invoice_id); cp=cp_row(connection,tenant_id,inv['counterparty_id']); reasons=[]
    if cp['hold']:reasons.append('counterparty_hold')
    if not cp['contact_allowed']:reasons.append('contact_not_authorized')
    if cp['mandate_expires_on'] and cp['mandate_expires_on']<str(business_today()):reasons.append('mandate_expired')
    if inv['status'] in ('paused','disputed') or balance(inv)<=0:reasons.append('invoice_not_actionable')
    if intent in ('promise','installment','installments','payment_promise'):
        if not cp['agent_promises_allowed']:reasons.append('promise_mandate_required')
        if amount is None or type(amount) is not int or amount<=0 or amount>balance(inv):reasons.append('invalid_promise_amount')
        if not due_date or not business_today()<=date.fromisoformat(str(due_date))<=business_today()+timedelta(days=cp['max_promise_days']):reasons.append('date_outside_mandate')
    return reasons


class BankInput(Input):
    external_id:str=Field(min_length=1,max_length=200)
    amount:Money
    paid_on:date
    payer_inn:str=Field(default='',max_length=12)
    payer_name:str=Field(default='',max_length=200)
    reference:str=Field(min_length=1,max_length=200)
    evidence:str=Field(min_length=1,max_length=3000)
    confirmed:StrictBool
    distinct_confirmed:StrictBool=False
    distinct_reason:str=Field(default='',max_length=3000)
    @field_validator('payer_inn')
    @classmethod
    def validate_payer_inn(cls,value):
        return InvoiceInput.inn_format(value)
    @field_validator('paid_on')
    @classmethod
    def not_future(cls,value):
        if value>business_today():raise ValueError('Дата поступления не может быть в будущем')
        return value
class AllocateInput(Input):
    invoice_id:str
    amount:Money
    idempotency_key:str=Field(min_length=1,max_length=200)
class ReverseInput(Input):
    amount:Money
    reason:str=Field(min_length=1,max_length=3000)
    idempotency_key:str=Field(min_length=1,max_length=200)
    kind:str='correction'
class AdjustmentInput(ReverseInput):
    effective_on:date
class InstallmentInput(Input):
    date:date
    amount:Money
class PromiseBody(Input):
    amount:Money
    date:date
    installments:list[InstallmentInput]|None=None
    idempotency_key:str=Field(min_length=1,max_length=200)
class ApproveImport(Input):
    reason:str=Field(min_length=1,max_length=3000)
class CounterpartyPatch(Input):
    hold:StrictBool|None=None
    hold_reason:str|None=Field(default=None,max_length=3000)
    contact_allowed:StrictBool|None=None
    agent_promises_allowed:StrictBool|None=None
    max_promise_days:StrictInt|None=Field(default=None,ge=1,le=365)
    max_installments:StrictInt|None=Field(default=None,ge=1,le=60)
    mandate_expires_on:date|None=None


def bank_view(row):return dict(row)|dict(available_amount=row['amount']-row['allocated_amount']-row['returned_amount'])
def payment_row(connection,tenant_id,payment_id):
    row=connection.execute('SELECT * FROM payments WHERE id=? AND tenant_id=?',(payment_id,tenant_id)).fetchone()
    if row is None:fail(404,'Платёж не найден')
    return row


def payment_view(connection,row):
    result=dict(row)
    reference=None
    if row['bank_payment_id']:
        source=connection.execute('SELECT reference FROM finance_bank_payments WHERE id=? AND tenant_id=?',(row['bank_payment_id'],row['tenant_id'])).fetchone()
        if source:reference=source['reference']
    result['display_reference']=reference or row['reference']
    return result


def create_router(ctx):
    router=APIRouter(prefix='/api/finance',tags=['finance'])
    @router.get('/counterparties')
    def counterparties(user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as c:
            items=[]
            for row in c.execute('SELECT * FROM finance_counterparties WHERE tenant_id=? ORDER BY name',(user['tenant_id'],)):
                debt=c.execute('SELECT COALESCE(SUM(amount+adjustment_amount-paid_amount),0) AS total FROM invoices WHERE tenant_id=? AND counterparty_id=?',(user['tenant_id'],row['id'])).fetchone()['total']
                items.append(dict(row)|dict(company=row['name'],outstanding=debt))
            return {'items':items}
    @router.patch('/counterparties/{cp_id}')
    def patch_cp(cp_id:str,data:CounterpartyPatch,user=Depends(ctx.get_user)):
        with ctx.database(ctx.config,write=True) as c:
            cp=cp_row(c,user['tenant_id'],cp_id);values={k:v for k,v in data.model_dump(exclude_unset=True,mode='json').items() if v is not None or k=='mandate_expires_on'}
            if set(values) - {'hold', 'hold_reason', 'contact_allowed'} or values.get('contact_allowed') is True:
                from .workflow import require_manager
                require_manager(c, user)
            if 'hold' in values:
                set_hold(c,user['tenant_id'],cp_id,values.pop('hold'),values.get('hold_reason') or cp['hold_reason'] or 'Решение ответственного',user['id'])
            if values:
                values={k:int(v) if isinstance(v,bool) else v for k,v in values.items()}
                columns=','.join(k+'=?' for k in values)
                c.execute(f'UPDATE finance_counterparties SET {columns},revision=revision+1 WHERE id=? AND tenant_id=?',(*values.values(),cp_id,user['tenant_id']))
                for inv in c.execute('SELECT id FROM invoices WHERE tenant_id=? AND counterparty_id=?',(user['tenant_id'],cp_id)).fetchall():
                    bump(c,user['tenant_id'],inv['id'],'counterparty_policy_changed')
                    emit(c,user['tenant_id'],inv['id'],'counterparty_policy_updated','Правила работы с контрагентом обновлены',', '.join(sorted(values)))
            return dict(cp_row(c,user['tenant_id'],cp_id))
    @router.get('/bank-payments')
    def list_bank(user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as c:return {'items':[bank_view(row) for row in c.execute('SELECT * FROM finance_bank_payments WHERE tenant_id=? ORDER BY paid_on DESC,created_at DESC',(user['tenant_id'],))]}
    @router.post('/bank-payments',status_code=201)
    def add_bank(data:BankInput,user=Depends(ctx.get_user)):
        if not data.confirmed:fail(422,'Подтвердите сверку поступления с банковским документом')
        with ctx.database(ctx.config,write=True) as c:
            old=c.execute('SELECT * FROM finance_bank_payments WHERE tenant_id=? AND external_id=?',(user['tenant_id'],data.external_id)).fetchone()
            values=data.model_dump(mode='json',exclude={'distinct_confirmed','distinct_reason'})
            if old:
                if any(str(old[k])!=str(v if k!='confirmed' else int(v)) for k,v in values.items()):fail(409,'Банковский идентификатор уже использован с другими данными')
                return bank_view(old)
            from .bank_exchange import assert_no_duplicate_source
            assert_no_duplicate_source(c,user['tenant_id'],values,distinct_confirmed=data.distinct_confirmed,
                reason=data.distinct_reason,actor_id=user['id'])
            bank_id=uid()
            c.execute('INSERT INTO finance_bank_payments(id,tenant_id,external_id,amount,paid_on,payer_inn,payer_name,reference,evidence,confirmed,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(bank_id,user['tenant_id'],data.external_id,data.amount,str(data.paid_on),data.payer_inn,data.payer_name,data.reference,data.evidence,1,timestamp()))
            return bank_view(c.execute('SELECT * FROM finance_bank_payments WHERE id=? AND tenant_id=?',(bank_id,user['tenant_id'])).fetchone())
    @router.post('/bank-payments/{bank_id}/allocate')
    def allocate(bank_id:str,data:AllocateInput,user=Depends(ctx.get_user)):
        with ctx.database(ctx.config,write=True) as c:
            payload=dict(bank_id=bank_id,**data.model_dump())
            old=existing_action(c,user['tenant_id'],'allocation',data.idempotency_key,payload)
            if old:return old
            bank=c.execute('SELECT * FROM finance_bank_payments WHERE id=? AND tenant_id=?',(bank_id,user['tenant_id'])).fetchone()
            if bank is None:fail(404,'Банковское поступление не найдено')
            inv=load_invoice(c,user['tenant_id'],data.invoice_id)
            if bank['payer_inn'] and (not inv['inn'] or identity_key('',bank['payer_inn'])!=identity_key('',inv['inn'])):fail(409,'ИНН плательщика не совпадает с контрагентом. Требуется отдельная сверка основания оплаты третьим лицом')
            if bank['paid_on']<inv['issued_on']:fail(422,'Поступление предшествует счёту: требуется отдельная сверка аванса')
            if data.amount>balance(inv):fail(422,'Сумма распределения превышает остаток счёта')
            changed=c.execute('UPDATE finance_bank_payments SET allocated_amount=allocated_amount+? WHERE id=? AND tenant_id=? AND amount-allocated_amount-returned_amount>=?',(data.amount,bank_id,user['tenant_id'],data.amount))
            if changed.rowcount!=1:fail(422,'Недостаточно нераспределённого банковского поступления')
            payment_id=uid();reference='bank:'+bank_id+':'+data.idempotency_key
            c.execute('INSERT INTO payments(id,tenant_id,invoice_id,amount,paid_on,reference,created_at,bank_payment_id,reversed_amount) VALUES(?,?,?,?,?,?,?,?,0)',(payment_id,user['tenant_id'],data.invoice_id,data.amount,bank['paid_on'],reference,timestamp(),bank_id))
            c.execute('UPDATE invoices SET paid_amount=paid_amount+? WHERE id=? AND tenant_id=?',(data.amount,data.invoice_id,user['tenant_id']))
            bump(c,user['tenant_id'],data.invoice_id);sync_promises(c,user['tenant_id'],data.invoice_id,data.amount)
            emit(c,user['tenant_id'],data.invoice_id,'bank_allocated','Банковское поступление распределено',bank['reference'])
            result={'invoice':view_invoice(load_invoice(c,user['tenant_id'],data.invoice_id)),'payment':payment_view(c,payment_row(c,user['tenant_id'],payment_id)),'bank_payment':bank_view(c.execute('SELECT * FROM finance_bank_payments WHERE id=?',(bank_id,)).fetchone())}
            save_action(c,user['tenant_id'],'allocation',data.idempotency_key,payload,result,user['id']);return result
    @router.post('/payments/{payment_id}/reverse')
    def reverse(payment_id:str,data:ReverseInput,user=Depends(ctx.get_user)):
        if data.kind not in ('correction','refund'):fail(422,'Некорректный вид сторнирования')
        with ctx.database(ctx.config,write=True) as c:
            payload=dict(payment_id=payment_id,**data.model_dump());old=existing_action(c,user['tenant_id'],'reversal',data.idempotency_key,payload)
            if old:return old
            payment=payment_row(c,user['tenant_id'],payment_id)
            if data.amount>payment['amount']-payment['reversed_amount']:fail(422,'Сумма сторнирования превышает остаток платежа')
            c.execute('UPDATE payments SET reversed_amount=reversed_amount+? WHERE id=? AND tenant_id=?',(data.amount,payment_id,user['tenant_id']))
            c.execute('UPDATE invoices SET paid_amount=paid_amount-? WHERE id=? AND tenant_id=?',(data.amount,payment['invoice_id'],user['tenant_id']))
            if payment['bank_payment_id']:
                c.execute('UPDATE finance_bank_payments SET allocated_amount=allocated_amount-?,returned_amount=returned_amount+? WHERE id=? AND tenant_id=?',(data.amount,data.amount if data.kind=='refund' else 0,payment['bank_payment_id'],user['tenant_id']))
            c.execute('INSERT INTO finance_reversals VALUES(?,?,?,?,?,?,?,?,?,?)',(uid(),user['tenant_id'],payment_id,payment['invoice_id'],data.amount,data.kind,data.reason,payment['paid_on'] if data.kind=='correction' else str(business_today()),user['id'],timestamp()))
            bump(c,user['tenant_id'],payment['invoice_id']);sync_promises(c,user['tenant_id'],payment['invoice_id'],-data.amount)
            emit(c,user['tenant_id'],payment['invoice_id'],'payment_reversed','Возврат оплаты' if data.kind=='refund' else 'Платёж сторнирован',data.reason)
            result={'invoice':view_invoice(load_invoice(c,user['tenant_id'],payment['invoice_id'])),'payment':payment_view(c,payment_row(c,user['tenant_id'],payment_id))}
            save_action(c,user['tenant_id'],'reversal',data.idempotency_key,payload,result,user['id']);return result
    @router.post('/invoices/{invoice_id}/adjustments')
    def adjust(invoice_id:str,data:AdjustmentInput,user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as c:
            from .workflow import require_manager
            require_manager(c, user)
        if data.kind not in ('return','offset','credit','debit'):fail(422,'Некорректный вид корректировки')
        if data.effective_on>business_today():fail(422,'Корректировка не может быть датирована будущим')
        with ctx.database(ctx.config,write=True) as c:
            payload=dict(invoice_id=invoice_id,**data.model_dump(mode='json'));old=existing_action(c,user['tenant_id'],'adjustment',data.idempotency_key,payload)
            if old:return old
            inv=load_invoice(c,user['tenant_id'],invoice_id);signed=data.amount if data.kind=='debit' else -data.amount
            if data.effective_on<date.fromisoformat(inv['issued_on']) or balance(inv)+signed<0:fail(422,'Корректировка выходит за пределы остатка или даты счёта')
            c.execute('INSERT INTO finance_adjustments VALUES(?,?,?,?,?,?,?,?,?,?)',(uid(),user['tenant_id'],invoice_id,data.kind,data.amount,signed,str(data.effective_on),data.reason,user['id'],timestamp()))
            c.execute('UPDATE invoices SET adjustment_amount=adjustment_amount+? WHERE id=? AND tenant_id=?',(signed,invoice_id,user['tenant_id']))
            bump(c,user['tenant_id'],invoice_id);sync_promises(c,user['tenant_id'],invoice_id)
            emit(c,user['tenant_id'],invoice_id,'principal_adjusted','Основание долга скорректировано',data.reason)
            result=view_invoice(load_invoice(c,user['tenant_id'],invoice_id));save_action(c,user['tenant_id'],'adjustment',data.idempotency_key,payload,result,user['id']);return result
    @router.post('/invoices/{invoice_id}/promise')
    def promise(invoice_id:str,data:PromiseBody,user=Depends(ctx.get_user)):
        with ctx.database(ctx.config,write=True) as c:
            if data.installments:
                from .workflow import require_manager
                require_manager(c, user)
            return record_promise(c,user['tenant_id'],invoice_id,data.amount,data.date,user['id'],data.idempotency_key,[i.model_dump(mode='json') for i in data.installments] if data.installments else None)
    @router.get('/invoices/{invoice_id}/ledger')
    def ledger(invoice_id:str,user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as c:
            snap=financial_snapshot(c,user['tenant_id'],invoice_id)
            promises=[]
            for row in c.execute('SELECT * FROM finance_promises WHERE tenant_id=? AND invoice_id=? ORDER BY created_at,id',(user['tenant_id'],invoice_id)):
                installments=[{key:item[key] for key in ('id','due_on','amount','fulfilled_amount')} for item in c.execute('SELECT s.* FROM finance_installments s JOIN finance_promises p ON p.id=s.promise_id WHERE p.tenant_id=? AND p.invoice_id=? AND p.id=? ORDER BY s.due_on,s.id',(user['tenant_id'],invoice_id,row['id']))]
                promises.append(dict(row)|dict(installments=installments))
            return {'invoice':snap['invoice'],'counterparty':snap['counterparty'],'payments':[payment_view(c,r) for r in c.execute('SELECT * FROM payments WHERE tenant_id=? AND invoice_id=?',(user['tenant_id'],invoice_id))],'adjustments':[dict(r) for r in c.execute('SELECT * FROM finance_adjustments WHERE tenant_id=? AND invoice_id=?',(user['tenant_id'],invoice_id))],'promises':promises,'snapshot_hash':snap['snapshot_hash'],'financial_events':snap['financial_events']}
    from .finance_imports import attach_import_routes
    attach_import_routes(router,ctx)
    return router
