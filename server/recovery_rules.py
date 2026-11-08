"""Pure rules of the debt-recovery pipeline: statuses, transitions, checks.

One debtor (counterparty) moves through pre-trial, court and enforcement. Money
and dates are calculated here by code; a language model never decides them.
All amounts are integer kopeks. No function in this module touches the database.
"""
from __future__ import annotations

from datetime import date, timedelta

from .legal import ORDER_LIMIT, arbitration_fee

PRETRIAL, COURT, ENFORCEMENT, CLOSED = 'pretrial', 'court', 'enforcement', 'closed'
STAGES = (PRETRIAL, COURT, ENFORCEMENT, CLOSED)
COURT_ORDER, LAWSUIT = 'court_order', 'statement_of_claim'

DEFAULT_PRETRIAL_DAYS = 30  # APC RF art. 4(5), unless the contract says otherwise.
LIMITATION_YEARS = 3  # Civil Code art. 196.
WRIT_YEARS = 3  # Federal Law 229-FZ art. 21.
ORDER_OBJECTION_DAYS = 10  # APC RF art. 229.5.
MIN_COURT_WORTHWHILE = 5_000_000  # 50 000 RUB: below this a practising lawyer advises against court.
BANKRUPTCY_THRESHOLD_COMPANY = 200_000_000  # 2 000 000 RUB, Federal Law 127-FZ art. 6.
BANKRUPTCY_THRESHOLD_SOLE = 50_000_000  # 500 000 RUB for sole proprietors.

STATUSES = {
    'new': (PRETRIAL, 'Новый'),
    'reminders': (PRETRIAL, 'Напоминания'),
    'promise': (PRETRIAL, 'Обещал оплатить'),
    'promise_broken': (PRETRIAL, 'Обещание нарушено'),
    'dispute': (PRETRIAL, 'Спор'),
    'claim_ready': (PRETRIAL, 'Претензия готова'),
    'claim_sent': (PRETRIAL, 'Претензия отправлена'),
    'ready_for_court': (PRETRIAL, 'Можно передавать в суд'),
    'court_prep': (COURT, 'Выбор маршрута'),
    'duty_pending': (COURT, 'Ожидает оплаты пошлины'),
    'duty_paid': (COURT, 'Пошлина оплачена'),
    'lawyer_review': (COURT, 'На проверке у юриста'),
    'ready_to_file': (COURT, 'Готово к подаче'),
    'filed': (COURT, 'Подано в суд'),
    'without_motion': (COURT, 'Оставлено без движения'),
    'order_issued': (COURT, 'Вынесен судебный приказ'),
    'lawsuit_prep': (COURT, 'Подготовка иска'),
    'hearing': (COURT, 'Идёт рассмотрение'),
    'decision': (COURT, 'Решение вынесено'),
    'in_force': (COURT, 'Решение вступило в силу'),
    'writ_requested': (ENFORCEMENT, 'Запрошен исполнительный лист'),
    'writ_received': (ENFORCEMENT, 'Исполнительный документ получен'),
    'sent_bank': (ENFORCEMENT, 'Предъявлен в банк'),
    'sent_fssp': (ENFORCEMENT, 'Передан в ФССП'),
    'no_assets': (ENFORCEMENT, 'Имущество не найдено'),
    'bankruptcy_intent': (ENFORCEMENT, 'Намерение о банкротстве'),
    'paid': (CLOSED, 'Оплачено'),
    'settled': (CLOSED, 'Мировое соглашение'),
    'written_off': (CLOSED, 'Списано'),
    'withdrawn': (CLOSED, 'Отозвано клиентом'),
    'lost': (CLOSED, 'В иске отказано'),
}

OPEN_STATUSES = frozenset(key for key, value in STATUSES.items() if value[0] != CLOSED)
PRETRIAL_ACTIVE = frozenset(('new', 'reminders', 'promise_broken', 'claim_sent', 'ready_for_court'))

