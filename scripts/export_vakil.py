#!/usr/bin/env python3
"""Ek vakil ke database mein saare faisle (Nainital HC): kis taraf, kis vishay ke, kya nateeja — CSV + Markdown.

    python3 scripts/export_vakil.py --db krishivlaw.db --name "Bhagwat Mehra" --out out/

Khoj: faislon ke paragraphs (full-text) mein naam ke saare shabd paas-paas. Phir har faisle ke text se taraf:
petitioner ka vakil / respondent ka vakil / sirf naam aaya (doosra vakil, holding brief, ya kisi aur roop mein).
Ek case (CNR) ke kai orders hon to aakhri order ka nateeja. Vishay = machine ki chhantai (labels, 'mukhya').
Database mein zyadatar case ka sirf final order hai; jo case database mein nahi, woh yahan nahi.
Nateeja machine ka hai — jaanch baaki.
"""
import argparse
import collections
import csv
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_vishay import advocates, judges, kismat, slug  # noqa: E402

COLS = ["case_no", "cnr", "petitioner", "respondent", "aakhri_order", "orders", "taraf", "saath_vakil",
        "disposal", "nateeja", "kismat", "vakil_ki_kismat", "shreni", "vishay", "upvishay", "judges", "judgment_id"]


def same(a, words):
    a = re.sub(r"[^A-Z ]", " ", (a or "").upper())
    return all(re.search(rf"\b{w}\b", a) for w in words)


SIDE_AFTER = re.compile(r"^[^;]{0,140}?\bfor\s+(?:the\s+)?(?:writ\s+)?(petitioner|appellant|applicant|revisionist|"
                        r"respondent|opposite\s+part|State|Union|caveator|complainant|accused)", re.I)
SIDE_BEFORE = re.compile(r"Counsel\s+for\s+(?:the\s+)?(petitioner|appellant|applicant|respondent)s?\s*:?[^:]{0,80}$", re.I)
PET_WORDS = ("petitioner", "appellant", "applicant", "revisionist", "accused")


