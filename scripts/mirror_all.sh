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
echo "== 1/3 Code ki copy (vendor/)"
python3 scripts/vendor_sync.py || status=1
echo "== 2/3 Judgments data -> $DEST"
python3 scripts/mirror_data.py --dest "$DEST" --groups "$GROUPS" --yes || status=1
echo "== 3/3 AI models -> $DEST/models"
python3 scripts/mirror_models.py --dest "$DEST" || status=1

[ $status -eq 0 ] && echo "Sab poora." || echo "Kuch hissa adhoora — wahi command dobara chalao, wahin se aage chalega."
exit $status
