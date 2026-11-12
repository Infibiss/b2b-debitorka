"""PDF recognition, several organizations, dashboards and scheduled reports."""
import base64
import io
import json
from datetime import date, timedelta

import pytest

from server import recovery_recognition as recognition
from server import recovery_dashboards as boards
from server.business_time import business_today
from server.database import database
from tests.test_recovery import act, client, detail, invoice, ready, register, to_court  # noqa: F401

COURT_ORDER = """АРБИТРАЖНЫЙ СУД РЕСПУБЛИКИ ТАТАРСТАН
СУДЕБНЫЙ ПРИКАЗ
г. Казань 12 марта 2026 года Дело № А65-1234/2026
Взыскать с ООО Север (ИНН 7701234567) задолженность 500 000 руб."""
PAYMENT = """ПЛАТЕЖНОЕ ПОРУЧЕНИЕ № 417 от 10.03.2026
Сумма 17 500-00
ИНН 7701000001
Назначение платежа Государственная пошлина по заявлению о выдаче судебного приказа"""


def pdf(text='', size=20):
    pytest.importorskip('reportlab', reason='reportlab builds text PDFs for the upload test')
    from reportlab.pdfgen import canvas
    buffer = io.BytesIO()
    page = canvas.Canvas(buffer)
    y = 800
    for line in text.split('\n'):
        page.drawString(40, y, line)
        y -= size
    page.save()
    return buffer.getvalue()


def test_classify_court_documents():
    assert recognition.classify(COURT_ORDER) == 'court_order'
    assert recognition.classify(PAYMENT) == 'payment_order'
    assert recognition.classify('Определение об отмене судебного приказа') == 'order_cancel'
    assert recognition.classify('ОПРЕДЕЛЕНИЕ об оставлении искового заявления без движения') == 'without_motion'
    assert recognition.classify('Определение о принятии искового заявления к производству') == 'acceptance'
    assert recognition.classify('Именем Российской Федерации Р Е Ш Е Н И Е') == 'decision'
    assert recognition.classify('Просто письмо') == 'unknown'


def test_extract_fields_reads_case_date_amount_and_tax_number():
    fields = recognition.extract_fields(COURT_ORDER, 'court_order')
    assert fields['case_number'] == 'А65-1234/2026' and fields['act_on'] == '2026-03-12'
    assert fields['amount'] == 50_000_000 and fields['inns'] == ['7701234567']
    assert 'Арбитражн' in recognition.extract_fields('Арбитражный суд города Москвы, дело A40-5/2026', 'decision')['court']
    assert recognition.extract_fields('Дело A40-5/2026', 'decision')['case_number'] == 'А40-5/2026'
    payment = recognition.extract_fields(PAYMENT, 'payment_order')
    assert payment['reference'] == '417' and payment['amount'] == 1_750_000 and 'пошлина' in payment['purpose']


def test_debtor_match_prefers_case_and_refuses_ambiguity():
    first, second = dict(id='1', inn='7701234567', case_number='А65-1234/2026'), dict(id='2', inn='7701234567', case_number='')
    assert recognition.match_debtor(dict(case_number='А65-1234/2026', inns=[]), [second, first])['id'] == '1'
    assert recognition.match_debtor(dict(case_number='', inns=['7701234567']), [first, second]) is None
    assert recognition.match_debtor(dict(case_number='', inns=['7701234567']), [second])['id'] == '2'


def test_suggested_step_depends_on_status():
    assert recognition.suggest_action('court_order', 'filed') == 'order_issued'
    assert recognition.suggest_action('court_order', 'new') is None
    assert recognition.suggest_action('payment_order', 'duty_pending', PAYMENT, 1_750_000, 1_750_000, 'Государственная пошлина') == 'duty_paid'
    assert recognition.suggest_action('payment_order', 'duty_pending', PAYMENT, 1_000, 1_750_000, 'Государственная пошлина') is None
    assert recognition.suggest_action('decision', 'hearing', 'В удовлетворении иска отказать.') == 'decision_lost'
    assert recognition.suggest_action('decision', 'hearing', 'Иск удовлетворить.') == 'decision_won'


