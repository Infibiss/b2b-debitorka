"""Builds docs/finance/Mandato_finance_model.xlsx with live formulas."""
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter as L

OUT = r'M:\mandato\docs\finance\Mandato_finance_model.xlsx'
FONT = 'Arial'
BLUE, BLACK, GREEN = Font(name=FONT, size=10, color='0000FF'), Font(name=FONT, size=10), Font(name=FONT, size=10, color='008000')
BOLD = Font(name=FONT, size=10, bold=True)
TITLE = Font(name=FONT, size=14, bold=True)
HEAD = PatternFill('solid', fgColor='183D31')
HEADF = Font(name=FONT, size=10, bold=True, color='FFFFFF')
KEY = PatternFill('solid', fgColor='FFFF00')
RUB = '#,##0;(#,##0);-'
PCT = '0.0%;(0.0%);-'

wb = Workbook()
inp = wb.active
inp.title = 'Inputs'
inp['A1'] = 'Mandato: допущения модели (₽, без НДС, если не указано иное)'
inp['A1'].font = TITLE
inp['A2'] = 'Синий текст: допущения, их можно менять. Чёрный: формулы. Зелёный: ссылки на другой лист. Жёлтая заливка: ключевые гипотезы, которые нужно проверить с экспертами.'
inp['A2'].font = BLACK
for col, text in enumerate(['Параметр', 'Базовый', 'Стресс', 'Рост', 'Источник или обоснование'], 1):
    c = inp.cell(4, col, text)
    c.font, c.fill = HEADF, HEAD

