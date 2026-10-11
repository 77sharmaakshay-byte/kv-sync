#!/bin/sh
# Ek command mein sab kuch apne paas: code ki copy, judgments data, AI models.
# Dobara chalao to sirf naya / badla hua aata hai.
#
#   sh scripts/mirror_all.sh ~/krishivlaw-data                  # Mac ki apni disk par
#   sh scripts/mirror_all.sh /Volumes/<drive>/krishivlaw-data   # external drive par
#   ... --with-hindi    SC ke Hindi/regional anuvaad bhi (+51.5 GB)
#   ... --no-kaggle     Kaggle wala (non-reportable) hissa abhi chhod do
set -u
# Python ka output turant dikhe, pipe (| tee) ke saath bhi.
export PYTHONUNBUFFERED=1
DEST="${1:?Pehla argument: data kahan rakhna hai, jaise ~/krishivlaw-data}"
shift
cd "$(dirname "$0")/.." || exit 1

DATA_GROUPS="sc-english,sc-meta-parquet,sc-meta-raw,uk-hc-pdf,uk-hc-meta-parquet,uk-hc-meta-raw"
WITH_KAGGLE=1
for opt in "$@"; do
  case "$opt" in
    --with-hindi) DATA_GROUPS="$DATA_GROUPS,sc-regional" ;;
    --no-kaggle) WITH_KAGGLE=0 ;;
    *) echo "Ye option samajh nahi aaya: $opt"; exit 1 ;;
  esac
done

mkdir -p "$DEST" || { echo "Folder nahi ban paya: $DEST"; exit 1; }
free_gb() { df -k "$1" | awk 'NR==2 {printf "%d", $4 / 1024 / 1024}'; }

status=0
echo "== 1/4 Code ki copy (vendor/)"
python3 scripts/vendor_sync.py || status=1

echo "== 2/4 Judgments data -> $DEST"
python3 scripts/mirror_data.py --dest "$DEST" --groups "$DATA_GROUPS" --yes
rc=$?
if [ $rc -eq 3 ]; then
  echo "Disk par jagah kam hai, isliye aage nahi badh raha. Jagah khaali karke dobara chalao."
  exit 3
fi
[ $rc -ne 0 ] && status=1

echo "== 3/4 AI models -> $DEST/models"
python3 scripts/mirror_models.py --dest "$DEST" || status=1

# SC ke non-reportable judgments: vanga ka purana Kaggle dataset (CC-BY).
echo "== 4/4 SC (reportable + non-reportable, 1950-2024) Kaggle se -> $DEST/kaggle-sc-all"
if [ $WITH_KAGGLE -eq 0 ]; then
  echo "   --no-kaggle diya hai, ye hissa chhod diya."
else
  # kaggle apne alag folder (.venv-tools) mein install hota hai, taaki Mac ke
  # system Python, PATH ya "externally-managed" jaisi dikkatein beech mein na aayein.
  KAGGLE=".venv-tools/bin/kaggle"
  if [ ! -x "$KAGGLE" ]; then
    echo "   kaggle install ho raha hai (.venv-tools/)..."
    python3 -m venv .venv-tools && .venv-tools/bin/python -m pip install -q --upgrade pip kaggle \
      || { echo "   kaggle install nahi hua — upar ka error message bhejo."; KAGGLE=""; }
  fi
  FREE=$(free_gb "$DEST")
  if [ -z "$KAGGLE" ] || [ ! -x "$KAGGLE" ]; then
    status=1
  elif [ ! -f "$HOME/.kaggle/kaggle.json" ] && [ ! -f "$HOME/.kaggle/access_token" ] \
       && [ -z "${KAGGLE_API_TOKEN:-}" ] && [ -z "${KAGGLE_KEY:-}" ]; then
    echo "   Kaggle token nahi mila. kaggle.com -> Settings -> API -> Generate New Token,"
    echo "   phir: mkdir -p ~/.kaggle && echo 'TOKEN' > ~/.kaggle/access_token && chmod 600 ~/.kaggle/access_token"
    status=1
  elif [ "$FREE" -lt 40 ]; then
    echo "   Disk par sirf ${FREE} GB khaali hai. Kaggle data ke liye kam se kam 40 GB chahiye,"
    echo "   isliye ye hissa chhod diya. Jagah khaali karke dobara chalao."
    status=1
  else
    echo "   Disk par ${FREE} GB khaali. Dataset ki size:"
    "$KAGGLE" datasets list --user vangap -s indian-supreme-court-judgments 2>&1 | sed 's/^/   /'
    "$KAGGLE" datasets download vangap/indian-supreme-court-judgments -p "$DEST/kaggle-sc-all" || status=1
  fi
fi

echo "== Disk par ab $(free_gb "$DEST") GB khaali"
[ $status -eq 0 ] && echo "Sab poora." || echo "Kuch hissa adhoora — wahi command dobara chalao, wahin se aage chalega."
exit $status
