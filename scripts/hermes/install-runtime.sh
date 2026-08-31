#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
manifest=
start=true
while (($#)); do
  case "$1" in
    --manifest) manifest=${2:?}; shift 2;;
    --no-start) start=false; shift;;
    *) echo "usage: $0 --manifest FILE [--no-start]" >&2; exit 64;;
  esac
done
[[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 77; }
[[ -n "$manifest" && -f "$manifest" ]]

python3 - "$manifest" <<'PY'
import json,re,sys
m=json.load(open(sys.argv[1]))
assert set(m)=={'schema_version','hermes_version','runtime_image','runtime_image_digest','model','provider','bots'}
assert m['schema_version']=='1.0' and m['model']=='gpt-5.6-sol' and m['provider']=='openai-codex'
assert re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:[+-][A-Za-z0-9.-]+)?',m['hermes_version'])
match=re.fullmatch(r'[A-Za-z0-9._/:~-]+@(sha256:[a-f0-9]{64})',m['runtime_image'])
assert match and match.group(1)==m['runtime_image_digest']
expected={'chief':('bot-chief',8701,'/workspaces/chief'),'test-worker':('bot-test-worker',8702,'/workspaces/test-worker')}
assert set(m['bots'])==set(expected)
for bot, values in expected.items():
    b=m['bots'][bot]
    assert set(b)=={'unix_user','serve_port','workspace'} and tuple(b.values())==values
PY

install -d -m 0755 /etc/hermes-fleet /usr/local/libexec
install -m 0755 "$ROOT/scripts/hermes/runtime-preflight.sh" /usr/local/libexec/hermes-fleet-preflight
install -m 0755 "$ROOT/scripts/hermes/runtime-run.sh" /usr/local/libexec/hermes-fleet-run
install -m 0755 "$ROOT/scripts/hermes/runtime-health.sh" /usr/local/libexec/hermes-fleet-health
install -m 0755 "$ROOT/scripts/hermes/wait-health.sh" /usr/local/libexec/hermes-fleet-wait-health
install -m 0755 "$ROOT/scripts/hermes/configure-dashboard-auth.sh" /usr/local/libexec/hermes-fleet-dashboard-auth
install -m 0755 "$ROOT/scripts/hermes/verify-runtime.sh" /usr/local/libexec/hermes-fleet-verify
install -m 0644 "$ROOT"/infra/hermes/systemd/* /etc/systemd/system/
command -v sqlite3 >/dev/null || { apt-get update -y; apt-get install -y --no-install-recommends sqlite3; }
install -m 0644 "$ROOT/infra/hermes/sysctl/90-hermes-rootless.conf" /etc/sysctl.d/90-hermes-rootless.conf
sysctl --system >/dev/null

image=$(jq -r .runtime_image "$manifest")
digest=$(jq -r .runtime_image_digest "$manifest")
version=$(jq -r .hermes_version "$manifest")
# The staging tree may be under fleetadmin's private home. Rootless Podman must
# start from an accessible cwd when run under each Bot identity.
cd /
for bot in test-worker chief; do
  user=$(jq -r ".bots[\"$bot\"].unix_user" "$manifest")
  port=$(jq -r ".bots[\"$bot\"].serve_port" "$manifest")
  workspace=$(jq -r ".bots[\"$bot\"].workspace" "$manifest")
  getent passwd "$user" >/dev/null || { echo "missing issue-10 user $user" >&2; exit 78; }
  root="/var/lib/hermes-bots/$bot"
  profile="$root/hermes-install/profiles/$bot"
  install -d -m 0700 -o "$user" -g "$user" "$profile" "$profile/home" "$root/workspace" "$root/downloads/released" "$root/tmp"
  find "$root/hermes-install/profiles" -mindepth 1 -maxdepth 1 -type d ! -name "$bot" -print -quit | grep -q . && {
    echo "unexpected profile under $bot installation root" >&2; exit 78;
  }
  sed "s|__WORKSPACE__|$workspace|g" "$ROOT/infra/hermes/config/profile-config.json.tmpl" >"$profile/config.yaml.new"
  chown "$user:$user" "$profile/config.yaml.new"; chmod 0600 "$profile/config.yaml.new"
  mv "$profile/config.yaml.new" "$profile/config.yaml"
  install -d -m 0750 -o root -g "$user" "/etc/hermes-fleet/$bot"
  cat >"/etc/hermes-fleet/$bot/runtime.env" <<EOF
HERMES_RUNTIME_IMAGE=$image
HERMES_RUNTIME_DIGEST=$digest
HERMES_VERSION=$version
HERMES_MODEL=gpt-5.6-sol
HERMES_PROVIDER=openai-codex
HERMES_PROFILE=$bot
HERMES_SERVE_PORT=$port
HERMES_WORKSPACE=$workspace
HERMES_TMPDIR=$root/tmp
EOF
  chown root:"$user" "/etc/hermes-fleet/$bot/runtime.env"; chmod 0640 "/etc/hermes-fleet/$bot/runtime.env"
  loginctl enable-linger "$user" >/dev/null
  uid=$(id -u "$user"); install -d -m 0700 -o "$user" -g "$user" "/run/user/$uid"
  runuser -u "$user" -- env XDG_RUNTIME_DIR="/run/user/$uid" TMPDIR="$root/tmp" podman pull "$image"
  actual=$(runuser -u "$user" -- env XDG_RUNTIME_DIR="/run/user/$uid" TMPDIR="$root/tmp" podman image inspect "$image" --format '{{.Digest}}')
  [[ "$actual" == "$digest" ]] || { echo "pulled image digest mismatch" >&2; exit 78; }
  /usr/local/libexec/hermes-fleet-dashboard-auth "$bot"
done
systemctl daemon-reload
if [[ $start == true ]]; then
  wait_health() {
    local bot=$1 scope=$2
    for _ in $(seq 1 60); do
      /usr/local/libexec/hermes-fleet-health "$bot" "$scope" >/dev/null 2>&1 && return 0
      sleep 2
    done
    /usr/local/libexec/hermes-fleet-health "$bot" "$scope"
  }
  for bot in test-worker chief; do
    profile="/var/lib/hermes-bots/$bot/hermes-install/profiles/$bot"
    if [[ ! -s "$profile/auth.json" && ! -s "$profile/.env" ]]; then
      echo "refusing activation: provision supported Bot-scoped credentials for $bot first" >&2
      exit 78
    fi
    for f in "$profile/auth.json" "$profile/.env"; do [[ ! -e "$f" || "$(stat -c %a "$f")" == 600 ]] || { echo "unsafe credential mode" >&2; exit 78; }; done
    systemctl enable --now "hermes-gateway@$bot.service"
    wait_health "$bot" gateway
    systemctl enable --now "hermes-serve@$bot.service" "hermes-health@$bot.timer" "hermes-runtime@$bot.target"
    wait_health "$bot" all
  done
fi
printf 'Hermes runtime installed from immutable manifest; start=%s\n' "$start"
