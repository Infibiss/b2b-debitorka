"""Tenant commercial records and an explicitly simulated payment adapter.

No bank/card credentials, provider calls, fiscal receipts or receivables entries.
Future adapters must independently verify provider payments before granting access.
"""
import calendar
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, Protocol

from fastapi import APIRouter, Depends
from pydantic import Field, StrictBool, field_validator

from .models import Input, single_line, valid_email

CATALOG = json.loads(Path(__file__).with_name('plan_catalog.json').read_text())
PLANS = {item['id']: item for item in CATALOG['items']}
TRIAL_PLAN = 'team'

SCHEMA = '''
CREATE TABLE IF NOT EXISTS registration_acceptances (
 user_id TEXT PRIMARY KEY REFERENCES users(id), tenant_id TEXT NOT NULL REFERENCES tenants(id),
 terms_version TEXT NOT NULL, accepted_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS commercial_requests (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('demo','custom')),
 name TEXT NOT NULL, email TEXT NOT NULL, company TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL CHECK(status='requested'), consent_at TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS commercial_accounts (
 tenant_id TEXT PRIMARY KEY REFERENCES tenants(id),
 state TEXT NOT NULL CHECK(state IN ('none','trial','sandbox_active','canceled')),
 plan_id TEXT, plan_snapshot TEXT, trial_started_at TEXT, trial_ends_at TEXT,
 subscription_started_at TEXT, subscription_ends_at TEXT, active_order_id TEXT,
 canceled_at TEXT, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS commercial_orders (
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id),
 created_by TEXT NOT NULL REFERENCES users(id), idempotency_key TEXT NOT NULL,
 plan_id TEXT NOT NULL, plan_name TEXT NOT NULL, amount INTEGER NOT NULL CHECK(amount>0),
 currency TEXT NOT NULL, billing_period TEXT NOT NULL, plan_snapshot TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('pending','sandbox_confirmed','canceled')),
 payment_mode TEXT NOT NULL CHECK(payment_mode='sandbox'), provider_reference TEXT,
 consent_at TEXT NOT NULL, created_at TEXT NOT NULL, confirmed_at TEXT, canceled_at TEXT,
 UNIQUE(tenant_id,idempotency_key)
);
CREATE INDEX IF NOT EXISTS commercial_orders_tenant ON commercial_orders(tenant_id,created_at);
CREATE TABLE IF NOT EXISTS commercial_deletion_requests (
 tenant_id TEXT PRIMARY KEY REFERENCES tenants(id), id TEXT NOT NULL UNIQUE,
 created_by TEXT NOT NULL REFERENCES users(id), status TEXT NOT NULL CHECK(status='requested'),
 consent_at TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS commercial_request_handling (
 request_id TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('demo','custom','deletion')),
 status TEXT NOT NULL CHECK(status='handled'), owner TEXT NOT NULL,
 reference TEXT NOT NULL, handled_at TEXT NOT NULL,
 PRIMARY KEY(kind,request_id)
);
'''


def initialize_schema(connection):
    for statement in SCHEMA.split(';'):
        if statement.strip():
            connection.execute(statement)


class Consent(Input):
    consent: StrictBool

    @field_validator('consent')
    @classmethod
    def affirmative(cls, value):
        if value is not True:
            raise ValueError('Необходимо явное согласие')
        return value


class CommercialRequest(Consent):
    kind: Literal['demo', 'custom']
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(max_length=254)
    company: str = Field(default='', max_length=200)
    note: str = Field(default='', max_length=2000)

    @field_validator('name', 'company')
    @classmethod
    def clean_line(cls, value):
        return single_line(value)

    @field_validator('email')
    @classmethod
    def mailbox(cls, value):
        return valid_email(value)


class OrderRequest(Consent):
    plan_id: Literal['start', 'team', 'scale']
    idempotency_key: str = Field(min_length=8, max_length=100, pattern=r'^[A-Za-z0-9_.:-]+$')


class DeletionRequest(Consent):
    confirmation: Literal['УДАЛИТЬ']


class PaymentAdapter(Protocol):
    """Provider boundary; real adapters require verified server-side callbacks.

    Only sandbox is registered. A future checkout adapter must implement a
    separate authenticated webhook, verify amount/currency and replay protection,
    and introduce a real payment state. It must not reuse sandbox-confirm.
    """
    mode: str

    def confirm(self, order: dict) -> str: ...


class SandboxPaymentAdapter:
    mode = 'sandbox'

    def confirm(self, order):
        return 'sandbox:' + order['id']


def payment_adapter(ctx) -> PaymentAdapter:
    # Explicitly fail closed if an operator tries selecting an unimplemented
    # provider. No environment switch can silently enable real billing.
    if os.getenv('COMMERCIAL_PAYMENT_MODE', 'sandbox') != 'sandbox':
        ctx.problem(503, 'Платёжный провайдер пока не подключён. Доступен только тестовый сценарий.')
    return SandboxPaymentAdapter()


