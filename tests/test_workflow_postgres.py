"""Actual PostgreSQL parity for policy automation, private OCR and organization roles."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import base64

from test_storage_pg import postgres_config, postgres_client
from server.business_time import business_today
from server.database import database


def test_postgres_contract_automation_concurrency_and_payment_preservation(postgres_client, monkeypatch):
    from server import workflow
    c = postgres_client
    day = business_today()
    invoices = []
    for number in ('PG-WF-1', 'PG-WF-2'):
        r = c.post('/api/invoices', json={'company': 'PG Покупатель', 'inn': '7701234567', 'email': 'buyer@example.ru', 'number': number, 'issued_on': str(day-timedelta(days=30)), 'due_on': str(day-timedelta(days=10)), 'amount': 12345})
        assert r.status_code == 201, r.text
        invoices.append(r.json())
    contract = c.post('/api/workflow/contracts', json={'counterparty_id': invoices[0]['counterparty_id'], 'number': 'PG-ДОГ-1', 'invoice_ids': [i['id'] for i in invoices]})
    assert contract.status_code == 201, contract.text
    items = c.get('/api/workflow/cases').json()['items']
    assert len(items) == 1 and items[0]['balance'] == 24690
    with database(c.app.state.config) as db:
        tenant = db.execute('SELECT tenant_id FROM users').fetchone()['tenant_id']
    for key, value in {'SMTP_TENANT_ID': tenant, 'SMTP_HOST': 'smtp.example.ru', 'SMTP_FROM': 'finance@example.ru'}.items():
        monkeypatch.setenv(key, value)
    policy = c.put('/api/workflow/policy', json={'expected_version': 0, 'enabled': True, 'weekdays': list(range(7)), 'start_hour': 0, 'end_hour': 24})
    assert policy.status_code == 200, policy.text
    assert c.post('/api/workflow/cases/' + items[0]['id'] + '/start', json={}).status_code == 200
    calls = []
    monkeypatch.setattr(workflow, 'send_email', lambda *args: calls.append(args))
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda _: workflow.run_once(c.app.state.config), range(3)))
    assert len(calls) == 1
    assert c.get('/api/workflow/cases').json()['items'][0]['balance'] == 24690
    r = c.post('/api/invoices/' + invoices[0]['id'] + '/payments', json={'amount': 12345, 'paid_on': str(day), 'reference': 'PG bank evidence'})
    assert r.status_code == 200, r.text
    assert c.get('/api/workflow/cases').json()['items'][0]['balance'] == 12345
    workflow.run_once(c.app.state.config)
    assert len(calls) == 1


def test_postgres_private_document_reservation_acceptance_and_restart(postgres_client, monkeypatch):
    from server import yandex_services as y
    c = postgres_client
    with database(c.app.state.config) as db:
        tenant = db.execute('SELECT tenant_id FROM users').fetchone()['tenant_id']
    monkeypatch.setenv('YANDEX_AGENT_TENANT_IDS', tenant)
    monkeypatch.setenv('YANDEX_API_KEY', 'test-only-key')
    monkeypatch.setenv('YANDEX_OCR_ENABLED', 'true')
    calls = []
    def provider(*args, **kwargs):
        calls.append(args)
        return {'result': {'textAnnotation': {'fullText': 'Договор №42'}}}
    monkeypatch.setattr(y, '_request', provider)
    png = b'\x89PNG\r\n\x1a\n' + b'\x00\x00\x00\rIHDR' + (1).to_bytes(4, 'big')*2 + b'\x08\x02\0\0\0' + b'\0'*4
    data = {'filename': 'contract.png', 'mime_type': 'image/png', 'content': base64.b64encode(png).decode()}
    response = c.post('/api/yandex/documents', json=data)
    assert response.status_code == 200, response.text
    document = response.json()
    assert document['status'] == 'completed'
    assert c.post('/api/yandex/documents', json=data).json()['id'] == document['id']
    assert len(calls) == 1
    accepted = c.post('/api/yandex/documents/' + document['id'] + '/accept', json={'text': document['text'], 'fields': {'contract': '42'}, 'reason': 'Сверено с оригиналом'})
    assert accepted.status_code == 200, accepted.text
    assert c.get('/api/invoices').json()['items'] == []
    from server.database import initialize
    initialize(c.app.state.config)
    assert c.get('/api/yandex/documents/' + document['id']).json()['acceptance']['fields']['contract'] == '42'
