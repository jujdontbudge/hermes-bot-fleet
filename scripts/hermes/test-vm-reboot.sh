#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
RESOURCE_GROUP=${RESOURCE_GROUP:-rg-hermes-fleet-prod}
VM=${VM:-vm-hermes-fleet-01}
HOST=${HOST:-fleet-server.tail2ea909.ts.net}
SSH_USER=${SSH_USER:-fleetadmin}
OUT=${OUT:-"$ROOT/evidence/issue-11/vm-reboot.json"}
[[ ${1:-} == --pre-activation-approved ]] || { echo 'requires --pre-activation-approved' >&2; exit 64; }
[[ ${PRODUCTION_ACTIVATION:-} == false ]] || { echo 'PRODUCTION_ACTIVATION must equal false' >&2; exit 78; }
mkdir -p "$(dirname "$OUT")"
pre=$(ssh -o BatchMode=yes "$SSH_USER@$HOST" 'cd / && sudo /usr/local/libexec/hermes-fleet-verify')
pre_boot=$(jq -r .boot_id <<<"$pre")
start=$(python3 -c 'import time; print(time.monotonic_ns())')
az vm restart --resource-group "$RESOURCE_GROUP" --name "$VM"
az vm wait --resource-group "$RESOURCE_GROUP" --name "$VM" --updated --timeout 600
for _ in $(seq 1 90); do
  post=$(ssh -o BatchMode=yes -o ConnectTimeout=5 "$SSH_USER@$HOST" 'cd / && sudo /usr/local/libexec/hermes-fleet-verify' 2>/dev/null || true)
  jq -e '.passed==true' >/dev/null 2>&1 <<<"$post" && break
  sleep 5
done
post=${post:-'{}'}
jq -e '.passed==true' <<<"$post" >/dev/null
post_boot=$(jq -r .boot_id <<<"$post"); [[ $post_boot != "$pre_boot" ]]
end=$(python3 -c 'import time; print(time.monotonic_ns())')
seconds=$(python3 - "$start" "$end" <<'PY'
import sys
print(round((int(sys.argv[2])-int(sys.argv[1]))/1e9,3))
PY
)
[[ $(python3 -c "print(str($seconds <= 600).lower())") == true ]]
vm_id=$(az vm show -g "$RESOURCE_GROUP" -n "$VM" --query id -o tsv | sed -E 's#^/subscriptions/[^/]+#/subscriptions/[REDACTED]#')
jq -n -S --arg observed_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --arg vm_id "$vm_id" --arg vm "$VM" \
  --arg pre_boot "$pre_boot" --arg post_boot "$post_boot" --argjson recovery "$seconds" \
  '{schema_version:"1.0",production_activation:false,observed_at:$observed_at,vm:{id:$vm_id,name:$vm},reboot_count:1,pre_boot_id:$pre_boot,post_boot_id:$post_boot,recovery_seconds:$recovery,objective_seconds:600,passed:($recovery<=600)}' >"$OUT"
