# Yandex VM: app + PostgreSQL + HTTPS по IP

Рецепт подготовлен 24.10.2026. По умолчанию: Ubuntu 24.04 LTS, Intel Ice Lake 2 vCPU/20%, RAM 2 ГБ, `network-ssd` 30 ГБ, один статический публичный IPv4. Ориентир 1 843,57 ₽/30 дней или 1 905,03 ₽/31 день без LLM/SMTP и дополнительного трафика. [Тарифы, источники и остановка расходов](../../docs/research/yandex-vm-budget.md).

Эти файлы сами не создают VM, IP, bucket или GitHub secrets. Публичный IP и диск платны; перед созданием нужен утверждённый владельцем бюджет. По умолчанию Langfuse не устанавливается на VM.

## До создания VM

1. Сохранить проверяемые изменения в Git; дождаться успешного `ci.yml` для выбранного полного commit SHA.
2. Подготовить операторский SSH Ed25519 ключ. В cloud-init попадает **только публичный** `.pub`, без API-ключей/паролей:

   ```sh
   python3 infra/yandex/render_cloud_init.py \
     --ssh-public-key /path/to/operator.pub --output /tmp/agentpay-cloud-init.yaml
   ```

3. В Yandex выбрать пользовательскую security group: TCP 22 только с внешнего IP оператора; TCP 80/443 из интернета. Остальной входящий трафик закрыт. Не использовать default SG с разрешением всего входящего трафика. При обновлении операторского IP сначала изменить правило SSH.
4. Создать согласованную VM с отрендеренным cloud-init и без лишних Marketplace лицензий/managed DB/LB/GPU. Зарезервировать её IPv4 как статический: после stop/restart динамический IP меняется, что меняет URL/сертификат/Origin. Сначала дождаться завершения cloud-init.
5. Проверить SSH host-key fingerprint через аутентифицированную Yandex serial console/serial output (cloud-init печатает fingerprints). Только после сравнения с этим источником сохранить строку известного host key в отдельный `known_hosts`. `ssh-keyscan` без такой сверки не подтверждает подлинность.

Генератор кодирует содержимое write_files в base64: CLI Yandex подставляет $NAME при передаче metadata-from-file, поэтому raw shell scripts передавать нельзя. Проверять полученный user-data после создания VM. Для генератора нужен PyYAML из requirements-dev.

Cloud-init устанавливает Docker из официального подписанного Ubuntu apt repository, создаёт пользователя `agentpay` с доступом к Docker, закрывает парольный/root SSH вход и включает таймеры. На VM с RAM менее 3 ГБ создаётся swap-файл 2 ГБ с правами `0600` и `swappiness=10`: это запас для кратковременного пика сборки, который занимает место на выбранном диске. Оператор имеет sudo; членство в Docker тоже даёт административные возможности; ключ оператора должен быть защищён.

## Первый deploy

```sh
bash scripts/deploy_yandex_vm.sh \
  --host PUBLIC_IPV4 --user agentpay \
  --revision FULL_40_CHARACTER_GIT_COMMIT_SHA \
  --identity-file /path/to/private-key \
  --known-hosts /path/to/verified-known-hosts
```

Для репозитория с настроенным доверенным signing key можно добавить `--require-signed-commit`. Скрипт не переключает VM на подвижную ветку: передаёт `git archive` точного SHA, проверяет SHA256 и Git commit id, проверяет безопасные пути архива и использует `StrictHostKeyChecking=yes`. SSH и SCP получают `-F /dev/null`, чтобы транспорт не зависел от пользовательского SSH config.

На VM создаётся `/etc/agentpay/production.env` с правами `0600` и случайным URL-safe DB password. Существующий файл/пароль не перезаписывается; несовпадающий IP/Origin требует осознанной правки оператором. Файл не попадает в Git/archive. При необходимости оператор добавляет туда Yandex/SMTP ключи и tenant binding; значения не выводятся deploy-скриптом.

Сначала собирается новый app image. При повторном deploy старый app получает до 45 секунд на завершение запросов; PostgreSQL выгружается в частный архив и проверяется `pg_restore --list`. При провале backup обновление отменяется и прежний app возобновляется. Затем запускаются только `app`, `app-db`, `proxy`. PostgreSQL/app не публикуют host ports.

Первый proxy отдаёт только ACME challenge и `503` для остальных HTTP-запросов. Certbot 5.8 получает доверенный IP-сертификат Let's Encrypt через webroot/`shortlived`, затем включается HTTPS и редирект. В конце скрипт проверяет `https://IP/api/health` с обычной проверкой доверия TLS; только после успеха меняет `/opt/agentpay/current`.

