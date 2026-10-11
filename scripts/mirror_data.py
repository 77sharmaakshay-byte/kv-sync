#!/usr/bin/env python3
"""AWS Open Data se SC aur Uttarakhand HC judgments ki apni copy.

Sirf Python standard library — Mac par bina kuch install kiye chalta hai.

- Pehle plan dikhata hai (kitni files, kitne GB). 5 GB se zyada ho to
  --yes ke bina download shuru nahi karta.
- Dobara chalao to sirf nayi ya badli files aati hain.
- Har file ki jaanch: size, MD5 (jahan S3 deta hai), SHA-256 apne record ke
  liye, aur tar ke andar ki files ki ginti index.json se.
- Upstream se koi file hat jaye to apni copy kabhi delete nahi hoti;
  manifest mein "upstream_missing" likh diya jata hai.

Usage:
    python3 scripts/mirror_data.py --dest /Volumes/Data/nyay-mirror
    python3 scripts/mirror_data.py --dest ... --yes
    python3 scripts/mirror_data.py --dest ... --groups sc-meta-parquet --yes
"""
import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import tarfile
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "upstreams.json"
DEFAULT_GROUPS = ["sc-english", "sc-meta-parquet", "sc-meta-raw",
                  "uk-hc-pdf", "uk-hc-meta-parquet", "uk-hc-meta-raw"]
ASK_ABOVE_BYTES = 5 * 1024 ** 3
CHUNK = 4 * 1024 * 1024


def list_objects(bucket, prefix):
    """Public S3 bucket ki listing (ListObjectsV2, bina AWS account ke)."""
    out, token = [], None
    while True:
        q = {"list-type": "2", "prefix": prefix}
        if token:
            q["continuation-token"] = token
        url = f"https://{bucket}.s3.amazonaws.com/?" + urllib.parse.urlencode(q)
        with urllib.request.urlopen(url, timeout=60) as r:
            xml = r.read().decode()
        for block in re.findall(r"<Contents>(.*?)</Contents>", xml, re.S):
            key = re.search(r"<Key>(.*?)</Key>", block).group(1)
            size = int(re.search(r"<Size>(\d+)</Size>", block).group(1))
            etag = re.search(r"<ETag>(.*?)</ETag>", block).group(1).replace("&quot;", "").strip('"')
            out.append({"key": key, "size": size, "etag": etag})
        m = re.search(r"<NextContinuationToken>(.*?)</NextContinuationToken>", xml)
        if not m:
            return out
        token = m.group(1)


def plan_group(cfg, group):
    """Ek group: (bucket, objects, scopes). scopes = [(prefix, contains)]."""
    for ds in cfg["datasets"].values():
        g = ds["groups"].get(group)
        if not g:
            continue
        prefixes = [g["prefix"]]
        if "{year}" in g["prefix"]:
            first = ds["years"][0]
            last = max(ds["years"][1], dt.date.today().year)
            prefixes = [g["prefix"].format(year=y, court=ds["court"]) for y in range(first, last + 1)]
        contains = g.get("contains", "")
        objs = []
        for p in prefixes:
            objs += [o for o in list_objects(ds["bucket"], p) if contains in o["key"]]
        return ds["bucket"], objs, [(p, contains) for p in prefixes]
    raise SystemExit(f"Group nahi mila: {group}")


def in_scope(rel, scopes):
    bucket, _, key = rel.partition("/")
    return any(b == bucket and key.startswith(p) and c in key for b, p, c in scopes)


def download(bucket, obj, dest):
    """Resume ke saath download. (md5, sha256) lautata hai."""
    part = dest.with_name(dest.name + ".part")
    dest.parent.mkdir(parents=True, exist_ok=True)
    have = part.stat().st_size if part.exists() else 0
    if have > obj["size"]:
        part.unlink()
        have = 0
    md5, sha = hashlib.md5(), hashlib.sha256()
    if have:
        with open(part, "rb") as f:
            for chunk in iter(lambda: f.read(CHUNK), b""):
                md5.update(chunk)
                sha.update(chunk)
    url = f"https://{bucket}.s3.amazonaws.com/{urllib.parse.quote(obj['key'])}"
    req = urllib.request.Request(url, headers={"Range": f"bytes={have}-"} if have else {})
    if have < obj["size"]:
        with urllib.request.urlopen(req, timeout=120) as r, open(part, "ab") as f:
            if have and r.status != 206:
                raise IOError("server ne resume mana kiya; .part file hata kar dobara chalao")
            for chunk in iter(lambda: r.read(CHUNK), b""):
                f.write(chunk)
                md5.update(chunk)
                sha.update(chunk)
    if part.stat().st_size != obj["size"]:
        raise IOError(f"size galat: {part.stat().st_size} != {obj['size']}")
    if "-" not in obj["etag"] and md5.hexdigest() != obj["etag"]:
        part.unlink()
        raise IOError("MD5 match nahi hua, file hata di — dobara chalao")
    part.replace(dest)
    return sha.hexdigest()


