# Approval, audit, and secret-handling policy

Status: **Locked for initial production provisioning**
Decision scope: [Choose the approval, audit, and secret-handling policy](https://github.com/JohanSardar/hermes-bot-fleet/issues/7)
Depends on: [Production topology and isolation boundaries](../architecture/production-topology.md)

## Decision

The fleet uses deny-first authorization, operation-bound single-use approvals, brokered credential injection, and append-only tamper-evident audit records. A Hermes profile is not a security boundary. Hermes supplies useful admission and command-safety controls, while the project-built policy gate, operating-system/container boundaries, browser lease supervisor, secret broker, egress proxy, and audit collector enforce this fleet contract.

Johan is the sole initial approval authority. The completion contract that created this fleet is standing authority for architecture-exact initial provisioning, but only while an action is assigned to an in-scope fleet ticket, is an exact step in its Johan-reviewed immutable provisioning manifest, and resolves entirely to Azure, server, or control-plane targets with no Mac side effect. That narrow carve-out covers non-Mac manifest creation, installation, configuration, repository push, issue closure after verification, and explicitly required server host, service, firewall, Tailscale, ACL, ownership, and permission changes on the declared `chief` and `test-worker` resources and their control plane. It may also plan or delegate `laptop-worker` provisioning automatically, but execution pauses before any Mac filesystem, process, application, permission, installation, configuration, or provisioning side effect and requires an exact Mac-local single-use approval. It is not authority for a discovered prerequisite or a semantically similar change. Any manifest deviation, later maintenance or unrelated production change, broad/wildcard permission grant, public exposure, purchase, publishing, third-party message, destructive replacement, account change, target outside the declared fleet resources, or Mac mutation requires the matrix result below (approval or permanent deny). There is no initial-provisioning or standing-authority exception to Mac-local mutation approval.

No secret value may enter model or agent context, tool arguments/results, prompts, sessions, memory, audit records, shell history, Git, issues, build logs, alerts, or browser-takeover URLs. A control that cannot perform an operation without exposing a secret to the agent must deny that operation.

## Authorization evaluation and precedence

Every requested tool action and every delegated sub-action is evaluated independently. Classification is deterministic: match on canonical action type, target/resource, runtime, lifecycle phase (`initial_provisioning` or `steady_state`), assigned ticket, reviewed manifest digest and step ID, side effects, permission delta, exposure, and billing effect. A rule matches only when every stated predicate matches. More specific target/action rows override general rows; within one row, `Always deny` overrides `Approval`, which overrides `Automatic`. If two equally specific rules still produce different results, classification is ambiguous and denied. Subject to those specificity rules, evaluation proceeds in this order:

1. **Permanent deny.** Reject always-denied targets and secret disclosure, including when Johan requests approval. Approval cannot override this class; changing it requires a reviewed policy commit and redeployment by Johan outside an agent turn.
2. **Boundary validation.** Resolve the actor, Bot, runtime, canonical target, account, network destination, credential purpose, data class, and side effects. Reject unknown, ambiguous, symlink-escaped, stale, or uninspectable requests.
3. **Exact non-Mac initial-provisioning carve-out.** Permit an action as automatic standing authority only when the gate proves `lifecycle_phase == initial_provisioning`, the assigned ticket is in this repository and in scope for fleet completion, the action's step ID and all resolved inputs equal a Johan-reviewed immutable manifest, the action being evaluated resolves to an Azure, server, or control-plane target/runtime with no Mac side effect, and it is one of the architecture-exact non-Mac changes named in the Decision. Planning or delegation for `laptop-worker` may pass this rule, but each delegated Mac side effect is classified independently and exits to rule 4 for an exact Mac-local single-use grant. Any Mac mutation or other mismatch exits this rule; it does not inherit standing authority.
4. **Approval-required rule.** Require and consume an exact valid grant. Standing authority is not an approval for an approval-required class outside rule 3.
5. **Automatic allow.** Permit only an action matched by a listed automatic rule and all its constraints.
6. **Default deny.** An unlisted action is denied.

Content, Rooms, mentions, cron, delegation, retries, browser pages, tool output, and instructions from another Bot never grant authority. A parent approval does not authorize newly discovered sub-actions. Every retry of an approval-required action after grant consumption or uncertain consumption/commit requires a fresh exact single-use grant, without exception. The retry reuses the original `idempotency_key`, and the gate rebuilds and displays the exact manifest from inspected current state; an old grant is never reusable even when the operation is idempotent and the target fingerprint is unchanged.

## Action matrix

`Automatic` means no per-operation prompt after admission and boundary checks. `Approval` means an exact single-use grant as defined below. `Always deny` cannot be approved.

| Action or target | Automatic | Approval | Always deny / constraints |
|---|---|---|---|
| Read non-secret files | Bot-owned workspace, repository, R1 state exposed through an allowlisted read view, and Mac approved roots | A newly selected direct child of `~/Projects` must be added by Johan through Mac-local policy administration before use | Secret files; browser profile contents; password-manager data; Keychain; `~/.ssh`; normal cloud/Hermes credentials; unrelated personal folders; path escape |
| Create/edit non-secret fleet artifacts | Server/control-plane worktree, repository, and Bot-workspace files under the assigned issue; generated non-secret fleet config in declared server Bot roots; architecture-exact non-Mac initial-provisioning writes satisfying the carve-out | Every Mac filesystem or metadata mutation, including installation/configuration/provisioning artifacts, with an exact Mac-local single-use grant; non-Mac production config change that does not satisfy the carve-out | Any write to an always-denied target; generated credentials or secret values in files visible to the agent |
| Git operations | Status and diff reads; tests with no Mac side effect; server/control-plane local branches/commits; push this repository after required checks; close/comment on the assigned issue with non-secret evidence after verification | Any Mac-side-effecting Git operation, including checkout, branch/commit, merge, reset, clean, or worktree mutation, requires an exact Mac-local single-use grant; force push, history rewrite, tag/release creation, branch-protection change, or operation in another repository | Committing secrets, browser state, private keys, cookies, approval tokens, or audit signing material |
| Fleet provisioning | Architecture-exact initial creation/install/configuration of declared Azure/server/control-plane resources for `chief` and `test-worker`, including manifest-required server host/service/firewall/Tailscale/ACL/ownership/permission steps, only when every carve-out predicate is proved; planning and delegation for `laptop-worker` up to but not including a Mac side effect; non-destructive verification | Every `laptop-worker` Mac filesystem, process, application, permission, installation, configuration, or provisioning side effect requires an exact Mac-local single-use grant; any deviation or newly discovered prerequisite; later maintenance/rollout; billable purchase or paid-plan change; quota/budget change; unrelated production resource; destructive replacement | Public exposure of SSH, VNC/noVNC, CDP, Hermes, MCP, or filesystem services; broad/wildcard admin; cross-Bot mounts/state |
| Package/image update | On Azure/server/control-plane targets, a digest-pinned install already specified by a reviewed manifest; server security patch within the pinned compatibility gate | Every Mac package/image installation, update, or configuration requires an exact Mac-local single-use grant; major version change, new publisher/repository, license/price implication, or non-carve-out production rollout | Unsigned/unverified artifact; silent model/provider fallback |
| Commands/processes | Read-only inspection, tests, builds, and bounded non-destructive commands inside an assigned server workspace/container; exact initial-provisioning server host/service commands satisfying the carve-out | Every Mac process launch with side effects requires an exact Mac-local single-use grant; destructive command; impactful service stop/restart, host administration, permission change, or production mutation that does not satisfy the carve-out | Known credential harvesting, policy bypass, audit disablement, sandbox escape, or commands against denied paths |
| Network/API reads | Approved provider and fleet endpoints through destination allowlist, without credentials in agent-visible request fields | Enabling a new egress destination or reading non-public account data not already in task scope | Public inbound control endpoint; arbitrary secret-bearing direct egress; bypass of credential-injection proxy |
| Third-party communication | Drafting without sending; replies to Johan in the current authorized Hermes surface; automated health alert from a fixed sanitized template | Exact recipient, channel, subject, and body/attachment digest for email, chat, issue comment outside this repository, form submission, invitation, or other third-party message | Secret-bearing message, deceptive impersonation, recipient wildcard, or mutable/dynamic payload after approval |
| Publishing | Local preview and private draft | Exact immutable artifact digest, destination, visibility, account, and release metadata | Publishing secrets, private audit/browser data, or to an unapproved destination |
| Financial action | Read-only price/quota observation without exposing account secrets | Exact vendor, item, currency, maximum total including tax, funding account alias, and one checkout | Open-ended spend, stored-value transfer, financial credential disclosure, or amount/destination change |
| Account/authentication | Use an already brokered Bot-scoped session for its recorded purpose | Create/delete account, login that changes account state, recovery, MFA enrollment, password/session change, role/membership change | Access to Johan's normal browser profile, password manager, Keychain, personal SSH/cloud/Hermes credentials; disabling MFA/security controls |
| Permissions/security policy | Read and compare effective policy; exact least-privilege Azure/server/control-plane ACL/ownership/firewall/Tailscale/service permission delta required by an initial-provisioning manifest satisfying the carve-out | Every Mac permission, ownership, privacy, firewall, Tailscale, service, or security-policy mutation requires an exact Mac-local single-use grant; any non-carve-out change requires exact principal, resource, before/after rights, duration, and rollback | Broad/wildcard admin, public control-plane exposure, audit/deny removal, or cross-Bot access |
| Server filesystem deletion | Bounded deletion of declared R4 transient data by a reviewed retention job | Exact canonical paths, expected object count/bytes, target fingerprints, backup status, and recovery plan | Deletion outside a Bot-owned root, another Bot's data, backups without retention authority, or ambiguous glob |
| Mac read | Resolved regular-file reads in `~/Agent-Inbox`, `~/Agent-Output`, and individually registered direct children of `~/Projects` | Registering or removing a selected project root is Mac-local policy administration | Denied roots, credential files, aliases/symlinks/hard-link escapes, mounts, devices, sockets, and unrelated personal folders |
| Mac mutation | None | Every create, write, overwrite, rename, move, copy-in, delete, metadata/xattr/permission change, process launch with side effects, application control, clipboard write, outbound send, installation, configuration, or provisioning action; exact Mac-local single-use grant with no standing-authority exception | Denied roots, hidden target substitution, mutation while locked/offline, broad permission, public exposure, or operation not mediated by the local gate |
| Browser automation | Navigation/read/interaction in the Bot's dedicated server Browser Profile under a valid automation lease, when the interaction is otherwise automatic above | Purchase, publish, message, account/permission change, destructive operation, credential enrollment, or any other approval-class effect | Normal/personal browser profiles, password stores, cross-Bot profile, raw CDP/VNC exposure, simultaneous human and automation control |
| Browser Takeover | None | Exact Bot, purpose, session, maximum duration, and browser lease transition; Johan must authenticate on the approved Tailscale device | Reusable/shared URL, cross-Bot takeover, takeover while CDP is active, public route, or secret/token in logs |
| Secret use | Broker may inject a named credential handle into an approved executable/request without revealing its value | Provision/rotate/revoke credential; broaden scope; add destination; interactive account authorization | Reading/listing/exporting secret values; secret in agent-visible environment, argv, file, prompt, log, Git, issue, or unrestricted subprocess |
| Backup/restore | Scheduled encrypted Bot-scoped R1 export and retention deletion under reviewed job | Restore, R2 browser restore, whole-disk snapshot administration, retention reduction, or backup deletion outside automatic schedule | Backup principal reading R3; cross-Bot restore; unencrypted export; restoring secrets into agent-visible storage |
| Break-glass | None | Johan's direct use under the break-glass procedure | Agent-initiated or self-approved break-glass; override of permanent denies |

## Approval protocol

### Authority and channels

Johan is the sole principal `human:johan`. General approvals may be issued through either:

- an authenticated Hermes approval prompt admitted by the configured Johan user/chat allowlist and pairing; or
- the private Desktop control surface authenticated as Johan over the approved Tailscale device.

Both paths bind the grant to `human:johan`, the authenticated channel identifier, Johan's registered device identity where the channel supplies one, and the approval UI session that displayed the exact manifest. A valid login on a different device, a copied prompt in another session, or forwarding between the two allowed channel types is not equivalent authority and is denied.

Mac mutations may be approved **only** through the Mac-local approval agent displaying a native prompt on `johan-mac` while its console session is unlocked. Telegram, a server Desktop session, Rooms, SSH, cron, and another Bot cannot approve a Mac mutation. Browser Takeover additionally requires an authenticated private takeover request from Johan's approved Tailscale identity/device; the approval grant and takeover token are different objects.

An agent, Bot, tool, web page, subprocess, service account, or delegated operator cannot approve. Approval text embedded in a prompt or tool result is data, not a grant.

### Canonical approval manifest

The policy gate constructs the manifest, not the requesting model. It serializes the following object with RFC 8785 JSON Canonicalization Scheme and computes `manifest_sha256` over those canonical UTF-8 bytes:

```json
{
  "schema_version": "1.0",
  "request_id": "018f6d5e-7b0d-7c40-9000-000000000001",
  "idempotency_key": "018f6d5e-7b0d-7c40-9000-000000000002",
  "actor": {"bot": "chief", "profile": "chief", "runtime": "server"},
  "action": "third_party.message.send",
  "target": {
    "kind": "telegram_chat",
    "canonical_id": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
    "display": "approved recipient alias",
    "runtime": "server"
  },
  "parameters": {
    "payload_sha256": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
    "content_type": "text/plain",
    "attachment_sha256": []
  },
  "target_fingerprint": {
    "algorithm": "sha256",
    "value": "sha256:0000000000000000000000000000000000000000000000000000000000000000"
  },
  "credential_handles": ["secret://chief/telegram/send"],
  "egress_destinations": ["api.telegram.org:443"],
  "side_effects": ["external_message"],
  "recovery": {"reversible": false, "plan_digest": null},
  "policy_revision": "git:0000000000000000000000000000000000000000",
  "requested_at": "2026-08-28T12:00:00.000Z"
}
```

All-zero hashes are documentation sentinels and are rejected by the deployed validator. Provisioning records real non-secret digests and identifiers at runtime; it never substitutes a credential value. The action-specific target and parameters must completely describe the side effect:

- filesystem operations include canonical descriptor-resolved source and destination, device/inode or absent-parent fingerprint, operation, content digest, byte count, mode, and expected prior state;
- commands include executable digest, fixed argv digest, cwd, container/image digest, affected service/resources, and bounded timeout;
- messages/publication include exact destination/account/visibility and immutable body plus attachment digests;
- purchases include vendor, SKU, quantity, currency, tax-inclusive maximum, funding-account alias, and checkout digest;
- IAM/account changes include principal, resource, exact before/after state, duration, and rollback digest;
- Browser Takeover includes Bot, browser-profile ID digest, reason, requested duration, current lease nonce digest, and expected `AUTOMATION -> DRAINING -> HUMAN` transition.

The prompt shows a human-readable rendering plus `manifest_sha256`. Hidden fields are prohibited.

### Grant, nonce, expiry, and consumption

On approval the authority service emits a signed grant containing:

```json
{
  "schema_version": "1.0",
  "grant_id": "018f6d60-a345-7bb0-9000-000000000003",
  "manifest_sha256": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
  "nonce_sha256": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
  "approver": "human:johan",
  "channel": "mac_local",
  "authority_context": {
    "channel_instance_id_digest": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
    "approval_session_id_digest": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
    "device_identity_digest": "sha256:0000000000000000000000000000000000000000000000000000000000000000"
  },
  "issued_at": "2026-08-28T12:00:05.000Z",
  "expires_at": "2026-08-28T12:01:05.000Z",
  "max_uses": 1,
  "policy_revision": "git:0000000000000000000000000000000000000000",
  "signing_key_id": "approval-ed25519-2026q3-01",
  "signature": "ed25519:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=="
}
```

The raw nonce is 32 bytes from the operating-system CSPRNG and is delivered only to the gate over an authenticated local/private channel; logs store its SHA-256 digest. General grants expire after five minutes. Mac mutation grants expire after 60 seconds. Browser Takeover grants expire after 60 seconds if not consumed; an established HUMAN lease lasts at most ten minutes and cannot be extended without a new approval. Purchase, permission, account, publishing, destructive, and break-glass grants expire after five minutes.

Grant signatures use pure Ed25519 exactly as specified by RFC 8032 (not Ed25519ph or Ed25519ctx). Let `grant_without_signature` be the complete grant object with only the `signature` member omitted; `signing_key_id` remains inside it. The authority signs the exact bytes `UTF8("fleet-approval-grant-v1\0") || RFC8785(grant_without_signature)`, where RFC 8785 produces canonical UTF-8 JSON bytes, and encodes the 64-byte signature as standard padded base64 after the literal `ed25519:` prefix. Verification rejects a missing, extra, duplicated, unknown, expired, not-yet-valid, or revoked `signing_key_id`, a non-canonical reconstruction, any other domain separator/algorithm/mode, and any signature not exactly 64 decoded bytes.

The grant-verification trust anchor is Johan's offline Ed25519 approval-root public-key fingerprint, pinned in both the reviewed policy deployment and each gate. The offline root signs canonical purpose-limited certificates for online grant-signing public keys containing `signing_key_id`, public key, environment, purpose `fleet-approval-grant-v1`, validity interval, and predecessor key ID; the root private key is never present on a fleet host. Online signing keys are non-exportable and rotate at least every 90 days. Rotation publishes and pins a root-signed successor certificate before activation, retains the predecessor only for verification, and never extends an issued grant's expiry. Suspected compromise causes an offline-root-signed revocation with an effective time, immediate signer removal, denial of grants whose signing time falls in the revoked interval, and activation of a newly certified key. Root rotation requires old/new cross-certification and a reviewed update of every pinned fingerprint; an unavailable old root requires Johan's out-of-band break-glass trust-anchor update and an audited discontinuity.

The gate verifies the RFC 8032 signature and pinned `signing_key_id` trust chain/revocation state; exact `human:johan` identity; channel eligibility; channel-instance, approval-session, and applicable registered-device identity digests in `authority_context`; exact manifest digest; nonce; policy revision; expiry using both wall and monotonic clocks; `max_uses == 1`; and unchanged target fingerprint immediately before execution. A channel without a device identity uses `null` for `device_identity_digest`; the channel-instance and approval-session digests are always required. It atomically writes a durable `approval.consumed` event and a uniqueness record for `(grant_id, nonce_sha256)` before releasing the side effect. A duplicate, uncertain commit, changed payload/target, clock rollback, reboot, gate restart, expired grant, missing audit sink, or already consumed nonce is denied. Any later attempt uses the original idempotency key but requires state inspection, a newly displayed exact manifest, and a fresh single-use grant. Grants are Bot-, runtime-, action-, target-, payload-, credential-handle-, egress-, policy-revision-, authority-context-, and side-effect-bound. They are not bearer authorization for any other operation.

Denial and timeout create audit events but no reusable negative token. Approval interfaces offer `deny` and `approve once`; there is no `always allow` control.

## Mac-local mutation enforcement

`laptop-worker` is confined to the roots and sensitive-path denies in the production topology. `~/Projects` itself is not a recursive grant. A root registry controlled by the Mac-local gate records only individually selected direct child directories.

The project-built Mac gate must:

1. receive a structured operation over a local authenticated IPC endpoint unavailable to server Bots;
2. open the registered root and traverse with descriptor-relative operations, refusing symlinks, aliases, mount/device changes, hard links to denied/out-of-root inodes, `..`, non-regular special files, and case/Unicode ambiguity;
3. capture source/destination identity, expected prior state, content digest/size, and relevant metadata in the manifest;
4. require an exact Mac-local single-use grant for every mutation, including installation, configuration, provisioning, and a mutation delegated by an automatically admitted `laptop-worker` plan, while the console is unlocked and the gate UI is foreground-visible;
5. re-resolve and compare the target fingerprint after approval;
6. durably audit grant consumption before mutation, execute once with least privilege, fsync the result and containing directory where applicable, and record outcome;
7. fail closed on sleep, lock, logout, network loss, UI loss, timeout, crash, audit failure, target change, or ambiguous completion.

Every mutation is gated, including installation, configuration, provisioning, cron, fleet work, application automation, shell commands, Git writes, clipboard writes, and operations requested by Johan through Telegram. There is no no-prompt provisioning mode and no initial-provisioning, reviewed-manifest, delegation, or standing-authority exception: an automatically admitted `laptop-worker` plan must pause before each Mac side effect for its exact local grant. Reads remain automatic only in approved roots and never include credential or denied paths. `HERMES_WRITE_SAFE_ROOT`, if enabled, is defense in depth and is set to an approved narrow root; it does not satisfy or bypass the local gate.

The permanent Mac deny set includes normal browser profiles, Keychain and `~/Library/Keychains`, password-manager data, `~/.ssh`, `~/.gnupg`, normal cloud credentials/configuration, Tailscale state, cloud/Hermes credentials, Hermes credential files outside the active `laptop-worker` runtime, macOS system/privacy databases, and unrelated personal folders. The active profile's credential files are also not exposed through general file tools; only the broker may use them.

## Browser automation and takeover

A project-built lease supervisor enforces the topology's `AUTOMATION -> DRAINING -> HUMAN -> RECOVERING -> AUTOMATION` state machine. Takeover approval binds the Bot, Browser Profile, Johan identity/device, current automation lease nonce, purpose, and duration. Consumption first drains new CDP work, applies bounded cancellation, verifies zero CDP clients, rotates/revokes the automation lease, and only then enables one authenticated noVNC input session. The takeover URL contains no credential, token, nonce, or secret in any component, including its fragment. After Johan authenticates from the approved Tailscale identity/device, a separate authenticated same-origin session bootstrap delivers the random single-use takeover credential outside URL/navigation data. The bootstrap response is `Cache-Control: no-store`, is never exposed to the agent/model or page JavaScript, and the supervisor/noVNC client keeps it out of browser history, logs, screenshots, CDP, crash reports, and any tool or model context; only its digest may be logged. If that isolation cannot be proved, takeover is denied.

During `HUMAN`, CDP is disconnected and denied. Disconnect, ten-minute timeout, browser/supervisor/proxy restart, session conflict, or uncertain ownership revokes input and enters `RECOVERING`. Recovery revokes all takeover credentials, closes VNC/CDP clients, validates profile health, resets a known window/tab state, rotates the automation lease nonce, and passes a harmless probe before automation resumes. A takeover does not approve any purchase, publication, message, account/permission change, destructive operation, or use of an ungranted credential encountered in the browser.

## Secret and credential policy

### Classification and storage

Secret values include passwords, API/session/OAuth tokens, private keys, cookies, MFA seeds/recovery codes, approval/takeover raw tokens, credential-bearing URLs, encryption/audit keys, and sensitive provider responses. They are R3 and are never committed or copied into R1 exports.

Each Bot has separate credentials and may reference only opaque handles of the form `secret://BOT/PURPOSE/NAME`. Handles and secret metadata are non-secret; values are not. `chief` receives only explicitly granted production credentials. `test-worker` receives test credentials only. `laptop-worker` receives deliberately provisioned profile-scoped credentials and never inherits Johan's normal account home.

Server secrets are supplied from an external secret authority into a root-owned project-built broker or narrowly scoped service credential facility. Mac secrets are held in the managed system credential scope accessible to the broker service, not the agent. Hermes managed system configuration/secret scope and external secret sources may hold Hermes/provider credentials where supported. Secret source administration is human/admin-only.

### Injection without agent-visible values

The agent submits a handle, operation class, destination, and payload digest to the broker. The broker authenticates the Bot workload identity, evaluates handle scope and approval evidence, and then uses exactly one of these adapters:

1. **HTTP signing proxy:** add the credential to an outbound request after the agent-visible request has crossed into the broker; enforce method, scheme, host, port, path template, payload limit, and resolved-IP policy; strip credential-bearing response headers.
2. **Process launcher:** open the secret as a sealed descriptor or one-shot stdin channel directly into a digest-pinned executable that explicitly supports it. The descriptor is absent from child enumeration and closed immediately. Environment variables, argv, inherited shell state, terminal output, and agent-readable files are prohibited.
3. **Native service credential:** let the supervised service consume its managed credential without exposing the service environment, config file, or process inspection to the Bot.
4. **Browser session:** a human authenticates during approved Browser Takeover; the resulting encrypted Browser Profile remains mounted only in that Bot's browser container and cookies/password stores are never returned through CDP/tool output.

MCP subprocess environment filtering removes undeclared parent variables. Container backends, mount isolation, Unix identities, process-inspection restrictions, and the credential-injection egress firewall are the actual boundary. Redaction is not a substitute for non-disclosure. A tool requiring a secret in a normal environment variable or command argument is unsupported until a safe adapter exists.

Broker responses contain status, bounded sanitized data, and a request ID. They reject redirects to unapproved origins, DNS rebinding, alternate IP literals, proxy tunneling, arbitrary TLS roots, response reflection of request credentials, and destinations not bound to the handle. Direct egress from credential-using workloads is denied so the broker cannot be bypassed.

### Scope, lifecycle, rotation, and revocation

Every credential inventory record contains owner Bot, authority, purpose, environment, permitted adapter, exact destinations/method/path class, account/resource scope, issue/expiry time, rotation maximum, revocation procedure, and non-secret version ID. Default scopes are one Bot, one environment, one purpose, and the minimum provider permissions. Sharing values or Browser Profiles between Bots is prohibited.

- Prefer short-lived workload/OAuth tokens. Access-token lifetime is at most one hour when the authority supports it.
- Rotate static API/channel/service credentials at least every 90 days, audit-chain keys every 90 days, and immediately after suspected exposure, staff/device loss, scope change, provider incident, or Bot retirement.
- Rotate refresh credentials at least annually when provider capability permits; otherwise reauthorize annually and record the exception metadata.
- Rotation is create-new, update broker version, canary, atomically activate, revoke-old, and verify-old-fails. There is no interval where both versions are agent-visible.
- Revocation disables the broker handle and egress first, revokes at the authority, terminates sessions/processes, rotates dependent credentials, invalidates browser/approval leases, and emits a security alert. A revoked handle fails closed even if cached work remains.
- `test-worker` can never receive production scope. Backup credentials are write-only to one Bot prefix and cannot read R3. Audit writers cannot read secret values.

Inventory contains metadata only and is reviewed monthly. Expiry within 14 days alerts. Missing inventory, unknown version, overdue rotation, unavailable revocation status, or excessive scope disables the handle.

## Audit contract

### Producer envelope contract

Every policy decision, approval request/decision/consumption, broker access, credential lifecycle event, command, network request, Mac operation, browser lease transition, takeover, backup/restore, security alert, configuration change, and break-glass action causes its producer to submit one object conforming to this producer-envelope schema. The authenticated local IPC workload identity is transport metadata, not an envelope field; the collector maps it to one configured producer/Bot/runtime and rejects an `actor` or `runtime` inconsistent with that identity. Producers apply typed safe-field allowlists and reject additional fields before submission. They never emit or reserve `sequence`, `observed_at`, `redactions`, or `integrity`; those names are collector-owned.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://fleet.invalid/schema/audit-producer-envelope-1.0.json",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "event_id", "occurred_at", "event_type", "severity", "actor", "runtime", "action", "resource", "decision", "correlation", "policy_revision", "details"],
  "properties": {
    "schema_version": {"const": "1.0"},
    "event_id": {"type": "string", "format": "uuid"},
    "occurred_at": {"type": "string", "format": "date-time"},
    "event_type": {"type": "string", "pattern": "^[a-z][a-z0-9_.-]{2,63}$"},
    "severity": {"enum": ["debug", "info", "notice", "warning", "error", "critical"]},
    "actor": {
      "type": "object", "additionalProperties": false,
      "required": ["type", "id", "bot", "session_id"],
      "properties": {"type": {"enum": ["human", "bot", "service", "system"]}, "id": {"type": "string", "maxLength": 128}, "bot": {"type": ["string", "null"], "enum": ["chief", "test-worker", "laptop-worker", null]}, "session_id": {"type": ["string", "null"], "maxLength": 128}}
    },
    "runtime": {"enum": ["server", "mac", "control"]},
    "action": {"type": "string", "pattern": "^[a-z][a-z0-9_.-]{2,127}$"},
    "resource": {
      "type": "object", "additionalProperties": false,
      "required": ["type", "id_digest", "display_class"],
      "properties": {"type": {"type": "string", "maxLength": 64}, "id_digest": {"type": ["string", "null"], "pattern": "^sha256:[a-f0-9]{64}$"}, "display_class": {"type": "string", "maxLength": 128}}
    },
    "decision": {"enum": ["allow", "deny", "require_approval", "approve", "consume", "error"]},
    "reason_code": {"type": ["string", "null"], "pattern": "^[A-Z0-9_]{3,64}$"},
    "correlation": {
      "type": "object", "additionalProperties": false,
      "required": ["request_id", "parent_event_id", "manifest_sha256", "grant_id", "nonce_sha256", "idempotency_key"],
      "properties": {
        "request_id": {"type": "string", "maxLength": 128},
        "parent_event_id": {"type": ["string", "null"], "format": "uuid"},
        "manifest_sha256": {"type": ["string", "null"], "pattern": "^sha256:[a-f0-9]{64}$"},
        "grant_id": {"type": ["string", "null"], "maxLength": 128},
        "nonce_sha256": {"type": ["string", "null"], "pattern": "^sha256:[a-f0-9]{64}$"},
        "idempotency_key": {"type": ["string", "null"], "maxLength": 128}
      }
    },
    "policy_revision": {"type": "string", "pattern": "^git:[a-f0-9]{40,64}$"},
    "details": {"type": "object", "additionalProperties": {"type": ["string", "number", "integer", "boolean", "null"]}, "maxProperties": 32}
  }
}
```

### Finalized collector event contract

The collector authenticates the producer, validates the producer envelope, applies typed redaction and rejection, sets `observed_at`, records the redaction classes in `redactions`, atomically assigns the next per-stream `sequence`, and computes `integrity`. Only then does it emit the finalized event to any sink. Downstream sinks accept only objects conforming to this finalized-event schema; a producer envelope is never itself an audit record.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://fleet.invalid/schema/audit-event-1.0.json",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "event_id", "sequence", "occurred_at", "observed_at", "event_type", "severity", "actor", "runtime", "action", "resource", "decision", "correlation", "policy_revision", "details", "redactions", "integrity"],
  "properties": {
    "schema_version": {"const": "1.0"},
    "event_id": {"type": "string", "format": "uuid"},
    "sequence": {"type": "integer", "minimum": 1},
    "occurred_at": {"type": "string", "format": "date-time"},
    "observed_at": {"type": "string", "format": "date-time"},
    "event_type": {"type": "string", "pattern": "^[a-z][a-z0-9_.-]{2,63}$"},
    "severity": {"enum": ["debug", "info", "notice", "warning", "error", "critical"]},
    "actor": {
      "type": "object", "additionalProperties": false,
      "required": ["type", "id", "bot", "session_id"],
      "properties": {"type": {"enum": ["human", "bot", "service", "system"]}, "id": {"type": "string", "maxLength": 128}, "bot": {"type": ["string", "null"], "enum": ["chief", "test-worker", "laptop-worker", null]}, "session_id": {"type": ["string", "null"], "maxLength": 128}}
    },
    "runtime": {"enum": ["server", "mac", "control"]},
    "action": {"type": "string", "pattern": "^[a-z][a-z0-9_.-]{2,127}$"},
    "resource": {
      "type": "object", "additionalProperties": false,
      "required": ["type", "id_digest", "display_class"],
      "properties": {"type": {"type": "string", "maxLength": 64}, "id_digest": {"type": ["string", "null"], "pattern": "^sha256:[a-f0-9]{64}$"}, "display_class": {"type": "string", "maxLength": 128}}
    },
    "decision": {"enum": ["allow", "deny", "require_approval", "approve", "consume", "error"]},
    "reason_code": {"type": ["string", "null"], "pattern": "^[A-Z0-9_]{3,64}$"},
    "correlation": {
      "type": "object", "additionalProperties": false,
      "required": ["request_id", "parent_event_id", "manifest_sha256", "grant_id", "nonce_sha256", "idempotency_key"],
      "properties": {
        "request_id": {"type": "string", "maxLength": 128},
        "parent_event_id": {"type": ["string", "null"], "format": "uuid"},
        "manifest_sha256": {"type": ["string", "null"], "pattern": "^sha256:[a-f0-9]{64}$"},
        "grant_id": {"type": ["string", "null"], "maxLength": 128},
        "nonce_sha256": {"type": ["string", "null"], "pattern": "^sha256:[a-f0-9]{64}$"},
        "idempotency_key": {"type": ["string", "null"], "maxLength": 128}
      }
    },
    "policy_revision": {"type": "string", "pattern": "^git:[a-f0-9]{40,64}$"},
    "details": {"type": "object", "additionalProperties": {"type": ["string", "number", "integer", "boolean", "null"]}, "maxProperties": 32},
    "redactions": {"type": "array", "items": {"type": "string", "maxLength": 64}, "uniqueItems": true},
    "integrity": {
      "type": "object", "additionalProperties": false,
      "required": ["stream_id", "previous_hash", "event_hash", "key_version"],
      "properties": {"stream_id": {"type": "string", "maxLength": 128}, "previous_hash": {"type": ["string", "null"], "pattern": "^hmac-sha256:[a-f0-9]{64}$"}, "event_hash": {"type": "string", "pattern": "^hmac-sha256:[a-f0-9]{64}$"}, "key_version": {"type": "string", "maxLength": 64}}
    }
  },
  "allOf": [
    {
      "if": {"properties": {"sequence": {"const": 1}}, "required": ["sequence"]},
      "then": {"properties": {"integrity": {"properties": {"previous_hash": {"type": "null"}}}}},
      "else": {"properties": {"integrity": {"properties": {"previous_hash": {"type": "string", "pattern": "^hmac-sha256:[a-f0-9]{64}$"}}}}}
    }
  ]
}
```

