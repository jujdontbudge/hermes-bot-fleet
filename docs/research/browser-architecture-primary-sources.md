# Persistent per-bot browsers for Hermes Agent on a private Linux server

Research snapshot: 2026-08-27 (America/Chicago; 2026-08-28 UTC)

Scope: Hermes Agent browser backends; durable per-bot browser identities; headful Linux; private human inspection/takeover over Tailscale; browser/display ownership and concurrency; service supervision; and acceptance tests. No GitHub repository or issue was modified.

## Executive conclusion

For self-hosted, durable, human-viewable browser identities, use this shape:

```text
Tailscale tailnet (deny by default; explicit operator -> viewer ports)
                         |
              native viewer or tailnet-only HTTPS
                         |
Linux server             v
+-- one Unix user or container per bot/trust boundary
|   +-- one Hermes profile / HERMES_HOME
|   +-- one browser profile directory on durable storage
|   +-- one live browser process that exclusively owns that directory
|   +-- one private X display or desktop session
|   +-- one private viewer endpoint
|   +-- one per-bot ownership lease
|   `-- systemd supervision and health checks
+-- CDP: loopback-only, never publicly routed
+-- VNC/viewer: loopback or tailscale0/Tailscale Serve only, never public
`-- backups made only after clean browser shutdown or from a tested snapshot
```

Recommended default:

1. **Chrome path (most capable):** one dedicated, non-default `--user-data-dir` and one Chrome process/CDP endpoint per bot. Keep CDP on loopback. Put headful Chrome on a per-bot X display and expose only the display through a private viewer. Configure that bot's Hermes profile with its unique `browser.cdp_url`. This retains Hermes's CDP/Browser Use CLI capabilities and makes identity boundaries explicit. [H1][H3][C1][C2][P1]
2. **Camofox path (anti-detection/fingerprinting):** one Hermes profile plus `browser.camofox.managed_persistence: true`, a Camofox server that really maps stable `userId` values to persistent Firefox profile directories, and persistent server storage. Use the server-controlled headed/VNC mode. Camofox is Firefox/REST-based and has no CDP; Hermes falls back to its built-in browser tools. [H1][H4][H5][CF1]
3. **Viewer:** prefer a native private viewer—Xpra over SSH/Tailscale, TigerVNC bound to localhost and reached over Tailscale/SSH, or RustDesk direct-IP over Tailscale—over publishing noVNC. If a browser-only UI is required, Tailscale Serve in front of loopback-only noVNC or Apache Guacamole is acceptable; do not use Funnel. [T1][T2][V1][X1][G1][R1]
4. **Ownership:** never permit the agent and human to inject input concurrently. A visible window does not create coordination. Use an explicit lease with `AUTOMATION`, `DRAINING`, `HUMAN`, and `RECOVERING` states. Multiple tabs or CDP clients are not separate cookie jars and do not prevent focus/input races. [H2][H6][C3]
5. **Supervision:** use systemd units/targets for the display, browser, viewer, and Hermes gateway. Use readiness probes, `Restart=on-failure`, bounded start/stop timeouts, and clean dependency ordering. Use a system service with a dedicated `User=` for the clearest boot semantics, or a user service only with `loginctl enable-linger`. [S1][S2][S3]

The critical invariant is: **one durable browser profile directory -> one owning browser process -> one bot lease holder at a time.** A Hermes profile is an application-state boundary, not by itself an OS/browser security boundary. [H7][C1][P1]

---

## 1. What Hermes supports

### 1.1 Backend and driver are separate choices

At the reviewed 2026-08-27 Hermes source snapshot (`NousResearch/hermes-agent` commit `6dcebea7fc5d0cc4f621eeaddf52b7d877a5f882`), Hermes documents these browser sources/backends:

- Browser Use Cloud
- Browserbase
- Firecrawl
- Nous Tool Gateway, backed by Browser Use
- Camofox
- local Chromium via `agent-browser`
- an explicit CDP endpoint

The browser driver/tool surface is separately selected:

- Browser Use CLI 3.0 through `browser_exec`; or
- Hermes's built-in `browser_*` tools.

Browser Use CLI is the default driver when runnable and `browser.backend` is unset; Hermes falls back to built-in tools if it is unavailable. Setting `browser.backend: off` forces built-in tools, while `browser.backend: browser-use` forces the Browser Use CLI path. Camofox cannot be driven through CDP and therefore stays on built-in tools. [H1][H2]

Backend selection is stored in `browser.cloud_provider`. Credentials do not silently override a stored selection. Recognized built-in selections include `browser-use`, `browserbase`, `firecrawl`, `camofox`, `nous`, and `local`. A stored missing backend errors rather than silently switching. [H1][H8]

An explicit `BROWSER_CDP_URL`, followed by persistent `browser.cdp_url`, takes precedence over cloud/local/Camofox selection for the browser tools. [H8]

### 1.2 Capability/persistence matrix

