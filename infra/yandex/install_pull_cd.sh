#!/usr/bin/env bash
# Run from an operator-reviewed release with sudo. Installs, but does not enable CD.
set -euo pipefail
[[ $(id -u) == 0 ]] || { echo 'Run with sudo'; exit 2; }
source_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
id agentpay >/dev/null
for tool in python3 git docker flock curl; do command -v "$tool" >/dev/null; done
systemctl disable --now agentpay-cd.timer 2>/dev/null || true
if systemctl is-active --quiet agentpay-cd.service; then
  echo 'An update is running; installation refused.' >&2
  exit 1
fi
install -d -o root -g root -m 755 /usr/local/lib/agentpay-cd
install -o root -g root -m 644 "$source_dir/pull_cd.py" /usr/local/lib/agentpay-cd/pull_cd.py
install -o root -g root -m 644 "$source_dir/deploy_release.sh" /usr/local/lib/agentpay-cd/deploy_release.sh
install -d -o agentpay -g agentpay -m 700 /var/lib/agentpay-cd
install -o root -g root -m 644 "$source_dir/agentpay-cd.service" /etc/systemd/system/agentpay-cd.service
install -o root -g root -m 644 "$source_dir/agentpay-cd.timer" /etc/systemd/system/agentpay-cd.timer
systemd-analyze verify /etc/systemd/system/agentpay-cd.service /etc/systemd/system/agentpay-cd.timer
systemctl daemon-reload
echo 'CD installed with timer stopped. Run dry-run and controlled acceptance before enabling timer.'
