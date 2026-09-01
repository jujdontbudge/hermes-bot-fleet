#!/usr/bin/env python3
import importlib.util
import base64
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
BROWSER = ROOT / "infra/browser"
SCRIPTS = ROOT / "scripts/browser"


def load_supervisor():
    spec = importlib.util.spec_from_file_location("browser_supervisor", SCRIPTS / "browser_supervisor.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


class BrowserLeasePublicSeamTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.mod = load_supervisor()

    @staticmethod
    def payload(machine, credential="fixture-credential", duration=60):
        current = machine.status()
        return {"grant_id":"fixture-grant","duration_seconds":duration,"human_identity":"human:johan","device_identity_digest":"d"*64,"takeover_credential_sha256":__import__("hashlib").sha256(credential.encode()).hexdigest()}

    def machine(self, tmp, probe=lambda: True):
        return self.mod.LeaseMachine("test-worker", Path(tmp)/"lease.json", probe, lambda: True, approval_verifier=lambda grant,current: grant)

    def test_restart_enters_recovering_then_automation_has_owner_nonce_and_monotonic_expiry(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"lease.json"; p.write_text(json.dumps({"state":"HUMAN","lease_generation":4}))
            m=self.machine(tmp); self.assertEqual(m.status()["state"],"RECOVERING")
            a=m.recover("fixture"); self.assertEqual(a["state"],"AUTOMATION"); self.assertEqual(a["owner"],"agent:test-worker")
            self.assertEqual(len(a["automation_nonce_sha256"]),64); self.assertGreater(a["expires_monotonic_ns"],self.mod._mono_ns())

    def test_signed_payload_takeover_bootstrap_release_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            m=self.machine(tmp); m.recover("fixture"); raw="one-time-credential"; h=m.takeover(self.payload(m,raw,600))
            self.assertEqual(h["state"],"HUMAN"); self.assertFalse(m.automation_allowed())
            session=m.bootstrap(raw); self.assertTrue(m.session_allowed(session)); self.assertFalse(m.session_allowed("wrong"))
            self.assertEqual(m.release(session)["state"],"RECOVERING"); self.assertEqual(m.recover("handback")["state"],"AUTOMATION")

    def test_invalid_transition_stale_session_and_concurrent_claim_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            m=self.machine(tmp); m.recover("fixture"); raw="credential"; m.takeover(self.payload(m,raw)); session=m.bootstrap(raw)
            with self.assertRaises(self.mod.LeaseError): m.takeover(self.payload(m,"other"))
            self.assertEqual(m.status()["state"],"RECOVERING")
            m.recover("retry"); m.takeover(self.payload(m,raw)); m.bootstrap(raw)
            with self.assertRaises(self.mod.LeaseError): m.release("stale")
            self.assertEqual(m.status()["state"],"RECOVERING")

    def test_disconnect_timeout_and_excessive_duration_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            m=self.machine(tmp); m.recover("fixture"); raw="credential"; m.takeover(self.payload(m,raw)); session=m.bootstrap(raw)
            m.viewer_disconnected(self.mod._digest(session)); self.assertEqual(m.status()["state"],"RECOVERING")
            m.recover("retry")
            with self.assertRaises(self.mod.LeaseError): m.takeover(self.payload(m,raw,601))
            self.assertEqual(m.status()["state"],"RECOVERING")

    def test_recovery_probe_failure_stays_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            m=self.machine(tmp,lambda:False)
            with self.assertRaises(self.mod.LeaseError): m.recover("bad")
            self.assertEqual(m.status()["state"],"RECOVERING")

    def test_ed25519_grant_verification_consumption_and_replay_denial(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp); profile=tmp/"profile"; profile.mkdir(mode=0o700); state=tmp/"lease.json"
            nonce="a"*64; state.write_text(json.dumps({"state":"AUTOMATION","automation_nonce_sha256":nonce}))
            trust=tmp/"trust.json"; grant=tmp/"grant.json"; manifest=tmp/"manifest.json"; nonce_file=tmp/"nonce"; credential=tmp/"credential"
            policy="git:"+"0"*40
            subprocess.run([str(SCRIPTS/"sign-takeover-fixture.py"),"--bot","test-worker","--state",str(state),"--profile",str(profile),"--trust-out",str(trust),"--grant-out",str(grant),"--manifest-out",str(manifest),"--nonce-out",str(nonce_file),"--duration","60","--policy-revision",policy],check=True,capture_output=True,text=True)
            grant_text=grant.read_text(); manifest_text=manifest.read_text(); nonce_text=nonce_file.read_text(); original=self.mod._profile_fingerprint
            st=profile.resolve().stat(); expected=self.mod._digest(f"{profile.resolve()}:{st.st_dev}:{st.st_ino}:{st.st_uid}:{st.st_gid}:{st.st_mode & 0o777}")
            setattr(self.mod,"_profile_fingerprint",lambda bot: expected)
            try:
                verifier=self.mod.GrantVerifier("test-worker",trust,tmp/"consumed")
                payload=verifier((grant,manifest,nonce_file,credential),{"automation_nonce_sha256":nonce}); self.assertEqual(payload["duration_seconds"],60); self.assertFalse(grant.exists())
                replay=tmp/"replay.json"; replay_manifest=tmp/"replay-manifest.json"; replay_nonce=tmp/"replay-nonce"; replay_credential=tmp/"replay-credential"
                for path,content in ((replay,grant_text),(replay_manifest,manifest_text),(replay_nonce,nonce_text)): path.write_text(content); path.chmod(0o600)
                with self.assertRaises(self.mod.LeaseError): verifier((replay,replay_manifest,replay_nonce,replay_credential),{"automation_nonce_sha256":nonce})
            finally: setattr(self.mod,"_profile_fingerprint",original)

    def test_retained_predecessor_signing_certificate_remains_verifiable(self):
        from Crypto.PublicKey import ECC
        from Crypto.Signature import eddsa
        root=ECC.generate(curve="Ed25519"); predecessor=ECC.generate(curve="Ed25519"); active=ECC.generate(curve="Ed25519")
        raw=lambda k:k.public_key().export_key(format="raw")
        key_id=lambda k:"approval-"+hashlib.sha256(raw(k)).hexdigest()[:16]
        pred_id=key_id(predecessor); active_id=key_id(active); now=time.time()
        iso=lambda ts:dt.datetime.fromtimestamp(ts,dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00","Z")
        def cert(key,kid,pred):
            payload={"schema_version":"1.0","signing_key_id":kid,"public_key":"ed25519:"+base64.b64encode(raw(key)).decode(),"environment":"fixture","purpose":"fleet-approval-grant-v1","not_before":iso(now-5),"not_after":iso(now+300),"predecessor_key_id":pred}
            signature=eddsa.new(root,"rfc8032").sign(b"fleet-approval-cert-v1\0"+self.mod._canonical(payload))
            return {"payload":payload,"signature":"ed25519:"+base64.b64encode(signature).decode()}
        root_text="ed25519:"+base64.b64encode(raw(root)).decode(); root_fp="sha256:"+hashlib.sha256(raw(root)).hexdigest()
        trust={"environment":"fixture","root_public_key":root_text,"root_public_key_fingerprint":root_fp,"root_rotation":{"current_fingerprint":root_fp,"predecessor_fingerprint":None,"cross_certificates":[]},"active_signing_key_id":active_id,"predecessor_signing_key_id":pred_id,"certificates":{active_id:cert(active,active_id,pred_id),pred_id:cert(predecessor,pred_id,None)},"revocations":[]}
        with tempfile.TemporaryDirectory() as tmp:
            verifier=self.mod.GrantVerifier("test-worker",Path(tmp)/"trust",Path(tmp)/"consumed")
            self.assertEqual(verifier._verify_certificate(trust,active_id,now,now)["signing_key_id"],active_id)
            self.assertEqual(verifier._verify_certificate(trust,pred_id,now,now)["signing_key_id"],pred_id)


class BrowserRuntimeArtifactsTest(unittest.TestCase):
    def test_manifest_has_separate_profiles_and_fixed_ports(self):
        m=json.loads((BROWSER/"browser-manifest.json").read_text()); self.assertRegex(m["image"],r"@sha256:[0-9a-f]{64}$")
        self.assertEqual(m["bots"],{"chief":{"display":99,"novnc_port":6081},"test-worker":{"display":99,"novnc_port":6082}})

    def test_exact_nonroot_hardened_display_stack_and_loopback_raw_cdp(self):
        run=(SCRIPTS/"browser-run.sh").read_text(); start=(BROWSER/"browser-start.sh").read_text()
        for text in ("--user 1200:1201","--read-only","--cap-drop=all","--security-opt=no-new-privileges"): self.assertIn(text,run)
        for text in ("Xvfb :99","fluxbox","x11vnc","-localhost","websockify","/opt/bin/noVNC","--remote-debugging-address=127.0.0.1","--remote-debugging-port=9222","--user-data-dir=/browser-profile"): self.assertIn(text,start)
        self.assertNotIn("--no-sandbox",start); self.assertNotIn('9222:9222',run); self.assertIn('127.0.0.1:$INTERNAL_WEB_PORT:6080',run)

    def test_runtime_vault_exclusion_and_static_private_gate(self):
        runtime=(ROOT/"scripts/hermes/runtime-run.sh").read_text(); self.assertIn('--network "hermes-$bot"',runtime)
        self.assertNotIn('/browser-profile',runtime); self.assertNotIn('/var/lib/hermes-bots/$bot/browser',runtime)
        cfg=json.loads((ROOT/"infra/hermes/config/profile-config.json.tmpl").read_text()); self.assertEqual(cfg["browser"]["cdp_url"],"http://10.89.0.10:9223")

    def test_browser_restart_does_not_restart_gateway(self):
        gateway=(ROOT/"infra/hermes/systemd/hermes-gateway@.service").read_text(); browser=(BROWSER/"systemd/hermes-browser@.service").read_text()
        self.assertIn("After=hermes-browser@%i.service",gateway); self.assertNotIn("Requires=hermes-browser@%i.service",gateway); self.assertNotIn("BindsTo=hermes-browser@%i.service",gateway); self.assertNotIn("hermes-gateway@%i.service",browser)
        self.assertIn("User=bot-%i",browser); self.assertIn("Restart=on-failure",browser)

    def test_signed_approval_and_authenticated_bootstrap_are_mandatory(self):
        s=(SCRIPTS/"browser_supervisor.py").read_text()
        for text in ("Ed25519PublicKey","fleet-approval-grant-v1\\0","RFC 8785","ed25519:","authority_context","nonce_sha256","manifest_sha256","max_uses","consumed-grants","approval.consumed","cross-certification","wall clock rollback","x-hermes-takeover-credential","Cache-Control: no-store","expires_monotonic_ns","MAX_HUMAN_SECONDS = 600"):
            self.assertIn(text.lower(),s.lower())
        self.assertIn("--grant",s); self.assertNotIn("--session opaque",s)

    def test_shell_python_and_evidence_schema(self):
        for script in sorted(SCRIPTS.glob("*.sh"))+sorted(BROWSER.glob("*.sh")):
            r=subprocess.run(["bash","-n",str(script)],capture_output=True,text=True); self.assertEqual(r.returncode,0,r.stderr)
        for script in sorted(SCRIPTS.glob("*.py")):
            r=subprocess.run(["python3","-m","py_compile",str(script)],capture_output=True,text=True); self.assertEqual(r.returncode,0,r.stderr)
        schema=json.loads((ROOT/"schemas/evidence/browser-runtime-evidence.schema.json").read_text()); self.assertFalse(schema["additionalProperties"])
        serialized=json.dumps(schema).lower()
        for unsafe in ("cookie","token","password","authorization","screenshot_content"): self.assertNotIn(f'"{unsafe}"',serialized)

    def test_runbook_names_vault_human_only_and_recovery(self):
        r=(ROOT/"docs/runbooks/browser-takeover.md").read_text(); self.assertIn("Browser Profiles are credential vaults",r); self.assertIn("human-only",r); self.assertIn("RECOVERING",r)

if __name__=="__main__": unittest.main(verbosity=2)
