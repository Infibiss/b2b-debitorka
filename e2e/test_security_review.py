"""Independent security acceptance checks; no external SMTP is contacted.

Run: python3 -m pytest -q e2e/test_security_review.py
"""
import importlib
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient


def moscow_today():
    """Expected API calendar, independent of the runner's local timezone."""
    return datetime.now(ZoneInfo("Europe/Moscow")).date()


@pytest.fixture
def reviewed_app(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_TIMEZONE", "Europe/Moscow")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "review.sqlite3"))
    monkeypatch.setenv("SECURE_COOKIES", "false")
    monkeypatch.delenv("APP_URL", raising=False)
    for name in ("SMTP_HOST", "SMTP_FROM", "SMTP_USER", "SMTP_PASSWORD", "SMTP_TENANT_ID"):
        monkeypatch.delenv(name, raising=False)
    module = importlib.import_module("server.main")
    return module.create_app()


def signup(client, email="reviewer@example.ru"):
    response = client.post("/api/auth/register", json={
        "company": "ООО Независимая проверка", "name": "Анна", "email": email,
        "password": "Review-correct-password-2026!",
    })
    assert response.status_code == 201, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return response.json()


def add_invoice(client, number="REVIEW-1"):
    response = client.post("/api/invoices", json={
        "company": "ООО Север", "number": number, "email": "ap@example.ru",
        "issued_on": str(moscow_today() - timedelta(days=30)),
        "due_on": str(moscow_today() - timedelta(days=10)), "amount": 125050,
    })
    assert response.status_code == 201, response.text
    return response.json()


def approved_message(client, invoice):
    response = client.post(f"/api/invoices/{invoice['id']}/draft", json={})
    assert response.status_code == 201, response.text
    message = response.json()
    assert client.post(f"/api/messages/{message['id']}/approve").status_code == 200
    return message


def test_public_signup_cannot_borrow_the_operators_smtp(reviewed_app, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "local-review.invalid")
    monkeypatch.setenv("SMTP_FROM", "operator@example.ru")
    with TestClient(reviewed_app) as client:
        signup(client)
        invoice = add_invoice(client)
        message = approved_message(client, invoice)
        assert client.get("/api/settings").json()["smtp_configured"] is False
        response = client.post(f"/api/messages/{message['id']}/send")
        assert response.status_code == 409, response.text
        assert client.get(f"/api/invoices/{invoice['id']}").json()["messages"][0]["status"] == "approved"


def test_smtp_is_bound_to_one_tenant_and_repeated_send_is_rejected(reviewed_app, monkeypatch):
    deliveries = []

    class LocalSMTP:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def starttls(self, **_kwargs):
            pass

        def send_message(self, message):
            deliveries.append((message["From"], message["To"], message.get_content()))
            return {}

    monkeypatch.setenv("SMTP_HOST", "local-review.invalid")
    monkeypatch.setenv("SMTP_FROM", "operator@example.ru")
    monkeypatch.setattr("server.main.smtplib.SMTP", LocalSMTP)
    with TestClient(reviewed_app) as client:
        signup(client)
        connection = sqlite3.connect(reviewed_app.state.config.database_path)
        tenant_id = connection.execute("SELECT tenant_id FROM users WHERE email=?", ("reviewer@example.ru",)).fetchone()[0]
        connection.close()
        monkeypatch.setenv("SMTP_TENANT_ID", tenant_id)
        assert client.get("/api/settings").json()["smtp_configured"] is True
        invoice = add_invoice(client)
        message = approved_message(client, invoice)
        assert client.post(f"/api/messages/{message['id']}/send").status_code == 200
        assert client.post(f"/api/messages/{message['id']}/send").status_code == 409
        assert len(deliveries) == 1
        assert deliveries[0][1] == "ap@example.ru"
        assert client.post("/api/auth/logout").status_code == 200
        signup(client, "another-tenant@example.ru")
        assert client.get("/api/settings").json()["smtp_configured"] is False
        other_invoice = add_invoice(client)
        other_message = approved_message(client, other_invoice)
        assert client.post(f"/api/messages/{other_message['id']}/send").status_code == 409
        assert len(deliveries) == 1


def test_every_sensitive_resource_rejects_another_tenant(reviewed_app):
    with TestClient(reviewed_app) as client:
        signup(client)
        invoice = add_invoice(client)
        message = approved_message(client, invoice)
        client.post("/api/auth/logout")
        signup(client, "isolated@example.ru")
        prefix = f"/api/invoices/{invoice['id']}"
        attempts = [
            ("GET", prefix, None),
            ("POST", prefix + "/draft", {}),
            ("POST", prefix + "/promise", {"date": str(moscow_today())}),
            ("POST", prefix + "/status", {"status": "paused"}),
            ("POST", prefix + "/payments", {"amount": 1, "paid_on": str(moscow_today()), "reference": "X"}),
            ("PATCH", prefix + "/contact", {"email": "other@example.ru", "notes": "X"}),
            ("PATCH", f"/api/messages/{message['id']}", {"subject": "X", "body": "X"}),
            ("POST", f"/api/messages/{message['id']}/approve", {}),
            ("POST", f"/api/messages/{message['id']}/send", {}),
        ]
        for method, path, body in attempts:
            response = client.request(method, path, json=body)
            assert response.status_code == 404, (method, path, response.text)
        assert client.get("/api/invoices").json()["items"] == []
        assert invoice["number"] not in client.get("/api/export").text
        assert client.get("/api/overview").json()["total_outstanding"] == 0


def test_payment_invalidates_approval_and_never_overstates_the_remaining_debt(reviewed_app):
    with TestClient(reviewed_app) as client:
        signup(client)
        invoice = add_invoice(client)
        message = approved_message(client, invoice)
        prefix = f"/api/invoices/{invoice['id']}"
        payment = {"amount": 25050, "paid_on": str(moscow_today()), "reference": "BANK-1"}
        assert client.post(prefix + "/payments", json=payment).json()["balance"] == 100000
        assert client.post(prefix + "/payments", json=payment).json()["balance"] == 100000
        old = client.get(prefix).json()["messages"][0]
        assert old["status"] == "draft"
        assert client.post(f"/api/messages/{message['id']}/approve").status_code == 409
        assert client.post(f"/api/messages/{message['id']}/send").status_code == 409
        overpayment = {**payment, "amount": 100001, "reference": "BANK-2"}
        assert client.post(prefix + "/payments", json=overpayment).status_code == 422
        assert client.get(prefix).json()["invoice"]["balance"] == 100000
        full = {**payment, "amount": 100000, "reference": "BANK-2"}
        assert client.post(prefix + "/payments", json=full).json()["status"] == "paid"
        assert client.post(prefix + "/draft", json={}).status_code == 409


def test_wrong_csrf_or_origin_cannot_mutate_data(reviewed_app):
    with TestClient(reviewed_app) as client:
        signup(client)
        correct = client.headers["X-CSRF-Token"]
        client.headers["X-CSRF-Token"] = "wrong"
        assert client.post("/api/invoices", json={}).status_code == 403
        client.headers["X-CSRF-Token"] = correct
        reviewed_app.state.config.app_url = "https://agentpay.example.ru"
        assert client.post("/api/invoices", json={}).status_code == 403
        assert client.post("/api/invoices", json={}, headers={"Origin": "https://evil.example.ru"}).status_code == 403
        assert client.get("/api/invoices").json()["items"] == []


def test_correcting_recipient_invalidates_old_drafts_without_changing_money(reviewed_app):
    with TestClient(reviewed_app) as client:
        signup(client)
        invoice = add_invoice(client)
        message = approved_message(client, invoice)
        prefix = f"/api/invoices/{invoice['id']}"
        updated = client.patch(prefix + "/contact", json={"email": "corrected@example.ru", "notes": "Проверено с покупателем"})
        assert updated.status_code == 200, updated.text
        assert updated.json()["amount"] == invoice["amount"]
        assert updated.json()["balance"] == invoice["balance"]
        assert client.get(prefix).json()["messages"][0]["status"] == "draft"
        response = client.post(f"/api/messages/{message['id']}/approve")
        assert response.status_code == 409
        assert "Адрес получателя изменился" in response.text
        assert client.post(f"/api/messages/{message['id']}/send").status_code == 409
        fresh = client.post(prefix + "/draft", json={})
        assert fresh.status_code == 201
        assert fresh.json()["recipient"] == "corrected@example.ru"
        mass_assignment = client.patch(prefix + "/contact", json={"email": "corrected@example.ru", "notes": "", "amount": 1})
        assert mass_assignment.status_code == 422
        assert client.get(prefix).json()["invoice"]["amount"] == invoice["amount"]
