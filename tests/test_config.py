"""Deployment-origin selection remains strict while Render supplies its URL."""
import pytest

from server.database import Config


@pytest.fixture
def production_environment(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECURE_COOKIES", "true")
    monkeypatch.setenv("APP_TIMEZONE", "Europe/Moscow")
    monkeypatch.delenv("APP_URL", raising=False)
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    return monkeypatch


def test_production_uses_render_generated_https_origin(production_environment):
    production_environment.setenv("RENDER_EXTERNAL_URL", "https://example.onrender.com/")
    assert Config.from_environment().app_url == "https://example.onrender.com"


def test_explicit_app_origin_overrides_render_default(production_environment):
    production_environment.setenv("RENDER_EXTERNAL_URL", "https://example.onrender.com")
    production_environment.setenv("APP_URL", "https://mandato.example.ru/")
    assert Config.from_environment().app_url == "https://mandato.example.ru"


def test_empty_app_origin_still_uses_render_default(production_environment):
    production_environment.setenv("APP_URL", "")
    production_environment.setenv("RENDER_EXTERNAL_URL", "https://example.onrender.com")
    assert Config.from_environment().app_url == "https://example.onrender.com"


@pytest.mark.parametrize("configured,render", [
    (None, "http://example.onrender.com"),
    ("http://mandato.example.ru", "https://example.onrender.com"),
    (None, None),
])
def test_production_rejects_insecure_or_missing_origin(production_environment, configured, render):
    if configured is not None:
        production_environment.setenv("APP_URL", configured)
    if render is not None:
        production_environment.setenv("RENDER_EXTERNAL_URL", render)
    with pytest.raises(RuntimeError, match="https APP_URL"):
        Config.from_environment()
