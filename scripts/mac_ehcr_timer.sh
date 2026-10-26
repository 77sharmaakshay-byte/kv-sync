#!/bin/bash
# Mac ka apna timer (launchd, .github/workflows/mac-timer.yml lagata hai): shaam 6, 7, 8 baje aur subah 6:30
# court ki site (ehcr) se cause list PDF laao, GitHub Release 'ehcr-inbox' mein daalo aur "Mac cause list"
# workflow ko batao (inbox = file ka naam) — GitHub ka der wala timer aur Mac runner ki line, dono ki zaroorat nahi.
# Token: ~/nyay-search/timer/gh_token (GitHub secret DISPATCH_TOKEN; is repo ka Contents + Actions likhna).
set -u
D="$HOME/nyay-search/timer"
REPO=$(cat "$D/repo" 2>/dev/null || echo "77sharmaakshay-byte/krishivlaw")   # mac-timer.yml likhta hai
cd "$D" || exit 1
log() { echo "$(date '+%F %T') $*" >> "$D/timer.log"; }
TOKEN=$(cat "$D/gh_token" 2>/dev/null) || { log "gh_token nahi"; exit 1; }
api() { curl -sSL --max-time 120 -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" "$@"; }
jid() { /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin).get("id", ""))' 2>/dev/null; }
# Repo ka naam badle (krishivlaw -> kv-sync) to uploads.github.com purane naam par chupchaap kuch nahi karta:
# har baar GitHub se asli naam poochho (purana naam bhi redirect se sahi repo deta hai) aur yaad rakho.
name=$(api "https://api.github.com/repos/$REPO" | /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin).get("full_name", ""))' 2>/dev/null)
if [ -n "$name" ] && [ "$name" != "$REPO" ]; then log "repo ka naya naam: $REPO -> $name"; REPO="$name"; printf '%s' "$REPO" > "$D/repo"; fi
# eCourts wala raasta bhi abhi (GitHub ka apna shaam ka schedule kabhi chalta hi nahi)
api -X POST "https://api.github.com/repos/$REPO/actions/workflows/daily-court.yml/dispatches" -d '{"ref":"main"}' > /dev/null \
  || log "daily-court dispatch fail"

for try in 1 2 3; do   # site kabhi der se jawab deti hai
  rm -rf out && /usr/bin/python3 ukhc_ehcr.py fetch --out out >> "$D/timer.log" 2>&1 && break
  sleep 60
done
n=$(find out -name ehcr.json 2>/dev/null | wc -l | tr -d ' ')
[ "$n" -gt 0 ] || { log "site par aaj/aage ki koi list nahi"; exit 0; }
NAME="ehcr-$(date +%Y%m%d-%H%M%S).tar.gz"
tar -czf "$NAME" -C out .
rid=$(api "https://api.github.com/repos/$REPO/releases/tags/ehcr-inbox" | jid)
if [ -z "$rid" ]; then
  rid=$(api -X POST "https://api.github.com/repos/$REPO/releases" \
    -d '{"tag_name":"ehcr-inbox","target_commitish":"main","name":"Cause list inbox (Mac timer)","body":"Mac ka timer yahan PDF daalta hai; Mac cause list workflow utha kar hata deta hai.","prerelease":true}' | jid)
fi
[ -n "$rid" ] || { log "release nahi bani (token?)"; exit 1; }
up=$(api -X POST -H "Content-Type: application/gzip" --data-binary @"$NAME" \
  "https://uploads.github.com/repos/$REPO/releases/$rid/assets?name=$NAME" \
  | /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin).get("state", ""))' 2>/dev/null)
if [ "$up" != "uploaded" ]; then   # file nahi pahunchi: GitHub ko bina file ke batao — Mac runner khud list laayega
  log "upload fail ($up) — Mac runner wala raasta"
  api -X POST "https://api.github.com/repos/$REPO/actions/workflows/mac-causelist.yml/dispatches" -d '{"ref":"main"}' > /dev/null
  exit 1
fi
api -X POST "https://api.github.com/repos/$REPO/actions/workflows/mac-causelist.yml/dispatches" \
  -d "{\"ref\":\"main\",\"inputs\":{\"inbox\":\"$NAME\"}}" > /dev/null || { log "dispatch fail"; exit 1; }
rm -f "$NAME"
log "bheja $NAME ($n din ki list)"