ROWS = [
    ('Тарифы', None),
    ('price_team', 'Подписка «Бизнес», ₽/мес с НДС', 32900, 32900, 32900, RUB, 'Решение 13.11.2026: досудебная работа, заказные письма и до 2 судебных пакетов в месяц включены.', 0),
    ('price_scale', 'Подписка «Объём», ₽/мес с НДС', 69900, 69900, 69900, RUB, 'Решение 13.11.2026: всё включено, письма тоже. ЮРРОБОТ Базовый 50 000 ₽/мес без НДС и свой юрист.', 0),
    ('mix_start', 'Доля клиентов «Разовый долг» (без подписки)', 0.40, 0.60, 0.30, PCT, 'Гипотеза: вход через банк, многие начинают с одного долга.', 1),
    ('mix_team', 'Доля клиентов «Бизнес»', 0.50, 0.35, 0.55, PCT, 'Гипотеза: основной сегмент, поставщики с отсрочкой платежа.', 1),
    ('pretrial_fee', '«Разовый долг»: % с денег до суда', 0.07, 0.07, 0.07, PCT, 'server/fee_tariff.json. Рынок: 3–10% (см. Benchmarks). На подписках 0%.', 0),
    ('order_fee', '«Разовый долг»: пакет судебного приказа, ₽ с НДС', 9900, 9900, 9900, RUB, 'Юристы: от 20 000 ₽ (консультации). На подписках входит в цену.', 0),
    ('lawsuit_fee', '«Разовый долг»: пакет иска, ₽ с НДС', 14900, 14900, 14900, RUB, 'Юристы: от 25 000 ₽ (консультации). На подписках входит в цену.', 0),
    ('financing_fee', 'Агентское вознаграждение за финансирование, % суммы', 0.01, 0.005, 0.015, PCT, 'Гипотеза. Договора с партнёром пока нет.', 1),
    ('Дела', None),
    ('cases_start', 'Долгов в год у клиента «Разовый долг»', 3, 2, 4, '0.0', 'Сегмент разовых долгов (расчёт сегментов 13.11.2026).', 1),
    ('cases_team', 'Долгов в год у клиента «Бизнес»', 20, 12, 24, '0.0', 'Поставщик с потоком: 10–50 долгов в год.', 1),
    ('cases_scale', 'Долгов в год у клиента «Объём»', 100, 60, 120, '0.0', 'Компании со своим юристом: 100+ дел в год.', 1),
    ('avg_debt', 'Средний долг, ₽', 400000, 300000, 500000, RUB, 'Юристы: обычно от 100 тыс. ₽. Сегменты: 300–500 тыс. ₽.', 1),
    ('paid_pretrial', 'Доля дел, оплаченных до суда', 0.30, 0.20, 0.35, PCT, 'Презентация 30%. Юристы: долю предсказать нельзя.', 1),
    ('partial', 'Средняя доля долга, которая реально поступает', 0.85, 0.70, 0.90, PCT, 'Гипотеза: частичные оплаты. В старой модели было 100%.', 1),
    ('to_court', 'Доля неоплаченных дел, которые клиент ведёт в суд', 0.60, 0.40, 0.70, PCT, 'В старой модели 100%. Клиент решает сам, часть долгов не стоит суда (меньше 50 тыс. ₽).', 1),
    ('order_share', 'Доля судебных дел через приказ', 0.60, 0.50, 0.65, PCT, 'До 750 тыс. ₽ и бесспорно: ст. 229.2 АПК.', 1),
    ('order_cancel', 'Доля приказов, которые отменяются и идут в иск', 0.30, 0.45, 0.25, PCT, 'Презентация 30%. Статистики у юристов нет.', 1),
    ('lag_months', 'Лаг от старта дела до выручки, мес', 3, 4, 2, '0', 'Юрист: взыскание в суде от 3 месяцев.', 0),
    ('Себестоимость', None),
    ('lawyer_rate', 'Час юриста на проверку, ₽', 2500, 3500, 2500, RUB, 'Гипотеза: аутсорс-ставка.', 1),
    ('lawyer_hours', 'Часов юриста на судебный пакет', 1.5, 2.5, 1.0, '0.0', 'Юрист: простое дело 1–2 часа, в презентации цель 1 час.', 0),
    ('case_var', 'ИИ, почта, связь, заказные письма на дело, ₽', 1500, 2500, 1200, RUB, 'Токены YandexGPT ≈ 50 ₽ на долг, два заказных письма ≈ 1 400 ₽, звонки и SMS.', 0),
    ('own_lawyer', 'Доля судебных пакетов «Объёма», которые проверяет свой юрист клиента', 0.8, 0.5, 0.9, PCT, 'У этого сегмента обычно есть юрист.', 0),
    ('cloud_client', 'Облако на клиента, ₽/мес', 800, 1200, 600, RUB, 'Презентация 1 000 ₽.', 0),
    ('Рост и канал', None),
    ('pilot_clients', 'Клиентов в пилоте банка (февраль–май 2027)', 40, 20, 40, '0', 'Презентация. Договора с банком пока нет.', 1),
    ('pilot_cases', 'Дел в месяц во время пилота', 60, 25, 60, '0', 'Презентация: 240 дел за 4 месяца.', 0),
    ('pilot_convert', 'Доля клиентов пилота, перешедших на платный тариф', 0.75, 0.40, 0.80, PCT, 'Презентация 30 из 40.', 1),
    ('new_2027', 'Новых клиентов в месяц, 2027 (с июня)', 3, 1, 5, '0', 'Было 5. Снижено, пока банк не подписан.', 1),
    ('new_2028', 'Новых клиентов в месяц, 2028', 7, 3, 10, '0', 'Было 10.', 1),
    ('new_2029', 'Новых клиентов в месяц, 2029', 12, 5, 15, '0', 'Было 15.', 1),
    ('bank_share', 'Доля клиентов из канала банка', 0.70, 0.50, 0.70, PCT, 'Гипотеза.', 1),
    ('bank_rev', 'Комиссия банка-партнёра, % выручки его клиентов', 0.20, 0.30, 0.15, PCT, 'В старой модели 0%. Банк почти наверняка попросит долю.', 1),
    ('cac_bank', 'Стоимость привлечения через банк, ₽', 15000, 30000, 15000, RUB, 'Презентация 15 000 ₽: реалистично только через канал банка.', 1),
    ('cac_direct', 'Стоимость прямого привлечения, ₽', 70000, 120000, 60000, RUB, 'В старой модели не было. Гипотеза для B2B-продаж с участием менеджера.', 1),
    ('cac_self', 'Привлечение клиента «Разовый долг», ₽', 3000, 6000, 2000, RUB, 'Самостоятельная регистрация по ссылке из банка, без менеджера.', 1),
    ('churn', 'Отток в месяц', 0.03, 0.05, 0.025, PCT, 'Презентация 3% и 5%.', 1),
    ('Команда и налоги (₽/мес)', None),
    ('payroll_2027', 'Ядро команды, 2027', 500000, 400000, 500000, RUB, 'Презентация 500 тыс. Основатели на минимуме и юрист-координатор.', 1),
    ('payroll_2028', 'Ядро команды, 2028', 700000, 500000, 800000, RUB, 'Презентация 700 тыс. Плюс разработчик.', 1),
    ('payroll_2029', 'Ядро команды, 2029', 1000000, 600000, 1200000, RUB, 'Было 900 тыс. Плюс продажи.', 1),
    ('cs_per', 'Клиентов на подписке на одного менеджера поддержки', 60, 40, 70, '0', '«Разовый долг» обслуживается сам, без менеджера. Гипотеза.', 1),
    ('cs_salary', 'Оклад менеджера поддержки, ₽/мес', 110000, 110000, 110000, RUB, 'Гипотеза.', 0),
    ('contrib', 'Страховые взносы', 0.30, 0.30, 0.30, PCT, 'Консервативно: 30%. Льготы МСП и IT уточнить с бухгалтером.', 0),
    ('opex_2027', 'Прочие расходы, 2027', 120000, 150000, 120000, RUB, 'Бухгалтерия, юрист, 152-ФЗ, сервисы, резерв.', 0),
    ('opex_2028', 'Прочие расходы, 2028', 200000, 220000, 220000, RUB, 'В старой модели отсутствовали.', 0),
    ('opex_2029', 'Прочие расходы, 2029', 300000, 300000, 350000, RUB, 'В старой модели отсутствовали.', 0),
    ('vat', 'НДС внутри цены', 0.05, 0.05, 0.05, PCT, 'Презентация 5%. Порог 20 млн ₽ и поэтапное снижение (425-ФЗ) уточнить с бухгалтером.', 0),
    ('usn', 'УСН «доходы»', 0.06, 0.06, 0.06, PCT, 'Презентация 6%. Без уменьшения на взносы: консервативно.', 0),
    ('ar_months', 'Дебиторка клиентов перед нами, мес выручки', 1, 1.5, 1, '0.0', 'В старой модели только разница денег и прибыли.', 0),
    ('grant', 'Внешнее финансирование в феврале 2027, ₽', 1000000, 0, 1000000, RUB, 'Презентация: запрос к банку 1 млн ₽.', 1),
]
ref = {}
row = 5
for item in ROWS:
    if item[1] is None:
        inp.cell(row, 1, item[0]).font = BOLD
        row += 1
        continue
    key, label, base, stress, up, fmt, note, key_flag = item
    inp.cell(row, 1, label).font = BLACK
    for col, value in zip((2, 3, 4), (base, stress, up)):
        c = inp.cell(row, col, value)
        c.font, c.number_format = BLUE, fmt
        if key_flag:
            c.fill = KEY
    inp.cell(row, 5, note).font = BLACK
    ref[key] = row
    row += 1
