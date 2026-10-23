"""No live provider calls: HTTP boundary is replaced and payloads inspected."""
import importlib
import json
from pathlib import Path

import httpx
import pytest


@pytest.fixture
def adapter(monkeypatch):
    assert (Path(__file__).parents[1] / "server" / "llm.py").exists(), "LLM adapter not implemented"
    monkeypatch.setenv("YANDEX_API_KEY", "test-provider-key")
    monkeypatch.setenv("YANDEX_MODEL", "gpt://folder/yandexgpt-lite/latest")
    module = importlib.import_module("server.llm")
    monkeypatch.setattr(module, "_cache", {})
    return module


def provider_response(text):
    return httpx.Response(200, json={"result": {"alternatives": [{"message": {"text": text}}]}}, request=httpx.Request("POST", "https://ai.api.cloud.yandex.net/"))


def test_llm_receives_only_generic_tone_and_returns_validated_fragments(adapter, monkeypatch):
    captured = []
    fragments = {"greeting": "Добрый день!", "request": "Подскажите, пожалуйста, когда планируется оплата?", "closing": "Спасибо за сотрудничество."}

    def post(url, **kwargs):
        captured.append((url, kwargs))
        return provider_response(json.dumps(fragments))

    monkeypatch.setattr(adapter.httpx, "post", post)
    result, source = adapter.phrases("soft")
    assert result == fragments and source == "yandex"
    url, arguments = captured[0]
    assert url == "https://ai.api.cloud.yandex.net/foundationModels/v1/completion"
    assert arguments["timeout"] <= 8
    payload = json.dumps(arguments["json"], ensure_ascii=False)
    assert "soft" in payload and "email" not in payload and "ИНН" not in payload
    assert "company" not in payload and "invoice" not in payload


@pytest.mark.parametrize("result", ["not json", '{"greeting":"Привет"}',
    json.dumps({"greeting": "Здравствуйте", "request": "Оплатите 500 рублей", "closing": "Спасибо"}),
    json.dumps({"greeting": "Здравствуйте", "request": "Подадим иск в суд", "closing": "Спасибо"}),
    json.dumps({"greeting": "Здравствуйте", "request": "Откройте https://evil.ru", "closing": "Спасибо"}),
    json.dumps({"greeting": "Здравствуйте", "request": "Предлагаем скидку", "closing": "Спасибо"}),
    json.dumps({"greeting": "Здравствуйте", "request": "Оплатите сто рублей", "closing": "Спасибо"}),
    json.dumps({"greeting": "Здравствуйте", "request": "Просим оплатить миллион", "closing": "Спасибо"}),
    json.dumps({"greeting": "Здравствуйте", "request": "Мы приедем к вам завтра", "closing": "Спасибо"}),
    json.dumps({"greeting": "Здравствуйте", "request": "Прощаем оплату", "closing": "Спасибо"}),
])
def test_malformed_or_unsafe_llm_output_falls_back(adapter, monkeypatch, result):
    monkeypatch.setattr(adapter.httpx, "post", lambda *args, **kwargs: provider_response(result))
    fragments, source = adapter.phrases("firm")
    assert source == "template" and fragments["greeting"]
    assert not any(character.isdigit() for text in fragments.values() for character in text)


def test_provider_timeout_falls_back_without_exposing_secret(adapter, monkeypatch):
    def timeout(*args, **kwargs):
        raise httpx.ReadTimeout("private provider details")
    monkeypatch.setattr(adapter.httpx, "post", timeout)
    fragments, source = adapter.phrases("soft")
    assert source == "template" and "private" not in str(fragments)


def test_no_credentials_never_calls_provider(adapter, monkeypatch):
    monkeypatch.delenv("YANDEX_API_KEY")
    monkeypatch.setattr(adapter.httpx, "post", lambda *args, **kwargs: pytest.fail("Must not request provider"))
    assert adapter.configured() is False
    assert adapter.phrases("soft")[1] == "template"


def test_generic_phrases_cache_caps_provider_calls_across_tenants(adapter, monkeypatch):
    calls = []
    fragments = {"greeting": "Добрый день!", "request": "Подскажите, пожалуйста, когда планируется оплата?", "closing": "Спасибо за сотрудничество."}
    def post(*args, **kwargs):
        calls.append(kwargs["json"])
        return provider_response(json.dumps(fragments))
    monkeypatch.setattr(adapter.httpx, "post", post)
    first = adapter.phrases("soft")
    for _ in range(20):
        assert adapter.phrases("soft") == first
    assert len(calls) == 1
