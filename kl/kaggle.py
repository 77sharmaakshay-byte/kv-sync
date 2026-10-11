"""Kaggle wala purana SC dataset (vangap, CC-BY-NC-SA-4.0) -> database.

Isme SCR (reportable) ke alawa non-reportable judgments bhi hain (1950-2024).
Zip ko kholna nahi padta — PDFs seedhe zip se padhe jaate hain.

Metadata CSV (diary_no, case_no, pet, res, bench, judgement_by,
judgment_dates, temp_link...) zip ke andar ho to wahi, warna repo mein rakhi
copy (vendor/product/indian-supreme-court-judgments-old) use hoti hai.
Zip mein PDF ka naam diary_no + '___' + temp_link hota hai
(jaise 'pdfs/-0___jonew__judis__10166.pdf'); CSV row isi se milti hai.

Jo judgment SCR wale data mein pehle se hai (tareekh + petitioner ke naam se
milaan), use dobara nahi jodte. Har row ke meta_json mein license likha hota
hai, taaki launch se pehle NC wale alag kiye ja sakein.
"""
import csv
import datetime as dt
import io
import json
import re
import zipfile
from collections import Counter
from pathlib import Path

from . import ingest

LICENSE = "CC-BY-NC-SA-4.0"
VENDORED_CSV = (Path(__file__).resolve().parent.parent / "vendor" / "product" /
                "indian-supreme-court-judgments-old" / "data" / "metadata" / "clean" / "judgments.csv")


def _tail(path, n=2):
    parts = [p for p in re.split(r"[\\/]", path or "") if p]
    return "/".join(parts[-n:]).lower()


def _iso(s):
    try:
        return dt.datetime.strptime((s or "").strip()[:10], "%d-%m-%Y").strftime("%Y-%m-%d")
    except ValueError:
        return None


def _key(name):
    """Naam ke pehle 12 akshar, 'THE' hata kar."""
    return re.sub(r"[^A-Z]", "", re.sub(r"^\s*THE\s+", "", (name or "").upper()))[:12]


def _is_dup(existing, counts, date, pet, res):
    """SCR mein yahi faisla hai? Tareekh + petitioner ek hi case se mile to haan; ek din mein usi
    petitioner ke kai case hon ('STATE OF ...') to respondent bhi milna chahiye."""
    cands = existing.get((date, _key(pet)))
    if not cands:
        return False
    if len(cands) == 1 and counts[(date, _key(pet))] == 1:
        return True
    rk = _key(res)
    # '& ORS.' / 'AND OTHERS' jaise pichhle hisse alag hote hain — chhota naam bade ka shuruaati hissa ho to wahi.
    return any(min(len(c), len(rk)) >= 5 and (c.startswith(rk) or rk.startswith(c)) for c in cands)


def _judges(bench):
    """'SIKRI, S.M.,SHELAT, J.M.' -> ['SIKRI, S.M.', 'SHELAT, J.M.'] (naam 'UPNAAM, INITIALS' jode mein hote hain)."""
    return [m.strip() for m in re.findall(r"[^,]+,[^,]+", bench or "") if m.strip()]


def find_zip(data_dir):
    zips = sorted((Path(data_dir) / "kaggle-sc-all").glob("*.zip"))
    return zips[0] if zips else None


def inspect(zip_path, show=15):
    """Zip ke andar kya hai — PDFs kitne, CSV kaun si, naam kaise dikhte hain."""
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
    pdfs = [n for n in names if n.lower().endswith(".pdf")]
    csvs = [n for n in names if n.lower().endswith(".csv")]
    print(f"{zip_path}: {len(names)} files, {len(pdfs)} PDF, {len(csvs)} CSV")
    for n in csvs[:5]:
        print("  csv:", n)
    for n in pdfs[:show]:
        print("  pdf:", n)


def _rows(z):
    """Metadata rows: zip ke andar ki CSV, warna repo wali copy."""
    inner = [n for n in z.namelist() if n.lower().endswith(".csv") and "judgment" in n.lower()]
    if inner:
        text = io.TextIOWrapper(z.open(inner[0]), encoding="utf-8", errors="replace")
        return list(csv.DictReader(text)), inner[0]
    with open(VENDORED_CSV, encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f)), str(VENDORED_CSV)


def _parse_member(name):
    """'pdfs/-0___jonew__judis__10166.pdf' -> ('-0', 'jonew/judis/10166.pdf').
    Kaggle zip mein naam = diary_no + '___' + temp_link ('/' ki jagah '__')."""
    base = name.rsplit("/", 1)[-1]
    if "___" not in base:
        return None, base.lower()
    diary, rest = base.split("___", 1)
    return diary, rest.replace("__", "/").lower()


