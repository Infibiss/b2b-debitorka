import json

import httpx
import pytest


def test_provider_uses_fixed_endpoint_schema_no_redirects_and_logging_disabled(monkeypatch):
    monkeypatch.setenv("YANDEX_API_KEY", "synthetic-key")
    monkeypatch.setenv("YANDEX_MODEL", "gpt://synthetic/yandexgpt/5.1")
    from server.agent_graph import extract_yandex
    captured = {}
    payload = {"intent": "payment_claim", "amount_kopeks": None, "due_date": None,
               "currency": "unknown", "ambiguous": False,
               "evidence": [{"field": "intent", "quote": "Мы оплатили"}]}

    def post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return httpx.Response(200, json={"result": {"alternatives": [
            {"message": {"text": json.dumps(payload)}}], "usage": {"inputTextTokens": "20", "completionTokens": "40"}}},
            request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", post)
    result = extract_yandex("Мы оплатили", "2026-10-24T12:00:00+00:00", "opaque-id")
    assert result["payload"] == payload
    assert captured["url"] == "https://ai.api.cloud.yandex.net/foundationModels/v1/completion"
    assert captured["headers"]["x-data-logging-enabled"] == "false"
    assert captured["follow_redirects"] is False and captured["trust_env"] is False
    assert captured["timeout"] <= 10
    assert int(captured["json"]["completionOptions"]["maxTokens"]) <= 1000
    assert captured["json"]["jsonSchema"]["schema"]["additionalProperties"] is False
    assert result["usage"]["input"] == 20


@pytest.mark.parametrize("kind", ["timeout", "invalid_json", "oversized", "permission"])
def test_provider_failure_returns_handoff_without_fake_extraction(monkeypatch, kind):
    monkeypatch.setenv("YANDEX_API_KEY", "synthetic-key")
    monkeypatch.setenv("YANDEX_MODEL", "gpt://synthetic/yandexgpt/5.1")
    from server.agent_graph import extract_yandex

    def post(url, **kwargs):
        if kind == "timeout":
            raise httpx.ReadTimeout("synthetic")
        if kind == "permission":
            return httpx.Response(403, request=httpx.Request("POST", url))
        content = b"x" * 33000 if kind == "oversized" else b"invalid"
        return httpx.Response(200, content=content, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", post)
    result = extract_yandex("Мы оплатили", "2026-10-24T12:00:00+00:00", "opaque-id")
    assert result["payload"] is None
    assert result["error"].startswith("provider_")


def test_no_credentials_does_not_make_network_request(monkeypatch):
    monkeypatch.delenv("YANDEX_API_KEY", raising=False)
    monkeypatch.delenv("YANDEX_MODEL", raising=False)
    from server.agent_graph import extract_yandex
    monkeypatch.setattr(httpx, "post", lambda *a, **k: pytest.fail("unexpected paid request"))
    assert extract_yandex("Мы оплатили", "2026-10-24T12:00:00+00:00", "opaque-id")["error"] == "provider_unconfigured"


def test_blank_optional_model_uses_existing_text_model(monkeypatch):
    monkeypatch.setenv("YANDEX_API_KEY", "synthetic-key")
    monkeypatch.setenv("YANDEX_MODEL", "gpt://synthetic/yandexgpt/5.1")
    monkeypatch.setenv("YANDEX_AGENT_MODEL", "")
    from server.agent_graph import extract_yandex
    captured = []
    def post(url, **kwargs):
        captured.append(kwargs["json"]["modelUri"])
        return httpx.Response(403, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", post)
    assert extract_yandex("Мы оплатили", "2026-10-24T12:00:00+00:00", "opaque-id")["error"] == "provider_permission"
    assert captured == ["gpt://synthetic/yandexgpt/5.1"]


def test_missing_usage_is_unknown_not_zero_cost(monkeypatch):
    monkeypatch.setenv("YANDEX_API_KEY", "synthetic-key")
    monkeypatch.setenv("YANDEX_MODEL", "gpt://synthetic/yandexgpt/5.1")
    monkeypatch.setenv("YANDEX_AGENT_INPUT_RUB_PER_1K", "1")
    monkeypatch.setenv("YANDEX_AGENT_OUTPUT_RUB_PER_1K", "1")
    from server.agent_graph import extract_yandex
    payload = {"intent": "unknown", "amount_kopeks": None, "due_date": None, "currency": "unknown", "ambiguous": False, "evidence": []}
    monkeypatch.setattr(httpx, "post", lambda url, **k: httpx.Response(200,
        json={"result": {"alternatives": [{"message": {"text": json.dumps(payload)}}]}}, request=httpx.Request("POST", url)))
    result = extract_yandex("Спасибо", "2026-10-24T12:00:00Z", "opaque-id")
    assert result["usage"] == {}
    assert result["estimated_cost_rub"] is None


def test_unavailable_observability_does_not_fail_model_extraction(monkeypatch):
    from server.agent_graph import extract_yandex
    from server.agent_observability import AgentObservability
    monkeypatch.setenv("YANDEX_API_KEY", "synthetic-key")
    monkeypatch.setenv("YANDEX_MODEL", "gpt://synthetic/yandexgpt/5.1")
    class UnavailableClient:
        def start_as_current_observation(self, **kwargs):
            raise ConnectionError("synthetic unavailable telemetry")
    payload = {"intent": "payment_claim", "amount_kopeks": None, "due_date": None,
        "currency": "unknown", "ambiguous": False, "evidence": [{"field": "intent", "quote": "Мы оплатили"}]}
    monkeypatch.setattr(httpx, "post", lambda url, **kwargs: httpx.Response(200,
        json={"result": {"alternatives": [{"message": {"text": json.dumps(payload)}}]}}, request=httpx.Request("POST", url)))
    result = extract_yandex("Мы оплатили", "2026-10-24T12:00:00Z", "opaque",
        observer=AgentObservability(client=UnavailableClient()))
    assert result["payload"] == payload and result["error"] is None
    assert result["trace_id"] is None
