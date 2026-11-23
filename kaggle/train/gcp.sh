#!/bin/bash
# Google Cloud par training round (kaggle-train.yml se; gcloud pehle se login — secret GCP_SA_KEY).
#   gcp.sh status N          -> running | complete | error | gone  (gone = machine nahi, nateeja nahi: spot cheen li / bani hi nahi)
#   gcp.sh fetch N DIR       -> nateeja DIR mein (adapter/, eval.json, *.log) — Kaggle 'kernels output' jaisa
#   gcp.sh start N LAUNCH DATASETS... -> GPU machine banao (spot L4; pehle India, phir US/Europe ke zone)
#   gcp.sh hours N           -> is round ki machine kitne ghante chali (andaza, 'started' se ab tak / nateeja tak)
#   gcp.sh clean N           -> bucket se round ka saaman hatao (Kaggle par model chadh gaya to)
# Kharcha: machine round ke baad khud delete hoti hai (gcp_vm.sh); --max-run-duration 12h; workflow ghante ginta hai.
set -euo pipefail
P=$(gcloud config get-value project 2>/dev/null)
B="nyay-train-$P"
VM() { echo "nyay-train-$1"; }
cmd=$1; shift
case "$cmd" in
  status)
    if gcloud storage ls "gs://$B/round-$1/rc" >/dev/null 2>&1; then
      rc=$(gcloud storage cat "gs://$B/round-$1/rc" | tr -dc 0-9)
      if [ "$rc" = 0 ] && gcloud storage ls "gs://$B/round-$1/adapter/state.json" >/dev/null 2>&1; then echo complete; else echo error; fi
    elif [ -n "$(gcloud compute instances list --filter="name=$(VM "$1")" --format='value(name)' 2>/dev/null)" ]; then
      echo running
    else
      echo gone
    fi ;;
  fetch)
    mkdir -p "$2"
    gcloud storage cp -r "gs://$B/round-$1/*" "$2/" ;;
  hours)
    s=$(gcloud storage cat "gs://$B/round-$1/started" 2>/dev/null | tr -dc 0-9 || true)
    e=$(gcloud storage ls -l "gs://$B/round-$1/rc" 2>/dev/null | awk 'NR==1{print $2}' || true)
    e=$( [ -n "$e" ] && date -d "$e" +%s || date +%s )
    [ -n "$s" ] && python3 -c "import sys;print(round((int(sys.argv[2])-int(sys.argv[1]))/3600+0.3,2))" "$s" "$e" || echo 0.3 ;;
  clean)
    gcloud storage rm -r "gs://$B/round-$1" >/dev/null 2>&1 || true ;;
  start)
    N=$1; LAUNCH=$2; shift 2
    gcloud storage buckets describe "gs://$B" >/dev/null 2>&1 || gcloud storage buckets create "gs://$B" --location=US
    gcloud storage rm -r "gs://$B/round-$N" >/dev/null 2>&1 || true
    SA=$(gcloud config get-value account 2>/dev/null)
    IMG=$(gcloud compute images list --project deeplearning-platform-release --no-standard-images \
          --filter="family~pytorch AND family~cu12 AND family~ubuntu AND status=READY" \
          --sort-by=~creationTimestamp --limit=1 --format='value(name)')
    echo "image: $IMG"
    md="bucket=$B,round=$N,datasets=$*,kaggle_user=${KAGGLE_USERNAME:-krishivlaw},install-nvidia-driver=True"
    [ -n "${KAGGLE_KEY:-}" ] && md="$md,kaggle_key=$KAGGLE_KEY"
    [ -n "${KAGGLE_API_TOKEN:-}" ] && md="$md,kaggle_token=$KAGGLE_API_TOKEN"
    d=$(dirname "$0")
    for Z in ${GCP_ZONES:-asia-south1-a asia-south1-b asia-south1-c us-central1-a us-central1-b us-central1-c us-east4-a us-east1-b europe-west4-a}; do
      echo "zone $Z ..."
      if gcloud compute instances create "$(VM "$N")" --zone "$Z" --machine-type g2-standard-8 \
          --accelerator type=nvidia-l4,count=1 --maintenance-policy TERMINATE \
          --provisioning-model SPOT --instance-termination-action DELETE --max-run-duration 12h \
          --image "$IMG" --image-project deeplearning-platform-release --boot-disk-size 200GB --boot-disk-type pd-balanced \
          --service-account "$SA" --scopes cloud-platform \
          --metadata "^|^$(echo "$md" | tr ',' '|')" \
          --metadata-from-file "startup-script=$d/gcp_vm.sh,launch=$LAUNCH" 2>&1 | tee /tmp/gcp-create.log; then
        grep -qi "error" /tmp/gcp-create.log || { echo "machine bani: $Z"; exit 0; }
      fi
    done
    echo "kisi zone mein GPU machine nahi bani"; exit 1 ;;
  *) echo "gcp.sh: $cmd?"; exit 2 ;;
esac
