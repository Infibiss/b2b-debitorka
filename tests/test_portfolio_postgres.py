"""New audit/partner modules run on actual PostgreSQL, including restart."""
import importlib
from datetime import timedelta

from fastapi.testclient import TestClient

from test_storage_pg import postgres_config, postgres_client
from server.business_time import business_today


def test_real_postgres_portfolio_documents_deadline_partner_and_restart(postgres_client):
    c=postgres_client
    inv=c.post('/api/invoices',json={'company':'PG Портфель','inn':'7701234567','number':'PG-AUDIT',
        'issued_on':str(business_today()-timedelta(days=20)),'due_on':str(business_today()-timedelta(days=10)),'amount':123456}).json()
    doc=c.post(f"/api/portfolio/invoices/{inv['id']}/evidence",json={'kind':'contract','reference':'Договор PG №1','occurred_on':inv['issued_on']})
    assert doc.status_code==201,doc.text
    deadline=c.post(f"/api/portfolio/invoices/{inv['id']}/deadlines",json={'kind':'court_review','review_on':str(business_today()),'basis':'Проверить документы по действующему делу'})
    assert deadline.status_code==201,deadline.text
    run=c.post('/api/portfolio/runs',json={})
    assert run.status_code==201,run.text
    assert run.json()['items'][0]['next_action']['code']=='lawyer_review'
    grant=c.post('/api/partner/grants',json={'partner_name':'PG Партнёр','purpose':'Приёмка агрегированного отчёта','expires_in_minutes':60,'confirmed':True})
    assert grant.status_code==201,grant.text
    token=grant.json()['token']
    assert c.get('/api/partner/summary',headers={'Authorization':'Bearer '+token}).json()['totals']['outstanding']==123456
    with TestClient(importlib.import_module('server.main').create_app()) as resumed:
        login=resumed.post('/api/auth/login',json={'email':'postgres@example.ru','password':'Postgres-test-2026!'})
        assert login.status_code==200,login.text
        resumed.headers['X-CSRF-Token']=login.json()['csrf_token']
        assert resumed.get('/api/portfolio').json()['id']==run.json()['id']
        assert resumed.get('/api/portfolio').json()['stale'] is False
        response=resumed.post(f"/api/portfolio/deadlines/{deadline.json()['id']}/resolve",json={'reason':'Юрист завершил проверку документов'})
        assert response.status_code==200,response.text
        assert resumed.get('/api/portfolio').json()['stale'] is True
        assert resumed.post(f"/api/partner/grants/{grant.json()['id']}/revoke",json={}).status_code==200
        assert resumed.get('/api/partner/summary',headers={'Authorization':'Bearer '+token}).status_code==401
