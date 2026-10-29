"""Real legal router, authenticated API and ledger; only disposable databases."""
import importlib
import io
import json
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient


def test_legal_router_contract_is_implemented():
    module=importlib.import_module("server.legal")
    assert callable(getattr(module,"initialize_schema",None)), "Legal persistence is not implemented"
    assert callable(getattr(module,"create_router",None)), "Legal API router is not implemented"


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv("DATABASE_PATH",str(tmp_path/"legal.sqlite3"))
    monkeypatch.setenv("APP_ENV","test")
    monkeypatch.setenv("SECURE_COOKIES","false")
    monkeypatch.setenv("APP_TIMEZONE","Europe/Moscow")
    for name in ("APP_URL","RENDER_EXTERNAL_URL","SMTP_HOST","SMTP_FROM","SMTP_TENANT_ID","YANDEX_API_KEY","YANDEX_MODEL"):
        monkeypatch.delenv(name,raising=False)
    main=importlib.import_module("server.main")
    legal=importlib.import_module("server.legal")
    app=main.create_app()
    # The final application mounts this router itself. During independent module
    # development mount the identical ctx contract before SPA/API fallbacks.
    if not any(getattr(route,"path","")=="/api/legal/rules" for route in app.routes):
        ctx=SimpleNamespace(**{name:getattr(main,name) for name in ("get_user","database","event","invoice_row","invoice_view","identifier","now","problem","settings_view","contactable")},config=app.state.config)
        before=len(app.routes)
        app.include_router(legal.create_router(ctx))
        added=app.router.routes[before:]
        app.router.routes=app.router.routes[:before]
        index=next((i for i,route in enumerate(app.routes) if getattr(route,"path","").startswith("/api/{")),len(app.routes))
        app.router.routes[index:index]=added
    with TestClient(app,raise_server_exceptions=False) as c:
        with main.database(app.state.config,write=True) as connection:legal.initialize_schema(connection)
        result=c.post("/api/auth/register",json={"name":"Юрист","company":"ООО Поставщик","email":"legal@example.ru","password":"Legal-review-2026!"})
        assert result.status_code==201,result.text
        c.headers["X-CSRF-Token"]=result.json()["csrf_token"]
        yield c


def invoice(c,**changes):
    body={"company":"ООО Покупатель","inn":"7701234567","email":"debtor@example.ru","number":"Ю-001","issued_on":"2026-08-01","due_on":"2026-09-01","amount":10000000}
    body.update(changes)
    response=c.post("/api/invoices",json=body)
    assert response.status_code==201,response.text
    return response.json()


def facts(**changes):
    data={"creditor":{"kind":"organization","name":"ООО Поставщик","inn":"7801234567","ogrn":"1027800000001","address":"Санкт-Петербург, Невский проспект, 1","email":"legal@example.ru","phone":"+7 812 000 00 00","bank_details":"Расчётный счёт 40702810000000000001, БИК 044030001"},
          "debtor":{"kind":"organization","name":"ООО Покупатель","inn":"7701234567","ogrn":"1027700000001","address":"Москва, улица Покупателя, 1","email":"debtor@example.ru","phone":"+7 495 000 00 00","bank_details":"Реквизиты в договоре № П-1"},
          "contract_number":"П-1","contract_date":"2026-07-01","obligation_description":"Оплата поставленного оборудования","performance_description":"Товар передан по УПД № 10 от 01.08.2026, принят без замечаний","due_basis":"Пункт 3.1 договора, отсрочка до 01.09.2026","legal_basis":"Статьи 309, 310, 516 ГК РФ и договор № П-1",
          "court_name":"Арбитражный суд города Москвы","court_address":"Москва, Большая Тульская, 17","jurisdiction_basis":"Место нахождения ответчика, статья 35 АПК РФ","undisputed":True,"business_debt_confirmed":True,"special_regimes_checked":True,
          "pretrial_days":30,"pretrial_basis":"Часть 5 статьи 4 АПК РФ","fee_agreement_reference":"Договор сопровождения № А-1","fee_start_on":"2026-08-01","fee_model_version":"mandato-2026-10-26","lawyer_agreement_reference":"Отдельное соглашение с адвокатом № 1"}
    data.update(changes)
    return data


