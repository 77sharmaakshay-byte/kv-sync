"""India server (Vercel, Mumbai 'bom1'): court ki site (ehcr.uk.gov.in) sirf India se khulti hai — yeh wahan se
cause list PDFs laa kar seedhe lautata hai (tar.gz: DD-MM-YYYY/ehcr.json + PDFs, Mac wale 'fetch' jaisa).
GitHub ka "Mac cause list" workflow bulata hai; text, data branch aur app wahi banata hai. ?test=1 = sirf ginti (JSON).
?kick=... = Vercel ka timer (vercel.json 'crons', shaam/subah): GitHub ka apna schedule ghanton der se ya chalta hi
nahi (1-2 Nov ki shaam ek bhi run nahi), isliye yahan se GitHub ko "Mac cause list" chalane ko kehte hain.
TRIGGER_TOKEN: sirf kv-sync, sirf Actions read/write (workflow chala sakta hai; code, files, secrets nahi).
?url=... = court ki do sites (ehcr, highcourtofuttarakhand.in) ka koi page jaisa India se dikhta hai (jaanch ke liye).
Env (.github/workflows/india-server.yml lagata hai): CRON_SECRET (chaabi), TRIGGER_TOKEN, REPO.
_ehcr.py = scripts/ukhc_ehcr.py ki copy (lagate waqt).
"""
import io
import json
import os
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ehcr  # noqa: E402


def run():
    start, err = time.time(), None
    for _ in range(3):   # site kabhi der se jawab deti hai; Vercel 300 second mein band kar deta hai
        out = Path(tempfile.mkdtemp())
        try:
            _ehcr.fetch(out)
            return out, None
        except Exception as e:  # noqa: BLE001 — kaisi bhi galti, dobara
            err = repr(e)
            if time.time() - start > 120:
                break
            time.sleep(10)
    return None, err


def kick():
    token, repo = os.environ.get("TRIGGER_TOKEN", ""), os.environ.get("REPO", "")
    if not token or not repo:
        return {"ok": False, "error": "TRIGGER_TOKEN / REPO nahi"}
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/actions/workflows/mac-causelist.yml/dispatches",
                                 data=b'{"ref": "main"}', method="POST",
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                          "User-Agent": "kv-relay"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            code = r.status
    except urllib.error.HTTPError as e:
        code = e.code
    return {"ok": code == 204, "github": code}


COURT_SITES = ("https://ehcr.uk.gov.in/", "https://highcourtofuttarakhand.in/", "https://www.highcourtofuttarakhand.in/")


def page(url):
    """Sirf court ki sites (khula proxy nahi); _ehcr ka opener: purane TLS ki chhoot + browser jaisa User-Agent."""
    if not url.startswith(COURT_SITES):
        return 400, "application/json", b'{"ok": false, "error": "sirf court ki site"}'
    try:
        with _ehcr.opener().open(url, timeout=60) as r:
            return r.status, r.headers.get("Content-Type", "text/html"), r.read()
    except urllib.error.HTTPError as e:
        return e.code, "text/plain", e.read()
    except Exception as e:  # noqa: BLE001
        return 502, "application/json", json.dumps({"ok": False, "error": repr(e)}).encode()


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        key = os.environ.get("CRON_SECRET", "")
        if not key or self.headers.get("Authorization") != f"Bearer {key}":
            return self.reply(401, "application/json", b'{"ok": false, "error": "chaabi galat"}')
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if "url" in q:
            return self.reply(*page(q["url"][0]))
        if "kick=" in self.path:
            res = kick()
            print(json.dumps(res))
            return self.reply(200 if res["ok"] else 502, "application/json", json.dumps(res).encode())
        out, err = run()
        if err:
            return self.reply(502, "application/json", json.dumps({"ok": False, "error": err}).encode())
        days = sorted(p.parent.name for p in out.glob("*/ehcr.json"))
        if "test=1" in self.path:
            res = {"ok": True, "days": days, "pdfs": sum(1 for _ in out.rglob("*.pdf"))}
            return self.reply(200, "application/json", json.dumps(res).encode())
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as t:
            for d in days:
                t.add(out / d, arcname=d)
        self.reply(200, "application/gzip", buf.getvalue(), {"X-Days": " ".join(days) or "-"})

    def reply(self, code, ctype, body, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)
