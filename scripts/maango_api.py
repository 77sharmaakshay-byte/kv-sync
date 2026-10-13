#!/usr/bin/env python3
"""App ka 'Abhi vishleshan karo' button: case number lo, GitHub par 'Case lookup' chalao (record + orders);
uske baad 'Case analysis' apne aap (vishay, mudde, milte-julte faisle) aur app update.

Render Web Service (free) par: Start Command `python scripts/maango_api.py`, env GH_TOKEN (fine-grained token,
sirf is repo ka 'Actions: Read and write'). Token kabhi repo ya app mein nahi.

    POST /maango  {"case": "WPSS/1992/2026"}  ->  {"ok": true, "msg": "..."}
    GET  /health

Sirf standard library. Ek case 6 ghante mein ek baar; poore ghante mein 40 maang tak; 45 second ki maang
ek saath ek run mein (har click par alag run nahi).
"""
import json
import os
import re
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPO = os.environ.get("REPO", "77sharmaakshay-byte/krishivlaw")
WORKFLOW = "case-lookup.yml"
ORIGINS = [o.strip() for o in os.environ.get("ORIGINS", "https://nyay-sahayak-jn1t.onrender.com").split(",") if o.strip()]
CASE_RE = re.compile(r"^[A-Z][A-Z0-9]{1,11}/\d{1,6}/(19|20)\d{2}$")
SAME_CASE_SEC, HOUR_LIMIT, BATCH_SEC = 6 * 3600, 40, 45

lock = threading.Lock()
recent = {}      # case -> kab maanga (time.time())
hour = []        # is ghante ki maang ke samay
batch = []       # agle run mein jaane wale cases


def dispatch(cases):
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW}/dispatches",
        data=json.dumps({"ref": "main", "inputs": {"cases": " ".join(cases)}}).encode(),
        headers={"Authorization": f"Bearer {os.environ['GH_TOKEN']}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "nyay-maango"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status


def flusher():
    while True:
        time.sleep(BATCH_SEC)
        with lock:
            cases, batch[:] = list(batch), []
        if not cases:
            continue
        try:
            print("dispatch", cases, dispatch(cases), flush=True)
        except Exception as err:  # noqa: BLE001 — agli baar dobara
            print("dispatch fail", cases, err, flush=True)
            with lock:
                batch.extend(c for c in cases if c not in batch)


def ask(case):
    now = time.time()
    with lock:
        hour[:] = [t for t in hour if now - t < 3600]
        if case in batch or now - recent.get(case, 0) < SAME_CASE_SEC:
            return True, "Is case ki maang pehle se line mein hai. Thodi der mein app par aa jaayega."
        if len(hour) >= HOUR_LIMIT:
            return False, "Abhi bahut maang aa gayi hai, ek ghante baad dobara dabaiye."
        hour.append(now)
        recent[case] = now
        batch.append(case)
    return True, "Maang bhej di. Court se record aur poora vishleshan ~20-30 minute mein yahin aa jaayega."


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        origin = self.headers.get("Origin", "")
        if origin in ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):  # noqa: N802
        self._send(204 if self.headers.get("Origin", "") in ORIGINS else 403, {})

    def do_GET(self):  # noqa: N802
        self._send(200 if self.path == "/health" else 404, {"ok": self.path == "/health"})

    def do_POST(self):  # noqa: N802
        if self.path != "/maango":
            return self._send(404, {"ok": False})
        if self.headers.get("Origin", "") not in ORIGINS:
            return self._send(403, {"ok": False, "msg": "Sirf app se"})
        try:
            size = int(self.headers.get("Content-Length") or 0)
            case = str(json.loads(self.rfile.read(min(size, 1000)) or b"{}").get("case", "")).strip().upper()
        except (ValueError, AttributeError):
            case = ""
        if not CASE_RE.match(case):
            return self._send(400, {"ok": False, "msg": "Case number samajh nahi aaya (jaise WPSS/1992/2026)"})
        ok, msg = ask(case)
        self._send(200 if ok else 429, {"ok": ok, "msg": msg})

    def log_message(self, fmt, *args):
        print(self.address_string(), fmt % args, flush=True)


def main():
    if not os.environ.get("GH_TOKEN"):
        raise SystemExit("GH_TOKEN env nahi hai (Render > Environment mein daalo)")
    threading.Thread(target=flusher, daemon=True).start()
    port = int(os.environ.get("PORT", "10000"))
    print(f"maango API :{port} -> {REPO} {WORKFLOW}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