def test_upload_rejects_non_pdf_and_scan_without_ocr(client):
    register(client)
    wrong = client.post('/api/recovery/recognitions', json=dict(filename='a.pdf', content=base64.b64encode(b'hello world').decode()))
    assert wrong.status_code == 422 and 'PDF' in wrong.json()['detail']
    from pypdf import PdfWriter
    buffer = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(200, 200)
    writer.write(buffer)
    scan = client.post('/api/recovery/recognitions', json=dict(filename='scan.pdf', content=base64.b64encode(buffer.getvalue()).decode()))
    assert scan.status_code == 422 and 'скан' in scan.json()['detail']


def test_upload_proposes_and_applies_only_after_confirmation(client, monkeypatch):
    key, item = ready(client)
    to_court(client, key)
    act(client, key, 'set_route', route='court_order')
    monkeypatch.setattr(recognition, 'pdf_text', lambda raw: PAYMENT)
    duty = detail(client, key)['duty_amount']
    text = PAYMENT.replace('17 500-00', f'{duty // 100}-00').replace('7701000001', item.get('inn', '7701234567'))
    monkeypatch.setattr(recognition, 'pdf_text', lambda raw: text)
    created = client.post('/api/recovery/recognitions', json=dict(filename='pp.pdf', content=base64.b64encode(b'%PDF-1.4 stub').decode()))
    assert created.status_code == 201, created.text
    row = created.json()
    assert row['kind'] == 'payment_order' and row['debtor_id'] == key and row['action'] == 'duty_paid'
    assert detail(client, key)['status'] == 'duty_pending'
    assert len(client.get('/api/recovery/recognitions').json()['items']) == 1
    applied = client.post(f"/api/recovery/recognitions/{row['id']}/apply", json=dict(debtor_id=key, action='duty_paid', reference='417'))
    assert applied.status_code == 200, applied.text
    after = detail(client, key)
    assert after['status'] == 'duty_paid' and after['register'][0]['title'] == 'Платёжное поручение'
    assert client.get('/api/recovery/recognitions').json()['items'] == []


def test_organizations_are_separate_and_switchable(client):
    key, _ = ready(client)
    first = client.get('/api/organizations').json()
    assert len(first['items']) == 1
    created = client.post('/api/organizations', json=dict(company='ООО Вторая', inn='7702000000'))
    assert created.status_code == 201, created.text
    second = created.json()['id']
    assert client.get('/api/organizations').json()['active'] == second
    assert client.get('/api/recovery/debtors').json()['items'] == []
    assert client.get('/api/auth/me').json()['user']['company'] == 'ООО Вторая'
    assert client.get('/api/recovery/organization').json()['inn'] == '7702000000'
    assert any(row['id'] for row in client.get('/api/workflow/team').json()['members'])
    invoice(client, company='ООО Другой', inn='7703000003', number='СЧ-2')
    assert len(client.get('/api/recovery/debtors').json()['items']) == 1
    assert client.post(f"/api/organizations/{first['active']}/switch").status_code == 200
    names = [row['name'] for row in client.get('/api/recovery/debtors').json()['items']]
    assert names == ['ООО Север']
    summary = client.get('/api/organizations/summary').json()['items']
    assert len(summary) == 2 and sum(row['debtors'] for row in summary) == 2


def test_organization_switch_refuses_foreign_company(client):
    register(client)
    assert client.post('/api/organizations/not-mine/switch').status_code == 404


