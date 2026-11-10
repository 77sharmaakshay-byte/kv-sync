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

# Vakil (petitioner aur respondent), faisle ke text se: "Mr. X, learned counsel for the petitioner"; holding brief
# ho to jiska brief hai; bunch faisle mein us case number wale hisse se. Na mile to khaali.
T = r"(?:Mr|Mrs|Ms|Miss|Dr|Shri|Sri|Smt|Km)\.?"
NAME = r"((?:[A-Z][a-zA-Z]*\.?\s?){1,5}[A-Z][a-zA-Z]+)"
ROLE = r"(?:(?:the\s+)?learned\s+)?(?:Senior\s+|Sr\.?\s+|Addl\.?\s+|Additional\s+|Deputy\s+|Dy\.?\s+|Assistant\s+|Asstt?\.?\s+|Astt\.?\s+)?(?:Advocate|Counsel|counsel|advocate|C\.?S\.?C\.?|Standing\s+Counsel|Brief\s+Holder|A\.?G\.?|S\.?G\.?|Government\s+Advocate)"
SIDE = {"pet": r"(?:the\s+)?(?:writ\s+)?(?:petitioners?|appellants?|applicants?)",
        "res": r"(?:the\s+)?(?:respondents?|State|Union\s+of\s+India|Corporation|University|opposite\s+part(?:y|ies))"}
HOLD = re.compile(rf"holding\s+brief\s+of\s+{T}\s*{NAME}")
HEAD = re.compile(r"(?:Writ\s+Petition|W\.?P\.?|WPSS|WPSB|Special\s+Appeal|SPA)\s*(?:\((?:S/S|S/B|SS|SB)\)\s*)?No\.?\s*(\d+)\s*(?:\((?:S/S|S/B|SS|SB)\)\s*)?of\s*(\d{4})", re.I)


def _pats(side):
    s = SIDE[side]
    return [re.compile(rf"{T}\s*{NAME}\s*,?\s*(?:{ROLE})(?:(?!\bfor\b)[^;]){{0,90}}?\bfor\s+{s}"),
            re.compile(rf"Counsel\s+for\s+{s}\s*:?\s*{T}\s*{NAME}")]


PATS = {k: _pats(k) for k in SIDE}


def clean(n):
    n = re.sub(r"\s+", " ", n).strip(" .,")
    n = re.sub(r"\s*,?\s*(learned|Senior|Sr|Advocate|Counsel|Addl|Additional|Standing|Brief)\b.*$", "", n, flags=re.I)
    n = re.sub(r"\.\s*", ".", n)
    n = re.sub(r"\.(?=[A-Za-z]{2,})", ". ", n)
    return n.upper()


def advocate(seg, side):
    for p in PATS[side]:
        m = p.search(seg)
        if m:
            h = HOLD.search(seg[m.start():m.end()])
            return clean(h.group(1) if h else m.group(1))
    return ""


def advocates(text, case_no=""):
    """(petitioner ka vakil, respondent ka vakil). Bunch faisle mein usi case number wale hisse se."""
    t = re.sub(r"\s+", " ", text[:60000])
    seg = t[:4000]
    m = re.search(r"/(\d+)/(\d{4})", case_no or "")
    heads = list(HEAD.finditer(t[:40000]))
    if m and len({(h.group(1), h.group(2)) for h in heads}) > 1:
        for i, h in enumerate(heads):
            if (h.group(1), h.group(2)) == (m.group(1), m.group(2)):
                end = heads[i + 1].start() if i + 1 < len(heads) else h.start() + 1500
                seg = t[h.start():min(end, h.start() + 1500)]
                break
    return advocate(seg, "pet"), advocate(seg, "res")


def subject_check(text, words):
    """Vishay ke shabd kitni baar, aur kya faisla asal mein kisi aur vishay (regularisation) ka lagta hai."""
    t = text[:80000]
    n = len(re.findall(words, t, re.I))
    reg = len(re.findall(r"regulari[sz]", t, re.I))
    return n, reg


