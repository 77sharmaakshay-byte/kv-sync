#!/bin/sh
# App (app/) + data branch se bana data -> 'site' branch. Render (Static Site) usi branch ko chalata hai.
#   sh scripts/publish_site.sh <data branch checkout>
# GitHub Actions mein chalta hai (daily-court aur case-lookup ke baad).
set -eu
DATA="${1:?data branch checkout ka path do}"
cd "$(dirname "$0")/.."
OUT="sitebranch"
# app/ aur scripts/ hamesha main ke taaze: lamba chala workflow (purane checkout wala) naya app purane se na badal de
# (3 Nov: "Case analysis" ne Live tab wala app 1 minute baad purane se badal diya tha).
SRC=.
if git fetch -q --depth 1 origin main 2>/dev/null; then
  MAIN=$(git rev-parse FETCH_HEAD); SRC=$(mktemp -d)
  git archive "$MAIN" app scripts kaggle/train/plan.json | tar -x -C "$SRC"   # build_app_data: app/notes, plan.json
fi
if git ls-remote --exit-code --heads origin site >/dev/null 2>&1; then
  git fetch -q --depth 1 origin +site:site
  git worktree add -q "$OUT" site
else
  git worktree add -q --orphan -b site "$OUT"
fi
find "$OUT" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp -R "$SRC/app/." "$OUT"/
rm -rf "$OUT/notes"
python3 "$SRC/scripts/build_app_data.py" --data-branch "$DATA" --out "$OUT/data"
cat > "$OUT/README.md" <<'TXT'
# site branch — apne aap banti hai, haath se mat badlo
Render Static Site: branch `site`, Build Command khaali, Publish Directory `.`
TXT
cd "$OUT"
git add -A
if git diff --cached --quiet; then echo "Site mein kuch naya nahi"; exit 0; fi
git commit -q -m "site: $(date -u +%Y-%m-%dT%H:%MZ)"
git push -q origin site
echo "Site update ho gayi"