| Hermes path | Control protocol | Durable identity as currently wired | Human-view path | Important constraint |
|---|---|---|---|---|
| Dedicated local Chrome + explicit CDP | CDP; Browser Use CLI or built-in tools | **Yes, operator-managed** with one durable non-default user-data dir per bot | Same headful X display through Xpra/VNC/etc. | One process per data dir; CDP is privileged and must stay private |
| Default local `agent-browser --session` | Local Chromium harness | **No durable per-bot guarantee**; random session and cleanup lifecycle | `browser.headed: true` shows a local window | Headed/warm is not the same as disk-backed persistent identity |
| Hermes “real profile” | CDP against a copied profile snapshot | Snapshot persists under `HERMES_HOME`, but is a copy of the OS user's active profile | Headed copied browser | Not a provisioning mechanism for independent bot accounts; do not treat as direct control of live default Chrome |
| Camofox default | REST / Firefox | No; random `userId` | Server-controlled VNC when enabled | Hermes `browser.headed` does not control Camofox visibility |
| Camofox managed persistence | REST / Firefox | **Potentially yes**: stable profile-derived `userId`; server must persist it | Camofox server VNC | No CDP; fewer console/dialog features; external ownership serialization required |
| Browser Use Cloud | Cloud + CDP | Service supports profiles, but reviewed Hermes provider does not expose/send a profile ID | Provider viewer if offered | Do not assume selecting Browser Use binds a bot to a durable provider profile |
| Browserbase | Cloud + CDP | No built-in per-bot durable profile mapping | Provider live-view/session | `keepAlive` is reconnection to a session, not cross-session profile identity |
| Firecrawl | Cloud + CDP | No; TTL browser deleted on cleanup | Provider-dependent | Task-scoped TTL |
| Nous Tool Gateway | Managed Browser Use | No documented per-bot profile binding in reviewed source | Provider-dependent | Task-scoped request |
| Lightpanda | Local engine | Not a graphical profile backend | None; no graphical rendering | Falls back to Chrome for unsupported operations |

Sources for this table: [H1]-[H6], [H8]-[H11].

### 1.3 Local Chrome/CDP details in Hermes

Without cloud or CDP override, Hermes generates a random local `agent-browser --session` name. On CDP/cloud paths it uses `--cdp` instead; Hermes explicitly avoids combining `--session` and `--cdp` because affected `agent-browser` versions prioritize the local session and ignore CDP. [H9]

The interactive `/browser connect` command can attach to or launch Chrome, Brave, Chromium, or Edge, normally on port 9222. It is a CLI slash command, not a gateway command, so Telegram/Discord/WebUI bot surfaces cannot establish it interactively. A persistent unattended server should configure a stable `browser.cdp_url` rather than depend on `/browser connect`. [H3]

Hermes's auto-launched debugging browser uses a Hermes-owned profile directory such as `$HERMES_HOME/chrome-debug`, which is necessary because Chrome 136+ ignores remote-debugging switches against the default Chrome data directory. [H3][C2]

`browser.use_real_profile: true` does **not** drive the live default profile. Hermes detects the default Chromium-family browser, reads the last-used profile, copies it under `$HERMES_HOME/browser-profile/<browser>/`, launches the copy, and re-syncs auth-bearing data when a fresh session starts. This avoids Chrome 136's default-profile restriction and live profile-lock contention. Disabling consent deletes the snapshot store. [H3]

Architectural consequences:

- Named `browser_exec` sessions attached to one CDP browser get separate harness daemons/tabs, **not separate cookie stores**.
- Multiple Hermes bots pointed to the same CDP endpoint share the same browser identity.
- Per-bot Chrome identity requires separately launched browsers, separate user-data directories, and separate loopback CDP ports/URLs.
- `browser.headed: true` applies to the default local `--session` path, not CDP/cloud/Camofox. Headed sessions can stay warm between turns but are still subject to Hermes cleanup/shutdown and are not a substitute for an explicitly durable profile. [H2][H6][H9]

### 1.4 Camofox details in Hermes

Hermes documents Camofox as a self-hosted Camoufox/Firefox REST server. Its headed mode is controlled by the server (for example `ENABLE_VNC=1`), not by Hermes's `browser.headed`. The documented Docker shape persists server state with a volume and commonly exposes noVNC on 6080 plus native VNC on 5900/5901. Those ports must be rebound/filtered for this architecture; the sample's existence is not permission to publish them. [H4]

Default Camofox sessions use a random `userId`, so state does not survive agent restarts. Durable identity is opt-in at the exact nested key:

```yaml
browser:
  cloud_provider: camofox
  camofox:
    managed_persistence: true
```

When enabled, Hermes derives a deterministic `userId` from its profile-scoped state path, uses a deterministic task `session_key`, and avoids destructive server-side cleanup. Hermes supplies a stable key; **the Camofox server must actually map that key to persistent Firefox storage**. Browser data remains server-side. [H4][H5]

Hermes also supports external `user_id`, `session_key`, and `adopt_existing_tab` settings. Tab adoption does not coordinate focus or ownership. Hermes's own docs warn that clients sharing a `userId` require external serialization. [H4][H5]

Camofox limitations relevant to selection:

- no CDP and no Browser Use CLI attach path;
- reduced browser-console/native-dialog support compared with CDP;
- `headless="virtual"` in the Camoufox library creates a Linux Xvfb display but not a complete authenticated takeover service;
- persistent Firefox storage is supported through Playwright persistent contexts, but deterministic fingerprint continuity across restarts is not guaranteed by current official documentation; verify the deployed build independently from cookie continuity. [H10][CF1][CF2]

### 1.5 Cloud backends are not the default answer for per-bot identity

Browser Use Cloud advertises reusable profiles at the service level, but the reviewed Hermes direct provider sends no profile ID in the create payload. Browserbase creates a task/session browser; `keepAlive` allows reconnection within that provider session and is not a profile mapping across new sessions. Firecrawl creates TTL browsers and deletes them on cleanup. The Nous-managed Browser Use path is similarly task-scoped in reviewed code. Therefore none should be called a built-in durable per-Hermes-bot identity without separately proving a provider profile mapping. [H1][H11]

---

## 2. Chrome, Playwright, and Camoufox constraints

