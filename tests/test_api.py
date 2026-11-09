"""HTTP integration tests for the complete receivables lifecycle."""
import csv
import importlib
import io
import sqlite3
import socketserver
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from server.business_time import business_today


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "mandato.sqlite3"))
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECURE_COOKIES", "false")
    monkeypatch.setenv("APP_TIMEZONE", "Europe/Moscow")
    monkeypatch.delenv("APP_URL", raising=False)
    for name in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM", "SMTP_TENANT_ID", "YANDEX_API_KEY", "YANDEX_MODEL"):
        monkeypatch.delenv(name, raising=False)
    assert (Path(__file__).parents[1] / "server" / "main.py").exists(), "API has not been implemented"
    module = importlib.import_module("server.main")
    with TestClient(module.create_app()) as connection:
        yield connection


def register(client, email="finance@example.ru"):
    response = client.post("/api/auth/register", json={
        "name": "Анна", "company": "ООО Поставка", "email": email,
        "password": "Correct-horse-24!",
    })
    assert response.status_code == 201, response.text
    body = response.json()
    client.headers["X-CSRF-Token"] = body["csrf_token"]
    return body


def invoice(client, **changes):
    data = {
        "company": "ООО Север", "inn": "7701234567", "email": "ap@example.ru",
        "number": "СЧ-24", "issued_on": str(business_today() - timedelta(days=30)),
        "due_on": str(business_today() - timedelta(days=10)), "amount": 125050,
        "notes": "Поставка комплектующих",
    }
    data.update(changes)
    response = client.post("/api/invoices", json=data)
    assert response.status_code == 201, response.text
    return response.json()


