#!/usr/bin/env python3
"""Exercise authenticated no-store takeover bootstrap without printing secrets."""
import argparse, base64, hashlib, http.client, json, os, socket
from pathlib import Path

p=argparse.ArgumentParser(); p.add_argument("--port",type=int,required=True); p.add_argument("--credential-file",type=Path,required=True); p.add_argument("--session-file",type=Path,required=True); a=p.parse_args()
credential=a.credential_file.read_text().strip(); a.credential_file.unlink()
conn=http.client.HTTPConnection("127.0.0.1",a.port,timeout=5)
conn.request("POST","/__takeover_bootstrap",headers={"X-Hermes-Takeover-Credential":credential,"Content-Length":"0"})
r=conn.getresponse(); r.read(); cookie=r.getheader("Set-Cookie") or ""; cache=r.getheader("Cache-Control") or ""
assert r.status==204 and cache.lower()=="no-store" and "HttpOnly" in cookie and "SameSite=Strict" in cookie and "Secure" in cookie
session=cookie.split("hermes_takeover=",1)[1].split(";",1)[0]
fd=os.open(a.session_file,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,"w") as fh: fh.write(session+"\n"); fh.flush(); os.fsync(fh.fileno())
conn.close()
conn=http.client.HTTPConnection("127.0.0.1",a.port,timeout=5); conn.request("GET","/",headers={"Cookie":f"hermes_takeover={session}"}); r=conn.getresponse(); body=r.read(); assert r.status==200 and (b"noVNC" in body or b"VNC" in body); conn.close()
key=base64.b64encode(os.urandom(16)).decode(); s=socket.create_connection(("127.0.0.1",a.port),timeout=5)
request=("GET /websockify HTTP/1.1\r\nHost: 127.0.0.1\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: "+key+"\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Protocol: binary\r\nCookie: hermes_takeover="+session+"\r\n\r\n")
s.sendall(request.encode()); response=s.recv(4096); assert b" 101 " in response.split(b"\r\n",1)[0]; s.close()
print(json.dumps({"bootstrap_status":204,"cache_control_no_store":True,"credential_in_url":False,"session_cookie_http_only":True,"session_cookie_secure":True,"authenticated_html_status":200,"authenticated_websocket_status":101,"credential_file_consumed":not a.credential_file.exists(),"secret_values_printed":False},sort_keys=True))
