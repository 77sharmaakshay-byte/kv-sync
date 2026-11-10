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

# Petitioner ka vakil, faisle ke shuru ke text se ("Mr. X, learned counsel for the petitioner"; holding brief
# ho to jiska brief hai). Na mile to khaali.
T = r"(?:Mr|Mrs|Ms|Miss|Dr|Shri|Sri|Smt|Km)\.?"
NAME = r"((?:[A-Z][a-zA-Z]*\.?\s?){1,5}[A-Z][a-zA-Z]+)"
PET = r"(?:the\s+)?(?:writ\s+)?(?:petitioners?|appellants?|applicants?)"
ROLE = r"(?:(?:the\s+)?learned\s+)?(?:Senior\s+|Sr\.?\s+)?(?:Advocate|Counsel|counsel|advocate)"
PATS = [
  re.compile(rf"{T}\s*{NAME}\s*,?\s*(?:{ROLE})(?:(?!\bfor\b)[^;]){{0,90}}?\bfor\s+{PET}", re.S),
  re.compile(rf"Counsel\s+for\s+(?:the\s+)?{PET}\s*:?\s*{T}\s*{NAME}", re.S),
]
HOLD = re.compile(rf"holding\s+brief\s+of\s+{T}\s*{NAME}", re.S)
def clean(n):
    n = re.sub(r"\s+", " ", n).strip(" .,")
    n = re.sub(r"\s*,?\s*(learned|Senior|Sr|Advocate|Counsel)\b.*$", "", n, flags=re.I)
    n = re.sub(r"\.\s*", ".", n); n = re.sub(r"\.(?=[A-Za-z]{2,})", ". ", n)
    return n.upper()
def pet_advocate(text):
    t = re.sub(r"\s+", " ", text[:4000])
    for p in PATS:
        m = p.search(t)
        if m:
            seg = t[m.start():m.end()]
            h = HOLD.search(seg)
            return clean(h.group(1) if h else m.group(1))
    return ""

COLS = ["court", "case_no", "cnr", "petitioner", "respondent", "pehla_order", "aakhri_order", "orders",
        "disposal", "nateeja", "vakil", "judges", "label", "judgment_id"]
JEET = {"ALLOWED", "PARTLY ALLOWED", "SUCCEED"}
JEET_N = {"Paksh mein", "Aanshik paksh mein"}
VICHAAR_N = {"Nirdesh: vibhag vichaar kare"}


def kismat(r):
    """jeet / vichaar / khilaf / baaki: court ka disposal pehle, phir machine ka nateeja."""
    d = r["disposal"].upper()
    if d in JEET or (d in ("DISPOSED", "") and r["nateeja"] in JEET_N):
        return "jeet"
    if d == "DISMISSED" or (d in ("DISPOSED", "") and r["nateeja"] == "Khilaf"):
        return "khilaf"
    if r["nateeja"] in VICHAAR_N:
        return "vichaar"
    return "baaki"


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
        text = con.execute("SELECT substr(clean, 1, 4000) FROM texts WHERE judgment_id = ?", (last[0],)).fetchone()
        vakil = pet_advocate(text[0] if text else "")
        rows.append(dict(c, pehla_order=dates[0] if dates else "", aakhri_order=dates[-1] if dates else "",
                         orders=len(dates) or len(orders), disposal=last[2] or "", nateeja=last[3] or "",
                         judges=judges(last[4]), judgment_id=last[0], vakil=vakil))
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
    vakeel(rows, args)
    print(f"{len(rows)} cases -> {args.out / name}.csv / .md ({len(disposed)} disposal ke saath)")


def vakeel(rows, args):
    """Petitioner ke vakil: kitne jeete / vichaar / khilaf; aur khilaf wale case har vakil ke neeche."""
    import collections
    stat = collections.defaultdict(collections.Counter)
    khilaf = collections.defaultdict(list)
    for r in rows:
        if not r["disposal"] and not r["nateeja"]:
            continue   # pending
        k = kismat(r)
        v = r["vakil"] or "(naam nahi mila)"
        stat[v][k] += 1
        stat[v]["kul"] += 1
        if k == "khilaf":
            khilaf[v].append(r)
    order = sorted(stat, key=lambda v: (-stat[v]["jeet"], -stat[v]["kul"], v))
    name = slug(args.upvishay) + (f"-{args.court.lower()}" if args.court else "")
    L = [f"# {args.upvishay}: petitioner ke vakil", "",
         "Jeet = court ka ALLOWED / PARTLY ALLOWED, ya DISPOSED mein machine ka 'Paksh mein'. Vichaar = vibhag ko dobara "
         "vichaar ka nirdesh. Khilaf = DISMISSED, ya DISPOSED mein machine ka 'Khilaf'. Vakil ka naam faisle ke text se "
         "machine ne nikala; nateeja machine ka — jaanch baaki.", "",
         "| Vakil (petitioner) | Kul faisle | Jeet | Vichaar | Khilaf | Baaki |", "|---|---|---|---|---|---|"]
    for v in order:
        c = stat[v]
        L.append(f"| {v} | {c['kul']} | {c['jeet']} | {c['vichaar']} | {c['khilaf']} | {c['baaki']} |")
    L += ["", "## Khilaf wale faisle, vakil ke hisaab se", ""]
    for v in sorted(khilaf, key=lambda v: (-len(khilaf[v]), v)):
        L.append(f"### {v} ({len(khilaf[v])})")
        L += [f"- {r['case_no']} · {r['petitioner'][:40]} vs {r['respondent'][:40]} · {r['aakhri_order']} · "
              f"{r['disposal'] or '-'} / {r['nateeja'] or '-'}" for r in khilaf[v]]
        L.append("")
    (args.out / f"{name}-vakil.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
