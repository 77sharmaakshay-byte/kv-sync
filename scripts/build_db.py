#!/usr/bin/env python3
"""Downloaded data se judgments database banana (ya adhoora ho to aage badhana).

    python3 scripts/build_db.py --data ~/krishivlaw-data
    python3 scripts/build_db.py --data ~/krishivlaw-data --search "compassionate appointment"

Database file: <data>/krishivlaw.db (ya --db se apna path).
Dobara chalao to sirf baaki documents bante hain; beech mein rok do to
agli baar wahin se chalega.
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kl import db, ingest, meta  # noqa: E402


def search(con, query, limit=10):
    rows = con.execute(
        "SELECT j.court, j.year, j.title, j.neutral_citation, j.case_no, count(*) AS hits "
        "FROM paragraphs_fts f JOIN paragraphs p ON p.id = f.rowid JOIN judgments j ON j.id = p.judgment_id "
        "WHERE paragraphs_fts MATCH ? GROUP BY j.id ORDER BY hits DESC LIMIT ?", (query, limit)).fetchall()
    for r in rows:
        print(f"{r['court']:5s} {r['year'] or '':5} {r['neutral_citation'] or r['case_no'] or '':16s} {r['title'] or ''}"[:150])
    if not rows:
        print("Kuch nahi mila.")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", required=True, type=Path, help="mirror_all.sh wala data folder")
    ap.add_argument("--db", type=Path, help="database file (default: <data>/krishivlaw.db)")
    ap.add_argument("--workers", type=int, help="kitne CPU cores (default: sab minus ek)")
    ap.add_argument("--search", help="database ban jaane ke baad sirf search karo")
    args = ap.parse_args()

    data = args.data.expanduser()
    dbp = (args.db or data / "krishivlaw.db").expanduser()
    con = db.connect(dbp)
    if args.search:
        search(con, args.search)
        return 0

    t0 = time.time()
    n_sc = meta.upsert(con, meta.sc_rows(data))
    n_uk = meta.upsert(con, meta.uk_rows(data))
    print(f"== Metadata: SC {n_sc}, Nainital HC {n_uk}  ({time.time() - t0:.0f}s)", flush=True)

    print("== PDFs padh kar text aur para (sabse lamba hissa)...", flush=True)
    stats = ingest.run(con, data, workers=args.workers, log=lambda m: print("  " + m, flush=True))
    total = con.execute("SELECT count(*), sum(text_version IS NOT NULL), sum(has_text) FROM judgments").fetchone()
    print(f"== Ho gaya: {total[0]} documents, {total[1]} padhe gaye, {total[2]} mein text mila. "
          f"Errors {stats['errors']}, bina metadata {stats['orphans']}. ({(time.time() - t0) / 60:.0f} min)")
    print(f"Database: {dbp}")
    return 1 if stats["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