### 2.1 Chrome profile layout and locking

Chromium defines the user-data directory as the parent containing browser state and one or more profile subdirectories such as `Default`. On Linux the normal defaults include `~/.config/google-chrome` and `~/.config/chromium`; `--user-data-dir=/absolute/path` overrides the location. `chrome://version` reports the active profile path; the user-data directory is its parent. [C1]

Chromium explicitly states that two running Chrome instances cannot share a user-data directory. Its Linux `ProcessSingleton` is keyed by that directory and uses singleton lock/socket machinery to ensure no more than one application instance owns it. [C1][C4]

Use this mapping:

```text
/var/lib/hermes-browsers/<bot>/chrome/       # user-data-dir; durable secret state
/run/hermes-browsers/<bot>/                  # PID, socket, lease; volatile
127.0.0.1:<unique-port>                      # CDP; loopback only
:<unique-display>                            # X display; one desktop per bot
```

Never pass `/var/lib/.../chrome/Default` as `--user-data-dir`; pass its parent. Never copy, rsync, or back up a live profile without a filesystem/database-consistent snapshot that has been tested. Prefer a clean browser shutdown.

### 2.2 Chrome 136+ remote-debugging restriction

Since Chrome 136, `--remote-debugging-port` and `--remote-debugging-pipe` are ignored when targeting Chrome's default data directory. They must be paired with `--user-data-dir` pointing at a non-standard directory. Chrome says the separate directory uses a different encryption key and recommends Chrome for Testing for automation-specific scenarios. [C2]

This reinforces, rather than weakens, the recommended design: create a dedicated automation profile from day one; do not attach CDP to an operator's everyday browser profile.

### 2.3 CDP is a privileged control plane

CDP exposes domains for DOM inspection, runtime JavaScript evaluation, network inspection, debugging, and page manipulation. Chrome's own 136 announcement cites attackers using remote debugging to extract cookies. Current Chromium listener source is loopback-oriented. Multiple CDP clients are technically supported, but that is transport concurrency, not safe operational ownership. [C2][C3][C5]

Policy:

- bind CDP to loopback only;
- do not Tailscale Serve it;
- do not route it directly across the tailnet unless an unusual debugging case requires an authenticated temporary tunnel;
- Hermes accesses it locally on the server;
- the human takes over through pixels/input, not through CDP;
- acceptance tests must prove public, LAN, and unauthorized tailnet clients cannot reach `/json/version` or the WebSocket endpoint.

### 2.4 Playwright persistent contexts

`browserType.launchPersistentContext(userDataDir, options)` stores cookies/local storage in the supplied directory and returns the browser's only context; closing it closes the browser. Playwright explicitly says browsers do not allow multiple instances with the same user-data directory and warns that automating Chrome's default user profile is unsupported. [P1]

`chromium.connectOverCDP()` can attach to an existing Chromium browser and exposes its default context, but Playwright calls CDP attachment significantly lower fidelity than its native protocol and warns that features may break if the external browser lacks expected launch arguments. [P2]

Use multiple pages inside one owned persistent context for within-bot concurrency, or separate profile directories for truly parallel identities. Never let two workers independently call `launchPersistentContext()` on the same directory.

### 2.5 Headful Linux

Chrome headless has no visible UI. Since Chrome 112 unified headless creates platform windows but does not display them; old headless left the main Chrome binary from Chrome 132. That does not provide human takeover. [C6]

Playwright's official Linux guidance says headed execution requires Xvfb on CI and demonstrates `xvfb-run`. Xvfb supplies a framebuffer only; a viewer/input transport is still required. [P3]

Camoufox supports:

- `headless=False`: ordinary visible/headful mode;
- `headless=True`: true Firefox headless;
- `headless="virtual"`: Linux-only Xvfb-backed headful rendering.

The virtual mode requires Xvfb and does not itself authenticate or publish a viewer. [CF1]

Chromium also warns that one Chrome instance cannot show windows on multiple X displays and that modern Linux D-Bus cross-talk can complicate multiple independent Chrome/X sessions under one Unix user. Separate Unix users or containers reduce those collisions and are preferred when bots differ in trust or run multiple desktops. [C1]

---

## 3. Concurrency and takeover ownership

### 3.1 Required lock layers

Use two separate locks:

1. **Process/profile lock:** guarantees one browser process owns one profile directory. Chrome/Firefox enforce parts of this internally, but systemd/orchestration must avoid duplicate launches and make stale-process recovery explicit.
2. **control lease:** guarantees only one actor injects input/navigation into the live browser at a time. Browser internal locks do not solve human-versus-agent races.

Suggested lease record (stored under `/run`, not in the profile):

```json
{
  "bot": "research-bot",
  "state": "AUTOMATION",
  "holder": "hermes-profile:research-bot",
  "lease_id": "opaque-random-id",
  "issued_at": "RFC3339",
  "expires_at": "RFC3339",
  "active_job": "session/task identifier",
  "browser_pid": 1234,
  "display": ":101"
}
```

Suggested state machine:

```text
AUTOMATION --takeover requested--> DRAINING
DRAINING --active command complete; automation paused--> HUMAN
HUMAN --operator releases--> RECOVERING
RECOVERING --URL/tabs/dialogs/profile health reconciled--> AUTOMATION
```

Rules:

- New browser jobs fail or queue while `DRAINING`, `HUMAN`, or `RECOVERING`.
- Do not revoke automation mid-click unless emergency stop is requested; let the current atomic operation end, then verify quiescence.
- Human takeover opens the existing display/browser. It never launches a second browser against the profile.
- On hand-back, record active URL, tabs, modal dialogs, downloads, and login state; dismiss only according to policy.
- Use a short renewable lease plus a maximum takeover duration, but do not auto-return control while human input is still active.
- On holder crash, move to `RECOVERING`; inspect browser/process state before granting a new holder.
- Keep audit events for request, drain complete, human attach/detach, hand-back, forced revocation, and browser restart. Never log cookies/CDP payloads.

For current Hermes, this is external orchestration: Hermes/Camofox named sessions or adopted tabs do not provide a universal takeover state machine. [H2][H4][H6]

### 3.2 Concurrency policy

- Default maximum: one active navigation workflow per browser identity.
- Allow parallel pages only for workflows explicitly designed not to change shared account state, focus, clipboard, downloads, or global browser settings.
- Never assume tab isolation equals cookie/localStorage isolation.
- Separate bots/accounts: separate user-data dirs and browser processes.
- Separate trust levels: separate Unix users/containers/VMs, not only Hermes profiles.
- Resource admission should account for RAM, file descriptors, X displays, and CPU. Neither Camoufox nor Chrome publishes a safe universal maximum; load-test the actual sites and builds.

---

## 4. Private visual inspection/takeover options

### 4.1 Network invariant

No browser-control or desktop endpoint is public:

- CDP: `127.0.0.1` only.
- Raw VNC: `127.0.0.1` only, or at most the server's Tailscale address with a host firewall and tailnet grant. Loopback is safer.
- Browser viewer (noVNC/Guacamole/Xpra HTML5): loopback backend; Tailscale Serve is the only ingress if browser access is required.
- Never use Tailscale Funnel, a public reverse proxy, public cloud security-group ingress, router port-forwarding, or `0.0.0.0` without an independently verified private-interface/firewall boundary.

A Tailscale tailnet is private, and Serve is tailnet-only; Funnel is public. Access-control grants still apply to Serve. Tailscale's own Serve guidance recommends loopback backends to prevent bypass/spoofing of identity or capability headers. [T1][T2][T3]

Use tailnet grants to permit only the operator identity/device group to the exact viewer port/service. A device merely joining the tailnet should not imply viewer access.

### 4.2 Option matrix

| Option | Best use | Strengths | Constraints / cautions | Verdict |
|---|---|---|---|---|
| **Xpra native over SSH/Tailscale** | Per-bot X11 app/full desktop, low operational exposure | Persistent sessions; attach over SSH using Unix sockets; can forward a single app or desktop; no browser web gateway required | Install native client; X11-centric; shadow mode capture can use more CPU; raw TCP examples are explicitly unauthenticated unless configured | **Preferred default** for Linux operators comfortable with a native client [X1][X2] |
| **TigerVNC native over Tailscale/SSH** | Straightforward full private virtual desktop | Mature; Xvnc creates desktop+VNC; upstream systemd integration; `localhost` option; multiple displays/users | VNC auth is comparatively basic; clipboard/input races remain; upstream warns not to run as root and that a user already in a graphical session may conflict | **Good simple option** when bound to localhost [V1] |
| **noVNC + websockify behind Tailscale Serve** | Browser-only access with minimal UI | Standard HTML5 VNC client; WSS support; easy to front a loopback VNC server | noVNC/websockify is a transport/UI, not a complete identity-aware takeover system; websockify translates WebSocket to raw socket; must protect both web and VNC legs; multiple clients can fight over mouse | **Acceptable browser-only option**, not preferred over native private viewers [N1][N2] |
| **Apache Guacamole behind Tailscale Serve** | Browser-only multi-bot gateway with user/auth/connection catalog | Mature HTML5 gateway; browser -> web app -> `guacd` -> VNC/RDP/SSH; extensible authentication; central connections | Heavier stack (Tomcat/web app/guacd/database); more services/secrets; reverse proxy/WebSocket configuration; must trust forwarded headers only from controlled proxy | **Best richer browser gateway** when noVNC is too bare [G1][G2][G3] |
| **RustDesk direct IP over Tailscale** | Full desktop native takeover without public rendezvous/relay | Tailscale officially documents server-free direct-IP private use; cross-platform; unattended password option | Whole-desktop tool, not per-window; persistent password is sensitive; direct-IP mode must be restricted by tailnet policy; verify Linux virtual-display compatibility | **Strong cross-platform native alternative** [R1][R2] |
| **Sunshine + Moonlight over Tailscale** | Very low latency/high-resolution desktop | Hardware/software encoding; native clients; pairing and input; Linux systemd units | Gaming-oriented; extra UDP/TCP surface; headless GPU/display setup can be complex; virtual input permissions; configuration UI and pairing must be private | **Use for latency/quality**, overkill for routine login takeover [SU1][SU2] |
| **Waypipe over Tailscale SSH** | Launching individual Wayland applications remotely | Wayland network transparency over SSH; no standing web/VNC service | Better for app forwarding than sharing the exact persistent desktop; client/server Wayland compatibility and latency; less appropriate for browser-only takeover | **Niche Wayland option**, not the primary shared-desktop path [W1] |
| **x11vnc** | Shadow an already-running X display | Shares the exact active display; works with native VNC/noVNC/Guacamole | It does not create the desktop; depends on Xvfb/Xorg; secure binding/auth left to operator; simultaneous clients can fight for input | **Useful component**, not a full architecture [N2][G2] |

### 4.3 Preferred viewer choices

