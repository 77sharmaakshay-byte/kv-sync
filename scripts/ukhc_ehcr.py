#!/usr/bin/env python3
"""Nainital HC ki apni cause list site (ehcr.uk.gov.in) — sirf India se khulti hai (Mac runner).

    python3 scripts/ukhc_ehcr.py --probe          # page, uski JS aur pehla jawab dikhao (format samajhne ke liye)

Sirf Python ki standard library; Mac par kuch install nahi karna.
"""
import argparse
import http.cookiejar
import re
import sys
import urllib.parse
import urllib.request

BASE = "https://ehcr.uk.gov.in/uk_causelist/"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"


def opener():
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    op.addheaders = [("User-Agent", UA), ("Referer", BASE + "view_causelist.php")]
    return op


def get(op, url):
    with op.open(url, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def post(op, url, data):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, headers={"X-Requested-With": "XMLHttpRequest",
                                                         "Content-Type": "application/x-www-form-urlencoded"})
    with op.open(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def probe():
    op = opener()
    page = get(op, BASE + "view_causelist.php")
    print("== page", len(page))
    for src in re.findall(r'<script[^>]+src="([^"]+)"', page):
        url = urllib.parse.urljoin(BASE, src)
        print("== script", url)
        if re.search(r"jquery|bootstrap|popper|select2|vendor", src, re.I):
            continue
        js = get(op, url)
        for m in re.finditer(r"search_btn|\.ajax|url\s*:|data\s*:|window\.open|\.pdf", js):
            print("   ...", js[max(0, m.start() - 300):m.start() + 500].replace("\n", " ")[:800])
    dt = (re.search(r"var dt='([\d-]+)'", page) or [None, ""])[1]
    print("== default date", dt)
    for rad in ("a", "d"):
        resp = post(op, BASE + "includes/cc_functions.php",
                    {"upt_rad_val": "upt_rad_val", "rad_val": rad, "sel_dt": dt, "se_id": ""})
        print(f"== cc_functions rad_val={rad}", len(resp))
        print(resp[:6000])
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--probe", action="store_true")
    args = ap.parse_args()
    if args.probe:
        return probe()
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
