"""Independent real-workflow audit. SMTP is captured locally; no real data/keys."""
import importlib
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.business_time import business_today


@pytest.fixture
def audit_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "audit.sqlite3"))
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECURE_COOKIES", "false")
    monkeypatch.setenv("APP_TIMEZONE", "Europe/Moscow")
    for name in ("APP_URL", "RENDER_EXTERNAL_URL", "SMTP_HOST", "SMTP_FROM", "SMTP_TENANT_ID", "SMTP_USER", "SMTP_PASSWORD", "YANDEX_API_KEY", "YANDEX_MODEL"):
        monkeypatch.delenv(name, raising=False)
    application = importlib.import_module("server.main").create_app()
    with TestClient(application, raise_server_exceptions=False) as client:
        result = client.post("/api/auth/register", json={"name": "Аудитор", "company": "ООО Поставщик", "email": "audit@example.ru", "password": "Independent-audit-2026!"})
        assert result.status_code == 201
        client.headers["X-CSRF-Token"] = result.json()["csrf_token"]
        yield client


def add_debt(client, **changes):
    fields = {"company": "ООО Покупатель", "inn": "7701234567", "email": "buyer@example.ru", "number": "П-001", "issued_on": str(business_today() - timedelta(days=40)), "due_on": str(business_today() - timedelta(days=10)), "amount": 150025, "notes": "Поставка товара"}
    fields.update(changes)
    response = client.post("/api/invoices", json=fields)
    assert response.status_code == 201, response.text
    return response.json()


def draft_and_approve(client, invoice_id):
    response = client.post(f"/api/invoices/{invoice_id}/draft", json={"tone": "soft"})
    assert response.status_code == 201, response.text
    message = response.json()
    assert client.post(f"/api/messages/{message['id']}/approve").status_code == 200
    return message


@pytest.fixture
def mail_capture(audit_client, monkeypatch):
    module = importlib.import_module("server.main")
    state = {"deliveries": [], "quit_failure": False, "data_timeout": False, "attempts": 0}
    with sqlite3.connect(audit_client.app.state.config.database_path) as connection:
        tenant_id = connection.execute("SELECT tenant_id FROM users").fetchone()[0]
    monkeypatch.setenv("SMTP_HOST", "isolated-mail.invalid")
    monkeypatch.setenv("SMTP_FROM", "finance@example.ru")
    monkeypatch.setenv("SMTP_TENANT_ID", tenant_id)
    monkeypatch.setenv("SMTP_USE_TLS", "false")
    monkeypatch.setenv("SMTP_USE_SSL", "false")

    class CapturedSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            if state["quit_failure"]:
                raise module.smtplib.SMTPResponseException(500, b"QUIT unavailable after accepted DATA")

        def send_message(self, message):
            state["attempts"] += 1
            if state["data_timeout"]:
                raise TimeoutError("Timeout before a positive SMTP DATA acknowledgement")
            state["deliveries"].append({"recipient": message["To"], "reply_to": message["Reply-To"], "sender": message["From"], "body": message.get_content()})
            return {}

    monkeypatch.setattr(module.smtplib, "SMTP", CapturedSMTP)
    monkeypatch.setattr(module.smtplib, "SMTP_SSL", CapturedSMTP)
    return state


def test_changed_bank_details_cannot_send_previously_approved_old_requisites(audit_client, mail_capture):
    assert audit_client.patch("/api/settings", json={"bank_details": "Старые реквизиты — счёт OLD-ACCOUNT"}).status_code == 200
    invoice = add_debt(audit_client)
    message = draft_and_approve(audit_client, invoice["id"])
    assert "OLD-ACCOUNT" in message["body"]
    assert audit_client.patch("/api/settings", json={"bank_details": "Исправленные реквизиты — счёт NEW-ACCOUNT"}).status_code == 200
    sent = audit_client.post(f"/api/messages/{message['id']}/send")
    assert sent.status_code == 409, "Approved draft with obsolete bank details was sent"
    assert mail_capture["deliveries"] == []
    assert audit_client.post(f"/api/messages/{message['id']}/approve").status_code == 409
    edited = audit_client.patch(f"/api/messages/{message['id']}", json={"subject": message["subject"], "body": "Проверенный вручную текст"})
    assert edited.status_code in (200, 409)
    assert audit_client.post(f"/api/messages/{message['id']}/approve").status_code == 409
    fresh = draft_and_approve(audit_client, invoice["id"])
    assert "NEW-ACCOUNT" in fresh["body"] and "OLD-ACCOUNT" not in fresh["body"]
    assert audit_client.post(f"/api/messages/{fresh['id']}/send").status_code == 200


