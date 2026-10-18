#!/usr/bin/env python3
"""Har case ka machine-vishleshan: vishay (kl/taxonomy.py ke niyam) + database se milte-julte faisle.

    python3 scripts/auto_notes.py --db krishivlaw.db --cases databranch/cases --out databranch/notes_auto

Sirf record se: case type, orders ka text, aur database ke faisle (unka asli paragraph). Paksh/khilaf ki
daleelein nahi likhta (woh advocate / haath ke notes ka kaam); har note par 'auto' aur 'jaanch baaki'.
Jis case ka haath ka note (app/notes) hai, ya jiska auto note pehle ban chuka, use chhod deta hai (--force se dobara).
"""
import argparse
import json
import math
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kl import classify, taxonomy  # noqa: E402

PER_COURT = 3   # har court (SC, Nainital HC) se kitne faisle (balance=True par: itne paksh + itne khilaf)
GOOD = ("Paksh mein", "Aanshik paksh mein", "Nirdesh: vibhag vichaar kare")


def side(nateeja):
    """Faisla petitioner ke paksh / khilaf / anya (app isi se 'support' aur 'against' alag dikhata hai)."""
    return "good" if nateeja in GOOD else "bad" if (nateeja or "").startswith("Khilaf") else "other"
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


def topics_for(case_type, text, acts=""):
    """Case ke apne text par wahi FTS niyam (chhoti in-memory table) -> [(upvishay, hits)], zyada pehle.
    acts: case ke record ke Act (ACT_TOPICS se bhi vishay)."""
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
    for pattern, up in taxonomy.ACT_TOPICS:
        if re.search(pattern, acts or "", re.I):
            found[up] = found.get(up, 0) + 50   # record ka Act: case type ke baad sabse pakka
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