`details` uses an event-type allowlist of safe scalar keys. It may contain exit status, byte count, duration, HTTP status, destination class, credential handle, credential version ID, image digest, file content digest, and sanitized error code. It may not contain command stdout/stderr unless a producer-specific sanitizer and size limit are tested. It never contains prompts, message bodies, file contents, URLs with query/fragment, headers, cookies, environment dumps, approval/takeover raw tokens, secret values, or browser screenshots. `integrity.previous_hash` is `null` only for sequence 1 (the stream genesis); every later event must carry the exact preceding `hmac-sha256:<64 hex>` `event_hash`.

### Sinks, redaction, retention, and integrity

Each producer sends structured events to a project-built local audit collector over authenticated local IPC. The collector validates schema, applies typed field allowlists and secret-pattern/known-value fingerprint detection, assigns a per-stream sequence, and appends to:

1. a Bot-scoped local append-only JSONL stream under the topology's audit directory (Mac: protected profile service log), readable by Johan/admin but not writable by the Bot;
2. the host system journal/unified log with the same sanitized event and bounded rotation; and
3. a private encrypted Azure Blob audit archive, separated by Bot and day, with public access disabled, Johan/admin read access, collector create-only access, and a 400-day immutable time-based retention policy plus legal hold capability disabled by default.