@pytest.mark.parametrize("setting,value", [("company", "ООО Новая подпись"), ("sender_name", "Новый ответственный"), ("reply_to", "new-finance@example.ru")])
def test_changed_sender_identity_cannot_mutate_approved_outgoing_mail(audit_client, mail_capture, setting, value):
    invoice = add_debt(audit_client)
    message = draft_and_approve(audit_client, invoice["id"])
    assert audit_client.patch("/api/settings", json={setting: value}).status_code == 200
    sent = audit_client.post(f"/api/messages/{message['id']}/send")
    assert sent.status_code == 409, "Outgoing identity changed after approval without renewed review"
    assert mail_capture["deliveries"] == []


def test_smtp_quit_failure_does_not_undo_confirmed_data_acceptance(audit_client, mail_capture):
    invoice = add_debt(audit_client)
    message = draft_and_approve(audit_client, invoice["id"])
    mail_capture["quit_failure"] = True
    sent = audit_client.post(f"/api/messages/{message['id']}/send")
    assert len(mail_capture["deliveries"]) == 1, "SMTP DATA was accepted before QUIT failed"
    assert sent.status_code == 200 and sent.json()["status"] == "sent", "Successful DATA delivery was incorrectly marked retryable"
    assert audit_client.post(f"/api/messages/{message['id']}/approve").status_code == 409
    assert audit_client.post(f"/api/messages/{message['id']}/send").status_code == 409
    assert len(mail_capture["deliveries"]) == 1
    detail = audit_client.get(f"/api/invoices/{invoice['id']}").json()
    assert sum(event["type"] == "message_sent" for event in detail["events"]) == 1


def test_timeout_before_smtp_data_acknowledgement_stays_failed_without_auto_retry(audit_client, mail_capture):
    invoice = add_debt(audit_client)
    message = draft_and_approve(audit_client, invoice["id"])
    mail_capture["data_timeout"] = True
    sent = audit_client.post(f"/api/messages/{message['id']}/send")
    assert sent.status_code == 502
    detail = audit_client.get(f"/api/invoices/{invoice['id']}").json()
    assert detail["messages"][0]["status"] == "failed"
    assert not any(event["type"] == "message_sent" for event in detail["events"])
    assert mail_capture["attempts"] == 1
    assert audit_client.post(f"/api/messages/{message['id']}/send").status_code == 409
    assert mail_capture["attempts"] == 1


def test_only_actual_identity_changes_invalidate_unsent_approvals_and_sent_history_is_immutable(audit_client, mail_capture):
    first = add_debt(audit_client)
    sent_message = draft_and_approve(audit_client, first["id"])
    assert audit_client.post(f"/api/messages/{sent_message['id']}/send").status_code == 200
    second = add_debt(audit_client, number="П-002")
    untouched = draft_and_approve(audit_client, second["id"])
    settings = audit_client.get("/api/settings").json()
    harmless = {"annual_rate": 25, "cooldown_days": 5, "sender_name": settings["sender_name"], "reply_to": settings["reply_to"], "bank_details": settings["bank_details"], "company": settings["company"]}
    assert audit_client.patch("/api/settings", json=harmless).status_code == 200
    assert audit_client.get(f"/api/invoices/{second['id']}").json()["messages"][0]["status"] == "approved"
    assert audit_client.patch("/api/settings", json={"sender_name": "Другой сотрудник"}).status_code == 200
    assert audit_client.get(f"/api/invoices/{second['id']}").json()["messages"][0]["status"] == "draft"
    historic = audit_client.get(f"/api/invoices/{first['id']}").json()["messages"][0]
    assert historic["status"] == "sent" and historic["body"] == sent_message["body"]
    assert audit_client.patch(f"/api/messages/{sent_message['id']}", json={"subject": "Новый", "body": "Новый текст"}).status_code == 409