Провал обновления после изменения схемы не запускает автоматический destructive restore. Сохранены предыдущий release и backup; оператор изучает ошибку и совместимость схемы. Если восстановление необходимо, использовать отдельную пустую БД и проверенную процедуру, а не затирать существующую наугад.

## Проверки после запуска

```sh
ssh -F /dev/null -i /path/to/private-key -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=/path/to/verified-known-hosts agentpay@PUBLIC_IPV4
cd /opt/agentpay/current
docker compose --env-file /etc/agentpay/production.env -p agentpay -f compose.production.yml ps
systemctl status agentpay-cert-renew.timer agentpay-backup.timer
systemctl status agentpay-cert-renew.service agentpay-backup.service
```

Проверить вход, создание/импорт счёта, ledger и API health через HTTPS; не вводить данные в HTTP. Для подтверждения автоматического renewal выполнить:

```sh
docker compose --env-file /etc/agentpay/production.env -p agentpay -f compose.production.yml \
  run --rm --no-deps certbot renew --dry-run
bash infra/yandex/renew-cert.sh
bash infra/yandex/backup.sh
```

IP-сертификат живёт около 160 часов, поэтому отказ таймера нельзя оставлять без внимания. Renewal timer проверяет его дважды в сутки и перезагружает Nginx; backup timer ежедневно создаёт private `pg_dump` в `/var/backups/agentpay`, сохраняя локальные копии около 14 дней. Проверка table of contents не заменяет периодический restore в отдельную пустую БД. Считать общий объём архива и свободное место на диске.

Локальный backup на том же диске не является off-VM защитой. Перед эксплуатацией реальных данных подключить частный Object Storage bucket/другое независимое хранилище, ротацию и проверку восстановления. [Отдельная инструкция S3](object-storage-backup.md) описывает передачу уже проверенного архива через официальный HTTPS endpoint и отдельный credential profile. Этот рецепт не утверждает, что bucket/upload уже настроены.

## CI/CD

Текущий режим по решению владельца: **CI проверяет автоматически, deploy выполняет оператор вручную** скриптом выше. TCP 22 разрешён только с операторского IP; private SSH key остаётся у оператора. Старый Render deploy job удалён из `ci.yml`. Если у ранее созданного Render сервиса отдельно включён provider auto-deploy или deploy hook, отключить его в самом сервисе.

`deploy-yandex.yml` сохранён как будущий opt-in и выключен, пока `YANDEX_VM_DEPLOY_ENABLED` не равен `true`. Сейчас эту переменную и GitHub deployment secrets **не настраивать**. У workflow есть автоматический триггер завершения `Verify` и ручной запуск: оба разрешают только успешный `ci.yml` для точного SHA, события `push`, ветки `main` и исходного репозитория. Успешный PR run недостаточен. Автоматический путь дополнительно сверяет ID именно завершившегося run. Environment — `production`.

Если владелец позже отдельно выберет автоматический SSH deploy, потребуются изменение сетевого допуска и настройка repository/environment secrets:

- `YANDEX_VM_HOST`: статический IPv4;
- `YANDEX_VM_USER`: `agentpay`;
- `YANDEX_VM_SSH_KEY`: отдельный private deployment key;
- `YANDEX_VM_KNOWN_HOSTS`: проверенная строка host key.

API/DB/provider secrets остаются только на VM. Workflow не создаёт платных ресурсов. Деплой по SSH защищён тем же known-host pin и archive checksum; параллельные deploy на VM блокируются lock. Текущий SSH ingress с единственного IP оператора не даёт GitHub-hosted runner доступа к VM; расширять его автоматически workflow не умеет.

## Langfuse

Не входит в дешёвый production stack. Существующий `compose.langfuse.yml` остаётся для явного локального запуска/позднего отдельного sizing. Сервисы совместимы по сети с Compose merge и `-p agentpay`, но 2 ГБ для полного Langfuse стека недостаточно. В случае такого отдельного запуска app должен использовать `LANGFUSE_INTERNAL_URL=http://web:3000`, а секреты — подготовленный отдельный env файл; админский web доступ — через SSH tunnel к `127.0.0.1:3033`. Не включать этот набор на дешёвой VM без нового sizing/бюджета.

## Локальная проверка рецепта

```sh
TZ=UTC .venv/bin/python -m pytest tests/test_yandex_deploy.py -q
bash -n scripts/deploy_yandex_vm.sh infra/yandex/backup.sh infra/yandex/renew-cert.sh
```

Compose-конфигурация/генераторы/права/SSH guard проверяются без VM. Фактический TLS ACME challenge и restore проверяются уже на согласованном экземпляре до объявления ссылки готовой.
