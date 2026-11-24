"""Application tariff: Mandato's fees and the lawyer's separate estimate.

This is a read-only calculation over evidenced filings and net bank allocations.
Existing agreement JSON is never migrated or repriced as a side effect of a read.

The plan in the case terms decides the pre-trial percentage (7% without a
subscription, 0% on «Бизнес» and «Объём») and whether a filed court package is
covered by the subscription. The monthly allowance is counted across the whole
organisation by the caller and passed in as `included_milestones`.
"""
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

TARIFF = json.loads(Path(__file__).with_name('fee_tariff.json').read_text(encoding='utf-8'))
FEE_FIELDS = ('fee_model_version', 'fee_plan_id', 'fee_agreement_reference', 'fee_start_on', 'lawyer_agreement_reference')


def current_model(facts):
    return (facts.get('fee_model_version') == TARIFF['version']
            and not {'pretrial_fee_percent', 'judicial_fee_percent'}.intersection(facts))


def plan_terms(facts):
    plan_id = facts.get('fee_plan_id') or TARIFF['default_plan']
    return plan_id, TARIFF['plans'].get(plan_id, TARIFF['plans'][TARIFF['default_plan']])


def kopeks(value):
    return int(value.quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def calculate_fees(facts, recovery, filings, claims, paid_amount, included_milestones=frozenset()):
    confirmed = current_model(facts)
    plan_id, terms = plan_terms(facts)
    start = facts.get('fee_start_on')
    configured = bool(confirmed and start and facts.get('fee_agreement_reference'))
    lawyer_configured = bool(configured and facts.get('lawyer_agreement_reference'))
    filed_on = min((row['occurred_on'] for row in filings), default=None)
    sent_on = min((row['occurred_on'] for row in claims), default=None)
    exact = {'mandato': Decimal(0), 'lawyer': Decimal(0)}
    excluded = dict(before_start=0, before_claim=0, ambiguous=0, lawyer_unconfigured=0)
    items = []
    recovered = 0
    for row in sorted(recovery, key=lambda item: (item['paid_on'], item['payment_id'])):
        amount = row['amount']
        if amount <= 0:
            continue
        day = row['paid_on']
        recipient, rate = None, None
        if not configured:
            stage = 'unconfigured'
        elif day < start:
            stage = 'before_start'
            excluded['before_start'] += amount
        else:
            recovered += amount
            # Calendar dates cannot establish whether a receipt precedes a
            # same-day claim/filing. Neither payee is silently awarded a fee.
            if day == filed_on or (day == sent_on and (not filed_on or day < filed_on)):
                stage = 'ambiguous'
                excluded['ambiguous'] += amount
            elif filed_on and day > filed_on:
                stage = 'judicial'
                if lawyer_configured:
                    recipient, rate = 'lawyer', TARIFF['lawyer_percent']
                else:
                    excluded['lawyer_unconfigured'] += amount
            elif not sent_on or day < sent_on:
                stage = 'before_claim'
                excluded['before_claim'] += amount
            else:
                stage = 'pretrial'
                recipient, rate = 'mandato', terms['pretrial_percent']
        part = Decimal(amount) * rate / 100 if rate is not None else Decimal(0)
        if recipient:
            exact[recipient] += part
        items.append(dict(payment_id=row['payment_id'], bank_payment_id=row['bank_payment_id'],
                          paid_on=day, amount=amount, stage=stage, recipient=recipient,
                          rate_percent=str(rate) if rate is not None else None,
                          fee_amount=kopeks(part), date_ordering_ambiguous=stage == 'ambiguous'))

    packages, seen = [], set()
    for row in sorted(filings, key=lambda item: (item['occurred_on'], item['created_at'], item['id'])):
        kind = row['kind']
        # One order package and one claim package per legal case, including
        # an explicitly grouped contract's invoices.
        # Repeated receipts and revised DOCX versions are not new paid services.
        if kind not in ('court_order', 'statement_of_claim') or kind in seen:
            continue
        seen.add(kind)
        billable = bool(configured and row['occurred_on'] >= start)
        included = billable and row['id'] in included_milestones
        packages.append(dict(kind=kind, document_id=row['document_id'], milestone_id=row['id'],
                             filed_on=row['occurred_on'], reference=row['reference'],
                             tariff_amount=TARIFF[kind + '_amount'],
                             fee_amount=TARIFF[kind + '_amount'] if billable and not included else 0,
                             billable=billable, included_in_subscription=included))
    pretrial = kopeks(exact['mandato'])
    package_total = sum(row['fee_amount'] for row in packages)
    lawyer = kopeks(exact['lawyer'])
    return dict(tariff=dict(TARIFF), plan_id=plan_id, pretrial_percent=terms['pretrial_percent'], configured=configured, lawyer_configured=lawyer_configured,
                requires_fee_model_confirmation=not confirmed,
                agreement_reference=facts.get('fee_agreement_reference', ''),
                lawyer_agreement_reference=facts.get('lawyer_agreement_reference', ''),
                claim_sent_on=sent_on, first_filed_on=filed_on,
                confirmed_recovery_amount=recovered, pretrial_fee_amount=pretrial,
                judicial_package_amount=package_total, fee_amount=pretrial + package_total,
                lawyer_fee_amount=lawyer, line_items=items, package_items=packages,
                excluded_before_start_amount=excluded['before_start'],
                excluded_before_claim_amount=excluded['before_claim'],
                ambiguous_recovery_amount=excluded['ambiguous'],
                lawyer_unconfigured_recovery_amount=excluded['lawyer_unconfigured'],
                excluded_manual_amount=max(0, paid_amount - sum(row['amount'] for row in recovery)),
                rounding_difference=pretrial - sum(row['fee_amount'] for row in items if row['recipient'] == 'mandato'),
                lawyer_rounding_difference=lawyer - sum(row['fee_amount'] for row in items if row['recipient'] == 'lawyer'),
                requires_contract_verification=True)


def first_packages(filings):
    """First filing of each package kind per case, the one that is billed."""
    first = {}
    order = lambda item: (str(item['occurred_on']), str(item['created_at']), item['id'])
    for row in sorted(filings, key=order):
        if row['kind'] in ('court_order', 'statement_of_claim'):
            first.setdefault((row['case_id'], row['kind']), row)
    return sorted(first.values(), key=order)


def included_packages(filings, plan_id):
    """Milestone ids covered by the plan's monthly allowance of court packages.

    `filings` are all filed package milestones of the organisation. The
    allowance is spent in filing order within each calendar month.
    """
    allowance = TARIFF['plans'].get(plan_id, {}).get('included_court_packages_monthly', 0)
    packages = first_packages(filings)
    if allowance is None:
        return frozenset(row['id'] for row in packages)
    used, included = {}, set()
    for row in packages:
        month = str(row['occurred_on'])[:7]
        if used.get(month, 0) < allowance:
            used[month] = used.get(month, 0) + 1
            included.add(row['id'])
    return frozenset(included)
