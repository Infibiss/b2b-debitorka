"""Portfolio analytics, court and enforcement registers, report builder and own templates.

All figures come from the invoice ledger and recorded payments; nothing is estimated
by a model. Amounts are integer kopeks.
"""
from __future__ import annotations

import csv
import io
from datetime import date
from typing import Annotated, Literal

from fastapi import Depends, Query
from fastapi.responses import Response
from pydantic import Field, StrictInt, field_validator

from . import finance as f
from . import recovery_rules as rules
from . import recovery_templates as templates
from .models import Input

AGING = (('not_due', 'Срок не наступил', None, 0), ('d30', '1–30 дней', 1, 30), ('d60', '31–60 дней', 31, 60),
         ('d90', '61–90 дней', 61, 90), ('d180', '91–180 дней', 91, 180), ('d180p', 'Больше 180 дней', 181, None))
REGISTER_KINDS = ('court_event', 'enforcement_case', 'bank_account', 'fns_request', 'measure')
Line = Annotated[str, Field(max_length=300)]


def bucket(days):
    for key, _, low, high in AGING:
        if low is None:
            if days <= 0:
                return key
        elif days >= low and (high is None or days <= high):
            return key
    return 'not_due'


def month_keys(today, count=12):
    year, month, keys = today.year, today.month, []
    for _ in range(count):
        keys.append(f'{year:04d}-{month:02d}')
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return list(reversed(keys))


def aging_rows(debtors):
    totals = {key: dict(key=key, label=label, count=0, amount=0) for key, label, _, _ in AGING}
    for debtor in debtors:
        for invoice in debtor['_invoices']:
            if invoice['balance'] > 0:
                row = totals[bucket(invoice['days_overdue'])]
                row['count'] += 1
                row['amount'] += invoice['balance']
    return list(totals.values())


def collected_by_month(connection, tenant, today):
    keys = month_keys(today)
    totals = dict.fromkeys(keys, 0)
    for row in connection.execute('SELECT * FROM payments WHERE tenant_id=?', (tenant,)):
        item = dict(row)
        month = str(item.get('paid_on') or item.get('received_on') or item.get('created_at') or '')[:7]
        if month in totals:
            totals[month] += item['amount'] - (item.get('reversed_amount') or 0)
    return [dict(month=key, amount=totals[key]) for key in keys]


def analytics(connection, tenant, debtors, today):
    """The owner's picture of the portfolio: where the money is and what blocks it."""
    active = [item for item in debtors if item['stage'] != rules.CLOSED]
    monthly = collected_by_month(connection, tenant, today)
    collected_total = connection.execute('SELECT COALESCE(SUM(amount-reversed_amount),0) AS amount FROM payments WHERE tenant_id=?', (tenant,)).fetchone()['amount']
    open_total = sum(item['balance'] for item in active)
    promised_soon = 0
    for item in active:
        promise = item['promise_date']
        if item['status'] == 'promise' and promise and 0 <= (date.fromisoformat(promise) - today).days <= 30:
            promised_soon += item['_state'].get('promise_amount') or item['balance']
    limitation = [deadline for item in active for deadline in rules.deadlines(item['_state'], item['oldest_due_on'], today) if deadline['key'] == 'limitation' and deadline['days_left'] <= 90]
    attention = [
        dict(key='promise_broken', label='Нарушили обещание', count=sum(item['status'] == 'promise_broken' for item in active), target='debtors:pretrial'),
        dict(key='dispute', label='Спорят с долгом', count=sum(item['status'] == 'dispute' for item in active), target='debtors:pretrial'),
        dict(key='ready', label='Можно идти в суд', count=sum(item['status'] == 'ready_for_court' for item in active), target='debtors:pretrial'),
        dict(key='duty', label='Ждут оплаты пошлины', count=sum(item['status'] == 'duty_pending' for item in active), target='debtors:court'),
        dict(key='documents', label='Не хватает документов', count=sum(item['evidence_score'] < 100 for item in active), target='debtors:pretrial'),
        dict(key='limitation', label='Давность истекает за 90 дней', count=len(limitation), target='debtors:pretrial'),
    ]
    statuses = {}
    for item in active:
        row = statuses.setdefault(item['status'], dict(status=item['status'], label=item['status_label'], stage=item['stage'], count=0, amount=0))
        row['count'] += 1
        row['amount'] += item['balance']
    top = sorted(active, key=lambda item: -item['balance'])[:5]
    return dict(
        aging=aging_rows(active), monthly=monthly, collected_total=collected_total, open_total=open_total,
        recovery_percent=round(100 * collected_total / (collected_total + open_total), 1) if collected_total + open_total else 0,
        collected_this_month=monthly[-1]['amount'], collected_last_month=monthly[-2]['amount'],
        promised_30_days=promised_soon, average_overdue_days=round(sum(item['days_overdue'] for item in active) / len(active)) if active else 0,
        attention=attention, statuses=sorted(statuses.values(), key=lambda row: -row['amount'])[:8],
        top=[dict(id=item['id'], name=item['name'], balance=item['balance'], status_label=item['status_label'], days_overdue=item['days_overdue']) for item in top],
    )


