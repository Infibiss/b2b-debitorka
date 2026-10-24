"""Bounded internal negotiations against actual authenticated API and ledger."""
from datetime import timedelta

from test_finance import client, invoice
from server.business_time import business_today


def policy(client, **changes):
    current = client.get('/api/negotiation/policy')
    assert current.status_code == 200, current.text
    body = dict(enabled=True,auto_accept=False,max_promise_days=30,max_installments=6,max_discount_bps=0,
                allowed_kinds=['promise','installment','document_request','dispute','payment_claim'],expected_version=current.json()['version'])
    body.update(changes)
    response = client.put('/api/negotiation/policy', json=body)
    assert response.status_code == 200, response.text
    return response.json()


def proposal(client,item, **changes):
    body = dict(invoice_id=item['id'],kind='promise',amount=30000,due_on=str(business_today()+timedelta(days=3)),
        confirmed_by_operator=True,evidence='Должник просит зафиксировать частичное обещание',expires_on=str(business_today()+timedelta(days=2)),idempotency_key='proposal-1')
    body.update(changes)
    response = client.post('/api/negotiation/proposals',json=body)
    assert response.status_code == 201, response.text
    return response.json()


def mandate(client,item, **changes):
    response = client.patch(f"/api/finance/counterparties/{item['counterparty_id']}",json=dict(agent_promises_allowed=True,**changes))
    assert response.status_code == 200,response.text


def test_no_policy_is_disabled_and_cannot_accept(client):
    item = invoice(client)
    current = client.get('/api/negotiation/policy')
    assert current.status_code == 200,current.text
    assert current.json()['enabled'] is False and current.json()['version'] == 0
    data = proposal(client,item)
    assert data['status'] == 'handoff' and 'policy_disabled' in data['reasons']
    assert client.post(f"/api/negotiation/proposals/{data['id']}/execute",json={}).status_code == 409


def test_partial_installment_acceptance_is_internal_idempotent_and_preserves_debt(client):
    item = invoice(client); mandate(client,item); policy(client)
    dates = [str(business_today()+timedelta(days=i)) for i in (2,3)]
    data = proposal(client,item,kind='installment',installments=[dict(date=dates[0],amount=10000),dict(date=dates[1],amount=20000)])
    assert data['status'] == 'review_required'
    accepted = client.post(f"/api/negotiation/proposals/{data['id']}/review",json=dict(decision='approve',reason='Проверено')).json()
    assert accepted['status'] == 'accepted'
    url = f"/api/negotiation/proposals/{data['id']}/execute"
    first, second = client.post(url,json={}),client.post(url,json={})
    assert first.status_code == second.status_code == 200
    assert first.json()['outcome'] == second.json()['outcome']
    current = client.get(f"/api/invoices/{item['id']}").json()['invoice']
    assert current['balance'] == 100000 and current['promised_amount'] == 30000
    assert len(client.get(f"/api/negotiation/proposals/{data['id']}").json()['events']) == 3


def test_auto_internal_acceptance_requires_explicit_policy_and_mandate(client):
    item = invoice(client);policy(client,auto_accept=True)
    blocked = proposal(client,item)
    assert blocked['status'] == 'handoff' and 'promise_mandate_required' in blocked['reasons']
    mandate(client,item)
    data = proposal(client,item,idempotency_key='enabled')
    assert data['status'] == 'accepted'
    assert client.post(f"/api/negotiation/proposals/{data['id']}/execute",json={}).status_code == 200


def test_payment_between_review_and_execute_invalidates_snapshot(client):
    item = invoice(client);mandate(client,item);policy(client)
    data = proposal(client,item)
    approved = client.post(f"/api/negotiation/proposals/{data['id']}/review",json=dict(decision='approve',reason='Проверено'))
    assert approved.status_code == 200, approved.text
    payment = client.post(f"/api/invoices/{item['id']}/payments",json=dict(amount=1000,paid_on=str(business_today()),reference='intervening'))
    assert payment.status_code == 200, payment.text
    response = client.post(f"/api/negotiation/proposals/{data['id']}/execute",json={})
    assert response.status_code == 409,response.text
    assert client.get(f"/api/negotiation/proposals/{data['id']}").json()['status'] == 'handoff'
    assert client.get(f"/api/invoices/{item['id']}").json()['invoice']['promised_amount'] == 0


def test_policy_revision_revocation_and_stop_list_require_handoff(client):
    item = invoice(client);mandate(client,item);policy(client,auto_accept=True)
    data = proposal(client,item)
    policy(client,auto_accept=True)
    assert client.post(f"/api/negotiation/proposals/{data['id']}/execute",json={}).status_code == 409
    revoked = proposal(client,item,idempotency_key='revoked')
    mandate(client,item,mandate_expires_on=str(business_today()-timedelta(days=1)))
    assert client.post(f"/api/negotiation/proposals/{revoked['id']}/execute",json={}).status_code == 409
    mandate(client,item,mandate_expires_on=None,hold=True,hold_reason='Стоп-лист')
    assert proposal(client,item,idempotency_key='held')['status'] == 'handoff'


