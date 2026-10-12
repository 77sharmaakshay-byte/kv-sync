#!/bin/sh
# App (app/) + data branch se bana data -> 'site' branch. Render (Static Site) usi branch ko chalata hai.
#   sh scripts/publish_site.sh <data branch checkout>
# GitHub Actions mein chalta hai (daily-court aur case-lookup ke baad).
set -eu
DATA="${1:?data branch checkout ka path do}"
cd "$(dirname "$0")/.."
OUT="sitebranch"
if git ls-remote --exit-code --heads origin site >/dev/null 2>&1; then
  git fetch -q --depth 1 origin +site:site
  git worktree add -q "$OUT" site
else
  git worktree add -q --orphan -b site "$OUT"
fi
find "$OUT" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp -R app/. "$OUT"/
rm -rf "$OUT/notes"
python3 scripts/build_app_data.py --data-branch "$DATA" --out "$OUT/data"
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
