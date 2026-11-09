"""Several companies in one login: membership already exists per tenant; this picks the active one."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import Field

from . import finance as f
from .models import Input, single_line

MAX_ORGANIZATIONS = 25
SCHEMA = '''
CREATE TABLE IF NOT EXISTS user_active_tenant (
 user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE, tenant_id TEXT NOT NULL REFERENCES tenants(id), updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS organization_memberships (
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, tenant_id TEXT NOT NULL REFERENCES tenants(id), role TEXT NOT NULL, created_at TEXT NOT NULL,
 PRIMARY KEY(user_id,tenant_id)
)
'''


def initialize_schema(connection):
    for statement in SCHEMA.split(';'):
        if statement.strip():
            connection.execute(statement)


class OrganizationInput(Input):
    company: str = Field(min_length=2, max_length=200)
    inn: Annotated[str, Field(pattern=r'^(\d{10}|\d{12})?$')] = ''


def active_tenant(connection, user_id):
    """The chosen company, only while the person is still a member of it."""
    row = connection.execute('SELECT a.tenant_id,t.company FROM user_active_tenant a JOIN tenants t ON t.id=a.tenant_id WHERE a.user_id=?', (user_id,)).fetchone()
    return row if row and any(item['id'] == row['tenant_id'] for item in memberships(connection, user_id)) else None


def memberships(connection, user_id):
    rows = connection.execute('''SELECT m.tenant_id AS id,t.company,m.role FROM workflow_memberships m JOIN tenants t ON t.id=m.tenant_id WHERE m.user_id=?
        UNION SELECT m.tenant_id AS id,t.company,m.role FROM organization_memberships m JOIN tenants t ON t.id=m.tenant_id WHERE m.user_id=?''', (user_id, user_id))
    return sorted((dict(row) for row in rows), key=lambda item: item['company'])


def team(connection, tenant):
    """People of one company, whether it is their first company or an added one."""
    return [dict(row) for row in connection.execute('''SELECT u.id,m.tenant_id,u.name,u.email,u.created_at FROM users u JOIN workflow_memberships m ON m.user_id=u.id WHERE m.tenant_id=?
        UNION SELECT u.id,m.tenant_id,u.name,u.email,u.created_at FROM users u JOIN organization_memberships m ON m.user_id=u.id WHERE m.tenant_id=?''', (tenant, tenant))]


def create_router(ctx):
    router = APIRouter(prefix='/api/organizations', tags=['organizations'])

    @router.get('')
    def organization_list(user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as c:
            items = memberships(c, user['id'])
        return dict(active=user['tenant_id'], items=items)

    @router.post('', status_code=201)
    def organization_add(data: OrganizationInput, user=Depends(ctx.get_user)):
        if user['role'] != 'manager':
            ctx.problem(403, 'Добавить организацию может руководитель')
        import json
        stamp = ctx.now()
        with ctx.database(ctx.config, write=True) as c:
            if len(memberships(c, user['id'])) >= MAX_ORGANIZATIONS:
                ctx.problem(409, 'Достигнут предел организаций в одном кабинете')
            key = f.uid()
            name = single_line(data.company)
            c.execute('INSERT INTO tenants VALUES(?,?,?)', (key, name, stamp))
            c.execute('INSERT INTO organization_memberships VALUES(?,?,?,?)', (user['id'], key, 'manager', stamp))
            c.execute('INSERT INTO settings(tenant_id,sender_name,reply_to) VALUES(?,?,?)', (key, user['name'], user['email']))
            if data.inn:
                c.execute('INSERT INTO recovery_organization VALUES(?,?,?)', (key, json.dumps(dict(full_name=name, inn=data.inn), ensure_ascii=False), stamp))
            # Tariffs are per organization: a trial is shared, a paid plan is not carried over.
            source = c.execute('SELECT * FROM commercial_accounts WHERE tenant_id=?', (user['tenant_id'],)).fetchone()
            if source and source['state'] == 'trial':
                c.execute("INSERT INTO commercial_accounts(tenant_id,state,plan_id,plan_snapshot,trial_started_at,trial_ends_at,updated_at) VALUES(?,'trial',?,?,?,?,?)",
                          (key, source['plan_id'], source['plan_snapshot'], source['trial_started_at'], source['trial_ends_at'], stamp))
            c.execute('INSERT INTO user_active_tenant VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET tenant_id=excluded.tenant_id,updated_at=excluded.updated_at', (user['id'], key, stamp))
        return dict(id=key, company=name)

    @router.post('/{key}/switch')
    def organization_switch(key: str, user=Depends(ctx.get_user)):
        with ctx.database(ctx.config, write=True) as c:
            if not any(item['id'] == key for item in memberships(c, user['id'])):
                ctx.problem(404, 'Организация не найдена')
            c.execute('INSERT INTO user_active_tenant VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET tenant_id=excluded.tenant_id,updated_at=excluded.updated_at', (user['id'], key, ctx.now()))
        return dict(id=key)

    @router.get('/summary')
    def organization_summary(user=Depends(ctx.get_user)):
        """Totals side by side, only for companies this person manages."""
        from .recovery import all_debtors, rules
        result = []
        with ctx.database(ctx.config) as c:
            for item in memberships(c, user['id']):
                if item['role'] != 'manager':
                    continue
                debtors = [row for row in all_debtors(c, item['id']) if row['stage'] != rules.CLOSED and not row['archived']]
                result.append(dict(id=item['id'], company=item['company'], debtors=len(debtors), balance=sum(row['balance'] for row in debtors), overdue=sum(row['overdue_amount'] for row in debtors)))
        return dict(items=result)

    return router
