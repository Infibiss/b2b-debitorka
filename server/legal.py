"""Deterministic B2B legal calculations and tenant-scoped reviewed documents.

Sources, scope and rounding are versioned in docs/research/legal-rules.md.
This module never submits a document or makes a legal approval by itself.
"""
from __future__ import annotations

import calendar
import base64
import hashlib
import json
import re
import threading
import time
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from pathlib import Path

import httpx

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from .business_time import business_today, business_timezone
from . import legal_models as models

RULES_VERSION = "ru-arbitration-b2b-2026-10-24-v1"
RATE_CACHE = json.loads(Path(__file__).with_name("legal_rates.json").read_text(encoding="utf-8"))
_RATE_LOCK=threading.Lock()
_RATE_FAILURE_UNTIL=0.0
ORDER_LIMIT = 75_000_000
MONEY_LIMIT = 1_000_000_000_000_000
SOURCES = {
    "fees": "https://arbitr.ru/materials/ojfederal_nixjarbitrazhnixjsudax/gosudarstvennajajposhlina",
    "liability": "https://vsrf.ru/documents/own/8478/",
    "pretrial": "https://www.vsrf.ru/documents/own/30139/",
    "order": "https://vsrf.ru/documents/own/8535/",
    "order_limit": "https://publication.pravo.gov.ru/document/0001202312250069",
}


def rules():
    return {"version": RULES_VERSION, "verified_on": "2026-10-24", "rates_version": RATE_CACHE["version"],
            "rates_verified_through": RATE_CACHE["verified_through"], "rates_available_from": RATE_CACHE["available_from"],
            "rates_last_observation_on":RATE_CACHE.get("last_observation_on","2026-10-23"),
            "rates_source": RATE_CACHE["source"], "rate_periods": RATE_CACHE["periods"], "sources": SOURCES,
            "court_order_limit": ORDER_LIMIT, "court_order_minimum_fee": 800000, "default_pretrial_days": 30,
            "payment_day_included": True, "year_basis": "actual/actual (365/366)",
            "money_rounding": "Сумма точных начислений → ROUND_HALF_UP до копейки; госпошлина → полные рубли",
            "requires_human_review": True}


def _money(value, *, signed=False, zero=False):
    if type(value) is not int or abs(value) > MONEY_LIMIT or (not signed and value < (0 if zero else 1)):
        raise ValueError("Денежная сумма должна быть целым числом копеек в допустимом диапазоне")
    return value


def _percent(value):
    if not isinstance(value, (str, Decimal)):
        raise ValueError("Ставка должна быть десятичной строкой")
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise ValueError("Некорректная ставка") from None
    if not result.is_finite() or result < 0 or result > 1000 or result.as_tuple().exponent < -8:
        raise ValueError("Ставка должна быть от 0 до 1000 процентов, до 8 знаков после запятой")
    return result


def _day(value):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        raise ValueError("Укажите календарную дату ГГГГ-ММ-ДД") from None


def _kopeks(value):
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def arbitration_fee(claim_amount, kind="claim"):
    """NK 333.21(1)(1),(3): price includes sanctions, fee excludes itself."""
    _money(claim_amount)
    if kind not in ("claim", "court_order"):
        raise ValueError("Неподдерживаемый вид госпошлины")
    rubles = Decimal(claim_amount) / 100
    if rubles <= 100000:
        fee = Decimal(10000)
    elif rubles <= 1000000:
        fee = Decimal(10000) + (rubles - 100000) * Decimal(".05")
    elif rubles <= 10000000:
        fee = Decimal(55000) + (rubles - 1000000) * Decimal(".03")
    elif rubles <= 50000000:
        fee = Decimal(325000) + (rubles - 10000000) * Decimal(".01")
    else:
        fee = min(Decimal(10000000), Decimal(725000) + (rubles - 50000000) * Decimal(".005"))
    if kind == "court_order":
        fee = max(Decimal(8000), fee / 2)
    return int(fee.quantize(Decimal(1), rounding=ROUND_HALF_UP)) * 100


def _rate_periods(start, finish, override, reason):
    if start < date(2016, 8, 1):
        raise ValueError("Для периодов до 01.08.2016 необходим отдельный юридический расчёт по действовавшему режиму")
    if override is not None:
        if not isinstance(reason, str) or len(reason.strip()) < 3:
            raise ValueError("Укажите основание и причину ручной замены истории ставок")
        if not override or len(override) > 1000:
            raise ValueError("Нужны периоды ставок, покрывающие весь расчёт")
        result = []
        for row in override:
            first, last = _day(row["from_on"]), _day(row["to_on"])
            rate = _percent(row["annual_percent"])
            if last < first or not row.get("source", "").strip():
                raise ValueError("Период ставки и источник должны быть указаны")
            result.append((first, last, rate))
        result.sort()
        if any(result[i][0] <= result[i-1][1] for i in range(1,len(result))):
            raise ValueError("Периоды ставок не должны пересекаться")
        cursor = start
        for first,last,_ in result:
            if last < cursor:
                continue
            if first > cursor:
                raise ValueError("В истории ставок есть непокрытый период")
            cursor = max(cursor,last + timedelta(days=1))
            if cursor > finish:
                break
        if cursor <= finish:
            raise ValueError("История ставок не покрывает дату расчёта")
        return result, "explicit-override"
    if finish > _day(RATE_CACHE["verified_through"]):
        raise ValueError("Кэш ставок не подтверждён на эту дату. Обновите историю либо задайте проверенные периоды с основанием")
    result=[]
    for index,row in enumerate(RATE_CACHE["periods"]):
        last = _day(RATE_CACHE["periods"][index+1]["from_on"]) - timedelta(days=1) if index+1 < len(RATE_CACHE["periods"]) else _day(RATE_CACHE["verified_through"])
        result.append((_day(row["from_on"]),last,_percent(row["annual_percent"])))
    return result, RATE_CACHE["version"]


