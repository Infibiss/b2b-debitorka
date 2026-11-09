"""Reads court acts and payment orders from PDF and proposes the matching step.

Extraction is deterministic and nothing changes until a person confirms it: the
result is a proposal with the fields, the debtor and the status step side by side.
"""
from __future__ import annotations

import base64
import binascii
import io
import json
import re
from datetime import date
from typing import Annotated

from fastapi import Depends
from fastapi.responses import Response
from pydantic import Field

from . import finance as f
from . import recovery_rules as rules
from .models import Input

MAX_PDF_BYTES = 8_000_000
MAX_BODY_BYTES = 11_000_000
UPLOAD_PATH = '/api/recovery/recognitions'
MAX_OCR_PAGES = 10
MIN_TEXT = 60
MONTHS = dict(января=1, февраля=2, марта=3, апреля=4, мая=5, июня=6, июля=7, августа=8, сентября=9, октября=10, ноября=11, декабря=12)
KIND_LABELS = {
    'payment_order': 'Платёжное поручение', 'order_cancel': 'Определение об отмене приказа', 'court_order': 'Судебный приказ',
    'return': 'Определение о возвращении', 'without_motion': 'Определение об оставлении без движения', 'refusal': 'Отказ в принятии заявления',
    'acceptance': 'Определение о принятии иска', 'decision': 'Решение суда', 'writ': 'Исполнительный лист', 'unknown': 'Документ не определён',
}
SCHEMA = '''
CREATE TABLE IF NOT EXISTS recovery_recognitions (
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id), filename TEXT NOT NULL, content_base64 TEXT NOT NULL,
 kind TEXT NOT NULL, fields_json TEXT NOT NULL, debtor_id TEXT, action TEXT, status TEXT NOT NULL DEFAULT 'pending', source TEXT NOT NULL,
 created_by TEXT NOT NULL, created_at TEXT NOT NULL, applied_at TEXT
);
CREATE INDEX IF NOT EXISTS recovery_recognitions_tenant ON recovery_recognitions(tenant_id,status,created_at);
'''


def compact(text):
    return re.sub(r'[ \t ]+', ' ', text or '')


def classify(text):
    low = compact(text).lower()
    if 'платежное поручение' in low or 'платёжное поручение' in low:
        return 'payment_order'
    if re.search(r'об?\s+отмене\s+судебного\s+приказа', low):
        return 'order_cancel'
    if re.search(r'исполнительный\s+лист\b', low[:600]):
        return 'writ'
    if re.search(r'судебный\s+приказ\b', low[:900]):
        return 'court_order'
    if re.search(r'об?\s+отказе\s+в\s+принятии', low):
        return 'refusal'
    if re.search(r'о\s+возвращении\s+(искового\s+)?заявления', low):
        return 'return'
    if re.search(r'без\s+движения', low):
        return 'without_motion'
    if re.search(r'о\s+принятии\s+искового\s+заявления', low):
        return 'acceptance'
    if re.search(r'р\s*е\s*ш\s*е\s*н\s*и\s*е', low[:1200]) or 'именем российской федерации' in low:
        return 'decision'
    return 'unknown'


def first_date(text):
    match = re.search(r'[«"]?(\d{1,2})[»"]?\s+(' + '|'.join(MONTHS) + r')\s+(\d{4})', text, re.I)
    if match:
        return _iso(int(match[3]), MONTHS[match[2].lower()], int(match[1]))
    match = re.search(r'\b(\d{2})\.(\d{2})\.(\d{4})\b', text)
    return _iso(int(match[3]), int(match[2]), int(match[1])) if match else ''


def _iso(year, month, day):
    try:
        return str(date(year, month, day))
    except ValueError:
        return ''


def kopeks(value):
    digits = re.match(r'^(\d+)(?:[.,-](\d{1,2}))?$', re.sub(r'[\s ]', '', value or ''))
    return int(digits[1]) * 100 + int((digits[2] or '0').ljust(2, '0')) if digits else None


def case_number(text):
    match = re.search(r'\b([АA])\s?(\d{1,3})\s?[-–]\s?(\d{1,7})\s?/\s?(\d{4})\b', text)
    return f'А{match[2]}-{match[3]}/{match[4]}' if match else ''


