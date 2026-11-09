"""Editable DOCX templates for each stage of recovery.

The claim and the court papers share one statement of facts, so a claim can
become a court filing by changing only the heading and the request. Every draft
is reviewed by a person; Mandato does not sign or file anything by itself.
"""
import re
from io import BytesIO

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt

FACTS = """Между {{creditor.name}} (Кредитор) и {{debtor.name}} (Должник) заключён договор {{contract}}.

Кредитор исполнил свои обязательства, что подтверждается следующими документами: {{performance_documents}}.

Должник в установленный срок оплату не произвёл. По состоянию на {{today}} задолженность составляет {{principal}} руб.:

{{invoices}}

{{interest_text}}"""

SIGNATURE = """{{creditor.signatory}}
{{creditor.name}}
{{today}}"""

_CREDITOR = "{{creditor.name}}\nИНН {{creditor.inn}}, ОГРН {{creditor.ogrn}}\nАдрес: {{creditor.address}}"
_DEBTOR = "{{debtor.name}}\nИНН {{debtor.inn}}, ОГРН {{debtor.ogrn}}\nАдрес: {{debtor.address}}"
_COURT = "В {{court.name}}\nАдрес: {{court.address}}\n\nЗаявитель: " + _CREDITOR + "\n\nДолжник: " + _DEBTOR