Server local logs retain 30 days or 2 GiB per Bot, whichever limit is reached first after successful archive confirmation. Mac local logs retain 30 days or 1 GiB and spool while offline; they upload when connected. Immutable archive retention is at least 400 days. Expiry alone never deletes an object: lifecycle deletion additionally requires the durable verifier authorization tag defined below. Deletion before expiry, retention reduction, archive restore, export, or manual bypass of that tag requires approval and is itself audited. R3 values and browser contents are never archived.

Before hashing, the collector canonicalizes the finalized event with `integrity.event_hash` omitted using RFC 8785. `event_hash` is HMAC-SHA-256 over the ASCII domain separator `fleet-audit-event-v1\0` followed by four components, each encoded as `uint64_be(byte_length) || bytes`: UTF-8 `stream_id`; `uint64_be(sequence)` (whose byte length is eight); the previous hash's lowercase ASCII representation (zero bytes only for sequence 1); and the canonical event bytes. The HMAC key resides in the audit service/managed secret scope and is unavailable to Bots.

HMAC rotation has an explicit sequence boundary. The collector first seals and signs a checkpoint through sequence `N` under key version `K`, activates `K+1` atomically for sequence `N+1`, and records both versions and the boundary in the first `K+1` event and checkpoint metadata. A key version therefore owns one contiguous, non-overlapping sequence interval; it cannot sign before its activation sequence or after its sealed terminal sequence. The first event under `K+1` keeps `previous_hash` equal to the terminal `K` event hash, so chain continuity does not depend on using the same HMAC key. Rotation never resets `stream_id` or `sequence`.

