#!/usr/bin/env bash
set -Eeuo pipefail
bot=${1:?bot}
case "$bot" in chief) NOVNC_PORT=6081; INTERNAL_WEB_PORT=16081;; test-worker) NOVNC_PORT=6082; INTERNAL_WEB_PORT=16082;; *) exit 64;; esac
# shellcheck disable=SC1090
source "/etc/hermes-browser/$bot.env"
automation_network="hermes-$bot"
browser="hermes-$bot-browser"
anchor="hermes-$bot-net-anchor"
podman network exists "$automation_network" || podman network create "$automation_network" >/dev/null
if [[ $(podman inspect --format '{{.State.Running}}' "$anchor" 2>/dev/null || true) != true ]]; then
  podman rm -f "$anchor" >/dev/null 2>&1 || true
  podman run -d --name "$anchor" --replace \
    --network "$automation_network" --ip 10.89.0.9 \
    --userns=keep-id:uid=1000,gid=1000 --user 1000:1000 \
    --read-only --tmpfs /tmp:rw,noexec,nosuid,nodev,size=16m \
    --cap-drop=all --security-opt=no-new-privileges --pids-limit=16 --memory=32m --cpus=0.01 \
    --entrypoint /bin/sleep "$CDP_GATE_IMAGE" infinity >/dev/null
fi
podman rm -f "$browser" >/dev/null 2>&1 || true
podman run -d --name "$browser" --replace \
  --network "$automation_network" --network-alias browser --ip 10.89.0.10 \
  --userns=keep-id:uid=1200,gid=1201 --user 1200:1201 \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=512m,mode=1777 \
  --tmpfs /tmp/.X11-unix:rw,noexec,nosuid,nodev,size=1m,mode=1777 \
  --tmpfs /run:rw,noexec,nosuid,nodev,size=64m \
  --cap-drop=all --security-opt=no-new-privileges \
  --security-opt seccomp=unconfined \
  --pids-limit=1024 --memory=1536m --cpus=0.75 --shm-size=768m \
  -p "127.0.0.1:$INTERNAL_WEB_PORT:6080" \
  -v /etc/hermes-browser/browser-start.sh:/browser-start.sh:ro,Z \
  -v /usr/local/libexec/hermes-browser-supervisor:/browser-supervisor.py:ro,Z \
  -v "/var/lib/hermes-bots/$bot/browser/state:/browser-state:ro,Z" \
  -v "/var/lib/hermes-bots/$bot/browser/profile:/browser-profile:rw,Z" \
  -v "/var/lib/hermes-bots/$bot/browser/config:/browser-config:rw,Z" \
  -v "/var/lib/hermes-bots/$bot/downloads/incoming:/downloads:rw,Z" \
  --entrypoint /browser-start.sh \
  "$BROWSER_IMAGE" >/dev/null
printf '%s\n' "$browser"