DEFAULTS = {
    'claim': dict(stage='pretrial', title='Претензия', heading='ПРЕТЕНЗИЯ\nоб оплате задолженности', address="Кому: " + _DEBTOR + "\n\nОт кого: " + _CREDITOR,
                  body=FACTS + """

На основании статей 309, 310 Гражданского кодекса РФ требуем в течение {{pretrial_days}} календарных дней с даты получения претензии перечислить {{claim_total}} руб. по реквизитам:
{{creditor.bank_details}}

Если требование не будет исполнено, Кредитор обратится в арбитражный суд и потребует также возмещения судебных расходов.

Приложения: расчёт задолженности, копии документов, подтверждающих долг, доверенность представителя."""),
    'court_order': dict(stage='court', title='Заявление о выдаче судебного приказа', heading='ЗАЯВЛЕНИЕ\nо выдаче судебного приказа', address=_COURT,
                        body=FACTS + """

Претензия направлена Должнику {{claim_sent_on}} (подтверждение: {{claim_reference}}). Срок ответа истёк, требование не исполнено.

Требование основано на письменных документах, признано Должником и не оспаривается. Цена требования не превышает 750 000 руб. (статья 229.2 АПК РФ).

Государственная пошлина в размере {{duty}} руб. уплачена.

Прошу выдать судебный приказ о взыскании с {{debtor.name}} в пользу {{creditor.name}} {{claim_total}} руб. и расходов по уплате государственной пошлины в размере {{duty}} руб.

Приложения: документ об уплате пошлины, договор, документы об исполнении, претензия и подтверждение её отправки, расчёт, выписки из ЕГРЮЛ/ЕГРИП, доверенность."""),
    'statement_of_claim': dict(stage='court', title='Исковое заявление', heading='ИСКОВОЕ ЗАЯВЛЕНИЕ\nо взыскании задолженности', address=_COURT.replace('Заявитель', 'Истец').replace('Должник:', 'Ответчик:'),
                               body=FACTS + """

Претензия направлена {{claim_sent_on}} (подтверждение: {{claim_reference}}). Срок ответа истёк, требование не исполнено.

Цена иска: {{claim_total}} руб. Государственная пошлина: {{duty}} руб.

На основании статей 309, 310, 395 Гражданского кодекса РФ, статей 125, 126 АПК РФ прошу взыскать с {{debtor.name}} в пользу {{creditor.name}} {{claim_total}} руб. и расходы по уплате государственной пошлины в размере {{duty}} руб.

Приложения: документ об уплате пошлины, договор, документы об исполнении, претензия и подтверждение её отправки, расчёт, доказательство направления иска ответчику, выписки из ЕГРЮЛ/ЕГРИП, доверенность."""),
    'writ_request': dict(stage='enforcement', title='Заявление о выдаче исполнительного листа', heading='ЗАЯВЛЕНИЕ\nо выдаче исполнительного листа', address=_COURT,
                         body="""По делу № {{case_number}} судебный акт вступил в законную силу {{act_on}}.

Прошу выдать исполнительный лист о взыскании с {{debtor.name}} в пользу {{creditor.name}} присуждённой суммы."""),
    'bank_application': dict(stage='enforcement', title='Заявление в банк должника', heading='ЗАЯВЛЕНИЕ\nо принудительном списании денежных средств', address="В банк: {{bank.name}}\n\nВзыскатель: " + _CREDITOR + "\n\nДолжник: " + _DEBTOR,
                             body="""На основании статьи 8 Федерального закона № 229-ФЗ «Об исполнительном производстве» предъявляю исполнительный документ № {{writ_number}} от {{writ_on}} по делу № {{case_number}}.

Прошу списать со счетов Должника {{balance}} руб. и перечислить по реквизитам:
{{creditor.bank_details}}

Приложения: оригинал исполнительного документа, доверенность."""),
    'fssp_application': dict(stage='enforcement', title='Заявление в ФССП', heading='ЗАЯВЛЕНИЕ\nо возбуждении исполнительного производства', address="В отделение судебных приставов по адресу Должника\n\nВзыскатель: " + _CREDITOR + "\n\nДолжник: " + _DEBTOR,
                             body="""Предъявляю к исполнению исполнительный документ № {{writ_number}} от {{writ_on}} по делу № {{case_number}}. Сумма к взысканию: {{balance}} руб.

Прошу возбудить исполнительное производство, запросить сведения о счетах и имуществе Должника, наложить арест на денежные средства и перечислять взысканное по реквизитам:
{{creditor.bank_details}}"""),
    'fns_request': dict(stage='enforcement', title='Запрос в ФНС о счетах должника', heading='ЗАЯВЛЕНИЕ\nо предоставлении сведений о счетах должника', address="В Федеральную налоговую службу\n\nВзыскатель: " + _CREDITOR + "\n\nДолжник: " + _DEBTOR,
                        body="""На основании части 8 статьи 69 Федерального закона № 229-ФЗ прошу сообщить сведения о банковских счетах {{debtor.name}}, ИНН {{debtor.inn}}.

Исполнительный документ № {{writ_number}} от {{writ_on}} прилагается."""),
    'bailiff_complaint': dict(stage='enforcement', title='Жалоба на бездействие пристава', heading='ЖАЛОБА\nна бездействие судебного пристава-исполнителя', address="Старшему судебному приставу\n\nЗаявитель: " + _CREDITOR,
                              body="""В рамках исполнения документа № {{writ_number}} от {{writ_on}} в отношении {{debtor.name}} необходимые действия не совершаются, денежные средства не поступают.

Прошу признать бездействие незаконным и обязать принять меры принудительного исполнения."""),
    'fedresurs_notice': dict(stage='enforcement', title='Текст намерения о банкротстве', heading='УВЕДОМЛЕНИЕ\nо намерении обратиться с заявлением о банкротстве', address="Для публикации на Федресурсе",
                             body="""{{creditor.name}}, ИНН {{creditor.inn}}, намерен обратиться в арбитражный суд с заявлением о признании {{debtor.name}}, ИНН {{debtor.inn}}, несостоятельным (банкротом).

Основание: судебный акт по делу № {{case_number}}, вступивший в силу {{act_on}}. Размер требования: {{balance}} руб."""),
}
_APPLICANT = "В {{court.name}}\nАдрес: {{court.address}}\n\nЗаявитель: " + _CREDITOR + "\n\nДолжник: " + _DEBTOR + "\n\nДело № {{case_number}}"
_FSSP = "В отделение судебных приставов\n\nВзыскатель: " + _CREDITOR + "\n\nДолжник: " + _DEBTOR


def _court(title, heading, body):
    return dict(stage='court', title=title, heading=heading, address=_APPLICANT, body=body)


def _fssp(title, heading, body):
    return dict(stage='enforcement', title=title, heading=heading, address=_FSSP, body=body)


