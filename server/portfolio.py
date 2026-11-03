"""Immutable portfolio audits assembled from actual tenant source records."""
import base64
import binascii
import csv
import hashlib
import importlib
import io
import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import Field, field_validator

from . import finance, legal
from .business_time import business_today
from .models import Input, single_line
from .portfolio_rules import audit_invoice, finding

SCHEMA = '''
CREATE TABLE IF NOT EXISTS portfolio_runs (
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id), snapshot_hash TEXT NOT NULL,
 report_json TEXT NOT NULL, created_at TEXT NOT NULL, actor_id TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS portfolio_runs_tenant ON portfolio_runs(tenant_id,created_at);
CREATE TABLE IF NOT EXISTS portfolio_evidence (
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, invoice_id TEXT NOT NULL, kind TEXT NOT NULL,
 reference TEXT NOT NULL, occurred_on TEXT NOT NULL, note TEXT NOT NULL, filename TEXT NOT NULL,
 content_base64 TEXT NOT NULL, sha256 TEXT NOT NULL, created_at TEXT NOT NULL, actor_id TEXT NOT NULL,
 FOREIGN KEY(invoice_id,tenant_id) REFERENCES invoices(id,tenant_id)
);
CREATE TABLE IF NOT EXISTS portfolio_deadlines (
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, invoice_id TEXT NOT NULL, kind TEXT NOT NULL,
 review_on TEXT NOT NULL, basis TEXT NOT NULL, created_at TEXT NOT NULL, actor_id TEXT NOT NULL,
 FOREIGN KEY(invoice_id,tenant_id) REFERENCES invoices(id,tenant_id)
);
CREATE TABLE IF NOT EXISTS portfolio_deadline_resolutions (
 deadline_id TEXT PRIMARY KEY REFERENCES portfolio_deadlines(id), tenant_id TEXT NOT NULL REFERENCES tenants(id),
 reason TEXT NOT NULL, resolved_at TEXT NOT NULL, actor_id TEXT NOT NULL
);
'''


def initialize_schema(connection):
    for statement in SCHEMA.split(';'):
        if statement.strip(): connection.execute(statement)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)


class EvidenceInput(Input):
    kind: Literal['contract', 'performance', 'payment_terms', 'reconciliation', 'correspondence', 'other']
    reference: str = Field(min_length=3, max_length=1000)
    occurred_on: date
    note: str = Field(default='', max_length=3000)
    filename: str = Field(default='', max_length=150)
    content_base64: str = Field(default='', max_length=1_400_000)

    @field_validator('occurred_on')
    @classmethod
    def not_future(cls, value):
        if value > business_today(): raise ValueError('Дата документа не может быть в будущем')
        return value

    @field_validator('reference', 'filename')
    @classmethod
    def safe_line(cls, value): return single_line(value)


class DeadlineInput(Input):
    kind: Literal['limitation_review', 'claim_review', 'court_review', 'other']
    review_on: date
    basis: str = Field(min_length=10, max_length=2000)


class AuditInput(Input):
    pass


class ResolveInput(Input):
    reason: str = Field(min_length=10, max_length=2000)


def _registry(connection, tenant):
    try: module = importlib.import_module('server.integrations')
    except ModuleNotFoundError as error:
        if error.name != 'server.integrations': raise
        return {}
    helper = getattr(module, 'latest_registry_checks', None)
    return helper(connection, tenant) if helper else {}


