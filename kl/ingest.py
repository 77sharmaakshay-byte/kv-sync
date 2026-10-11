"""Tar archives se PDFs padh kar text, para, citations database mein daalna.

- Har tar ek hi baar shuru se aakhir tak padha jata hai (tez, disk par seek nahi).
- PDF -> text -> structure ka bhaari kaam alag processes mein hota hai;
  database mein likhna sirf main process karta hai.
- Dobara chalao to sirf wahi documents dobara bante hain jinka text abhi
  nahi bana, ya jo purane parser version se bane the (PARSER_VERSION).
- Jo PDF tar mein hai par metadata mein nahi, uski bhi row ban jaati hai
  (source_key = file ka naam), taaki koi judgment chhoote nahi.
"""
import hashlib
import json
import os
import tarfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from . import pdftext, structure, textnorm

PARSER_VERSION = structure.VERSION


def _process(args):
    """Worker: PDF bytes -> sab kuch jo database mein jana hai. (Alag process mein chalta hai.)"""
    jid, court, pdf_bytes = args
    out = {"id": jid, "sha256": hashlib.sha256(pdf_bytes).hexdigest()}
    try:
        pages, has_text = pdftext.extract(pdf_bytes)
    except ValueError as err:
        out["error"] = str(err)
        return out
    raw = "\f".join(pages)
    clean = textnorm.clean(raw)
    out.update(pages=len(pages), has_text=has_text, raw=raw, clean=clean,
               parsed=structure.parse(court, clean) if has_text else None)
    return out


def _pending(con, archive, force):
    """Is tar ke documents: {tar member: (judgment id, court)} jinka text banana hai."""
    cond = "" if force else " AND (text_version IS NULL OR text_version < ?)"
    params = [archive] + ([] if force else [PARSER_VERSION])
    rows = con.execute(f"SELECT id, court, pdf_member FROM judgments WHERE pdf_archive = ?{cond}", params)
    return {r["pdf_member"]: (r["id"], r["court"]) for r in rows}


def member_name(name):
    """Tar ke andar ka naam bina './' ke — index.json aur tar dono mein yahi roop rakhte hain."""
    return name[2:] if name.startswith("./") else name


def _orphan_row(con, archive, name):
    """Tar mein PDF hai par metadata nahi — minimal row bana do."""
    court = "UKHC" if "court=5_15" in archive else "SC"
    key = name[:-4] if name.lower().endswith(".pdf") else name
    if court == "SC" and key.endswith("_EN"):
        key = key[:-3]
    cur = con.execute(
        "INSERT INTO judgments (source, source_key, court, pdf_archive, pdf_member, meta_json) "
        "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(source_key) DO NOTHING",
        ("uk-hc" if court == "UKHC" else "sc-scr", key, court, archive, name,
         json.dumps({"orphan": "metadata mein nahi mila"})))
    return (cur.lastrowid, court) if cur.rowcount else None


