"""Old endpoints must respect the new organization roles too."""
from tests.test_api import client, register


def accountant(client):
    register(client)
    response = client.post('/api/workflow/invitations', json={'email': 'accountant-security@example.ru'})
    assert response.status_code == 201, response.text
    token = response.json()['token']
    assert client.post('/api/workflow/invitations/accept', json={'token': token, 'name': 'Бухгалтер', 'password': 'Secure-Accountant-2026!'}).status_code == 201
    client.post('/api/auth/logout')
    response = client.post('/api/auth/login', json={'email': 'accountant-security@example.ru', 'password': 'Secure-Accountant-2026!'})
    client.headers['X-CSRF-Token'] = response.json()['csrf_token']


def test_old_settings_endpoint_cannot_bypass_director_policy(client):
    accountant(client)
    assert client.patch('/api/settings', json={'cooldown_days': 0}).status_code == 403
    assert client.get('/api/auth/me').json()['user']['role'] == 'accountant'
    assert client.get('/api/settings').status_code == 200


def test_old_negotiation_policy_and_partner_grants_require_director(client):
    accountant(client)
    assert client.put('/api/negotiation/policy', json={'expected_version': 0, 'enabled': False}).status_code == 403
    assert client.post('/api/partner/grants', json={}).status_code == 403


def test_accountant_cannot_expand_contact_mandate(client):
    from tests.test_api import invoice
    accountant(client)
    inv = invoice(client)
    response = client.patch('/api/finance/counterparties/' + inv['counterparty_id'], json={'agent_promises_allowed': True})
    assert response.status_code == 403
    assert client.patch('/api/finance/counterparties/' + inv['counterparty_id'], json={'hold': True, 'hold_reason': 'Бухгалтер остановил контакты'}).status_code == 200


def test_accountant_cannot_bypass_installment_and_principal_approval(client):
    from tests.test_api import invoice
    from server.business_time import business_today
    from datetime import timedelta
    accountant(client)
    inv = invoice(client)
    tomorrow = str(business_today()+timedelta(days=1))
    response = client.post('/api/finance/invoices/' + inv['id'] + '/promise', json={'amount': 10000, 'date': tomorrow, 'installments': [{'date': tomorrow, 'amount': 10000}], 'idempotency_key': 'forbidden-schedule'})
    assert response.status_code == 403
    response = client.post('/api/finance/invoices/' + inv['id'] + '/adjustments', json={'amount': 10000, 'effective_on': str(business_today()), 'kind': 'credit', 'reason': 'Снизить долг', 'idempotency_key': 'forbidden-credit'})
    assert response.status_code == 403
    assert client.get('/api/invoices/' + inv['id']).json()['invoice']['balance'] == inv['balance']


def test_case_includes_registered_primary_documents_without_exposing_file_bytes(client):
    from tests.test_api import invoice
    from server.business_time import business_today
    register(client)
    inv = invoice(client)
    response = client.post('/api/portfolio/invoices/' + inv['id'] + '/evidence', json={'kind': 'contract', 'reference': 'Договор № 42', 'occurred_on': str(business_today())})
    assert response.status_code == 201
    item = client.get('/api/workflow/cases').json()['items'][0]
    detail = client.get('/api/workflow/cases/' + item['id']).json()
    assert any(doc.get('reference') == 'Договор № 42' for doc in detail['documents'])
    assert all('content_base64' not in doc for doc in detail['documents'])


def test_case_document_download_links_retain_private_originals(client):
    from tests.test_api import invoice
    from server.business_time import business_today
    import base64
    register(client)
    inv = invoice(client)
    content = b'%PDF-1.4\n% private evidence\n%%EOF'
    response = client.post('/api/portfolio/invoices/' + inv['id'] + '/evidence', json={'kind': 'contract', 'reference': 'Закрытый договор', 'occurred_on': str(business_today()), 'filename': 'private.pdf', 'content_base64': base64.b64encode(content).decode()})
    assert response.status_code == 201
    item = client.get('/api/workflow/cases').json()['items'][0]
    documents = client.get('/api/workflow/cases/' + item['id']).json()['documents']
    document = next(d for d in documents if d.get('reference') == 'Закрытый договор')
    assert document.get('download_url')
    assert client.get(document['download_url']).content == content


def test_accepted_ocr_is_visible_in_its_case_without_creating_financial_events(client, monkeypatch):
    from tests.test_api import invoice
    from server.database import database
    from server import yandex_services
    import base64
    register(client)
    inv = invoice(client)
    with database(client.app.state.config) as db:
        tenant = db.execute('SELECT tenant_id FROM users').fetchone()['tenant_id']
    monkeypatch.setenv('YANDEX_AGENT_TENANT_IDS', tenant)
    monkeypatch.setenv('YANDEX_API_KEY', 'test-only')
    monkeypatch.setenv('YANDEX_OCR_ENABLED', 'true')
    monkeypatch.setattr(yandex_services, '_request', lambda *a, **kw: {'result': {'textAnnotation': {'fullText': 'Договор №42'}}})
    png = b'\x89PNG\r\n\x1a\n' + b'\x00\x00\x00\rIHDR' + (1).to_bytes(4, 'big')*2 + b'\x08\x02\0\0\0' + b'\0'*4
    response = client.post('/api/yandex/documents', json={'content': base64.b64encode(png).decode(), 'mime_type': 'image/png', 'filename': 'ocr-contract.png', 'invoice_id': inv['id']})
    assert response.status_code == 200, response.text
    doc = response.json()
    accepted = client.post('/api/yandex/documents/' + doc['id'] + '/accept', json={'text': doc['text'], 'fields': {'number': '42'}, 'reason': 'Сверено с оригиналом'})
    assert accepted.status_code == 200
    item = client.get('/api/workflow/cases').json()['items'][0]
    detail = client.get('/api/workflow/cases/' + item['id']).json()
    assert any(d.get('source') == 'yandex_ocr' and d.get('filename') == 'ocr-contract.png' for d in detail['documents'])
    assert detail['balance'] == inv['balance']