def calculate_debt(*, principal, due_on, through_on, reductions=None, sanction="art395", penalty_daily_percent=None,
                   penalty_basis="", penalty_cap_amount=None, penalty_agreed=False, combination_basis="",
                   rate_override=None, override_reason="", excluded_periods=None):
    """Actual calendar days; credited payment day accrues, reduction starts next day.

    Signed reductions are principal allocations/adjustments, never total bank
    receipts or payments of costs. Positive reduces principal, negative restores it.
    No compound interest and no automatic judicial reduction/exception assessment.
    """
    _money(principal)
    due, finish = _day(due_on), _day(through_on)
    if finish < due or (finish-due).days > 36600:
        raise ValueError("Дата расчёта не раньше срока оплаты; период не более 100 лет")
    if sanction not in ("none","penalty","art395","both"):
        raise ValueError("Выберите вид начисления")
    interest_enabled = sanction in ("art395","both")
    penalty_enabled = sanction in ("penalty","both")
    if interest_enabled and penalty_agreed and not combination_basis.strip():
        raise ValueError("Договорная неустойка исключает проценты 395 без специального договорного/законного основания")
    if sanction == "both" and not combination_basis.strip():
        raise ValueError("Для совместного взыскания нужно явное договорное или законное основание")
    if penalty_enabled and (not penalty_agreed or not penalty_basis.strip() or penalty_daily_percent is None):
        raise ValueError("Для неустойки нужны согласованная ставка и основание в договоре")
    daily_rate = _percent(penalty_daily_percent) if penalty_enabled else Decimal(0)
    if penalty_cap_amount is not None:
        _money(penalty_cap_amount,zero=True)
    events={}
    for row in reductions or []:
        amount = _money(row["signed_reduction"],signed=True)
        effective = _day(row["effective_on"]) + timedelta(days=1)
        events[effective] = events.get(effective,0) + amount
    # Validate the whole selected principal chronology, including pre-due payments.
    outstanding=principal
    for effective,amount in sorted(events.items()):
        # Interest includes the payment day, but the principal demanded at the
        # close of that day already reflects its payment/reversal.
        if effective > finish+timedelta(days=1):
            break
        outstanding -= amount
        if outstanding < 0 or outstanding > MONEY_LIMIT:
            raise ValueError("История оплат/корректировок выводит основной долг за допустимые пределы")
    excluded=[]
    for row in excluded_periods or []:
        first,last=_day(row["from_on"]),_day(row["to_on"])
        if last < first or not row.get("basis", "").strip():
            raise ValueError("Для исключённого периода нужны даты и правовое основание")
        excluded.append((first,last,row["basis"]))
    start=due+timedelta(days=1)
    rates,rate_version=_rate_periods(start,finish,rate_override,override_reason) if interest_enabled and start <= finish else ([],"not-applicable")
    current=principal - sum(amount for effective,amount in events.items() if effective<=start)
    lines=[]
    with localcontext() as context:
        context.prec=50
        cursor=start
        while cursor<=finish:
            if cursor != start:
                current -= events.get(cursor,0)
            matches=[rate for first,last,rate in rates if first<=cursor<=last]
            annual=matches[0] if matches else Decimal(0)
            if interest_enabled and len(matches)!=1:
                raise ValueError("Нет однозначной ставки на дату")
            basis="; ".join(text for first,last,text in excluded if first<=cursor<=last)
            denied=bool(basis)
            denominator=366 if calendar.isleap(cursor.year) else 365
            signature=(current,str(annual),denominator,denied,basis)
            if lines and lines[-1]["_signature"]==signature:
                lines[-1]["to_on"]=str(cursor)
                lines[-1]["days"]+=1
            else:
                lines.append({"from_on":str(cursor),"to_on":str(cursor),"days":1,"principal_amount":current,
                              "annual_percent":str(annual),"daily_penalty_percent":str(daily_rate),"denominator":denominator,
                              "excluded":denied,"basis":basis,"_signature":signature})
            cursor+=timedelta(days=1)
        interest_total=penalty_total=Decimal(0)
        for row in lines:
            interest=Decimal(0) if row["excluded"] else Decimal(row["principal_amount"])*Decimal(row["annual_percent"])/100*row["days"]/row["denominator"]
            penalty=Decimal(0) if row["excluded"] else Decimal(row["principal_amount"])*daily_rate/100*row["days"]
            interest_total+=interest
            penalty_total+=penalty
            row.update(interest_amount=_kopeks(interest),penalty_amount=_kopeks(penalty),interest_exact_kopeks=str(interest),penalty_exact_kopeks=str(penalty))
            row.pop("_signature")
        if penalty_cap_amount is not None:
            penalty_total=min(penalty_total,Decimal(penalty_cap_amount))
        interest_amount,penalty_amount=_kopeks(interest_total),_kopeks(penalty_total)
    principal_amount=outstanding
    claim=principal_amount+interest_amount+penalty_amount
    if claim>MONEY_LIMIT:
        raise ValueError("Сумма требования превышает допустимый предел")
    return {"rules_version":RULES_VERSION,"rates_version":rate_version,"rates_source":RATE_CACHE["source"],
            "from_on":str(start),"through_on":str(finish),"days":max(0,(finish-due).days),
            "original_principal":principal,"principal_amount":principal_amount,"sanction":sanction,
            "interest_amount":interest_amount,"penalty_amount":penalty_amount,"total_claim_amount":claim,
            "fee_claim_amount":arbitration_fee(claim) if claim else 0,"fee_order_amount":arbitration_fee(claim,"court_order") if claim else 0,
            "order_eligible":bool(0<claim<=ORDER_LIMIT),"line_items":lines,
            "rounding_difference_interest":interest_amount-sum(row["interest_amount"] for row in lines),
            "rounding_or_cap_penalty":penalty_amount-sum(row["penalty_amount"] for row in lines),
            "penalty_basis":penalty_basis,"combination_basis":combination_basis,"override_reason":override_reason,
            "requires_human_review":True}


