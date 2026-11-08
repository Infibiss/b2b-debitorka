"""Tenant-scoped case workbench and policy-authorized reminder automation.

The ledger remains authoritative. A durable delivery claim is committed before
SMTP; uncertain outcomes are held for an operator and never automatically retried.
"""
import asyncio
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from fastapi import APIRouter, Depends, Request
from pydantic import ConfigDict, Field, StrictBool, StrictInt, field_validator, model_validator

from . import finance as f
from .business_time import business_timezone
from .database import database
from .models import Input, valid_email, single_line
from .workflow_delivery import smtp_configured, send_email, message_id

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS workflow_memberships (
 user_id TEXT PRIMARY KEY REFERENCES users(id),tenant_id TEXT NOT NULL REFERENCES tenants(id),
 role TEXT NOT NULL CHECK(role IN('manager','accountant')),created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workflow_invitations (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL REFERENCES tenants(id),email TEXT NOT NULL,
 token_hash TEXT NOT NULL UNIQUE,expires_at TEXT NOT NULL,accepted_at TEXT,created_by TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workflow_contracts (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,counterparty_id TEXT NOT NULL,number TEXT NOT NULL,
 created_at TEXT NOT NULL,UNIQUE(tenant_id,counterparty_id,number),UNIQUE(id,tenant_id),
 FOREIGN KEY(counterparty_id,tenant_id) REFERENCES finance_counterparties(id,tenant_id)
);
CREATE TABLE IF NOT EXISTS workflow_invoice_contracts (
 invoice_id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,contract_id TEXT NOT NULL,
 FOREIGN KEY(invoice_id,tenant_id) REFERENCES invoices(id,tenant_id),
 FOREIGN KEY(contract_id,tenant_id) REFERENCES workflow_contracts(id,tenant_id)
);
CREATE TABLE IF NOT EXISTS workflow_policies (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL REFERENCES tenants(id),version INTEGER NOT NULL,
 policy_json TEXT NOT NULL,created_by TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(tenant_id,version)
);
CREATE TABLE IF NOT EXISTS workflow_cases (
 tenant_id TEXT NOT NULL REFERENCES tenants(id),case_id TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 0,
 paused INTEGER NOT NULL DEFAULT 0,reason TEXT NOT NULL DEFAULT '',started_by TEXT NOT NULL,
 updated_at TEXT NOT NULL,PRIMARY KEY(tenant_id,case_id)
);
CREATE TABLE IF NOT EXISTS workflow_jobs (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,case_id TEXT NOT NULL,invoice_id TEXT NOT NULL,
 counterparty_id TEXT NOT NULL,recipient TEXT NOT NULL,policy_version INTEGER NOT NULL,snapshot_hash TEXT NOT NULL,
 subject TEXT NOT NULL,body TEXT NOT NULL,status TEXT NOT NULL,source_key TEXT NOT NULL,
 created_at TEXT NOT NULL,claimed_at TEXT,completed_at TEXT,reason TEXT NOT NULL DEFAULT '',
 UNIQUE(tenant_id,source_key),UNIQUE(id,tenant_id),
 FOREIGN KEY(invoice_id,tenant_id) REFERENCES invoices(id,tenant_id)
);
CREATE TABLE IF NOT EXISTS workflow_deliveries (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,job_id TEXT NOT NULL,recipient TEXT NOT NULL,
 counterparty_id TEXT NOT NULL,status TEXT NOT NULL,claimed_at TEXT NOT NULL,completed_at TEXT,
 UNIQUE(job_id,recipient),FOREIGN KEY(job_id,tenant_id) REFERENCES workflow_jobs(id,tenant_id)
);
CREATE TABLE IF NOT EXISTS workflow_exceptions (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,case_id TEXT NOT NULL,invoice_id TEXT NOT NULL,
 kind TEXT NOT NULL,detail TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'open',source_key TEXT NOT NULL,
 created_at TEXT NOT NULL,resolved_at TEXT,resolved_by TEXT,resolution TEXT,
 UNIQUE(tenant_id,source_key),FOREIGN KEY(invoice_id,tenant_id) REFERENCES invoices(id,tenant_id)
);
CREATE TABLE IF NOT EXISTS workflow_inbound (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,invoice_id TEXT NOT NULL,source TEXT NOT NULL,
 source_id TEXT NOT NULL,sender TEXT NOT NULL,source_text TEXT NOT NULL,request_hash TEXT NOT NULL,
 status TEXT NOT NULL,proposal_id TEXT,result_json TEXT,created_at TEXT NOT NULL,
 UNIQUE(tenant_id,source,source_id),FOREIGN KEY(invoice_id,tenant_id) REFERENCES invoices(id,tenant_id)
);
CREATE TABLE IF NOT EXISTS workflow_inbound_receipts (
 incoming_id TEXT PRIMARY KEY REFERENCES workflow_inbound(id),received_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS workflow_jobs_ready ON workflow_jobs(status,created_at);
CREATE INDEX IF NOT EXISTS workflow_deliveries_contact ON workflow_deliveries(tenant_id,counterparty_id,claimed_at);
CREATE INDEX IF NOT EXISTS workflow_exceptions_case ON workflow_exceptions(tenant_id,case_id,status);
"""
DEFAULT_POLICY = dict(version=0, enabled=False, cooldown_days=3, weekdays=[0, 1, 2, 3, 4],
                      start_hour=9, end_hour=18, auto_record_promises=True, auto_record_disputes=True)


def initialize_schema(connection):
    for statement in SCHEMA_SQL.split(';'):
        if statement.strip():
            connection.execute(statement)
    from .workflow_mailbox import initialize_schema as initialize_mailbox
    initialize_mailbox(connection)
    # New organization creators are managers by default; invited users always
    # receive an explicit membership in the same transaction as account creation.
    connection.execute("""INSERT INTO workflow_memberships(user_id,tenant_id,role,created_at)
        SELECT id,tenant_id,'manager',created_at FROM users WHERE 1=1
        ON CONFLICT(user_id) DO NOTHING""")


def membership_role(connection, user):
    row = connection.execute('SELECT role FROM workflow_memberships WHERE user_id=? AND tenant_id=?',
                             (user['id'], user['tenant_id'])).fetchone()
    return row['role'] if row else 'accountant'


def require_manager(connection, user):
    if membership_role(connection, user) != 'manager':
        f.fail(403, 'Это решение доступно только руководителю')


def current_policy(connection, tenant):
    row = connection.execute('SELECT policy_json FROM workflow_policies WHERE tenant_id=? ORDER BY version DESC LIMIT 1', (tenant,)).fetchone()
    return json.loads(row['policy_json']) if row else dict(DEFAULT_POLICY)


class PolicyInput(Input):
    expected_version: StrictInt = Field(ge=0)
    enabled: StrictBool = False
    cooldown_days: StrictInt = Field(default=3, ge=1, le=90)
    weekdays: list[StrictInt] = Field(default_factory=lambda: [0, 1, 2, 3, 4], min_length=1, max_length=7)
    start_hour: StrictInt = Field(default=9, ge=0, le=23)
    end_hour: StrictInt = Field(default=18, ge=1, le=24)
    auto_record_promises: StrictBool = True
    auto_record_disputes: StrictBool = True

    @model_validator(mode='after')
    def schedule(self):
        if self.end_hour <= self.start_hour or len(set(self.weekdays)) != len(self.weekdays) or any(day < 0 or day > 6 for day in self.weekdays):
            raise ValueError('Укажите дни недели и рабочее окно без повторов')
        return self


class InvitationInput(Input):
    email: str = Field(max_length=254)
    @field_validator('email')
    @classmethod
    def email_valid(cls, value): return valid_email(value)


class AcceptInput(Input):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)
    token: str = Field(min_length=20, max_length=200)
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=10, max_length=256)
    @field_validator('name')
    @classmethod
    def name_valid(cls, value): return single_line(value)


class ControlInput(Input):
    reason: str = Field(default='', max_length=2000)


class ContractInput(Input):
    counterparty_id: str = Field(min_length=1, max_length=100)
    number: str = Field(min_length=1, max_length=200)
    invoice_ids: list[str] = Field(min_length=1, max_length=200)
    @field_validator('number')
    @classmethod
    def number_valid(cls, value): return single_line(value)


class ResolveInput(Input):
    resolution: str = Field(min_length=1, max_length=2000)


class InboundInput(Input):
    invoice_id: str = Field(min_length=1, max_length=100)
    source: str = Field(min_length=1, max_length=100)
    source_id: str = Field(min_length=1, max_length=200)
    sender: str = Field(max_length=254)
    text: str = Field(min_length=3, max_length=12000)
    received_at: datetime | None = None
    @field_validator('sender')
    @classmethod
    def sender_valid(cls, value): return valid_email(value)
    @field_validator('received_at')
    @classmethod
    def received_valid(cls, value):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None or value > datetime.now(timezone.utc) + timedelta(minutes=5)):
            raise ValueError('Укажите подтверждённое время получения с часовым поясом, не из будущего')
        return value


def _states(c, tenant):
    return {row['case_id']: dict(row) for row in c.execute('SELECT * FROM workflow_cases WHERE tenant_id=?', (tenant,))}


def case_items(c, tenant):
    from .workflow_mailbox import mailbox_blocked
    mailbox_unavailable = mailbox_blocked(c, tenant)
    groups = {}
    # Contract association is explicit. A missing contract is one case per
    # invoice rather than an invented shared agreement.
    rows = c.execute('''SELECT i.*,m.contract_id,k.number AS contract_number,
        p.hold AS counterparty_hold,p.contact_allowed AS counterparty_contact_allowed,
        p.mandate_expires_on AS counterparty_mandate_expires_on
        FROM invoices i JOIN finance_counterparties p ON p.id=i.counterparty_id AND p.tenant_id=i.tenant_id
        LEFT JOIN workflow_invoice_contracts m ON m.invoice_id=i.id AND m.tenant_id=i.tenant_id
        LEFT JOIN workflow_contracts k ON k.id=m.contract_id AND k.tenant_id=i.tenant_id
        WHERE i.tenant_id=? ORDER BY i.due_on,i.id''', (tenant,)).fetchall()
    states, policy = _states(c, tenant), current_policy(c, tenant)
    legal_stages = {}
    for row in c.execute('''SELECT COALESCE(ci.invoice_id,l.invoice_id) AS invoice_id,m.stage FROM legal_milestones m
        JOIN legal_cases l ON l.id=m.case_id AND l.tenant_id=m.tenant_id
        LEFT JOIN legal_case_invoices ci ON ci.case_id=l.id AND ci.tenant_id=l.tenant_id
        WHERE m.tenant_id=? ORDER BY m.occurred_on,m.created_at,m.id''', (tenant,)):
        legal_stages[row['invoice_id']] = row['stage']
    today = datetime.now(business_timezone()).date()
    deadlines = [dict(row) for row in c.execute('''SELECT d.* FROM portfolio_deadlines d
        LEFT JOIN portfolio_deadline_resolutions r ON r.deadline_id=d.id AND r.tenant_id=d.tenant_id
        WHERE d.tenant_id=? AND r.deadline_id IS NULL AND d.review_on<=? ORDER BY d.review_on''',
        (tenant, str(today + timedelta(days=14))))]
    for raw in rows:
        row = dict(raw)
        key = 'contract:' + row['contract_id'] if row['contract_id'] else 'invoice:' + row['id']
        groups.setdefault(key, []).append(row)
    result = []
    for key, invoices in groups.items():
        first, state = invoices[0], states.get(key, {})
        balance = sum(f.balance(inv) for inv in invoices)
        # Unresolved issues follow their invoice when contract grouping changes.
        ids = [inv['id'] for inv in invoices]
        urgent_deadlines = [row for row in deadlines if row['invoice_id'] in ids]
        judicial_stages = [legal_stages[key] for key in ids if legal_stages.get(key) in ('filed', 'order_issued', 'order_cancelled', 'judgment', 'writ_received', 'bank_submitted', 'fssp_submitted')]
        exceptions = [dict(row) for row in c.execute("SELECT * FROM workflow_exceptions WHERE tenant_id=? AND status='open'", (tenant,)) if row['invoice_id'] in ids]
        active = bool(state.get('active'))
        if balance == 0:
            stage, queue, action = 'paid', 'results', 'Обязательства закрыты по финансовому реестру'
        elif any(inv['status'] == 'disputed' for inv in invoices):
            stage, queue, action = 'disputed', 'needs_decision', 'Разрешить спор'
        elif state.get('paused') or any(inv['status'] == 'paused' or inv['counterparty_hold'] for inv in invoices):
            stage, queue, action = 'paused', 'needs_decision', state.get('reason') or 'Контакт приостановлен'
        elif exceptions:
            stage, queue, action = 'verification', 'needs_decision', exceptions[0]['detail']
        elif not all(inv['email'] for inv in invoices):
            stage, queue, action = 'contact', 'needs_decision', 'Указать подтверждённый email'
        elif not active or not policy['enabled']:
            stage, queue, action = 'verification', 'needs_decision', 'Проверить дело и запустить Mandato' if policy['enabled'] else 'Включить правила работы Mandato'
        elif any(inv['promised_amount'] > 0 for inv in invoices):
            missed = any(inv['promised_amount'] > 0 and inv['promise_date'] and inv['promise_date'] < str(today) for inv in invoices)
            stage, queue, action = ('contact', 'in_progress', 'Нарушено обещание оплаты: напоминание по правилам') if missed else ('agreement', 'in_progress', 'Проверить оплату в обещанную дату')
        else:
            delivered = c.execute("SELECT id FROM workflow_jobs WHERE tenant_id=? AND case_id=? AND status='sent' LIMIT 1", (tenant, key)).fetchone()
            stage, queue, action = ('waiting', 'in_progress', 'Ожидать ответ; следующее напоминание по расписанию') if delivered else ('contact', 'in_progress', 'Напоминание по утверждённым правилам')
        if judicial_stages and balance>0:
            stage='legal'
        if urgent_deadlines:
            queue, action = 'needs_decision', 'Юридическая проверка: контрольный срок ' + urgent_deadlines[0]['review_on']
        elif judicial_stages:
            queue, action = 'needs_decision', ('Приказ отменён: подготовить иск' if 'order_cancelled' in judicial_stages else 'Открыть юридическое дело и проверить следующий шаг')
        elif balance == 0 and exceptions:
            queue, action = 'needs_decision', exceptions[0]['detail']
        elif mailbox_unavailable and balance > 0:
            queue, action = 'needs_decision', 'Проверьте подключение входящей почты: синхронизация недоступна'
        result.append(dict(id=key, counterparty_id=first['counterparty_id'], company=first['company'], inn=first['inn'], email=first['email'],
            contract_id=first['contract_id'], contract_number=first['contract_number'], contract_known=bool(first['contract_id']),
            invoice_ids=ids, invoice_count=len(ids), balance=balance, overdue_amount=sum(f.balance(inv) for inv in invoices if inv['due_on'] < str(datetime.now(business_timezone()).date())),
            paid_amount=sum(inv['paid_amount'] for inv in invoices), stage=stage, queue=queue,
            automation_active=active and not bool(state.get('paused')) and policy['enabled'], next_action=action, exceptions_count=len(exceptions), deadlines=urgent_deadlines,
            legal_escalation=bool(judicial_stages), legal_stage=judicial_stages[0] if judicial_stages else None))
    return result


def find_case(c, tenant, key):
    item = next((item for item in case_items(c, tenant) if item['id'] == key), None)
    if not item:
        f.fail(404, 'Дело не найдено')
    return item


def _exception(c, tenant, case_id, invoice_id, kind, detail, source):
    c.execute('''INSERT INTO workflow_exceptions(id,tenant_id,case_id,invoice_id,kind,detail,source_key,created_at)
        VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(tenant_id,source_key) DO NOTHING''',
        (f.uid(), tenant, case_id, invoice_id, kind, detail, source, f.timestamp()))


def exception_role(kind):
    return 'manager' if kind in ('discount', 'installment', 'legal_escalation', 'legal_approval') else 'accountant'


def _snapshot(c, tenant, item):
    values = [f.financial_snapshot(c, tenant, invoice_id)['snapshot_hash'] for invoice_id in sorted(item['invoice_ids'])]
    sender = c.execute('SELECT sender_name,reply_to,bank_details,cooldown_days FROM settings WHERE tenant_id=?', (tenant,)).fetchone()
    # Connector identity changes invalidate a prepared delivery as well.
    return hashlib.sha256(f._request_json(dict(invoices=values, sender=dict(sender), smtp={key: os.getenv(key, '') for key in ('SMTP_HOST', 'SMTP_FROM', 'SMTP_TENANT_ID')})).encode()).hexdigest()


def _calendar(policy, instant=None):
    local = (instant or datetime.now(timezone.utc)).astimezone(business_timezone())
    return local.weekday() in policy['weekdays'] and policy['start_hour'] <= local.hour < policy['end_hour']


def _blocking(c, tenant, item, policy):
    if not policy['enabled']: return 'policy_disabled'
    state = c.execute('SELECT * FROM workflow_cases WHERE tenant_id=? AND case_id=?', (tenant, item['id'])).fetchone()
    if not state or not state['active'] or state['paused']: return 'case_paused'
    if item['queue'] != 'in_progress': return 'case_requires_decision'
    if not _calendar(policy): return 'outside_contact_calendar'
    if not smtp_configured(tenant): return 'smtp_unconfigured'
    if not item['overdue_amount']: return 'invoice_not_overdue'
    for invoice_id in item['invoice_ids']:
        inv = f.load_invoice(c, tenant, invoice_id)
        if f.balance(inv) <= 0: continue
        if inv['status'] != 'open' or inv['counterparty_hold'] or not inv['counterparty_contact_allowed']: return 'contact_not_authorized'
        if inv['counterparty_mandate_expires_on'] and inv['counterparty_mandate_expires_on'] < str(datetime.now(business_timezone()).date()): return 'mandate_expired'
        if inv['promise_date'] and inv['promised_amount'] > 0 and inv['promise_date'] >= str(datetime.now(business_timezone()).date()): return 'promise_not_due'
    settings = c.execute('SELECT cooldown_days FROM settings WHERE tenant_id=?', (tenant,)).fetchone()
    return 'counterparty_cooldown' if contact_blocked(c, tenant, item['counterparty_id'], item['email'], max(policy['cooldown_days'], settings['cooldown_days'])) else None


def contact_blocked(c, tenant, counterparty_id, recipient, cooldown_days):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=cooldown_days)).isoformat()
    # Any uncertain or in-flight delivery blocks forever until reviewed, and
    # legacy sends share the same counterparty-wide cooldown.
    pending = c.execute("SELECT id FROM workflow_deliveries WHERE tenant_id=? AND (counterparty_id=? OR recipient=?) AND (status IN('claimed','unknown') OR (status!='cancelled' AND claimed_at>?)) LIMIT 1", (tenant, counterparty_id, recipient, cutoff)).fetchone()
    legacy = c.execute("SELECT m.id FROM messages m JOIN invoices i ON i.id=m.invoice_id AND i.tenant_id=m.tenant_id WHERE m.tenant_id=? AND (i.counterparty_id=? OR m.recipient=?) AND ((m.status='sent' AND COALESCE(m.sent_at,m.created_at)>?) OR m.invalidation_reason='smtp_outcome_unknown') LIMIT 1", (tenant, counterparty_id, recipient, cutoff)).fetchone()
    reviewed = c.execute("SELECT e.id FROM workflow_exceptions e JOIN invoices i ON i.id=e.invoice_id AND i.tenant_id=e.tenant_id WHERE e.tenant_id=? AND (i.counterparty_id=? OR i.email=?) AND e.kind='delivery_unknown' AND e.status='resolved' AND e.resolved_at>? LIMIT 1", (tenant, counterparty_id, recipient, cutoff)).fetchone()
    return bool(pending or legacy or reviewed)


def schedule_jobs(config):
    scheduled = 0
    with database(config, write=True) as c:
        tenants = c.execute('SELECT id FROM tenants').fetchall()
        for tenant_row in tenants:
            tenant = tenant_row['id']
            policy = current_policy(c, tenant)
            for item in case_items(c, tenant):
                if _blocking(c, tenant, item, policy): continue
                inv = next((f.load_invoice(c, tenant, key) for key in item['invoice_ids'] if f.balance(f.load_invoice(c, tenant, key)) > 0), None)
                if not inv: continue
                # A case containing multiple recipient addresses requires a
                # human decision rather than leaking a combined balance.
                emails = {f.load_invoice(c, tenant, key)['email'] for key in item['invoice_ids']}
                if len(emails) != 1:
                    _exception(c, tenant, item['id'], inv['id'], 'contact_ambiguous', 'У счетов дела разные получатели: проверьте адрес', 'recipients:' + item['id'])
                    continue
                source = f"{item['id']}:{policy['version']}:{datetime.now(business_timezone()).date()}"
                subject = 'Напоминание об оплате ' + (item['contract_number'] or 'счёта № ' + inv['number'])
                lines = [f"№ {f.load_invoice(c, tenant, key)['number']}: остаток {f.money(f.balance(f.load_invoice(c, tenant, key)))} ₽" for key in item['invoice_ids']]
                settings = c.execute('SELECT * FROM settings WHERE tenant_id=?', (tenant,)).fetchone()
                body = 'Здравствуйте!\n\nПросим уточнить дату оплаты:\n' + '\n'.join(lines) + '\n\nЕсли платёж уже отправлен, сообщите его реквизиты для сверки.'
                if settings['bank_details']: body += '\n\nРеквизиты: ' + settings['bank_details']
                cursor = c.execute('''INSERT INTO workflow_jobs(id,tenant_id,case_id,invoice_id,counterparty_id,recipient,policy_version,snapshot_hash,subject,body,status,source_key,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(tenant_id,source_key) DO NOTHING''',
                    (f.uid(), tenant, item['id'], inv['id'], inv['counterparty_id'], inv['email'], policy['version'], _snapshot(c, tenant, item), subject, body, 'queued', source, f.timestamp()))
                scheduled += cursor.rowcount
    return scheduled


def dispatch_jobs(config, limit=30):
    sent = 0
    with database(config) as c:
        ids = [row['id'] for row in c.execute("SELECT id FROM workflow_jobs WHERE status='queued' ORDER BY created_at,id LIMIT ?", (limit,))]
    for job_id in ids:
        # Claim must survive process loss before an external side effect.
        with database(config, write=True) as c:
            job = c.execute('SELECT * FROM workflow_jobs WHERE id=?', (job_id,)).fetchone()
            if not job or job['status'] != 'queued': continue
            tenant, policy = job['tenant_id'], current_policy(c, job['tenant_id'])
            item = next((item for item in case_items(c, tenant) if item['id'] == job['case_id']), None)
            reason = 'case_changed' if item is None else _blocking(c, tenant, item, policy)
            if not reason and policy['version'] != job['policy_version']: reason = 'policy_changed'
            if not reason and _snapshot(c, tenant, item) != job['snapshot_hash']: reason = 'financial_snapshot_changed'
            if reason:
                c.execute("UPDATE workflow_jobs SET status='cancelled',reason=?,completed_at=? WHERE id=?", (reason, f.timestamp(), job_id))
                continue
            c.execute("UPDATE workflow_jobs SET status='claimed',claimed_at=? WHERE id=?", (f.timestamp(), job_id))
            c.execute("INSERT INTO workflow_deliveries(id,tenant_id,job_id,recipient,counterparty_id,status,claimed_at) VALUES(?,?,?,?,?,'claimed',?)", (f.uid(), tenant, job_id, job['recipient'], job['counterparty_id'], f.timestamp()))
            c.execute('INSERT INTO workflow_message_ids VALUES(?,?,?)', (message_id(job), tenant, job_id))
        # Keep the financial write lock during the final check and SMTP call:
        # a pause/revocation/payment cannot commit between check and dispatch.
        with database(config, write=True) as c:
            job = c.execute('SELECT * FROM workflow_jobs WHERE id=?', (job_id,)).fetchone()
            policy = current_policy(c, tenant)
            item = next((item for item in case_items(c, tenant) if item['id'] == job['case_id']), None)
            state = c.execute('SELECT * FROM workflow_cases WHERE tenant_id=? AND case_id=?', (tenant, job['case_id'])).fetchone()
            valid = item and state and state['active'] and not state['paused'] and item['queue'] == 'in_progress' and policy['enabled'] and policy['version'] == job['policy_version'] and _calendar(policy) and smtp_configured(tenant) and _snapshot(c, tenant, item) == job['snapshot_hash']
            if not valid:
                c.execute("UPDATE workflow_jobs SET status='cancelled',reason='revoked_before_dispatch',completed_at=? WHERE id=?", (f.timestamp(), job_id))
                c.execute("UPDATE workflow_deliveries SET status='cancelled',completed_at=? WHERE job_id=?", (f.timestamp(), job_id))
                continue
            settings = dict(c.execute('SELECT * FROM settings WHERE tenant_id=?', (tenant,)).fetchone())
            try:
                send_email(dict(job), settings)
            except Exception:
                # No transport error text or credentials enter public history.
                c.execute("UPDATE workflow_jobs SET status='unknown',reason='smtp_outcome_unknown',completed_at=? WHERE id=?", (f.timestamp(), job_id))
                c.execute("UPDATE workflow_deliveries SET status='unknown',completed_at=? WHERE job_id=?", (f.timestamp(), job_id))
                _exception(c, tenant, job['case_id'], job['invoice_id'], 'delivery_unknown', 'Исход отправки неизвестен. Проверьте почтовый сервер перед новым контактом.', 'delivery:' + job_id)
            else:
                c.execute("UPDATE workflow_jobs SET status='sent',completed_at=? WHERE id=?", (f.timestamp(), job_id))
                c.execute("UPDATE workflow_deliveries SET status='sent',completed_at=? WHERE job_id=?", (f.timestamp(), job_id))
                c.execute("INSERT INTO messages(id,tenant_id,invoice_id,subject,body,recipient,status,source,balance_snapshot,created_at,sent_at) VALUES(?,?,?,?,?,?,'sent','workflow',?,?,?)", (job_id, tenant, job['invoice_id'], job['subject'], job['body'], job['recipient'], item['balance'], job['created_at'], f.timestamp()))
                f.emit(c, tenant, job['invoice_id'], 'workflow_sent', 'Mandato отправил напоминание по правилам', 'Политика версии ' + str(policy['version']))
                sent += 1
    # A crashed claim is not a retry lease. Promote old claims to a visible
    # exception; an operator must investigate external SMTP logs.
    with database(config, write=True) as c:
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        for job in c.execute("SELECT * FROM workflow_jobs WHERE status='claimed' AND claimed_at<?", (cutoff,)).fetchall():
            c.execute("UPDATE workflow_jobs SET status='unknown',reason='worker_interrupted' WHERE id=?", (job['id'],))
            c.execute("UPDATE workflow_deliveries SET status='unknown' WHERE job_id=?", (job['id'],))
            _exception(c, job['tenant_id'], job['case_id'], job['invoice_id'], 'delivery_unknown', 'Обработка отправки прервана. Проверьте журнал почтового сервера.', 'delivery:' + job['id'])
    return sent


def run_once(config):
    from .workflow_mailbox import poll_once
    incoming = poll_once(config)
    from .recovery import run_automation
    return dict(moved=run_automation(config), scheduled=schedule_jobs(config), sent=dispatch_jobs(config), mailbox=incoming)


async def scheduler_loop(config):
    while True:
        try:
            await asyncio.to_thread(run_once, config)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Keep the loop alive, but surface failures in server logs without
            # serializing financial data or provider exception text.
            import logging
            logging.getLogger(__name__).error('Workflow worker cycle failed')
        await asyncio.sleep(60)


def create_router(ctx):
    router = APIRouter(prefix='/api/workflow', tags=['workflow'])

    @router.get('/mailbox')
    def mailbox(user=Depends(ctx.get_user)):
        from .workflow_mailbox import mailbox_status
        with database(ctx.config) as c:
            return mailbox_status(c, user['tenant_id'])

    @router.post('/mailbox/issues/{receipt_id}/resolve')
    def resolve_mailbox(receipt_id: str, data: ResolveInput, user=Depends(ctx.get_user)):
        with database(ctx.config, write=True) as c:
            receipt = c.execute('SELECT * FROM workflow_mailbox_receipts WHERE id=? AND tenant_id=?', (receipt_id, user['tenant_id'])).fetchone()
            if not receipt: f.fail(404, 'Проблема входящей почты не найдена')
            if receipt['status'] == 'processed': f.fail(409, 'Сообщение уже обработано')
            previous = c.execute('SELECT reason FROM workflow_mailbox_reviews WHERE receipt_id=? AND tenant_id=?', (receipt_id, user['tenant_id'])).fetchone()
            if previous:
                if previous['reason'] != data.resolution: f.fail(409, 'Результат проверки уже записан')
            else:
                c.execute('INSERT INTO workflow_mailbox_reviews VALUES(?,?,?,?,?)', (receipt_id, user['tenant_id'], data.resolution, user['id'], f.timestamp()))
                c.execute("UPDATE workflow_mailbox_receipts SET status='reviewed' WHERE id=?", (receipt_id,))
            return dict(id=receipt_id, status='reviewed')

    @router.get('/invoices/{invoice_id}/timeline')
    def timeline(invoice_id: str, offset: int = 0, user=Depends(ctx.get_user)):
        if offset < 0: ctx.problem(422, 'Неверная позиция истории')
        tenant = user['tenant_id']
        entries = []
        def add(key, at, title, body='', section='messages', reference='', amount=None):
            entries.append(dict(id=key, created_at=at, title=title, body=body, section=section, reference=reference, amount=amount))
        with database(ctx.config) as c:
            snapshot = f.financial_snapshot(c, tenant, invoice_id)
            for row in c.execute('SELECT * FROM messages WHERE tenant_id=? AND invoice_id=?', (tenant, invoice_id)):
                status = dict(draft='Черновик', approved='Согласовано', sent='Отправлено', failed='Ошибка отправки').get(row['status'], row['status'])
                add('message:'+row['id'], row['created_at'], 'Исходящее · '+status, row['subject']+'\n'+row['body'])
            for row in c.execute('SELECT * FROM workflow_inbound WHERE tenant_id=? AND invoice_id=?', (tenant, invoice_id)):
                add('inbound:'+row['id'], row['created_at'], 'Входящее письмо', row['source_text'], 'agent')
            for row in c.execute('SELECT * FROM agent_proposals WHERE tenant_id=? AND invoice_id=?', (tenant, invoice_id)):
                facts = json.loads(row['extraction_json'] or '{}')
                add('agent:'+row['id'], row['received_at'], 'Входящий ответ · разбор', row['source_text'], 'agent', row['id'])
                if facts:
                    title = dict(promise='Обещание оплаты', dispute='Возражение', payment_claim='Заявление об оплате').get(facts.get('intent'), 'Нужна ручная проверка')
                    add('facts:'+row['id'], row['created_at'], 'Извлечённые факты · '+title, 'Дата оплаты: '+str(facts.get('due_date') or 'не определена'), 'agent', row['id'], facts.get('amount_kopeks'))
                if row['reviewed_at']:
                    add('review:'+row['id'], row['reviewed_at'], 'Решение по ответу · '+('Подтверждено' if row['decision']=='approve' else 'Отклонено'), row['review_reason'] or '', 'agent', row['id'])
                if row['outcome_json']:
                    outcome = json.loads(row['outcome_json'])
                    add('outcome:'+row['id'], row['reviewed_at'] or row['created_at'], 'Результат обработки ответа', outcome.get('message') or 'Откройте решение для проверки результата.', 'agent', row['id'])
            from .negotiation import public_proposal
            for row in c.execute('SELECT * FROM negotiation_proposals WHERE tenant_id=? AND invoice_id=?', (tenant, invoice_id)):
                proposal = public_proposal(c, row)
                names = dict(proposed='Условия зарегистрированы', reviewed='Решение по условиям', executed='Действие исполнено в кабинете', handoff='Нужна проверка условий', rechecked='Условия проверены повторно')
                for event in proposal['events']:
                    add('terms:'+event['id'], event['created_at'], names.get(event['type'], 'Изменение условий'), proposal['terms']['evidence'], 'intelligence', row['id'], proposal['terms'].get('amount'))
            for event in snapshot['financial_events']:
                label = dict(opening='Оплачено на начало учёта (дата платежа неизвестна)', payment='Банковская оплата' if event.get('confirmed') else 'Оплата, внесённая вручную', reversal='Отмена или возврат оплаты', adjustment='Корректировка обязательства').get(event['type'], 'Финансовая операция')
                add('finance:'+event['id'], event.get('created_at') or event.get('effective_on'), label, event.get('reference') or event.get('reason') or '', 'finance', amount=event['amount'])
            for row in c.execute('SELECT * FROM events WHERE tenant_id=? AND invoice_id=?', (tenant, invoice_id)):
                add('event:'+row['id'], row['created_at'], row['title'], row['detail'] or '', 'workflow')
        entries.sort(key=lambda e: (e['created_at'] or '', e['id']), reverse=True)
        return dict(items=entries[offset:offset+100], total=len(entries), next_offset=offset+100 if offset+100<len(entries) else None)

    @router.get('/cases')
    def list_cases(user=Depends(ctx.get_user)):
        with database(ctx.config) as c:
            items = case_items(c, user['tenant_id'])
            return dict(items=items, summary={key: sum(item['queue'] == key for item in items) for key in ('needs_decision', 'in_progress', 'results')})

    @router.get('/cases/{case_id}')
    def detail(case_id: str, user=Depends(ctx.get_user)):
        with database(ctx.config) as c:
            tenant = user['tenant_id']
            item = find_case(c, tenant, case_id)
            ids = item['invoice_ids']
            item['invoices'] = [f.view_invoice(f.load_invoice(c, tenant, key)) for key in ids]
            item['events'] = [dict(row) for row in c.execute('SELECT * FROM events WHERE tenant_id=? ORDER BY created_at DESC,id', (tenant,)) if row['invoice_id'] in ids]
            item['messages'] = [{key: row[key] for key in ('id', 'invoice_id', 'subject', 'body', 'recipient', 'status', 'source', 'created_at', 'sent_at')} for row in c.execute('SELECT * FROM messages WHERE tenant_id=? ORDER BY created_at DESC,id', (tenant,)) if row['invoice_id'] in ids]
            # Inbound is retained separately and clearly labelled; no fake sent
            # messages are inserted into the legacy outbox table.
            item['messages'] += [dict(id=row['id'], invoice_id=row['invoice_id'], subject='Входящее письмо', body=row['source_text'], recipient=row['sender'], status='received', source=row['source'], created_at=row['created_at'], sent_at=None) for row in c.execute('SELECT * FROM workflow_inbound WHERE tenant_id=? ORDER BY created_at DESC,id', (tenant,)) if row['invoice_id'] in ids]
            item['messages'].sort(key=lambda row: row['created_at'], reverse=True)
            item['financial_events'] = [dict(row) for key in ids for row in f.financial_snapshot(c, tenant, key)['financial_events']]
            item['exceptions'] = [dict(row) | dict(title=row['detail'], required_role=exception_role(row['kind'])) for row in c.execute('SELECT * FROM workflow_exceptions WHERE tenant_id=? ORDER BY created_at DESC,id', (tenant,)) if row['invoice_id'] in ids]
            legal_case_ids={row['case_id'] for row in c.execute('SELECT case_id,invoice_id FROM legal_case_invoices WHERE tenant_id=?',(tenant,)) if row['invoice_id'] in ids}
            item['documents'] = [dict(row) for row in c.execute('''SELECT d.id,d.case_id,d.kind,d.version,d.created_at,l.invoice_id
                FROM legal_documents d JOIN legal_cases l ON l.id=d.case_id AND l.tenant_id=d.tenant_id WHERE d.tenant_id=? ORDER BY d.created_at DESC''', (tenant,)) if row['case_id'] in legal_case_ids]
            item['documents'] += [dict(row) | dict(source='portfolio_evidence') for row in c.execute('''SELECT id,invoice_id,kind,reference,occurred_on,filename,sha256,created_at
                FROM portfolio_evidence WHERE tenant_id=? ORDER BY created_at DESC''', (tenant,)) if row['invoice_id'] in ids]
            for document in item['documents']:
                if document.get('source') == 'portfolio_evidence':
                    document['download_url'] = '/api/portfolio/evidence/' + document['id'] + '/download' if document.get('filename') else None
                else:
                    document['download_url'] = '/api/legal/documents/' + document['id'] + '/download'
            for row in c.execute("SELECT id,invoice_id,payload_json,created_at FROM yandex_service_requests WHERE tenant_id=? AND kind='ocr' AND status='completed' AND acceptance_json IS NOT NULL ORDER BY created_at DESC", (tenant,)):
                if row['invoice_id'] not in ids:
                    continue
                payload = json.loads(row['payload_json'])
                item['documents'].append(dict(id=row['id'], invoice_id=row['invoice_id'], kind='other', source='yandex_ocr',
                    filename=payload.get('filename', 'Распознанный документ'), reference=payload.get('filename', 'Распознанный документ'),
                    created_at=row['created_at'], download_url='/api/yandex/documents/' + row['id'] + '/original'))
            item['documents'].sort(key=lambda document: document.get('created_at', ''), reverse=True)
            return item

    @router.post('/contracts', status_code=201)
    def contract(data: ContractInput, user=Depends(ctx.get_user)):
        with database(ctx.config, write=True) as c:
            tenant = user['tenant_id']
            f.cp_row(c, tenant, data.counterparty_id)
            for key in set(data.invoice_ids):
                inv = f.load_invoice(c, tenant, key)
                if inv['counterparty_id'] != data.counterparty_id:
                    f.fail(409, 'Счета договора должны относиться к одному контрагенту')
                old = c.execute('SELECT contract_id FROM workflow_invoice_contracts WHERE invoice_id=? AND tenant_id=?', (key, tenant)).fetchone()
                if old:
                    old_contract = c.execute('SELECT number FROM workflow_contracts WHERE id=? AND tenant_id=?', (old['contract_id'], tenant)).fetchone()
                    if old_contract['number'] != data.number:
                        f.fail(409, 'Счёт уже привязан к другому договору')
            contract_id = f.uid()
            c.execute('INSERT INTO workflow_contracts VALUES(?,?,?,?,?) ON CONFLICT(tenant_id,counterparty_id,number) DO NOTHING', (contract_id, tenant, data.counterparty_id, data.number, f.timestamp()))
            row = c.execute('SELECT * FROM workflow_contracts WHERE tenant_id=? AND counterparty_id=? AND number=?', (tenant, data.counterparty_id, data.number)).fetchone()
            for key in set(data.invoice_ids):
                c.execute('INSERT INTO workflow_invoice_contracts VALUES(?,?,?) ON CONFLICT(invoice_id) DO NOTHING', (key, tenant, row['id']))
                # A merge starts inactive; prior unknown-invoice authority must
                # not silently extend to newly combined invoices.
                c.execute("UPDATE workflow_cases SET active=0,updated_at=? WHERE tenant_id=? AND case_id IN(?,?)", (f.timestamp(), tenant, 'invoice:' + key, 'contract:' + row['id']))
                f.emit(c, tenant, key, 'workflow_contract', 'Указан договор дела', data.number)
            return dict(row) | dict(case_id='contract:' + row['id'])

    @router.get('/policy')
    def policy(user=Depends(ctx.get_user)):
        with database(ctx.config) as c:
            return current_policy(c, user['tenant_id']) | dict(smtp_configured=smtp_configured(user['tenant_id']), timezone=business_timezone().key)

    @router.put('/policy')
    def update_policy(data: PolicyInput, user=Depends(ctx.get_user)):
        with database(ctx.config, write=True) as c:
            require_manager(c, user)
            old = current_policy(c, user['tenant_id'])
            if old['version'] != data.expected_version:
                f.fail(409, 'Правила уже изменены. Обновите страницу')
            if data.enabled and not smtp_configured(user['tenant_id']):
                f.fail(409, 'Сначала подключите SMTP для этой организации')
            value = data.model_dump(exclude={'expected_version'}) | dict(version=old['version'] + 1)
            c.execute('INSERT INTO workflow_policies VALUES(?,?,?,?,?,?)', (f.uid(), user['tenant_id'], value['version'], f._request_json(value), user['id'], f.timestamp()))
            return value | dict(smtp_configured=smtp_configured(user['tenant_id']), timezone=business_timezone().key)

    @router.get('/team')
    def team(user=Depends(ctx.get_user)):
        with database(ctx.config) as c:
            members = [dict(id=row['id'], name=row['name'], email=row['email'], role=membership_role(c, row)) for row in c.execute('SELECT id,tenant_id,name,email FROM users WHERE tenant_id=? ORDER BY created_at,id', (user['tenant_id'],))]
            invitations = [{key: row[key] for key in ('id', 'email', 'expires_at', 'accepted_at')} for row in c.execute('SELECT * FROM workflow_invitations WHERE tenant_id=? ORDER BY created_at DESC', (user['tenant_id'],))]
            return dict(role=membership_role(c, user), members=members, invitations=invitations)

    @router.post('/invitations', status_code=201)
    def invite(data: InvitationInput, user=Depends(ctx.get_user)):
        token = secrets.token_urlsafe(36)
        with database(ctx.config, write=True) as c:
            require_manager(c, user)
            if c.execute('SELECT id FROM users WHERE email=?', (data.email,)).fetchone():
                f.fail(409, 'Этот email уже зарегистрирован; перенос между организациями запрещён')
            expires = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
            key = f.uid()
            c.execute('INSERT INTO workflow_invitations(id,tenant_id,email,token_hash,expires_at,created_by,created_at) VALUES(?,?,?,?,?,?,?)', (key, user['tenant_id'], data.email, hashlib.sha256(token.encode()).hexdigest(), expires, user['id'], f.timestamp()))
            return dict(id=key, email=data.email, token=token, expires_at=expires)

    @router.post('/invitations/accept', status_code=201)
    def accept(data: AcceptInput):
        # Invitation possession authorizes only the fixed email/tenant and the
        # accountant role. It never moves an existing account across tenants.
        password_hash = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2).hash(data.password)
        try:
            with database(ctx.config, write=True) as c:
                row = c.execute('SELECT * FROM workflow_invitations WHERE token_hash=?', (hashlib.sha256(data.token.encode()).hexdigest(),)).fetchone()
                if not row or row['accepted_at'] or row['expires_at'] <= f.timestamp():
                    f.fail(409, 'Приглашение недействительно или истекло')
                if c.execute('SELECT id FROM users WHERE email=?', (row['email'],)).fetchone():
                    f.fail(409, 'Аккаунт уже существует; войдите с существующими данными')
                key, stamp = f.uid(), f.timestamp()
                c.execute('INSERT INTO users VALUES(?,?,?,?,?,?)', (key, row['tenant_id'], data.name, row['email'], password_hash, stamp))
                c.execute("INSERT INTO workflow_memberships VALUES(?,?,'accountant',?)", (key, row['tenant_id'], stamp))
                c.execute('UPDATE workflow_invitations SET accepted_at=? WHERE id=? AND accepted_at IS NULL', (stamp, row['id']))
                company = c.execute('SELECT company FROM tenants WHERE id=?', (row['tenant_id'],)).fetchone()['company']
                return dict(user=dict(id=key, name=data.name, email=row['email'], company=company), role='accountant', login_required=True)
        except sqlite3.IntegrityError:
            f.fail(409, 'Приглашение уже использовано или аккаунт существует')

    def control(case_id, data, user, action):
        with database(ctx.config, write=True) as c:
            item = find_case(c, user['tenant_id'], case_id)
            if action != 'pause' and not current_policy(c, user['tenant_id'])['enabled']:
                f.fail(409, 'Руководитель должен включить правила Mandato')
            active, paused = (1, 1) if action == 'pause' else (1, 0)
            c.execute('''INSERT INTO workflow_cases(tenant_id,case_id,active,paused,reason,started_by,updated_at) VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(tenant_id,case_id) DO UPDATE SET active=excluded.active,paused=excluded.paused,reason=excluded.reason,started_by=excluded.started_by,updated_at=excluded.updated_at''',
                (user['tenant_id'], case_id, active, paused, data.reason, user['id'], f.timestamp()))
            for key in item['invoice_ids']:
                f.emit(c, user['tenant_id'], key, 'workflow_' + action, 'Mandato: ' + {'start': 'дело запущено', 'pause': 'пауза', 'resume': 'дело возобновлено'}[action], data.reason)
            return find_case(c, user['tenant_id'], case_id)

    @router.post('/cases/{case_id}/start')
    def start(case_id: str, data: ControlInput, user=Depends(ctx.get_user)):
        return control(case_id, data, user, 'start')

    @router.post('/cases/{case_id}/pause')
    def pause(case_id: str, data: ControlInput, user=Depends(ctx.get_user)):
        return control(case_id, data, user, 'pause')

    @router.post('/cases/{case_id}/resume')
    def resume(case_id: str, data: ControlInput, user=Depends(ctx.get_user)):
        return control(case_id, data, user, 'resume')

    @router.post('/exceptions/{exception_id}/resolve')
    def resolve(exception_id: str, data: ResolveInput, user=Depends(ctx.get_user)):
        with database(ctx.config, write=True) as c:
            row = c.execute('SELECT * FROM workflow_exceptions WHERE id=? AND tenant_id=?', (exception_id, user['tenant_id'])).fetchone()
            if not row: f.fail(404, 'Исключение не найдено')
            if exception_role(row['kind']) == 'manager': require_manager(c, user)
            if row['status'] != 'open': return dict(row)
            c.execute("UPDATE workflow_exceptions SET status='resolved',resolution=?,resolved_by=?,resolved_at=? WHERE id=?", (data.resolution, user['id'], f.timestamp(), exception_id))
            if row['source_key'].startswith('delivery:'):
                # Resolving uncertainty acknowledges external investigation. We
                # never retry the same job; a new future contact observes the
                # cooldown counted from the operator's resolution timestamp.
                c.execute("UPDATE workflow_deliveries SET status='reviewed',claimed_at=?,completed_at=? WHERE job_id=? AND tenant_id=? AND status IN('unknown','claimed')", (f.timestamp(), f.timestamp(), row['source_key'].removeprefix('delivery:'), user['tenant_id']))
            elif row['source_key'].startswith('legacy-delivery:'):
                c.execute("UPDATE messages SET invalidation_reason='delivery_reviewed' WHERE id=? AND tenant_id=? AND invalidation_reason='smtp_outcome_unknown'", (row['source_key'].removeprefix('legacy-delivery:'), user['tenant_id']))
            f.emit(c, user['tenant_id'], row['invoice_id'], 'workflow_exception_resolved', 'Сотрудник рассмотрел исключение', data.resolution)
            return dict(c.execute('SELECT * FROM workflow_exceptions WHERE id=?', (exception_id,)).fetchone())

    @router.post('/inbound')
    def inbound(data: InboundInput, request: Request):
        expected = os.getenv('WORKFLOW_INBOUND_TOKEN', '')
        supplied = request.headers.get('authorization', '')
        if not expected or not hmac.compare_digest(supplied.encode(), ('Bearer ' + expected).encode()):
            f.fail(401, 'Требуется авторизация входящего канала')
        tenant, source = os.getenv('WORKFLOW_INBOUND_TENANT_ID', ''), os.getenv('WORKFLOW_INBOUND_SOURCE', '')
        if not tenant or not source or not hmac.compare_digest(source.encode(), data.source.encode()):
            f.fail(403, 'Источник не привязан к организации')
        return ingest_verified(ctx, data, tenant, source)

    return router


def ingest_verified(ctx, data, tenant, source):
    """Private ingestion boundary; caller must authenticate the trusted source."""
    digest = hashlib.sha256(f._request_json(data.model_dump()).encode()).hexdigest()
    with database(ctx.config, write=True) as c:
        inv = f.load_invoice(c, tenant, data.invoice_id)
        if not inv['email'] or not hmac.compare_digest(inv['email'].lower(), data.sender):
            f.fail(403, 'Автор не совпадает с подтверждённым контактом счёта')
        existing = c.execute('SELECT * FROM workflow_inbound WHERE tenant_id=? AND source=? AND source_id=?', (tenant, source, data.source_id)).fetchone()
        if existing:
            if existing['request_hash'] != digest: f.fail(409, 'Идентификатор письма уже использован с другими данными')
            return json.loads(existing['result_json']) if existing['result_json'] else dict(id=existing['id'], status=existing['status'], proposal_id=existing['proposal_id'])
        item = next(item for item in case_items(c, tenant) if data.invoice_id in item['invoice_ids'])
        key, stamp = f.uid(), f.timestamp()
        policy = current_policy(c, tenant)
        c.execute("INSERT INTO workflow_inbound(id,tenant_id,invoice_id,source,source_id,sender,source_text,request_hash,status,created_at) VALUES(?,?,?,?,?,?,?,?,'processing',?)", (key, tenant, data.invoice_id, source, data.source_id, data.sender, data.text, digest, stamp))
        if data.received_at is not None:
            c.execute('INSERT INTO workflow_inbound_receipts VALUES(?,?)', (key, data.received_at.isoformat()))
        # Register the exception before provider work. A process interruption
        # leaves a visible issue and never repeats a billed extraction.
        _exception(c, tenant, item['id'], data.invoice_id, 'incoming_review', 'Входящее сообщение требует проверки', 'inbound:' + key)
        f.emit(c, tenant, data.invoice_id, 'workflow_inbound', 'Получено письмо из проверенного канала', source)
    result = _process_inbound(ctx, key, tenant, item, policy)
    with database(ctx.config, write=True) as c:
        c.execute('UPDATE workflow_inbound SET status=?,proposal_id=?,result_json=? WHERE id=?', (result['status'], result.get('proposal_id'), f._request_json(result), key))
    return result


class PolicyServices:
    """Existing graph finance service plus policy checks inside its write lock."""

    def __init__(self, tenant, case_id, version):
        self.tenant, self.case_id, self.version = tenant, case_id, version

    def __getattr__(self, name):
        return getattr(f, name)

    def agent_gate(self, connection, tenant, invoice_id, intent, amount=None, due_date=None):
        reasons = f.agent_gate(connection, tenant, invoice_id, intent, amount=amount, due_date=due_date)
        policy = current_policy(connection, tenant)
        state = connection.execute('SELECT * FROM workflow_cases WHERE tenant_id=? AND case_id=?', (tenant, self.case_id)).fetchone()
        if tenant != self.tenant or policy['version'] != self.version or not policy['enabled']:
            reasons.append('workflow_policy_changed')
        if not state or not state['active'] or state['paused']:
            reasons.append('workflow_case_paused')
        scope = next((item for item in case_items(connection, tenant) if invoice_id in item['invoice_ids']), None)
        if intent in ('promise', 'dispute') and scope and scope['invoice_count'] > 1:
            reasons.append('workflow_invoice_scope_ambiguous')
        if intent == 'promise' and not policy['auto_record_promises']:
            reasons.append('workflow_promise_not_allowed')
        if intent == 'dispute' and not policy['auto_record_disputes']:
            reasons.append('workflow_dispute_not_allowed')
        return reasons


def _process_inbound(ctx, incoming_id, tenant, item, approved_policy):
    """Run existing persistent LangGraph and authorize ordinary extracted facts.

    A policy actor is recorded explicitly, never disguised as a human reviewer.
    Payment claims, ambiguity, missing mandate and disabled policy remain issues.
    """
    from .agent import AgentRuntime
    from .agent_policy import provider_allowed, provider_configured
    if not approved_policy['enabled'] or not provider_allowed(tenant, production=ctx.config.production) or not provider_configured():
        return dict(id=incoming_id, status='needs_decision', proposal_id=None)
    with database(ctx.config, write=True) as c:
        incoming = c.execute('SELECT * FROM workflow_inbound WHERE id=? AND tenant_id=?', (incoming_id, tenant)).fetchone()
        receipt = c.execute('SELECT received_at FROM workflow_inbound_receipts WHERE incoming_id=?', (incoming_id,)).fetchone()
        if not receipt and re.search(r'\b(?:сегодня|завтра|послезавтра)\b', incoming['source_text'], re.I):
            c.execute("UPDATE workflow_exceptions SET kind='received_time_required',detail='Для относительной даты нужно подтверждённое время получения письма. Уточните полную дату у контрагента.' WHERE tenant_id=? AND source_key=?", (tenant, 'inbound:' + incoming_id))
            return dict(id=incoming_id, status='needs_decision', proposal_id=None)
        hourly = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        if c.execute('SELECT COUNT(*) AS n FROM agent_proposals WHERE tenant_id=? AND created_at>?', (tenant, hourly)).fetchone()['n'] >= 30:
            return dict(id=incoming_id, status='needs_decision', proposal_id=None)
        policy = current_policy(c, tenant)
        state = c.execute('SELECT * FROM workflow_cases WHERE tenant_id=? AND case_id=?', (tenant, item['id'])).fetchone()
        if policy['version'] != approved_policy['version'] or not policy['enabled'] or not state or not state['active'] or state['paused']:
            return dict(id=incoming_id, status='needs_decision', proposal_id=None)
        key, stamp = f.uid(), f.timestamp()
        actor = 'workflow-policy:' + str(policy['version'])
        c.execute('''INSERT INTO agent_proposals(id,tenant_id,invoice_id,thread_id,source_key,source_text,received_at,created_by,created_at,expires_at,status)
            VALUES(?,?,?,?,?,?,?,?,?,?,'processing')''', (key, tenant, incoming['invoice_id'], f.uid(), 'workflow:' + incoming_id, incoming['source_text'], receipt['received_at'] if receipt else incoming['created_at'], actor, stamp, (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()))
        c.execute('UPDATE workflow_inbound SET proposal_id=? WHERE id=?', (key, incoming_id))
        proposal = dict(c.execute('SELECT * FROM agent_proposals WHERE id=?', (key,)).fetchone())
    runtime = AgentRuntime(ctx, services=PolicyServices(tenant, item['id'], approved_policy['version']))
    try:
        proposal = runtime.run(proposal)
        extracted = json.loads(proposal['extraction_json'] or '{}')
        allowed = extracted.get('intent') in ('promise', 'dispute') and approved_policy['auto_record_' + ('promises' if extracted.get('intent') == 'promise' else 'disputes')]
        with database(ctx.config, write=True) as c:
            if extracted.get('intent') == 'payment_claim':
                c.execute("UPDATE workflow_exceptions SET kind='payment_claim',detail='Контрагент сообщил об оплате. Сверьте поступление с банком; остаток не изменён.' WHERE tenant_id=? AND source_key=?", (tenant, 'inbound:' + incoming_id))
            scope = next((value for value in case_items(c, tenant) if proposal['invoice_id'] in value['invoice_ids']), None)
            if scope and scope['invoice_count'] > 1 and extracted.get('intent') in ('promise', 'dispute'):
                allowed = False
                detail = 'Уточните, к каким счетам относятся сумма и условия ответа. Автоматическое распределение не выполнено.'
                c.execute("UPDATE workflow_exceptions SET kind='invoice_scope_ambiguous',detail=? WHERE tenant_id=? AND source_key=?", (detail, tenant, 'inbound:' + incoming_id))
                if extracted.get('intent') == 'dispute':
                    c.execute('''INSERT INTO workflow_cases VALUES(?,?,0,1,?,?,?)
                        ON CONFLICT(tenant_id,case_id) DO UPDATE SET paused=1,reason=excluded.reason,updated_at=excluded.updated_at''',
                        (tenant, scope['id'], detail, actor, f.timestamp()))
                    f.emit(c, tenant, proposal['invoice_id'], 'workflow_scope_paused', 'Mandato приостановил дело: требуется уточнение спора', detail)
            current = current_policy(c, tenant)
            state = c.execute('SELECT * FROM workflow_cases WHERE tenant_id=? AND case_id=?', (tenant, item['id'])).fetchone()
            # The graph's own validate/execute nodes additionally recheck exact
            # snapshot, mandate, current debt and expiry before domain writes.
            allowed = allowed and proposal['status'] == 'review_required' and current['enabled'] and current['version'] == approved_policy['version'] and state and state['active'] and not state['paused']
            if allowed:
                c.execute("UPDATE agent_proposals SET decision='approve',reviewed_by=?,review_reason=?,reviewed_at=? WHERE id=? AND tenant_id=? AND decision IS NULL", (actor, 'Автоматическое решение по политике версии ' + str(current['version']), f.timestamp(), key, tenant))
        if allowed:
            # The existing runtime reopens its own transactions. No database
            # context is retained while graph/checkpointer/provider runs.
            proposal = runtime.run(proposal, resume=True)
            if proposal['status'] == 'executed':
                with database(ctx.config, write=True) as c:
                    c.execute("UPDATE workflow_exceptions SET status='resolved',resolved_at=?,resolved_by=?,resolution='Обработано агентом по утверждённой политике' WHERE tenant_id=? AND source_key=?", (f.timestamp(), actor, tenant, 'inbound:' + incoming_id))
                    f.emit(c, tenant, proposal['invoice_id'], 'workflow_policy_action', 'Mandato обработал входящее по правилам', extracted['intent'])
                return dict(id=incoming_id, status='processed', proposal_id=key)
    except Exception:
        # The persistent proposal is available to operators for diagnosis. An
        # inbox duplicate never reruns extraction or execution automatically.
        pass
    return dict(id=incoming_id, status='needs_decision', proposal_id=key)