# action: (allowed statuses, next status, manager only, required payload fields)
ACTIONS = {
    'start': (frozenset(('new',)), 'reminders', False, ()),
    'promise': (PRETRIAL_ACTIVE, 'promise', False, ('promise_date',)),
    'dispute': (PRETRIAL_ACTIVE | {'promise', 'claim_ready'}, 'dispute', False, ('note',)),
    'resolve_dispute': (frozenset(('dispute',)), 'reminders', False, ('note',)),
    'prepare_claim': (frozenset(('new', 'reminders', 'promise_broken')), 'claim_ready', False, ()),
    'send_claim': (frozenset(('claim_ready',)), 'claim_sent', False, ('sent_on', 'reference')),
    'to_court': (frozenset(('ready_for_court', 'dispute')), 'court_prep', True, ()),
    'set_route': (frozenset(('court_prep', 'lawsuit_prep')), 'duty_pending', False, ('route',)),
    'duty_paid': (frozenset(('duty_pending',)), 'duty_paid', False, ('reference',)),
    'send_to_lawyer': (frozenset(('duty_paid',)), 'lawyer_review', False, ()),
    'lawyer_approve': (frozenset(('lawyer_review',)), 'ready_to_file', True, ()),
    'file': (frozenset(('ready_to_file',)), 'filed', False, ('filed_on', 'reference')),
    'without_motion': (frozenset(('filed', 'hearing')), 'without_motion', False, ('note',)),
    'fix_motion': (frozenset(('without_motion',)), 'filed', False, ('note',)),
    'court_returned': (frozenset(('filed', 'without_motion')), 'court_prep', False, ('note',)),
    'order_issued': (frozenset(('filed',)), 'order_issued', False, ('case_number', 'act_on')),
    'order_cancelled': (frozenset(('order_issued',)), 'lawsuit_prep', False, ('act_on',)),
    'accepted': (frozenset(('filed',)), 'hearing', False, ('case_number',)),
    'decision_won': (frozenset(('hearing',)), 'decision', False, ('act_on',)),
    'decision_lost': (frozenset(('hearing',)), 'lost', False, ('act_on',)),
    'in_force': (frozenset(('decision',)), 'in_force', False, ('act_on',)),
    'to_enforcement': (frozenset(('order_issued', 'in_force')), 'writ_requested', False, ()),
    'writ_received': (frozenset(('writ_requested',)), 'writ_received', False, ('reference', 'act_on')),
    'send_bank': (frozenset(('writ_received', 'no_assets')), 'sent_bank', False, ('reference',)),
    'send_fssp': (frozenset(('writ_received', 'sent_bank', 'no_assets')), 'sent_fssp', False, ('reference',)),
    'no_assets': (frozenset(('sent_bank', 'sent_fssp')), 'no_assets', False, ('note',)),
    'bankruptcy_intent': (frozenset(('sent_bank', 'sent_fssp', 'no_assets')), 'bankruptcy_intent', True, ('act_on',)),
    'settle': (OPEN_STATUSES, 'settled', True, ('note',)),
    'write_off': (OPEN_STATUSES, 'written_off', True, ('note',)),
    'withdraw': (OPEN_STATUSES, 'withdrawn', True, ('note',)),
    'reopen': (frozenset(('settled', 'written_off', 'withdrawn')), 'reminders', True, ('note',)),
}

ACTION_LABELS = {
    'start': 'Начать работу', 'promise': 'Записать обещание', 'dispute': 'Отметить спор',
    'resolve_dispute': 'Спор снят', 'prepare_claim': 'Подготовить претензию',
    'send_claim': 'Отметить отправку претензии', 'to_court': 'Передать в суд',
    'set_route': 'Выбрать маршрут', 'duty_paid': 'Пошлина оплачена',
    'send_to_lawyer': 'Отправить юристу', 'lawyer_approve': 'Юрист проверил',
    'file': 'Отметить подачу', 'without_motion': 'Без движения', 'fix_motion': 'Недостатки устранены',
    'court_returned': 'Заявление возвращено', 'order_issued': 'Приказ вынесен',
    'order_cancelled': 'Приказ отменён', 'accepted': 'Иск принят',
    'decision_won': 'Решение в нашу пользу', 'decision_lost': 'В иске отказано',
    'in_force': 'Решение вступило в силу', 'to_enforcement': 'Перейти к взысканию',
    'writ_received': 'Лист получен', 'send_bank': 'Предъявить в банк', 'send_fssp': 'Передать в ФССП',
    'no_assets': 'Имущество не найдено', 'bankruptcy_intent': 'Намерение о банкротстве',
    'settle': 'Мировое соглашение', 'write_off': 'Списать', 'withdraw': 'Отозвать',
    'reopen': 'Вернуть в работу',
}