inp.column_dimensions['A'].width = 58
for col in 'BCD':
    inp.column_dimensions[col].width = 13
inp.column_dimensions['E'].width = 90
inp.freeze_panes = 'B5'


def I(key, col):
    return f"Inputs!${col}${ref[key]}"


# Unit economics, one column per scenario.
unit = wb.create_sheet('Unit')
unit['A1'] = 'Экономика одного дела и клиента (₽, без НДС)'
unit['A1'].font = TITLE
for col, text in enumerate(['Показатель', 'Базовый', 'Стресс', 'Рост'], 1):
    c = unit.cell(3, col, text)
    c.font, c.fill = HEADF, HEAD
U = {}
UNIT = [
    ('net', 'Коэффициент без НДС', lambda c: f"=1/(1+{I('vat', c)})", '0.000'),
    ('mix_scale', 'Доля клиентов «Объём»', lambda c: f"=1-{I('mix_start', c)}-{I('mix_team', c)}", PCT),
    ('recovered', 'Поступило до суда в среднем на долг', lambda c: f"={I('avg_debt', c)}*{I('paid_pretrial', c)}*{I('partial', c)}", RUB),
    ('court_rate', 'Вероятность суда', lambda c: f"=(1-{I('paid_pretrial', c)})*{I('to_court', c)}", PCT),
    ('packages', 'Судебных пакетов на долг', lambda c: f"={{court_rate}}*(1+{I('order_share', c)}*{I('order_cancel', c)})", '0.00'),
    ('pre_fee', '«Разовый долг»: 7% до суда на долг', lambda c: f"={{recovered}}*{I('pretrial_fee', c)}*{{net}}", RUB),
    ('pkg_fee', '«Разовый долг»: пакеты на долг', lambda c: f"={{court_rate}}*({I('order_share', c)}*{I('order_fee', c)}+((1-{I('order_share', c)})+{I('order_share', c)}*{I('order_cancel', c)})*{I('lawsuit_fee', c)})*{{net}}", RUB),
    ('case_rev', '«Разовый долг»: выручка на долг', lambda c: "={pre_fee}+{pkg_fee}", RUB),
    ('case_cogs', 'Себестоимость долга (письма, ИИ, юрист на пакеты)', lambda c: f"={I('case_var', c)}+{{packages}}*{I('lawyer_rate', c)}*{I('lawyer_hours', c)}", RUB),
    ('scale_cogs', 'Себестоимость долга «Объёма» (пакеты чаще проверяет свой юрист)', lambda c: f"={I('case_var', c)}+{{packages}}*{I('lawyer_rate', c)}*{I('lawyer_hours', c)}*(1-{I('own_lawyer', c)})", RUB),
    ('rev_start', 'Выручка с клиента «Разовый долг», ₽/мес', lambda c: f"={I('cases_start', c)}/12*{{case_rev}}", RUB),
    ('rev_team', 'Выручка с клиента «Бизнес», ₽/мес', lambda c: f"={I('price_team', c)}*{{net}}", RUB),
    ('rev_scale', 'Выручка с клиента «Объём», ₽/мес', lambda c: f"={I('price_scale', c)}*{{net}}", RUB),
    ('arpa', 'Средняя выручка с клиента, ₽/мес', lambda c: f"={I('mix_start', c)}*{{rev_start}}+{I('mix_team', c)}*{{rev_team}}+{{mix_scale}}*{{rev_scale}}", RUB),
    ('sub_arpa', 'Из неё подписка, ₽/мес', lambda c: f"={I('mix_team', c)}*{{rev_team}}+{{mix_scale}}*{{rev_scale}}", RUB),
    ('cases_avg', 'Долгов на клиента в год, в среднем', lambda c: f"={I('mix_start', c)}*{I('cases_start', c)}+{I('mix_team', c)}*{I('cases_team', c)}+{{mix_scale}}*{I('cases_scale', c)}", '0.0'),
    ('cases_paid_share', 'Доля долгов, оплачиваемых поштучно («Разовый долг»)', lambda c: f"={I('mix_start', c)}*{I('cases_start', c)}/{{cases_avg}}", PCT),
    ('cogs_m', 'Себестоимость долгов на клиента, ₽/мес', lambda c: f"=({I('mix_start', c)}*{I('cases_start', c)}+{I('mix_team', c)}*{I('cases_team', c)})/12*{{case_cogs}}+{{mix_scale}}*{I('cases_scale', c)}/12*{{scale_cogs}}", RUB),
    ('monthly', 'Вклад клиента в месяц, после переменных расходов и доли банка', lambda c: f"={{arpa}}*(1-{I('bank_share', c)}*{I('bank_rev', c)})-{{cogs_m}}-{I('cloud_client', c)}", RUB),
    ('cac', 'Средняя стоимость привлечения', lambda c: f"={I('mix_start', c)}*{I('cac_self', c)}+(1-{I('mix_start', c)})*({I('bank_share', c)}*{I('cac_bank', c)}+(1-{I('bank_share', c)})*{I('cac_direct', c)})", RUB),
    ('payback', 'Окупаемость привлечения, месяцев', lambda c: "=IF({monthly}>0,{cac}/{monthly},0)", '0.0'),
    ('life', 'Срок жизни клиента, месяцев', lambda c: f"=1/{I('churn', c)}", '0.0'),
    ('ltv', 'LTV (вклад за срок жизни)', lambda c: "={monthly}*{life}", RUB),
    ('ltv_cac', 'LTV / CAC', lambda c: "=IF({cac}>0,{ltv}/{cac},0)", '0.0x'),
]
for i, (key, label, build, fmt) in enumerate(UNIT, 4):
    U[key] = i
