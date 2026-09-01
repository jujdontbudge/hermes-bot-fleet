#!/usr/bin/env python3
"""Fail-closed browser ownership, signed takeover grants, and private gates."""
from __future__ import annotations

import argparse
import base64
import contextlib
import datetime as dt
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import select
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from typing import Callable

STATES = {"AUTOMATION", "DRAINING", "HUMAN", "RECOVERING"}
BOTS = {"chief": 6081, "test-worker": 6082}
MAX_HUMAN_SECONDS = 600
AUTOMATION_SECONDS = 86_400
BOOT_ID = Path("/proc/sys/kernel/random/boot_id").read_text().strip() if Path("/proc/sys/kernel/random/boot_id").exists() else "test-boot"


class LeaseError(RuntimeError):
    pass


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _wall() -> float:
    return time.time()


def _mono_ns() -> int:
    return time.monotonic_ns()


def _digest(value: str | bytes) -> str:
    if isinstance(value, str):
        value = value.encode()
    return hashlib.sha256(value).hexdigest()


def _canonical(data: dict) -> bytes:
    # RFC 8785 for this locked schema: member names and accepted string values
    # are ASCII, numbers are integers, and non-finite/floating values are absent.
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _read_state(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"state": "RECOVERING", "lease_generation": 0, "boot_id": BOOT_ID}
    if data.get("state") not in STATES:
        return {"state": "RECOVERING", "lease_generation": int(data.get("lease_generation", 0)), "boot_id": BOOT_ID}
    return data


def _not_expired(data: dict) -> bool:
    return data.get("boot_id") == BOOT_ID and int(data.get("expires_monotonic_ns", 0)) > _mono_ns()


def _state_allows(path: Path, wanted: str) -> bool:
    data = _read_state(path)
    return data.get("state") == wanted and _not_expired(data)


def _profile_fingerprint(bot: str) -> str:
    path = Path(f"/var/lib/hermes-bots/{bot}/browser/profile").resolve(strict=True)
    st = path.stat()
    return _digest(f"{path}:{st.st_dev}:{st.st_ino}:{st.st_uid}:{st.st_gid}:{st.st_mode & 0o777}")


