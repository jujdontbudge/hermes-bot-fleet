#!/usr/bin/env python3
"""Configure one live Hermes profile as a Bot through authenticated Desktop RPC."""
import argparse, http.cookiejar, json, urllib.parse, urllib.request
from pathlib import Path
from websockets.sync.client import connect

BOTS={
 "chief":{"title":"Chief","description":"Primary fleet coordinator. Delegates bounded test work and preserves each target Bot's authority.","soul":"You are Chief, the primary personal fleet coordinator. Plan and delegate bounded work to named teammates with message_agent, but never borrow their credentials or permissions. Preserve attribution, escalate consequential decisions to Johan, use gpt-5.6-sol through openai-codex, and never switch reasoning to Anthropic. Keep operational replies concise and evidence-backed."},
 "test-worker":{"title":"Test Worker","description":"Disposable test and verification specialist with no production credentials or production account authority.","soul":"You are Test Worker, the fleet's disposable validation specialist. Use only test-owned data, identities, credentials, fixtures, and reversible actions. Refuse production purchases, publishing, account changes, permissions, or production credentials. Report exact tests and evidence. Use gpt-5.6-sol through openai-codex and never switch reasoning to Anthropic."},
}
p=argparse.ArgumentParser(); p.add_argument("--base",required=True); p.add_argument("--password-file",type=Path,required=True); p.add_argument("--bot",required=True,choices=sorted(BOTS)); a=p.parse_args()
password=a.password_file.read_text().strip(); jar=http.cookiejar.CookieJar(); opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
def post(path,data):
 req=urllib.request.Request(a.base+path,data=json.dumps(data).encode(),headers={"Content-Type":"application/json"},method="POST"); return json.load(opener.open(req,timeout=10))
assert post("/auth/password-login",{"provider":"basic","username":"desktop","password":password,"next":""}).get("ok") is True

def rpc(method,params):
 ticket=post("/api/auth/ws-ticket",{})["ticket"]; ws=a.base.replace("http://","ws://").replace("https://","wss://")+"/api/ws?ticket="+urllib.parse.quote(ticket,safe="")
 with connect(ws,open_timeout=10) as sock:
  rid="configure-1"; sock.send(json.dumps({"id":rid,"method":method,"params":params}))
  while True:
   msg=json.loads(sock.recv())
   if msg.get("id")==rid:
    if "error" in msg: raise RuntimeError(json.dumps(msg["error"],sort_keys=True))
    return msg.get("result",{})

cfg=BOTS[a.bot]
default_result=rpc("profiles.configure",{"name":"default","ui_meta":{"hermes-bots":{"title":"Disabled installation root","description":"Not a fleet Bot","hidden":True}}})
bot_result=rpc("profiles.configure",{"name":a.bot,"description":cfg["description"],"soul":cfg["soul"],"model":"gpt-5.6-sol","provider":"openai-codex","confirm_expensive_model":True,"ui_meta":{"hermes-bots":{"title":cfg["title"],"description":cfg["description"],"groups":["fleet-ops"],"hidden":False}}})
profiles=rpc("profiles.list",{"include_sessions":True})["profiles"]; row=next(x for x in profiles if x["name"]==a.bot)
created=False
if not row.get("canonical_session"):
 res=rpc("session.create",{"profile":a.bot,"title":"Bot Chat","hidden":True,"follow_profile_config":True}); runtime=res.get("session_id")
 if not runtime: raise RuntimeError("canonical session runtime id missing")
 rpc("session.title",{"session_id":runtime,"title":"Bot Chat"}); created=True
profiles=rpc("profiles.list",{"include_sessions":True})["profiles"]; named=next(x for x in profiles if x["name"]==a.bot); default=next(x for x in profiles if x["name"]=="default")
assert named.get("canonical_session") and named.get("model")=="gpt-5.6-sol" and named.get("provider")=="openai-codex"
assert named.get("ui_meta",{}).get("hermes-bots",{}).get("title")==cfg["title"]
assert default.get("ui_meta",{}).get("hermes-bots",{}).get("hidden") is True
print(json.dumps({"bot":a.bot,"title":cfg["title"],"canonical_chat":True,"canonical_created":created,"default_profile_hidden":True,"model":"gpt-5.6-sol","provider":"openai-codex","description_applied":bot_result.get("applied",{}).get("description") is True,"soul_applied":bot_result.get("applied",{}).get("soul") is True},sort_keys=True))
