"""SQLite-only v3 rebuild. Portable final DDL is also exported for PostgreSQL."""
import re
from . import finance as f

INVOICE_DDL="""CREATE TABLE IF NOT EXISTS invoices (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL REFERENCES tenants(id),company TEXT NOT NULL,
 inn TEXT NOT NULL DEFAULT '',email TEXT NOT NULL DEFAULT '',number TEXT NOT NULL,number_key TEXT NOT NULL,
 counterparty_id TEXT NOT NULL,issued_on TEXT NOT NULL,due_on TEXT NOT NULL,amount INTEGER NOT NULL CHECK(amount>0),
 paid_amount INTEGER NOT NULL DEFAULT 0 CHECK(paid_amount>=0),opening_paid_amount INTEGER NOT NULL DEFAULT 0 CHECK(opening_paid_amount>=0),
 adjustment_amount INTEGER NOT NULL DEFAULT 0,promised_amount INTEGER NOT NULL DEFAULT 0,revision INTEGER NOT NULL DEFAULT 1,
 status TEXT NOT NULL DEFAULT 'open' CHECK(status IN('open','disputed','paused')),promise_date TEXT,notes TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,
 UNIQUE(tenant_id,counterparty_id,number_key),UNIQUE(id,tenant_id),
 FOREIGN KEY(counterparty_id,tenant_id) REFERENCES finance_counterparties(id,tenant_id),
 CHECK(amount+adjustment_amount>=paid_amount)
);"""
PAYMENT_DDL="""CREATE TABLE IF NOT EXISTS payments (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL REFERENCES tenants(id),invoice_id TEXT NOT NULL,
 amount INTEGER NOT NULL CHECK(amount>0),paid_on TEXT NOT NULL,reference TEXT NOT NULL,created_at TEXT NOT NULL,
 bank_payment_id TEXT,reversed_amount INTEGER NOT NULL DEFAULT 0 CHECK(reversed_amount>=0 AND reversed_amount<=amount),
 UNIQUE(tenant_id,invoice_id,reference),FOREIGN KEY(invoice_id,tenant_id) REFERENCES invoices(id,tenant_id) ON DELETE CASCADE,
 FOREIGN KEY(bank_payment_id,tenant_id) REFERENCES finance_bank_payments(id,tenant_id)
);"""

def final_schema(legacy):
    sql=re.sub(r"\s*INSERT OR IGNORE INTO schema_version.*?;",'',legacy,flags=re.S)
    sql=re.sub(r'\s*PRAGMA user_version\s*=\s*1;','',sql)
    sql=re.sub(r'CREATE TABLE IF NOT EXISTS invoices \(.*?\n\s*\);',lambda _:f.COUNTERPARTY_SCHEMA+INVOICE_DDL,sql,flags=re.S)
    sql=re.sub(r'CREATE TABLE IF NOT EXISTS payments \(.*?\n\s*\);',lambda _:PAYMENT_DDL,sql,flags=re.S)
    sql=sql.replace('source TEXT NOT NULL DEFAULT \'template\', balance_snapshot INTEGER NOT NULL,','source TEXT NOT NULL DEFAULT \'template\', balance_snapshot INTEGER NOT NULL, invalidation_reason TEXT,')
    return sql+f.SCHEMA_SQL


def migrate_v3(c,legacy):
    c.row_factory=__import__('sqlite3').Row
    f.initialize_schema(c)
    invoices=[dict(row) for row in c.execute('SELECT * FROM invoices')]
    children={table:[dict(row) for row in c.execute('SELECT * FROM '+table)] for table in ('events','messages','payments')}
    seen={}
    for inv in invoices:
        cp=f.ensure_counterparty(c,inv['tenant_id'],inv['company'],inv['inn'],inv['email'])
        key=(inv['tenant_id'],cp,f.number_key(inv['number']))
        normalized=key[2]
        if key in seen:
            c.execute('INSERT INTO finance_identity_conflicts VALUES(?,?,?,?,?,?)',(f.uid(),inv['tenant_id'],inv['id'],seen[key],'Повтор счета одного юрлица в старом реестре',f.timestamp()))
            c.execute('UPDATE finance_counterparties SET hold=1,hold_reason=? WHERE id=?',('Дубликаты исходного реестра: требуется ручная сверка',cp))
            normalized+=' #legacy-conflict:'+inv['id']
        else:seen[key]=inv['id']
        paid=sum(row['amount'] for row in children['payments'] if row['invoice_id']==inv['id'] and row['tenant_id']==inv['tenant_id'])
        inv.update(counterparty_id=cp,number_key=normalized,opening_paid_amount=max(0,inv['paid_amount']-paid),adjustment_amount=0,revision=1,promised_amount=(inv['amount']-inv['paid_amount']) if inv['promise_date'] else 0)
    # Drop the three old dependants first so SQLite ON DELETE CASCADE cannot
    # delete history while rebuilding the parent to replace its unique key.
    for table in ('events','messages','payments','invoices'):c.execute('DROP TABLE '+table)
    for statement in final_schema(legacy).split(';'):
        if statement.strip():c.execute(statement)
    def insert(table,row):
        columns=list(row)
        c.execute('INSERT INTO '+table+'('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',tuple(row[k] for k in columns))
    for row in invoices:insert('invoices',row)
    for table in ('events','messages','payments'):
        for row in children[table]:
            if table=='messages' and row['status']!='sent':row.update(status='draft',invalidation_reason=row.get('invalidation_reason') or 'ledger_migrated')
            insert(table,row)
    for inv in invoices:
        if inv['promised_amount']>0:
            promise=f.uid()
            c.execute('INSERT INTO finance_promises(id,tenant_id,invoice_id,amount,due_on,source_key,actor_id,created_at) VALUES(?,?,?,?,?,?,?,?)',(promise,inv['tenant_id'],inv['id'],inv['promised_amount'],inv['promise_date'],'legacy:'+inv['id'],'migration',f.timestamp()))
            c.execute('INSERT INTO finance_installments(id,promise_id,due_on,amount) VALUES(?,?,?,?)',(f.uid(),promise,inv['promise_date'],inv['promised_amount']))
    c.execute('INSERT INTO schema_version(version,applied_at) VALUES(3,?)',(f.timestamp(),))
    c.execute('PRAGMA user_version=3')
