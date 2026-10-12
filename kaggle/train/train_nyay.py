# Nyay model v1: Qwen2.5-7B-Instruct ko SC faisla -> headnote par QLoRA se sikhana (Kaggle, free T4 GPU).
# GitHub Actions 'Kaggle' workflow (task: train) ise `kaggle kernels push` se chalata hai.
# Data: private Kaggle dataset <user>/nyay-train-v1 (scripts/build_train_data.py se bana, CC-BY-4.0).
# Nateeja /kaggle/working/: adapter/ (LoRA weights), eval.json (test faislon par score aur namoone).
import gzip
import json
import os
import random
import subprocess
import sys
import time

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", "peft", "bitsandbytes", "rouge-score"], check=True)

import torch  # noqa: E402,F811
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training  # noqa: E402
from rouge_score import rouge_scorer  # noqa: E402
from transformers import (AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, Trainer,  # noqa: E402
                          TrainingArguments)

BASE = "Qwen/Qwen2.5-7B-Instruct"
# Kaggle .gz ko kabhi khol deta hai (train.jsonl), kabhi waise hi rakhta hai; dono chalein
FILES = {f: os.path.join(r, f) for r, _, fs in os.walk("/kaggle/input") for f in fs}
if not any(k.startswith("train.jsonl") for k in FILES):
    raise SystemExit("train.jsonl nahi mila. /kaggle/input mein: " + ", ".join(sorted(FILES)[:50]))
OUT = "/kaggle/working"
N_TRAIN = int(os.environ.get("NYAY_N_TRAIN", "2000"))  # T4 par session ki seema mein rehne ke liye
N_EVAL = int(os.environ.get("NYAY_N_EVAL", "25"))
IN_TOK, OUT_TOK = 2600, 700
SYSTEM = ("Aap Indian Supreme Court ke faislon ke headnote likhne wale anubhavi reporter hain. Faisle ka text padh "
          "kar Supreme Court Reports ke format mein headnote likhiye: vishay (Act, section), tathya, mudda, "
          "'Held:' ke point, aur kaunse purane faisle relied on / distinguished hue. Sirf faisle mein likhi baat; "
          "apni taraf se koi citation ya tathya mat jodiye.")
T0 = time.time()
if not torch.cuda.is_available():
    raise SystemExit("GPU nahi mila: Kaggle account phone se verify karo aur notebook mein GPU on karo")
print("GPU:", [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())], flush=True)


def load(name, n):
    path = FILES.get(name) or FILES[name.replace(".gz", "")]
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f]
    random.Random(7).shuffle(rows)
    return rows[:n]


tok = AutoTokenizer.from_pretrained(BASE)
tok.padding_side = "right"


def clip(text, n):
    """Lambe faisle: shuru (tathya, mudda) + ant (nateeja) rakho."""
    ids = tok(text, add_special_tokens=False)["input_ids"]
    if len(ids) <= n:
        return text
    head, tail = int(n * 0.7), n - int(n * 0.7)
    return tok.decode(ids[:head]) + "\n[...]\n" + tok.decode(ids[-tail:])


def prompt(row):
    msgs = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": "Faisla:\n" + clip(row["input"], IN_TOK) + "\n\nIska headnote likhiye."}]
    return tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)


def encode(row):
    p = tok(prompt(row), add_special_tokens=False)["input_ids"]
    t = tok(row["target"] + tok.eos_token, add_special_tokens=False)["input_ids"][:OUT_TOK]
    return {"input_ids": p + t, "labels": [-100] * len(p) + t}


def collate(batch):
    n = max(len(b["input_ids"]) for b in batch)
    pad = tok.pad_token_id
    ids = torch.tensor([b["input_ids"] + [pad] * (n - len(b["input_ids"])) for b in batch])
    lab = torch.tensor([b["labels"] + [-100] * (n - len(b["labels"])) for b in batch])
    return {"input_ids": ids, "labels": lab, "attention_mask": (ids != pad).long()}


train = [encode(r) for r in load("train.jsonl.gz", N_TRAIN)]
test = load("test.jsonl.gz", N_EVAL)
print(f"train {len(train)}, eval {len(test)}, {time.time() - T0:.0f}s", flush=True)

model = AutoModelForCausalLM.from_pretrained(
    BASE, device_map="auto", torch_dtype=torch.float16,
    quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                           bnb_4bit_compute_dtype=torch.float16, bnb_4bit_use_double_quant=True))
model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
model = get_peft_model(model, LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, task_type="CAUSAL_LM",
                                         target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                                                         "gate_proj", "up_proj", "down_proj"]))
model.print_trainable_parameters()

# transformers ke naye/purane version: jo setting is version mein nahi, use chhod do (aur batao)
import inspect  # noqa: E402
steps = max(1, -(-len(train) // 16))
want = dict(output_dir=f"{OUT}/ckpt", per_device_train_batch_size=1, gradient_accumulation_steps=16,
            num_train_epochs=1, learning_rate=2e-4, lr_scheduler_type="cosine", warmup_steps=max(1, int(steps * 0.03)),
            fp16=True, logging_steps=10, save_steps=50, save_total_limit=2, report_to=[],
            gradient_checkpointing=True, optim="paged_adamw_8bit", max_grad_norm=0.3)
ok = set(inspect.signature(TrainingArguments.__init__).parameters)
print("TrainingArguments mein nahi:", [k for k in want if k not in ok], flush=True)
args = TrainingArguments(**{k: v for k, v in want.items() if k in ok})
Trainer(model=model, args=args, train_dataset=train, data_collator=collate).train()
model.save_pretrained(f"{OUT}/adapter")
tok.save_pretrained(f"{OUT}/adapter")
print(f"training done {time.time() - T0:.0f}s", flush=True)

# Jaanch: test ke faislon par headnote likhwao (bina training wala model vs hamara model),
# court ke asli headnote se ROUGE-L. Dono ek hi faislon par, taaki tulna imaandaar ho.
model.eval()
tok.padding_side = "left"
scorer = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=True)


def write(row):
    enc = tok(prompt(row), return_tensors="pt", add_special_tokens=False).to(model.device)
    with torch.no_grad():
        out = model.generate(**enc, max_new_tokens=OUT_TOK, do_sample=False, repetition_penalty=1.05)
    return tok.decode(out[0][enc["input_ids"].shape[1]:], skip_special_tokens=True)


samples = []
for row in test:
    ours = write(row)
    with model.disable_adapter():
        base = write(row)
    samples.append({"key": row["key"], "title": row["title"], "court": row["target"][:1500],
                    "ours": ours[:1500], "base": base[:1500],
                    "rougeL_ours": round(scorer.score(row["target"], ours)["rougeL"].fmeasure, 3),
                    "rougeL_base": round(scorer.score(row["target"], base)["rougeL"].fmeasure, 3)})
    print(row["key"], samples[-1]["rougeL_base"], "->", samples[-1]["rougeL_ours"], f"{time.time() - T0:.0f}s",
          flush=True)
mean = lambda k: round(sum(x[k] for x in samples) / max(len(samples), 1), 4)  # noqa: E731
json.dump({"base_model": BASE, "n_train": len(train), "n_eval": len(samples), "rougeL_base": mean("rougeL_base"),
           "rougeL_ours": mean("rougeL_ours"), "seconds": round(time.time() - T0), "samples": samples},
          open(f"{OUT}/eval.json", "w"), ensure_ascii=False, indent=1)
print("rougeL base", mean("rougeL_base"), "ours", mean("rougeL_ours"), f"{time.time() - T0:.0f}s", flush=True)
