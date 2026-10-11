"""Court website se laaye naye judgments/orders (scripts/fetch_live.py) -> database.

fetch_live.py har PDF ke saath ek JSON (sidecar) rakhta hai:
    <data>/live/sc/<id>.pdf + <id>.json
    <data>/live/uk/<case>/<tarikh>-<n>.pdf + .json
Yahan woh JSON padh kar judgments mein row banti hai, phir PDF ka text/para
usi ingest wale raaste se banta hai. Jo PDF (sha256 se) database mein pehle
se hai — AWS ya Kaggle se — use dobara nahi jodte.
"""
import hashlib
import json
from pathlib import Path

from . import ingest

ARCHIVE = "live"
COLS = ("court", "title", "petitioner", "respondent", "case_no", "case_type", "decision_date",
        "neutral_citation", "cnr", "doc_kind")


def _row(con, rel, side, sha):
    year = int(side["decision_date"][:4]) if side.get("decision_date") else None
    judges = side.get("judges") or None
    meta = {k: side.get(k) for k in ("pdf_url", "source_url", "fetched_at", "order_type", "case_status", "fetched_by")}
    cur = con.execute(
        "INSERT INTO judgments (source, source_key, year, judges, bench_size, pdf_archive, pdf_member, pdf_sha256, "
        f"meta_json, {', '.join(COLS)}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, {', '.join('?' * len(COLS))}) "
        "ON CONFLICT(source_key) DO NOTHING",
        (side["source"], side["source_key"], year, json.dumps(judges, ensure_ascii=False) if judges else None,
         len(judges) if judges else None, ARCHIVE, rel, sha, json.dumps(meta, ensure_ascii=False))
        + tuple(side.get(k) or None for k in COLS))
    return cur.rowcount


def load(con, data_dir, workers=None, log=print):
    data_dir = Path(data_dir)
    root = data_dir / "live"
    # '_case.json' (case page) aur '_gap/' (court ki lists) PDF ke sidecar nahi hain.
    sides = sorted(p for p in root.glob("**/*.json")
                   if not any(part.startswith("_") for part in p.relative_to(root).parts)) if root.exists() else []
    known = {r[0] for r in con.execute("SELECT pdf_sha256 FROM judgments WHERE pdf_sha256 IS NOT NULL")}
    # AWS mein case ka aakhri faisla pehle se ho (wahi CNR + tarikh) to court wali copy dobara nahi.
    known_cd = {(r[0], r[1]) for r in con.execute(
        "SELECT cnr, decision_date FROM judgments WHERE cnr IS NOT NULL AND decision_date IS NOT NULL "
        "AND (pdf_archive IS NULL OR pdf_archive != ?)", (ARCHIVE,))}
    stats = {"files": len(sides), "added": 0, "already": 0, "bad": 0}
    for sp in sides:
        pdf = sp.with_suffix(".pdf")
        try:
            side = json.loads(sp.read_text(encoding="utf-8"))
            if not (side.get("source") and side.get("source_key") and side.get("court")) or not pdf.exists():
                raise ValueError("source/source_key/court ya PDF nahi")
        except ValueError as err:
            stats["bad"] += 1
            log(f"[chhoda] {sp}: {err}")
            continue
        sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
        if sha in known or (side.get("cnr"), side.get("decision_date")) in known_cd:
            stats["already"] += 1
            continue
        if _row(con, str(pdf.relative_to(data_dir)), side, sha):
            known.add(sha)
            stats["added"] += 1
        else:
            stats["already"] += 1
    con.commit()
    log(f"Live: {stats['files']} files, {stats['added']} naye, {stats['already']} pehle se, {stats['bad']} kharab.")
    todo = con.execute("SELECT id, court, pdf_member FROM judgments WHERE pdf_archive = ? "
                       "AND (text_version IS NULL OR text_version < ?)", (ARCHIVE, ingest.PARSER_VERSION)).fetchall()
    log(f"Live: {len(todo)} PDFs padhne hain...")
    stats.update(ingest.run_items(con, ((jid, court, (data_dir / m).read_bytes()) for jid, court, m in todo),
                                  workers=workers))
    return stats
