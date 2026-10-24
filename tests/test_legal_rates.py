"""Trusted fixed-host refresh; synthetic transport responses, no network."""
import copy
import importlib
import sqlite3
from datetime import date

import httpx
import pytest


def test_trusted_rate_refresh_is_implemented():
    module=importlib.import_module("server.legal")
    assert callable(getattr(module,"refresh_rates",None)), "Daily trusted CBR refresh is not implemented"


@pytest.fixture
def rates(tmp_path,monkeypatch):
    module=importlib.import_module("server.legal")
    monkeypatch.setattr(module,"RATE_CACHE",copy.deepcopy(module.RATE_CACHE))
    monkeypatch.setattr(module,"business_today",lambda:date(2026,10,25))
    connection=sqlite3.connect(tmp_path/'rates.db');connection.row_factory=sqlite3.Row
    module.initialize_schema(connection)
    yield module,connection
    connection.close()


def response(module,target="23.10.2026"):
    rows="".join(f"<tr><td>{'.'.join(reversed(row['from_on'].split('-')))}</td><td>{row['annual_percent'].replace('.',',')}</td></tr>" for row in module.RATE_CACHE['periods'])
    return f'<html><table>{rows}<tr><td>{target}</td><td>14,00</td></tr></table></html>'


def test_refresh_persists_public_history_without_customer_data_and_handles_weekend(rates,monkeypatch):
    module,c=rates;calls=[]
    def get(url,**kwargs):
        calls.append((url,kwargs))
        return httpx.Response(200,text=response(module),request=httpx.Request('GET',url))
    monkeypatch.setattr(module.httpx,'get',get)
    result=module.refresh_rates(c,date(2026,10,25))
    assert result['verified_through']=='2026-10-25'
    assert result['last_observation_on']=='2026-10-23'
    assert calls[0][0].startswith('https://www.cbr.ru/hd_base/KeyRate/')
    assert 'UniDbQuery.To=25.10.2026' in calls[0][0]
    assert c.execute('SELECT count(*) FROM legal_rate_caches').fetchone()[0]==1
    assert module.rules()['rates_verified_through']=='2026-10-25'


def test_failed_or_malformed_refresh_never_extends_the_cached_coverage(rates,monkeypatch):
    module,c=rates
    for payload,status in (('<html>blocked</html>',200),(response(module),503)):
        monkeypatch.setattr(module.httpx,'get',lambda url,**kw:httpx.Response(status,text=payload,request=httpx.Request('GET',url)))
        with pytest.raises(ValueError):module.refresh_rates(c,date(2026,10,25))
        assert module.RATE_CACHE['verified_through']=='2026-10-24'
    assert c.execute('SELECT count(*) FROM legal_rate_caches').fetchone()[0]==0


def test_future_trusted_coverage_cannot_be_asserted(rates):
    module,c=rates
    with pytest.raises(ValueError):module.refresh_rates(c,date(2026,10,26))