def legacy_v1_copy(client, target):
    """Produce the real v1 shape from a disposable fixture, never a working DB."""
    from server.database import LEGACY_SCHEMA_SQL
    with sqlite3.connect(client.app.state.config.database_path) as source:
        source.row_factory = sqlite3.Row
        with sqlite3.connect(target) as saved:
            saved.executescript(LEGACY_SCHEMA_SQL)
            for table in ("tenants", "users", "sessions", "settings", "invoices", "events", "messages", "payments"):
                columns = [row[1] for row in saved.execute("PRAGMA table_info(" + table + ")")]
                for row in source.execute("SELECT * FROM " + table):
                    saved.execute("INSERT INTO " + table + "(" + ",".join(columns) + ") VALUES(" + ",".join("?" for _ in columns) + ")", tuple(row[k] for k in columns))
    return target


def test_v1_migration_preserves_finances_and_sent_history_but_requires_new_legacy_drafts(audit_client, tmp_path):
    from server.database import Config, initialize

    first = add_debt(audit_client)
    assert pay(audit_client, first["id"], 25025, "PRE-MIGRATION-PAYMENT").status_code == 200
    old_approved = draft_and_approve(audit_client, first["id"])
    second = add_debt(audit_client, number="П-002")
    old_sent = draft_and_approve(audit_client, second["id"])
    with sqlite3.connect(audit_client.app.state.config.database_path) as connection:
        connection.execute("UPDATE messages SET status='sent',sent_at='2026-10-24T00:00:00+00:00' WHERE id=?", (old_sent["id"],))
    path = legacy_v1_copy(audit_client, tmp_path / "legacy.db")
    initialize(Config(str(path)))
    initialize(Config(str(path)))  # Additive migration must be idempotent.
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        assert connection.execute("SELECT count(*) FROM schema_version WHERE version=2").fetchone()[0] == 1
        stale = connection.execute("SELECT * FROM messages WHERE id=?", (old_approved["id"],)).fetchone()
        assert stale["status"] == "draft" and stale["invalidation_reason"]
        historical = connection.execute("SELECT * FROM messages WHERE id=?", (old_sent["id"],)).fetchone()
        assert historical["status"] == "sent" and historical["body"] == old_sent["body"] and historical["invalidation_reason"] is None
        assert connection.execute("SELECT sum(amount-paid_amount) FROM invoices").fetchone()[0] == 275025
        assert connection.execute("SELECT sum(amount) FROM payments").fetchone()[0] == 25025


def test_restore_accepts_v1_backup_then_startup_migrates_to_current_schema(audit_client, tmp_path):
    from scripts.backup import backup_database
    from scripts.restore import restore_database
    from server.database import Config, initialize

    invoice = add_debt(audit_client)
    assert pay(audit_client, invoice["id"], 25025, "BEFORE-BACKUP").status_code == 200
    legacy = legacy_v1_copy(audit_client, tmp_path / "legacy-source.db")
    snapshot, restored = tmp_path / "v1-backup.db", tmp_path / "restored.db"
    backup_database(legacy, snapshot)
    assert restore_database(snapshot, restored) is None
    initialize(Config(str(restored)))
    with sqlite3.connect(restored) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        assert connection.execute("SELECT sum(amount-paid_amount) FROM invoices").fetchone()[0] == 125000
        assert connection.execute("SELECT count(*) FROM payments").fetchone()[0] == 1


def test_restore_accepts_current_v3_backup_without_rewriting_history(audit_client, tmp_path):
    from scripts.backup import backup_database
    from scripts.restore import restore_database
    from server.database import Config, initialize

    invoice = add_debt(audit_client)
    approved = draft_and_approve(audit_client, invoice["id"])
    snapshot, restored = tmp_path / "v2-backup.db", tmp_path / "restored-v2.db"
    backup_database(Path(audit_client.app.state.config.database_path), snapshot)
    assert restore_database(snapshot, restored) is None
    initialize(Config(str(restored)))
    with sqlite3.connect(restored) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        assert connection.execute("SELECT sum(amount-paid_amount) FROM invoices").fetchone()[0] == 150025
        restored_message = connection.execute("SELECT status,body,invalidation_reason FROM messages WHERE id=?", (approved["id"],)).fetchone()
        assert restored_message == ("approved", approved["body"], None)


