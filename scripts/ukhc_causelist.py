"""Nainital High Court ki roz ki cause list — fetch_live.py ke uk-causelist / uk-find commands.

- uk-causelist : us din ki saari cause list PDFs (civil + criminal, har bench ki) laao,
                 text nikaalo, <out>/<DD-MM-YYYY>/ mein rakho (PDF + .txt + index.json).
                 List abhi court ne nahi daali to exit code 4 — GitHub Actions isi se
                 tay karta hai ki 8/10 baje dobara koshish karni hai.
- uk-find      : rakhi hui cause list mein naam / case number dhundho (enrolment number nahi chahiye).
"""
import hashlib
import json
import re
from pathlib import Path

from bharat_courts.hcservices.client import HCServicesClient

import ukhc_live
from live_common import safe

NOT_YET = 4


def _pdf_text(pdf):
    import pypdfium2  # Python 3.12 venv mein: pip install pypdfium2
    doc = pypdfium2.PdfDocument(pdf)
    try:
        return [doc[i].get_textpage().get_text_range() for i in range(len(doc))]
    finally:
        doc.close()


async def uk_causelist(out, args):
    day = args.date or ukhc_live._today_ist()
    folder = (Path(args.out).expanduser() if args.out else out / "uk" / "_causelist") / day
    index_path = folder / "index.json"
    if index_path.exists() and not args.force:
        print(f"{day} ki cause list pehle se hai: {index_path}")
        return 0
    entries, bad, seen = [], 0, set()
    async with HCServicesClient() as client:
        for civil in (True, False):
            kind = "civil" if civil else "criminal"
            try:
                pdfs = await client.cause_list(ukhc_live.UK, civil=civil, bench_code=args.bench, causelist_date=day)
            except Exception as err:  # noqa: BLE001
                bad += 1
                print(f"[error] {kind} list: {err}")
                continue
            print(f"{kind}: {len(pdfs)} PDF")
            for n, item in enumerate(pdfs, 1):
                name = safe(f"{kind}-{n:02d}-{item.bench}-{item.cause_list_type}")[:120]
                try:
                    pdf = await ukhc_live.order_pdf(client, item.pdf_url)
                except Exception as err:  # noqa: BLE001
                    bad += 1
                    print(f"  [error] {item.bench}: {err}")
                    continue
                digest = hashlib.sha256(pdf).hexdigest()
                if digest in seen:  # court civil aur criminal mein aksar wahi PDF deta hai
                    continue
                seen.add(digest)
                folder.mkdir(parents=True, exist_ok=True)
                (folder / f"{name}.pdf").write_bytes(pdf)
                pages = _pdf_text(pdf)
                (folder / f"{name}.txt").write_text("\f".join(pages), encoding="utf-8")
                entries.append({"kind": kind, "bench": item.bench, "type": item.cause_list_type,
                                "file": f"{name}.pdf", "pages": len(pages), "chars": sum(map(len, pages))})
                print(f"  [ok] {item.bench} · {item.cause_list_type} · {len(pages)} pages")
    if not entries:
        print(f"{day} ki cause list abhi court par nahi mili" + (" (errors upar)" if bad else ""))
        return NOT_YET
    index_path.write_text(json.dumps({"date": day, "benches": entries, "errors": bad}, ensure_ascii=False, indent=1),
                          encoding="utf-8")
    print(f"{day}: {len(entries)} PDFs saved in {folder}" + (f" · {bad} errors" if bad else ""))
    return 0


def _pattern(query):
    """'Bhagwat Mehra' -> naam ke shabd beech mein space/dot/naya line ke saath bhi milein; 'WPSS/818/2025' bhi."""
    words = [re.escape(w) for w in re.split(r"[\s./-]+", query.strip()) if w]
    return re.compile(r"[\s./-]*(?:No\.?|of)?[\s./-]*".join(words), re.I)


async def uk_find(out, args):
    day = args.date or ukhc_live._today_ist()
    folder = (Path(args.out).expanduser() if args.out else out / "uk" / "_causelist") / day
    if not (folder / "index.json").exists():
        print(f"{day} ki cause list nahi hai — pehle: uk-causelist --date {day}")
        return 1
    index = json.loads((folder / "index.json").read_text(encoding="utf-8"))
    pat, hits = _pattern(args.query), 0
    for e in index["benches"]:
        pages = (folder / e["file"]).with_suffix(".txt").read_text(encoding="utf-8").split("\f")
        for pno, text in enumerate(pages, 1):
            lines = text.splitlines()
            for i, line in enumerate(lines):
                nxt = lines[i + 1] if i + 1 < len(lines) else ""
                # Naam do lines mein toota ho to bhi milao, par ek hi jagah do baar na gino.
                if not (pat.search(line) or (pat.search(line + " " + nxt) and not pat.search(nxt))):
                    continue
                hits += 1
                ctx = " | ".join(x.strip() for x in lines[max(0, i - args.context):i + args.context + 1] if x.strip())
                print(f"[{e['bench']} · {e['type']} · page {pno}] {ctx[:400]}")
    print(f"{day}: '{args.query}' {hits} jagah mila")
    return 0 if hits else 1


def add_commands(sub):
    p = sub.add_parser("uk-causelist")
    p.add_argument("--date", help="DD-MM-YYYY (default: aaj, IST)")
    p.add_argument("--out", help="kahan rakhein (default: <data>/live/uk/_causelist)")
    p.add_argument("--force", action="store_true", help="pehle se ho to bhi dobara laao")
    p = sub.add_parser("uk-find")
    p.add_argument("query", help="advocate ka naam ya case number, jaise \"Bhagwat Mehra\" ya WPSS/818/2025")
    p.add_argument("--date", help="DD-MM-YYYY (default: aaj)")
    p.add_argument("--out", help="cause list kahan rakhi hai (default: <data>/live/uk/_causelist)")
    p.add_argument("--context", type=int, default=2, help="aas-paas ki kitni lines dikhani hain")
    return {"uk-causelist": uk_causelist, "uk-find": uk_find}
