"""Vercel ka timer (vercel.json 'crons': shaam ~6:30-7:30, subah ~6:30-7:30 IST) — GitHub ka apna schedule ghanton der
se chalta hai ya chalta hi nahi (1-2 Nov ki shaam ek bhi run nahi), isliye yahan se GitHub ko "Mac cause list" chalane
ko kehte hain; woh phir causelist.py se list laata hai. TRIGGER_TOKEN: sirf kv-sync, sirf Actions read/write
(workflow chala sakta hai; code, files, secrets nahi). Env (india-server.yml): CRON_SECRET, TRIGGER_TOKEN, REPO.
"""
import json
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler


def dispatch(repo, token):
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/actions/workflows/mac-causelist.yml/dispatches",
                                 data=b'{"ref": "main"}', method="POST",
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                          "User-Agent": "kv-relay"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        key = os.environ.get("CRON_SECRET", "")
        if not key or self.headers.get("Authorization") != f"Bearer {key}":
            return self.reply(401, {"ok": False, "error": "chaabi galat"})
        token, repo = os.environ.get("TRIGGER_TOKEN", ""), os.environ.get("REPO", "")
        if not token or not repo:
            return self.reply(200, {"ok": False, "error": "TRIGGER_TOKEN / REPO nahi"})
        code = dispatch(repo, token)
        res = {"ok": code == 204, "github": code}
        print(json.dumps(res))
        self.reply(200 if res["ok"] else 502, res)

    def reply(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
