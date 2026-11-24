"""API-to-worker regressions: case isolation, promises, stale jobs, legacy history.

No live mail/provider calls. The mail boundary records dispatch attempts; database,
API, scheduling, final dispatch checks and restart initialization are real.
"""
from datetime import datetime, timedelta

import pytest

from tests.test_api import client, invoice, register  # noqa:F401
from tests.test_workflow import configure
from server import recovery, workflow
from server.business_time import business_today
from server.database import database, initialize


def action(c, debtor, case, name, **data):
    return c.post(f'/api/recovery/debtors/{debtor}/actions', params={'case_id': case} if case else {}, json=dict(action=name, **data))


def detail(c, debtor, case=None):
    r = c.get(f'/api/recovery/debtors/{debtor}', params={'case_id': case} if case else {})
    assert r.status_code == 200, r.text
    return r.json()


def two_contracts(c, monkeypatch):
    first, _, tenant = configure(c, monkeypatch)
    second = invoice(c, number='B', amount=150000)
    third = invoice(c, number='UNGROUPED', amount=270000)
    scopes = []
    for inv, number in ((first, 'Договор A'), (second, 'Договор B')):
        r = c.post('/api/workflow/contracts', json=dict(counterparty_id=first['counterparty_id'], number=number, invoice_ids=[inv['id']]))
        assert r.status_code == 201, r.text
        scopes.append(r.json()['case_id'])
    return first, second, third, scopes, tenant


def test_future_promise_blocks_prepared_job_through_due_date_and_survives_restart(client, monkeypatch):
    inv, case, tenant = configure(client, monkeypatch)
    assert action(client, inv['counterparty_id'], None, 'start').status_code == 200
    assert workflow.schedule_jobs(client.app.state.config) == 1
    due = business_today() + timedelta(days=2)
    r = action(client, inv['counterparty_id'], None, 'promise', promise_date=str(due), promise_amount=inv['balance'])
    assert r.status_code == 200, r.text
    sent = []
    monkeypatch.setattr(workflow, 'send_email', lambda *args: sent.append(args))
    initialize(client.app.state.config)
    assert workflow.dispatch_jobs(client.app.state.config) == 0
    assert not sent
    monkeypatch.setattr(recovery, 'business_today', lambda: due)
    assert workflow.schedule_jobs(client.app.state.config) == 0
    monkeypatch.setattr(recovery, 'business_today', lambda: due + timedelta(days=1))
    class AfterPromise(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) + timedelta(days=3)
    monkeypatch.setattr(workflow, 'datetime', AfterPromise)
    assert workflow.schedule_jobs(client.app.state.config) == 1
    assert workflow.dispatch_jobs(client.app.state.config) == 1
    workflow.run_once(client.app.state.config)
    assert len(sent) == 1  # durable idempotency/cooldown, not one call per tick


def test_partial_promise_never_creates_money_or_claims_full_balance(client, monkeypatch):
    inv, _, _ = configure(client, monkeypatch)
    cp = inv['counterparty_id']
    assert action(client, cp, None, 'start').status_code == 200
    due = business_today() + timedelta(days=5)
    assert action(client, cp, None, 'promise', promise_date=str(due), promise_amount=50000).status_code == 200
    assert client.get('/api/recovery/dashboard').json()['totals']['promised'] == 50000
    assert client.post(f"/api/invoices/{inv['id']}/payments", json=dict(amount=20000, paid_on=str(business_today()), reference='Частичная оплата')).status_code == 200
    assert detail(client, cp)['balance'] == inv['balance'] - 20000
    assert workflow.schedule_jobs(client.app.state.config) == 0
    assert client.post(f"/api/invoices/{inv['id']}/payments", json=dict(amount=inv['balance'] - 20000, paid_on=str(business_today()), reference='Остаток')).status_code == 200
    assert detail(client, cp)['status'] == 'paid'
    monkeypatch.setattr(recovery, 'business_today', lambda: due + timedelta(days=1))
    assert workflow.schedule_jobs(client.app.state.config) == 0