Retired HMAC keys move to verification-only custody in the managed secret authority: collectors cannot request them for writes, and only the isolated verifier identity can use them. Each retired key remains available until every archive object and checkpoint containing its events has individually completed the real 400-day immutable period. The isolated verifier then performs and durably records one final end-to-end verification while the key and every covered object still exist. Only a passing final verification may issue a signed, durable deletion-authorization record naming the key version, complete object-digest set, sequence range, verification evidence digest, and authorization time; the archive controller applies the corresponding verifier-only authorization tag to those exact objects. Lifecycle rules delete an expired object only when that valid tag is present, so staggered object expiries cannot race key-wide verification. The collector then confirms every covered object's deletion from archive inventory and failed object reads. Only after that deletion confirmation may the authority cryptographically destroy all wrapped key copies and backups, record the key-version fingerprint, covered sequence range, final-verification evidence, deletion confirmation, and destruction time in a checkpointed `audit.key_destroyed` event, and confirm that no recoverable copy remains. Early deletion, destruction, tag forgery/mismatch, or loss blocks verification and is a critical incident; archive retention cannot be extended without extending key custody by the same interval.

Daily checkpoints contain schema version, stream ID, UTC day, first/last sequence, first/terminal event hash, all `(key_version, first_sequence, last_sequence)` intervals present, prior checkpoint digest, archive object SHA-256 digest, event count, and trusted timestamp. The checkpoint signer signs `UTF8("fleet-audit-checkpoint-v1\0") || RFC8785(checkpoint_payload)` with Ed25519 as specified by RFC 8032; `signature_algorithm`, `signing_key_id`, and the base64 signature are outside `checkpoint_payload` and therefore cannot be confused with signed fields. The trust anchor is Johan's offline Ed25519 audit root public-key fingerprint pinned both in this reviewed policy deployment and in the independent verifier. That offline root signs canonical, purpose-limited certificates for online checkpoint-signing public keys, including key ID, validity interval, environment, and predecessor key ID; the private root is never present on a fleet host.

