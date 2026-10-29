# Финансовый контур v3 и бухгалтерские источники

24.10.2026. Все JSON-суммы — целые копейки RUB; CSV/XLSX-суммы — рубли с максимум двумя дробными знаками. Все новые методы используют серверную tenant-сессию и существующую CSRF/Origin-проверку. Изменения выполняются одной транзакцией. SQLite сохраняет локальный путь, PostgreSQL использует тот же контракт финансовых операций.

## Идентичность, остаток и совместимость

Контрагент определяется по ИНН (10/12 цифр), при отсутствии — по Unicode NFKC/регистру/пробелам/пунктуации нормализованного названия (`ё`→`е`). Название не меняет идентичность при наличии ИНН. Один счёт уникален внутри tenant по контрагенту и нормализованному номеру. Разные ИНН могут иметь одинаковые названия и номера. Автоматического восстановления ИНН и объединения ранее безымянного ИНН с другой карточкой нет.

Invoice сохраняет прежние поля и добавляет `counterparty_id`, `original_amount`, `adjustment_amount`, `opening_paid_amount`, `revision`, `promised_amount`. `original_amount` — исходная сумма счёта; API `amount = original_amount + adjustment_amount`; `balance = amount - paid_amount`. `paid_amount` включает начальную оплату и нетто зарегистрированных платежей. Начальные оплаты не увеличивают `overview.collected_amount`, не создают банковских поступлений и не считаются подтверждённым взысканием для success fee.

Прежние `/api/invoices/{id}/payments` и `/promise` сохранены. Первый — ручная запись оплаты с invoice-scoped `reference`, без банковского подтверждения; второй — обещание всего текущего остатка на дату. Для ограниченного общего банковского поступления и частичного обещания нужны новые методы ниже. Финансовое изменение навсегда инвалидирует старые неотправленные письма; новое письмо подготавливается по актуальным фактам. Контакт/статус/настройки отправителя также увеличивают ревизию для проверки документов и agent proposals. Ежедневное изменение aging не меняет financial snapshot hash.

## Методы `/api/finance`

| Метод | Ввод / результат |
| --- | --- |
| `GET /counterparties` | `{items}`: `id,name,company,inn,email,hold,hold_reason,contact_allowed,agent_promises_allowed,max_promise_days,max_installments,mandate_expires_on,revision,outstanding` |
| `PATCH /counterparties/{id}` | Необязательные поля `hold`, `hold_reason`, `contact_allowed`, `agent_promises_allowed`, `max_promise_days` (1–365), `max_installments` (1–60), `mandate_expires_on` (дата или `null` для отмены срока). Возвращает карточку |
| `GET /bank-payments` | `{items}`: `id,external_id,amount,allocated_amount,returned_amount,available_amount,paid_on,payer_inn,payer_name,reference,evidence,confirmed,created_at` |
| `POST /bank-payments` | `{external_id,amount,paid_on,payer_inn?,payer_name?,reference,evidence,confirmed:true}`. Оператор явно подтверждает проверку банковского документа. Повтор того же `external_id` с теми же полями возвращает существующий источник, с другими — `409` |
| `POST /bank-payments/{id}/allocate` | `{invoice_id,amount,idempotency_key}` → `{invoice,payment,bank_payment}`. Сумма всех активных распределений и возвратов не превышает источник. Переплата/недостаток — `422`; несовпадающий непустой ИНН плательщика — `409` до отдельной сверки оплаты третьим лицом; аванс до даты счёта не распределяется этим методом |
| `POST /payments/{id}/reverse` | `{amount,reason,idempotency_key,kind:'correction'|'refund'}` → `{invoice,payment}`. Correction исторически отменяет ошибочную запись на первоначальную дату платежа и освобождает распределение в источнике; refund действует на дату фактического возврата (сегодня) и учитывает деньги как возвращённые, доступный остаток источника не увеличивается. История сохраняется |
| `POST /invoices/{id}/adjustments` | `{kind:'return'|'offset'|'credit'|'debit',amount,reason,effective_on,idempotency_key}` → Invoice. Первые три уменьшают principal, debit увеличивает. Нельзя уменьшить ниже уже оплаченного или датировать раньше счёта/после сегодня |
| `POST /invoices/{id}/promise` | `{amount,date,idempotency_key,installments?:[{date,amount}]}` → Promise. Частичная сумма не превращает весь долг в обещанный. Сумма графика равна обещанию, `date` совпадает с последним взносом. Новое обещание заменяет текущее; оплата закрывает взносы по очереди, исправление оплаты восстанавливает соответствующую часть |
| `GET /invoices/{id}/ledger` | `{invoice,counterparty,payments,adjustments,promises,snapshot_hash,financial_events}`. События содержат датированные signed principal reductions |
| `POST /imports/preview` | `{content:CSV}` → `{id,items,errors,changes}`; `changes.action` = `create`, `update`, `skip`, `conflict`, с before/after и ожидаемой ревизией |
| `POST /imports/{id}/approve` | `{reason}` → `{created,updated,skipped}`. Подтверждение всего валидного preview; повтор идемпотентен, устаревший preview — `409`, ошибки/конфликты — `422` |

Contact hold блокирует все письма контрагенту. Cooldown охватывает все его счета и тот же почтовый адрес, а не отдельный счёт. По умолчанию контакт оператором разрешён, автономное оформление обещания агентом — нет: требуется явный mandate. Эти правила ограничивают коммуникацию и агентское действие, но не запрещают учёт реального платежа.

## Начальные суммы и повторный импорт

