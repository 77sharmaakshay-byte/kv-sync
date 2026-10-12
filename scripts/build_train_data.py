#!/usr/bin/env python3
"""Apna model sikhane ke liye data: Supreme Court ke faisle -> court ka khud likha headnote.

    python3 scripts/build_train_data.py --db full.db --out train/ [--test 1000]

Sirf AWS Open Data (CC-BY-4.0) wale SC faisle ('sc-scr') jinmein "HELD" hai.
Har line (JSONL): input = faisle ka text (headnote ke baad se), target = headnote
(mudda, HELD ke point, kaunse faisle relied on / distinguished). Seed fixed, taaki
test wale 1000 faisle har baar wahi rahein aur model ki jaanch imaandaar ho.
"""
import argparse
import gzip
import json
import random
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_judgment import _clean_lines  # noqa: E402  (page header / hashiye ki safai wahi)

BODY = re.compile(r"(The Judgment of the Court was delivered by|The following Judgment of the Court was delivered"
                  r"|Judgment / Order of the Supreme Court|delivered the following Judgment|"
                  r"The Judgment of the Court was delivered)", re.I)
HEAD_END = re.compile(r"\n(CIVIL|CRIMINAL) (APPELLATE|ORIGINAL) JURISDICTION|\nORIGINAL JURISDICTION|\nCase Arising From"
                      r"|\nAppearances for Parties|\nEXTRAORDINARY ORIGINAL JURISDICTION", re.I)
TREAT = re.compile(r"(relied on|followed|distinguished|referred to|overruled|approved|explained|held inapplicable)\.?\s*$",
                   re.I)


def _join(text, title):
    t = (title or "").upper()
    lines = _clean_lines(text, {t, t.replace(" VERSUS ", " V. ")})
    return re.sub(r"(\w)-\s+(\w)", r"\1\2", " ".join(lines)).strip()


def _treatments(head_raw):
    """Headnote ke case-law hisse se: '<case>, <citation>, relied on.' jaisi lines."""
    out = []
    for chunk in re.split(r"(?<=\.)\s+(?=[A-Z])", head_raw):
        m = TREAT.search(chunk)
        if m and (" v. " in chunk or " vs " in chunk.lower()):
            out.append({"case": chunk[:m.start()].strip(" ,;"), "treatment": m.group(1).lower()})
    return out


def pair(row):
    text = row["clean"]
    held = re.search(r"\bHELD\s*:", text)
    if not held:
        return None
    body = BODY.search(text, held.end())
    if not body:
        return None
    head_raw = text[:body.start()]
    cut = HEAD_END.search(head_raw, held.end())
    head_raw = head_raw[:cut.start()] if cut else head_raw
    head = _join(head_raw, row["title"])
    inp = _join(text[body.start():], row["title"])
    if len(head) < 300 or len(inp) < 2000:
        return None
    return {"key": row["source_key"], "year": row["year"], "title": row["title"],
            "cite": row["neutral_citation"], "report": row["report_citation"], "disposal": row["disposal"],
            "input": inp, "target": head, "treatments": _treatments(head)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--test", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=13)
    args = ap.parse_args()
    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute("select j.source_key, j.year, j.title, j.neutral_citation, j.report_citation, j.disposal, t.clean "
                       "from judgments j join texts t on t.judgment_id = j.id "
                       "where j.court = 'SC' and j.source = 'sc-scr' and t.clean like '%HELD%' order by j.id")
    pairs, skipped = [], 0
    for row in rows:
        p = pair(row)
        if p:
            pairs.append(p)
        else:
            skipped += 1
    random.Random(args.seed).shuffle(pairs)
    test, train = pairs[:args.test], pairs[args.test:]
    args.out.mkdir(parents=True, exist_ok=True)
    for name, items in (("train", train), ("test", test)):
        with gzip.open(args.out / f"{name}.jsonl.gz", "wt", encoding="utf-8") as f:
            for p in items:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
    stats = {"pairs": len(pairs), "train": len(train), "test": len(test), "skipped": skipped,
             "with_treatments": sum(1 for p in pairs if p["treatments"]),
             "licence": "AWS Open Data indian-supreme-court-judgments, CC-BY-4.0"}
    (args.out / "stats.json").write_text(json.dumps(stats, indent=1), encoding="utf-8")
    print(json.dumps(stats))


if __name__ == "__main__":
    main()
