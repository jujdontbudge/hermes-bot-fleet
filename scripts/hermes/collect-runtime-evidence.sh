#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
HOST=${HOST:-fleet-server.tail2ea909.ts.net}
SSH_USER=${SSH_USER:-fleetadmin}
OUT=${OUT:-"$ROOT/evidence/issue-11"}
mkdir -p "$OUT"
tmp=$(mktemp -d "${TMPDIR:-/tmp}/issue11-evidence.XXXXXX")
trap 'rm -rf "$tmp"' EXIT INT TERM

ssh -o BatchMode=yes -o ConnectTimeout=10 "$SSH_USER@$HOST" 'sudo /usr/local/libexec/hermes-fleet-verify' >"$tmp/host.json"
probe() { if nc -z -G 5 -w 3 "$HOST" "$1" >/dev/null 2>&1; then printf reachable; else printf denied; fi; }
ssh_state=$(probe 22); [[ $ssh_state == reachable ]]
control=$(probe 443); [[ $control == reachable ]] || control=not-configured
prohibited='{}'
for port in 8642 8701 8702 9222 9223; do
  state=$(probe "$port"); [[ $state == denied ]] || { echo "prohibited port $port reachable" >&2; exit 1; }
  prohibited=$(jq -c --arg p "$port" --arg s "$state" '. + {($p):$s}' <<<"$prohibited")
done
jq -S --arg target "$HOST" --arg ssh "$ssh_state" --arg control "$control" --argjson prohibited "$prohibited" \
  '. + {external_probes:{target:$target,ssh_22:$ssh,control_443:$control,prohibited:$prohibited}}' "$tmp/host.json" >"$OUT/runtime.json"
python3 - "$OUT/runtime.json" <<'PY'
import json,re,sys
p=json.load(open(sys.argv[1]))
assert p['passed'] is True and not p['failures']
assert [x['bot'] for x in p['bots']]==['chief','test-worker']
assert p['network']=={'api_8642_listener_count':0,'public_control_listener_count':0}
assert p['scheduler']=={'owner':'gateway','standalone_cron_service_count':0}
assert p['external_probes']['ssh_22']=='reachable'
assert set(p['external_probes']['prohibited'].values())=={'denied'}
for b in p['bots']:
    assert b['gateway_pid_count']==b['isolated_serve_pid_count']==1
    assert b['model']=='gpt-5.6-sol' and b['provider']=='openai-codex'
    assert re.fullmatch(r'sha256:[a-f0-9]{64}',b['runtime_image_digest'])
    forbidden=('token','secret','password','authorization','cookie')
    assert not any(x in json.dumps(b).lower() for x in forbidden)
PY
printf 'sanitized evidence written to %s/runtime.json\n' "$OUT"