# Documents a user generates in each status; the action is blocked without them.
REQUIRED_DOCUMENT = {'prepare_claim': 'claim', 'send_to_lawyer': 'route'}


def stage_of(status):
    return STATUSES[status][0]


def add_years(day, years):
    try:
        return day.replace(year=day.year + years)
    except ValueError:  # 29 February
        return day.replace(year=day.year + years, day=28)


def debtor_kind(inn):
    return 'sole_proprietor' if len(inn or '') == 12 else 'company' if len(inn or '') == 10 else 'unknown'


def effective_status(state, today, balance, automation):
    """Status as of today: time and money move a debtor without a stored write."""
    status = state['status']
    if balance <= 0 and status in OPEN_STATUSES:
        return 'paid'
    if status == 'promise' and state.get('promise_date'):
        grace = timedelta(days=automation.get('payment_control_days', 3))
        if date.fromisoformat(state['promise_date']) + grace < today:
            return 'promise_broken'
    if status == 'claim_sent' and state.get('claim_sent_on'):
        days = state.get('pretrial_days') or DEFAULT_PRETRIAL_DAYS
        if date.fromisoformat(state['claim_sent_on']) + timedelta(days=days) <= today:
            return 'ready_for_court'
    return status


EVIDENCE_LABELS = {
    'contract': 'Договор или иное основание сделки',
    'performance': 'Подтверждение исполнения: акт, УПД или накладная',
    'reconciliation': 'Акт сверки',
    'correspondence': 'Переписка с должником',
    'power_of_attorney': 'Доверенность представителя',
    'claim_proof': 'Подтверждение отправки претензии',
}
EVIDENCE_HINTS = {
    'contract': 'Без документа о сделке суд не увидит основания долга.',
    'performance': 'Нужна подпись уполномоченного лица: без неё исполнение можно оспорить.',
    'reconciliation': 'Подписанный должником акт сверки признаёт долг и прерывает давность.',
    'correspondence': 'Письма и сообщения укрепляют позицию, если должник спорит.',
    'power_of_attorney': 'ИП без печати нужна нотариальная доверенность.',
    'claim_proof': 'Опись вложения и квитанция или отчёт оператора ЭДО.',
}
REQUIRED_FOR_COURT = ('contract', 'performance', 'power_of_attorney', 'claim_proof')


def evidence_report(open_invoice_ids, evidence, *, has_poa, claim_proof):
    """Which documents exist. Contract and performance must cover every open invoice."""
    covered = {}
    for row in evidence:
        covered.setdefault(row['kind'], set()).add(row['invoice_id'])
    open_ids = set(open_invoice_ids)
    state = {
        'contract': bool(open_ids) and open_ids <= covered.get('contract', set()),
        'performance': bool(open_ids) and open_ids <= covered.get('performance', set()),
        'reconciliation': bool(covered.get('reconciliation', set()) & open_ids),
        'correspondence': bool(covered.get('correspondence', set()) & open_ids),
        'power_of_attorney': has_poa,
        'claim_proof': claim_proof,
    }
    items = [dict(key=key, label=EVIDENCE_LABELS[key], hint=EVIDENCE_HINTS[key],
                  present=state[key], required=key in REQUIRED_FOR_COURT) for key in EVIDENCE_LABELS]
    required = [item for item in items if item['required']]
    present = sum(item['present'] for item in required)
    return dict(items=items, score=round(100 * present / len(required)),
                ready_for_court=present == len(required),
                missing=[item['key'] for item in required if not item['present']])


