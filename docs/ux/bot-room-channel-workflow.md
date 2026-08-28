# Bot, Room, and Channel operator workflow

Status: issue #8 UX recommendation. The prototype in `prototypes/bot-room-channel-workflow/` is deliberately throwaway: it has no backend, persistence, authentication, or production control authority. Its in-memory simulations must not be reused as fleet implementation code.

## Recommended operator workflow

1. **Create an independently owned Bot.** Choose a unique lowercase profile identity, role, runtime, model, profile seed, memory mode, persona, capabilities, skill, opaque credential handles, and first routine. The owner segment of every `secret://<owner>/…` handle must exactly match the Bot/profile name; the builder updates its generated default as the name changes, but preserves an operator-overridden value so validation can reject accidental cross-Bot ownership. The resulting Bot projection and canonical chat metadata retain these non-secret setup choices; credential material remains an opaque broker handle only. Creation also projects the Bot into Room membership, mention, Channel owner, and routine controls. Review authority before creation. A server Bot receives a separate OS/container boundary and, when selected, a dedicated persistent Browser Profile initially in `RECOVERING`. A Laptop Runtime Bot is intermittent, creates no server Browser Profile, pauses while the Mac is unavailable, and requires Mac-local single-use approval for mutations. A Hermes profile separates application state; it is not an OS security boundary.
2. **Open its canonical Bot Chat.** Use the persistent, attributed Bot conversation as the Bot's home. A direct message or delegation can route work to another Bot, but the target executes only with its own credentials, capabilities, runtime availability, and approval policy. Messages never grant authority.
3. **Assemble a Bot Room.** Add only the Bots needed for the task and use `@mentions` to scope dispatch. An unmentioned message may invite each member to reply or pass. Route serially with bounded rounds to prevent loops. Offline and non-member Bots are not dispatched. The shared transcript records attribution; it does not merge profiles or credentials.
4. **Map external Channels separately.** Telegram is a transport, not a Bot Room and not the canonical Bot Chat session. Map an allowlisted destination to one owning profile gateway. Changing the owner must derive the Bot-bound channel handle (`secret://<owner>/telegram/gateway`); reject any mismatched handle rather than allowing credentials to cross Bots. Require strict numeric Telegram user and chat IDs plus explicitly paired and approved admission state before saving. Store those numeric IDs, admission state, and owning Bot as authority; a friendly sender alias is display-only and must never authorize access. Do not expose a public inbound listener.
5. **Operate from explicit state.** Inspect Bot/runtime health, routine owner and result, Mac reachability, and Browser Takeover state before retrying. Mac reconnect restores reachability but does not pre-approve queued mutations. A failed routine remains failed when its provider is unavailable; do not silently fall back to a different provider/model.
6. **Take over a browser safely.** Follow only `AUTOMATION → DRAINING → HUMAN → RECOVERING → AUTOMATION`. Drain automation before issuing a single-use, Bot-bound takeover; releasing human control always enters recovery. Revoke takeover access, close VNC/CDP clients, verify profile health, rotate the lease, and pass a harmless probe before automation resumes. Uncertainty fails closed to `RECOVERING`.

The recommended default presentation is **A · Guided** for setup and occasional operators. **B · Canvas** presents the same state as a spatial planning surface. **C · Console** is a dense operations presentation. These are visual alternatives over one interaction model, selected with `?variant=guided`, `?variant=canvas`, or `?variant=console`.

## Native Hermes and fleet-built boundary

| Concern | Boundary |
|---|---|
| Hermes profile identity, instructions/persona, memory, sessions, skills, tools, model/provider configuration | Native Hermes primitives; fleet validates and provisions an independently owned instance/configuration. |
| Canonical Bot Chat and attributed Bot Room transcript/mentions | Native Hermes/Desktop interaction primitives; fleet supplies cross-runtime discovery, reachability, bounded routing policy, and status. |
| Routines | Native Hermes cron/gateway execution; fleet aggregates owner, schedule, health, and results without becoming a second scheduler. Exactly one gateway owns messaging polling and the cron ticker per profile. |
| Telegram adapter and polling | Native Hermes gateway transport; fleet-built mapping selects the owning Bot and enforces deployment policy around pairing, allowlists, credentials, and no public listener. Platform sessions remain separate from canonical Bot Chat. |
| Server OS identities, rootless containers, per-Bot mounts/networks, private reverse proxy, and supervision | Fleet-built infrastructure. Hermes profile separation alone is not security isolation. |
| Laptop discovery/reconnect and Mac-local mutation approval | Fleet-built coordination around the native Laptop Runtime. Reconnect is availability, not authorization. |
| Persistent server Browser Profile container, automation lease, takeover grant/proxy, and fail-closed state machine | Fleet-built boundary around browser automation. Raw CDP/VNC must never be publicly exposed. |
| Unified roster, state rail, activity feed, and cross-runtime health | Fleet-built operator projection derived from authoritative runtime state. The prototype currently simulates it in memory only. |
| Credential values and grants | External secret broker/runtime policy. The UI accepts and displays opaque `secret://` handles only; neither chat nor fleet metadata contains secret values. |

## Prototype acceptance check

From the repository root, run:

```sh
prototypes/bot-room-channel-workflow/test.sh
```

The headless Playwright check opens all three variants and exercises validation and creation (including default credential derivation, cross-Bot owner mismatch rejection, corrected creation, and changed memory/capability persistence), created-Bot projection into generic Room membership and `@mention`, Telegram owner, and routine inspection controls, runtime implications, canonical chat/delegation, offline Room routing followed by Mac reconnect eligibility, the preserved `laptop-worker` Room path, rejected nonnumeric/unpaired/cross-Bot Telegram mappings, accepted numeric allowlist/pairing/created-owner state with a derived owner credential, fixture and created-routine inspection, the complete browser ownership cycle, state/activity projection, and browser console/page errors. Playwright is a test-only local dependency; this prototype intentionally adds no production package or server.
