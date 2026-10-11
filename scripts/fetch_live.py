#!/usr/bin/env python3
"""Court websites se seedhe naye judgments/orders laana — AWS/Kaggle ka intezaar nahi.

Python 3.11+ chahiye (bharat-courts). Ek baar: sh scripts/setup_live.sh
Phir (Mac par, .venv-live wale Python se):

    .venv-live/bin/python scripts/fetch_live.py --data ~/krishivlaw-data sc-latest
    .venv-live/bin/python scripts/fetch_live.py --data ~/krishivlaw-data uk-types
    .venv-live/bin/python scripts/fetch_live.py --data ~/krishivlaw-data uk-case WPSS/1304/2024 WPSB/12/2025
    .venv-live/bin/python scripts/fetch_live.py --data ~/krishivlaw-data uk-search "compassionate appointment" --max 300

- sc-latest : sci.gov.in ke "Latest Judgements / Orders" (aakhri 50; roz chalao to kuch nahi chhootega)
- uk-types  : Nainital HC ke case type codes (WPSS, WPSB, SPA...) dikhao
- uk-case   : case number se us case ke orders/judgment (hcservices.ecourts.gov.in)
- uk-search : judgments.ecourts.gov.in par shabd se Uttarakhand HC judgments (pura search, pages ke saath)

Har PDF ke saath ek JSON sidecar <data>/live/... mein banta hai. Database mein
daalne ke liye: python3 scripts/build_db.py --data ~/krishivlaw-data --live
Jo file pehle se hai use dobara download nahi karte, isliye beech mein rukne
par dobara chalana safe hai. Captcha bharat-courts ka OCR (ddddocr, model saath aata hai) khud padhta hai.
"""
import argparse
import asyncio
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode

import httpx
from bharat_courts.courts import get_court
from bharat_courts.hcservices.client import HCServicesClient
from bharat_courts.judgments import endpoints as judg_endpoints
from bharat_courts.judgments.client import JudgmentSearchClient
from bharat_courts.sci.client import SCIClient

UK = get_court("uttarakhand")
CASE_RE = re.compile(r"^([A-Za-z0-9.()^]+)[/ -](\d+)[/ -](\d{4})$")


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def iso(d):
    return d.isoformat() if d else None


def save(path, pdf, side):
    """PDF + JSON sidecar. Pehle JSON .tmp mein, taaki adhoori file kabhi 'poori' na lage."""
    path.parent.mkdir(parents=True, exist_ok=True)
    side = dict(side, sha256=hashlib.sha256(pdf).hexdigest(), fetched_at=now(), fetched_by="fetch_live.py")
    path.with_suffix(".pdf").write_bytes(pdf)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(side, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path.with_suffix(".json"))


def safe(s):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s or "").strip("_") or "x"


async def sc_latest(out, args):
    new = old = bad = 0
    async with SCIClient() as client:
        items = await client.list_recent_judgments(limit=args.limit)
        print(f"sci.gov.in: {len(items)} latest judgments/orders")
        for j in items:
            kind = (j.metadata or {}).get("type") or "x"
            key = f"{j.source_id}-{iso(j.judgment_date) or 'nodate'}-{kind}"
            path = out / "sc" / safe(key)
            if path.with_suffix(".json").exists():
                old += 1
                continue
            try:
                await client.download_pdf(j)
            except Exception as err:  # noqa: BLE001 — ek file ki galti se baaki na rukein
                bad += 1
                print(f"  [error] {j.case_number} {j.title[:60]}: {err}")
                continue
            save(path, j.pdf_bytes, {
                "court": "SC", "source": "sc-live", "source_key": "sci-live:" + key,
                "title": j.title, "petitioner": (j.metadata or {}).get("petitioner"),
                "respondent": (j.metadata or {}).get("respondent"), "case_no": j.case_number,
                "decision_date": iso(j.judgment_date), "doc_kind": {"j": "judgment", "o": "order"}.get(kind),
                "diary_no": j.source_id, "pdf_url": j.pdf_url, "source_url": j.source_url})
            new += 1
            print(f"  [new] {iso(j.judgment_date)} {j.case_number} {j.title[:70]}")
    print(f"SC: {new} naye, {old} pehle se, {bad} errors")
    return 1 if bad else 0


def _label(name):
    return re.sub(r"[^A-Z]", "", re.split(r"[(\-]", name)[0].upper())


def _match_type(types, label):
    """'WPSS' (ya seedha code '12') -> [codes]. Portal ke naam 'WPSS(...)' / 'WPSS - ...' jaise hote hain."""
    if label in types:
        return [label]
    want = re.sub(r"[^A-Z]", "", label.upper())
    return [code for code, name in types.items() if _label(name) == want]


async def uk_types(out, args):
    async with HCServicesClient() as client:
        types = await client.list_case_types(UK, bench_code=args.bench)
    for code, name in sorted(types.items(), key=lambda x: x[1]):
        print(f"  {code:10s} {name}")
    print(f"{len(types)} case types")
    return 0


