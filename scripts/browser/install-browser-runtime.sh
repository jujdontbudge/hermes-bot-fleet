#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'run as root' >&2; exit 77; }
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq catatonit
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
manifest=${1:-$ROOT/infra/browser/browser-manifest.json}
image=$(jq -er .image "$manifest")
gate_image=$(jq -er .cdp_gate_image "$manifest")
install -d -m 0755 /etc/hermes-browser /usr/local/libexec

install -o root -g root -m 0755 "$ROOT/infra/browser/browser-start.sh" /etc/hermes-browser/browser-start.sh
install -o root -g root -m 0755 "$ROOT/scripts/browser/browser_supervisor.py" /usr/local/libexec/hermes-browser-supervisor
install -o root -g root -m 0755 "$ROOT/scripts/browser/browser-run.sh" /usr/local/libexec/hermes-browser-run
install -o root -g root -m 0755 "$ROOT/scripts/browser/browser-health.sh" /usr/local/libexec/hermes-browser-health
install -o root -g root -m 0755 "$ROOT/scripts/browser/sign-takeover-fixture.py" /usr/local/libexec/hermes-browser-sign-fixture
install -o root -g root -m 0755 "$ROOT/scripts/browser/test-authenticated-takeover.py" /usr/local/libexec/hermes-browser-test-authenticated-takeover
install -o root -g root -m 0644 "$ROOT/infra/browser/systemd/"* /etc/systemd/system/

install -o root -g root -m 0755 "$ROOT/scripts/hermes/runtime-run.sh" /usr/local/libexec/hermes-fleet-run
install -o root -g root -m 0644 "$ROOT/infra/hermes/systemd/hermes-gateway@.service" /etc/systemd/system/hermes-gateway@.service
systemctl stop hermes-browser@chief.service hermes-browser@test-worker.service \
  hermes-serve@chief.service hermes-gateway@chief.service \
  hermes-serve@test-worker.service hermes-gateway@test-worker.service 2>/dev/null || true
for bot in chief test-worker; do
  user="bot-$bot"
  install -d -o "$user" -g "$user" -m 0700 "/var/lib/hermes-bots/$bot/browser" "/var/lib/hermes-bots/$bot/browser/profile" "/var/lib/hermes-bots/$bot/browser/config" "/var/lib/hermes-bots/$bot/browser/state"
  cat >"/etc/hermes-browser/$bot.env" <<EOF
BROWSER_IMAGE=$image
CDP_GATE_IMAGE=$gate_image
EOF
  chown root:"$user" "/etc/hermes-browser/$bot.env"; chmod 0640 "/etc/hermes-browser/$bot.env"
  uid=$(id -u "$user")
  cd /
  runuser -u "$user" -- env XDG_RUNTIME_DIR="/run/user/$uid" TMPDIR="/var/lib/hermes-bots/$bot/tmp" podman pull "$image" >/dev/null
  runuser -u "$user" -- env XDG_RUNTIME_DIR="/run/user/$uid" TMPDIR="/var/lib/hermes-bots/$bot/tmp" podman pull "$gate_image" >/dev/null
  runuser -u "$user" -- env XDG_RUNTIME_DIR="/run/user/$uid" podman network exists "hermes-$bot" || runuser -u "$user" -- env XDG_RUNTIME_DIR="/run/user/$uid" podman network create "hermes-$bot" >/dev/null
  for setting in 'browser.cdp_url=http://10.89.0.10:9223' 'browser.restrict_evaluate=true'; do
    key=${setting%%=*}; value=${setting#*=}
    runuser -u "$user" -- env XDG_RUNTIME_DIR="/run/user/$uid" TMPDIR="/var/lib/hermes-bots/$bot/tmp" podman run --rm \
      --userns=keep-id:uid=1000,gid=1000 --cap-drop=all \
      --cap-add=CHOWN --cap-add=DAC_OVERRIDE --cap-add=FOWNER --cap-add=SETGID --cap-add=SETUID \
      --security-opt=no-new-privileges -e PUID=1000 -e PGID=1000 \
      -e "HOME=/opt/data/profiles/$bot/home" \
      -v "/var/lib/hermes-bots/$bot/hermes-install:/opt/data:rw,Z" \
      --entrypoint /opt/hermes/.venv/bin/hermes \
      "$gate_image" -p "$bot" config set "$key" "$value" >/dev/null
  done
  runuser -u "$user" -- env XDG_RUNTIME_DIR="/run/user/$uid" podman pod rm -f "hermes-$bot-browser-pod" >/dev/null 2>&1 || true
  runuser -u "$user" -- env XDG_RUNTIME_DIR="/run/user/$uid" podman rm -f "hermes-$bot-browser" "hermes-$bot-gateway" "hermes-$bot-serve" "hermes-$bot-net-anchor" >/dev/null 2>&1 || true
  pkill -KILL -u "$user" slirp4netns 2>/dev/null || true
  pause_pid="/run/user/$uid/libpod/tmp/pause.pid"
  if [[ -f $pause_pid ]]; then
    read -r pid <"$pause_pid"
    kill -KILL "$pid" 2>/dev/null || true
    rm -f "$pause_pid"
  fi
  rm -rf "/run/user/$uid/libpod/tmp/rootless-netns"
  runuser -u "$user" -- env XDG_RUNTIME_DIR="/run/user/$uid" TMPDIR=/var/tmp podman system migrate
done
systemctl daemon-reload
systemctl enable --now hermes-browser@chief.target hermes-browser@test-worker.target
for bot in chief test-worker; do
  systemctl start "hermes-gateway@$bot.service" "hermes-serve@$bot.service"
done
