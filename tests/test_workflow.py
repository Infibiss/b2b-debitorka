"""Workflow behavior: grouping, permissions and durable automation safety."""
import hashlib
from datetime import datetime, timezone

import pytest
from tests.test_api import client, invoice, register
from server.database import database


@pytest.fixture(autouse=True)
def workflow_environment(monkeypatch):
    # Local operator connector settings must never cause live network calls
    # while running this integration suite.
    for name in ('IMAP_HOST', 'IMAP_USER', 'IMAP_PASSWORD', 'IMAP_TENANT_ID', 'IMAP_AUTH_SERV_ID'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('WORKFLOW_WORKER_ENABLED', 'false')


def cases(client):
    response = client.get('/api/workflow/cases')
    assert response.status_code == 200, response.text
    return response.json()['items']


def test_unknown_contracts_are_separate_and_paid_stage_is_derived(client):
    register(client)
    first = invoice(client)
    second = invoice(client, number='СЧ-25')
    items = cases(client)
    assert len(items) == 2
    assert {item['invoice_ids'][0] for item in items} == {first['id'], second['id']}
    assert all(item['contract_id'] is None and item['contract_known'] is False for item in items)
    client.post(f"/api/invoices/{first['id']}/payments", json={'amount': first['balance'], 'paid_on': '2026-10-26', 'reference': 'manual'})
    result = next(item for item in cases(client) if first['id'] in item['invoice_ids'])
    assert result['stage'] == 'paid' and result['queue'] == 'results'


def test_explicit_contract_groups_invoices_and_detail_is_tenant_scoped(client):
    register(client)
    first, second = invoice(client), invoice(client, number='СЧ-25')
    cp = first['counterparty_id']
    contract = client.post('/api/workflow/contracts', json={'counterparty_id': cp, 'number': 'Д-1', 'invoice_ids': [first['id'], second['id']]} )
    assert contract.status_code == 201, contract.text
    item = cases(client)[0]
    assert len(cases(client)) == 1 and item['contract_number'] == 'Д-1'
    detail = client.get('/api/workflow/cases/' + item['id']).json()
    assert len(detail['invoices']) == 2
    assert all(key in detail for key in ('events', 'messages', 'documents', 'financial_events', 'exceptions'))
    client.post('/api/auth/logout')
    register(client, 'other@example.ru')
    assert client.get('/api/workflow/cases/' + item['id']).status_code == 404


def test_invitation_is_hashed_one_use_and_accountant_cannot_change_policy(client):
    register(client)
    invitation = client.post('/api/workflow/invitations', json={'email': 'bookkeeper@example.ru'})
    assert invitation.status_code == 201, invitation.text
    token = invitation.json()['token']
    with database(client.app.state.config) as c:
        row = c.execute('SELECT * FROM workflow_invitations').fetchone()
        assert row['token_hash'] == hashlib.sha256(token.encode()).hexdigest()
        assert token not in str(dict(row))
    accepted = client.post('/api/workflow/invitations/accept', json={'token': token, 'name': 'Бухгалтер', 'password': 'Correct-horse-24!'})
    assert accepted.status_code == 201, accepted.text
    assert client.post('/api/workflow/invitations/accept', json={'token': token, 'name': 'Бухгалтер', 'password': 'Correct-horse-24!'}).status_code == 409
    client.post('/api/auth/logout')
    login = client.post('/api/auth/login', json={'email': 'bookkeeper@example.ru', 'password': 'Correct-horse-24!'}).json()
    client.headers['X-CSRF-Token'] = login['csrf_token']
    assert client.get('/api/workflow/team').json()['role'] == 'accountant'
    assert client.put('/api/workflow/policy', json={'expected_version': 0, 'enabled': False}).status_code == 403


def configure(client, monkeypatch):
    register(client)
    inv = invoice(client)
    with database(client.app.state.config) as c:
        tenant = c.execute('SELECT tenant_id FROM users').fetchone()['tenant_id']
    monkeypatch.setenv('SMTP_HOST', 'smtp.example.ru')
    monkeypatch.setenv('SMTP_FROM', 'finance@example.ru')
    monkeypatch.setenv('SMTP_TENANT_ID', tenant)
    policy = client.put('/api/workflow/policy', json={'expected_version': 0, 'enabled': True, 'weekdays': list(range(7)), 'start_hour': 0, 'end_hour': 24})
    assert policy.status_code == 200, policy.text
    case = cases(client)[0]
    assert client.post('/api/workflow/cases/' + case['id'] + '/start', json={}).status_code == 200
    return inv, case, tenant


def test_policy_conflict_revocation_and_changed_snapshot_cancel_jobs(client, monkeypatch):
    from server import workflow
    inv, case, tenant = configure(client, monkeypatch)
    assert client.put('/api/workflow/policy', json={'expected_version': 0, 'enabled': False}).status_code == 409
    assert workflow.schedule_jobs(client.app.state.config) == 1
    assert client.post('/api/invoices/' + inv['id'] + '/status', json={'status': 'paused'}).status_code == 200
    calls = []
    monkeypatch.setattr(workflow, 'send_email', lambda *args: calls.append(args))
    workflow.dispatch_jobs(client.app.state.config)
    assert calls == []
    with database(client.app.state.config) as c:
        assert c.execute('SELECT status FROM workflow_jobs').fetchone()['status'] == 'cancelled'


def test_counterparty_cooldown_covers_other_unknown_contract_and_duplicate_worker(client, monkeypatch):
    from server import workflow
    inv, case, tenant = configure(client, monkeypatch)
    invoice(client, number='СЧ-25')
    other = next(item for item in cases(client) if item['id'] != case['id'])
    client.post('/api/workflow/cases/' + other['id'] + '/start', json={})
    calls = []
    monkeypatch.setattr(workflow, 'send_email', lambda *args: calls.append(args))
    workflow.run_once(client.app.state.config)
    workflow.run_once(client.app.state.config)
    assert len(calls) == 1
    assert any(item['stage'] == 'waiting' for item in cases(client))


def test_ambiguous_smtp_is_never_retried_and_creates_exception(client, monkeypatch):
    from server import workflow
    configure(client, monkeypatch)
    calls = []
    def fail(*args):
        calls.append(args)
        raise TimeoutError('delivery result unknown')
    monkeypatch.setattr(workflow, 'send_email', fail)
    workflow.run_once(client.app.state.config)
    workflow.run_once(client.app.state.config)
    assert len(calls) == 1
    detail = client.get('/api/workflow/cases/' + cases(client)[0]['id']).json()
    assert detail['exceptions'][0]['kind'] == 'delivery_unknown'
    assert detail['queue'] == 'needs_decision'


def test_protected_inbound_binding_idempotency_and_no_financial_mutation(client, monkeypatch):
    inv, case, tenant = configure(client, monkeypatch)
    monkeypatch.setenv('WORKFLOW_INBOUND_TOKEN', 'private-connector-token')
    monkeypatch.setenv('WORKFLOW_INBOUND_TENANT_ID', tenant)
    monkeypatch.setenv('WORKFLOW_INBOUND_SOURCE', 'mailbox-1')
    payload = {'invoice_id': inv['id'], 'source': 'mailbox-1', 'source_id': 'message-123', 'sender': inv['email'], 'text': 'Оплатили, проверьте банк'}
    assert client.post('/api/workflow/inbound', json=payload).status_code == 401
    headers = {'Authorization': 'Bearer private-connector-token'}
    assert client.post('/api/workflow/inbound', json={**payload, 'sender': 'attacker@example.ru'}, headers=headers).status_code == 403
    result = client.post('/api/workflow/inbound', json=payload, headers=headers)
    assert result.status_code == 200, result.text
    assert client.post('/api/workflow/inbound', json=payload, headers=headers).json() == result.json()
    assert client.post('/api/workflow/inbound', json={**payload, 'text': 'Другое письмо'}, headers=headers).status_code == 409
    detail = client.get('/api/workflow/cases/' + case['id']).json()
    assert len(detail['exceptions']) == 1 and detail['balance'] == inv['balance']


def test_policy_revocation_and_paid_snapshot_cancel_prepared_job(client, monkeypatch):
    from server import workflow
    inv, case, tenant = configure(client, monkeypatch)
    assert workflow.schedule_jobs(client.app.state.config) == 1
    response = client.put('/api/workflow/policy', json={'expected_version': 1, 'enabled': False})
    assert response.status_code == 200
    calls = []
    monkeypatch.setattr(workflow, 'send_email', lambda *args: calls.append(args))
    assert workflow.dispatch_jobs(client.app.state.config) == 0 and not calls
    with database(client.app.state.config) as c:
        assert c.execute('SELECT status FROM workflow_jobs').fetchone()['status'] == 'cancelled'


def test_partial_payment_invalidates_snapshot_before_send(client, monkeypatch):
    from server import workflow
    inv, case, tenant = configure(client, monkeypatch)
    assert workflow.schedule_jobs(client.app.state.config) == 1
    assert client.post('/api/invoices/' + inv['id'] + '/payments', json={'amount': 100, 'paid_on': '2026-10-26', 'reference': 'partial'}).status_code == 200
    calls = []
    monkeypatch.setattr(workflow, 'send_email', lambda *args: calls.append(args))
    workflow.dispatch_jobs(client.app.state.config)
    assert calls == []
    with database(client.app.state.config) as c:
        assert c.execute('SELECT reason FROM workflow_jobs').fetchone()['reason'] == 'financial_snapshot_changed'


def test_legacy_sent_message_blocks_contact_across_unknown_contracts(client, monkeypatch):
    from server import workflow
    inv, case, tenant = configure(client, monkeypatch)
    other = invoice(client, number='legacy')
    with database(client.app.state.config, write=True) as c:
        stamp = datetime.now(timezone.utc).isoformat()
        c.execute("INSERT INTO messages(id,tenant_id,invoice_id,subject,body,recipient,status,balance_snapshot,created_at,sent_at) VALUES('legacy',?,?, 's','b',?,'sent',?,?,?)", (tenant, other['id'], other['email'], other['balance'], stamp, stamp))
    assert workflow.schedule_jobs(client.app.state.config) == 0


def inbound_headers(monkeypatch, tenant):
    monkeypatch.setenv('WORKFLOW_INBOUND_TOKEN', 'private-connector-token')
    monkeypatch.setenv('WORKFLOW_INBOUND_TENANT_ID', tenant)
    monkeypatch.setenv('WORKFLOW_INBOUND_SOURCE', 'mailbox-1')
    return {'Authorization': 'Bearer private-connector-token'}


def provider(monkeypatch, tenant, intent, text, *, amount=None, due_date=None, hook=None):
    from server import agent
    monkeypatch.setenv('YANDEX_API_KEY', 'test-never-sent')
    monkeypatch.setenv('YANDEX_AGENT_MODEL', 'gpt://test/model')
    monkeypatch.setenv('YANDEX_AGENT_TENANT_IDS', tenant)
    evidence = [{'field': 'intent', 'quote': text}]
    if amount:
        evidence += [{'field': 'amount', 'quote': text}, {'field': 'due_date', 'quote': text}]
    def extracted(*args, **kwargs):
        if hook: hook()
        return dict(payload=dict(intent=intent, amount_kopeks=amount, due_date=due_date, currency='RUB' if amount else 'unknown', ambiguous=False, evidence=evidence), error=None, usage={})
    monkeypatch.setattr(agent, 'extract_yandex', extracted)


def test_verified_dispute_is_processed_by_graph_without_per_message_review(client, monkeypatch):
    inv, case, tenant = configure(client, monkeypatch)
    text = 'Не согласны с долгом, спор по поставке.'
    provider(monkeypatch, tenant, 'dispute', text)
    response = client.post('/api/workflow/inbound', headers=inbound_headers(monkeypatch, tenant), json={'invoice_id': inv['id'], 'source': 'mailbox-1', 'source_id': 'dispute', 'sender': inv['email'], 'text': text})
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'processed'
    with database(client.app.state.config) as c:
        proposal = c.execute('SELECT * FROM agent_proposals WHERE id=?', (response.json()['proposal_id'],)).fetchone()
        assert proposal['reviewed_by'] == 'workflow-policy:1'
    detail = client.get('/api/workflow/cases/' + case['id']).json()
    assert detail['stage'] == 'disputed' and detail['balance'] == inv['balance']
    assert all(row['status'] == 'resolved' for row in detail['exceptions'])


def test_policy_gate_is_rechecked_inside_graph_execution_transaction(client, monkeypatch):
    from server import workflow
    inv, case, tenant = configure(client, monkeypatch)
    with database(client.app.state.config) as c:
        policy = workflow.current_policy(c, tenant)
    services = workflow.PolicyServices(tenant, case['id'], policy['version'])
    with database(client.app.state.config, write=True) as c:
        assert services.agent_gate(c, tenant, inv['id'], 'dispute') == []
        value = dict(policy, version=2, enabled=False)
        c.execute('INSERT INTO workflow_policies VALUES(?,?,?,?,?,?)', ('revoked', tenant, 2, workflow.f._request_json(value), 'manager', workflow.f.timestamp()))
        assert 'workflow_policy_changed' in services.agent_gate(c, tenant, inv['id'], 'dispute')


def test_verified_promise_is_recorded_only_with_explicit_counterparty_mandate(client, monkeypatch):
    inv, case, tenant = configure(client, monkeypatch)
    from server.business_time import business_today
    due = str(business_today())
    text = f'Обещаем оплатить 100 рублей {due}'
    provider(monkeypatch, tenant, 'promise', text, amount=10000, due_date=due)
    headers = inbound_headers(monkeypatch, tenant)
    payload = {'invoice_id': inv['id'], 'source': 'mailbox-1', 'source_id': 'promise-no-mandate', 'sender': inv['email'], 'text': text}
    response = client.post('/api/workflow/inbound', headers=headers, json=payload)
    assert response.json()['status'] == 'needs_decision'
    with database(client.app.state.config, write=True) as c:
        assert c.execute('SELECT COUNT(*) AS n FROM finance_promises WHERE tenant_id=?', (tenant,)).fetchone()['n'] == 0
        c.execute('UPDATE finance_counterparties SET agent_promises_allowed=1 WHERE id=?', (inv['counterparty_id'],))
    response = client.post('/api/workflow/inbound', headers=headers, json=dict(payload, source_id='promise-with-mandate'))
    assert response.json()['status'] == 'processed', response.text
    detail = client.get('/api/workflow/cases/' + case['id']).json()
    assert detail['balance'] == inv['balance'] and detail['invoices'][0]['promised_amount'] == 10000


def test_delivery_exception_resolution_requires_manager_and_preserves_balance(client, monkeypatch):
    from server import workflow
    inv, case, tenant = configure(client, monkeypatch)
    monkeypatch.setattr(workflow, 'send_email', lambda *args: (_ for _ in ()).throw(TimeoutError()))
    workflow.run_once(client.app.state.config)
    exception = client.get('/api/workflow/cases/' + case['id']).json()['exceptions'][0]
    response = client.post('/api/workflow/exceptions/' + exception['id'] + '/resolve', json={'resolution': 'Проверили почтовый сервер: письмо доставлено'})
    assert response.status_code == 200
    assert response.json()['status'] == 'resolved'
    assert client.get('/api/workflow/cases/' + case['id']).json()['balance'] == inv['balance']
    assert workflow.schedule_jobs(client.app.state.config) == 0


def test_closed_balance_keeps_due_legal_review_visible(client, monkeypatch):
    inv, case, tenant = configure(client, monkeypatch)
    from server.business_time import business_today
    deadline = client.post('/api/portfolio/invoices/' + inv['id'] + '/deadlines', json={'kind': 'court_review', 'review_on': str(business_today()), 'basis': 'Проверить определение суда по делу'})
    assert deadline.status_code == 201, deadline.text
    client.post('/api/invoices/' + inv['id'] + '/payments', json={'amount': inv['balance'], 'paid_on': str(business_today()), 'reference': 'closed'})
    item = cases(client)[0]
    assert item['stage'] == 'paid' and item['queue'] == 'needs_decision'
    assert 'срок' in item['next_action'].lower() or 'провер' in item['next_action'].lower()


def test_missed_promise_shows_follow_up_and_is_actionable(client, monkeypatch):
    from server import workflow
    from server.business_time import business_today
    from datetime import timedelta
    inv, case, tenant = configure(client, monkeypatch)
    with database(client.app.state.config, write=True) as c:
        c.execute('UPDATE invoices SET promised_amount=?,promise_date=? WHERE id=?', (10000, str(business_today() - timedelta(days=1)), inv['id']))
    item = cases(client)[0]
    assert 'наруш' in item['next_action'].lower() or 'просроч' in item['next_action'].lower()
    assert workflow.schedule_jobs(client.app.state.config) == 1


def test_accountant_can_resolve_operational_incoming_exception(client, monkeypatch):
    inv, case, tenant = configure(client, monkeypatch)
    response = client.post('/api/workflow/inbound', headers=inbound_headers(monkeypatch, tenant), json={'invoice_id': inv['id'], 'source': 'mailbox-1', 'source_id': 'unclear', 'sender': inv['email'], 'text': 'Пришлите пожалуйста акт сверки'})
    assert response.status_code == 200
    invitation = client.post('/api/workflow/invitations', json={'email': 'accountant@example.ru'}).json()
    client.post('/api/workflow/invitations/accept', json={'token': invitation['token'], 'name': 'Accountant', 'password': 'Correct-horse-24!'})
    client.post('/api/auth/logout')
    login = client.post('/api/auth/login', json={'email': 'accountant@example.ru', 'password': 'Correct-horse-24!'}).json()
    client.headers['X-CSRF-Token'] = login['csrf_token']
    issue = client.get('/api/workflow/cases/' + case['id']).json()['exceptions'][0]
    assert issue['required_role'] == 'accountant'
    resolved = client.post('/api/workflow/exceptions/' + issue['id'] + '/resolve', json={'resolution': 'Проверили письмо и подготовили документы'})
    assert resolved.status_code == 200, resolved.text


def test_same_recipient_cooldown_spans_distinct_counterparties(client, monkeypatch):
    from server import workflow
    inv, case, tenant = configure(client, monkeypatch)
    second = invoice(client, company='Other', inn='7801234567', number='Other', email=inv['email'])
    other = next(item for item in cases(client) if second['id'] in item['invoice_ids'])
    client.post('/api/workflow/cases/' + other['id'] + '/start', json={})
    calls = []
    monkeypatch.setattr(workflow, 'send_email', lambda *args: calls.append(args))
    workflow.run_once(client.app.state.config)
    assert len(calls) == 1


def test_concurrent_worker_claims_deliver_once(client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from server import workflow
    configure(client, monkeypatch)
    calls = []
    monkeypatch.setattr(workflow, 'send_email', lambda *args: calls.append(args))
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: workflow.run_once(client.app.state.config), range(2)))
    assert len(calls) == 1