async def uk_case(out, args):
    bad = 0
    async with HCServicesClient() as client:
        types = await client.list_case_types(UK, bench_code=args.bench)
        for spec in args.cases:
            m = CASE_RE.match(spec.strip())
            codes = _match_type(types, m.group(1)) if m else []
            if len(codes) != 1:
                bad += 1
                hint = ", ".join(f"{c}={types[c]}" for c in codes) or "uk-types se dekho"
                print(f"[samjha nahi] {spec} — likho jaise WPSS/1304/2024; type ke liye code bhi chalega ({hint})")
                continue
            code, no, year = codes[0], m.group(2), m.group(3)
            ctype = _label(types[code]) or code
            try:
                infos = await client.case_status(UK, case_type=code, case_number=no, year=year,
                                                 bench_code=args.bench)
                orders = await client.court_orders(UK, case_type=code, case_number=no, year=year,
                                                   bench_code=args.bench)
            except Exception as err:  # noqa: BLE001
                bad += 1
                print(f"[error] {spec}: {err}")
                continue
            info = infos[0] if infos else None
            print(f"{spec}: {info.status if info else 'status nahi mila'} · "
                  f"{info.petitioner if info else ''} v. {info.respondent if info else ''} · {len(orders)} order PDF")
            folder = out / "uk" / f"{ctype}-{no}-{year}"
            for n, order in enumerate(orders, 1):
                try:
                    pdf = await client.download_order_pdf(order.pdf_url)
                except Exception as err:  # noqa: BLE001
                    bad += 1
                    print(f"  [error] order {n}: {err}")
                    continue
                sha = hashlib.sha256(pdf).hexdigest()
                path = folder / sha[:16]
                if path.with_suffix(".json").exists():
                    continue
                # JSON wale jawab mein order ki tarikh nahi aati (library aaj ki tarikh bhar deti hai) —
                # galat tarikh se behtar hai khaali; text se baad mein nikalegi.
                odate = iso(order.order_date) if order.order_date != dt.date.today() else None
                save(path, pdf, {
                    "court": "UKHC", "source": "uk-live", "source_key": f"ukhc-live:{ctype}/{no}/{year}:{sha[:16]}",
                    "title": f"{info.petitioner} versus {info.respondent}" if info else None,
                    "petitioner": info.petitioner if info else None, "respondent": info.respondent if info else None,
                    "case_no": f"{ctype}/{no}/{year}", "case_type": ctype, "decision_date": odate,
                    "cnr": info.cnr_number if info else None, "doc_kind": "order", "order_type": order.order_type,
                    "judges": [order.judge] if order.judge else (info.judges if info else None),
                    "case_status": info.status if info else None, "pdf_url": order.pdf_url})
                print(f"  [new] {path.with_suffix('.pdf').name}")
    return 1 if bad else 0


def _with_filters(build, extra):
    """bharat-courts ka search form + hamare filters (court, tarikh). Library ko chhue bina."""
    def wrapped(**kw):
        pairs = [(k, extra.get(k, v)) for k, v in parse_qsl(build(**kw), keep_blank_values=True)]
        return urlencode(pairs)
    return wrapped


async def uk_search(out, args):
    extra = {"state_code": UK.judgment_compound_code}  # TODO: portal par confirm karna (experimental)
    if args.from_date:
        extra["from_date"] = args.from_date
    if args.to_date:
        extra["to_date"] = args.to_date
    judg_endpoints.search_results_form = _with_filters(judg_endpoints.search_results_form, extra)
    new = old = other = bad = seen = 0
    async with JudgmentSearchClient() as client:
        async for page in client.search_all(args.text, page_size=50, search_opt=args.opt, court_type="2"):
            for j in page.items:
                seen += 1
                if "uttarakhand" not in (j.court_name or "").lower():
                    other += 1
                    continue
                key = safe(f"{j.case_number}-{iso(j.judgment_date) or 'nodate'}")
                path = out / "uk" / "search" / key
                if path.with_suffix(".json").exists():
                    old += 1
                    continue
                try:
                    await client.download_pdf(j, court_type="2")
                except Exception as err:  # noqa: BLE001
                    bad += 1
                    print(f"  [error] {j.case_number}: {err}")
                    continue
                save(path, j.pdf_bytes, {
                    "court": "UKHC", "source": "uk-live", "source_key": "ecourts-judg:" + key,
                    "title": j.title, "case_no": j.case_number, "decision_date": iso(j.judgment_date),
                    "judges": j.judges or None, "neutral_citation": j.citation or None, "doc_kind": "judgment",
                    "source_url": j.source_url})
                new += 1
                print(f"  [new] {iso(j.judgment_date)} {j.case_number} {j.title[:70]}")
            if args.max and seen >= args.max:
                break
    print(f"UK search: {seen} results dekhe, {new} naye, {old} pehle se, {other} doosre courts ke, {bad} errors")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", required=True, type=Path)
    ap.add_argument("--bench", default="1", help="Nainital HC bench code (default 1)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("sc-latest")
    p.add_argument("--limit", type=int, default=50)
    sub.add_parser("uk-types")
    p = sub.add_parser("uk-case")
    p.add_argument("cases", nargs="+", help="jaise WPSS/1304/2024")
    p = sub.add_parser("uk-search")
    p.add_argument("text")
    p.add_argument("--opt", default="PHRASE", choices=["PHRASE", "ALL", "ANY"])
    p.add_argument("--from-date", help="DD-MM-YYYY (experimental)")
    p.add_argument("--to-date", help="DD-MM-YYYY (experimental)")
    p.add_argument("--max", type=int, default=0, help="itne results ke baad ruko (0 = sab)")
    args = ap.parse_args()
    out = args.data.expanduser() / "live"
    run = {"sc-latest": sc_latest, "uk-types": uk_types, "uk-case": uk_case, "uk-search": uk_search}[args.cmd]
    try:
        return asyncio.run(run(out, args))
    except httpx.HTTPError as err:
        print(f"Court ki site se jud nahi paya ({type(err).__name__}: {err}). Internet/site check karke dobara chalao.")
        return 2


if __name__ == "__main__":
    sys.exit(main())
