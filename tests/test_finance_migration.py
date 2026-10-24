"""Real legacy SQL shape to v3 migration, preservation and transactional recovery."""
import sqlite3

import pytest

from server.database import BASE_SCHEMA_SQL, Config, LEGACY_SCHEMA_SQL, SCHEMA_VERSION, initialize


def legacy_database(path,version=2,conflict=False):
    with sqlite3.connect(path) as c:
        c.executescript(LEGACY_SCHEMA_SQL)
        if version==2:
            c.execute('ALTER TABLE messages ADD COLUMN invalidation_reason TEXT')
            c.execute("INSERT INTO schema_version VALUES(2,'2026-10-01')")
            c.execute('PRAGMA user_version=2')
        c.execute("INSERT INTO tenants VALUES('t','Поставщик','2026-10-01')")
        for ident,name,number,paid in [('i1','ООО Берёзка','A-1',40000),('i2','ООО Бере\u0308зка','A-1' if conflict else 'A-2',0)]:
            c.execute("INSERT INTO invoices(id,tenant_id,company,inn,email,number,issued_on,due_on,amount,paid_amount,promise_date,created_at) VALUES(?,'t',?,'7701234567','buyer@example.ru',?,'2026-10-01','2026-10-15',100000,?,'2026-10-28','2026-10-01')",(ident,name,number,paid))
        c.execute("INSERT INTO payments VALUES('p1','t','i1',10000,'2026-10-10','Manual-ref','2026-10-10')")
        c.execute("INSERT INTO events VALUES('e1','t','i1','payment','Сохранить','Детали','2026-10-10')")
        c.execute("INSERT INTO messages(id,tenant_id,invoice_id,subject,body,recipient,status,balance_snapshot,created_at,sent_at) VALUES('m1','t','i1','Сохранить','Историческое письмо','buyer@example.ru','sent',60000,'2026-10-10','2026-10-10')")
        c.execute("INSERT INTO messages(id,tenant_id,invoice_id,subject,body,recipient,status,balance_snapshot,created_at) VALUES('m2','t','i2','Обновить','Черновик','buyer@example.ru','approved',100000,'2026-10-10')")


@pytest.mark.parametrize('version',[1,2])
def test_legacy_migration_preserves_history_and_distinguishes_opening_from_receipts(tmp_path,version):
    path=tmp_path/'legacy.db';legacy_database(path,version)
    initialize(Config(str(path)));initialize(Config(str(path)))
    with sqlite3.connect(path) as c:
        assert c.execute('PRAGMA user_version').fetchone()[0]==SCHEMA_VERSION
        assert c.execute('SELECT count(*) FROM finance_counterparties').fetchone()[0]==1
        assert c.execute("SELECT paid_amount,opening_paid_amount FROM invoices WHERE id='i1'").fetchone()==(40000,30000)
        assert c.execute('SELECT sum(amount+adjustment_amount-paid_amount) FROM invoices').fetchone()[0]==160000
        assert c.execute('SELECT count(*) FROM finance_bank_payments').fetchone()[0]==0
        assert c.execute("SELECT status,body,invalidation_reason FROM messages WHERE id='m1'").fetchone()==('sent','Историческое письмо',None)
        assert c.execute("SELECT status FROM messages WHERE id='m2'").fetchone()[0]=='draft'
        assert c.execute('SELECT count(*) FROM finance_promises').fetchone()[0]==2
        assert c.execute('PRAGMA foreign_key_check').fetchall()==[]


def test_old_identity_conflicts_are_preserved_and_held_for_review(tmp_path):
    path=tmp_path/'duplicate.db';legacy_database(path,conflict=True);initialize(Config(str(path)))
    with sqlite3.connect(path) as c:
        assert c.execute('SELECT count(*) FROM invoices').fetchone()[0]==2
        assert c.execute('SELECT count(*) FROM finance_identity_conflicts').fetchone()[0]==1
        assert c.execute('SELECT hold FROM finance_counterparties').fetchone()[0]==1
        assert c.execute('SELECT count(DISTINCT number_key) FROM invoices').fetchone()[0]==2
        assert c.execute('SELECT count(*) FROM payments').fetchone()[0]==1


def test_v3_failure_rolls_back_entire_rebuild_and_retry_works(tmp_path,monkeypatch):
    from server import finance_migration
    path=tmp_path/'rollback.db';legacy_database(path)
    original=finance_migration.final_schema
    def fail_after_drop(legacy):
        assert sqlite3.connect(path).execute('PRAGMA user_version').fetchone()[0]==2
        raise RuntimeError('Injected failure after transactional DROP')
    monkeypatch.setattr(finance_migration,'final_schema',fail_after_drop)
    with pytest.raises(RuntimeError,match='Injected'):initialize(Config(str(path)))
    with sqlite3.connect(path) as c:
        assert c.execute('PRAGMA user_version').fetchone()[0]==2
        assert c.execute('SELECT count(*) FROM invoices').fetchone()[0]==2
        assert c.execute('SELECT count(*) FROM messages').fetchone()[0]==2
        assert 'counterparty_id' not in {r[1] for r in c.execute('PRAGMA table_info(invoices)')}
    monkeypatch.setattr(finance_migration,'final_schema',original);initialize(Config(str(path)))
    with sqlite3.connect(path) as c:assert c.execute('PRAGMA foreign_key_check').fetchall()==[]


def test_portable_final_schema_has_finance_fields_and_no_sqlite_bootstrap(tmp_path):
    assert 'PRAGMA' not in BASE_SCHEMA_SQL and 'strftime' not in BASE_SCHEMA_SQL
    with sqlite3.connect(tmp_path/'portable.db') as c:
        c.executescript(BASE_SCHEMA_SQL)
        assert {'counterparty_id','revision','opening_paid_amount'} <= {r[1] for r in c.execute('PRAGMA table_info(invoices)')}
        assert 'invalidation_reason' in {r[1] for r in c.execute('PRAGMA table_info(messages)')}