for i, (key, label, build, fmt) in enumerate(UNIT, 4):
    unit.cell(i, 1, label).font = BLACK
    for col in 'BCD':
        formula = build(col)
        for k, v in U.items():
            formula = formula.replace('{' + k + '}', f'{col}{v}')
        c = unit[f'{col}{i}']
        c.value, c.number_format, c.font = formula, fmt, GREEN if 'Inputs!' in formula else BLACK
unit.column_dimensions['A'].width = 62
for col in 'BCD':
    unit.column_dimensions[col].width = 14

MONTHS = 36
LINES = [
    ('year', 'Год'), ('new', 'Новые клиенты'), ('pilot_in', 'Переход из пилота'), ('churned', 'Ушло'), ('clients', 'Платящие клиенты, конец месяца'),
    ('cases', 'Новых долгов в работе'), ('cases_paid', 'Из них оплачиваются поштучно'), ('sub', 'Подписка'), ('case_rev', '«Разовый долг»: 7% и пакеты'), ('fin', 'Вознаграждение за финансирование'), ('rev', 'Выручка без НДС'),
    ('bank', 'Доля банка-партнёра'), ('cogs', 'Себестоимость дел'), ('cloud', 'Облако'), ('cac', 'Привлечение клиентов'), ('payroll', 'ФОТ'), ('contrib', 'Страховые взносы'), ('opex', 'Прочие расходы'),
    ('ebt', 'Прибыль до налога'), ('tax', 'УСН'), ('profit', 'Чистая прибыль'), ('ar', 'Дебиторка клиентов'), ('cashflow', 'Денежный поток'), ('funding', 'Внешнее финансирование'), ('cash', 'Остаток денег, конец месяца'),
]
RF = {key: i for i, (key, _) in enumerate(LINES, 4)}
FIRST = 2
LAST = FIRST + MONTHS - 1


