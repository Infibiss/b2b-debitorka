# Локальные проверки и PostgreSQL

Запускайте команды из корня `Mandato_project`. Python 3.12 и зависимости из `requirements-dev.txt` устанавливаются в `.venv`. `pytest.ini` собирает тесты из `tests` и `e2e`; runtime, резервные копии и служебные checkout в `var` в сбор не попадают.

## Windows

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m server.agent_evals --mode replay --out var/agent-eval-replay.json
```

Shell-проверкам нужен нативный Git Bash или MSYS2 Bash. Можно явно указать путь в `TEST_BASH`; автоматически проверяются Git for Windows и `C:/msys64/usr/bin/bash.exe`. Windows-обёртка WSL не подменяет этот runtime. Синтаксис проверяется на UTF-8/LF-исходнике, а CI gate исполняется целиком с локальными заглушками `gh` и Python. Проверки точного commit SHA, trusted CI push и SSH pinning сохраняются.

Приватные backup/config-файлы создаются исключительно: POSIX `0600`, Windows — защищённая DACL для текущего пользователя и SYSTEM, заданная при создании файла. Проверка приватности читает реальные права платформы; `chmod/stat` не заменяют проверку NTFS ACL. SQLite backup проходит `integrity_check` и `fsync` через дескриптор с правом записи, как требуется Windows.

## Отдельная тестовая PostgreSQL

Нужны PostgreSQL 17 и его `pg_dump`/`pg_restore` в PATH. `TEST_POSTGRES_URL` должен указывать только на отдельную тестовую БД. Фикстуры создают и удаляют временные схемы. Проверка backup/restore также создаёт отдельную пустую БД `mandato_restore_<uuid>`, проверяет суммы и отказ от повторного восстановления, затем удаляет только эту БД. Тестовому пользователю нужны права на схемы и создание БД.

Для текущей Windows-среды подготовлен portable PostgreSQL 17.11, без системной службы:

- Runtime: `var/postgres-runtime/17.11/pgsql/bin`.
- Кластер: `var/postgres-tests-20261027/data`.
- Сервер: `127.0.0.1:55432`; БД и пользователь `mandato_test`, аутентификация SCRAM.
- Закрытые настройки: `var/postgres-tests-20261027/connection.json`. Файл содержит тестовый пароль; не выводите его в чат/логи. Весь `var` исключён из Git.
- Дистрибутив получен с [официальной страницы EDB](https://www.enterprisedb.com/download-postgresql-binaries); SHA-256 архива проверен по [публикации EDB](https://github.com/EnterpriseDB/edb-installers/issues/682).

Для повторного запуска подготовленного кластера:

```powershell
$pgTest = Get-Content var/postgres-tests-20261027/connection.json -Raw | ConvertFrom-Json
$pgCtl = Join-Path $pgTest.bin 'pg_ctl.exe'
# Выполняйте start, только если status показывает остановленный кластер.
& $pgCtl -D $pgTest.data status
& $pgCtl -D $pgTest.data -l var/postgres-tests-20261027/server.log `
  -o '-h 127.0.0.1 -p 55432 -c max_connections=30' -w start `
  *> var/postgres-tests-20261027/control.log
$env:PATH = $pgTest.bin + ';' + $env:PATH
$env:TEST_POSTGRES_URL = $pgTest.url
.\.venv\Scripts\python.exe -m pytest -q
# После проверок остановите только этот кластер; данные сохраняются для повторного запуска.
& $pgCtl -D $pgTest.data -m fast -w stop
Remove-Item Env:TEST_POSTGRES_URL
```

PostgreSQL-набор отдельно:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_storage_pg.py `
  tests/test_legal_fees_postgres.py tests/test_portfolio_postgres.py `
  tests/test_workflow_postgres.py tests/test_postgres_backup.py `
  tests/test_integrations.py::test_real_postgres_bank_approval_and_registry_use_same_tenant_contract -q