SCHEMA="""
CREATE TABLE IF NOT EXISTS legal_cases (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,invoice_id TEXT NOT NULL,facts_json TEXT NOT NULL,
 facts_revision BIGINT NOT NULL DEFAULT 1,created_by TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
 UNIQUE(id,tenant_id),FOREIGN KEY(invoice_id,tenant_id) REFERENCES invoices(id,tenant_id)
);
CREATE TABLE IF NOT EXISTS legal_evidence (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,case_id TEXT NOT NULL,kind TEXT NOT NULL,title TEXT NOT NULL,
 reference TEXT NOT NULL,occurred_on TEXT NOT NULL,sha256 TEXT NOT NULL DEFAULT '',created_by TEXT NOT NULL,created_at TEXT NOT NULL,
 UNIQUE(id,tenant_id),FOREIGN KEY(case_id,tenant_id) REFERENCES legal_cases(id,tenant_id)
);
CREATE TABLE IF NOT EXISTS legal_documents (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,case_id TEXT NOT NULL,kind TEXT NOT NULL,version BIGINT NOT NULL,
 snapshot_hash TEXT NOT NULL,payload_json TEXT NOT NULL,calculation_json TEXT NOT NULL,sha256 TEXT NOT NULL,
 content_base64 TEXT NOT NULL,created_by TEXT NOT NULL,created_at TEXT NOT NULL,
 UNIQUE(id,tenant_id),UNIQUE(tenant_id,case_id,version),FOREIGN KEY(case_id,tenant_id) REFERENCES legal_cases(id,tenant_id)
);
CREATE TABLE IF NOT EXISTS legal_document_reviews (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,document_id TEXT NOT NULL,decision TEXT NOT NULL,
 reviewer_name TEXT NOT NULL,authority_reference TEXT NOT NULL,qualification_confirmed BIGINT NOT NULL,
 notes TEXT NOT NULL,actor_id TEXT NOT NULL,created_at TEXT NOT NULL,
 FOREIGN KEY(document_id,tenant_id) REFERENCES legal_documents(id,tenant_id)
);
CREATE TABLE IF NOT EXISTS legal_milestones (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,case_id TEXT NOT NULL,stage TEXT NOT NULL,occurred_on TEXT NOT NULL,
 reference TEXT NOT NULL,notes TEXT NOT NULL,document_id TEXT,evidence_ids_json TEXT NOT NULL,
 actor_id TEXT NOT NULL,created_at TEXT NOT NULL,
 FOREIGN KEY(case_id,tenant_id) REFERENCES legal_cases(id,tenant_id)
);
CREATE TABLE IF NOT EXISTS legal_rate_caches (
 version TEXT PRIMARY KEY,verified_through TEXT NOT NULL,cache_json TEXT NOT NULL,created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS legal_documents_case ON legal_documents(tenant_id,case_id,created_at);
CREATE INDEX IF NOT EXISTS legal_milestones_case ON legal_milestones(tenant_id,case_id,occurred_on);
CREATE UNIQUE INDEX IF NOT EXISTS legal_case_invoice ON legal_cases(tenant_id,invoice_id);
CREATE TABLE IF NOT EXISTS legal_case_invoices (
 tenant_id TEXT NOT NULL,case_id TEXT NOT NULL,invoice_id TEXT NOT NULL,
 PRIMARY KEY(tenant_id,invoice_id),
 FOREIGN KEY(case_id,tenant_id) REFERENCES legal_cases(id,tenant_id),
 FOREIGN KEY(invoice_id,tenant_id) REFERENCES invoices(id,tenant_id)
);
CREATE TABLE IF NOT EXISTS legal_evidence_invoices (
 tenant_id TEXT NOT NULL,evidence_id TEXT NOT NULL,invoice_id TEXT NOT NULL,
 PRIMARY KEY(tenant_id,evidence_id,invoice_id),
 FOREIGN KEY(evidence_id) REFERENCES legal_evidence(id),
 FOREIGN KEY(invoice_id,tenant_id) REFERENCES invoices(id,tenant_id)
);
"""


def initialize_schema(connection):
    for statement in SCHEMA.split(";"):
        if statement.strip():connection.execute(statement)
    connection.execute('''INSERT INTO legal_case_invoices(tenant_id,case_id,invoice_id)
        SELECT tenant_id,id,invoice_id FROM legal_cases WHERE 1=1 ON CONFLICT(tenant_id,invoice_id) DO NOTHING''')
    # Historical evidence belongs only to its original invoice; expanding a
    # legal case never silently proves performance for other invoices.
    connection.execute('''INSERT INTO legal_evidence_invoices(tenant_id,evidence_id,invoice_id)
        SELECT e.tenant_id,e.id,l.invoice_id FROM legal_evidence e JOIN legal_cases l
        ON l.id=e.case_id AND l.tenant_id=e.tenant_id
        WHERE NOT EXISTS(SELECT 1 FROM legal_evidence_invoices x WHERE x.evidence_id=e.id AND x.tenant_id=e.tenant_id)
        ON CONFLICT(tenant_id,evidence_id,invoice_id) DO NOTHING''')


def case_invoice_ids(connection,row):
    ids=[r['invoice_id'] for r in connection.execute('SELECT invoice_id FROM legal_case_invoices WHERE tenant_id=? AND case_id=? ORDER BY invoice_id',(row['tenant_id'],row['id']))]
    return [row['invoice_id']]+[key for key in ids if key!=row['invoice_id']]


def _json(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=str)


def document_sender_snapshot(connection, tenant_id):
    """Declared sender facts shared by document review and portfolio freshness."""
    row = connection.execute('''SELECT t.company,s.sender_name,s.reply_to,s.bank_details
        FROM settings s JOIN tenants t ON t.id=s.tenant_id WHERE s.tenant_id=?''', (tenant_id,)).fetchone()
    return {key:row[key] for key in ('company','sender_name','reply_to','bank_details')}


def pretrial_snapshot(connection, row):
    """Stable source facts; passage of the waiting period is not a mutation."""
    facts = json.loads(row['facts_json'])
    last = connection.execute('''SELECT occurred_on,reference FROM legal_milestones
        WHERE tenant_id=? AND case_id=? AND stage='claim_sent'
        ORDER BY occurred_on DESC,created_at DESC,id DESC LIMIT 1''', (row['tenant_id'],row['id'])).fetchone()
    ready = _day(last['occurred_on'])+timedelta(days=facts['pretrial_days']+1) if last else None
    return dict(sent_on=last['occurred_on'] if last else None, reference=last['reference'] if last else '',
                days=facts['pretrial_days'], ready_on=str(ready) if ready else None, applicable=facts['pretrial_days']>0)


def document_snapshot(connection, row, kind):
    """Single authority for exact generated document review/freshness checks."""
    from . import finance
    ledger = finance.financial_snapshot(connection,row['tenant_id'],row['invoice_id'])
    content = dict(ledger=ledger['snapshot_hash'], facts=json.loads(row['facts_json']), facts_revision=row['facts_revision'],
                   sender=document_sender_snapshot(connection,row['tenant_id']))
    ids=case_invoice_ids(connection,row)
    if len(ids)>1:
        content['additional_invoices']=[finance.financial_snapshot(connection,row['tenant_id'],key)['snapshot_hash'] for key in ids[1:]]
    if kind == 'statement_of_claim':
        content['pretrial'] = pretrial_snapshot(connection,row)
    return hashlib.sha256(_json(content).encode()).hexdigest()