@pytest.mark.parametrize('stop', ['withdraw', 'write_off', 'settle', 'dispute'])
def test_stop_actions_cancel_stale_jobs_and_keep_money(client, monkeypatch, stop):
    inv, _, _ = configure(client, monkeypatch)
    cp = inv['counterparty_id']
    assert action(client, cp, None, 'start').status_code == 200
    assert workflow.schedule_jobs(client.app.state.config) == 1
    r = action(client, cp, None, stop, note='Решение руководителя')
    assert r.status_code == 200, r.text
    attempts = []
    monkeypatch.setattr(workflow, 'send_email', lambda *args: attempts.append(args))
    assert workflow.dispatch_jobs(client.app.state.config) == 0
    assert not attempts
    assert detail(client, cp)['balance'] == inv['balance']


def test_two_contracts_and_unassigned_invoice_are_separate_end_to_end(client, monkeypatch):
    first, second, third, scopes, tenant = two_contracts(client, monkeypatch)
    cp = first['counterparty_id']
    overview = detail(client, cp)
    assert overview['read_only'] and overview['actions'] == []
    assert len(overview['cases']) == 3
    assert overview['balance'] == first['balance'] + second['balance'] + third['balance']
    assert {r['invoice_ids'][0] for r in overview['cases']} == {first['id'], second['id'], third['id']}
    assert action(client, cp, None, 'start').status_code == 409
    for scope in scopes:
        assert action(client, cp, scope, 'start').status_code == 200
    due = str(business_today() + timedelta(days=4))
    assert action(client, cp, scopes[0], 'promise', promise_date=due, promise_amount=first['balance']).status_code == 200
    assert detail(client, cp, scopes[1])['status'] == 'reminders'
    assert detail(client, cp, 'invoice:' + third['id'])['status'] == 'new'
    assert workflow.schedule_jobs(client.app.state.config) == 1
    with database(client.app.state.config) as c:
        job = c.execute('SELECT case_id FROM workflow_jobs WHERE tenant_id=?', (tenant,)).fetchone()
        assert job['case_id'] == scopes[1]
    assert action(client, cp, scopes[0], 'withdraw', note='Отозван только договор A').status_code == 200
    with database(client.app.state.config) as c:
        paused = {r['case_id']: r['paused'] for r in c.execute('SELECT * FROM workflow_cases WHERE tenant_id=?', (tenant,))}
    assert paused[scopes[0]] == 1 and paused[scopes[1]] == 0
    assert client.post(f"/api/invoices/{second['id']}/payments", json=dict(amount=second['balance'], paid_on=str(business_today()), reference='Оплачен B')).status_code == 200
    assert detail(client, cp, scopes[1])['status'] == 'paid'
    assert detail(client, cp, scopes[0])['balance'] == first['balance']
    assert detail(client, cp, 'invoice:' + third['id'])['balance'] == third['balance']


def test_invalid_case_and_other_tenant_case_cannot_mutate(client, monkeypatch):
    first, second, third, scopes, tenant = two_contracts(client, monkeypatch)
    cp = first['counterparty_id']
    assert action(client, cp, 'contract:missing', 'start').status_code == 404
    client.post('/api/auth/logout')
    register(client, email='another@example.ru')
    assert action(client, cp, scopes[0], 'start').status_code == 404


def test_legacy_state_requires_explicit_assignment_and_preserves_original(client, monkeypatch):
    inv, _, tenant = configure(client, monkeypatch)
    cp = inv['counterparty_id']
    assert action(client, cp, None, 'start').status_code == 200
    due = str(business_today() + timedelta(days=5))
    assert action(client, cp, None, 'promise', promise_date=due, promise_amount=50000).status_code == 200
    other = invoice(client, number='Second agreement')
    for item, name in ((inv, 'Legacy target'), (other, 'Other')):
        r = client.post('/api/workflow/contracts', json=dict(counterparty_id=cp, number=name, invoice_ids=[item['id']]))
        assert r.status_code == 201
    overview = detail(client, cp)
    assert overview['legacy_review_required']
    scope = next(row['case_id'] for row in overview['cases'] if inv['id'] in row['invoice_ids'])
    assert action(client, cp, scope, 'start').status_code == 409
    assert workflow.schedule_jobs(client.app.state.config) == 0
    assigned = client.post(f'/api/recovery/debtors/{cp}/legacy-assignment', params={'case_id':scope})
    assert assigned.status_code == 200, assigned.text
    assert detail(client, cp, scope)['promise_date'] == due
    assert not detail(client, cp)['legacy_review_required']
    assert client.post(f'/api/recovery/debtors/{cp}/legacy-assignment', params={'case_id':scope}).status_code == 409
    with database(client.app.state.config) as c:
        original = c.execute('SELECT promise_date FROM recovery_debtors WHERE tenant_id=? AND counterparty_id=?', (tenant,cp)).fetchone()
        assert original['promise_date'] == due


