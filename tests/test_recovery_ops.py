"""Analytics, registers, bulk actions, report builder and client-made templates."""
from datetime import timedelta

from server import recovery_rules as rules
from server.business_time import business_today
from tests.test_recovery import act, client, debtor_id, detail, invoice, ready, register, to_court  # noqa: F401


def test_dashboard_analytics_splits_debt_by_age(client):
    key, _ = ready(client)
    data = client.get('/api/recovery/dashboard').json()['analytics']
    assert sum(row['amount'] for row in data['aging']) == data['open_total'] > 0
    assert len(data['monthly']) == 12 and data['recovery_percent'] == 0
    assert any(row['status'] == 'new' for row in data['statuses']) and data['top'][0]['id'] == key


def test_bulk_hold_assign_status_and_archive(client):
    key, _ = ready(client)
    def bulk(**payload):
        response = client.post('/api/recovery/debtors/bulk', json=dict(ids=[key], **payload))
        assert response.status_code == 200 and response.json()['done'] == 1, response.text
    bulk(action='hold')
    assert detail(client, key)['hold'] is True
    bulk(action='unhold')
    bulk(action='custom_status', custom_status='Звонить в пятницу')
    assert detail(client, key)['custom_status'] == 'Звонить в пятницу'
    bulk(action='archive')
    assert detail(client, key)['archived'] is True
    assert client.get('/api/recovery/dashboard').json()['totals']['debtors'] == 0
    bulk(action='unarchive')
    assert detail(client, key)['archived'] is False


def test_bulk_generates_documents(client):
    key, _ = ready(client)
    response = client.post('/api/recovery/debtors/bulk', json=dict(ids=[key], action='document', kind='repayment_agreement'))
    assert response.json()['done'] == 1, response.text
    documents = detail(client, key)['documents']
    assert documents[0]['title'] == 'Соглашение о погашении задолженности'
    assert client.get(f"/api/recovery/documents/{documents[0]['id']}/download").status_code == 200


def test_register_keeps_court_and_enforcement_records_per_tenant(client):
    key, _ = ready(client)
    payload = dict(kind='bank_account', on_date=str(business_today()), title='АО Банк', reference='40702810000000000002', amount=100_000)
    response = client.post(f'/api/recovery/debtors/{key}/register', json=payload)
    assert response.status_code == 201, response.text
    entry = detail(client, key)['register'][0]
    assert entry['title'] == 'АО Банк' and entry['amount'] == 100_000
    assert client.delete(f"/api/recovery/register/{entry['id']}").status_code == 200
    assert detail(client, key)['register'] == []


def test_report_builder_uses_chosen_columns_and_stage(client):
    ready(client)
    text = client.get('/api/recovery/report/build.csv', params=dict(columns='name,balance,evil', stage='pretrial')).text
    header = text.lstrip('﻿').splitlines()[0]
    assert header == 'Должник;Остаток, ₽'
    assert 'ООО Север' in text
    assert 'ООО Север' not in client.get('/api/recovery/report/build.csv', params=dict(stage='court')).text
    assert 'Больше 180 дней' in client.get('/api/recovery/report/aging.csv').text


def test_duty_register_lists_debtors_waiting_for_the_fee(client):
    key, _ = ready(client)
    to_court(client, key)
    act(client, key, 'set_route', route='court_order')
    text = client.get('/api/recovery/duty-register.csv').text
    assert 'ООО Север' in text and 'Госпошлина, должник' in text


def test_client_template_generates_and_validates_variables(client):
    key, _ = ready(client)
    bad = dict(title='Письмо', stage='pretrial', heading='ПИСЬМО', body='Текст с {{nope}} переменной внутри')
    assert client.post('/api/recovery/custom-templates', json=bad).status_code == 422
    good = bad | dict(body='Уважаемые коллеги из {{debtor.name}}, долг {{principal}} руб.')
    created = client.post('/api/recovery/custom-templates', json=good)
    assert created.status_code == 201, created.text
    kind = 'custom:' + created.json()['id']
    response = client.post(f'/api/recovery/debtors/{key}/documents', json=dict(kind=kind))
    assert response.status_code == 201, response.text
    assert detail(client, key)['documents'][0]['title'] == 'Письмо'
    assert client.post(f'/api/recovery/debtors/{key}/documents', json=dict(kind='nope')).status_code == 404


def test_claim_tier_follows_the_debt_amount():
    tiers = [dict(min_amount=0, kind='claim_soft'), dict(min_amount=10_000_000, kind='claim'), dict(min_amount=50_000_000, kind='claim_final')]
    automation = dict(claim_tiers=tiers)
    assert rules.claim_kind(5_000_000, automation) == 'claim_soft'
    assert rules.claim_kind(10_000_000, automation) == 'claim'
    assert rules.claim_kind(90_000_000, automation) == 'claim_final'
    assert rules.claim_kind(90_000_000, {}) == 'claim'


def test_court_and_enforcement_automation_needs_opt_in():
    automation = rules.DEFAULT_AUTOMATION | dict(enabled=True)
    arguments = dict(balance=10_000_000, days_overdue=90, contact_allowed=True)
    assert rules.automation_decision('ready_for_court', automation=automation, **arguments) is None
    assert rules.automation_decision('ready_for_court', automation=automation | dict(auto_to_court=True), **arguments) == 'to_court'
    low = automation | dict(auto_to_court=True, court_min_amount=20_000_000)
    assert rules.automation_decision('ready_for_court', automation=low, **arguments) is None
    assert rules.automation_decision('in_force', automation=automation | dict(auto_enforcement=True), **arguments) == 'to_enforcement'
    today = business_today()
    on = automation | dict(auto_enforcement=True)
    assert rules.automation_decision('order_issued', automation=on, act_on=str(today - timedelta(days=5)), today=today, **arguments) is None
    assert rules.automation_decision('order_issued', automation=on, act_on=str(today - timedelta(days=11)), today=today, **arguments) == 'to_enforcement'


def test_new_automation_fields_save_and_default(client):
    ready(client)
    current = client.get('/api/recovery/automation').json()
    assert current['auto_to_court'] is False and current['claim_tiers'] == []
    current.pop('mail_connected')
    current |= dict(month_days=[1, 15], claim_tiers=[dict(min_amount=0, kind='claim_soft')], auto_enforcement=True)
    response = client.put('/api/recovery/automation', json=current)
    assert response.status_code == 200, response.text
    assert client.get('/api/recovery/automation').json()['month_days'] == [1, 15]