def test_dashboard_builds_tiles_and_aggregates_companies(client):
    ready(client)
    client.post('/api/organizations', json=dict(company='ООО Вторая'))
    invoice(client, company='ООО Другой', inn='7703000003', number='СЧ-2', amount=300_000)
    tiles = [dict(id='a', title='Долг', chart='number', measure='debt'), dict(id='b', title='По этапам', chart='columns', measure='debt', group='stage'),
             dict(id='c', title='По компаниям', chart='bars', measure='count', group='organization'), dict(id='d', title='Динамика', chart='line', measure='collected', group='month', width=2),
             dict(id='e', title='По срокам', chart='bars', measure='debt', group='aging')]
    current = client.post('/api/recovery/dashboards', json=dict(name='Моя', tiles=tiles))
    assert current.status_code == 201, current.text
    data = {row['id']: row for row in client.get(f"/api/recovery/dashboards/{current.json()['id']}/data").json()['items']}
    assert data['a']['value'] == 300_000 and data['a']['unit'] == 'money' and len(data['d']['rows']) == 12
    everything = client.post('/api/recovery/dashboards', json=dict(name='Группа', scope='all', tiles=tiles)).json()['id']
    data = {row['id']: row for row in client.get(f'/api/recovery/dashboards/{everything}/data').json()['items']}
    assert data['a']['value'] > 300_000 and len(data['c']['rows']) == 2
    copy = client.post('/api/recovery/dashboards', json=dict(name='Копия', copy_from=everything)).json()['id']
    assert len(next(row for row in client.get('/api/recovery/dashboards').json()['items'] if row['id'] == copy)['tiles']) == 5
    assert client.delete(f'/api/recovery/dashboards/{copy}').status_code == 200
    assert client.get(f'/api/recovery/dashboards/{copy}/data').status_code == 404


def test_report_due_runs_once_on_schedule():
    monday = date(2026, 11, 9)
    plan = dict(active=1, hour=9, last_sent_on=None, weekdays_json='[0]', month_day=None)
    assert boards.report_due(plan, monday, 9) and not boards.report_due(plan, monday, 8)
    assert not boards.report_due(plan | dict(last_sent_on='2026-11-09'), monday, 10)
    assert not boards.report_due(plan, monday + timedelta(days=1), 10)
    assert boards.report_due(plan | dict(weekdays_json='[]', month_day=9), monday, 10)


def test_schedule_only_sends_to_members_and_records_status(client):
    ready(client)
    me = client.get('/api/workflow/team').json()['members'][0]['id']
    body = dict(name='Для бухгалтерии', columns=['name', 'balance'], weekdays=list(range(7)), hour=0, recipients=['stranger'])
    assert client.post('/api/recovery/report-schedules', json=body).status_code == 422
    assert client.post('/api/recovery/report-schedules', json=body | dict(recipients=[me], weekdays=[])).status_code == 422
    created = client.post('/api/recovery/report-schedules', json=body | dict(recipients=[me]))
    assert created.status_code == 201, created.text
    assert 'ООО Север' in client.get(f"/api/recovery/report-schedules/{created.json()['id']}/preview.csv").text
    sent = []
    config = client.app.state.config
    assert boards.run_report_schedules(config, send=lambda c, plan, today: sent.append(plan['name']) or 'Отправлено') == 1
    assert boards.run_report_schedules(config, send=lambda c, plan, today: sent.append(plan['name']) or 'Отправлено') == 0
    assert sent == ['Для бухгалтерии']
    assert client.get('/api/recovery/report-schedules').json()['items'][0]['last_status'] == 'Отправлено'


def test_home_charts_start_from_defaults_and_keep_changes(client):
    ready(client)
    home = client.get('/api/recovery/home').json()
    assert [tile['id'] for tile in home['tiles']] == ['aging', 'monthly', 'stages', 'statuses']
    data = {row['id']: row for row in home['data']}
    assert len(data['aging']['rows']) == 6 and len(data['monthly']['rows']) == 12 and data['monthly']['months']
    assert [row['label'] for row in data['stages']['rows']] == ['Досудебная работа', 'Суд', 'Исполнение']
    tiles = home['tiles'][:1] + [dict(home['tiles'][1], chart='columns'), dict(id='n', title='Просрочено', chart='number', measure='overdue', group='stage', stage='', width=1)]
    saved = client.put('/api/recovery/home', json=dict(name='Главная', tiles=tiles))
    assert saved.status_code == 200, saved.text
    again = client.get('/api/recovery/home').json()
    assert [tile['chart'] for tile in again['tiles']] == ['columns', 'columns', 'number']
    assert next(row for row in again['data'] if row['id'] == 'n')['value'] > 0
    assert len(client.delete('/api/recovery/home').json()['tiles']) == 4


def test_tiles_saved_before_chart_types_still_render():
    from server.recovery_dashboards import normalize
    assert normalize(dict(id='x', title='t', kind='timeline', measure='debt'))['group'] == 'month'
    assert normalize(dict(id='x', title='t', kind='metric', measure='debt'))['chart'] == 'number'
