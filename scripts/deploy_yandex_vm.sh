#!/usr/bin/env bash
# Pin both the SSH host key and the exact Git release; never fetch mutable main on the VM.
set -euo pipefail
usage() {
  cat <<'HELP'
Usage: scripts/deploy_yandex_vm.sh --host IPv4 --revision FULL_GIT_SHA --identity-file SSH_KEY --known-hosts PINNED_KNOWN_HOSTS [--public-url https://existing-domain] [--user agentpay] [--require-signed-commit]

Creates a checksum-verified git archive, sends it through pinned SSH, builds before stopping the old app,
backs up PostgreSQL, then starts the selected release. No cloud resources are created.
Host keys must be verified out of band using the VM console; ssh-keyscan alone is not verification.
HELP
}
host='' revision='' identity='' known_hosts='' user='agentpay' signed='false' public_url=''
while (($#)); do
  case "$1" in
    --host|--revision|--identity-file|--known-hosts|--user|--public-url)
      (($#>=2)) || { usage >&2; exit 2; }
      case "$1" in --host) host=$2;; --revision) revision=$2;; --identity-file) identity=$2;; --known-hosts) known_hosts=$2;; --user) user=$2;; --public-url) public_url=$2;; esac
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
public_url=${public_url:-https://$host}
# Validate before the first remote action; only a canonical HTTPS origin is passed to SSH.
python3 "$repo/infra/yandex/prepare_env.py" --public-ip "$host" --public-url "$public_url" --validate-only >/dev/null
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
cp "$repo/infra/yandex/deploy_release.sh" "$remote_script"
scp "${options[@]}" "$remote_script" "$user@$host:/opt/agentpay/incoming/$revision.deploy.sh"
ssh "${options[@]}" "$user@$host" bash "/opt/agentpay/incoming/$revision.deploy.sh" "$revision" "$checksum" "$host" "$public_url" < /dev/null
