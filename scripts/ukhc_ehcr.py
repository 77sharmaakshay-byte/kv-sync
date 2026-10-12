#!/usr/bin/env python3
"""Nainital HC ki apni cause list site (ehcr.uk.gov.in) — court yahan list eCourts se pehle daalta hai
(jaise kal ki list aaj shaam 5 baje), par site sirf India se khulti hai, isliye 'fetch' Mac runner par chalta hai.

    python3 scripts/ukhc_ehcr.py fetch --out ehcr          # Mac: aaj aur aage ki saari list PDFs + ehcr.json
    python3 scripts/ukhc_ehcr.py split --dir ehcr          # GitHub: PDF -> text, har court alag .txt + index.json
    python3 scripts/ukhc_ehcr.py --probe                   # site ka format dikhao (jaanch ke liye)

'fetch' sirf Python ki standard library se; Mac par kuch install nahi karna. 'split' ko pypdfium2 chahiye.
"""
import argparse
import datetime as dt
import html
import http.cookiejar
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://ehcr.uk.gov.in/uk_causelist/"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
KINDS = {"d": "Daily", "s": "Supplementary", "w": "Weekly"}
ROW = re.compile(r"<td[^>]*>\s*(\d+)\s*</td>\s*<td[^>]*>(.*?)<br\s*/?>\s*<strong[^>]*>\s*\(Uploaded Date ([^)]*)\)"
                 r".*?href='([^']+\.pdf)'", re.S | re.I)


def opener():
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    op.addheaders = [("User-Agent", UA), ("Referer", BASE + "view_causelist.php")]
    return op


def get(op, url, binary=False):
    with op.open(url, timeout=90) as r:
        data = r.read()
    return data if binary else data.decode("utf-8", "replace")


def post(op, url, data):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(),
                                 headers={"X-Requested-With": "XMLHttpRequest",
                                          "Content-Type": "application/x-www-form-urlencoded"})
    with op.open(req, timeout=90) as r:
        return r.read().decode("utf-8", "replace")


def dates_on_site(op):
    """Site par jin tareekhon ki list hai (ISO), naye pehle."""
    get(op, BASE + "view_causelist.php")  # session cookie
    resp = post(op, BASE + "includes/cc_functions.php",
                {"upt_rad_val": "upt_rad_val", "rad_val": "a", "sel_dt": "", "se_id": ""})
    return re.findall(r"value=\\?'(\d{4}-\d\d-\d\d)", resp)


def lists_for(op, iso, kind):
    resp = post(op, BASE + "view_causelist_ajax.php", {"rad_val": kind, "cause_date": iso})
    try:
        body = json.loads(resp).get("data", "")
    except ValueError:
        body = resp
    out = []
    for sno, title, uploaded, href in ROW.findall(body):
        out.append({"kind": KINDS[kind], "sno": int(sno), "title": html.unescape(re.sub(r"<[^>]+>", " ", title)).strip(),
                    "uploaded": uploaded.strip(), "url": urllib.parse.urljoin(BASE, href)})
    return out


def today_ist():
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=5, minutes=30)).date()


def fetch(out):
    op = opener()
    days = [d for d in dates_on_site(op) if dt.date.fromisoformat(d) >= today_ist()]
    print("site par aaj/aage ki tareekhein:", days or "koi nahi")
    for iso in days:
        day = dt.date.fromisoformat(iso).strftime("%d-%m-%Y")
        items = [it for kind in KINDS for it in lists_for(op, iso, kind)]
        if not items:
            continue
        folder = out / day
        folder.mkdir(parents=True, exist_ok=True)
        for it in items:
            it["file"] = re.sub(r"[^\w.-]+", "_", Path(urllib.parse.urlparse(it["url"]).path).name)
            (folder / it["file"]).write_bytes(get(op, it["url"], binary=True))
            print(f"  {day} [{it['kind']}] {it['title']} ({it['uploaded']}) -> {it['file']}")
        (folder / "ehcr.json").write_text(json.dumps({"date": day, "items": items}, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    return 0


# ---------- split (GitHub par) ----------
HEAD = re.compile(r"^HIGH COURT OF UTTARAKHAND\s*$")
COURT = re.compile(r"^COURT NUMBER\s+(\d+)\s*$")


def split_courts(text):
    """Poore din ki ek PDF -> har court ka hissa. 'HIGH COURT OF UTTARAKHAND' ... 'COURT NUMBER 03' se naya court."""
    lines = text.split("\n")
    starts = []
    for i, ln in enumerate(lines):
        if HEAD.match(ln.strip()) and any(COURT.match(x.strip()) for x in lines[i + 1:i + 6]):
            num = next(COURT.match(x.strip()).group(1) for x in lines[i + 1:i + 6] if COURT.match(x.strip()))
            if not starts or starts[-1][1] != num:  # agle panne par wahi court dobara shuru na maano
                starts.append((i, num))
    if not starts:
        return [(None, text)]
    return [(num, "\n".join(lines[s:(starts[k + 1][0] if k + 1 < len(starts) else len(lines))]))
            for k, (s, num) in enumerate(starts)]


def pdf_text(path):
    import pypdfium2
    doc = pypdfium2.PdfDocument(str(path))
    try:
        return [doc[i].get_textpage().get_text_range() for i in range(len(doc))]
    finally:
        doc.close()


def split(folder):
    """<dir>/<DD-MM-YYYY>/ehcr.json + PDFs -> wahi folder mein court-wise .txt + index.json (daily-court jaisa)."""
    for day_dir in sorted(p for p in folder.iterdir() if (p / "ehcr.json").exists()):
        meta = json.loads((day_dir / "ehcr.json").read_text(encoding="utf-8"))
        benches = []
        for it in meta["items"]:
            pages = pdf_text(day_dir / it["file"])
            text = "\n".join(p.replace("\r\n", "\n") for p in pages)
            parts = split_courts(text)
            stem = Path(it["file"]).stem
            for k, (num, part) in enumerate(parts, 1):
                name = f"ehcr-{stem}-{k:02d}" + (f"-court-{num}" if num else "")
                (day_dir / f"{name}.txt").write_text(part, encoding="utf-8")
                benches.append({"kind": it["kind"], "bench": f"Court {num}" if num else it["title"],
                                "type": it["title"], "file": f"{name}.pdf", "source_pdf": it["file"],
                                "uploaded": it["uploaded"], "chars": len(part)})
            print(f"{meta['date']}: {it['title']} — {len(pages)} panne, {len(parts)} court")
            if len(parts) == 1:
                print("   (court alag nahi hue; shuru ka hissa:)\n   " + text[:600].replace("\n", " | "))
        index = {"date": meta["date"], "fetched": today_ist().strftime("%d-%m-%Y"), "source": "ehcr",
                 "uploads": sorted(f"{it['title']}|{it['uploaded']}" for it in meta["items"]), "benches": benches}
        (day_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


def probe():
    op = opener()
    days = dates_on_site(op)
    print("== tareekhein", days)
    for iso in days[:2]:
        for kind in KINDS:
            for it in lists_for(op, iso, kind):
                print(iso, it)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", nargs="?", choices=["fetch", "split"])
    ap.add_argument("--out", type=Path, default=Path("ehcr"))
    ap.add_argument("--dir", type=Path, default=Path("ehcr"))
    ap.add_argument("--probe", action="store_true")
    args = ap.parse_args()
    if args.probe:
        return probe()
    if args.cmd == "fetch":
        return fetch(args.out)
    if args.cmd == "split":
        return split(args.dir)
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
