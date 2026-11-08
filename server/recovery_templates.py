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
KINDS = tuple(DEFAULTS)
VARIABLES = {
    'creditor.name': 'Полное наименование вашей компании', 'creditor.inn': 'Ваш ИНН', 'creditor.ogrn': 'Ваш ОГРН или ОГРНИП',
    'creditor.address': 'Ваш юридический адрес', 'creditor.bank_details': 'Ваши банковские реквизиты', 'creditor.signatory': 'Кто подписывает',
    'debtor.name': 'Наименование должника', 'debtor.inn': 'ИНН должника', 'debtor.ogrn': 'ОГРН должника', 'debtor.address': 'Адрес должника',
    'contract': 'Номер и дата договора', 'performance_documents': 'Документы об исполнении', 'invoices': 'Список счетов', 'interest_text': 'Абзац о процентах',
    'principal': 'Основной долг', 'balance': 'Текущий остаток', 'claim_total': 'Общая цена требования', 'duty': 'Госпошлина', 'today': 'Сегодняшняя дата',
    'pretrial_days': 'Дней на ответ', 'claim_sent_on': 'Дата отправки претензии', 'claim_reference': 'Трек-номер или ЭДО',
    'court.name': 'Название суда', 'court.address': 'Адрес суда', 'case_number': 'Номер дела', 'act_on': 'Дата судебного акта',
    'writ_number': 'Номер исполнительного документа', 'writ_on': 'Дата исполнительного документа', 'bank.name': 'Банк должника',
}
_TOKEN = re.compile(r'\{\{\s*([a-z_.]+)\s*\}\}')


# Interest is left out when official rates are unavailable; the claim must still be issued.
OPTIONAL_VARIABLES = {'interest_text'}


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