Счёт может содержать `paid_amount` и/или `balance`: должно выполняться `amount = paid_amount + balance`. В CSV поддержаны `оплачено`, `сумма оплаты`, `paid_amount`, `Paid Amount`, `amount_paid`; `остаток`, `сальдо`, `balance`, `outstanding_amount`. Суффиксы `руб.`, `(руб.)` нормализуются. При одном остатке оплаченная сумма выводится из gross. Валюта при наличии столбца — только RUB/руб/643/₽. Неизвестные колонки, статус, противоречивые суммы, лишняя точность и ошибки хотя бы одной строки блокируют импорт.

Legacy `POST /api/invoices/import` создаёт или пропускает идентичные счета. Изменившиеся существующие строки возвращают `409` и требуют `/api/finance/imports/preview` → review → `/approve`. Нельзя перезаписать зарегистрированную оплату меньшей source-оплатой, перенести дату счёта после зарегистрированного платежа или молча переписать корректировки. Подтверждённый новый source-paid пересчитывает начальную оплату и выполнение обещаний; банковское поступление при этом не выдумывается. Before/after сохраняются в записи preview.

У начальной оплаты неизвестна фактическая банковская дата: `financial_events` содержит `type:'opening'`, `confirmed:false`, `verified_date:false`, `date_basis:'assumed_issue_date'`. Техническая дата счёта не является доказательством времени оплаты для юридического расчёта.

## ОСВ 62 / акты сверки: `/api/accounting`

`POST /preview` принимает:

```json
{
  "source_type": "osv62",
  "source_ref": "1С: ОСВ62 октябрь",
  "as_of": "2026-10-24",
  "format": "csv",
  "content": "...CSV text, or base64 XLSX...",
  "mapping": {
    "company": "Контрагент",
    "inn": "ИНН",
    "opening_debit": "НачД",
    "opening_credit": "НачК",
    "debit_turnover": "ОборД",
    "credit_turnover": "ОборК",
    "ending_debit": "КонД",
    "ending_credit": "КонК"
  },
  "header_row": 1
}
```

`source_type` также `reconciliation_act`. Для акта нужны company и хотя бы один ending debit/credit; для ОСВ все шесть денежных полей. `inn` необязателен. `header_row` позволяет пропустить преамбулу выгрузки; `sheet` выбирает лист XLSX. Возвращаются `id`, `columns:[{key:'column_1',label:'Контрагент'}]`, `items`, `errors`, `comparison_basis:'current_ledger'`. При пустом mapping можно получить columns и сообщение о необходимости сопоставить поля. Значение mapping — точный уникальный заголовок или `column_N` при повторяющихся названиях.

Строка содержит рублёвые суммы, преобразованные в копейки, `source_balance = ending_debit - ending_credit`, `ledger_current_balance`, `discrepancy`, `requires_review`. Источник имеет собственную `as_of`; сравнение **всегда с текущим реестром**, а не реконструкцией исторического сальдо. Контроль проверяет начальное сальдо + обороты = конечное сальдо. Итоги/повторные строки контрагента/невалидные суммы нельзя утвердить.

`POST /imports/{id}/approve` принимает `{reason,selected_rows:[2,3]}` — номера строк preview, не индексы списка. Можно выбрать только валидные строки. Изменившийся после preview ledger требует нового сравнения (`409`). Подтверждение сохраняет source-only записи и при необходимости карточку контрагента; **из агрегатного сальдо не создаются счета**, платежи, обещания или документы для иска. Повтор источника `(tenant,type,ref,as_of,counterparty)` с теми же суммами пропускается, с другими — `409`. `GET /reconciliations` возвращает эти записи, исходные строки и причину/автора/время подтверждения.

XLSX читается в памяти в read-only режиме; формулы, макросы, внешние связи, небезопасный XML, избыточные архивы/число строк/столбцов отклоняются. Не более 5 000 строк и 100 столбцов; обычный лимит HTTP/body сохраняется. Парсер использует [openpyxl](https://openpyxl.readthedocs.io/en/stable/tutorial.html) и [defusedxml согласно рекомендации проекта](https://openpyxl.readthedocs.io/en/stable/index.html#security).

## Миграция и восстановление

Условия вознаграждения актуализированы отдельно от ledger: [6% Mandato, фикс 7/12 тыс. ₽ и отдельные 12% адвокату](payment-terms.md). `fee_amount` в юридическом API содержит только Mandato; `lawyer_fee_amount` возвращается отдельно. Чтение расчёта не меняет оплаты/остатки; старые дела требуют явного подтверждения новой версии руководителем.

SQLite v1/v2 → v3 перестраивается под одним write lock и одной транзакцией: сохраняются tenant/user/session/settings, счета, платежи, события и отправленная история. Legacy payments остаются ручными, отсутствие bank-source не восполняется. Идентичные старые счета одного ИНН не удаляются: сохраняются обе записи, создаётся `finance_identity_conflicts`, контрагент ставится на hold для ручной сверки. Старые неотправленные письма требуют нового черновика. Ошибка в середине перестройки откатывает всю миграцию; повторный запуск проверен.

`BASE_SCHEMA_SQL` — итоговая portable DDL v3 для свежего PostgreSQL. `scripts/restore.py` принимает backup v1/v2/v3 и проверяет обязательные таблицы/колонки; v1/v2 мигрируют при следующем старте. Перед эксплуатационным обновлением нужна обычная резервная копия и остановка экземпляра. Разработка и проверки этого изменения не обращались к рабочей БД.
