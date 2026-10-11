"""AWS metadata (parquet) -> judgments table ki rows.

Data folder wahi hai jo scripts/mirror_data.py banata hai:
  <data>/indian-supreme-court-judgments/metadata/parquet/year=YYYY/metadata.parquet
  <data>/indian-supreme-court-judgments/data/tar/year=YYYY/english/*.tar (+ english.index.json)
  <data>/indian-high-court-judgments/metadata/parquet/year=YYYY/court=5_15/bench=*/metadata.parquet
  <data>/indian-high-court-judgments/data/tar/year=YYYY/court=5_15/bench=*/*.tar (+ data.index.json)
"""
import datetime as dt
import json
import re
from pathlib import Path

import pyarrow.parquet as pq

SC_BUCKET = "indian-supreme-court-judgments"
HC_BUCKET = "indian-high-court-judgments"
UK_COURT = "5_15"

_UK_TITLE = re.compile(r"^\s*(?P<case>[A-Z0-9().-]+/\d+/\d{4})\s+of\s+(?P<pet>.*?)\s+Vs\.?\s+(?P<res>.*?)\s*$", re.S | re.I)


def _iso(value):
    """'25-09-2024' / datetime / '2024-09-25' -> '2024-09-25' (ya None)."""
    if value is None or value == "":
        return None
    if isinstance(value, (dt.date, dt.datetime)):
        return value.strftime("%Y-%m-%d")
    s = str(value).strip()
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(s[:19] if "%H" in fmt else s[:10], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _s(value):
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _index_members(index_path):
    """index.json -> {pdf file ka naam: (tar ka naam, naam bina './' ke)}."""
    data = json.loads(Path(index_path).read_text(encoding="utf-8"))
    out = {}
    for part in data.get("parts", []):
        for name in part.get("files", []):
            short = name[2:] if name.startswith("./") else name
            out[short] = (part["name"], short)
    return out


def sc_rows(data_dir):
    """Supreme Court (e-SCR) ki rows."""
    base = Path(data_dir) / SC_BUCKET
    for pq_path in sorted((base / "metadata" / "parquet").glob("year=*/metadata.parquet")):
        year_dir = pq_path.parent.name                      # 'year=2024'
        tar_dir = base / "data" / "tar" / year_dir / "english"
        index = tar_dir / "english.index.json"
        members = _index_members(index) if index.exists() else {}
        cols = [c for c in pq.read_schema(pq_path).names if c != "raw_html"]
        for r in pq.read_table(pq_path, columns=cols).to_pylist():
            key = _s(r.get("path"))
            if not key:
                continue
            tar, member = members.get(f"{key}_EN.pdf", (None, None))
            date = _iso(r.get("decision_date"))
            yield {
                "source": "sc-scr", "source_key": key, "court": "SC",
                "title": _s(r.get("title")), "petitioner": _s(r.get("petitioner")),
                "respondent": _s(r.get("respondent")),
                "decision_date": date, "year": int(date[:4]) if date else _int(r.get("year")),
                "author_judge": _s(r.get("author_judge")),
                "neutral_citation": _s(r.get("case_id")), "report_citation": _s(r.get("citation")),
                "cnr": _s(r.get("cnr")), "disposal": _s(r.get("disposal_nature")),
                "pdf_archive": str((tar_dir / tar).relative_to(data_dir)) if tar else None,
                "pdf_member": member,
                "meta_json": json.dumps({k: _s(r.get(k)) for k in ("judge", "description", "available_languages", "scraped_at")},
                                        ensure_ascii=False),
            }


def uk_rows(data_dir):
    """Uttarakhand High Court ki rows."""
    base = Path(data_dir) / HC_BUCKET
    for pq_path in sorted((base / "metadata" / "parquet").glob(f"year=*/court={UK_COURT}/bench=*/metadata.parquet")):
        rel = pq_path.parent.relative_to(base / "metadata" / "parquet")   # year=..../court=.../bench=...
        tar_dir = base / "data" / "tar" / rel
        index = tar_dir / "data.index.json"
        members = _index_members(index) if index.exists() else {}
        cols = [c for c in pq.read_schema(pq_path).names if c not in ("raw_html", "description")]
        for r in pq.read_table(pq_path, columns=cols).to_pylist():
            link = _s(r.get("pdf_link"))
            if not link:
                continue
            fname = link.rsplit("/", 1)[-1]
            key = fname[:-4] if fname.lower().endswith(".pdf") else fname
            tar, member = members.get(fname, (None, None))
            date = _iso(r.get("decision_date"))
            m = _UK_TITLE.match(r.get("title") or "")
            yield {
                "source": "uk-hc", "source_key": key, "court": "UKHC",
                "title": _s(r.get("title")),
                "petitioner": _s(m.group("pet")) if m else None,
                "respondent": _s(m.group("res")) if m else None,
                "case_no": m.group("case").upper() if m else None,
                "case_type": m.group("case").split("/")[0].upper() if m else None,
                "decision_date": date, "year": int(date[:4]) if date else None,
                "cnr": _s(r.get("cnr")), "disposal": _s(r.get("disposal_nature")),
                "pdf_archive": str((tar_dir / tar).relative_to(data_dir)) if tar else None,
                "pdf_member": member,
                "meta_json": json.dumps({"judge": _s(r.get("judge")),
                                         "date_of_registration": _s(r.get("date_of_registration"))},
                                        ensure_ascii=False),
            }


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


COLUMNS = ["source", "source_key", "court", "title", "petitioner", "respondent", "case_no", "case_type",
           "decision_date", "year", "author_judge", "neutral_citation", "report_citation", "cnr",
           "disposal", "pdf_archive", "pdf_member", "meta_json"]


def upsert(con, rows):
    """Rows ko judgments mein daalo; pehle se ho to metadata taaza karo (text wale columns nahi chhedte)."""
    sql = (f"INSERT INTO judgments ({', '.join(COLUMNS)}) VALUES ({', '.join('?' * len(COLUMNS))}) "
           "ON CONFLICT(source_key) DO UPDATE SET "
           + ", ".join(f"{c}=COALESCE(excluded.{c}, judgments.{c})" for c in COLUMNS if c != "source_key"))
    n = 0
    for row in rows:
        con.execute(sql, [row.get(c) for c in COLUMNS])
        n += 1
    con.commit()
    return n
