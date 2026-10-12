"""Nainital High Court (hcservices.ecourts.gov.in) — fetch_live.py ke uk-* commands.

- uk-types : case type codes
- uk-case  : case number se us case ke saare orders
- uk-gap   : case type + registration saal ke SAARE disposed cases ki list court se,
             phir har case ke saare orders. Lambe samay tak chalne ke liye:
             list aur har poora hua case yaad rehta hai (<data>/live/uk/_gap, <case>/_done),
             to rukne par dobara chalao — wahin se aage.
- uk-probe : court ke page ka JavaScript padh kar 'Case Type' search ke form fields dikhao
             (uk-gap ka form bharat-courts mein nahi hai, isliye pehle isse pakka karte hain)
"""
import asyncio
import json
import re
import sqlite3

from bharat_courts.courts import get_court
from bharat_courts.hcservices import endpoints as hc_endpoints
from bharat_courts.hcservices.client import HCServicesClient
from bharat_courts.hcservices.parser import ServerError, _case_infos_from_records, _parse_json_envelope
from live_common import iso, save

UK = get_court("uttarakhand")
CASE_RE = re.compile(r"^([A-Za-z0-9.()^]+)[/ -](\d+)[/ -](\d{4})$")
# Portal ke funShowRecords() ka 'Case Type' wala hissa (andaaza; uk-probe se pakka karo, --form se badlo).
GAP_FORM = {"caseStatusSearchType": "CScaseType", "case_type": "{code}", "search_year": "{year}", "f": "Disposed"}


def _label(name):
    return re.sub(r"[^A-Z]", "", re.split(r"[(\-]", name)[0].upper())


def _match_type(types, label):
    """'WPSS' (ya seedha code '12') -> [codes]. Portal ke naam 'WPSS(...)' / 'WPSS - ...' jaise hote hain."""
    if label in types:
        return [label]
    want = re.sub(r"[^A-Z]", "", label.upper())
    return [code for code, name in types.items() if _label(name) == want]


def clean_pdf(content):
    """Nainital HC ka server PDF se pehle UTF-8 BOM (3 bytes) laga deta hai — hata do.
    PDF ke andar ke byte-offsets bina BOM ke hisaab se hote hain, isliye kaatna hi sahi hai."""
    start = content.find(b"%PDF", 0, 1024)
    if start < 0:
        text = content[:200].decode("utf-8", "replace").lstrip("﻿").strip()
        raise RuntimeError(f"PDF nahi mili, server ne kaha: {text!r}")
    return content[start:]


async def order_pdf(client, url):
    """bharat-courts ka download_order_pdf BOM wali PDF ko 'galat' maan leta hai; wahi request, apni jaanch."""
    resp = await client._http.get(url, headers={"Referer": hc_endpoints.MAIN_PAGE_URL,
                                               "Accept": "application/pdf,*/*"})
    return clean_pdf(resp.content)