COLUMNS = {
    'name': ('Должник', lambda item: item['name']), 'inn': ('ИНН', lambda item: item['inn']), 'stage': ('Этап', lambda item: item['stage']),
    'status': ('Статус', lambda item: item['status_label']), 'custom_status': ('Мой статус', lambda item: item['custom_status']),
    'balance': ('Остаток, ₽', lambda item: f.money(item['balance'])), 'overdue': ('Просрочено, ₽', lambda item: f.money(item['overdue_amount'])),
    'days': ('Просрочка, дней', lambda item: item['days_overdue']), 'invoices': ('Открытых счетов', lambda item: item['open_invoice_count']),
    'evidence': ('Документы, %', lambda item: item['evidence_score']), 'assignee': ('Ответственный', lambda item: item['assignee_id'] or ''),
    'contract': ('Договор', lambda item: item['contract']), 'case': ('Номер дела', lambda item: item['case_number']), 'court': ('Суд', lambda item: item['court_name']),
    'writ': ('Исполнительный документ', lambda item: item['writ_number']), 'duty': ('Госпошлина, ₽', lambda item: f.money(item['duty_amount'] or 0)),
    'phone': ('Телефон', lambda item: item['phone']), 'email': ('Почта', lambda item: item['email']),
}


def csv_response(rows, filename):
    output = io.StringIO()
    csv.writer(output, delimiter=';').writerows(rows)
    return Response('﻿' + output.getvalue(), media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename="{filename}"', 'Cache-Control': 'private, no-store'})


class RegisterInput(Input):
    kind: Literal[REGISTER_KINDS]  # type: ignore[valid-type]
    on_date: date
    title: Line = Field(min_length=1)
    reference: Line = ''
    amount: Annotated[StrictInt, Field(ge=0, le=1_000_000_000_000_000)] | None = None
    status: Line = ''
    note: Annotated[str, Field(max_length=2000)] = ''


class CustomTemplateInput(Input):
    title: Line = Field(min_length=3)
    stage: Literal['pretrial', 'court', 'enforcement']
    heading: Line = Field(min_length=3)
    address: Annotated[str, Field(max_length=2000)] = ''
    body: str = Field(min_length=20, max_length=20000)

    @field_validator('body', 'address', 'heading')
    @classmethod
    def known_variables(cls, value):
        unknown = templates.unknown_variables(value)
        if unknown:
            raise ValueError('Неизвестные переменные: ' + ', '.join(unknown))
        return value


def add_routes(router, ctx):
    from . import recovery_dashboards, recovery_recognition
    from .recovery import all_debtors, csv_safe, debtor_rows
    recovery_dashboards.add_routes(router, ctx)
    recovery_recognition.add_routes(router, ctx)

    def manager(user):
        if user['role'] != 'manager':
            ctx.problem(403, 'Это решение принимает руководитель')

    @router.get('/report/columns')
    def report_columns(user=Depends(ctx.get_user)):
        return dict(items=[dict(key=key, label=value[0]) for key, value in COLUMNS.items()], aging=[dict(key=row[0], label=row[1]) for row in AGING])

    @router.get('/report/build.csv')
    def report_build(columns: str = Query('name,inn,stage,status,balance,days', max_length=500), stage: str = Query('', max_length=20),
                     min_days: int = Query(0, ge=0), archived: bool = False, user=Depends(ctx.get_user)):
        keys = [key for key in columns.split(',') if key in COLUMNS] or ['name', 'balance']
        with ctx.database(ctx.config) as c:
            debtors = all_debtors(c, user['tenant_id'])
        chosen = [item for item in debtors if (not stage or item['stage'] == stage) and item['days_overdue'] >= min_days and item['archived'] == archived]
        rows = [[COLUMNS[key][0] for key in keys]] + [[csv_safe(COLUMNS[key][1](item)) for key in keys] for item in chosen]
        return csv_response(rows, 'mandato-report.csv')

    @router.get('/report/aging.csv')
    def report_aging(user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as c:
            debtors = [item for item in all_debtors(c, user['tenant_id']) if item['stage'] != rules.CLOSED and not item['archived']]
        rows = [['Просрочка', 'Счетов', 'Сумма, ₽']] + [[row['label'], row['count'], f.money(row['amount'])] for row in aging_rows(debtors)]
        return csv_response(rows, 'mandato-aging.csv')

    @router.get('/duty-register.csv')
    def duty_register(user=Depends(ctx.get_user)):
        """Payment list for the accountant: every debtor waiting for the state fee."""
        with ctx.database(ctx.config) as c:
            debtors = [item for item in all_debtors(c, user['tenant_id']) if item['status'] == 'duty_pending' and not item['archived']]
        rows = [['Должник', 'ИНН', 'Суд', 'Цена требования, ₽', 'Госпошлина, ₽', 'Назначение платежа']]
        for item in debtors:
            rows.append([csv_safe(item['name']), csv_safe(item['inn']), csv_safe(item['court_name']), f.money(item['_state'].get('claim_amount') or item['balance']), f.money(item['duty_amount'] or 0),
                         csv_safe('Госпошлина, должник ' + item['name'])])
        return csv_response(rows, 'mandato-duty-register.csv')

    @router.post('/debtors/{debtor_id}/register', status_code=201)
    def register_add(debtor_id: str, data: RegisterInput, user=Depends(ctx.get_user)):
        tenant = user['tenant_id']
        with ctx.database(ctx.config, write=True) as c:
            if debtor_id not in debtor_rows(c, tenant):
                ctx.problem(404, 'Должник не найден')
            key = f.uid()
            c.execute('INSERT INTO recovery_register VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                      (key, tenant, debtor_id, data.kind, str(data.on_date), data.title, data.reference, data.amount, data.status, data.note, user['id'], ctx.now()))
        return dict(id=key)

    @router.delete('/register/{entry_id}')
    def register_delete(entry_id: str, user=Depends(ctx.get_user)):
        with ctx.database(ctx.config, write=True) as c:
            c.execute('DELETE FROM recovery_register WHERE id=? AND tenant_id=?', (entry_id, user['tenant_id']))
        return dict(ok=True)

    @router.get('/custom-templates')
    def custom_list(user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as c:
            return dict(items=[dict(row) for row in c.execute('SELECT id,title,stage,heading,address,body FROM recovery_custom_templates WHERE tenant_id=? ORDER BY title', (user['tenant_id'],))])

    @router.post('/custom-templates', status_code=201)
    def custom_add(data: CustomTemplateInput, user=Depends(ctx.get_user)):
        manager(user)
        key = f.uid()
        with ctx.database(ctx.config, write=True) as c:
            c.execute('INSERT INTO recovery_custom_templates VALUES(?,?,?,?,?,?,?,?,?)', (key, user['tenant_id'], data.title, data.stage, data.heading, data.address, data.body, user['id'], ctx.now()))
        return dict(id=key)

    @router.put('/custom-templates/{key}')
    def custom_save(key: str, data: CustomTemplateInput, user=Depends(ctx.get_user)):
        manager(user)
        with ctx.database(ctx.config, write=True) as c:
            c.execute('UPDATE recovery_custom_templates SET title=?,stage=?,heading=?,address=?,body=?,updated_by=?,updated_at=? WHERE id=? AND tenant_id=?',
                      (data.title, data.stage, data.heading, data.address, data.body, user['id'], ctx.now(), key, user['tenant_id']))
        return dict(id=key)

    @router.delete('/custom-templates/{key}')
    def custom_delete(key: str, user=Depends(ctx.get_user)):
        manager(user)
        with ctx.database(ctx.config, write=True) as c:
            c.execute('DELETE FROM recovery_custom_templates WHERE id=? AND tenant_id=?', (key, user['tenant_id']))
        return dict(ok=True)