def monthly(name, col):
    ws = wb.create_sheet(name)
    ws['A1'] = f'Помесячный план: {name}'
    ws['A1'].font = TITLE
    ws.cell(3, 1, 'Месяц').font = BOLD
    for key, label in LINES:
        ws.cell(RF[key], 1, label).font = BOLD if key in ('clients', 'rev', 'profit', 'cash') else BLACK
    ws.column_dimensions['A'].width = 40
    for m in range(MONTHS):
        x = FIRST + m
        c, p = L(x), L(x - 1)
        year = 2027 + m // 12
        month = m % 12 + 1
        h = ws.cell(3, x, f'{month:02d}.{year}')
        h.font, h.fill = HEADF, HEAD
        ws.column_dimensions[c].width = 12
        R = lambda k: f'{c}{RF[k]}'
        P = lambda k: f'{p}{RF[k]}'
        ws[R('year')] = year
        ws[R('year')].number_format = '0'
        by_year = lambda stem: I(f'{stem}_{year}', col)
        ws[R('new')] = f"={by_year('new')}" if (year > 2027 or month >= 6) else 0
        ws[R('pilot_in')] = f"={I('pilot_clients', col)}*{I('pilot_convert', col)}" if (year, month) == (2027, 6) else 0
        ws[R('churned')] = (f"={P('clients')}*{I('churn', col)}" if m else 0)
        ws[R('clients')] = f"={P('clients') if m else 0}+{R('new')}+{R('pilot_in')}-{R('churned')}"
        pilot = year == 2027 and 2 <= month <= 5
        ws[R('cases')] = f"={I('pilot_cases', col)}" if pilot else f"={R('clients')}*Unit!${col}${U['cases_avg']}/12"
        # The pilot runs on «Разовый долг» terms: no subscription, payment per result.
        ws[R('cases_paid')] = f"={R('cases')}" if pilot else f"={R('cases')}*Unit!${col}${U['cases_paid_share']}"
        ws[R('sub')] = f"={R('clients')}*Unit!${col}${U['sub_arpa']}"
        # Results revenue follows the case start by the configured lag.
        ws[R('case_rev')] = f"=IF({m + 1}>{I('lag_months', col)},INDEX(${L(FIRST)}${RF['cases_paid']}:${L(LAST)}${RF['cases_paid']},1,{m + 1}-{I('lag_months', col)})*Unit!${col}${U['case_rev']},0)"
        ws[R('fin')] = f"={R('cases')}*0.05*{I('avg_debt', col)}*0.4*{I('financing_fee', col)}*Unit!${col}${U['net']}"
        ws[R('rev')] = f"={R('sub')}+{R('case_rev')}+{R('fin')}"
        ws[R('bank')] = f"=-({R('sub')}+{R('case_rev')})*{I('bank_share', col)}*{I('bank_rev', col)}"
        ws[R('cogs')] = f"=-IF({R('clients')}>0,{R('clients')}*Unit!${col}${U['cogs_m']},{R('cases')}*Unit!${col}${U['case_cogs']})" if not pilot else f"=-{R('cases')}*Unit!${col}${U['case_cogs']}"
        ws[R('cloud')] = f"=-{R('clients')}*{I('cloud_client', col)}"
        pilot_cac = f"{I('pilot_clients', col)}*{I('cac_bank', col)}" if (year, month) == (2027, 2) else '0'
        ws[R('cac')] = f"=-({R('new')}*Unit!${col}${U['cac']}+{pilot_cac})"
        ws[R('payroll')] = f"=-({by_year('payroll')}+{R('clients')}*(1-{I('mix_start', col)})/{I('cs_per', col)}*{I('cs_salary', col)})"
        ws[R('contrib')] = f"={R('payroll')}*{I('contrib', col)}"
        ws[R('opex')] = f"=-{by_year('opex')}"
        ws[R('ebt')] = f"={R('rev')}+SUM({c}{RF['bank']}:{c}{RF['opex']})"
        ws[R('tax')] = f"=-{R('rev')}*{I('usn', col)}"
        ws[R('profit')] = f"={R('ebt')}+{R('tax')}"
        ws[R('ar')] = f"={R('rev')}*{I('ar_months', col)}"
        ws[R('cashflow')] = f"={R('profit')}-({R('ar')}-{P('ar') if m else 0})"
        ws[R('funding')] = f"={I('grant', col)}" if (year, month) == (2027, 2) else 0
        ws[R('cash')] = f"={P('cash') if m else 0}+{R('cashflow')}+{R('funding')}"
        for key, _ in LINES:
            cell = ws[R(key)]
            if key != 'year':
                cell.number_format = '#,##0.0;(#,##0.0);-' if key in ('new', 'pilot_in', 'churned', 'clients', 'cases', 'cases_paid') else RUB
            value = cell.value
            cell.font = GREEN if isinstance(value, str) and ('Inputs!' in value or 'Unit!' in value) else BOLD if key in ('clients', 'rev', 'profit', 'cash') else BLACK
    ws.freeze_panes = 'B4'
    return ws


