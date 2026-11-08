"""Financing a receivable until the debtor pays.

Mandato pre-qualifies a debtor and passes an application to a financing partner
only with the client's consent. Mandato does not lend; the partner decides and
sets the final terms. Repayment is tracked from confirmed receipts.
"""
from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import Field, StrictBool, StrictInt, field_validator

from . import finance as f
from .models import Input

CATALOG = json.loads(Path(__file__).with_name('financing_catalog.json').read_text(encoding='utf-8'))
PRODUCTS = {item['id']: item for item in CATALOG['products']}
OPEN = ('requested', 'in_review', 'offer')
STATUS_LABELS = dict(requested='Заявка принята', in_review='На рассмотрении у партнёра', offer='Есть предложение', funded='Деньги выданы',
                     repaid='Погашено', declined='Отказ', withdrawn='Заявка отозвана')

SCHEMA = '''
CREATE TABLE IF NOT EXISTS financing_requests (
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id), counterparty_id TEXT NOT NULL,
 product_id TEXT NOT NULL, debtor_name TEXT NOT NULL, debtor_inn TEXT NOT NULL DEFAULT '', amount INTEGER NOT NULL CHECK(amount>0), balance_snapshot INTEGER NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('requested','in_review','offer','funded','repaid','declined','withdrawn')),
 partner TEXT NOT NULL DEFAULT '', funded_amount INTEGER, repay_amount INTEGER, funded_on TEXT, partner_note TEXT NOT NULL DEFAULT '',
 consent_at TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 FOREIGN KEY(counterparty_id,tenant_id) REFERENCES finance_counterparties(id,tenant_id)
);
CREATE INDEX IF NOT EXISTS financing_requests_tenant ON financing_requests(tenant_id,created_at);
'''


def initialize_schema(connection):
    for statement in SCHEMA.split(';'):
        if statement.strip():
            connection.execute(statement)


class FinancingRequest(Input):
    product_id: Literal[tuple(PRODUCTS)]  # type: ignore[valid-type]
    amount: Annotated[StrictInt, Field(gt=0, le=1_000_000_000_000_000)]
    consent: StrictBool

    @field_validator('consent')
    @classmethod
    def affirmative(cls, value):
        if value is not True:
            raise ValueError('Нужно согласие на передачу данных партнёру')
        return value


