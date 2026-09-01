#!/usr/bin/env python3
"""Fixed-shape Bot relay waiter used instead of approval-blocked python -c."""
import argparse, base64, json, os, sys, time
from pathlib import Path

p=argparse.ArgumentParser(); p.add_argument("--reply",required=True); p.add_argument("--label-b64",required=True); p.add_argument("--timeout",type=int,required=True); a=p.parse_args()
reply=Path(a.reply)
allowed=Path("/opt/data/bot_relay/replies")
try: reply.resolve().relative_to(allowed)
except ValueError: raise SystemExit("reply path denied")
if not 1<=a.timeout<=300: raise SystemExit("timeout denied")
label=base64.urlsafe_b64decode(a.label_b64.encode()).decode("utf-8")
if not label or len(label)>200 or any(ord(c)<32 for c in label): raise SystemExit("label denied")
deadline=time.time()+a.timeout
while time.time()<deadline:
    if reply.exists():
        data=json.loads(reply.read_text(encoding="utf-8"))
        if set(data)-{"reply","error","reason"}: raise SystemExit("reply shape denied")
        if data.get("error"):
            code=str(data.get("reason") or "").strip(); tag=" [reason: "+code+"]" if code else ""
            print("Delivery to "+label+" failed"+tag+": "+str(data["error"])); raise SystemExit(1)
        print("Reply from "+label+":"); print(data.get("reply") or "(empty reply)"); raise SystemExit(0)
    time.sleep(2)
print(f"No reply from {label} within {a.timeout}s. The message may still be delivered when the Desktop reconnects; do not resend blindly.")
raise SystemExit(1)