Checkpoint-signing keys live in a non-exportable managed HSM/Keychain service identity and rotate at least every 90 days. Rotation publishes an overlap certificate before activation, has the old key sign a final checkpoint naming the new certificate digest, and has the new key's first checkpoint name the old terminal checkpoint digest. Expiry stops new signatures but preserves verification. Suspected compromise triggers revocation signed by the offline root, removal from the online signer, a bounded incident interval, re-verification from the last trusted checkpoint, and a new root-certified key; events/checkpoints in the affected interval remain retained and explicitly marked untrusted rather than silently re-signed. Root-key rotation requires a cross-certificate signed by both old and new roots, a reviewed policy update to both pinned fingerprints, and independent verification before the old root is retired. If the old root cannot sign, Johan must update the trust anchor out of band and record the discontinuity as a break-glass incident.

Checkpoints are written to a separate immutable prefix. Cross-day streams chain to the prior checkpoint digest, and verifier state retains all HMAC and signing key IDs plus activation/revocation intervals, preserving continuity across key versions. Verification runs daily and monthly end-to-end; gaps, duplicate sequence/nonce, an event outside its key activation interval, invalid HMAC/signature/certificate, unknown or revoked key, changed object digest, broken cross-key/cross-checkpoint link, clock skew over 60 seconds, archive delay over 24 hours, or failed checkpoint alerts and blocks approval-required/high-impact operations.