def test_expired_invitation_cannot_create_account(client):
    register(client)
    invited = client.post('/api/workflow/invitations', json={'email': 'expired@example.ru'}).json()
    with database(client.app.state.config, write=True) as c:
        c.execute("UPDATE workflow_invitations SET expires_at='2000-01-01T00:00:00+00:00'")
    assert client.post('/api/workflow/invitations/accept', json={'token': invited['token'], 'name': 'Expired', 'password': 'Correct-horse-24!'}).status_code == 409
    with database(client.app.state.config) as c:
        assert c.execute("SELECT id FROM users WHERE email='expired@example.ru'").fetchone() is None


def test_legacy_unresolved_smtp_outcome_blocks_workflow(client, monkeypatch):
    from server import workflow
    inv, case, tenant = configure(client, monkeypatch)
    with database(client.app.state.config, write=True) as c:
        c.execute("INSERT INTO messages(id,tenant_id,invoice_id,subject,body,recipient,status,balance_snapshot,created_at,invalidation_reason) VALUES('uncertain',?,?,'s','b',?,'failed',?,?,'smtp_outcome_unknown')", (tenant, inv['id'], inv['email'], inv['balance'], datetime.now(timezone.utc).isoformat()))
    assert workflow.schedule_jobs(client.app.state.config) == 0


