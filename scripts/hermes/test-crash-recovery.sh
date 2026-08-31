#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
HOST=${HOST:-fleet-server.tail2ea909.ts.net}
SSH_USER=${SSH_USER:-fleetadmin}
OUT=${OUT:-"$ROOT/evidence/issue-11/crash-recovery.json"}
[[ ${1:-} == --disposable-fixture ]] || { echo 'requires --disposable-fixture; never run against an enabled production Bot' >&2; exit 64; }
mkdir -p "$(dirname "$OUT")"
container_hpid() {
  local bot=$1 component=$2 uid
  case "$bot" in chief) uid=1001;; test-worker) uid=1002;; *) return 64;; esac
  ssh -o BatchMode=yes "$SSH_USER@$HOST" "cd / && sudo -u bot-$bot env XDG_RUNTIME_DIR=/run/user/$uid TMPDIR=/var/lib/hermes-bots/$bot/tmp podman top hermes-$bot-$component hpid comm args | awk '\$2==\"hermes\" {print \$1; exit}'"
}
results=()
for bot in test-worker chief; do
  for component in gateway serve; do
    before=$(container_hpid "$bot" "$component")
    [[ $before =~ ^[1-9][0-9]*$ ]]
    start=$(python3 -c 'import time; print(time.monotonic_ns())')
    ssh -o BatchMode=yes "$SSH_USER@$HOST" "sudo kill -KILL '$before'"
    deadline=$((SECONDS+120)); after=0
    while ((SECONDS < deadline)); do
      after=$(container_hpid "$bot" "$component" 2>/dev/null || true)
      if [[ $after =~ ^[1-9][0-9]*$ && $after != "$before" ]]; then
        ssh -o BatchMode=yes "$SSH_USER@$HOST" "sudo /usr/local/libexec/hermes-fleet-health '$bot' '$component'" && break
      fi
      sleep 2
    done
    [[ $after =~ ^[1-9][0-9]*$ && $after != "$before" ]] || { echo "$bot $component Hermes process did not recover" >&2; exit 1; }
    end=$(python3 -c 'import time; print(time.monotonic_ns())')
    seconds=$(python3 - "$start" "$end" <<'PY'
import sys
print(round((int(sys.argv[2])-int(sys.argv[1]))/1e9,3))
PY
)
    results+=("$(jq -cn --arg bot "$bot" --arg component "$component" --argjson recovery "$seconds" '{bot:$bot,component:$component,crash_target:"in-container-hermes-process",process_identity_changed:true,recovery_seconds:$recovery,healthy_pid_count:1,within_objective:($recovery<=120)}')")
  done
done
rows=$(printf '%s\n' "${results[@]}" | jq -s .)
jq -n -S --arg observed_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --argjson results "$rows" '{schema_version:"1.0",fixture:"disposable-pre-activation",observed_at:$observed_at,objective_seconds:120,results:$results,passed:([$results[].within_objective]|all)}' >"$OUT"
jq -e '.passed==true and (.results|length)==4 and ([.results[].crash_target]|unique)==["in-container-hermes-process"]' "$OUT" >/dev/null