def taraf_from_text(text, name_re):
    """Naam ke theek baad 'for the petitioner / respondent no.4 / State' (ya pehle 'Counsel for the X :')."""
    t = re.sub(r"\s+", " ", text[:60000])
    for m in name_re.finditer(t):
        a = SIDE_AFTER.search(t[m.end():m.end() + 160])
        b = SIDE_BEFORE.search(t[max(0, m.start() - 120):m.start()])
        w = (a.group(1) if a else b.group(1) if b else "").lower()
        if w:
            return "petitioner" if w.startswith(PET_WORDS) else "respondent"
    return ""


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True, type=Path)
    ap.add_argument("--name", required=True, help='jaise "Bhagwat Mehra" (beech ka naam ho ya na ho, dono milenge)')
    ap.add_argument("--court", default="UKHC", choices=["SC", "UKHC"])
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    words = [w.upper() for w in re.findall(r"[A-Za-z]+", args.name)]
    near = " ".join(f'"{w.lower()}"' for w in words)

    ids = {r[0] for r in con.execute(
        "SELECT DISTINCT p.judgment_id FROM paragraphs_fts f JOIN paragraphs p ON p.id = f.rowid "
        f"WHERE paragraphs_fts MATCH ?", (f"NEAR({near}, 3)",))}
    print(f"full-text se {len(ids)} faisle", flush=True)
    # faisle ka shuru (vakilon ke naam) paragraph mein na toota ho to: pehle 4000 akshar mein aakhri shabd
    ids |= {r[0] for r in con.execute(
        "SELECT t.judgment_id FROM texts t JOIN judgments j ON j.id = t.judgment_id WHERE j.court = ? "
        "AND instr(upper(substr(t.clean, 1, 4000)), ?) > 0", (args.court, words[-1]))}
    print(f"shuru ke text ke saath {len(ids)} (naam ki pakki jaanch neeche)", flush=True)
    name_re = re.compile(r"\b" + r"\W+(?:\w+\W+){0,2}".join(words) + r"\b", re.I)

    cases = {}
    for jid in sorted(ids):
        row = con.execute("SELECT j.court, j.case_no, j.cnr, j.petitioner, j.respondent, j.decision_date, j.disposal, "
                          "c.outcome, j.judges, substr(t.clean, 1, 80000) FROM judgments j "
                          "LEFT JOIN categories c ON c.judgment_id = j.id LEFT JOIN texts t ON t.judgment_id = j.id "
                          "WHERE j.id = ?", (jid,)).fetchone()
        if not row or row[0] != args.court:
            continue
        court, case_no, cnr, pet, res, date, disp, nat, jud, text = row
        text = text or ""
        if not name_re.search(text):
            continue
        pv, rv = advocates(text, case_no or "")
        taraf = ("petitioner" if same(pv, words) else "respondent" if same(rv, words)
                 else taraf_from_text(text, name_re) or "naam aaya")
        lab = con.execute("SELECT category, vishay, upvishay FROM labels WHERE judgment_id = ? AND mudda = '' "
                          "AND strength = 'mukhya' ORDER BY hits DESC LIMIT 1", (jid,)).fetchone() or ("", "", "")
        key = cnr or case_no or f"id-{jid}"
        r = dict(case_no=case_no or "", cnr=cnr or "", petitioner=pet or "", respondent=res or "",
                 aakhri_order=date or "", taraf=taraf, saath_vakil=rv if taraf == "petitioner" else pv,
                 disposal=disp or "", nateeja=nat or "", shreni=lab[0], vishay=lab[1], upvishay=lab[2],
                 judges=judges(jud), judgment_id=jid)
        prev = cases.get(key)
        n = (prev["orders"] if prev else 0) + 1
        if not prev or r["aakhri_order"] >= prev["aakhri_order"]:
            if prev and r["taraf"] == "naam aaya" and prev["taraf"] != "naam aaya":
                r["taraf"], r["saath_vakil"] = prev["taraf"], prev["saath_vakil"]
            cases[key] = r
        cases[key]["orders"] = n

    rows = sorted(cases.values(), key=lambda r: r["aakhri_order"], reverse=True)
    for r in rows:
        k = kismat(r) if (r["disposal"] or r["nateeja"]) else "pending"
        r["kismat"] = k
        # petitioner ka vakil: khilaf = haar; respondent ka vakil: petitioner jeeta = haar, khilaf = jeet
        side = {"petitioner": {"khilaf": "haar"}, "respondent": {"jeet": "haar", "khilaf": "jeet"}}.get(r["taraf"])
        r["vakil_ki_kismat"] = side.get(k, k) if side is not None else ""

    args.out.mkdir(parents=True, exist_ok=True)
    name = slug(args.name) + "-" + args.court.lower()
    with open(args.out / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, COLS)
        w.writeheader()
        w.writerows(rows)

    def cell(s):
        return re.sub(r"\s+", " ", str(s)).replace("|", "/")[:70]

    taraf = collections.Counter(r["taraf"] for r in rows)
    L = [f"# {args.name}: Nainital HC ke faisle (database)", "",
         f"Kul cases: {len(rows)} · petitioner ki taraf {taraf['petitioner']} · respondent ki taraf {taraf['respondent']} · "
         f"sirf naam aaya {taraf['naam aaya']}. Vishay aur nateeja machine ke — jaanch baaki. Database mein na pahunche "
         "case (zyadatar pending) yahan nahi.", "",
         "## Taraf ke hisaab se vakil ki kismat", "", "| Taraf | Kul | Jeet | Vichaar | Haar | Baaki |", "|---|---|---|---|---|---|"]
    for t in ("petitioner", "respondent"):
        c = collections.Counter(r["vakil_ki_kismat"] for r in rows if r["taraf"] == t)
        L.append(f"| {t} | {sum(c.values())} | {c['jeet']} | {c['vichaar']} | {c['haar']} | {c['baaki'] + c['pending']} |")
    L += ["", "## Vishay ke hisaab se (petitioner ki taraf)", "",
          "| Shreni | Upvishay | Kul | Jeet | Vichaar | Haar | Baaki |", "|---|---|---|---|---|---|---|"]
    by = collections.defaultdict(collections.Counter)
    for r in rows:
        if r["taraf"] == "petitioner":
            k = (r["shreni"] or "(pata nahi)", r["upvishay"] or "(pata nahi)")
            by[k][r["vakil_ki_kismat"]] += 1
            by[k]["kul"] += 1
    for (sh, up), c in sorted(by.items(), key=lambda x: -x[1]["kul"]):
        L.append(f"| {sh} | {up} | {c['kul']} | {c['jeet']} | {c['vichaar']} | {c['haar']} | {c['baaki'] + c['pending']} |")
    L += ["", "## Haare hue cases", "", "| Case | Parties | Tareekh | Taraf | Disposal / nateeja | Upvishay | Saamne vakil |",
          "|---|---|---|---|---|---|---|"]
    for r in rows:
        if r["vakil_ki_kismat"] == "haar":
            L.append("| " + " | ".join(cell(x) for x in (
                r["case_no"], f"{r['petitioner'][:30]} vs {r['respondent'][:30]}", r["aakhri_order"], r["taraf"],
                f"{r['disposal'] or '-'} / {r['nateeja'] or '-'}", r["upvishay"], r["saath_vakil"])) + " |")
    L += ["", "## Saare cases", "", "| Case | Parties | Tareekh | Taraf | Disposal / nateeja | Upvishay | Vakil ki kismat |",
          "|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append("| " + " | ".join(cell(x) for x in (
            r["case_no"], f"{r['petitioner'][:30]} vs {r['respondent'][:30]}", r["aakhri_order"], r["taraf"],
            f"{r['disposal'] or '-'} / {r['nateeja'] or '-'}", r["upvishay"], r["vakil_ki_kismat"] or "-")) + " |")
    (args.out / f"{name}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"{len(rows)} cases -> {args.out / name}.csv / .md ({dict(taraf)})")


if __name__ == "__main__":
    main()
