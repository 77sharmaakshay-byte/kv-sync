#!/bin/sh
# Ek command mein sab kuch apne paas: code ki copy, judgments data, AI models.
# Dobara chalao to sirf naya / badla hua aata hai.
#
#   sh scripts/mirror_all.sh /Volumes/<drive>/krishivlaw-data
#   sh scripts/mirror_all.sh /Volumes/<drive>/krishivlaw-data --with-hindi   # +51.5 GB SC Hindi/regional
set -u
DEST="${1:?Pehla argument: data kahan rakhna hai, jaise /Volumes/MyDrive/krishivlaw-data}"
cd "$(dirname "$0")/.." || exit 1

GROUPS="sc-english,sc-meta-parquet,sc-meta-raw,uk-hc-pdf,uk-hc-meta-parquet,uk-hc-meta-raw"
[ "${2:-}" = "--with-hindi" ] && GROUPS="$GROUPS,sc-regional"

status=0
echo "== 1/4 Code ki copy (vendor/)"
python3 scripts/vendor_sync.py || status=1
echo "== 2/4 Judgments data -> $DEST"
python3 scripts/mirror_data.py --dest "$DEST" --groups "$GROUPS" --yes || status=1
echo "== 3/4 AI models -> $DEST/models"
python3 scripts/mirror_models.py --dest "$DEST" || status=1

# SC ke non-reportable judgments: vanga ka purana Kaggle dataset (CC-BY).
# Free Kaggle account + ~/.kaggle/kaggle.json token chahiye.
echo "== 4/4 SC (reportable + non-reportable, 1950-2024) Kaggle se -> $DEST/kaggle-sc-all"
if command -v kaggle >/dev/null 2>&1; then
  kaggle datasets download -d vangap/indian-supreme-court-judgments -p "$DEST/kaggle-sc-all" || status=1
else
  echo "   kaggle command nahi mila: 'pip3 install kaggle' karo aur kaggle.com se API token ~/.kaggle/kaggle.json mein rakho."
  status=1
fi

[ $status -eq 0 ] && echo "Sab poora." || echo "Kuch hissa adhoora — wahi command dobara chalao, wahin se aage chalega."
exit $status