def case(c,**changes):
    inv=invoice(c,**changes)
    result=c.post("/api/legal/cases",json={"invoice_id":inv["id"],"facts":facts()})
    assert result.status_code==201,result.text
    return inv,result.json()


def evidence(c,case_id,kind="performance",reference="УПД № 10",occurred_on="2026-08-01"):
    result=c.post(f"/api/legal/cases/{case_id}/evidence",json={"kind":kind,"title":reference,"reference":reference,"occurred_on":occurred_on})
    assert result.status_code==201,result.text
    return result.json()


def document(c,case_id,kind="pretrial_claim",sanction="art395"):
    response=c.post(f"/api/legal/cases/{case_id}/documents",json={"kind":kind,"calculation":{"through_on":"2026-10-24","sanction":sanction}})
    assert response.status_code==201,response.text
    return response.json()


def review(c,doc_id,**changes):
    data={"decision":"approved","reviewer_name":"Проверяющий юрист","authority_reference":"Доверенность № 1 от 01.08.2026","qualification_confirmed":True,"notes":"Проверены расчёт, первичные документы и полномочия"}
    data.update(changes)
    return c.post(f"/api/legal/documents/{doc_id}/review",json=data)


def test_calculation_uses_actual_authenticated_ledger_and_rejects_financial_mass_assignment(client):
    inv=invoice(client)
    result=client.post("/api/legal/calculations",json={"invoice_id":inv["id"],"through_on":"2026-10-24","sanction":"art395"})
    assert result.status_code==200,result.text
    assert result.json()["principal_amount"]==10000000
    assert result.json()["snapshot_hash"]
    assert client.post("/api/legal/calculations",json={"invoice_id":inv["id"],"principal":1,"through_on":"2026-10-24"}).status_code==422


def test_docx_is_a_real_immutable_version_and_does_not_self_approve(client):
    inv,item=case(client)
    evidence(client,item["id"],"contract","Договор № П-1","2026-07-01")
    evidence(client,item["id"])
    first=document(client,item["id"])
    assert first["version"]==1 and first["status"]=="draft"
    assert first["review_required"] is True
    downloaded=client.get(first["download_url"])
    assert downloaded.status_code==200 and downloaded.headers["content-type"].startswith("application/vnd.openxmlformats")
    with ZipFile(io.BytesIO(downloaded.content)) as archive:
        text=archive.read("word/document.xml").decode()
        assert "ПРЕТЕНЗИЯ" in text and "ООО Поставщик" in text and "100 000,00" in text
        assert "14,00" in text and "395" in text and "УПД № 10" in text
    second=document(client,item["id"])
    assert second["version"]==2 and second["id"]!=first["id"]
    assert client.get(first["download_url"]).content==downloaded.content
    assert client.patch(f"/api/legal/documents/{first['id']}",json={"body":"Подмена"}).status_code in (404,405)


def test_review_requires_explicit_human_attestation_and_tracks_exact_snapshot(client):
    inv,item=case(client)
    evidence(client,item["id"],"contract","Договор № П-1","2026-07-01");evidence(client,item["id"])
    doc=document(client,item["id"])
    assert review(client,doc["id"],qualification_confirmed=False).status_code==422
    assert review(client,doc["id"]).status_code==200
    assert client.post(f"/api/invoices/{inv['id']}/payments",json={"amount":100000,"paid_on":"2026-10-24","reference":"MANUAL-1"}).status_code==200
    assert review(client,doc["id"]).status_code==409
    detail=client.get(f"/api/legal/cases/{item['id']}").json()
    old=next(row for row in detail["documents"] if row["id"]==doc["id"])
    assert old["stale"] is True and old["status"]=="stale"
    assert client.get(doc["download_url"]).status_code==200  # Historical version survives.