def recommend_route(claim_amount, *, disputed, order_cancelled):
    """Court order only for a documented undisputed claim within the statutory limit."""
    if order_cancelled:
        return dict(route=LAWSUIT, reason='Судебный приказ отменён: дальше только иск.')
    if disputed:
        return dict(route=LAWSUIT, reason='Должник оспаривает долг: приказное производство не подходит.')
    if claim_amount > ORDER_LIMIT:
        return dict(route=LAWSUIT, reason='Требование больше 750 000 ₽: нужен иск.')
    return dict(route=COURT_ORDER, reason='Бесспорный документальный долг до 750 000 ₽: приказ быстрее и в два раза дешевле по пошлине.')


def duty_amount(claim_amount, route):
    return arbitration_fee(claim_amount, 'court_order' if route == COURT_ORDER else 'claim')


def economics(claim_amount, route, tariff):
    """Upfront money for going to court, without any promise of recovery."""
    duty = duty_amount(claim_amount, route)
    package = tariff['court_order_amount' if route == COURT_ORDER else 'statement_of_claim_amount']
    upfront = duty + package
    warnings = []
    if claim_amount < MIN_COURT_WORTHWHILE:
        warnings.append('Долг меньше 50 000 ₽: судебные расходы могут превысить результат.')
    return dict(route=route, duty_amount=duty, package_amount=package, upfront_amount=upfront,
                upfront_percent=round(100 * upfront / claim_amount, 1) if claim_amount else 0,
                duty_recoverable=True, warnings=warnings)


def solvency_report(check):
    """Interpret the latest registry check; absence of data is reported as unknown."""
    state = str((check or {}).get('result', {}).get('state') or '').upper() if check and check.get('status') == 'completed' else ''
    if not state:
        return dict(state='unknown', label='Статус не проверен', warning='Проверьте должника перед судом: взыскивать с неплатёжеспособной компании невыгодно.')
    if state in ('LIQUIDATED', 'BANKRUPT'):
        return dict(state='stop', label='Компания ликвидирована или банкрот', warning='Обычное взыскание невозможно: проверьте реестр требований.')
    if state in ('LIQUIDATING', 'REORGANIZING'):
        return dict(state='risk', label='Идёт ликвидация или реорганизация', warning='Заявите требование в установленный срок.')
    return dict(state='active', label='Действующая компания', warning='')


def deadlines(state, oldest_due_on, today):
    items = []
    if oldest_due_on:
        limit = add_years(date.fromisoformat(oldest_due_on), LIMITATION_YEARS)
        items.append(dict(key='limitation', label='Срок исковой давности', on=str(limit), days_left=(limit - today).days))
    if state.get('claim_sent_on') and state['status'] == 'claim_sent':
        end = date.fromisoformat(state['claim_sent_on']) + timedelta(days=state.get('pretrial_days') or DEFAULT_PRETRIAL_DAYS)
        items.append(dict(key='claim_wait', label='Срок ответа на претензию', on=str(end), days_left=(end - today).days))
    if state['status'] == 'order_issued' and state.get('act_on'):
        end = date.fromisoformat(state['act_on']) + timedelta(days=ORDER_OBJECTION_DAYS)
        items.append(dict(key='order_objection', label='Срок возражений на приказ', on=str(end), days_left=(end - today).days))
    if stage_of(state['status']) == ENFORCEMENT and state.get('writ_on'):
        end = add_years(date.fromisoformat(state['writ_on']), WRIT_YEARS)
        items.append(dict(key='writ', label='Срок предъявления исполнительного листа', on=str(end), days_left=(end - today).days))
    return items


STEPS = {
    PRETRIAL: (('new', 'Долг загружен'), ('reminders', 'Напоминания'), ('claim_ready', 'Претензия подготовлена'),
               ('claim_sent', 'Претензия отправлена'), ('ready_for_court', 'Срок ответа истёк')),
    COURT: (('court_prep', 'Маршрут выбран'), ('duty_pending', 'Пошлина рассчитана'), ('duty_paid', 'Пошлина оплачена'),
            ('lawyer_review', 'Проверка юристом'), ('ready_to_file', 'Готово к подаче'), ('filed', 'Подано'),
            ('decision', 'Судебный акт')),
    ENFORCEMENT: (('writ_requested', 'Запрос листа'), ('writ_received', 'Документ получен'),
                  ('sent', 'Предъявлен'), ('paid', 'Деньги получены')),
}
_ORDER = {PRETRIAL: ('new', 'reminders', 'promise', 'promise_broken', 'dispute', 'claim_ready', 'claim_sent', 'ready_for_court'),
          COURT: ('court_prep', 'lawsuit_prep', 'duty_pending', 'duty_paid', 'lawyer_review', 'ready_to_file', 'filed', 'without_motion', 'hearing', 'order_issued', 'decision', 'in_force'),
          ENFORCEMENT: ('writ_requested', 'writ_received', 'sent_bank', 'sent_fssp', 'no_assets', 'bankruptcy_intent')}
