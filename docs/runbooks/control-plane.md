# Bot, Room, Channel, and routine control plane

Issue: [#13](https://github.com/JohanSardar/hermes-bot-fleet/issues/13)

## Current deployment

The server runs Hermes Agent 0.21.0, the first stable Bot Mode release, from immutable image digest `sha256:62b451ba2e2cfcfc834ed35eb4f28a174325b03e8800c97e7ea2e6402b5ef2c9` and OCI revision `f98f5e74e00e54c36088fa2e78171e2a408ba7c9`.

Hermes Desktop was built headlessly from release commit `29112bef099274229cadff79cdff7bf7b99c4b77`, installed at `/Applications/Hermes.app`, and code-signature verified. It has not been launched or used to manipulate the Mac GUI.

`chief` and `test-worker` are separate profiles, Unix identities, rootless container sets, workspaces, Browser Profiles, credentials, sessions, memory, skills, and canonical Bot Chats. The installation-root `default` profile on each backend is marked hidden and "Not a fleet Bot". Both named profiles pin `gpt-5.6-sol` through `openai-codex`; no Anthropic reasoning role is configured.

`laptop-worker` is represented in `infra/control/fleet-control.json` as a Mac-owned intermittent runtime with no server Browser Profile. Its live runtime is issue #14.

## Native Bot metadata and canonical chats

`scripts/control/configure_bot_mode.py` authenticates to the loopback-only serve backend with its Bot-owned Dashboard credential and uses the native v0.21 JSON-RPC surface to:

- persist title, description, SOUL persona, model/provider, and `hermes-bots` UI metadata;
- mark the installation root hidden;
- create and title the unique hidden `Bot Chat` canonical session;
- verify the backend reports `bot_mode_protocol: true` and a non-null canonical session.

The script rejects/prints no credential material.

## Routines

The gateway is the sole cron ticker. Current pinned jobs:

- chief `126350fa1fa0`, `[bot:chief] Daily fleet check`, `0 7 * * *`;
- test-worker `d830bb92a029`, `[bot:test-worker] Daily test check`, `0 8 * * *`.

Both pin provider/model and deliver via `bot-chat` (the owning profile; do not use `bot-chat:<same-profile>`, because a profile-scoped gateway would interpret that as a nested profile). Manual runs completed, delivery errors are null, and each canonical Bot Chat recorded a two-message routine delivery turn while clients were closed.

## Cross-connection relay

Bot relay rosters are synced in both directions. The v0.21 upstream waiter used generated `python -c`, which the non-interactive approval gate correctly classified as arbitrary code execution. The fleet does not weaken global approval policy. Instead it mounts a reviewed two-file override:

- `infra/hermes/overrides/tools/bot_relay.py` — upstream v0.21 module with only the waiter command changed;
- `infra/hermes/overrides/tools/bot_relay_waiter.py` — fixed-shape argv runner that validates the reply path, label, timeout, and reply object.

The generated command no longer evaluates source text and passes the command safety classifier. Live evidence proves Chief's native `message_agent` created a cross-connection envelope, the Desktop relay RPC delivered it to Test Worker, Test Worker returned `RELAY_OVERRIDE_OK`, the reply was written to Chief's gateway, and both canonical Bot Chats contain attributed markers.

Approval mode is `smart`: low-risk internal relay processes can run unattended, while fleet policy gates still govern third-party messages, publishing, purchases, account/permission changes, destructive operations, and other consequential effects.

## Rooms

The native hosted-room driver and protocol v2 are active. `fleet-ops` is defined with Chief authority and members Chief, Test Worker, and Laptop Worker. Cross-backend Room activation requires the private HTTPS peer endpoints locked by the topology.

At this checkpoint Tailscale returned `account does not support getting TLS certs`, so peer endpoint catalogs correctly report `not_configured`. No insecure HTTP peer route, public listener, self-signed trust bypass, SSH tunnel fallback, Serve/Funnel, or Room simulation was enabled. After tailnet HTTPS is enabled, configure the Bot-private peer URLs, complete `groups.peer.invite/register`, create the authoritative room, send mention-scoped disposable turns, and verify replication/attribution.

## Telegram

Telegram uses one BotFather token per profile and native outbound polling only. Never reuse one token in multiple gateways. Group defaults are mention-required and exclusive-bot-mentions; user/chat admission is numeric allowlist or approved pairing. No public webhook is allowed.

No Telegram token currently exists. Capture the first human-issued token without shell history or output:

```sh
scripts/control/capture-telegram-token.sh chief
```

The wizard uses hidden input and writes mode 0600 under `~/.config/hermes-fleet/`. After secure transfer into the Chief profile, enable `telegram-platform`, start the gateway, verify `getMe`, perform approved DM pairing, set the home channel, and retain inbound/outbound provider receipts. Repeat with a separate Test Worker BotFather bot and test-only admission.

## Upgrade invariants

`install-runtime.sh` deep-merges locked runtime defaults instead of replacing `config.yaml`, preserving Dashboard auth, Bot metadata, Channel configuration, and future extension keys. It verifies the immutable source digest via `RepoDigests` and the OCI revision label; it no longer launches version-probe or dashboard-auth one-shot containers that can deadlock a live rootless store. Dashboard auth is configured through the already healthy gateway before serve starts.

## Evidence

Current pre-human-checkpoint evidence: `evidence/issue-13/pre-telegram.json`.

This issue is not complete until Telegram round trips and the private HTTPS Room path are live and verified.