def test_verified_payment_claim_is_exception_not_money_or_promise(client, monkeypatch):
    inv, case, tenant = configure(client, monkeypatch)
    text = 'Оплатили, проверьте банк'
    provider(monkeypatch, tenant, 'payment_claim', text)
    response = client.post('/api/workflow/inbound', headers=inbound_headers(monkeypatch, tenant), json={'invoice_id': inv['id'], 'source': 'mailbox-1', 'source_id': 'payment-claim', 'sender': inv['email'], 'text': text})
    assert response.json()['status'] == 'needs_decision'
    detail = client.get('/api/workflow/cases/' + case['id']).json()
    assert detail['balance'] == inv['balance']
    assert detail['exceptions'][0]['kind'] == 'payment_claim'
    assert detail['exceptions'][0]['required_role'] == 'accountant'


def test_new_legacy_uncertainty_can_be_resolved_with_audited_evidence(client, monkeypatch):
    from server import workflow
    inv, case, tenant = configure(client, monkeypatch)
    with database(client.app.state.config, write=True) as c:
        stamp = datetime.now(timezone.utc).isoformat()
        c.execute("INSERT INTO messages(id,tenant_id,invoice_id,subject,body,recipient,status,balance_snapshot,created_at,invalidation_reason) VALUES('legacy-unknown',?,?,'s','b',?,'failed',?,?,'smtp_outcome_unknown')", (tenant, inv['id'], inv['email'], inv['balance'], stamp))
        workflow._exception(c, tenant, case['id'], inv['id'], 'delivery_unknown', 'Проверьте почтовый сервер', 'legacy-delivery:legacy-unknown')
    issue = client.get('/api/workflow/cases/' + case['id']).json()['exceptions'][0]
    response = client.post('/api/workflow/exceptions/' + issue['id'] + '/resolve', json={'resolution': 'Проверили SMTP журнал: письмо не принято; повтор возможен после интервала'})
    assert response.status_code == 200
    with database(client.app.state.config) as c:
        message = c.execute("SELECT * FROM messages WHERE id='legacy-unknown'").fetchone()
        assert message['invalidation_reason'] == 'delivery_reviewed'
        assert message['status'] == 'failed'
    assert workflow.schedule_jobs(client.app.state.config) == 0