def test_facts_and_sender_settings_changes_invalidate_approved_document(client):
    inv,item=case(client)
    evidence(client,item["id"],"contract","Договор № П-1","2026-07-01");evidence(client,item["id"])
    doc=document(client,item["id"]);assert review(client,doc["id"]).status_code==200
    assert client.patch(f"/api/legal/cases/{item['id']}",json={"facts":facts(due_basis="Исправленный пункт договора 3.2")}).status_code==200
    assert review(client,doc["id"]).status_code==409
    fresh=document(client,item["id"]);assert review(client,fresh["id"]).status_code==200
    assert client.patch('/api/settings',json={"bank_details":"Новые реквизиты компании"}).status_code==200
    assert review(client,fresh["id"]).status_code==409


def test_missing_factual_fields_and_contested_or_above_limit_order_fail_closed(client):
    inv,item=case(client,amount=75000000)
    # No primary evidence: a court application cannot be manufactured.
    assert client.post(f"/api/legal/cases/{item['id']}/documents",json={"kind":"court_order","calculation":{"through_on":"2026-10-24","sanction":"none"}}).status_code==422
    evidence(client,item["id"],"contract","Договор № П-1","2026-07-01");evidence(client,item["id"])
    order=document(client,item["id"],"court_order","none")
    assert order["calculation"]["total_claim_amount"]==75000000
    assert client.post(f"/api/legal/cases/{item['id']}/documents",json={"kind":"court_order","calculation":{"through_on":"2026-10-24","sanction":"art395"}}).status_code==422
    assert client.patch(f"/api/legal/cases/{item['id']}",json={"facts":facts(undisputed=False)}).status_code==200
    assert client.post(f"/api/legal/cases/{item['id']}/documents",json={"kind":"court_order","calculation":{"through_on":"2026-10-24","sanction":"none"}}).status_code==422


def test_recorded_delivery_and_filing_are_manual_evidenced_milestones_with_pretrial_gate(client,monkeypatch):
    freeze_document_clock(monkeypatch)
    inv,item=case(client)
    evidence(client,item["id"],"contract","Договор № П-1","2026-07-01");evidence(client,item["id"])
    claim=document(client,item["id"]);assert review(client,claim["id"]).status_code==200
    sent_proof=evidence(client,item["id"],"claim_dispatch","Почтовая квитанция TRACK-1","2026-10-01")
    sent=client.post(f"/api/legal/cases/{item['id']}/milestones",json={"stage":"claim_sent","occurred_on":"2026-10-01","reference":"TRACK-1","notes":"Историческая претензия оператора вне кабинета подтверждена квитанцией","evidence_ids":[sent_proof["id"]]})
    assert sent.status_code==201,sent.text
    lawsuit=document(client,item["id"],"statement_of_claim")
    assert review(client,lawsuit["id"]).status_code==200
    duty=evidence(client,item["id"],"duty_payment","Платёжное поручение 11","2026-10-24")
    copies=evidence(client,item["id"],"application_copy_sent","Копия иска направлена","2026-10-24")
    filing=evidence(client,item["id"],"filing_receipt","Квитанция Мой Арбитр","2026-10-24")
    early=client.post(f"/api/legal/cases/{item['id']}/milestones",json={"stage":"filed","occurred_on":"2026-10-24","reference":"А40-TEST","notes":"Ручная подача юриста","document_id":lawsuit["id"],"evidence_ids":[duty["id"],copies["id"],filing["id"]]})
    assert early.status_code==409
    assert client.get(f"/api/legal/cases/{item['id']}").json()["pretrial"]["ready_on"]=="2026-11-01"


def test_success_fee_never_treats_manual_income_as_confirmed_bank_recovery(client):
    inv,item=case(client)
    assert client.post(f"/api/invoices/{inv['id']}/payments",json={"amount":100000,"paid_on":"2026-10-24","reference":"MANUAL"}).status_code==200
    fee=client.get(f"/api/legal/cases/{item['id']}/fee")
    assert fee.status_code==200,fee.text
    assert fee.json()["confirmed_recovery_amount"]==0 and fee.json()["fee_amount"]==0