Redaction order is typed omission, exact known-secret fingerprint rejection, credential/header/URL parser stripping, conservative token-pattern replacement, then output size limiting. Values are replaced by a class marker and optional one-way digest only when correlation is necessary. A redaction failure drops the unsafe event payload, emits a minimal `audit.redaction_failure` event through a separate safe path, quarantines the producer output outside agent access, and fails the attempted operation; it never writes the suspected value to fallback logs or alerts.

Audit access is read-only for Johan and requires approval for bulk export. Alerts contain event ID, Bot, safe reason code, and time only. System clock is synchronized, but expiry also uses monotonic time.

## Break-glass

Break-glass is for imminent loss of availability or data when normal approval infrastructure is unavailable. It does not override permanent denies, disclose secrets to an agent, permit public control endpoints, or authorize an agent to act independently.

1. Johan works directly from the approved Mac, authenticates locally, and activates the offline break-glass command outside Hermes.
2. The tool shows exact scope and requires entry of a stored offline recovery code plus a typed incident reason. It creates a hardware/local-key-signed, single-use grant limited to one Bot/resource and 15 minutes.
3. Activation disables autonomous Bot turns, cron mutations, browser automation, and secret issuance not essential to the declared recovery. It snapshots safe metadata and starts an append-only local incident stream.
4. Johan performs only the declared recovery through the restricted admin tool. All commands, resources, and outcomes are recorded; secret output is suppressed.
5. The grant expires without renewal. Recovery revokes temporary credentials, rotates any credential touched, restores normal policy, verifies audit chains and Bot isolation, and requires a non-secret incident report in this repository within 24 hours.
6. If local audit cannot be made durable, break-glass remains unavailable. Physical/manual provider recovery is then required.