```

Без `TEST_POSTGRES_URL` реальные PG-проверки пропускаются; такой прогон не подтверждает PostgreSQL. Платный live Yandex eval остаётся отдельным opt-in. Обычный safety replay не вызывает внешнюю модель.

## Проверено 27.10.2026

Локально под Windows, Python 3.12.14 и PostgreSQL 17.11:

- Полный проектный набор с `TEST_POSTGRES_URL`: **531 passed, 1 skipped**, 186,83 с; ошибок и падений нет. Пропущен только opt-in `test_real_yandex_review_and_local_langfuse_delivery`.
- Отдельный PostgreSQL-набор выше: **23 passed**, без пропусков; включая настоящий dump/restore в пустую БД, копейки, откат, checkpoints, изоляцию, конкурентные операции и тариф.
- Safety replay: **19/19**, false-ready 0. Это проверка защит на синтетике.
- Временные схемы и БД восстановления удалены тестами; кластер `mandato_test` остановлен. Его файлы и закрытые настройки сохранены для повторного запуска.

Полный лог и JUnit: `var/verification-with-postgres-final.log`, `var/verification-with-postgres-final.xml`. Службы Windows и production-контур при этих проверках не изменялись.

## Исправления пути пользователя — 29.10.2026

Полный серверный набор после исправлений: **540 passed, 1 skipped**, 208,92 с, с `TEST_POSTGRES_URL` локального кластера `mandato_test`. Включены новые проверки восстановления пароля, одноразового потребления токена и отзыва сессий, истечения срока, отказа доставки, Origin/rate limit, прав на заявки SMTP, изоляции компаний, общего архива и переноса договора. Те же ключевые контракты проверены на отдельной схеме PostgreSQL. Лог: `var/verification-ux-20261029.log`, JUnit: `var/verification-ux-20261029.xml`.

Браузерные регрессии находятся в `e2e/ux-repairs.spec.ts`: черновик после вкладок/refresh, ошибочного сохранения и недоступного sessionStorage; дополнительные поля ИП; подтверждение выхода и очистка черновиков; контекст счёта, deep link и Back; загрузка договора, заявка на почту; помощь на входе; первый экран 390 × 844. Для запуска: `npm run build`, затем `npm run test:e2e`. Восстановление и SMTP тестируются без отправки реальных писем.

После финального уточнения выборки архива отдельно повторены новые API-контракты: **9 passed** на SQLite и PostgreSQL. Незавершённых временных схем `audit_*` не осталось; локальный тестовый кластер остановлен.

Браузерный набор завершён без сбоев: **96/96** на desktop/mobile (два непересекающихся запуска: 6 и 90). После уточнения контекстных переходов дополнительно **28/28**: работа с делом, оплаты и согласования, архив, черновики, доступ и мобильная компоновка. Итоги запусков: `var/ui-repairs/focused-results/.last-run.json`, `e2e/results/.last-run.json`, `var/ui-repairs/final-context-results/.last-run.json`. Скриншот итогового мобильного экрана: `var/ui-repairs/mobile-work.png`.

`tsc --noEmit`, сборка Vite и `git diff --check` прошли. Реальные SMTP-письма не отправлялись; сервисная почта восстановления включается параметрами `AUTH_SMTP_*`. Контакт поддержки оставлен заглушкой по решению владельца.


## Оставшиеся пункты отчёта UI — 29 октября 2026

После доработки всех 14 пунктов отчёта полный серверный прогон завершён: **548 passed, 1 skipped**, 230,89 с. Включены **29 проверок, связанных с PostgreSQL**, без сбоев. Новые контракты: предварительная проверка полномочий, повторная оценка того же предложения без обхода согласования/срока/остатка, изоляция истории счёта и компании, разделение источников оплат, сохранение неполных юридических фактов при сохранённом запрете генерации неподготовленного пакета. Файлы: `tests/test_ui_audit_contracts.py`, `tests/test_ui_audit_postgres.py`. Лог и JUnit: `var/ui-audit-followup/pytest.log`, `pytest.xml`. Временных схем после прогона: 0; отдельный кластер остановлен.

Полный браузерный прогон: **106 passed**, desktop и mobile, 5,2 минуты. Новые сценарии находятся в `e2e/audit-followup.spec.ts`: намерение импорта после регистрации; разрешения с возвратом к сохранённому графику; повторная проверка предложения; помощь без ухода с формы; сохранение неполного юридического шага; общая история и сверка; ручное предложение из сохранённого ответа; компактная очередь, фильтры URL и читаемость подписей аудита. Лог: `var/ui-audit-followup/playwright-final.log`. Итог: `var/ui-audit-followup/final-results/.last-run.json`.

Исходный отчёт `var/ui-audit/report.html` дополнен текущими изменениями по всем 14 пунктам; наблюдения и скриншоты 27 октября сохранены как история. Реальные отправки SMTP, сервисная доставка восстановления и платные внешние провайдеры требуют настроек и отдельной контрольной проверки. Контакт поддержки остаётся заглушкой.

После последнего уточнения шрифта следующего действия и контраста подписей повторно прошли **4/4** проверки очереди и ширин, включая 390 × 844, 320, 650, 768, 1024 и 1280 px. Сборка, `tsc --noEmit` и `git diff --check` прошли. Итоговая сводка: `var/ui-audit-followup/verification.json`, снимок: `var/ui-audit-followup/mobile-queue.png`.
