# Azure Server Runtime provisioning and evidence

Issue: #10. Scope: base private Azure VM and host hardening only. Hermes services,
browser containers, backup storage, proxy, and application credentials remain later
deployment gates and are not claimed by this runbook.

## Deploy

Prerequisites are Azure CLI authentication and the operator's durable public key at
`~/.ssh/id_ed25519.pub`. The private key never enters Azure CLI, Git, or evidence.

```sh
az bicep build --file infra/azure/main.bicep
az deployment sub what-if --location westus --template-file infra/azure/main.bicep \
  --parameters adminSshPublicKey="$(<~/.ssh/id_ed25519.pub)"
scripts/azure/deploy.sh
```

The VM has no public IP and the NSG has no custom inbound allow. Azure Run Command,
which uses the outbound VM agent channel, is the only bootstrap path before Tailscale.
The bootstrap patches Ubuntu, configures SSH and default-drop nftables, creates locked
service identities and separated mode-0700 state roots, enables auditing/time sync/
automatic updates, and installs but deliberately does not enroll Tailscale.

### Live feasibility decision (2026-08-28 UTC)

The subscription's enforced allowed-location policy rejects Central US. East US 2 is
allowed, but every usable 8 GiB SKU was subscription-restricted and the request for
two `StandardDasv7Family` vCPUs failed with `ResourceNotAvailableForOffer`. West US is
the least-cost allowed fallback with live quota and availability: `Standard_D2s_v3`
(2 vCPU, 8 GiB, encryption-at-host supported), Standard DSv3 quota 4 vCPU, regional
quota 6 vCPU. This exception supersedes the preferred-region assumption only because
neither preferred region was deployable; it does not relax any security or cost
boundary. Current retail baseline is USD 0.117/hour for Linux compute (USD 85.41
at 730 hours) plus USD 9.60/month for the 128 GiB E10 Standard SSD: USD 95.01/month
before small transaction/diagnostic charges, within the USD 100 monthly student credit.
The machine-readable quote inputs and source URLs are retained in
`evidence/issue-10/feasibility.json`.

## Verify, reboot, and collect

```sh
scripts/azure/collect-evidence.sh
az vm restart -g rg-hermes-fleet-prod -n vm-hermes-fleet-01
az vm wait -g rg-hermes-fleet-prod -n vm-hermes-fleet-01 --updated --timeout 600
scripts/azure/collect-evidence.sh
```

The collector fails unless Azure and host controls pass and writes only sanitized,
machine-readable facts under `evidence/issue-10/`. Subscription/tenant IDs, SSH key
material, Run Command wrapper logs, and credential-bearing URLs are excluded.

## Tailscale enrollment checkpoint

Only after hardening and reboot verification, invoke this exact command through Azure
Run Command (never cloud-init or a public SSH bootstrap):

```sh
az vm run-command invoke -g rg-hermes-fleet-prod -n vm-hermes-fleet-01 \
  --command-id RunShellScript --scripts 'timeout 30s tailscale up --hostname=fleet-server --ssh=false'
```

If the command returns a one-time authorization URL, store it outside Git and present
it as the sole human checkpoint. Do not add the URL to evidence, logs, commits, issues,
or documentation. After authorization, rerun the collector and inspect `tailscale
status --json` through Run Command; Tailscale SSH must remain false. Tailnet ACL/device
posture authorization is a human control-plane step and is not inferred from node
enrollment.

The reviewed default-deny policy is `infra/tailscale/policy.hujson`. In the Tailscale
admin console, replace the default allow-all policy with that file and save only after
its embedded tests pass. It grants Johan's account only TCP 22/443 to the stable
`fleet-server` address, denies all other paths implicitly, and includes explicit denial
tests. MagicDNS must remain enabled; Funnel, Tailscale SSH, exit-node advertisement,
subnet routes, and public sharing remain disabled. After the approved Mac joins the
same tailnet, verify SSH with the durable key to `fleet-server.tail2ea909.ts.net`, test
TCP 443 reachability, and prove the listed prohibited ports fail.
