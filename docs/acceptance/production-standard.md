# Production acceptance and recovery standard

Status: **Normative release standard; execution is deferred to the full-suite ticket**
Decision scope: [Define the production acceptance and recovery standard](https://github.com/JohanSardar/hermes-bot-fleet/issues/9)
Locked inputs: [production topology](../architecture/production-topology.md), [approval/audit/secrets policy](../security/approval-audit-secrets-policy.md), and [Bot/Room/Channel workflow](../ux/bot-room-channel-workflow.md)

## 1. Authority and scope

This document defines the binary production release contract. `acceptance/production-requirements.json` is the canonical machine-readable requirement catalog. Prose explains how to execute and judge that catalog; it does not waive, replace, reorder, or weaken a catalog item. If prose and catalog differ, release is blocked until both are corrected against the locked decisions.

The catalog's top-level `locked_source_crosswalk` is normative. Its key set is exactly the locked security-policy matrix case set, and each source case maps to a nonempty list of one or more unique canonical `PSC-*` requirements. A case is split when live configuration inspection and destructive disposable verification require different targets; `AUD-04` and `AUD-05` each map to exactly one live inspection and one disposable fixture requirement. Removing, combining across source cases, or silently renaming a source case is catalog drift and blocks release.

This ticket defines tests and hooks; it does not claim that the production fleet or live tests exist. `acceptance/hooks/run-requirement` is an exact future hook interface for the execution ticket. A hook that is absent, unimplemented, or unable to run returns `BLOCKED`, which fails release. Prototype, mock, CI-only, documentation, or prior-ticket evidence cannot substitute for evidence from the declared target.

The production outcome includes the Server Runtime, `chief`, `test-worker`, the native `laptop-worker`, Hermes Desktop, Bot Rooms, Telegram, routines, persistent headed Browser Profiles and Browser Takeover, Azure/Tailscale, encrypted backup/restore, monitoring, the additional-Bot runbook, and honest unsupported-gap reporting. A Hermes profile is semantic isolation; Unix identities, rootless containers, mounts, networks, policy gates, and host controls are the security boundaries.

## 2. Binary release gates and result semantics

Every catalog requirement is `mandatory=true`. A result object has one terminal status:

- `PASS`: the declared hook ran against the declared target after all prerequisites passed; every pass criterion is proved by current, valid, sanitized evidence; cleanup and required rollback checks passed.
- `FAIL`: the hook ran and any criterion, threshold, evidence rule, safety assertion, cleanup, or rollback assertion failed.
- `BLOCKED`: the hook could not make a valid judgment because a prerequisite, implementation, credential broker, target, approval, fixture, observer, or evidence sink was unavailable or unsafe.
- `SKIPPED`: the hook was not run or was intentionally omitted.

The sole binary release calculation is:

```text
production_ready = PASS
  only if every catalog requirement has exactly one current PASS result
  and the evidence bundle itself passes validation;
otherwise production_ready = FAIL.
```

`BLOCKED` and `SKIPPED` are diagnostic statuses, never waivers. Because every requirement is mandatory, either status makes the release `FAIL`. “Not applicable,” “expected failure,” flaky-test retry exhaustion, operator judgment without artifacts, and unsupported implementation are not alternate success states. An unsupported requested capability passes only the explicit gap-honesty requirements when the capability is accurately disabled and documented; it does not pass a functional requirement for that capability.

A release result is valid only for the exact repository revision, manifest digest, image/package versions, Azure inventory, policy revision, and target identities in its evidence manifest. A change to any security boundary, pinned Hermes/Desktop/browser version, network exposure, storage/backup policy, credential scope, scheduler ownership, or test implementation invalidates that result and all transitively affected results.

## 3. Target classes and fixture rules

Each requirement declares exactly one environment class.

### Clean environment

A fresh, isolated host/resource namespace with no inherited profile, database, browser directory, token, container volume, network, cache, or credential. It is mandatory for reproducible bootstrap, isolated restore, and additional-Bot creation/retirement. Secrets are provisioned by the human/admin authority through the broker and never copied from production or exposed to the runner. “Clean” must be proved by before-inventory, not asserted.

### Live production

The actual provisioned fleet. Only read-only inspection, non-destructive negative probes, explicitly safe end-to-end messages/turns, and the bounded test-owned state in `GAT-002` are allowed. `GAT-002` runs only while production activation is false: it writes one test-owned session marker, memory marker, and cron tick per exact deployed profile, performs a controlled gateway/serve restart, reconciles commits, checks DB/WAL integrity, and removes every marker; unrelated state must remain digest-identical. A live requirement may not reboot, kill, corrupt, race, delete, restore over, or mutate non-test production data merely because its catalog flag is false. The sole destructive exception is `SVC-005`: exactly one reboot of the actual provisioned Azure VM during the approved pre-activation execution window, while production activation is still false, with Azure resource-ID/Activity Log evidence binding the tested VM to the live inventory. Every other live destructive test is invalid and `BLOCKED` until moved to a disposable fixture without weakening the assertion.

### Disposable fixture

A bounded, separately named, non-production resource/data/account fixture whose owner, maximum effects, cleanup, and rollback are recorded before injection. Destructive requirements run only here (except the specifically approved VM reboot acceptance against the not-yet-enabled fleet during the execution window). Browser logins use disposable accounts and non-production data. Telegram denial/routing tests use approved test identities and chats. Mac tests use files created solely for the test under an approved root and still require every Mac-local single-use approval mandated by policy. No fixture may contain or clone a production credential, Browser Profile, personal file, or production Bot state.

Before a destructive hook starts, it must verify target identity, prerequisite PASS results, current backup/rollback point, blast radius, approval where required, monitoring readiness, and cleanup plan. A mismatch is `BLOCKED`, causes no injection, and fails release. Cleanup failure is `FAIL` even if the primary assertion passed.

## 4. Evidence contract

Each execution creates `evidence/<run_id>/` and a canonical manifest. Every requirement result records:

- requirement ID and catalog digest;
- status, UTC start/end, measured duration, target class and non-secret target digest;
- repository, policy, manifest, package/image, Hermes/Desktop/browser, and runner revisions;
- prerequisite result digests;
- exact hook and sanitized argument digest;
- declared artifact paths, SHA-256 digests, artifact media types, collection source, and collector identity;
- a nonempty `assertions` array for every hook; every row has exactly `{assertion_id, observed_field, operator, expected, actual, source_artifact, passed}`, `operator` is one of `eq`, `ne`, `lt`, `lte`, `gt`, `gte`, `in`, `not_in`, `contains`, `not_contains`, `matches`, or `exists`, and `source_artifact` is a declared artifact path;
- each pass criterion with exact observed field, typed comparator/operator, expected value or threshold, actual value, pass Boolean, and artifact reference;
- fixture identifier, approved blast radius, pre/post state digests, cleanup result, and rollback result when applicable;
- sanitized audit/event correlation IDs and operator/approver identity digest where required;
- terminal status and a safe reason code.

Evidence must be generated by the authoritative plane: Azure API/effective rules plus an external probe for Azure exposure; host/container inspection plus remote probes for listeners; provider/platform receipt plus gateway/audit correlation for Telegram; DB integrity and observed messages for concurrency; lease supervisor state plus independent socket/input probes for takeover; broker/gate/audit records plus file digests for Mac mutations; storage configuration, manifests, checksums, and restored service behavior for backup/restore. Screenshots alone, copied terminal text, self-reported Bot statements, documentation, mocks, or a single-plane assertion are insufficient.

Time thresholds use monotonic measurement at the observer where possible, with synchronized UTC timestamps for correlation. A threshold passes only when the measured upper bound is less than or equal to the configured maximum. Missing start/end events, clock uncertainty that prevents proof, or a measurement rounded below a threshold is `FAIL`.

### Redaction and secret safety

Evidence contains no credential value, password, private key, token, cookie, authorization header, MFA material, secret-bearing environment/argv, browser storage/content, message/prompt body, personal file content, takeover credential/URL, or credential-bearing URL. It uses opaque credential handles, one-way digests, safe aliases, counts, reason codes, and redacted structured fields. Numeric platform/account/resource identifiers are secret-risk data: store only where operationally required in the encrypted bundle and use digests in reports.

Collectors apply typed omission first, known-secret/canary fingerprint rejection, header/URL parsing, conservative token-pattern redaction, and size limiting. Redaction is defense in depth, not permission to collect a secret. A secret-shaped or known-canary value causes payload suppression, evidence quarantine, credential rotation where exposure is possible, a safe incident record, and release `FAIL`. It must never be copied into an issue, Git, alert, model context, fallback log, or test failure output.

### Integrity and retention

The final evidence manifest is canonical JSON, references every catalog ID exactly once, and binds every artifact by SHA-256. It is signed/checkpointed by the approved evidence/audit authority and stored encrypted at rest and in transit in private Bot/run-scoped storage. Public access is disabled. Collector writes are create-only; operator reads and exports follow the locked approval policy.

Release evidence and associated audit correlation are retained encrypted for **400 days**, without secrets. Production configuration must enforce the real 400-day immutable period; accelerated retention may be used only in an additional disposable lifecycle fixture and never as evidence of production configuration. Evidence whose digest, signature, chain, key custody, archive object, or retention configuration cannot be verified is invalid and turns its requirement into `FAIL`.

## 5. Exact objectives and defaults

These values are release limits, not suggestions:

| Objective | Required maximum |
|---|---:|
| Gateway, serve, proxy, and safely recoverable component process recovery | 120 seconds |
| Azure VM reboot to complete fleet health | 10 minutes (600 seconds) |
| Scheduled R1 configuration backup age / RPO | 24 hours |
| Browser-consistent encrypted snapshot age | 24 hours |
| Telegram alert delivery after detectable condition | 5 minutes (300 seconds) |
| Mac state to `laptop_unavailable` | 60 seconds |
| Mac reconnect discovery and ledger reconciliation | 5 minutes (300 seconds) |
| Browser ownership/takeover transition | 60 seconds per transition |
| Isolated R1/R2 restore RTO | 4 hours (14,400 seconds) |
| Encrypted, secret-free release evidence retention | 400 days |

The process objective does not authorize unsafe automatic recovery: uncertainty in browser ownership remains `RECOVERING`; uncertain side effects remain quarantined; a failed policy, broker, audit, or secret boundary stays fail-closed. Recovery may meet availability timing and still fail the requirement if isolation, integrity, attribution, deduplication, or safety is not proved.

## 6. Rollback, restore, and retry rules

Before any change or injection, identify the last known-good immutable manifest/image/configuration and applicable Bot-scoped restore point. Rollback is preferred only when the change is reversible and state integrity is proved. It must drain new work, stop both gateway and serve for profile-affecting maintenance, verify no DB/WAL descriptor remains, restore exact ownership/modes, validate checksums and DB health, then start gateway, pass its health check, and start serve. Browser state always resumes in `RECOVERING` and must revoke old takeover/automation credentials, close clients, validate profile health, reset a known window/tab, rotate the lease nonce, and pass a harmless probe before `AUTOMATION`.

Never clone, merge, or cross-restore a Bot profile, Browser Profile, credential namespace, backup prefix, or database. Never restore into production first to discover whether a backup works. The mandatory drill restores `test-worker` R1 and R2 into a clean isolated target while proving `chief` is not read, stopped, or changed, and completes within four hours. R3 secrets are re-established from their authority or remain protected inside approved whole-disk ciphertext; they are never exported into the runner. R4 transient state is not restored.

A partial or uncertain side effect is not blindly retried. Preserve the original idempotency key, inspect authoritative state, create a new exact manifest, obtain a fresh single-use approval where required, and record reconciliation. No “idempotent” exception permits grant replay. If rollback validation fails, keep the affected capability/Bot disabled and use isolated restore or human break-glass; do not perform speculative in-place repair. Break-glass cannot override permanent denies or make a failed release pass.

## 7. Complete execution order

Run from Johan's approved Mac using the pinned runner. The JSON `execution_order` array is the exact item-by-item order; prerequisites additionally enforce the DAG. Parallel execution is permitted only when prerequisite closure is complete, fixtures and targets are disjoint, observers can prove attribution, and evidence order remains deterministic. The default safe order is serial.

1. Repository/documentation preflight and clean bootstrap (`REP-*`).
2. Locked security-policy acceptance cases and source crosswalk (`PSC-*`, preserving `AUTH-*`, `MAC-*`, `BROW-*`, `SEC-*`, `AUD-*`, `FAIL-*`, `BG-01`, `ISO-01`, and `SCAN-01`); inspect live `AUD-04`/`AUD-05` controls separately from their destructive accelerated lifecycle/key fixtures.
3. Live Azure feasibility, cost, resource, encryption, NSG, diagnostics, and budget inspection (`AZR-*`).
4. Listener/firewall/Tailscale/private-access gates and bounded tailnet-loss fixture (`NET-*`).
5. Service inventory, disposable process/component recovery, the narrow actual-VM pre-activation reboot exception, and maintenance quiescence (`SVC-*`).
6. Gateway/scheduler ownership, safe-but-stateful live pre-activation exact-profile session/memory/cron writes plus controlled gateway/serve restart and cleanup, destructive equivalent fixture contention/restart, provider pin, and cron semantics (`GAT-*`).
7. Telegram inbound, outbound, admission, owner-routing, and retry assertions (`TEL-*`).
8. Bot configuration/state/skill/credential/workspace/Unix/container/cross-Bot isolation (`BOT-*`).
9. Desktop canonical chats, Rooms, mentions, and authority-preserving delegation (`DSK-*`).
10. Routine execution with clients closed and Mac awake/off (`RTN-*`).
11. Browser persistence, private visual access, raw CDP/VNC denial, takeover state/races/abandon/reboot, concurrency/leakage, and disposable login (`BRW-*`).
12. Native laptop-worker inventory, delegation/read/deny/path controls, approvals/mutations/races/offline/reconnect (`LAP-*`).
13. Encrypted backup freshness, snapshot consistency, Azure server-Bot (`chief` and `test-worker`) R1/R2 retention (7 daily/4 weekly/3 monthly), separate Mac-local R5 proof and Azure-count exclusion for `laptop-worker`, deletion authority, backup-principal boundary, isolated restore, browser recovery, and rollback (`BKP-*`).
14. Monitoring inventory, Telegram alert injections, and 400-day encrypted audit/evidence controls (`MON-*`).
15. Every bounded failure injection, including gateway, serve, browser, lease, proxy, provider, backup, audit/storage, broker/gate, Telegram, Mac, VM, Tailscale, takeover, DB/WAL contention, and corrupt restore point (`FIN-*`).
16. Additional disposable Bot creation and retirement through the runbook (`RUN-*`).
17. Capability parity, repository/documentation honesty, Grok/vendor-only gaps, and deferred File Bridge absence (`GAP-*`).
18. Post-cleanup whole-fleet health, evidence assembly, and binary decision (`HLT-*`).

On the first unsafe `FAIL`, stop dependent execution, execute the declared cleanup/rollback, and mark all unrun dependents `BLOCKED`; the release is `FAIL`. Safe independent diagnostics may continue to establish cause. After correction, create a new run ID and rerun the failed item plus every transitive dependent. Do not overwrite failed evidence.

## 8. Unsupported-gap honesty

Capability parity has only three labels: native and live-tested; implemented equivalent and live-tested; unsupported. A prototype, planned hook, Grok/vendor UI behavior, undocumented Hermes behavior, disabled File Bridge, or unexecuted workflow is unsupported. Each gap must state exact user impact, safe degraded behavior, source/version basis, owner and tracking issue, and the feature/control that remains disabled. There is no silent model/provider fallback, no public-access fallback, no broad Mac filesystem substitute, no simulated success, and no claim that profile separation is a security sandbox.

A functional gate cannot be waived by relabeling its failed behavior a gap. Conversely, an explicitly out-of-scope Grok-only behavior passes the honesty gate only when no production UI/runbook claims it and its absence cannot weaken a locked security/recovery outcome.

## 9. One-command catalog validation

From repository root:

```sh
tests/acceptance/run-production-catalog-validation.sh
```

This is a static standard/catalog validator, not the production suite. It proves schema shape, mandatory fields, stable unique IDs, exact document coverage, target classes, default thresholds, prerequisite validity/acyclicity/order, required categories and failure cases, exact one-or-more locked-case crosswalk coverage and `AUD-04`/`AUD-05` target composition, the sole `SVC-005` live destructive exception, the safe-stateful live/destructive-fixture concurrency split, Azure server-Bot retention plus laptop-worker R5 exclusion, the structured assertion-row contract, concrete artifact-bound comparator criteria, rejection of self-referential/vague umbrella criteria, absence of skip-allowed semantics/stale markers, and absence of secret-shaped values. A passing static validator does not claim any live deployment requirement has passed.

## 10. Canonical catalog index

Every canonical ID is listed below so prose/catalog drift is machine-detectable. Requirement text, hooks, evidence artifacts, criteria, and recovery behavior remain authoritative in the JSON catalog.

<!-- CATALOG_INDEX_START -->
| ID | Category | Declared target |
|---|---|---|
| `REP-001` | `repository` | `clean-environment` |
| `REP-002` | `repository` | `clean-environment` |
| `REP-003` | `repository` | `clean-environment` |
| `REP-004` | `repository` | `clean-environment` |
| `PSC-001` | `policy-security` | `disposable-fixture` |
| `PSC-002` | `policy-security` | `disposable-fixture` |
| `PSC-003` | `policy-security` | `disposable-fixture` |
| `PSC-004` | `policy-security` | `disposable-fixture` |
| `PSC-005` | `policy-security` | `disposable-fixture` |
| `PSC-006` | `policy-security` | `disposable-fixture` |
| `PSC-007` | `policy-security` | `disposable-fixture` |
| `PSC-008` | `policy-security` | `live-production` |
| `PSC-009` | `policy-security` | `disposable-fixture` |
| `PSC-010` | `policy-security` | `disposable-fixture` |
| `PSC-011` | `policy-security` | `disposable-fixture` |
| `PSC-012` | `policy-security` | `disposable-fixture` |
| `PSC-013` | `policy-security` | `disposable-fixture` |
| `PSC-014` | `policy-security` | `disposable-fixture` |
| `PSC-015` | `policy-security` | `disposable-fixture` |
| `PSC-016` | `policy-security` | `disposable-fixture` |
| `PSC-017` | `policy-security` | `disposable-fixture` |
| `PSC-018` | `policy-security` | `disposable-fixture` |
| `PSC-019` | `policy-security` | `disposable-fixture` |
| `PSC-020` | `policy-security` | `disposable-fixture` |
| `PSC-021` | `policy-security` | `disposable-fixture` |
| `PSC-022` | `policy-security` | `live-production` |
| `PSC-023` | `policy-security` | `live-production` |
| `PSC-029` | `policy-security` | `disposable-fixture` |
| `PSC-030` | `policy-security` | `disposable-fixture` |
| `PSC-024` | `policy-security` | `disposable-fixture` |
| `PSC-025` | `policy-security` | `disposable-fixture` |
| `PSC-026` | `policy-security` | `disposable-fixture` |
| `PSC-027` | `policy-security` | `disposable-fixture` |
| `PSC-028` | `policy-security` | `disposable-fixture` |
| `AZR-001` | `azure` | `live-production` |
| `AZR-002` | `azure` | `live-production` |
| `AZR-003` | `azure` | `live-production` |
| `AZR-004` | `azure` | `live-production` |
| `AZR-005` | `azure` | `live-production` |
| `AZR-006` | `azure` | `live-production` |
| `NET-001` | `network` | `live-production` |
| `NET-002` | `network` | `live-production` |
| `NET-003` | `network` | `live-production` |
| `NET-004` | `network` | `live-production` |
| `NET-005` | `network` | `disposable-fixture` |
| `SVC-001` | `services` | `live-production` |
| `SVC-002` | `services` | `disposable-fixture` |
| `SVC-003` | `services` | `disposable-fixture` |
| `SVC-004` | `services` | `disposable-fixture` |
| `SVC-005` | `services` | `live-production` |
| `SVC-006` | `services` | `disposable-fixture` |
| `GAT-001` | `gateway-scheduler` | `live-production` |
| `GAT-002` | `gateway-scheduler` | `live-production` |
| `GAT-005` | `gateway-scheduler` | `disposable-fixture` |
| `GAT-003` | `gateway-scheduler` | `live-production` |
| `GAT-004` | `gateway-scheduler` | `disposable-fixture` |
| `TEL-001` | `telegram` | `live-production` |
| `TEL-002` | `telegram` | `disposable-fixture` |
| `TEL-003` | `telegram` | `disposable-fixture` |
| `TEL-004` | `telegram` | `disposable-fixture` |
| `BOT-001` | `bot-isolation` | `live-production` |
| `BOT-002` | `bot-isolation` | `disposable-fixture` |
| `BOT-003` | `bot-isolation` | `disposable-fixture` |
| `BOT-004` | `bot-isolation` | `disposable-fixture` |
| `BOT-005` | `bot-isolation` | `live-production` |
| `BOT-006` | `bot-isolation` | `disposable-fixture` |
| `BOT-007` | `bot-isolation` | `disposable-fixture` |
| `BOT-008` | `bot-isolation` | `live-production` |
| `DSK-001` | `desktop-rooms` | `live-production` |
| `DSK-002` | `desktop-rooms` | `disposable-fixture` |
| `DSK-003` | `desktop-rooms` | `disposable-fixture` |
| `DSK-004` | `desktop-rooms` | `disposable-fixture` |
| `RTN-001` | `routines` | `disposable-fixture` |
| `RTN-002` | `routines` | `disposable-fixture` |
| `RTN-003` | `routines` | `disposable-fixture` |
| `BRW-001` | `browser` | `live-production` |
| `BRW-002` | `browser` | `disposable-fixture` |
| `BRW-003` | `browser` | `disposable-fixture` |
| `BRW-004` | `browser` | `disposable-fixture` |
| `BRW-005` | `browser` | `disposable-fixture` |
| `BRW-006` | `browser` | `disposable-fixture` |
| `BRW-007` | `browser` | `disposable-fixture` |
| `BRW-008` | `browser` | `disposable-fixture` |
| `BRW-009` | `browser` | `disposable-fixture` |
| `BRW-010` | `browser` | `disposable-fixture` |
| `LAP-001` | `laptop` | `live-production` |
| `LAP-002` | `laptop` | `disposable-fixture` |
| `LAP-003` | `laptop` | `disposable-fixture` |
| `LAP-004` | `laptop` | `disposable-fixture` |
| `LAP-005` | `laptop` | `disposable-fixture` |
| `LAP-006` | `laptop` | `disposable-fixture` |
| `LAP-007` | `laptop` | `disposable-fixture` |
| `LAP-008` | `laptop` | `disposable-fixture` |
| `LAP-009` | `laptop` | `disposable-fixture` |
| `BKP-001` | `backup-restore` | `live-production` |
| `BKP-002` | `backup-restore` | `live-production` |
| `BKP-003` | `backup-restore` | `disposable-fixture` |
| `BKP-004` | `backup-restore` | `clean-environment` |
| `BKP-005` | `backup-restore` | `clean-environment` |
| `BKP-006` | `backup-restore` | `disposable-fixture` |
| `BKP-007` | `backup-restore` | `live-production` |
| `MON-001` | `monitoring` | `live-production` |
| `MON-002` | `monitoring` | `disposable-fixture` |
| `MON-003` | `monitoring` | `live-production` |
| `FIN-001` | `failure-injection` | `disposable-fixture` |
| `FIN-002` | `failure-injection` | `disposable-fixture` |
| `FIN-003` | `failure-injection` | `disposable-fixture` |
| `FIN-004` | `failure-injection` | `disposable-fixture` |
| `FIN-005` | `failure-injection` | `disposable-fixture` |
| `FIN-006` | `failure-injection` | `disposable-fixture` |
| `FIN-007` | `failure-injection` | `disposable-fixture` |
| `FIN-008` | `failure-injection` | `disposable-fixture` |
| `FIN-009` | `failure-injection` | `disposable-fixture` |
| `FIN-010` | `failure-injection` | `disposable-fixture` |
| `FIN-011` | `failure-injection` | `disposable-fixture` |
| `FIN-012` | `failure-injection` | `disposable-fixture` |
| `FIN-013` | `failure-injection` | `disposable-fixture` |
| `FIN-014` | `failure-injection` | `disposable-fixture` |
| `FIN-015` | `failure-injection` | `disposable-fixture` |
| `FIN-016` | `failure-injection` | `disposable-fixture` |
| `RUN-001` | `runbook` | `clean-environment` |
| `RUN-002` | `runbook` | `clean-environment` |
| `GAP-001` | `unsupported-gaps` | `clean-environment` |
| `GAP-002` | `unsupported-gaps` | `clean-environment` |
| `GAP-003` | `unsupported-gaps` | `live-production` |
| `HLT-001` | `final-health` | `live-production` |
| `HLT-002` | `final-health` | `clean-environment` |
<!-- CATALOG_INDEX_END -->
