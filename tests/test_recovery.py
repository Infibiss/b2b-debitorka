"""Debtor pipeline: stages, guards, documents, automation and financing."""
from datetime import date, timedelta

import pytest

from server import financing, recovery_rules as rules
from server.business_time import business_today
from server.database import database
from tests.test_api import client, invoice, register  # noqa: F401

ORGANIZATION = dict(full_name='ООО Поставка', inn='7701000001', ogrn='1027700000001', legal_address='Москва, ул. Ленина, 1',
                    bank_details='р/с 40702810000000000001', signatory='Директор Анна Иванова', poa_number='Д-7')
DETAILS = dict(custom_status='', legal_address='Казань, ул. Мира, 2', ogrn='1021600000001', contract='№ 12 от 10.01.2026',
               performance_documents='УПД № 5 от 20.01.2026', court_name='Арбитражный суд Республики Татарстан', court_address='Казань, ул. Ново-Песочная, 40')


def debtor_id(client):
    return client.get('/api/recovery/debtors').json()['items'][0]['id']


def detail(client, key):
    response = client.get(f'/api/recovery/debtors/{key}')
    assert response.status_code == 200, response.text
    return response.json()


def act(client, key, action, status=200, **payload):
    response = client.post(f'/api/recovery/debtors/{key}/actions', json=dict(action=action, **payload))
    assert response.status_code == status, response.text
    return response.json()


def evidence(client, invoice_id):
    for kind in ('contract', 'performance'):
        response = client.post(f'/api/portfolio/invoices/{invoice_id}/evidence', json=dict(kind=kind, reference=f'{kind}-1', occurred_on=str(business_today() - timedelta(days=20))))
        assert response.status_code == 201, response.text


def ready(client, amount=50_000_000):
    register(client)
    item = invoice(client, amount=amount)
    key = item['counterparty_id']
    assert client.put('/api/recovery/organization', json=ORGANIZATION).status_code == 200
    assert client.patch(f'/api/recovery/debtors/{key}', json=DETAILS).status_code == 200
    evidence(client, item['id'])
    return key, item


def back_date_claim(client, key):
    config = client.app.state.config
    with database(config, write=True) as connection:
        connection.execute('UPDATE recovery_debtors SET claim_sent_on=? WHERE counterparty_id=?', (str(business_today() - timedelta(days=31)), key))


def to_court(client, key):
    act(client, key, 'start')
    act(client, key, 'prepare_claim')
    act(client, key, 'send_claim', sent_on=str(business_today()), reference='80091234567890')
    back_date_claim(client, key)
    assert detail(client, key)['status'] == 'ready_for_court'
    act(client, key, 'to_court')


def test_rules_route_and_duty():
    assert rules.recommend_route(75_000_000, disputed=False, order_cancelled=False)['route'] == rules.COURT_ORDER
    assert rules.recommend_route(75_000_001, disputed=False, order_cancelled=False)['route'] == rules.LAWSUIT
    assert rules.recommend_route(100, disputed=True, order_cancelled=False)['route'] == rules.LAWSUIT
    assert rules.recommend_route(100, disputed=False, order_cancelled=True)['route'] == rules.LAWSUIT
    assert rules.duty_amount(60_000_000, rules.LAWSUIT) == 3_500_000
    assert rules.duty_amount(60_000_000, rules.COURT_ORDER) == 1_750_000


def test_time_and_money_move_status_without_writes():
    today = date(2026, 11, 8)
    automation = rules.DEFAULT_AUTOMATION
    assert rules.effective_status(dict(status='court_prep'), today, 0, automation) == 'paid'
    promise = dict(status='promise', promise_date='2026-11-01')
    assert rules.effective_status(promise, today, 100, automation) == 'promise_broken'
    assert rules.effective_status(dict(promise, promise_date='2026-11-07'), today, 100, automation) == 'promise'
    sent = dict(status='claim_sent', claim_sent_on='2026-10-09', pretrial_days=30)
    assert rules.effective_status(sent, today, 100, automation) == 'ready_for_court'
    assert rules.effective_status(dict(sent, claim_sent_on='2026-10-10'), today, 100, automation) == 'claim_sent'