DEFAULTS.update({
    'claim_soft': dict(stage='pretrial', title='Уведомление о задолженности', heading='УВЕДОМЛЕНИЕ\nо задолженности', address=DEFAULTS['claim']['address'],
                       body=FACTS + """

Просим погасить задолженность {{claim_total}} руб. в течение {{pretrial_days}} календарных дней по реквизитам:
{{creditor.bank_details}}

Если оплата уже произведена, сообщите нам реквизиты платёжного документа."""),
    'claim_final': dict(stage='pretrial', title='Досудебная претензия (последняя)', heading='ДОСУДЕБНАЯ ПРЕТЕНЗИЯ\nоб оплате задолженности', address=DEFAULTS['claim']['address'],
                        body=FACTS + """

На основании статей 309, 310, 395 Гражданского кодекса РФ требуем в течение {{pretrial_days}} календарных дней с даты получения претензии перечислить {{claim_total}} руб. по реквизитам:
{{creditor.bank_details}}

В случае неисполнения требования Кредитор обратится в арбитражный суд с требованием о взыскании долга, процентов и судебных расходов, а после вступления судебного акта в силу предъявит его в банк Должника или службу судебных приставов.

Приложения: расчёт задолженности, копии документов, подтверждающих долг, доверенность представителя."""),
    'calculation': dict(stage='pretrial', title='Расчёт задолженности и процентов', heading='РАСЧЁТ\nзадолженности и процентов', address="Кредитор: " + _CREDITOR + "\n\nДолжник: " + _DEBTOR,
                        body="""Расчёт на {{today}}. Основной долг: {{principal}} руб.

{{calculation}}

Итого с процентами: {{claim_total}} руб."""),
    'repayment_agreement': dict(stage='pretrial', title='Соглашение о погашении задолженности', heading='СОГЛАШЕНИЕ\nо порядке погашения задолженности', address="Кредитор: " + _CREDITOR + "\n\nДолжник: " + _DEBTOR,
                                body="""Должник признаёт задолженность перед Кредитором в размере {{claim_total}} руб. по договору {{contract}}:

{{invoices}}

Должник обязуется погасить задолженность по следующему графику: ____________________.

При нарушении графика Кредитор вправе потребовать досрочного погашения всей суммы и обратиться в суд.

Подписание настоящего соглашения является признанием долга (статья 203 Гражданского кодекса РФ)."""),
    'guarantee_letter': dict(stage='pretrial', title='Гарантийное письмо (форма для должника)', heading='ГАРАНТИЙНОЕ ПИСЬМО', address="Кому: " + _CREDITOR + "\n\nОт кого: " + _DEBTOR,
                             body="""{{debtor.name}} подтверждает наличие задолженности перед {{creditor.name}} в размере {{claim_total}} руб. по договору {{contract}} и гарантирует её оплату в срок до ____________________.

{{invoices}}"""),
    'reconciliation_act': dict(stage='pretrial', title='Акт сверки', heading='АКТ СВЕРКИ\nвзаимных расчётов', address="Кредитор: " + _CREDITOR + "\n\nДолжник: " + _DEBTOR,
                               body="""Стороны подтверждают задолженность {{debtor.name}} перед {{creditor.name}} на {{today}} в размере {{balance}} руб.:

{{invoices}}"""),
    'lawsuit_after_refusal': _court('Иск после отказа или отмены приказа', 'ИСКОВОЕ ЗАЯВЛЕНИЕ\nо взыскании задолженности', FACTS + """

Судебный приказ по делу № {{case_number}} отменён либо в его выдаче отказано определением от {{act_on}}. Претензия направлена {{claim_sent_on}} (подтверждение: {{claim_reference}}).

На основании статей 309, 310, 395 Гражданского кодекса РФ, статей 125, 126 АПК РФ прошу взыскать с {{debtor.name}} в пользу {{creditor.name}} {{claim_total}} руб. и расходы по уплате государственной пошлины в размере {{duty}} руб.

Приложения: определение суда, документ об уплате пошлины, договор, документы об исполнении, претензия, расчёт, выписки из ЕГРЮЛ/ЕГРИП, доверенность."""),
    'court_clarify': _court('Уточнение исковых требований', 'ХОДАТАЙСТВО\nоб уточнении исковых требований', """На основании статьи 49 АПК РФ уточняю требования по делу № {{case_number}}: прошу взыскать с {{debtor.name}} {{claim_total}} руб.

Основной долг на {{today}}: {{principal}} руб.

{{calculation}}"""),
    'court_waiver': _court('Отказ от иска', 'ЗАЯВЛЕНИЕ\nоб отказе от исковых требований', """На основании части 2 статьи 49 и пункта 4 части 1 статьи 150 АПК РФ заявляю об отказе от исковых требований по делу № {{case_number}} и прошу прекратить производство по делу. Последствия отказа от иска известны."""),
    'court_acceleration': _court('Заявление об ускорении рассмотрения', 'ЗАЯВЛЕНИЕ\nоб ускорении рассмотрения дела', """На основании части 6 статьи 6.1 АПК РФ прошу принять меры к ускорению рассмотрения дела № {{case_number}}, которое не рассмотрено в установленный срок."""),
    'court_motivated': _court('Заявление о мотивированном решении', 'ЗАЯВЛЕНИЕ\nо составлении мотивированного решения', """На основании части 2 статьи 229 АПК РФ прошу составить мотивированное решение по делу № {{case_number}}, резолютивная часть которого принята {{act_on}}."""),
    'court_copy_request': _court('Запрос копии судебного акта', 'ЗАЯВЛЕНИЕ\nо выдаче копии судебного акта', """Прошу выдать заверенную копию судебного акта от {{act_on}} по делу № {{case_number}}."""),
    'court_duty_refund': _court('Возврат госпошлины', 'ЗАЯВЛЕНИЕ\nо возврате государственной пошлины', """На основании статьи 333.40 Налогового кодекса РФ прошу выдать справку на возврат государственной пошлины в размере {{duty}} руб., уплаченной по делу № {{case_number}}.

Приложения: документ об уплате пошлины, определение суда."""),
    'court_duty_offset': _court('Зачёт госпошлины', 'ЗАЯВЛЕНИЕ\nо зачёте государственной пошлины', """На основании пункта 6 статьи 333.40 Налогового кодекса РФ прошу зачесть уплаченную государственную пошлину в размере {{duty}} руб. в счёт пошлины, подлежащей уплате по настоящему заявлению."""),
    'court_appeal_short': _court('Краткая апелляционная жалоба', 'АПЕЛЛЯЦИОННАЯ ЖАЛОБА\n(краткая)', """Не согласен с судебным актом от {{act_on}} по делу № {{case_number}}. На основании статей 257, 260 АПК РФ прошу его отменить. Мотивированная жалоба будет представлена после получения полного текста судебного акта."""),
    'court_writ_to_fssp': _court('Направить лист в ФССП через суд', 'ХОДАТАЙСТВО\nо направлении исполнительного листа', """На основании части 3 статьи 319 АПК РФ прошу направить исполнительный лист по делу № {{case_number}} для исполнения в службу судебных приставов."""),
    'fssp_status': _fssp('Запрос о ходе производства', 'ЗАЯВЛЕНИЕ\nо предоставлении сведений о ходе исполнительного производства', """На основании статьи 50 Федерального закона № 229-ФЗ прошу предоставить сведения о ходе исполнительного производства по документу № {{writ_number}} от {{writ_on}} и о совершённых исполнительных действиях."""),
    'fssp_arrest': _fssp('Арест имущества и счетов', 'ХОДАТАЙСТВО\nоб аресте имущества должника', """На основании статей 64, 80 Федерального закона № 229-ФЗ прошу наложить арест на денежные средства и имущество {{debtor.name}} в пределах {{balance}} руб. по документу № {{writ_number}} от {{writ_on}}."""),
    'fssp_property_search': _fssp('Розыск имущества', 'ЗАЯВЛЕНИЕ\nо розыске имущества должника', """На основании статьи 65 Федерального закона № 229-ФЗ прошу объявить исполнительный розыск имущества {{debtor.name}} по документу № {{writ_number}} от {{writ_on}}. Сумма к взысканию: {{balance}} руб."""),
    'fssp_debtor_info': _fssp('Сведения об имуществе должника', 'ЗАЯВЛЕНИЕ\nо наличии у должника имущества', """Сообщаю, что у {{debtor.name}} имеется имущество, на которое может быть обращено взыскание: ____________________. Прошу совершить исполнительные действия в отношении указанного имущества."""),
    'fssp_recall': _fssp('Отзыв исполнительного документа', 'ЗАЯВЛЕНИЕ\nоб отзыве исполнительного документа', """На основании пункта 1 части 1 статьи 46 Федерального закона № 229-ФЗ прошу возвратить исполнительный документ № {{writ_number}} от {{writ_on}}."""),
    'fssp_repeat': _fssp('Повторное предъявление', 'ЗАЯВЛЕНИЕ\nо повторном предъявлении исполнительного документа', """На основании части 4 статьи 46 Федерального закона № 229-ФЗ повторно предъявляю исполнительный документ № {{writ_number}} от {{writ_on}}. Сумма к взысканию: {{balance}} руб."""),
    'fssp_paid': _fssp('Сообщение о погашении долга', 'ЗАЯВЛЕНИЕ\nо погашении задолженности', """Сообщаю, что задолженность {{debtor.name}} по документу № {{writ_number}} от {{writ_on}} погашена. Текущий остаток: {{balance}} руб."""),
    'fssp_cancel_end': _fssp('Отмена окончания производства', 'ЖАЛОБА\nна постановление об окончании исполнительного производства', """Постановление об окончании исполнительного производства по документу № {{writ_number}} от {{writ_on}} вынесено при неполном исполнении: остаток долга {{balance}} руб. На основании статьи 123 Федерального закона № 229-ФЗ прошу его отменить и возобновить производство."""),
})
KINDS = tuple(DEFAULTS)
VARIABLES = {
    'creditor.name': 'Полное наименование вашей компании', 'creditor.inn': 'Ваш ИНН', 'creditor.ogrn': 'Ваш ОГРН или ОГРНИП',
    'creditor.address': 'Ваш юридический адрес', 'creditor.bank_details': 'Ваши банковские реквизиты', 'creditor.signatory': 'Кто подписывает',
    'debtor.name': 'Наименование должника', 'debtor.inn': 'ИНН должника', 'debtor.ogrn': 'ОГРН должника', 'debtor.address': 'Адрес должника',
    'contract': 'Номер и дата договора', 'performance_documents': 'Документы об исполнении', 'invoices': 'Список счетов', 'interest_text': 'Абзац о процентах',
    'principal': 'Основной долг', 'balance': 'Текущий остаток', 'claim_total': 'Общая цена требования', 'duty': 'Госпошлина', 'today': 'Сегодняшняя дата',
    'pretrial_days': 'Дней на ответ', 'claim_sent_on': 'Дата отправки претензии', 'claim_reference': 'Трек-номер или ЭДО',
    'court.name': 'Название суда', 'court.address': 'Адрес суда', 'case_number': 'Номер дела', 'act_on': 'Дата судебного акта',
    'calculation': 'Расчёт по счетам', 'contact_person': 'Контактное лицо должника', 'writ_number': 'Номер исполнительного документа', 'writ_on': 'Дата исполнительного документа', 'bank.name': 'Банк должника',
}
_TOKEN = re.compile(r'\{\{\s*([a-z_.]+)\s*\}\}')


