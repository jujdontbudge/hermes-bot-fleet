#!/usr/bin/env bash
set -Eeuo pipefail

pass=true
failures=()
check() {
  local name=$1; shift
  if ! "$@" >/dev/null 2>&1; then
    pass=false
    failures+=("$name")
  fi
}

check sshd_config bash -c 'sshd -T | grep -qx "permitrootlogin no" && sshd -T | grep -qx "passwordauthentication no" && sshd -T | grep -qx "allowtcpforwarding no"'
check firewall_policy bash -c 'nft list chain inet hermes_filter input | grep -q "policy drop" && nft list chain inet hermes_filter forward | grep -q "policy drop"'
check patching bash -c 'systemctl is-enabled unattended-upgrades.service | grep -qx enabled && grep -q "Unattended-Upgrade.*1" /etc/apt/apt.conf.d/20auto-upgrades'
check mandatory_services bash -c 'for s in apparmor auditd chrony nftables ssh tailscaled unattended-upgrades; do systemctl is-active --quiet "$s" || exit 1; done'
check service_accounts bash -c 'for u in bot-chief bot-test-worker hermes-proxy hermes-backup; do test "$(getent passwd "$u" | cut -d: -f7)" = /usr/sbin/nologin || exit 1; passwd -S "$u" | grep -Eq "^[^ ]+ L "; done'
check bot_boundaries bash -c 'test "$(stat -c "%U:%G:%a" /var/lib/hermes-bots/chief)" = bot-chief:bot-chief:700 && test "$(stat -c "%U:%G:%a" /var/lib/hermes-bots/test-worker)" = bot-test-worker:bot-test-worker:700'
check rootless_subids bash -c 'grep -q "^bot-chief:" /etc/subuid && grep -q "^bot-chief:" /etc/subgid && grep -q "^bot-test-worker:" /etc/subuid && grep -q "^bot-test-worker:" /etc/subgid'
check kernel_hardening bash -c 'test "$(sysctl -n kernel.kptr_restrict)" = 2 && test "$(sysctl -n kernel.dmesg_restrict)" = 1 && test "$(sysctl -n kernel.unprivileged_userns_clone)" = 1'
check no_prohibited_listener bash -c '! ss -H -lnt | awk "{print \$4}" | grep -Eq "(^|:)(443|5900|6081|6082|8642|8701|8702|9222|9223)$"'
check bootstrap_marker bash -c 'jq -e ".state == \"HOST_HARDENED\" and .hermes_installed == false" /var/lib/hermes-provisioning/bootstrap.json'
check tailscale_installed command -v tailscale

fail_json=$(printf '%s\n' "${failures[@]:-}" | jq -Rsc 'split("\n") | map(select(length > 0))')
jq -cn --argjson passed "$pass" --argjson failures "$fail_json" \
  --arg boot_id "$(cat /proc/sys/kernel/random/boot_id)" --arg kernel "$(uname -r)" \
  --arg tailscale_state "$(tailscale status --json 2>/dev/null | jq -r '.BackendState // "Unknown"' 2>/dev/null || printf Unknown)" \
  '{schema_version:"1.0",control_set:"issue-10-host-hardening",passed:$passed,failures:$failures,boot_id:$boot_id,kernel:$kernel,tailscale_state:$tailscale_state}'
[[ $pass == true ]]
