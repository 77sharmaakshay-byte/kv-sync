#!/usr/bin/env python3
"""App (PWA) ke liye data: 'data' branch ki cause list + case lookups -> chhoti JSON files.

    python3 scripts/build_app_data.py --data-branch <data branch checkout> --out <site>/data

- causelist/<DD-MM-YYYY>/*.txt  ->  data/causelist/<YYYY-MM-DD>.json  (court-wise, item-wise)
- cases/<TYPE-NO-YEAR>/         ->  data/cases/<TYPE-NO-YEAR>.json    (case page + orders ka text)
- app/notes/<TYPE-NO-YEAR>.json ->  case ke saath (advocate ke liye taiyaar vishleshan)
- data/index.json: kaunsi tareekhein aur cases hain

Cause list PDF ka text column-wise toota hota hai; party aur vakeel ki pehchan andaaze se
hoti hai, isliye har entry ke saath poora 'raw' text bhi rakhte hain (search usi par).
"""
import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEEP_DAYS = 45

FOOTER = re.compile(r"\s*\d+/\d+\s+COURT NUMBER \d+\s*")
SECTION = re.compile(r"^\*\s*(.+?)\s*\*$")
ENTRY = re.compile(r"^(\d{1,4}(?:\(\d+\))?)\s+(\S.*)$")
CASE_NO = re.compile(r"\b(?!IA/|CLMA/)([A-Z][A-Z0-9.]{1,12}/\d{1,6}/\d{4})\b")
APP = re.compile(r"^(IA|CLMA|CRMA|MCC|DLR)/\d+/\d{4}\b")
JOIN_NEXT = ("AND", "&", "OF", "THROUGH", "THRU.", "BY")


def _lines(text):
    text = FOOTER.sub("\n", text.replace("\f", "\n"))
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _header(lines):
    court, time, judges = None, None, []
    for i, ln in enumerate(lines[:20]):
        m = re.match(r"COURT NUMBER (\d+)", ln)
        if m:
            court = int(m.group(1))
        m = re.search(r"AT (\d{1,2}:\d{2}) ?([AP])\.?M", ln)
        if m:
            time = f"{m.group(1)} {m.group(2)}M"
            for nxt in lines[i + 1:i + 6]:
                if nxt.startswith("(") or nxt.lower().startswith("sno") or len(nxt) > 60:
                    break
                if nxt != "AND":
                    judges.append(nxt.title().replace("Hon'Ble", "Hon'ble"))
    return court, time, judges


def _entry(item, block, section):
    m = CASE_NO.search(" ".join(block))
    case_no = m.group(1) if m else None
    apps = []
    # Application wale item ("64(1) IA/1/2024 FOR ... IN" + "WPSS/2332/2023 NAAM") mein case number aage hota hai.
    at = next((k for k, ln in enumerate(block) if case_no and case_no in ln), 0)
    for ln in block[:at]:
        rest = re.sub(r"^\d{1,4}(?:\(\d+\))?\s+", "", ln)
        if rest not in ("IN", "WITH"):
            apps.append(rest)
    head = block[at]
    if case_no and case_no in head:
        head = head.split(case_no, 1)[1].strip()
    elif at == 0:
        head = re.sub(r"^\d{1,4}(?:\(\d+\))?\s+", "", head)
    pet, res, adv, connected = [head] if head else [], [], [], False
    state, i = "pet", at + 1
    while i < len(block):
        ln = block[i]
        if ln == "Versus":
            state = "res"
        elif ln in ("WITH", "CONNECTED WITH", "IN") or ln.endswith("CONNECTED WITH"):
            connected = connected or "CONNECTED" in ln
            state = "apps"
        elif APP.match(ln):
            apps.append(ln)
            state = "apps"
        elif state == "pet":
            pet.append(ln)
        elif state == "res":
            res.append(ln)
            # Respondent ka naam aksar 1-2 line: "STATE OF UTTARAKHAND AND" + "OTHERS"
            nxt = block[i + 1] if i + 1 < len(block) else ""
            if not (ln.endswith(JOIN_NEXT) or nxt in ("OTHERS", "ANOTHER", "ORS", "ORS.")):
                state = "adv"
        elif state == "adv":
            adv.append(ln)
        i += 1
    return {"item": item, "case_no": case_no, "section": section,
            "pet": " ".join(pet).strip() or None, "res": " ".join(res).strip() or None,
            "adv": " ".join(adv) or None, "apps": apps, "raw": " ".join(block)}


def parse_causelist(text, bench=None):
    lines = _lines(text)
    court, time, judges = _header(lines)
    start = next((i for i, ln in enumerate(lines) if ln.startswith("SNo.")), 0)
    entries, section, cur = [], None, None
    for ln in lines[start + 1:]:
        sm = SECTION.match(ln)
        if sm:
            section = sm.group(1).title()
            continue
        em = ENTRY.match(ln)
        if em and (CASE_NO.search(em.group(2)) or APP.match(em.group(2))):
            if cur:
                entries.append(_entry(cur[0], cur[1], cur[2]))
            cur = (em.group(1), [ln], section)
        elif cur:
            cur[1].append(ln)
    if cur:
        entries.append(_entry(cur[0], cur[1], cur[2]))
    return {"court_no": court, "bench": bench, "judges": judges, "time": time, "entries": entries}


