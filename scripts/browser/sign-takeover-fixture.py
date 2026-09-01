#!/usr/bin/env python3
"""Create an ephemeral disposable authority and one locked-format takeover grant.

Private keys exist only in process memory. This is for the BROW-01 disposable
fixture and is never a production approval authority.
"""
from __future__ import annotations
import argparse, base64, datetime as dt, hashlib, json, os
from pathlib import Path
import secrets, time, uuid
try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    class CryptographySigner:
        def __init__(self): self.key=Ed25519PrivateKey.generate()
        def public_raw(self): return self.key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        def sign(self,message): return self.key.sign(message)
    Signer=CryptographySigner
except ModuleNotFoundError:
    from Crypto.PublicKey import ECC
    from Crypto.Signature import eddsa
    class PyCryptodomeSigner:
        def __init__(self): self.key=ECC.generate(curve="Ed25519")
        def public_raw(self): return self.key.public_key().export_key(format="raw")
        def sign(self,message): return eddsa.new(self.key,"rfc8032").sign(message)
    Signer=PyCryptodomeSigner


def canonical(d): return json.dumps(d,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def digest(v): return hashlib.sha256(v.encode() if isinstance(v,str) else v).hexdigest()
def pub(k): return "ed25519:"+base64.b64encode(k.public_raw()).decode()
def sig(k,payload,domain): return "ed25519:"+base64.b64encode(k.sign(domain+canonical(payload))).decode()
def iso(ts): return dt.datetime.fromtimestamp(ts,dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00","Z")
def profile_id(path):
    path=path.resolve(strict=True); st=path.stat(); return digest(f"{path}:{st.st_dev}:{st.st_ino}:{st.st_uid}:{st.st_gid}:{st.st_mode & 0o777}")
def secure_write(path,data):
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True); fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"w") as fh: fh.write(data); fh.flush(); os.fsync(fh.fileno())

p=argparse.ArgumentParser()
p.add_argument("--bot",required=True,choices=["chief","test-worker"]); p.add_argument("--state",type=Path,required=True); p.add_argument("--profile",type=Path,required=True)
p.add_argument("--trust-out",type=Path,required=True); p.add_argument("--grant-out",type=Path,required=True); p.add_argument("--manifest-out",type=Path,required=True); p.add_argument("--nonce-out",type=Path,required=True)
p.add_argument("--duration",type=int,default=60); p.add_argument("--reason",default="disposable BROW-01 validation"); p.add_argument("--policy-revision",required=True)
a=p.parse_args()
if not 1<=a.duration<=600 or not a.policy_revision.startswith("git:") or len(a.policy_revision)!=44: raise SystemExit("invalid duration or policy revision")
state=json.loads(a.state.read_text())
if state.get("state")!="AUTOMATION" or not state.get("automation_nonce_sha256"): raise SystemExit("AUTOMATION lease required")
now=time.time(); root=Signer(); signer=Signer(); key_id="approval-ed25519-fixture-"+digest(signer.public_raw())[:12]; device="sha256:"+digest("disposable-johan-device")
cert_payload={"schema_version":"1.0","signing_key_id":key_id,"public_key":pub(signer),"environment":"disposable-fixture","purpose":"fleet-approval-grant-v1","not_before":iso(now-5),"not_after":iso(now+3600),"predecessor_key_id":None}
certificate={"payload":cert_payload,"signature":sig(root,cert_payload,b"fleet-approval-cert-v1\0")}
manifest={"schema_version":"1.0","action":"browser-takeover","bot":a.bot,"runtime":"azure-server","browser_profile_id_digest":"sha256:"+profile_id(a.profile),"reason":a.reason,"requested_duration_seconds":a.duration,"current_lease_nonce_digest":"sha256:"+state["automation_nonce_sha256"],"expected_transition":["AUTOMATION","DRAINING","HUMAN"],"side_effect":"exclusive-browser-input"}
raw_nonce=secrets.token_bytes(32); unsigned={"schema_version":"1.0","grant_id":str(uuid.uuid4()),"manifest_sha256":"sha256:"+digest(canonical(manifest)),"nonce_sha256":"sha256:"+digest(raw_nonce),"approver":"human:johan","channel":"mac_local","authority_context":{"channel_instance_id_digest":"sha256:"+digest("disposable-channel-instance"),"approval_session_id_digest":"sha256:"+digest(secrets.token_hex(16)),"device_identity_digest":device},"issued_at":iso(now),"expires_at":iso(now+45),"max_uses":1,"policy_revision":a.policy_revision,"signing_key_id":key_id}
grant={**unsigned,"signature":sig(signer,unsigned,b"fleet-approval-grant-v1\0")}
root_text=pub(root); root_fp="sha256:"+digest(root.public_raw())
trust={"schema_version":"1.0","bot":a.bot,"environment":"disposable-fixture","root_public_key":root_text,"root_public_key_fingerprint":root_fp,"root_rotation":{"current_fingerprint":root_fp,"predecessor_fingerprint":None,"cross_certificates":[]},"active_signing_key_id":key_id,"predecessor_signing_key_id":None,"certificates":{key_id:certificate},"revocations":[],"eligible_channels":["mac_local"],"approved_device_identity_digests":[device],"policy_revision":a.policy_revision}
secure_write(a.trust_out,json.dumps(trust,sort_keys=True)+"\n"); secure_write(a.grant_out,json.dumps(grant,sort_keys=True)+"\n"); secure_write(a.manifest_out,json.dumps(manifest,sort_keys=True)+"\n"); secure_write(a.nonce_out,base64.b64encode(raw_nonce).decode()+"\n")
print(json.dumps({"bot":a.bot,"environment":"disposable-fixture","grant_id":grant["grant_id"],"manifest_sha256":grant["manifest_sha256"],"grant_lifetime_seconds":45,"duration_seconds":a.duration,"private_keys_persisted":False,"locked_domain_separator":True},sort_keys=True))
