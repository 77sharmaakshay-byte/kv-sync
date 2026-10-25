#!/usr/bin/env python3
"""Apna model, padhai: faisle shuru se ant tak, bade bench se chhote bench tak (Kaggle training ka ek daur).

    python3 scripts/build_padhai.py --db krishivlaw.db --court SC --out padhai-sc/

Har faisla ~3500 akshar ke tukdon mein (paragraph par toota), kram se; har tukde ke upar faisle ki pehchaan
([Supreme Court | 7 judge | 1973 | ... | bhaag 3/40]). Model har agla shabd andaaze se sikhta hai — koi jawab
(target) nahi chahiye, isliye saare faisle chal jaate hain.
Kram: SC mein 7+ judge, phir 5-6, 3-4, 2, 1; Nainital HC mein Division Bench, phir Single Bench. Har bench ke andar
naye faisle pehle. v1 ke 1000 jaanch wale headnote faisle yahan nahi padhaye jaate (jaanch imaandaar rahe);
test.jsonl.gz mein wahi 1000 (har daur mein headnote ka score, model bhoola to dikhe).
Nikalta hai: padhai-00001.jsonl.gz ... (har ek mein SHARD tukde), eval.jsonl.gz (na padhe faislon ke 200 tukde),
test.jsonl.gz, index.json (kaunsa bench kis tukde se shuru, ginti).
"""
import argparse
import gzip
import json
import random
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_train_data import v1  # noqa: E402

CHUNK = 3500   # akshar (~1000 token): T4 par poore tukde par loss, OOM nahi
SHARD = 20000
COURT = {"SC": "Supreme Court", "UKHC": "Nainital High Court"}


def bench(n_bench, judges):
    if n_bench:
        return int(n_bench)
    try:
        return max(1, len(json.loads(judges or "[]")))
    except ValueError:
        return 1


def stage(court, n):
    if court == "SC":
        return "7+ judge" if n >= 7 else "5-6 judge" if n >= 5 else "3-4 judge" if n >= 3 else (
            "2 judge" if n == 2 else "1 judge")
    return "Division Bench" if n >= 2 else "Single Bench"


ORDER = {"SC": ["7+ judge", "5-6 judge", "3-4 judge", "2 judge", "1 judge"],
         "UKHC": ["Division Bench", "Single Bench"]}


def chunks(text):
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n(?=\d{1,3}\.\s)", text) if p.strip()]
    out, cur = [], ""
    for p in paras:
        while len(p) > CHUNK:            # bahut lamba paragraph: shabd par todo
            cut = p.rfind(" ", 0, CHUNK)
            cut = cut if cut > CHUNK // 2 else CHUNK
            if cur:
                out.append(cur)
                cur = ""
            out.append(p[:cut])
            p = p[cut:].strip()
        if cur and len(cur) + len(p) + 2 > CHUNK:
            out.append(cur)
            cur = p
        else:
            cur = f"{cur}\n\n{p}" if cur else p
    if cur:
        out.append(cur)
    return [c for c in out if len(c) >= 200]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True, type=Path)
    ap.add_argument("--court", required=True, choices=["SC", "UKHC"])
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--eval", type=int, default=200)
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--v1", type=Path, help="v1 data ka folder (train-data branch: train/test.jsonl.gz)")
    ap.add_argument("--v1-test", type=int, default=1000, help="v1 ke jaanch wale headnote faisle (badlo mat)")
    args = ap.parse_args()
    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    rng = random.Random(args.seed)
    _, test_hn = v1(con, args.v1, args.v1_test)
    skip = {p["key"] for p in test_hn}

    meta = []
    for jid, key, title, case_no, year, date, nb, judges, rep in con.execute(
            "SELECT j.id, j.source_key, j.title, j.case_no, j.year, j.decision_date, j.bench_size, j.judges, "
            "j.reportable FROM judgments j JOIN texts t ON t.judgment_id = j.id WHERE j.court = ? "
            "AND length(t.clean) >= 1500", (args.court,)):
        if key in skip:
            continue
        st = stage(args.court, bench(nb, judges))
        meta.append((ORDER[args.court].index(st), -(year or 0), date or "", rep != "reportable", jid, key,
                     title or case_no, year, st))
    meta.sort()
    held = set(rng.sample(range(len(meta)), min(len(meta) // 50, args.eval)))  # jaanch ke faisle: padhaye nahi

    args.out.mkdir(parents=True, exist_ok=True)
    index = {"kind": "padhai", "court": args.court, "chunk_chars": CHUNK, "shard": SHARD, "stages": [],
             "judgments": 0, "chunks": 0, "chars": 0}
    buf, shard_no, n, evals = [], 0, 0, []

    def flush():
        nonlocal buf, shard_no
        if buf:
            shard_no += 1
            with gzip.open(args.out / f"padhai-{shard_no:05d}.jsonl.gz", "wt", encoding="utf-8") as f:
                f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in buf)
            buf = []

    cur_stage = None
    for i, (_, _, _, _, jid, key, title, year, st) in enumerate(meta):
        clean, start = con.execute("SELECT clean, body_start FROM texts WHERE judgment_id = ?", (jid,)).fetchone()
        text = re.sub(r"[ \t]+", " ", clean).strip()
        parts = chunks(text)
        if not parts:
            continue
        name = re.sub(r"\s+", " ", title or "")[:120]
        head = f"[{COURT[args.court]} | {st} | {year or ''} | {name}"
        rows = [{"key": key, "stage": st, "text": f"{head} | bhaag {k + 1}/{len(parts)}]\n{p}"}
                for k, p in enumerate(parts)]
        if i in held:
            evals.append(rng.choice(rows))
            continue
        if st != cur_stage:
            index["stages"].append({"stage": st, "from": n, "judgments": 0, "chunks": 0, "chars": 0})
            cur_stage = st
        s = index["stages"][-1]
        s["judgments"] += 1
        s["chunks"] += len(rows)
        s["chars"] += sum(len(r["text"]) for r in rows)
        for r in rows:
            buf.append(r)
            n += 1
            if len(buf) >= SHARD:
                flush()
    flush()
    index.update(judgments=sum(s["judgments"] for s in index["stages"]), chunks=n,
                 chars=sum(s["chars"] for s in index["stages"]), shards=shard_no, eval=len(evals),
                 approx_tokens=sum(s["chars"] for s in index["stages"]) // 4)
    with gzip.open(args.out / "eval.jsonl.gz", "wt", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in evals)
    with gzip.open(args.out / "test.jsonl.gz", "wt", encoding="utf-8") as f:
        f.writelines(json.dumps(dict(p, task="headnote"), ensure_ascii=False) + "\n" for p in test_hn)
    (args.out / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(index, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