def test_evidence_must_cover_every_open_invoice():
    rows = [dict(invoice_id='a', kind='contract'), dict(invoice_id='a', kind='performance'), dict(invoice_id='b', kind='contract')]
    report = rules.evidence_report(['a', 'b'], rows, has_poa=True, claim_proof=True)
    assert not report['ready_for_court'] and report['missing'] == ['performance']


def test_full_court_order_path_ends_paid(client):
    key, item = ready(client)
    assert detail(client, key)['status'] == 'new'
    to_court(client, key)
    state = detail(client, key)
    assert state['stage'] == 'court' and state['route'] == rules.COURT_ORDER
    act(client, key, 'set_route', route=rules.COURT_ORDER)
    assert detail(client, key)['duty_amount'] >= 800_000
    act(client, key, 'duty_paid', reference='ПП-1')
    act(client, key, 'send_to_lawyer')
    act(client, key, 'lawyer_approve')
    today = str(business_today())
    act(client, key, 'file', filed_on=today, reference='Мой арбитр 1')
    act(client, key, 'order_issued', case_number='А65-1/2026', act_on=today)
    assert act(client, key, 'to_enforcement')['status'] == 'writ_received'
    act(client, key, 'send_bank', reference='Банк 1')
    assert detail(client, key)['stage'] == 'enforcement'
    assert client.post(f"/api/invoices/{item['id']}/payments", json=dict(amount=item['balance'], paid_on=today, reference='оплата')).status_code in (200, 201)
    assert detail(client, key)['status'] == 'paid'
    assert {row['kind'] for row in detail(client, key)['documents']} == {'claim', rules.COURT_ORDER}


def test_cancelled_order_forces_lawsuit(client):
    key, _ = ready(client)
    to_court(client, key)
    act(client, key, 'set_route', route=rules.COURT_ORDER)
    act(client, key, 'duty_paid', reference='ПП-1')
    act(client, key, 'send_to_lawyer')
    act(client, key, 'lawyer_approve')
    today = str(business_today())
    act(client, key, 'file', filed_on=today, reference='1')
    act(client, key, 'order_issued', case_number='А65-1', act_on=today)
    act(client, key, 'order_cancelled', act_on=today)
    state = detail(client, key)
    assert state['status'] == 'lawsuit_prep' and state['route'] == rules.LAWSUIT
    act(client, key, 'set_route', 409, route=rules.COURT_ORDER)
    act(client, key, 'set_route', route=rules.LAWSUIT)


def test_court_needs_documents_and_claim(client):
    register(client)
    item = invoice(client, amount=50_000_000)
    key = item['counterparty_id']
    client.put('/api/recovery/organization', json=ORGANIZATION)
    client.patch(f'/api/recovery/debtors/{key}', json=DETAILS)
    act(client, key, 'to_court', 409)
    act(client, key, 'prepare_claim')
    act(client, key, 'send_claim', sent_on=str(business_today()), reference='track')
    back_date_claim(client, key)
    message = act(client, key, 'to_court', 409)
    assert 'Договор' in message['detail'] and 'исполнения' in message['detail']


def test_claim_lists_missing_details(client):
    register(client)
    key = invoice(client, amount=50_000_000)['counterparty_id']
    response = client.post(f'/api/recovery/debtors/{key}/actions', json=dict(action='prepare_claim'))
    assert response.status_code == 422 and 'Ваш ОГРН' in response.json()['detail']
    assert detail(client, key)['status'] == 'new'


