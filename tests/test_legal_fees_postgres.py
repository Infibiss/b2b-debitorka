"""Same public fee API and immutable filing references on a disposable PG schema."""
from test_storage_pg import postgres_config, postgres_client
from tests.test_legal_api import case, evidence, document, review, file_package, bank_allocate, freeze_document_clock


def test_postgres_fee_separates_mandato_packages_and_lawyer_recovery(postgres_client,monkeypatch):
    c=postgres_client
    freeze_document_clock(monkeypatch)
    inv,item=case(c)
    evidence(c,item['id'],'contract','Договор PG','2026-07-01');evidence(c,item['id'])
    bank_allocate(c,inv['id'],'PG-BEFORE-CLAIM',1000000,'2026-10-23')
    doc=document(c,item['id'],'court_order','none')
    assert review(c,doc['id']).status_code==200
    file_package(c,item['id'],doc)
    file_package(c,item['id'],doc)
    bank_allocate(c,inv['id'],'PG-AFTER-FILING',1000000,'2026-10-25')
    result=c.get(f"/api/legal/cases/{item['id']}/fee")
    assert result.status_code==200,result.text
    fee=result.json()
    assert fee['fee_amount']==fee['judicial_package_amount']==700000
    assert fee['pretrial_fee_amount']==0 and fee['lawyer_fee_amount']==120000
    assert len(fee['package_items'])==1
    assert c.get('/api/invoices/'+inv['id']).json()['invoice']['balance']==8000000
