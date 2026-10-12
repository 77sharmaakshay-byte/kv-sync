#!/usr/bin/env python3
"""App ke 'Khoj' tab ke liye: har upvishay / mudda ke chune hue faisle (asli paragraph + nateeja) aur
phone par chalne wale milaan-niyam (kl/taxonomy.py ke FTS niyam se bane regex).

    python3 scripts/export_khoj.py --db krishivlaw.db --out databranch/khoj

Nateeja: <out>/index.json (vishay ka ped, niyam, ginti) + <out>/t/<slug>.json (har upvishay ke faisle).
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

PER_TOPIC, PER_MUDDA = 8, 4   # har court se


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


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    con = sqlite3.connect(args.db)
    (args.out / "t").mkdir(parents=True, exist_ok=True)
    topics = []
    for cat, vishay, up, query, checked in taxonomy.TOPICS:
        n = con.execute("SELECT count(*) FROM labels WHERE upvishay = ? AND mudda = '' AND strength = 'mukhya'",
                        (up,)).fetchone()[0]
        doc = {"upvishay": up, "judgments": similar(con, up, None, query, PER_TOPIC), "by_mudda": {}}
        issues = []
        for mudda, mq in taxonomy.ISSUES.get(up, []):
            cnt = con.execute("SELECT count(*) FROM labels WHERE upvishay = ? AND mudda = ?", (up, mudda)).fetchone()[0]
            doc["by_mudda"][mudda] = similar(con, up, mudda, query, PER_MUDDA)
            issues.append({"mudda": mudda, "rules": js_rules(mq), "faisle": cnt})
        (args.out / "t" / f"{slug(up)}.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")),
                                                        encoding="utf-8")
        topics.append({"id": slug(up), "shreni": cat, "vishay": vishay, "upvishay": up, "jaancha": checked,
                       "faisle": n, "rules": js_rules(query), "issues": issues})
        print(f"{cat} / {vishay} / {up}: {n} faisle, {len(doc['judgments'])} chune, {len(issues)} mudde")
    (args.out / "index.json").write_text(json.dumps({"topics": topics}, ensure_ascii=False, separators=(",", ":")),
                                         encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