def inputs(connection, tenant):
    invoices = [dict(r) for r in connection.execute('SELECT * FROM invoices WHERE tenant_id=? ORDER BY id', (tenant,))]
    if len(invoices) > 5000: finance.fail(422, 'За один аудит доступно до 5 000 счетов. Разделите портфель.')
    rows = lambda table, order='id': [dict(r) for r in connection.execute(f'SELECT * FROM {table} WHERE tenant_id=? ORDER BY {order}', (tenant,))]
    # Table/order identifiers are exclusively static call-site literals, never user input.
    evidence = [dict(r) for r in connection.execute('SELECT id,invoice_id,kind,reference,occurred_on,note,filename,sha256,created_at,actor_id FROM portfolio_evidence WHERE tenant_id=? ORDER BY id', (tenant,))]
    return dict(as_of=str(business_today()), sender=legal.document_sender_snapshot(connection,tenant),
        invoices=invoices, counterparties=rows('finance_counterparties'),
        evidence=evidence, deadlines=rows('portfolio_deadlines'), deadline_resolutions=rows('portfolio_deadline_resolutions', 'deadline_id'), reconciliations=rows('accounting_reconciliations'),
        bank=rows('finance_bank_payments'), promises=rows('finance_promises'), cases=rows('legal_cases'), case_invoices=rows('legal_case_invoices','invoice_id'),
        installments=[dict(r) for r in connection.execute('SELECT s.* FROM finance_installments s JOIN finance_promises p ON p.id=s.promise_id WHERE p.tenant_id=? ORDER BY s.id', (tenant,))],
        legal_evidence=rows('legal_evidence'), legal_evidence_invoices=rows('legal_evidence_invoices','invoice_id'), documents=[dict(r) for r in connection.execute(
            'SELECT id,case_id,kind,version,snapshot_hash,created_at FROM legal_documents WHERE tenant_id=? ORDER BY id', (tenant,))],
        registry=_registry(connection, tenant))


def snapshot(data): return hashlib.sha256(encoded(data).encode()).hexdigest()


def _registry_view(raw, as_of):
    result = raw.get('result') or {}
    checked = raw.get('checked_at')
    fresh = False
    if checked:
        try:
            then = datetime.fromisoformat(checked.replace('Z', '+00:00'))
            if then.tzinfo is None: then = then.replace(tzinfo=timezone.utc)
            fresh = timedelta(0) <= datetime.now(timezone.utc)-then <= timedelta(days=1)
        except (ValueError, TypeError): pass
    return dict(status=raw.get('status', 'unverified'), checked_at=checked, provider=raw.get('provider', 'registry'),
        coverage=raw.get('coverage', []), fresh=fresh,
        registration_status=raw.get('registration_status') or result.get('registration_status', 'UNKNOWN'))