def test_empty_registration_is_persistent_and_password_is_hashed(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/invoices").status_code == 401
    user = register(client)
    assert user["user"]["company"] == "ООО Поставка"
    assert client.get("/api/invoices").json() == {"items": []}
    assert client.get("/api/overview").json()["total_outstanding"] == 0
    assert client.get("/api/auth/me").json() == user
    assert "httponly" in client.cookies.__repr__().lower() or "session" in str(client.cookies)
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    login = client.post("/api/auth/login", json={"email": "FINANCE@example.ru", "password": "Correct-horse-24!"})
    assert login.status_code == 200
    assert login.json()["user"] == user["user"]
    connection = sqlite3.connect(client.app.state.config.database_path)
    stored = connection.execute("SELECT password_hash FROM users").fetchone()[0]
    assert stored.startswith("$argon2") and "Correct-horse" not in stored
    connection.close()


def test_auth_validation_and_csrf(client):
    assert client.post("/api/auth/login", json={"email": "missing@example.ru", "password": "wrong"}).status_code == 401
    register(client)
    csrf = client.headers.pop("X-CSRF-Token")
    assert client.post("/api/invoices", json={}).status_code == 403
    client.headers["X-CSRF-Token"] = csrf
    assert client.post("/api/auth/register", json={"name": "A", "company": "B", "email": "finance@example.ru", "password": "Correct-horse-24!"}).status_code == 409
    assert client.post("/api/auth/register", json={"name": "A", "company": "B", "email": "invalid", "password": "x"}).status_code == 422


def test_financial_lifecycle_and_idempotent_payment(client):
    register(client)
    item = invoice(client)
    assert item["balance"] == 125050 and item["days_overdue"] == 10
    assert item["priority_reasons"]
    promised = str(business_today() + timedelta(days=3))
    assert client.post(f"/api/invoices/{item['id']}/promise", json={"date": promised}).json()["status"] == "promised"
    overview = client.get("/api/overview").json()
    assert overview["total_outstanding"] == overview["overdue_amount"] == overview["promised_amount"] == 125050
    assert sum(bucket["amount"] for bucket in overview["aging"]) == 125050
    payment = {"amount": 25050, "paid_on": str(business_today()), "reference": "Банк-001"}
    response = client.post(f"/api/invoices/{item['id']}/payments", json=payment)
    assert response.status_code == 200 and response.json()["balance"] == 100000
    assert client.post(f"/api/invoices/{item['id']}/payments", json=payment).json()["balance"] == 100000
    changed = {**payment, "amount": 25051}
    assert client.post(f"/api/invoices/{item['id']}/payments", json=changed).status_code == 409
    assert client.post(f"/api/invoices/{item['id']}/payments", json={**payment, "reference": "Банк-002", "amount": 100001}).status_code == 422
    paid = client.post(f"/api/invoices/{item['id']}/payments", json={**payment, "reference": "Банк-002", "amount": 100000}).json()
    assert paid["status"] == "paid" and paid["balance"] == 0
    assert client.post(f"/api/invoices/{item['id']}/draft", json={"tone": "soft"}).status_code == 409
    assert client.get("/api/overview").json()["collected_amount"] == 125050
    detail = client.get(f"/api/invoices/{item['id']}").json()
    assert len(detail["payments"]) == 2 and len(detail["events"]) >= 4


def test_tenant_isolation_across_read_and_mutation(client):
    register(client)
    first = invoice(client)
    message = client.post(f"/api/invoices/{first['id']}/draft", json={"tone": "firm"}).json()
    client.post("/api/auth/logout")
    register(client, "other@example.ru")
    assert client.get("/api/invoices").json() == {"items": []}
    assert client.get(f"/api/invoices/{first['id']}").status_code == 404
    assert client.post(f"/api/invoices/{first['id']}/promise", json={"date": str(business_today())}).status_code == 404
    assert client.patch(f"/api/messages/{message['id']}", json={"subject": "Stolen", "body": "Stolen"}).status_code == 404
    assert client.post(f"/api/messages/{message['id']}/approve").status_code == 404
    assert first["number"] not in client.get("/api/export").text


def test_csv_locales_duplicate_skipping_and_atomic_validation(client):
    register(client)
    content = '\ufeffконтрагент;инн;email;номер;дата;срок;сумма\nООО Север;7701234567;ap@example.ru;А-1;01.10.2026;21.10.2026;1 250,50\n'
    preview = client.post("/api/invoices/import/preview", json={"content": content})
    assert preview.status_code == 200, preview.text
    assert preview.json()["items"][0]["amount"] == 125050
    assert preview.json()["errors"] == []
    assert client.post("/api/invoices/import", json={"content": content}).json() == {"imported": 1, "skipped": 0}
    assert client.post("/api/invoices/import/preview", json={"content": content}).json()["duplicate_count"] == 1
    assert client.post("/api/invoices/import", json={"content": content}).json() == {"imported": 0, "skipped": 1}
    invalid = content + 'ООО Юг;7801234567;ap@example.ru;А-2;01.10.2026;21.10.2026;-12\n'
    result = client.post("/api/invoices/import/preview", json={"content": invalid}).json()
    assert result["errors"][0]["row"] == 3
    assert client.post("/api/invoices/import", json={"content": invalid}).status_code == 422
    assert len(client.get("/api/invoices").json()["items"]) == 1
    english = 'company,number,issued_on,due_on,amount,email\nSouth,B-2,2026-10-01,2026-10-31,0.01,ap@example.ru\n'
    assert client.post("/api/invoices/import", json={"content": english}).json()["imported"] == 1


def test_draft_edit_resets_approval_and_unconfigured_smtp_never_sends(client):
    register(client)
    item = invoice(client)
    message = client.post(f"/api/invoices/{item['id']}/draft", json={"tone": "soft"}).json()
    assert "1 250,50" in message["body"] and item["number"] in message["body"]
    assert message["status"] == "draft" and message["source"] == "template"
    assert client.post(f"/api/messages/{message['id']}/send").status_code == 409
    assert client.post(f"/api/messages/{message['id']}/approve").json()["status"] == "approved"
    edited = client.patch(f"/api/messages/{message['id']}", json={"subject": "Оплата поставки", "body": message["body"] + " Спасибо."})
    assert edited.json()["status"] == "draft"
    client.post(f"/api/messages/{message['id']}/approve")
    assert client.post(f"/api/messages/{message['id']}/send").status_code == 409
    detail = client.get(f"/api/invoices/{item['id']}").json()
    assert detail["messages"][0]["status"] == "approved"
    assert not any(event["type"] == "message_sent" for event in detail["events"])


@pytest.mark.parametrize("status", ["disputed", "paused"])
def test_sensitive_account_states_block_contact(client, status):
    register(client)
    item = invoice(client)
    response = client.post(f"/api/invoices/{item['id']}/status", json={"status": status, "notes": "Ожидаем документы"})
    assert response.status_code == 200 and response.json()["status"] == status
    assert client.post(f"/api/invoices/{item['id']}/draft", json={"tone": "firm"}).status_code == 409


def test_search_priority_and_export_formula_escaping(client):
    register(client)
    invoice(client, company="=SUM(1+1)", number="=1+1")
    invoice(client, company="ООО Юг", number="Ю-2", due_on=str(business_today() + timedelta(days=10)))
    assert len(client.get("/api/invoices?search=Юг").json()["items"]) == 1
    assert len(client.get("/api/invoices?priority=low").json()["items"]) == 1
    response = client.get("/api/export")
    assert response.status_code == 200 and "text/csv" in response.headers["content-type"]
    rows = list(csv.reader(io.StringIO(response.text.lstrip("\ufeff")), delimiter=";"))
    assert any("'=1+1" in cell for row in rows for cell in row)


def test_settings_persist_without_secrets_and_money_is_strict(client):
    register(client)
    response = client.patch("/api/settings", json={"sender_name": "Анна Иванова", "reply_to": "finance@example.ru", "bank_details": "Р/с 40702", "annual_rate": 22, "cooldown_days": 4})
    assert response.status_code == 200
    assert client.get("/api/settings").json()["cooldown_days"] == 4
    assert "password" not in response.text and response.json()["smtp_configured"] is False
    for value in (1.01, "100", True, 0, -1):
        data = {"company": "A", "number": "A", "issued_on": "2026-10-01", "due_on": "2026-10-02", "amount": value}
        assert client.post("/api/invoices", json=data).status_code == 422


def test_origin_and_body_size_controls(client):
    register(client)
    client.app.state.config.app_url = "https://mandato.example.ru"
    response = client.post("/api/invoices", json={}, headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    client.app.state.config.app_url = ""
    assert client.post("/api/invoices/import/preview", content=b"x" * 2_100_000, headers={"Content-Type": "application/json"}).status_code == 413


def test_changed_balance_invalidates_approval(client):
    register(client)
    item = invoice(client)
    message = client.post(f"/api/invoices/{item['id']}/draft", json={"tone": "soft"}).json()
    client.post(f"/api/messages/{message['id']}/approve")
    client.post(f"/api/invoices/{item['id']}/payments", json={"amount": 50, "paid_on": str(business_today()), "reference": "PART-1"})
    detail = client.get(f"/api/invoices/{item['id']}").json()
    assert detail["messages"][0]["status"] == "draft"
    assert client.post(f"/api/messages/{message['id']}/approve").status_code == 409
    assert client.post(f"/api/messages/{message['id']}/send").status_code == 409


def test_concurrent_payments_cannot_overpay(client):
    register(client)
    item = invoice(client, amount=1000)

    def pay(reference):
        return client.post(f"/api/invoices/{item['id']}/payments", json={"amount": 750, "paid_on": str(business_today()), "reference": reference}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(pay, ("PAR-1", "PAR-2")))
    assert sorted(results) == [200, 422]
    assert client.get(f"/api/invoices/{item['id']}").json()["invoice"]["balance"] == 250


@pytest.fixture
def smtp_receiver(monkeypatch):
    received = []

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            self.wfile.write(b"220 localhost ESMTP\r\n")
            body, reading = [], False
            while line := self.rfile.readline():
                command = line.strip().upper()
                if reading:
                    if command == b".":
                        received.append(b"".join(body))
                        self.wfile.write(b"250 Queued\r\n")
                        reading = False
                    else:
                        body.append(line)
                elif command.startswith((b"EHLO", b"HELO", b"MAIL", b"RCPT", b"RSET")):
                    self.wfile.write(b"250 OK\r\n")
                elif command == b"DATA":
                    self.wfile.write(b"354 End with dot\r\n")
                    reading = True
                elif command == b"QUIT":
                    self.wfile.write(b"221 Bye\r\n")
                    break
                else:
                    self.wfile.write(b"500 Unsupported\r\n")

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    monkeypatch.setenv("SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("SMTP_PORT", str(server.server_address[1]))
    monkeypatch.setenv("SMTP_FROM", "finance@example.ru")
    monkeypatch.setenv("SMTP_USE_TLS", "false")
    monkeypatch.setenv("SMTP_USE_SSL", "false")
    yield received
    server.shutdown()
    server.server_close()
    worker.join(timeout=2)


def test_actual_smtp_acceptance_and_cooldown(client, smtp_receiver, monkeypatch):
    register(client)
    # One corporate mailbox is explicitly bound to one registered tenant.
    connection = sqlite3.connect(client.app.state.config.database_path)
    tenant_id = connection.execute("SELECT tenant_id FROM users").fetchone()[0]
    connection.close()
    monkeypatch.setenv("SMTP_TENANT_ID", tenant_id)
    item = invoice(client)
    message = client.post(f"/api/invoices/{item['id']}/draft", json={"tone": "soft"}).json()
    client.post(f"/api/messages/{message['id']}/approve")
    sent = client.post(f"/api/messages/{message['id']}/send")
    assert sent.status_code == 200 and sent.json()["status"] == "sent", sent.text
    assert len(smtp_receiver) == 1 and b"To: ap@example.ru" in smtp_receiver[0]
    assert client.post(f"/api/messages/{message['id']}/send").status_code == 409
    assert client.patch(f"/api/messages/{message['id']}", json={"subject": "Changed", "body": "Changed"}).status_code == 409
    another = client.post(f"/api/invoices/{item['id']}/draft", json={"tone": "firm"}).json()
    client.post(f"/api/messages/{another['id']}/approve")
    assert client.post(f"/api/messages/{another['id']}/send").status_code == 409
    assert len(smtp_receiver) == 1


def test_auth_rate_limit_and_no_validation_secret_echo(client):
    for _ in range(15):
        response = client.post("/api/auth/login", json={"email": "not-email", "password": "private-secret"})
        assert response.status_code == 422
        assert "private-secret" not in response.text
    assert client.post("/api/auth/login", json={"email": "a@example.ru", "password": "wrong"}).status_code == 429


def test_password_whitespace_is_not_silently_changed(client):
    registered = client.post("/api/auth/register", json={"name": "Анна", "company": "Поставка", "email": "password@example.ru", "password": "  Secret-with-spaces-123  "})
    assert registered.status_code == 201
    assert client.post("/api/auth/login", json={"email": "password@example.ru", "password": "Secret-with-spaces-123"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "password@example.ru", "password": "  Secret-with-spaces-123  "}).status_code == 200


def test_smtp_is_fail_closed_without_tenant_binding(client, monkeypatch):
    register(client)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.ru")
    monkeypatch.setenv("SMTP_FROM", "operator@example.ru")
    monkeypatch.delenv("SMTP_TENANT_ID", raising=False)
    assert client.get("/api/settings").json()["smtp_configured"] is False
    item = invoice(client)
    draft = client.post(f"/api/invoices/{item['id']}/draft", json={"tone": "soft"}).json()
    client.post(f"/api/messages/{draft['id']}/approve")
    assert client.post(f"/api/messages/{draft['id']}/send").status_code == 409
    monkeypatch.setenv("SMTP_TENANT_ID", "some-other-tenant")
    assert client.get("/api/settings").json()["smtp_configured"] is False


def test_header_injection_is_rejected_before_message_composition(client):
    register(client)
    response = client.patch("/api/settings", json={"sender_name": "Anna\r\nBcc: attacker@example.ru"})
    assert response.status_code == 422
    data = {"company": "A", "number": "Invoice\nBcc: attacker@example.ru", "issued_on": "2026-10-01", "due_on": "2026-10-02", "amount": 100}
    assert client.post("/api/invoices", json=data).status_code == 422


@pytest.mark.parametrize("email", ["a,b@example.ru", "anna:admin@example.ru", "a..b@example.ru", "a@example..ru", "a@-example.ru"])
def test_email_is_one_valid_mailbox_not_a_header_list(client, email):
    register(client)
    data = {"company": "A", "number": "A", "email": email, "issued_on": "2026-10-01", "due_on": "2026-10-02", "amount": 100}
    assert client.post("/api/invoices", json=data).status_code == 422


def test_production_cookie_and_origin_configuration(client, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECURE_COOKIES", "true")
    monkeypatch.setenv("APP_URL", "https://mandato.example.ru")
    module = importlib.import_module("server.main")
    with TestClient(module.create_app(), base_url="https://mandato.example.ru") as production:
        payload = {"name": "Анна", "company": "A", "email": "secure@example.ru", "password": "Strong-password-2026"}
        assert production.post("/api/auth/register", json=payload).status_code == 403
        registered = production.post("/api/auth/register", json=payload, headers={"Origin": "https://mandato.example.ru"})
        cookie = registered.headers["set-cookie"].lower()
        assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie
        assert production.get("/api/auth/me").status_code == 200
        assert production.get("/api/openapi.json").status_code == 404
        assert production.get("/api/auth/me").headers["cache-control"] == "no-store"


def test_api_llm_payload_contains_no_invoice_or_contact_data(client, monkeypatch):
    import json
    import httpx
    from server import llm

    register(client)
    item = invoice(client, number="PRIVATE-996", company="Секретный Заказчик")
    monkeypatch.setenv("YANDEX_API_KEY", "fake-key")
    monkeypatch.setenv("YANDEX_MODEL", "gpt://folder/model/latest")
    monkeypatch.setattr(llm, "_cache", {})
    payloads = []

    def provider(url, **arguments):
        payloads.append(json.dumps(arguments["json"], ensure_ascii=False))
        fragments = {"greeting": "Добрый день!", "request": "Подскажите, пожалуйста, когда планируется оплата?", "closing": "Спасибо за сотрудничество."}
        return httpx.Response(200, json={"alternatives": [{"message": {"text": json.dumps(fragments)}}]}, request=httpx.Request("POST", url))

    monkeypatch.setattr(llm.httpx, "post", provider)
    response = client.post(f"/api/invoices/{item['id']}/draft", json={"tone": "soft"})
    assert response.status_code == 201
    assert response.json()["source"] == "yandex"
    assert "PRIVATE-996" in response.json()["body"] and "1 250,50" in response.json()["body"]
    assert len(payloads) == 1
    for private_value in ("PRIVATE-996", "Секретный Заказчик", "ap@example.ru", "7701234567", "125050", "finance@example.ru"):
        assert private_value not in payloads[0]


def test_concurrent_send_delivers_only_one_message(client, smtp_receiver, monkeypatch):
    register(client)
    connection = sqlite3.connect(client.app.state.config.database_path)
    tenant_id = connection.execute("SELECT tenant_id FROM users").fetchone()[0]
    connection.close()
    monkeypatch.setenv("SMTP_TENANT_ID", tenant_id)
    item = invoice(client)
    message = client.post(f"/api/invoices/{item['id']}/draft", json={"tone": "soft"}).json()
    client.post(f"/api/messages/{message['id']}/approve")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: client.post(f"/api/messages/{message['id']}/send").status_code, range(2)))
    assert sorted(results) == [200, 409]
    assert len(smtp_receiver) == 1


def test_moscow_midnight_controls_aging_promises_payments_and_weekly_chart(client, monkeypatch):
    from server import business_time

    instant = importlib.import_module("datetime").datetime.fromisoformat("2026-10-24T21:30:00+00:00")

    class FrozenDatetime(importlib.import_module("datetime").datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)

    monkeypatch.setattr(business_time, "datetime", FrozenDatetime)
    register(client)
    item = invoice(client, issued_on="2026-10-01", due_on="2026-10-24")
    assert item["days_overdue"] == 1
    assert client.post(f"/api/invoices/{item['id']}/promise", json={"date": "2026-10-24"}).status_code == 422
    assert client.post(f"/api/invoices/{item['id']}/promise", json={"date": "2026-10-25"}).status_code == 200
    payment = {"amount": 50, "paid_on": "2026-10-25", "reference": "MOSCOW-BOUNDARY"}
    assert client.post(f"/api/invoices/{item['id']}/payments", json=payment).status_code == 200
    assert client.post(f"/api/invoices/{item['id']}/payments", json={**payment, "paid_on": "2026-10-26", "reference": "FUTURE"}).status_code == 422
    overview = client.get("/api/overview").json()
    assert overview["weekly"][-1] == {"date": "2026-10-25", "amount": 50}
    assert overview["aging"][1]["amount"] == item["amount"] - 50


def test_expired_sessions_are_pruned_when_login_creates_a_new_session(client):
    register(client)
    connection = sqlite3.connect(client.app.state.config.database_path)
    connection.execute("UPDATE sessions SET expires_at='2000-01-01T00:00:00+00:00'")
    connection.commit()
    connection.close()
    assert client.get("/api/auth/me").status_code == 401
    response = client.post("/api/auth/login", json={"email": "finance@example.ru", "password": "Correct-horse-24!"})
    assert response.status_code == 200
    connection = sqlite3.connect(client.app.state.config.database_path)
    assert connection.execute("SELECT count(*) FROM sessions").fetchone()[0] == 1
    connection.close()


def test_contact_correction_requires_new_draft_for_new_recipient(client):
    register(client)
    item = invoice(client)
    message = client.post(f"/api/invoices/{item['id']}/draft", json={"tone": "soft"}).json()
    client.post(f"/api/messages/{message['id']}/approve")
    changed = client.patch(f"/api/invoices/{item['id']}/contact", json={"email": "new-ap@example.ru", "notes": "Адрес уточнён у клиента"})
    assert changed.status_code == 200, changed.text
    assert changed.json()["email"] == "new-ap@example.ru"
    assert changed.json()["notes"] == "Адрес уточнён у клиента"
    assert changed.json()["amount"] == item["amount"]
    detail = client.get(f"/api/invoices/{item['id']}").json()
    assert detail["messages"][0]["status"] == "draft"
    assert detail["messages"][0]["recipient"] == "ap@example.ru"
    assert detail["events"][0]["title"] == "Контакт обновлён"
    assert client.post(f"/api/messages/{message['id']}/approve").status_code == 409
    assert client.post(f"/api/messages/{message['id']}/send").status_code == 409
    fresh = client.post(f"/api/invoices/{item['id']}/draft", json={"tone": "soft"}).json()
    assert fresh["recipient"] == "new-ap@example.ru"
    assert client.post(f"/api/messages/{fresh['id']}/approve").status_code == 200


def test_contact_change_is_tenant_scoped_and_only_accepts_safe_contact_fields(client):
    register(client)
    item = invoice(client)
    endpoint = f"/api/invoices/{item['id']}/contact"
    assert client.patch(endpoint, json={"email": "new@example.ru\r\nBcc: other@example.ru", "notes": ""}).status_code == 422
    assert client.patch(endpoint, json={"email": "new@example.ru", "notes": "", "amount": 1}).status_code == 422
    assert client.patch("/api/invoices/missing/contact", json={"email": "new@example.ru", "notes": ""}).status_code == 404
    client.post("/api/auth/logout")
    register(client, "another@example.ru")
    assert client.patch(endpoint, json={"email": "stolen@example.ru", "notes": ""}).status_code == 404


def test_paid_invoice_contact_and_notes_can_still_be_corrected(client):
    register(client)
    item = invoice(client)
    client.post(f"/api/invoices/{item['id']}/payments", json={"amount": item["amount"], "paid_on": str(business_today()), "reference": "CLOSED"})
    updated = client.patch(f"/api/invoices/{item['id']}/contact", json={"email": "corrected@example.ru", "notes": "Сверка завершена"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "paid" and updated.json()["balance"] == 0
    assert updated.json()["email"] == "corrected@example.ru"


def test_status_changes_preserve_notes_unless_replacement_is_supplied(client):
    register(client)
    item = invoice(client)
    endpoint = f"/api/invoices/{item['id']}"
    assert client.patch(endpoint + "/contact", json={"email": item["email"], "notes": "Важный контекст"}).status_code == 200
    paused = client.post(endpoint + "/status", json={"status": "paused"})
    assert paused.status_code == 200
    assert paused.json()["notes"] == "Важный контекст"
    assert client.get(endpoint).json()["invoice"]["notes"] == "Важный контекст"
    replaced = client.post(endpoint + "/status", json={"status": "disputed", "notes": "Ожидаем акт сверки"})
    assert replaced.json()["notes"] == "Ожидаем акт сверки"
    cleared = client.post(endpoint + "/status", json={"status": "open", "notes": ""})
    assert cleared.json()["notes"] == ""
    assert client.get(endpoint).json()["invoice"]["notes"] == ""
