# Persistent Browser Profiles and Private Takeover

Issue: [Deploy persistent Browser Profiles and private Browser Takeover](https://github.com/JohanSardar/hermes-bot-fleet/issues/12)

Browser Profiles are credential vaults. Each server Bot owns one mode-0700 profile at `/var/lib/hermes-bots/<bot>/browser/profile`. It is mounted only into that Bot's browser container—never into Hermes runtime/terminal containers, another Bot, a human's everyday browser profile, or an unencrypted file export.

## Deployed browser plane

Each Bot runs:

- `selenium/standalone-chromium` pinned by multi-architecture digest;
- container user `1200:1201` (`seluser`), never container root;
- a read-only root filesystem, all Linux capabilities dropped, `no-new-privileges`, resource limits, no host/container-engine socket, and no privileged mode;
- Chromium's user-namespace and renderer Seccomp-BPF sandbox, with live renderer requirements `Seccomp: 2`, `NoNewPrivs: 1`, and no `--no-sandbox` argument;
- exact Xvfb display `:99`, fluxbox, x11vnc on container loopback `5900`, and websockify/noVNC on container `6080`;
- a persistent `/browser-profile`, separate `/browser-config`, quarantined `/downloads`, and read-only lease state;
- a credential-free, capability-free 32 MiB network-anchor container that keeps Podman 4.9's rootless CNI namespace stable across browser-only restarts.

Raw CDP is container-loopback `127.0.0.1:9222` and is never published. The lease-aware Python relay in the same browser container exposes `10.89.0.10:9223` only to that Bot's private rootless network and only during a valid `AUTOMATION` lease. Both Bots use the same private addresses inside separate Unix-user network namespaces; there is no cross-Bot route.

Host publications are loopback only:

- chief internal noVNC: `127.0.0.1:16081`;
- test-worker internal noVNC: `127.0.0.1:16082`;
- chief authenticated human gate: `127.0.0.1:6081`;
- test-worker authenticated human gate: `127.0.0.1:6082`.

Raw VNC, raw CDP, and gated CDP have no host listener. SSH forwarding remains globally disabled. Issue #13 supplies the locked tailnet-private HTTPS reverse-proxy route; exposing noVNC before that authenticated route exists is prohibited.

The container runtime uses `seccomp=unconfined` because Podman's default outer profile prevents Chromium from creating its nested user namespace. This does not disable Chromium's own sandbox: the outer container remains rootless/non-root/read-only/capability-free/no-new-privileges, and every live Chromium renderer must independently report its own `Seccomp: 2` filter. Missing renderer proof fails deployment.

## Ownership lease

The legal lifecycle is:

`AUTOMATION -> DRAINING -> HUMAN -> RECOVERING -> AUTOMATION`

`AUTOMATION` has an owner, random nonce digest, monotonic expiry, generation, and boot identity. Every supervisor start forces `RECOVERING`.

`takeover` requires the locked top-level approval grant from `approval-audit-secrets-policy.md`. The grant contains exactly `schema_version`, `grant_id`, prefixed `manifest_sha256`/`nonce_sha256`, `approver`, `channel`, nested `authority_context`, canonical UTC `issued_at`/`expires_at`, `max_uses`, `policy_revision`, `signing_key_id`, and `signature`.

The authority signs exactly `UTF8("fleet-approval-grant-v1\0") || RFC8785(grant_without_signature)` using pure RFC 8032 Ed25519. Signatures and public keys use the `ed25519:<padded-base64>` form; digests use `sha256:<hex>`. Browser grants expire within 60 seconds (the disposable signer uses 45 seconds), while the established HUMAN lease remains capped at 600 seconds.

The gate validates the pinned offline-root fingerprint, purpose-limited online certificate, active/predecessor key set, root cross-certification during rotation, root-signed revocations and effective times, persisted wall-clock rollback guard, channel/device eligibility, raw 32-byte nonce, and exact manifest. The manifest binds:

- Bot and Browser Profile fingerprint;
- current automation nonce;
- `human:johan` and an approved device digest;
- channel instance and approval session;
- purpose `browser-takeover`;
- exact manifest digest and policy revision;
- random nonce, maximum use count one, short wall-clock grant validity, and HUMAN duration at most 600 seconds.

The verifier atomically fsyncs an `approval.consumed` audit row and uniqueness record for `(grant_id, nonce_sha256)` before any side effect. Invalid signature/domain/encoding, replay, stale nonce, wrong target, excessive duration, revoked/unknown signer, rollback, concurrent claim, or uncertain state enters `RECOVERING`.

After grant consumption, the supervisor writes `DRAINING`, rejects new CDP work, closes the CDP relay, waits for raw CDP client count zero, and only then writes `HUMAN`. There is no direct HUMAN-to-AUTOMATION transition.

## Authenticated noVNC bootstrap

The takeover URL contains no credential, token, nonce, or secret. During HUMAN, the separately delivered random takeover credential is posted once in the `X-Hermes-Takeover-Credential` header to same-origin `/__takeover_bootstrap`.

The response is HTTP 204 with:

- `Cache-Control: no-store`;
- `Pragma: no-cache`;
- a random `Secure; HttpOnly; SameSite=Strict` session cookie.

Only the cookie digest is retained. The credential is consumed once and removed. It is never put in URL/navigation data, page JavaScript, logs, screenshots, CDP, or model/tool output. A missing/wrong credential, second bootstrap, cookie conflict, second claimant, or viewer WebSocket disconnect revokes input and enters `RECOVERING`.

Tailscale identity is necessary but does not replace this application authorization.

## Recovery

Recovery:

1. revokes takeover/session state;
2. closes the gated CDP relay and waits for zero raw CDP clients;
3. denies the human gate;
4. validates the profile owner/mode;
5. creates one known `about:blank` target and closes stale targets;
6. probes raw CDP;
7. starts the relay while it is still state-denied;
8. rotates the automation nonce and grants a new monotonic AUTOMATION lease.

Any failure remains RECOVERING. Browser restart does not restart the Hermes gateway. At VM boot only, browser startup repairs stale Podman pause/slirp state before the ordered gateway start. Browser-only restarts skip this migration because gateway/serve remain running.

## Operator commands

Run from `/` so `sudo -u` never inherits an inaccessible directory.

```sh
cd /
sudo -u bot-chief env XDG_RUNTIME_DIR=/run/user/1001 \
  /usr/local/libexec/hermes-browser-supervisor status --bot chief

# Grant files are R3, mode 0600, delivered by the approval authority, and consumed.
sudo -u bot-chief env XDG_RUNTIME_DIR=/run/user/1001 \
  /usr/local/libexec/hermes-browser-supervisor takeover \
  --bot chief \
  --grant /approved-r3-channel/takeover-grant.json \
  --manifest /approved-r3-channel/takeover-manifest.json \
  --nonce-file /approved-r3-channel/raw-nonce \
  --credential-out /var/lib/hermes-bots/chief/browser/state/takeover-credential

# Recovery never accepts a standing grant.
sudo -u bot-chief env XDG_RUNTIME_DIR=/run/user/1001 \
  TMPDIR=/var/lib/hermes-bots/chief/tmp \
  /usr/local/libexec/hermes-browser-supervisor recover \
  --bot chief --reason inspected-handback
```

A human-only approval application supplies the production grant and separate bootstrap credential. The disposable signer described below must never be used for production.

## Disposable BROW-01 test

`hermes-browser-sign-fixture` creates ephemeral in-memory Ed25519 root/signer keys, a test-worker-only trust file, locked-format grant, exact manifest, and raw nonce. Private keys are never persisted. After grant consumption, the supervisor—not the signer—creates the separate one-use bootstrap credential at the approved Bot-state destination. The fixture is restricted to disposable test-owned validation; production data/credentials are forbidden. Remove the fixture trust and credential files immediately after the test while retaining consumed-grant and lease-audit records.

The retained test proves:

- valid signature, exact manifest, Bot/profile/device/current-nonce binding;
- durable single-use consumption and replay denial;
- CDP client count zero before HUMAN;
- one authenticated no-store noVNC session;
- no simultaneous HUMAN and CDP samples;
- wrong credential, invalid signature, concurrent claimant, replay, disconnect, and monotonic timeout all enter RECOVERING;
- secrets never appear in URL, output, or retained evidence.

## Authentication persistence test

The login test uses an isolated, disposable test-owned HTTP fixture with no password or production identity. Chromium receives an HttpOnly persistent authenticated session, proves authenticated state, restarts while the gateway PID remains unchanged, performs explicit recovery, proves the same authenticated state, then logs out and proves unauthenticated state. No session value is observed or retained.

`--password-store=basic` is required in this headless Linux container so Chromium can reopen its persistent cookie database without a desktop keyring. The Browser Profile remains an encrypted-disk, mode-0700 credential vault; file-level backup still excludes it.

## Human-only checkpoints

Real account login, MFA, CAPTCHA, passkey, approval-root setup, and production takeover grant issuance are human-only. Start with disposable accounts. A Browser Takeover authorizes browser input only; it never authorizes purchases, publication, messages, account/permission changes, destructive actions, or use of newly encountered credentials.

## Retained evidence

- `evidence/issue-12/browser-runtime.json`
- `evidence/issue-12/takeover.json`
- `evidence/issue-12/reboot-recovery.json`
- `evidence/issue-12/test-login-persistence.json`
- `evidence/issue-12/private-novnc-headed-chromium-final.png`

The screenshot is an authenticated disposable noVNC session showing the final non-root Xvfb/x11vnc Chromium stack and contains no real account state.
