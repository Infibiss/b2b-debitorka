"""Debt-recovery workspace API: one debtor, three stages, one next step.

Builds on the invoice ledger, evidence store and reminder worker rather than
replacing them. Statuses and guards live in ``recovery_rules``.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import Field, StrictBool, StrictInt, field_validator, model_validator

from . import finance as f
from . import recovery_rules as rules
from . import recovery_templates as templates
from .business_time import business_today
from .database import database
from .legal import _ensure_rates, calculate_debt
from .legal_fees import TARIFF
from .models import Input, single_line

SCHEMA = '''
CREATE TABLE IF NOT EXISTS recovery_debtors (
 tenant_id TEXT NOT NULL REFERENCES tenants(id), counterparty_id TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'new', custom_status TEXT NOT NULL DEFAULT '', assignee_id TEXT,
 route TEXT, promise_date TEXT, promise_amount INTEGER, note TEXT NOT NULL DEFAULT '',
 claim_sent_on TEXT, claim_reference TEXT NOT NULL DEFAULT '', pretrial_days INTEGER NOT NULL DEFAULT 30,
 duty_amount INTEGER, duty_reference TEXT NOT NULL DEFAULT '', claim_amount INTEGER,
 filed_on TEXT, court_reference TEXT NOT NULL DEFAULT '', case_number TEXT NOT NULL DEFAULT '', act_on TEXT,
 writ_number TEXT NOT NULL DEFAULT '', writ_on TEXT, enforcement_reference TEXT NOT NULL DEFAULT '',
 order_cancelled INTEGER NOT NULL DEFAULT 0, has_court_act INTEGER NOT NULL DEFAULT 0,
 details_json TEXT NOT NULL DEFAULT '{}', stage_changed_at TEXT, updated_at TEXT NOT NULL,
 PRIMARY KEY(tenant_id,counterparty_id),
 FOREIGN KEY(counterparty_id,tenant_id) REFERENCES finance_counterparties(id,tenant_id)
);
CREATE TABLE IF NOT EXISTS recovery_log (
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id), counterparty_id TEXT NOT NULL,
 action TEXT NOT NULL, from_status TEXT NOT NULL, to_status TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '',
 actor_id TEXT NOT NULL, actor_name TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS recovery_log_debtor ON recovery_log(tenant_id,counterparty_id,created_at);
CREATE TABLE IF NOT EXISTS recovery_organization (
 tenant_id TEXT PRIMARY KEY REFERENCES tenants(id), data_json TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recovery_automation (
 tenant_id TEXT PRIMARY KEY REFERENCES tenants(id), data_json TEXT NOT NULL, version INTEGER NOT NULL,
 updated_by TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recovery_templates (
 tenant_id TEXT NOT NULL REFERENCES tenants(id), kind TEXT NOT NULL, body TEXT NOT NULL,
 updated_by TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(tenant_id,kind)
);
CREATE TABLE IF NOT EXISTS recovery_documents (
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id), counterparty_id TEXT NOT NULL,
 kind TEXT NOT NULL, version INTEGER NOT NULL, sha256 TEXT NOT NULL, content_base64 TEXT NOT NULL,
 created_by TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(tenant_id,counterparty_id,kind,version)
);
'''

Text = Annotated[str, Field(max_length=2000)]
Line = Annotated[str, Field(max_length=300)]


def initialize_schema(connection):
    for statement in SCHEMA.split(';'):
        if statement.strip():
            connection.execute(statement)


class ActionInput(Input):
    action: Literal[tuple(rules.ACTIONS)]  # type: ignore[valid-type]
    note: Text = ''
    reference: Line = ''
    case_number: Line = ''
    route: Literal['court_order', 'statement_of_claim'] | None = None
    promise_date: date | None = None
    promise_amount: Annotated[StrictInt, Field(gt=0, le=1_000_000_000_000_000)] | None = None
    sent_on: date | None = None
    filed_on: date | None = None
    act_on: date | None = None


class BulkInput(Input):
    ids: list[str] = Field(min_length=1, max_length=500)
    action: Literal['start', 'prepare_claim']


class DebtorPatch(Input):
    custom_status: Line = ''
    assignee_id: str | None = Field(default=None, max_length=100)
    legal_address: Line = ''
    ogrn: Annotated[str, Field(max_length=15, pattern=r'^\d*$')] = ''
    contract: Line = ''
    performance_documents: Line = ''
    court_name: Line = ''
    court_address: Line = ''
    bank_name: Line = ''


class Organization(Input):
    full_name: Line = ''
    inn: Annotated[str, Field(max_length=12, pattern=r'^(\d{10}|\d{12})?$')] = ''
    ogrn: Annotated[str, Field(max_length=15, pattern=r'^(\d{13}|\d{15})?$')] = ''
    legal_address: Line = ''
    bank_details: Text = ''
    signatory: Line = ''
    poa_number: Line = ''
    poa_valid_until: date | None = None


class Channel(Input):
    enabled: StrictBool
    min_amount: Annotated[StrictInt, Field(ge=0)]
    repeat_days: Annotated[StrictInt, Field(ge=1, le=90)]


class Channels(Input):
    email: Channel
    voice: Channel
    sms: Channel
    post: Channel


class Automation(Input):
    enabled: StrictBool
    min_amount: Annotated[StrictInt, Field(ge=0)]
    max_amount: Annotated[StrictInt, Field(gt=0)]
    start_after_overdue_days: Annotated[StrictInt, Field(ge=0, le=365)]
    claim_after_overdue_days: Annotated[StrictInt, Field(ge=1, le=1095)]
    auto_prepare_claim: StrictBool
    payment_control_days: Annotated[StrictInt, Field(ge=0, le=60)]
    pretrial_days: Annotated[StrictInt, Field(ge=1, le=120)]
    channels: Channels
    weekdays: list[StrictInt] = Field(min_length=1, max_length=7)
    start_hour: Annotated[StrictInt, Field(ge=0, le=23)]
    end_hour: Annotated[StrictInt, Field(ge=1, le=24)]

    @model_validator(mode='after')
    def consistent(self):
        if self.max_amount < self.min_amount:
            raise ValueError('Верхняя граница суммы меньше нижней')
        if self.end_hour <= self.start_hour or len(set(self.weekdays)) != len(self.weekdays) or any(d < 0 or d > 6 for d in self.weekdays):
            raise ValueError('Проверьте расписание')
        return self


class DocumentInput(Input):
    kind: Literal[templates.KINDS]  # type: ignore[valid-type]


class TemplateInput(Input):
    body: str = Field(min_length=20, max_length=20000)

    @field_validator('body')
    @classmethod
    def known_variables(cls, value):
        unknown = templates.unknown_variables(value)
        if unknown:
            raise ValueError('Неизвестные переменные: ' + ', '.join(unknown))
        return value


def money(amount):
    return f.money(amount)


def day(value):
    return '.'.join(reversed(str(value).split('-'))) if value else ''


def get_automation(connection, tenant):
    row = connection.execute('SELECT data_json FROM recovery_automation WHERE tenant_id=?', (tenant,)).fetchone()
    return json.loads(row['data_json']) if row else json.loads(json.dumps(rules.DEFAULT_AUTOMATION))


def get_organization(connection, tenant):
    row = connection.execute('SELECT data_json FROM recovery_organization WHERE tenant_id=?', (tenant,)).fetchone()
    return json.loads(row['data_json']) if row else {}


def state_row(connection, tenant, debtor_id):
    row = connection.execute('SELECT * FROM recovery_debtors WHERE tenant_id=? AND counterparty_id=?', (tenant, debtor_id)).fetchone()
    return dict(row) if row else dict(status='new', custom_status='', assignee_id=None, route=None, promise_date=None, promise_amount=None,
                                      note='', claim_sent_on=None, claim_reference='', pretrial_days=rules.DEFAULT_PRETRIAL_DAYS, duty_amount=None,
                                      duty_reference='', claim_amount=None, filed_on=None, court_reference='', case_number='', act_on=None,
                                      writ_number='', writ_on=None, enforcement_reference='', order_cancelled=0, has_court_act=0, details_json='{}',
                                      stage_changed_at=None, updated_at=None)


def debtor_rows(connection, tenant):
    """All invoices grouped by debtor; an empty state row means status 'new'."""
    groups = {}
    for row in connection.execute('SELECT * FROM invoices WHERE tenant_id=? ORDER BY due_on,id', (tenant,)):
        groups.setdefault(row['counterparty_id'], []).append(f.view_invoice(row))
    return groups


def tenant_context(connection, tenant):
    from .integrations import latest_registry_checks
    evidence = {}
    for row in connection.execute('SELECT invoice_id,kind FROM portfolio_evidence WHERE tenant_id=?', (tenant,)):
        evidence.setdefault(row['invoice_id'], []).append(dict(invoice_id=row['invoice_id'], kind=row['kind']))
    return dict(evidence=evidence, checks=latest_registry_checks(connection, tenant), automation=get_automation(connection, tenant),
                organization=get_organization(connection, tenant), today=business_today(),
                states={row['counterparty_id']: dict(row) for row in connection.execute('SELECT * FROM recovery_debtors WHERE tenant_id=?', (tenant,))},
                counterparties={row['id']: dict(row) for row in connection.execute('SELECT * FROM finance_counterparties WHERE tenant_id=?', (tenant,))})


def has_poa(organization):
    return bool(organization.get('poa_number'))


def summarize(debtor_id, invoices, context):
    counterparty = context['counterparties'][debtor_id]
    state = context['states'].get(debtor_id) or state_row_default()
    open_invoices = [item for item in invoices if item['balance'] > 0]
    balance = sum(item['balance'] for item in open_invoices)
    overdue = sum(item['balance'] for item in open_invoices if item['days_overdue'] > 0)
    status = rules.effective_status(state, context['today'], balance, context['automation'])
    evidence_rows = [row for item in open_invoices for row in context['evidence'].get(item['id'], [])]
    evidence = rules.evidence_report([item['id'] for item in open_invoices], evidence_rows,
                                     has_poa=has_poa(context['organization']), claim_proof=bool(state.get('claim_reference')))
    return dict(id=debtor_id, name=counterparty['name'], inn=counterparty['inn'], email=counterparty['email'],
                hold=bool(counterparty['hold']), contact_allowed=bool(counterparty['contact_allowed']),
                status=status, status_label=rules.STATUSES[status][1], stage=rules.stage_of(status), custom_status=state['custom_status'],
                assignee_id=state['assignee_id'], balance=balance, overdue_amount=overdue, invoice_count=len(invoices), open_invoice_count=len(open_invoices),
                days_overdue=max((item['days_overdue'] for item in open_invoices), default=0),
                oldest_due_on=min((item['due_on'] for item in open_invoices), default=None), route=state['route'], promise_date=state['promise_date'],
                evidence_score=evidence['score'], steps=rules.steps(status), next_step=rules.next_step(status, evidence=evidence), updated_at=state['updated_at'],
                _state=state, _evidence=evidence, _invoices=invoices)


def state_row_default():
    return dict(status='new', custom_status='', assignee_id=None, route=None, promise_date=None, claim_sent_on=None, claim_reference='',
                pretrial_days=rules.DEFAULT_PRETRIAL_DAYS, updated_at=None)


def public(view):
    return {key: value for key, value in view.items() if not key.startswith('_')}


def all_debtors(connection, tenant, context=None):
    context = context or tenant_context(connection, tenant)
    return [summarize(debtor_id, items, context) for debtor_id, items in debtor_rows(connection, tenant).items()]


def interest(invoices, today):
    """Art. 395 interest on current balances; omitted rather than guessed when rates are missing."""
    total, first = 0, None
    for item in invoices:
        if item['balance'] <= 0 or date.fromisoformat(item['due_on']) >= today:
            continue
        try:
            result = calculate_debt(principal=item['balance'], due_on=date.fromisoformat(item['due_on']), through_on=today, sanction='art395')
        except ValueError:
            return None, None
        total += result['interest_amount']
        first = min(first or item['due_on'], item['due_on'])
    return total, first


def document_values(view, organization, *, duty=None):
    state, today = view['_state'], business_today()
    details = json.loads(state.get('details_json') or '{}')
    invoices = [item for item in view['_invoices'] if item['balance'] > 0]
    accrued, since = interest(invoices, today)
    claim_total = view['balance'] + (accrued or 0)
    table = '\n'.join(f"Счёт № {item['number']} от {day(item['issued_on'])}, срок оплаты {day(item['due_on'])}: {money(item['balance'])} руб." for item in invoices)
    interest_text = (f'Проценты по статье 395 ГК РФ за период с {day(since)} по {day(today)} составляют {money(accrued)} руб.' if accrued else '')
    signatory = organization.get('signatory') or ''
    return {
        'creditor.name': organization.get('full_name'), 'creditor.inn': organization.get('inn'), 'creditor.ogrn': organization.get('ogrn'),
        'creditor.address': organization.get('legal_address'), 'creditor.bank_details': organization.get('bank_details'), 'creditor.signatory': signatory,
        'debtor.name': view['name'], 'debtor.inn': view['inn'], 'debtor.ogrn': details.get('ogrn'), 'debtor.address': details.get('legal_address'),
        'contract': details.get('contract'), 'performance_documents': details.get('performance_documents'), 'invoices': table, 'interest_text': interest_text or ' ',
        'principal': money(view['balance']), 'balance': money(view['balance']), 'claim_total': money(claim_total), 'duty': money(duty or state.get('duty_amount') or 0),
        'today': day(today), 'pretrial_days': state.get('pretrial_days') or rules.DEFAULT_PRETRIAL_DAYS, 'claim_sent_on': day(state.get('claim_sent_on')),
        'claim_reference': state.get('claim_reference'), 'court.name': details.get('court_name'), 'court.address': details.get('court_address'),
        'case_number': state.get('case_number'), 'act_on': day(state.get('act_on')), 'writ_number': state.get('writ_number'), 'writ_on': day(state.get('writ_on')),
        'bank.name': details.get('bank_name'),
    }, claim_total


def load_template(connection, tenant, kind):
    base = dict(templates.DEFAULTS[kind])
    row = connection.execute('SELECT body FROM recovery_templates WHERE tenant_id=? AND kind=?', (tenant, kind)).fetchone()
    if row:
        base['body'] = row['body']
    return base


def generate_document(connection, tenant, view, kind, actor_id, organization):
    template = load_template(connection, tenant, kind)
    values, _ = document_values(view, organization)
    missing = templates.missing_variables(template, values)
    if missing:
        f.fail(422, 'Заполните: ' + ', '.join(templates.VARIABLES[key] for key in missing))
    content = templates.build_docx(template, values)
    version = (connection.execute('SELECT MAX(version) AS v FROM recovery_documents WHERE tenant_id=? AND counterparty_id=? AND kind=?', (tenant, view['id'], kind)).fetchone()['v'] or 0) + 1
    document_id = f.uid()
    connection.execute('INSERT INTO recovery_documents VALUES(?,?,?,?,?,?,?,?,?)',
                       (document_id, tenant, view['id'], kind, version, hashlib.sha256(content).hexdigest(), base64.b64encode(content).decode(), actor_id, f.timestamp()))
    return document_id


def upsert_state(connection, tenant, debtor_id, status, values):
    stamp = f.timestamp()
    current = connection.execute('SELECT status FROM recovery_debtors WHERE tenant_id=? AND counterparty_id=?', (tenant, debtor_id)).fetchone()
    previous_stage = rules.stage_of(current['status']) if current else rules.PRETRIAL
    if not current:
        connection.execute('INSERT INTO recovery_debtors(tenant_id,counterparty_id,status,updated_at) VALUES(?,?,?,?)', (tenant, debtor_id, status, stamp))
    fields = dict(values, status=status, updated_at=stamp)
    if rules.stage_of(status) != previous_stage or not current:
        fields['stage_changed_at'] = stamp
    assignments = ','.join(f'{key}=?' for key in fields)
    connection.execute(f'UPDATE recovery_debtors SET {assignments} WHERE tenant_id=? AND counterparty_id=?', (*fields.values(), tenant, debtor_id))


def log(connection, tenant, debtor_id, action, before, after, detail, actor_id, actor_name):
    connection.execute('INSERT INTO recovery_log VALUES(?,?,?,?,?,?,?,?,?,?)', (f.uid(), tenant, debtor_id, action, before, after, detail, actor_id, actor_name, f.timestamp()))


def set_reminders(connection, tenant, view, *, active):
    """Link the debtor to the existing reminder worker: start it or stop it."""
    from .workflow import case_items, current_policy
    invoice_ids = {item['id'] for item in view['_invoices']}
    if active and not current_policy(connection, tenant)['enabled']:
        return False
    stamp = f.timestamp()
    for case in case_items(connection, tenant):
        if not set(case['invoice_ids']) & invoice_ids:
            continue
        connection.execute('''INSERT INTO workflow_cases(tenant_id,case_id,active,paused,reason,started_by,updated_at) VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(tenant_id,case_id) DO UPDATE SET active=excluded.active,paused=excluded.paused,reason=excluded.reason,updated_at=excluded.updated_at''',
                           (tenant, case['id'], 1, 0 if active else 1, 'Этап взыскания', 'recovery', stamp))
    return active


def apply_action(connection, tenant, debtor_id, data: ActionInput, actor_id, actor_name, role):
    context = tenant_context(connection, tenant)
    invoices = debtor_rows(connection, tenant).get(debtor_id)
    if invoices is None:
        f.fail(404, 'Должник не найден')
    view = summarize(debtor_id, invoices, context)
    status, action = view['status'], data.action
    allowed, target, manager_only, required = rules.ACTIONS[action]
    if status not in allowed:
        f.fail(409, f'Действие недоступно в статусе «{view["status_label"]}»')
    if manager_only and role != 'manager':
        f.fail(403, 'Это решение принимает руководитель')
    for name in required:
        if getattr(data, name) in (None, ''):
            f.fail(422, f'Заполните поле: {name}')
    state = view['_state']
    route = data.route or state.get('route')
    claim_total = view['balance']
    if action in ('set_route', 'to_court'):
        _, claim_total = document_values(view, context['organization'])
    facts = dict(evidence=view['_evidence'], solvency=rules.solvency_report(context['checks'].get(view['inn'])), claim_sent_on=state.get('claim_sent_on'),
                 route=route, claim_amount=claim_total, disputed=status == 'dispute', order_cancelled=bool(state.get('order_cancelled')),
                 has_court_act=bool(state.get('has_court_act')), kind=rules.debtor_kind(view['inn']), balance=view['balance'])
    reason = rules.guard(action, status, facts=facts)
    if reason:
        f.fail(409, reason)
    if action == 'reopen' and view['balance'] <= 0:
        f.fail(409, 'Долг полностью оплачен')

    values, detail, stored = {}, data.note, False
    open_ids = [item['id'] for item in view['_invoices'] if item['balance'] > 0]
    if action == 'start':
        stored = set_reminders(connection, tenant, view, active=True)
    elif action == 'promise':
        values = dict(promise_date=str(data.promise_date), promise_amount=data.promise_amount)
        detail = day(data.promise_date) + (f', {money(data.promise_amount)} ₽' if data.promise_amount else '')
    elif action == 'dispute':
        for key in open_ids:
            connection.execute("UPDATE invoices SET status='disputed' WHERE id=? AND tenant_id=? AND status='open'", (key, tenant))
        values = dict(note=data.note)
    elif action == 'resolve_dispute':
        for key in open_ids:
            connection.execute("UPDATE invoices SET status='open' WHERE id=? AND tenant_id=? AND status='disputed'", (key, tenant))
        values = dict(note=data.note)
    elif action == 'prepare_claim':
        generate_document(connection, tenant, view, 'claim', actor_id, context['organization'])
    elif action == 'send_claim':
        values = dict(claim_sent_on=str(data.sent_on), claim_reference=data.reference, pretrial_days=context['automation']['pretrial_days'])
        detail = data.reference
    elif action == 'to_court':
        recommendation = rules.recommend_route(claim_total, disputed=status == 'dispute', order_cancelled=bool(state.get('order_cancelled')))
        values = dict(route=recommendation['route'], claim_amount=claim_total)
        detail = recommendation['reason']
        set_reminders(connection, tenant, view, active=False)
    elif action == 'set_route':
        values = dict(route=data.route, claim_amount=claim_total, duty_amount=rules.duty_amount(claim_total, data.route))
        detail = f"{money(values['duty_amount'])} ₽"
    elif action == 'duty_paid':
        values, detail = dict(duty_reference=data.reference), data.reference
    elif action == 'send_to_lawyer':
        generate_document(connection, tenant, view, route, actor_id, context['organization'])
    elif action == 'file':
        values, detail = dict(filed_on=str(data.filed_on), court_reference=data.reference), data.reference
    elif action in ('accepted', 'order_issued'):
        values = dict(case_number=data.case_number)
        if action == 'order_issued':
            values |= dict(act_on=str(data.act_on), has_court_act=1)
        detail = data.case_number
    elif action == 'order_cancelled':
        values = dict(order_cancelled=1, route=rules.LAWSUIT, has_court_act=0, act_on=str(data.act_on), claim_amount=None, duty_amount=None)
    elif action == 'decision_won':
        values = dict(act_on=str(data.act_on))
    elif action == 'in_force':
        values = dict(act_on=str(data.act_on), has_court_act=1)
    elif action == 'to_enforcement' and status == 'order_issued':
        target, values = 'writ_received', dict(writ_number=state['case_number'], writ_on=state['act_on'])
    elif action == 'writ_received':
        values, detail = dict(writ_number=data.reference, writ_on=str(data.act_on)), data.reference
    elif action in ('send_bank', 'send_fssp'):
        values, detail = dict(enforcement_reference=data.reference), data.reference
    elif action == 'bankruptcy_intent':
        values = dict(act_on=str(data.act_on))

    upsert_state(connection, tenant, debtor_id, target, values)
    log(connection, tenant, debtor_id, action, status, target, detail, actor_id, actor_name)
    return dict(status=target, reminders_active=stored)


def onboarding(connection, tenant, context, debtors):
    organization, policy_saved = context['organization'], connection.execute('SELECT 1 AS x FROM recovery_automation WHERE tenant_id=?', (tenant,)).fetchone()
    from .workflow_delivery import smtp_configured
    required = ('full_name', 'inn', 'ogrn', 'legal_address', 'bank_details', 'signatory')
    items = [
        dict(key='organization', label='Заполнить реквизиты компании', hint='Они подставятся в претензии и заявления.', done=all(organization.get(key) for key in required), target='settings:organization'),
        dict(key='debtors', label='Загрузить должников', hint='Excel-реестр или выгрузка из 1С.', done=bool(debtors), target='debtors:import'),
        dict(key='evidence', label='Добавить документы по долгу', hint='Договор и акт или УПД: без них суд не примет долг.', done=any(item['evidence_score'] >= 50 for item in debtors), target='debtors'),
        dict(key='poa', label='Указать доверенность представителя', hint='Обычная письменная доверенность с печатью.', done=has_poa(organization), target='settings:organization'),
        dict(key='mail', label='Подключить почту для писем должникам', hint='Письма будут уходить с вашего адреса.', done=smtp_configured(tenant), target='settings:connections'),
        dict(key='automation', label='Утвердить правила автоматизации', hint='С какой суммы и как часто писать.', done=bool(policy_saved), target='settings:automation'),
    ]
    return dict(items=items, done=sum(item['done'] for item in items), total=len(items))


def report_rows(debtors):
    totals = {stage: dict(stage=stage, count=0, amount=0) for stage in rules.STAGES}
    for item in debtors:
        totals[item['stage']]['count'] += 1
        totals[item['stage']]['amount'] += item['balance']
    return [totals[stage] for stage in rules.STAGES]


def csv_safe(value):
    value = str(value if value is not None else '')
    return "'" + value if value[:1] in ('=', '+', '-', '@', '\t', '\r') else value


def run_automation(config):
    """Move debtors on the client's approved rules. Never goes to court by itself."""
    moved = 0
    with database(config) as connection:
        tenants = [row['tenant_id'] for row in connection.execute('SELECT tenant_id FROM recovery_automation')]
    for tenant in tenants:
        with database(config, write=True) as connection:
            context = tenant_context(connection, tenant)
            if not context['automation'].get('enabled'):
                continue
            for view in all_debtors(connection, tenant, context):
                action = rules.automation_decision(view['status'], balance=view['balance'], days_overdue=view['days_overdue'],
                                                   contact_allowed=view['contact_allowed'] and not view['hold'], automation=context['automation'])
                if not action:
                    continue
                try:
                    apply_action(connection, tenant, view['id'], ActionInput(action=action), 'automation', 'Mandato', 'manager')
                    moved += 1
                except HTTPException:
                    continue  # Missing details stay visible as this debtor's next step.
    return moved