## Failure behavior

All controls fail closed:

- policy gate unavailable, policy revision mismatch, malformed/ambiguous request, or no matching rule: deny;
- approval timeout, channel loss, invalid signature, stale nonce, replay, target change, restart, or uncertain consumption/commit: deny; inspect current state and, for any retry, preserve the original idempotency key while requiring a newly displayed exact manifest and fresh single-use grant;
- secret source/broker/egress firewall unavailable, scope mismatch, destination mismatch, rotation overdue, or revocation uncertain: do not inject and stop the operation;
- audit collector unavailable, disk full, schema/redaction/integrity failure, or archive lag over 24 hours: deny approvals, secret use, Mac mutations, browser takeover, and other side effects; allow only bounded read-only diagnostics that generate a recoverable local event;
- Mac asleep, locked, offline, gate/UI unavailable, or path identity uncertain: deny mutation; reads also stop if confinement cannot be proved;
- browser supervisor uncertainty: enter `RECOVERING`, disable CDP and noVNC input, revoke leases, and alert;
- provider/model unavailable: fail the turn or cron run and alert; never fall back from `openai-codex` and `gpt-5.6-sol`;
- redaction uncertainty: suppress payload, preserve only safe failure metadata, and alert;
- partial side effect: record `error` with the idempotency key, quarantine retries, inspect actual state, and require a newly displayed exact manifest plus a fresh single-use grant for every retry; reuse the same idempotency key and provide no idempotent-replay exception.

Alerts use fixed sanitized templates. No emergency path silently broadens access.

## Native Hermes controls and project-built enforcement

| Control | Ownership | Fleet use and limitation |
|---|---|---|
| User/chat allowlists and pairing | Native Hermes | Admission for Telegram; not side-effect authorization |
| Dangerous-command approval with fail-closed timeout | Native Hermes | Enabled as defense in depth; project policy may classify more actions and denial wins |
| Protected paths and optional `HERMES_WRITE_SAFE_ROOT` | Native Hermes | Narrow Mac/workspace guardrails; not a complete filesystem sandbox and never a Mac mutation approval |
| Named profiles, profile home mode, managed system config/secret scope, external secret sources | Native Hermes | State/config organization and supported secret source; profiles alone are not security boundaries |
| MCP subprocess environment filtering | Native Hermes | Removes undeclared inherited variables; does not stop argv/files/network exfiltration by itself |
| Container terminal backends | Native Hermes capability plus deployment configuration | True server execution boundary when combined with rootless containers, mounts, users, and firewall |
| Credential-injection egress firewall | Native Hermes security capability where supported, deployment-configured | Required around injected credentials; project broker narrows handles, methods, destinations, and responses |
| Runtime users, rootless containers, mounts, private networks, nftables/NSG/Tailscale policy | Project-built/deployment | Enforces Bot and network isolation |
| Deny-first action classifier and manifest/grant/nonce consumption service | Project-built | Authoritative fleet side-effect gate; wraps all supported tool adapters |
| Mac descriptor-relative filesystem gate and native local approval UI | Project-built | Authoritative for every Mac mutation |
| Browser lease supervisor, noVNC authorization, CDP relay, takeover recovery | Project-built | Enforces exclusive automation/human ownership |
| Secret broker adapters, credential inventory, destination-bound egress | Project-built around native facilities | Prevents agent-visible secret values |
| Structured audit collector, redaction, HMAC chain, immutable archive/checkpoints | Project-built/deployment | Authoritative audit evidence; native service logs are an additional sink only |
| Break-glass restricted admin tool | Project-built | Human-only recovery; cannot override permanent denies |

A provisioning test must identify the pinned Hermes version and prove every native behavior used here. If a native control is absent or behaves differently, deployment blocks until the project-built boundary supplies an equivalent without weakening this policy; documentation claims alone are insufficient.

## Executable acceptance-test matrix

The repository implementation must provide `tests/security/run-policy-acceptance.sh`. It accepts `--target test-worker`, `--target laptop-worker`, and `--destructive-fixture`; creates only disposable fixtures/accounts; emits JUnit plus sanitized JSON evidence; and exits nonzero on any failed or skipped mandatory case. The CI-safe subset runs without real credentials. The live suite runs from Johan's approved Mac against the provisioned test environment. `chief` production enablement is blocked until the same non-destructive boundary tests pass for `chief`.