NAMES = [('Base', 'B', 'Базовый'), ('Stress', 'C', 'Стресс'), ('Upside', 'D', 'Рост')]
for name, col, _ in NAMES:
    monthly(name, col)

s = wb.create_sheet('Summary', 0)
s['A1'] = 'Mandato: финансовая модель 2027–2029'
s['A1'].font = TITLE
s['A2'] = 'Все числа считаются из листа Inputs. Это гипотезы команды, а не прогноз: договоров с банком и партнёрами пока нет.'
s['A2'].font = BLACK
s.column_dimensions['A'].width = 46
METRICS = [('Клиенты на конец года', 'clients', 'end', '0'), ('Выручка без НДС, ₽', 'rev', 'sum', RUB), ('Чистая прибыль, ₽', 'profit', 'sum', RUB), ('Денежный поток, ₽', 'cashflow', 'sum', RUB), ('Остаток денег на конец года, ₽', 'cash', 'end', RUB)]
row = 4
for name, col, label in NAMES:
    s.cell(row, 1, label).font = HEADF
    s.cell(row, 1).fill = HEAD
    for i, year in enumerate((2027, 2028, 2029)):
        c = s.cell(row, 2 + i, str(year))
        c.font, c.fill = HEADF, HEAD
    row += 1
    for metric, key, mode, fmt in METRICS:
        s.cell(row, 1, metric).font = BLACK
        for i in range(3):
            first, last = L(FIRST + 12 * i), L(FIRST + 12 * i + 11)
            formula = f"={name}!{last}{RF[key]}" if mode == 'end' else f"=SUM({name}!{first}{RF[key]}:{last}{RF[key]})"
            c = s.cell(row, 2 + i, formula)
            c.font, c.number_format = GREEN, fmt
        row += 1
    s.cell(row, 1, 'Минимальный остаток денег (потребность в финансировании)').font = BOLD
    c = s.cell(row, 2, f"=MIN({name}!{L(FIRST)}{RF['cash']}:{L(LAST)}{RF['cash']})")
    c.font, c.number_format = GREEN, RUB
    row += 1
    s.cell(row, 1, 'LTV / CAC').font = BLACK
    c = s.cell(row, 2, f"=Unit!{col}{U['ltv_cac']}")
    c.font, c.number_format = GREEN, '0.0x'
    row += 1
    s.cell(row, 1, 'Окупаемость привлечения, мес').font = BLACK
    c = s.cell(row, 2, f"=Unit!{col}{U['payback']}")
    c.font, c.number_format = GREEN, '0.0'
    row += 2
