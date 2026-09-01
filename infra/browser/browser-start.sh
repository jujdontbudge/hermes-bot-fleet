#!/usr/bin/env bash
set -Eeuo pipefail
export DISPLAY=:99
export HOME=/browser-config/home
export XDG_CONFIG_HOME=/browser-config/xdg-config
export XDG_CACHE_HOME=/browser-config/xdg-cache
export XDG_STATE_HOME=/browser-config/xdg-state
export OPENBLAS_NUM_THREADS=1
mkdir -p "$HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_STATE_HOME" /browser-profile /tmp/.X11-unix
rm -f /browser-profile/Singleton*

pids=()
start() { "$@" & pids+=("$!"); }
cleanup() {
  trap - TERM INT EXIT
  for pid in "${pids[@]}"; do kill -TERM "$pid" 2>/dev/null || true; done
  for _ in $(seq 1 100); do
    alive=false
    for pid in "${pids[@]}"; do kill -0 "$pid" 2>/dev/null && alive=true; done
    $alive || break
    sleep 0.1
  done
  for pid in "${pids[@]}"; do kill -KILL "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap cleanup TERM INT EXIT

start Xvfb :99 -screen 0 1440x900x24 -nolisten tcp -noreset
for _ in $(seq 1 50); do [[ -S /tmp/.X11-unix/X99 ]] && break; sleep 0.1; done
[[ -S /tmp/.X11-unix/X99 ]]
start fluxbox -display :99
start x11vnc -display :99 -localhost -rfbport 5900 -forever -shared -nopw -noxdamage
start /home/seluser/venv/bin/websockify --web=/opt/bin/noVNC 6080 127.0.0.1:5900
start /usr/lib/chromium/chromium \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port=9222 \
  --user-data-dir=/browser-profile \
  --no-first-run \
  --no-default-browser-check \
  --disable-dev-shm-usage \
  --disable-crash-reporter \
  --disable-breakpad \
  --disable-setuid-sandbox \
  --password-store=basic \
  --start-maximized \
  about:blank

# The lease-aware relay is visible on the Bot-private network but rejects every
# connection unless the durable ownership state is AUTOMATION.
/home/seluser/venv/bin/python /browser-supervisor.py cdp-proxy \
  --state /browser-state/lease.json \
  --listen 0.0.0.0:9223 \
  --upstream 127.0.0.1:9222 &
gate_pid=$!
printf '%s\n' "$gate_pid" >/tmp/cdp-gate.pid

wait -n "${pids[@]}"
exit 1
