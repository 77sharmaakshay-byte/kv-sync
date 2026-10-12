# Nyay model: Qwen2.5-7B-Instruct ko SC faisla -> headnote par QLoRA se sikhana (Kaggle, free T4 GPU).
# Ek round: pichhle round ka adapter (Kaggle dataset <user>/nyay-model, agar hai) lo, training data ka agla
# hissa sikhao, samay ki seema par ruko, phir test faislon par jaanch. kaggle/train/launch.py ise dono GPU par
# ek saath chalata hai (torchrun); .github/workflows/kaggle-train.yml round ke baad agla round.
# Data: private Kaggle dataset <user>/nyay-train-v1 (scripts/build_train_data.py se bana, CC-BY-4.0).
# Nateeja /kaggle/working/: adapter/ (LoRA weights), state.json (agla round kahan se), eval.json (score, namoone).
import gzip
import inspect
import json
import os
import random
import sys
import time

import torch
import torch.distributed as dist
from peft import LoraConfig, PeftModel, get_peft_model, prepare_model_for_kbit_training
from rouge_score import rouge_scorer
from transformers import (AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, Trainer, TrainerCallback,
                          TrainingArguments)

BASE = "Qwen/Qwen2.5-7B-Instruct"
OUT = "/kaggle/working"
T0 = float(os.environ.get("NYAY_T0") or time.time())
ROUND = int(os.environ.get("NYAY_ROUND", "1"))
N_TRAIN = int(os.environ.get("NYAY_N_TRAIN", "4000"))     # round mein zyada se zyada; samay ki seema pehle aa sakti hai
N_EVAL = int(os.environ.get("NYAY_N_EVAL", "20"))
TRAIN_SEC = float(os.environ.get("NYAY_TRAIN_HOURS", "9.5")) * 3600  # Kaggle session 12 ghante; jaanch ke liye jagah
IN_TOK, OUT_TOK = 2000, 512
BATCH = 16                                                 # ek optimizer step mein kitne faisle (sab GPU milakar)
LOCAL = int(os.environ.get("LOCAL_RANK", "0"))
WORLD = int(os.environ.get("WORLD_SIZE", "1"))
MAIN = LOCAL == 0
SYSTEM = ("Aap Indian Supreme Court ke faislon ke headnote likhne wale anubhavi reporter hain. Faisle ka text padh "
          "kar Supreme Court Reports ke format mein headnote likhiye: vishay (Act, section), tathya, mudda, "
          "'Held:' ke point, aur kaunse purane faisle relied on / distinguished hue. Sirf faisle mein likhi baat; "
          "apni taraf se koi citation ya tathya mat jodiye.")


def log(*a):
    if MAIN:
        print(*a, f"[{time.time() - T0:.0f}s]", flush=True)


if not torch.cuda.is_available():
    raise SystemExit("GPU nahi mila: Kaggle account phone se verify karo aur notebook mein GPU on karo")
log("GPU:", [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())], "processes:", WORLD)

# Kaggle .gz ko kabhi khol deta hai (train.jsonl), kabhi waise hi rakhta hai; dono chalein
FILES = {f: os.path.join(r, f) for r, _, fs in os.walk("/kaggle/input") for f in fs}
if not any(k.startswith("train.jsonl") for k in FILES):
    raise SystemExit("train.jsonl nahi mila. /kaggle/input mein: " + ", ".join(sorted(FILES)[:50]))

# Pichhla round: adapter + state.json (pehle round mein nahi hote)
prev = json.load(open(FILES["state.json"])) if "state.json" in FILES else {"round": 0, "offset": 0}
if prev["round"] != ROUND - 1:  # Kaggle ne purana version diya to us par training mat karo
    raise SystemExit(f"round {ROUND} ke liye round {ROUND - 1} ka adapter chahiye, mila round {prev['round']}")
ADAPTER = os.path.dirname(FILES["adapter_config.json"]) if ROUND > 1 else None