_POSITION = {
    'new': 0, 'reminders': 1, 'promise': 1, 'promise_broken': 1, 'dispute': 1, 'claim_ready': 2, 'claim_sent': 3, 'ready_for_court': 4,
    'court_prep': 0, 'lawsuit_prep': 0, 'duty_pending': 1, 'duty_paid': 2, 'lawyer_review': 3, 'ready_to_file': 4,
    'filed': 5, 'without_motion': 5, 'hearing': 5, 'order_issued': 6, 'decision': 6, 'in_force': 6,
    'writ_requested': 0, 'writ_received': 1, 'sent_bank': 2, 'sent_fssp': 2, 'no_assets': 2, 'bankruptcy_intent': 2,
}
_ATTENTION = frozenset(('promise_broken', 'dispute', 'without_motion', 'no_assets'))


def steps(status):
    """Progress chips for the current stage: done, current, attention or pending."""
    stage = stage_of(status)
    if stage == CLOSED:
        return []
    position = _POSITION[status]
    result = []
    for index, (key, label) in enumerate(STEPS[stage]):
        state = 'done' if index < position else 'current' if index == position else 'pending'
        if state == 'current' and status in _ATTENTION:
            state = 'attention'
        result.append(dict(key=key, label=label, state=state))
    return result


def available_actions(status, *, route=None):
    result = [key for key, value in ACTIONS.items() if status in value[0]]
    if route == COURT_ORDER:
        result = [key for key in result if key != 'accepted']
    elif route == LAWSUIT:
        result = [key for key in result if key != 'order_issued']
    return result


def guard(action, status, *, facts):
    """Business reason an otherwise valid transition must stop, or None."""
    if action == 'to_court':
        if status == 'dispute' and not facts.get('claim_sent_on'):
            return 'Сначала направьте претензию: без неё суд оставит заявление без рассмотрения.'
        if not facts['evidence']['ready_for_court']:
            return 'Не хватает документов для суда: ' + ', '.join(EVIDENCE_LABELS[key] for key in facts['evidence']['missing'])
        if facts['solvency']['state'] == 'stop':
            return 'Компания ликвидирована или признана банкротом: иск не принесёт денег.'
    if action == 'set_route':
        if facts.get('route') == COURT_ORDER and (facts['claim_amount'] > ORDER_LIMIT or facts['disputed'] or facts['order_cancelled']):
            return 'Судебный приказ здесь невозможен: выберите иск.'
    if action == 'bankruptcy_intent':
        if not facts.get('has_court_act'):
            return 'Нужен вступивший в силу судебный акт.'
        threshold = BANKRUPTCY_THRESHOLD_SOLE if facts['kind'] == 'sole_proprietor' else BANKRUPTCY_THRESHOLD_COMPANY
        if facts['balance'] < threshold:
            return 'Сумма долга ниже порога для банкротства: 2 000 000 ₽ для компании, 500 000 ₽ для ИП.'
    return None


