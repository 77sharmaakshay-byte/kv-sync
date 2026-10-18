#!/bin/bash
# Mac ka apna timer (launchd, .github/workflows/mac-timer.yml lagata hai): shaam 6, 7, 8 baje aur subah 6:30
# court ki site (ehcr) se cause list PDF laao, GitHub Release 'ehcr-inbox' mein daalo aur "Mac cause list"
# workflow ko batao (inbox = file ka naam) — GitHub ka der wala timer aur Mac runner ki line, dono ki zaroorat nahi.
# Token: ~/nyay-search/timer/gh_token (GitHub secret DISPATCH_TOKEN; is repo ka Contents + Actions likhna).
set -u
D="$HOME/nyay-search/timer"
REPO="77sharmaakshay-byte/krishivlaw"
cd "$D" || exit 1
log() { echo "$(date '+%F %T') $*" >> "$D/timer.log"; }
TOKEN=$(cat "$D/gh_token" 2>/dev/null) || { log "gh_token nahi"; exit 1; }
api() { curl -sS --max-time 120 -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" "$@"; }
jid() { /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin).get("id", ""))' 2>/dev/null; }

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
api -X POST -H "Content-Type: application/gzip" --data-binary @"$NAME" \
  "https://uploads.github.com/repos/$REPO/releases/$rid/assets?name=$NAME" > /dev/null || { log "upload fail"; exit 1; }
api -X POST "https://api.github.com/repos/$REPO/actions/workflows/mac-causelist.yml/dispatches" \
  -d "{\"ref\":\"main\",\"inputs\":{\"inbox\":\"$NAME\"}}" > /dev/null || { log "dispatch fail"; exit 1; }
rm -f "$NAME"
log "bheja $NAME ($n din ki list)"