# Interest is left out when official rates are unavailable; the claim must still be issued.
OPTIONAL_VARIABLES = {'interest_text', 'calculation', 'contact_person'}


def missing_variables(template, values):
    text = template['address'] + template['body']
    return sorted({key for key in _TOKEN.findall(text) if key not in OPTIONAL_VARIABLES and not str(values.get(key) or '').strip()})


def unknown_variables(text):
    return sorted({key for key in _TOKEN.findall(text) if key not in VARIABLES})


def render(text, values):
    return _TOKEN.sub(lambda match: str(values.get(match.group(1), '')), text)


def build_docx(template, values):
    document = Document()
    section = document.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.left_margin, section.right_margin = Cm(2.5), Cm(2)
    section.top_margin = section.bottom_margin = Cm(2)
    normal = document.styles['Normal']
    normal.font.name = 'Times New Roman'
    normal.font.size = Pt(12)
    for line in render(template['address'], values).split('\n'):
        paragraph = document.add_paragraph(line)
        paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        paragraph.paragraph_format.space_after = Pt(0)
    document.add_paragraph()
    for line in template['heading'].split('\n'):
        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.add_run(line).bold = True
    document.add_paragraph()
    for block in render(template['body'], values).split('\n\n'):
        if block.strip():
            paragraph = document.add_paragraph(block.strip())
            paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    document.add_paragraph()
    for line in render(SIGNATURE, values).split('\n'):
        document.add_paragraph(line).paragraph_format.space_after = Pt(0)
    output = BytesIO()
    document.save(output)
    return output.getvalue()