def test_generated_document_cannot_be_recorded_as_sent_before_it_existed(client):
    inv,item=case(client)
    evidence(client,item["id"],"contract","Договор № П-1","2026-07-01");evidence(client,item["id"])
    doc=document(client,item["id"]);assert review(client,doc["id"]).status_code==200
    proof=evidence(client,item["id"],"claim_dispatch","Старая квитанция","2026-10-01")
    response=client.post(f"/api/legal/cases/{item['id']}/milestones",json={"stage":"claim_sent","occurred_on":"2026-10-01","reference":"TRACK-OLD","notes":"Попытка связать новую версию со старой отправкой","document_id":doc["id"],"evidence_ids":[proof["id"]]})
    assert response.status_code==422


def test_expiration_of_waiting_period_does_not_invalidate_unchanged_document(client,monkeypatch):
    from datetime import date
    legal=importlib.import_module("server.legal")
    inv,item=case(client)
    evidence(client,item["id"],"contract","Договор № П-1","2026-07-01");evidence(client,item["id"])
    proof=evidence(client,item["id"],"claim_dispatch","Претензия направлена вне кабинета","2026-10-01")
    assert client.post(f"/api/legal/cases/{item['id']}/milestones",json={"stage":"claim_sent","occurred_on":"2026-10-01","reference":"TRACK-1","notes":"Исторический документ подтверждён оператором","evidence_ids":[proof["id"]]}).status_code==201
    doc=document(client,item["id"],"statement_of_claim")
    assert review(client,doc["id"]).status_code==200
    monkeypatch.setattr(legal,"business_today",lambda:date(2026,11,2))
    assert review(client,doc["id"]).status_code==200


def test_document_cannot_demand_old_principal_when_newer_payment_is_already_recorded(client):
    inv,item=case(client)
    evidence(client,item["id"],"contract","Договор № П-1","2026-07-01");evidence(client,item["id"])
    assert client.post(f"/api/invoices/{inv['id']}/payments",json={"amount":100000,"paid_on":"2026-10-24","reference":"NEW-1"}).status_code==200
    result=client.post(f"/api/legal/cases/{item['id']}/documents",json={"kind":"pretrial_claim","calculation":{"through_on":"2026-10-23","sanction":"none"}})
    assert result.status_code==422


def test_opening_payments_require_verified_dates_for_sanctions_and_never_become_bank_recovery(client):
    inv=invoice(client,paid_amount=3000000)
    data={"invoice_id":inv["id"],"through_on":"2026-10-24","sanction":"art395"}
    assert client.post('/api/legal/calculations',json=data).status_code==422
    simple=client.post('/api/legal/calculations',json={**data,"sanction":"none"})
    assert simple.status_code==200 and simple.json()['principal_amount']==7000000
    verified=client.post('/api/legal/calculations',json={**data,"opening_reductions":[{"effective_on":"2026-08-10","amount":3000000,"evidence":"Выписка и платёжное поручение 12"}]})
    assert verified.status_code==200 and verified.json()['opening_payment_dates_verified'] is True
    mismatch=client.post('/api/legal/calculations',json={**data,"opening_reductions":[{"effective_on":"2026-08-10","amount":1,"evidence":"Недостаточно"}]})
    assert mismatch.status_code==422


def bank_allocate(c,invoice_id,number,amount,paid_on):
    bank=c.post('/api/finance/bank-payments',json={"external_id":number,"amount":amount,"paid_on":paid_on,"reference":number,"evidence":"Подтверждённая выписка: "+number,"confirmed":True})
    assert bank.status_code==201,bank.text
    result=c.post(f"/api/finance/bank-payments/{bank.json()['id']}/allocate",json={"invoice_id":invoice_id,"amount":amount,"idempotency_key":"allocation:"+number})
    assert result.status_code==200,result.text
    return result.json()['payment']


