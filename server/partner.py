"""Tenant-owned, expiring read-only partner grants. No bank SSO is implied."""
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from pydantic import Field, StrictBool, StrictInt

from .business_time import business_today
from .models import Input

SCHEMA = '''
CREATE TABLE IF NOT EXISTS partner_grants (
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id), partner_name TEXT NOT NULL,
 purpose TEXT NOT NULL, scope TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE, expires_at TEXT NOT NULL,
 revoked_at TEXT, created_at TEXT NOT NULL, actor_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS partner_access_log (
 id TEXT PRIMARY KEY, grant_id TEXT NOT NULL REFERENCES partner_grants(id), occurred_at TEXT NOT NULL,
 action TEXT NOT NULL
);
'''


def initialize_schema(connection):
    for statement in SCHEMA.split(';'):
        if statement.strip(): connection.execute(statement)


def utc_now(): return datetime.now(timezone.utc)


class GrantInput(Input):
    partner_name: str = Field(min_length=2, max_length=200)
    purpose: str = Field(min_length=10, max_length=1000)
    expires_in_minutes: StrictInt = Field(default=60, ge=1, le=1440)
    confirmed: StrictBool


def create_router(ctx):
    router = APIRouter(prefix='/api/partner', tags=['partner'])

    def view(row):
        return {key: row[key] for key in ('id', 'partner_name', 'purpose', 'scope', 'expires_at', 'revoked_at', 'created_at')}

    @router.get('/grants')
    def grants(user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as c:
            return {'items': [view(row) for row in c.execute('SELECT * FROM partner_grants WHERE tenant_id=? ORDER BY created_at DESC,id DESC', (user['tenant_id'],))]}

    @router.post('/grants', status_code=201)
    def issue(data: GrantInput, user=Depends(ctx.get_user)):
        if not data.confirmed: ctx.problem(422, 'Подтвердите передачу партнёру только агрегированного отчёта на указанный срок')
        token = 'mt_'+secrets.token_urlsafe(32)
        key, stamp = ctx.identifier(), utc_now()
        expiry = (stamp+timedelta(minutes=data.expires_in_minutes)).isoformat()
        with ctx.database(ctx.config, write=True) as c:
            active = c.execute('SELECT COUNT(*) AS n FROM partner_grants WHERE tenant_id=? AND revoked_at IS NULL AND expires_at>?', (user['tenant_id'], stamp.isoformat())).fetchone()['n']
            if active >= 10: ctx.problem(422, 'Отзовите неиспользуемые доступы: одновременно доступно до 10')
            c.execute('INSERT INTO partner_grants VALUES(?,?,?,?,?,?,?,?,?,?)', (key, user['tenant_id'], data.partner_name, data.purpose,
                'portfolio.summary', hashlib.sha256(token.encode()).hexdigest(), expiry, None, stamp.isoformat(), user['id']))
            return {**view(c.execute('SELECT * FROM partner_grants WHERE id=?', (key,)).fetchone()), 'token': token}

    @router.post('/grants/{grant_id}/revoke')
    def revoke(grant_id: str, user=Depends(ctx.get_user)):
        with ctx.database(ctx.config, write=True) as c:
            row=c.execute('SELECT * FROM partner_grants WHERE id=? AND tenant_id=?', (grant_id,user['tenant_id'])).fetchone()
            if row is None: ctx.problem(404,'Доступ не найден')
            c.execute('UPDATE partner_grants SET revoked_at=COALESCE(revoked_at,?) WHERE id=? AND tenant_id=?',(utc_now().isoformat(),grant_id,user['tenant_id']))
            return view(c.execute('SELECT * FROM partner_grants WHERE id=? AND tenant_id=?',(grant_id,user['tenant_id'])).fetchone())

    @router.get('/summary')
    def summary(request: Request):
        auth=request.headers.get('Authorization','')
        if not auth.startswith('Bearer mt_') or len(auth)>120: ctx.problem(401,'Требуется действующий партнёрский доступ')
        digest=hashlib.sha256(auth[7:].encode()).hexdigest()
        # Validation, read and access receipt share a transaction with revocation.
        with ctx.database(ctx.config,write=True) as c:
            row=c.execute("SELECT * FROM partner_grants WHERE token_hash=? AND revoked_at IS NULL AND expires_at>? AND scope='portfolio.summary'",(digest,utc_now().isoformat())).fetchone()
            if row is None: ctx.problem(401,'Доступ истёк или отозван')
            tenant=row['tenant_id']
            balances=c.execute('SELECT COUNT(*) AS invoices,COALESCE(SUM(amount+adjustment_amount-paid_amount),0) AS outstanding,COALESCE(SUM(CASE WHEN due_on<? THEN amount+adjustment_amount-paid_amount ELSE 0 END),0) AS overdue FROM invoices WHERE tenant_id=?',(str(business_today()),tenant)).fetchone()
            run=c.execute('SELECT * FROM portfolio_runs WHERE tenant_id=? ORDER BY created_at DESC,id DESC LIMIT 1',(tenant,)).fetchone()
            report=json.loads(run['report_json']) if run else None
            fresh=False
            if run:
                from .portfolio import inputs,snapshot
                fresh=run['snapshot_hash']==snapshot(inputs(c,tenant))
            c.execute('INSERT INTO partner_access_log VALUES(?,?,?,?)',(ctx.identifier(),row['id'],utc_now().isoformat(),'portfolio.summary'))
            return {'as_of':str(business_today()),'scope':'portfolio.summary','unit':'kopeks',
                'totals':{'invoice_count':balances['invoices'],'outstanding':balances['outstanding'],'overdue':balances['overdue']},
                'audit':{'available':bool(run),'fresh':fresh,'created_at':run['created_at'] if run else None,
                    'urgent_count':report['totals']['urgent_count'] if report and fresh else None,
                    'discrepancies':report['totals']['discrepancies'] if report and fresh else None},
                'limitations':['Агрегаты отражают учётные записи клиента; это не банковское подтверждение и не кредитный скоринг.']}

    return router
