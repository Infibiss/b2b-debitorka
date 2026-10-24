"""Operator checks must distinguish real provider success from a safe fallback."""
import importlib
import json

import httpx
import pytest


@pytest.fixture
def adapter(monkeypatch):
    module = importlib.import_module("server.llm")
    monkeypatch.setenv("YANDEX_API_KEY", "private-key-never-print")
    monkeypatch.setenv("YANDEX_API_KEY_ID", "private-id-never-print")
    monkeypatch.setenv("YANDEX_MODEL", "gpt://test-folder/yandexgpt-lite/latest")
    return module


def test_key_id_does_not_supply_a_missing_model(adapter, monkeypatch):
    monkeypatch.setenv("YANDEX_MODEL", "")
    monkeypatch.setattr(adapter.httpx, "post", lambda *a, **k: pytest.fail("No model: no paid call"))
    result = adapter.probe()
    assert result["status"] == "configuration_error"
    assert result["missing"] == ["YANDEX_MODEL"]
    assert result["key_id_present"] is True
    assert "private" not in json.dumps(result)


def test_probe_rejects_invalid_model_uri_before_network(adapter, monkeypatch):
    monkeypatch.setenv("YANDEX_MODEL", "api-key-id-is-not-a-model")
    monkeypatch.setattr(adapter.httpx, "post", lambda *a, **k: pytest.fail("Invalid URI: no call"))
    assert adapter.configured() is False
    assert adapter.probe()["reason"] == "invalid_model_uri"


def test_successful_probe_bypasses_cached_fallback(adapter, monkeypatch):
    calls = []
    fragments = {"greeting": "Здравствуйте!", "request": "Подскажите, пожалуйста, когда планируется оплата?", "closing": "С уважением,"}
    def post(url, **kwargs):
        calls.append(kwargs)
        return httpx.Response(200, json={"result": {"alternatives": [{"message": {"text": json.dumps(fragments)}}]}}, request=httpx.Request("POST", url))
    monkeypatch.setattr(adapter.httpx, "post", post)
    assert adapter.probe()["status"] == "ok"
    assert adapter.probe()["source"] == "yandex"
    assert len(calls) == 2
    assert "private" not in json.dumps(adapter.probe())


@pytest.mark.parametrize("status,reason", [(401, "authentication"), (403, "permission"), (429, "rate_limit"), (404, "model_or_request"), (503, "provider_unavailable")])
def test_provider_errors_are_redacted_and_not_reported_as_success(adapter, monkeypatch, status, reason):
    def post(url, **kwargs):
        return httpx.Response(status, text="private upstream body and key", request=httpx.Request("POST", url))
    monkeypatch.setattr(adapter.httpx, "post", post)
    result = adapter.probe()
    assert result["status"] == "unavailable"
    assert result["source"] == "template"
    assert result["reason"] == reason and result["http_status"] == status
    assert "private" not in json.dumps(result)


def test_valid_provider_json_can_still_be_rejected_by_product_policy(adapter, monkeypatch):
    fragments = {"greeting": "Здравствуйте!", "request": "Мы списали сто рублей.", "closing": "Спасибо"}
    monkeypatch.setattr(adapter.httpx, "post", lambda url, **kw: httpx.Response(200, json={"alternatives": [{"message": {"text": json.dumps(fragments)}}]}, request=httpx.Request("POST", url)))
    result = adapter.probe()
    assert result["status"] == "unavailable"
    assert result["reason"] == "output_rejected"


def test_timeout_diagnostics_do_not_echo_exception(adapter, monkeypatch):
    def post(*args, **kwargs):
        raise httpx.ReadTimeout("private key and provider details")
    monkeypatch.setattr(adapter.httpx, "post", post)
    assert adapter.probe()["reason"] == "timeout"
    assert "private" not in json.dumps(adapter.probe())


def test_neutral_russian_inflections_are_not_misclassified_as_unsafe(adapter):
    fragments = {"greeting": "Здравствуйте!", "request": "Просим сообщить планируемую дату оплаты. Благодарим вас за ваш ответ.", "closing": "С уважением,"}
    assert adapter.validate_fragments(fragments) == fragments
