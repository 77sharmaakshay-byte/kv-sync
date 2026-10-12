#!/usr/bin/env python3
"""Database ke saare faislon ki chhantai: shreni -> vishay -> upvishay -> mudda -> nateeja (kl/taxonomy.py).

    python3 scripts/classify_db.py --db krishivlaw.db
    python3 scripts/classify_db.py --db krishivlaw.db --sample "Compassionate appointment" --n 25
    python3 scripts/classify_db.py --db krishivlaw.db --sample "Vivahit beti / bahu" --n 15

    python3 scripts/classify_db.py --db krishivlaw.db --tree
    python3 scripts/classify_db.py --db krishivlaw.db --khoj "Compassionate appointment" --mudda "Vivahit beti / bahu" \
        --nateeja "Paksh mein" --court UKHC

--tree: paanchon level ki ginti (shreni > vishay > upvishay > mudda, aur nateeja).
--khoj: upvishay (aur chaaho to mudda / nateeja / court) ke faisle, naye pehle.
--sample: kisi upvishay (ya mudda) ke random faisle, us jagah ke text ke saath (niyam jaanchne ke liye).
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


def sample(con, label, n, seed, pattern):
    rows = con.execute("SELECT l.judgment_id, l.strength, l.hits, j.court, j.case_no, j.neutral_citation, j.title, "
                       "l.mudda FROM labels l JOIN judgments j ON j.id = l.judgment_id "
                       "WHERE (l.upvishay = ? AND l.mudda = '') OR l.mudda = ?", (label, label)).fetchall()
    random.Random(seed).shuffle(rows)
    print(f"{label}: {len(rows)} faisle")
    for jid, strength, hits, court, case_no, cite, title, _ in rows[:n]:
        text = con.execute("SELECT clean FROM texts WHERE judgment_id = ?", (jid,)).fetchone()[0]
        m = re.search(pattern, text, re.I) if pattern else None
        at = m.start() if m else 0
        print(f"== {jid} {court} {case_no or cite or ''} [{strength}, {hits}] {(title or '')[:70]}")
        print("   " + re.sub(r"\s+", " ", text[max(0, at - 220):at + 260]))


def tree(con):
    last = (None, None)
    for cat, vishay, up, n_m, n_z in con.execute(
            "SELECT category, vishay, upvishay, sum(strength = 'mukhya'), sum(strength = 'zikr') FROM labels "
            "WHERE mudda = '' GROUP BY 1, 2, 3 ORDER BY 1, 2, 3"):
        if cat != last[0]:
            print(f"{cat}")
        if (cat, vishay) != last:
            print(f"  {vishay}")
        last = (cat, vishay)
        print(f"    {up:45s} mukhya {n_m:6d}  zikr {n_z:6d}")
        for mudda, n in con.execute("SELECT mudda, count(*) FROM labels WHERE upvishay = ? AND mudda != '' "
                                    "GROUP BY 1 ORDER BY 2 DESC", (up,)):
            print(f"      - {mudda:43s} {n:6d}")


def khoj(con, args):
    sql = ("SELECT k.court, k.case_no, k.neutral_citation, k.decision_date, k.strength, k.nateeja, k.title "
           "FROM khoj k WHERE k.upvishay = ? AND k.mudda = ?")
    params = [args.khoj, args.mudda or ""]
    for col, val in (("k.nateeja", args.nateeja), ("k.court", args.court)):
        if val:
            sql += f" AND {col} = ?"
            params.append(val)
    if not args.zikr:
        sql += " AND k.strength = 'mukhya'"
    rows = con.execute(sql + " ORDER BY k.decision_date DESC", params).fetchall()
    print(f"{len(rows)} faisle")
    for court, case_no, cite, date, strength, nateeja, title in rows[:args.n]:
        print(f"{date or '':10s} {court:4s} {case_no or cite or '':22s} {nateeja or '-':28s} {(title or '')[:70]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True, type=Path)
    ap.add_argument("--sample")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--near", help="namoone mein yeh regex jahan mile wahan ka text dikhao")
    ap.add_argument("--tree", action="store_true")
    ap.add_argument("--khoj", metavar="UPVISHAY")
    ap.add_argument("--mudda")
    ap.add_argument("--nateeja")
    ap.add_argument("--court", choices=["SC", "UKHC"])
    ap.add_argument("--zikr", action="store_true", help="--khoj mein sirf zikr wale faisle bhi")
    args = ap.parse_args()
    con = sqlite3.connect(args.db)
    if args.tree:
        tree(con)
        return 0
    if args.khoj:
        khoj(con, args)
        return 0
    if args.sample:
        sample(con, args.sample, args.n, args.seed, args.near)
        return 0
    t0 = time.time()
    classify.run(con, log=lambda m: print("  " + m, flush=True))
    for what in ("category", "outcome"):
        print(f"-- {what}")
        for v, n in con.execute(f"SELECT coalesce({what}, '(pata nahi)'), count(*) FROM categories GROUP BY 1 "
                                "ORDER BY 2 DESC"):
            print(f"   {v:30s} {n}")
    print(f"== Ho gaya ({time.time() - t0:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