def test_court_decision_is_manager_only(client):
    key, _ = ready(client)
    act(client, key, 'start')
    act(client, key, 'prepare_claim')
    act(client, key, 'send_claim', sent_on=str(business_today()), reference='track')
    back_date_claim(client, key)
    invitation = client.post('/api/workflow/invitations', json=dict(email='acc@example.ru'))
    assert invitation.status_code == 201, invitation.text
    client.post('/api/workflow/invitations/accept', json=dict(token=invitation.json()['token'], name='Бухгалтер', password='Correct-horse-24!'))
    client.post('/api/auth/logout')
    login = client.post('/api/auth/login', json=dict(email='acc@example.ru', password='Correct-horse-24!'))
    client.headers['X-CSRF-Token'] = login.json()['csrf_token']
    act(client, key, 'to_court', 403)


def test_debtors_are_tenant_scoped(client):
    key, _ = ready(client)
    client.post('/api/auth/logout')
    register(client, email='other@example.ru')
    assert client.get(f'/api/recovery/debtors/{key}').status_code == 404
    assert client.post(f'/api/recovery/debtors/{key}/actions', json=dict(action='start')).status_code == 404


def test_bankruptcy_needs_threshold_and_court_act():
    facts = dict(has_court_act=False, kind='company', balance=300_000_000)
    assert 'судебный акт' in rules.guard('bankruptcy_intent', 'no_assets', facts=facts)
    assert 'порога' in rules.guard('bankruptcy_intent', 'no_assets', facts=dict(facts, has_court_act=True, balance=100_000_000))
    assert rules.guard('bankruptcy_intent', 'no_assets', facts=dict(facts, has_court_act=True, kind='sole_proprietor', balance=60_000_000)) is None


def test_automation_starts_but_never_goes_to_court(client):
    key, _ = ready(client)
    settings = {k: v for k, v in rules.DEFAULT_AUTOMATION.items()} | dict(enabled=True, auto_prepare_claim=True, claim_after_overdue_days=5)
    assert client.put('/api/recovery/automation', json=settings).status_code == 200
    from server.recovery import run_automation
    config = client.app.state.config
    assert run_automation(config) == 1 and detail(client, key)['status'] == 'reminders'
    assert run_automation(config) == 1 and detail(client, key)['status'] == 'claim_ready'
    assert run_automation(config) == 0


def test_dashboard_onboarding_and_report(client):
    key, _ = ready(client)
    data = client.get('/api/recovery/dashboard').json()
    done = {item['key'] for item in data['onboarding']['items'] if item['done']}
    assert {'organization', 'debtors', 'poa', 'evidence'} <= done and 'mail' not in done
    assert data['tasks'][0]['id'] == key and data['totals']['debtors'] == 1
    assert client.get('/api/recovery/report').json()['stages'][0]['count'] == 1
    assert 'ООО Север' in client.get('/api/recovery/report.csv').text


def test_csv_neutralizes_formulas():
    from server.recovery import csv_safe
    assert csv_safe('=HYPERLINK("x")').startswith("'=")


def test_template_rejects_unknown_variables_and_resets(client):
    ready(client)
    assert client.put('/api/recovery/templates/claim', json=dict(body='Текст с {{unknown.var}} переменной')).status_code == 422
    assert client.put('/api/recovery/templates/claim', json=dict(body='Новый текст претензии для {{debtor.name}}')).status_code == 200
    item = next(row for row in client.get('/api/recovery/templates').json()['items'] if row['kind'] == 'claim')
    assert item['body'].startswith('Новый')
    client.delete('/api/recovery/templates/claim')
    item = next(row for row in client.get('/api/recovery/templates').json()['items'] if row['kind'] == 'claim')
    assert item['body'] == item['default_body']


