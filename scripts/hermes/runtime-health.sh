#!/usr/bin/env bash
set -Eeuo pipefail
bot=${1:?bot required}
scope=${2:-all}
case "$bot" in chief|test-worker) ;; *) exit 64;; esac
case "$bot:$scope" in chief:gateway|chief:serve|chief:all|test-worker:gateway|test-worker:serve|test-worker:all) ;; *) exit 64;; esac
cd /
# shellcheck disable=SC1090
source "/etc/hermes-fleet/$bot/runtime.env"
user="bot-$bot"
run_podman() {
  local uid; uid=$(id -u "$user")
  if [[ $(id -un) == "$user" ]]; then
    env XDG_RUNTIME_DIR="/run/user/$uid" TMPDIR="$HERMES_TMPDIR" podman "$@"
  elif [[ $EUID -eq 0 ]]; then
    runuser -u "$user" -- env XDG_RUNTIME_DIR="/run/user/$uid" TMPDIR="$HERMES_TMPDIR" podman "$@"
  else
    echo "health probe must run as root or $user" >&2; return 77
  fi
}

if [[ "$scope" == gateway || "$scope" == all ]]; then
  systemctl is-active --quiet "hermes-gateway@$bot.service"
  [[ "$(run_podman inspect "hermes-$bot-gateway" --format '{{.State.Running}}')" == true ]]
fi
if [[ "$scope" == serve || "$scope" == all ]]; then
  systemctl is-active --quiet "hermes-serve@$bot.service"
  [[ "$(run_podman inspect "hermes-$bot-serve" --format '{{.State.Running}}')" == true ]]
  ss -H -lnt "sport = :$HERMES_SERVE_PORT" | awk '{print $4}' | grep -Eq "^(127\\.0\\.0\\.1|\\[::1\\]):$HERMES_SERVE_PORT$"
fi

profile="/var/lib/hermes-bots/$bot/hermes-install/profiles/$bot"
if [[ -f "$profile/state.db" ]]; then
  [[ "$(sqlite3 "$profile/state.db" 'pragma integrity_check;')" == ok ]]
fi
