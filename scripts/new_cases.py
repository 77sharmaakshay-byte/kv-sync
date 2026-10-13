#!/usr/bin/env python3
"""Aaj aur aage ki cause list ke wo cases jinka court record app mein nahi hai (ya purana hai) — roz ke
naye cases miss na hon. 'Naye cases' workflow inhe uk-case se laata hai.

    python3 scripts/new_cases.py --data-branch databranch --max 150

state/case_fetched.json: {case id: 'YYYY-MM-DD' kab laaya}. --stale-days se purana record dobara (naye orders ke liye).
Cause list ke baad advocates/*.json (workflow 'Advocate ke cases') ke saare cases: jinka record nahi, ya
--adv-stale-days se purana — chune hue advocate ka poora kaam bhi dheere-dheere (har baar chhatha hissa unka).
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_app_data import parse_causelist  # noqa: E402


def today_ist():
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=5, minutes=30)).date()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data-branch", required=True, type=Path)
    ap.add_argument("--max", type=int, default=150)
    ap.add_argument("--stale-days", type=int, default=7)
    ap.add_argument("--adv-stale-days", type=int, default=14)
    args = ap.parse_args()
    src = args.data_branch
    fetched = {}
    state = src / "state" / "case_fetched.json"
    if state.exists():
        fetched = json.loads(state.read_text(encoding="utf-8"))
    today = today_ist()
    want = []

    def need(no, stale_days):
        cid = no.replace("/", "-")
        have = (src / "cases" / cid / "_case.json").exists()
        last = fetched.get(cid)
        old = not last or (today - dt.date.fromisoformat(last)).days >= stale_days
        return not have or (old and last)

    days = []
    for folder in (p for p in (src / "causelist").glob("*") if p.is_dir()):
        try:
            day = dt.datetime.strptime(folder.name, "%d-%m-%Y").date()
        except ValueError:
            continue
        if day >= today:
            days.append((day, folder))
    # Shaam 3 baje ke baad kal ki list pehle (court ~5:30 daalta hai; 7 baje tak taiyaar), warna aaj ki
    evening = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=5, minutes=30)).hour >= 15
    days.sort(key=lambda x: (evening and x[0] == today, x[0]))
    for day, folder in days:
        for txt in sorted(folder.glob("*.txt")):
            for e in parse_causelist(txt.read_text(encoding="utf-8"))["entries"]:
                no = e.get("case_no")
                if no and no not in want and need(no, args.stale_days):
                    want.append(no)
    adv = []
    for f in sorted((src / "advocates").glob("*.json")):
        for c in json.loads(f.read_text(encoding="utf-8")).get("cases", []):
            no = c.get("case")
            if no and no not in want and no not in adv and need(no, args.adv_stale_days):
                adv.append(no)
    # Har baar kam se kam chhatha hissa advocate walon ko (roz ki lambi list mein woh atke na rahein)
    n_adv = min(len(adv), max(args.max // 6, args.max - len(want)))
    pick = want[:args.max - n_adv] + adv[:n_adv]   # list wale pehle laaye jaate hain
    print(f"# aaj/aage ki list mein naye ya purane record wale: {len(want)}, advocates ke: {len(adv)} "
          f"(is baar {len(pick)}: advocate ke {n_adv})", file=sys.stderr)
    print(" ".join(pick))
    return 0


if __name__ == "__main__":
    sys.exit(main())