- **Best minimal native path:** Xpra over Tailscale SSH, attaching to the existing per-bot X session.
- **Best simple traditional path:** TigerVNC/Xvnc per bot with `localhost`, then a native viewer through a Tailscale/SSH tunnel.
- **Best browser-only path:** Apache Guacamole through Tailscale Serve when you need authentication, connection inventory, and multiple bots; noVNC through Serve when minimalism matters more.
- **Best whole-desktop cross-platform path:** RustDesk direct-IP over tailnet, with its public rendezvous/relay path disabled/not used and tailnet grants restricting access.
- **Best high-frame-rate path:** Sunshine/Moonlight, only if its GPU/display complexity is justified.

Do not expose both native VNC and browser viewer merely for convenience. Select one ingress and firewall the rest.

---

## 5. Service supervision

### 5.1 Unit topology

Use a template target per bot:

```text
hermes-browser@BOT.target
+-- display@BOT.service       (Xvfb/Xorg/Xpra desktop/Xvnc)
+-- browser@BOT.service       (Chrome or Camofox client/server component)
+-- viewer@BOT.service        (Xpra/VNC/websockify/Guacamole connector)
+-- lease@BOT.service         (optional lock API/daemon)
`-- hermes-gateway@BOT.service / Hermes profile gateway
```

Keep the browser and profile durable state outside `/run`; put only PID files, sockets, and leases in runtime directories. systemd's `StateDirectory=` persists across stops, while `RuntimeDirectory=` is normally removed on stop/reboot. [S3]

Recommended system-service properties (adapt to packaged binaries and distro):

```ini
[Unit]
Description=Per-bot browser for %i
Requires=display@%i.service
After=display@%i.service network-online.target tailscaled.service
PartOf=hermes-browser@%i.target

[Service]
Type=exec
User=bot-%i
Group=bot-%i
Environment=DISPLAY=:<allocated-by-instance>
ExecStartPre=/usr/local/libexec/check-browser-profile-unowned %i
ExecStart=/usr/bin/google-chrome \
  --user-data-dir=/var/lib/hermes-browsers/%i/chrome \
  --remote-debugging-port=<unique-loopback-port> \
  --no-first-run --no-default-browser-check
ExecStartPost=/usr/local/libexec/wait-cdp-ready %i
ExecStop=/usr/local/libexec/graceful-browser-stop %i
Restart=on-failure
RestartSec=5s
TimeoutStartSec=60s
TimeoutStopSec=45s
RuntimeDirectory=hermes-browsers/%i
StateDirectory=hermes-browsers/%i
UMask=0077
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/hermes-browsers/%i

[Install]
WantedBy=hermes-browser@%i.target
```

This is an architecture template, not a drop-in universal unit. Chrome's sandbox must remain enabled; do not add `--no-sandbox`. Sandboxing options must be tested because browsers legitimately need namespaces, shared memory, font/config paths, D-Bus, GPU devices, and sometimes downloads. systemd notes that some filesystem namespacing hardening is unavailable to unprivileged user services unless combined with suitable user namespaces. [S3]

### 5.2 Readiness and restart semantics

- `Type=simple` declares startup too early. `Type=exec` at least confirms `execve`; `Type=notify` is best only when a wrapper correctly sends `READY=1` after the display/CDP/viewer health checks pass. [S1]
- An `ExecStartPost=` readiness probe participates in startup ordering; fail the unit if the endpoint/display never becomes ready. [S1]
- Use `Restart=on-failure`, not blind `always`, so a clean administrative stop remains stopped. systemd defines `on-failure` to restart for non-zero exits, signals, timeouts, and watchdog failures. [S1]
- Add start-rate limiting to avoid restart storms on profile corruption or a bad launch flag.
- Graceful stop must drain automation, close the browser, wait for its process and profile lock to disappear, then stop the display.
- Do not use shell backgrounding/nohup inside `ExecStart`; let systemd own the foreground process/cgroup.
- Use the journal and structured health output; alert on repeated restarts, failed readiness, stale leases, and disk pressure.

### 5.3 System vs user services

A system service with a dedicated unprivileged `User=bot-X` is simplest for boot-time servers and permits stronger systemd sandboxing. A user service is acceptable, but enable linger:

```sh
sudo loginctl enable-linger bot-X
```

Official `loginctl` documentation says lingering starts the user's service manager at boot and keeps it after logout, allowing long-running services without an active login. [S2]

Do not mistake a lingering systemd user manager for a graphical login session. The display still needs an explicitly supervised Xvfb/Xorg/Xvnc/Xpra service and correct `DISPLAY`, runtime directory, D-Bus, and permissions.

### 5.4 Camofox supervision

If using the Camofox Docker/server pattern:

- persist the actual Camofox/Firefox profile volume;
- bind REST, VNC, and noVNC to loopback/private network only;
- give each bot a unique stable Hermes-derived `userId` and do not share it;
- verify server version semantics: stable `userId` must reopen the same profile after server and host restart;
- supervise the Camofox server independently from Hermes so Hermes restarts do not destroy browser state;
- ensure cleanup is soft for managed/external identities;
- use one control lease per `userId`.

---

## 6. Tailscale and host firewall posture

1. Install Tailscale on server and operator devices; do not forward router/cloud ports for CDP or remote desktop.
2. Tag the server, for example `tag:hermes-browser-host`, and use tailnet grants to authorize only the operator/group to exact viewer destinations/ports. Tailscale grants consist of source, destination, and permitted IP/port capability. [T3]
3. Prefer loopback-only viewer backends plus either:
   - Tailscale Serve for browser-based HTTPS; or
   - an SSH/Tailscale/native-client tunnel.
4. Never enable Funnel for this service. Serve is tailnet-only; Funnel is public. [T1]
5. Keep a host firewall that drops viewer/CDP ports on public/LAN interfaces even if cloud security groups are misconfigured.
6. Prove the binding with `ss -lntup`, not only configuration files.
7. Restrict Tailscale SSH independently; viewer access should not automatically grant a shell.
8. Log tailnet policy changes and device enrollment; revoke lost operator devices promptly.
9. Avoid exposing viewer services directly on the tailnet if Serve/tunnel can proxy a loopback listener. Defense in depth matters because a viewer controls authenticated browser sessions.

Example policy intent (syntax must be validated against the current tailnet policy schema before deployment):

```text
operator group/device -> tag:hermes-browser-host:<viewer-port> only
all other tailnet principals -> denied
any principal -> CDP ports denied
public/LAN interfaces -> viewer and CDP ports denied by host firewall
```

---

## 7. Backup, recovery, and secret treatment

Browser profiles contain cookies, saved credentials, local storage, and encryption material; treat them as credential vaults.

- Separate backup units: Hermes profile, browser profile, work artifacts, service/network config, and secret-injection metadata.
- Quiesce automation and cleanly stop the browser before file-level backup. Verify no process owns the profile and singleton lock/socket is gone.
- If using storage snapshots while live, prove application consistency through restoration tests; do not assume crash consistency equals valid browser databases.
- Encrypt backups and restrict restore operators.
- Do not copy an everyday personal Chrome profile to the server. Provision server-side service identities in dedicated profiles.
- Restore to an isolated host/temporary tailnet tag first; never test a restore by racing the production profile.
- Pin browser/Camofox versions deliberately and test upgrades against login persistence, fingerprint expectations, and site behavior.

---

## 8. Acceptance tests

A deployment is not accepted until every applicable test has captured command output, timestamps, and failure evidence.

### A. Process and reboot durability

1. Enable all per-bot target units; reboot the server.
2. Verify display, browser, viewer, lease service, and Hermes gateway are active without an interactive login.
3. For user services, verify `loginctl show-user BOT --property=Linger` reports enabled.
4. Check journal for restart loops and readiness timeouts.
5. Verify the browser PID is a non-root per-bot identity and Chrome sandboxing has not been disabled.

Pass: all services recover after reboot/logout; readiness waits for a usable browser rather than mere process existence.

### B. Browser identity persistence

For each bot:

1. Log into a dedicated test site/account and set cookie/localStorage marker values.
2. Record `chrome://version` profile path (Chrome) or the server-side Camofox profile mapping.
3. Cleanly restart browser service; verify session and markers persist.
4. Restart Hermes only; verify identity persists.
5. Reboot host; verify identity persists.
6. Confirm another bot cannot see the marker/session.
7. For Camofox, separately test cookie continuity and fingerprint continuity; do not conflate them.

