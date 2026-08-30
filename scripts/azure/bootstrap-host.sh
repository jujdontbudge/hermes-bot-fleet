#!/usr/bin/env bash
set -Eeuo pipefail
export DEBIAN_FRONTEND=noninteractive

retry() {
  local attempts=0
  until "$@"; do
    attempts=$((attempts + 1))
    if (( attempts >= 5 )); then return 1; fi
    sleep $((attempts * 3))
  done
}

retry apt-get update -y
retry apt-get dist-upgrade -y
retry apt-get install -y --no-install-recommends \
  apparmor apparmor-utils auditd audispd-plugins ca-certificates chrony curl \
  fail2ban fuse-overlayfs gnupg jq libpam-tmpdir logrotate needrestart nftables \
  podman rootlesskit slirp4netns uidmap unattended-upgrades

install -d -m 0755 /usr/share/keyrings
if [[ ! -s /usr/share/keyrings/tailscale-archive-keyring.gpg ]]; then
  curl --fail --silent --show-error --location \
    https://pkgs.tailscale.com/stable/ubuntu/noble.noarmor.gpg \
    -o /usr/share/keyrings/tailscale-archive-keyring.gpg
  chmod 0644 /usr/share/keyrings/tailscale-archive-keyring.gpg
fi
cat >/etc/apt/sources.list.d/tailscale.list <<'EOF'
deb [signed-by=/usr/share/keyrings/tailscale-archive-keyring.gpg] https://pkgs.tailscale.com/stable/ubuntu noble main
EOF
retry apt-get update -y
retry apt-get install -y --no-install-recommends tailscale

cat >/etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
cat >/etc/apt/apt.conf.d/52hermes-unattended-upgrades <<'EOF'
Unattended-Upgrade::Allowed-Origins {
  "${distro_id}:${distro_codename}";
  "${distro_id}:${distro_codename}-security";
  "${distro_id}ESMApps:${distro_codename}-apps-security";
  "${distro_id}ESM:${distro_codename}-infra-security";
};
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "03:30";
EOF

cat >/etc/ssh/sshd_config.d/60-hermes-hardening.conf <<'EOF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no
PubkeyAuthentication yes
AllowAgentForwarding no
AllowTcpForwarding no
GatewayPorts no
PermitTunnel no
X11Forwarding no
PermitUserEnvironment no
MaxAuthTries 3
LoginGraceTime 30
ClientAliveInterval 300
ClientAliveCountMax 2
EOF
install -d -m 0755 /run/sshd
sshd -t

cat >/etc/nftables.conf <<'EOF'
#!/usr/sbin/nft -f
flush ruleset

table inet hermes_filter {
  chain input {
    type filter hook input priority filter; policy drop;
    iifname "lo" accept
    ct state established,related accept
    ct state invalid drop
    iifname "tailscale0" tcp dport { 22, 443 } ct state new accept
  }
  chain forward {
    type filter hook forward priority filter; policy drop;
  }
  chain output {
    type filter hook output priority filter; policy accept;
  }
}
EOF
nft -c -f /etc/nftables.conf
nft -f /etc/nftables.conf

cat >/etc/sysctl.d/60-hermes-sandbox.conf <<'EOF'
# Rootless containers and Chromium must retain their non-setuid user namespace sandbox.
kernel.unprivileged_userns_clone=1
kernel.kptr_restrict=2
kernel.dmesg_restrict=1
fs.protected_fifos=2
fs.protected_regular=2
fs.protected_hardlinks=1
fs.protected_symlinks=1
net.ipv4.conf.all.accept_redirects=0
net.ipv4.conf.default.accept_redirects=0
net.ipv4.conf.all.send_redirects=0
net.ipv4.conf.default.send_redirects=0
net.ipv4.conf.all.accept_source_route=0
net.ipv4.conf.default.accept_source_route=0
net.ipv6.conf.all.accept_redirects=0
net.ipv6.conf.default.accept_redirects=0
EOF
sysctl --system >/dev/null

ensure_user() {
  local user="$1"
  if ! getent passwd "$user" >/dev/null; then
    useradd --create-home --shell /usr/sbin/nologin --user-group "$user"
  fi
  usermod --lock --shell /usr/sbin/nologin "$user"
}
for user in bot-chief bot-test-worker hermes-proxy hermes-backup; do ensure_user "$user"; done

ensure_subids() {
  local user="$1"
  grep -q "^${user}:" /etc/subuid || usermod --add-subuids 100000-165535 "$user"
  grep -q "^${user}:" /etc/subgid || usermod --add-subgids 100000-165535 "$user"
}
ensure_subids bot-chief
ensure_subids bot-test-worker

create_bot_tree() {
  local bot="$1" user="$2" root="/var/lib/hermes-bots/$1"
  install -d -m 0700 -o "$user" -g "$user" \
    "$root" "$root/hermes-install" "$root/hermes-install/profiles" \
    "$root/hermes-install/profiles/$bot" "$root/hermes-install/profiles/$bot/home" \
    "$root/workspace" "$root/browser" "$root/downloads" \
    "$root/downloads/incoming" "$root/downloads/released" \
    "$root/audit" "$root/backup-staging"
}
install -d -m 0755 -o root -g root /var/lib/hermes-bots
create_bot_tree chief bot-chief
create_bot_tree test-worker bot-test-worker
install -d -m 0700 -o hermes-proxy -g hermes-proxy /var/lib/hermes-proxy
install -d -m 0700 -o hermes-backup -g hermes-backup /var/lib/hermes-backup
install -d -m 0755 -o root -g root /opt/hermes-agent

cat >/etc/audit/rules.d/hermes-fleet.rules <<'EOF'
-w /etc/nftables.conf -p wa -k hermes_network_policy
-w /etc/ssh/sshd_config.d/60-hermes-hardening.conf -p wa -k hermes_ssh_policy
-w /var/lib/hermes-bots -p wa -k hermes_bot_state
EOF
augenrules --load >/dev/null || true

systemctl enable --now apparmor.service auditd.service chrony.service nftables.service ssh.service tailscaled.service unattended-upgrades.service
systemctl disable --now ssh.socket 2>/dev/null || true
systemctl restart ssh.service nftables.service

# Enrollment is a separate post-hardening Run Command step.
tailscale down 2>/dev/null || true

install -d -m 0755 /var/lib/hermes-provisioning
cat >/var/lib/hermes-provisioning/bootstrap.json <<EOF
{"schema_version":"1.0","state":"HOST_HARDENED","hermes_installed":false,"completed_at":"$(date -u +%Y-%m-%dT%H:%M:%SZ)"}
EOF
chmod 0644 /var/lib/hermes-provisioning/bootstrap.json

printf '%s\n' 'HOST_HARDENED'