def promised_amount(debtor):
    """Money promised on invoices, or the whole balance when the debtor as a whole promised to pay."""
    by_invoice = sum(item.get('promised_amount') or 0 for item in debtor['_invoices'] if item['balance'] > 0)
    return max(by_invoice, debtor['balance'] if debtor['status'] == 'promise' else 0)


def create_router(ctx):
    router = APIRouter(prefix='/api/recovery', tags=['recovery'])

    def manager(user):
        if user['role'] != 'manager':
            ctx.problem(403, 'Это решение принимает руководитель')

    def refresh_rates():
        try:
            _ensure_rates(ctx, business_today())
        except (ValueError, RuntimeError, OSError):
            pass  # Interest is omitted from drafts rather than guessed.

    @router.get('/meta')
    def meta(user=Depends(ctx.get_user)):
        return dict(statuses={key: dict(stage=value[0], label=value[1]) for key, value in rules.STATUSES.items()}, action_labels=rules.ACTION_LABELS,
                    actions={key: dict(manager_only=value[2], required=value[3]) for key, value in rules.ACTIONS.items()},
                    document_kinds={key: dict(title=value['title'], stage=value['stage']) for key, value in templates.DEFAULTS.items()},
                    variables=templates.VARIABLES, tariff=TARIFF)

    @router.get('/dashboard')
    def dashboard(user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as c:
            context = tenant_context(c, user['tenant_id'])
            debtors = all_debtors(c, user['tenant_id'], context)
            setup = onboarding(c, user['tenant_id'], context, debtors)
        order = {'today': 0, 'soon': 1, 'later': 2}
        tasks = sorted((item for item in debtors if item['stage'] != rules.CLOSED and item['next_step'] and item['next_step']['action']),
                       key=lambda item: (order[item['next_step']['urgency']], -item['balance']))
        closing = [dict(debtor_id=item['id'], name=item['name'], **deadline) for item in debtors if item['stage'] != rules.CLOSED
                   for deadline in rules.deadlines(item['_state'], item['oldest_due_on'], context['today']) if deadline['days_left'] <= 30]
        open_debtors = [item for item in debtors if item['stage'] != rules.CLOSED]
        return dict(onboarding=setup, stages=report_rows(debtors), tasks=[public(item) for item in tasks[:10]], task_count=len(tasks),
                    deadlines=sorted(closing, key=lambda item: item['days_left'])[:10],
                    totals=dict(debtors=len(open_debtors), balance=sum(item['balance'] for item in open_debtors), overdue=sum(item['overdue_amount'] for item in open_debtors),
                                promised=sum(promised_amount(item) for item in open_debtors)))

    @router.get('/debtors')
    def debtors(user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as c:
            items = all_debtors(c, user['tenant_id'])
        return dict(items=[public(item) for item in sorted(items, key=lambda item: -item['balance'])])

    @router.get('/debtors/{debtor_id}')
    def debtor(debtor_id: str, user=Depends(ctx.get_user)):
        from .financing import offers
        tenant = user['tenant_id']
        with ctx.database(ctx.config) as c:
            context = tenant_context(c, tenant)
            invoices = debtor_rows(c, tenant).get(debtor_id)
            if invoices is None:
                ctx.problem(404, 'Должник не найден')
            view = summarize(debtor_id, invoices, context)
            state = view['_state']
            solvency = rules.solvency_report(context['checks'].get(view['inn']))
            logs = [dict(row) for row in c.execute('SELECT * FROM recovery_log WHERE tenant_id=? AND counterparty_id=? ORDER BY created_at DESC,id', (tenant, debtor_id))]
            documents = [dict(row) for row in c.execute('SELECT id,kind,version,created_at FROM recovery_documents WHERE tenant_id=? AND counterparty_id=? ORDER BY created_at DESC,id', (tenant, debtor_id))]
            financing = offers(c, tenant, view, solvency, context['today'])
        route = view['route'] or rules.recommend_route(view['balance'], disputed=view['status'] == 'dispute', order_cancelled=bool(state.get('order_cancelled')))['route']
        recommendation = rules.recommend_route(view['balance'], disputed=view['status'] == 'dispute', order_cancelled=bool(state.get('order_cancelled')))
        fields = {key: state.get(key) for key in ('claim_sent_on', 'claim_reference', 'duty_amount', 'duty_reference', 'filed_on', 'court_reference', 'case_number', 'act_on', 'writ_number', 'writ_on', 'enforcement_reference', 'promise_amount', 'note')}
        return public(view) | dict(invoices=view['_invoices'], evidence=view['_evidence'], solvency=solvency, deadlines=rules.deadlines(state if state.get('status') else view['_state'] | dict(status=view['status']), view['oldest_due_on'], context['today']),
                                   economics=rules.economics(view['balance'], route, TARIFF) if view['balance'] else None, recommendation=recommendation,
                                   details=json.loads(state.get('details_json') or '{}'), actions=rules.available_actions(view['status'], route=view['route']), log=logs, documents=documents, financing=financing, **fields)

    @router.patch('/debtors/{debtor_id}')
    def patch_debtor(debtor_id: str, data: DebtorPatch, user=Depends(ctx.get_user)):
        tenant = user['tenant_id']
        with ctx.database(ctx.config, write=True) as c:
            if debtor_id not in debtor_rows(c, tenant):
                ctx.problem(404, 'Должник не найден')
            state = state_row(c, tenant, debtor_id)
            details = {key: value for key, value in data.model_dump(exclude={'custom_status', 'assignee_id'}).items()}
            upsert_state(c, tenant, debtor_id, state['status'], dict(custom_status=single_line(data.custom_status), assignee_id=data.assignee_id, details_json=json.dumps(details, ensure_ascii=False)))
        return dict(ok=True)

    @router.post('/debtors/{debtor_id}/actions')
    def action(debtor_id: str, data: ActionInput, user=Depends(ctx.get_user)):
        if data.action in ('prepare_claim', 'set_route', 'send_to_lawyer', 'to_court'):
            refresh_rates()
        with ctx.database(ctx.config, write=True) as c:
            return apply_action(c, user['tenant_id'], debtor_id, data, user['id'], user['name'], user['role'])

    @router.post('/debtors/bulk')
    def bulk(data: BulkInput, user=Depends(ctx.get_user)):
        refresh_rates()
        results = []
        for debtor_id in data.ids:
            try:
                with ctx.database(ctx.config, write=True) as c:
                    apply_action(c, user['tenant_id'], debtor_id, ActionInput(action=data.action), user['id'], user['name'], user['role'])
                results.append(dict(id=debtor_id, ok=True))
            except HTTPException as error:
                results.append(dict(id=debtor_id, ok=False, error=error.detail))
        return dict(items=results, done=sum(item['ok'] for item in results))

    @router.post('/debtors/{debtor_id}/documents', status_code=201)
    def create_document(debtor_id: str, data: DocumentInput, user=Depends(ctx.get_user)):
        refresh_rates()
        tenant = user['tenant_id']
        with ctx.database(ctx.config, write=True) as c:
            context = tenant_context(c, tenant)
            invoices = debtor_rows(c, tenant).get(debtor_id)
            if invoices is None:
                ctx.problem(404, 'Должник не найден')
            return dict(id=generate_document(c, tenant, summarize(debtor_id, invoices, context), data.kind, user['id'], context['organization']))

    @router.get('/documents/{document_id}/download')
    def download(document_id: str, user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as c:
            row = c.execute('SELECT kind,version,content_base64 FROM recovery_documents WHERE id=? AND tenant_id=?', (document_id, user['tenant_id'])).fetchone()
        if not row:
            ctx.problem(404, 'Документ не найден')
        return Response(base64.b64decode(row['content_base64']), media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                        headers={'Content-Disposition': f'attachment; filename="mandato-{row["kind"]}-v{row["version"]}.docx"', 'Cache-Control': 'private, no-store'})

    @router.get('/organization')
    def organization(user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as c:
            return get_organization(c, user['tenant_id'])

    @router.put('/organization')
    def save_organization(data: Organization, user=Depends(ctx.get_user)):
        manager(user)
        with ctx.database(ctx.config, write=True) as c:
            payload = json.dumps(data.model_dump(mode='json'), ensure_ascii=False)
            c.execute('''INSERT INTO recovery_organization VALUES(?,?,?) ON CONFLICT(tenant_id) DO UPDATE SET data_json=excluded.data_json,updated_at=excluded.updated_at''', (user['tenant_id'], payload, ctx.now()))
        return data.model_dump(mode='json')

    @router.get('/automation')
    def automation(user=Depends(ctx.get_user)):
        from .workflow_delivery import smtp_configured
        with ctx.database(ctx.config) as c:
            return get_automation(c, user['tenant_id']) | dict(mail_connected=smtp_configured(user['tenant_id']))

    @router.put('/automation')
    def save_automation(data: Automation, user=Depends(ctx.get_user)):
        from .workflow import current_policy
        from .workflow_delivery import smtp_configured
        manager(user)
        tenant, stamp, mail = user['tenant_id'], ctx.now(), smtp_configured(user['tenant_id'])
        payload = data.model_dump()
        with ctx.database(ctx.config, write=True) as c:
            row = c.execute('SELECT version FROM recovery_automation WHERE tenant_id=?', (tenant,)).fetchone()
            c.execute('''INSERT INTO recovery_automation VALUES(?,?,?,?,?) ON CONFLICT(tenant_id) DO UPDATE SET data_json=excluded.data_json,version=excluded.version,updated_by=excluded.updated_by,updated_at=excluded.updated_at''',
                      (tenant, json.dumps(payload), (row['version'] if row else 0) + 1, user['id'], stamp))
            # Email reminders run through the established worker and its stored policy.
            old = current_policy(c, tenant)
            policy = dict(enabled=bool(data.enabled and data.channels.email.enabled and mail), cooldown_days=data.channels.email.repeat_days, weekdays=data.weekdays,
                          start_hour=data.start_hour, end_hour=data.end_hour, auto_record_promises=old.get('auto_record_promises', True), auto_record_disputes=old.get('auto_record_disputes', True), version=old['version'] + 1)
            c.execute('INSERT INTO workflow_policies VALUES(?,?,?,?,?,?)', (f.uid(), tenant, policy['version'], f._request_json(policy), user['id'], stamp))
        return payload | dict(mail_connected=mail)

    @router.get('/templates')
    def template_list(user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as c:
            return dict(items=[dict(kind=kind, title=item['title'], stage=item['stage'], body=load_template(c, user['tenant_id'], kind)['body'], default_body=item['body']) for kind, item in templates.DEFAULTS.items()], variables=templates.VARIABLES)

    @router.put('/templates/{kind}')
    def template_save(kind: str, data: TemplateInput, user=Depends(ctx.get_user)):
        manager(user)
        if kind not in templates.DEFAULTS:
            ctx.problem(404, 'Шаблон не найден')
        with ctx.database(ctx.config, write=True) as c:
            c.execute('''INSERT INTO recovery_templates VALUES(?,?,?,?,?) ON CONFLICT(tenant_id,kind) DO UPDATE SET body=excluded.body,updated_by=excluded.updated_by,updated_at=excluded.updated_at''', (user['tenant_id'], kind, data.body, user['id'], ctx.now()))
        return dict(kind=kind)

    @router.delete('/templates/{kind}')
    def template_reset(kind: str, user=Depends(ctx.get_user)):
        manager(user)
        with ctx.database(ctx.config, write=True) as c:
            c.execute('DELETE FROM recovery_templates WHERE tenant_id=? AND kind=?', (user['tenant_id'], kind))
        return dict(kind=kind)

    @router.get('/report')
    def report(user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as c:
            debtors = all_debtors(c, user['tenant_id'])
            recovered = c.execute('SELECT COALESCE(SUM(p.amount-p.reversed_amount),0) AS amount FROM payments p WHERE p.tenant_id=?', (user['tenant_id'],)).fetchone()['amount']
            duties = c.execute('SELECT COALESCE(SUM(duty_amount),0) AS amount FROM recovery_debtors WHERE tenant_id=? AND duty_reference<>?', (user['tenant_id'], '')).fetchone()['amount']
        return dict(stages=report_rows(debtors), recovered_amount=recovered, duties_paid_amount=duties,
                    by_status=[dict(status=status, label=rules.STATUSES[status][1], count=sum(item['status'] == status for item in debtors), amount=sum(item['balance'] for item in debtors if item['status'] == status)) for status in rules.STATUSES if any(item['status'] == status for item in debtors)])

    @router.get('/report.csv')
    def report_csv(user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as c:
            debtors = all_debtors(c, user['tenant_id'])
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')
        writer.writerow(['Должник', 'ИНН', 'Этап', 'Статус', 'Мой статус', 'Остаток, ₽', 'Просрочка, дней', 'Документы, %'])
        for item in debtors:
            writer.writerow([csv_safe(item['name']), csv_safe(item['inn']), item['stage'], item['status_label'], csv_safe(item['custom_status']), money(item['balance']), item['days_overdue'], item['evidence_score']])
        return Response('﻿' + output.getvalue(), media_type='text/csv; charset=utf-8', headers={'Content-Disposition': 'attachment; filename="mandato-debtors.csv"', 'Cache-Control': 'private, no-store'})

    return router