def test_fee_uses_only_net_bank_allocations_and_handles_stage_date_ambiguity_conservatively(client,monkeypatch):
    freeze_document_clock(monkeypatch)
    from datetime import date
    inv,item=case(client)
    evidence(client,item["id"],"contract","Договор № П-1","2026-07-01");evidence(client,item["id"])
    proof=evidence(client,item['id'],'claim_dispatch','Претензия направлена','2026-10-22')
    assert client.post(f"/api/legal/cases/{item['id']}/milestones",json={'stage':'claim_sent','occurred_on':'2026-10-22','reference':'Почтовая квитанция','notes':'Подтверждено направление претензии','evidence_ids':[proof['id']]}).status_code==201
    bank_allocate(client,inv['id'],'B-PRE',1000000,'2026-10-23')
    doc=document(client,item['id'],'court_order','none');assert review(client,doc['id']).status_code==200
    proofs=[evidence(client,item['id'],kind,kind,'2026-10-24')['id'] for kind in ('duty_payment','application_copy_sent','filing_receipt')]
    filing=client.post(f"/api/legal/cases/{item['id']}/milestones",json={'stage':'filed','occurred_on':'2026-10-24','reference':'Мой Арбитр квитанция 1','notes':'Ручная подача проверенного заявления','document_id':doc['id'],'evidence_ids':proofs})
    assert filing.status_code==201,filing.text
    bank_allocate(client,inv['id'],'B-SAME-DAY',2000000,'2026-10-24')
    fee=client.get(f"/api/legal/cases/{item['id']}/fee").json()
    assert fee['confirmed_recovery_amount']==3000000 and fee['fee_amount']==760000
    assert fee['pretrial_fee_amount']==60000 and fee['judicial_package_amount']==700000
    assert fee['ambiguous_recovery_amount']==2000000 and fee['lawyer_fee_amount']==0
    assert fee['line_items'][-1]['stage']=='ambiguous'
    finance=importlib.import_module('server.finance');monkeypatch.setattr(finance,'business_today',lambda:date(2026,10,25))
    legal=importlib.import_module('server.legal');monkeypatch.setattr(legal,'business_today',lambda:date(2026,10,25))
    later=bank_allocate(client,inv['id'],'B-JUDICIAL',1000000,'2026-10-25')
    later_fee=client.get(f"/api/legal/cases/{item['id']}/fee").json()
    assert later_fee['fee_amount']==760000 and later_fee['lawyer_fee_amount']==120000
    reversed_payment=client.post(f"/api/finance/payments/{later['id']}/reverse",json={'amount':500000,'reason':'Возвращена часть подтверждённого поступления','idempotency_key':'refund-1','kind':'refund'})
    assert reversed_payment.status_code==200,reversed_payment.text
    after=client.get(f"/api/legal/cases/{item['id']}/fee").json()
    assert after['confirmed_recovery_amount']==3500000 and after['fee_amount']==760000
    assert after['lawyer_fee_amount']==60000


def test_case_cannot_change_the_debtor_identity_or_duplicate_fee_scope(client):
    inv,item=case(client)
    duplicate=client.post('/api/legal/cases',json={'invoice_id':inv['id'],'facts':facts()})
    assert duplicate.status_code==409
    data=facts();data['debtor']['inn']='7801234567'
    assert client.patch(f"/api/legal/cases/{item['id']}",json={'facts':data}).status_code==200
    evidence(client,item["id"],"contract","Договор № П-1","2026-07-01");evidence(client,item["id"])
    generated=client.post(f"/api/legal/cases/{item['id']}/documents",json={'kind':'pretrial_claim','calculation':{'through_on':'2026-10-24','sanction':'none'}})
    assert generated.status_code==422


def test_actual_dispute_blocks_court_order_even_if_old_case_facts_say_undisputed(client):
    inv,item=case(client)
    evidence(client,item["id"],"contract","Договор № П-1","2026-07-01");evidence(client,item["id"])
    old=document(client,item['id'],'court_order','none');assert review(client,old['id']).status_code==200
    assert client.post(f"/api/invoices/{inv['id']}/status",json={'status':'disputed','notes':'Покупатель оспорил поставку'}).status_code==200
    result=client.post(f"/api/legal/cases/{item['id']}/documents",json={'kind':'court_order','calculation':{'through_on':'2026-10-24','sanction':'none'}})
    assert result.status_code==422
    assert review(client,old['id']).status_code==409