@pytest.mark.parametrize('days,amount', [(-1, 50000), (2, 999999999)])
def test_promise_rejects_past_date_or_more_than_balance(client, monkeypatch, days, amount):
    inv, _, _ = configure(client, monkeypatch)
    assert action(client, inv['counterparty_id'], None, 'start').status_code == 200
    assert action(client, inv['counterparty_id'], None, 'promise', promise_date=str(business_today()+timedelta(days=days)), promise_amount=amount).status_code == 422


def test_dashboard_and_reports_use_case_states_without_double_counting(client, monkeypatch):
    first, second, third, scopes, tenant = two_contracts(client, monkeypatch)
    cp = first['counterparty_id']
    for scope in scopes:
        assert action(client, cp, scope, 'start').status_code == 200
    assert action(client, cp, scopes[0], 'promise', promise_date=str(business_today()+timedelta(days=4)), promise_amount=50000).status_code == 200
    assert action(client, cp, scopes[1], 'dispute', note='Only B').status_code == 200
    result = client.get('/api/recovery/dashboard')
    assert result.status_code == 200, result.text
    dashboard = result.json()
    total = first['balance'] + second['balance'] + third['balance']
    assert dashboard['totals'] == dict(debtors=1,balance=total,overdue=total,promised=50000)
    assert sum(row['amount'] for row in dashboard['stages']) == total
    assert dashboard['analytics']['promised_30_days'] == 50000
    assert any(row['status']=='dispute' and row['amount']==second['balance'] for row in dashboard['analytics']['statuses'])
    assert len(dashboard['analytics']['top']) == 1
    assert all(row['case_id'] for row in dashboard['tasks'])
    report = client.get('/api/recovery/report')
    assert report.status_code == 200, report.text
    assert any(row['status']=='promise' and row['amount']==first['balance'] for row in report.json()['by_status'])


def test_auto_archiving_paid_case_never_archives_other_contract(client, monkeypatch):
    first, second, third, scopes, tenant = two_contracts(client, monkeypatch)
    cp = first['counterparty_id']
    assert action(client, cp, scopes[1], 'start').status_code == 200
    assert client.post(f"/api/invoices/{first['id']}/payments", json=dict(amount=first['balance'], paid_on=str(business_today()), reference='Paid only A')).status_code == 200
    assert client.put('/api/recovery/automation', json=dict(recovery.rules.DEFAULT_AUTOMATION, enabled=True,auto_archive_paid=True,weekdays=list(range(7)),start_hour=0,end_hour=24)).status_code == 200
    recovery.run_automation(client.app.state.config)
    assert detail(client, cp, scopes[0])['archived']
    assert not detail(client, cp, scopes[1])['archived']
    assert not detail(client, cp)['archived']
    assert workflow.schedule_jobs(client.app.state.config) == 1


def test_documents_register_and_history_follow_only_selected_contract(client, monkeypatch):
    first, second, third, scopes, tenant = two_contracts(client, monkeypatch)
    cp = first['counterparty_id']
    monkeypatch.setattr(recovery, '_ensure_rates', lambda *args: None)
    assert action(client, cp, scopes[0], 'start').status_code == 200
    template = client.post('/api/recovery/custom-templates', json=dict(title='Письмо по договору',stage='pretrial',heading='Письмо',body='Просим согласовать документы по указанному договору.'))
    assert template.status_code == 201, template.text
    doc = client.post(f'/api/recovery/debtors/{cp}/documents', params=dict(case_id=scopes[0]), json=dict(kind='custom:'+template.json()['id']))
    assert doc.status_code == 201, doc.text
    entry = client.post(f'/api/recovery/debtors/{cp}/register', params=dict(case_id=scopes[1]), json=dict(kind='court_event',on_date=str(business_today()),title='Событие только B'))
    assert entry.status_code == 201, entry.text
    a, b = detail(client,cp,scopes[0]),detail(client,cp,scopes[1])
    assert len(a['documents'])==1 and b['documents']==[]
    assert a['register']==[] and len(b['register'])==1
    assert any(row['action']=='start' for row in a['log'])
    assert not any(row['action']=='start' for row in b['log'])
    assert {item['id'] for item in a['invoices']} == {first['id']}
    assert {item['id'] for item in b['invoices']} == {second['id']}
