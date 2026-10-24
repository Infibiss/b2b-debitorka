"""An unsupported accounting export must not silently inflate an imported debt."""
import pytest

from server.csv_import import parse_csv


@pytest.mark.parametrize("header", ["оплачено", "остаток", "paid_amount", "balance", "сумма оплаты", "сальдо", "amount_paid", "outstanding_amount", "статус", "status"])
def test_unsupported_financial_columns_fail_closed_instead_of_being_ignored(header):
    content = f"контрагент;номер;дата;срок;сумма;{header}\nПоставщик;417;01.10.2026;15.10.2026;1000;400\n"
    items, errors = parse_csv(content)
    assert items == [] and errors
    assert errors[0]["row"] == 1


def test_unknown_columns_require_explicit_mapping_instead_of_silent_discard():
    content = "контрагент;номер;дата;срок;сумма;менеджер\nПоставщик;417;01.10.2026;15.10.2026;1000;Ирина\n"
    items, errors = parse_csv(content)
    assert items == [] and errors


def test_accounting_export_is_rejected_atomically_by_both_preview_and_commit(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from server.main import create_app
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "csv-audit.db"))
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("SECURE_COOKIES", "false")
    monkeypatch.setenv("APP_URL", "http://testserver")
    content = "контрагент;номер;дата;срок;сумма;оплачено;остаток\nПоставщик;417;01.10.2026;15.10.2026;1000;400;600\n"
    with TestClient(create_app(), headers={"Origin": "http://testserver"}) as client:
        response = client.post("/api/auth/register", json={"name": "Аудит", "company": "Тестовая организация", "email": "csv-audit@example.com", "password": "test-only-password-123"})
        assert response.status_code == 201
        client.headers["x-csrf-token"] = response.json()["csrf_token"]
        preview = client.post("/api/invoices/import/preview", json={"content": content})
        assert preview.status_code == 200 and preview.json()["errors"]
        assert preview.json()["items"] == []
        assert client.post("/api/invoices/import", json={"content": content}).status_code == 422
        assert client.get("/api/invoices").json()["items"] == []
