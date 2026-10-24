#!/usr/bin/env bash
# Pin both the SSH host key and the exact Git release; never fetch mutable main on the VM.
set -euo pipefail
usage() {
  cat <<'HELP'
Usage: scripts/deploy_yandex_vm.sh --host IPv4 --revision FULL_GIT_SHA --identity-file SSH_KEY --known-hosts PINNED_KNOWN_HOSTS [--user agentpay] [--require-signed-commit]

Creates a checksum-verified git archive, sends it through pinned SSH, builds before stopping the old app,
backs up PostgreSQL, then starts the selected release. No cloud resources are created.
Host keys must be verified out of band using the VM console; ssh-keyscan alone is not verification.
HELP
}
host='' revision='' identity='' known_hosts='' user='agentpay' signed='false'
while (($#)); do
  case "$1" in
    --host|--revision|--identity-file|--known-hosts|--user)
      (($#>=2)) || { usage >&2; exit 2; }
      case "$1" in --host) host=$2;; --revision) revision=$2;; --identity-file) identity=$2;; --known-hosts) known_hosts=$2;; --user) user=$2;; esac
      shift 2;;
    --require-signed-commit) signed='true'; shift;;
    --help|-h) usage; exit 0;;
    *) usage >&2; exit 2;;
  esac
done
[[ "$host" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ && "$revision" =~ ^[a-f0-9]{40}$ && "$user" =~ ^[a-z_][a-z0-9_-]*$ ]] || { usage >&2; exit 2; }
[[ -f "$identity" && -s "$known_hosts" ]] || { echo 'SSH identity and verified known_hosts files are required.' >&2; exit 2; }
for tool in git ssh scp python3; do command -v "$tool" >/dev/null || { echo "Missing tool: $tool" >&2; exit 2; }; done
repo=$(git rev-parse --show-toplevel)
[[ $(git -C "$repo" cat-file -t "$revision") == commit ]] || { echo 'Revision must identify a Git commit.' >&2; exit 2; }
if [[ "$signed" == true ]]; then git -C "$repo" verify-commit "$revision"; fi
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
archive="$work/release.tar"
git -C "$repo" archive --format=tar "$revision" > "$archive"
checksum=$(python3 - "$archive" <<'PY'
import hashlib,sys
with open(sys.argv[1],'rb') as handle:print(hashlib.file_digest(handle,'sha256').hexdigest())
PY
)
# Explicit key pinning; never use accept-new, StrictHostKeyChecking=no, or /dev/null known_hosts.
options=(-F /dev/null -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$known_hosts" -o ConnectTimeout=10 -i "$identity")
ssh "${options[@]}" "$user@$host" 'test -d /opt/agentpay/incoming && test -d /etc/agentpay && command -v docker >/dev/null'
scp "${options[@]}" "$archive" "$user@$host:/opt/agentpay/incoming/$revision.tar"
# Run a saved file with closed stdin: docker compose run attaches stdin by default
# and can otherwise consume the remainder of a streamed `bash -s` deployment.
remote_script="$work/$revision.deploy.sh"
cat > "$remote_script" <<'REMOTE'
set -euo pipefail
release=$1 checksum=$2 public_ip=$3
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
python3 infra/yandex/prepare_env.py --public-ip "$public_ip" --output /etc/agentpay/production.env
compose=(docker compose --env-file /etc/agentpay/production.env -p agentpay -f compose.production.yml)
"${compose[@]}" config --quiet
# On a 2GB VM start only app/DB/proxy. Build first, before any optional observability stack.
"${compose[@]}" build app
"${compose[@]}" pull app-db proxy certbot
old_app=false
if "${compose[@]}" ps --status running --services | grep -qx app; then
  old_app=true
  "${compose[@]}" stop --timeout 45 app
fi
if "${compose[@]}" ps --status running --services | grep -qx app-db; then
  if ! bash infra/yandex/backup.sh; then
    if [[ "$old_app" == true ]]; then "${compose[@]}" start app; fi
    echo 'Backup failed. The previous app was resumed; upgrade refused.' >&2
    exit 1
  fi
fi
config=/etc/agentpay/nginx-site.conf
certificate_present=false
# Certbot's private archive is root-owned; inspect it inside the pinned container.
if "${compose[@]}" run --rm --no-deps --entrypoint sh certbot -c 'test -f /etc/letsencrypt/live/agentpay-ip/fullchain.pem'; then
  certificate_present=true
fi
if [[ "$certificate_present" == true ]]; then
  sed "s/PUBLIC_IP/$public_ip/g" infra/yandex/nginx-https.conf.template > "$config"
else
  cat infra/yandex/nginx-bootstrap.conf > "$config"
fi
"${compose[@]}" up -d --wait --wait-timeout 240 app app-db proxy
if [[ "$certificate_present" == false ]]; then
  "${compose[@]}" run --rm --no-deps certbot certonly --webroot --webroot-path /var/www/acme \
    --preferred-profile shortlived --ip-address "$public_ip" --cert-name agentpay-ip \
    --non-interactive --agree-tos --register-unsafely-without-email
  sed "s/PUBLIC_IP/$public_ip/g" infra/yandex/nginx-https.conf.template > "$config"
  "${compose[@]}" exec -T proxy nginx -t
  "${compose[@]}" exec -T proxy nginx -s reload
else
  "${compose[@]}" run --rm --no-deps certbot renew --quiet
  "${compose[@]}" exec -T proxy nginx -t
  "${compose[@]}" exec -T proxy nginx -s reload
fi
curl --fail --silent --show-error --retry 5 --retry-delay 3 "https://$public_ip/api/health" >/dev/null
ln -sfn "$destination" /opt/agentpay/current.next
mv -Tf /opt/agentpay/current.next /opt/agentpay/current
rm -f "$archive"
echo 'Verified release is healthy over trusted HTTPS. Check UI and the certificate/backup timers before reopening writes.'
REMOTE
scp "${options[@]}" "$remote_script" "$user@$host:/opt/agentpay/incoming/$revision.deploy.sh"
ssh "${options[@]}" "$user@$host" bash "/opt/agentpay/incoming/$revision.deploy.sh" "$revision" "$checksum" "$host" < /dev/null