def test_financing_offer_request_and_limits(client):
    key, _ = ready(client)
    offers = detail(client, key)['financing']['items']
    advance = next(item for item in offers if item['id'] == 'recovery_advance')
    assert advance['eligible'] and advance['amount_to'] == 25_000_000
    assert not next(item for item in offers if item['id'] == 'judgment_advance')['eligible']
    factoring = next(item for item in offers if item['id'] == 'factoring')
    assert factoring['eligible']
    url = f'/api/financing/debtors/{key}/requests'
    assert client.post(url, json=dict(product_id='factoring', amount=factoring['amount_to'] + 1, consent=True)).status_code == 422
    assert client.post(url, json=dict(product_id='factoring', amount=factoring['amount_from'], consent=False)).status_code == 422
    created = client.post(url, json=dict(product_id='factoring', amount=factoring['amount_from'], consent=True))
    assert created.status_code == 201, created.text
    assert client.post(url, json=dict(product_id='factoring', amount=factoring['amount_from'], consent=True)).status_code == 409
    assert client.post(f"/api/financing/requests/{created.json()['id']}/withdraw", json={}).json()['status'] == 'withdrawn'
    assert client.post(url, json=dict(product_id='factoring', amount=factoring['amount_from'], consent=True)).status_code == 201


def test_financing_refused_for_dispute_and_bankrupt(client):
    product = financing.PRODUCTS['factoring']
    view = dict(stage='pretrial', status='dispute', balance=50_000_000, days_overdue=5, evidence_score=100)
    assert 'Спор с должником нужно снять' in financing.assess(product, view, solvency_state='active', has_court_act=False)
    view['status'] = 'reminders'
    assert financing.assess(product, view, solvency_state='active', has_court_act=False) == []
    assert financing.assess(product, view, solvency_state='stop', has_court_act=False)
    assert financing.assess(financing.PRODUCTS['judgment_advance'], dict(view, stage='court'), solvency_state='active', has_court_act=False) == ['Нужен вступивший в силу судебный акт']


def test_repayment_tracks_bank_receipts_after_funding(client):
    key, item = ready(client)
    with database(client.app.state.config, write=True) as connection:
        tenant = connection.execute('SELECT tenant_id FROM invoices WHERE id=?', (item['id'],)).fetchone()['tenant_id']
        connection.execute('''INSERT INTO financing_requests(id,tenant_id,counterparty_id,product_id,debtor_name,amount,balance_snapshot,status,funded_amount,repay_amount,funded_on,consent_at,created_by,created_at,updated_at)
            VALUES('f1',?,?,'factoring','ООО Север',1000,1000,'funded',1000,1500,?,'x','x','x','x')''', (tenant, key, str(business_today() - timedelta(days=5))))
    row = client.get('/api/financing/requests').json()['items'][0]
    assert row['remaining_amount'] == 1500 and row['repaid_amount'] == 0


def test_claim_is_issued_without_interest_when_rates_are_unavailable():
    from server import recovery_templates as templates
    template = dict(address='', body='Сумма {{principal}}. {{interest_text}}')
    assert templates.missing_variables(template, {'principal': '100', 'interest_text': ' '}) == []
    assert templates.missing_variables(template, {'principal': '', 'interest_text': ' '}) == ['principal']


def test_platform_dadata_key_serves_clients_without_their_own(monkeypatch):
    from server import integration_providers as providers
    monkeypatch.setenv('MANDATO_INTEGRATIONS_JSON', '[]')
    monkeypatch.delenv('DADATA_API_KEY', raising=False)
    assert providers.binding('tenant', 'dadata') is None
    monkeypatch.setenv('DADATA_API_KEY', 'platform-key')
    assert providers.binding('tenant', 'dadata')['token'] == 'platform-key'
    assert providers.configured(providers.binding('tenant', 'dadata'), 'dadata')
    assert providers.binding('tenant', 'tbank') is None
    own = '[{"tenant_id":"tenant","provider":"dadata","token":"own-key"}]'
    monkeypatch.setenv('MANDATO_INTEGRATIONS_JSON', own)
    assert providers.binding('tenant', 'dadata')['token'] == 'own-key'