ORDER_FIELDS = ('id', 'plan_id', 'plan_name', 'amount', 'currency', 'billing_period',
                'status', 'payment_mode', 'created_at', 'confirmed_at', 'canceled_at')


def order_view(row):
    return {key: row[key] for key in ORDER_FIELDS}


def next_month(stamp):
    value = datetime.fromisoformat(stamp)
    year, month = (value.year + 1, 1) if value.month == 12 else (value.year, value.month + 1)
    return value.replace(year=year, month=month, day=min(value.day, calendar.monthrange(year, month)[1])).isoformat(timespec='microseconds')


def create_router(ctx):
    router = APIRouter(prefix='/api/commercial')

    def manager(user):
        if user['role'] != 'manager':
            ctx.problem(403, 'Управление тарифом и аккаунтом доступно только руководителю')

    def ensure_account(c, tenant_id):
        c.execute("INSERT INTO commercial_accounts(tenant_id,state,updated_at) VALUES(?,'none',?) ON CONFLICT(tenant_id) DO NOTHING", (tenant_id, ctx.now()))

    def account_view(c, user):
        row = c.execute('SELECT * FROM commercial_accounts WHERE tenant_id=?', (user['tenant_id'],)).fetchone()
        status = row['state'] if row else 'none'
        stamp = ctx.now()
        if status == 'trial' and row['trial_ends_at'] <= stamp:
            status = 'trial_expired'
        if status == 'sandbox_active' and row['subscription_ends_at'] <= stamp:
            status = 'sandbox_expired'
        subscription = None
        if row and row['subscription_started_at']:
            subscription = {'plan_id': row['plan_id'], 'status': status, 'started_at': row['subscription_started_at'],
                            'ends_at': row['subscription_ends_at'], 'order_id': row['active_order_id'], 'auto_renew': False}
        deletion = c.execute('SELECT id,status,created_at FROM commercial_deletion_requests WHERE tenant_id=?', (user['tenant_id'],)).fetchone()
        return {'payment_mode': 'sandbox', 'can_manage': user['role'] == 'manager',
                'plan': json.loads(row['plan_snapshot']) if row and row['plan_snapshot'] else None,
                'status': status,
                'trial': {'days': CATALOG['trial_days'], 'started_at': row['trial_started_at'] if row else None,
                          'ends_at': row['trial_ends_at'] if row else None,
                          'available': not row or (not row['trial_started_at'] and row['state'] == 'none')},
                'subscription': subscription,
                'orders': [order_view(order) for order in c.execute('SELECT * FROM commercial_orders WHERE tenant_id=? ORDER BY created_at DESC,id', (user['tenant_id'],))],
                'deletion_request': dict(deletion) if deletion else None}

    def find_order(c, user, order_id):
        row = c.execute('SELECT * FROM commercial_orders WHERE tenant_id=? AND id=?', (user['tenant_id'], order_id)).fetchone()
        if not row:
            ctx.problem(404, 'Заказ не найден')
        return row

    @router.get('/plans')
    def plans():
        return CATALOG

    @router.post('/requests', status_code=201)
    def request_demo(data: CommercialRequest):
        stamp, request_id = ctx.now(), ctx.identifier()
        with ctx.database(ctx.config, write=True) as c:
            c.execute("INSERT INTO commercial_requests VALUES(?,?,?,?,?,?,'requested',?,?)", (request_id, data.kind, data.name, data.email, data.company, data.note, stamp, stamp))
        return {'id': request_id, 'kind': data.kind, 'status': 'requested', 'created_at': stamp}

    @router.get('/account')
    def account(user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as c:
            return account_view(c, user)

    @router.post('/trial')
    def start_trial(data: Input, user=Depends(ctx.get_user)):
        manager(user)
        with ctx.database(ctx.config, write=True) as c:
            ensure_account(c, user['tenant_id'])
            row = c.execute('SELECT * FROM commercial_accounts WHERE tenant_id=?', (user['tenant_id'],)).fetchone()
            if row['trial_started_at'] or row['state'] != 'none':
                ctx.problem(409, 'Пробный период доступен один раз до подключения тарифа')
            stamp = ctx.now()
            end = (datetime.fromisoformat(stamp) + timedelta(days=CATALOG['trial_days'])).isoformat(timespec='microseconds')
            c.execute("UPDATE commercial_accounts SET state='trial',plan_id=?,plan_snapshot=?,trial_started_at=?,trial_ends_at=?,updated_at=? WHERE tenant_id=?", (TRIAL_PLAN, json.dumps(PLANS[TRIAL_PLAN], ensure_ascii=False), stamp, end, stamp, user['tenant_id']))
            return account_view(c, user)

    @router.post('/orders', status_code=201)
    def create_order(data: OrderRequest, user=Depends(ctx.get_user)):
        manager(user)
        adapter = payment_adapter(ctx)
        with ctx.database(ctx.config, write=True) as c:
            existing = c.execute('SELECT * FROM commercial_orders WHERE tenant_id=? AND idempotency_key=?', (user['tenant_id'], data.idempotency_key)).fetchone()
            if existing:
                if existing['plan_id'] != data.plan_id:
                    ctx.problem(409, 'Ключ заказа уже использован для другого тарифа')
                return order_view(existing)
            plan, stamp, order_id = PLANS[data.plan_id], ctx.now(), ctx.identifier()
            c.execute("INSERT INTO commercial_orders(id,tenant_id,created_by,idempotency_key,plan_id,plan_name,amount,currency,billing_period,plan_snapshot,status,payment_mode,consent_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,'pending',?,?,?)", (order_id, user['tenant_id'], user['id'], data.idempotency_key, plan['id'], plan['name'], plan['price_monthly'], plan['currency'], plan['billing_period'], json.dumps(plan, ensure_ascii=False), adapter.mode, stamp, stamp))
            return order_view(find_order(c, user, order_id))

    @router.post('/orders/{order_id}/sandbox-confirm')
    def confirm_order(order_id: str, data: Input, user=Depends(ctx.get_user)):
        manager(user)
        adapter = payment_adapter(ctx)
        with ctx.database(ctx.config, write=True) as c:
            row = find_order(c, user, order_id)
            if row['status'] == 'canceled':
                ctx.problem(409, 'Отменённый заказ нельзя подтвердить')
            if row['status'] == 'pending':
                if row['payment_mode'] != adapter.mode or adapter.mode != 'sandbox':
                    ctx.problem(409, 'Заказ не относится к тестовой оплате')
                reference, stamp = adapter.confirm(dict(row)), ctx.now()
                ensure_account(c, user['tenant_id'])
                c.execute("UPDATE commercial_orders SET status='sandbox_confirmed',provider_reference=?,confirmed_at=? WHERE id=? AND tenant_id=?", (reference, stamp, order_id, user['tenant_id']))
                c.execute("UPDATE commercial_orders SET status='canceled',canceled_at=? WHERE tenant_id=? AND id<>? AND status='pending'", (stamp, user['tenant_id'], order_id))
                c.execute("UPDATE commercial_accounts SET state='sandbox_active',plan_id=?,plan_snapshot=?,subscription_started_at=?,subscription_ends_at=?,active_order_id=?,canceled_at=NULL,updated_at=? WHERE tenant_id=?", (row['plan_id'], row['plan_snapshot'], stamp, next_month(stamp), order_id, stamp, user['tenant_id']))
            return {'order': order_view(find_order(c, user, order_id)), 'account': account_view(c, user)}

    @router.post('/orders/{order_id}/cancel')
    def cancel_order(order_id: str, data: Input, user=Depends(ctx.get_user)):
        manager(user)
        with ctx.database(ctx.config, write=True) as c:
            row = find_order(c, user, order_id)
            if row['status'] == 'sandbox_confirmed':
                ctx.problem(409, 'Тариф уже подключён. Используйте отмену тарифа.')
            if row['status'] == 'pending':
                c.execute("UPDATE commercial_orders SET status='canceled',canceled_at=? WHERE id=? AND tenant_id=?", (ctx.now(), order_id, user['tenant_id']))
            return order_view(find_order(c, user, order_id))

    @router.post('/cancel')
    def cancel(data: Consent, user=Depends(ctx.get_user)):
        manager(user)
        with ctx.database(ctx.config, write=True) as c:
            stamp = ctx.now()
            c.execute("UPDATE commercial_accounts SET state='canceled',canceled_at=?,updated_at=? WHERE tenant_id=? AND state IN ('trial','sandbox_active')", (stamp, stamp, user['tenant_id']))
            c.execute("UPDATE commercial_orders SET status='canceled',canceled_at=? WHERE tenant_id=? AND status='pending'", (stamp, user['tenant_id']))
            return account_view(c, user)

    @router.post('/deletion-request', status_code=201)
    def request_deletion(data: DeletionRequest, user=Depends(ctx.get_user)):
        manager(user)
        with ctx.database(ctx.config, write=True) as c:
            stamp = ctx.now()
            c.execute("INSERT INTO commercial_deletion_requests VALUES(?,?,?,'requested',?,?) ON CONFLICT(tenant_id) DO NOTHING", (user['tenant_id'], ctx.identifier(), user['id'], stamp, stamp))
            row = c.execute('SELECT id,status,created_at FROM commercial_deletion_requests WHERE tenant_id=?', (user['tenant_id'],)).fetchone()
            return dict(row)

    return router
