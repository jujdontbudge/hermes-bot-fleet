#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'run as root' >&2; exit 77; }
bot=${1:?bot required}
case "$bot" in chief|test-worker) ;; *) exit 64;; esac
cd /
user="bot-$bot"
root="/var/lib/hermes-bots/$bot"
profile="$root/hermes-install/profiles/$bot"
# shellcheck disable=SC1090
source "/etc/hermes-fleet/$bot/runtime.env"
uid=$(id -u "$user")
password_file="$profile/dashboard-password"
configured=$(python3 - "$profile/config.yaml" <<'PY'
import sys,yaml
cfg=yaml.safe_load(open(sys.argv[1],encoding='utf-8')) or {}
b=(cfg.get('dashboard') or {}).get('basic_auth') or {}
print('yes' if b.get('username') and b.get('password_hash') and b.get('secret') else 'no')
PY
)
if [[ $configured != yes || ! -s "$password_file" ]]; then
  runuser -u "$user" -- env XDG_RUNTIME_DIR="/run/user/$uid" TMPDIR="$HERMES_TMPDIR" \
    podman run --rm --network=none \
      --userns=keep-id:uid=1000,gid=1000 --user 1000:1000 \
      --entrypoint /opt/hermes/.venv/bin/python \
      -v "$root/hermes-install:/opt/data:rw,Z" \
      "$HERMES_RUNTIME_IMAGE" -c "import json,secrets,os,yaml; from pathlib import Path; from plugins.dashboard_auth.basic import hash_password; d=Path('/opt/data/profiles/$bot'); p=secrets.token_urlsafe(32); c=yaml.safe_load((d/'config.yaml').read_text()) or {}; c['dashboard']={'basic_auth':{'username':'desktop','password_hash':hash_password(p),'secret':secrets.token_hex(32),'session_ttl_seconds':86400}}; t=d/'config.yaml.new'; t.write_text(yaml.safe_dump(c,sort_keys=False)); os.chmod(t,0o600); t.replace(d/'config.yaml'); q=d/'dashboard-password'; q.write_text(p+'\\n'); os.chmod(q,0o600)" >/dev/null
fi
runuser -u "$user" -- env XDG_RUNTIME_DIR="/run/user/$uid" TMPDIR="$HERMES_TMPDIR" \
  podman run --rm --network=none \
    --userns=keep-id:uid=1000,gid=1000 --user 1000:1000 \
    --entrypoint /opt/hermes/.venv/bin/hermes \
    -e "HOME=/opt/data/profiles/$bot/home" \
    -v "$root/hermes-install:/opt/data:rw,Z" \
    "$HERMES_RUNTIME_IMAGE" -p "$bot" plugins enable basic >/dev/null
chown "$user:$user" "$profile/config.yaml" "$password_file"
chmod 0600 "$profile/config.yaml" "$password_file"
printf 'dashboard auth configured for %s\n' "$bot"