def pay(client, invoice_id, amount, reference):
    return client.post(f"/api/invoices/{invoice_id}/payments", json={"amount": amount, "paid_on": str(business_today()), "reference": reference})


def test_split_bank_payment_across_invoices_is_counted_once_per_allocation(audit_client):
    first = add_debt(audit_client, amount=10000)
    second = add_debt(audit_client, number="П-002", amount=20000)
    assert pay(audit_client, first["id"], 5000, "БАНК-001").status_code == 200
    assert pay(audit_client, second["id"], 12000, "БАНК-001").status_code == 200
    assert pay(audit_client, first["id"], 5000, "БАНК-001").json()["balance"] == 5000
    assert pay(audit_client, first["id"], 5001, "БАНК-002").status_code == 422
    overview = audit_client.get("/api/overview").json()
    assert overview["collected_amount"] == 17000 and overview["total_outstanding"] == 13000
    assert sum(item["amount"] for item in overview["aging"]) == 13000
    assert pay(audit_client, first["id"], 5000, "БАНК-002").json()["status"] == "paid"
    assert pay(audit_client, second["id"], 8000, "БАНК-002").json()["status"] == "paid"
    overview = audit_client.get("/api/overview").json()
    assert overview["collected_amount"] == 30000 and overview["total_outstanding"] == 0


def test_concurrent_identical_full_payment_is_one_entry_and_retry_after_closure_is_idempotent(audit_client):
    invoice = add_debt(audit_client, amount=1000)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: pay(audit_client, invoice["id"], 1000, "ONE-BANK-ENTRY").status_code, range(2)))
    assert results == [200, 200]
    assert pay(audit_client, invoice["id"], 1000, "ONE-BANK-ENTRY").status_code == 200
    detail = audit_client.get(f"/api/invoices/{invoice['id']}").json()
    assert detail["invoice"]["status"] == "paid" and detail["invoice"]["balance"] == 0
    assert len(detail["payments"]) == 1
    assert sum(event["type"] == "payment_recorded" for event in detail["events"]) == 1


@pytest.mark.parametrize("value", [-1, 0, True, 0.01])
def test_unsupported_refund_or_fractional_kopeks_cannot_corrupt_the_ledger(audit_client, value):
    invoice = add_debt(audit_client, amount=1000)
    assert pay(audit_client, invoice["id"], 100, "VALID").status_code == 200
    assert pay(audit_client, invoice["id"], value, "INVALID").status_code == 422
    detail = audit_client.get(f"/api/invoices/{invoice['id']}").json()
    assert detail["invoice"]["paid_amount"] == 100 and len(detail["payments"]) == 1


def test_stale_draft_edit_cannot_reapprove_an_obsolete_balance_and_sent_text_is_immutable(audit_client, mail_capture):
    invoice = add_debt(audit_client, amount=1000)
    old = draft_and_approve(audit_client, invoice["id"])
    assert pay(audit_client, invoice["id"], 100, "PARTIAL").status_code == 200
    edited = audit_client.patch(f"/api/messages/{old['id']}", json={"subject": "Обновлено", "body": "Остаток 9 рублей, проверено вручную"})
    assert edited.status_code == 409
    assert audit_client.post(f"/api/messages/{old['id']}/approve").status_code == 409
    fresh = draft_and_approve(audit_client, invoice["id"])
    assert "9,00" in fresh["body"]
    assert audit_client.post(f"/api/messages/{fresh['id']}/send").status_code == 200
    assert audit_client.patch(f"/api/messages/{fresh['id']}", json={"subject": "Из другой вкладки", "body": "Старый несохранённый текст"}).status_code == 409
    detail = audit_client.get(f"/api/invoices/{invoice['id']}").json()
    sent = next(item for item in detail["messages"] if item["id"] == fresh["id"])
    assert sent["status"] == "sent" and sent["body"] == fresh["body"]


