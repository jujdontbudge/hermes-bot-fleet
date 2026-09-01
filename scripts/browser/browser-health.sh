#!/usr/bin/env bash
set -Eeuo pipefail
bot=${1:?bot required}
case "$bot" in chief) uid=1001;; test-worker) uid=1002;; *) exit 64;; esac
cd /
export XDG_RUNTIME_DIR="/run/user/$uid"
state=$(/usr/local/libexec/hermes-browser-supervisor status --bot "$bot" | jq -r .state)
[[ $(podman inspect "hermes-$bot-browser" --format '{{.State.Running}}') == true ]]
[[ $(podman inspect "hermes-$bot-browser" --format '{{.Config.User}}') == 1200:1201 ]]
[[ $(podman inspect "hermes-$bot-browser" --format '{{.HostConfig.ReadonlyRootfs}}') == true ]]
probe="import urllib.request; urllib.request.urlopen('http://127.0.0.1:9222/json/version',timeout=3).read()"
podman exec "hermes-$bot-browser" /home/seluser/venv/bin/python -c "$probe"
if [[ $state == AUTOMATION ]]; then
  gate_probe="import urllib.request; urllib.request.urlopen('http://127.0.0.1:9223/json/version',timeout=3).read()"
  podman exec "hermes-$bot-browser" /home/seluser/venv/bin/python -c "$gate_probe"
else
  ! podman exec "hermes-$bot-browser" /home/seluser/venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9223/json/version',timeout=2)" 2>/dev/null
fi
printf '{"bot":"%s","state":"%s","healthy":true}\n' "$bot" "$state"