def tar_count_ok(tar_path):
    """Tar ke andar ki files ki ginti, saath wali index.json se milao."""
    idx = next(iter(sorted(tar_path.parent.glob("*.index.json"))), None)
    if idx is None:
        return None
    parts = json.loads(idx.read_text(encoding="utf-8")).get("parts", [])
    want = next((p.get("file_count") for p in parts if p.get("name") == tar_path.name), None)
    if want is None:
        return None
    with tarfile.open(tar_path) as t:
        got = sum(1 for m in t if m.isfile())
    return got == want


def human(n):
    return f"{n / 1024 ** 3:.2f} GB"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dest", required=True, type=Path, help="data kahan rakhna hai")
    ap.add_argument("--groups", default=",".join(DEFAULT_GROUPS),
                    help="comma se alag; sc-regional (51 GB) default mein nahi hai")
    ap.add_argument("--yes", action="store_true", help="5 GB se bade download ki manzoori")
    args = ap.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    manifest_path = args.dest / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}

    todo, seen, scopes, total = [], set(), [], 0
    for group in [g.strip() for g in args.groups.split(",") if g.strip()]:
        bucket, objs, group_scopes = plan_group(cfg, group)
        scopes += [(bucket, p, c) for p, c in group_scopes]
        new = [o for o in objs
               if manifest.get(f"{bucket}/{o['key']}", {}).get("etag") != o["etag"]
               or not (args.dest / bucket / o["key"]).exists()]
        size = sum(o["size"] for o in new)
        total += size
        seen.update(f"{bucket}/{o['key']}" for o in objs)
        print(f"{group:20s} {len(objs):6d} files upstream, {len(new):6d} naye/badle, {human(size)}")
        todo += [(bucket, o) for o in new]

    print(f"{'KUL':20s} {len(todo):6d} files, {human(total)}")
    if total > ASK_ABOVE_BYTES and not args.yes:
        print("5 GB se zyada hai. Manzoori ho to --yes ke saath dobara chalao.")
        return 2

    failed = 0
    for i, (bucket, obj) in enumerate(sorted(todo, key=lambda t: not t[1]["key"].endswith(".json")), 1):
        rel = f"{bucket}/{obj['key']}"
        dest = args.dest / bucket / obj["key"]
        print(f"[{i}/{len(todo)}] {rel} ({human(obj['size'])})", flush=True)
        try:
            sha = download(bucket, obj, dest)
        except (OSError, IOError) as err:
            failed += 1
            print(f"   FAIL: {err}")
            continue
        entry = {"size": obj["size"], "etag": obj["etag"], "sha256": sha,
                 "md5_checked": "-" not in obj["etag"],
                 "downloaded_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        if dest.suffix == ".tar":
            try:
                entry["tar_count_ok"] = tar_count_ok(dest)
            except (tarfile.TarError, OSError, ValueError) as err:
                entry["tar_count_ok"] = False
                print(f"   tar padh nahi paya: {err}")
            if entry["tar_count_ok"] is False:
                failed += 1
                print("   WARN: tar ki ginti index.json se match nahi hui")
        manifest[rel] = entry
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")

    gone = [k for k in manifest
            if k not in seen and in_scope(k, scopes) and not manifest[k].get("upstream_missing")]
    for k in gone:
        manifest[k]["upstream_missing"] = dt.date.today().isoformat()
        print(f"[upstream se hata] {k} — apni copy rakhi hai")
    if manifest:
        manifest_path.write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    print("Ho gaya." if not failed else f"{failed} file(s) mein dikkat — dobara chalao, wahi se resume hoga.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
