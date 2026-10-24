import uuid
import pytest
from test_finance import client, invoice


@pytest.mark.parametrize("binding", [None, "", "not-a-uuid", "other"])
def test_production_unbound_signup_cannot_spend_on_agent_or_old_phrase_api(client, monkeypatch, binding):
    from server import agent, llm
    client.app.state.config.production = True
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("YANDEX_API_KEY", "synthetic-key")
    monkeypatch.setenv("YANDEX_MODEL", "gpt://synthetic/yandexgpt/5.1")
    if binding is None:
        monkeypatch.delenv("YANDEX_AGENT_TENANT_IDS", raising=False)
    else:
        monkeypatch.setenv("YANDEX_AGENT_TENANT_IDS", str(uuid.uuid4()) if binding == "other" else binding)
    monkeypatch.setattr(agent, "extract_yandex", lambda *a, **k: pytest.fail("unauthorized paid extraction"))
    monkeypatch.setattr(llm, "phrases", lambda *a, **k: pytest.fail("unauthorized paid wording"))
    item = invoice(client)
    status = client.get("/api/agent/status")
    assert status.status_code == 200
    assert status.json()["enabled"] is False
    assert status.json()["organization_id"]
    assert "synthetic-key" not in status.text
    submitted = client.post("/api/agent/ingest", json={"invoice_id": item["id"], "text": "Мы оплатили.", "idempotency_key": "policy-source-001"})
    assert submitted.status_code == 201 and submitted.json()["status"] == "handoff"
    assert submitted.json()["reasons"] == ["provider_tenant_denied"]
    draft = client.post(f"/api/invoices/{item['id']}/draft", json={"tone": "soft"})
    assert draft.status_code == 201 and draft.json()["source"] == "template"
    assert client.get("/api/settings").json()["llm_configured"] is False


def test_production_allowlisted_tenant_can_use_agent_and_phrase_api(client, monkeypatch):
    from server import agent, llm
    client.app.state.config.production = True
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("YANDEX_API_KEY", "synthetic-key")
    monkeypatch.setenv("YANDEX_MODEL", "gpt://synthetic/yandexgpt/5.1")
    status = client.get("/api/agent/status")
    assert status.status_code == 200
    monkeypatch.setenv("YANDEX_AGENT_TENANT_IDS", status.json()["organization_id"])
    calls = []
    payload = {"intent": "payment_claim", "amount_kopeks": None, "due_date": None, "currency": "unknown", "ambiguous": False,
        "evidence": [{"field": "intent", "quote": "Мы оплатили."}]}
    def extract(*a, **k):
        calls.append("extract")
        return {"payload": payload, "error": None, "usage": {}}
    def phrases(tone):
        calls.append("phrases")
        return llm.fallback(tone), "yandex"
    monkeypatch.setattr(agent, "extract_yandex", extract)
    monkeypatch.setattr(llm, "phrases", phrases)
    item = invoice(client)
    assert client.get("/api/agent/status").json()["enabled"]
    assert client.post("/api/agent/ingest", json={"invoice_id": item["id"], "text": "Мы оплатили.", "idempotency_key": "policy-source-002"}).json()["status"] == "review_required"
    assert client.post(f"/api/invoices/{item['id']}/draft", json={"tone": "soft"}).json()["source"] == "yandex"
    assert calls == ["extract", "phrases"]


def test_invalid_entry_denies_entire_allowlist_and_development_is_explicit(monkeypatch):
    from server.agent_policy import provider_allowed
    tenant = str(uuid.uuid4())
    monkeypatch.setenv("YANDEX_AGENT_TENANT_IDS", tenant + ",broken")
    assert not provider_allowed(tenant, production=True)
    monkeypatch.delenv("YANDEX_AGENT_TENANT_IDS")
    assert not provider_allowed(tenant, production=True)
    assert provider_allowed(tenant, production=False)
