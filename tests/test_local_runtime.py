"""Only the explicit local entry point loads .env; environment values win."""
import importlib
import json


def test_local_env_loader_does_not_overwrite_host_environment_or_print_secrets(tmp_path, monkeypatch, capsys):
    runtime = importlib.import_module("scripts.run_local")
    path = tmp_path / ".env"
    path.write_text("YANDEX_API_KEY=private-dotenv-key\nAPP_URL=http://127.0.0.1:9999\n", encoding="utf-8")
    monkeypatch.delenv("YANDEX_API_KEY", raising=False)
    monkeypatch.setenv("APP_URL", "http://127.0.0.1:8000")
    runtime.load_local_env(path)
    import os
    assert os.environ["YANDEX_API_KEY"] == "private-dotenv-key"
    assert os.environ["APP_URL"] == "http://127.0.0.1:8000"
    assert "private" not in capsys.readouterr().out


def test_check_command_is_offline_unless_live_is_explicit(tmp_path, monkeypatch, capsys):
    check = importlib.import_module("scripts.check_llm")
    from server import llm
    path = tmp_path / ".env"
    path.write_text("YANDEX_API_KEY=private-dotenv-key\nYANDEX_MODEL=gpt://test-folder/yandexgpt-lite/latest\n", encoding="utf-8")
    monkeypatch.delenv("YANDEX_API_KEY", raising=False)
    monkeypatch.delenv("YANDEX_MODEL", raising=False)
    monkeypatch.setattr(llm.httpx, "post", lambda *a, **k: (_ for _ in ()).throw(AssertionError("Offline command made a paid call")))
    assert check.main(["--env-file", str(path)]) == 0
    output = capsys.readouterr().out
    result = json.loads(output)
    assert result["status"] == "configured_not_tested"
    assert "private" not in output and "test-folder" not in output
