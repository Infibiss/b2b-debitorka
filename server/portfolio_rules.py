"""Explainable AR worklist, not credit scoring or an assertion of legal merit."""
from datetime import date
from .legal import arbitration_fee


def finding(code, severity, title, detail, next_step, evidence):
    return dict(code=code, severity=severity, title=title, detail=detail, next_step=next_step, evidence=evidence)


ACTIONS = {
    'closed': ('Оплата отражена', 'Проверьте закрытие обязательства и сохраните подтверждающие документы.'),
    'stop': ('Приостановить контакт', 'Разберите спор или получите новое разрешение ответственного сотрудника.'),
    'reconcile': ('Сверить расчёты', 'Сопоставьте первичные документы, оплаты, возвраты и зачёты с бухгалтером.'),
    'lawyer_review': ('Передать юристу', 'Проверьте сроки, основания требования и допустимый порядок взыскания.'),
    'check_debtor': ('Проверить должника', 'Подтвердите статус и идентичность должника по актуальному источнику.'),
    'obtain_documents': ('Собрать документы', 'Запросите отсутствующий договор, подтверждение исполнения и условия оплаты.'),
    'wait_promise': ('Контролировать обещание', 'Проверьте поступление в согласованный срок. Новую серию напоминаний не начинайте.'),
    'contact': ('Уточнить оплату', 'Подготовьте согласованное обращение с текущим остатком и проверьте разрешение на контакт.'),
    'monitor': ('Контролировать срок', 'Дождитесь срока оплаты и проверьте поступление.'),
}


