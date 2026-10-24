"""Actual authenticated API, actual finance services, actual persistent graph."""
from datetime import timedelta

from test_finance import client, invoice
from server.business_time import business_today


def provider(monkeypatch, intent="promise"):
    from server import agent
    due = str(business_today() + timedelta(days=3))
    text = f"Обещаем оплатить 300 рублей {due}." if intent == "promise" else "Мы оплатили, проверьте поступление."
    payload = {"intent": intent, "amount_kopeks": 30000 if intent == "promise" else None,
        "due_date": due if intent == "promise" else None, "currency": "RUB" if intent == "promise" else "unknown",
        "ambiguous": False, "evidence": [{"field": "intent", "quote": text}]}
    if intent == "promise":
        payload["evidence"] += [{"field": "amount", "quote": "300 рублей"}, {"field": "due_date", "quote": due}]
    monkeypatch.setattr(agent, "extract_yandex", lambda *a, **k: {"payload": payload, "error": None, "model": "offline-fixture",
        "prompt_version": "test", "usage": {}, "latency_ms": 1, "trace_id": None})
    return text


def submit(client, item, text, key="real-finance-001"):
    r = client.post("/api/agent/ingest", json={"invoice_id": item["id"], "text": text, "idempotency_key": key})
    assert r.status_code == 201, r.text
    return r.json()


def test_explicit_mandate_enables_only_partial_promise(client, monkeypatch):
    item = invoice(client)
    text = provider(monkeypatch)
    blocked = submit(client, item, text)
    assert blocked["status"] == "handoff" and "promise_mandate_required" in blocked["reasons"]
    assert client.post(f"/api/agent/proposals/{blocked['id']}/review", json={"decision": "approve"}).status_code == 409
    assert client.patch(f"/api/finance/counterparties/{item['counterparty_id']}", json={"agent_promises_allowed": True}).status_code == 200
    proposal = submit(client, item, text, "real-finance-002")
    assert proposal["status"] == "review_required", proposal
    approved = client.post(f"/api/agent/proposals/{proposal['id']}/review", json={"decision": "approve"})
    assert approved.status_code == 200, approved.text
    current = client.get(f"/api/invoices/{item['id']}").json()["invoice"]
    assert current["promised_amount"] == 30000 and current["balance"] == 100000
    assert client.get("/api/overview").json()["promised_amount"] == 30000


def test_verified_payment_claim_does_not_confirm_money(client, monkeypatch):
    item = invoice(client)
    text = provider(monkeypatch, "payment_claim")
    proposal = submit(client, item, text)
    assert proposal["status"] == "review_required", proposal
    approved = client.post(f"/api/agent/proposals/{proposal['id']}/review", json={"decision": "approve"})
    assert approved.status_code == 200
    assert approved.json()["outcome"]["action"] == "verify_payment"
    assert client.get(f"/api/invoices/{item['id']}").json()["invoice"]["paid_amount"] == 0
    assert client.get("/api/overview").json()["collected_amount"] == 0


def test_counterparty_policy_change_invalidates_previously_reviewable_promise(client, monkeypatch):
    item = invoice(client)
    text = provider(monkeypatch)
    cp_url = f"/api/finance/counterparties/{item['counterparty_id']}"
    client.patch(cp_url, json={"agent_promises_allowed": True})
    proposal = submit(client, item, text)
    assert proposal["status"] == "review_required"
    client.patch(cp_url, json={"hold": True, "hold_reason": "Разбор претензии"})
    assert client.post(f"/api/agent/proposals/{proposal['id']}/review", json={"decision": "approve"}).status_code == 409
    assert client.get(f"/api/agent/proposals/{proposal['id']}").json()["status"] == "stale"
    assert client.get(f"/api/invoices/{item['id']}").json()["invoice"]["promised_amount"] == 0
