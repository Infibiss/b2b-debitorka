"""Contract-level claims keep invoice accounting separate and evidence explicit."""
from tests.test_legal_api import client, invoice, facts, document, review, bank_allocate, file_package, freeze_document_clock


def evidence(c,case_id,kind='performance',reference='УПД 10',occurred_on='2026-08-01'):
    response=c.post(f'/api/legal/cases/{case_id}/evidence',json={
        'kind':kind,'title':reference,'reference':reference,'occurred_on':occurred_on,'covers_all_invoices':True})
    assert response.status_code==201,response.text
    return response.json()


def grouped_case(c):
    first=invoice(c)
    second=invoice(c,number='Ю-002',due_on='2026-09-10',amount=20000000)
    grouped=c.post('/api/workflow/contracts',json={'counterparty_id':first['counterparty_id'],'number':'П-1','invoice_ids':[first['id'],second['id']]})
    assert grouped.status_code==201,grouped.text
    r=c.post('/api/legal/cases',json={'invoice_id':first['id'],'invoice_ids':[second['id'],first['id']],'facts':facts()})
    assert r.status_code==201,r.text
    return first,second,r.json()


def test_contract_claim_totals_payment_fees_and_second_invoice_staleness(client,monkeypatch):
    freeze_document_clock(monkeypatch)
    first,second,item=grouped_case(client)
    assert item['invoice_count']==2 and item['balance']==30000000
    evidence(client,item['id'],'contract','Договор П-1','2026-07-01');evidence(client,item['id'])
    proof=evidence(client,item['id'],'claim_dispatch','Претензия по двум счетам','2026-09-02')
    r=client.post(f"/api/legal/cases/{item['id']}/milestones",json={'stage':'claim_sent','occurred_on':'2026-09-02','reference':'Почтовая квитанция','notes':'Претензия охватывает оба счёта','evidence_ids':[proof['id']]})
    assert r.status_code==201,r.text
    bank_allocate(client,second['id'],'CONTRACT-PARTIAL',5000000,'2026-10-23')
    calc=client.post(f"/api/legal/cases/{item['id']}/calculation",json={'through_on':'2026-10-24','sanction':'none'})
    assert calc.status_code==200,calc.text
    assert calc.json()['principal_amount']==25000000
    assert len(calc.json()['invoice_calculations'])==2
    doc=document(client,item['id'],'court_order','none')
    from io import BytesIO
    from docx import Document
    rendered=Document(BytesIO(client.get(doc['download_url']).content))
    assert rendered.tables[0].rows[0].cells[0].text=='Счёт'
    assert {row.cells[0].text for row in rendered.tables[0].rows[1:]}=={first['number'],second['number']}
    assert review(client,doc['id']).status_code==200
    file_package(client,item['id'],doc)
    fee=client.get(f"/api/legal/cases/{item['id']}/fee").json()
    assert fee['pretrial_fee_amount']==300000
    assert fee['judicial_package_amount']==700000 and len(fee['package_items'])==1
    bank_allocate(client,second['id'],'CONTRACT-SECOND',1000000,'2026-10-25')
    changed=client.get(f"/api/legal/cases/{item['id']}").json()
    assert changed['balance']==24000000
    assert changed['documents'][0]['stale'] is True
    assert client.post('/api/legal/cases',json={'invoice_id':second['id'],'facts':facts()}).status_code==409
    assert client.get('/api/invoices/'+first['id']).json()['invoice']['balance']==10000000


def test_grouping_requires_same_contract_and_tenant(client):
    first=invoice(client)
    second=invoice(client,number='Ю-002')
    r=client.post('/api/legal/cases',json={'invoice_id':first['id'],'invoice_ids':[second['id']],'facts':facts()})
    assert r.status_code==422
    assert client.get('/api/legal/cases').json()['items']==[]
    assert client.post('/api/legal/cases',json={'invoice_id':first['id'],'invoice_ids':['foreign-invoice'],'facts':facts()}).status_code==404


