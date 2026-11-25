#!/usr/bin/env python3
"""Saare vakil A-Z (Nainital HC database ke saare faisle): kisne kitne case lade, kis taraf, kis vishay, kitne jeete.

    python3 scripts/export_vakil_sab.py --db krishivlaw.db --out out/vakil-sab/

Har faisle ke shuru ke text se petitioner aur respondent ka vakil (export_vishay.advocates; har taraf ka pehla
naam). Ek case (CNR) ke kai orders hon to aakhri order ka nateeja. Jeet/haar vakil ki taraf se:
petitioner ka vakil -> case allow = jeet, dismiss = haar; respondent ka vakil -> ulta.
Bane:
  index.csv / index.md  -> har vakil ek line, A-Z (kul, taraf, jeet, haar, vichaar, baaki, mukhya vishay, saal)
  vishay.csv            -> vakil x shreni x upvishay x taraf ke hisaab se ginti ("service ke case kisne lade")
  cases.csv             -> har vakil ka har case (khoj / app ke liye)
Sirf court ke apne record (faisle) se. Nateeja aur vishay machine ke — jaanch baaki. Ek jaise naam wale do vakil
(jaise do 'Vinay Kumar') yahan ek ho jaate hain; database mein na pahunche case (zyadatar pending) yahan nahi.
Yeh vakil ke apne kaam ke liye hai — public ranking / prachaar ke liye nahi (Bar Council Rule 36).
"""
import argparse
import collections
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_vishay import advocates, kismat  # noqa: E402

SKIP = re.compile(r"^(?:THE |LEARNED )?(?:ADVOCATE|COUNSEL|STATE|UNION|PETITIONER|RESPONDENT|APPELLANT|NONE|NO ONE)\b")