def test_future_invoice_is_not_reminded_before_due_date(client, monkeypatch):
    from server import workflow
    from server.business_time import business_today
    from datetime import timedelta
    inv, case, tenant = configure(client, monkeypatch)
    with database(client.app.state.config, write=True) as c:
        c.execute('UPDATE invoices SET due_on=? WHERE id=?', (str(business_today() + timedelta(days=3)), inv['id']))
    assert workflow.schedule_jobs(client.app.state.config) == 0


def test_invited_password_preserves_significant_whitespace(client):
    register(client)
    invited = client.post('/api/workflow/invitations', json={'email': 'spaces@example.ru'}).json()
    password = '  Correct-horse-24!  '
    assert client.post('/api/workflow/invitations/accept', json={'token': invited['token'], 'name': 'Spaces', 'password': password}).status_code == 201
    client.post('/api/auth/logout')
    assert client.post('/api/auth/login', json={'email': 'spaces@example.ru', 'password': password}).status_code == 200


def test_case_documents_include_registered_portfolio_evidence(client):
    register(client)
    inv = invoice(client)
    response = client.post('/api/portfolio/invoices/' + inv['id'] + '/evidence', json={'kind': 'contract', 'reference': 'Договор поставки № 10', 'occurred_on': inv['issued_on']})
    assert response.status_code == 201
    detail = client.get('/api/workflow/cases/' + cases(client)[0]['id']).json()
    assert any(doc.get('reference') == 'Договор поставки № 10' for doc in detail['documents'])