def test_cancelled_order_needs_evidence_and_blocks_enforcement(client,monkeypatch):
    freeze_document_clock(monkeypatch)
    first,second,item=grouped_case(client)
    evidence(client,item['id'],'contract','Договор П-1','2026-07-01');evidence(client,item['id'])
    doc=document(client,item['id'],'court_order','none');assert review(client,doc['id']).status_code==200
    file_package(client,item['id'],doc)
    act=evidence(client,item['id'],'court_act','Приказ суда','2026-10-24')
    base={'occurred_on':'2026-10-24','reference':'А40-ТЕСТ','notes':'Судебный акт проверен','evidence_ids':[act['id']]}
    assert client.post(f"/api/legal/cases/{item['id']}/milestones",json=dict(base,stage='order_issued')).status_code==201
    assert client.post(f"/api/legal/cases/{item['id']}/milestones",json=dict(base,stage='order_cancelled',evidence_ids=[])).status_code==422
    assert client.post(f"/api/legal/cases/{item['id']}/milestones",json=dict(base,stage='order_cancelled')).status_code==422
    cancellation=evidence(client,item['id'],'order_cancellation','Определение об отмене','2026-10-25')
    cancelled=client.post(f"/api/legal/cases/{item['id']}/milestones",json=dict(base,stage='order_cancelled',occurred_on='2026-10-25',evidence_ids=[cancellation['id']]))
    assert cancelled.status_code==201,cancelled.text
    denied=client.post(f"/api/legal/cases/{item['id']}/documents",json={'kind':'court_order','calculation':{'through_on':'2026-10-24','sanction':'none'}})
    assert denied.status_code==422
    proof=evidence(client,item['id'],'bank_submission','Передача отменённого приказа','2026-10-24')
    assert client.post(f"/api/legal/cases/{item['id']}/milestones",json=dict(base,stage='bank_submitted',evidence_ids=[proof['id']])).status_code==409
    assert client.get(f"/api/legal/cases/{item['id']}").json()['next_action']=='Подготовить иск после отмены приказа'
    work=client.get('/api/workflow/cases').json()['items'][0]
    assert work['stage']=='legal' and work['next_action']=='Приказ отменён: подготовить иск'
    assert client.post(f"/api/legal/cases/{item['id']}/milestones",json=dict(base,stage='judgment',occurred_on='2026-10-25')).status_code==422
    # After cancellation the intended path is a newly reviewed claim, a new
    # filing, judgment and enforcement document; the old order is insufficient.
    dispatch=evidence(client,item['id'],'claim_dispatch','Квитанция претензии по договору','2026-09-11')
    assert client.post(f"/api/legal/cases/{item['id']}/milestones",json={
        'stage':'claim_sent','occurred_on':'2026-09-11','reference':'Претензия П-1',
        'notes':'Досудебный срок подтверждён','evidence_ids':[dispatch['id']]}).status_code==201
    claim=document(client,item['id'],'statement_of_claim','none')
    assert review(client,claim['id']).status_code==200
    filing_proofs=[evidence(client,item['id'],kind,'Иск: '+kind,'2026-10-26')['id'] for kind in ('duty_payment','application_copy_sent','filing_receipt')]
    filed=client.post(f"/api/legal/cases/{item['id']}/milestones",json={
        'stage':'filed','occurred_on':'2026-10-26','reference':'Квитанция подачи иска',
        'notes':'Подан проверенный иск после отмены приказа','document_id':claim['id'],'evidence_ids':filing_proofs})
    assert filed.status_code==201,filed.text
    judgment=evidence(client,item['id'],'court_act','Решение суда по иску','2026-10-27')
    assert client.post(f"/api/legal/cases/{item['id']}/milestones",json=dict(base,stage='judgment',occurred_on='2026-10-27',evidence_ids=[judgment['id']])).status_code==201
    writ=evidence(client,item['id'],'writ','Исполнительный лист по решению','2026-10-28')
    assert client.post(f"/api/legal/cases/{item['id']}/milestones",json=dict(base,stage='writ_received',occurred_on='2026-10-28',evidence_ids=[writ['id']])).status_code==201
    bank=evidence(client,item['id'],'bank_submission','Принят банком','2026-10-29')
    result=client.post(f"/api/legal/cases/{item['id']}/milestones",json=dict(base,stage='bank_submitted',occurred_on='2026-10-29',evidence_ids=[bank['id']]))
    assert result.status_code==201,result.text
    assert client.get(f"/api/legal/cases/{item['id']}/fee").json()['judicial_package_amount']==1900000


def test_existing_single_invoice_document_survives_membership_backfill(client):
    from server.database import database
    from server.legal import initialize_schema
    first=invoice(client)
    r=client.post('/api/legal/cases',json={'invoice_id':first['id'],'facts':facts(responsible_lawyer='Анна Петрова',lawyer_authority='Доверенность 7',review_due_on='2026-12-01')})
    item=r.json()
    evidence(client,item['id'],'contract','Договор','2026-07-01');evidence(client,item['id'])
    doc=document(client,item['id'],'pretrial_claim','none')
    before=client.get(doc['download_url']).content
    with database(client.app.state.config,write=True) as c:
        c.execute('DELETE FROM legal_case_invoices WHERE case_id=?',(item['id'],))
        initialize_schema(c)
    after=client.get(f"/api/legal/cases/{item['id']}").json()
    assert after['invoice_ids']==[first['id']]
    assert after['documents'][0]['stale'] is False
    assert client.get(doc['download_url']).content==before
    assert after['facts']['responsible_lawyer']=='Анна Петрова'