Pass: intended identity survives all lifecycle events and is absent from every other bot.

### C. Profile ownership and locks

1. While bot A browser is running, attempt a second launch against A's same user-data dir.
2. Confirm orchestration refuses before launch or Chrome/Firefox singleton enforcement fails safely.
3. Start bot B with a different profile concurrently; confirm both remain healthy.
4. Kill browser A ungracefully; verify lease becomes `RECOVERING`, stale PID state is detected, profile integrity checks run, and only then can one replacement start.
5. Run backup while active and verify policy blocks it or uses the approved snapshot path.

Pass: never two owners for one profile; crashes do not produce silent duplicate writers.

### D. Human takeover

1. Start an automation task that performs several visible steps.
2. Request takeover; confirm state moves to `DRAINING`, no new browser work starts, and active operation reaches a defined boundary.
3. Attach through the private viewer and perform mouse/keyboard actions.
4. Confirm the agent cannot inject input or navigate while state is `HUMAN`.
5. Disconnect unexpectedly; confirm lease timeout/recovery policy does not immediately race the operator.
6. Release normally; verify reconciliation captures tabs/URL/dialogs and automation resumes only after `RECOVERING` passes.
7. Repeat with MFA/login dialog and with a modal browser prompt.

Pass: no simultaneous control, clean handoff and hand-back, complete audit trail.

### E. Network non-exposure

1. On server, inspect listeners. CDP and raw VNC must be loopback-only unless a documented Tailscale-only exception exists.
2. From an unauthorized tailnet device, attempt viewer and CDP access; both fail.
3. From the authorized operator device, viewer succeeds and CDP remains inaccessible.
4. From LAN and public vantage points, scan viewer/CDP ports; all fail.
5. Verify no Tailscale Funnel configuration exists for the service.
6. If using Serve, verify its URL works only inside tailnet and tailnet grants deny non-operators.
7. Temporarily stop Tailscale; confirm no fallback public/LAN route remains.

Pass: pixels/input are privately reachable only by operator; CDP is server-local only.

### F. Viewer-specific behavior

- Resize and high-DPI behavior.
- Keyboard modifiers, clipboard policy, mouse capture, and non-US layout if applicable.
- Multiple viewer connection behavior: second viewer denied or read-only; never uncontrolled shared input.
- Viewer reconnect while browser remains running.
- Browser remains alive when viewer disconnects.
- For Guacamole/noVNC, WebSocket reconnect and proxy timeout behavior.
- For Sunshine/RustDesk, private direct path, pairing/password rotation, and no public relay dependency.

### G. Resource/concurrency limits

1. Measure baseline and loaded RAM/CPU/file descriptors per Chrome and Camofox bot.
2. Run the intended maximum bot count plus one; verify admission control rejects the excess cleanly.
3. Open the maximum tested tabs/pages per bot and exercise representative sites.
4. Simulate low disk, full inode table, memory pressure, and viewer disconnect.
5. Confirm one bot's crash or OOM does not kill/corrupt other identities.

