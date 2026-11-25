#!/bin/bash
# Google Cloud ki GPU machine par chalne wali startup script (kaggle/train/gcp.sh 'start' isko metadata mein daalta hai).
# Kaggle jaisa hi: /kaggle/input mein data + pichhla model, launch.py (train_nyay.py ke saath) chalao, nateeja
# /kaggle/working se bucket mein (gs://<bucket>/round-N/), phir machine khud ko delete kare — bekaar paisa na kate.
# Machine banate waqt --max-run-duration bhi hai: kuch atke to Google khud delete kar dega.
exec >> /var/log/nyay.log 2>&1
set -x
MD=http://metadata.google.internal/computeMetadata/v1/instance
get() { curl -sf -H Metadata-Flavor:Google "$MD/$1"; }
B=$(get attributes/bucket); R=$(get attributes/round)
NAME=$(get name); ZONE=$(get zone | sed 's#.*/##')
D="gs://$B/round-$R"
bye() {   # nateeja / log bucket mein, phir machine delete
  echo "bye $1"
  gcloud storage cp /var/log/nyay.log "$D/vm.log"   # log hamesha (shuru mein hi atke to bhi)
  for f in /kaggle/working/adapter /kaggle/working/eval.json /kaggle/working/nyay-train.log; do
    [ -e "$f" ] && gcloud storage cp -r "$f" "$D/"
  done
  echo "$1" | gcloud storage cp - "$D/rc"
  gcloud compute instances delete "$NAME" --zone "$ZONE" --quiet
  exit 0
}
# reboot ke baad dobara mat chalo (spot machine delete hoti hai, par phir bhi)
[ -f /var/nyay-started ] && bye 97
touch /var/nyay-started
date -u +%s | gcloud storage cp - "$D/started"

# GPU driver (Deep Learning VM image install-nvidia-driver se lagata hai; thoda samay lagta hai)
for i in $(seq 1 60); do nvidia-smi -L && break; sleep 10; done
nvidia-smi -L || bye 90

export KAGGLE_USERNAME=$(get attributes/kaggle_user)
k=$(get attributes/kaggle_key); [ -n "$k" ] && export KAGGLE_KEY="$k"
t=$(get attributes/kaggle_token); [ -n "$t" ] && export KAGGLE_API_TOKEN="$t"
# Apna alag Python (venv): Ubuntu 24.04 wali image system Python mein pip install mana karti hai (rc 91 isi se).
# torch bhi venv mein (PyPI wala CUDA 12 build; driver image ka) — image kaunsi bhi ho, ek jaisa chale.
V=/opt/nyay
if [ ! -x "$V/bin/python" ]; then
  python3 -m venv "$V" || { apt-get update -q && apt-get install -y -q python3-venv python3-pip && python3 -m venv "$V"; } || bye 93
fi
PY="$V/bin/python"; export PATH="$V/bin:$PATH"
$PY -m pip install -q -U pip || bye 91
$PY -m pip install -q torch transformers accelerate datasets peft bitsandbytes rouge-score kaggle six || bye 91
$PY -c "import torch;print('torch', torch.__version__, 'cuda', torch.cuda.is_available())"
mkdir -p /kaggle/input /kaggle/working
for ds in $(get attributes/datasets); do
  kaggle datasets download -d "$ds" -p "/kaggle/input/${ds#*/}" --unzip || bye 92
done
find /kaggle/input -maxdepth 3 | head -50
get attributes/launch > /tmp/launch.py
# Spot machine Google kabhi bhi waapas le sakta hai (24 Nov: 6.5 ghante baad, poora round gaya) — chhote round
th=$(get attributes/train_hours); [ -n "$th" ] && export NYAY_TRAIN_HOURS="$th"
cd /kaggle/working && $PY /tmp/launch.py > /kaggle/working/nyay-train.log 2>&1
bye $?