def extract_fields(text, kind):
    body = compact(text)
    fields = dict(case_number=case_number(body), act_on=first_date(body), inns=sorted(set(re.findall(r'ИНН[:\s№]*(\d{12}|\d{10})\b', body))), amount=None, reference='', court='', purpose='')
    court = re.search(r'Арбитражн\w+ суд\w*[^\n,.;]{0,70}', body)
    fields['court'] = court[0].strip() if court else ''
    if kind == 'payment_order':
        number = re.search(r'поручение\s*(?:№|N)\s*(\d{1,10})', body, re.I)
        amount = re.search(r'Сумма\s*:?\s*(\d[\d\s ]*(?:[.,-]\d{2})?)', body)
        purpose = re.search(r'Назначение\s+платежа\s*:?\s*([^\n]{5,210})', body, re.I)
        fields['reference'] = number[1] if number else ''
        fields['amount'] = kopeks(amount[1].strip()) if amount else None
        fields['purpose'] = purpose[1].strip() if purpose else ''
    else:
        amount = re.search(r'(\d[\d\s ]{0,16}(?:[.,]\d{2})?)\s*(?:руб|₽)', body)
        fields['amount'] = kopeks(amount[1].strip()) if amount else None
        fields['reference'] = fields['case_number']
    return fields


def match_debtor(fields, debtors):
    """Case number is decisive; a tax number counts only when it points to one debtor."""
    if fields['case_number']:
        for item in debtors:
            if item['case_number'] and case_number(item['case_number']) == fields['case_number']:
                return item
    found = [item for item in debtors if item['inn'] and item['inn'] in fields['inns']]
    return found[0] if len(found) == 1 else None


def suggest_action(kind, status, text='', amount=None, duty=None, purpose=''):
    """The step a document supports in the debtor's current status, or None."""
    low = compact(text).lower()
    if kind == 'payment_order':
        fee = 'пошлин' in (purpose or low)
        return 'duty_paid' if status == 'duty_pending' and fee and (not amount or not duty or amount == duty) else None
    if kind == 'decision':
        if status != 'hearing':
            return None
        return 'decision_lost' if re.search(r'в\s+(иске|удовлетворении[^.]{0,40})\s*отказать|отказать\s+в\s+удовлетворении', low) else 'decision_won'
    table = {'court_order': ('filed', 'order_issued'), 'order_cancel': ('order_issued', 'order_cancelled'), 'acceptance': ('filed', 'accepted'), 'writ': ('writ_requested', 'writ_received')}
    if kind in table:
        return table[kind][1] if status == table[kind][0] else None
    if kind == 'without_motion':
        return 'without_motion' if status in ('filed', 'hearing') else None
    if kind in ('return', 'refusal'):
        return 'court_returned' if status in ('filed', 'without_motion') else None
    return None


def pdf_text(raw):
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(raw))
    if reader.is_encrypted:
        raise ValueError('encrypted')
    return '\n'.join(page.extract_text() or '' for page in reader.pages[:40])


def ocr_text(raw, tenant):
    """Scans go to the client's connected OCR; without one the document stays unread."""
    from . import yandex_services as ocr
    if not ocr._configured(tenant, 'ocr'):
        return None
    parts = []
    for page in ocr._pages(raw, 'application/pdf')[:MAX_OCR_PAGES]:
        response = ocr._request('ocr', {'content': base64.b64encode(page).decode(), 'mimeType': 'PDF', 'languageCodes': ['ru', 'en'], 'model': 'page'})
        envelope = response.get('result', response) if isinstance(response, dict) else {}
        parts.append(str((envelope.get('textAnnotation') or {}).get('fullText') or ''))
    return '\n'.join(parts)


class Upload(Input):
    filename: str = Field(min_length=1, max_length=180)
    content: str = Field(min_length=8, max_length=MAX_BODY_BYTES)


class Apply(Input):
    debtor_id: str = Field(min_length=1, max_length=100)
    action: Annotated[str, Field(max_length=40)] = ''
    case_number: Annotated[str, Field(max_length=60)] = ''
    act_on: date | None = None
    reference: Annotated[str, Field(max_length=120)] = ''
    note: Annotated[str, Field(max_length=500)] = ''


def view(row):
    data = dict(row)
    data.pop('content_base64', None)
    data['fields'] = json.loads(data.pop('fields_json'))
    data['kind_label'] = KIND_LABELS[data['kind']]
    return data


