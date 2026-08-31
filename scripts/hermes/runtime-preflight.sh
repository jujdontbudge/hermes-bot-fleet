#!/usr/bin/env bash
set -Eeuo pipefail

bot=${1:?bot required}
component=${2:?component required}
case "$bot" in chief|test-worker) ;; *) echo "invalid bot" >&2; exit 64;; esac
case "$component" in gateway|serve) ;; *) echo "invalid component" >&2; exit 64;; esac

root="/var/lib/hermes-bots/$bot"
env_file="/etc/hermes-fleet/$bot/runtime.env"
[[ -r "$env_file" ]] || { echo "runtime environment missing" >&2; exit 78; }
# This file is generated from a validated, non-secret manifest.
# shellcheck disable=SC1090
source "$env_file"
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export TMPDIR="$HERMES_TMPDIR"

[[ "$HERMES_RUNTIME_IMAGE" =~ @sha256:[a-f0-9]{64}$ ]]
[[ "$HERMES_RUNTIME_DIGEST" =~ ^sha256:[a-f0-9]{64}$ ]]
[[ "$HERMES_MODEL" == gpt-5.6-sol ]]
[[ "$HERMES_PROVIDER" == openai-codex ]]
[[ "$HERMES_PROFILE" == "$bot" ]]
[[ "$HERMES_WORKSPACE" == "/workspaces/$bot" ]]
[[ "$HERMES_SERVE_PORT" == 8701 || "$HERMES_SERVE_PORT" == 8702 ]]
[[ -f "$root/hermes-install/profiles/$bot/config.yaml" ]]
[[ "$(stat -c %a "$root/hermes-install/profiles/$bot/config.yaml")" == 600 ]]

mapfile -t profiles < <(find "$root/hermes-install/profiles" -mindepth 1 -maxdepth 1 -type d -printf '%f\n')
[[ ${#profiles[@]} -eq 1 && "${profiles[0]}" == "$bot" ]] || {
  echo "profile isolation invariant failed" >&2; exit 78;
}

config="$root/hermes-install/profiles/$bot/config.yaml"
python3 - "$config" "$bot" <<'PY'
import sys, yaml
with open(sys.argv[1], encoding="utf-8") as fh:
    cfg = yaml.safe_load(fh) or {}
bot = sys.argv[2]
assert cfg.get("model") == {"default": "gpt-5.6-sol", "provider": "openai-codex"}
terminal = cfg.get("terminal", {})
assert terminal.get("backend") == "local"
assert terminal.get("cwd") == f"/workspaces/{bot}"
assert terminal.get("home_mode") == "profile"
assert cfg.get("security", {}).get("redact_secrets") is True
PY

actual_digest=$(podman image inspect "$HERMES_RUNTIME_IMAGE" --format '{{.Digest}}')
[[ "$actual_digest" == "$HERMES_RUNTIME_DIGEST" ]] || {
  echo "runtime image digest mismatch" >&2; exit 78;
}
image_user=$(podman image inspect "$HERMES_RUNTIME_IMAGE" --format '{{.Config.User}}')
# The official image starts s6 as container root and drops service privileges.
# Rootless Podman maps that identity away from host root.
[[ "$image_user" == root || "$image_user" == 0 ]]
version_output=$(podman run --rm --network=none --tmpfs /opt/data:rw,size=128m \
  "$HERMES_RUNTIME_IMAGE" hermes --version 2>&1)
grep -F -- "$HERMES_VERSION" <<<"$version_output" >/dev/null || {
  echo "Hermes executable version does not match approved manifest" >&2; exit 78;
}

# runtime-run removes a stale same-name container before starting. This is
# required after a hard kill of the Podman client, where conmon may leave the
# old container and its loopback publication alive until replacement.
