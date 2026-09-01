#!/usr/bin/env python3
"""Disposable test-owned authenticated-session fixture; contains no real credentials."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import secrets

SESSION = secrets.token_urlsafe(24)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return
    def _send(self, status, body, headers=()):
        data=body.encode(); self.send_response(status)
        for k,v in headers: self.send_header(k,v)
        self.send_header("Content-Type","text/html; charset=utf-8"); self.send_header("Content-Length",str(len(data))); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        authenticated=f"fixture_session={SESSION}" in (self.headers.get("Cookie") or "")
        if authenticated:
            self._send(200,"<html><body><h1>AUTHENTICATED DISPOSABLE TEST USER</h1><form method=post action=/logout><button>Logout</button></form></body></html>")
        else:
            self._send(200,"<html><body><h1>DISPOSABLE LOGIN REQUIRED</h1><form method=post action=/login><button>Login as disposable test user</button></form></body></html>")
    def do_POST(self):
        if self.path=="/login":
            self._send(303,"",[("Set-Cookie",f"fixture_session={SESSION}; HttpOnly; SameSite=Strict; Path=/; Max-Age=3600"),("Location","/")])
        elif self.path=="/logout":
            self._send(303,"",[("Set-Cookie","fixture_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"),("Location","/")])
        else: self._send(404,"not found")

ThreadingHTTPServer(("0.0.0.0",8080),Handler).serve_forever()
