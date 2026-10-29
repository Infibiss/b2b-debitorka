"""The same UX API contracts against an isolated PostgreSQL schema."""
from test_storage_pg import postgres_config, postgres_client
from tests import test_account_help as contracts
from tests.test_account_help import no_live_service_mail


def test_postgres_recovery_atomic_consumption(postgres_client, monkeypatch):
    contracts.test_recovery_single_use_revokes_sessions_and_hides_account_existence(postgres_client, monkeypatch)


def test_postgres_mail_requests_tenant_permissions(postgres_client):
    contracts.test_mail_setup_is_durable_scoped_and_manager_only(postgres_client)


def test_postgres_contract_prefill_and_archive(postgres_client):
    contracts.test_contract_prefill_archive_and_tenant_isolation(postgres_client)
