#!/usr/bin/env bash
set -Eeuo pipefail

LOCATION=${LOCATION:-westus}
RESOURCE_GROUP=${RESOURCE_GROUP:-rg-hermes-fleet-prod}
DEPLOYMENT=${DEPLOYMENT:-issue-10-azure-runtime}
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
SSH_PUBLIC_KEY_FILE=${SSH_PUBLIC_KEY_FILE:-"$HOME/.ssh/id_ed25519.pub"}

[[ "$LOCATION" == westus ]] || { echo 'issue 10 live feasibility permits only westus' >&2; exit 2; }
az account show --query "state" -o tsv | grep -qx Enabled
[[ -f "$SSH_PUBLIC_KEY_FILE" ]] || { echo "operator public key not found: $SSH_PUBLIC_KEY_FILE" >&2; exit 2; }
[[ $(awk '{print NF}' "$SSH_PUBLIC_KEY_FILE") -ge 2 ]] || { echo 'invalid SSH public key' >&2; exit 2; }

az deployment sub create \
  --name "$DEPLOYMENT" \
  --location "$LOCATION" \
  --template-file "$ROOT/infra/azure/main.bicep" \
  --parameters location="$LOCATION" resourceGroupName="$RESOURCE_GROUP" \
    adminSshPublicKey="$(<"$SSH_PUBLIC_KEY_FILE")" \
  --query '{provisioningState:properties.provisioningState,outputs:properties.outputs}' \
  --output json

# A managed OS disk is not an application endpoint and must not support public
# SAS export/import. The VM attachment continues to work with both controls denied.
az disk update --resource-group "$RESOURCE_GROUP" --name vm-hermes-fleet-01-osdisk \
  --network-access-policy DenyAll --public-network-access Disabled --output none

if [[ ${SKIP_BOOTSTRAP:-false} != true ]]; then
  az vm run-command invoke \
    --resource-group "$RESOURCE_GROUP" \
    --name vm-hermes-fleet-01 \
    --command-id RunShellScript \
    --scripts @"$ROOT/scripts/azure/bootstrap-host.sh" \
    --query "value[].{code:code,message:message}" \
    --output json
fi
