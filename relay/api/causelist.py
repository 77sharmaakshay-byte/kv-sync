"""India server (Vercel, Mumbai 'bom1'): court ki site (ehcr.uk.gov.in) sirf India se khulti hai — yeh wahan se
cause list PDFs laa kar seedhe lautata hai (tar.gz: DD-MM-YYYY/ehcr.json + PDFs, Mac wale 'fetch' jaisa).
GitHub ka "Mac cause list" workflow bulata hai; text, data branch aur app wahi banata hai. Iske paas GitHub ka koi
token nahi. ?test=1 = sirf ginti (JSON). Env (.github/workflows/india-server.yml lagata hai): CRON_SECRET (chaabi).
_ehcr.py = scripts/ukhc_ehcr.py ki copy (lagate waqt).
"""
import io
import json
import os
import sys
import tarfile
import tempfile
import time
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


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        key = os.environ.get("CRON_SECRET", "")
        if not key or self.headers.get("Authorization") != f"Bearer {key}":
            return self.reply(401, "application/json", b'{"ok": false, "error": "chaabi galat"}')
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
