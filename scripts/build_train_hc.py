#!/usr/bin/env python3
"""Apna model, doosra daur (nyay-train-v2): Nainital HC + SC faisle -> shreni, vishay, mudda, nateeja.

    python3 scripts/build_train_hc.py --db krishivlaw.db --out train2/

Jawab (target) database ki chhantai (kl/classify.py) se: shreni HC mein case type se, nateeja court ke disposal
(ya faisle ke aakhri hisse) se, vishay/mudda FTS niyam se (sirf 'mukhya'). Jin faislon ka vishay niyam se nahi
mila, woh yahan nahi — unhe baad mein yahi sikha hua model padhega.
Har upvishay se barabar (ek vishay hi na chha jaaye), andar nateeja bhi baari-baari. Saath mein SC headnote ke
kuch purane jode (pehla daur bhoole nahi); test mein v1 ke wahi 1000 headnote faisle (round dar round tulna).
"""
import argparse
import gzip
import json
import random
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_train_data import v1  # noqa: E402

HEAD_CHARS, TAIL_CHARS = 6000, 3000   # shuru (paksh, tathya, mudda) + ant (aadesh / nateeja)
IN_TOK = 1536


def labels(con, court):
    """judgment_id -> {'up': [(hits, vishay, upvishay)], 'mudda': {upvishay: [mudda]}} (sirf mukhya)."""
    out = defaultdict(lambda: {"up": [], "mudda": defaultdict(list)})
    for jid, vishay, up, mudda, hits in con.execute(
            "SELECT l.judgment_id, l.vishay, l.upvishay, l.mudda, l.hits FROM labels l JOIN judgments j "
            "ON j.id = l.judgment_id WHERE j.court = ? AND l.strength = 'mukhya'", (court,)):
        if mudda:
            out[jid]["mudda"][up].append((hits, mudda))
        else:
            out[jid]["up"].append((hits, vishay, up))
    return out


def target(cat, outcome, lab):
    ups = sorted(lab["up"], reverse=True)[:3]
    muddas = [m for _, _, up in ups for _, m in sorted(lab["mudda"].get(up, []), reverse=True)][:2]
    lines = [f"Shreni: {cat}", "Vishay: " + "; ".join(f"{v} > {u}" for _, v, u in ups)]
    if muddas:
        lines.append("Mudda: " + "; ".join(muddas))
    lines.append(f"Nateeja: {outcome}")
    return "\n".join(lines), {"shreni": cat, "vishay": [u for _, _, u in ups], "nateeja": outcome}


def text_of(clean, start=0):
    t = re.sub(r"[ \t]+", " ", clean[start or 0:]).strip()
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t if len(t) <= HEAD_CHARS + TAIL_CHARS else t[:HEAD_CHARS] + "\n[...]\n" + t[-TAIL_CHARS:]