def test_future_promise_pause_dispute_and_full_payment_do_not_reopen_closed_debt(audit_client):
    invoice = add_debt(audit_client, amount=1000)
    prefix = f"/api/invoices/{invoice['id']}"
    future = str(business_today() + timedelta(days=5))
    assert audit_client.post(prefix + "/promise", json={"date": future}).json()["status"] == "promised"
    assert audit_client.post(prefix + "/status", json={"status": "paused"}).json()["promise_date"] == future
    assert audit_client.post(prefix + "/draft", json={"tone": "soft"}).status_code == 409
    reopened = audit_client.post(prefix + "/status", json={"status": "open"}).json()
    assert reopened["status"] == "promised" and reopened["promise_date"] == future
    assert audit_client.post(prefix + "/status", json={"status": "disputed"}).status_code == 200
    assert audit_client.post(prefix + "/promise", json={"date": future}).status_code == 409
    assert pay(audit_client, invoice["id"], 1000, "CLOSED").json()["status"] == "paid"
    assert audit_client.post(prefix + "/promise", json={"date": future}).status_code == 409
    assert audit_client.post(prefix + "/status", json={"status": "open"}).status_code == 409
    assert audit_client.post(prefix + "/draft", json={"tone": "soft"}).status_code == 409
    assert audit_client.get("/api/overview").json()["promised_amount"] == 0


def test_concurrent_csv_commits_cannot_duplicate_the_same_invoice(audit_client):
    content = "контрагент;инн;email;номер;дата;срок;сумма\nООО Покупатель;7701234567;buyer@example.ru;CSV-001;01.10.2026;15.10.2026;1234,56\n"
    def commit(_):
        response = audit_client.post("/api/invoices/import", json={"content": content})
        assert response.status_code == 200
        return response.json()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(commit, range(2)))
    assert sorted((item["imported"], item["skipped"]) for item in results) == [(0, 1), (1, 0)]
    assert audit_client.get("/api/overview").json()["total_outstanding"] == 123456


def test_csv_unicode_spaces_and_quoted_notes_preserve_exact_money_and_text(audit_client):
    content = '\ufeffконтрагент;инн;email;номер;дата;срок;сумма;примечание\nООО Берёзка;7701234567;buyer@example.ru;Ю-001;01.10.2026;15.10.2026;1\u202f234,56;"Условия; строка\nпродолжение"\n'
    preview = audit_client.post("/api/invoices/import/preview", json={"content": content}).json()
    assert preview["errors"] == [] and preview["items"][0]["amount"] == 123456
    assert audit_client.post("/api/invoices/import", json={"content": content}).json() == {"imported": 1, "skipped": 0}
    item = audit_client.get("/api/invoices").json()["items"][0]
    assert item["notes"] == "Условия; строка\nпродолжение" and item["company"] == "ООО Берёзка"


def test_mixed_csv_with_invalid_precision_or_unicode_contact_is_all_or_nothing(audit_client):
    header = "company,number,issued_on,due_on,amount,email\n"
    good = "North,A-1,2026-10-01,2026-10-15,100.00,buyer@example.ru\n"
    for bad in ("South,A-2,2026-10-01,2026-10-15,0.001,buyer@example.ru\n", "South,A-2,2026-10-01,2026-10-15,100.00,контакт@example.ru\n"):
        content = header + good + bad
        assert audit_client.post("/api/invoices/import/preview", json={"content": content}).json()["errors"]
        assert audit_client.post("/api/invoices/import", json={"content": content}).status_code == 422
        assert audit_client.get("/api/invoices").json()["items"] == []


def test_stable_inn_identity_rejects_alias_duplicates_and_allows_different_legal_entities(audit_client):
    original = add_debt(audit_client, company="ООО Берёзка")
    fields = {k: original[k] for k in ("company", "inn", "email", "number", "issued_on", "due_on", "amount")}
    assert audit_client.post("/api/invoices", json={**fields, "company": "ООО Бере\u0308зка"}).status_code == 409
    distinct = audit_client.post("/api/invoices", json={**fields, "inn": "7801234567"})
    assert distinct.status_code == 201
    assert distinct.json()["counterparty_id"] != original["counterparty_id"]
    assert audit_client.get("/api/overview").json()["total_outstanding"] == 300050


