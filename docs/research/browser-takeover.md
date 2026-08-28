# Server browser and human-takeover architecture

**Research ticket:** [hermes-bot-fleet #4](https://github.com/JohanSardar/hermes-bot-fleet/issues/4)  
**Date:** 2026-08-27  
**Target:** Azure Ubuntu VM, private Tailscale access, one persistent browser identity per Bot, live visual inspection and human takeover, no public VNC/noVNC/CDP  
**Scope:** Browser runtime and takeover only. This report does not redesign Bot Mode, messaging, or the general fleet control plane.

## Decision

Use a **dedicated, externally supervised, headed Chromium process per Bot**, attached to Hermes through loopback CDP. Give every Bot:

- its own non-root Unix service account (or its own VM for a high-trust boundary);
- its own Hermes home/profile;
- its own Chromium `--user-data-dir`, X display, CDP port, VNC port, and noVNC port;
- one systemd-supervised browser/display stack;
- one systemd-supervised Hermes gateway whose entire lifetime holds the Bot's browser-ownership lock;
- a takeover command that stops that Bot's gateway, obtains the same lock exclusively, and leaves Chromium running for the human;
- noVNC reachable only by forwarding its loopback listener over Tailscale SSH (preferred), with Tailscale Serve as an optional tailnet-only convenience.

This is the production design because it is the only supported Hermes option that simultaneously gives direct ownership of browser state, durable server-side login sessions, a visible window, a deterministic human-control path, and no cloud-browser custody. Hermes explicitly supports attaching browser tools to a running Chrome/Brave/Chromium/Edge through `browser.cdp_url` or `/browser connect`, and says CDP is useful for real-time viewing and interaction with existing cookies/sessions ([Hermes browser docs: local Chromium via CDP](https://hermes-agent.nousresearch.com/docs/user-guide/features/browser#local-chromium-family-browser-via-cdp-browser-connect)).

**Fallback:** Camofox in headed Docker mode with VNC and `browser.camofox.managed_persistence: true`. It is appropriate when anti-detection is more important than Chromium compatibility. Hermes documents Camofox's built-in VNC live view, deterministic profile-scoped persistence, external tab adoption, and the need to coordinate ownership outside Camofox ([Camofox local mode](https://hermes-agent.nousresearch.com/docs/user-guide/features/browser#camofox-local-mode), [persistent sessions](https://hermes-agent.nousresearch.com/docs/user-guide/features/browser#persistent-browser-sessions), [external sessions/concurrency](https://hermes-agent.nousresearch.com/docs/user-guide/features/browser#externally-managed-camofox-sessions)). Do not use it as the first production choice because it is a Firefox fork, its server build must actually honor `userId` persistence, it has no CDP endpoint for Hermes's Browser Use harness, and Camofox does not arbitrate human/agent control.

## Supported Hermes browser backends: bounded comparison

Hermes currently lists Browser Use Cloud, Browserbase, Browser Use CLI (the default driver), Firecrawl, Camofox, Lightpanda, local Chromium-family CDP, and local Chromium via `agent-browser` ([official backend list](https://hermes-agent.nousresearch.com/docs/user-guide/features/browser)). “Driver” and “browser source” are distinct: Browser Use CLI can drive local Chrome or supported cloud sources; Camofox instead keeps Hermes's built-in tools because it has no CDP endpoint ([Browser Use mode](https://hermes-agent.nousresearch.com/docs/user-guide/features/browser#browser-use-mode-default)).

| Backend/source | Persistence | Human view/takeover | Custody | Fit for this ticket |
|---|---|---|---|---|
| Externally supervised headed Chromium + loopback CDP | Dedicated `--user-data-dir`; survives Hermes and VM service restarts | Native visible window through VNC/noVNC; same browser process | Self-hosted | **Recommended** |
| Hermes local `agent-browser`, `browser.headed: true` | Window is kept between turns, but idle sessions are still reaped and all sessions close on Hermes shutdown | Visible and manually interactive | Self-hosted | Useful development mode, weaker always-on lifecycle contract |
| Camofox headed + managed persistence | Stable profile-scoped `userId`; actual data is server-side and server build must honor it | Documented VNC/noVNC view; external tab adoption | Self-hosted | **Fallback** for anti-detection |
| Browser Use Cloud | Provider persistent profiles for cookies/localStorage/passwords | Provider tooling, not the server's noVNC desktop | Third party | Managed fallback, not preferred for authenticated custody |
| Browserbase | Cloud sessions, plan timeouts/keep-alive | Provider session viewer | Third party | Managed fallback for stealth/proxies |
| Firecrawl cloud browser | TTL-oriented cloud session | Not the required persistent local desktop | Third party/self-hosted Firecrawl | Scraping, not primary Bot identity |
| Lightpanda | Headless engine; Chrome fallback for unsupported actions/screenshots | No graphical renderer, so no direct Lightpanda takeover | Self-hosted | Reject as primary takeover browser |

The local headed-mode docs say Hermes keeps the window open between turns, but also reap idle sessions after `browser.inactivity_timeout` (default 120 seconds) and close sessions on shutdown ([Headed Mode](https://hermes-agent.nousresearch.com/docs/user-guide/features/browser#headed-mode-visible-browser-window)). Externally supervising Chromium decouples the authenticated browser's lifetime from an individual Hermes task or gateway lifecycle.

## Production topology

```text
Azure Ubuntu VM (no public inbound browser ports)
│
├── tailscaled
│   └── private tailnet / Tailscale SSH
│
├── Bot researcher (Unix user: hermes-researcher)
│   ├── HERMES_HOME=/var/lib/hermes-bots/researcher/hermes
│   ├── workspace=/var/lib/hermes-bots/researcher/workspace
│   ├── Chromium data=/var/lib/hermes-bots/researcher/chromium
│   ├── Xvfb :101 -> Openbox -> headed Chromium
│   ├── CDP 127.0.0.1:9222
│   ├── x11vnc 127.0.0.1:5901
│   ├── websockify/noVNC 127.0.0.1:6081
│   └── /run/hermes-browser/researcher/owner.lock
│
└── Bot operator (Unix user: hermes-operator)
    ├── separate Hermes and Chromium state
    ├── Xvfb :102
    ├── CDP 127.0.0.1:9223
    ├── VNC 127.0.0.1:5902
    ├── noVNC 127.0.0.1:6082
    └── separate ownership lock
```

Install the minimal GUI stack: `xvfb`, a small window manager such as `openbox`, `x11vnc`, `novnc`, `websockify`, and Google Chrome/Chromium. Xvfb supplies an in-memory X11 screen; Openbox gives normal window placement; headed Chromium renders onto it; x11vnc exports that existing X display; websockify/noVNC provides a browser client. noVNC's own README describes it as an HTML VNC client and documents `novnc_proxy`/WebSockets to a VNC server ([noVNC README](https://github.com/novnc/noVNC#readme)).

Use one Azure VM only for Bots in the same trust zone. Hermes profiles separate Hermes state but **do not sandbox filesystem access**; the official docs distinguish profiles, workspaces, and sandboxes and state that local-backend profiles retain the OS user's filesystem authority ([Hermes Profiles: profiles vs sandboxing](https://hermes-agent.nousresearch.com/docs/user-guide/profiles#profiles-vs-workspaces-vs-sandboxing)). One Unix user per Bot is therefore the practical baseline. Use a separate VM for finance, customer-admin, production-admin, or mutually distrusting identities.

## Browser and Hermes configuration

### Per-Bot Chromium launch

Illustrative launch for `researcher`:

```bash
export DISPLAY=:101
exec /usr/bin/google-chrome-stable \
  --user-data-dir=/var/lib/hermes-bots/researcher/chromium \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port=9222 \
  --no-first-run \
  --no-default-browser-check \
  --disable-background-networking=false \
  about:blank
```

Do **not** add `--no-sandbox` in a normal host deployment. Run Chromium as the Bot's non-root Unix account and retain its sandbox. Size `/dev/shm` appropriately rather than routinely using `--disable-dev-shm-usage`.

The dedicated user-data directory is mandatory, not cosmetic. Hermes documents that Chrome 136+ refuses remote debugging against the default profile and requires a non-default `--user-data-dir` ([Hermes CDP note](https://hermes-agent.nousresearch.com/docs/user-guide/features/browser#local-chromium-family-browser-via-cdp-browser-connect)); Chrome's own security announcement explains that from Chrome 136 the remote-debugging switches are not honored for the default data directory and recommends a non-standard data directory ([Chrome remote debugging security change](https://developer.chrome.com/blog/remote-debugging-port)).

### Per-Bot Hermes config

```yaml
# /var/lib/hermes-bots/researcher/hermes/config.yaml
browser:
  backend: browser-use
  cdp_url: "http://127.0.0.1:9222"
  restrict_evaluate: true
  dialog_policy: must_respond
  dialog_timeout_s: 300
  record_sessions: true

terminal:
  backend: docker
  cwd: "/workspace"
  docker_forward_env: []

approvals:
  mode: smart
  cron_mode: deny
  single_query_mode: deny

security:
  allow_private_urls: false
  allow_lazy_installs: false
```

`browser.backend: browser-use` explicitly selects the documented default driver; when terminal tools are unavailable Hermes falls back to built-in browser tools ([Browser Use mode and terminal requirement](https://hermes-agent.nousresearch.com/docs/user-guide/features/browser#browser-use-mode-default)). `browser.cdp_url` makes raw `browser_cdp` available at session start and directs normal browser operations to the external browser ([browser_cdp availability](https://hermes-agent.nousresearch.com/docs/user-guide/features/browser#browser_cdp)). Set `restrict_evaluate: true` for logged-in profiles, understanding that it is a primitive-name denylist and can block legitimate expressions ([browser_console security framing](https://hermes-agent.nousresearch.com/docs/user-guide/features/browser#browser_console)).

Do not enable `browser.use_real_profile` on the server. That option copies the server user's current default browser profile into Hermes-managed storage and is intended as consent-gated convenience, not isolation ([Real profile browsing](https://hermes-agent.nousresearch.com/docs/user-guide/features/browser#real-profile-browsing-use-your-own-logins)). Create the dedicated server profile directly through noVNC and sign into only the services that Bot needs.

Hermes profiles still matter: each gets separate `config.yaml`, `.env`, `SOUL.md`, memory, sessions, skills, cron jobs, and state DB; official guidance says never run two agent writers against the same Hermes home ([Profiles](https://hermes-agent.nousresearch.com/docs/user-guide/profiles#what-are-profiles)). In this design each OS service account has exactly one `HERMES_HOME`, and only its supervised gateway writes it.

## Private visual inspection and takeover

### Network rule

Bind all three control surfaces to loopback:

- CDP: `127.0.0.1:922x`
- x11vnc: `127.0.0.1:590x`
- websockify/noVNC: `127.0.0.1:608x`

Example:

```bash
x11vnc -display :101 -forever -shared -localhost -rfbport 5901
websockify --web=/usr/share/novnc 127.0.0.1:6081 127.0.0.1:5901
```

Azure NSG and host firewall must have no inbound allow rule for 922x, 590x, or 608x. CDP is browser control, not an observability endpoint: it can inspect pages, cookies/storage, and execute browser actions. Never publish it through Tailscale Serve either; Hermes alone should connect over loopback.

### Preferred operator path: SSH forwarding over Tailscale

From an authorized tailnet device:

```bash
ssh -N -L 6081:127.0.0.1:6081 hermes-admin@researcher-vm
# Then open http://127.0.0.1:6081/vnc.html
```

Use Tailscale SSH or ordinary SSH addressed to the VM's tailnet name/IP; enforce tailnet ACL/grants so only the operator group reaches SSH. This keeps noVNC itself on loopback and gives the access path Tailscale device/user identity plus SSH authorization. Tailscale documents access controls as deny-by-default for connections not explicitly permitted ([Tailscale access-control policy](https://tailscale.com/kb/1018/acls)).

Optional convenience: publish only noVNC with Tailscale Serve, which proxies a local service exclusively within the tailnet and can provide HTTPS ([Tailscale Serve](https://tailscale.com/kb/1242/tailscale-serve)). Keep the listener local, require narrow grants, and never use Funnel. SSH forwarding remains preferred because the URL ceases to exist when the operator closes the tunnel.

A VNC password is still useful defense in depth, but it is not the network boundary. Store it outside the Hermes profile and do not put it in `config.yaml`, a prompt, or a systemd command line.

## Exclusive agent/human ownership

Hermes/Camofox do not provide a universal browser ownership mutex. Hermes explicitly warns that external clients can drive the same Camofox identity simultaneously and that ownership must be coordinated at the application layer ([Camofox concurrency note](https://hermes-agent.nousresearch.com/docs/user-guide/features/browser#externally-managed-camofox-sessions)). Opening noVNC alone must therefore be read-only operationally until takeover completes.

### Lock invariant

For each Bot, exactly one of these states is valid:

1. **AGENT:** the gateway process is running while holding `/run/hermes-browser/<bot>/owner.lock` exclusively;
2. **HUMAN:** the gateway is stopped and the takeover shell holds that same lock exclusively;
3. **IDLE/FAULT:** neither owns it; automation must not silently resume after a failed takeover.

The advisory lock handles live-process exclusion. Pair it with a durable fail-closed marker, `/var/lib/hermes-bots/<bot>/control/HUMAN`, because `flock` locks do not survive reboot. The gateway unit has an `ExecCondition=` that refuses startup while this marker exists. The takeover helper creates the marker after it has stopped the gateway and acquired the lock; only an explicit normal release or `takeover --recover` removes it. Thus a VM reboot or takeover-shell crash cannot silently restore AGENT ownership.

Run the gateway under `flock` for its entire lifetime:

```ini
ExecStart=/usr/bin/flock --exclusive /run/hermes-browser/%i/owner.lock \
  /usr/local/bin/hermes gateway run
```

A takeover helper performs:

```bash
systemctl stop hermes-gateway@researcher.service
systemctl is-active --quiet hermes-gateway@researcher.service && exit 1
exec flock --exclusive /run/hermes-browser/researcher/owner.lock \
  /usr/local/libexec/hermes-human-session researcher
```

`hermes-human-session` creates the durable HUMAN marker, writes an audit record (operator, Bot, UTC start), prints the noVNC tunnel command, and waits until the operator explicitly types `release`. On normal release it writes the end record, removes the marker while still holding the lock, starts the gateway (which waits on the lock), and exits to release the lock. Use a shell `trap` to record abnormal termination and **leave both the marker and gateway stopped**; recovery then requires an explicit `takeover --recover <bot>`. Fail-closed is preferable to an agent resuming while the person still believes they own the browser.

Stopping the per-Bot gateway also stops new messaging work and its in-process scheduler before human input. Wait for the process to exit and verify no Bot-scoped `hermes` process remains before granting HUMAN. Existing Chrome stays alive. Forbid ad-hoc `hermes -p <bot>` processes in production; operators must use wrappers that take the same lock. A root/admin user can always bypass this convention, so this is a strong operational interlock, not a kernel security boundary.

If jobs can originate from another daemon, multiplex gateway, or external worker, that producer must also acquire the same lock or be stopped. The simplest safe fleet layout is one per-Bot gateway and no shared gateway for browser-owning Bots.

## systemd supervision

Use system units (not login-session processes) and order them as:

```text
network-online.target
  └─ tailscaled.service
hermes-display@BOT.service (Xvfb + Openbox)
  └─ hermes-browser@BOT.service (Chromium)
      ├─ hermes-vnc@BOT.service (x11vnc)
      │   └─ hermes-novnc@BOT.service (websockify)
      └─ hermes-gateway@BOT.service (Hermes + ownership lock)
```

Template characteristics:

- `User=hermes-%i`, `Group=hermes-%i`; never root.
- `EnvironmentFile=/etc/hermes-bots/%i/runtime` for non-secret port/display/path assignments.
- `EnvironmentFile=/etc/hermes-bots/%i/secrets` only on the Hermes gateway, mode `0600`, never on browser/VNC units.
- `Restart=on-failure`, bounded restart delay, start-limit protection.
- `Requires=` and `After=` on display/browser dependencies; `BindsTo=` where loss of the display should terminate Chromium.
- Create `/run/hermes-browser/<bot>/` at boot with `systemd-tmpfiles`, owned by the Bot account and mode `0750`; do not tie the lock directory's lifetime to the gateway unit, because it must remain available while that unit is stopped for HUMAN ownership. Persistent data belongs under `/var/lib/hermes-bots/%i`.
- `UMask=0077`, `NoNewPrivileges=true`, `PrivateTmp=true`, `ProtectSystem=strict`, and narrowly enumerated `ReadWritePaths=`. Test hardening against Chromium's sandbox and shared-memory requirements before enabling every knob.
- Explicit `TimeoutStopSec`; Chromium gets SIGTERM and time to flush profile databases before SIGKILL.
- Health checks against `http://127.0.0.1:$CDP/json/version`, VNC/noVNC listeners, and `hermes -p ... doctor/status` as appropriate.

Example browser unit core:

```ini
[Unit]
Description=Persistent headed browser for Hermes Bot %i
Requires=hermes-display@%i.service
After=hermes-display@%i.service

[Service]
Type=simple
User=hermes-%i
Group=hermes-%i
EnvironmentFile=/etc/hermes-bots/%i/runtime
ExecStart=/usr/local/libexec/hermes-chromium %i
Restart=on-failure
RestartSec=5s
TimeoutStopSec=45s
UMask=0077
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

Example gateway core:

```ini
[Unit]
Description=Hermes gateway for Bot %i
Requires=hermes-browser@%i.service
After=network-online.target hermes-browser@%i.service

[Service]
Type=simple
User=hermes-%i
Group=hermes-%i
Environment=HERMES_HOME=/var/lib/hermes-bots/%i/hermes
EnvironmentFile=/etc/hermes-bots/%i/secrets
ExecCondition=/usr/local/libexec/hermes-agent-allowed %i
ExecStart=/usr/bin/flock --exclusive /run/hermes-browser/%i/owner.lock /usr/local/bin/hermes gateway run
Restart=on-failure
RestartSec=10s
UMask=0077
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

Provision each runtime directory and lock file independently. For example, generate `/etc/tmpfiles.d/hermes-browser.conf` with concrete Bot names:

```text
d /run/hermes-browser/researcher 0750 hermes-researcher hermes-researcher -
f /run/hermes-browser/researcher/owner.lock 0640 hermes-researcher hermes-researcher -
d /run/hermes-browser/operator 0750 hermes-operator hermes-operator -
f /run/hermes-browser/operator/owner.lock 0640 hermes-operator hermes-operator -
```

Run `systemd-tmpfiles --create /etc/tmpfiles.d/hermes-browser.conf` during provisioning. Pre-creating each lock prevents a root-run takeover helper from creating a root-owned file that the Bot service cannot later open. Avoid one shared `RuntimeDirectory=` declaration on every template instance: ownership would conflict, and stopping the gateway could remove the directory needed by HUMAN ownership.

Alternatively, Hermes can install a separate named profile gateway service itself (`<profile> gateway install`), and the profile docs confirm independent systemd services ([Profiles: persistent services](https://hermes-agent.nousresearch.com/docs/user-guide/profiles#persistent-services)). For this design, add a systemd drop-in that wraps its `ExecStart` with the ownership lock; do not run both the generated unit and a custom duplicate.

## State, backups, and secret boundaries

### Persistent state

| State | Location | Owner | Backup treatment |
|---|---|---|---|
| Hermes profile | `/var/lib/hermes-bots/<bot>/hermes` | Bot Unix user | Encrypted; stop gateway or use application-consistent snapshot |
| Browser profile | `/var/lib/hermes-bots/<bot>/chromium` | Bot Unix user | Treat as credential vault; stop Chromium or use tested filesystem snapshot |
| Workspace | `/var/lib/hermes-bots/<bot>/workspace` | Bot Unix user/container mapping | Normal data classification |
| Ownership control state | `/var/lib/hermes-bots/<bot>/control/HUMAN` (present only in HUMAN/failed takeover) | Bot account; checked by gateway `ExecCondition` | Back up or otherwise preserve across reboot |
| Ownership audit | append-only journal/syslog or protected `/var/log/hermes-browser-ownership/` | root/audit group | Retain and monitor |
| Runtime locks | `/run/hermes-browser/<bot>/owner.lock` | Bot account; directory provisioned by tmpfiles | Never back up |

Cookies, saved sessions, localStorage, service-worker data, and saved passwords make the Chromium directory equivalent to a secret. Encrypt Azure managed disks and backups, encrypt off-site copies, restrict snapshot/RBAC access, and perform a restore drill into an isolated VM. Never live-copy the browser directory with plain `cp -r`; stop Chromium or use a crash-consistent snapshot and verify the restored browser opens cleanly.

### Secret compartments

1. **Hermes/provider and messaging secrets:** per-Bot Hermes `.env` or root-owned systemd credentials file, mode `0600`; exposed only to that Bot's gateway.
2. **Browser-auth secrets:** browser profile directory; never mount into terminal containers, never expose over SMB/NFS, never include in profile exports.
3. **VNC secret:** separate root-managed credential file; available only to x11vnc.
4. **Tailscale node identity:** owned by `tailscaled`/root, not readable by Hermes or the browser.
5. **Workload credentials:** prefer narrow, revocable service accounts. Do not reuse the human's everyday Chrome profile.

Hermes recommends non-root gateway operation, explicit messaging allowlists, `.env` mode `0600`, container terminal backend for production, and no host environment variables forwarded by default ([Hermes production security checklist](https://hermes-agent.nousresearch.com/docs/user-guide/security#best-practices-for-production-deployment), [container resource and environment controls](https://hermes-agent.nousresearch.com/docs/user-guide/security#resource-limits)). Leave `GATEWAY_ALLOW_ALL_USERS` unset and use pairing/allowlists. Keep `security.allow_private_urls: false`; Hermes notes that enabling it disables SSRF rejection for RFC1918, loopback, link-local, CGNAT/Tailscale, and metadata destinations ([SSRF protection](https://hermes-agent.nousresearch.com/docs/user-guide/security#ssrf-protection)). The loopback `browser.cdp_url` is an operator-configured backend connection, not a reason to grant arbitrary webpage navigation to private networks.

## Concrete acceptance tests

All tests are per Bot and then repeated concurrently for at least two Bots.

### A. Network exposure

1. From the VM: `ss -lntp` shows CDP, VNC, and noVNC only on `127.0.0.1` (or `::1` if intentionally configured), never `0.0.0.0`, public NIC, or Tailscale NIC.
2. From an internet host: scans of the Azure public IP for 922x/590x/608x time out or refuse; Azure NSG has no corresponding rules.
3. From an unauthorized tailnet identity: SSH/noVNC access is denied by grants/ACL.
4. From an authorized tailnet identity: the SSH-forward command opens noVNC; closing SSH removes local access.
5. CDP remains unreachable from every remote device, including authorized tailnet devices.

### B. Browser identity and restart persistence

1. Through noVNC, sign into a low-risk test application and set a unique cookie/localStorage marker.
2. Run a Hermes browser task; it sees the same test identity and marker.
3. Restart only the Hermes gateway; marker and login remain.
4. Restart Chromium cleanly; marker and login remain.
5. Reboot the VM; systemd restores display, Chromium, noVNC, then gateway; marker and login remain.
6. Verify Bot A cannot see Bot B's marker, cookies, history, downloads, or `user-data-dir` by Unix permissions or through Hermes.
7. `curl http://127.0.0.1:9222/json/version` succeeds locally, and Chromium's command line contains the expected non-default `--user-data-dir`.

### C. Agent operation and visual parity

1. In AGENT state, ask Hermes to navigate, click, type a harmless string, take a snapshot, and take a vision screenshot.
2. Observe the same actions live in noVNC.
3. Confirm `browser_cdp(method="Target.getTargets")` works for the intended Bot.
4. Trigger a test `alert()` page; verify `must_respond` surfaces it and the agent can accept/dismiss it (the Hermes availability matrix lists full dialog support for local Chrome via CDP: [browser_dialog](https://hermes-agent.nousresearch.com/docs/user-guide/features/browser#browser_dialog)).
5. Confirm browser recordings, if enabled, are created and expire under the documented policy.

### D. Ownership and takeover race tests

1. With gateway active, a takeover request stops it, waits for exit, acquires the lock, records HUMAN state, and only then tells the operator to interact.
2. While HUMAN holds the lock, `systemctl start hermes-gateway@BOT` blocks/fails to obtain ownership and no browser action occurs.
3. Messages and scheduled browser work received during HUMAN do not execute; document whether they queue or are rejected.
4. Human completes an MFA/test login, explicitly releases takeover, then gateway starts and can use the new session.
5. Kill the takeover SSH shell without releasing. The trap records an abnormal end and the gateway remains stopped (fail-closed).
6. Reboot during HUMAN. Gateway must not automatically resume unless the ownership state/recovery policy explicitly permits it; alert the operator.
7. Attempt to launch a second gateway or ad-hoc Bot CLI. It cannot obtain the lock or is denied by operational permissions.
8. Run two Bot takeovers simultaneously; locks and browsers remain independent.

### E. Failure and recovery

1. Kill Chromium: systemd restarts it; gateway either reconnects or is restarted after CDP health passes. No infinite crash loop.
2. Kill Xvfb: dependent Chromium/VNC are stopped and restarted in dependency order.
3. Fill a test filesystem to the alert threshold: monitoring detects it before browser-profile corruption.
4. Corrupt a disposable browser profile: service refuses unsafe fallback to another Bot/default profile and raises an alert.
5. Restore encrypted Hermes and browser backups into an isolated VM; verify Bot identity, login marker, gateway, and noVNC.
6. Expire/rotate one Bot's provider and channel tokens; only that Bot is affected.

### F. Security regression

1. Confirm services run as their Bot accounts, not root.
2. `namei -l` verifies other Bot users cannot traverse/read another Chromium or Hermes directory.
3. Terminal container cannot read host Chromium profile, Tailscale state, other Bots' `.env`, or VNC password.
4. Messaging from an unpaired/non-allowlisted user is denied.
5. A browser prompt-injection test cannot navigate to Azure metadata or Tailscale/private addresses while `allow_private_urls` remains false.
6. Patch/upgrade rehearsal preserves loopback bindings, profile paths, and lock behavior.

## Rollout and fallback trigger

1. Build one disposable Bot with a test account.
2. Pass sections A–F, including reboot, abnormal takeover, and restore.
3. Template ports/displays/users and add a second Bot; repeat isolation and concurrency tests.
4. Add real low-risk identities only after the test profile is destroyed.
5. Use Camofox only if target sites demonstrably reject standard Chromium automation and its compatibility/persistence tests pass. For Camofox set the nested key exactly:

```yaml
browser:
  cloud_provider: camofox
  camofox:
    managed_persistence: true
```

Hermes warns that putting `managed_persistence` at the top level is ignored and yields ephemeral identities ([nested-path warning](https://hermes-agent.nousresearch.com/docs/user-guide/features/browser#persistent-browser-sessions)). Mount Camofox's profile storage persistently, bind its API/VNC/noVNC host ports to loopback rather than the documentation's broad demonstration mapping, and reuse the same ownership-lock protocol.

## Risks and explicit non-goals

- The ownership lock coordinates supervised processes; it does not defend against root or an administrator intentionally bypassing it.
- A Hermes profile is not an OS sandbox. Unix users/containers/VMs supply the actual isolation boundary.
- noVNC is not an authorization system by itself. Tailscale identity/ACL plus SSH is the access boundary.
- A persistent logged-in browser is a high-value credential store. Server compromise is account compromise until sessions are revoked.
- CAPTCHAs and MFA may prohibit automation or require site-specific compliance review; takeover capability does not waive service terms.
- This report does not promise seamless queuing of messages during takeover; acceptance testing must establish the gateway/channel behavior and the operator runbook.
- This report does not expose a public VNC/CDP endpoint, clone a laptop's everyday browser profile, or allow multiple agents to share one browser identity concurrently.

## Source index

Primary sources consulted and linked above:

- [Hermes Browser Automation](https://hermes-agent.nousresearch.com/docs/user-guide/features/browser)
- [Hermes Profiles](https://hermes-agent.nousresearch.com/docs/user-guide/profiles)
- [Hermes Configuration](https://hermes-agent.nousresearch.com/docs/user-guide/configuration)
- [Hermes Security](https://hermes-agent.nousresearch.com/docs/user-guide/security)
- [Chrome: Changes to remote debugging switches to improve security](https://developer.chrome.com/blog/remote-debugging-port)
- [noVNC README](https://github.com/novnc/noVNC#readme)
- [Tailscale Serve](https://tailscale.com/kb/1242/tailscale-serve)
- [Tailscale access-control policy](https://tailscale.com/kb/1018/acls)

Background synthesis reviewed first: `/Users/johansardar/research/hermes-grok-bot-server-feasibility.md`. Material Hermes claims in this report were rechecked against the official live documentation on 2026-08-27.