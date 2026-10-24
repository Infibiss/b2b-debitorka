"""Explicit opt-in paid synthetic Yandex + local Langfuse integration canary."""
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


@pytest.mark.skipif(os.getenv("RUN_AGENT_LIVE_CANARY") != "1", reason="Explicit synthetic live canary opt-in required")
def test_real_yandex_review_and_local_langfuse_delivery(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from langfuse import get_client
    from server.main import create_app
    from server.business_time import business_today
    from scripts.langfuse_local import observations_for_trace
    assert os.getenv("YANDEX_API_KEY") and os.getenv("LANGFUSE_SECRET_KEY")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECURE_COOKIES", "false")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "synthetic.db"))
    for key in ("DATABASE_URL", "APP_URL", "RENDER_EXTERNAL_URL", "YANDEX_AGENT_TENANT_IDS"):
        monkeypatch.delenv(key, raising=False)
    settings = {key: os.environ[key] for key in ("LANGFUSE_BASE_URL", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")}
    start = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    with TestClient(create_app()) as client:
        auth = client.post("/api/auth/register", json={"name": "Синтетический оператор", "company": "Тестовая организация", "email": "canary@example.invalid", "password": "Synthetic-only-canary-2026!"})
        assert auth.status_code == 201
        client.headers["X-CSRF-Token"] = auth.json()["csrf_token"]
        r = client.post("/api/invoices", json={"company": "Синтетический контрагент", "number": "SYNTHETIC-ONLY", "issued_on": str(business_today()-timedelta(days=10)), "due_on": str(business_today()-timedelta(days=1)), "amount": 100000})
        assert r.status_code == 201
        r = client.post("/api/agent/ingest", json={"invoice_id": r.json()["id"], "text": "Мы оплатили, проверьте поступление.", "idempotency_key": "live-synthetic-only-001"})
        assert r.status_code == 201
        proposal = r.json()
        assert proposal["status"] == "review_required", proposal["reasons"]
        approved = client.post(f"/api/agent/proposals/{proposal['id']}/review", json={"decision": "approve"})
        assert approved.status_code == 200
        assert approved.json()["outcome"]["action"] == "verify_payment"
        assert client.get(f"/api/invoices/{proposal['invoice_id']}").json()["invoice"]["paid_amount"] == 0
        get_client(public_key=settings["LANGFUSE_PUBLIC_KEY"]).flush()
        trace_id = proposal["provider"]["trace_id"]
        for _ in range(20):
            rows = observations_for_trace(settings, trace_id, start, (datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat())
            generations = [row for row in rows if row.get("type") == "GENERATION"]
            if generations:
                assert all(row.get("input") in (None, "", "null") and row.get("output") in (None, "", "null") for row in rows)
                report = {"status": "delivered", "created_at": datetime.now(timezone.utc).isoformat(), "trace_id": trace_id,
                    "action": "verify_payment", "workflow_status": "executed", "paid_amount": 0, "io_empty": True,
                    "observations": len(rows), "input_tokens": generations[0].get("inputUsage"),
                    "output_tokens": generations[0].get("outputUsage"), "model": generations[0].get("model")}
                target = Path(os.getenv("AGENT_LIVE_REPORT", str(tmp_path / "delivery.json")))
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n")
                return
            time.sleep(2)
        pytest.fail("Actual agent generation did not become readable in Langfuse within bounded wait")
