#!/usr/bin/env python3
"""OpenNyAI ke AI model files ki apni copy (HuggingFace se).

opennyai library ye files chalte waqt HuggingFace se utharti hai. Agar wo
link band ho jaye to apni copy se install kar sakte hain. Har file ka
SHA-256 dest/models/models.json mein likha jata hai.

Usage:
    python3 scripts/mirror_models.py --dest /Volumes/Data/nyay-mirror
"""
import argparse
import datetime as dt
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "upstreams.json"
CHUNK = 4 * 1024 * 1024


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dest", required=True, type=Path)
    args = ap.parse_args()

    out_dir = args.dest / "models"
    out_dir.mkdir(parents=True, exist_ok=True)
    record_path = out_dir / "models.json"
    record = json.loads(record_path.read_text(encoding="utf-8")) if record_path.exists() else {}
    failed = 0

    for model in json.loads(CONFIG.read_text(encoding="utf-8"))["models"]:
        dest = out_dir / model["name"]
        if dest.exists() and record.get(model["name"], {}).get("size") == dest.stat().st_size:
            print(f"[same] {model['name']}")
            continue
        part = dest.with_name(dest.name + ".part")
        sha = hashlib.sha256()
        try:
            with urllib.request.urlopen(model["url"], timeout=120) as r, open(part, "wb") as f:
                for chunk in iter(lambda: r.read(CHUNK), b""):
                    f.write(chunk)
                    sha.update(chunk)
        except OSError as err:
            failed += 1
            print(f"[fail] {model['name']}: {err} — purani copy (agar hai) rakhi hai")
            continue
        part.replace(dest)
        record[model["name"]] = {
            "url": model["url"], "size": dest.stat().st_size, "sha256": sha.hexdigest(),
            "downloaded_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        }
        print(f"[copied] {model['name']} ({dest.stat().st_size / 1024 ** 2:.0f} MB)")
        record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