async def fetch_case(client, out, ctype, no, year, cnr, pet=None, res=None, fallback=None):
    """Ek case: CNR page -> saare orders download. Lautata hai kitne orders fail hue (0 = poora)."""
    detail, orders = None, []
    if cnr:
        # CNR wala poora case page: har order ki tarikh, judge aur apna link.
        try:
            detail = await client.case_status_by_cnr(cnr)
            orders = detail.orders
        except Exception as err:  # noqa: BLE001
            print(f"  [CNR page nahi mila{', doosra raasta' if fallback else ''}] {err}")
            if not fallback:
                return 1
    if not orders and fallback:
        try:
            orders = await fallback()
        except Exception as err:  # noqa: BLE001
            print(f"  [orders nahi mile] {err}")
    pet = (detail.petitioners[0].name if detail and detail.petitioners else None) or pet
    res = (detail.respondents[0].name if detail and detail.respondents else None) or res
    status = (detail.status or detail.case_stage) if detail else "?"
    print(f"{ctype}/{no}/{year}: {pet} v. {res} · CNR {cnr or '?'} · {status}"
          f"{' · faisla ' + iso(detail.decision_date) if detail and detail.decision_date else ''}"
          f" · {len(orders)} order PDF")
    folder = out / "uk" / f"{ctype}-{no}-{year}"
    if detail:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "_case.json").write_text(detail.to_json(indent=1), encoding="utf-8")
    bad = 0
    for n, order in enumerate(orders, 1):
        # Sirf CNR page wali tarikh sahi hai; doosre raaste mein library aaj ki tarikh bhar deti hai.
        odate = iso(order.order_date) if detail else None
        path = folder / (f"{odate}-{n:03d}" if odate else f"order-{n:03d}")
        if path.with_suffix(".json").exists():
            continue
        pdf, err = None, None
        for attempt in range(3):  # 'Unable to connect to server' aksar thodi der ka hota hai
            try:
                pdf = await order_pdf(client, order.pdf_url)
                break
            except Exception as e:  # noqa: BLE001
                err = e
                await asyncio.sleep(5 * (attempt + 1))
        if pdf is None:
            bad += 1
            print(f"  [error] {odate or ''} {order.order_type}: {err}")
            continue
        # Nainital HC 'order on' mein case number likhta hai, isliye aakhri faisla tarikh se pehchano.
        final = bool(detail and detail.decision_date and order.order_date == detail.decision_date)
        kind = "judgment" if final or "judg" in (order.order_type or "").lower() else "order"
        save(path, pdf, {
            "court": "UKHC", "source": "uk-live", "source_key": f"ukhc-live:{ctype}/{no}/{year}:{path.name}",
            "title": f"{pet} versus {res}" if pet or res else None, "petitioner": pet, "respondent": res,
            "case_no": f"{ctype}/{no}/{year}", "case_type": ctype, "decision_date": odate, "cnr": cnr,
            "doc_kind": kind, "order_type": order.order_type, "judges": [order.judge] if order.judge else None,
            "case_status": status, "pdf_url": order.pdf_url})
        print(f"  [new] {odate or ''} {order.judge}")
    return bad


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
            kw = {"case_type": code, "case_number": no, "year": year, "bench_code": args.bench}
            try:
                infos = await client.case_status(UK, **kw)
            except Exception as err:  # noqa: BLE001
                bad += 1
                print(f"[error] {spec}: {err}")
                continue
            info = infos[0] if infos else None
            bad += await fetch_case(client, out, _label(types[code]) or code, no, year,
                                    info.cnr_number if info else None, info and info.petitioner,
                                    info and info.respondent, fallback=lambda: client.court_orders(UK, **kw))
    return 1 if bad else 0


def _years(spec):
    """'2001-2026' / '2024' / '2020,2024' -> [2026, ..., 2001] (naye pehle)."""
    out = set()
    for part in spec.split(","):
        lo, _, hi = part.partition("-")
        out.update(range(int(lo), int(hi or lo) + 1))
    return sorted(out, reverse=True)


async def _gap_list(client, gapdir, code, year, form, bench):
    """Ek case type + saal ke disposed cases (court se ek baar, phir file se)."""
    cache = gapdir / f"{code.replace('^', '_')}-{year}.json"
    if cache.exists():
        saved = json.loads(cache.read_text(encoding="utf-8"))
        if saved.get("form") == form:  # form badla to list dobara lo (galat form ki khaali list na atke)
            return saved["rows"]

    def build(captcha):
        base = {"court_code": bench, "state_code": UK.state_code, "court_complex_code": bench, "captcha": captcha}
        return dict(base, **{k: v.format(code=code, year=year) for k, v in form.items()})

    resp = await client._post_with_captcha_retry(hc_endpoints.SHOW_RECORDS_URL, build)
    records, total, _ = _parse_json_envelope(resp.text)
    infos = _case_infos_from_records(records, total)
    if total > len(infos):
        print(f"  [chetavni] court ne {total} bataye par {len(infos)} bheje — list pages mein ho sakti hai")
    rows = [{"cnr": c.cnr_number, "no": c.registration_number or c.case_number.split("/")[0],
             "year": (c.case_number.split("/") + [str(year)])[1], "pet": c.petitioner, "res": c.respondent}
            for c in infos if c.cnr_number]
    gapdir.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"form": form, "total": total, "rows": rows}, ensure_ascii=False), encoding="utf-8")
    return rows


def _known_cnrs(db_path):
    """Database (AWS + pehle laaye) mein jin Nainital HC cases ka faisla pehle se hai, unke CNR."""
    if not db_path.exists():
        raise SystemExit(f"Database nahi mila: {db_path} — pehle build_db.py chalao")
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return {r[0] for r in con.execute("SELECT DISTINCT cnr FROM judgments WHERE court = 'UKHC' AND cnr IS NOT NULL")}
    finally:
        con.close()


