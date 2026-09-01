#!/usr/bin/env python3
"""Merge locked runtime defaults into an existing profile config without clobbering user/Bot metadata."""
import argparse, os
from pathlib import Path
import yaml

p=argparse.ArgumentParser(); p.add_argument("--config",type=Path,required=True); p.add_argument("--template",type=Path,required=True); p.add_argument("--workspace",required=True); a=p.parse_args()
required=yaml.safe_load(a.template.read_text().replace("__WORKSPACE__",a.workspace)) or {}
try: existing=yaml.safe_load(a.config.read_text()) or {}
except FileNotFoundError: existing={}

def merge(current, wanted):
    if not isinstance(current,dict) or not isinstance(wanted,dict): return wanted
    out=dict(current)
    for key,value in wanted.items(): out[key]=merge(out.get(key),value)
    return out

result=merge(existing,required)
tmp=a.config.with_suffix(a.config.suffix+".new")
tmp.write_text(yaml.safe_dump(result,sort_keys=False)); os.chmod(tmp,0o600); tmp.replace(a.config)
