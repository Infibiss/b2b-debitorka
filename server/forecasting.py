"""Conservative, current-date cash scenarios from observed bank allocations.

No fitted ML model or calibrated confidence is claimed. Historical mutable
opening balances and source revisions cannot provide point-in-time labels.
"""
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from fractions import Fraction

from fastapi import APIRouter, Depends

from . import finance as f
from .business_time import business_today, business_timezone

METHOD = 'empirical_due_cohort_v1'
HORIZONS = (7, 30, 60)
MIN_COHORT = 5
MIN_BANK_ALLOCATIONS = 3
LOOKBACK_DAYS = 730


def initialize_schema(connection):
    # The baseline reads the financial ledger and requires no parallel ledger.
    pass


def _known_at(value, cutoff):
    if isinstance(value, (tuple, list)):
        return all(_known_at(item, cutoff) for item in value)
    try:
        observed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=business_timezone())
        return observed <= cutoff
    except (ValueError, TypeError, AttributeError):
        return False


def _end_of(day):
    return datetime.combine(day, time.max, business_timezone())


def cash_forecast(c, tenant_id):
    today = business_today()
    cutoff = datetime.now(timezone.utc)
    invoices = [dict(row) for row in c.execute('SELECT * FROM invoices WHERE tenant_id=? ORDER BY id', (tenant_id,))]
    counterparties = {row['id']: dict(row) for row in c.execute('SELECT * FROM finance_counterparties WHERE tenant_id=?', (tenant_id,))}
    payments = [dict(row) for row in c.execute('''SELECT p.*,b.confirmed,b.created_at AS bank_created_at,b.paid_on AS bank_paid_on
        FROM payments p LEFT JOIN finance_bank_payments b ON b.id=p.bank_payment_id AND b.tenant_id=p.tenant_id
        WHERE p.tenant_id=? ORDER BY p.paid_on,p.id''', (tenant_id,))]
    reversals = [dict(row) for row in c.execute('SELECT * FROM finance_reversals WHERE tenant_id=? ORDER BY effective_on,id', (tenant_id,))]
    unsuitable = {row['invoice_id'] for row in c.execute('SELECT invoice_id FROM finance_adjustments WHERE tenant_id=?', (tenant_id,))}
    unsuitable.update(row['invoice_id'] for row in c.execute("SELECT invoice_id FROM events WHERE tenant_id=? AND type='import_reconciled'", (tenant_id,)))
    unsuitable.update(row['invoice_id'] for row in payments if not row['bank_payment_id'])
    valid_payments = {}
    invoice_payment_ids = defaultdict(set)
    temporal_unknown = set()
    timelines = defaultdict(list)
    for row in payments:
        if (row['confirmed'] != 1 or not row['bank_payment_id'] or row['paid_on'] > str(today)
                or row['bank_paid_on'] > str(today) or row['paid_on'] != row['bank_paid_on']
                or not _known_at(row['created_at'], cutoff) or not _known_at(row['bank_created_at'], cutoff)):
            temporal_unknown.add(row['invoice_id'])
            continue
        valid_payments[row['id']] = row
        invoice_payment_ids[row['invoice_id']].add(row['id'])
        timelines[row['invoice_id']].append(dict(day=date.fromisoformat(row['paid_on']), amount=row['amount'], known=(row['created_at'], row['bank_created_at']), source=row['id']))
    for row in reversals:
        if row['effective_on'] > str(today) or not _known_at(row['created_at'], cutoff):
            temporal_unknown.add(row['invoice_id'])
        if row['payment_id'] in valid_payments and row['effective_on'] <= str(today) and _known_at(row['created_at'], cutoff):
            timelines[row['invoice_id']].append(dict(day=date.fromisoformat(row['effective_on']), amount=-row['amount'], known=(row['created_at'], valid_payments[row['payment_id']]['created_at'], valid_payments[row['payment_id']]['bank_created_at']), source=row['id']))
    mature = [row for row in invoices if not row['opening_paid_amount'] and row['id'] not in unsuitable
              and row['issued_on'] <= str(today) and row['due_on'] >= str(today-timedelta(days=LOOKBACK_DAYS))
              and _known_at(row['created_at'], cutoff)]
    totals = {h: dict(expected=0, low=0, high=0) for h in HORIZONS}
    open_balance = eligible_balance = covered_balance = 0
    details = []
    training_ids = set()
    cohort_cache = {}
    for inv in invoices:
        remaining = max(0, f.balance(inv))
        if not remaining:
            continue
        open_balance += remaining
        cp = counterparties.get(inv['counterparty_id'], {})
        reasons = []
        if inv['status'] in ('paused', 'disputed') or cp.get('hold') or not cp.get('contact_allowed', 0):
            reasons.append('held_or_disputed')
        if inv['issued_on'] > str(today) or not _known_at(inv['created_at'], cutoff):
            reasons.append('not_yet_available')
        if inv['opening_paid_amount'] or inv['id'] in unsuitable:
            reasons.append('unreconstructible_history')
        if inv['id'] in temporal_unknown:
            reasons.append('temporal_history_unavailable')
        if reasons:
            details.append(dict(invoice_id=inv['id'], status='excluded', reasons=reasons))
            continue
        eligible_balance += remaining
        age = (today-date.fromisoformat(inv['due_on'])).days
        if age not in cohort_cache:
            cohort = []
            cohort_payment_ids = set()
            for old in mature:
                anchor = date.fromisoformat(old['due_on'])+timedelta(days=age)
                if anchor < date.fromisoformat(old['issued_on']) or _end_of(anchor+timedelta(days=max(HORIZONS))) > cutoff:
                    continue
                if not _known_at(old['created_at'], _end_of(anchor)):
                    continue
                events = timelines[old['id']]
                starting = old['amount']-sum(item['amount'] for item in events if item['day'] <= anchor and _known_at(item['known'], _end_of(anchor)))
                if starting <= 0:
                    continue
                fractions = {}
                for h in HORIZONS:
                    net = sum(item['amount'] for item in events if anchor < item['day'] <= anchor+timedelta(days=h))
                    # Refunds reduce labels in the window in which they occur.
                    fractions[h] = Fraction(min(starting, max(0, net)), starting)
                cohort.append((old, starting, fractions))
                cohort_payment_ids.update(invoice_payment_ids[old['id']])
            cohort_cache[age] = (cohort, cohort_payment_ids)
        cohort, cohort_payment_ids = cohort_cache[age]
        if len(cohort) < MIN_COHORT or len(cohort_payment_ids) < MIN_BANK_ALLOCATIONS:
            details.append(dict(invoice_id=inv['id'], status='abstained', reasons=['insufficient_comparable_history'], training_invoices=len(cohort)))
            continue
        covered_balance += remaining
        training_ids.update(row['id'] for row, _, _ in cohort)
        denominators = sum(starting for _, starting, _ in cohort)
        item_horizons = []
        for h in HORIZONS:
            ratio = sum(starting*fractions[h] for _, starting, fractions in cohort)/denominators
            expected = int(remaining*ratio)
            low = int(remaining*min(fractions[h] for _, _, fractions in cohort))
            high = int(remaining*max(fractions[h] for _, _, fractions in cohort))
            totals[h]['expected'] += expected
            totals[h]['low'] += low
            totals[h]['high'] += high
            item_horizons.append(dict(days=h, expected_amount=expected, low_scenario=low, high_scenario=high))
        details.append(dict(invoice_id=inv['id'], status='available', training_invoices=len(cohort), horizons=item_horizons))
    available = covered_balance > 0
    return dict(as_of=str(today), generated_at=cutoff.isoformat(), method=METHOD, status='available' if available else 'abstained',
        reason=None if available else 'insufficient_comparable_history', unit='kopeks',
        horizons=[dict(days=h, expected_amount=totals[h]['expected'] if available else None,
            low_scenario=totals[h]['low'] if available else None, high_scenario=totals[h]['high'] if available else None) for h in HORIZONS],
        coverage=dict(open_balance=open_balance, eligible_balance=eligible_balance, covered_balance=covered_balance,
            training_invoices=len(training_ids), bank_allocations=len(valid_payments), excluded_balance=open_balance-eligible_balance,
            uncovered_balance=eligible_balance-covered_balance),
        evidence=dict(source='confirmed_dated_bank_allocations', allocation_ids=sorted(valid_payments),
            cohort_invoice_ids=sorted(training_ids), cutoff=cutoff.isoformat(), minimum_cohort=MIN_COHORT,
            minimum_bank_allocations=MIN_BANK_ALLOCATIONS, lookback_days=LOOKBACK_DAYS,
            cohort='same_days_relative_to_due_date; fully_observed_60_day_window; tenant_only',
            observed_at_and_effective_date_checked=True, includes_unpaid_cohort_members=True),
        limitations=['Эмпирический сценарий, не обученная ML-модель и не гарантия поступлений.',
            'Границы — минимум и максимум наблюдавшихся долей, не калиброванный доверительный интервал.',
            'Прогноз относится только к покрытому остатку. Недостаточная история означает отказ от оценки.',
            'Начальные оплаты, ручные платежи, корректировки и пересогласованные источники исключены.',
            'Сценарий чистых поступлений учитывает датированные возвраты; исторический прогноз на прошлую дату недоступен.'],
        invoices=details)


def create_router(ctx):
    router = APIRouter(prefix='/api', tags=['forecast'])

    @router.get('/forecast')
    def get_forecast(as_of: date | None = None, user=Depends(ctx.get_user)):
        if as_of is not None and as_of != business_today():
            f.fail(422, 'Доступен прогноз только на текущую дату: исторический снимок портфеля отсутствует')
        with ctx.database(ctx.config) as c:
            return cash_forecast(c, user['tenant_id'])

    return router