def norm(n):
    """'Mr. B.S. Mehra' / 'B. S. MEHRA' -> 'B S MEHRA' (sirf akshar, ek space)."""
    n = re.sub(r"[^A-Z ]", " ", (n or "").upper())
    n = re.sub(r"\b(?:MR|MRS|MS|MISS|DR|SHRI|SRI|SMT|KM|SR|SENIOR|ADVOCATE|COUNSEL|LEARNED)\b", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return "" if len(n) < 4 or " " not in n or SKIP.match(n) else n


def side_kismat(taraf, k):
    if taraf == "petitioner":
        return {"khilaf": "haar"}.get(k, k)
    return {"jeet": "haar", "khilaf": "jeet"}.get(k, k)


def main():
    import sqlite3
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True, type=Path)
    ap.add_argument("--court", default="UKHC", choices=["SC", "UKHC"])
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--min-cases", type=int, default=1, help="index.md mein kam se kam itne case wale vakil")
    args = ap.parse_args()
    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)

    lab = {}
    for jid, cat, vis, up in con.execute(
            "SELECT l.judgment_id, l.category, l.vishay, l.upvishay FROM labels l JOIN judgments j ON j.id = l.judgment_id "
            "WHERE j.court = ? AND l.mudda = '' AND l.strength = 'mukhya' ORDER BY l.hits", (args.court,)):
        lab[jid] = (cat, vis, up)   # sabse zyada hits wala aakhir mein -> wahi bachta hai
    print(f"vishay: {len(lab)} faisle", flush=True)

    cases = {}   # case key -> aakhri order ki row
    n = 0
    for jid, case_no, cnr, pet, res, date, disp, nat, text in con.execute(
            "SELECT j.id, j.case_no, j.cnr, j.petitioner, j.respondent, j.decision_date, j.disposal, c.outcome, "
            "substr(t.clean, 1, 40000) FROM judgments j LEFT JOIN categories c ON c.judgment_id = j.id "
            "LEFT JOIN texts t ON t.judgment_id = j.id WHERE j.court = ?", (args.court,)):
        n += 1
        if n % 20000 == 0:
            print(f"  {n} faisle padhe", flush=True)
        pv, rv = advocates(text or "", case_no or "")
        pv, rv = norm(pv), norm(rv)
        if not pv and not rv:
            continue
        key = cnr or case_no or f"id-{jid}"
        prev = cases.get(key)
        if prev and (date or "") < prev["aakhri_order"]:
            prev["pv"] = prev["pv"] or pv
            prev["rv"] = prev["rv"] or rv
            continue
        sh, vis, up = lab.get(jid, ("", "", ""))
        cases[key] = dict(case_no=case_no or "", cnr=cnr or "", petitioner=(pet or "")[:80], respondent=(res or "")[:80],
                          aakhri_order=date or "", disposal=disp or "", nateeja=nat or "", shreni=sh, vishay=vis,
                          upvishay=up, pv=pv or (prev or {}).get("pv", ""), rv=rv or (prev or {}).get("rv", ""))
    print(f"{n} faisle, {len(cases)} case jinmein vakil ka naam mila", flush=True)

    rows = []
    for c in cases.values():
        k = kismat(c) if (c["disposal"] or c["nateeja"]) else "baaki"
        for taraf, v, other in (("petitioner", c["pv"], c["rv"]), ("respondent", c["rv"], c["pv"])):
            if v:
                rows.append(dict(vakil=v, taraf=taraf, saamne_vakil=other, vakil_ki_kismat=side_kismat(taraf, k),
                                 **{x: c[x] for x in ("case_no", "cnr", "petitioner", "respondent", "aakhri_order",
                                                      "shreni", "vishay", "upvishay", "disposal", "nateeja")}))
    rows.sort(key=lambda r: (r["vakil"], r["aakhri_order"]))

    args.out.mkdir(parents=True, exist_ok=True)
    cols = ["vakil", "taraf", "case_no", "cnr", "petitioner", "respondent", "aakhri_order", "shreni", "vishay",
            "upvishay", "disposal", "nateeja", "vakil_ki_kismat", "saamne_vakil"]
    with open(args.out / "cases.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, cols)
        w.writeheader()
        w.writerows(rows)

    by_v = collections.defaultdict(list)
    for r in rows:
        by_v[r["vakil"]].append(r)
    vis = collections.defaultdict(collections.Counter)
    for r in rows:
        k = (r["vakil"], r["shreni"] or "(pata nahi)", r["upvishay"] or "(pata nahi)", r["taraf"])
        vis[k]["kul"] += 1
        vis[k][r["vakil_ki_kismat"]] += 1
    with open(args.out / "vishay.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["vakil", "shreni", "upvishay", "taraf", "kul", "jeet", "haar", "vichaar", "baaki"])
        for k in sorted(vis):
            c = vis[k]
            w.writerow([*k, c["kul"], c["jeet"], c["haar"], c["vichaar"], c["baaki"]])

    icols = ["vakil", "kul", "petitioner_ki_taraf", "respondent_ki_taraf", "jeet", "haar", "vichaar", "baaki",
             "jeet_pratishat", "mukhya_shreni", "mukhya_upvishay", "pehla", "aakhri"]
    index = []
    for v in sorted(by_v):
        rs = by_v[v]
        kc = collections.Counter(r["vakil_ki_kismat"] for r in rs)
        tc = collections.Counter(r["taraf"] for r in rs)
        tay = kc["jeet"] + kc["haar"]
        dates = [r["aakhri_order"] for r in rs if r["aakhri_order"]]
        sh = collections.Counter(r["shreni"] for r in rs if r["shreni"]).most_common(1)
        up = collections.Counter(r["upvishay"] for r in rs if r["upvishay"]).most_common(1)
        index.append(dict(vakil=v, kul=len(rs), petitioner_ki_taraf=tc["petitioner"], respondent_ki_taraf=tc["respondent"],
                          jeet=kc["jeet"], haar=kc["haar"], vichaar=kc["vichaar"], baaki=kc["baaki"],
                          jeet_pratishat=round(100 * kc["jeet"] / tay) if tay >= 5 else "",
                          mukhya_shreni=sh[0][0] if sh else "", mukhya_upvishay=up[0][0] if up else "",
                          pehla=min(dates)[:4] if dates else "", aakhri=max(dates)[:4] if dates else ""))
    with open(args.out / "index.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, icols)
        w.writeheader()
        w.writerows(index)

    L = [f"# Vakil A-Z: {args.court} database ke faisle", "",
         f"{len(index)} vakil · {len(cases)} case. Jeet/haar vakil ki taraf se (faisle ke disposal / machine ka nateeja); "
         "jeet % sirf jahan 5+ tay case. Machine ka kaam — jaanch baaki. Ek naam ke do vakil ek ho sakte hain. "
         "Sirf vakil ke apne kaam ke liye, public ranking nahi.", ""]
    letter = ""
    for r in index:
        if r["kul"] < args.min_cases:
            continue
        if r["vakil"][0] != letter:
            letter = r["vakil"][0]
            L += ["", f"## {letter}", "", "| Vakil | Kul | Pet/Res | Jeet | Haar | Vichaar | Baaki | Jeet % | Mukhya vishay | Saal |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        L.append(f"| {r['vakil']} | {r['kul']} | {r['petitioner_ki_taraf']}/{r['respondent_ki_taraf']} | {r['jeet']} | "
                 f"{r['haar']} | {r['vichaar']} | {r['baaki']} | {r['jeet_pratishat']} | "
                 f"{r['mukhya_upvishay'] or r['mukhya_shreni']} | {r['pehla']}-{r['aakhri']} |")
    (args.out / "index.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"{len(index)} vakil, {len(rows)} vakil-case -> {args.out}/index.csv, vishay.csv, cases.csv, index.md")


if __name__ == "__main__":
    main()
