#!/usr/bin/env python3
"""Upstream GitHub repos ki apni copy banana / taaza karna.

Har repo jo config/upstreams.json mein hai, uski latest commit ka snapshot
vendor/<use>/<name>/ mein copy hota hai (.git ke bina), aur
vendor/SOURCES.json + vendor/SOURCES.md mein commit, tareekh aur license
likha jata hai. Agar koi upstream private ya delete ho jaye, to purani copy
waise hi rehti hai aur report mein "GAYAB" dikhta hai — kuch delete nahi hota.

Usage:
    python3 scripts/vendor_sync.py            # sab repos taaza karo
    python3 scripts/vendor_sync.py --check    # sirf dekho kaun zinda hai
"""
import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "upstreams.json"
VENDOR = ROOT / "vendor"
LOCK = VENDOR / "SOURCES.json"


def git(*args, cwd=None):
    env = dict(os.environ, GIT_LFS_SKIP_SMUDGE="1", GIT_TERMINAL_PROMPT="0")
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=env)


def remote_head(url, branch=None):
    """Upstream ki HEAD (ya branch) commit, ya None agar repo/branch nahi mila."""
    res = git("ls-remote", url, f"refs/heads/{branch}" if branch else "HEAD")
    if res.returncode != 0 or not res.stdout.strip():
        return None
    return res.stdout.split()[0]


def snapshot(repo, dest):
    """Repo ko clone karke .git ke bina dest mein rakho. Commit info lautao."""
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "repo"
        branch = ["--branch", repo["branch"]] if repo.get("branch") else []
        res = git("clone", "--quiet", "--depth", "1", *branch, repo["url"], str(work))
        if res.returncode != 0:
            raise RuntimeError(res.stderr.strip())
        info = git("log", "-1", "--format=%H%n%cI", cwd=work).stdout.split("\n")
        staged = dest.with_name(dest.name + ".new")
        if staged.exists():
            shutil.rmtree(staged)
        shutil.copytree(work, staged, ignore=shutil.ignore_patterns(".git"))
        # Nayi copy poori ban gayi, tabhi purani hatao.
        if dest.exists():
            shutil.rmtree(dest)
        staged.rename(dest)
        return {"commit": info[0], "commit_date": info[1]}


def write_md(lock):
    lines = [
        "# Upstream copies",
        "",
        "`scripts/vendor_sync.py` se bani. Haath se mat badlo.",
        "",
        "| Repo | Use | License | Commit | Commit date | Last change | Status |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, r in sorted(lock.items()):
        lines.append(
            f"| [{name}]({r['url']}) | {r['use']} | {r['license']} | "
            f"`{r.get('commit', '')[:10]}` | {r.get('commit_date', '')[:10]} | "
            f"{r.get('updated_at', '')[:10]} | {r.get('status', '')} |"
        )
    lines += [
        "",
        "- `vendor/product/`: license product mein use karne deta hai (MIT / CC-BY, attribution ke saath).",
        "- `vendor/reference/`: sirf padhne ke liye. Is code ko product mein copy mat karo.",
        "",
    ]
    (VENDOR / "SOURCES.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="sirf upstream check karo, copy mat karo")
    args = ap.parse_args()

    repos = json.loads(CONFIG.read_text(encoding="utf-8"))["repos"]
    lock = json.loads(LOCK.read_text(encoding="utf-8")) if LOCK.exists() else {}
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    problems = 0

    for repo in repos:
        name = repo["name"]
        old = dict(lock.get(name, {}))
        old.pop("checked_at", None)               # purane version ka field
        entry = dict(old)
        entry.update({k: repo[k] for k in ("url", "license", "use")})
        head = remote_head(repo["url"], repo.get("branch"))
        if head is None:
            problems += 1
            entry["status"] = "GAYAB — upstream nahi mila, purani copy rakhi hai"
            print(f"[GAYAB] {name}: {repo['url']}")
        elif args.check:
            same = head == entry.get("commit")
            entry["status"] = "zinda — copy taaza hai" if same else "zinda — nayi commit hai, sync chalao"
            print(f"[ok] {name}: {head[:10]}{'' if same else '  (nayi commit)'}")
        elif head == entry.get("commit"):
            entry["status"] = "zinda — copy taaza hai"
            print(f"[same] {name}: {head[:10]}")
        else:
            dest = VENDOR / repo["use"] / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                entry.update(snapshot(repo, dest))
                entry["status"] = "zinda — copy taaza hai"
                print(f"[copied] {name}: {entry['commit'][:10]} -> {dest.relative_to(ROOT)}")
            except RuntimeError as err:
                problems += 1
                entry["status"] = f"clone fail — purani copy rakhi hai ({err})"
                print(f"[fail] {name}: {err}")
        # Samay tabhi badlo jab kuch sach mein badla ho (commit, status...),
        # warna har run par file badal jaati hai bina kisi wajah ke.
        changed = {k: v for k, v in entry.items() if k != "updated_at"} != \
                  {k: v for k, v in old.items() if k != "updated_at"}
        if changed or "updated_at" not in entry:
            entry["updated_at"] = now
        lock[name] = entry

    VENDOR.mkdir(exist_ok=True)
    text = json.dumps(lock, indent=2, ensure_ascii=False) + "\n"
    if not LOCK.exists() or LOCK.read_text(encoding="utf-8") != text:
        LOCK.write_text(text, encoding="utf-8")
        write_md(lock)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