def lines(name):
    path = FILES.get(name) or FILES[name.replace(".gz", "")]
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        rows = f.readlines()
    random.Random(7).shuffle(rows)  # har round wahi kram; round apna hissa (offset se) leta hai
    return rows


tok = AutoTokenizer.from_pretrained(BASE)
tok.padding_side = "right"


def clip(text, n):
    """Lambe faisle: shuru (tathya, mudda) + ant (nateeja) rakho."""
    ids = tok(text, add_special_tokens=False)["input_ids"]
    if len(ids) <= n:
        return text
    head = int(n * 0.7)
    return tok.decode(ids[:head]) + "\n[...]\n" + tok.decode(ids[-(n - head):])


def prompt(row):
    msgs = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": "Faisla:\n" + clip(row["input"], IN_TOK) + "\n\nIska headnote likhiye."}]
    return tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)


def encode(row):
    p = tok(prompt(row), add_special_tokens=False)["input_ids"]
    t = tok(row["target"] + tok.eos_token, add_special_tokens=False)["input_ids"][:OUT_TOK]
    return {"input_ids": p + t, "labels": [-100] * len(p) + t}


def collate(batch):
    # batch 1 (per_device_train_batch_size=1). Loss sirf headnote par lagta hai, isliye logits bhi sirf
    # aakhri hisse ke banao: poore 2600 token x 1.5 lakh shabd ke float32 logits ~3 GB (wahi OOM tha).
    assert len(batch) == 1
    b = batch[0]
    ids = torch.tensor([b["input_ids"]])
    keep = sum(1 for x in b["labels"] if x != -100) + 1
    return {"input_ids": ids, "labels": torch.tensor([b["labels"][-keep:]]),
            "attention_mask": torch.ones_like(ids), "logits_to_keep": keep}


all_train = lines("train.jsonl.gz")
TOTAL, OFF = len(all_train), prev["offset"]
train = [encode(json.loads(x)) for x in all_train[OFF:OFF + N_TRAIN]]
del all_train
test = [json.loads(x) for x in lines("test.jsonl.gz")[:N_EVAL]]
log(f"round {ROUND}: train {len(train)} (faisle {OFF}-{OFF + len(train)} / {TOTAL}), eval {len(test)}")
if not train:
    raise SystemExit("training data khatam: saare faisle sikhaye ja chuke")


def allowed(fn, kw):
    """Library ke naye/purane version: jo setting is version mein nahi, use chhod do (aur batao)."""
    ok = set(inspect.signature(fn).parameters)
    log(fn.__qualname__, "mein nahi:", [k for k in kw if k not in ok])
    return {k: v for k, v in kw.items() if k in ok}


model = AutoModelForCausalLM.from_pretrained(
    BASE, device_map={"": LOCAL}, torch_dtype=torch.float16,
    quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                           bnb_4bit_compute_dtype=torch.float16, bnb_4bit_use_double_quant=True))
GC = {"use_reentrant": False}
model = prepare_model_for_kbit_training(model, **allowed(prepare_model_for_kbit_training, dict(
    use_gradient_checkpointing=True, gradient_checkpointing_kwargs=GC)))
if ADAPTER:
    model = PeftModel.from_pretrained(model, ADAPTER, is_trainable=True)
    log("pichhla adapter:", ADAPTER)
else:
    model = get_peft_model(model, LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, task_type="CAUSAL_LM",
                                             target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                                                             "gate_proj", "up_proj", "down_proj"]))
if MAIN:
    model.print_trainable_parameters()


class Budget(TrainerCallback):
    """Samay ki seema par training roko; sab GPU ek hi step par ruken (warna ek intezaar mein atak jaata)."""

    def on_step_end(self, args, state, control, **kw):
        flag = torch.tensor([float(time.time() - T0 > TRAIN_SEC)], device=f"cuda:{LOCAL}")
        if dist.is_available() and dist.is_initialized():
            dist.all_reduce(flag, op=dist.ReduceOp.MAX)
        if flag.item():
            log(f"samay ki seema: step {state.global_step} par ruke")
            control.should_training_stop = True