def add_routes(router, ctx):
    from .recovery import ActionInput, all_debtors, apply_action

    @router.get('/recognitions')
    def recognition_list(user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as c:
            rows = c.execute("SELECT * FROM recovery_recognitions WHERE tenant_id=? AND status='pending' ORDER BY created_at DESC LIMIT 100", (user['tenant_id'],)).fetchall()
        return dict(items=[view(row) for row in rows], action_labels=rules.ACTION_LABELS)

    @router.post('/recognitions', status_code=201)
    def recognition_add(data: Upload, user=Depends(ctx.get_user)):
        try:
            raw = base64.b64decode(data.content, validate=True)
        except (binascii.Error, ValueError):
            ctx.problem(422, 'Файл повреждён')
        if not raw.startswith(b'%PDF-'):
            ctx.problem(422, 'Загрузите файл в формате PDF')
        if len(raw) > MAX_PDF_BYTES:
            ctx.problem(413, 'PDF больше 8 МБ')
        source = 'text'
        try:
            text = pdf_text(raw)
        except Exception:  # A malformed PDF must never surface a parser trace to the client.
            ctx.problem(422, 'Не удалось открыть PDF. Проверьте, что файл не защищён паролем')
        if len(text.strip()) < MIN_TEXT:
            source = 'ocr'
            try:
                text = ocr_text(raw, user['tenant_id'])
            except Exception:
                text = None
            if text is None or len(text.strip()) < MIN_TEXT:
                ctx.problem(422, 'Это скан без текста. Для сканов подключите распознавание в настройках')
        kind = classify(text)
        fields = extract_fields(text, kind)
        tenant = user['tenant_id']
        with ctx.database(ctx.config, write=True) as c:
            debtors = [item for item in all_debtors(c, tenant) if not item['archived']]
            debtor = match_debtor(fields, debtors)
            action = suggest_action(kind, debtor['status'], text, fields['amount'], debtor['duty_amount'], fields['purpose']) if debtor else None
            key = f.uid()
            c.execute('INSERT INTO recovery_recognitions(id,tenant_id,filename,content_base64,kind,fields_json,debtor_id,action,status,source,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                      (key, tenant, data.filename[:180], data.content, kind, json.dumps(fields, ensure_ascii=False), debtor['id'] if debtor else None, action, 'pending', source, user['id'], ctx.now()))
            row = c.execute('SELECT * FROM recovery_recognitions WHERE id=?', (key,)).fetchone()
        return view(row)

    @router.get('/recognitions/{key}/file')
    def recognition_file(key: str, user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as c:
            row = c.execute('SELECT content_base64 FROM recovery_recognitions WHERE id=? AND tenant_id=?', (key, user['tenant_id'])).fetchone()
        if not row:
            ctx.problem(404, 'Документ не найден')
        return Response(base64.b64decode(row['content_base64']), media_type='application/pdf', headers={'Content-Disposition': 'attachment; filename="document.pdf"', 'Cache-Control': 'private, no-store'})

    @router.delete('/recognitions/{key}')
    def recognition_delete(key: str, user=Depends(ctx.get_user)):
        with ctx.database(ctx.config, write=True) as c:
            c.execute("DELETE FROM recovery_recognitions WHERE id=? AND tenant_id=? AND status='pending'", (key, user['tenant_id']))
        return dict(ok=True)

    @router.post('/recognitions/{key}/apply')
    def recognition_apply(key: str, data: Apply, user=Depends(ctx.get_user)):
        tenant = user['tenant_id']
        with ctx.database(ctx.config, write=True) as c:
            row = c.execute("SELECT * FROM recovery_recognitions WHERE id=? AND tenant_id=? AND status='pending'", (key, tenant)).fetchone()
            if not row:
                ctx.problem(404, 'Документ не найден')
            if not any(item['id'] == data.debtor_id for item in all_debtors(c, tenant)):
                ctx.problem(404, 'Должник не найден')
            fields = json.loads(row['fields_json'])
            on_date = data.act_on or date.today()
            if data.action:
                if data.action not in rules.ACTIONS:
                    ctx.problem(422, 'Неизвестное действие')
                note = data.note or KIND_LABELS[row['kind']]
                sent = dict(action=data.action, note=note, reference=data.reference or fields.get('reference') or row['filename'][:100], case_number=data.case_number, act_on=on_date)
                sent = {name: value for name, value in sent.items() if name == 'action' or name in rules.ACTIONS[data.action][3] or name == 'note'}
                apply_action(c, tenant, data.debtor_id, ActionInput(**sent), user['id'], user['name'], user['role'])
            c.execute('INSERT INTO recovery_register VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                      (f.uid(), tenant, data.debtor_id, 'court_event', str(on_date), KIND_LABELS[row['kind']], data.case_number or data.reference, fields.get('amount'), '', row['filename'][:200], user['id'], ctx.now()))
            c.execute("UPDATE recovery_recognitions SET status='applied',debtor_id=?,action=?,applied_at=? WHERE id=?", (data.debtor_id, data.action or None, ctx.now(), key))
        return dict(ok=True)
