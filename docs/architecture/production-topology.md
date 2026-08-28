# Production topology and isolation boundaries

Status: **Locked for initial production provisioning**
Decision scope: [Choose the production topology and isolation boundaries](https://github.com/JohanSardar/hermes-bot-fleet/issues/6)
Depends on: the browser decision in issue 4 and the Mac access decision in issue 5

## Decision

The initial fleet is one cost-optimized Azure Ubuntu Server Runtime plus Johan's existing Mac Laptop Runtime. The Server Runtime hosts `chief` and `test-worker`; the Mac hosts `laptop-worker`. Each Bot is one named Hermes profile. Each server profile has exactly one independently supervised `hermes gateway` process for Telegram and cron and exactly one independently supervised `hermes serve` process for Desktop HTTP/WebSocket access. They may be resident together, but a profile-scoped turn lock permits only one mutating agent turn at a time. Each server Bot also has a distinct Unix identity, rootless container set, private container network, persistent browser profile, credentials, service units, and backup namespace. A Hermes profile is semantic state isolation, **not** a security boundary; the Unix user, container mounts/network, and host firewall are the server security boundaries.

The only administration network is Tailscale. The Azure VM has no Internet-reachable inbound service. SSH, Hermes serve/dashboard, messaging gateway, noVNC, CDP, VNC, API, MCP, and filesystem services must never be published to the Internet. Telegram is the user interaction and alert channel; each gateway initiates its Telegram connection outbound, so Telegram creates no inbound VM listener.

All reasoning is pinned to `gpt-5.6-sol` through `openai-codex`. There is no fallback reasoning provider or model. A missing, expired, unavailable, quota-limited, or misconfigured provider fails the turn or scheduled run and alerts; it must not silently select another model.

## Exact four-plane topology

```text
                       Internet (outbound only)
                +-------------+  +----------------+
                | Telegram API|  | openai-codex   |
                +------^------+  +--------^-------+
                       |                  |
  1 Interaction plane | outbound polling | outbound HTTPS
  ---------------------+------------------+--------------------
                                          |
  2 Private admin plane      Johan's Mac == Tailscale == Azure VM
                             Desktop/SSH                 private proxy
                                 |                   (tailnet HTTPS only)
  -------------------------------+--------------------------+---
                                                              |
  3 Execution plane       Mac Laptop Runtime          Server Runtime
                          laptop-worker            chief       test-worker
                          native profile           runtime     runtime
                               |                       |           |
                       local approval gate          gated CDP   gated CDP
                               |                       |           |
                     approved Mac roots            headed      headed
                                                   Chromium    Chromium
  --------------------------------------------------------------
  4 State/protection plane   Mac local state     encrypted managed disk
                                                snapshots + encrypted blob
                                                Bot-scoped restore units
```

### 1. Interaction plane

- Telegram is the only initial external messaging surface and the alert destination.
- Only explicitly allowlisted Telegram user/chat identifiers may invoke a Bot. Pairing/allowlist checks remain enabled.
- Server gateways use outbound Telegram API traffic; no webhook or inbound public listener is allowed.
- `chief` is the primary human-facing coordinator. `test-worker` is not granted production credentials or production browser accounts. `laptop-worker` is reachable through the Mac-owned gateway only while the Mac is awake.
- Bot Rooms, mentions, cron, and Kanban are coordination features, not authority escalation. Cross-runtime delegation is explicit and retains the target runtime's permissions.

### 2. Private administration plane

- Tailnet nodes have private device names, initially `fleet-server` and `johan-mac`. Public DNS names are prohibited.
- Johan's named Tailscale user/device posture is the only initial admin principal. No shared tailnet users and no reusable tag owner grants are admitted initially.
- A host reverse proxy binds only the VM's Tailscale address on TCP 443 and presents tailnet-private HTTPS names. It routes authenticated Desktop HTTP/WebSocket traffic only to Bot-specific `hermes serve` host-loopback ports and routes lease-authorized noVNC paths separately. Messaging gateways are outbound-only and are not proxy targets.
- SSH binds TCP 22 only on the Tailscale address (or is blocked on all other interfaces by both nftables and the Azure NSG). Password login and root login are disabled; key authentication is required.
- noVNC is reachable only through tailnet HTTPS and a short-lived, single-Bot takeover authorization. Raw VNC and raw CDP never leave their browser container.
- The Azure NSG has no Internet inbound allow rule. Host firewall default policy is inbound drop; loopback, established traffic, and policy-approved traffic arriving on `tailscale0` are the only inbound exceptions.
- Tailscale is not an identity substitute for application authentication: Hermes retains its session/token authentication and noVNC retains its takeover authorization.

### 3. Execution plane

- The Server Runtime consists of two independent rootless container sets, one owned by each Bot Unix user. A set has a Hermes runtime container and a browser-desktop container joined only to that Bot's internal container network.
- Containers use immutable, digest-pinned images, read-only root filesystems where supported, dropped Linux capabilities, `no-new-privileges`, resource limits, and no Docker/Podman socket. They do not run privileged or as root. Chromium's sandbox remains enabled.
- The Mac Laptop Runtime is native, not a server-side mount or general remote shell. `laptop-worker` executes as Johan's logged-in macOS identity and is constrained by Hermes approvals plus the Mac boundary below.

### 4. State and protection plane

- Server durable state resides on Azure encrypted managed disks. Azure snapshots and encrypted private Blob backups are restore media, not live shared filesystems.
- Every durable item has exactly one Bot owner and one restore target. No profile, browser directory, database, or secret file is shared between Bots.
- File-level backup jobs can read only a root-prepared, non-secret R1 export for one Bot at a time—not its live state root or R3 paths—and have write-only access to that Bot's blob prefix. Encrypted whole-disk snapshots use the separate Azure/host administrative principal. Restore requires an explicit administrative operation with both Bot Hermes processes stopped.

## Components, bindings, and ports

The following port allocation is locked. A live check must confirm availability before units are installed; a collision is a provisioning failure, not permission to pick an undocumented port.

| Component | Bind / exposure | Port | Rule |
|---|---|---:|---|
| SSH | VM Tailscale address only | TCP 22 | Admin ACL only; never Azure-public |
| Private reverse proxy | VM Tailscale address only | TCP 443 | Tailnet HTTPS; Hermes and noVNC routes only |
| `chief` `hermes serve` Desktop backend | host loopback | TCP 8701 | Independently supervised; reverse-proxied privately; HTTP and WebSocket auth required |
| `test-worker` `hermes serve` Desktop backend | host loopback | TCP 8702 | Independently supervised; reverse-proxied privately; HTTP and WebSocket auth required |
| `chief` / `test-worker` Telegram gateways | no inbound listener | none | Separate `hermes gateway` processes; outbound Telegram polling and cron only |
| `chief` noVNC/websockify | host loopback | TCP 6081 | Reverse-proxied only while takeover is authorized |
| `test-worker` noVNC/websockify | host loopback | TCP 6082 | Same policy |
| Chromium raw CDP, each browser container | browser-container loopback | TCP 9222 | Never published; browser supervisor is sole client |
| Lease-gated CDP relay | Bot-private container network | TCP 9223 | Reachable only from that Bot's runtime container |
| x11vnc, each browser container | browser-container loopback | TCP 5900 | Never published; local websockify is sole client |
| Xvfb | Unix display socket inside browser container | display `:99` | Not a network listener |
| Hermes OpenAI-compatible API | disabled in both gateway profiles | default TCP 8642 unused | `hermes serve` is the Desktop JSON-RPC/WebSocket backend, not this API; no fleet requirement |
| File Bridge | absent initially | none | A later implementation may allocate a tailnet-only port through a separate decision |

The reverse proxy's private routes are one origin per Bot `serve` backend and one takeover route per Bot; routing must never make a request for one Bot reach another Bot's loopback port. `chief` port 8701 is pinned only to the `chief` serve unit and root, and `test-worker` port 8702 only to the `test-worker` serve unit and root. Exact tailnet DNS suffixes, TLS material, and backend tokens are generated during provisioning and must not be committed.

Required outbound traffic is narrowly permitted for OS/package updates, Tailscale coordination/DERP/STUN, Telegram, `openai-codex`, explicitly enabled Hermes tool providers, Azure control/backup endpoints, DNS, and time synchronization. Tailscale may use outbound TCP 443, UDP 3478, and direct UDP (normally 41641); these are egress/return paths and do not authorize application ingress. Any optional tool provider must be separately recorded before its egress is allowed.

## Unix users, groups, paths, and ownership

| Identity | Primary group | Owns | Must not access |
|---|---|---|---|
| `bot-chief` | `bot-chief` | `/var/lib/hermes-bots/chief` and its rootless container state | `test-worker` state and host admin config |
| `bot-test-worker` | `bot-test-worker` | `/var/lib/hermes-bots/test-worker` and its rootless container state | `chief` state and production credentials |
| `hermes-proxy` | `hermes-proxy` | no Bot data; only proxy runtime/config needed for routing | Bot profile, browser, and secret contents |
| `hermes-backup` | `hermes-backup` | no interactive login; non-secret backup staging metadata | all R3 source paths and live write access; it is not trusted to read secrets |
| root / Johan via sudo | administrative boundary | units, firewall, restore operations | routine Bot execution |

Every service account is non-login and has a locked password. Bot roots are mode `0700`, owned by their Bot user/group. Files containing credentials are mode `0600`. There is no broad `hermes-bots` group. Administrative access is through audited `sudo`, not group-readable Bot data.

Each server Bot root has this fixed host/container layout. `/opt/hermes-agent` is the digest/version-pinned, read-only application installation and is not `HERMES_HOME`.

```text
/var/lib/hermes-bots/<bot>/
  hermes-install/              # host mount source; Hermes installation home, 0700
    profiles/<bot>/            # only configured named profile; effective HERMES_HOME
      home/                    # HOME for tool subprocesses; profile credentials/config
  workspace/                   # only terminal.cwd for this Bot
  browser/                     # Chromium user-data-dir; 0700
  downloads/incoming/          # quarantined browser downloads
  downloads/released/          # files explicitly released to runtime
  audit/                       # append-only service/lease events
  backup-staging/              # bounded, same-Bot temporary data
```

The runtime container mounts that Bot's host `hermes-install/` at `/home/hermes/.hermes`, its `workspace/` at `/workspaces/<bot>`, and `downloads/released`; it mounts `/opt/hermes-agent` read-only. The named-profile selection makes the effective `HERMES_HOME` `/home/hermes/.hermes/profiles/<bot>` (the corresponding host path is `/var/lib/hermes-bots/<bot>/hermes-install/profiles/<bot>`). The installation-root default profile `/home/hermes/.hermes` is not a Bot: it has no model/provider, messaging token, cron jobs, serve unit, or gateway unit, and multiplexing is disabled. Provisioning must fail if any other named profile is present.

Both server units use `HOME=/home/hermes` and the same pinned Hermes executable, with exact command shapes `hermes -p <bot> gateway run` and `hermes -p <bot> serve --host 127.0.0.1 --port <8701|8702> --skip-build`; unit/container arguments provide the fixed port. In each named profile, configuration locks `terminal.backend: local`, `terminal.cwd: /workspaces/<bot>`, and `terminal.home_mode: profile`. Thus tool subprocesses use `{HERMES_HOME}/home`, not the account home. That directory may contain deliberately initialized per-Bot Git/SSH/GitHub/Azure/Codex credentials and is R3: mode 0700/0600 as applicable, never linked to host credentials or another Bot, excluded from file-level backup, and covered only by the encrypted-disk snapshot/re-provisioning policy below.

The browser container mounts only `browser`, `downloads/incoming`, and its X11 runtime. Neither container mounts `/`, the host `/home`, `/var/run/docker.sock`, `/run/podman/podman.sock`, another Bot root, or host SSH/cloud configuration. Browser downloads do not become runtime inputs until a policy-controlled release step scans and moves them.

## Bot Profile and Browser Profile boundaries

| Bot | Runtime | Hermes profile | Browser identity | Initial authority |
|---|---|---|---|---|
| `chief` | Azure Server Runtime | only `chief` | persistent `chief` Chromium profile | coordination and explicitly granted production accounts |
| `test-worker` | Azure Server Runtime | only `test-worker` | persistent `test-worker` Chromium profile | test accounts/data only; no production secrets |
| `laptop-worker` | native Mac Laptop Runtime | only `laptop-worker` | no server Browser Profile | approved Mac operations while online |

The supported live concurrency contract is a deliberate two-process pair per profile: exactly one messaging `gateway` instance and exactly one Desktop `serve` instance. The gateway alone owns Telegram polling and the cron ticker; `serve` must have messaging adapters, cron dispatch, gateway multiplexing, and the OpenAI-compatible API disabled. Neither process is called the sole writer: both can mutate sessions, memory, skills, and `state.db` while handling a turn.

A supervisor-owned, profile-scoped interprocess turn lock therefore covers each complete mutating turn, including post-turn persistence and self-improvement. A turn arriving at the idle process acquires the lock; a simultaneous turn at the other process is queued only to the configured short bound and is then rejected/busy with no partial execution or write. There is never more than one active turn for a profile. A second gateway, second serve, CLI/chat agent, dashboard backend, standalone cron daemon, or repair process against that live home is prohibited and startup must fail. This lock is a required deployment compatibility gate: if the pinned Hermes release cannot demonstrate safe cross-process serialization and healthy `state.db` under the acceptance stress test, `serve` remains stopped and Desktop access is not accepted rather than running two uncoordinated writers. Shared memory, if ever needed, must be an explicit external service; profile-directory sharing or cloning live state is prohibited.

Configuration edits, updates, exports, repair, restore, file-level backup capture, and snapshot quiescence stop both gateway and serve, reject/drain new work, wait for the turn lock to become free, and verify no process has the profile database or WAL open. Start order after maintenance is gateway, health check, then serve. Crash-consistent disk snapshots may instead use the pinned Hermes application backup command only if a live restore test proves that command coordinates both processes; otherwise both are stopped.

Browser cookies, saved passwords, local storage, downloads, and account sessions belong only to their Bot. Browser directories are never cloned between Bots. Authentication through Browser Takeover grants state to that Bot, not to the fleet. `test-worker` must use non-production identities.

The browser container runs one externally supervised headed Chromium with a persistent `--user-data-dir`, Xvfb, Openbox, x11vnc, websockify/noVNC, and a lease supervisor. Chromium raw CDP binds its container loopback on 9222. The supervisor exposes only a lease-gated relay on the Bot-private network; Hermes is configured for that relay. This preserves loopback-only raw CDP while allowing the separate runtime container to automate without exposing CDP to the host or tailnet.

## Browser ownership lease (fail closed)

The lease supervisor is the source of truth. State and transitions are persisted to the Bot audit log, but after supervisor restart the effective state is `RECOVERING`, never implicitly `AUTOMATION`.

| State | CDP automation | noVNC input | Entry / exit rule |
|---|---:|---:|---|
| `AUTOMATION` | allowed to the one current lease holder | view-only/off | Normal state; lease has owner, nonce, and expiry |
| `DRAINING` | new commands denied; in-flight command gets bounded grace | off | Requested takeover; expiry of grace forces CDP disconnect |
| `HUMAN` | denied and socket closed | allowed to one authenticated admin session | Enter only after CDP clients are zero and a single-use takeover grant is consumed |
| `RECOVERING` | denied | input denied | Human release, timeout, disconnect, process restart, or uncertain ownership |

Allowed transitions are `AUTOMATION -> DRAINING -> HUMAN -> RECOVERING -> AUTOMATION`. Any invalid transition, stale nonce, concurrent claimant, expired heartbeat, supervisor loss, browser crash, proxy error, or uncertain client count moves to `RECOVERING` and disables both control paths. There is no direct `HUMAN -> AUTOMATION` transition.

To leave `RECOVERING`, the supervisor must revoke the takeover URL/token, disconnect VNC input, close all CDP sessions, verify Chromium and profile-directory health, reset to a known tab/window condition, rotate the automation lease nonce, and pass a harmless CDP probe. Failure keeps the Bot in `RECOVERING` and sends a Telegram alert. Lease and takeover expirations use monotonic time. Takeover grants are Bot-bound, admin-bound, single-use, short-lived, and never logged in plaintext.

## Container and crash boundaries

- A server Bot's runtime and browser containers share only that Bot's internal network and declared mounts. The two Bots have separate rootless engines/networks; there is no cross-Bot container DNS or routable bridge.
- Browser compromise is contained from the host by non-root execution, the Chromium sandbox, container restrictions, mount minimization, and egress policy. It can still compromise that Bot's Browser Profile and accounts; those are treated as a high-sensitivity trust zone.
- Runtime compromise is limited to that Bot's mounted Hermes state/workspaces and gated browser capability. It receives no host-admin socket or another Bot's credentials.
- A Bot restart does not restart the other Bot. A browser restart does not require a gateway restart, but forces that Bot's lease to `RECOVERING`.
- The host kernel, root, reverse proxy, Tailscale daemon, and backup operator remain common trusted infrastructure. This design reduces blast radius; it does not claim VM/kernel isolation between hostile tenants.

## Tailscale policy intent

The tailnet policy is default deny and expresses these grants only:

| Source | Destination | Allowed |
|---|---|---|
| Johan's approved admin user on an approved device | `fleet-server` | TCP 22 and 443 |
| `fleet-server` | `johan-mac` | no inbound service initially |
| future Server Runtime File Bridge client | future Mac File Bridge | only the separately allocated mTLS port, after issue 5's bridge is implemented |
| any other user, tagged node, or subnet route | either runtime | none |

Tailscale SSH, Funnel, Serve-to-public, exit-node use, subnet routing, and public sharing are disabled unless a later recorded decision enables them. Tailnet HTTPS serving may be used only as a private tailnet frontend. Device approval, key expiry policy, node ownership, and ACL tests are provisioning-time configuration facts; they must satisfy the intent above. Loss of tailnet connectivity removes administration and Browser Takeover but does not open fallback public access.

## Mac interaction boundary

`laptop-worker` is the only configured Bot on the Mac and normally lives at `~/.hermes/profiles/laptop-worker` (effective `HERMES_HOME`; the installation root is `~/.hermes`). Its configuration locks `terminal.cwd: /Users/johansardar/Agent-Inbox` and `terminal.home_mode: profile`, so tool credentials live deliberately under `~/.hermes/profiles/laptop-worker/home`; it must not inherit Johan's normal SSH, cloud, GitHub, or Codex credentials. The profile's Telegram/cron process is the independently managed per-profile launchd service installed with `hermes -p laptop-worker gateway install` (generated service invocation: `hermes -p laptop-worker gateway run`); only that one gateway may run.

Hermes Desktop manages its own local `hermes serve` process and does not use the gateway as its HTTP/WebSocket backend. For `laptop-worker`, that app-managed local backend is the one permitted serve instance: do not install a second launchd serve service and do not expose the local serve port over Tailscale. Desktop must explicitly select `laptop-worker`; the installation-root default is not configured as another Bot. The same profile turn lock/queue-or-reject contract applies between the launchd gateway and app-managed serve. Closing Desktop stops local serve but leaves the gateway online. If the pinned Desktop/Hermes build cannot pass that concurrency test, the operator must stop the gateway before opening Desktop for this profile.

The gateway is the only Mac cron ticker and cron never bypasses local mutation approval. Gateway, Desktop serve, approval, and denied-path events are retained in the profile/service audit logs with secret redaction and Mac log rotation. FileVault must be enabled. Encrypted Mac backup may cover non-secret `laptop-worker` profile state and approved roots under Johan's local policy; `.env`, `auth.json`, and `{HERMES_HOME}/home` credentials are excluded from file export and restored from their authorities. Backup/repair requires Desktop serve and the launchd gateway quiesced under the same rule as server profiles.

`laptop-worker` runs natively as Johan's logged-in macOS identity and is offline when the Mac sleeps, disconnects, or its gateway is stopped. The approved roots are exactly:

- `~/Agent-Inbox`
- `~/Agent-Output`
- individually selected directories directly under `~/Projects` (selection is explicit; `~/Projects` is not recursively granted by default)

Reads and writes are confined to resolved descendants of those roots. Symlinks, aliases, mount changes, `..`, hard-link tricks, and path races must not escape them. All Mac mutations require a local, single-use approval showing operation, resolved path, and relevant source/destination. Timeout, lock screen, offline state, approval-channel loss, changed target metadata, or denial fails closed. Headless cron cannot auto-approve mutations.

Sensitive roots are permanently denied, including Johan's `~/.ssh`, `~/.gnupg`, `~/Library/Keychains`, browser profiles, password-manager data, normal cloud credential/config directories, Tailscale state, Hermes credential files outside the active `laptop-worker` runtime, and macOS system/privacy databases. Being inside an approved parent never overrides a sensitive-root deny. The Bot may use only credentials deliberately provisioned into `{HERMES_HOME}/home`, and access to those files is never exposed as a general file tool operation.

Initially, Server Bots delegate work to the native `laptop-worker` through explicit Hermes messaging/Rooms; they receive results, not arbitrary Mac filesystem access. The later File Bridge is a separate purpose-built service with mTLS over Tailscale, descriptor-relative path operations, the same local approvals, idempotency keys, audit, and offline fail-closed behavior. It must not be implemented as SSH, SMB/NFS, a general shell, a Desktop file browser, or a broad MCP filesystem server. No Mac directory is mounted on Azure.

## Storage, backup, and restore classes

| Class | Examples | Live storage | Backup rule |
|---|---|---|---|
| R0 rebuildable | pinned images, packages, generated units | OS disk / repository | Rebuild from code and manifests; no state backup required |
| R1 Hermes durable | non-secret profile config, memory, sessions, state DB, cron, skills, audit | Bot-owned encrypted managed disk paths | Daily file-level encrypted blob backup from an R1-only source view; snapshot only with gateway and serve quiesced or a proven application backup command |
| R2 browser sensitive | Chromium user-data-dir, cookies, saved sessions | Bot-owned encrypted managed disk path | Encrypted snapshot/backup in separate Bot prefix; restore only to same Bot; never export unencrypted |
| R3 secrets | `.env`, `auth.json`, provider OAuth/token state, Telegram/backend keys, `{HERMES_HOME}/home` tool credentials | mode-0600 files / mode-0700 directories on encrypted disk | Never mounted or read by the file-backup principal; included only in encrypted whole-disk snapshots where unavoidable and otherwise re-established from the authority/provider |
| R4 transient | caches, container layers, X11 sockets, active lease nonce, quarantined temp files | ephemeral/container storage | Do not back up; restore starts `RECOVERING` |
| R5 Mac state | `laptop-worker` profile and approved roots | Mac local storage | Remains under the Mac's local backup policy; never copied wholesale to Azure |

Initial server retention is seven daily, four weekly, and three monthly restore points per Bot, subject to Azure for Students credit alarms. Blob containers are private, public access is disabled, transport is TLS, encryption at rest is required, and delete/restore operations are administrative. Backup logs contain object identifiers and outcomes, not secret values or browser contents.

The file-level backup service is not given a read-only mount of the whole Bot root. A root-owned preparation unit, run only after gateway/serve quiescence, projects an allowlisted R1 tree into `backup-staging/r1-export` while omitting `.env`, `auth.json`, `{HERMES_HOME}/home`, tokens, browser state, and every other R3 path. It validates the manifest contains no symlink, hard link to an excluded inode, secret filename, socket, or device. Only that prepared export is bind-mounted read-only into the `hermes-backup` namespace; the live Bot root and R3 paths are absent. The backup principal has write-only credentials for that Bot's blob prefix. Encrypted whole-disk snapshots run under the Azure/host administrative control plane, not the file-backup principal; that higher-trust principal is explicitly trusted with ciphertext infrastructure but snapshots are never mounted into the backup service.

A restore is successful only after checksums/manifest validation, ownership and mode restoration, profile database health checks, verification of the one-turn-at-a-time/two-unit contract, and separate gateway and serve smoke tests. Browser restore additionally starts in `RECOVERING` and requires the recovery checklist before automation. A scheduled restore drill must prove one Bot can be restored without reading, overwriting, or stopping the other Bot.

## Trust boundaries

| Boundary crossed | Data/capability crossing | Controls | Residual trust / failure |
|---|---|---|---|
| Telegram user -> gateway | prompts, files, approval responses | user/chat allowlist, pairing, platform auth, size/type handling | Telegram sees messages; malicious content can prompt-inject |
| Gateway -> `openai-codex` | model context and tool results | provider/model pin, secret handling, minimized context | Provider receives submitted context; outage stops reasoning |
| Admin Mac -> VM | SSH, dashboard, takeover | Tailscale identity/device policy, app auth, TLS, audit | Compromised approved admin device controls fleet |
| Reverse proxy -> Bot `serve` | authenticated Desktop HTTP/WebSocket | fixed route-to-loopback map; per-Bot token | Proxy/root are common trusted components |
| Runtime -> browser | browser commands/results | private network, lease-gated CDP relay, Bot-only network | Web content is untrusted; browser account is exposed to that Bot |
| Human -> browser | keyboard/mouse/display | draining, single-use takeover, no concurrent CDP | Human can change that Bot's browser state |
| Browser -> Internet/downloads | web requests and untrusted files | sandbox, egress controls, quarantine/release | Logged-in sites and downloads remain high risk |
| Bot A -> Bot B | messages/delegated task descriptions | explicit Rooms/mentions, target-side permissions, no shared mounts | Content may be hostile; authority does not transfer |
| Server -> Mac | task request, later narrow file operations | laptop-worker boundary; later mTLS bridge + local approval | Mac is a higher-trust personal endpoint |
| File-backup service -> Azure storage | encrypted Bot-scoped R1 objects | read-only prepared R1-only mount, no live/R3 mount, write-only prefix, private blob, audit | Azure/root snapshot admins—not this principal—are trusted for whole-disk secret ciphertext |
| Container -> host kernel | syscalls and resource use | rootless non-root containers, seccomp, caps dropped, limits | Shared kernel remains a common compromise boundary |

## Service supervision

Systemd system units are installed by root but run under the appropriate non-login Bot user. There is one target per Bot with independently restartable units:

1. rootless container/network preparation;
2. browser-desktop container and lease supervisor;
3. browser readiness/recovery check;
4. Hermes messaging/cron gateway runtime container (`hermes -p <bot> gateway run`), with no Desktop or API listener;
5. Hermes Desktop backend runtime container (`hermes -p <bot> serve --host 127.0.0.1 --port <fixed> --skip-build`), bound to that Bot's host-loopback publication only;
6. host-loopback noVNC publication, normally input-disabled.

Gateway and serve have separate unit names, PIDs, health checks, restart budgets, logs, and fixed command lines, but share only their Bot's named profile and profile turn-lock unit. The serve unit cannot enumerate, switch to, route to, mount, or manage the other Bot's profile; its environment contains only its own effective `HERMES_HOME`, and the reverse proxy has no cross-profile fallback. Gateway multiplexing is explicitly off. Both units use graceful SIGTERM and restart-on-failure; custom `ExecStopPost` kill hooks are prohibited. The gateway unit must not run both a Hermes user gateway and a system gateway for the same profile, and the serve unit must not coexist with another dashboard/serve backend for that profile. A bounded systemd watchdog may be enabled after a live compatibility test. Restart-rate limits prevent alert/restart storms.

Dependencies are strict: gateway startup may proceed only when the gated CDP endpoint reports a safe state; serve starts only after gateway/profile health and turn-lock checks pass. Browser failure moves the lease to `RECOVERING` and disables browser tools without granting takeover. Gateway and serve may continue non-browser work, subject to the one-turn lock. Reverse proxy, Tailscale, firewall, backup timer, disk/credit monitor, and Telegram alert health are host-level supervised services. Alerts cover either Hermes unit's crash loops, turn-lock failure, lease recovery failure, backup/restore failure, low disk, provider auth/quota failure, and Azure credit/budget thresholds; alerts contain no secrets.

## Deployment order and gates

1. **Record live Azure facts.** Query Azure for Students quota, currently available Ubuntu-compatible VM/disk SKUs, and current prices in Central US and East US 2. Select the cheaper feasible region/SKU within credits. Do not provision from assumed availability.
2. **Create the base network.** VM/NIC/NSG with no public inbound service (prefer no public IP if deployment/bootstrapping supports it), encrypted managed disk, private storage, budget/credit alerts, and boot diagnostics without secret payloads.
3. **Establish admin identity.** Enroll `fleet-server` in Tailscale using a short-lived provisioning mechanism, apply/test default-deny policy, then verify SSH and private HTTPS from Johan's approved Mac. Remove bootstrap access before continuing.
4. **Harden the host.** Patch Ubuntu; install nftables, rootless container runtime, audit/log rotation, time sync, and backup tooling; create service identities and exact directories/modes.
5. **Deploy `test-worker` first.** Build its isolated network, containers, named profile, non-production browser identity, lease state machine, separate gateway and serve units, Telegram polling, fixed serve route, and private admin routes. Verify all isolation and negative exposure tests.
6. **Prove recovery.** Exercise automation-to-human-to-automation flow, crash each component, run an encrypted backup, and restore `test-worker` to a clean target while `chief` remains absent.
7. **Deploy `chief`.** Reuse versioned manifests, never state. Configure separate credentials, production Browser Profile, model pin, gateway, serve route, and backups. Prove that `test-worker` cannot access it.
8. **Configure the Mac.** Create only the native named `laptop-worker` profile, install its launchd gateway, enforce approved/denied roots and local mutation approvals, use Desktop's one app-managed local serve for it, register both server serve backends in Hermes Desktop over Tailscale, and test explicit cross-runtime delegation while offline behavior fails closed.
9. **Operational acceptance.** Run the complete test matrix below, capture non-secret evidence, and only then permit unattended routines. The File Bridge remains a later deployment stage.

## Locked decisions versus live provisioning facts

### Locked here

- Azure for Students and one initial Ubuntu Server Runtime.
- Region is constrained to Central US or East US 2 and selected by live feasibility/cost.
- Tailscale-exclusive administration; no public admin/control/data endpoints.
- Initial Bots and ownership: server `chief`, server `test-worker`, native Mac `laptop-worker`.
- Exactly one messaging gateway and one Desktop serve process per live server profile, one app-managed local serve plus one launchd gateway for `laptop-worker`, and one serialized mutating turn per profile; no multiplex gateway.
- Separate Unix users, rootless container sets, networks, mounts, credentials, and browser profiles for server Bots.
- Externally supervised headed Chromium, persistent per-Bot profile, sandbox enabled, raw loopback CDP, private noVNC, fail-closed lease.
- `gpt-5.6-sol` through `openai-codex` only, with no reasoning fallback.
- Exact serve/noVNC service port allocation and binding classes in this document; messaging gateways have no inbound listener and the OpenAI-compatible API remains off.
- Mac roots/denies/local mutation approval and the staged File Bridge boundary.
- Encrypted disks, snapshots, private encrypted blob backup, restore isolation, Telegram alerts.

### Must be measured or generated live

- Azure subscription/tenant identifiers, remaining student credit, quotas, SKU availability, prices, image version, disk SKU/size, VM private address, and selected region.
- Tailnet name/suffix, node addresses, Johan's Tailscale identity/device identifiers, node keys, ACL object IDs, and certificate material.
- Telegram bot/user/chat identifiers, provider OAuth state, gateway/API tokens, SSH keys, and every other secret.
- Exact Hermes/container/browser package versions and image digests available at deployment time.
- Selected `~/Projects` children, backup storage account/container names, restore-point object IDs, and measured resource limits.

These facts belong in secret management or a non-secret deployment inventory as appropriate; they are not to be guessed or embedded in this decision record.

## Acceptance implications

Provisioning is not accepted until automated or operator-recorded tests prove all of the following:

- Internet scans and Azure effective rules show no public inbound SSH, VNC/noVNC, CDP, Hermes gateway/serve/dashboard, API, MCP, or filesystem endpoint; Tailscale Funnel/public sharing is off.
- From an unauthorized tailnet principal, TCP 22/443 and all Bot routes are denied. From Johan's approved device, only TCP 22/443 are reachable.
- On the host, only 22/443 bind the Tailscale address; 8701/8702/6081/6082 bind loopback; 5900/9222 are container-loopback only; 8642 and any File Bridge port are absent.
- Each Bot runs non-root, Chromium sandbox checks pass, privileged mode/capabilities/admin sockets are absent, and cross-Bot filesystem/network probes fail.
- Process inventory proves exactly one gateway and one serve instance for each server profile, with no gateway multiplexing, second gateway/serve/dashboard, CLI agent, or standalone cron writer. Simultaneous Telegram and Desktop turns prove bounded queue-or-busy behavior, never overlap execution, preserve `state.db`/WAL integrity, and never cross Bot roots; duplicate process startup is rejected.
- Gateway/serve maintenance and backup tests drain and stop both processes, verify the turn lock is free and no profile DB/WAL descriptor remains, then restart gateway before serve. The file-backup namespace has only the prepared R1 mount: direct probes for `.env`, `auth.json`, `{HERMES_HOME}/home`, browser state, and another Bot root fail.
- Provider inspection and a real turn/cron preflight show only `openai-codex` + `gpt-5.6-sol`; induced provider failure causes no fallback call and triggers a sanitized alert.
- Browser state survives a normal restart for its Bot but is inaccessible to the other Bot. Raw CDP and VNC cannot be reached from the host or tailnet.
- Every legal browser lease transition works; concurrent CDP/noVNC input is impossible; timeout, disconnect, invalid transition, and component crash land in `RECOVERING` with an alert.
- Telegram authorization rejects an unapproved sender and permits the approved sender without creating a public webhook.
- Mac tests prove the normal named-profile path, fixed `terminal.cwd`, profile `HOME`, one launchd gateway, one Desktop-managed local serve, serialized concurrent turns, gateway-owned cron, redacted audit, encrypted backup exclusions, approved-root reads, local single-use approval for every mutation, sensitive-root/path-escape denial, and locked/offline fail-closed behavior.
- Encrypted backup and isolated restore tests pass, including Browser Profile recovery and proof that restoring one Bot does not expose or alter the other.
- Credit, disk, service, provider, browser-recovery, and backup failure alerts arrive in Telegram without secret values.

## Documentation basis

This topology follows current official Hermes documentation: named profiles resolve to independent effective homes under an installation root; `HERMES_HOME` is separate from `terminal.cwd`; `terminal.home_mode: profile` gives tool subprocesses `{HERMES_HOME}/home`; and profiles are not filesystem sandboxes. The Desktop documentation identifies `hermes serve` as its HTTP/JSON-RPC/WebSocket backend and explicitly distinguishes that process from the messaging gateway. The profile and multi-gateway documentation supports one independently managed gateway per profile and warns against uncoordinated writers; Messaging documents Telegram, gateway-owned cron, managed services, and watchdogs. Remote Desktop backends can operate over Tailscale, browser automation supports Chromium through CDP, and Security documents approvals, protected paths, and container isolation. The one-turn lock, quiescence protocol, OS/container/network boundaries, and R1-only backup projection are additional production controls required to make the deliberately concurrent gateway-plus-serve pair safe; they do not redefine `serve` as the disabled OpenAI-compatible API.