for col in 'BCD':
    s.column_dimensions[col].width = 16

b = wb.create_sheet('Benchmarks', 2)
b['A1'] = 'Цены конкурентов и рынка (проверено 08–13.11.2026)'
b['A1'].font = TITLE
for col, text in enumerate(['Кто', 'Что', 'Цена', 'Как использовали', 'Источник'], 1):
    c = b.cell(3, col, text)
    c.font, c.fill = HEADF, HEAD
BENCH = [
    ('ЮРРОБОТ', 'Облако Базовый, до 500 должников, 1 пользователь', '50 000 ₽/мес без НДС', 'Верхняя планка для подписки. «Объём» 59 900 ₽ со всеми пакетами.', 'https://urrobot.tech/tariff/'),
    ('ЮРРОБОТ', 'Облако Продвинутый / Стандартный / Профессиональный', '90 000 / 170 000 / 325 000 ₽/мес', 'Рассчитан на массовые портфели, не на МСБ.', 'https://urrobot.tech/tariff/'),
    ('Chaser', 'Напоминания и контроль дебиторки', 'от £199/мес (источники расходятся)', 'Ориентир для «Бизнеса» 24 900 ₽.', 'https://erpresearch.com/erp-add-ons/ar-collections/chaser/pricing'),
    ('Upflow', 'Управление дебиторкой, ИИ-агент', 'по запросу, средний контракт $15 000/год', 'Подтверждает готовность платить за автоматизацию.', 'https://www.vendr.com/marketplace/upflow'),
    ('Юристы (интервью)', 'Простое дело в суде', 'от 20 000–25 000 ₽', 'Пакеты 9 900 и 14 900 ₽ в 2 раза дешевле.', 'lawyers/*.docx'),
    ('Юрфирмы', 'Взыскание с оплатой от результата', '3–10% от суммы', '«Разовый долг»: 7% до суда.', 'https://vfs.consulting/services/dosudebnoe-vzyskanie-debitorskoj-zadolzhennosti-s-juridicheskih-lic-stoimost/'),
    ('Юрфирмы', 'Иски 1–5 млн ₽', '8–15% от суммы', '«Разовый долг»: 7% до суда.', 'https://usila.ru/uslugi/vziskanie-zadolzhennosti/'),
    ('Банк России', 'Ключевая ставка', '14,00% на 06.11.2026', 'База ставки в продуктах финансирования.', 'https://www.cbr.ru/hd_base/keyrate/'),
    ('Сравни', 'Факторинг, агрегатор', 'комиссия от 1,5% в месяц', 'Ориентир, точных тарифов банки не публикуют.', 'https://www.sravni.ru/biznes-kredity/faktoring/'),
    ('Resolve', 'Западная модель: аванс до 90–100% и взыскание вместе', 'по запросу', 'Идея финансирования до оплаты долга.', 'https://resolvepay.com/blog/resolve-pay-vs-hokodo-vs-gaviti'),
]
for i, line in enumerate(BENCH, 4):
    for j, value in enumerate(line, 1):
        b.cell(i, j, value).font = BLACK
