#!/usr/bin/env bash
set -euo pipefail
release=$1 checksum=$2 public_ip=$3 public_url=$4
[[ "$release" =~ ^[a-f0-9]{40}$ && "$checksum" =~ ^[a-f0-9]{64}$ ]] || exit 2
exec 8>/opt/agentpay/.deploy.lock
flock -n 8 || { echo 'Another deployment is running.' >&2; exit 1; }
archive="/opt/agentpay/incoming/$release.tar"
destination="/opt/agentpay/releases/$release"
python3 - "$archive" "$checksum" <<'PY'
import hashlib,sys,tarfile
from pathlib import PurePosixPath
path,expected=sys.argv[1:]
with open(path,'rb') as handle:
    if hashlib.file_digest(handle,'sha256').hexdigest()!=expected:raise SystemExit('Release checksum mismatch')
with tarfile.open(path) as archive:
    for member in archive.getmembers():
        name=PurePosixPath(member.name)
        if name.is_absolute() or '..' in name.parts or member.issym() or member.islnk() or member.isdev():raise SystemExit('Unsafe release archive member')
PY
[[ $(git get-tar-commit-id < "$archive") == "$release" ]] || { echo 'Release commit mismatch' >&2; exit 1; }
if [[ -f "$destination/.agentpay-verified-release" && $(cat "$destination/.agentpay-verified-release") != "$checksum" ]]; then
  echo 'Existing release checksum differs; deployment refused.' >&2
  exit 1
fi
if [[ ! -f "$destination/.agentpay-verified-release" ]]; then
  mkdir -p "$destination"
  python3 - "$archive" "$destination" <<'PY'
import sys,tarfile
with tarfile.open(sys.argv[1]) as archive:archive.extractall(sys.argv[2],filter='data')
PY
  printf '%s\n' "$checksum" > "$destination/.agentpay-verified-release"
fi
cd "$destination"
export AGENTPAY_RELEASE="$release"
python3 infra/yandex/prepare_env.py --public-ip "$public_ip" --public-url "$public_url" --output /etc/agentpay/production.env
config=/etc/agentpay/nginx-site.conf
custom_domain=false
if [[ "$public_url" != "https://$public_ip" ]]; then
  custom_domain=true
  [[ -s "$config" ]] || { echo 'Custom-domain nginx configuration is missing; deployment refused.' >&2; exit 1; }
fi
compose=(docker compose --env-file /etc/agentpay/production.env -p agentpay -f compose.production.yml)
"${compose[@]}" config --quiet
# On a 2GB VM start only app/DB/proxy. Build first, before any optional observability stack.
"${compose[@]}" build app
"${compose[@]}" pull app-db proxy certbot
if [[ -n "${AGENTPAY_CD_GUARD:-}" ]]; then
  python3 "$AGENTPAY_CD_GUARD" --guard "$release" --public-ip "$public_ip" --public-url "$public_url"
fi
# BEGIN RECOVERY
old_stopped=false
phase=preflight
operator_marker=${AGENTPAY_OPERATOR_MARKER:-/opt/agentpay/deploy-needs-operator}
recover_release() {
  result=$?
  if ((result != 0)); then
    if [[ "$old_stopped" == true && "$phase" == backup ]]; then
      if ! "${compose[@]}" start app; then
        (umask 077; printf '%s\n' "$release" > "$operator_marker")
      fi
    elif [[ "$phase" == activating || "$phase" == verifying ]]; then
      (umask 077; printf '%s\n' "$release" > "$operator_marker")
      echo 'Activation failed; inspect app/database and recover manually before restarting CD.' >&2
    fi
  fi
  return "$result"
}
trap recover_release EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
# END RECOVERY
old_app=false
if "${compose[@]}" ps --status running --services | grep -qx app; then
  old_app=true
  phase=backup
  old_stopped=true
  "${compose[@]}" stop --timeout 45 app
fi
if "${compose[@]}" ps --status running --services | grep -qx app-db; then
  if ! bash infra/yandex/backup.sh; then
    if [[ "$old_app" == true ]]; then "${compose[@]}" start app; old_stopped=false; fi
    echo 'Backup failed. The previous app was resumed; upgrade refused.' >&2
    exit 1
  fi
fi
certificate_present=false
# Certbot's private archive is root-owned; inspect it inside the pinned container.
if [[ "$custom_domain" == true ]]; then
  # The operator already provisioned domain TLS. Preserve its names, paths and nginx server blocks.
  certificate_present=true
elif "${compose[@]}" run --rm --no-deps --entrypoint sh certbot -c 'test -f /etc/letsencrypt/live/agentpay-ip/fullchain.pem'; then
  certificate_present=true
fi
if [[ "$custom_domain" == true ]]; then
  : # Keep the existing custom-domain configuration byte-for-byte.
elif [[ "$certificate_present" == true ]]; then
  sed "s/PUBLIC_IP/$public_ip/g" infra/yandex/nginx-https.conf.template > "$config"
else
  cat infra/yandex/nginx-bootstrap.conf > "$config"
fi
phase=activating
"${compose[@]}" up -d --wait --wait-timeout 240 app app-db proxy
phase=verifying
if [[ "$certificate_present" == false ]]; then
  "${compose[@]}" run --rm --no-deps certbot certonly --webroot --webroot-path /var/www/acme \
    --preferred-profile shortlived --ip-address "$public_ip" --cert-name agentpay-ip \
    --non-interactive --agree-tos --register-unsafely-without-email
  sed "s/PUBLIC_IP/$public_ip/g" infra/yandex/nginx-https.conf.template > "$config"
  "${compose[@]}" exec -T proxy nginx -t
  "${compose[@]}" exec -T proxy nginx -s reload
else
  "${compose[@]}" run --rm --no-deps certbot renew --quiet || echo 'Certificate renewal deferred; trusted HTTPS health must still pass.' >&2
  "${compose[@]}" exec -T proxy nginx -t
  "${compose[@]}" exec -T proxy nginx -s reload
fi
curl --fail --silent --show-error --retry 5 --retry-delay 3 "$public_url/api/health" >/dev/null
ln -sfn "$destination" /opt/agentpay/current.next
mv -Tf /opt/agentpay/current.next /opt/agentpay/current
rm -f "$archive" "$operator_marker"
phase=complete
echo 'Verified release is healthy over trusted HTTPS. Check UI and the certificate/backup timers before reopening writes.'
