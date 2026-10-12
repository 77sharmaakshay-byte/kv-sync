#!/usr/bin/env python3
"""Database se ek judgment app ke liye: saaf para-wise text (JSON) + asli PDF.

    python3 scripts/export_judgment.py --db full.db "2024 INSC 675" WPSB/316/2023 2017_6_444_452

Pehchaan: neutral citation ('2024 INSC 675'), source_key, HC case number, ya database id.
Nateeja app/judgments/<key>.json aur <key>.pdf; Render wali site par 'Download PDF' isi se.
PDF AWS Open Data (CC-BY-4.0) ke tar se aati hai: tar ko stream karke sirf woh file nikalte hain,
poora tar disk par nahi utarta.

app/notes/judgments/<key>.json ho to woh 'note' (advocate ke liye saar) ke roop mein jud jaata hai.
"""
import argparse
import json
import re
import sqlite3
import ssl
import sys
import tarfile
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "app" / "judgments"
NOTES = ROOT / "app" / "notes" / "judgments"
BUCKETS = {
    "indian-supreme-court-judgments": "https://indian-supreme-court-judgments.s3.amazonaws.com/",
    "indian-high-court-judgments": "https://indian-high-court-judgments.s3.amazonaws.com/",
}
LICENCE = "AWS Open Data — CC-BY-4.0 (indian-supreme-court-judgments / indian-high-court-judgments)"

# Page ke upar-neeche baar baar aane wali lines (SCR header, HC neutral citation, page number, margin letters)
NOISE = [
    re.compile(r"^\[?\d{4}[\])]\s*\d+\s*S\.\s?C\.\s?R\.\s*\d*(\s*:\s*\d{4} INSC \d+)?$"),
    re.compile(r"^\d+\s+(\[\d{4}\]\s*\d+\s*S\.C\.R\.|SUPREME COURT REPORTS.*)$"),
    re.compile(r"^Digital Supreme Court Reports$"),
    re.compile(r"^\d{4}:UHC:\d+(-DB)?$"),
    re.compile(r"^\d{1,3}$"),
    re.compile(r"^[A-H]$"),
]
PARA = re.compile(r"^(\d{1,3})\.\s+(?=\S)")


def _clean_lines(text, running_titles):
    out = []
    for ln in text.replace("\f", "\n").splitlines():
        s = re.sub(r"^[A-H]\s+(?=\d{1,3}\.\s)", "", ln.strip())  # purani SCR ke hashiye ke akshar
        if s.startswith("Digitally signed by"):  # HC PDF ke ant mein signature ka block
            break
        if not s or any(p.match(s) for p in NOISE) or s.upper() in running_titles:
            continue
        out.append(re.sub(r"\s+[A-H]$", "", s))
    return out


def split_paras(text, title):
    """Saaf text ko judgment ke apne para numbers par baanto. Pehle para se pehle ka hissa 'head'."""
    t = (title or "").upper()
    running = {t, t.replace(" VERSUS ", " V. "), t.replace(" VERSUS ", " V ")}
    head, paras, cur, expect = [], [], None, 1
    for s in _clean_lines(text, running):
        m = PARA.match(s)
        # Ek number OCR mein bigad jaye ('I.' for '1.') to agla number bhi chalega
        if m and expect <= int(m.group(1)) <= expect + 1:
            if cur:
                paras.append(cur)
            cur = {"no": m.group(1), "lines": [s[m.end():]]}
            expect = int(m.group(1)) + 1
        elif cur:
            cur["lines"].append(s)
        else:
            head.append(s)
    if cur:
        paras.append(cur)
    join = lambda ls: re.sub(r"(\w)-\s+(\w)", r"\1\2", " ".join(ls)).strip()
    return join(head), [{"no": p["no"], "text": join(p["lines"])} for p in paras]