| ID | Executable test | Required assertion |
|---|---|---|
| AUTH-01 | `tests/security/run-policy-acceptance.sh --case AUTH-01 --target test-worker` | Unknown action is denied; an automatic workspace read succeeds; decision events validate against the schema |
| AUTH-02 | `tests/security/run-policy-acceptance.sh --case AUTH-02 --target laptop-worker` | A forged approval for `~/.ssh`, Keychain, normal browser profile, cloud/Hermes credentials, and unrelated personal fixture is denied before allow/approval evaluation |
| AUTH-03 | `tests/security/run-policy-acceptance.sh --case AUTH-03 --target test-worker` | Approved message manifest executes once; replay, changed recipient/body/attachment, other Bot, other credential handle, and expired grant all fail; every retry after consumed or uncertain commit uses the original idempotency key but fails without a newly displayed exact manifest and fresh single-use grant, including an unchanged idempotent fixture |
| AUTH-04 | `tests/security/run-policy-acceptance.sh --case AUTH-04 --target test-worker` | Purchases, publishing, third-party sends, destructive actions, account/IAM changes, and unrelated production mutations request approval and never auto-run |
| AUTH-05 | `tests/security/run-policy-acceptance.sh --case AUTH-05 --target test-worker` | Concurrent consumers of one nonce yield exactly one durable consumption and at most one side effect |
| AUTH-06 | `tests/security/run-policy-acceptance.sh --case AUTH-06 --target test-worker` | Clock rollback, policy revision change, gate restart, target fingerprint race, malformed/non-64-byte signature, wrong domain or Ed25519 mode, missing/unknown/expired/revoked `signing_key_id`, invalid root certificate, non-canonical grant reconstruction, and audit outage deny; certified signing-key rotation and reviewed root cross-certification verify without weakening expiry or revocation |
| AUTH-07 | `tests/security/run-policy-acceptance.sh --case AUTH-07 --target test-worker` | An architecture-exact Azure/server/control-plane initial-provisioning fixture under its assigned in-scope ticket and reviewed manifest runs automatically, including its exact server host/service/firewall/Tailscale/permission steps; a `laptop-worker` fixture may be planned/delegated automatically but pauses before every Mac side effect for MAC-01; any Mac mutation, wrong ticket/manifest/step/input, discovered deviation, steady-state replay, unrelated production target, purchase, broad permission, or public exposure cannot use standing authority and resolves deterministically to approval or deny |
| AUTH-08 | `tests/security/run-policy-acceptance.sh --case AUTH-08 --target test-worker` | The same exact general-approval fixture succeeds once through (a) Johan's allowlisted/paired authenticated Hermes approval prompt and (b) Johan's private Desktop surface on the approved Tailscale device; grants attributed to another human, any Bot/service/tool/delegate, wrong or unregistered device, different UI/login session, copied/forwarded prompt, Mac-local-only agent, Room, SSH, cron, browser page, tool output, or any other channel are rejected and produce no side effect |
| MAC-01 | `tests/security/run-policy-acceptance.sh --case MAC-01 --target laptop-worker` | Every Mac mutation type in the matrix prompts locally without exception, including installation, configuration, provisioning, exact reviewed-manifest steps, and side effects delegated by an automatically admitted `laptop-worker` plan; Telegram/server/standing authority cannot satisfy it; one exact Mac-local single-use grant changes exactly one fixture and no no-prompt Mac mutation path exists |
| MAC-02 | `tests/security/run-policy-acceptance.sh --case MAC-02 --target laptop-worker` | Symlink, alias, hard-link escape, mount/device swap, case/Unicode ambiguity, `..`, destination race, and selected-root removal fail |
| MAC-03 | `tests/security/run-policy-acceptance.sh --case MAC-03 --target laptop-worker` | Lock, sleep simulation, offline state, approval UI kill, gateway restart, timeout, and audit-full fixture leave files unchanged |
| BROW-01 | `tests/security/run-policy-acceptance.sh --case BROW-01 --target test-worker` | Exact approved takeover drains CDP, permits one Johan session for at most ten minutes, and never permits simultaneous CDP/noVNC input |
| BROW-02 | `tests/security/run-policy-acceptance.sh --case BROW-02 --target test-worker` | Replayed/wrong-Bot/wrong-device/expired takeover token, supervisor/proxy/browser crash, and disconnect enter `RECOVERING` and revoke input |
| BROW-03 | `tests/security/run-policy-acceptance.sh --case BROW-03 --target test-worker` | Every takeover URL component, including fragment, is token-free; the credential is delivered only by the authenticated no-store bootstrap and is absent from browser history, access/application logs, screenshots, CDP, crash reports, agent/model/tool context, and page JavaScript; takeover does not authorize an approval-class browser effect |
| SEC-01 | `tests/security/run-policy-acceptance.sh --case SEC-01 --target test-worker` | Agent process environment, argv, open readable files, tool output, model/session capture, and logs contain handles only and no seeded canary secret |
| SEC-02 | `tests/security/run-policy-acceptance.sh --case SEC-02 --target test-worker` | Broker accepts the exact Bot/handle/method/destination and rejects cross-Bot use, redirect, DNS rebinding fixture, alternate port/path, direct egress, and response reflection |
| SEC-03 | `tests/security/run-policy-acceptance.sh --case SEC-03 --target test-worker` | Rotation canary succeeds, old version is revoked and fails, inventory updates, and simulated expiry/overdue rotation disables the handle |
| SEC-04 | `tests/security/run-policy-acceptance.sh --case SEC-04 --target test-worker` | `test-worker` cannot resolve production handles; backup principal cannot read R3 or another Bot prefix |
| AUD-01 | `tests/security/run-policy-acceptance.sh --case AUD-01 --target test-worker` | All required event classes first validate as authenticated safe producer envelopes with no collector-owned sequence/hash fields, then validate as finalized collector events with assigned observation/redaction/sequence/integrity fields; extra fields, identity mismatch, incomplete correlation, and raw values are rejected |
| AUD-02 | `tests/security/run-policy-acceptance.sh --case AUD-02 --target test-worker` | Seeded password/token/cookie/header/query canaries are omitted or redacted from local, journal, archive, alert, and JUnit evidence |
| AUD-03 | `tests/security/run-policy-acceptance.sh --case AUD-03 --target test-worker` | Edit/delete/reorder/duplicate/gap/key-version mutations break chain verification; HMAC rotation occurs at the declared sequence boundary with cross-key continuity; daily Ed25519 checkpoint signature/certificate/object digest and cross-checkpoint link detect replacement or an unknown/revoked signing key |
| AUD-04 | `tests/security/run-policy-acceptance.sh --case AUD-04 --target test-worker` | Collector create-only archive rights, private encryption, Bot separation, 30-day local rotation, and 24-hour lag alarm match policy; live configuration inspection proves immutable retention is at least 400 days and lifecycle deletion requires both expiry and a valid verifier-only authorization tag, while separately retained recurring daily/monthly evidence proves scheduled verification runs and alerts on skipped/failed runs |
| AUD-05 | `tests/security/run-policy-acceptance.sh --case AUD-05 --target test-worker --destructive-fixture` | An accelerated disposable retirement fixture proves a retired HMAC key cannot sign, remains verifier-only until all covered objects expire, performs and records final verification, issues a digest-bound deletion authorization/tag, rejects missing/forged/mismatched tags, deletes the exact covered objects next, confirms deletion, and destroys all key copies only last; the test also inspects the real 400-day production configuration without shortening it, and signing-key rotation/revocation and root cross-certification preserve or explicitly mark trust continuity |
| FAIL-01 | `tests/security/run-policy-acceptance.sh --case FAIL-01 --target test-worker` | Kill each gate/broker/audit/lease component and fill disposable log storage; side effects stop, safe diagnostics remain bounded, sanitized alert arrives |
| FAIL-02 | `tests/security/run-policy-acceptance.sh --case FAIL-02 --target test-worker` | Induced `openai-codex`/`gpt-5.6-sol` failure produces no fallback call and emits a sanitized failure event/alert |
| BG-01 | `tests/security/run-policy-acceptance.sh --case BG-01 --target laptop-worker` | Bot cannot invoke break-glass; one human fixture grant is scope/time limited, disables autonomy, preserves permanent denies, expires, and requires recovery checks |
| ISO-01 | `tests/security/run-policy-acceptance.sh --case ISO-01 --target test-worker` | Cross-Bot filesystem, network, browser, credential, audit-write, process-inspection, and approval use all fail |
| SCAN-01 | `tests/security/run-policy-acceptance.sh --case SCAN-01 --target test-worker` | Tracked files, Git history, issues evidence, generated config, logs, and test artifacts contain no seeded canary or recognized secret/private-key/cookie pattern |

Before production activation, run:

```sh
set -eu
tests/security/run-policy-acceptance.sh --target test-worker --destructive-fixture
tests/security/run-policy-acceptance.sh --target laptop-worker --destructive-fixture
tests/security/run-policy-acceptance.sh --target chief
git diff --check
tests/security/check-repository-consistency.sh
```

The consistency check must report no stale markers, unresolved documentation sentinels outside fenced schema examples, secret-shaped values, private keys, exported cookies, or credential-bearing URLs. It scans tracked files, history, generated configuration, logs, and test artifacts with entropy and provider-specific detectors. Acceptance evidence records test IDs, versions, policy commit, sanitized event IDs, and pass/fail only. A skipped mandatory test is a failure.
