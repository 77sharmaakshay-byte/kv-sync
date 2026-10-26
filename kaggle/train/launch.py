# Kaggle par chalne wala launcher (kernel ki code file). Workflow kaggle-train.yml isme
# train_nyay.py (base64), round number, data (Kaggle dataset) aur learning rate bharta hai. Dono T4 GPU par ek saath training (torchrun);
# woh shuru mein hi fail ho to ek GPU par.
import base64
import os
import subprocess
import sys
import time

os.environ["NYAY_T0"] = str(time.time())
os.environ["NYAY_ROUND"] = "__ROUND__"
os.environ["NYAY_DATA"] = "__DATA__"
os.environ["NYAY_LR"] = "__LR__"
os.environ["NYAY_UPTO"] = "__UPTO__"
os.environ["NYAY_FROM"] = "__FROM__"
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
WORKER = "/tmp/train_nyay.py"
with open(WORKER, "wb") as f:
    f.write(base64.b64decode("__WORKER_B64__"))
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", "peft", "bitsandbytes", "rouge-score"], check=True)
gpus = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True).stdout.count("GPU ")
print("GPUs:", gpus, flush=True)
rc = 1
if gpus >= 2:
    rc = subprocess.call([sys.executable, "-m", "torch.distributed.run", "--standalone",
                          f"--nproc_per_node={gpus}", WORKER])
    print("torchrun:", rc, flush=True)
done = os.path.exists("/kaggle/working/adapter/state.json")
if rc != 0 and not done and time.time() - float(os.environ["NYAY_T0"]) < 3600:
    rc = subprocess.call([sys.executable, WORKER])
if rc != 0:
    raise SystemExit(f"training fail (rc {rc})")
