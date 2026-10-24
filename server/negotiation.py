"""Versioned, operator-confirmed negotiation proposals and internal execution.

The financial DB is the authority; LangGraph routes deterministic business
checks. No channel delivery, debt write-off, court filing or receipt confirmation.
"""
import json
from datetime import date, timedelta
from typing import Literal, TypedDict

from fastapi import APIRouter, Depends
from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context
from pydantic import Field, StrictBool, StrictInt, model_validator

from . import finance as f
from .business_time import business_today
from .models import Input, Money

Kind = Literal['promise', 'installment', 'discount', 'document_request', 'dispute', 'payment_claim']
KINDS = ('promise', 'installment', 'discount', 'document_request', 'dispute', 'payment_claim')
DEFAULT_POLICY = dict(version=0, enabled=False, auto_accept=False, max_promise_days=30,
                      max_installments=6, max_discount_bps=0, allowed_kinds=list(KINDS))
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS negotiation_policies (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL REFERENCES tenants(id),version INTEGER NOT NULL,
 policy_json TEXT NOT NULL,actor_id TEXT NOT NULL,created_at TEXT NOT NULL,
 UNIQUE(tenant_id,version)
);
CREATE TABLE IF NOT EXISTS negotiation_proposals (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL REFERENCES tenants(id),invoice_id TEXT NOT NULL,
 kind TEXT NOT NULL,terms_json TEXT NOT NULL,request_json TEXT NOT NULL,source_key TEXT NOT NULL,
 policy_version INTEGER NOT NULL,snapshot_hash TEXT NOT NULL,status TEXT NOT NULL,reasons_json TEXT NOT NULL,
 outcome_json TEXT,actor_id TEXT NOT NULL,created_at TEXT NOT NULL,
 UNIQUE(tenant_id,source_key),UNIQUE(id,tenant_id),
 FOREIGN KEY(invoice_id,tenant_id) REFERENCES invoices(id,tenant_id)
);
CREATE TABLE IF NOT EXISTS negotiation_events (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,proposal_id TEXT NOT NULL,event_type TEXT NOT NULL,
 data_json TEXT NOT NULL,actor_id TEXT NOT NULL,created_at TEXT NOT NULL,
 FOREIGN KEY(proposal_id,tenant_id) REFERENCES negotiation_proposals(id,tenant_id)
);
CREATE INDEX IF NOT EXISTS negotiation_proposals_tenant ON negotiation_proposals(tenant_id,created_at);
CREATE INDEX IF NOT EXISTS negotiation_events_proposal ON negotiation_events(tenant_id,proposal_id,created_at);
"""


def initialize_schema(connection):
    for statement in SCHEMA_SQL.split(';'):
        if statement.strip():
            connection.execute(statement)


class PolicyInput(Input):
    expected_version: StrictInt = Field(ge=0)
    enabled: StrictBool = False
    auto_accept: StrictBool = False
    max_promise_days: StrictInt = Field(default=30, ge=1, le=365)
    max_installments: StrictInt = Field(default=6, ge=1, le=60)
    max_discount_bps: StrictInt = Field(default=0, ge=0, le=10000)
    allowed_kinds: list[Kind] = Field(default_factory=lambda: list(KINDS), max_length=6)

    @model_validator(mode='after')
    def unique_kinds(self):
        if len(set(self.allowed_kinds)) != len(self.allowed_kinds):
            raise ValueError('Типы предложения не должны повторяться')
        return self


class Installment(Input):
    date: date
    amount: Money


class ProposalInput(Input):
    invoice_id: str = Field(min_length=1, max_length=100)
    kind: Kind
    amount: Money | None = None
    due_on: date | None = None
    installments: list[Installment] = Field(default_factory=list, max_length=60)
    discount_bps: StrictInt | None = Field(default=None, gt=0, le=10000)
    ambiguous: StrictBool = False
    confirmed_by_operator: StrictBool = False
    evidence: str = Field(min_length=1, max_length=5000)
    expires_on: date
    idempotency_key: str = Field(min_length=1, max_length=200)

    @model_validator(mode='after')
    def complete_terms(self):
        if self.kind in ('promise', 'installment') and (self.amount is None or self.due_on is None):
            raise ValueError('Укажите обещанную сумму и полную дату')
        if self.kind == 'installment':
            if not self.installments or sum(item.amount for item in self.installments) != self.amount:
                raise ValueError('Сумма графика должна совпадать с обещанной суммой')
            if max(item.date for item in self.installments) != self.due_on:
                raise ValueError('Последняя дата графика должна совпадать со сроком обещания')
            if len({item.date for item in self.installments}) != len(self.installments):
                raise ValueError('Объедините платежи на одну дату')
        elif self.installments:
            raise ValueError('График допустим только для рассрочки')
        if self.kind == 'discount' and self.discount_bps is None:
            raise ValueError('Укажите размер запрашиваемой скидки в базисных пунктах')
        if self.kind != 'discount' and self.discount_bps is not None:
            raise ValueError('Скидка допустима только для предложения о скидке')
        return self


class ReviewInput(Input):
    decision: Literal['approve', 'reject']
    reason: str = Field(min_length=1, max_length=3000)


class ExecuteInput(Input):
    pass


def current_policy(c, tenant_id):
    row = c.execute('SELECT * FROM negotiation_policies WHERE tenant_id=? ORDER BY version DESC LIMIT 1', (tenant_id,)).fetchone()
    return json.loads(row['policy_json']) if row else dict(DEFAULT_POLICY)


def proposal_row(c, tenant_id, proposal_id):
    row = c.execute('SELECT * FROM negotiation_proposals WHERE id=? AND tenant_id=?', (proposal_id, tenant_id)).fetchone()
    if row is None:
        f.fail(404, 'Предложение не найдено')
    return row


def _event(c, tenant_id, proposal_id, kind, data, actor_id):
    c.execute('INSERT INTO negotiation_events VALUES(?,?,?,?,?,?,?)',
              (f.uid(), tenant_id, proposal_id, kind, f._request_json(data), actor_id, f.timestamp()))


def public_proposal(c, row):
    result = {key: row[key] for key in ('id', 'invoice_id', 'kind', 'policy_version', 'snapshot_hash', 'status', 'created_at')}
    result.update(terms=json.loads(row['terms_json']), reasons=json.loads(row['reasons_json']),
                  outcome=json.loads(row['outcome_json']) if row['outcome_json'] else None)
    result['events'] = [dict(id=item['id'], type=item['event_type'], data=json.loads(item['data_json']),
                              actor_id=item['actor_id'], created_at=item['created_at'])
                        for item in c.execute('SELECT * FROM negotiation_events WHERE tenant_id=? AND proposal_id=? ORDER BY created_at,id',
                                              (row['tenant_id'], row['id']))]
    return result


class NegotiationState(TypedDict, total=False):
    terms: dict
    snapshot: dict
    policy: dict
    expected_snapshot: str | None
    expected_policy_version: int | None
    reasons: list[str]
    status: str


def _validate_current(state):
    terms, snapshot, policy = state['terms'], state['snapshot'], state['policy']
    inv, cp = snapshot['invoice'], snapshot['counterparty']
    today = business_today()
    reasons = []
    if not policy['enabled']:
        reasons.append('policy_disabled')
    if terms['kind'] not in policy['allowed_kinds']:
        reasons.append('kind_outside_policy')
    if not terms['confirmed_by_operator']:
        reasons.append('unverified_proposal')
    if terms['ambiguous']:
        reasons.append('ambiguous_terms')
    if state.get('expected_snapshot') and state['expected_snapshot'] != snapshot['snapshot_hash']:
        reasons.append('financial_snapshot_changed')
    if state.get('expected_policy_version') is not None and state['expected_policy_version'] != policy['version']:
        reasons.append('policy_changed')
    if cp['hold']:
        reasons.append('counterparty_hold')
    if not cp['contact_allowed']:
        reasons.append('contact_not_authorized')
    if cp['mandate_expires_on'] and cp['mandate_expires_on'] < str(today):
        reasons.append('mandate_expired')
    if inv['status'] in ('paused', 'disputed') or inv['balance'] <= 0:
        reasons.append('invoice_not_actionable')
    return dict(reasons=reasons)


def _validate_bounds(state):
    terms, policy, snapshot = state['terms'], state['policy'], state['snapshot']
    reasons = list(state['reasons'])
    cp, inv = snapshot['counterparty'], snapshot['invoice']
    today = business_today()
    if terms['kind'] in ('promise', 'installment'):
        if not cp['agent_promises_allowed']:
            reasons.append('promise_mandate_required')
        if not terms['amount'] or terms['amount'] > inv['balance']:
            reasons.append('amount_outside_current_balance')
        deadline = today+timedelta(days=min(policy['max_promise_days'], cp['max_promise_days']))
        if not str(today) <= terms['due_on'] <= str(deadline):
            reasons.append('date_outside_policy_or_mandate')
        if terms['kind'] == 'installment':
            if len(terms['installments']) > min(policy['max_installments'], cp['max_installments']):
                reasons.append('installments_outside_policy_or_mandate')
            if any(item['date'] < str(today) for item in terms['installments']):
                reasons.append('installment_date_in_past')
    if terms['kind'] == 'discount' and terms['discount_bps'] > policy['max_discount_bps']:
        reasons.append('discount_outside_policy')
    return dict(reasons=list(dict.fromkeys(reasons)))


def _decision(state):
    if state['terms']['expires_on'] < str(business_today()):
        return dict(status='expired', reasons=list(dict.fromkeys(state['reasons']+['offer_expired'])))
    return dict(status='handoff' if state['reasons'] else 'accepted' if state['policy']['auto_accept'] else 'review_required')


def _build_graph():
    graph = StateGraph(NegotiationState)
    graph.add_node('current_authority', _validate_current)
    graph.add_node('deterministic_bounds', _validate_bounds)
    graph.add_node('business_decision', _decision)
    graph.add_edge(START, 'current_authority')
    graph.add_edge('current_authority', 'deterministic_bounds')
    graph.add_edge('deterministic_bounds', 'business_decision')
    graph.add_edge('business_decision', END)
    return graph.compile()


NEGOTIATION_GRAPH = _build_graph()


def evaluate(c, tenant_id, invoice_id, terms, expected_snapshot=None, expected_policy_version=None):
    # Shell defaults must not export correspondence/financial facts to an
    # additional tracing sink outside the application's minimized observer.
    with tracing_context(enabled=False):
        return NEGOTIATION_GRAPH.invoke(dict(terms=terms, snapshot=f.financial_snapshot(c, tenant_id, invoice_id),
            policy=current_policy(c, tenant_id), expected_snapshot=expected_snapshot, expected_policy_version=expected_policy_version))


def _set_state(c, row, state, actor_id, event_type='handoff'):
    c.execute('UPDATE negotiation_proposals SET status=?,reasons_json=? WHERE id=? AND tenant_id=?',
              (state['status'], f._request_json(state['reasons']), row['id'], row['tenant_id']))
    _event(c, row['tenant_id'], row['id'], event_type, dict(status=state['status'], reasons=state['reasons']), actor_id)


def _recheck(c, row, actor_id):
    state = evaluate(c, row['tenant_id'], row['invoice_id'], json.loads(row['terms_json']), row['snapshot_hash'], row['policy_version'])
    if state['reasons']:
        _set_state(c, row, state, actor_id)
        return state, 'Условия, полномочия или финансовый снимок изменились. Передайте сотруднику'
    return state, None


def execute_proposal(c, tenant_id, proposal_id, actor_id):
    row = proposal_row(c, tenant_id, proposal_id)
    if row['status'] == 'executed':
        return public_proposal(c, row), None
    if row['status'] != 'accepted':
        return None, 'Предложение должно быть принято и актуально'
    state, error = _recheck(c, row, actor_id)
    if error:
        return None, error
    terms, kind = state['terms'], row['kind']
    # Every action below is internal. The promise ledger keeps accepted amount
    # distinct from debt and replaces any older active schedule atomically.
    if kind in ('promise', 'installment'):
        promise = f.record_promise(c, tenant_id, row['invoice_id'], terms['amount'], terms['due_on'], actor_id,
            'negotiation:'+proposal_id, terms['installments'] if kind == 'installment' else None)
        outcome = dict(action='promise_recorded', promise=promise, external_delivery=False)
    elif kind == 'dispute':
        f.set_dispute(c, tenant_id, row['invoice_id'], True, terms['evidence'], actor_id, 'negotiation:'+proposal_id)
        outcome = dict(action='dispute_recorded', external_delivery=False)
    else:
        action = dict(discount='concession_recorded_for_review', payment_claim='verify_payment', document_request='request_documents')[kind]
        outcome = dict(action=action, external_delivery=False, ledger_changed=False)
        if kind == 'discount':
            outcome.update(discount_bps=terms['discount_bps'], concession_amount=state['snapshot']['invoice']['balance']*terms['discount_bps']//10000,
                           write_off_requires_separate_approval=True)
        f.emit(c, tenant_id, row['invoice_id'], 'negotiation_internal', 'Результат переговоров требует обработки', action)
    c.execute("UPDATE negotiation_proposals SET status='executed',outcome_json=? WHERE id=? AND tenant_id=?",
              (f._request_json(outcome), proposal_id, tenant_id))
    _event(c, tenant_id, proposal_id, 'executed', outcome, actor_id)
    return public_proposal(c, proposal_row(c, tenant_id, proposal_id)), None


def create_router(ctx):
    router = APIRouter(prefix='/api/negotiation', tags=['negotiation'])

    @router.get('/policy')
    def policy(user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as c:
            return current_policy(c, user['tenant_id'])

    @router.get('/policy/history')
    def policy_history(user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as c:
            return dict(items=[dict(policy=json.loads(row['policy_json']), created_at=row['created_at'], actor_id=row['actor_id'])
                for row in c.execute('SELECT * FROM negotiation_policies WHERE tenant_id=? ORDER BY version DESC', (user['tenant_id'],))])

    @router.put('/policy')
    def put_policy(data: PolicyInput, user=Depends(ctx.get_user)):
        with ctx.database(ctx.config, write=True) as c:
            previous = current_policy(c, user['tenant_id'])
            if data.expected_version != previous['version']:
                f.fail(409, 'Политика изменена. Обновите текущую версию')
            updated = data.model_dump(exclude={'expected_version'}, mode='json') | dict(version=previous['version']+1)
            c.execute('INSERT INTO negotiation_policies VALUES(?,?,?,?,?,?)',
                      (f.uid(), user['tenant_id'], updated['version'], f._request_json(updated), user['id'], f.timestamp()))
            return updated

    @router.post('/proposals', status_code=201)
    def propose(data: ProposalInput, user=Depends(ctx.get_user)):
        with ctx.database(ctx.config, write=True) as c:
            payload = data.model_dump(mode='json')
            old = c.execute('SELECT * FROM negotiation_proposals WHERE tenant_id=? AND source_key=?', (user['tenant_id'], data.idempotency_key)).fetchone()
            if old:
                if old['request_json'] != f._request_json(payload):
                    f.fail(409, 'Ключ предложения уже использован с другими условиями')
                return public_proposal(c, old)
            terms = data.model_dump(mode='json', exclude={'invoice_id', 'idempotency_key'})
            state = evaluate(c, user['tenant_id'], data.invoice_id, terms)
            proposal_id = f.uid()
            c.execute('''INSERT INTO negotiation_proposals(id,tenant_id,invoice_id,kind,terms_json,request_json,source_key,
                policy_version,snapshot_hash,status,reasons_json,actor_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (proposal_id,user['tenant_id'],data.invoice_id,data.kind,f._request_json(terms),f._request_json(payload),data.idempotency_key,
                 state['policy']['version'],state['snapshot']['snapshot_hash'],state['status'],f._request_json(state['reasons']),user['id'],f.timestamp()))
            _event(c,user['tenant_id'],proposal_id,'proposed',dict(status=state['status'],reasons=state['reasons'],
                policy_version=state['policy']['version'],snapshot_hash=state['snapshot']['snapshot_hash'],
                operator_confirmed=terms['confirmed_by_operator'],graph='current_authority/deterministic_bounds/business_decision'),user['id'])
            return public_proposal(c, proposal_row(c, user['tenant_id'], proposal_id))

    @router.get('/proposals')
    def proposals(user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as c:
            return dict(items=[public_proposal(c, row) for row in c.execute('SELECT * FROM negotiation_proposals WHERE tenant_id=? ORDER BY created_at DESC LIMIT 200', (user['tenant_id'],))])

    @router.get('/proposals/{proposal_id}')
    def get_proposal(proposal_id: str, user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as c:
            return public_proposal(c, proposal_row(c, user['tenant_id'], proposal_id))

    @router.post('/proposals/{proposal_id}/review')
    def review(proposal_id: str, data: ReviewInput, user=Depends(ctx.get_user)):
        error = None
        with ctx.database(ctx.config, write=True) as c:
            row = proposal_row(c, user['tenant_id'], proposal_id)
            if row['status'] not in ('review_required', 'accepted'):
                f.fail(409, 'Предложение недоступно для согласования; создайте актуальное предложение')
            if data.decision == 'reject':
                c.execute("UPDATE negotiation_proposals SET status='rejected' WHERE id=? AND tenant_id=?", (proposal_id, user['tenant_id']))
            else:
                _, error = _recheck(c, row, user['id'])
                if not error:
                    c.execute("UPDATE negotiation_proposals SET status='accepted' WHERE id=? AND tenant_id=?", (proposal_id, user['tenant_id']))
            if not error:
                _event(c, user['tenant_id'], proposal_id, 'reviewed', data.model_dump(), user['id'])
            result = public_proposal(c, proposal_row(c, user['tenant_id'], proposal_id))
        if error:
            f.fail(409, error)
        return result

    @router.post('/proposals/{proposal_id}/execute')
    def execute(proposal_id: str, data: ExecuteInput, user=Depends(ctx.get_user)):
        with ctx.database(ctx.config, write=True) as c:
            result, error = execute_proposal(c, user['tenant_id'], proposal_id, user['id'])
        if error:
            f.fail(409, error)
        return result

    return router