def test_grouped_evidence_does_not_prove_uncovered_invoice(client):
    first,second,item=grouped_case(client)
    evidence(client,item['id'],'contract','Общий договор','2026-07-01')
    response=client.post(f"/api/legal/cases/{item['id']}/evidence",json={'kind':'performance','title':'УПД только первого счёта','reference':'УПД 1','occurred_on':'2026-08-01','invoice_ids':[first['id']]})
    assert response.status_code==201,response.text
    denied=client.post(f"/api/legal/cases/{item['id']}/documents",json={'kind':'pretrial_claim','calculation':{'through_on':'2026-10-24','sanction':'none'}})
    assert denied.status_code==422 and second['number'] in denied.text
    run=client.post('/api/portfolio/runs',json={}).json()
    report={row['invoice_id']:row for row in run['items']}
    assert 'performance' in report[first['id']]['documents']
    assert 'performance' not in report[second['id']]['documents']
    no_scope=client.post(f"/api/legal/cases/{item['id']}/evidence",json={'kind':'performance','title':'Без выбора счетов','reference':'УПД 2','occurred_on':'2026-08-01'})
    assert no_scope.status_code==422
    response=client.post(f"/api/legal/cases/{item['id']}/evidence",json={'kind':'performance','title':'УПД второго счёта','reference':'УПД 2','occurred_on':'2026-08-01','invoice_ids':[second['id']]})
    assert response.status_code==201,response.text
    assert document(client,item['id'],'pretrial_claim','none')['status']=='draft'


def test_grouped_initial_payment_dates_are_explicit_per_invoice(client):
    first=invoice(client,paid_amount=2000000)
    second=invoice(client,number='Ю-002',paid_amount=3000000)
    assert client.post('/api/workflow/contracts',json={'counterparty_id':first['counterparty_id'],'number':'П-1','invoice_ids':[first['id'],second['id']]}).status_code==201
    result=client.post('/api/legal/cases',json={'invoice_id':first['id'],'invoice_ids':[second['id']],'facts':facts()})
    item=result.json()
    body={'through_on':'2026-10-24','sanction':'art395','rate_override':[{'from_on':'2026-09-01','to_on':'2026-10-24','annual_percent':'10','source':'Проверенная ставка'}],'override_reason':'Проверено по источнику ЦБ',
          'invoice_opening_reductions':{first['id']:[{'effective_on':'2026-09-10','amount':2000000,'evidence':'Выписка 1'}],second['id']:[{'effective_on':'2026-09-20','amount':3000000,'evidence':'Выписка 2'}]}}
    calc=client.post(f"/api/legal/cases/{item['id']}/calculation",json=body)
    assert calc.status_code==200,calc.text
    assert calc.json()['principal_amount']==15000000
    assert all(part['opening_payment_dates_verified'] for part in calc.json()['invoice_calculations'])
    evidence(client,item['id'],'contract','Общий договор','2026-07-01');evidence(client,item['id'])
    generated=client.post(f"/api/legal/cases/{item['id']}/documents",json={'kind':'pretrial_claim','calculation':body})
    assert generated.status_code==201,generated.text
    assert generated.json()['calculation']['principal_amount']==15000000
    body['invoice_opening_reductions'][second['id']][0]['amount']=2000000
    assert client.post(f"/api/legal/cases/{item['id']}/calculation",json=body).status_code==422


def test_each_invoice_must_match_current_balance_even_if_offsets_cancel(client):
    first,second,item=grouped_case(client)
    evidence(client,item['id'],'contract','Договор','2026-07-01');evidence(client,item['id'])
    bank_allocate(client,first['id'],'AFTER-CUTOFF',1000000,'2026-10-25')
    correction=client.post(f"/api/finance/invoices/{second['id']}/adjustments",json={'kind':'debit','amount':1000000,'effective_on':'2026-10-25','reason':'Допоставка после даты расчёта','idempotency_key':'post-cutoff-debit'})
    assert correction.status_code==200,correction.text
    # Aggregate debt remains 300000, but neither invoice matches its old claim.
    assert client.get(f"/api/legal/cases/{item['id']}").json()['balance']==30000000
    response=client.post(f"/api/legal/cases/{item['id']}/documents",json={'kind':'pretrial_claim','calculation':{'through_on':'2026-10-24','sanction':'none'}})
    assert response.status_code==422 and 'одному из счетов' in response.text
