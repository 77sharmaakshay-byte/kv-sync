#!/usr/bin/env python3
"""Har case ka machine-vishleshan: vishay (kl/taxonomy.py ke niyam) + database se milte-julte faisle.

    python3 scripts/auto_notes.py --db krishivlaw.db --cases databranch/cases --out databranch/notes_auto

Sirf record se: case type, orders ka text, aur database ke faisle (unka asli paragraph). Paksh/khilaf ki
daleelein nahi likhta (woh advocate / haath ke notes ka kaam); har note par 'auto' aur 'jaanch baaki'.
Jis case ka haath ka note (app/notes) hai, ya jiska auto note pehle ban chuka, use chhod deta hai (--force se dobara).
"""
import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kl import classify, taxonomy  # noqa: E402

PER_COURT = 3   # har court (SC, Nainital HC) se kitne faisle
# Paragraph ke shuru/beech mein panne ka header: '[2026] 6 S.C.R. 425', 'Supreme Court Reports', CNR, neutral citation
NOISE = re.compile(r"\d*\s*\[\d{4}\]\s*\d+\s*S\.C\.R\.(\s*\d+)?(\s*:\s*\d{4} INSC \d+)?|Supreme Court Reports|"
                   r"UKHC\d{10,}|\d{4}:UHC:\d+(-DB)?|Approved For Reporting|HIGH COURT OF UTTARAKHAND AT NAINITAL", re.I)


def clean_quote(text):
    return re.sub(r"\s+", " ", NOISE.sub(" ", text)).strip(" ;:,")


def case_text(folder):
    parts = []
    c = json.loads((folder / "_case.json").read_text(encoding="utf-8"))
    for p in (c.get("petitioners") or []) + (c.get("respondents") or []):
        parts.append(p.get("name") or "")
    for a in c.get("acts") or []:
        parts.append(" ".join(str(v) for v in a.values() if v))
    for txt in sorted(folder.glob("*.txt")):
        parts.append(txt.read_text(encoding="utf-8"))
    return c, "\n\n".join(parts)


def topics_for(case_type, text):
    """Case ke apne text par wahi FTS niyam (chhoti in-memory table) -> [(upvishay, hits)], zyada pehle."""
    mem = sqlite3.connect(":memory:")
    mem.execute('CREATE VIRTUAL TABLE f USING fts5(text, tokenize="porter unicode61 remove_diacritics 2")')
    paras = [p for p in re.split(r"\n\s*\n|\f", text) if p.strip()] or [text]
    mem.executemany("INSERT INTO f VALUES (?)", [(p,) for p in paras])
    found = {}
    for cat, vishay, up, query, _ in taxonomy.TOPICS:
        if cat == "Service" and (case_type or "").upper().startswith(classify.CRIMINAL):
            continue
        n = mem.execute("SELECT count(*) FROM f WHERE f MATCH ?", (query,)).fetchone()[0]
        if n:
            found[up] = n
    for prefixes, up in taxonomy.CASE_TOPICS:
        if (case_type or "").upper().startswith(prefixes):
            found[up] = found.get(up, 0) + 100   # case type sabse pakka saboot
    issues = {}
    for up in found:
        for mudda, query in taxonomy.ISSUES.get(up, []):
            n = mem.execute("SELECT count(*) FROM f WHERE f MATCH ?", (query,)).fetchone()[0]
            if n:
                issues.setdefault(up, []).append(mudda)
    return sorted(found.items(), key=lambda x: -x[1]), issues


_SIM = {}