def _fetch_official_rates(through):
    if through>business_today():raise ValueError("Будущие ставки нельзя подтвердить заранее")
    source="https://www.cbr.ru/hd_base/KeyRate/?UniDbQuery.Posted=True&UniDbQuery.From=01.08.2016&UniDbQuery.To="+through.strftime("%d.%m.%Y")
    try:
        response=httpx.get(source,timeout=8,follow_redirects=False)
        response.raise_for_status()
        if len(response.content)>2_000_000:raise ValueError("Ответ источника слишком большой")
        raw=re.findall(r"<td[^>]*>\s*(\d{2}\.\d{2}\.\d{4})\s*</td>\s*<td[^>]*>\s*([\d,.]+)",response.text)
        observations={}
        for raw_date,raw_rate in raw:
            when=datetime.strptime(raw_date,"%d.%m.%Y").date()
            rate=str(_percent(raw_rate.replace(",",".")))
            if when>through:raise ValueError("Источник вернул будущую дату")
            if when in observations and observations[when]!=rate:raise ValueError("Противоречивые ставки источника")
            observations[when]=rate
        if len(observations)<30 or min(observations)>date(2016,8,1):raise ValueError("История источника неполна")
        periods=[]
        for when,rate in sorted(observations.items()):
            if when<date(2016,8,1):continue
            if not periods or periods[-1]["annual_percent"]!=rate:periods.append({"from_on":str(when),"annual_percent":rate})
        digest=hashlib.sha256(response.content).hexdigest()
        return {"version":f"cbr-keyrate-{through}-{digest[:12]}","verified_through":str(through),"available_from":"2016-08-01",
                "last_observation_on":str(max(observations)),"source":source,"raw_sha256":digest,"daily_rows":len(observations),"periods":periods}
    except (httpx.HTTPError,ValueError,KeyError):
        raise ValueError("Не удалось подтвердить новую историю ставок на официальном сайте ЦБ. Используйте прежнюю подтверждённую дату либо проверенные периоды с основанием") from None


def _persist_rates(connection,cache):
    connection.execute("INSERT INTO legal_rate_caches(version,verified_through,cache_json,created_at) VALUES(?,?,?,?) ON CONFLICT(version) DO NOTHING",(cache["version"],cache["verified_through"],_json(cache),datetime.now().isoformat()))


def refresh_rates(connection,through):
    """Explicit trusted refresh; no arbitrary endpoint, key or client data."""
    cache=_fetch_official_rates(through)
    _persist_rates(connection,cache)
    global RATE_CACHE
    RATE_CACHE=cache
    return cache


def _ensure_rates(ctx,through):
    """One verified public history per day, persisted across process restarts.

    Fetch outside a database transaction; a failed fetch never extends coverage.
    Failed attempts are bounded per process, so a provider outage is not amplified
    by each invoice calculation. Explicit overrides do not call this provider.
    """
    global RATE_CACHE,_RATE_FAILURE_UNTIL
    with _RATE_LOCK:
        with ctx.database(ctx.config) as connection:
            row=connection.execute("SELECT cache_json FROM legal_rate_caches ORDER BY verified_through DESC,created_at DESC LIMIT 1").fetchone()
            if row:
                stored=json.loads(row["cache_json"])
                if stored["verified_through"]>=RATE_CACHE["verified_through"]:RATE_CACHE=stored
        if through<=_day(RATE_CACHE["verified_through"]):return
        if time.monotonic()<_RATE_FAILURE_UNTIL:
            raise ValueError("История ставок временно недоступна. Задайте проверенные периоды с основанием или повторите позднее")
        try:
            cache=_fetch_official_rates(business_today())
            with ctx.database(ctx.config,write=True) as connection:_persist_rates(connection,cache)
            RATE_CACHE=cache
        except ValueError:
            _RATE_FAILURE_UNTIL=time.monotonic()+300
            raise