def test_cooldown_spans_counterparty_invoices_and_shared_mailbox(audit_client, mail_capture):
    first = add_debt(audit_client)
    second = add_debt(audit_client, number="П-002")
    message = draft_and_approve(audit_client, first["id"])
    assert audit_client.post(f"/api/messages/{message['id']}/send").status_code == 200
    other = draft_and_approve(audit_client, second["id"])
    assert audit_client.post(f"/api/messages/{other['id']}/send").status_code == 409
    assert len(mail_capture["deliveries"]) == 1


@pytest.mark.parametrize("header,expected_paid", [("Оплачено, руб.", 40000), ("Остаток (руб.)", 60000), ("Paid Amount", 40000)])
def test_accounting_headers_with_units_preserve_opening_payment_and_exact_balance(audit_client, header, expected_paid):
    content = f"контрагент;номер;дата;срок;сумма;{header}\nПокупатель;F-001;01.10.2026;15.10.2026;1000;400\n"
    preview = audit_client.post("/api/invoices/import/preview", json={"content": content}).json()
    assert not preview["errors"] and preview["items"][0]["paid_amount"] == expected_paid
    assert audit_client.post("/api/invoices/import", json={"content": content}).status_code == 200
    item = audit_client.get("/api/invoices").json()["items"][0]
    assert item["balance"] == 100000 - expected_paid
    assert audit_client.get("/api/overview").json()["collected_amount"] == 0


def test_two_fresh_startups_cannot_downgrade_schema_or_repeat_column_migration(tmp_path, monkeypatch):
    from server.database import Config, initialize

    target = tmp_path / "concurrent-fresh.db"
    # An empty WAL database still has schema version zero. Pre-setting WAL keeps
    # this test focused on the schema-read race rather than journal negotiation.
    with sqlite3.connect(target) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
    both_read_zero = threading.Barrier(2)
    first_finished = threading.Event()
    role = threading.local()
    original_connect = sqlite3.connect

    class CachedRow:
        def __init__(self, row):
            self.row = row

        def fetchone(self):
            return self.row

    class InterleavedConnection(sqlite3.Connection):
        def execute(self, statement, parameters=()):
            cursor = super().execute(statement, parameters)
            if statement.strip().upper() == "PRAGMA USER_VERSION" and not self.in_transaction:
                row = cursor.fetchone()
                if row[0] == 0:
                    # Force the vulnerable interleaving only if the version was
                    # read outside a transaction. A correctly locked read needs
                    # no artificial scheduling and proceeds normally.
                    both_read_zero.wait(timeout=5)
                    if role.value == "second":
                        assert first_finished.wait(timeout=5)
                return CachedRow(row)
            return cursor

    def gated_connect(*args, **kwargs):
        return original_connect(*args, **kwargs, factory=InterleavedConnection)

    monkeypatch.setattr(sqlite3, "connect", gated_connect)

    def start(name):
        role.value = name
        try:
            initialize(Config(str(target)))
        finally:
            if name == "first":
                first_finished.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(start, ("first", "second")))
    with original_connect(target) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        assert connection.execute("SELECT count(*) FROM schema_version WHERE version=2").fetchone()[0] == 1


def test_bootstrap_retries_a_transient_wal_negotiation_lock(tmp_path, monkeypatch):
    from server.database import Config, initialize

    original_connect = sqlite3.connect

    class BusyOnceConnection(sqlite3.Connection):
        wal_attempts = 0

        def execute(self, statement, parameters=()):
            if statement.strip().upper() == "PRAGMA JOURNAL_MODE = WAL":
                self.wal_attempts += 1
                if self.wal_attempts == 1:
                    error = sqlite3.OperationalError("database is locked")
                    error.sqlite_errorcode = sqlite3.SQLITE_BUSY
                    raise error
            return super().execute(statement, parameters)

    monkeypatch.setattr(sqlite3, "connect", lambda *args, **kwargs: original_connect(*args, **kwargs, factory=BusyOnceConnection))
    target = tmp_path / "transient-wal.db"
    initialize(Config(str(target)))
    with original_connect(target) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3


def test_real_parallel_fresh_file_startups_end_in_one_current_wal_schema(tmp_path):
    from server.database import Config, initialize

    for iteration in range(10):
        target = tmp_path / f"fresh-{iteration}.db"
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: initialize(Config(str(target))), range(2)))
        with sqlite3.connect(target) as connection:
            assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
            assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
