"""PostgreSQL parity for the temporary free hosted instance."""
import importlib
import os
import uuid
from types import SimpleNamespace

import pytest


def test_parameter_conversion_does_not_touch_quoted_question_marks():
    module = importlib.import_module("server.storage_pg")
    assert module.translate_sql("SELECT '?' AS literal, ? AS value", True) == "SELECT '?' AS literal, %s AS value"
    assert module.translate_sql("SELECT 'it''s ?' AS literal, ?", True) == "SELECT 'it''s ?' AS literal, %s"
    assert module.translate_sql("INSERT OR IGNORE INTO demo(id) VALUES(?)", True) == "INSERT INTO demo(id) VALUES(%s) ON CONFLICT DO NOTHING"


def test_parameter_conversion_escapes_static_percent_and_widens_feature_money():
    module = importlib.import_module("server.storage_pg")
    assert module.translate_sql("SELECT ? WHERE 'abc' LIKE 'a%'", True) == "SELECT %s WHERE 'abc' LIKE 'a%%'"
    assert module.translate_sql("CREATE TABLE money(amount INTEGER, ratio REAL)") == "CREATE TABLE money(amount BIGINT, ratio DOUBLE PRECISION)"


def test_rows_support_sqlite_name_and_numeric_access():
    module = importlib.import_module("server.storage_pg")
    row = module.Record({"id": "one", "amount": 125})
    assert row["amount"] == row[1] == 125
    assert dict(row) == {"id": "one", "amount": 125}
    assert tuple(row) == ("one", 125)


