"""Client-built dashboards and reports e-mailed on a schedule."""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Annotated, Literal

from fastapi import Depends
from pydantic import Field, StrictBool, StrictInt, model_validator

from . import finance as f
from . import recovery_rules as rules
from .business_time import business_today
from .models import Input
from .recovery_ops import AGING, COLUMNS, aging_rows, collected_by_month, csv_response, bucket

SCHEMA = '''
CREATE TABLE IF NOT EXISTS recovery_dashboards (
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id), owner_id TEXT NOT NULL, name TEXT NOT NULL,
 shared INTEGER NOT NULL DEFAULT 0, scope TEXT NOT NULL DEFAULT 'current', tiles_json TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS recovery_dashboards_tenant ON recovery_dashboards(tenant_id);
CREATE TABLE IF NOT EXISTS recovery_report_schedules (
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id), name TEXT NOT NULL, columns TEXT NOT NULL, stage TEXT NOT NULL DEFAULT '',
 min_days INTEGER NOT NULL DEFAULT 0, weekdays_json TEXT NOT NULL, month_day INTEGER, hour INTEGER NOT NULL, recipients_json TEXT NOT NULL,
 active INTEGER NOT NULL DEFAULT 1, last_sent_on TEXT, last_status TEXT NOT NULL DEFAULT '', created_by TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS recovery_report_schedules_tenant ON recovery_report_schedules(tenant_id)
'''
Line = Annotated[str, Field(max_length=120)]
MEASURES = {'debt': 'Сумма долга', 'overdue': 'Просрочено', 'count': 'Количество должников', 'promised': 'Обещано оплатить', 'collected': 'Получено оплат', 'duty': 'Госпошлина'}
GROUPS = {'stage': 'Этапы', 'status': 'Статусы', 'aging': 'Срок просрочки', 'assignee': 'Ответственные', 'organization': 'Организации', 'month': 'Месяцы'}
CHARTS = {'number': 'Число', 'columns': 'Столбцы', 'bars': 'Полосы', 'line': 'Линия'}
HOME_TILES = [
    dict(id='aging', title='Долг по сроку просрочки', chart='columns', measure='debt', group='aging', stage='', width=1),
    dict(id='monthly', title='Поступления за 12 месяцев', chart='line', measure='collected', group='month', stage='', width=1),
    dict(id='stages', title='Долг по этапам', chart='bars', measure='debt', group='stage', stage='', width=1),
    dict(id='statuses', title='Должники по статусам', chart='bars', measure='count', group='status', stage='', width=1),
]
STAGE_TITLES = {rules.PRETRIAL: 'Досудебная работа', rules.COURT: 'Суд', rules.ENFORCEMENT: 'Исполнение', rules.CLOSED: 'Закрыто'}


class Tile(Input):
    id: str = Field(min_length=1, max_length=40)
    title: Line = Field(min_length=1)
    chart: Literal[tuple(CHARTS)] = 'bars'  # type: ignore[valid-type]
    measure: Literal[tuple(MEASURES)]  # type: ignore[valid-type]
    group: Literal[tuple(GROUPS)] = 'stage'  # type: ignore[valid-type]
    stage: Literal['', 'pretrial', 'court', 'enforcement', 'closed'] = ''
    width: Literal[1, 2] = 1


class DashboardInput(Input):
    name: Line = Field(min_length=1)
    shared: StrictBool = False
    scope: Literal['current', 'all'] = 'current'
    tiles: list[Tile] = Field(default_factory=list, max_length=24)
    copy_from: Annotated[str, Field(max_length=60)] = ''