class GrantVerifier:
    """Verify the locked RFC 8032/RFC 8785 single-use approval grant."""

    GRANT_FIELDS = {
        "schema_version", "grant_id", "manifest_sha256", "nonce_sha256", "approver", "channel",
        "authority_context", "issued_at", "expires_at", "max_uses", "policy_revision",
        "signing_key_id", "signature",
    }
    AUTHORITY_FIELDS = {"channel_instance_id_digest", "approval_session_id_digest", "device_identity_digest"}
    MANIFEST_FIELDS = {
        "schema_version", "action", "bot", "runtime", "browser_profile_id_digest", "reason",
        "requested_duration_seconds", "current_lease_nonce_digest", "expected_transition", "side_effect",
    }

    def __init__(self, bot: str, trust_path: Path, consumed_dir: Path):
        self.bot = bot
        self.trust_path = trust_path
        self.consumed_dir = consumed_dir

    @staticmethod
    def _decode_prefixed(value: str, prefix: str, expected_len: int) -> bytes:
        if not isinstance(value, str) or not value.startswith(prefix):
            raise LeaseError("approval encoding prefix mismatch")
        try:
            decoded = base64.b64decode(value[len(prefix):], validate=True)
        except Exception as exc:
            raise LeaseError("approval base64 invalid") from exc
        if len(decoded) != expected_len:
            raise LeaseError("approval encoded length invalid")
        return decoded

    @classmethod
    def _verify(cls, public_text: str, signature_text: str, payload: dict, domain: bytes) -> None:
        public = cls._decode_prefixed(public_text, "ed25519:", 32)
        signature = cls._decode_prefixed(signature_text, "ed25519:", 64)
        message = domain + _canonical(payload)
        try:
            try:
                from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
                Ed25519PublicKey.from_public_bytes(public).verify(signature, message)
            except ModuleNotFoundError:
                from Crypto.Signature import eddsa
                eddsa.new(eddsa.import_public_key(public), "rfc8032").verify(message, signature)
        except Exception as exc:
            raise LeaseError("invalid approval signature") from exc

    @staticmethod
    def _time(value: str) -> float:
        if not isinstance(value, str) or not value.endswith("Z"):
            raise LeaseError("approval timestamp is not canonical UTC")
        try:
            return dt.datetime.fromisoformat(value[:-1] + "+00:00").timestamp()
        except ValueError as exc:
            raise LeaseError("approval timestamp invalid") from exc

    @staticmethod
    def _prefixed_digest(value: str) -> str:
        return "sha256:" + _digest(value)

    def _verify_certificate(self, trust: dict, signing_key_id: str, now: float, issued: float) -> dict:
        root_text = trust.get("root_public_key", "")
        root_raw = self._decode_prefixed(root_text, "ed25519:", 32)
        if trust.get("root_public_key_fingerprint") != "sha256:" + _digest(root_raw):
            raise LeaseError("approval root fingerprint mismatch")
        rotation = trust.get("root_rotation", {})
        if rotation.get("current_fingerprint") != trust.get("root_public_key_fingerprint"):
            raise LeaseError("approval root rotation state invalid")
        if rotation.get("predecessor_fingerprint") is not None:
            predecessor = rotation.get("predecessor_public_key", "")
            predecessor_raw = self._decode_prefixed(predecessor, "ed25519:", 32)
            if rotation.get("predecessor_fingerprint") != "sha256:" + _digest(predecessor_raw):
                raise LeaseError("approval predecessor root fingerprint mismatch")
            crosses = rotation.get("cross_certificates", [])
            if len(crosses) != 2:
                raise LeaseError("approval root cross-certification missing")
            seen = set()
            for cross in crosses:
                if set(cross) != {"payload", "signature"}:
                    raise LeaseError("approval root cross-certificate shape invalid")
                cp = cross["payload"]
                direction = (cp.get("from_fingerprint"), cp.get("to_fingerprint"))
                if direction == (rotation["current_fingerprint"], rotation["predecessor_fingerprint"]):
                    self._verify(root_text, cross["signature"], cp, b"fleet-approval-root-cross-cert-v1\0")
                elif direction == (rotation["predecessor_fingerprint"], rotation["current_fingerprint"]):
                    self._verify(predecessor, cross["signature"], cp, b"fleet-approval-root-cross-cert-v1\0")
                else:
                    raise LeaseError("approval root cross-certificate direction invalid")
                seen.add(direction)
            if len(seen) != 2:
                raise LeaseError("approval root cross-certification incomplete")
        certificates = trust.get("certificates", {})
        allowed_keys = {trust.get("active_signing_key_id")}
        if trust.get("predecessor_signing_key_id") is not None:
            allowed_keys.add(trust.get("predecessor_signing_key_id"))
        if signing_key_id not in allowed_keys or set(certificates) != allowed_keys:
            raise LeaseError("unknown or extra approval signing key")
        cert = certificates[signing_key_id]
        if set(cert) != {"payload", "signature"}:
            raise LeaseError("approval certificate shape invalid")
        payload = cert["payload"]
        expected = {"schema_version", "signing_key_id", "public_key", "environment", "purpose", "not_before", "not_after", "predecessor_key_id"}
        if set(payload) != expected or payload.get("schema_version") != "1.0":
            raise LeaseError("approval certificate payload invalid")
        self._verify(root_text, cert["signature"], payload, b"fleet-approval-cert-v1\0")
        if payload.get("signing_key_id") != signing_key_id or payload.get("purpose") != "fleet-approval-grant-v1" or payload.get("environment") != trust.get("environment"):
            raise LeaseError("approval certificate scope mismatch")
        if not self._time(payload["not_before"]) <= now <= self._time(payload["not_after"]):
            raise LeaseError("approval certificate expired")
        if signing_key_id == trust.get("active_signing_key_id") and payload.get("predecessor_key_id") != trust.get("predecessor_signing_key_id"):
            raise LeaseError("active approval predecessor mismatch")
        if signing_key_id == trust.get("predecessor_signing_key_id") and payload.get("signing_key_id") != signing_key_id:
            raise LeaseError("retained predecessor certificate mismatch")
        for revocation in trust.get("revocations", []):
            if set(revocation) != {"payload", "signature"}:
                raise LeaseError("approval revocation shape invalid")
            rp = revocation["payload"]
            self._verify(root_text, revocation["signature"], rp, b"fleet-approval-revocation-v1\0")
            if rp.get("signing_key_id") == signing_key_id and issued >= self._time(rp["effective_at"]):
                raise LeaseError("approval signing key revoked")
        return payload

    def _clock_guard(self, now: float) -> None:
        clock_path = self.consumed_dir.parent / "approval-clock.json"
        last = 0.0
        try:
            last = float(json.loads(clock_path.read_text()).get("last_wall_time", 0))
        except (OSError, ValueError, TypeError):
            pass
        if now + 1.0 < last:
            raise LeaseError("approval wall clock rollback")
        fd, tmp = tempfile.mkstemp(prefix="clock-", dir=clock_path.parent)
        with os.fdopen(fd, "w") as fh:
            json.dump({"last_wall_time": max(now, last), "updated_at": _now()}, fh, sort_keys=True)
            fh.write("\n"); fh.flush(); os.fsync(fh.fileno())
        os.chmod(tmp, 0o600); os.replace(tmp, clock_path)

    def __call__(self, grant_source: object, current: dict) -> dict:
        if not (isinstance(grant_source, tuple) and len(grant_source) == 4 and all(isinstance(x, Path) for x in grant_source)):
            raise LeaseError("takeover requires grant, manifest, nonce, and credential-output paths")
        grant_path, manifest_path, nonce_path, credential_out = grant_source
        for path in (grant_path, manifest_path, nonce_path):
            if path.stat().st_mode & 0o077:
                raise LeaseError("approval input permissions are too broad")
        try:
            grant = json.loads(grant_path.read_text())
            manifest = json.loads(manifest_path.read_text())
            raw_nonce = base64.b64decode(nonce_path.read_text().strip(), validate=True)
            trust = json.loads(self.trust_path.read_text())
        except (OSError, ValueError, KeyError) as exc:
            raise LeaseError("unreadable approval input") from exc
        finally:
            for path in (grant_path, manifest_path, nonce_path):
                with contextlib.suppress(OSError):
                    path.unlink()
        if set(grant) != self.GRANT_FIELDS or grant.get("schema_version") != "1.0":
            raise LeaseError("locked approval grant shape mismatch")
        if set(grant.get("authority_context", {})) != self.AUTHORITY_FIELDS:
            raise LeaseError("approval authority context shape mismatch")
        if set(manifest) != self.MANIFEST_FIELDS or manifest.get("schema_version") != "1.0":
            raise LeaseError("browser takeover manifest shape mismatch")
        unsigned = {k: v for k, v in grant.items() if k != "signature"}
        now = _wall(); received_mono = _mono_ns()
        issued = self._time(grant["issued_at"]); expires = self._time(grant["expires_at"])
        self._clock_guard(now)
        cert = self._verify_certificate(trust, grant["signing_key_id"], now, issued)
        self._verify(cert["public_key"], grant["signature"], unsigned, b"fleet-approval-grant-v1\0")
        if grant["approver"] != "human:johan" or grant["channel"] not in trust.get("eligible_channels", []):
            raise LeaseError("approval principal or channel denied")
        authority = grant["authority_context"]
        for key in ("channel_instance_id_digest", "approval_session_id_digest"):
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", authority[key] or ""):
                raise LeaseError("approval authority context missing")
        device = authority["device_identity_digest"]
        if device is not None and device not in trust.get("approved_device_identity_digests", []):
            raise LeaseError("approval device denied")
        if not issued <= now <= expires or expires - issued > 60 or _mono_ns() - received_mono > 60_000_000_000:
            raise LeaseError("browser takeover grant expired")
        if grant["max_uses"] != 1 or grant["policy_revision"] != trust.get("policy_revision") or not re.fullmatch(r"git:[0-9a-f]{40}", grant["policy_revision"]):
            raise LeaseError("approval use count or policy mismatch")
        try:
            import uuid
            uuid.UUID(grant["grant_id"])
        except (ValueError, AttributeError) as exc:
            raise LeaseError("approval grant id invalid") from exc
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", grant["manifest_sha256"]) or not re.fullmatch(r"sha256:[0-9a-f]{64}", grant["nonce_sha256"]):
            raise LeaseError("approval digest encoding invalid")
        if len(raw_nonce) != 32 or grant["nonce_sha256"] != "sha256:" + _digest(raw_nonce):
            raise LeaseError("approval nonce mismatch")
        if grant["manifest_sha256"] != "sha256:" + _digest(_canonical(manifest)):
            raise LeaseError("approval manifest digest mismatch")
        duration = int(manifest["requested_duration_seconds"])
        if not isinstance(manifest.get("reason"), str) or not re.fullmatch(r"[ -~]{1,256}", manifest["reason"]):
            raise LeaseError("browser takeover reason must be bounded ASCII")
        expected_manifest = {
            "schema_version": "1.0", "action": "browser-takeover", "bot": self.bot, "runtime": "azure-server",
            "browser_profile_id_digest": "sha256:" + _profile_fingerprint(self.bot), "reason": manifest["reason"],
            "requested_duration_seconds": duration,
            "current_lease_nonce_digest": "sha256:" + str(current.get("automation_nonce_sha256", "")),
            "expected_transition": ["AUTOMATION", "DRAINING", "HUMAN"], "side_effect": "exclusive-browser-input",
        }
        if manifest != expected_manifest or duration < 1 or duration > MAX_HUMAN_SECONDS:
            raise LeaseError("approval target or manifest changed")
        if credential_out.exists() or credential_out.parent.resolve() != self.consumed_dir.parent.resolve():
            raise LeaseError("takeover credential destination denied")
        self.consumed_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        record = self.consumed_dir / f"{grant['grant_id']}.{grant['nonce_sha256'][7:]}"
        try:
            fd = os.open(record, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise LeaseError("approval grant already consumed") from exc
        with os.fdopen(fd, "w") as fh:
            json.dump({"grant_id": grant["grant_id"], "nonce_sha256": grant["nonce_sha256"], "consumed_at": _now()}, fh, sort_keys=True)
            fh.write("\n"); fh.flush(); os.fsync(fh.fileno())
        approval_audit = self.consumed_dir.parent / "approval-audit.jsonl"
        afd = os.open(approval_audit, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(afd, "a") as fh:
            fh.write(json.dumps({"at": _now(), "event": "approval.consumed", "grant_id": grant["grant_id"], "nonce_sha256": grant["nonce_sha256"], "manifest_sha256": grant["manifest_sha256"]}, sort_keys=True) + "\n")
            fh.flush(); os.fsync(fh.fileno())
        dir_fd = os.open(self.consumed_dir, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
        credential = secrets.token_urlsafe(32)
        cfd = os.open(credential_out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(cfd, "w") as fh:
            fh.write(credential + "\n"); fh.flush(); os.fsync(fh.fileno())
        return {"grant_id": grant["grant_id"], "duration_seconds": duration, "human_identity": grant["approver"],
                "device_identity_digest": device, "takeover_credential_sha256": _digest(credential),
                "credential_path": str(credential_out)}


class LeaseMachine:
    def __init__(self, bot: str, state_path: Path, recovery_probe: Callable[[], bool],
                 drain_probe: Callable[[], bool] | None = None, boot: bool = True,
                 approval_verifier: Callable[[object, dict], dict] | None = None) -> None:
        if bot not in BOTS:
            raise LeaseError("unknown bot")
        self.bot = bot
        self.path = Path(state_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.path.with_suffix(".lock")
        self.audit_path = self.path.parent / "audit.jsonl"
        self.recovery_probe = recovery_probe
        self.drain_probe = drain_probe or (lambda: True)
        self.approval_verifier = approval_verifier
        if boot:
            with self._locked():
                current = _read_state(self.path)
                self._write(self._recovering(current, "supervisor-start-fail-closed"))
                self._audit("BOOT_RECOVERING", "supervisor-start-fail-closed")

    @contextlib.contextmanager
    def _locked(self):
        self.lock_path.touch(mode=0o600, exist_ok=True)
        with self.lock_path.open("r+") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    def _write(self, data: dict) -> None:
        fd, tmp = tempfile.mkstemp(prefix="lease-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(data, fh, sort_keys=True); fh.write("\n"); fh.flush(); os.fsync(fh.fileno())
            os.chmod(tmp, 0o600); os.replace(tmp, self.path)
            dir_fd = os.open(self.path.parent, os.O_RDONLY)
            try: os.fsync(dir_fd)
            finally: os.close(dir_fd)
        finally:
            with contextlib.suppress(FileNotFoundError): os.unlink(tmp)

    def _audit(self, event: str, reason: str, details: dict | None = None) -> None:
        safe: dict[str, object] = {"at": _now(), "bot": self.bot, "event": event, "reason": reason}
        if details:
            safe["details"] = details
        fd = os.open(self.audit_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as fh:
            fh.write(json.dumps(safe, sort_keys=True) + "\n"); fh.flush(); os.fsync(fh.fileno())

    @staticmethod
    def _recovering(current: dict, reason: str) -> dict:
        return {"state": "RECOVERING", "lease_generation": int(current.get("lease_generation", 0)),
                "boot_id": BOOT_ID, "expires_monotonic_ns": _mono_ns() + 300_000_000_000,
                "updated_at": _now(), "reason": reason}

    def force_recovering(self, reason: str) -> dict:
        with self._locked():
            current = _read_state(self.path); data = self._recovering(current, reason)
            self._write(data); self._audit("FORCED_RECOVERING", reason); return data

    def status(self) -> dict:
        with self._locked():
            data = _read_state(self.path)
            if data.get("state") in {"AUTOMATION", "HUMAN"} and not _not_expired(data):
                data = self._recovering(data, f"{data.get('state','lease').lower()}-lease-expired")
                self._write(data); self._audit("LEASE_EXPIRED", data["reason"])
            return dict(data)

    def automation_allowed(self) -> bool:
        return self.status().get("state") == "AUTOMATION"

    def human_input_allowed(self) -> bool:
        return self.status().get("state") == "HUMAN"

    def recover(self, reason: str) -> dict:
        with self._locked():
            current = _read_state(self.path)
            if current.get("state") != "RECOVERING":
                self._write(self._recovering(current, "invalid-recovery-transition")); self._audit("INVALID_TRANSITION", "recover")
                raise LeaseError("recovery requires RECOVERING")
            if not self.recovery_probe():
                self._write(self._recovering(current, "recovery-probe-failed")); self._audit("RECOVERY_FAILED", reason)
                raise LeaseError("recovery probe failed")
            nonce = secrets.token_hex(32)
            data = {"state": "AUTOMATION", "lease_generation": int(current.get("lease_generation", 0)) + 1,
                    "owner": f"agent:{self.bot}", "automation_nonce_sha256": _digest(nonce), "boot_id": BOOT_ID,
                    "expires_monotonic_ns": _mono_ns() + AUTOMATION_SECONDS * 1_000_000_000,
                    "updated_at": _now(), "reason": reason}
            self._write(data); self._audit("AUTOMATION_GRANTED", reason, {"automation_nonce_sha256": data["automation_nonce_sha256"]})
            return dict(data)

    def takeover(self, grant_source: object) -> dict:
        with self._locked():
            current = _read_state(self.path)
            if current.get("state") != "AUTOMATION" or not _not_expired(current):
                self._write(self._recovering(current, "invalid-or-concurrent-takeover")); self._audit("TAKEOVER_DENIED", "invalid-or-concurrent-takeover")
                raise LeaseError("takeover requires a valid AUTOMATION lease")
            if self.approval_verifier is None:
                self._write(self._recovering(current, "approval-verifier-unavailable")); self._audit("TAKEOVER_DENIED", "approval-verifier-unavailable")
                raise LeaseError("takeover approval unavailable")
            try:
                payload = self.approval_verifier(grant_source, current)
            except Exception as exc:
                self._write(self._recovering(current, "takeover-approval-denied")); self._audit("TAKEOVER_DENIED", "takeover-approval-denied")
                raise LeaseError(str(exc)) from exc
            duration = int(payload.get("duration_seconds", 0))
            if duration < 1 or duration > MAX_HUMAN_SECONDS:
                self._write(self._recovering(current, "takeover-duration-denied")); self._audit("TAKEOVER_DENIED", "takeover-duration-denied")
                raise LeaseError("takeover duration denied")
            generation = int(current.get("lease_generation", 0))
            draining = {"state": "DRAINING", "lease_generation": generation, "boot_id": BOOT_ID,
                        "expires_monotonic_ns": _mono_ns() + 60_000_000_000, "updated_at": _now(),
                        "reason": "human-takeover-drain", "grant_id": payload["grant_id"]}
            self._write(draining); self._audit("DRAINING", "human-takeover-drain", {"grant_id": payload["grant_id"]})
            if not self.drain_probe():
                with contextlib.suppress(OSError):
                    Path(payload.get("credential_path", "")).unlink()
                self._write(self._recovering(draining, "automation-drain-failed")); self._audit("DRAIN_FAILED", "automation-drain-failed")
                raise LeaseError("automation drain failed")
            duration = int(payload["duration_seconds"])
            data = {"state": "HUMAN", "lease_generation": generation, "boot_id": BOOT_ID,
                    "expires_monotonic_ns": _mono_ns() + duration * 1_000_000_000,
                    "updated_at": _now(), "reason": "human-takeover", "grant_id": payload["grant_id"],
                    "human_identity": payload["human_identity"], "device_identity_digest": payload["device_identity_digest"],
                    "takeover_credential_sha256": payload["takeover_credential_sha256"],
                    "bootstrap_consumed": False, "human_session_digest": None}
            self._write(data); self._audit("HUMAN_GRANTED", "human-takeover", {"grant_id": payload["grant_id"], "duration_seconds": duration})
            return dict(data)

    def bootstrap(self, credential: str) -> str:
        with self._locked():
            current = _read_state(self.path)
            if current.get("state") != "HUMAN" or not _not_expired(current) or current.get("bootstrap_consumed"):
                self._write(self._recovering(current, "bootstrap-conflict")); self._audit("BOOTSTRAP_DENIED", "bootstrap-conflict")
                raise LeaseError("takeover bootstrap denied")
            if not hmac.compare_digest(current.get("takeover_credential_sha256", ""), _digest(credential)):
                self._write(self._recovering(current, "bootstrap-credential-mismatch")); self._audit("BOOTSTRAP_DENIED", "bootstrap-credential-mismatch")
                raise LeaseError("takeover bootstrap denied")
            session = secrets.token_urlsafe(32)
            current["bootstrap_consumed"] = True; current["human_session_digest"] = _digest(session); current["updated_at"] = _now()
            self._write(current); self._audit("BOOTSTRAP_CONSUMED", "authenticated-no-store-bootstrap")
            return session

    def session_allowed(self, session: str) -> bool:
        data = self.status()
        return data.get("state") == "HUMAN" and hmac.compare_digest(data.get("human_session_digest") or "", _digest(session))

    def release(self, session: str, reason: str = "human-release") -> dict:
        with self._locked():
            current = _read_state(self.path)
            if current.get("state") != "HUMAN" or not hmac.compare_digest(current.get("human_session_digest") or "", _digest(session)):
                self._write(self._recovering(current, "stale-session-release")); self._audit("INVALID_TRANSITION", "stale-session-release")
                raise LeaseError("stale or mismatched human session")
            data = self._recovering(current, reason); self._write(data); self._audit("HUMAN_RELEASED", reason); return data

    def viewer_disconnected(self, session_digest: str) -> None:
        with self._locked():
            current = _read_state(self.path)
            if current.get("state") == "HUMAN" and hmac.compare_digest(current.get("human_session_digest") or "", session_digest):
                self._write(self._recovering(current, "human-viewer-disconnected")); self._audit("HUMAN_DISCONNECTED", "human-viewer-disconnected")


class HumanGate:
    def __init__(self, machine: LeaseMachine, listen: tuple[str, int], upstream: tuple[str, int]):
        self.machine = machine; self.listen = listen; self.upstream = upstream; self.stop = threading.Event()

    @staticmethod
    def _read_headers(client: socket.socket) -> tuple[bytes, str, dict[str, str]]:
        data = b""
        while b"\r\n\r\n" not in data and len(data) < 65536:
            chunk = client.recv(4096)
            if not chunk: break
            data += chunk
        head = data.split(b"\r\n\r\n", 1)[0].decode("latin1", "replace")
        lines = head.split("\r\n"); request = lines[0] if lines else ""
        headers = {}
        for line in lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1); headers[k.lower().strip()] = v.strip()
        return data, request, headers

    @staticmethod
    def _respond(client: socket.socket, status: str, headers: list[str] | None = None) -> None:
        rows = [f"HTTP/1.1 {status}", "Content-Length: 0", "Cache-Control: no-store", "Pragma: no-cache"] + (headers or []) + ["", ""]
        client.sendall("\r\n".join(rows).encode())

    def _connection(self, client: socket.socket) -> None:
        websocket = False; session = ""
        try:
            data, request, headers = self._read_headers(client)
            parts = request.split(); path = parts[1] if len(parts) >= 2 else ""
            if path == "/__takeover_bootstrap" and request.startswith("POST "):
                try:
                    session = self.machine.bootstrap(headers.get("x-hermes-takeover-credential", ""))
                except LeaseError:
                    self._respond(client, "403 Forbidden")
                    return
                self._respond(client, "204 No Content", [f"Set-Cookie: hermes_takeover={session}; Secure; HttpOnly; SameSite=Strict; Path=/"])
                return
            cookies = {}
            for item in headers.get("cookie", "").split(";"):
                if "=" in item:
                    k, v = item.strip().split("=", 1); cookies[k] = v
            session = cookies.get("hermes_takeover", "")
            if not self.machine.session_allowed(session):
                self.machine.force_recovering("human-session-conflict"); self._respond(client, "403 Forbidden"); return
            websocket = headers.get("upgrade", "").lower() == "websocket"
            peer = socket.create_connection(self.upstream, timeout=5)
            with peer, client:
                peer.sendall(data); client.setblocking(False); peer.setblocking(False)
                while self.machine.session_allowed(session):
                    readable, _, exceptional = select.select([client, peer], [], [client, peer], 0.5)
                    if exceptional: break
                    for src in readable:
                        chunk = src.recv(65536)
                        if not chunk: return
                        (peer if src is client else client).sendall(chunk)
        except (OSError, LeaseError):
            with contextlib.suppress(OSError): client.close()
        finally:
            if websocket and session:
                self.machine.viewer_disconnected(_digest(session))

    def serve(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); server.bind(self.listen); server.listen(32); server.settimeout(1)
            while not self.stop.is_set():
                try: client, _ = server.accept()
                except socket.timeout: continue
                threading.Thread(target=self._connection, args=(client,), daemon=True).start()


def _proxy_connection(client: socket.socket, upstream: tuple[str, int], state: Path, wanted: str) -> None:
    try:
        if not _state_allows(state, wanted): return
        peer = socket.create_connection(upstream, timeout=5)
        with peer, client:
            client.setblocking(False); peer.setblocking(False)
            while _state_allows(state, wanted):
                readable, _, exceptional = select.select([client, peer], [], [client, peer], 0.25)
                if exceptional: break
                for src in readable:
                    chunk = src.recv(65536)
                    if not chunk: return
                    (peer if src is client else client).sendall(chunk)
    except OSError:
        with contextlib.suppress(OSError): client.close()


def serve_proxy(listen: tuple[str, int], upstream: tuple[str, int], state: Path, wanted: str) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); server.bind(listen); server.listen(32)
        while True:
            client, _ = server.accept()
            if not _state_allows(state, wanted): client.close(); continue
            threading.Thread(target=_proxy_connection, args=(client, upstream, state, wanted), daemon=True).start()


def _run(cmd: list[str], check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, text=True, capture_output=capture)


def _paths(bot: str) -> tuple[Path, Path]:
    root = Path(f"/var/lib/hermes-bots/{bot}/browser")
    return root / "state" / "lease.json", root / "state"


def _raw_probe(bot: str) -> bool:
    code = "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9222/json/version',timeout=4).read()"
    return _run(["podman", "exec", f"hermes-{bot}-browser", "/home/seluser/venv/bin/python", "-c", code], check=False).returncode == 0


def _cdp_clients(bot: str) -> int:
    result = _run(["podman", "exec", f"hermes-{bot}-browser", "cat", "/proc/net/tcp"], check=False, capture=True)
    if result.returncode: return -1
    count = 0
    for line in result.stdout.splitlines()[1:]:
        cols = line.split()
        if len(cols) > 3 and (cols[1].upper().endswith(":2406") or cols[2].upper().endswith(":2406")) and cols[3] == "01": count += 1
    return count


def _stop_cdp_gate(bot: str) -> bool:
    script = "if [ -f /tmp/cdp-gate.pid ]; then kill $(cat /tmp/cdp-gate.pid) 2>/dev/null || true; rm -f /tmp/cdp-gate.pid; fi; for p in $(pgrep -f '[/]browser-supervisor.py cdp-proxy' || true); do kill $p 2>/dev/null || true; done"
    return _run(["podman", "exec", f"hermes-{bot}-browser", "bash", "-c", script], check=False).returncode == 0


def _start_cdp_gate(bot: str) -> bool:
    _stop_cdp_gate(bot)
    cmd = ["podman", "exec", "-d", "--user", "1200:1201", f"hermes-{bot}-browser", "/home/seluser/venv/bin/python", "/browser-supervisor.py", "cdp-proxy", "--state", "/browser-state/lease.json", "--listen", "0.0.0.0:9223", "--upstream", "127.0.0.1:9222"]
    return _run(cmd, check=False, capture=True).returncode == 0


def _reset_known_tab(bot: str) -> bool:
    code = """import json,urllib.request
base='http://127.0.0.1:9222'
old=json.load(urllib.request.urlopen(base+'/json/list'))
req=urllib.request.Request(base+'/json/new?about:blank',method='PUT')
new=json.load(urllib.request.urlopen(req,timeout=4))
for page in old:
    if page.get('id')!=new.get('id'):
        try: urllib.request.urlopen(base+'/json/close/'+page['id'],timeout=2).read()
        except Exception: pass
assert json.load(urllib.request.urlopen(base+'/json/version',timeout=4)).get('webSocketDebuggerUrl')
"""
    return _run(["podman", "exec", f"hermes-{bot}-browser", "/home/seluser/venv/bin/python", "-c", code], check=False).returncode == 0


def _profile_healthy(bot: str) -> bool:
    try:
        st = Path(f"/var/lib/hermes-bots/{bot}/browser/profile").stat()
        return st.st_uid == os.getuid() and st.st_mode & 0o077 == 0
    except OSError: return False


def _recovery_probe(bot: str) -> bool:
    _stop_cdp_gate(bot)
    for _ in range(40):
        if _cdp_clients(bot) == 0: break
        time.sleep(0.25)
    else: return False
    return _profile_healthy(bot) and _raw_probe(bot) and _reset_known_tab(bot) and _start_cdp_gate(bot)


def _drain_probe(bot: str) -> bool:
    if not _stop_cdp_gate(bot): return False
    for _ in range(40):
        if _cdp_clients(bot) == 0: return _raw_probe(bot)
        time.sleep(0.25)
    return False


def machine_for_cli(bot: str, boot: bool = False) -> LeaseMachine:
    state, state_dir = _paths(bot)
    trust = Path(f"/etc/hermes-browser/{bot}-approval-trust.json")
    verifier = GrantVerifier(bot, trust, state_dir / "consumed-grants")
    return LeaseMachine(bot, state, lambda: _recovery_probe(bot), lambda: _drain_probe(bot), boot=boot, approval_verifier=verifier)


def _boot_rootless_repair(bot: str) -> None:
    # At boot no Bot workload should be running yet. Clear stale Podman pause/
    # slirp state before creating the network anchor. During a browser-only
    # restart gateway/serve remain running, so migration is deliberately skipped.
    running = _run(["podman", "ps", "--format", "{{.Names}}"], check=False, capture=True)
    names = set(running.stdout.split()) if running.returncode == 0 else set()
    if f"hermes-{bot}-gateway" in names or f"hermes-{bot}-serve" in names:
        return
    _run(["pkill", "-KILL", "-u", str(os.getuid()), "slirp4netns"], check=False)
    pause = Path(f"/run/user/{os.getuid()}/libpod/tmp/pause.pid")
    if pause.exists():
        with contextlib.suppress(Exception):
            os.kill(int(pause.read_text().strip()), 9)
        with contextlib.suppress(OSError):
            pause.unlink()
    shutil.rmtree(f"/run/user/{os.getuid()}/libpod/tmp/rootless-netns", ignore_errors=True)
    _run(["podman", "system", "migrate"], check=False)


def daemon(bot: str) -> int:
    os.environ["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"; os.environ["TMPDIR"] = f"/var/lib/hermes-bots/{bot}/tmp"
    machine = machine_for_cli(bot, boot=True)
    _boot_rootless_repair(bot)
    _run(["/usr/local/libexec/hermes-browser-run", bot])
    gate = HumanGate(machine, ("127.0.0.1", BOTS[bot]), ("127.0.0.1", 16081 if bot == "chief" else 16082))
    thread = threading.Thread(target=gate.serve, daemon=True); thread.start()
    try:
        while True:
            for name in (f"hermes-{bot}-browser", f"hermes-{bot}-net-anchor"):
                result = _run(["podman", "inspect", "--format", "{{.State.Running}}", name], check=False, capture=True)
                if result.returncode or result.stdout.strip() != "true": raise LeaseError(f"container unhealthy: {name}")
            machine.status(); time.sleep(2)
    finally:
        gate.stop.set(); _run(["podman", "rm", "-f", f"hermes-{bot}-browser"], check=False)


def main() -> int:
    parser = argparse.ArgumentParser(); sub = parser.add_subparsers(dest="cmd", required=True)
    for command in ("daemon", "stop", "status"):
        p = sub.add_parser(command); p.add_argument("--bot", required=True, choices=sorted(BOTS))
    p = sub.add_parser("recover"); p.add_argument("--bot", required=True, choices=sorted(BOTS)); p.add_argument("--reason", required=True)
    p = sub.add_parser("takeover"); p.add_argument("--bot", required=True, choices=sorted(BOTS)); p.add_argument("--grant", type=Path, required=True); p.add_argument("--manifest", type=Path, required=True); p.add_argument("--nonce-file", type=Path, required=True); p.add_argument("--credential-out", type=Path, required=True)
    p = sub.add_parser("release"); p.add_argument("--bot", required=True, choices=sorted(BOTS)); p.add_argument("--session-file", type=Path, required=True)
    p = sub.add_parser("check-automation"); p.add_argument("--bot", required=True, choices=sorted(BOTS))
    p = sub.add_parser("check-human"); p.add_argument("--bot", required=True, choices=sorted(BOTS))
    p = sub.add_parser("cdp-proxy"); p.add_argument("--state", type=Path, required=True); p.add_argument("--listen", required=True); p.add_argument("--upstream", required=True)
    args = parser.parse_args()
    try:
        if args.cmd == "daemon": return daemon(args.bot)
        if args.cmd == "stop": _run(["podman", "rm", "-f", f"hermes-{args.bot}-browser"], check=False); return 0
        if args.cmd == "cdp-proxy":
            lh, lp = args.listen.rsplit(":", 1); uh, up = args.upstream.rsplit(":", 1); serve_proxy((lh, int(lp)), (uh, int(up)), args.state, "AUTOMATION"); return 0
        machine = machine_for_cli(args.bot)
        if args.cmd == "status": out = machine.status()
        elif args.cmd == "recover": out = machine.recover(args.reason)
        elif args.cmd == "takeover": out = machine.takeover((args.grant, args.manifest, args.nonce_file, args.credential_out))
        elif args.cmd == "release":
            session = args.session_file.read_text().strip(); args.session_file.unlink(); out = machine.release(session)
        elif args.cmd == "check-automation": return 0 if machine.automation_allowed() else 3
        elif args.cmd == "check-human": return 0 if machine.human_input_allowed() else 3
        else: raise LeaseError("unsupported command")
        print(json.dumps(out, sort_keys=True)); return 0
    except LeaseError as exc:
        print(str(exc), file=sys.stderr); return 3


if __name__ == "__main__":
    raise SystemExit(main())
