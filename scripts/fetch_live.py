#!/usr/bin/env python3
"""Court websites se seedhe naye judgments/orders laana — AWS/Kaggle ka intezaar nahi.

Python 3.11+ chahiye (bharat-courts). Ek baar: sh scripts/setup_live.sh
Phir (Mac par, .venv-live wale Python se):

    .venv-live/bin/python scripts/fetch_live.py --data ~/krishivlaw-data sc-latest
    .venv-live/bin/python scripts/fetch_live.py --data ~/krishivlaw-data uk-types
    .venv-live/bin/python scripts/fetch_live.py --data ~/krishivlaw-data uk-case WPSS/1304/2024 WPSB/12/2025
    .venv-live/bin/python scripts/fetch_live.py --data ~/krishivlaw-data uk-search "compassionate appointment" --max 300
    .venv-live/bin/python scripts/fetch_live.py --data ~/krishivlaw-data uk-gap --types WPSS --years 2026 --list-only

- sc-latest : sci.gov.in ke "Latest Judgements / Orders" (aakhri 50; roz chalao to kuch nahi chhootega)
- uk-types  : Nainital HC ke case type codes (WPSS, WPSB, SPA...) dikhao
- uk-case   : case number se us case ke orders/judgment (hcservices.ecourts.gov.in)
- uk-search : judgments.ecourts.gov.in par shabd se Uttarakhand HC judgments (pura search, pages ke saath)
- uk-gap    : Nainital HC ke SAARE disposed cases (case type + saal) aur unke saare orders
- uk-probe  : uk-gap ka form court ke page se pakka karo (scripts/ukhc_live.py dekho)

Har PDF ke saath ek JSON sidecar <data>/live/... mein banta hai. Database mein
daalne ke liye: python3 scripts/build_db.py --data ~/krishivlaw-data --live
Jo file pehle se hai use dobara download nahi karte, isliye beech mein rukne
par dobara chalana safe hai. Captcha bharat-courts ka OCR (ddddocr, model saath aata hai) khud padhta hai.
"""
import argparse
import asyncio
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode

import httpx
import ukhc_live
from bharat_courts.judgments import endpoints as judg_endpoints
from bharat_courts.judgments.client import JudgmentSearchClient
from bharat_courts.sci.client import SCIClient
from live_common import iso, safe, save

UK = ukhc_live.UK


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
    commands = ukhc_live.add_commands(sub)
    p = sub.add_parser("uk-search")
    p.add_argument("text")
    p.add_argument("--opt", default="PHRASE", choices=["PHRASE", "ALL", "ANY"])
    p.add_argument("--from-date", help="DD-MM-YYYY (experimental)")
    p.add_argument("--to-date", help="DD-MM-YYYY (experimental)")
    p.add_argument("--max", type=int, default=0, help="itne results ke baad ruko (0 = sab)")
    args = ap.parse_args()
    out = args.data.expanduser() / "live"
    run = dict(commands, **{"sc-latest": sc_latest, "uk-search": uk_search})[args.cmd]
    try:
        return asyncio.run(run(out, args))
    except httpx.HTTPError as err:
        print(f"Court ki site se jud nahi paya ({type(err).__name__}: {err}). Internet/site check karke dobara chalao.")
        return 2


if __name__ == "__main__":
    sys.exit(main())