class ScheduleInput(Input):
    name: Line = Field(min_length=1)
    columns: list[str] = Field(min_length=1, max_length=len(COLUMNS))
    stage: Literal['', 'pretrial', 'court', 'enforcement', 'closed'] = ''
    min_days: Annotated[StrictInt, Field(ge=0, le=3650)] = 0
    weekdays: list[Annotated[StrictInt, Field(ge=0, le=6)]] = Field(default_factory=list, max_length=7)
    month_day: Annotated[StrictInt, Field(ge=1, le=28)] | None = None
    hour: Annotated[StrictInt, Field(ge=0, le=23)]
    recipients: list[str] = Field(min_length=1, max_length=20)
    active: StrictBool = True

    @model_validator(mode='after')
    def timing_and_columns(self):
        if not self.weekdays and self.month_day is None:
            raise ValueError('Выберите дни недели или число месяца')
        if set(self.columns) - set(COLUMNS):
            raise ValueError('Неизвестная колонка отчёта')
        return self


def report_due(schedule, today, hour):
    """One letter a day at most, on or after the chosen hour."""
    if not schedule['active'] or hour < schedule['hour'] or schedule['last_sent_on'] == str(today):
        return False
    weekdays = json.loads(schedule['weekdays_json'])
    return today.weekday() in weekdays or schedule['month_day'] == today.day


def normalize(tile):
    """Tiles saved before chart types existed keep working."""
    tile = dict(tile)
    kind = tile.pop('kind', None)
    if 'chart' not in tile:
        tile['chart'] = {'metric': 'number', 'timeline': 'line'}.get(kind, 'bars')
        if kind == 'timeline':
            tile['group'], tile['measure'] = 'month', 'collected'
    tile.setdefault('group', 'stage')
    tile.setdefault('stage', '')
    tile.setdefault('width', 1)
    return tile


def measure_value(item, measure):
    return {'debt': item['balance'], 'overdue': item['overdue_amount'], 'count': 1, 'duty': item['duty_amount'] or 0,
            'promised': item['balance'] if item['status'] == 'promise' else 0}.get(measure, 0)


def tile_data(tile, debtors, connection, tenants, today, names):
    """Numbers behind one chart. Payments exist per month, debts per debtor."""
    tile = normalize(tile)
    chosen = [item for item in debtors if (item['stage'] == tile['stage'] if tile['stage'] else item['stage'] != rules.CLOSED)]
    unit = 'count' if tile['measure'] == 'count' else 'money'
    if tile['measure'] == 'collected' or tile['group'] == 'month':
        series = [collected_by_month(connection, tenant, today) for tenant in tenants]
        monthly = [dict(month=rows[0]['month'], amount=sum(row['amount'] for row in rows)) for rows in zip(*series)]
        if tile['chart'] == 'number':
            return dict(unit='money', value=monthly[-1]['amount'], note='В этом месяце')
        return dict(unit='money', rows=[dict(label=row['month'], value=row['amount']) for row in monthly], months=True)
    if tile['chart'] == 'number':
        return dict(unit=unit, value=sum(measure_value(item, tile['measure']) for item in chosen))
    if tile['group'] == 'aging' and tile['measure'] != 'promised':
        field = 'count' if tile['measure'] == 'count' else 'amount'
        return dict(unit=unit, rows=[dict(label=row['label'], value=row[field]) for row in aging_rows(chosen)])
    totals = {}
    if tile['group'] == 'stage':
        totals = {STAGE_TITLES[key]: 0 for key in (rules.PRETRIAL, rules.COURT, rules.ENFORCEMENT) if not tile['stage'] or key == tile['stage']}
    for item in chosen:
        label = {'stage': STAGE_TITLES[item['stage']], 'status': item['status_label'], 'aging': next(row[1] for row in AGING if row[0] == bucket(item['days_overdue'])),
                 'assignee': names.get(item['assignee_id']) or 'Не назначен', 'organization': item['_company']}[tile['group']]
        totals[label] = totals.get(label, 0) + measure_value(item, tile['measure'])
    ordered = list(totals.items()) if tile['group'] == 'stage' else sorted(totals.items(), key=lambda pair: -pair[1])
    return dict(unit=unit, rows=[dict(label=key, value=value) for key, value in ordered][:10])


