#!/usr/bin/env python3
"""Nyay Sahayak ka keyword search (Indian Kanoon jaisa): SC + Nainital HC ke saare faisle, paragraph tak.

Aapke Mac par chalta hai (.github/workflows/mac-search.yml: database Kaggle se, Cloudflare tunnel). DATA_DIR mein
krishivlaw.db na ho to HF dataset (DB_REPO) se laata hai. SQLite FTS5 (porter); sirf standard library.

    GET /health                       -> {"ready": bool, "faisle": n}
    GET /search?q=&court=&nateeja=&from=&to=&page=
    GET /j/<id>?q=                    -> poora faisla, q wale paragraph chinhit
    GET /stats?key=                   -> kaunse shabd dhoonde gaye (sirf ginti; sawaal ka text/IP nahi rakhte)

Query: shabd = sab hone chahiye (AND); "do shabd" = phrase; -shabd = ye na ho.
"""
import gzip
import hashlib
import json
import os
import re
import shutil
import sqlite3
import threading
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

DB_REPO = os.environ.get("DB_REPO", "")
TOKEN = os.environ.get("HF_TOKEN", "")
ADMIN_KEY = hashlib.sha256(TOKEN.encode()).hexdigest()[:32] if TOKEN else ""
ORIGINS = [o.strip() for o in os.environ.get("ORIGINS", "https://nyay-sahayak-jn1t.onrender.com").split(",") if o.strip()]
DATA = os.environ.get("DATA_DIR", "/tmp/nyay")
DB = os.path.join(DATA, "krishivlaw.db")
PAGE, CANDIDATES, MAX_TEXT = 20, 3000, 120000
STOP = set("a an the of in on to for and or is are was were be by with as at from that this it its".split())
GOOD = ("Paksh mein", "Aanshik paksh mein", "Nirdesh: vibhag vichaar kare")

state = {"ready": False, "error": None, "faisle": 0}
terms = Counter()
hits_ip = {}
local = threading.local()


def prepare():
    """Database HF dataset se lao (ek baar), kholo."""
    try:
        os.makedirs(DATA, exist_ok=True)
        if not os.path.exists(DB):
            from huggingface_hub import hf_hub_download
            gz = hf_hub_download(DB_REPO, "krishivlaw.db.gz", repo_type="dataset", token=TOKEN or None,
                                 local_dir=DATA)
            with gzip.open(gz, "rb") as src, open(DB + ".tmp", "wb") as dst:
                shutil.copyfileobj(src, dst, 16 << 20)
            os.replace(DB + ".tmp", DB)
            os.remove(gz)
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        state["faisle"] = con.execute("SELECT count(*) FROM judgments").fetchone()[0]
        state["ready"] = True
        print("taiyaar:", state["faisle"], "faisle", flush=True)
    except Exception as err:  # noqa: BLE001 — /health par dikhe
        state["error"] = f"{type(err).__name__}: {err}"
        print("database nahi khula:", state["error"], flush=True)


def db():
    if not hasattr(local, "con"):
        local.con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, check_same_thread=False)
        local.con.execute("PRAGMA mmap_size = 4000000000")
    return local.con


def fts_query(q):
    """Aam aadmi ki query -> surakshit FTS5 query (har shabd quote mein, taaki galat syntax se error na ho)."""
    q = (q or "")[:300]
    must, nots = [], []
    for phrase in re.findall(r'"([^"]+)"', q):
        words = re.findall(r"[A-Za-z0-9]+", phrase)
        if words:
            must.append('"' + " ".join(words) + '"')
    rest = re.sub(r'"[^"]*"', " ", q)
    for neg, word in re.findall(r"(-?)([A-Za-z0-9]+)", rest):
        if word.lower() in STOP or (len(word) < 2 and not word.isdigit()):
            continue
        (nots if neg else must).append(f'"{word}"')
    if not must:
        return None, []
    query = " AND ".join(must) + "".join(f" NOT {n}" for n in nots)
    return (f"({query})" if nots else query), [m.strip('"') for m in must]


