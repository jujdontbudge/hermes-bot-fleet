#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
RESOURCE_GROUP=${RESOURCE_GROUP:-rg-hermes-fleet-prod}
VM=${VM:-vm-hermes-fleet-01}
OUT=${OUT:-"$ROOT/evidence/issue-10"}
mkdir -p "$OUT"
tmp=$(mktemp -d "${TMPDIR:-/tmp}/issue10-evidence.XXXXXX")
trap 'rm -rf "$tmp"' EXIT INT TERM

az group show -n "$RESOURCE_GROUP" -o json >"$tmp/group.json"
az vm show -g "$RESOURCE_GROUP" -n "$VM" -d -o json >"$tmp/vm.json"
az network nic show -g "$RESOURCE_GROUP" -n nic-hermes-fleet-01 -o json >"$tmp/nic.json"
az network nsg show -g "$RESOURCE_GROUP" -n nsg-hermes-fleet-prod -o json >"$tmp/nsg.json"
az disk show -g "$RESOURCE_GROUP" -n "${VM}-osdisk" -o json >"$tmp/disk.json"
az vm get-instance-view -g "$RESOURCE_GROUP" -n "$VM" -o json >"$tmp/instance.json"
principal_id=$(az vm show -g "$RESOURCE_GROUP" -n "$VM" --query identity.principalId -o tsv)
az role assignment list --assignee-object-id "$principal_id" --all -o json >"$tmp/roles.json"
az vm run-command invoke -g "$RESOURCE_GROUP" -n "$VM" --command-id RunShellScript \
  --scripts @"$ROOT/scripts/azure/verify-host.sh" -o json >"$tmp/host-command.json"

jq -n -S \
  --slurpfile group "$tmp/group.json" --slurpfile vm "$tmp/vm.json" \
  --slurpfile nic "$tmp/nic.json" --slurpfile nsg "$tmp/nsg.json" \
  --slurpfile disk "$tmp/disk.json" --slurpfile instance "$tmp/instance.json" \
  --slurpfile roles "$tmp/roles.json" '
  ($group[0]) as $g | ($vm[0]) as $v | ($nic[0]) as $n |
  ($nsg[0]) as $s | ($disk[0]) as $d | ($instance[0]) as $i |
  {
    schema_version:"1.0", evidence_scope:"issue-10-azure-runtime",
    resource_group:{id:($g.id|sub("^/subscriptions/[^/]+";"/subscriptions/[REDACTED]")),name:$g.name,location:$g.location,tags:$g.tags},
    vm:{id:($v.id|sub("^/subscriptions/[^/]+";"/subscriptions/[REDACTED]")),name:$v.name,location:$v.location,power_state:$v.powerState,
      private_ips:$v.privateIps,public_ips:($v.publicIps // ""),identity_type:$v.identity.type,
      managed_identity_role_assignment_count:($roles[0]|length),
      vm_size:$v.hardwareProfile.vmSize,security_type:$v.securityProfile.securityType,
      encryption_at_host:$v.securityProfile.encryptionAtHost,
      secure_boot:$v.securityProfile.uefiSettings.secureBootEnabled,
      vtpm:$v.securityProfile.uefiSettings.vTpmEnabled,
      patch_mode:$v.osProfile.linuxConfiguration.patchSettings.patchMode,
      assessment_mode:$v.osProfile.linuxConfiguration.patchSettings.assessmentMode,
      password_auth_disabled:$v.osProfile.linuxConfiguration.disablePasswordAuthentication},
    network:{nic_id:($n.id|sub("^/subscriptions/[^/]+";"/subscriptions/[REDACTED]")),
      public_ip_association_count:([($n.ipConfigurations // [])[]|select(.publicIPAddress != null)]|length),
      ip_forwarding:$n.enableIPForwarding,accelerated_networking:$n.enableAcceleratedNetworking,
      nsg_id:($s.id|sub("^/subscriptions/[^/]+";"/subscriptions/[REDACTED]")),custom_inbound_allow_rule_count:([($s.securityRules // [])[]|select(.direction=="Inbound" and .access=="Allow")]|length)},
    disk:{id:($d.id|sub("^/subscriptions/[^/]+";"/subscriptions/[REDACTED]")),sku:$d.sku.name,size_gb:$d.diskSizeGB,encryption_type:$d.encryption.type,
      network_access_policy:$d.networkAccessPolicy,public_network_access:$d.publicNetworkAccess},
    instance:{provisioning_state:([($i.instanceView.statuses // [])[]|select(.code|startswith("ProvisioningState/"))][0].displayStatus),
      power_state:([($i.instanceView.statuses // [])[]|select(.code|startswith("PowerState/"))][0].displayStatus)}
  }' >"$OUT/azure-controls.json"

# Run Command wraps stdout; retain only the final machine-readable host line.
jq -r '[.value[].message | split("\n")[] | select(startswith("{"))] | last' \
  "$tmp/host-command.json" | jq -S . >"$OUT/host-controls.json"

jq -e '
  .vm.public_ips=="" and .network.public_ip_association_count==0 and
  .network.custom_inbound_allow_rule_count==0 and .network.ip_forwarding==false and
  .vm.identity_type=="SystemAssigned" and .vm.security_type=="TrustedLaunch" and
  .vm.managed_identity_role_assignment_count==0 and
  .vm.encryption_at_host==true and .vm.secure_boot==true and .vm.vtpm==true and
  .vm.password_auth_disabled==true and .vm.patch_mode=="AutomaticByPlatform" and
  .disk.encryption_type=="EncryptionAtRestWithPlatformKey" and
  .disk.network_access_policy=="DenyAll" and .disk.public_network_access=="Disabled" and
  .instance.provisioning_state=="Provisioning succeeded" and .instance.power_state=="VM running"
' "$OUT/azure-controls.json" >/dev/null
jq -e '.passed==true' "$OUT/host-controls.json" >/dev/null
printf 'evidence written to %s\n' "$OUT"