_NEXT = {
    'new': ('start', 'Запустите напоминания: первое письмо уйдёт по вашим правилам.', 'today'),
    'reminders': ('prepare_claim', 'Если должник молчит, следующая ступень — претензия.', 'soon'),
    'promise': (None, 'Ждём оплату к обещанной дате. Выписка закроет долг автоматически.', 'later'),
    'promise_broken': ('prepare_claim', 'Обещание не выполнено: пора направить претензию.', 'today'),
    'dispute': ('resolve_dispute', 'Разберите возражение: качество, сроки или подпись могут изменить исход.', 'today'),
    'claim_ready': ('send_claim', 'Отправьте претензию по юридическому адресу и сохраните подтверждение.', 'today'),
    'claim_sent': (None, 'Идёт срок ответа на претензию. Суд откроется автоматически.', 'later'),
    'ready_for_court': ('to_court', 'Срок ответа истёк. Руководитель решает, идти ли в суд.', 'today'),
    'court_prep': ('set_route', 'Подтвердите маршрут: приказ или иск.', 'today'),
    'lawsuit_prep': ('set_route', 'Подтвердите подготовку иска и рассчитайте пошлину.', 'today'),
    'duty_pending': ('duty_paid', 'Оплатите госпошлину и укажите номер платёжного поручения.', 'today'),
    'duty_paid': ('send_to_lawyer', 'Сформируйте пакет и передайте юристу.', 'today'),
    'lawyer_review': ('lawyer_approve', 'Юрист проверяет документы и расчёт.', 'soon'),
    'ready_to_file': ('file', 'Подайте пакет через «Мой арбитр» и укажите номер.', 'today'),
    'filed': (None, 'Ожидаем определение суда: внесите результат, когда он появится в картотеке.', 'later'),
    'without_motion': ('fix_motion', 'Суд указал на недостатки: устраните их до указанной даты.', 'today'),
    'hearing': (None, 'Дело рассматривается. Внесите решение, когда оно будет вынесено.', 'later'),
    'order_issued': ('to_enforcement', 'Если возражений нет, предъявите приказ к исполнению.', 'soon'),
    'decision': ('in_force', 'Отметьте дату вступления решения в силу.', 'soon'),
    'in_force': ('to_enforcement', 'Решение вступило в силу: запросите исполнительный лист.', 'today'),
    'writ_requested': ('writ_received', 'Внесите номер листа, когда суд его выдаст.', 'later'),
    'writ_received': ('send_bank', 'Сначала банк должника: так деньги приходят быстрее, чем через ФССП.', 'today'),
    'sent_bank': (None, 'Контролируем поступления по выписке.', 'later'),
    'sent_fssp': (None, 'Контролируем исполнительное производство и поступления.', 'later'),
    'no_assets': ('bankruptcy_intent', 'Денег нет: оцените банкротство или списание долга.', 'soon'),
    'bankruptcy_intent': (None, 'Заявление о банкротстве можно подать через 15 дней после публикации на Федресурсе.', 'later'),
}


def next_step(status, *, evidence):
    if status not in _NEXT:
        return None
    action, reason, urgency = _NEXT[status]
    if status == 'ready_for_court' and not evidence['ready_for_court']:
        action, reason, urgency = None, 'Для суда не хватает документов. Загрузите их в карточке.', 'today'
    return dict(action=action, label=ACTION_LABELS.get(action), reason=reason, urgency=urgency)


DEFAULT_AUTOMATION = {
    'enabled': False, 'min_amount': 1_000_000, 'max_amount': 1_000_000_000,
    'start_after_overdue_days': 1, 'claim_after_overdue_days': 30, 'auto_prepare_claim': False,
    'payment_control_days': 3, 'pretrial_days': DEFAULT_PRETRIAL_DAYS,
    'channels': {
        'email': {'enabled': True, 'min_amount': 0, 'repeat_days': 7},
        'voice': {'enabled': False, 'min_amount': 5_000_000, 'repeat_days': 7},
        'sms': {'enabled': False, 'min_amount': 1_000_000, 'repeat_days': 7},
        'post': {'enabled': False, 'min_amount': 5_000_000, 'repeat_days': 30},
    },
    'weekdays': [0, 1, 2, 3, 4], 'start_hour': 9, 'end_hour': 18,
}


def automation_decision(status, *, balance, days_overdue, contact_allowed, automation):
    """Next unattended move for a debtor. Court is always a human decision."""
    if not automation.get('enabled') or not contact_allowed:
        return None
    if not automation['min_amount'] <= balance <= automation['max_amount']:
        return None
    if status == 'new' and days_overdue >= automation['start_after_overdue_days']:
        return 'start'
    if status in ('reminders', 'promise_broken') and automation['auto_prepare_claim'] and days_overdue >= automation['claim_after_overdue_days']:
        return 'prepare_claim'
    return None
