#!/usr/bin/env python3
import argparse, json, time, urllib.request
from websockets.sync.client import connect

p=argparse.ArgumentParser(); p.add_argument("mode",choices=["login","check","logout"]); p.add_argument("--cdp",default="10.89.0.10:9223"); p.add_argument("--fixture",default="http://10.89.0.20:8080/"); a=p.parse_args()
pages=json.load(urllib.request.urlopen(f"http://{a.cdp}/json/list",timeout=5))
page=pages[0]; ws=page["webSocketDebuggerUrl"].replace("127.0.0.1:9222",a.cdp).replace("localhost:9222",a.cdp)
c=connect(ws,open_timeout=5); counter=0
def call(method,params=None):
 global counter
 counter+=1; c.send(json.dumps({"id":counter,"method":method,"params":params or {}}))
 while True:
  r=json.loads(c.recv())
  if r.get("id")==counter: return r
call("Page.navigate",{"url":a.fixture}); time.sleep(2)
if a.mode=="login":
 expr="fetch('/login',{method:'POST',credentials:'include'}).then(()=>location.reload())"
 call("Runtime.evaluate",{"expression":expr,"awaitPromise":True}); time.sleep(2)
elif a.mode=="logout":
 expr="fetch('/logout',{method:'POST',credentials:'include'}).then(()=>location.reload())"
 call("Runtime.evaluate",{"expression":expr,"awaitPromise":True}); time.sleep(2)
r=call("Runtime.evaluate",{"expression":"document.body.innerText","returnByValue":True}); text=r["result"]["result"].get("value",""); c.close()
authenticated="AUTHENTICATED DISPOSABLE TEST USER" in text
if a.mode in {"login","check"}: assert authenticated
else: assert not authenticated
print(json.dumps({"mode":a.mode,"authenticated":authenticated,"disposable_test_owned":True,"credential_value_used":False,"session_value_observed":False},sort_keys=True))