def test_zero_pretrial_period_cannot_reuse_the_general_30_day_statutory_basis(client):
    inv=invoice(client)
    result=client.post('/api/legal/cases',json={'invoice_id':inv['id'],'facts':facts(pretrial_days=0)})
    assert result.status_code==422


def test_every_legal_resource_and_action_is_tenant_scoped(client):
    inv,item=case(client)
    evidence(client,item["id"],"contract","Договор № П-1","2026-07-01");proof=evidence(client,item["id"])
    doc=document(client,item["id"])
    other=client.post("/api/auth/register",json={"name":"Чужой","company":"Другая компания","email":"other-legal@example.ru","password":"Other-legal-2026!"})
    client.headers["X-CSRF-Token"]=other.json()["csrf_token"]
    assert client.get('/api/legal/cases').json()["items"]==[]
    for path in (f"/api/legal/cases/{item['id']}",doc["download_url"],f"/api/legal/cases/{item['id']}/fee"):
        assert client.get(path).status_code==404,path
    assert review(client,doc["id"]).status_code==404
    assert client.post('/api/legal/calculations',json={"invoice_id":inv["id"],"through_on":"2026-10-24"}).status_code==404
    assert client.post(f"/api/legal/cases/{item['id']}/evidence",json={"kind":"other","title":"Подмена","reference":"Файл","occurred_on":"2026-10-24"}).status_code==404
    assert client.patch(f"/api/legal/cases/{item['id']}",json={"facts":facts()}).status_code==404


def freeze_document_clock(monkeypatch):
    """These historical filing scenarios require a document already created that day."""
    from datetime import datetime, timezone
    class DocumentClock(datetime):
        @classmethod
        def now(cls, tz=None):
            instant = cls(2026, 10, 24, 9, tzinfo=timezone.utc)
            return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)
    monkeypatch.setattr(importlib.import_module('server.main'), 'datetime', DocumentClock)


def file_package(c, case_id, doc):
    proofs=[evidence(c,case_id,kind,kind,'2026-10-24')['id'] for kind in ('duty_payment','application_copy_sent','filing_receipt')]
    result=c.post(f'/api/legal/cases/{case_id}/milestones',json={
        'stage':'filed','occurred_on':'2026-10-24','reference':'Квитанция '+doc['id'],
        'notes':'Подтверждена ручная подача пакета','document_id':doc['id'],'evidence_ids':proofs})
    assert result.status_code==201,result.text


def test_package_fixed_prices_require_filing_and_do_not_duplicate_versions_or_receipts(client,monkeypatch):
    freeze_document_clock(monkeypatch)
    inv,item=case(client)
    evidence(client,item['id'],'contract','Договор','2026-07-01');evidence(client,item['id'])
    sent=evidence(client,item['id'],'claim_dispatch','Претензия до суда','2026-09-02')
    assert client.post(f"/api/legal/cases/{item['id']}/milestones",json={
        'stage':'claim_sent','occurred_on':'2026-09-02','reference':'Квитанция претензии',
        'notes':'Претензия подтверждена оператором','evidence_ids':[sent['id']]}).status_code==201
    order=document(client,item['id'],'court_order','none')
    assert review(client,order['id']).status_code==200
    assert client.get(f"/api/legal/cases/{item['id']}/fee").json()['fee_amount']==0
    file_package(client,item['id'],order)
    file_package(client,item['id'],order)
    revised=document(client,item['id'],'court_order','none')
    assert review(client,revised['id']).status_code==200
    file_package(client,item['id'],revised)
    assert client.get(f"/api/legal/cases/{item['id']}/fee").json()['fee_amount']==700000
    lawsuit=document(client,item['id'],'statement_of_claim','none')
    assert review(client,lawsuit['id']).status_code==200
    file_package(client,item['id'],lawsuit)
    fee=client.get(f"/api/legal/cases/{item['id']}/fee").json()
    assert fee['fee_amount']==fee['judicial_package_amount']==1900000
    assert fee['pretrial_fee_amount']==fee['lawyer_fee_amount']==0
    assert len(fee['package_items'])==2
    assert client.get('/api/invoices/'+inv['id']).json()['invoice']['balance']==inv['balance']