Pass: defined capacity, deterministic rejection, no cross-bot failure propagation.

### H. Backup/restore

1. Quiesce and back up one Hermes profile and browser identity.
2. Restore to an isolated test user/host with changed CDP/viewer ports.
3. Start exactly one browser owner.
4. Verify marker/session continuity, Hermes profile separation, and viewer takeover.
5. Revoke restored production credentials after the test if the restore contained live cookies.

Pass: a real restore works; configuration-only backup is insufficient.

### I. Upgrade/rollback

1. Record Hermes, Chrome/Chromium, Playwright/agent-browser, Camofox/Camoufox, viewer, Tailscale, and systemd versions.
2. Upgrade one canary bot.
3. Re-run identity, lock, takeover, and non-exposure tests.
4. Verify rollback restores both binaries and compatible profile data, or document one-way migrations.

Pass: tested canary and rollback before fleet rollout.

---

## 9. Decision summary

Choose **dedicated Chrome + CDP + per-bot Xpra/TigerVNC display** when broad web compatibility and Hermes's strongest browser tooling matter. It is the clearest self-hosted architecture, provided CDP remains loopback-only and process/control locks are explicit.

Choose **Camofox managed persistence** when anti-detection/fingerprint behavior is more important than CDP/Browser Use CLI features. Prove that the Camofox server—not merely Hermes—persists each stable `userId`, and serialize all clients.

Choose **Xpra native over Tailscale SSH** for the least web-facing takeover surface; **TigerVNC via a private tunnel** for simplicity; **Guacamole via Tailscale Serve** for a richer browser-only gateway; **noVNC via Serve** for a minimal browser-only viewer; **RustDesk direct-IP over Tailscale** for a full desktop native client; and **Sunshine/Moonlight** only when streaming quality warrants additional complexity.

Do not use:

- one shared CDP browser for bots that require separate identities;
- multiple browser processes against one user-data dir;
- Chrome's default personal profile;
- public VNC/noVNC/CDP;
- Tailscale Funnel;
- `--no-sandbox` as a deployment shortcut;
- “headed” as evidence of persistence;
- multiple CDP clients/tabs as evidence of ownership safety;
- backup success without an isolated restore.

---

## Primary sources

### Hermes Agent (authoritative for Hermes behavior)

- **[H1]** Browser feature guide and backend matrix: https://hermes-agent.nousresearch.com/docs/user-guide/features/browser ; source snapshot: https://github.com/NousResearch/hermes-agent/blob/6dcebea7fc5d0cc4f621eeaddf52b7d877a5f882/website/docs/user-guide/features/browser.md
- **[H2]** Browser Use CLI integration, Camofox fallback, named session behavior: https://github.com/NousResearch/hermes-agent/blob/6dcebea7fc5d0cc4f621eeaddf52b7d877a5f882/tools/browser_use_cli.py
- **[H3]** `/browser connect`, dedicated debug profiles, real-profile snapshot implementation: https://github.com/NousResearch/hermes-agent/blob/6dcebea7fc5d0cc4f621eeaddf52b7d877a5f882/hermes_cli/browser_connect.py
- **[H4]** Camofox configuration, persistence, VNC, and adoption docs: https://github.com/NousResearch/hermes-agent/blob/6dcebea7fc5d0cc4f621eeaddf52b7d877a5f882/website/docs/user-guide/features/browser.md#camofox-self-hosted
- **[H5]** Camofox runtime and state derivation: https://github.com/NousResearch/hermes-agent/blob/6dcebea7fc5d0cc4f621eeaddf52b7d877a5f882/tools/browser_camofox.py and https://github.com/NousResearch/hermes-agent/blob/6dcebea7fc5d0cc4f621eeaddf52b7d877a5f882/tools/browser_camofox_state.py
- **[H6]** Browser lifecycle/session cache/cleanup: https://github.com/NousResearch/hermes-agent/blob/6dcebea7fc5d0cc4f621eeaddf52b7d877a5f882/tools/browser_tool.py
- **[H7]** Hermes profiles and isolation caveats: https://hermes-agent.nousresearch.com/docs/user-guide/profiles/ ; source snapshot: https://github.com/NousResearch/hermes-agent/blob/6dcebea7fc5d0cc4f621eeaddf52b7d877a5f882/website/docs/user-guide/profiles.md
- **[H8]** Provider resolution/CDP precedence: https://github.com/NousResearch/hermes-agent/blob/6dcebea7fc5d0cc4f621eeaddf52b7d877a5f882/tools/browser_tool.py#L828-L938
- **[H9]** Local session and command construction: https://github.com/NousResearch/hermes-agent/blob/6dcebea7fc5d0cc4f621eeaddf52b7d877a5f882/tools/browser_tool.py#L2693-L2734 and https://github.com/NousResearch/hermes-agent/blob/6dcebea7fc5d0cc4f621eeaddf52b7d877a5f882/tools/browser_tool.py#L3483-L3504
- **[H10]** Camofox limitations in Hermes: https://github.com/NousResearch/hermes-agent/blob/6dcebea7fc5d0cc4f621eeaddf52b7d877a5f882/website/docs/user-guide/features/browser.md#L669-L724
- **[H11]** Hermes cloud provider implementations: https://github.com/NousResearch/hermes-agent/tree/6dcebea7fc5d0cc4f621eeaddf52b7d877a5f882/plugins/browser

### Chrome / Chromium / DevTools

