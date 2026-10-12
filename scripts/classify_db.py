#!/usr/bin/env python3
"""Database ke saare faislon ki chhantai: category -> vishay -> upvishay (kl/classify.py ke niyam).

    python3 scripts/classify_db.py --db krishivlaw.db
    python3 scripts/classify_db.py --db krishivlaw.db --sample "Compassionate appointment" --n 25

--sample: kisi upvishay ke random faisle, us jagah ke text ke saath (niyam jaanchne ke liye).
Dobara chalao to tables nayi ban jaati hain; database ka baaki hissa nahi chhoota.
"""
import argparse
import random
import re
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kl import classify  # noqa: E402


def sample(con, topic, n, seed):
    rows = con.execute("SELECT t.judgment_id, t.strength, t.hits, j.court, j.case_no, j.neutral_citation, j.title "
                       "FROM topics t JOIN judgments j ON j.id = t.judgment_id WHERE t.topic = ?", (topic,)).fetchall()
    random.Random(seed).shuffle(rows)
    for jid, strength, hits, court, case_no, cite, title in rows[:n]:
        text = con.execute("SELECT clean FROM texts WHERE judgment_id = ?", (jid,)).fetchone()[0]
        m = re.search(r"compassionate|harness|regulari|pension|promotion|transfer|terminat|dismiss|eligib|NDPS|POCSO|"
                      r"498|Negotiable", text, re.I)
        at = m.start() if m else 0
        print(f"== {jid} {court} {case_no or cite or ''} [{strength}, {hits}] {(title or '')[:70]}")
        print("   " + re.sub(r"\s+", " ", text[max(0, at - 220):at + 260]))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True, type=Path)
    ap.add_argument("--sample")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    con = sqlite3.connect(args.db)
    if args.sample:
        sample(con, args.sample, args.n, args.seed)
        return 0
    t0 = time.time()
    classify.run(con, log=lambda m: print("  " + m, flush=True))
    for cat, n in con.execute("SELECT coalesce(category, '(pata nahi)'), count(*) FROM categories GROUP BY 1 "
                              "ORDER BY 2 DESC"):
        print(f"{cat:18s} {n}")
    print(f"== Ho gaya ({time.time() - t0:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
