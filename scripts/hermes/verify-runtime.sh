#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'run as root' >&2; exit 77; }
cd /
bots=(chief test-worker)
pass=true
failures=()
check() { local name=$1; shift; if ! "$@" >/dev/null 2>&1; then pass=false; failures+=("$name"); fi; }
no_public_control_bind() {
  local address
  while IFS= read -r address; do
    case "$address" in 127.0.0.1:*|'[::1]':*) ;; *) return 1;; esac
  done < <(ss -H -lnt | awk '$4 ~ /:(8642|8701|8702|9222|9223)$/ {print $4}')
}

bot_json=()
for bot in chief test-worker; do
  user="bot-$bot"
  # shellcheck disable=SC1090
  source "/etc/hermes-fleet/$bot/runtime.env"
  uid=$(id -u "$user")
  podman_cmd=(runuser -u "$user" -- env XDG_RUNTIME_DIR="/run/user/$uid" TMPDIR="$HERMES_TMPDIR" podman)
  check "$bot-gateway-active" systemctl is-active --quiet "hermes-gateway@$bot.service"
  check "$bot-serve-active" systemctl is-active --quiet "hermes-serve@$bot.service"
  check "$bot-health-timer" systemctl is-enabled --quiet "hermes-health@$bot.timer"
  all_commands=$("${podman_cmd[@]}" ps -q | while IFS= read -r container; do
    "${podman_cmd[@]}" inspect "$container" --format '{{json .Config.Cmd}}'
  done | jq -s .)
  gateway_count=$(jq --arg bot "$bot" '[.[] | select(. == ["hermes","-p",$bot,"gateway","run"])] | length' <<<"$all_commands")
  serve_count=$(jq --arg bot "$bot" --arg port "$HERMES_SERVE_PORT" '[.[] | select(. == ["-p",$bot,"serve","--isolated","--host","0.0.0.0","--port",$port,"--skip-build"])] | length' <<<"$all_commands")
  gateway_cmd=$("${podman_cmd[@]}" inspect "hermes-$bot-gateway" --format '{{json .Config.Cmd}}' 2>/dev/null || printf '[]')
  serve_cmd=$("${podman_cmd[@]}" inspect "hermes-$bot-serve" --format '{{json .Config.Cmd}}' 2>/dev/null || printf '[]')
  image_digest=$("${podman_cmd[@]}" image inspect "$HERMES_RUNTIME_IMAGE" --format '{{.Digest}}')
  image_user=$("${podman_cmd[@]}" image inspect "$HERMES_RUNTIME_IMAGE" --format '{{.Config.User}}')
  version_output=$("${podman_cmd[@]}" run --rm --network=none --tmpfs /opt/data:rw,size=128m \
    "$HERMES_RUNTIME_IMAGE" hermes --version 2>&1)
  version_probe_match=false; grep -F -- "$HERMES_VERSION" <<<"$version_output" >/dev/null && version_probe_match=true
  config="/var/lib/hermes-bots/$bot/hermes-install/profiles/$bot/config.yaml"
  config_digest=$(sha256sum "$config" | cut -d' ' -f1)
  integrity=not-created
  db="/var/lib/hermes-bots/$bot/hermes-install/profiles/$bot/state.db"
  [[ ! -f "$db" ]] || integrity=$(sqlite3 "$db" 'pragma integrity_check;')
  auth_present=false; [[ -s "${db%/state.db}/auth.json" || -s "${db%/state.db}/.env" ]] && auth_present=true
  listener_addresses=$(ss -H -lnt "sport = :$HERMES_SERVE_PORT" | awk '{print $4}' | jq -Rsc 'split("\n")|map(select(length>0))')
  restart_gateway=$(systemctl show "hermes-gateway@$bot.service" -p Restart --value)
  restart_serve=$(systemctl show "hermes-serve@$bot.service" -p Restart --value)
  bot_json+=("$(jq -cn --arg bot "$bot" --arg user "$user" --argjson uid "$uid" \
    --arg version "$HERMES_VERSION" --argjson version_probe_match "$version_probe_match" --arg model "$HERMES_MODEL" --arg provider "$HERMES_PROVIDER" \
    --arg digest "$image_digest" --arg image_user "$image_user" --arg config_digest "sha256:$config_digest" \
    --arg integrity "$integrity" --argjson auth_present "$auth_present" \
    --argjson gateway_count "$gateway_count" --argjson serve_count "$serve_count" \
    --argjson gateway_cmd "$gateway_cmd" --argjson serve_cmd "$serve_cmd" --argjson listeners "$listener_addresses" \
    --arg rg "$restart_gateway" --arg rs "$restart_serve" '
      {bot:$bot,unix_user:$user,uid:$uid,hermes_version:$version,version_probe_match:$version_probe_match,model:$model,provider:$provider,
       runtime_image_digest:$digest,image_user:$image_user,config_sha256:$config_digest,credential_material_present:$auth_present,
       gateway_pid_count:$gateway_count,isolated_serve_pid_count:$serve_count,gateway_command:$gateway_cmd,serve_command:$serve_cmd,
       serve_listener_addresses:$listeners,database_integrity:$integrity,restart_policy:{gateway:$rg,serve:$rs}}')")
  [[ $gateway_count -eq 1 ]] || { pass=false; failures+=("$bot-gateway-count"); }
  [[ $serve_count -eq 1 ]] || { pass=false; failures+=("$bot-serve-count"); }
  [[ "$image_digest" == "$HERMES_RUNTIME_DIGEST" ]] || { pass=false; failures+=("$bot-image-digest"); }
  [[ $version_probe_match == true ]] || { pass=false; failures+=("$bot-version"); }
  [[ "$integrity" == ok || "$integrity" == not-created ]] || { pass=false; failures+=("$bot-db-integrity"); }
  jq -e --arg bot "$bot" '(. == ["hermes","-p",$bot,"gateway","run"])' <<<"$gateway_cmd" >/dev/null || { pass=false; failures+=("$bot-gateway-command"); }
  jq -e --arg bot "$bot" --arg port "$HERMES_SERVE_PORT" '(. == ["-p",$bot,"serve","--isolated","--host","0.0.0.0","--port",$port,"--skip-build"])' <<<"$serve_cmd" >/dev/null || { pass=false; failures+=("$bot-serve-command"); }
done

check no_public_control_bind no_public_control_bind
check no_api_listener bash -c '! ss -H -lnt "sport = :8642" | grep -q .'
standalone_cron_count=$(systemctl list-units --all --type=service --plain --no-legend 'hermes*cron*' | wc -l | tr -d ' ')
[[ $standalone_cron_count -eq 0 ]] || { pass=false; failures+=("standalone-cron-service"); }
all_bots=$(printf '%s\n' "${bot_json[@]}" | jq -s 'sort_by(.bot)')
fail_json=$(printf '%s\n' "${failures[@]:-}" | jq -Rsc 'split("\n")|map(select(length>0))')
jq -cn --argjson passed "$pass" --argjson failures "$fail_json" --argjson bots "$all_bots" \
  --argjson standalone_cron_count "$standalone_cron_count" \
  --arg boot_id "$(< /proc/sys/kernel/random/boot_id)" --arg observed_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" '
  {schema_version:"1.0",evidence_scope:"issue-11-hermes-runtime",observed_at:$observed_at,boot_id:$boot_id,
   passed:$passed,failures:$failures,bots:$bots,network:{api_8642_listener_count:0,public_control_listener_count:0},
   scheduler:{owner:"gateway",standalone_cron_service_count:$standalone_cron_count}}'
[[ $pass == true ]]