def _index(names):
    """Zip ke PDFs teen tarah se dhoondhne layak: (diary, link), sirf link, aur aakhri hissa."""
    exact, by_link, by_tail = {}, {}, {}
    for n in names:
        if not n.lower().endswith(".pdf"):
            continue
        diary, link = _parse_member(n)
        exact[(diary, link)] = n
        by_link.setdefault(link, []).append(n)
        by_tail.setdefault(_tail(link), []).append(n)
    return exact, by_link, by_tail


def _find(idx, diary, link):
    exact, by_link, by_tail = idx
    link = link.lower()
    if (diary, link) in exact:
        return exact[(diary, link)]
    for table, key in ((by_link, link), (by_tail, _tail(link))):
        hits = table.get(key, [])
        if len(hits) == 1:
            return hits[0]
    return None


def _insert(con, rel, member, r, csv_src):
    """Ek Kaggle row (r = CSV row, ya None jab PDF ka metadata nahi mila)."""
    r = r or {}
    date = _iso(r.get("judgment_dates"))
    pet, res = (r.get("pet") or "").strip(), (r.get("res") or "").strip()
    judges = _judges(r.get("bench"))
    meta = {"license": LICENSE, "diary_no": r.get("diary_no") or _parse_member(member)[0], "csv": csv_src,
            "pet_adv": r.get("pet_adv"), "res_adv": r.get("res_adv")}
    if not r:
        meta["orphan"] = "Kaggle CSV mein nahi mila"
    cur = con.execute(
        "INSERT INTO judgments (source, source_key, court, title, petitioner, respondent, case_no, "
        "decision_date, year, judges, bench_size, author_judge, pdf_archive, pdf_member, meta_json) "
        "VALUES ('sc-kaggle', ?, 'SC', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(source_key) DO NOTHING",
        ("kaggle:" + member.rsplit("/", 1)[-1], f"{pet} versus {res}" if pet or res else None, pet or None,
         res or None, (r.get("case_no") or "").strip() or None, date, int(date[:4]) if date else None,
         json.dumps(judges, ensure_ascii=False) if judges else None, len(judges) or None,
         (r.get("judgement_by") or "").strip() or None, rel, member, json.dumps(meta, ensure_ascii=False)))
    return cur.rowcount


def load(con, data_dir, workers=None, log=print):
    data_dir = Path(data_dir)
    zpath = find_zip(data_dir)
    if zpath is None:
        log("Kaggle zip nahi mili (<data>/kaggle-sc-all/*.zip).")
        return None
    rel = str(zpath.relative_to(data_dir))
    existing = {}
    for d, pet, res in con.execute("SELECT decision_date, petitioner, respondent FROM judgments "
                                   "WHERE court = 'SC' AND source != 'sc-kaggle' AND decision_date IS NOT NULL"):
        existing.setdefault((d, _key(pet)), []).append(_key(res))
    with zipfile.ZipFile(zpath) as z:
        names = z.namelist()
        idx = _index(names)
        rows, csv_src = _rows(z)
        counts = Counter((_iso(r.get("judgment_dates")), _key(r.get("pet"))) for r in rows)
        stats = {"rows": len(rows), "already_scr": 0, "no_pdf": 0, "added": 0, "orphans": 0}
        used = set()
        for r in rows:
            link = (r.get("temp_link") or "").strip()
            member = _find(idx, (r.get("diary_no") or "").strip(), link) if link else None
            if member is None:
                stats["no_pdf"] += 1
                continue
            if member in used:
                continue
            used.add(member)
            date = _iso(r.get("judgment_dates"))
            pet, res = (r.get("pet") or "").strip(), (r.get("res") or "").strip()
            if date and pet and _is_dup(existing, counts, date, pet, res):
                stats["already_scr"] += 1
                continue
            stats["added"] += _insert(con, rel, member, r, csv_src)
        # Zip mein PDF hai par CSV mein uski row nahi — phir bhi jodo, koi judgment na chhoote.
        for n in names:
            if n.lower().endswith(".pdf") and n not in used:
                stats["orphans"] += _insert(con, rel, n, None, csv_src)
        con.commit()
        log(f"Kaggle: {stats['rows']} CSV rows, {len(used)} PDFs se mili; {stats['already_scr']} SCR mein pehle se, "
            f"{stats['no_pdf']} rows ki PDF zip mein nahi, {stats['added']} naye, "
            f"{stats['orphans']} PDFs bina CSV row ke (phir bhi jode).")
        todo = con.execute("SELECT id, pdf_member FROM judgments WHERE source = 'sc-kaggle' AND pdf_archive = ? "
                           "AND (text_version IS NULL OR text_version < ?)", (rel, ingest.PARSER_VERSION)).fetchall()
        log(f"Kaggle: {len(todo)} PDFs padhne hain...")
        result = ingest.run_items(con, ((jid, "SC", z.read(m)) for jid, m in todo), workers=workers)
    stats.update(result)
    return stats
