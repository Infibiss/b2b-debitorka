"""Contract-level legal claims exercise the real PostgreSQL adapter too."""
from test_storage_pg import postgres_config, postgres_client
from tests.test_legal_contract_cases import (
    test_contract_claim_totals_payment_fees_and_second_invoice_staleness as _contract_scenario,
    test_cancelled_order_needs_evidence_and_blocks_enforcement as _cancellation_scenario,
    test_grouped_evidence_does_not_prove_uncovered_invoice as _coverage_scenario,
    test_grouped_initial_payment_dates_are_explicit_per_invoice as _opening_scenario,
    test_each_invoice_must_match_current_balance_even_if_offsets_cancel as _offset_scenario,
)


def test_postgres_contract_claim_keeps_finances_and_document_freshness(postgres_client,monkeypatch):
    _contract_scenario(postgres_client,monkeypatch)


def test_postgres_cancelled_order_cannot_be_enforced(postgres_client,monkeypatch):
    _cancellation_scenario(postgres_client,monkeypatch)


def test_postgres_grouped_document_coverage(postgres_client):
    _coverage_scenario(postgres_client)


def test_postgres_grouped_opening_payment_dates(postgres_client):
    _opening_scenario(postgres_client)


def test_postgres_each_invoice_claim_is_current(postgres_client):
    _offset_scenario(postgres_client)