def create_router(ctx):
    """Keep main import-free; all auth/database operations use the shared context."""
    from . import finance
    from .legal_documents import build_docx
    from .legal_fees import FEE_FIELDS, calculate_fees, current_model
    from .workflow import require_manager
    router=APIRouter(prefix="/api/legal",tags=["legal"])

    def case_row(connection,tenant,case_id):
        row=connection.execute("SELECT * FROM legal_cases WHERE id=? AND tenant_id=?",(case_id,tenant)).fetchone()
        if row is None:ctx.problem(404,"Юридическое дело не найдено")
        return row

    def document_row(connection,tenant,document_id):
        row=connection.execute("SELECT * FROM legal_documents WHERE id=? AND tenant_id=?",(document_id,tenant)).fetchone()
        if row is None:ctx.problem(404,"Документ не найден")
        return row

    def evidence_rows(connection,tenant,case_id):
        rows=[dict(row) for row in connection.execute("SELECT * FROM legal_evidence WHERE tenant_id=? AND case_id=? ORDER BY created_at,id",(tenant,case_id))]
        anchor=case_row(connection,tenant,case_id)['invoice_id']
        for row in rows:
            row['invoice_ids']=[r['invoice_id'] for r in connection.execute('SELECT invoice_id FROM legal_evidence_invoices WHERE tenant_id=? AND evidence_id=? ORDER BY invoice_id',(tenant,row['id']))] or [anchor]
        return rows

    def milestones(connection,tenant,case_id):
        result=[]
        for row in connection.execute("SELECT * FROM legal_milestones WHERE tenant_id=? AND case_id=? ORDER BY occurred_on,created_at,id",(tenant,case_id)):
            item=dict(row);item["evidence_ids"]=json.loads(item.pop("evidence_ids_json"));item["manual"]=True;item.pop("tenant_id",None)
            result.append(item)
        return result

    def pretrial(connection,row):
        value=pretrial_snapshot(connection,row)
        return {**value,"ready":value['days']==0 or bool(value['ready_on'] and business_today()>=_day(value['ready_on']))}

    def snapshot(connection,row,kind):
        return document_snapshot(connection,row,kind)

    def calculation(connection,tenant,invoice_id,data):
        ledger=finance.financial_snapshot(connection,tenant,invoice_id)
        inv=ledger["invoice"]
        raw=data.model_dump(mode="json")
        raw.pop("invoice_id",None)
        opening=raw.pop("opening_reductions",[])
        history=ledger["financial_events"]
        assumed=[event for event in history if event["type"]=="opening"]
        reductions=[{"effective_on":event["effective_on"],"signed_reduction":event["signed_reduction"]} for event in history if event["type"]!="opening"]
        opening_amount=sum(event["signed_reduction"] for event in assumed)
        if opening_amount:
            if raw["sanction"]!="none":
                if sum(item["amount"] for item in opening)!=opening_amount:
                    raise ValueError("У начальных оплат нет подтверждённых дат. Укажите opening_reductions с датами, доказательствами и общей суммой начальных оплат")
                if any(_day(item["effective_on"])>_day(raw["through_on"]) for item in opening):
                    raise ValueError("Дата начальной оплаты позже даты расчёта")
                reductions.extend({"effective_on":item["effective_on"],"signed_reduction":item["amount"]} for item in opening)
            else:
                reductions.extend({"effective_on":event["effective_on"],"signed_reduction":event["signed_reduction"]} for event in assumed)
        elif opening:
            raise ValueError("В реестре нет начальных оплат для такой замены дат")
        result=calculate_debt(principal=inv["original_amount"],due_on=inv["due_on"],reductions=reductions,**raw)
        result.update(invoice_id=invoice_id,snapshot_hash=ledger["snapshot_hash"],opening_payment_dates_verified=not opening_amount or bool(opening))
        return result

    def doc_view(connection,row):
        parent=case_row(connection,row["tenant_id"],row["case_id"])
        stale=snapshot(connection,parent,row["kind"])!=row["snapshot_hash"]
        reviews=[dict(item) for item in connection.execute("SELECT id,decision,reviewer_name,authority_reference,qualification_confirmed,notes,created_at FROM legal_document_reviews WHERE tenant_id=? AND document_id=? ORDER BY created_at,id",(row["tenant_id"],row["id"]))]
        status="stale" if stale else reviews[-1]["decision"] if reviews else "draft"
        return {**{key:row[key] for key in ("id","case_id","kind","version","created_at","sha256","snapshot_hash")},
                "calculation":json.loads(row["calculation_json"]),"status":status,"stale":stale,"review_required":True,
                "download_url":f"/api/legal/documents/{row['id']}/download","reviews":reviews}

    def fee(connection,row):
        facts=json.loads(row["facts_json"])
        ids=case_invoice_ids(connection,row)
        recovery=[item for key in ids for item in finance.confirmed_recovery(connection,row["tenant_id"],key)]
        paid=sum(finance.financial_snapshot(connection,row["tenant_id"],key)["invoice"]['paid_amount'] for key in ids)
        steps=milestones(connection,row['tenant_id'],row['id'])
        filing=[dict(item) for item in connection.execute('''SELECT m.*,d.kind FROM legal_milestones m
            JOIN legal_documents d ON d.id=m.document_id AND d.tenant_id=m.tenant_id AND d.case_id=m.case_id
            WHERE m.tenant_id=? AND m.case_id=? AND m.stage='filed' ''',(row['tenant_id'],row['id']))]
        return calculate_fees(facts,recovery,filing,[item for item in steps if item['stage']=='claim_sent'],paid)

    def case_calculation(connection,row,data):
        ids=case_invoice_ids(connection,row)
        per_invoice=getattr(data,'invoice_opening_reductions',{})
        if any(key not in ids for key in per_invoice):raise ValueError('Начальная оплата относится к счёту вне этого дела')
        raw=data.model_dump(mode='json',exclude={'invoice_opening_reductions'})
        if len(ids)==1:
            if per_invoice:
                if data.opening_reductions:raise ValueError('Укажите начальные оплаты одним способом')
                raw['opening_reductions']=[r.model_dump(mode='json') for r in per_invoice.get(ids[0],[])]
            return calculation(connection,row['tenant_id'],ids[0],models.Calculation(**raw))
        if data.opening_reductions:
            raise ValueError('Для общего требования укажите даты начальных оплат отдельно для каждого счёта')
        if data.penalty_cap_amount is not None:
            raise ValueError('Общий лимит неустойки по нескольким счетам требует отдельного расчёта юриста')
        parts=[calculation(connection,row['tenant_id'],key,models.Calculation(**dict(raw,opening_reductions=[r.model_dump(mode='json') for r in per_invoice.get(key,[])]))) for key in ids]
        result=dict(parts[0])
        for key in ('original_principal','principal_amount','interest_amount','penalty_amount','total_claim_amount','rounding_difference_interest','rounding_or_cap_penalty'):
            result[key]=sum(p[key] for p in parts)
        result.update(from_on=min(p['from_on'] for p in parts),invoice_ids=ids,invoice_calculations=parts,
                      line_items=[dict(line,invoice_id=key) for key,p in zip(ids,parts) for line in p['line_items']],
                      fee_claim_amount=arbitration_fee(result['total_claim_amount']) if result['total_claim_amount'] else 0,
                      fee_order_amount=arbitration_fee(result['total_claim_amount'],'court_order') if result['total_claim_amount'] else 0,
                      order_eligible=bool(0<result['total_claim_amount']<=ORDER_LIMIT))
        return result

    def case_view(connection,row,detail=False):
        steps=milestones(connection,row["tenant_id"],row["id"])
        item={**{key:row[key] for key in ("id","invoice_id","facts_revision","created_at","updated_at")},"facts":json.loads(row["facts_json"]),
              "stage":steps[-1]["stage"] if steps else "intake","invoice":finance.financial_snapshot(connection,row["tenant_id"],row["invoice_id"])["invoice"],
              "pretrial":pretrial(connection,row)}
        invoices=[finance.financial_snapshot(connection,row['tenant_id'],key)['invoice'] for key in case_invoice_ids(connection,row)]
        item.update(invoices=invoices,invoice_ids=[inv['id'] for inv in invoices],balance=sum(inv['balance'] for inv in invoices),invoice_count=len(invoices))
        item['next_action']='Подготовить иск после отмены приказа' if item['stage']=='order_cancelled' else 'Проверить документы и выбрать следующий шаг'
        contract=connection.execute("SELECT k.number FROM workflow_invoice_contracts m JOIN workflow_contracts k ON k.id=m.contract_id AND k.tenant_id=m.tenant_id WHERE m.invoice_id=? AND m.tenant_id=?",(row['invoice_id'],row['tenant_id'])).fetchone()
        item['suggested_contract_number']=contract['number'] if contract else ''
        if detail:
            docs=[doc_view(connection,doc) for doc in connection.execute("SELECT * FROM legal_documents WHERE tenant_id=? AND case_id=? ORDER BY version DESC",(row["tenant_id"],row["id"]))]
            item.update(evidence=[{k:v for k,v in value.items() if k!="tenant_id"} for value in evidence_rows(connection,row["tenant_id"],row["id"])],
                        documents=docs,milestones=steps,fee=fee(connection,row),calculation=docs[0]["calculation"] if docs else None)
        return item

    @router.get("/rules")
    def get_rules(user=Depends(ctx.get_user)):
        try:_ensure_rates(ctx,business_today())
        except ValueError as error:return {**rules(),"refresh_error":str(error)}
        return rules()

    @router.post("/calculations")
    def calculate(data:models.CalculationRequest,user=Depends(ctx.get_user)):
        if data.sanction in ("art395","both") and data.rate_override is None:
            try:_ensure_rates(ctx,data.through_on)
            except ValueError as error:ctx.problem(422,str(error))
        with ctx.database(ctx.config) as connection:
            try:return calculation(connection,user["tenant_id"],data.invoice_id,data)
            except ValueError as error:ctx.problem(422,str(error))

    @router.get("/cases")
    def list_cases(user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as connection:
            return {"items":[case_view(connection,row) for row in connection.execute("SELECT * FROM legal_cases WHERE tenant_id=? ORDER BY updated_at DESC LIMIT 500",(user["tenant_id"],))]}

    @router.post("/cases",status_code=201)
    def create_case(data:models.CaseCreate,user=Depends(ctx.get_user)):
        with ctx.database(ctx.config,write=True) as connection:
            if data.facts.fee_agreement_reference or data.facts.fee_start_on or data.facts.lawyer_agreement_reference:
                require_manager(connection,user)
            finance.financial_snapshot(connection,user["tenant_id"],data.invoice_id)
            ids=list(dict.fromkeys([data.invoice_id]+data.invoice_ids))
            for invoice_id in ids:
                finance.financial_snapshot(connection,user['tenant_id'],invoice_id)
            if len(ids)>1:
                contract_ids=[]
                for key in ids:
                    finance.financial_snapshot(connection,user['tenant_id'],key)
                    mapped=connection.execute('SELECT contract_id FROM workflow_invoice_contracts WHERE tenant_id=? AND invoice_id=?',(user['tenant_id'],key)).fetchone()
                    if mapped is None:ctx.problem(422,'Сначала объедините выбранные счета в один договор во вкладке «Работа»')
                    contract_ids.append(mapped['contract_id'])
                if len(set(contract_ids))!=1:ctx.problem(422,'В одном юридическом деле могут быть только счета одного договора')
            for key in ids:
                if connection.execute('SELECT case_id FROM legal_case_invoices WHERE tenant_id=? AND invoice_id=?',(user['tenant_id'],key)).fetchone():
                    ctx.problem(409,'По одному из выбранных счетов уже открыто юридическое дело')
            # Workflow contract is a factual prefill, never a legal confirmation.
            contract=connection.execute("SELECT k.number FROM workflow_invoice_contracts m JOIN workflow_contracts k ON k.id=m.contract_id AND k.tenant_id=m.tenant_id WHERE m.invoice_id=? AND m.tenant_id=?",(data.invoice_id,user["tenant_id"])).fetchone()
            if contract and not data.facts.contract_number:
                data.facts.contract_number=contract["number"]
            key=ctx.identifier();stamp=ctx.now()
            inserted=connection.execute("INSERT INTO legal_cases(id,tenant_id,invoice_id,facts_json,facts_revision,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(tenant_id,invoice_id) DO NOTHING",(key,user["tenant_id"],data.invoice_id,_json(data.facts.model_dump(mode="json")),1,user["id"],stamp,stamp))
            if inserted.rowcount!=1:ctx.problem(409,"По этому счёту уже открыто юридическое дело. Продолжите его, чтобы не дублировать требования и гонорар")
            for invoice_id in ids:
                member=connection.execute('INSERT INTO legal_case_invoices(tenant_id,case_id,invoice_id) VALUES(?,?,?) ON CONFLICT(tenant_id,invoice_id) DO NOTHING',(user['tenant_id'],key,invoice_id))
                if member.rowcount!=1:ctx.problem(409,'Счёт уже включён в другое юридическое дело')
            ctx.event(connection,user["tenant_id"],data.invoice_id,"legal_case_created","Открыто юридическое дело",key)
            return case_view(connection,case_row(connection,user["tenant_id"],key),True)

    @router.get("/cases/{case_id}")
    def get_case(case_id:str,user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as connection:return case_view(connection,case_row(connection,user["tenant_id"],case_id),True)

    @router.post('/cases/{case_id}/calculation')
    def calculate_case(case_id:str,data:models.CaseCalculation,user=Depends(ctx.get_user)):
        if data.sanction in ('art395','both') and data.rate_override is None:
            try:_ensure_rates(ctx,data.through_on)
            except ValueError as error:ctx.problem(422,str(error))
        with ctx.database(ctx.config) as connection:
            try:return case_calculation(connection,case_row(connection,user['tenant_id'],case_id),data)
            except ValueError as error:ctx.problem(422,str(error))

    @router.patch("/cases/{case_id}")
    def update_case(case_id:str,data:models.CaseUpdate,user=Depends(ctx.get_user)):
        with ctx.database(ctx.config,write=True) as connection:
            row=case_row(connection,user["tenant_id"],case_id);value=_json(data.facts.model_dump(mode="json"))
            previous=json.loads(row['facts_json'])
            if not current_model(previous) and 'fee_model_version' not in data.facts.model_fields_set:
                ctx.problem(409,'Руководитель должен явно подтвердить новую модель вознаграждения')
            if not current_model(previous) or any(previous.get(key)!=data.facts.model_dump(mode='json').get(key) for key in FEE_FIELDS):
                require_manager(connection,user)
            if value!=row["facts_json"]:
                connection.execute("UPDATE legal_cases SET facts_json=?,facts_revision=facts_revision+1,updated_at=? WHERE id=? AND tenant_id=?",(value,ctx.now(),case_id,user["tenant_id"]))
                ctx.event(connection,user["tenant_id"],row["invoice_id"],"legal_facts_updated","Обновлены юридические факты","Ранее подготовленные версии требуют повторной подготовки")
            return case_view(connection,case_row(connection,user["tenant_id"],case_id),True)

    @router.post("/cases/{case_id}/evidence",status_code=201)
    def add_evidence(case_id:str,data:models.Evidence,user=Depends(ctx.get_user)):
        with ctx.database(ctx.config,write=True) as connection:
            parent=case_row(connection,user["tenant_id"],case_id);key=ctx.identifier();stamp=ctx.now()
            members=case_invoice_ids(connection,parent)
            coverage=list(dict.fromkeys(members if data.covers_all_invoices else data.invoice_ids))
            if any(invoice_id not in members for invoice_id in coverage):ctx.problem(422,'Выберите счета этого юридического дела')
            if not coverage:
                if len(members)>1 and data.kind in ('contract','performance','reconciliation'):
                    ctx.problem(422,'Отметьте счета, которые подтверждает доказательство')
                coverage=[parent['invoice_id']]
            connection.execute("INSERT INTO legal_evidence(id,tenant_id,case_id,kind,title,reference,occurred_on,sha256,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(key,user["tenant_id"],case_id,data.kind,data.title,data.reference,str(data.occurred_on),data.sha256,user["id"],stamp))
            for invoice_id in coverage:connection.execute('INSERT INTO legal_evidence_invoices(tenant_id,evidence_id,invoice_id) VALUES(?,?,?)',(user['tenant_id'],key,invoice_id))
            ctx.event(connection,user["tenant_id"],parent["invoice_id"],"legal_evidence_recorded","Добавлено доказательство",data.title)
            return {"id":key,"case_id":case_id,**data.model_dump(mode="json"),"invoice_ids":coverage,"created_at":stamp}

    @router.post("/cases/{case_id}/documents",status_code=201)
    def generate(case_id:str,data:models.DocumentCreate,user=Depends(ctx.get_user)):
        if data.calculation.sanction in ("art395","both") and data.calculation.rate_override is None:
            try:_ensure_rates(ctx,data.calculation.through_on)
            except ValueError as error:ctx.problem(422,str(error))
        with ctx.database(ctx.config,write=True) as connection:
            parent=case_row(connection,user["tenant_id"],case_id)
            try:
                result=case_calculation(connection,parent,data.calculation)
                invoices=[finance.financial_snapshot(connection,user['tenant_id'],key)['invoice'] for key in case_invoice_ids(connection,parent)]
                current_balance=sum(inv['balance'] for inv in invoices)
                if result.get('invoice_calculations') and any(part['principal_amount']!=inv['balance'] for part,inv in zip(result['invoice_calculations'],invoices)):
                    raise ValueError('После даты расчёта изменился долг по одному из счетов. Выберите актуальную дату расчёта')
                if result["principal_amount"]!=current_balance:
                    raise ValueError("После даты расчёта изменился основной долг. Выберите актуальную дату, чтобы не предъявить уже погашенную сумму")
                facts=json.loads(parent["facts_json"]);facts["_pretrial"]=pretrial(connection,parent)
                invoice_identity=finance.financial_snapshot(connection,user["tenant_id"],parent["invoice_id"])["invoice"]
                facts["_invoice"]=invoice_identity
                facts['_invoices']=invoices
                if invoice_identity.get("inn") and facts["debtor"]["inn"]!=invoice_identity["inn"]:
                    raise ValueError("ИНН должника в юридических фактах не совпадает со счётом. Сначала исправьте и сверьте источник")
                if data.kind=="court_order" and any(inv['status']=='disputed' for inv in invoices):
                    raise ValueError("В реестре зафиксирован спор. Приказное производство для такого требования недоступно; требуется разбор юриста")
                if data.kind=='court_order' and any(step['stage']=='order_cancelled' for step in milestones(connection,user['tenant_id'],case_id)):
                    raise ValueError('Приказ отменён. Подготовьте исковое заявление после проверки юристом')
                proof=evidence_rows(connection,user["tenant_id"],case_id)
                version=connection.execute("SELECT COALESCE(MAX(version),0)+1 AS next_version FROM legal_documents WHERE tenant_id=? AND case_id=?",(user["tenant_id"],case_id)).fetchone()["next_version"]
                content=build_docx(data.kind,facts,result,proof,version=version,created_on=str(business_today()))
            except ValueError as error:ctx.problem(422,str(error))
            key=ctx.identifier();digest=hashlib.sha256(content).hexdigest()
            connection.execute("INSERT INTO legal_documents(id,tenant_id,case_id,kind,version,snapshot_hash,payload_json,calculation_json,sha256,content_base64,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(key,user["tenant_id"],case_id,data.kind,version,snapshot(connection,parent,data.kind),_json({"facts":facts,"evidence":proof,"calculation_input":data.calculation.model_dump(mode="json")}),_json(result),digest,base64.b64encode(content).decode(),user["id"],ctx.now()))
            ctx.event(connection,user["tenant_id"],parent["invoice_id"],"legal_document_prepared","Подготовлен юридический документ",f"{data.kind}, версия {version}; требуется проверка")
            return doc_view(connection,document_row(connection,user["tenant_id"],key))

    @router.post("/documents/{document_id}/review")
    def review_document(document_id:str,data:models.Review,user=Depends(ctx.get_user)):
        with ctx.database(ctx.config,write=True) as connection:
            doc=document_row(connection,user["tenant_id"],document_id)
            view=doc_view(connection,doc)
            if view["stale"]:ctx.problem(409,"Факты, реквизиты или финансовый снимок изменились. Подготовьте новую версию документа")
            connection.execute("INSERT INTO legal_document_reviews(id,tenant_id,document_id,decision,reviewer_name,authority_reference,qualification_confirmed,notes,actor_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(ctx.identifier(),user["tenant_id"],document_id,data.decision,data.reviewer_name,data.authority_reference,int(data.qualification_confirmed),data.notes,user["id"],ctx.now()))
            parent=case_row(connection,user["tenant_id"],doc["case_id"])
            ctx.event(connection,user["tenant_id"],parent["invoice_id"],"legal_document_reviewed","Зафиксирована проверка документа",data.reviewer_name+": "+data.decision)
            return doc_view(connection,doc)

    @router.get("/documents/{document_id}/download")
    def download(document_id:str,user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as connection:doc=dict(document_row(connection,user["tenant_id"],document_id))
        content=base64.b64decode(doc["content_base64"])
        if hashlib.sha256(content).hexdigest()!=doc["sha256"]:ctx.problem(409,"Контрольная сумма документа не совпадает")
        return Response(content,media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",headers={"Content-Disposition":f'attachment; filename="mandato-{doc["kind"]}-v{doc["version"]}.docx"',"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})

    @router.get("/cases/{case_id}/fee")
    def calculate_fee(case_id:str,user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as connection:return fee(connection,case_row(connection,user["tenant_id"],case_id))

    @router.post("/cases/{case_id}/milestones",status_code=201)
    def record_milestone(case_id:str,data:models.Milestone,user=Depends(ctx.get_user)):
        with ctx.database(ctx.config,write=True) as connection:
            parent=case_row(connection,user["tenant_id"],case_id)
            all_proof={row["id"]:row for row in evidence_rows(connection,user["tenant_id"],case_id)}
            if any(key not in all_proof for key in data.evidence_ids):ctx.problem(404,"Доказательство не найдено в этом деле")
            selected=[all_proof[key] for key in data.evidence_ids];kinds={row["kind"] for row in selected}
            if any(_day(row["occurred_on"])>data.occurred_on for row in selected):ctx.problem(422,"Доказательство датировано позже ручного действия")
            existing=milestones(connection,user["tenant_id"],case_id)
            doc=None
            if data.document_id:
                doc=document_row(connection,user["tenant_id"],data.document_id)
                if doc["case_id"]!=case_id:ctx.problem(404,"Документ не относится к этому делу")
                view=doc_view(connection,doc)
                if view["status"]!="approved":ctx.problem(409,"Нужно согласовать актуальную версию документа")
                if datetime.fromisoformat(doc["created_at"]).astimezone(business_timezone()).date()>data.occurred_on:
                    ctx.problem(422,"Действие не могло состояться раньше создания этой версии. Для внешней исторической претензии укажите доказательство без ссылки на новый документ")
            if data.stage=="claim_sent":
                if "claim_dispatch" not in kinds:ctx.problem(422,"Нужно доказательство направления претензии")
                if doc is not None and doc["kind"]!="pretrial_claim":ctx.problem(422,"Выберите претензию")
            elif data.stage=="claim_delivered":
                if "claim_delivery" not in kinds or not any(item["stage"]=="claim_sent" and item["occurred_on"]<=str(data.occurred_on) for item in existing):ctx.problem(422,"Нужны направление претензии и доказательство вручения")
            elif data.stage=="filed":
                if doc is None or doc["kind"] not in ("court_order","statement_of_claim"):ctx.problem(422,"Нужна проверенная версия заявления или иска")
                if not {"duty_payment","application_copy_sent","filing_receipt"}.issubset(kinds):ctx.problem(422,"Нужны доказательства пошлины, направления копий и ручной подачи")
                if doc["kind"]=="statement_of_claim":
                    timer=pretrial(connection,parent)
                    if timer["applicable"] and (not timer["ready_on"] or str(data.occurred_on)<timer["ready_on"]):ctx.problem(409,"Досудебный срок ещё не истёк")
            elif data.stage in ("order_issued","judgment"):
                if "court_act" not in kinds or not any(item["stage"]=="filed" and item["occurred_on"]<=str(data.occurred_on) for item in existing):ctx.problem(422,"Нужны ранее зафиксированная подача и судебный акт")
                expected='court_order' if data.stage=='order_issued' else 'statement_of_claim'
                filings=connection.execute('''SELECT m.occurred_on FROM legal_milestones m JOIN legal_documents d
                    ON d.id=m.document_id AND d.tenant_id=m.tenant_id AND d.case_id=m.case_id
                    WHERE m.tenant_id=? AND m.case_id=? AND m.stage='filed' AND d.kind=? AND m.occurred_on<=?''',
                    (user['tenant_id'],case_id,expected,str(data.occurred_on))).fetchall()
                if not filings:ctx.problem(422,'Сначала подтвердите подачу соответствующего заявления в суд')
                cancelled_on=max((item['occurred_on'] for item in existing if item['stage']=='order_cancelled'),default=None)
                if data.stage=='judgment' and cancelled_on and not any(row['occurred_on']>=cancelled_on for row in filings):
                    ctx.problem(422,'После отмены приказа нужно подтвердить подачу иска')
            elif data.stage=='order_cancelled':
                if 'order_cancellation' not in kinds or not any(item['stage']=='order_issued' and item['occurred_on']<=str(data.occurred_on) for item in existing):
                    ctx.problem(422,'Нужны полученный судебный приказ и определение о его отмене')
            elif data.stage=="writ_received":
                if "writ" not in kinds or not any(item["stage"] in ("judgment","order_issued") and item["occurred_on"]<=str(data.occurred_on) for item in existing):ctx.problem(422,"Нужны судебный акт и исполнительный документ")
            elif data.stage in ("bank_submitted","fssp_submitted"):
                required="bank_submission" if data.stage=="bank_submitted" else "fssp_submission"
                if required not in kinds or not any(item["stage"] in ("writ_received","order_issued") and item["occurred_on"]<=str(data.occurred_on) for item in existing):ctx.problem(422,"Нужны исполнительный документ и доказательство ручной передачи")
            elif data.stage=="closed":
                if any(finance.financial_snapshot(connection,user['tenant_id'],key)['invoice']['balance']!=0 for key in case_invoice_ids(connection,parent)):ctx.problem(409,"В реестре остаётся непогашенный долг; зафиксируйте основание остановки")
            cancelled=[item for item in existing if item['stage']=='order_cancelled']
            if cancelled and data.stage in ('writ_received','bank_submitted','fssp_submitted','order_issued'):
                last_cancel=max(item['occurred_on'] for item in cancelled)
                if not any(item['stage']=='judgment' and item['occurred_on']>=last_cancel for item in existing):
                    ctx.problem(409,'Приказ отменён. Исполнение возможно после нового судебного решения')
            if data.stage=='filed' and doc and doc['kind']=='court_order' and cancelled:
                ctx.problem(409,'Приказ отменён. Подготовьте и согласуйте исковое заявление')
            key=ctx.identifier();stamp=ctx.now()
            connection.execute("INSERT INTO legal_milestones(id,tenant_id,case_id,stage,occurred_on,reference,notes,document_id,evidence_ids_json,actor_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(key,user["tenant_id"],case_id,data.stage,str(data.occurred_on),data.reference,data.notes,data.document_id,_json(data.evidence_ids),user["id"],stamp))
            connection.execute("UPDATE legal_cases SET updated_at=? WHERE id=? AND tenant_id=?",(stamp,case_id,user["tenant_id"]))
            ctx.event(connection,user["tenant_id"],parent["invoice_id"],"legal_manual_milestone","Зафиксировано ручное действие",data.stage+": "+data.reference)
            return {"id":key,"case_id":case_id,**data.model_dump(mode="json"),"manual":True,"created_at":stamp}

    return router