def test_active_judicial_escalation_stops_ordinary_reminders(client, monkeypatch):
    from server import workflow
    inv, case, tenant = configure(client, monkeypatch)
    with database(client.app.state.config, write=True) as c:
        stamp = datetime.now(timezone.utc).isoformat()
        c.execute("INSERT INTO legal_cases VALUES('legal-active',?,?,'{}',1,'manager',?,?)", (tenant, inv['id'], stamp, stamp))
        c.execute("INSERT INTO legal_milestones VALUES('filed-active',?,'legal-active','filed','2026-10-26','Подача подтверждена','',NULL,'[]','manager',?)", (tenant, stamp))
    item = cases(client)[0]
    assert item['legal_escalation'] and item['legal_stage'] == 'filed'
    assert item['queue'] == 'needs_decision'
    assert workflow.schedule_jobs(client.app.state.config) == 0


def test_inbound_unrecognized_unicode_source_is_rejected_cleanly(client, monkeypatch):
    inv, case, tenant = configure(client, monkeypatch)
    response = client.post('/api/workflow/inbound', headers=inbound_headers(monkeypatch, tenant), json={'invoice_id': inv['id'], 'source': 'Чужой источник', 'source_id': 'bad-source', 'sender': inv['email'], 'text': 'Проверка источника'})
    assert response.status_code == 403