def audit_invoice(inv, cp, *, evidence, reconciliation, registry, promises, deadlines, document_stale, as_of):
    balance = inv['amount'] + inv['adjustment_amount'] - inv['paid_amount']
    result = dict(invoice_id=inv['id'], counterparty_id=cp['id'], company=inv['company'], inn=inv['inn'],
        number=inv['number'], due_on=inv['due_on'], balance=balance, findings=[],
        days_overdue=max(0, (as_of-date.fromisoformat(inv['due_on'])).days) if balance else 0,
        registry=registry, documents=sorted(set(evidence)), deadlines=deadlines)
    findings = result['findings']
    result['economics'] = {'basis':'principal_only','claim_duty':arbitration_fee(balance) if balance>0 else 0,
        'court_order_duty':arbitration_fee(balance,'court_order') if 0<balance<=75_000_000 else None,
        'other_costs_known':False,'route_requires_legal_review':True}
    source = [{'source': 'ledger', 'reference': inv['number'], 'revision': inv['revision']}]
    code = 'closed' if balance <= 0 else 'monitor'
    if balance > 0:
        days = result['days_overdue']
        code = 'contact' if days else 'monitor'
        if result['economics']['claim_duty']*10>balance:
            findings.append(finding('court_cost_review','attention','Сопоставить расходы с суммой долга',
                'Пошлина по иску от основного долга превышает 10% остатка. Проценты, расходы представителя и возможные льготы в этой оценке не учтены.',
                'Сравните досудебное урегулирование, стоимость представителя и судебный маршрут до решения о расходах.',source))
        missing = {'contract': ('missing_contract', 'Нет договора', 'contract'),
                   'performance': ('missing_performance', 'Нет подтверждения исполнения', 'performance'),
                   'payment_terms': ('missing_payment_terms', 'Не подтверждены условия оплаты', 'payment_terms')}
        for kind, (key, title, _) in missing.items():
            if kind not in evidence:
                findings.append(finding(key, 'review', title,
                    'Подтверждающий документ не зарегистрирован. Это не утверждение, что его нет у организации.',
                    'Найдите первичный документ и зарегистрируйте его реквизиты или файл.', source))
                code = 'obtain_documents'
        if not inv['email']:
            findings.append(finding('missing_contact', 'review', 'Нет адреса для письма',
                'В реестре не указан email получателя.', 'Уточните рабочий контакт и основание обращения.', source))
        known = registry.get('status') == 'completed' and registry.get('fresh') is True
        if not known:
            findings.append(finding('registry_unverified', 'review', 'Статус должника требует проверки',
                'Нет свежего результата проверки с подтверждённым ИНН. Отсутствие данных не означает отсутствие рисков.',
                'Проверьте ИНН и обновите сведения о регистрации; судебные и исполнительные риски проверяются отдельно.',
                [{'source': registry.get('provider', 'registry'), 'reference': registry.get('checked_at') or 'Нет проверки'}]))
            code = 'check_debtor'
        if known and registry.get('registration_status') in ('LIQUIDATING', 'LIQUIDATED', 'BANKRUPT', 'REORGANIZING'):
            findings.append(finding('registry_adverse', 'urgent', 'Изменение статуса должника',
                'В источнике отмечена ликвидация, прекращение деятельности, реорганизация или банкротство.',
                'Передайте результат юристу до выбора следующего действия.',
                [{'source': registry.get('provider', 'registry'), 'reference': registry.get('checked_at', '')}]))
            code = 'lawyer_review'
        active = [p for p in promises if p['status'] == 'active']
        promised_remaining = sum(max(0,p['amount']-p['fulfilled_amount']) for p in active)
        tranches=[{**part,'promise_id':p['id']} for p in active for part in p.get('installments',[])]
        missed=[part for part in tranches if part['due_on']<str(as_of) and part['fulfilled_amount']<part['amount']]
        if missed or any(p['due_on'] < str(as_of) and p['fulfilled_amount'] < p['amount'] for p in active):
            findings.append(finding('broken_promise', 'attention', 'Срок обещания прошёл',
                'По зарегистрированному графику осталась неоплаченная сумма.',
                'Сначала проверьте поступления и выясните причину нарушения договорённости.',
                [{'source': 'promise', 'reference': p.get('promise_id',p['id']), 'due_on': p['due_on']} for p in (missed or active)]))
            if code in ('contact', 'monitor'): code = 'contact'
        elif active:
            if promised_remaining >= balance and code in ('contact', 'monitor'):
                code = 'wait_promise'
            elif 0 < promised_remaining < balance:
                findings.append(finding('partial_promise', 'attention', 'Обещание покрывает только часть остатка',
                    'Действующее обещание не включает всю задолженность. По непокрытой части требуется отдельная договорённость.',
                    'Согласуйте оплату непокрытого остатка, сохранив действующее частичное обещание отдельно.',
                    [{'source':'promise','reference':p['id'],'amount':p['amount']-p['fulfilled_amount'],'due_on':p['due_on']}
                     for p in active if p['amount']>p['fulfilled_amount']]))
        if document_stale:
            findings.append(finding('stale_document', 'attention', 'Документ требует обновления',
                'После подготовки документа изменились финансовые данные или юридические факты.',
                'Подготовьте новую версию и получите повторное согласование.', source))
        if days >= 900:
            findings.append(finding('limitation_review', 'urgent', 'Проверить исковую давность',
                'Просрочка превышает 900 дней. Этот сигнал не определяет начало или истечение исковой давности: признание долга, договор и процессуальные обстоятельства проверяет юрист.',
                'Назначьте юридическую проверку срока и документируйте её основание.', source))
            code = 'lawyer_review'
        if reconciliation and reconciliation['current_discrepancy'] != 0:
            findings.append(finding('accounting_discrepancy', 'attention', 'Есть расхождение с учётным источником',
                'Остаток из принятой ОСВ или акта отличается от текущего реестра. Даты источника и реестра могут различаться.',
                'Проверьте движения между датой выгрузки и текущим состоянием, затем первичные документы.',
                [{'source': 'accounting', 'reference': reconciliation['source_ref'], 'as_of': reconciliation['as_of'],
                  'source_balance': reconciliation['source_balance'], 'current_discrepancy': reconciliation['current_discrepancy']}]))
            if code != 'lawyer_review': code = 'reconcile'
        if cp['hold'] or not cp['contact_allowed'] or inv['status'] in ('paused', 'disputed') or (
            cp['mandate_expires_on'] and cp['mandate_expires_on'] < str(as_of)):
            findings.append(finding('contact_blocked', 'attention', 'Контакт приостановлен',
                cp['hold_reason'] or 'Спор, пауза или недействующее разрешение на контакт.',
                'Получите решение ответственного сотрудника; не запускайте напоминания.', source))
            code = 'stop'
    # Explicit legal control dates are independent of principal payment: a paid
    # claim may still need a court statement, expense review or formal closure.
    for deadline in deadlines:
        remaining = (date.fromisoformat(deadline['review_on'])-as_of).days
        if remaining <= 30:
            findings.append(finding('legal_deadline', 'urgent' if remaining <= 14 else 'attention',
                'Назначен срок юридической проверки',
                f"Контрольная дата {deadline['review_on']}. Основание: {deadline['basis']}",
                'Свяжитесь с ответственным юристом до контрольной даты.',
                [{'source': 'operator_deadline', 'reference': deadline['id'], 'review_on': deadline['review_on']}]))
            if code != 'stop': code = 'lawyer_review'
    rank = {'urgent': 0, 'attention': 1, 'review': 2}
    findings.sort(key=lambda item: (rank[item['severity']], item['code']))
    result['severity'] = findings[0]['severity'] if findings else 'clear'
    title, detail = ACTIONS[code]
    result['next_action'] = {'code': code, 'title': title, 'detail': detail}
    return result