def part(amount, percent):
    return int((Decimal(amount) * Decimal(percent) / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def annual_rate(product):
    return None if not product['margin_percent'] else str(Decimal(CATALOG['key_rate_percent']) + Decimal(product['margin_percent']))


def assess(product, view, *, solvency_state, has_court_act):
    """Rejection reasons are shown to the client, so each one states what to fix."""
    reasons = []
    if view['stage'] not in product['stages']:
        reasons.append('Не подходит для текущего этапа взыскания')
    if view['status'] == 'dispute':
        reasons.append('Спор с должником нужно снять')
    if view['balance'] < product['min_amount']:
        reasons.append('Сумма долга меньше минимальной')
    if view['days_overdue'] > product['max_days_overdue']:
        reasons.append('Просрочка слишком большая для этого продукта')
    if view['evidence_score'] < product['min_evidence_score']:
        reasons.append('Загрузите договор и документы об исполнении')
    if solvency_state in ('stop', 'risk'):
        reasons.append('Должник ликвидируется или признан банкротом')
    if product.get('requires_court_act') and not has_court_act:
        reasons.append('Нужен вступивший в силу судебный акт')
    return reasons


def offers(connection, tenant, view, solvency, today):
    state = view['_state']
    active = connection.execute("SELECT id FROM financing_requests WHERE tenant_id=? AND counterparty_id=? AND status IN ('requested','in_review','offer','funded')", (tenant, view['id'])).fetchone()
    items = []
    for product in CATALOG['products']:
        reasons = assess(product, view, solvency_state=solvency['state'], has_court_act=bool(state.get('has_court_act')))
        low, high = product['advance_percent']
        items.append(dict(id=product['id'], name=product['name'], summary=product['summary'], eligible=not reasons and not active, reasons=reasons,
                          advance_percent=[low, high], amount_from=part(view['balance'], low), amount_to=part(view['balance'], high), annual_rate_percent=annual_rate(product)))
    return dict(items=items, has_active_request=bool(active), key_rate_percent=CATALOG['key_rate_percent'])


def repaid_amount(connection, tenant, row):
    """Confirmed receipts from this debtor after funding reduce what the partner is owed."""
    if not row['funded_on']:
        return 0
    return connection.execute('''SELECT COALESCE(SUM(p.amount-p.reversed_amount),0) AS amount FROM payments p JOIN invoices i ON i.id=p.invoice_id AND i.tenant_id=p.tenant_id
        WHERE p.tenant_id=? AND i.counterparty_id=? AND p.paid_on>=? AND p.bank_payment_id IS NOT NULL''', (tenant, row['counterparty_id'], row['funded_on'])).fetchone()['amount']


def view_request(connection, row):
    item = {key: row[key] for key in ('id', 'counterparty_id', 'product_id', 'debtor_name', 'debtor_inn', 'amount', 'balance_snapshot', 'status', 'partner', 'funded_amount', 'repay_amount', 'funded_on', 'partner_note', 'created_at', 'updated_at')}
    product = PRODUCTS[row['product_id']]
    repaid = repaid_amount(connection, row['tenant_id'], row)
    owed = row['repay_amount'] or 0
    return item | dict(product_name=product['name'], status_label=STATUS_LABELS[row['status']], repaid_amount=min(repaid, owed) if owed else repaid, remaining_amount=max(0, owed - repaid) if owed else None, surplus_to_client=max(0, repaid - owed) if owed else None)


def create_router(ctx):
    router = APIRouter(prefix='/api/financing', tags=['financing'])

    @router.get('/catalog')
    def catalog(user=Depends(ctx.get_user)):
        return CATALOG

    @router.get('/requests')
    def requests(user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as c:
            rows = c.execute('SELECT * FROM financing_requests WHERE tenant_id=? ORDER BY created_at DESC,id', (user['tenant_id'],)).fetchall()
            return dict(items=[view_request(c, row) for row in rows])

    @router.post('/debtors/{debtor_id}/requests', status_code=201)
    def create(debtor_id: str, data: FinancingRequest, user=Depends(ctx.get_user)):
        from . import recovery
        from . import recovery_rules as rules
        if user['role'] != 'manager':
            ctx.problem(403, 'Заявку на финансирование подаёт руководитель')
        tenant, product = user['tenant_id'], PRODUCTS[data.product_id]
        with ctx.database(ctx.config, write=True) as c:
            context = recovery.tenant_context(c, tenant)
            invoices = recovery.debtor_rows(c, tenant).get(debtor_id)
            if invoices is None:
                ctx.problem(404, 'Должник не найден')
            view = recovery.summarize(debtor_id, invoices, context)
            if c.execute("SELECT id FROM financing_requests WHERE tenant_id=? AND counterparty_id=? AND status IN ('requested','in_review','offer','funded')", (tenant, debtor_id)).fetchone():
                ctx.problem(409, 'По этому должнику уже есть активная заявка')
            solvency = rules.solvency_report(context['checks'].get(view['inn']))
            reasons = assess(product, view, solvency_state=solvency['state'], has_court_act=bool(view['_state'].get('has_court_act')))
            if reasons:
                ctx.problem(409, reasons[0])
            ceiling = part(view['balance'], product['advance_percent'][1])
            if data.amount > ceiling:
                ctx.problem(422, 'Сумма больше доступного лимита')
            request_id, stamp = f.uid(), ctx.now()
            c.execute('''INSERT INTO financing_requests(id,tenant_id,counterparty_id,product_id,debtor_name,debtor_inn,amount,balance_snapshot,status,consent_at,created_by,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,'requested',?,?,?,?)''', (request_id, tenant, debtor_id, data.product_id, view['name'], view['inn'], data.amount, view['balance'], stamp, user['id'], stamp, stamp))
            return view_request(c, c.execute('SELECT * FROM financing_requests WHERE id=?', (request_id,)).fetchone())

    @router.post('/requests/{request_id}/withdraw')
    def withdraw(request_id: str, data: Input, user=Depends(ctx.get_user)):
        if user['role'] != 'manager':
            ctx.problem(403, 'Заявку отзывает руководитель')
        with ctx.database(ctx.config, write=True) as c:
            row = c.execute('SELECT * FROM financing_requests WHERE id=? AND tenant_id=?', (request_id, user['tenant_id'])).fetchone()
            if not row:
                ctx.problem(404, 'Заявка не найдена')
            if row['status'] not in OPEN:
                ctx.problem(409, 'Эту заявку уже нельзя отозвать')
            c.execute("UPDATE financing_requests SET status='withdrawn',updated_at=? WHERE id=?", (ctx.now(), request_id))
            return view_request(c, c.execute('SELECT * FROM financing_requests WHERE id=?', (request_id,)).fetchone())

    return router