- **[C1]** Chromium user-data directory documentation, defaults, multiple-instance/X-display constraints: https://chromium.googlesource.com/chromium/src/+/main/docs/user_data_dir.md
- **[C2]** Chrome 136 remote-debugging changes and cookie-theft rationale: https://developer.chrome.com/blog/remote-debugging-port
- **[C3]** Chrome DevTools Protocol and multi-client FAQ: https://chromedevtools.github.io/devtools-protocol/
- **[C4]** Chromium `ProcessSingleton`: https://chromium.googlesource.com/chromium/src/+/main/chrome/browser/process_singleton.h and https://chromium.googlesource.com/chromium/src/+/main/chrome/browser/process_singleton_posix.cc
- **[C5]** Chromium remote-debugging listener source: https://chromium.googlesource.com/chromium/src/+/main/chrome/browser/devtools/remote_debugging_server.cc and https://chromium.googlesource.com/chromium/src/+/main/headless/lib/browser/headless_devtools.cc
- **[C6]** Chrome headless mode: https://developer.chrome.com/docs/chromium/headless and https://chromium.googlesource.com/chromium/src/+/main/headless/README.md

### Playwright / Camoufox

- **[P1]** Playwright persistent context API and user-data-dir restrictions: https://playwright.dev/docs/api/class-browsertype#browser-type-launch-persistent-context
- **[P2]** Playwright CDP attachment limitations: https://playwright.dev/docs/api/class-browsertype#browser-type-connect-over-cdp
- **[P3]** Headed Linux/Xvfb and remote-desktop guidance: https://playwright.dev/docs/ci#running-headed and https://playwright.dev/docs/docker#using-with-remote-desktop
- **[CF1]** Camoufox usage, persistent context, and virtual display: https://camoufox.com/python/usage/ and https://camoufox.com/python/virtual-display/
- **[CF2]** Camoufox experimental remote server: https://camoufox.com/python/remote-server/
- Official Camoufox source showing Firefox persistent-context launch: https://github.com/daijro/camoufox/blob/4edbcffdd3a8690b3ef66f30c282aaf804a14908/pythonlib/camoufox/sync_api.py

### systemd

- **[S1]** Service startup/readiness/restart semantics: https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html
- **[S2]** User lingering: https://www.freedesktop.org/software/systemd/man/latest/loginctl.html
- **[S3]** Execution sandboxing and runtime/state directories: https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html
- Unit dependency semantics: https://www.freedesktop.org/software/systemd/man/latest/systemd.unit.html

### Tailscale

- **[T1]** Tailscale Serve (tailnet-only) and distinction from Funnel: https://tailscale.com/docs/features/tailscale-serve
- **[T2]** Serve examples, loopback backends, access-control application: https://tailscale.com/docs/reference/examples/serve
- **[T3]** Tailnet grants: https://tailscale.com/docs/features/access-control/grants
- Tailnet privacy concept: https://tailscale.com/kb/1136/tailnet

### Remote desktop/viewer options

- **[V1]** TigerVNC official systemd HOWTO, `localhost`, per-display mapping, and limitations: https://github.com/TigerVNC/tigervnc/blob/master/unix/vncserver/HOWTO.md
- **[N1]** noVNC official repository: https://github.com/novnc/noVNC
- **[N2]** websockify official README and encrypted WebSocket support: https://github.com/novnc/websockify/blob/master/README.md ; noVNC advanced VNC/x11vnc notes: https://github.com/novnc/noVNC/wiki/Advanced-usage
- **[X1]** Xpra overview/persistent display: https://xpra.org/index.html and https://xpra.org/manual
- **[X2]** Xpra SSH transport and shadow mode: https://github.com/Xpra-org/xpra/blob/master/docs/Network/SSH.md and https://xpra-org.github.io/xpra/Usage/Shadow.html
- **[G1]** Apache Guacamole architecture: https://guacamole.apache.org/doc/gug/guacamole-architecture.html
- **[G2]** Guacamole VNC configuration: https://guacamole.apache.org/doc/gug/configuring-guacamole.html#vnc
- **[G3]** Guacamole reverse proxy/SSL guidance: https://guacamole.apache.org/doc/gug/reverse-proxy.html
- **[R1]** Tailscale's official RustDesk direct-IP guide: https://tailscale.com/docs/solutions/access-remote-desktops-with-rustdesk
- **[R2]** RustDesk official documentation: https://rustdesk.com/docs/en/
- **[SU1]** Sunshine overview: https://docs.lizardbyte.dev/projects/sunshine/latest/
- **[SU2]** Sunshine Linux setup/services/headless notes: https://docs.lizardbyte.dev/projects/sunshine/latest/md_docs_2getting__started.html
- **[W1]** Waypipe official project/README: https://gitlab.freedesktop.org/mstoeckl/waypipe and https://gitlab.freedesktop.org/mstoeckl/waypipe/-/blob/master/README.md

## Research limitations

- Hermes evolves rapidly; the official live Hermes docs remain authoritative over this snapshot. The pinned source links make the reviewed implementation auditable.
- Camofox/Camoufox server persistence semantics vary by deployed server/version. Hermes's stable `userId` is necessary but not sufficient; test the server's actual profile mapping.
- Neither Chrome nor Camoufox publishes a universal safe fleet concurrency number. Capacity must be measured on the target host and representative sites.
- Waypipe's official GitLab pages were bot-challenge protected during retrieval; only high-level official project metadata was relied upon here.
- Example systemd and tailnet policy fragments are architecture templates and must be adapted and validated against the target distribution, browser package, and current Tailscale policy schema.