def test_refused_and_expired_offers_cannot_execute(client):
    item = invoice(client);mandate(client,item);policy(client)
    data = proposal(client,item)
    rejected = client.post(f"/api/negotiation/proposals/{data['id']}/review",json=dict(decision='reject',reason='Отказ должника'))
    assert rejected.json()['status'] == 'rejected'
    assert client.post(f"/api/negotiation/proposals/{data['id']}/execute",json={}).status_code == 409
    expired = proposal(client,item,idempotency_key='expired',expires_on=str(business_today()-timedelta(days=1)))
    assert expired['status'] == 'expired'
    assert client.post(f"/api/negotiation/proposals/{expired['id']}/execute",json={}).status_code == 409


def test_discount_and_payment_claim_never_write_off_or_confirm_money(client):
    item = invoice(client);mandate(client,item)
    policy(client,auto_accept=True,max_discount_bps=500,allowed_kinds=['discount','payment_claim'])
    discount = proposal(client,item,kind='discount',amount=None,due_on=None,discount_bps=500)
    assert discount['status'] == 'accepted'
    executed = client.post(f"/api/negotiation/proposals/{discount['id']}/execute",json={})
    assert executed.status_code == 200,executed.text
    assert executed.json()['outcome']['action'] == 'concession_recorded_for_review'
    claim = proposal(client,item,kind='payment_claim',idempotency_key='claim')
    assert client.post(f"/api/negotiation/proposals/{claim['id']}/execute",json={}).json()['outcome']['action'] == 'verify_payment'
    current = client.get(f"/api/invoices/{item['id']}").json()['invoice']
    assert current['balance'] == 100000 and current['paid_amount'] == 0


def test_outside_bound_ambiguous_invalid_schedule_and_policy_conflict(client):
    item = invoice(client);mandate(client,item);policy(client,max_promise_days=2)
    assert proposal(client,item)['status'] == 'handoff'
    assert proposal(client,item,idempotency_key='ambiguous',ambiguous=True)['status'] == 'handoff'
    bad = dict(invoice_id=item['id'],kind='installment',amount=30000,due_on=str(business_today()+timedelta(days=2)),
        installments=[dict(date=str(business_today()+timedelta(days=2)),amount=1)],evidence='test',expires_on=str(business_today()),idempotency_key='bad')
    assert client.post('/api/negotiation/proposals',json=bad).status_code == 422
    assert client.put('/api/negotiation/policy',json=dict(enabled=True,expected_version=0)).status_code == 409


def test_cross_tenant_policy_proposals_and_execution_are_isolated(client):
    item = invoice(client);mandate(client,item);policy(client,auto_accept=True)
    data = proposal(client,item)
    registration = client.post('/api/auth/register', json=dict(name='Другой',company='Другой',email='negotiation-other@example.ru',password='Negotiation-testing2026'))
    client.headers['X-CSRF-Token'] = registration.json()['csrf_token']
    assert client.get('/api/negotiation/policy').json()['enabled'] is False
    assert client.get('/api/negotiation/proposals').json()['items'] == []
    for suffix in ('','/execute','/review'):
        url = f"/api/negotiation/proposals/{data['id']}"+suffix
        response = client.get(url) if not suffix else client.post(url,json={} if suffix=='/execute' else dict(decision='approve',reason='Нет'))
        assert response.status_code == 404


def test_unverified_terms_never_get_automatic_acceptance(client):
    item = invoice(client);mandate(client,item);policy(client,auto_accept=True)
    data = proposal(client,item,confirmed_by_operator=False)
    assert data['status'] == 'handoff' and 'unverified_proposal' in data['reasons']
    assert client.post(f"/api/negotiation/proposals/{data['id']}/review",json=dict(decision='approve',reason='Нельзя обойти проверку')).status_code == 409


def test_execution_rechecks_today_including_schedule_and_expiry(client,monkeypatch):
    from server import negotiation
    today = business_today()
    item = invoice(client);mandate(client,item);policy(client,auto_accept=True)
    data = proposal(client,item,expires_on=str(today),due_on=str(today))
    monkeypatch.setattr(negotiation,'business_today',lambda: today+timedelta(days=1))
    result = client.post(f"/api/negotiation/proposals/{data['id']}/execute",json={})
    assert result.status_code == 409,result.text
    current = client.get(f"/api/negotiation/proposals/{data['id']}").json()
    assert current['status'] == 'expired' and 'offer_expired' in current['reasons']


