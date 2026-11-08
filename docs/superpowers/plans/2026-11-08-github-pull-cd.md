# GitHub Pull CD Implementation Plan

Согласовано владельцем: public GitHub → успешный CI точного текущего main → VM, интервал пять минут, без нового входящего SSH.

1. RED: тесты происхождения CI, смены main, rate limit, отсутствия CI, no-op текущей версии и отказа от повторов неудачного SHA.
2. Общий release script для SSH и локального запуска: прежние проверки архива, backup и HTTPS; guard повторной проверки main после сборки и до остановки приложения.
3. Python pull controller: только публичный API, фиксированный репозиторий, bare git cache, archive точного SHA, атомарное состояние и блокировка. Непроверенные/ошибочные ответы не вызывают deploy.
4. Systemd service/timer: пользователь agentpay, root-owned исполняемые файлы; state/cache отдельно; ручное выключение и повтор отказавшего SHA документированы. Обычный SSH workflow остаётся отключённым.
5. Регрессии deployment, полный CI; фиксация main.
6. На VM: финансовые fingerprints, установка с timer выключенным, dry-run, один контролируемый CD deploy проверенного SHA, HTTPS/config/backup/DB проверки, затем timer; проверка повторного запуска как no-op.