def search(params):
    query, words = fts_query(params.get("q"))
    if not query:
        return {"error": "Kam se kam ek shabd likho"}
    where, args = ["paragraphs_fts MATCH ?", "p.section != 'header'"], [query]
    court = params.get("court")
    if court in ("SC", "UKHC"):
        where.append("j.court = ?"); args.append(court)
    for key, op in (("from", ">="), ("to", "<=")):
        if re.fullmatch(r"\d{4}", params.get(key) or ""):
            where.append(f"j.year {op} ?"); args.append(int(params[key]))
    nateeja = params.get("nateeja")
    if nateeja == "good":
        where.append(f"c.outcome IN ({','.join('?' * len(GOOD))})"); args += list(GOOD)
    elif nateeja == "bad":
        where.append("c.outcome LIKE 'Khilaf%'")
    page = max(0, min(int(params.get("page") or 0), 50))
    t = time.time()
    rows = db().execute(
        "WITH h AS (SELECT p.judgment_id AS jid, p.id AS pid, bm25(paragraphs_fts) AS s FROM paragraphs_fts "
        "JOIN paragraphs p ON p.id = paragraphs_fts.rowid JOIN judgments j ON j.id = p.judgment_id "
        f"LEFT JOIN categories c ON c.judgment_id = j.id WHERE {' AND '.join(where)} ORDER BY s LIMIT {CANDIDATES}) "
        "SELECT jid, pid, min(s), count(*) FROM h GROUP BY jid ORDER BY min(s)", args).fetchall()
    total = len(rows)
    out = []
    for jid, pid, score, n in rows[page * PAGE:(page + 1) * PAGE]:
        meta = db().execute(
            "SELECT j.court, j.title, j.case_no, j.neutral_citation, j.report_citation, j.decision_date, j.judges, "
            "c.outcome FROM judgments j LEFT JOIN categories c ON c.judgment_id = j.id WHERE j.id = ?", (jid,)).fetchone()
        snip = db().execute("SELECT snippet(paragraphs_fts, 0, '[[', ']]', '…', 48) FROM paragraphs_fts "
                            "WHERE paragraphs_fts MATCH ? AND rowid = ?", (query, pid)).fetchone()
        para = db().execute("SELECT para_no FROM paragraphs WHERE id = ?", (pid,)).fetchone()
        court, title, case_no, cite, report, date, judges, outcome = meta
        out.append({"id": jid, "court": "Supreme Court" if court == "SC" else "Nainital HC", "title": title or case_no,
                    "case_no": case_no, "cite": cite or report, "date": date,
                    "judges": (judges or "").strip("[]").replace('"', "").split(",")[0],
                    "nateeja": outcome, "paras": n, "para": para[0] if para else None,
                    "snippet": re.sub(r"\s+", " ", snip[0]) if snip else ""})
    terms.update(w.lower() for w in words)
    return {"q": params.get("q"), "query": query, "total": total, "more": total >= CANDIDATES // 3,
            "page": page, "results": out, "ms": int((time.time() - t) * 1000)}


def judgment(jid, params):
    con = db()
    row = con.execute("SELECT j.court, j.title, j.case_no, j.neutral_citation, j.report_citation, j.decision_date, "
                      "j.judges, j.disposal, j.pages, c.outcome FROM judgments j LEFT JOIN categories c "
                      "ON c.judgment_id = j.id WHERE j.id = ?", (jid,)).fetchone()
    if not row:
        return None
    court, title, case_no, cite, report, date, judges, disposal, pages, outcome = row
    paras, size = [], 0
    for seq, no, section, text in con.execute("SELECT seq, para_no, section, text FROM paragraphs WHERE judgment_id = ? "
                                              "AND section != 'header' ORDER BY seq", (jid,)):
        text = re.sub(r"[ \t]+", " ", text).strip()
        if size + len(text) > MAX_TEXT:
            paras.append({"seq": seq, "no": None, "text": "[… aage ka text yahan nahi; poora faisla court ki copy mein]"})
            break
        paras.append({"seq": seq, "no": no, "text": text})
        size += len(text)
    hits = []
    query, _ = fts_query(params.get("q"))
    if query:
        hits = [r[0] for r in con.execute(
            "SELECT p.seq FROM paragraphs_fts JOIN paragraphs p ON p.id = paragraphs_fts.rowid WHERE paragraphs_fts "
            "MATCH ? AND p.judgment_id = ? ORDER BY bm25(paragraphs_fts) LIMIT 5", (query, jid))]
    return {"id": jid, "court": "Supreme Court" if court == "SC" else "Nainital HC", "title": title, "case_no": case_no,
            "cite": cite, "report": report, "date": date, "judges": judges, "disposal": disposal, "pages": pages,
            "nateeja": outcome, "hits": hits, "paras": paras}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        origin = self.headers.get("Origin", "")
        if origin in ORIGINS or origin.startswith("http://127.0.0.1"):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        url = urlparse(self.path)
        params = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path in ("/", "/health"):
            return self._send(200, {k: state[k] for k in ("ready", "error", "faisle")})
        if url.path == "/stats":
            if not ADMIN_KEY or params.get("key") != ADMIN_KEY:
                return self._send(403, {"error": "nahi"})
            return self._send(200, dict(terms.most_common(500)))
        if not state["ready"]:
            return self._send(503, {"error": "Server jaag raha hai, database khul raha hai (2-5 minute)",
                                    "jaag": True, "detail": state["error"]})
        ip = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0]
        now = time.time()
        recent = [t for t in hits_ip.get(ip, []) if now - t < 60]
        if len(recent) >= 40:
            return self._send(429, {"error": "Bahut tez; ek minute ruk kar"})
        hits_ip[ip] = recent + [now]
        try:
            if url.path == "/search":
                return self._send(200, search(params))
            m = re.fullmatch(r"/j/(\d+)", url.path)
            if m:
                d = judgment(int(m.group(1)), params)
                return self._send(200 if d else 404, d or {"error": "faisla nahi mila"})
        except sqlite3.OperationalError as err:
            return self._send(400, {"error": f"Query samajh nahi aayi: {err}"})
        self._send(404, {"error": "nahi mila"})

    def log_message(self, fmt, *args):
        pass   # sawaal (client ki baat ho sakti hai) log mein nahi


def main():
    threading.Thread(target=prepare, daemon=True).start()
    port = int(os.environ.get("PORT", "7860"))
    print(f"nyay search :{port} <- {DB_REPO}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
