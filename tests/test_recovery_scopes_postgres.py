"""PostgreSQL parity of case promises and independent contract control."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from test_storage_pg import postgres_config, postgres_client  # noqa:F401
from server import workflow
from server.business_time import business_today
from server.database import database, initialize


def test_postgres_scoped_promise_dispatch_concurrency_and_restart(postgres_client, monkeypatch):
    c = postgres_client
    today = business_today()
    invoices, cases = [], []
    for number in ('A', 'B'):
        r = c.post('/api/invoices', json=dict(company='PG Должник', inn='7701234567', email='buyer@example.ru', number=number,
                 issued_on=str(today-timedelta(days=30)), due_on=str(today-timedelta(days=10)), amount=100000))
        assert r.status_code == 201, r.text
        inv = r.json(); invoices.append(inv)
        r = c.post('/api/workflow/contracts', json=dict(counterparty_id=inv['counterparty_id'], number='Договор '+number, invoice_ids=[inv['id']]))
        assert r.status_code == 201, r.text
        cases.append(r.json()['case_id'])
    cp = invoices[0]['counterparty_id']
    with database(c.app.state.config) as db:
        tenant = db.execute('SELECT tenant_id FROM users').fetchone()['tenant_id']
    for key, value in dict(SMTP_TENANT_ID=tenant, SMTP_HOST='smtp.example.ru', SMTP_FROM='finance@example.ru').items():
        monkeypatch.setenv(key, value)
    r = c.put('/api/workflow/policy', json=dict(expected_version=0, enabled=True, weekdays=list(range(7)), start_hour=0, end_hour=24))
    assert r.status_code == 200
    for case in cases:
        assert c.post(f'/api/recovery/debtors/{cp}/actions', params={'case_id':case}, json={'action':'start'}).status_code == 200
    assert workflow.schedule_jobs(c.app.state.config) == 2
    r = c.post(f'/api/recovery/debtors/{cp}/actions', params={'case_id':cases[0]}, json=dict(action='promise', promise_date=str(today+timedelta(days=2)), promise_amount=50000))
    assert r.status_code == 200, r.text
    initialize(c.app.state.config)
    attempts = []
    monkeypatch.setattr(workflow, 'send_email', lambda *args: attempts.append(args))
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda _: workflow.dispatch_jobs(c.app.state.config), range(3)))
    assert len(attempts) == 1
    with database(c.app.state.config) as db:
        states = {r['case_id']:r['status'] for r in db.execute('SELECT case_id,status FROM workflow_jobs WHERE tenant_id=?', (tenant,))}
    assert states[cases[0]] == 'cancelled' and states[cases[1]] == 'sent'
    assert c.get(f'/api/recovery/debtors/{cp}', params={'case_id':cases[0]}).json()['balance'] == 100000
    assert c.get(f'/api/recovery/debtors/{cp}', params={'case_id':cases[1]}).json()['promise_date'] is None
    assert c.post(f'/api/recovery/debtors/{cp}/actions', params={'case_id':cases[0]}, json=dict(action='withdraw', note='Только A')).status_code == 200
    with database(c.app.state.config) as db:
        paused={r['case_id']:r['paused'] for r in db.execute('SELECT case_id,paused FROM workflow_cases WHERE tenant_id=?', (tenant,))}
    assert paused[cases[0]] == 1 and paused[cases[1]] == 0
