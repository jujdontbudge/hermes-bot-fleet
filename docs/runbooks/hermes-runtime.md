# Persistent Hermes Server Runtime

Issue: [Install and supervise the persistent Hermes Runtime](https://github.com/JohanSardar/hermes-bot-fleet/issues/11)

This runbook installs the two server Bot runtimes only: `chief` and `test-worker`. It does not deploy browser/noVNC, the private reverse proxy/TLS frontend, backups, Mac services, or Telegram credentials. Those remain separate release gates. The Desktop backends created here are intentionally host-loopback-only until the reviewed tailnet HTTPS proxy is installed; an SSH tunnel may be used for an operator-only preflight, but no non-loopback port may be opened.

## Invariants

- The reviewed deployment manifest is committed at `infra/hermes/runtime-manifest.json`. It pins Hermes `0.20.6` / upstream `52e5e7c0` as `docker.io/nousresearch/hermes-agent@sha256:859d33c223ffa243f5927882b4f41263c5994218baa2197b3deeebbf9782ba72`; floating tags are rejected.
- The official image intentionally reports OCI `Config.User=root` because s6 performs startup reconciliation before dropping to its `hermes` user. The host launches it through each Bot's rootless Podman namespace, maps that Bot to container UID/GID 1000, publishes loopback only, and provides no host/container-engine socket or host capabilities.
- `bot-chief` and `bot-test-worker` own separate installation roots, profiles, workspaces, credentials, Podman storage, and containers.
- Model/provider are exactly `gpt-5.6-sol` through `openai-codex`, with no configured fallback.
- Each profile has one s6-backed `hermes -p BOT gateway run`, which alone owns messaging polling and cron. The isolated Desktop backend bypasses image PID-1 reconciliation with the immutable Hermes entrypoint and runs exactly one `-p BOT serve --isolated --host 0.0.0.0 --port PORT --skip-build`; this prevents a second gateway from being restored in the serve container.
- Host publications are only `127.0.0.1:8701` and `127.0.0.1:8702`. Port 8642 is unused. Gateway has no inbound listener.
- Secrets are provisioned directly into each Bot-owned profile as supported Hermes `auth.json`/`.env` material, mode 0600. Both `chief` and `test-worker` completed independent official OpenAI Codex device flows. Their credential-file one-way digests differ and reciprocal Unix reads are denied. Both authorizations may still belong to the same provider account, so account-level revocation remains shared. Never print, clone, or commit either credential.
- Each profile has a generated, non-committed Dashboard basic-auth password, stable signing secret, and hash, with the bundled `dashboard_auth/basic` plugin enabled. This satisfies the official non-loopback-in-container auth gate even though host publication is loopback-only.
- Ubuntu 24.04's `kernel.apparmor_restrict_unprivileged_userns=1` blocks the nested sandbox used by `slirp4netns` after rootless Podman namespace recreation. The dedicated fleet VM therefore installs `infra/hermes/sysctl/90-hermes-rootless.conf` with that restriction disabled. The compensating boundary is explicit: dedicated non-login Bot users, subordinate-ID rootless namespaces, container `no-new-privileges`, seccomp, cgroup limits, no engine socket, no host root mount, Bot-scoped 0700 state, and loopback-only publications.

## 1. Inspect the immutable live manifest

The approved manifest is committed and contains no credentials:

```json
{
  "schema_version": "1.0",
  "hermes_version": "0.20.6",
  "runtime_image": "docker.io/nousresearch/hermes-agent@sha256:859d33c223ffa243f5927882b4f41263c5994218baa2197b3deeebbf9782ba72",
  "runtime_image_digest": "sha256:859d33c223ffa243f5927882b4f41263c5994218baa2197b3deeebbf9782ba72",
  "model": "gpt-5.6-sol",
  "provider": "openai-codex",
  "bots": {
    "chief": {"unix_user": "bot-chief", "serve_port": 8701, "workspace": "/workspaces/chief"},
    "test-worker": {"unix_user": "bot-test-worker", "serve_port": 8702, "workspace": "/workspaces/test-worker"}
  }
}
```

The deployed image was independently probed as `Hermes Agent v0.20.6 (2026.8.27) · upstream 52e5e7c0`. Do not replace the digest with a floating tag.

## 2. Install without activation

Copy this repository to a root-owned staging directory on `fleet-server`, then:

```sh
sudo scripts/hermes/install-runtime.sh --manifest infra/hermes/runtime-manifest.json --no-start
sudo systemd-analyze verify infra/hermes/systemd/*.service infra/hermes/systemd/*.timer infra/hermes/systemd/*.target
```

The installer validates identities created by issue 10, writes only non-secret config/environment, pulls the digest-pinned image independently under each Unix identity, and installs systemd units and health helpers.

## 3. Provision credentials out of band and activate

Using a human/admin channel that does not expose values to Hermes, shell history, logs, Git, or evidence, provision each profile's supported OpenAI Codex OAuth state and separate Telegram credential. Confirm ownership and mode without printing content:

```sh
sudo chown bot-chief:bot-chief /var/lib/hermes-bots/chief/hermes-install/profiles/chief/{auth.json,.env}
sudo chown bot-test-worker:bot-test-worker /var/lib/hermes-bots/test-worker/hermes-install/profiles/test-worker/{auth.json,.env}
sudo chmod 0600 /var/lib/hermes-bots/{chief/hermes-install/profiles/chief,test-worker/hermes-install/profiles/test-worker}/{auth.json,.env}
sudo scripts/hermes/install-runtime.sh --manifest infra/hermes/runtime-manifest.json
```

If a supported Hermes build stores only one of those files, provision only that file. The installer requires at least one credential store per Bot and never reads it.

## 4. Verify

On the VM:

```sh
sudo /usr/local/libexec/hermes-fleet-verify | jq .
sudo systemctl status hermes-runtime@chief.target hermes-runtime@test-worker.target
sudo ss -lnt
```

From Johan's approved Mac, collect sanitized dual-plane evidence:

```sh
scripts/hermes/collect-runtime-evidence.sh
```

This writes `evidence/issue-11/runtime.json`. It contains versions, digests, safe command arrays, process counts, listener classes, DB integrity, boot ID, and negative private-network probes. It never contains environment values, auth contents, logs, prompts, messages, URLs, tokens, or cookies. TCP 443 may be `not-configured` until the separate reviewed private proxy is installed; prohibited ports must always be denied.

Retained live acceptance evidence is split by concern:

- `evidence/issue-11/runtime.json` — final dual-Bot process, image, model/provider, listener, DB, and external-port state.
- `evidence/issue-11/live-inference.json` — successful exact one-shot OpenAI Codex inference from both isolated profiles and cross-Bot credential-read denial.
- `evidence/issue-11/crash-recovery.json` — historical pre-activation live-runtime SIGKILL recovery for both gateway and serve processes, all under 120 seconds. It is retained honestly but is not eligible as the disposable-fixture proof required by catalog SVC-002/SVC-003; those cases must be rerun by the canonical acceptance harness.
- `evidence/issue-11/vm-reboot.json` — Azure-bound boot-ID change and complete recovery in 141.968 seconds.
- `evidence/issue-11/routine-execution.json` — a gateway-owned one-shot no-agent routine completed while no client process was involved.
- `evidence/issue-11/isolation.json` — Unix ownership/modes and reciprocal cross-Bot credential denials.

## 5. Scheduled execution

Do not install a standalone cron daemon for Hermes. Add/list jobs with the profile-aware official CLI in a one-shot admin container only while the normal gateway/serve pair is quiesced, then restart gateway before serve. Prefer invoking the maintenance helper with a reviewed fixed command. Verify `hermes cron status` and `hermes cron list` through the pinned image without recording prompts or delivery content. The gateway is the sole ticker; `hermes-health@BOT.timer` is only an infrastructure health timer and uses `Persistent=true` so a missed check runs after reboot.

## 6. Crash and reboot proof

Crash injection is destructive and allowed only on an explicitly disposable pre-activation fixture:

```sh
scripts/hermes/test-crash-recovery.sh --disposable-fixture
```

The script kills each in-container Hermes process independently and requires s6/systemd to restore a distinct healthy PID within 120 seconds. It writes sanitized recovery timings.

The actual VM reboot is the sole live destructive exception and requires the approved pre-activation window:

```sh
PRODUCTION_ACTIVATION=false scripts/hermes/test-vm-reboot.sh --pre-activation-approved
```

It records one Azure-bound reboot, changed boot ID, complete fleet health, and recovery within 600 seconds. Never run it after production activation.

## 7. Maintenance and rollback

Profile-affecting maintenance must stop serve and gateway, verify no DB/WAL descriptor remains, run one reviewed command, then start and health-check gateway before serve:

```sh
sudo scripts/hermes/maintenance.sh test-worker -- /path/to/reviewed-maintenance-command
```

If image/config validation, DB integrity, restart, or listener checks fail, leave the affected Bot disabled. Restore the prior digest-pinned image/config only after both processes are stopped. Do not clone or cross-restore profiles, blindly retry uncertain writes, expose loopback ports, or add another gateway/serve/CLI/cron writer.
