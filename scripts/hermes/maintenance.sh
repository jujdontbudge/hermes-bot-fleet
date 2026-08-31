#!/usr/bin/env bash
set -Eeuo pipefail
bot=${1:?bot required}; shift
[[ ${1:-} == -- ]] || { echo "usage: $0 BOT -- MAINTENANCE_COMMAND..." >&2; exit 64; }; shift
(($#)) || { echo 'maintenance command required' >&2; exit 64; }
case "$bot" in chief|test-worker) ;; *) exit 64;; esac
profile="/var/lib/hermes-bots/$bot/hermes-install/profiles/$bot"
systemctl stop "hermes-serve@$bot.service" "hermes-gateway@$bot.service"
if command -v lsof >/dev/null && lsof +D "$profile" 2>/dev/null | grep -E 'state\.db(-wal|-shm)?' >/dev/null; then
  echo 'profile database still open; maintenance denied' >&2; exit 1
fi
"$@"
systemctl start "hermes-gateway@$bot.service"
/usr/local/libexec/hermes-fleet-health "$bot" gateway
systemctl start "hermes-serve@$bot.service"
/usr/local/libexec/hermes-fleet-health "$bot" all