def test_grouped_reminder_reply_never_attributes_partial_promise_to_primary_invoice(client, monkeypatch):
    inv, initial, tenant = configure(client, monkeypatch)
    second = invoice(client, number='aggregate-second')
    merged = client.post('/api/workflow/contracts', json={'counterparty_id': inv['counterparty_id'], 'number': 'Group-1', 'invoice_ids': [inv['id'], second['id']]}).json()
    client.post('/api/workflow/cases/' + merged['case_id'] + '/start', json={})
    from server.business_time import business_today
    due = str(business_today())
    text = f'Обещаем оплатить 100 рублей {due}'
    provider(monkeypatch, tenant, 'promise', text, amount=10000, due_date=due)
    with database(client.app.state.config, write=True) as c:
        c.execute('UPDATE finance_counterparties SET agent_promises_allowed=1 WHERE id=?', (inv['counterparty_id'],))
    response = client.post('/api/workflow/inbound', headers=inbound_headers(monkeypatch, tenant), json={'invoice_id': inv['id'], 'source': 'mailbox-1', 'source_id': 'group-promise', 'sender': inv['email'], 'text': text})
    assert response.json()['status'] == 'needs_decision'
    detail = client.get('/api/workflow/cases/' + merged['case_id']).json()
    assert detail['exceptions'][0]['kind'] == 'invoice_scope_ambiguous'
    assert all(item['promised_amount'] == 0 for item in detail['invoices'])
    assert detail['balance'] == inv['balance'] + second['balance']