COLS = ["court", "case_no", "cnr", "petitioner", "respondent", "pehla_order", "aakhri_order", "orders",
        "disposal", "nateeja", "vakil", "vakil_res", "shabd", "regularisation", "vishay_shak", "judges", "label", "judgment_id"]
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
    ap.add_argument("--shabd", help="vishay ke shabd (regex); faisle mein na hon / doosra vishay haavi ho to 'vishay_shak'")
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
        text = con.execute("SELECT substr(clean, 1, 80000) FROM texts WHERE judgment_id = ?", (last[0],)).fetchone()
        text = text[0] if text else ""
        vakil, vakil_res = advocates(text, c["case_no"])
        shabd, reg = subject_check(text, args.shabd) if args.shabd else (0, 0)
        # faisla asal mein kisi aur vishay ka (jaise daily wagers ka regularisation bunch, CA sirf saath ki maang)
        shak = bool(args.shabd) and (shabd == 0 or (reg >= 10 and reg > 5 * shabd))
        rows.append(dict(c, pehla_order=dates[0] if dates else "", aakhri_order=dates[-1] if dates else "",
                         orders=len(dates) or len(orders), disposal=last[2] or "", nateeja=last[3] or "",
                         judges=judges(last[4]), judgment_id=last[0], vakil=vakil, vakil_res=vakil_res, shabd=shabd,
                         regularisation=reg, vishay_shak="haan" if shak else ""))
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
    """Har vakil: petitioner ki taraf jeet / vichaar / khilaf, respondent ki taraf kitne aur unmein petitioner haara
    (= vakil jeeta). Vishay par shak wale faisle alag. Khilaf wale case har vakil ke neeche."""
    import collections
    stat = collections.defaultdict(collections.Counter)
    khilaf = collections.defaultdict(list)
    shak = []
    for r in rows:
        if not r["disposal"] and not r["nateeja"]:
            continue   # pending
        if r["vishay_shak"]:
            shak.append(r)
            continue
        k = kismat(r)
        v = r["vakil"] or "(naam nahi mila)"
        stat[v][k] += 1
        stat[v]["kul"] += 1
        if k == "khilaf":
            khilaf[v].append(r)
        if r["vakil_res"]:
            w = stat[r["vakil_res"]]
            w["res_kul"] += 1
            w["res_jeet"] += k == "khilaf"
            w["res_haar"] += k == "jeet"
    order = sorted(stat, key=lambda v: (-stat[v]["jeet"], -stat[v]["kul"], -stat[v]["res_kul"], v))
    name = slug(args.upvishay) + (f"-{args.court.lower()}" if args.court else "")
    L = [f"# {args.upvishay}: vakil", "",
         "Petitioner ki taraf: Jeet = ALLOWED / PARTLY ALLOWED, ya DISPOSED mein machine ka 'Paksh mein'; Vichaar = vibhag "
         "ko dobara vichaar ka nirdesh; Khilaf = DISMISSED, ya DISPOSED mein machine ka 'Khilaf'. Respondent ki taraf "
         "(State / vibhag ke vakil): petitioner khilaf = vakil jeeta, petitioner jeeta = vakil haara. Senior ke saath "
         "junior ho to senior ka naam; holding brief ho to jiska brief. Vakil ka naam aur nateeja machine ka — jaanch baaki.",
         f"Vishay par shak wale {len(shak)} faisle (shabd nahi, ya faisla asal mein regularisation ka) table se bahar, "
         "neeche alag.", "",
         "| Vakil | Petitioner ki taraf | Jeet | Vichaar | Khilaf | Baaki | Respondent ki taraf | Res. jeet | Res. haar |",
         "|---|---|---|---|---|---|---|---|---|"]
    for v in order:
        c = stat[v]
        L.append(f"| {v} | {c['kul']} | {c['jeet']} | {c['vichaar']} | {c['khilaf']} | {c['baaki']} | "
                 f"{c['res_kul']} | {c['res_jeet']} | {c['res_haar']} |")
    L += ["", "## Khilaf wale faisle (petitioner ki taraf), vakil ke hisaab se", ""]
    for v in sorted(khilaf, key=lambda v: (-len(khilaf[v]), v)):
        L.append(f"### {v} ({len(khilaf[v])})")
        L += [f"- {r['case_no']} · {r['petitioner'][:40]} vs {r['respondent'][:40]} · {r['aakhri_order']} · "
              f"{r['disposal'] or '-'} / {r['nateeja'] or '-'}" for r in khilaf[v]]
        L.append("")
    L += ["## Vishay par shak (table mein nahi)", ""]
    L += [f"- {r['case_no']} · {r['vakil'] or '-'} · shabd {r['shabd']}, regularisation {r['regularisation']} · "
          f"{r['disposal'] or '-'} / {r['nateeja'] or '-'}" for r in shak]
    (args.out / f"{name}-vakil.md").write_text("\n".join(L) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
