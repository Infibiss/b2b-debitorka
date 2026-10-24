# Необязательная копия backup вне VM

Подготовлено 24.10.2026. **Bucket, IAM-права, static access key и загрузка этим рецептом не созданы и не включены.** Ежедневный systemd timer пока сохраняет только локальный архив. Для текущего режима с SSH только с IP оператора копирование можно выполнять с его компьютера; S3-ключ не нужен на VM.

## Подготовка оператором

После отдельного согласования хранилища использовать частный bucket в Yandex Object Storage: публичные чтение, список и запись выключены. Выделить сервисный аккаунт с доступом только к выбранному bucket/prefix; не выдавать ему административные права каталога. Подготовить отдельный AWS CLI profile `agentpay-backup` в credential storage оператора. Файлы с static access key имеют права `0600`, не попадают в репозиторий, shell history, `production.env` или cloud-init. Ключи вводятся через локальный механизм настройки CLI, без аргументов командной строки.

Официальные параметры: endpoint `https://storage.yandexcloud.net`, region `ru-central1`. Для совместимости профиль может использовать `s3.addressing_style=path`. Установку AWS CLI и создание profile выполнить по [документации Yandex](https://yandex.cloud/ru/docs/storage/tools/aws-cli); права ограничить согласно [модели доступа](https://yandex.cloud/ru/docs/storage/security/overview). Срок хранения и предел расходов утвердить отдельно. Lifecycle для prefix `agentpay/` задаётся в bucket; версии объектов при включённом versioning требуют собственного правила удаления.

## Копирование проверенного архива

Сначала запустить `bash infra/yandex/backup.sh` на VM и выбрать **конкретное** имя нового архива `/var/backups/agentpay/agentpay-YYYYMMDDTHHMMSSZ-PID.dump`. Использовать проверенный SSH host key и тот же операторский ключ, что при deploy. Следующие команды выполняются на компьютере оператора; значения `PUBLIC_IPV4`, путей, имени архива и bucket заменить своими. Здесь нет вызовов создания ресурсов.

```sh
umask 077
mkdir -p "$HOME/agentpay-private-backups"
chmod 700 "$HOME/agentpay-private-backups"
archive="$HOME/agentpay-private-backups/agentpay-YYYYMMDDTHHMMSSZ-PID.dump"
scp -F /dev/null -i /path/to/operator-key -o IdentitiesOnly=yes \
  -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/path/to/verified-known-hosts \
  agentpay@PUBLIC_IPV4:/var/backups/agentpay/agentpay-YYYYMMDDTHHMMSSZ-PID.dump "$archive"
chmod 600 "$archive"
bucket=YOUR_PRIVATE_BUCKET
name=$(basename "$archive")
checksum=$(python3 - "$archive" <<'PY'
import hashlib, sys
with open(sys.argv[1], 'rb') as handle:
    print(hashlib.file_digest(handle, 'sha256').hexdigest())
PY
)
aws --profile agentpay-backup --region ru-central1 \
  --endpoint-url https://storage.yandexcloud.net s3 cp \
  "$archive" "s3://$bucket/agentpay/$name" --only-show-errors \
  --metadata "sha256=$checksum"
```

Дамп содержит данные пользователей и контрагентов. Файл передаётся через pinned SSH и HTTPS S3, bucket остаётся частным. Для защиты от компрометации облачного аккаунта отдельно выбрать и проверить шифрование backup с независимым ключом; этот рецепт не объявляет такое шифрование настроенным.

## Проверка независимой копии

Metadata/успешный upload не доказывают восстанавливаемость. Загрузить объект обратно и сравнить фактические байты; не сравнивать multipart ETag с SHA256:

```sh
download=$(mktemp "$HOME/agentpay-private-backups/restore-check.XXXXXX")
aws --profile agentpay-backup --region ru-central1 \
  --endpoint-url https://storage.yandexcloud.net s3 cp \
  "s3://$bucket/agentpay/$name" "$download" --only-show-errors
python3 - "$download" "$checksum" <<'PY'
import hashlib, sys
with open(sys.argv[1], 'rb') as handle:
    actual = hashlib.file_digest(handle, 'sha256').hexdigest()
if actual != sys.argv[2]:
    raise SystemExit('Backup checksum mismatch; preserve both files for review')
print('Downloaded backup bytes match the local archive')
PY
```

Затем периодически выполнять полный restore именно этой загруженной копии в отдельную пустую PostgreSQL и проверять контрольные данные, согласно [операционной процедуре](../../docs/operations.md). Рабочую БД не перезаписывать. Удалять локальные копии только после проверки и по согласованной политике. Если нужен автоматический offsite backup, оператор отдельно подключает этот шаг к backup timer и мониторингу: текущая реализация такого расписания не содержит.