def pick(con, court, per, n_test, skip_keys, rng):
    """Har upvishay (faisle ka sabse mazboot) se `per` faisle, nateeja baari-baari; alag se `n_test` jaanch ke liye."""
    lab = labels(con, court)
    groups = defaultdict(lambda: defaultdict(list))
    for jid, key, cat, outcome, n in con.execute(
            "SELECT j.id, j.source_key, c.category, c.outcome, length(t.clean) FROM judgments j "
            "JOIN categories c ON c.judgment_id = j.id JOIN texts t ON t.judgment_id = j.id "
            "WHERE j.court = ? AND c.category IS NOT NULL AND c.outcome IS NOT NULL", (court,)):
        if jid in lab and lab[jid]["up"] and n >= 800 and key not in skip_keys:
            top = max(lab[jid]["up"])[2]
            groups[top][outcome].append((jid, cat, outcome))
    pool = {up: sum(len(v) for v in g.values()) for up, g in groups.items()}
    k = -(-n_test // max(1, len(groups)))   # har upvishay se itne jaanch ke liye (pehle), baaki training
    train, test = [], []
    for up in sorted(groups):
        by_out = groups[up]
        for items in by_out.values():
            rng.shuffle(items)
        order = []   # nateeja baari-baari: Paksh, Khilaf, Nipataara, Paksh, ...
        while any(by_out.values()):
            for o in sorted(by_out):
                if by_out[o]:
                    order.append(by_out[o].pop())
        n = min(k, len(order) // 5)   # chhote upvishay ka zyada hissa jaanch mein na jaaye
        test += order[:n]
        train += order[n:n + per]
    rng.shuffle(test)
    return train, test[:n_test], lab, pool


def rows(con, court, picked, lab):
    ids = {jid: (cat, outcome) for jid, cat, outcome in picked}
    out = []
    items = list(ids)
    for i in range(0, len(items), 2000):
        chunk = items[i:i + 2000]
        for jid, key, title, case_no, year, clean, start in con.execute(
                "SELECT j.id, j.source_key, j.title, j.case_no, j.year, t.clean, t.body_start FROM judgments j "
                f"JOIN texts t ON t.judgment_id = j.id WHERE j.id IN ({','.join('?' * len(chunk))})", chunk):
            cat, outcome = ids[jid]
            tgt, gold = target(cat, outcome, lab[jid])
            out.append({"key": key, "task": "vargikaran", "court": court, "title": title or case_no,
                        "case_no": case_no, "year": year, "in_tok": IN_TOK,
                        "input": text_of(clean, start if court == "SC" else 0), "target": tgt, "gold": gold})
    return out


def write(path, items):
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for r in items:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--hc-per", type=int, default=400, help="Nainital HC: har upvishay se kitne")
    ap.add_argument("--sc-per", type=int, default=80, help="SC: har upvishay se kitne")
    ap.add_argument("--replay", type=int, default=2000, help="SC headnote ke purane jode")
    ap.add_argument("--hc-test", type=int, default=300)
    ap.add_argument("--sc-test", type=int, default=100)
    ap.add_argument("--seed", type=int, default=21)
    ap.add_argument("--v1", type=Path, help="v1 data ka folder (train-data branch: train/test.jsonl.gz)")
    ap.add_argument("--v1-test", type=int, default=1000, help="v1 ke jaanch wale headnote faisle (badlo mat)")
    args = ap.parse_args()
    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    rng = random.Random(args.seed)

    sc_train_hn, sc_test_hn = v1(con, args.v1, args.v1_test)   # v1 wala hi bantwara
    for p in sc_train_hn + sc_test_hn:
        p["task"] = "headnote"
    skip = {p["key"] for p in sc_test_hn}                # v1 ke test faisle vargikaran mein bhi nahi

    hc_tr, hc_te, hc_lab, hc_pool = pick(con, "UKHC", args.hc_per, args.hc_test, set(), rng)
    sc_tr, sc_te, sc_lab, sc_pool = pick(con, "SC", args.sc_per, args.sc_test, skip, rng)
    train = rows(con, "UKHC", hc_tr, hc_lab) + rows(con, "SC", sc_tr, sc_lab) + rng.sample(
        sc_train_hn, min(args.replay, len(sc_train_hn)))
    rng.shuffle(train)
    # test: pehle v1 ke 1000 headnote (usi kram mein: train_nyay unme se wahi 20 chunta hai), phir vargikaran
    test = sc_test_hn + rows(con, "UKHC", hc_te, hc_lab) + rows(con, "SC", sc_te, sc_lab)

    args.out.mkdir(parents=True, exist_ok=True)
    write(args.out / "train.jsonl.gz", train)
    write(args.out / "test.jsonl.gz", test)
    count = lambda items, task, court=None: sum(  # noqa: E731
        1 for r in items if r.get("task") == task and (court is None or r.get("court") == court))
    stats = {"train": len(train), "test": len(test),
             "train_ukhc": count(train, "vargikaran", "UKHC"), "train_sc": count(train, "vargikaran", "SC"),
             "train_headnote": count(train, "headnote"),
             "test_ukhc": count(test, "vargikaran", "UKHC"), "test_sc": count(test, "vargikaran", "SC"),
             "test_headnote": count(test, "headnote"),
             "pool_ukhc": sum(hc_pool.values()), "pool_sc": sum(sc_pool.values()),
             "upvishay_ukhc": dict(sorted(hc_pool.items(), key=lambda x: -x[1])),
             "licence": "Nainital HC faisle (sarvajanik court record); SC: AWS Open Data, CC-BY-4.0"}
    (args.out / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in stats.items() if k != "upvishay_ukhc"}))


if __name__ == "__main__":
    main()
