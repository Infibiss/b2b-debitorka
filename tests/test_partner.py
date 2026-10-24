"""A partner gets explicit read-only, revocable aggregate access, never owner cookies."""
import importlib
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from server.business_time import business_today


@pytest.fixture
def client(tmp_path, monkeypatch):
    for key in ('DATABASE_URL','APP_URL','RENDER_EXTERNAL_URL'):
        monkeypatch.delenv(key,raising=False)
    monkeypatch.setenv('APP_ENV','test');monkeypatch.setenv('SECURE_COOKIES','false')
    monkeypatch.setenv('DATABASE_PATH',str(tmp_path/'partner.db'))
    with TestClient(importlib.import_module('server.main').create_app()) as c:
        register(c,'partner-owner@example.ru')
        yield c


def register(c,email):
    r=c.post('/api/auth/register',json={'company':'Поставщик','name':'Владелец','email':email,'password':'Partner-tests-2026!'})
    assert r.status_code==201,r.text
    c.headers['X-CSRF-Token']=r.json()['csrf_token']


def grant(c,**changes):
    data={'partner_name':'Тестовый интегратор','purpose':'Оценка пилота по агрегированным данным','expires_in_minutes':60,'confirmed':True}
    data.update(changes)
    return c.post('/api/partner/grants',json=data)


def test_aggregate_requires_own_scoped_token_even_with_owner_session(client):
    assert client.get('/api/partner/summary').status_code==401
    assert client.get('/api/partner/summary',headers={'Authorization':'Bearer wrong'}).status_code==401


def test_grant_requires_explicit_scope_and_consent_and_token_is_shown_once(client):
    assert grant(client,confirmed=False).status_code==422
    response=grant(client)
    assert response.status_code==201,response.text
    data=response.json();assert data['scope']=='portfolio.summary' and data['token'].startswith('mt_')
    listed=client.get('/api/partner/grants').json()['items']
    assert len(listed)==1 and 'token' not in listed[0] and 'token_hash' not in listed[0]


def test_summary_only_contains_own_aggregates_and_no_contacts_or_financial_documents(client):
    r=client.post('/api/invoices',json={'company':'Секретный покупатель','email':'secret@example.ru','inn':'7701234567',
        'number':'SECRET-123','issued_on':str(business_today()-timedelta(days=20)),'due_on':str(business_today()-timedelta(days=10)),'amount':123456})
    assert r.status_code==201,r.text
    data=grant(client).json()
    register(client,'partner-other@example.ru')
    r=client.get('/api/partner/summary',headers={'Authorization':'Bearer '+data['token']})
    assert r.status_code==200,r.text
    assert r.json()['totals']['outstanding']==123456
    assert not any(x in r.text for x in ('Секретный','secret@example.ru','7701234567','SECRET-123','tenant_id'))
    assert client.post('/api/portfolio/runs',headers={'Authorization':'Bearer '+data['token']},json={}).status_code==201
    assert client.get('/api/portfolio').json()['totals']['outstanding']==0


def test_revocation_is_immediate_and_cross_tenant_cannot_revoke(client):
    data=grant(client).json()
    assert client.get('/api/partner/summary',headers={'Authorization':'Bearer '+data['token']}).status_code==200
    assert client.post(f"/api/partner/grants/{data['id']}/revoke",json={}).status_code==200
    assert client.get('/api/partner/summary',headers={'Authorization':'Bearer '+data['token']}).status_code==401
    register(client,'cannot-revoke@example.ru')
    assert client.post(f"/api/partner/grants/{data['id']}/revoke",json={}).status_code==404


def test_partner_token_cannot_be_used_as_customer_login_or_for_financial_write(client):
    data=grant(client).json()
    client.cookies.clear()
    headers={'Authorization':'Bearer '+data['token']}
    assert client.get('/api/invoices',headers=headers).status_code==401
    assert client.post('/api/portfolio/runs',headers=headers,json={}).status_code==401


def test_expired_grant_and_excessive_duration_are_rejected(client,monkeypatch):
    assert grant(client,expires_in_minutes=1441).status_code==422
    data=grant(client).json()
    from server import partner
    from datetime import datetime, timezone
    monkeypatch.setattr(partner,'utc_now',lambda:datetime.now(timezone.utc)+timedelta(days=2))
    assert client.get('/api/partner/summary',headers={'Authorization':'Bearer '+data['token']}).status_code==401
