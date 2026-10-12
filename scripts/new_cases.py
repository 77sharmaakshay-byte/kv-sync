#!/usr/bin/env python3
"""Aaj aur aage ki cause list ke wo cases jinka court record app mein nahi hai (ya purana hai) — roz ke
naye cases miss na hon. 'Naye cases' workflow inhe uk-case se laata hai.

    python3 scripts/new_cases.py --data-branch databranch --max 150

state/case_fetched.json: {case id: 'YYYY-MM-DD' kab laaya}. --stale-days se purana record dobara (naye orders ke liye).
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
    args = ap.parse_args()
    src = args.data_branch
    fetched = {}
    state = src / "state" / "case_fetched.json"
    if state.exists():
        fetched = json.loads(state.read_text(encoding="utf-8"))
    today = today_ist()
    want = []
    for folder in sorted(p for p in (src / "causelist").glob("*") if p.is_dir()):
        try:
            day = dt.datetime.strptime(folder.name, "%d-%m-%Y").date()
        except ValueError:
            continue
        if day < today:
            continue
        for txt in sorted(folder.glob("*.txt")):
            for e in parse_causelist(txt.read_text(encoding="utf-8"))["entries"]:
                no = e.get("case_no")
                if not no or no in want:
                    continue
                cid = no.replace("/", "-")
                have = (src / "cases" / cid / "_case.json").exists()
                last = fetched.get(cid)
                old = not last or (today - dt.date.fromisoformat(last)).days >= args.stale_days
                if not have or (old and last):
                    want.append(no)
    print(f"# aaj/aage ki list mein naye ya purane record wale: {len(want)} (is baar {min(len(want), args.max)})",
          file=sys.stderr)
    print(" ".join(want[:args.max]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
