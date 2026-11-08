"""Money and phase boundaries of the application tariff, without external I/O."""
import pytest

from server.legal_fees import TARIFF, calculate_fees


def terms(**changes):
    return dict(fee_model_version=TARIFF['version'], fee_agreement_reference='Mandato agreement',
                fee_start_on='2026-08-01', lawyer_agreement_reference='Separate lawyer agreement', **changes)


def receipt(day, amount=1_000_000, key='receipt'):
    return dict(payment_id=key, bank_payment_id='bank-' + key, paid_on=day, amount=amount)


def filing(kind='court_order', key='filing', day='2026-10-20'):
    return dict(id=key, document_id='doc-' + key, kind=kind, occurred_on=day,
                created_at=day + 'T12:00:00Z', reference='Receipt ' + key)


def calculate(recovery=(), filings=(), claims=(), facts=None):
    return calculate_fees(terms() if facts is None else facts, list(recovery), list(filings),
                          [dict(occurred_on=day) for day in claims], sum(row['amount'] for row in recovery))


@pytest.mark.parametrize('day,stage,mandato,lawyer', [
    ('2026-07-31', 'before_start', 0, 0),
    ('2026-10-09', 'before_claim', 0, 0),
    ('2026-10-10', 'ambiguous', 0, 0),
    ('2026-10-11', 'pretrial', 80_000, 0),
    ('2026-10-20', 'ambiguous', 0, 0),
    ('2026-10-21', 'judicial', 0, 120_000),
])
def test_recovery_phase_never_moves_lawyer_income_into_mandato(day, stage, mandato, lawyer):
    result = calculate([receipt(day)], [filing()], ['2026-10-10'])
    assert result['line_items'][0]['stage'] == stage
    assert result['pretrial_fee_amount'] == mandato
    assert result['lawyer_fee_amount'] == lawyer
    assert result['fee_amount'] == 990_000 + mandato


def test_no_claim_means_no_pretrial_percentage_but_order_still_has_its_fixed_price():
    result = calculate([receipt('2026-10-19'), receipt('2026-10-21', key='later')], [filing()])
    assert result['excluded_before_claim_amount'] == 1_000_000
    assert result['pretrial_fee_amount'] == 0
    assert result['lawyer_fee_amount'] == 120_000
    assert result['fee_amount'] == 990_000


def test_lawyer_requires_a_separate_agreement_even_when_mandato_is_configured():
    facts = terms(); facts['lawyer_agreement_reference'] = ''
    result = calculate([receipt('2026-10-21')], [filing()], facts=facts)
    assert result['configured'] is True and result['lawyer_configured'] is False
    assert result['fee_amount'] == 990_000 and result['lawyer_fee_amount'] == 0
    assert result['lawyer_unconfigured_recovery_amount'] == 1_000_000


def test_each_filed_package_kind_is_counted_once_independently_of_recovery_or_versions():
    filings = [filing(), filing(key='same-package-v2'), filing('statement_of_claim', 'lawsuit')]
    result = calculate(filings=filings)
    assert result['fee_amount'] == result['judicial_package_amount'] == 2_480_000
    assert result['lawyer_fee_amount'] == result['pretrial_fee_amount'] == 0
    assert len(result['package_items']) == 2
    assert calculate()['judicial_package_amount'] == 0


def test_filings_before_the_agreement_are_not_rebilled_by_a_later_revision():
    filings = [filing(day='2026-07-31'), filing(key='revision')]
    result = calculate(filings=filings)
    assert result['fee_amount'] == 0
    assert result['package_items'][0]['billable'] is False


@pytest.mark.parametrize('field,value', [
    ('fee_agreement_reference', ''), ('fee_start_on', None),
    ('fee_model_version', None), ('judicial_fee_percent', '15'),
])
def test_missing_or_legacy_terms_never_silently_reprice_existing_cases(field, value):
    facts = terms(); facts[field] = value
    original = dict(facts)
    result = calculate([receipt('2026-10-21')], [filing()], ['2026-10-10'], facts=facts)
    assert result['configured'] is False
    assert result['fee_amount'] == result['lawyer_fee_amount'] == 0
    assert facts == original


def test_refunded_allocations_reduce_percentages_but_not_the_price_of_filed_work():
    full = calculate([receipt('2026-10-15'), receipt('2026-10-21', key='later')], [filing()], ['2026-10-10'])
    partial = calculate([receipt('2026-10-15', 500_000), receipt('2026-10-21', 500_000, 'later')], [filing()], ['2026-10-10'])
    refunded = calculate([receipt('2026-10-15', 0), receipt('2026-10-21', 0, 'later')], [filing()], ['2026-10-10'])
    assert (full['pretrial_fee_amount'], partial['pretrial_fee_amount'], refunded['pretrial_fee_amount']) == (80_000, 40_000, 0)
    assert (full['lawyer_fee_amount'], partial['lawyer_fee_amount'], refunded['lawyer_fee_amount']) == (120_000, 60_000, 0)
    assert all(result['judicial_package_amount'] == 990_000 for result in [full, partial, refunded])


def test_each_payee_is_rounded_independently_without_floats():
    recovery = [receipt('2026-10-15', 8, 'pre1'), receipt('2026-10-15', 8, 'pre2'),
                receipt('2026-10-21', 4, 'post1'), receipt('2026-10-21', 4, 'post2')]
    result = calculate(recovery, [filing()], ['2026-10-10'])
    assert result['pretrial_fee_amount'] == result['lawyer_fee_amount'] == 1
    assert result['rounding_difference'] == -1 and result['lawyer_rounding_difference'] == 1
    assert result['fee_amount'] == 990_001
