"""Registration acceptance contract against real PostgreSQL transactions."""
import pytest

from test_storage_pg import postgres_config, postgres_client
from tests import test_registration_acceptance as contracts


def test_postgres_explicit_acceptance_is_atomic_and_immutable(postgres_client):
    contracts.test_explicit_registration_acceptance_is_durable_scoped_and_never_overwritten(postgres_client)


def test_postgres_registration_acceptance_rollback(postgres_client, monkeypatch):
    contracts.test_acceptance_and_registration_rollback_together_on_session_failure(postgres_client, monkeypatch)


def test_postgres_legacy_registration_does_not_invent_acceptance(postgres_client):
    contracts.test_legacy_registration_without_explicit_acceptance_does_not_invent_consent(postgres_client, {})


@pytest.mark.parametrize('fields', [
    {'terms_accepted': False}, {'terms_accepted': 1}, {'terms_accepted': 'true'},
    {'terms_accepted': 'omit'}, {'terms_version': 'omit'}, {'terms_version': '2026-11-03'},
])
def test_postgres_invalid_terms_registration_does_not_create_identity(postgres_client, fields):
    contracts.test_registration_rejects_false_coerced_unpaired_or_unknown_version_acceptance(postgres_client, fields)