for col, width in zip('ABCDE', (20, 50, 36, 48, 72)):
    b.column_dimensions[col].width = width

w = wb.create_sheet('Что исправили', 3)
w['A1'] = 'Слабые места прежней модели'
w['A1'].font = TITLE
for col, text in enumerate(['Проблема', 'Что сделали'], 1):
    c = w.cell(3, col, text)
    c.font, c.fill = HEADF, HEAD
ISSUES = [
    ('Банк получает 0% выручки, хотя это главный канал.', 'Добавили долю банка: 20% в базе, 30% в стрессе.'),
    ('CAC 15 тыс. ₽ для всех клиентов.', 'Разделили: банк 15 тыс. ₽, прямые продажи 70 тыс. ₽.'),
    ('Все неоплаченные дела идут в суд, долг поступает полностью.', 'Добавили долю дел в суде (60%) и частичные оплаты (85%).'),
    ('Выручка считается в момент старта дела.', 'Добавили лаг 3 месяца и дебиторку клиентов.'),
    ('Команда 500–900 тыс. ₽ в месяц без взносов и прочих расходов.', 'Ядро команды плюс поддержка по числу клиентов, взносы 30%, прочие расходы.'),
    ('План продаж предполагает, что банк уже подписан.', 'Базовый план снижен: 3 / 7 / 12 клиентов в месяц.'),
    ('Стресс менял только отток и средний долг.', 'Стресс меняет большинство допущений, включая долю банка и конверсию пилота. Команда в стрессе сокращается.'),
    ('Пакеты 7 / 12 тыс. ₽ и 6% ниже рынка без причины.', '8%, 9 900 и 14 900 ₽: всё ещё заметно дешевле юристов.'),
    ('Подписка и проценты одновременно: малому клиенту дороже юрфирмы (13.11.2026).', 'Три тарифа: «Разовый долг» без подписки (7% и пакеты), «Бизнес» 24 900 ₽ и «Объём» 59 900 ₽ без процентов. Число долгов задано по сегментам.'),
]
for i, line in enumerate(ISSUES, 4):
    for j, value in enumerate(line, 1):
        cell = w.cell(i, j, value)
        cell.font, cell.alignment = BLACK, Alignment(wrap_text=True, vertical='top')
w.column_dimensions['A'].width = 62
w.column_dimensions['B'].width = 62
wb.calculation.fullCalcOnLoad = True
wb.save(OUT)
print('saved', len(ROWS))