def test_proposal_retry_is_same_record_and_changed_payload_conflicts(client):
    item = invoice(client);mandate(client,item);policy(client,auto_accept=True)
    first = proposal(client,item)
    second = proposal(client,item)
    assert first['id'] == second['id'] and len(second['events']) == 1
    changed = dict(invoice_id=item['id'],kind='promise',amount=40000,due_on=str(business_today()+timedelta(days=3)),
        confirmed_by_operator=True,evidence='Changed offer',expires_on=str(business_today()+timedelta(days=2)),idempotency_key='proposal-1')
    assert client.post('/api/negotiation/proposals',json=changed).status_code == 409


def test_document_request_and_dispute_are_internal_but_dispute_stops_contacts(client):
    item = invoice(client);policy(client,auto_accept=True)
    document = proposal(client,item,kind='document_request',amount=None,due_on=None)
    result = client.post(f"/api/negotiation/proposals/{document['id']}/execute",json={})
    assert result.json()['outcome']['action'] == 'request_documents'
    dispute = proposal(client,item,kind='dispute',amount=None,due_on=None,idempotency_key='dispute')
    response = client.post(f"/api/negotiation/proposals/{dispute['id']}/execute",json={})
    assert response.status_code == 200,response.text
    assert client.get(f"/api/invoices/{item['id']}").json()['invoice']['status'] == 'disputed'
    assert proposal(client,item,idempotency_key='after-dispute')['status'] == 'handoff'


def test_concurrent_execution_records_one_promise_and_one_outcome(client):
    from concurrent.futures import ThreadPoolExecutor
    from server.database import database
    item = invoice(client);mandate(client,item);policy(client,auto_accept=True)
    data = proposal(client,item)
    def execute(_):
        return client.post(f"/api/negotiation/proposals/{data['id']}/execute",json={})
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(execute,range(4)))
    assert all(response.status_code == 200 for response in responses)
    assert len({response.json()['outcome']['promise']['id'] for response in responses}) == 1
    with database(client.app.state.config) as c:
        assert c.execute('SELECT COUNT(*) AS n FROM finance_promises WHERE invoice_id=?',(item['id'],)).fetchone()['n'] == 1
        assert c.execute("SELECT COUNT(*) AS n FROM negotiation_events WHERE proposal_id=? AND event_type='executed'",(data['id'],)).fetchone()['n'] == 1


def test_strict_money_boolean_and_schedule_bounds(client):
    item = invoice(client);mandate(client,item);policy(client,max_installments=1)
    dates = [str(business_today()+timedelta(days=i)) for i in (2,3)]
    data = proposal(client,item,kind='installment',installments=[dict(date=dates[0],amount=10000),dict(date=dates[1],amount=20000)])
    assert data['status'] == 'handoff' and 'installments_outside_policy_or_mandate' in data['reasons']
    body = dict(invoice_id=item['id'],kind='promise',amount=True,due_on=dates[0],evidence='Strict amount',expires_on=dates[0],idempotency_key='strict')
    assert client.post('/api/negotiation/proposals',json=body).status_code == 422
    body.update(amount=1000,confirmed_by_operator='true')
    assert client.post('/api/negotiation/proposals',json=body).status_code == 422


def test_evaluate_disables_ambient_langsmith_tracing_for_private_business_state(client,monkeypatch):
    from types import SimpleNamespace
    from langsmith import tracing_context
    from langsmith.run_helpers import get_tracing_context
    from server import negotiation
    from server.database import database

    item=invoice(client)
    monkeypatch.setenv('LANGSMITH_TRACING','true')
    monkeypatch.setenv('LANGCHAIN_TRACING_V2','true')
    calls=[]
    def inspect_private_state(state):
        # Replace the graph boundary, so this regression never creates a trace
        # or initializes a tracing transport even with ambient tracing enabled.
        assert get_tracing_context()['enabled'] is False
        assert state['terms']['evidence']=='Private customer correspondence fixture'
        assert state['snapshot']['invoice']['balance']==100000
        calls.append(state['snapshot']['snapshot_hash'])
        return {'status':'review_required'}
    monkeypatch.setattr(negotiation,'NEGOTIATION_GRAPH',SimpleNamespace(invoke=inspect_private_state))
    with database(client.app.state.config) as c:
        tenant=c.execute('SELECT tenant_id FROM invoices WHERE id=?',(item['id'],)).fetchone()['tenant_id']
        with tracing_context(enabled=True):
            assert get_tracing_context()['enabled'] is True
            result=negotiation.evaluate(c,tenant,item['id'],{'kind':'payment_claim','evidence':'Private customer correspondence fixture'})
            assert get_tracing_context()['enabled'] is True
    assert result=={'status':'review_required'} and len(calls)==1