def test_grouped_reply_dispute_pauses_case_without_guessing_invoice_scope(client, monkeypatch):
    inv, initial, tenant = configure(client, monkeypatch)
    second = invoice(client, number='dispute-second')
    merged = client.post('/api/workflow/contracts', json={'counterparty_id': inv['counterparty_id'], 'number': 'Group-2', 'invoice_ids': [inv['id'], second['id']]}).json()
    client.post('/api/workflow/cases/' + merged['case_id'] + '/start', json={})
    text = 'Не согласны с долгом, спор по поставке'
    provider(monkeypatch, tenant, 'dispute', text)
    response = client.post('/api/workflow/inbound', headers=inbound_headers(monkeypatch, tenant), json={'invoice_id': inv['id'], 'source': 'mailbox-1', 'source_id': 'group-dispute', 'sender': inv['email'], 'text': text})
    assert response.json()['status'] == 'needs_decision'
    detail = client.get('/api/workflow/cases/' + merged['case_id']).json()
    assert detail['stage'] == 'paused' and detail['queue'] == 'needs_decision'
    assert all(item['status'] == 'open' for item in detail['invoices'])


def test_relative_promise_without_trusted_received_time_is_not_retimed(client, monkeypatch):
    inv, case, tenant = configure(client, monkeypatch)
    from server.business_time import business_today
    from datetime import timedelta
    due = str(business_today() + timedelta(days=1))
    text = 'Обещаем оплатить 100 рублей завтра'
    provider(monkeypatch, tenant, 'promise', text, amount=10000, due_date=due)
    with database(client.app.state.config, write=True) as c:
        c.execute('UPDATE finance_counterparties SET agent_promises_allowed=1 WHERE id=?', (inv['counterparty_id'],))
    response = client.post('/api/workflow/inbound', headers=inbound_headers(monkeypatch, tenant), json={'invoice_id': inv['id'], 'source': 'mailbox-1', 'source_id': 'missing-time', 'sender': inv['email'], 'text': text})
    assert response.json()['status'] == 'needs_decision'
    detail = client.get('/api/workflow/cases/' + case['id']).json()
    assert detail['exceptions'][0]['kind'] == 'received_time_required'
    assert detail['invoices'][0]['promised_amount'] == 0
