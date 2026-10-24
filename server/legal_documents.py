"""Real DOCX drafts from declared facts; no e-signature or submission side effect."""
from io import BytesIO

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


TITLES={"pretrial_claim":"ПРЕТЕНЗИЯ\nоб оплате задолженности", "court_order":"ЗАЯВЛЕНИЕ\nо выдаче судебного приказа", "statement_of_claim":"ИСКОВОЕ ЗАЯВЛЕНИЕ\nо взыскании задолженности"}


def money(value):
    sign="-" if value<0 else ""
    value=abs(value)
    return sign+f"{value//100:,}".replace(","," ")+f",{value%100:02d}"


def day(value):
    return ".".join(reversed(str(value).split("-")))


def validate_document_facts(kind,facts,evidence,calculation):
    if kind not in TITLES:raise ValueError("Неизвестный вид документа")
    missing=[]
    for side in ("creditor","debtor"):
        party=facts[side]
        for field in ("name","inn","ogrn","address"):
            if not party.get(field):missing.append(f"{side}.{field}")
        if party.get("kind")=="sole_proprietor" and (not party.get("birth_on") or not party.get("birth_place")) and not party.get("birth_details_unknown"):
            missing.append(f"{side}: дата/место рождения либо отметка, что они неизвестны")
    if not facts["creditor"].get("bank_details"):missing.append("creditor.bank_details")
    for field in ("contract_number","contract_date","obligation_description","performance_description","due_basis","legal_basis"):
        if not facts.get(field):missing.append(field)
    if not facts.get("business_debt_confirmed"):missing.append("подтверждение предпринимательского характера долга")
    if not facts.get("special_regimes_checked"):missing.append("проверка мораториев, банкротства, специальных правил и давности")
    kinds={row["kind"] for row in evidence}
    for field in ("contract","performance"):
        if field not in kinds:missing.append("доказательство: "+field)
    if kind!="pretrial_claim":
        for field in ("court_name","court_address","jurisdiction_basis"):
            if not facts.get(field):missing.append(field)
    if kind=="court_order" and (not facts.get("undisputed") or not calculation["order_eligible"]):
        raise ValueError("Судебный приказ: нужны бесспорное документальное требование и общая цена не более 750 000 ₽")
    if kind=="statement_of_claim" and not facts.get("_pretrial",{}).get("sent_on") and facts.get("pretrial_days",30)>0:
        missing.append("подтверждённое направление претензии")
    if missing:raise ValueError("Заполните юридически значимые факты: "+", ".join(missing))
    if calculation["total_claim_amount"]<=0:raise ValueError("Нет непогашенного денежного требования")


