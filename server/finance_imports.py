"""Explicit approval of ledger-source changes; no opening payment is a bank receipt."""
import json
from fastapi import Depends
from . import finance as f
from .csv_import import parse_csv
from .models import CSVInput


def preview_changes(c,tenant_id,items):
    changes=[];seen=set()
    for item in items:
        key=(f.identity_key(item['company'],item.get('inn','')),f.number_key(item['number']))
        if key in seen:
            changes.append(dict(action='conflict',after=item,reason='Один счёт повторяется в источнике'));continue
        seen.add(key)
        cp=c.execute('SELECT id FROM finance_counterparties WHERE tenant_id=? AND identity_key=?',(tenant_id,key[0])).fetchone()
        existing=c.execute('SELECT * FROM invoices WHERE tenant_id=? AND counterparty_id=? AND number_key=?',(tenant_id,cp['id'],key[1])).fetchone() if cp else None
        if not existing:
            changes.append(dict(action='create',after=item));continue
        registered=c.execute('SELECT COALESCE(SUM(amount-reversed_amount),0) AS total FROM payments WHERE tenant_id=? AND invoice_id=?',(tenant_id,existing['id'])).fetchone()['total']
        before=f.view_invoice(existing);target_paid=item.get('paid_amount',0)
        after=dict(item,opening_paid_amount=target_paid-registered)
        first_payment=c.execute('SELECT MIN(paid_on) AS first_date FROM payments WHERE tenant_id=? AND invoice_id=?',(tenant_id,existing['id'])).fetchone()['first_date']
        if target_paid<registered or existing['adjustment_amount'] or (first_payment and item['issued_on']>first_payment):
            changes.append(dict(action='conflict',invoice_id=existing['id'],before=before,after=after,reason='Источник противоречит зарегистрированным оплатам или корректировкам'));continue
        fields=('company','inn','email','number','issued_on','due_on','amount','notes')
        same=all(str(existing[k])==str(item.get(k,'')) for k in fields) and existing['paid_amount']==target_paid
        changes.append(dict(action='skip' if same else 'update',invoice_id=existing['id'],expected_revision=existing['revision'],before=before,after=after))
    return changes


def create_invoice(c,tenant_id,data):
    cp=f.ensure_counterparty(c,tenant_id,data['company'],data.get('inn',''),data.get('email',''))
    if c.execute('SELECT id FROM invoices WHERE tenant_id=? AND counterparty_id=? AND number_key=?',(tenant_id,cp,f.number_key(data['number']))).fetchone():f.fail(409,'Счёт этого контрагента уже существует')
    invoice_id=f.uid();opening=data.get('paid_amount',0)
    c.execute('''INSERT INTO invoices(id,tenant_id,company,inn,email,number,issued_on,due_on,amount,paid_amount,opening_paid_amount,notes,created_at,counterparty_id,number_key)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(invoice_id,tenant_id,data['company'],data.get('inn',''),data.get('email',''),data['number'],str(data['issued_on']),str(data['due_on']),data['amount'],opening,opening,data.get('notes',''),f.timestamp(),cp,f.number_key(data['number'])))
    f.emit(c,tenant_id,invoice_id,'invoice_created','Счёт добавлен','Начальная оплата учтена отдельно от банковских поступлений' if opening else data['number'])
    return f.load_invoice(c,tenant_id,invoice_id)


def attach_import_routes(router,ctx):
    @router.post('/imports/preview')
    def preview(data:CSVInput,user=Depends(ctx.get_user)):
        items,errors=parse_csv(data.content)
        with ctx.database(ctx.config,write=True) as c:
            changes=preview_changes(c,user['tenant_id'],items) if not errors else []
            import_id=f.uid();payload=dict(items=items,errors=errors,changes=changes)
            c.execute('INSERT INTO finance_imports(id,tenant_id,payload_json,created_at,actor_id) VALUES(?,?,?,?,?)',(import_id,user['tenant_id'],json.dumps(payload,ensure_ascii=False),f.timestamp(),user['id']))
            return dict(id=import_id,**payload)
    @router.post('/imports/{import_id}/approve')
    def approve(import_id:str,data:f.ApproveImport,user=Depends(ctx.get_user)):
        with ctx.database(ctx.config,write=True) as c:
            row=c.execute('SELECT * FROM finance_imports WHERE id=? AND tenant_id=?',(import_id,user['tenant_id'])).fetchone()
            if row is None:f.fail(404,'Сверка импорта не найдена')
            if row['result_json']:return json.loads(row['result_json'])
            payload=json.loads(row['payload_json'])
            if payload['errors'] or any(x['action']=='conflict' for x in payload['changes']):f.fail(422,'Исправьте ошибки и конфликты до согласования')
            result=dict(created=0,updated=0,skipped=0)
            for change in payload['changes']:
                item=change['after'];action=change['action']
                if action=='create':
                    create_invoice(c,user['tenant_id'],item);result['created']+=1
                elif action=='skip':result['skipped']+=1
                else:
                    current=f.load_invoice(c,user['tenant_id'],change['invoice_id'])
                    if current['revision']!=change['expected_revision']:f.fail(409,'Счёт изменился после предпросмотра. Выполните сверку заново')
                    c.execute('''UPDATE invoices SET company=?,inn=?,email=?,number=?,number_key=?,issued_on=?,due_on=?,amount=?,opening_paid_amount=?,paid_amount=?,notes=? WHERE id=? AND tenant_id=?''',(item['company'],item.get('inn',''),item.get('email',''),item['number'],f.number_key(item['number']),item['issued_on'],item['due_on'],item['amount'],item['opening_paid_amount'],item['paid_amount'],item.get('notes',''),current['id'],user['tenant_id']))
                    f.bump(c,user['tenant_id'],current['id'],'import_reconciled');f.sync_promises(c,user['tenant_id'],current['id'],item['paid_amount']-current['paid_amount'])
                    f.emit(c,user['tenant_id'],current['id'],'import_reconciled','Изменения источника согласованы',data.reason)
                    result['updated']+=1
            c.execute('UPDATE finance_imports SET result_json=?,approved_at=? WHERE id=? AND tenant_id=?',(json.dumps(result),f.timestamp(),import_id,user['tenant_id']))
            return result