def build_csv(debtors, schedule):
    keys, output = schedule['columns'].split(','), io.StringIO()
    from .recovery import csv_safe
    chosen = [item for item in debtors if not item['archived'] and (not schedule['stage'] or item['stage'] == schedule['stage']) and item['days_overdue'] >= schedule['min_days']]
    writer = csv.writer(output, delimiter=';')
    writer.writerow([COLUMNS[key][0] for key in keys])
    for item in chosen:
        writer.writerow([csv_safe(COLUMNS[key][1](item)) for key in keys])
    return '﻿' + output.getvalue(), len(chosen)


def send_report(recipients, subject, body, content, filename):
    sender = os.environ['SMTP_FROM']
    mail = EmailMessage()
    mail['Subject'], mail['To'], mail['From'] = subject, ', '.join(recipients), sender
    mail.set_content(body)
    mail.add_attachment(content.encode('utf-8'), maintype='text', subtype='csv', filename=filename)
    secure, use_ssl = ssl.create_default_context(), os.getenv('SMTP_USE_SSL', 'false').lower() == 'true'
    options = dict(timeout=15)
    if use_ssl:
        options['context'] = secure
    with (smtplib.SMTP_SSL if use_ssl else smtplib.SMTP)(os.environ['SMTP_HOST'], int(os.getenv('SMTP_PORT', '587')), **options) as smtp:
        if not use_ssl and os.getenv('SMTP_USE_TLS', 'true').lower() == 'true':
            smtp.starttls(context=secure)
        if os.getenv('SMTP_USER'):
            smtp.login(os.environ['SMTP_USER'], os.getenv('SMTP_PASSWORD', ''))
        smtp.send_message(mail)


def member_emails(connection, tenant, ids):
    """Reports leave only for the company's own people, so the service mailbox cannot relay."""
    from .organizations import team
    allowed = {row['id']: row['email'] for row in team(connection, tenant)}
    return [allowed[key] for key in ids if key in allowed]


def deliver(connection, schedule, today):
    from .recovery import all_debtors
    tenant = schedule['tenant_id']
    if not (os.getenv('SMTP_HOST') and os.getenv('SMTP_FROM')):
        return 'Почта сервиса не настроена'
    recipients = member_emails(connection, tenant, json.loads(schedule['recipients_json']))
    if not recipients:
        return 'Нет получателей'
    content, count = build_csv(all_debtors(connection, tenant), schedule)
    send_report(recipients, f"Mandato: {schedule['name']}", f"Отчёт «{schedule['name']}» на {today}. Строк: {count}.", content, 'mandato-report.csv')
    return 'Отправлено'


def run_report_schedules(config, send=deliver):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from .database import database
    today, hour, count = business_today(), datetime.now(ZoneInfo(os.getenv('APP_TIMEZONE', 'Europe/Moscow'))).hour, 0
    with database(config) as connection:
        schedules = [dict(row) for row in connection.execute('SELECT * FROM recovery_report_schedules WHERE active=1')]
    for schedule in schedules:
        if not report_due(schedule, today, hour):
            continue
        try:
            with database(config) as connection:
                status = send(connection, schedule, today)
        except Exception:  # One broken mailbox must not stop other clients' reports.
            logging.getLogger(__name__).error('Report delivery failed')
            status = 'Не удалось отправить'
        with database(config, write=True) as connection:
            connection.execute('UPDATE recovery_report_schedules SET last_sent_on=?,last_status=? WHERE id=?', (str(today), status, schedule['id']))
        count += 1
    return count