def similar(con, up, mudda, query, per_court=PER_COURT, balance=False):
    """Usi upvishay (aur mudda ho to usi) ke mukhya faisle, sabse milta asli paragraph ke saath. SC pehle,
    phir Nainital HC; naye aur zyada pannon par is vishay wale pehle. Ek upvishay ka nateeja yaad rakhte hain.
    balance: har court se per_court paksh wale + per_court khilaf wale (anya sirf jagah bache to)."""
    key = (up, mudda, per_court, balance)
    if key in _SIM:
        return _SIM[key]
    out = []
    for court in ("SC", "UKHC"):
        rows = con.execute(
            "SELECT k.judgment_id, k.title, k.case_no, k.neutral_citation, k.decision_date, k.nateeja, j.judges "
            "FROM khoj k JOIN judgments j ON j.id = k.judgment_id "
            "WHERE k.upvishay = ? AND k.mudda = ? AND k.strength = 'mukhya' AND k.court = ? "
            "ORDER BY (k.hits >= 3) DESC, k.decision_date DESC LIMIT ?",
            (up, mudda or "", court, max(150 if balance else 30, per_court * 6))).fetchall()
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
        picked, got = 0, {"good": 0, "bad": 0, "other": 0}
        for jid, title, case_no, cite, date, nateeja, judges in rows:
            if jid not in best:
                continue
            if balance:
                g = side(nateeja)
                if got[g] >= per_court or (g == "other" and got["good"] + got["bad"] + got["other"] >= per_court):
                    continue
            para_no, text = best[jid]
            text = clean_quote(text)
            if any(text[:200] in o["quote"] for o in out):  # judi hui petitions mein wahi paragraph
                continue
            out.append({
                "id": jid, "side": side(nateeja), "mudda": mudda or up,
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
            if balance:
                got[side(nateeja)] += 1
                if got["good"] >= per_court and got["bad"] >= per_court:
                    break
            elif picked >= per_court:
                break
    _SIM[key] = out
    return out


# ---- Vishay na mile to: orders ke khaas shabdon se database ke milte-julte faisle (BM25) ----
# Orders ka kaam-kaaji hissa (tareekh, vakeel, counter affidavit...) shabd chunne se pehle hata do
PROCEDURE = re.compile(
    r"^.*\b(hon.?ble|learned counsel|advocate|counsel for|standing counsel|c\.s\.c|d\.a\.g|a\.g\.a|brief holder|"
    r"list (on|this|after|the)|put up|counter affidavit|rejoinder|weeks?.? time|issue (fresh )?notice|office notes|registrar|"
    r"sl\. ?no|video conferenc|holding brief|steps to be taken|service report|vakalatnama|"
    r"court.s or judge.s orders|versus|signatures?)\b.*$|^.*,\s*(c\.)?j\.\)?\s*$|^.*\(\s*[\w. ]+,\s*(c\.)?j\.\s*\).*$",
    re.I | re.M)
STOP = set("""petition petitioner petitioners respondent respondents state uttarakhand order orders dated date court
hon judge justice learned counsel matter hearing case cases list file filed filing time week weeks month months
granted grant application applications affidavit counter rejoinder notice notices issue issued interim extended
para paras submit submitted submits further also said shall would could within copy party parties present
nainital high writ prayer prayed connected heard record records direct directed direction directions dispose
disposed accordingly therefore thereof herein whether since however reply instruction instructions seek seeks
sought day days year years next made make produce take taken taking place last first second third service
registry office adjourn adjourned adjournment none appearance appear appeared behalf counsel's urgency
mr ms shri smt sri one two three four five six seven eight nine ten nos that with been which this those these
from have has were they them their there what when where stand stands proceed proceeding proceedings report
reports name names document documents inform informed section sections rule rules argue argued versus signature
signatures implead impleaded impleadment hon'ble respondent's petitioner's
amend amended amendment restore restored restoration request requested after allow allowed object objection
objections senior certified conference ground grounds incorporate incorporated memo misc miscellaneous till
continue continued continue then union before complete completed through already general note under article
articles constitution india given other even every stay stayed again only some such than into upon about above
below being both each more most much must need needs other same should very will while your yours above
earlier later today tomorrow time pending pend final finally finalise finally argument arguments relief reliefs
material materials consider considered considering opportunity opportunities appropriate appropriately
government uttaranchal secretary district collector officer authority authorities department director principal
reference referred learned petition's counsels deputy additional standing vide letter letters annexure annexures
dehradun haridwar nainital almora udham singh nagar pithoragarh tehri garhwal pauri chamoli bageshwar champawat
rudraprayag uttarkashi conference conferencing video urgent meantime another batch body bodies link linked along
well want whereby operate operation status question decision commence commenced appellant appellants appeal
appeals delay condone condonation period mean means because clarify clarified conclude concluded persons person
cost costs provide provided legal""".split())
_DF = {}


def _stems(text, instances=False):
    """Database jaisa tokenizer (porter): text -> stemmed shabd (instances=True par har baar aane ki ginti)."""
    mem = sqlite3.connect(":memory:")
    mem.execute('CREATE VIRTUAL TABLE f USING fts5(text, tokenize="porter unicode61 remove_diacritics 2")')
    mem.execute(f'CREATE VIRTUAL TABLE v USING fts5vocab(f, {"instance" if instances else "row"})')
    mem.execute("INSERT INTO f VALUES (?)", (text,))
    counts = {}
    for (t,) in mem.execute("SELECT term FROM v"):
        counts[t] = counts.get(t, 0) + 1
    return counts


_STOP_STEMS = None


def _terms(text, names):
    """Case ke orders ke kaam ke shabd (stemmed) aur ginti: kaam-kaaj ki lines, vakeel/party ke naam, aam shabd hata ke."""
    global _STOP_STEMS
    if _STOP_STEMS is None:
        _STOP_STEMS = set(_stems(" ".join(STOP)))
    clean = PROCEDURE.sub(" ", text)
    clean = " ".join(re.findall(r"\b[a-z]+\b", clean))   # sirf chhote akshar wale shabd: naam (judge, vakeel, staff) bade akshar se
    skip = _STOP_STEMS | set(_stems(" ".join(names)))
    return {t: n for t, n in _stems(clean, instances=True).items()
            if n >= 2 and len(t) >= 4 and t.isalpha() and t not in skip}   # ek baar aaya shabd = bhrosa nahi


def _df(con, term):
    if term not in _DF:
        con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS temp.pv USING fts5vocab(main, paragraphs_fts, row)")
        _DF[term] = (con.execute("SELECT doc FROM temp.pv WHERE term = ?", (term,)).fetchone() or [0])[0]
    return _DF[term]


def free_terms(con, text, names, top=6, min_df=40, max_share=0.05):
    """tf x idf se case ke sabse khaas shabd (bahut kam milne wale = naam / OCR galti, chhod do)."""
    total = con.execute("SELECT max(rowid) FROM paragraphs_fts").fetchone()[0] or 1
    scored = []
    for t, n in _terms(text, names).items():
        df = _df(con, t)
        if df < min_df or df > total * max_share:
            continue
        scored.append((n * math.log(total / df), t))
    return [t for _, t in sorted(scored, reverse=True)[:top]]


def related_free(con, terms, per_court=PER_COURT):
    """Kam se kam do khaas shabd ek hi paragraph mein: aise faisle, court ke nateeje (support/against) ke saath."""
    if len(terms) < 3:   # do-teen khaas shabd bhi nahi = orders mein vishay hai hi nahi; galat faisle se behtar kuch nahi
        return []
    pairs = [f'("{a}" AND "{b}")' for i, a in enumerate(terms[:5]) for b in terms[i + 1:5]]
    rows = con.execute(
        "SELECT p.judgment_id, p.para_no, p.text FROM paragraphs_fts f JOIN paragraphs p ON p.id = f.rowid "
        "WHERE paragraphs_fts MATCH ? AND p.section = 'body' ORDER BY bm25(paragraphs_fts) LIMIT 400",
        (" OR ".join(pairs),)).fetchall()
    best = {}
    for jid, para_no, text in rows:
        if jid not in best and len(text) > 150:
            best[jid] = (para_no, text)
    if not best:
        return []
    meta = {r[0]: r[1:] for r in con.execute(
        "SELECT j.id, j.court, j.title, j.case_no, j.neutral_citation, j.decision_date, j.judges, c.outcome "
        f"FROM judgments j LEFT JOIN categories c ON c.judgment_id = j.id WHERE j.id IN ({','.join('?' * len(best))})",
        list(best))}
    out, got = [], {}
    for jid, (para_no, text) in best.items():   # bm25 ke kram mein
        if jid not in meta:
            continue
        court, title, case_no, cite, date, judges, nateeja = meta[jid]
        g = side(nateeja)
        k = (court, g)
        if got.get(k, 0) >= per_court or (g == "other" and got.get((court, "other"), 0) >= 1):
            continue
        text = clean_quote(text)
        if any(text[:200] in o["quote"] for o in out):
            continue
        got[k] = got.get(k, 0) + 1
        out.append({
            "id": jid, "side": g, "q": " OR ".join(pairs),
            "court": "Supreme Court" if court == "SC" else "Nainital HC",
            "tag": (nateeja or "Nateeja ?") + " · shabdon se mila",
            "verified": False, "title": title or case_no or cite,
            "cite": " · ".join(x for x in [cite or case_no, ".".join(reversed((date or "").split("-"))),
                                            (judges or "").split(";")[0]] if x),
            "why": "Is case ke orders ke khaas shabd (" + ", ".join(terms[:5]) + ") isi faisle ke paragraph mein. "
                   "Court ka nateeja: " + (nateeja or "record mein nahi") + ".",
            "quote": "“" + (text[:420] + ("…" if len(text) > 420 else "")) + "”" + (f" (para {para_no})" if para_no else ""),
        })
    return sorted(out, key=lambda j: (j["court"] != "Supreme Court"))


SHRENI_BY_TYPE = [(("WPSS", "WPSB", "SPA", "CLAIM"), "Service"), (("BA", "ABA", "C482", "C528", "CRL", "WPCRL", "HABC", "SABA"), "Criminal"),
                  (("FA", "SA", "AO", "CLR", "CRP", "CR", "CMA"), "Civil"), (("WPMS", "WPMB", "WPPIL"), "Constitutional"),
                  (("CLCON", "CONC"), "Contempt"), (("ITA", "ITR", "GSTR", "STR", "TAX"), "Tax")]


def free_note(con, c, folder, case_type):
    """Vishay ke niyam na lage (orders mein sirf tareekhein / kaam-kaaj): shabdon se milte faisle, saaf likh ke."""
    _, text = case_text(folder)
    names = [p.get("name") or "" for p in (c.get("petitioners") or []) + (c.get("respondents") or [])]
    names += [p.get("advocate") or "" for p in (c.get("petitioners") or []) + (c.get("respondents") or [])]
    terms = free_terms(con, text, names)
    sims = related_free(con, terms)
    if len(sims) < 2:
        return None
    shreni = next((sh for pre, sh in SHRENI_BY_TYPE if case_type.upper().startswith(pre)), "Anya")
    return {
        "auto": True, "free": True,
        "badge": "Machine vishleshan · shabdon se",
        "vishay": {"shreni": shreni, "vishay": "Orders ke shabdon se", "upvishay": ", ".join(terms[:4]),
                   "mudde": [], "aur": []},
        "shabd": terms,
        "similar": sims,
        "disclaimer": "Is case ke orders mein vishay saaf nahi likha (zyaadatar tareekh / kaam-kaaj). Ye faisle orders ke "
                      "khaas shabdon se mile hain, isliye milaan kamzor ho sakta hai — advocate jaanch lein. Quote "
                      "faisle ka asli paragraph hai. Behtar nateeje ke liye Khoj mein case ki baat likhein.",
    }


def note_for(con, folder):
    c, text = case_text(folder)
    case_type = (c.get("registration_number") or folder.name).split("/")[0].split("-")[0]
    acts = " ".join(str(v) for a in c.get("acts") or [] for v in a.values() if v)
    tops, issues = topics_for(case_type, text, acts)
    if not tops:
        return free_note(con, c, folder, case_type)
    up = tops[0][0]
    cat, vishay, _, query, _ = next(t for t in taxonomy.TOPICS if t[2] == up)
    mudda = (issues.get(up) or [None])[0]
    sims = similar(con, up, mudda, query, balance=True) if mudda else []
    if len(sims) < 2:
        sims = similar(con, up, None, query, balance=True)
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
