def test_delivery_check_uses_current_v2_api_with_bounded_time_and_io_fields(monkeypatch):
    import httpx
    from scripts.langfuse_local import observations_for_trace
    captured = {}
    def get(url, **kwargs):
        captured.update(url=url, **kwargs)
        return httpx.Response(200, json={"data": [{"traceId": "opaque", "model": "synthetic-fixture", "input": None, "output": None}]})
    monkeypatch.setattr(httpx, "get", get)
    settings = {"LANGFUSE_BASE_URL": "http://127.0.0.1:3033", "LANGFUSE_PUBLIC_KEY": "synthetic", "LANGFUSE_SECRET_KEY": "synthetic"}
    assert observations_for_trace(settings, "opaque", "2026-10-24T00:00:00Z", "2026-10-25T00:00:00Z")[0]["traceId"] == "opaque"
    assert captured["url"].endswith("/api/public/v2/observations")
    assert captured["params"]["traceId"] == "opaque"
    assert "io" in captured["params"]["fields"]
    assert captured["params"]["fromStartTime"] and captured["params"]["toStartTime"]


def test_run_app_uses_actual_local_launcher_cli(monkeypatch):
    from scripts import langfuse_local
    captured = []
    monkeypatch.setattr(langfuse_local, "values", lambda: {"LANGFUSE_PUBLIC_KEY": "pk-synthetic", "LANGFUSE_SECRET_KEY": "sk-synthetic", "LANGFUSE_BASE_URL": "http://localhost:3033"})
    monkeypatch.setattr(langfuse_local.os, "execv", lambda executable, argv: captured.extend(argv))
    for key in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL"):
        monkeypatch.setenv(key, "")
    langfuse_local.run_application()
    assert captured[1:] == ["-m", "scripts.run_local"]


def test_delivery_check_reports_storage_resource_failure(monkeypatch):
    import httpx
    import pytest
    from scripts.langfuse_local import observations_for_trace
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(429, json={"message": "synthetic storage limit"}))
    settings = {"LANGFUSE_BASE_URL": "http://127.0.0.1:3033", "LANGFUSE_PUBLIC_KEY": "synthetic", "LANGFUSE_SECRET_KEY": "synthetic"}
    with pytest.raises(RuntimeError, match="429"):
        observations_for_trace(settings, "opaque", "2026-10-24T00:00:00Z", "2026-10-25T00:00:00Z")
