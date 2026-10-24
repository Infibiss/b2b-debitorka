"""Real persistent LangGraph checkpoints + business DB across router recreation."""
import hashlib
import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from server.database import Config, database, initialize


class Ledger:
    """Minimal real SQL domain for testing the graph independently of finance UI."""
    @staticmethod
    def financial_snapshot(c, tenant, invoice):
        row = c.execute("SELECT * FROM invoices WHERE id=? AND tenant_id=?", (invoice, tenant)).fetchone()
        if row is None:
            raise HTTPException(404, "missing")
        values = dict(row)
        return {**values, "snapshot_hash": hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()}

    @staticmethod
    def agent_gate(c, tenant, invoice, intent, amount=None, due_date=None):
        row = Ledger.financial_snapshot(c, tenant, invoice)
        return ["held"] if row["status"] == "paused" else []

    @staticmethod
    def record_promise(c, tenant, invoice, amount, due_date, actor_id, source_key, installments=None):
        c.execute("UPDATE invoices SET promise_date=? WHERE id=? AND tenant_id=?", (due_date, invoice, tenant))
        c.execute("INSERT INTO execution_test VALUES(?,?,?)", (source_key, amount, actor_id))
        return {"amount": amount, "due_date": due_date}

    @staticmethod
    def set_dispute(c, tenant, invoice, disputed, reason, actor_id, source_key=None):
        c.execute("UPDATE invoices SET status='disputed' WHERE id=? AND tenant_id=?", (invoice, tenant))
        return {"status": "disputed"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    from server.agent import initialize_schema
    config = Config(str(tmp_path / "business.sqlite3"))
    initialize(config)
    def user(request: Request):
        return {"tenant_id": request.headers.get("tenant", "tenant-a"), "id": "reviewer-1"}
    def event(c, tenant, invoice, kind, title, detail=""):
        pass
    ctx = SimpleNamespace(config=config, database=database, get_user=user, event=event,
        identifier=lambda: __import__('uuid').uuid4().hex,
        now=lambda: datetime.now(timezone.utc).isoformat())
    with database(config, write=True) as c:
        initialize_schema(c)
        c.execute("INSERT INTO tenants VALUES('tenant-a','Synthetic','2026-01-01')")
        from server.finance import ensure_counterparty
        counterparty = ensure_counterparty(c, 'tenant-a', 'Synthetic')
        c.execute("INSERT INTO invoices(id,tenant_id,company,number,number_key,counterparty_id,issued_on,due_on,amount,created_at) VALUES('invoice-a','tenant-a','Synthetic','S-1','s-1',?,'2026-01-01','2026-10-20',100000,'2026-01-01')", (counterparty,))
        c.execute("CREATE TABLE execution_test(source_key TEXT PRIMARY KEY,amount INTEGER,actor TEXT)")
    return ctx


def make_client(ctx, monkeypatch, intent="promise"):
    from server import agent
    from server.agent import create_router
    target = (date.today() + timedelta(days=2)).isoformat()
    text = f"Обещаем оплатить 300 рублей {target}." if intent == "promise" else "Мы оплатили вчера."
    payload = {"intent": intent, "amount_kopeks": 30000 if intent == "promise" else None,
        "due_date": target if intent == "promise" else None, "currency": "RUB" if intent == "promise" else "unknown",
        "ambiguous": False, "evidence": [{"field": "intent", "quote": text}]}
    if intent == "promise":
        payload["evidence"] += [{"field": "amount", "quote": "300 рублей"}, {"field": "due_date", "quote": target}]
    def extract(*args, **kwargs):
        return {"payload": payload, "error": None, "usage": {"input": 20, "output": 40}, "latency_ms": 1,
            "model": "synthetic", "prompt_version": "test", "trace_id": None, "estimated_cost_rub": None}
    monkeypatch.setattr(agent, "extract_yandex", extract)
    application = FastAPI()
    application.include_router(create_router(ctx, services=Ledger))
    return TestClient(application), text


def ingest(client, text, key="source-unique-001"):
    r = client.post("/api/agent/ingest", json={"invoice_id": "invoice-a", "text": text, "idempotency_key": key})
    assert r.status_code == 201, r.text
    return r.json()


def test_partial_promise_waits_for_real_review_and_survives_restart(env, monkeypatch):
    client, text = make_client(env, monkeypatch)
    proposal = ingest(client, text)
    assert proposal["status"] == "review_required"
    with database(env.config) as c:
        assert c.execute("SELECT COUNT(*) FROM execution_test").fetchone()[0] == 0
    assert list(__import__('pathlib').Path(env.config.database_path).parent.glob("*.agent-checkpoints.sqlite3"))
    client.close()
    second, _ = make_client(env, monkeypatch)
    r = second.post(f"/api/agent/proposals/{proposal['id']}/review", json={"decision": "approve"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "executed"
    assert r.json()["outcome"]["amount"] == 30000
    assert second.post(f"/api/agent/proposals/{proposal['id']}/review", json={"decision": "approve"}).status_code == 200
    with database(env.config) as c:
        assert c.execute("SELECT COUNT(*) FROM execution_test").fetchone()[0] == 1


def test_payment_claim_only_creates_verification_task(env, monkeypatch):
    client, text = make_client(env, monkeypatch, "payment_claim")
    p = ingest(client, text)
    r = client.post(f"/api/agent/proposals/{p['id']}/review", json={"decision": "approve"})
    assert r.json()["outcome"]["action"] == "verify_payment"
    with database(env.config) as c:
        assert c.execute("SELECT paid_amount FROM invoices").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM agent_verifications").fetchone()[0] == 1


def test_reject_is_durable_and_cannot_be_changed_to_approve(env, monkeypatch):
    client, text = make_client(env, monkeypatch)
    p = ingest(client, text)
    assert client.post(f"/api/agent/proposals/{p['id']}/review", json={"decision": "reject", "reason": "Нужна сверка"}).json()["status"] == "rejected"
    assert client.post(f"/api/agent/proposals/{p['id']}/review", json={"decision": "approve"}).status_code == 409


def test_stale_ledger_or_new_hold_blocks_execution(env, monkeypatch):
    client, text = make_client(env, monkeypatch)
    p = ingest(client, text)
    with database(env.config, write=True) as c:
        c.execute("UPDATE invoices SET paid_amount=1000,status='paused'")
    r = client.post(f"/api/agent/proposals/{p['id']}/review", json={"decision": "approve"})
    assert r.status_code == 409
    assert client.get(f"/api/agent/proposals/{p['id']}").json()["status"] == "stale"
    with database(env.config) as c:
        assert c.execute("SELECT COUNT(*) FROM execution_test").fetchone()[0] == 0


def test_approval_expiry_and_cross_tenant_access(env, monkeypatch):
    client, text = make_client(env, monkeypatch)
    p = ingest(client, text)
    client.headers["tenant"] = "tenant-b"
    assert client.get(f"/api/agent/proposals/{p['id']}").status_code == 404
    assert client.post(f"/api/agent/proposals/{p['id']}/review", json={"decision": "approve"}).status_code == 404
    client.headers.pop("tenant")
    with database(env.config, write=True) as c:
        c.execute("UPDATE agent_proposals SET expires_at='2020-01-01T00:00:00+00:00'")
    assert client.post(f"/api/agent/proposals/{p['id']}/review", json={"decision": "approve"}).status_code == 409
    assert client.get(f"/api/agent/proposals/{p['id']}").json()["status"] == "stale"


def test_source_replay_idempotency_conflict_and_revision(env, monkeypatch):
    client, text = make_client(env, monkeypatch)
    p = ingest(client, text)
    assert ingest(client, text)["id"] == p["id"]
    assert client.post("/api/agent/ingest", json={"invoice_id": "invoice-a", "text": text + "X", "idempotency_key": "source-unique-001"}).status_code == 409
    revision = client.post(f"/api/agent/proposals/{p['id']}/revise", json={"text": text, "idempotency_key": "source-unique-002"})
    assert revision.status_code == 201, revision.text
    assert revision.json()["revision_of"] == p["id"]
    assert client.get(f"/api/agent/proposals/{p['id']}").json()["status"] == "superseded"
    assert client.post(f"/api/agent/proposals/{p['id']}/review", json={"decision": "approve"}).status_code == 409


def test_forged_resume_does_not_authorize_action(env, monkeypatch):
    from server.agent import AgentRuntime
    from server.agent_graph import persistent_graph
    from langgraph.types import Command
    client, text = make_client(env, monkeypatch)
    p = ingest(client, text)
    runtime = AgentRuntime(env, services=Ledger)
    with persistent_graph(runtime) as graph:
        with pytest.raises(HTTPException):
            graph.invoke(Command(resume={"decision": "approve"}), {"configurable": {"thread_id": p["thread_id"]}})
    with database(env.config) as c:
        assert c.execute("SELECT COUNT(*) FROM execution_test").fetchone()[0] == 0