def _store(con, res):
    jid = res["id"]
    if "error" in res:
        con.execute("UPDATE judgments SET has_text = 0, pdf_sha256 = ?, text_version = ?, meta_json = "
                    "json_set(COALESCE(meta_json, '{}'), '$.pdf_error', ?) WHERE id = ?",
                    (res["sha256"], PARSER_VERSION, res["error"], jid))
        return
    p = res["parsed"] or {}
    con.execute("DELETE FROM paragraphs WHERE judgment_id = ?", (jid,))
    con.execute("DELETE FROM citations WHERE judgment_id = ?", (jid,))
    con.execute("DELETE FROM treatments WHERE judgment_id = ?", (jid,))
    con.execute("INSERT OR REPLACE INTO texts (judgment_id, raw, clean, body_start) VALUES (?, ?, ?, ?)",
                (jid, res["raw"], res["clean"], p.get("body_start")))
    para_ids = []
    for seq, para in enumerate(p.get("paragraphs", [])):
        cur = con.execute(
            "INSERT INTO paragraphs (judgment_id, seq, para_no, section, opinion, char_start, char_end, text) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (jid, seq, para.get("para_no"), para["section"], para.get("opinion"),
             para["start"], para["end"], res["clean"][para["start"]:para["end"]]))
        para_ids.append(cur.lastrowid)
    for c in p.get("citations", []):
        con.execute("INSERT INTO citations (judgment_id, paragraph_id, kind, raw, normalized) VALUES (?, ?, ?, ?, ?)",
                    (jid, _para_id(para_ids, c.get("para_seq")), c["kind"], c["raw"], c["normalized"]))
    for t in p.get("treatments", []):
        con.execute("INSERT INTO treatments (judgment_id, paragraph_id, phrase, context) VALUES (?, ?, ?, ?)",
                    (jid, _para_id(para_ids, t.get("para_seq")), t["phrase"], t["context"]))
    fields = {k: p.get(k) for k in ("reportable", "doc_kind", "doc_kind_score", "bench_size", "author_judge")}
    fields["judges"] = json.dumps(p["judges"], ensure_ascii=False) if p.get("judges") else None
    con.execute(
        "UPDATE judgments SET has_text = ?, pages = ?, chars = ?, pdf_sha256 = ?, text_version = ?, "
        "reportable = COALESCE(?, reportable), doc_kind = ?, doc_kind_score = ?, "
        "bench_size = COALESCE(?, bench_size), author_judge = COALESCE(?, author_judge), "
        "judges = COALESCE(?, judges), case_no = COALESCE(case_no, ?) WHERE id = ?",
        (int(res["has_text"]), res["pages"], len(res["clean"]), res["sha256"], PARSER_VERSION,
         fields["reportable"], fields["doc_kind"], fields["doc_kind_score"], fields["bench_size"],
         fields["author_judge"], fields["judges"], p.get("case_no"), jid))


def _para_id(para_ids, seq):
    return para_ids[seq] if seq is not None and 0 <= seq < len(para_ids) else None


def run(con, data_dir, archives=None, workers=None, force=False, log=print):
    """Saare (ya diye gaye) tar archives process karo. Lautata hai {done, errors, orphans}."""
    data_dir = Path(data_dir)
    if archives is None:
        archives = [r[0] for r in con.execute(
            "SELECT DISTINCT pdf_archive FROM judgments WHERE pdf_archive IS NOT NULL ORDER BY 1")]
        # Metadata ke bina wale part-*.tar bhi pakdo.
        for tar in sorted(data_dir.glob("*/data/tar/**/*.tar")):
            rel = str(tar.relative_to(data_dir))
            if rel not in archives and ("/english/" in rel or "court=5_15" in rel):
                archives.append(rel)
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    stats = {"done": 0, "errors": 0, "orphans": 0, "conflicts": 0}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for archive in archives:
            path = data_dir / archive
            if not path.exists():
                log(f"[missing] {archive}")
                continue
            todo = _pending(con, archive, force)
            jobs = []
            with tarfile.open(path) as tar:
                for member in tar:
                    if not member.isfile() or not member.name.lower().endswith(".pdf"):
                        continue
                    name = member_name(member.name)
                    target = todo.get(name)
                    if target is None and not con.execute(
                            "SELECT 1 FROM judgments WHERE pdf_archive = ? AND pdf_member = ?",
                            (archive, name)).fetchone():
                        target = _orphan_row(con, archive, name)
                        if target:
                            stats["orphans"] += 1
                        else:
                            # Isi naam ki row kisi aur tar ke saath pehle se hai — chupchaap mat chhodo.
                            stats["conflicts"] += 1
                            log(f"[conflict] {archive}: {name} ki row doosre archive ke saath pehle se hai")
                    if target is None:
                        continue
                    jobs.append((target[0], target[1], tar.extractfile(member).read()))
                    if len(jobs) >= workers * 8:
                        stats = _flush(con, pool, jobs, stats)
                        jobs = []
                stats = _flush(con, pool, jobs, stats)
            log(f"[ok] {archive}: kul {stats['done']} done, {stats['errors']} errors, "
                f"{stats['orphans']} bina metadata, {stats['conflicts']} conflicts")
    return stats


def _flush(con, pool, jobs, stats):
    for res in pool.map(_process, jobs, chunksize=4):
        _store(con, res)
        stats["done"] += 1
        stats["errors"] += "error" in res
    con.commit()
    return stats
