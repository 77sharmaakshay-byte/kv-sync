"""fetch_live.py aur ukhc_live.py ke saanjhe chhote kaam: PDF + JSON sidecar save karna."""
import datetime as dt
import hashlib
import json
import re


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
