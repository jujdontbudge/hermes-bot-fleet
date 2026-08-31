#!/usr/bin/env bash
set -Eeuo pipefail
bot=${1:?bot required}
component=${2:?component required}
case "$bot:$component" in chief:gateway|chief:serve|test-worker:gateway|test-worker:serve) ;; *) exit 64;; esac
# shellcheck disable=SC1090
source "/etc/hermes-fleet/$bot/runtime.env"
runtime_uid=$(id -u)
export XDG_RUNTIME_DIR="/run/user/$runtime_uid"
export TMPDIR="$HERMES_TMPDIR"
mkdir -p "$XDG_RUNTIME_DIR"
chmod 0700 "$XDG_RUNTIME_DIR"

name="hermes-$bot-$component"
podman rm -f "$name" >/dev/null 2>&1 || true
if [[ "$component" == gateway ]]; then
  # A SIGKILL of the Podman client can strand conmon/network-namespace state.
  # BindsTo stops the Bot's serve unit first; wait for its container to leave,
  # then rebuild the rootless pause namespace before launching the gateway.
  for _ in $(seq 1 30); do
    [[ -z $(podman ps -q) ]] && break
    sleep 1
  done
  [[ -z $(podman ps -q) ]] || { echo "Bot containers did not quiesce" >&2; exit 75; }
  podman system migrate
fi
common=(
  run --rm --name "$name" --replace
  --label "com.hermes-fleet.bot=$bot" --label "com.hermes-fleet.component=$component"
  --userns=keep-id:uid=1000,gid=1000
  --cap-drop=all --security-opt=no-new-privileges --pids-limit=512
  --memory=3g --cpus=0.8 --network=slirp4netns:allow_host_loopback=false
  -e PUID=1000 -e PGID=1000
  -e "HOME=/opt/data/profiles/$bot/home"
  -v "/var/lib/hermes-bots/$bot/hermes-install:/opt/data:rw,Z"
  -v "/var/lib/hermes-bots/$bot/workspace:$HERMES_WORKSPACE:rw,Z"
  -v "/var/lib/hermes-bots/$bot/downloads/released:/downloads/released:ro,Z"
  "$HERMES_RUNTIME_IMAGE"
)
if [[ "$component" == gateway ]]; then
  common=("${common[@]:0:${#common[@]}-1}" \
    --cap-add=CHOWN --cap-add=DAC_OVERRIDE --cap-add=FOWNER \
    --cap-add=SETGID --cap-add=SETUID \
    "${common[-1]}")
  exec podman "${common[@]}" hermes -p "$bot" gateway run
else
  common=("${common[@]:0:${#common[@]}-1}" \
    -p "127.0.0.1:$HERMES_SERVE_PORT:$HERMES_SERVE_PORT" \
    --user 1000:1000 --entrypoint /opt/hermes/.venv/bin/hermes \
    "${common[-1]}")
  exec podman "${common[@]}" -p "$bot" serve --isolated --host 0.0.0.0 --port "$HERMES_SERVE_PORT" --skip-build
fi