def test_legacy_agreement_requires_explicit_confirmation_and_preserves_finances_and_docx(client):
    inv,item=case(client)
    evidence(client,item['id'],'contract','Договор','2026-07-01');evidence(client,item['id'])
    doc=document(client,item['id'])
    original=client.get(doc['download_url']).content
    legacy=facts();legacy.pop('fee_model_version');legacy.pop('lawyer_agreement_reference')
    legacy.update(pretrial_fee_percent='6',judicial_fee_percent='15')
    raw=json.dumps(legacy,ensure_ascii=False)
    main=importlib.import_module('server.main')
    with main.database(client.app.state.config,write=True) as c:
        c.execute('UPDATE legal_cases SET facts_json=? WHERE id=?',(raw,item['id']))
    fee=client.get(f"/api/legal/cases/{item['id']}/fee").json()
    assert fee['requires_fee_model_confirmation'] is True
    assert fee['fee_amount']==fee['lawyer_fee_amount']==0
    with main.database(client.app.state.config) as c:
        assert c.execute('SELECT facts_json FROM legal_cases WHERE id=?',(item['id'],)).fetchone()['facts_json']==raw
    unspecified=facts();unspecified.pop('fee_model_version')
    assert client.patch(f"/api/legal/cases/{item['id']}",json={'facts':unspecified}).status_code==409
    assert client.patch(f"/api/legal/cases/{item['id']}",json={'facts':facts()}).status_code==200
    assert client.get(f"/api/legal/cases/{item['id']}/fee").json()['requires_fee_model_confirmation'] is False
    assert client.get(doc['download_url']).content==original
    assert client.get('/api/invoices/'+inv['id']).json()['invoice']['balance']==inv['balance']


def test_fee_terms_cannot_be_changed_by_accountant_or_overridden_with_old_percentages(client):
    inv,item=case(client)
    assert client.patch(f"/api/legal/cases/{item['id']}",json={'facts':facts(judicial_fee_percent='15')}).status_code==422
    assert client.patch(f"/api/legal/cases/{item['id']}",json={'facts':facts(fee_model_version='old')}).status_code==422
    invite=client.post('/api/workflow/invitations',json={'email':'fee-accountant@example.ru'}).json()
    assert client.post('/api/workflow/invitations/accept',json={'token':invite['token'],'name':'Бухгалтер','password':'Accountant-fees-2026!'}).status_code==201
    assert client.post('/api/auth/logout').status_code==200
    session=client.post('/api/auth/login',json={'email':'fee-accountant@example.ru','password':'Accountant-fees-2026!'}).json()
    client.headers['X-CSRF-Token']=session['csrf_token']
    assert client.patch(f"/api/legal/cases/{item['id']}",json={'facts':facts(lawyer_agreement_reference='Подменённый договор')}).status_code==403
    assert client.patch(f"/api/legal/cases/{item['id']}",json={'facts':facts(performance_description='Уточнены сведения об исполнении')}).status_code==200
    # Even an old JSON carrying the new version string cannot bypass manager
    # confirmation by deleting its legacy editable percentage fields.
    main=importlib.import_module('server.main')
    with main.database(client.app.state.config,write=True) as c:
        c.execute('UPDATE legal_cases SET facts_json=? WHERE id=?',(json.dumps(facts(judicial_fee_percent='15')),item['id']))
    assert client.patch(f"/api/legal/cases/{item['id']}",json={'facts':facts()}).status_code==403
    another=invoice(client,number='OTHER-FEE')
    assert client.post('/api/legal/cases',json={'invoice_id':another['id'],'facts':facts()}).status_code==403
