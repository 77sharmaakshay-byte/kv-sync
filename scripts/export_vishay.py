#!/usr/bin/env python3
"""Ek upvishay (jaise Compassionate appointment) ke saare cases ki list, database se: CSV + Markdown table.

    python3 scripts/export_vishay.py --db krishivlaw.db --upvishay "Compassionate appointment" --out out/

Har case (Nainital HC: CNR, warna case number; SC: faisla) ek line:
  case number, parties, pehle aur aakhri order ki tareekh, database mein kitni tareekhon ke order,
  aakhri order ka disposal (court ki site se) aur nateeja (machine ki chhantai, kl/classify.py), judge.
"Orders ki ginti" = database mein us case ke alag-alag tareekh wale orders. Court ki har hearing ka order
database mein ho, yeh zaroori nahi — isliye yeh hearing ki pakki ginti nahi; pakki ginti case lookup
(court ki site ka case history) se.
Nateeja machine ka hai; kisi faisle par bharosa karne se pehle poora faisla aur appeal (SPA/SLP) dekhein.
"""
import argparse
import csv
import json
import re
import sqlite3
from pathlib import Path

COLS = ["court", "case_no", "cnr", "petitioner", "respondent", "pehla_order", "aakhri_order", "orders",
        "disposal", "nateeja", "judges", "label", "judgment_id"]


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def judges(raw):
    try:
        return ", ".join(json.loads(raw or "[]"))
    except ValueError:
        return raw or ""


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True, type=Path)
    ap.add_argument("--upvishay", required=True)
    ap.add_argument("--court", choices=["SC", "UKHC"])
    ap.add_argument("--zikr", action="store_true", help="sirf zikr wale faisle bhi (warna sirf mukhya)")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)

    sql = ("SELECT j.id, j.court, j.case_no, j.cnr, j.petitioner, j.respondent, j.title, j.decision_date, "
           "j.disposal, c.outcome, j.judges, l.strength FROM labels l JOIN judgments j ON j.id = l.judgment_id "
           "LEFT JOIN categories c ON c.judgment_id = j.id WHERE l.upvishay = ? AND l.mudda = ''")
    params = [args.upvishay]
    if not args.zikr:
        sql += " AND l.strength = 'mukhya'"
    if args.court:
        sql += " AND j.court = ?"
        params.append(args.court)
    cases = {}
    for jid, court, case_no, cnr, pet, res, title, date, disp, nat, jud, strength in con.execute(sql, params):
        key = (court, cnr or case_no or f"id-{jid}") if court == "UKHC" else (court, f"id-{jid}")
        cases.setdefault(key, dict(court=court, case_no=case_no or title or "", cnr=cnr or "",
                                   petitioner=pet or "", respondent=res or "", label=strength, judgment_id=jid))

    rows = []
    for (court, k), c in cases.items():
        if court == "UKHC" and c["cnr"]:
            orders = con.execute("SELECT j.id, j.decision_date, j.disposal, c.outcome, j.judges FROM judgments j "
                                 "LEFT JOIN categories c ON c.judgment_id = j.id WHERE j.cnr = ? "
                                 "ORDER BY j.decision_date", (c["cnr"],)).fetchall()
        else:
            orders = con.execute("SELECT j.id, j.decision_date, j.disposal, c.outcome, j.judges FROM judgments j "
                                 "LEFT JOIN categories c ON c.judgment_id = j.id WHERE j.id = ?",
                                 (c["judgment_id"],)).fetchall()
        dates = sorted({o[1] for o in orders if o[1]})
        last = orders[-1]
        rows.append(dict(c, pehla_order=dates[0] if dates else "", aakhri_order=dates[-1] if dates else "",
                         orders=len(dates) or len(orders), disposal=last[2] or "", nateeja=last[3] or "",
                         judges=judges(last[4]), judgment_id=last[0]))
    rows.sort(key=lambda r: (r["court"], r["aakhri_order"]), reverse=True)

    args.out.mkdir(parents=True, exist_ok=True)
    name = slug(args.upvishay) + (f"-{args.court.lower()}" if args.court else "")
    with open(args.out / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, COLS)
        w.writeheader()
        w.writerows(rows)

    def cell(s):
        return re.sub(r"\s+", " ", str(s)).replace("|", "/")[:80]

    disposed = [r for r in rows if r["disposal"]]
    lines = [f"# {args.upvishay}: database ke cases", "",
             f"Kul cases: {len(rows)} · disposal ke saath: {len(disposed)}. Nateeja machine ka hai (jaanch baaki); "
             "'Orders' = database mein us case ki alag tareekhon ke orders, hearing ki pakki ginti nahi.", "",
             "| Court | Case | Petitioner vs Respondent | Pehla order | Aakhri order | Orders | Disposal | Nateeja | Judge |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append("| " + " | ".join(cell(x) for x in (
            r["court"], r["case_no"], f"{r['petitioner'][:35]} vs {r['respondent'][:35]}", r["pehla_order"],
            r["aakhri_order"], r["orders"], r["disposal"], r["nateeja"], r["judges"][:60])) + " |")
    (args.out / f"{name}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(rows)} cases -> {args.out / name}.csv / .md ({len(disposed)} disposal ke saath)")


if __name__ == "__main__":
    main()