def build_report(connection, tenant, data):
    as_of = date.fromisoformat(data['as_of'])
    cps = {r['id']: r for r in data['counterparties']}
    evidence = defaultdict(set)
    for row in data['evidence']: evidence[row['invoice_id']].add(row['kind'])
    cases = {r['id']: r for r in data['cases']}
    memberships=data.get('case_invoices') or [dict(invoice_id=r['invoice_id'],case_id=r['id']) for r in data['cases']]
    case_by_invoice = {r['invoice_id']:r for r in data['cases']}
    case_by_invoice.update({r['invoice_id']: cases[r['case_id']] for r in memberships if r['case_id'] in cases})
    for row in data['legal_evidence']:
        coverage=[r['invoice_id'] for r in data.get('legal_evidence_invoices',[]) if r['evidence_id']==row['id']]
        if not coverage and row['case_id'] in cases:coverage=[cases[row['case_id']]['invoice_id']]
        for invoice_id in coverage:evidence[invoice_id].add(row['kind'])
    # A contractual due basis is separately registered; a typed due date is not primary evidence.
    for invoice_id,row in case_by_invoice.items():
        facts = json.loads(row['facts_json'])
        if facts.get('due_basis') and 'contract' in evidence[invoice_id]: evidence[invoice_id].add('payment_terms')
    latest = {}
    for row in data['reconciliations']:
        old = latest.get(row['counterparty_id'])
        if not old or (row['as_of'], row['created_at'], row['id']) > (old['as_of'], old['created_at'], old['id']): latest[row['counterparty_id']] = dict(row)
    balances, invoice_counts = defaultdict(int), defaultdict(int)
    for inv in data['invoices']:
        balances[inv['counterparty_id']] += finance.balance(inv)
        invoice_counts[inv['counterparty_id']] += 1
    for cp_id, row in latest.items(): row['current_discrepancy'] = row['source_balance']-balances.get(cp_id, 0)
    promises, deadlines = defaultdict(list), defaultdict(list)
    installments=defaultdict(list)
    for row in data['installments']: installments[row['promise_id']].append(row)
    for row in data['promises']: promises[row['invoice_id']].append({**row,'installments':installments[row['id']]})
    resolved={r['deadline_id'] for r in data['deadline_resolutions']}
    for row in data['deadlines']:
        if row['id'] not in resolved: deadlines[row['invoice_id']].append(row)
    docs = {}
    for row in data['documents']:
        by_kind = docs.setdefault(row['case_id'], {})
        if row['kind'] not in by_kind or row['version'] > by_kind[row['kind']]['version']:
            by_kind[row['kind']] = row
    items = []
    for inv in data['invoices']:
        stale = False
        case = case_by_invoice.get(inv['id'])
        if case and case['id'] in docs:
            stale = any(doc['snapshot_hash'] != legal.document_snapshot(connection,case,doc['kind'])
                        for doc in docs[case['id']].values())
        items.append(audit_invoice(inv, cps[inv['counterparty_id']], evidence=evidence[inv['id']],
            reconciliation=latest.get(inv['counterparty_id']), registry=_registry_view(data['registry'].get(inv['inn'], {}), as_of),
            promises=promises[inv['id']], deadlines=deadlines[inv['id']], document_stale=stale, as_of=as_of))
    global_findings = []
    unallocated = sum(r['amount']-r['allocated_amount']-r['returned_amount'] for r in data['bank'] if r['confirmed'])
    if unallocated:
        global_findings.append(finding('unallocated_cash', 'attention', 'Есть нераспределённые поступления',
            'Деньги в источниках выписки ещё не сопоставлены со счетами. Они не уменьшают задолженность автоматически.',
            'Сверьте плательщика и назначение платежа в разделе «Финансы».',
            [{'source': 'bank_ledger', 'reference': r['reference'], 'amount': r['amount']-r['allocated_amount']-r['returned_amount']} for r in data['bank'] if r['amount']>r['allocated_amount']+r['returned_amount']]))
    for cp_id, row in latest.items():
        if not invoice_counts.get(cp_id, 0) and row['source_balance'] > 0:
            global_findings.append(finding('aggregate_without_documents', 'attention', 'Сальдо без документов обязательства',
                f"{cps[cp_id]['name']}: в принятом источнике есть дебетовое сальдо, но нет счетов в реестре.",
                'Загрузите расшифровку по документам и проверьте первичку. Не создавайте счёт из общего сальдо.',
                [{'source': 'accounting', 'reference': row['source_ref'], 'as_of': row['as_of'], 'amount': row['source_balance']}]))
        elif invoice_counts.get(cp_id, 0) and row['current_discrepancy'] != 0 and balances.get(cp_id, 0) == 0:
            global_findings.append(finding('accounting_discrepancy', 'attention', 'Сверить остаток источника с закрытыми счетами',
                f"{cps[cp_id]['name']}: счета присутствуют в реестре и текущий остаток равен нулю; остаток принятого источника отличается.",
                'Проверьте дату источника и последующие оплаты, возвраты и зачёты. Не создавайте повторные счета из общего сальдо.',
                [{'source': 'accounting', 'reference': row['source_ref'], 'as_of': row['as_of'],
                  'source_balance': row['source_balance'], 'current_discrepancy': row['current_discrepancy']}]))
    order = {'urgent': 0, 'attention': 1, 'review': 2, 'clear': 3}
    items.sort(key=lambda x: (order[x['severity']], -x['balance'], x['invoice_id']))
    return dict(as_of=data['as_of'], method='evidence_rules_v1', items=items, findings=global_findings,
        totals=dict(invoice_count=len(items), counterparty_count=len(cps), outstanding=sum(x['balance'] for x in items),
            overdue=sum(x['balance'] for x in items if x['days_overdue']), unallocated_cash=unallocated,
            urgent_count=sum(x['severity']=='urgent' for x in items),
            discrepancies=sum(r['current_discrepancy']!=0 for r in latest.values()),
            missing_documents=sum(bool({'contract','performance','payment_terms'}-set(x['documents'])) for x in items if x['balance']>0),
            unchecked_debtors=len({x['counterparty_id'] for x in items if x['balance']>0 and not(x['registry']['status']=='completed' and x['registry']['fresh'])})),
        limitations=['Остатки отражают текущее состояние реестра. Источник ОСВ сохраняет собственную дату.',
            'Реквизиты документов зарегистрированы сотрудником; их подлинность и правовую силу проверяет специалист.',
            'План действий не является прогнозом собираемости или юридическим заключением.'])