@pytest.fixture
def postgres_config():
    url = os.getenv("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set TEST_POSTGRES_URL for the real PostgreSQL integration tests")
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo
    schema = "audit_" + uuid.uuid4().hex
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    configured = make_conninfo(url, options=f"-csearch_path={schema}")
    try:
        yield SimpleNamespace(database_url=configured)
    finally:
        with psycopg.connect(url, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_real_postgres_transactions_preserve_kopeks_and_rollback(postgres_config):
    module = importlib.import_module("server.storage_pg")
    with module.database(postgres_config, write=True) as connection:
        connection.execute("CREATE TABLE parity(id TEXT PRIMARY KEY, amount BIGINT NOT NULL)")
        connection.execute("INSERT INTO parity VALUES(?,?)", ("one", 1_000_000_000_000_000))
    with pytest.raises(RuntimeError):
        with module.database(postgres_config, write=True) as connection:
            connection.execute("UPDATE parity SET amount=? WHERE id=?", (25, "one"))
            raise RuntimeError("rollback this synthetic transaction")
    with module.database(postgres_config) as connection:
        assert connection.execute("SELECT * FROM parity").fetchone()["amount"] == 1_000_000_000_000_000
        total = connection.execute("SELECT SUM(amount) AS total FROM parity").fetchone()["total"]
        assert type(total) is int and total == 1_000_000_000_000_000


def test_real_postgres_integrity_errors_keep_existing_api_contract(postgres_config):
    import sqlite3
    module = importlib.import_module("server.storage_pg")
    with module.database(postgres_config, write=True) as connection:
        connection.execute("CREATE TABLE parity(id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO parity VALUES(?)", ("one",))
    with pytest.raises(sqlite3.IntegrityError):
        with module.database(postgres_config, write=True) as connection:
            connection.execute("INSERT INTO parity VALUES(?)", ("one",))
    with module.database(postgres_config) as connection:
        assert connection.execute("SELECT count(*) FROM parity").fetchone()[0] == 1


def test_read_transaction_keeps_one_consistent_financial_snapshot(postgres_config):
    module = importlib.import_module('server.storage_pg')
    with module.database(postgres_config, write=True) as connection:
        connection.execute('CREATE TABLE snapshot_test(amount BIGINT)')
        connection.execute('INSERT INTO snapshot_test VALUES(?)',(100,))
    with module.database(postgres_config) as reader:
        assert reader.execute('SELECT amount FROM snapshot_test').fetchone()[0] == 100
        with module.database(postgres_config, write=True) as writer:
            writer.execute('UPDATE snapshot_test SET amount=?',(200,))
        assert reader.execute('SELECT amount FROM snapshot_test').fetchone()[0] == 100


@pytest.fixture
def postgres_client(postgres_config, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setenv("DATABASE_URL", postgres_config.database_url)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "unused.sqlite3"))
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECURE_COOKIES", "false")
    for key in ("APP_URL", "RENDER_EXTERNAL_URL", "SMTP_HOST", "YANDEX_API_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.delenv(key, raising=False)
    module = importlib.import_module("server.main")
    with TestClient(module.create_app()) as client:
        result = client.post("/api/auth/register", json={"name":"Финансист", "company":"Поставщик", "email":"postgres@example.ru", "password":"Postgres-test-2026!"})
        assert result.status_code == 201, result.text
        client.headers["X-CSRF-Token"] = result.json()["csrf_token"]
        yield client


def test_real_postgres_receivables_import_bank_reversal_and_calculation(postgres_client):
    c = postgres_client
    source = "контрагент;инн;номер;дата;срок;сумма;оплачено;остаток\nООО Покупатель;7701234567;PG-1;01.08.2026;01.09.2026;1000;200;800\n"
    response = c.post("/api/finance/imports/preview", json={"content":source})
    assert response.status_code == 200, response.text
    preview = response.json()
    assert c.post(f"/api/finance/imports/{preview['id']}/approve", json={"reason":"Сверено с бухгалтерией"}).status_code == 200
    item = c.get("/api/invoices").json()["items"][0]
    second = c.post("/api/finance/imports/preview", json={"content":source.replace(";200;800", ";300;700")})
    assert second.status_code == 200, second.text
    assert c.post(f"/api/finance/imports/{second.json()['id']}/approve", json={"reason":"Новая выгрузка"}).status_code == 200
    response = c.post("/api/finance/bank-payments", json={"external_id":"PG-BANK-1","amount":50000,"paid_on":"2026-10-24","reference":"ПП PG-1","evidence":"Подтверждено выпиской","confirmed":True})
    assert response.status_code == 201, response.text
    bank = response.json()
    response = c.post(f"/api/finance/bank-payments/{bank['id']}/allocate", json={"invoice_id":item['id'],"amount":40000,"idempotency_key":"pg-allocate"})
    assert response.status_code == 200, response.text
    allocation = response.json()
    assert allocation['invoice']['balance'] == 30000
    response = c.post(f"/api/finance/payments/{allocation['payment']['id']}/reverse", json={"amount":10000,"kind":"correction","reason":"Исправлено разнесение","idempotency_key":"pg-reverse"})
    assert response.status_code == 200, response.text
    assert response.json()['invoice']['balance'] == 40000
    response = c.post("/api/legal/calculations", json={"invoice_id":item['id'],"through_on":"2026-10-24","sanction":"none"})
    assert response.status_code == 200, response.text
    assert response.json()['principal_amount'] == 40000
    assert c.get('/api/overview').json()['collected_amount'] == 30000


def test_real_postgres_agent_checkpoint_survives_app_recreation(postgres_client, monkeypatch):
    from fastapi.testclient import TestClient
    from datetime import timedelta
    from server.business_time import business_today
    agent = importlib.import_module("server.agent")
    due = str(business_today() + timedelta(days=2))
    text = f"Оплатим 300 рублей {due}."
    monkeypatch.setattr(agent, "extract_yandex", lambda *args, **kwargs: {
        "payload":{"intent":"promise","amount_kopeks":30000,"due_date":due,"currency":"RUB","ambiguous":False,
            "evidence":[{"field":"intent","quote":"Оплатим"},{"field":"amount","quote":"300 рублей"},{"field":"due_date","quote":due}]},
        "error":None,"usage":{},"latency_ms":1,"trace_id":None})
    c = postgres_client
    item = c.post('/api/invoices', json={"company":"ООО Покупатель","inn":"7701234567","email":"ap@example.ru","number":"PG-AGENT","issued_on":"2026-08-01","due_on":"2026-09-01","amount":100000}).json()
    assert c.patch(f"/api/finance/counterparties/{item['counterparty_id']}",json={"agent_promises_allowed":True}).status_code == 200
    response = c.post('/api/agent/ingest',json={"invoice_id":item['id'],"text":text,"idempotency_key":"pg-agent-event"})
    assert response.status_code == 201, response.text
    proposal = response.json()
    assert proposal['status'] == 'review_required'
    main = importlib.import_module('server.main')
    with TestClient(main.create_app()) as resumed:
        logged = resumed.post('/api/auth/login',json={"email":"postgres@example.ru","password":"Postgres-test-2026!"})
        assert logged.status_code == 200
        resumed.headers['X-CSRF-Token'] = logged.json()['csrf_token']
        response = resumed.post(f"/api/agent/proposals/{proposal['id']}/review",json={"decision":"approve"})
        assert response.status_code == 200, response.text
        assert response.json()['status'] == 'executed'
        assert resumed.post(f"/api/agent/proposals/{proposal['id']}/review",json={"decision":"approve"}).json()['status'] == 'executed'
        summary = resumed.get('/api/overview').json()
        assert summary['promised_amount'] == 30000 and summary['total_outstanding'] == 100000


@pytest.mark.parametrize('statement',[
    'CREATE VIEW archive_existing_view AS SELECT 1 AS value',
    'CREATE SEQUENCE archive_existing_sequence',
    "CREATE FUNCTION archive_existing_function() RETURNS integer LANGUAGE SQL AS 'SELECT 1'",
    "CREATE TYPE archive_existing_type AS ENUM ('existing')",
])
def test_restore_rejects_non_table_user_objects(postgres_config, statement):
    import psycopg
    from scripts.postgres_backup import ensure_empty_target
    with psycopg.connect(postgres_config.database_url) as connection:
        connection.execute(statement)
        with pytest.raises(ValueError,match='empty database'):
            ensure_empty_target(connection)


def test_restore_does_not_mistake_pg_prefix_for_reserved_pg_underscore(postgres_config):
    import psycopg
    from psycopg import sql
    from scripts.postgres_backup import ensure_empty_target
    name='pgagent'+uuid.uuid4().hex
    with psycopg.connect(postgres_config.database_url) as connection:
        connection.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(name)))
        connection.execute(sql.SQL('CREATE FUNCTION {}.existing() RETURNS integer LANGUAGE SQL AS \'SELECT 1\'').format(sql.Identifier(name)))
        with pytest.raises(ValueError,match='empty database'):
            ensure_empty_target(connection)
        connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(name)))