accum = max(1, BATCH // WORLD)
steps = max(1, -(-len(train) // (accum * WORLD)))
args = TrainingArguments(**allowed(TrainingArguments.__init__, dict(
    output_dir=f"{OUT}/ckpt", per_device_train_batch_size=1, gradient_accumulation_steps=accum,
    num_train_epochs=1, learning_rate=2e-4 if ROUND == 1 else 1e-4, lr_scheduler_type="cosine",
    warmup_steps=max(1, int(steps * 0.03)), fp16=True, logging_steps=10, save_strategy="no", report_to=[],
    gradient_checkpointing=True, gradient_checkpointing_kwargs=GC, optim="paged_adamw_8bit", max_grad_norm=0.3,
    ddp_find_unused_parameters=False)))
trainer = Trainer(model=model, args=args, train_dataset=train, data_collator=collate, callbacks=[Budget()])
trainer.train()
trained = min(len(train), trainer.state.global_step * accum * WORLD)
log(f"training done: {trainer.state.global_step} step, {trained} faisle")
if not MAIN:  # jaanch sirf pehle GPU par
    sys.exit(0)
model.save_pretrained(f"{OUT}/adapter")

# Jaanch: test ke faislon par headnote likhwao (bina training wala model vs hamara model),
# court ke asli headnote se ROUGE-L. Har round wahi faisle, taaki round dar round tulna imaandaar ho.
model.eval()
model.config.use_cache = True
tok.padding_side = "left"
scorer = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=True)


def write(row):
    enc = tok(prompt(row), return_tensors="pt", add_special_tokens=False).to(model.device)
    with torch.no_grad():
        out = model.generate(**enc, max_new_tokens=OUT_TOK, do_sample=False, repetition_penalty=1.05, use_cache=True)
    return tok.decode(out[0][enc["input_ids"].shape[1]:], skip_special_tokens=True)


base_cache = prev.get("base", {})  # bina training wale model ke jawab badalte nahi; pehle round ke rakh lo
samples = []
for row in test:
    ours = write(row)
    if row["key"] not in base_cache:
        with model.disable_adapter():
            text = write(row)
        base_cache[row["key"]] = {"text": text[:1500],
                                  "score": round(scorer.score(row["target"], text)["rougeL"].fmeasure, 3)}
    b = base_cache[row["key"]]
    samples.append({"key": row["key"], "title": row["title"], "court": row["target"][:1500], "ours": ours[:1500],
                    "base": b["text"], "rougeL_ours": round(scorer.score(row["target"], ours)["rougeL"].fmeasure, 3),
                    "rougeL_base": b["score"]})
    log(row["key"], b["score"], "->", samples[-1]["rougeL_ours"])
mean = lambda k: round(sum(x[k] for x in samples) / max(len(samples), 1), 4)  # noqa: E731
summary = {"round": ROUND, "base_model": BASE, "trained": trained, "from": OFF, "to": OFF + trained, "total": TOTAL,
           "n_eval": len(samples), "rougeL_base": mean("rougeL_base"), "rougeL_ours": mean("rougeL_ours"),
           "gpus": WORLD, "seconds": round(time.time() - T0)}
json.dump(dict(summary, samples=samples), open(f"{OUT}/eval.json", "w"), ensure_ascii=False, indent=1)
json.dump({"round": ROUND, "offset": OFF + trained, "total": TOTAL, "base": base_cache,
           "history": prev.get("history", []) + [summary]},
          open(f"{OUT}/adapter/state.json", "w"), ensure_ascii=False, indent=1)
log("rougeL base", summary["rougeL_base"], "ours", summary["rougeL_ours"])
