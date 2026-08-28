# Secure Mac file-access architecture

Status: recommendation for [Determine the secure Mac file-access architecture](https://github.com/JohanSardar/hermes-bot-fleet/issues/5)  
Date: 2026-08-27  
Scope: online access from the Azure Ubuntu Server Runtime to explicitly approved folders on the macOS Laptop Runtime

## Decision

Adopt two stages, in this order:

1. **Native Laptop Worker first.** Run a dedicated `laptop-worker` Bot on the Mac. The Chief sends a bounded job to that Bot; the job executes locally using only user-approved folders and returns a result. The Server Runtime never receives a general Mac shell or filesystem mount. This is the default path because the Laptop Worker can show local approvals and keep Mac-only authority on the Mac.
2. **Direct scoped MCP File Bridge second.** Add a purpose-built, signed, sandboxed macOS File Bridge only after the Laptop Worker acceptance tests pass and direct low-latency file operations are demonstrably needed. Connect Hermes on Azure to it with MCP Streamable HTTP over a private Tailscale path. Expose only narrow file tools, not shell execution.

Both stages use the same local policy engine, approved-root registry, mutation approval service, path resolver, operation ledger, and audit sink. The MCP bridge is another caller of that policy engine, not a broader bypass.

Do **not** use SMB/NFS/SFTP mounts, SSH command execution, a generic filesystem MCP package, or a remotely accessible Hermes terminal as the long-term File Bridge. Those options place too much authority on the server and cannot provide the required local, operation-bound approvals.

## Exact topology

```text
Azure Ubuntu                                    macOS laptop
+----------------------+                        +--------------------------------+
| Chief / Server Bots  |                        | laptop-worker Hermes profile   |
|                      |  bounded job/result    | (phase 1, local execution)     |
|                      |<======================>|              |                 |
| Hermes MCP client    |                        |              v                 |
| (phase 2 only)       |-- Tailscale + mTLS --->| File Bridge policy service     |
+----------------------+  Streamable HTTP /mcp  | - approved bookmark roots      |
                                                 | - descriptor-relative resolver |
                                                 | - local approval UI            |
                                                 | - operation/audit ledger        |
                                                 +--------------------------------+
```

Network reachability is one-way: only the tagged Azure Server Runtime may initiate TCP connections to the File Bridge port on the tagged Mac. The bridge has no public listener, router port-forward, Funnel, public DNS endpoint, or LAN listener. Tailscale is a network gate, not the application authorization decision.

### Phase 1: native Laptop Worker

- Create a dedicated Hermes profile and OS launch service for `laptop-worker`; profile separation controls Bot state but is **not** an OS security boundary.
- Run file actions through the signed/sandboxed local policy service. Do not give the Laptop Worker unrestricted `terminal`, built-in file tools over `$HOME`, Full Disk Access, Accessibility, Keychain access, or browser automation merely to satisfy a file job.
- The Chief sends a structured job containing `job_id`, operation, logical `root_id`, relative path(s), constraints, expiry, and reply route. Absolute Mac paths are not accepted.
- Prefer an outbound pull/long-poll from the Laptop Worker to the authenticated fleet control plane. If an inbound Hermes endpoint is used, it receives the same private-network and application-auth controls as phase 2 and exposes only the job API.
- Reads may run without a second prompt only inside roots that the user has explicitly approved for read access. Every create, modify, rename, move, permission change, or deletion requires a Mac-local approval.
- Results identify the operation and outcome; large or sensitive file contents are not copied into chat unless that was the explicit approved job.

### Phase 2: scoped MCP File Bridge

Use the MCP `2026-07-28` Streamable HTTP transport: one HTTPS `/mcp` endpoint, one POST per JSON-RPC message, and JSON or request-scoped SSE responses. Do not start a new implementation on deprecated HTTP+SSE. Validate `Origin` on every request and reject an absent or unexpected origin according to a documented non-browser-client policy; the MCP specification requires rejecting an invalid supplied Origin and recommends authentication for every connection.[^mcp-transport]

Expose a deliberately small tool set:

- `roots_list` — logical root IDs, display names, and capabilities; never physical paths.
- `file_stat`, `directory_list`, `file_read_range`, `file_search` — bounded read-only operations.
- `mutation_prepare` — validates an explicit mutation manifest and creates a local approval request.
- `mutation_status` — returns `pending`, `approved`, `denied`, `expired`, `committed`, `failed`, or `indeterminate`.
- `mutation_commit` — executes exactly one approved manifest, idempotently.

Do not expose arbitrary command execution, arbitrary URL fetch, globbed deletion, recursive deletion by default, unrestricted copy/move, chmod/chown, xattr manipulation, package execution, MCP sampling, MCP elicitation, prompts, or server-initiated access to any other Hermes tools. Configure Hermes with an explicit per-server tool include list. Hermes supports remote HTTP MCP servers, mTLS/static auth, tool filtering, and automatic discovery; disable sampling for this bridge.[^hermes-mcp]

MCP Roots may be reported for usability, but they are not the security boundary. The current MCP specification explicitly describes Roots as informational guidance rather than an enforced access-control mechanism.[^mcp-roots] The bridge must enforce its own approved-root policy on every operation.

## Identity and authentication

Use independent layers:

1. **Network identity:** tag the Azure node `tag:server-runtime` and the Mac `tag:laptop-runtime`. A deny-by-default Tailscale Grant permits only the Azure tag to reach the single File Bridge TCP port. Add policy tests proving other users/devices and all other ports are denied. Tailscale Grants are the recommended deny-by-default mechanism and can restrict source, destination, protocol, and port.[^tailscale-grants]
2. **Transport security:** TLS on the MCP endpoint. WireGuard already protects tailnet traffic, but TLS gives the MCP client normal HTTPS semantics and server authentication. If using a `*.ts.net` certificate, account for certificate renewal and the fact that machine names enter Certificate Transparency logs.[^tailscale-https]
3. **Application identity:** mutual TLS with a dedicated server-client certificate issued only for this bridge. Pin the private CA/public key at both ends, require the expected client identity, use short certificate lifetimes, and maintain an explicit revocation/rotation procedure. Do not reuse SSH, GitHub, Hermes provider, or Tailscale account credentials.
4. **Authorization:** map the authenticated client certificate to one bridge principal and evaluate `{principal, tool, root_id, relative_path, operation}` locally. Tailscale reachability never implies file authorization.

Do not rely solely on Tailscale Serve identity headers: they are proxy-supplied application context, and Tailscale documents that identity headers are populated for users, not tagged devices.[^tailscale-identity] If Serve is used, the backend must listen only on loopback so callers cannot forge proxy headers; mTLS authorization remains authoritative.

No credential value belongs in this repository, Hermes prompts, approval text, audit events, or MCP errors. Keep private keys in OS-protected storage with restrictive ACLs. Hermes's MCP client supports mTLS and security-sensitive configuration, but secret redaction is defense in depth, not permission to log secrets.[^hermes-mcp]

## Approved roots and permanent denials

The bridge is a sandboxed, hardened-runtime macOS app/helper. The user adds each root with `NSOpenPanel`; the app stores a security-scoped bookmark in its protected container and records a random `root_id`, display name, read/write capability, and stable volume/file identity. Apple documents security-scoped bookmarks as the mechanism for persistent access selected by a user in a sandboxed app.[^apple-sandbox]

A root is accepted only if it is a dedicated work folder. Reject `/`, the home directory, `~/Library`, any hidden configuration root, removable/network volumes unless separately enabled, and any selected directory that equals, contains, or is contained by a permanent-deny location.

Permanent denials apply before allowlist evaluation and cannot be overridden through UI, config, MCP Roots, an approval, or a server role:

- macOS Keychains and credential stores, including `~/Library/Keychains`.
- SSH/GPG/cloud/developer credentials, including `~/.ssh`, `~/.gnupg`, `~/.aws`, `~/.azure`, `~/.config/gcloud`, `~/.kube`, `.env` credential stores, and Hermes `.env`, `auth.json`, or equivalent auth stores.
- Browser profiles and exported browser state, including Safari data and Chrome/Chromium/Firefox/Edge/Arc profile trees under `~/Library`.
- Mail, Messages, Contacts, Photos libraries, cookies, exported cookies, password-manager vaults, and token databases.
- `/System`, `/Library`, `/private`, other users' homes, app containers outside this bridge, and the bridge's own policy, key, approval, and audit stores.

Also deny sensitive basenames and extensions (`.env`, `.netrc`, private-key formats, cookie databases) anywhere under an otherwise allowed root. This content-oriented rule is intentionally conservative. A dedicated work folder avoids confusing exceptions.

Do not grant Full Disk Access. App Sandbox and macOS privacy controls provide an additional boundary if policy code fails. A root bookmark gives hierarchy-wide access, so broad selections must be rejected rather than trying to repair them with a denylist alone.[^apple-file-permissions]

## Path resolution and symlink defenses

The wire format accepts only UTF-8 relative path components under a `root_id`. Reject empty components, absolute paths, `.`/`..`, NUL/control characters, alternate separators, overlong paths, and Unicode that does not match the chosen normalization. Never expand `~`, environment variables, shell syntax, Finder aliases, or URLs.

For **every** operation:

1. Resolve the root's security-scoped bookmark, reject stale/unavailable bookmarks, open the root directory, and verify its recorded volume ID and file ID.
2. Walk each path component relative to that open root descriptor (`openat`-style), opening intermediate directories with `O_DIRECTORY | O_NOFOLLOW`. On supported macOS versions use `O_NOFOLLOW_ANY` as an additional fast-fail defense, but retain component-by-component checks.
3. `fstat` every opened descriptor. Reject symlinks, mount/device changes, non-regular-file/non-directory types, and regular files with multiple hard links. Never perform the operation later by reusing a string path.
4. Enforce the permanent deny rules and root policy against the logical path and the descriptor-resolved object before reading or mutating.
5. Read and write only through the verified descriptor. Apple documents that `O_NOFOLLOW` causes opening a symlink to fail.[^apple-nofollow]

For creation, open and retain the verified parent directory descriptor, use an unpredictable same-directory temporary file with exclusive creation, set restrictive mode, write and `fsync`, revalidate the destination, and atomically `renameat` only after approval. Overwrite is a distinct approved action. For deletion/rename, bind approval to parent/target file IDs and revalidate immediately before the descriptor-relative operation. Abort if any identity, metadata, policy version, or content digest differs.

This prevents lexical-prefix bugs (`/approved` versus `/approved-old`), `..` traversal, symlink escapes, and common check-then-use races. Canonicalizing a string with `realpath` and then opening it later is insufficient.

## Local approvals and mutation semantics

All mutations are fail-closed and locally approved on the Mac. A remote Bot cannot approve its own request.

`mutation_prepare` produces a normalized manifest containing:

- request/operation ID and authenticated principal;
- root display name and relative paths;
- action and whether it creates, overwrites, renames, or deletes;
- byte count plus SHA-256 digest or a human-readable bounded diff for writes;
- current target identity/digest, policy version, expiry, and idempotency key.

The Mac UI shows that manifest and offers Deny or biometric/user-presence approval. Approval is single-use, expires quickly (recommended: five minutes), and is cryptographically bound to the exact manifest. Any changed path, bytes, target identity, operation, principal, or policy requires a new approval.

- No “approve all”, wildcard, recursive, background, or permanent mutation approval.
- A batch must enumerate every path and have strict item/byte limits; recursive delete is unsupported initially.
- `mutation_commit` is idempotent. The ledger stores the final result before acknowledging it.
- A disconnect does not imply rollback or success. After reconnect, the caller checks `mutation_status` by idempotency key and never blindly repeats a mutation.
- Approval of a write never authorizes reading a pre-existing sensitive destination or returning old content.

## Audit design

Write a structured event for authentication, policy decision, approval request/decision, operation start, and terminal outcome. Include timestamp, monotonic sequence, request/job ID, principal/certificate fingerprint, Tailscale peer identity if independently obtained, tool/action, logical root ID, redacted relative path or path HMAC, byte count/digest, policy version, approval actor/presence result, outcome, error class, and previous-event hash.

Never log file contents, diffs containing content, absolute home paths, bookmark blobs, access tokens, private keys, approval secrets, or unredacted credential-like values.

Store the append-only hash-chained JSONL ledger in the bridge's sandbox container with restrictive permissions, rotate by size/time, and periodically ship signed checkpoints to the Server Runtime's central log store. The server copy is useful for tamper evidence but does not replace the local record. Protect retention/deletion behind a separate local administrative action. Alert on repeated denials, authentication failures, denylist hits, stale bookmark changes, and audit-write failure. If the mandatory audit event cannot be durably written, reject the file operation.

## Offline and disconnect behavior

The Laptop Runtime is an online-only capability:

- When the Mac sleeps, exits Tailscale, revokes its root bookmark, or the bridge health check fails, the Server Runtime reports `laptop_unavailable`; it does not mount stale data or silently fall back to another channel.
- Do not queue reads or mutations for automatic replay. The user/server must resubmit after reconnect with a new expiry; pending approvals expire.
- Cancel work that has not crossed the atomic commit point. If transport loss occurs during commit, record `indeterminate` remotely until `mutation_status` reconciles against the local ledger.
- Never return cached file content as though it were current. Metadata caches must be labeled stale and must not authorize an operation.
- On restart, recover only ledger state: complete or roll back safe temporary-file cleanup, preserve committed idempotency results, and never auto-commit an approved-but-uncommitted mutation.
- Removing a root or revoking the client identity takes effect immediately and invalidates pending operations.

## Threat model

| Threat | Required control |
|---|---|
| Compromised/prompt-injected Server Bot | No shell; narrow tools; local policy; Mac-local single-use mutation approval; size/rate limits |
| Compromised tailnet peer | Deny-by-default port Grant plus mTLS principal authorization |
| Stolen/replayed client credential | Short-lived dedicated cert, pinning, revocation, request IDs/idempotency, no bearer credential in logs |
| Path traversal or symlink swap | Logical roots, strict components, descriptor-relative walk, no-follow flags, `fstat` and pre-commit identity checks |
| Accidental broad folder selection | Native picker plus rejection of broad/ancestor/sensitive roots; App Sandbox; no Full Disk Access |
| Credential/browser exfiltration | Permanent deny evaluated before allowlist; sensitive basename deny; dedicated work roots; no browser profile tools |
| Destructive or disguised write | Exact manifest, digest/diff, local user presence, atomic write, no recursive/wildcard delete |
| Laptop disconnect during mutation | Idempotency ledger and explicit reconciliation; never blind retry |
| Local audit tampering | Restricted local store, hash chain, signed remote checkpoints, fail closed on audit failure |
| Malicious unprivileged local process | Sandboxed service, authenticated IPC, dedicated storage, descriptor checks, signed app/helper |

Out of scope: a root/admin compromise of macOS, a compromised kernel, or physical access after the user has unlocked the laptop can defeat an app-level bridge. FileVault, rapid OS patching, screen lock, Secure Enclave-backed keys, and endpoint security reduce but do not remove that risk.

## Deployment and verification plan

### Stage 0 — policy service

1. Build/sign/notarize the sandboxed local helper and approval UI; run it as the logged-in user, not root.
2. Implement approved bookmarks, hard permanent denials, descriptor-relative resolver, mutation ledger, and audit sink.
3. Start with one disposable dedicated test root and read-only operations.
4. Unit/fuzz test path normalization, Unicode, traversal, symlink races, hard links, mount swaps, stale bookmarks, and denylist ancestors/descendants.

Acceptance gates (must produce retained test evidence):

- Allowed read succeeds; sibling and parent reads fail.
- Every permanent-deny fixture fails even when reached through a symlink, renamed parent, hard link, or a deliberately over-broad root selection.
- A continuously swapped symlink never escapes during a stress test.
- No mutation executes before a local approval; changed bytes/path/target after approval fail.
- Duplicate commit returns one recorded outcome and performs one mutation.
- Audit failure causes operation failure, and audit entries contain no fixture secret.

### Stage 1 — Laptop Worker

1. Create the dedicated profile with only the job tools and local policy-service IPC.
2. Use private authenticated job transport and expiring, idempotent job envelopes.
3. Verify Mac asleep/offline, reconnect, root revocation, approval expiry, duplicate job, and mid-commit disconnect behavior.
4. Run a pilot for at least a week. Keep direct MCP disabled until logs show the task model is insufficient.

### Stage 2 — MCP File Bridge

1. Add Streamable HTTP, strict Origin/Host validation, TLS/mTLS, request/body/time/rate limits, and Tailscale-only binding/firewalling.
2. Add a Tailscale Grant for exactly Azure tag -> Mac tag -> one TCP port, with positive and negative policy tests.
3. Configure Hermes `mcp_servers` with the private HTTPS URL, client cert/key, CA verification, `sampling.enabled: false`, and an explicit include list for the seven tools. Store key paths/values outside Git; run `hermes mcp test` and inspect the discovered tools.[^hermes-mcp]
4. Test from the tagged Azure node, an unauthorized tailnet node, the LAN, and the public internet. Only the first may complete mTLS and invoke an allowed read.
5. Test malformed JSON-RPC, invalid/missing auth, invalid Origin/Host, oversized payloads, slow requests, cancellation, version negotiation, and bridge restart.
6. Re-run all Stage 0 tests through MCP and verify local and central audit correlation by request ID.

### Operational checks

- Quarterly: access review, root review, negative Tailscale policy test, restore/reconciliation drill, certificate revocation drill, dependency update, and audit-secret scan.
- On every release: code signing/notarization verification, sandbox entitlement diff, tool-schema snapshot, path-race test, and denial corpus.
- Treat any new tool or approved root as a security change requiring review and acceptance tests.

## Alternatives considered

| Alternative | Decision | Reason |
|---|---|---|
| Native Laptop Worker only | Keep as default and possibly final state | Best local context and approvals; adequate unless fine-grained synchronous access is proven necessary |
| Generic `@modelcontextprotocol/server-filesystem` on Mac | Reject for production | Useful reference/prototype, but MCP Roots are not a protocol security boundary and the generic mutation surface lacks the required Mac-local approvals and permanent denials |
| SSH/SFTP/rsync from Azure | Reject as bridge | Broad account/filesystem authority, difficult per-operation approval, and easy accidental expansion to shell access |
| SMB/NFS/SSHFS/Tailscale Drive-style mount | Reject | Makes offline/stale and write semantics opaque and moves too much authority into the Server Runtime |
| Tailscale Serve identity alone | Reject as sole auth | Network/proxy identity is not operation authorization; tagged-device identity-header limitations and header-spoofing risk at a non-loopback backend |
| Public HTTPS with OAuth bearer tokens | Reject | Violates the private-endpoint rule and increases token theft/replay and internet attack surface; MCP OAuth is optional, while this two-node deployment is better served by mTLS over Tailscale[^mcp-auth] |
| macOS File Sharing or Full Disk Access | Reject | Cannot enforce dedicated roots/permanent denials and materially worsens compromise impact |
| Server-side copy/synchronization of Mac folders | Reject as live access | Creates uncontrolled replicas and stale-data ambiguity; use explicit approved export jobs if copying is actually desired |

## Sources

[^hermes-mcp]: Nous Research, [Hermes Agent — MCP](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp) (remote HTTP, mTLS/static headers, identity headers, per-server tool filters, sampling controls, testing/configuration).
[^mcp-transport]: Model Context Protocol, [Streamable HTTP, 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http) (POST transport, JSON/SSE responses, Origin validation, authentication, cancellation, and HTTP+SSE deprecation).
[^mcp-auth]: Model Context Protocol, [Authorization, 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization) (HTTP authorization is optional; when used, OAuth resource-server requirements and least-privilege scopes apply).
[^mcp-roots]: Model Context Protocol, [Roots, 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/client/roots) (Roots are informational, not enforced access control; clients must validate URIs and implement controls).
[^mcp-security]: Model Context Protocol, [Security Best Practices](https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices) (token audience validation, least privilege, and confused-deputy/SSRF defenses).
[^tailscale-grants]: Tailscale, [Grants](https://tailscale.com/docs/features/access-control/grants) (deny-by-default source/destination and port/protocol controls; Grants preferred over legacy ACLs).
[^tailscale-https]: Tailscale, [Enabling HTTPS](https://tailscale.com/docs/how-to/set-up-https-certificates) (tailnet encryption, certificate issuance/renewal, and Certificate Transparency implications).
[^tailscale-identity]: Tailscale, [Tailscale identity](https://tailscale.com/docs/concepts/tailscale-identity) and [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve) (Serve identity headers and tagged-device limitation).
[^apple-sandbox]: Apple, [App Sandbox Design Guide — Security-Scoped Bookmarks and Persistent Resource Access](https://developer.apple.com/library/archive/documentation/Security/Conceptual/AppSandboxDesignGuide/AppSandboxInDepth/AppSandboxInDepth.html#//apple_ref/doc/uid/TP40011183-CH3-SW16).
[^apple-file-permissions]: Apple Developer Forums, [On File System Permissions](https://developer.apple.com/forums/thread/678819) (directory grants generally cover the hierarchy and persistent sandbox access uses security-scoped bookmarks).
[^apple-nofollow]: Apple, [`FileDescriptor.OpenOptions.noFollow`](https://developer.apple.com/documentation/system/filedescriptor/openoptions/nofollow) and [`open(2)`](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/open.2.html) (`O_NOFOLLOW` rejects a symbolic-link target).