def _find(con, spec):
    q = "select * from judgments where "
    for where, arg in (("neutral_citation = ?", spec), ("source_key = ?", spec),
                       ("case_no = ? order by decision_date desc", spec.upper())):
        row = con.execute(q + where, (arg,)).fetchone()
        if row:
            return row
    if spec.isdigit():
        return con.execute(q + "id = ?", (int(spec),)).fetchone()
    return None


def _ctx():
    cafile = None
    for cand in ("/root/.ccr/ca-bundle.crt",):
        if Path(cand).exists():
            cafile = cand
    return ssl.create_default_context(cafile=cafile)


def fetch_pdf(archive, member):
    """archive: 'indian-supreme-court-judgments/data/tar/...tar'. Tar stream karke member nikalo."""
    bucket, _, key = archive.partition("/")
    base = BUCKETS.get(bucket)
    if not base:
        raise ValueError(f"anjaan archive: {archive}")
    url = base + urllib.parse.quote(key)
    with urllib.request.urlopen(url, context=_ctx(), timeout=120) as resp:
        with tarfile.open(fileobj=resp, mode="r|") as tar:
            for info in tar:
                if Path(info.name).name == member:
                    data = tar.extractfile(info).read()
                    if not data.startswith(b"%PDF"):
                        data = data[data.find(b"%PDF"):] if b"%PDF" in data[:1024] else data
                    return data
    raise FileNotFoundError(f"{member} tar mein nahi mila ({url})")


def _key(row):
    return re.sub(r"[^A-Za-z0-9_-]", "-", row["source_key"])


def _pdf_name(row):
    who = " v ".join(x for x in [(row["petitioner"] or "").title(), (row["respondent"] or "").title()] if x)
    cite = row["neutral_citation"] or row["case_no"] or row["source_key"]
    name = re.sub(r"[^A-Za-z0-9]+", "-", f"{who[:60]} {cite}").strip("-")
    return name + ".pdf"


def export(con, spec, with_pdf=True):
    row = _find(con, spec)
    if not row:
        print(f"!! {spec}: database mein nahi mila", file=sys.stderr)
        return None
    text = con.execute("select clean from texts where judgment_id = ?", (row["id"],)).fetchone()
    head, paras = split_paras(text[0] if text else "", row["title"])
    meta = json.loads(row["meta_json"] or "{}")
    key = _key(row)
    doc = {
        "key": key, "court": "Supreme Court" if row["court"] == "SC" else "Nainital HC",
        "title": row["title"], "petitioner": row["petitioner"], "respondent": row["respondent"],
        "case_no": row["case_no"], "date": row["decision_date"],
        "neutral_citation": row["neutral_citation"], "report_citation": row["report_citation"],
        "judges": meta.get("judge"), "disposal": row["disposal"], "pages": row["pages"],
        "head": head, "paras": paras, "source": LICENCE,
        "pdf": None, "pdf_name": _pdf_name(row),
    }
    note = NOTES / f"{key}.json"
    if note.exists():
        doc["note"] = json.loads(note.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    pdf_path = OUT / f"{key}.pdf"
    if with_pdf and row["pdf_archive"] and row["pdf_member"]:
        if not pdf_path.exists():
            try:
                pdf_path.write_bytes(fetch_pdf(row["pdf_archive"], row["pdf_member"]))
            except Exception as e:  # PDF na mile to bhi text wala page bane
                print(f"!! {spec}: PDF nahi aayi — {e}", file=sys.stderr)
        if pdf_path.exists():
            doc["pdf"] = f"{key}.pdf"
    (OUT / f"{key}.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{spec} -> {key} · {len(paras)} para · pdf {'haan' if doc['pdf'] else 'nahi'}")
    return key


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True, type=Path)
    ap.add_argument("--no-pdf", action="store_true")
    ap.add_argument("specs", nargs="+")
    args = ap.parse_args()
    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    bad = [s for s in args.specs if not export(con, s, not args.no_pdf)]
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
