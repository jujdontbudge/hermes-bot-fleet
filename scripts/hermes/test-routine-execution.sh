#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
HOST=${HOST:-fleet-server.tail2ea909.ts.net}
SSH_USER=${SSH_USER:-fleetadmin}
OUT=${OUT:-"$ROOT/evidence/issue-11/routine-execution.json"}
[[ ${1:-} == --maintenance-approved ]] || { echo 'requires --maintenance-approved' >&2; exit 64; }
mkdir -p "$(dirname "$OUT")"
schedule=$(python3 - <<'PY'
from datetime import datetime,timezone,timedelta
print((datetime.now(timezone.utc)+timedelta(seconds=120)).strftime('%Y-%m-%dT%H:%M:%SZ'))
PY
)
scp -q "$ROOT/scripts/hermes/fixtures/routine-proof.sh" "$SSH_USER@$HOST:/home/fleetadmin/issue11-routine-proof.sh"
ssh -o BatchMode=yes "$SSH_USER@$HOST" 'sudo install -d -o bot-test-worker -g bot-test-worker -m 0700 /var/lib/hermes-bots/test-worker/hermes-install/profiles/test-worker/scripts; sudo install -o bot-test-worker -g bot-test-worker -m 0700 /home/fleetadmin/issue11-routine-proof.sh /var/lib/hermes-bots/test-worker/hermes-install/profiles/test-worker/scripts/issue11-routine-proof.sh; sudo rm -f /var/lib/hermes-bots/test-worker/workspace/routine-proof.marker; sudo systemctl stop hermes-serve@test-worker.service hermes-gateway@test-worker.service'
create=$(ssh -o BatchMode=yes "$SSH_USER@$HOST" "cd / && sudo -u bot-test-worker env XDG_RUNTIME_DIR=/run/user/1002 TMPDIR=/var/lib/hermes-bots/test-worker/tmp podman run --rm --network=none --userns=keep-id:uid=1000,gid=1000 --user 1000:1000 --entrypoint /opt/hermes/.venv/bin/hermes -e HOME=/opt/data/profiles/test-worker/home -v /var/lib/hermes-bots/test-worker/hermes-install:/opt/data:rw,Z -v /var/lib/hermes-bots/test-worker/workspace:/workspaces/test-worker:rw,Z docker.io/nousresearch/hermes-agent@sha256:859d33c223ffa243f5927882b4f41263c5994218baa2197b3deeebbf9782ba72 -p test-worker cron create '$schedule' --name issue11-routine-proof --script issue11-routine-proof.sh --no-agent --deliver local --repeat 1")
job_id=$(awk '/Created job:/ {print $3}' <<<"$create")
[[ $job_id =~ ^[a-f0-9]{12}$ ]]
ssh -o BatchMode=yes "$SSH_USER@$HOST" 'sudo systemctl start hermes-gateway@test-worker.service; sudo /usr/local/libexec/hermes-fleet-wait-health test-worker gateway 180; sudo systemctl start hermes-serve@test-worker.service; sudo /usr/local/libexec/hermes-fleet-wait-health test-worker all 180'
client_count_before=$(ssh -o BatchMode=yes "$SSH_USER@$HOST" "ps -eo args= | awk '/\/opt\/hermes\/.venv\/bin\/hermes/ && \$0 !~ /gateway run|serve --isolated/ {n++} END{print n+0}'")
gateway_hpid_before=$(ssh -o BatchMode=yes "$SSH_USER@$HOST" "cd / && sudo -u bot-test-worker env XDG_RUNTIME_DIR=/run/user/1002 TMPDIR=/var/lib/hermes-bots/test-worker/tmp podman top hermes-test-worker-gateway hpid comm args | awk '\$2==\"hermes\" {print \$1; exit}'")
marker=
for _ in $(seq 1 48); do
  marker=$(ssh -o BatchMode=yes "$SSH_USER@$HOST" 'sudo test -f /var/lib/hermes-bots/test-worker/workspace/routine-proof.marker && sudo cat /var/lib/hermes-bots/test-worker/workspace/routine-proof.marker' 2>/dev/null || true)
  [[ $marker == routine-ran ]] && break
  sleep 5
done
[[ $marker == routine-ran ]]
receipt=$(ssh -o BatchMode=yes "$SSH_USER@$HOST" "cd / && sudo -u bot-test-worker env XDG_RUNTIME_DIR=/run/user/1002 TMPDIR=/var/lib/hermes-bots/test-worker/tmp podman exec hermes-test-worker-gateway hermes -p test-worker cron runs '$job_id' --limit 1")
grep -Eq "completed[[:space:]]+job=${job_id}[[:space:]]+source=builtin" <<<"$receipt"
run_id=$(awk 'NR==1 {print $1}' <<<"$receipt")
executed_at=$(awk 'NR==1 {print $5}' <<<"$receipt")
marker_sha256=$(ssh -o BatchMode=yes "$SSH_USER@$HOST" 'sudo sha256sum /var/lib/hermes-bots/test-worker/workspace/routine-proof.marker | cut -d" " -f1')
gateway_hpid_after=$(ssh -o BatchMode=yes "$SSH_USER@$HOST" "cd / && sudo -u bot-test-worker env XDG_RUNTIME_DIR=/run/user/1002 TMPDIR=/var/lib/hermes-bots/test-worker/tmp podman top hermes-test-worker-gateway hpid comm args | awk '\$2==\"hermes\" {print \$1; exit}'")
client_count_after=$(ssh -o BatchMode=yes "$SSH_USER@$HOST" "ps -eo args= | awk '/\/opt\/hermes\/.venv\/bin\/hermes/ && \$0 !~ /gateway run|serve --isolated/ {n++} END{print n+0}'")
[[ $gateway_hpid_before == "$gateway_hpid_after" && $client_count_before == 0 && $client_count_after == 0 ]]
ssh -o BatchMode=yes "$SSH_USER@$HOST" 'sudo rm -f /var/lib/hermes-bots/test-worker/workspace/routine-proof.marker /var/lib/hermes-bots/test-worker/hermes-install/profiles/test-worker/scripts/issue11-routine-proof.sh'
jq -n -S --arg observed_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --arg schedule "$schedule" --arg job_id "$job_id" --arg run_id "$run_id" --arg executed_at "$executed_at" --arg marker_sha256 "$marker_sha256" --argjson clients_before "$client_count_before" --argjson clients_after "$client_count_after" '{schema_version:"1.0",observed_at:$observed_at,bot:"test-worker",job_id:$job_id,run_id:$run_id,source:"builtin",mode:"no-agent",schedule:$schedule,executed_at:$executed_at,run_status:"completed",marker_sha256:$marker_sha256,gateway_process_persisted_through_run:true,interactive_client_process_count_before:$clients_before,interactive_client_process_count_after:$clients_after,authoritative_receipt_observed:true,passed:true}' >"$OUT"
printf 'routine evidence written to %s\n' "$OUT"
