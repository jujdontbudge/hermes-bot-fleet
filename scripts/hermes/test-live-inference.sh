#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
HOST=${HOST:-fleet-server.tail2ea909.ts.net}
SSH_USER=${SSH_USER:-fleetadmin}
OUT=${OUT:-"$ROOT/evidence/issue-11/live-inference.json"}
[[ ${1:-} == --maintenance-approved ]] || { echo 'requires --maintenance-approved' >&2; exit 64; }
restore() {
  ssh -o BatchMode=yes "$SSH_USER@$HOST" 'sudo systemctl start hermes-gateway@chief.service hermes-gateway@test-worker.service; sudo systemctl start hermes-serve@chief.service hermes-serve@test-worker.service' >/dev/null 2>&1 || true
}
trap restore EXIT INT TERM
mkdir -p "$(dirname "$OUT")"
results='[]'
for spec in 'chief:1001:CHIEF-RUNTIME-OK' 'test-worker:1002:TEST-WORKER-RUNTIME-OK'; do
  IFS=: read -r bot uid expected <<<"$spec"
  ssh -o BatchMode=yes "$SSH_USER@$HOST" "sudo systemctl stop hermes-serve@$bot.service hermes-gateway@$bot.service"
  output=$(ssh -o BatchMode=yes "$SSH_USER@$HOST" "cd / && sudo -u bot-$bot env XDG_RUNTIME_DIR=/run/user/$uid TMPDIR=/var/lib/hermes-bots/$bot/tmp podman run --rm --network=slirp4netns:allow_host_loopback=false --userns=keep-id:uid=1000,gid=1000 --user 1000:1000 --entrypoint /opt/hermes/.venv/bin/hermes -e HOME=/opt/data/profiles/$bot/home -v /var/lib/hermes-bots/$bot/hermes-install:/opt/data:rw,Z -v /var/lib/hermes-bots/$bot/workspace:/workspaces/$bot:rw,Z docker.io/nousresearch/hermes-agent@sha256:859d33c223ffa243f5927882b4f41263c5994218baa2197b3deeebbf9782ba72 -p $bot -z 'Reply with exactly: $expected'")
  [[ "$output" == "$expected" ]]
  ssh -o BatchMode=yes "$SSH_USER@$HOST" "sudo systemctl start hermes-gateway@$bot.service; sudo /usr/local/libexec/hermes-fleet-wait-health $bot gateway 180; sudo systemctl start hermes-serve@$bot.service; sudo /usr/local/libexec/hermes-fleet-wait-health $bot all 180"
  results=$(jq -c --arg bot "$bot" --arg expected "$expected" '. + [{bot:$bot,model_query_passed:true,exact_result:$expected}]' <<<"$results")
done
trap - EXIT INT TERM
isolation=$(ssh -o BatchMode=yes "$SSH_USER@$HOST" 'set -e; if sudo -u bot-chief test -r /var/lib/hermes-bots/test-worker/hermes-install/profiles/test-worker/auth.json; then exit 1; fi; if sudo -u bot-test-worker test -r /var/lib/hermes-bots/chief/hermes-install/profiles/chief/auth.json; then exit 1; fi; printf pass')
[[ $isolation == pass ]]
ssh -o BatchMode=yes "$SSH_USER@$HOST" 'sudo /usr/local/libexec/hermes-fleet-verify' >/dev/null
jq -n -S --arg observed_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --argjson results "$results" '{schema_version:"1.0",observed_at:$observed_at,provider:"openai-codex",model:"gpt-5.6-sol",results:$results,cross_bot_credential_read_denied:true,post_test_runtime_healthy:true,passed:true}' >"$OUT"
printf 'live inference evidence written to %s\n' "$OUT"