def add_routes(router, ctx):
    from .organizations import memberships
    from .recovery import all_debtors

    def manager(user):
        if user['role'] != 'manager':
            ctx.problem(403, 'Это решение принимает руководитель')

    def visible(c, user, key):
        row = c.execute('SELECT * FROM recovery_dashboards WHERE id=? AND tenant_id=?', (key, user['tenant_id'])).fetchone()
        if not row or not (row['shared'] or row['owner_id'] == user['id']):
            ctx.problem(404, 'Панель не найдена')
        return dict(row)

    def editable(c, user, key):
        row = visible(c, user, key)
        if row['owner_id'] != user['id'] and user['role'] != 'manager':
            ctx.problem(403, 'Изменить общую панель может руководитель')
        return row

    def board_data(c, user, board):
        from .organizations import team
        today = business_today()
        orgs = [item for item in memberships(c, user['id']) if board['scope'] == 'all' and item['role'] == 'manager'] or [dict(id=user['tenant_id'], company=user['company'])]
        debtors = []
        for org in orgs:
            debtors += [item | dict(_company=org['company']) for item in all_debtors(c, org['id']) if not item['archived']]
        names = {row['id']: row['name'] for org in orgs for row in team(c, org['id'])}
        tenants = [org['id'] for org in orgs]
        return [dict(id=tile['id'], **tile_data(tile, debtors, c, tenants, today, names)) for tile in json.loads(board['tiles_json'])]

    def home_board(c, user):
        key = f"home:{user['tenant_id']}:{user['id']}"
        row = c.execute('SELECT * FROM recovery_dashboards WHERE id=?', (key,)).fetchone()
        if row:
            return dict(row)
        board = dict(id=key, tenant_id=user['tenant_id'], owner_id=user['id'], name='Главная', shared=0, scope='current', tiles_json=json.dumps(HOME_TILES, ensure_ascii=False), updated_at=ctx.now())
        return board

    @router.get('/home')
    def home(user=Depends(ctx.get_user)):
        """Charts of the first screen: one board per person, built from defaults until changed."""
        with ctx.database(ctx.config) as c:
            board = home_board(c, user)
            tiles = [normalize(tile) for tile in json.loads(board['tiles_json'])]
            several = len([item for item in memberships(c, user['id']) if item['role'] == 'manager']) > 1
            return dict(scope=board['scope'], tiles=tiles, data=board_data(c, user, board), measures=MEASURES, groups=GROUPS, charts=CHARTS, several_organizations=several)

    @router.put('/home')
    def home_save(data: DashboardInput, user=Depends(ctx.get_user)):
        key = f"home:{user['tenant_id']}:{user['id']}"
        tiles = json.dumps([tile.model_dump() for tile in data.tiles], ensure_ascii=False)
        with ctx.database(ctx.config, write=True) as c:
            c.execute('''INSERT INTO recovery_dashboards VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET scope=excluded.scope,tiles_json=excluded.tiles_json,updated_at=excluded.updated_at''',
                      (key, user['tenant_id'], user['id'], 'Главная', 0, data.scope, tiles, ctx.now()))
        return home(user)

    @router.delete('/home')
    def home_reset(user=Depends(ctx.get_user)):
        with ctx.database(ctx.config, write=True) as c:
            c.execute('DELETE FROM recovery_dashboards WHERE id=?', (f"home:{user['tenant_id']}:{user['id']}",))
        return home(user)

    @router.get('/dashboards')
    def dashboard_list(user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as c:
            rows = c.execute('SELECT * FROM recovery_dashboards WHERE tenant_id=? AND (shared=1 OR owner_id=?) ORDER BY name', (user['tenant_id'], user['id'])).fetchall()
        return dict(items=[dict(id=row['id'], name=row['name'], shared=bool(row['shared']), scope=row['scope'], mine=row['owner_id'] == user['id'], tiles=json.loads(row['tiles_json'])) for row in rows],
                    measures=MEASURES, groups=GROUPS)

    @router.post('/dashboards', status_code=201)
    def dashboard_add(data: DashboardInput, user=Depends(ctx.get_user)):
        key = f.uid()
        with ctx.database(ctx.config, write=True) as c:
            tiles = json.loads(visible(c, user, data.copy_from)['tiles_json']) if data.copy_from else [tile.model_dump() for tile in data.tiles]
            c.execute('INSERT INTO recovery_dashboards VALUES(?,?,?,?,?,?,?,?)', (key, user['tenant_id'], user['id'], data.name, int(data.shared), data.scope, json.dumps(tiles, ensure_ascii=False), ctx.now()))
        return dict(id=key)

    @router.put('/dashboards/{key}')
    def dashboard_save(key: str, data: DashboardInput, user=Depends(ctx.get_user)):
        with ctx.database(ctx.config, write=True) as c:
            editable(c, user, key)
            c.execute('UPDATE recovery_dashboards SET name=?,shared=?,scope=?,tiles_json=?,updated_at=? WHERE id=?', (data.name, int(data.shared), data.scope, json.dumps([tile.model_dump() for tile in data.tiles], ensure_ascii=False), ctx.now(), key))
        return dict(id=key)

    @router.delete('/dashboards/{key}')
    def dashboard_delete(key: str, user=Depends(ctx.get_user)):
        with ctx.database(ctx.config, write=True) as c:
            editable(c, user, key)
            c.execute('DELETE FROM recovery_dashboards WHERE id=?', (key,))
        return dict(ok=True)

    @router.get('/dashboards/{key}/data')
    def dashboard_data(key: str, user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as c:
            return dict(items=board_data(c, user, visible(c, user, key)))

    @router.get('/report-schedules')
    def schedule_list(user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as c:
            rows = c.execute('SELECT * FROM recovery_report_schedules WHERE tenant_id=? ORDER BY name', (user['tenant_id'],)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item['columns'] = item['columns'].split(',')
            item['weekdays'], item['recipients'] = json.loads(item.pop('weekdays_json')), json.loads(item.pop('recipients_json'))
            item['active'] = bool(item['active'])
            result.append(item)
        return dict(items=result, mail_ready=bool(os.getenv('SMTP_HOST') and os.getenv('SMTP_FROM')))

    @router.post('/report-schedules', status_code=201)
    def schedule_add(data: ScheduleInput, user=Depends(ctx.get_user)):
        manager(user)
        key = f.uid()
        with ctx.database(ctx.config, write=True) as c:
            if not member_emails(c, user['tenant_id'], data.recipients):
                ctx.problem(422, 'Получатели должны быть сотрудниками организации')
            c.execute('INSERT INTO recovery_report_schedules(id,tenant_id,name,columns,stage,min_days,weekdays_json,month_day,hour,recipients_json,active,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (key, user['tenant_id'], data.name, ','.join(data.columns), data.stage, data.min_days, json.dumps(data.weekdays), data.month_day, data.hour, json.dumps(data.recipients), int(data.active), user['id'], ctx.now()))
        return dict(id=key)

    @router.delete('/report-schedules/{key}')
    def schedule_delete(key: str, user=Depends(ctx.get_user)):
        manager(user)
        with ctx.database(ctx.config, write=True) as c:
            c.execute('DELETE FROM recovery_report_schedules WHERE id=? AND tenant_id=?', (key, user['tenant_id']))
        return dict(ok=True)

    @router.get('/report-schedules/{key}/preview.csv')
    def schedule_preview(key: str, user=Depends(ctx.get_user)):
        with ctx.database(ctx.config) as c:
            row = c.execute('SELECT * FROM recovery_report_schedules WHERE id=? AND tenant_id=?', (key, user['tenant_id'])).fetchone()
            if not row:
                ctx.problem(404, 'Отчёт не найден')
            content, _ = build_csv(all_debtors(c, user['tenant_id']), dict(row))
        rows = list(csv.reader(io.StringIO(content.lstrip('﻿')), delimiter=';'))
        return csv_response(rows, 'mandato-report.csv')