def build_causelists(src, out):
    days = []
    for folder in sorted(p for p in (src / "causelist").glob("*") if p.is_dir()):
        try:
            day = dt.datetime.strptime(folder.name, "%d-%m-%Y").date()
        except ValueError:
            continue
        index = json.loads((folder / "index.json").read_text(encoding="utf-8")) if (folder / "index.json").exists() else {}
        benches = {Path(b["file"]).stem: b.get("bench") for b in index.get("benches", [])}
        courts, seen = [], set()
        for txt in sorted(folder.glob("*.txt")):
            text = txt.read_text(encoding="utf-8")
            digest = hashlib.sha256(text.encode()).hexdigest()
            if digest in seen:  # civil/criminal mein wahi list dobara
                continue
            seen.add(digest)
            c = parse_causelist(text, benches.get(txt.stem))
            if c["entries"]:
                courts.append(c)
        courts.sort(key=lambda c: (c["court_no"] is None, c["court_no"] or 0))
        days.append(day)
        (out / "causelist").mkdir(parents=True, exist_ok=True)
        (out / "causelist" / f"{day.isoformat()}.json").write_text(
            json.dumps({"date": day.isoformat(), "courts": courts}, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8")
    keep = sorted(days)[-KEEP_DAYS:]
    for f in (out / "causelist").glob("*.json") if (out / "causelist").exists() else []:
        if f.stem not in {d.isoformat() for d in keep}:
            f.unlink()
    return [d.isoformat() for d in sorted(keep, reverse=True)]


def build_cases(src, out):
    ids = []
    notes_dir = ROOT / "app" / "notes"
    for folder in sorted(p for p in (src / "cases").glob("*") if p.is_dir()):
        case_json = folder / "_case.json"
        if not case_json.exists():
            continue
        c = json.loads(case_json.read_text(encoding="utf-8"))
        if not c.get("registration_number"):  # lookup mein case nahi mila; app cause list se dikhayegi
            continue
        # hcservices kabhi agli tareekh ko 'decision date' + "Case disposed" dikha deta hai; aage ki tareekh faisla nahi
        if (c.get("decision_date") or "") > dt.date.today().isoformat():
            c["next_hearing_date"] = c.get("next_hearing_date") or c["decision_date"]
            c["decision_date"], c["status"] = None, None
        orders = []
        for side in sorted(folder.glob("*.json")):
            if side.name.startswith("_"):
                continue
            meta = json.loads(side.read_text(encoding="utf-8"))
            txt = side.with_suffix(".txt")
            orders.append({"date": meta.get("decision_date"), "judge": (meta.get("judges") or [None])[0],
                           "kind": meta.get("doc_kind"),
                           "text": txt.read_text(encoding="utf-8") if txt.exists() else ""})
        orders.sort(key=lambda o: o["date"] or "")
        doc = {"id": folder.name, "cnr": c.get("cnr_number"), "case_no": (c.get("registration_number") or "").replace(" ", ""),
               "filing": {"no": (c.get("filing_number") or "").replace(" ", ""), "date": c.get("filing_date")},
               "registered": c.get("registration_date"), "next_date": c.get("next_hearing_date"),
               "decision_date": c.get("decision_date"), "stage": c.get("case_stage"), "status": c.get("status"),
               "coram": c.get("coram"), "bench_type": c.get("bench_type"),
               "petitioners": c.get("petitioners") or [], "respondents": c.get("respondents") or [],
               "acts": c.get("acts") or [], "history": c.get("history") or [], "orders": orders}
        note = notes_dir / f"{folder.name}.json"
        if note.exists():
            doc["notes"] = json.loads(note.read_text(encoding="utf-8"))
        (out / "cases").mkdir(parents=True, exist_ok=True)
        (out / "cases" / f"{folder.name}.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")),
                                                         encoding="utf-8")
        ids.append({"id": folder.name, "case_no": doc["case_no"],
                    "title": " v. ".join(x for x in [(doc["petitioners"] or [{}])[0].get("name"),
                                                     (doc["respondents"] or [{}])[0].get("name")] if x),
                    "advocates": sorted({p.get("advocate") for p in doc["petitioners"] + doc["respondents"]
                                         if p.get("advocate")}),
                    "next_date": doc["next_date"]})
    return ids


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data-branch", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    dates = build_causelists(args.data_branch, out)
    cases = build_cases(args.data_branch, out)
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
    (out / "index.json").write_text(json.dumps({"generated_at": now, "dates": dates, "cases": cases},
                                               ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(dates)} din ki cause list, {len(cases)} cases -> {out}")


if __name__ == "__main__":
    main()
