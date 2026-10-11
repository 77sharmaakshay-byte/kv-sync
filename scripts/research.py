#!/usr/bin/env python3
"""Ek case ke saare mudde database mein dhundho — bina limit ke — aur report file banao.

    .venv/bin/python scripts/research.py --data ~/krishivlaw-data --topics config/topics/compassionate.json

Har topic ek ya zyada FTS queries hain. Report (Markdown) mein HAR milne wala
judgment aata hai: kis topic mein mila, court, saal, citation, aur sabse
milta-julta para ka chhota hissa. Pehle Supreme Court, phir High Court, naye
pehle. Report file chat mein upload karke aage ka vishleshan hota hai.
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kl import db  # noqa: E402

SNIPPET = 320


def run_query(con, query):
    """{judgment_id: (hits, best_para_text)} — saare matches, koi limit nahi."""
    out = {}
    rows = con.execute(
        "SELECT p.judgment_id, p.text, bm25(paragraphs_fts) AS score FROM paragraphs_fts "
        "JOIN paragraphs p ON p.id = paragraphs_fts.rowid WHERE paragraphs_fts MATCH ? ORDER BY score",
        (query,))
    for jid, text, _ in rows:
        hits, best = out.get(jid, (0, None))
        out[jid] = (hits + 1, best or text)
    return out


def snippet(text, query):
    words = [w.strip('"()').lower() for w in re.findall(r'"[^"]+"|\w+', query)
             if w.upper() not in ("AND", "OR", "NOT", "NEAR")]
    low = text.lower()
    pos = min([i for i in (low.find(w) for w in words if w) if i >= 0] or [0])
    s = max(0, pos - SNIPPET // 3)
    return " ".join(text[s:s + SNIPPET].split())


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", required=True, type=Path)
    ap.add_argument("--db", type=Path)
    ap.add_argument("--topics", required=True, type=Path, help="JSON: {naam, topics: [{id, title, queries: [...]}]}")
    ap.add_argument("--out", type=Path, help="report file (default: <data>/research-<naam>.md)")
    args = ap.parse_args()

    data = args.data.expanduser()
    con = db.connect((args.db or data / "krishivlaw.db").expanduser())
    spec = json.loads(args.topics.read_text(encoding="utf-8"))
    found = defaultdict(lambda: {"topics": set(), "hits": 0, "snip": None})
    counts = {}
    for topic in spec["topics"]:
        ids = set()
        for q in topic["queries"]:
            for jid, (hits, text) in run_query(con, q).items():
                f = found[jid]
                f["topics"].add(topic["id"])
                f["hits"] += hits
                if f["snip"] is None:
                    f["snip"] = snippet(text, q)
                ids.add(jid)
        counts[topic["id"]] = len(ids)

    meta = {}
    if found:
        marks = ",".join("?" * len(found))
        for r in con.execute(f"SELECT id, court, year, decision_date, title, case_no, neutral_citation, "
                             f"report_citation, disposal, source FROM judgments WHERE id IN ({marks})", list(found)):
            meta[r["id"]] = r
    order = sorted(found, key=lambda j: (meta[j]["court"] != "SC", -(meta[j]["year"] or 0), -found[j]["hits"]))

    out = (args.out or data / f"research-{spec['naam']}.md").expanduser()
    lines = [f"# Research: {spec['naam']}", "",
             f"Kul {len(found)} documents (SC {sum(meta[j]['court'] == 'SC' for j in found)}, "
             f"HC {sum(meta[j]['court'] != 'SC' for j in found)}).", "", "| Topic | Documents |", "|---|---:|"]
    lines += [f"| {t['id']} — {t['title']} | {counts[t['id']]} |" for t in spec["topics"]]
    lines.append("")
    for j in order:
        m, f = meta[j], found[j]
        cite = m["neutral_citation"] or m["report_citation"] or m["case_no"] or ""
        lines += [f"## {m['court']} {m['year'] or ''} · {cite} · {m['title'] or ''}",
                  f"- id {j} · tarikh {m['decision_date'] or '?'} · nateeja {m['disposal'] or '?'} · source {m['source']}",
                  f"- topics: {', '.join(sorted(f['topics']))} · {f['hits']} para mile",
                  f"- > {f['snip']}", ""]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(found)} documents mile. Report: {out}")
    for t in spec["topics"]:
        print(f"  {counts[t['id']]:5d}  {t['id']} — {t['title']}")


if __name__ == "__main__":
    sys.exit(main())
