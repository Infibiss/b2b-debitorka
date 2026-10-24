from concurrent.futures import ThreadPoolExecutor
import pytest

from test_agent_workflow import Ledger, env, make_client, ingest
from server.database import database


def test_simultaneous_approvals_execute_once(env, monkeypatch):
    client, text = make_client(env, monkeypatch)
    p = ingest(client, text)
    def approve(_):
        return client.post(f"/api/agent/proposals/{p['id']}/review", json={"decision": "approve"})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(approve, range(2)))
    assert [r.status_code for r in responses] == [200, 200]
    with database(env.config) as c:
        assert c.execute("SELECT COUNT(*) FROM execution_test").fetchone()[0] == 1


def test_no_approval_after_handoff_or_provider_failure(env, monkeypatch):
    from server import agent
    client, text = make_client(env, monkeypatch)
    monkeypatch.setattr(agent, "extract_yandex", lambda *a, **k: {"payload": None, "error": "provider_timeout", "usage": {}, "latency_ms": 8000})
    p = ingest(client, text)
    assert p["status"] == "handoff" and p["reasons"] == ["provider_timeout"]
    assert client.post(f"/api/agent/proposals/{p['id']}/review", json={"decision": "approve"}).status_code == 409


def test_revision_replay_does_not_supersede_newer_draft(env, monkeypatch):
    client, text = make_client(env, monkeypatch)
    p = ingest(client, text)
    body = {"text": text, "idempotency_key": "revision-001"}
    first = client.post(f"/api/agent/proposals/{p['id']}/revise", json=body).json()
    again = client.post(f"/api/agent/proposals/{p['id']}/revise", json=body)
    assert again.status_code == 201 and again.json()["id"] == first["id"]
    assert client.get(f"/api/agent/proposals/{first['id']}").json()["status"] == "review_required"


def test_budget_is_persistent_and_duplicate_does_not_use_another_slot(env, monkeypatch):
    client, text = make_client(env, monkeypatch)
    first = ingest(client, text)
    with database(env.config, write=True) as c:
        for i in range(29):
            c.execute("""INSERT INTO agent_proposals(id,tenant_id,invoice_id,thread_id,source_key,source_text,
                received_at,created_by,created_at,expires_at,status) SELECT ?,tenant_id,invoice_id,?,?,source_text,
                received_at,created_by,created_at,expires_at,'handoff' FROM agent_proposals WHERE id=?""",
                (f"budget-{i}", f"thread-budget-{i}", f"source-budget-{i}", first["id"]))
    assert ingest(client, text)["id"] == first["id"]
    assert client.post("/api/agent/ingest", json={"invoice_id": "invoice-a", "text": text, "idempotency_key": "after-limit"}).status_code == 429


def test_failed_domain_transaction_resumes_without_losing_real_review(env, monkeypatch):
    client, text = make_client(env, monkeypatch)
    p = ingest(client, text)
    original = Ledger.record_promise
    def interrupted(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("simulate worker termination before business commit")
    with monkeypatch.context() as patch:
        patch.setattr(Ledger, "record_promise", interrupted)
        with pytest.raises(RuntimeError):
            client.post(f"/api/agent/proposals/{p['id']}/review", json={"decision": "approve"})
    with database(env.config) as c:
        assert c.execute("SELECT COUNT(*) FROM execution_test").fetchone()[0] == 0
    second, _ = make_client(env, monkeypatch)
    r = second.post(f"/api/agent/proposals/{p['id']}/review", json={"decision": "approve"})
    assert r.status_code == 200 and r.json()["status"] == "executed"
    with database(env.config) as c:
        assert c.execute("SELECT COUNT(*) FROM execution_test").fetchone()[0] == 1