def build_docx(kind,facts,calculation,evidence,*,version,created_on):
    validate_document_facts(kind,facts,evidence,calculation)
    doc=Document()
    section=doc.sections[0]
    section.page_width=Cm(21);section.page_height=Cm(29.7)
    section.left_margin=Cm(2.5);section.right_margin=Cm(2)
    section.top_margin=Cm(2);section.bottom_margin=Cm(2)
    normal=doc.styles["Normal"]
    normal.font.name="Times New Roman";normal.font.size=Pt(11)
    normal.paragraph_format.space_after=Pt(2)
    normal.paragraph_format.line_spacing=1
    normal.paragraph_format.widow_control=True
    for name in ("Heading 1","Heading 2"):
        style=doc.styles[name];style.font.name="Times New Roman";style.font.size=Pt(12)
        style.font.color.rgb=RGBColor(0,0,0)
        for key in ("asciiTheme","hAnsiTheme","eastAsiaTheme","cstheme"):
            if style.element.rPr.rFonts is not None:style.element.rPr.rFonts.attrib.pop(qn("w:"+key),None)
        style.font.bold=True;style.paragraph_format.keep_with_next=True
        style.paragraph_format.space_before=Pt(8)
        style.paragraph_format.space_after=Pt(3)
    doc.core_properties.title=TITLES[kind].replace("\n"," ")
    doc.core_properties.author="Mandato"
    doc.core_properties.subject="Договорное денежное требование B2B"
    doc.core_properties.comments=""
    creditor,debtor=facts["creditor"],facts["debtor"]
    if kind!="pretrial_claim":
        doc.add_paragraph(facts["court_name"])
        doc.add_paragraph(facts["court_address"])
    for label,party in (("Кредитор" if kind=="pretrial_claim" else "Взыскатель" if kind=="court_order" else "Истец",creditor),("Должник" if kind!="statement_of_claim" else "Ответчик",debtor)):
        p=doc.add_paragraph();p.add_run(label+": ").bold=True;p.add_run(party["name"])
        doc.add_paragraph(party["address"])
        doc.add_paragraph(f"ИНН {party['inn']}; {'ОГРНИП' if party.get('kind')=='sole_proprietor' else 'ОГРН'} {party['ogrn']}")
        if party.get("birth_on") or party.get("birth_place"):
            doc.add_paragraph(f"Дата и место рождения: {day(party['birth_on']) if party.get('birth_on') else 'неизвестно'}, {party.get('birth_place') or 'неизвестно'}")
        elif party.get("kind")=="sole_proprietor" and party.get("birth_details_unknown"):
            doc.add_paragraph("Дата и место рождения взыскателю неизвестны.")
        contact="; ".join(value for value in (party.get("email"),party.get("phone")) if value)
        if contact:doc.add_paragraph(contact)
    if kind!="pretrial_claim":
        doc.add_paragraph(f"Цена требования: {money(calculation['total_claim_amount'])} ₽")
        fee=calculation["fee_order_amount"] if kind=="court_order" else calculation["fee_claim_amount"]
        doc.add_paragraph(f"Государственная пошлина: {money(fee)} ₽")
    heading=doc.add_paragraph()
    heading.alignment=WD_ALIGN_PARAGRAPH.CENTER
    run=heading.add_run(TITLES[kind]);run.bold=True;run.font.size=Pt(14)
    doc.add_paragraph(f"Дата составления: {day(created_on)}. Версия документа: {version}.")
    doc.add_heading("Обстоятельства и основание требования",level=1)
    doc.add_paragraph(f"Между {creditor['name']} и {debtor['name']} заключён договор № {facts['contract_number']} от {day(facts['contract_date'])}.")
    doc.add_paragraph(facts["obligation_description"])
    doc.add_paragraph(facts["performance_description"])
    if facts.get("_invoice"):
        invoice=facts["_invoice"]
        doc.add_paragraph(f"Счёт № {invoice['number']} от {day(invoice['issued_on'])}; срок оплаты — {day(invoice['due_on'])}.")
    doc.add_paragraph("Срок исполнения денежного обязательства: "+facts["due_basis"])
    doc.add_paragraph(f"По состоянию на {day(calculation['through_on'])} непогашенный основной долг составляет {money(calculation['principal_amount'])} ₽. Расчёт учитывает отражённые в реестре погашения и корректировки.")
    doc.add_paragraph(facts["legal_basis"])
    if calculation["penalty_amount"]:
        doc.add_paragraph(f"Договорная неустойка: {money(calculation['penalty_amount'])} ₽. Основание: {calculation['penalty_basis']}.")
    if calculation["interest_amount"]:
        doc.add_paragraph(f"Проценты за просрочку исполнения денежного обязательства по статье 395 ГК РФ: {money(calculation['interest_amount'])} ₽. Применены ставки и периоды из расчёта ниже.")
    if calculation.get("combination_basis"):
        doc.add_paragraph("Основание выбранного сочетания санкций: "+calculation["combination_basis"])
    if kind!="pretrial_claim":
        doc.add_paragraph("Подсудность: "+facts["jurisdiction_basis"])
    pretrial=facts.get("_pretrial",{})
    if pretrial.get("sent_on"):
        doc.add_paragraph(f"Ранее претензия направлена {day(pretrial['sent_on'])}; основание подтверждения: {pretrial.get('reference','')}. Срок досудебного порядка: {facts['pretrial_days']} календарных дней; основание: {facts['pretrial_basis']}.")
    doc.add_heading("Требования",level=1)
    if kind=="pretrial_claim":
        doc.add_paragraph(f"Просим погасить основной долг {money(calculation['principal_amount'])} ₽ и начисленные санкции {money(calculation['interest_amount']+calculation['penalty_amount'])} ₽, всего {money(calculation['total_claim_amount'])} ₽, и направить мотивированный ответ в течение {facts['pretrial_days']} календарных дней с учётом установленного законом или договором порядка.")
        doc.add_paragraph("Реквизиты кредитора для оплаты: "+creditor["bank_details"])
        doc.add_paragraph("При неурегулировании спора кредитор намерен обратиться в компетентный суд с требованием о взыскании долга и судебных расходов.")
    else:
        verb="Выдать судебный приказ о взыскании" if kind=="court_order" else "Взыскать"
        doc.add_paragraph(f"{verb} с {debtor['name']} в пользу {creditor['name']} основной долг {money(calculation['principal_amount'])} ₽, неустойку {money(calculation['penalty_amount'])} ₽ и проценты {money(calculation['interest_amount'])} ₽, всего {money(calculation['total_claim_amount'])} ₽.")
        doc.add_paragraph(f"Взыскать расходы по уплате государственной пошлины в размере {money(fee)} ₽ при подтверждении её уплаты.")
        doc.add_paragraph("Банковские реквизиты взыскателя: "+creditor["bank_details"])
    doc.add_heading("Перечень доказательств и приложений",level=1)
    for index,row in enumerate(evidence,1):
        doc.add_paragraph(f"{index}. {row['title']}: {row['reference']} (дата {day(row['occurred_on'])}).")
    doc.add_paragraph(f"{len(evidence)+1}. Расчёт суммы требований по состоянию на {day(calculation['through_on'])}, приведённый ниже.")
    if kind!="pretrial_claim":
        doc.add_paragraph("При ручной подаче приложить подтверждение уплаты пошлины/льготы, направления копий заявления и приложений другой стороне, актуальные регистрационные сведения, документы о полномочиях и квалификации подписанта в применимом объёме.")
    doc.add_paragraph("Подпись уполномоченного лица: _______________ / __________________________")
    doc.add_page_break()
    doc.add_heading("Расчёт денежного требования",level=1)
    doc.add_paragraph(f"Первоначальный основной долг: {money(calculation['original_principal'])} ₽. Период начисления: {day(calculation['from_on'])} — {day(calculation['through_on'])}.")
    table=doc.add_table(rows=1,cols=6);table.style="Table Grid"
    headings=("Период","Дни","Основной долг, ₽","Ставка / год","395, ₽","Неустойка, ₽")
    for cell,text in zip(table.rows[0].cells,headings):cell.text=text
    repeat=OxmlElement("w:tblHeader");table.rows[0]._tr.get_or_add_trPr().append(repeat)
    for row in calculation["line_items"]:
        values=(day(row["from_on"])+"\n"+day(row["to_on"]),str(row["days"]),money(row["principal_amount"]),row["annual_percent"].replace(".",",")+"% / "+str(row["denominator"]),money(row["interest_amount"]),money(row["penalty_amount"]))
        cells=table.add_row().cells
        for cell,text in zip(cells,values):cell.text=text
        if row["excluded"]:
            doc.add_paragraph(f"Исключён период {day(row['from_on'])} — {day(row['to_on'])}: {row['basis']}.")
    for row in table.rows:
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.space_after=Pt(3)
                for run in paragraph.runs:run.font.size=Pt(9)
    doc.add_paragraph("Методика: фактические календарные дни; год 365/366 дней. День погашения включён; уменьшение базы применяется со следующего дня. Проценты на санкции не начисляются. Сумма точных начислений округляется до копейки по ROUND_HALF_UP; пошлина — до полного рубля.")
    doc.add_paragraph(f"Основной долг: {money(calculation['principal_amount'])} ₽. Проценты: {money(calculation['interest_amount'])} ₽. Неустойка: {money(calculation['penalty_amount'])} ₽. Всего: {money(calculation['total_claim_amount'])} ₽.")
    if calculation["rounding_difference_interest"] or calculation["rounding_or_cap_penalty"]:
        doc.add_paragraph(f"Корректировка суммы отображённых строк из-за итогового округления/лимита: проценты {money(calculation['rounding_difference_interest'])} ₽; неустойка {money(calculation['rounding_or_cap_penalty'])} ₽.")
    doc.add_paragraph("Версия правил: "+calculation["rules_version"]+". История ставок: "+calculation["rates_version"]+".")
    doc.add_paragraph("Источник ключевой ставки: "+calculation["rates_source"])
    if calculation.get("override_reason"):doc.add_paragraph("Основание иной истории ставок: "+calculation["override_reason"])
    stream=BytesIO();doc.save(stream)
    return stream.getvalue()