def create_router(ctx):
    router = APIRouter(prefix='/api/portfolio', tags=['portfolio'])

    def load(connection, tenant, run_id):
        row = connection.execute('SELECT * FROM portfolio_runs WHERE id=? AND tenant_id=?', (run_id, tenant)).fetchone()
        if row is None: ctx.problem(404, 'Аудит не найден')
        return dict(row)

    def view(row): return {**json.loads(row['report_json']), 'id': row['id'], 'created_at': row['created_at'], 'snapshot_hash': row['snapshot_hash']}

    @router.get('')
    def latest(user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as c:
            row = c.execute('SELECT * FROM portfolio_runs WHERE tenant_id=? ORDER BY created_at DESC,id DESC LIMIT 1', (user['tenant_id'],)).fetchone()
            return {'latest': None, 'stale': False} if row is None else {**view(row), 'latest': row['id'], 'stale': row['snapshot_hash'] != snapshot(inputs(c, user['tenant_id']))}

    @router.post('/runs', status_code=201)
    def create(data: AuditInput, user=Depends(ctx.get_user)):
        with ctx.database(ctx.config, write=True) as c:
            source = inputs(c, user['tenant_id'])
            report = build_report(c, user['tenant_id'], source)
            key, timestamp = ctx.identifier(), ctx.now()
            c.execute('INSERT INTO portfolio_runs VALUES(?,?,?,?,?,?)', (key, user['tenant_id'], snapshot(source), encoded(report), timestamp, user['id']))
            return {**report, 'id': key, 'created_at': timestamp, 'snapshot_hash': snapshot(source), 'stale': False}

    @router.get('/runs')
    def history(user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as c:
            return {'items': [{'id': r['id'], 'created_at': r['created_at'], 'totals': json.loads(r['report_json'])['totals']}
                for r in c.execute('SELECT * FROM portfolio_runs WHERE tenant_id=? ORDER BY created_at DESC,id DESC LIMIT 50', (user['tenant_id'],))]}

    @router.get('/runs/{run_id}')
    def detail(run_id: str, user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as c: return view(load(c, user['tenant_id'], run_id))

    @router.get('/runs/{run_id}/export')
    def export(run_id: str, user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as c: report = view(load(c, user['tenant_id'], run_id))
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=';')
        writer.writerow(['Контрагент', 'ИНН', 'Счёт', 'Остаток, руб.', 'Срок', 'Следующее действие', 'Наблюдения', 'Дата аудита'])
        def safe(v):
            text = str(v)
            return "'"+text if text.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else text
        for item in report['items']:
            writer.writerow([safe(item['company']), safe(item['inn']), safe(item['number']), f"{item['balance']//100},{item['balance']%100:02}", item['due_on'],
                safe(item['next_action']['title']), safe(' · '.join(f['title'] for f in item['findings'])), report['as_of']])
        return Response('\ufeff'+buffer.getvalue(), media_type='text/csv; charset=utf-8', headers={'Content-Disposition': 'attachment; filename="mandato-audit.csv"'})

    @router.get('/documents')
    def document_archive(invoice_id: str = '', user=Depends(ctx.get_user)):
        tenant = user['tenant_id']
        with ctx.database(ctx.config) as c:
            if invoice_id:
                finance.load_invoice(c, tenant, invoice_id)
            items = []
            for row in c.execute('SELECT id,invoice_id,kind,reference,occurred_on,note,filename,sha256,created_at FROM portfolio_evidence WHERE tenant_id=? ORDER BY created_at DESC', (tenant,)):
                items.append(evidence_view(row) | {'source': 'Первичный документ'})
            for table, source in [('legal_documents', 'Юридический документ'), ('legal_evidence', 'Доказательство')]:
                fields = 'd.id,d.case_id,d.kind,d.created_at,l.invoice_id'
                fields += ',d.version' if table == 'legal_documents' else ',d.title,d.reference,d.occurred_on'
                for row in c.execute(f'SELECT {fields} FROM {table} d JOIN legal_cases l ON l.id=d.case_id AND l.tenant_id=d.tenant_id WHERE d.tenant_id=?', (tenant,)):
                    item = dict(row) | {'source': source}
                    parent=c.execute('SELECT * FROM legal_cases WHERE id=? AND tenant_id=?',(row['case_id'],tenant)).fetchone()
                    if table=='legal_documents':item['invoice_ids']=legal.case_invoice_ids(c,parent)
                    else:item['invoice_ids']=[r['invoice_id'] for r in c.execute('SELECT invoice_id FROM legal_evidence_invoices WHERE tenant_id=? AND evidence_id=?',(tenant,row['id']))] or [parent['invoice_id']]
                    if table == 'legal_documents':
                        names = {'pretrial_claim': 'Претензия', 'court_order': 'Судебный приказ', 'statement_of_claim': 'Иск'}
                        item.update(reference=f"{names.get(row['kind'], row['kind'])} · версия {row['version']}", occurred_on=row['created_at'][:10], download_url=f"/api/legal/documents/{row['id']}/download")
                    items.append(item)
            for row in c.execute("SELECT id,invoice_id,payload_json,created_at FROM yandex_service_requests WHERE tenant_id=? AND kind='ocr'", (tenant,)):
                payload = json.loads(row['payload_json'])
                items.append(dict(row) | {'source': 'Распознавание', 'kind': 'other', 'reference': payload.get('filename', 'Распознанный документ'), 'occurred_on': row['created_at'][:10], 'download_url': f"/api/yandex/documents/{row['id']}/original"})
            items = [item for item in items if not invoice_id or invoice_id in item.get('invoice_ids',[item['invoice_id']])]
            for item in items:
                item.pop('payload_json', None)
            return {'items': sorted(items, key=lambda item: (item['created_at'], item['id']), reverse=True)}

    @router.get('/invoices/{invoice_id}/evidence')
    def evidence(invoice_id: str, user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as c:
            finance.load_invoice(c, user['tenant_id'], invoice_id)
            return {'items': [evidence_view(r) for r in c.execute('SELECT * FROM portfolio_evidence WHERE invoice_id=? AND tenant_id=? ORDER BY created_at DESC,id', (invoice_id, user['tenant_id']))]}

    def evidence_view(r):
        value = {key: r[key] for key in ('id', 'invoice_id', 'kind', 'reference', 'occurred_on', 'note', 'filename', 'sha256', 'created_at')}
        value['download_url'] = f"/api/portfolio/evidence/{r['id']}/download" if r['filename'] else None
        return value

    @router.post('/invoices/{invoice_id}/evidence', status_code=201)
    def add_evidence(invoice_id: str, data: EvidenceInput, user=Depends(ctx.get_user)):
        content, digest = b'', ''
        if bool(data.filename) != bool(data.content_base64): ctx.problem(422, 'Укажите и файл, и его название')
        if data.content_base64:
            try: content = base64.b64decode(data.content_base64, validate=True)
            except (ValueError, binascii.Error): ctx.problem(422, 'Не удалось прочитать файл')
            if len(content)>1_000_000: ctx.problem(422, 'Документ должен быть не больше 1 МБ')
            name = data.filename.casefold()
            valid = (name.endswith('.pdf') and content.startswith(b'%PDF-')) or (name.endswith('.png') and content.startswith(b'\x89PNG\r\n\x1a\n')) or (name.endswith(('.jpg','.jpeg')) and content.startswith(b'\xff\xd8\xff'))
            if not valid: ctx.problem(422, 'Допустимы PDF, PNG и JPEG с соответствующим содержимым')
            if any(s in data.filename for s in ('/', '\\', '..')): ctx.problem(422, 'Недопустимое название файла')
            digest = hashlib.sha256(content).hexdigest()
        with ctx.database(ctx.config, write=True) as c:
            finance.load_invoice(c, user['tenant_id'], invoice_id)
            key = ctx.identifier()
            c.execute('INSERT INTO portfolio_evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', (key,user['tenant_id'],invoice_id,data.kind,data.reference,str(data.occurred_on),data.note,data.filename,data.content_base64,digest,ctx.now(),user['id']))
            ctx.event(c,user['tenant_id'],invoice_id,'portfolio_evidence','Зарегистрирован документ',data.reference)
            row=c.execute('SELECT * FROM portfolio_evidence WHERE id=? AND tenant_id=?',(key,user['tenant_id'])).fetchone()
            return evidence_view(row)

    @router.get('/evidence/{evidence_id}/download')
    def download(evidence_id: str, user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as c: row=c.execute('SELECT * FROM portfolio_evidence WHERE id=? AND tenant_id=?',(evidence_id,user['tenant_id'])).fetchone()
        if row is None or not row['filename']: ctx.problem(404,'Документ не найден')
        content=base64.b64decode(row['content_base64'])
        if hashlib.sha256(content).hexdigest()!=row['sha256']: ctx.problem(409,'Контрольная сумма документа не совпадает')
        return Response(content,media_type='application/octet-stream',headers={'Content-Disposition':f'attachment; filename="mandato-evidence-{evidence_id}"','Cache-Control':'private, no-store'})

    @router.post('/invoices/{invoice_id}/deadlines', status_code=201)
    def deadline(invoice_id: str, data: DeadlineInput, user=Depends(ctx.get_user)):
        with ctx.database(ctx.config,write=True) as c:
            finance.load_invoice(c,user['tenant_id'],invoice_id)
            key, timestamp=ctx.identifier(),ctx.now()
            c.execute('INSERT INTO portfolio_deadlines VALUES(?,?,?,?,?,?,?,?)',(key,user['tenant_id'],invoice_id,data.kind,str(data.review_on),data.basis,timestamp,user['id']))
            ctx.event(c,user['tenant_id'],invoice_id,'portfolio_deadline','Назначен срок проверки',data.basis)
            return {'id':key,**data.model_dump(mode='json'),'created_at':timestamp}

    @router.post('/deadlines/{deadline_id}/resolve')
    def resolve(deadline_id: str, data: ResolveInput, user=Depends(ctx.get_user)):
        with ctx.database(ctx.config,write=True) as c:
            row=c.execute('SELECT * FROM portfolio_deadlines WHERE id=? AND tenant_id=?',(deadline_id,user['tenant_id'])).fetchone()
            if row is None: ctx.problem(404,'Контрольная дата не найдена')
            prior=c.execute('SELECT * FROM portfolio_deadline_resolutions WHERE deadline_id=? AND tenant_id=?',(deadline_id,user['tenant_id'])).fetchone()
            if prior:
                if prior['reason']!=data.reason: ctx.problem(409,'Результат проверки уже зарегистрирован с другим основанием')
                return {'id':deadline_id,'resolved_at':prior['resolved_at'],'reason':prior['reason']}
            stamp=ctx.now()
            c.execute('INSERT INTO portfolio_deadline_resolutions VALUES(?,?,?,?,?)',(deadline_id,user['tenant_id'],data.reason,stamp,user['id']))
            ctx.event(c,user['tenant_id'],row['invoice_id'],'portfolio_deadline_resolved','Завершена проверка',data.reason)
            return {'id':deadline_id,'resolved_at':stamp,'reason':data.reason}

    return router
