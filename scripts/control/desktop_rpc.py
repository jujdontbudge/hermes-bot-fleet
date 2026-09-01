#!/usr/bin/env python3
"""Authenticated allowlisted Hermes Desktop JSON-RPC client; never prints auth material."""
import argparse, http.cookiejar, json, urllib.parse, urllib.request
from pathlib import Path
from websockets.sync.client import connect

ALLOWED={"profiles.list","profiles.describe","profiles.configure","groups.capabilities","groups.list","groups.create","groups.state","groups.send","groups.log","session.list","session.create","session.title","bot_relay.roster.sync","bot_relay.outbox.drain","bot_relay.deliver","bot_relay.reply"}
p=argparse.ArgumentParser(); p.add_argument("--base",required=True); p.add_argument("--password-file",type=Path,required=True); p.add_argument("--method",required=True,choices=sorted(ALLOWED)); p.add_argument("--params",default="{}")
a=p.parse_args(); params=json.loads(a.params); password=a.password_file.read_text().strip()
jar=http.cookiejar.CookieJar(); opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
def post(path,data):
 req=urllib.request.Request(a.base+path,data=json.dumps(data).encode(),headers={"Content-Type":"application/json"},method="POST")
 return json.load(opener.open(req,timeout=10))
login=post("/auth/password-login",{"provider":"basic","username":"desktop","password":password,"next":""}); assert login.get("ok") is True
ticket=post("/api/auth/ws-ticket",{}).get("ticket"); assert ticket
ws=a.base.replace("http://","ws://").replace("https://","wss://")+"/api/ws?ticket="+urllib.parse.quote(ticket,safe="")
with connect(ws,open_timeout=10) as sock:
 request_id="fleet-rpc-1"; sock.send(json.dumps({"id":request_id,"method":a.method,"params":params}))
 while True:
  message=json.loads(sock.recv())
  if message.get("id")==request_id:
   if "error" in message: raise RuntimeError(json.dumps(message["error"],sort_keys=True))
   result=message.get("result",{}); break

def reject_secret_keys(value):
 if isinstance(value,dict):
  for key,item in value.items():
   if any(word in key.lower() for word in ("token","password","secret","cookie","authorization")): raise RuntimeError("secret-shaped RPC response rejected")
   reject_secret_keys(item)
 elif isinstance(value,list):
  for item in value: reject_secret_keys(item)
reject_secret_keys(result); print(json.dumps(result,sort_keys=True))