def similar(con, up, mudda, query, per_court=PER_COURT):
    """Usi upvishay (aur mudda ho to usi) ke mukhya faisle, sabse milta asli paragraph ke saath. SC pehle,
    phir Nainital HC; naye aur zyada pannon par is vishay wale pehle. Ek upvishay ka nateeja yaad rakhte hain."""
    key = (up, mudda, per_court)
    if key in _SIM:
        return _SIM[key]
    out = []
    for court in ("SC", "UKHC"):
        rows = con.execute(
            "SELECT k.judgment_id, k.title, k.case_no, k.neutral_citation, k.decision_date, k.nateeja, j.judges "
            "FROM khoj k JOIN judgments j ON j.id = k.judgment_id "
            "WHERE k.upvishay = ? AND k.mudda = ? AND k.strength = 'mukhya' AND k.court = ? "
            "ORDER BY (k.hits >= 3) DESC, k.decision_date DESC LIMIT ?", (up, mudda or "", court, max(30, per_court * 6))).fetchall()
        if not rows:
            continue
        meta = {r[0]: r for r in rows}
        best = {}
        for jid, para_no, text, score in con.execute(
                "SELECT p.judgment_id, p.para_no, p.text, bm25(paragraphs_fts) FROM paragraphs_fts "
                "JOIN paragraphs p ON p.id = paragraphs_fts.rowid WHERE paragraphs_fts MATCH ? AND p.section = 'body' "
                f"AND p.judgment_id IN ({','.join('?' * len(meta))}) ORDER BY 4", (query, *meta)):
            if jid not in best and len(text) > 120:
                best[jid] = (para_no, text)
        picked = 0
        for jid, title, case_no, cite, date, nateeja, judges in rows:
            if jid not in best:
                continue
            para_no, text = best[jid]
            text = clean_quote(text)
            if any(text[:200] in o["quote"] for o in out):  # judi hui petitions mein wahi paragraph
                continue
            out.append({
                "id": jid,
                "court": "Supreme Court" if court == "SC" else "Nainital HC",
                "tag": (nateeja or "Nateeja ?") + " · machine se chuna",
                "verified": False,
                "title": title or case_no or cite,
                "cite": " · ".join(x for x in [cite or case_no, ".".join(reversed((date or "").split("-"))),
                                                (judges or "").split(";")[0]] if x),
                "why": f"Isi vishay par: {up}" + (f" — {mudda}" if mudda else "") + ". Court ka nateeja: "
                       + (nateeja or "record mein nahi") + ".",
                "quote": "“" + (text[:420] + ("…" if len(text) > 420 else "")) + "”" + (f" (para {para_no})" if para_no else ""),
            })
            picked += 1
            if picked >= per_court:
                break
    _SIM[key] = out
    return out


def note_for(con, folder):
    c, text = case_text(folder)
    case_type = (c.get("registration_number") or folder.name).split("/")[0].split("-")[0]
    tops, issues = topics_for(case_type, text)
    if not tops:
        return None
    up = tops[0][0]
    cat, vishay, _, query, _ = next(t for t in taxonomy.TOPICS if t[2] == up)
    mudda = (issues.get(up) or [None])[0]
    sims = similar(con, up, mudda, query) if mudda else []
    if len(sims) < 2:
        sims = similar(con, up, None, query)
    counts = {m: con.execute("SELECT count(*) FROM labels WHERE upvishay = ? AND mudda = ?", (up, m)).fetchone()[0]
              for m, _ in taxonomy.ISSUES.get(up, [])}
    return {
        "auto": True,
        "badge": "Machine vishleshan",
        "vishay": {"shreni": cat, "vishay": vishay, "upvishay": up, "mudde": issues.get(up, []),
                   "aur": [t for t, _ in tops[1:4]]},
        "issues_title": f"{up}: is vishay ke aam mudde",
        "issues": [{"mudda": m, "faisle": n, "is_case_mein": m in issues.get(up, [])}
                   for m, n in sorted(counts.items(), key=lambda x: -x[1])],
        "similar": sims,
        "disclaimer": "Yeh vishleshan machine ne case ke record aur database ke niyamon se banaya hai; vishay aur "
                      "faisle advocate jaanch lein. Quote faisle ka asli paragraph hai.",
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True, type=Path)
    ap.add_argument("--cases", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    con = sqlite3.connect(args.db)
    args.out.mkdir(parents=True, exist_ok=True)
    made = skipped = none = 0
    for folder in sorted(p for p in args.cases.iterdir() if (p / "_case.json").exists()):
        dest = args.out / f"{folder.name}.json"
        if (ROOT / "app" / "notes" / f"{folder.name}.json").exists() or (dest.exists() and not args.force):
            skipped += 1
            continue
        note = note_for(con, folder)
        if not note:
            none += 1
            print(f"{folder.name}: vishay nahi mila")
            continue
        dest.write_text(json.dumps(note, ensure_ascii=False, indent=1), encoding="utf-8")
        made += 1
        print(f"{folder.name}: {note['vishay']['upvishay']} {note['vishay']['mudde']} · {len(note['similar'])} faisle")
    print(f"== bane {made}, pehle se/haath ke {skipped}, vishay nahi {none}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