async def uk_gap(out, args):
    form = dict(GAP_FORM, **json.loads(args.form)) if args.form else GAP_FORM
    gapdir = out / "uk" / "_gap"
    total = done = bad = skipped = 0
    known = _known_cnrs(out.parent / "krishivlaw.db") if args.only_missing else set()
    if args.only_missing:
        print(f"Database mein {len(known)} Nainital HC cases pehle se — sirf baaki wale laayenge")
    async with HCServicesClient() as client:
        types = await client.list_case_types(UK, bench_code=args.bench)
        wanted = [c for t in args.types.split(",") for c in _match_type(types, t.strip())] if args.types else \
            sorted(types, key=lambda c: types[c])
        for code in wanted:
            ctype = _label(types[code]) or code
            for year in _years(args.years):
                try:
                    rows = await _gap_list(client, gapdir, code, year, form, args.bench)
                except ServerError as err:
                    print(f"[list error] {ctype} {year}: {err} — form galat ho sakta hai; uk-probe chala kar output bhejo")
                    return 3
                except Exception as err:  # noqa: BLE001
                    bad += 1
                    print(f"[list error] {ctype} {year}: {err}")
                    continue
                print(f"== {ctype} {year}: {len(rows)} disposed cases")
                total += len(rows)
                if args.list_only:
                    continue
                for r in rows:
                    if r["cnr"] in known:
                        skipped += 1
                        continue
                    marker = out / "uk" / f"{ctype}-{r['no']}-{r['year']}" / "_done"
                    if marker.exists():
                        done += 1
                        continue
                    failed = await fetch_case(client, out, ctype, r["no"], r["year"], r["cnr"], r["pet"], r["res"])
                    if failed:
                        bad += 1
                    else:
                        marker.parent.mkdir(parents=True, exist_ok=True)
                        marker.write_text("ok", encoding="utf-8")
                        done += 1
    print(f"UK gap: {total} disposed cases list mein, {skipped} database mein pehle se (chhode), "
          f"{done} poore, {bad} adhoore (dobara chalao)")
    return 1 if bad else 0


async def uk_probe(out, args):
    """Court ke main page aur uski JS files mein 'Case Type' search ke field dhoondho."""
    async with HCServicesClient() as client:
        page = (await client._http.get(hc_endpoints.MAIN_PAGE_URL)).text
        srcs = re.findall(r'<script[^>]+src="([^"]+)"', page)
        texts = [("main.php", page)]
        for src in srcs:
            if src.startswith("http") and "ecourts.gov.in" not in src:
                continue
            url = src if src.startswith("http") else f"{hc_endpoints.BASE_URL}/{src.lstrip('./')}"
            try:
                texts.append((src, (await client._http.get(url)).text))
            except Exception as err:  # noqa: BLE001
                print(f"[nahi mila] {src}: {err}")
    pat = re.compile(r"caseStatusSearchType|CScaseType|CScasetype|search_year|case_type_qry|rgyear|\bf\s*[:=]", re.I)
    shown = 0
    for name, text in texts:
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if pat.search(line) and shown < 80:
                shown += 1
                print(f"{name}:{i + 1}: {line.strip()[:200]}")
    print(f"{len(texts)} files dekhi, {shown} lines mili")
    return 0


def add_commands(sub):
    sub.add_parser("uk-types")
    p = sub.add_parser("uk-case")
    p.add_argument("cases", nargs="+", help="jaise WPSS/1304/2024")
    p = sub.add_parser("uk-gap")
    p.add_argument("--types", help="jaise WPSS,WPSB (default: saare case types)")
    p.add_argument("--years", default="2001-2026", help="registration saal, jaise 2001-2026 ya 2024")
    p.add_argument("--list-only", action="store_true", help="sirf ginti, download nahi")
    p.add_argument("--only-missing", action="store_true",
                   help="jin cases ka faisla database (AWS) mein pehle se hai unhe chhodo — sirf chhoote hue laao")
    p.add_argument("--form", help='form badalna ho to JSON, jaise {"caseStatusSearchType": "CScaseType"}')
    sub.add_parser("uk-probe")
    return {"uk-types": uk_types, "uk-case": uk_case, "uk-gap": uk_gap, "uk-probe": uk_probe}
