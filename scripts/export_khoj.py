#!/usr/bin/env python3
"""App ke 'Khoj' tab ke liye: har upvishay / mudda ke chune hue faisle (asli paragraph + nateeja) aur
phone par chalne wale milaan-niyam (kl/taxonomy.py ke FTS niyam se bane regex).

    python3 scripts/export_khoj.py --db krishivlaw.db --out databranch/khoj

Nateeja: <out>/index.json (vishay ka ped, niyam, ginti) + <out>/t/<slug>.json (har upvishay ke faisle) + <out>/j/<id>.json (har chune faisle ka poora text).
--notes <notes_auto>: cases ke auto notes wale (paksh/khilaf) faislon ka poora text bhi, taaki case ke page se click par khule.
build_app_data.py ise site ke data/khoj/ mein daalta hai; app bina server ke milaan karta hai.
"""
import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from kl import taxonomy  # noqa: E402
from auto_notes import similar  # noqa: E402

PER_TOPIC, PER_MUDDA = 8, 6   # har court se
MAX_TEXT = 90000              # ek faisle ka poora text (akshar) app mein, isse lamba ho to kaat do


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def word_re(w):
    w = w.lower()
    if re.fullmatch(r"\d+[a-z]?", w):
        return r"\b" + re.escape(w) + r"\b"
    stem = w[:max(4, min(len(w), 7))]
    return r"\b" + re.escape(stem) + r"\w*"


def term_re(term):
    words = re.findall(r"[A-Za-z0-9]+", term)
    return r"\W+(?:\w+\W+){0,2}".join(word_re(w) for w in words) if words else None


def js_rules(query):
    """FTS query -> [[regex, ...], ...]: bahar ki list OR, andar ki AND. NOT wala hissa chhod dete hain."""
    q = re.split(r"\)\s*NOT\s+", query)[0].strip()
    q = q[1:] if q.startswith("(") else q
    alts = []
    for alt in re.split(r"\s+OR\s+", q):
        alt = alt.strip().strip("()")
        m = re.match(r"NEAR\((.*),\s*\d+\s*\)?$", alt)
        inner = m.group(1) if m else alt
        terms = re.findall(r'"([^"]+)"|(\S+)', inner)
        regs = [term_re(a or b) for a, b in terms]
        regs = [r for r in regs if r]
        if regs:
            alts.append(regs)
    return alts


def judgment_doc(con, jid, matches):
    """Ek chune faisle ki detail: record, kaunse paragraph kis vishay/mudde se mile, aur poora text."""
    (title, court, case_no, cite, report, date, judges, disposal, pages) = con.execute(
        "SELECT title, court, case_no, neutral_citation, report_citation, decision_date, judges, disposal, pages "
        "FROM judgments WHERE id = ?", (jid,)).fetchone()
    nateeja = (con.execute("SELECT outcome FROM categories WHERE judgment_id = ?", (jid,)).fetchone() or [None])[0]
    paras, size = [], 0
    for seq, no, section, text in con.execute("SELECT seq, para_no, section, text FROM paragraphs WHERE judgment_id = ? "
                                              "AND section != 'header' ORDER BY seq", (jid,)):
        text = re.sub(r"[ \t]+", " ", text).strip()
        if size + len(text) > MAX_TEXT:
            paras.append({"seq": seq, "no": None, "text": "[… aage ka text app mein nahi; poora faisla court ki copy mein]"})
            break
        paras.append({"seq": seq, "no": no, "section": section, "text": text})
        size += len(text)
    hits = {}
    for label, query in matches.items():
        hits[label] = [r[0] for r in con.execute(
            "SELECT p.seq FROM paragraphs_fts f JOIN paragraphs p ON p.id = f.rowid WHERE paragraphs_fts MATCH ? "
            "AND p.judgment_id = ? AND p.section != 'header' ORDER BY bm25(paragraphs_fts) LIMIT 3", (query, jid))]
    return {"id": jid, "title": title, "court": "Supreme Court" if court == "SC" else "Nainital HC",
            "case_no": case_no, "cite": cite, "report": report, "date": date, "judges": judges,
            "disposal": disposal, "nateeja": nateeja, "pages": pages, "hits": hits, "paras": paras}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--notes", type=Path, help="notes_auto folder (case ke milte-julte faisle bhi)")
    args = ap.parse_args()
    con = sqlite3.connect(args.db)
    (args.out / "t").mkdir(parents=True, exist_ok=True)
    (args.out / "j").mkdir(parents=True, exist_ok=True)
    topics, wanted = [], {}   # wanted: judgment id -> {label: FTS query} (detail mein kaunse paragraph upar)
    for cat, vishay, up, query, checked in taxonomy.TOPICS:
        n = con.execute("SELECT count(*) FROM labels WHERE upvishay = ? AND mudda = '' AND strength = 'mukhya'",
                        (up,)).fetchone()[0]
        doc = {"upvishay": up, "judgments": similar(con, up, None, query, PER_TOPIC), "by_mudda": {}}
        issues = []
        for mudda, mq in taxonomy.ISSUES.get(up, []):
            cnt = con.execute("SELECT count(*) FROM labels WHERE upvishay = ? AND mudda = ?", (up, mudda)).fetchone()[0]
            doc["by_mudda"][mudda] = similar(con, up, mudda, mq, PER_MUDDA)  # quote mudde wala paragraph
            issues.append({"mudda": mudda, "rules": js_rules(mq), "faisle": cnt})
        for j in doc["judgments"]:
            wanted.setdefault(j["id"], {})[up] = query
        for mudda, mq in taxonomy.ISSUES.get(up, []):
            for j in doc["by_mudda"][mudda]:
                wanted.setdefault(j["id"], {})[mudda] = mq
        (args.out / "t" / f"{slug(up)}.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")),
                                                        encoding="utf-8")
        topics.append({"id": slug(up), "shreni": cat, "vishay": vishay, "upvishay": up, "jaancha": checked,
                       "faisle": n, "rules": js_rules(query), "issues": issues})
        print(f"{cat} / {vishay} / {up}: {n} faisle, {len(doc['judgments'])} chune, {len(issues)} mudde")
    queries = {t[2]: t[3] for t in taxonomy.TOPICS}
    queries.update({m: q for issues in taxonomy.ISSUES.values() for m, q in issues})
    for f in sorted(args.notes.glob("*.json")) if args.notes and args.notes.exists() else []:
        for j in json.loads(f.read_text(encoding="utf-8")).get("similar") or []:
            if j.get("id") and queries.get(j.get("mudda")):
                wanted.setdefault(j["id"], {})[j["mudda"]] = queries[j["mudda"]]
    for jid, matches in wanted.items():
        (args.out / "j" / f"{jid}.json").write_text(json.dumps(judgment_doc(con, jid, matches), ensure_ascii=False,
                                                               separators=(",", ":")), encoding="utf-8")
    print(f"{len(wanted)} faislon ki detail")
    (args.out / "index.json").write_text(json.dumps({"topics": topics}, ensure_ascii=False, separators=(",", ":")),
                                         encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
