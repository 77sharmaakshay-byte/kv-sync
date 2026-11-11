#!/usr/bin/env python3
"""Ek upvishay ke faislon mein ek khaas mudda (regex) dhoondho: har faisle ka asli text-ansh, dono taraf ke vakil, nateeja.

    python3 scripts/export_mudda.py --db krishivlaw.db --upvishay "Compassionate appointment" \
        --mudda "retrospect|prospective" --naam retrospective --out out/

Har milne wale faisle ke liye: case, court, tareekh, judge, disposal, nateeja (machine ka), petitioner aur respondent
ke vakil (text se), mudde ke shabd kitni baar, aur jahan mile wahan ke asli ansh (quote — badle nahi jaate).
Aakhri hissa (operative order) bhi, taaki padh kar pata chale court ne kya kiya. Yeh padhne ke liye kachcha maal hai:
kaun jeeta / mudde par court ne kya kaha, faisla padh kar hi pakka.
"""
import argparse
import csv
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_vishay import advocates, judges, slug  # noqa: E402

COLS = ["court", "case_no", "cite", "title", "date", "judges", "disposal", "nateeja", "vakil_pet", "vakil_res",
        "hits", "judgment_id"]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True, type=Path)
    ap.add_argument("--upvishay", required=True)
    ap.add_argument("--mudda", required=True, help="regex")
    ap.add_argument("--naam", required=True, help="file ke naam ke liye chhota naam")
    ap.add_argument("--court", choices=["SC", "UKHC"])
    ap.add_argument("--zikr", action="store_true", help="zikr wale faisle bhi (warna sirf mukhya)")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    pat = re.compile(args.mudda, re.I)

    sql = ("SELECT DISTINCT j.id, j.court, j.case_no, j.neutral_citation, j.title, j.decision_date, j.judges, j.disposal, "
           "c.outcome FROM labels l JOIN judgments j ON j.id = l.judgment_id LEFT JOIN categories c ON c.judgment_id = j.id "
           "WHERE l.upvishay = ?")
    params = [args.upvishay]
    if not args.zikr:
        sql += " AND l.strength = 'mukhya'"
    if args.court:
        sql += " AND j.court = ?"
        params.append(args.court)
    rows, blocks = [], []
    for jid, court, case_no, cite, title, date, jud, disp, nat in con.execute(sql, params).fetchall():
        t = con.execute("SELECT clean FROM texts WHERE judgment_id = ?", (jid,)).fetchone()
        text = re.sub(r"\s+", " ", t[0]) if t else ""
        hits = list(pat.finditer(text))
        if not hits:
            continue
        pv, rv = advocates(text, case_no or "")
        r = dict(court=court, case_no=case_no or "", cite=cite or "", title=(title or "")[:150], date=date or "",
                 judges=judges(jud), disposal=disp or "", nateeja=nat or "", vakil_pet=pv, vakil_res=rv,
                 hits=len(hits), judgment_id=jid)
        rows.append(r)
        quotes, last = [], -10_000
        for m in hits:
            if m.start() - last < 700:
                continue
            quotes.append(text[max(0, m.start() - 450):m.end() + 450])
            last = m.start()
            if len(quotes) >= 3:
                break
        blocks.append((r, quotes, text[-1200:]))

    rows.sort(key=lambda r: (r["court"], r["date"]), reverse=True)
    blocks.sort(key=lambda b: (b[0]["court"], b[0]["date"]), reverse=True)
    args.out.mkdir(parents=True, exist_ok=True)
    name = f"{slug(args.upvishay)}-{slug(args.naam)}" + (f"-{args.court.lower()}" if args.court else "")
    with open(args.out / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, COLS)
        w.writeheader()
        w.writerows(rows)
    L = [f"# {args.upvishay} · mudda: {args.naam}", "", f"Regex: `{args.mudda}` · {len(rows)} faisle. Quote faisle ka asli "
         "text hai; nateeja aur vakil machine ke — padh kar pakka karein.", ""]
    for r, quotes, tail in blocks:
        L += [f"## {r['court']} · {r['case_no'] or r['cite']} · {r['date']}", "",
              f"{r['title']}  ", f"Judge: {r['judges'] or '-'} · Disposal: {r['disposal'] or '-'} · Nateeja (machine): "
              f"{r['nateeja'] or '-'}  ", f"Petitioner ke vakil: {r['vakil_pet'] or '-'} · Respondent ke vakil: "
              f"{r['vakil_res'] or '-'} · mudde ke shabd: {r['hits']}", ""]
        L += [f"> …{q}…" for q in quotes]
        L += ["", f"**Aakhri hissa:** …{tail}", ""]
    (args.out / f"{name}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (args.out / f"{name}.json").write_text(json.dumps([dict(r, quotes=q, tail=t) for r, q, t in blocks],
                                                      ensure_ascii=False), encoding="utf-8")
    print(f"{len(rows)} faisle -> {args.out / name}.md / .csv / .json")


if __name__ == "__main__":
    main()
