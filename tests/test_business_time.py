"""Business dates follow the configured IANA zone, independently of host TZ."""
import importlib
from datetime import datetime, timezone
from pathlib import Path

import pytest


def clock_module():
    assert (Path(__file__).parents[1] / "server" / "business_time.py").exists(), "Central business clock not implemented"
    return importlib.import_module("server.business_time")


@pytest.mark.parametrize("utc_time,expected", [
    ("2026-10-24T20:59:59+00:00", "2026-10-24"),
    ("2026-10-24T21:00:00+00:00", "2026-10-25"),
    ("2026-10-24T21:30:00+00:00", "2026-10-25"),
    ("2026-12-31T21:30:00+00:00", "2027-01-01"),
])
def test_actual_moscow_conversion_crosses_midnight_at_utc_21(utc_time, expected, monkeypatch):
    module = clock_module()
    monkeypatch.delenv("APP_TIMEZONE", raising=False)
    instant = datetime.fromisoformat(utc_time)
    assert str(module.business_today(instant)) == expected


def test_business_timezone_override_does_not_depend_on_host_timezone(monkeypatch):
    module = clock_module()
    instant = datetime(2026, 10, 24, 21, 30, tzinfo=timezone.utc)
    monkeypatch.setenv("APP_TIMEZONE", "UTC")
    assert str(module.business_today(instant)) == "2026-10-24"
    monkeypatch.setenv("APP_TIMEZONE", "Europe/Moscow")
    assert str(module.business_today(instant)) == "2026-10-25"


def test_invalid_timezone_fails_at_app_configuration(monkeypatch):
    clock_module()
    from server.database import Config
    monkeypatch.setenv("APP_TIMEZONE", "Definitely/NotAZone")
    with pytest.raises(RuntimeError, match="APP_TIMEZONE"):
        Config.from_environment()


def test_business_clock_rejects_ambiguous_naive_instants():
    module = clock_module()
    with pytest.raises(ValueError, match="timezone-aware"):
        module.business_today(datetime(2026, 10, 24, 21, 30))
