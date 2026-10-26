# Nyay model: Qwen2.5-7B-Instruct par QLoRA (Kaggle, free T4 GPU). Teen tarah ka data (NYAY_DATA dataset):
#   padhai    : faisle shuru se ant tak, kram se (index.json; scripts/build_padhai.py) — har agla shabd sikhna
#   headnote  : SC faisla -> court ka headnote (scripts/build_train_data.py)
#   vargikaran: faisla -> shreni / vishay / mudda / nateeja (scripts/build_train_hc.py)
# Ek round: pichhle round ka adapter (Kaggle dataset <user>/nyay-model, agar hai) lo, data ka agla hissa sikhao,
# samay ki seema par ruko, phir jaanch. kaggle/train/launch.py ise dono GPU par chalata hai (torchrun);
# .github/workflows/kaggle-train.yml round ke baad agla round, aur ek data khatam to plan ka agla data.
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
from torch.utils.data import SequentialSampler
from transformers import (AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, Trainer, TrainerCallback,
                          TrainingArguments)

BASE = "Qwen/Qwen2.5-7B-Instruct"
OUT = "/kaggle/working"
T0 = float(os.environ.get("NYAY_T0") or time.time())
ROUND = int(os.environ.get("NYAY_ROUND", "1"))
V1 = "krishivlaw/nyay-train-v1"
DATA = os.environ.get("NYAY_DATA") or V1
N_TRAIN = int(os.environ.get("NYAY_N_TRAIN", "18000"))    # round mein zyada se zyada; samay ki seema pehle aa sakti hai
HN_MIX = 0.05   # padhai mein itne headnote jode bhi (sirf padhne se model headnote likhna bhoolta hai: round 7 mein 0.25 -> 0.11)
N_EVAL = int(os.environ.get("NYAY_N_EVAL", "20"))         # headnote (har round wahi 20)
N_EVAL_V = int(os.environ.get("NYAY_N_EVAL_V", "150"))    # vargikaran
TRAIN_SEC = float(os.environ.get("NYAY_TRAIN_HOURS", "9")) * 3600  # Kaggle session 12 ghante; jaanch ke liye jagah
IN_TOK, OUT_TOK, LM_TOK, V_TOK = 2000, 512, 1024, 128
BATCH = 16                                                 # ek optimizer step mein kitne faisle (sab GPU milakar)
LOCAL = int(os.environ.get("LOCAL_RANK", "0"))
WORLD = int(os.environ.get("WORLD_SIZE", "1"))
MAIN = LOCAL == 0
SYSTEM = ("Aap Indian Supreme Court ke faislon ke headnote likhne wale anubhavi reporter hain. Faisle ka text padh "
          "kar Supreme Court Reports ke format mein headnote likhiye: vishay (Act, section), tathya, mudda, "
          "'Held:' ke point, aur kaunse purane faisle relied on / distinguished hue. Sirf faisle mein likhi baat; "
          "apni taraf se koi citation ya tathya mat jodiye.")
TASKS = {
    "headnote": (SYSTEM, "Iska headnote likhiye."),
    "vargikaran": ("Aap Indian adalaton (Supreme Court, Nainital High Court) ke faislon ki chhantai karne wale anubhavi "
                   "vakeel hain. Faisla padh kar in panktiyon mein likhiye: 'Shreni:', 'Vishay:' (vishay > upvishay, "
                   "';' se alag), 'Mudda:' (ho to), 'Nateeja:'. Sirf faisle se.",
                   "Is faisle ki shreni, vishay, mudda aur nateeja batayiye."),
}


def log(*a):
    if MAIN:
        print(*a, f"[{time.time() - T0:.0f}s]", flush=True)


if not torch.cuda.is_available():
    raise SystemExit("GPU nahi mila: Kaggle account phone se verify karo aur notebook mein GPU on karo")
log("GPU:", [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())], "processes:", WORLD)

# Kaggle .gz ko kabhi khol deta hai (train.jsonl), kabhi waise hi rakhta hai; dono chalein
FILES = {f: os.path.join(r, f) for r, _, fs in os.walk("/kaggle/input") for f in fs}
INDEX = json.load(open(FILES["index.json"])) if "index.json" in FILES else None
MODE = "padhai" if INDEX and INDEX.get("kind") == "padhai" else "kaam"
if MODE == "kaam" and not any(k.startswith("train.jsonl") for k in FILES):
    raise SystemExit("train.jsonl / index.json nahi mila. /kaggle/input mein: " + ", ".join(sorted(FILES)[:50]))

# Pichhla round: adapter + state.json (pehle round mein nahi hote)
prev = json.load(open(FILES["state.json"])) if "state.json" in FILES else {"round": 0, "offset": 0}
if prev["round"] != ROUND - 1:  # Kaggle ne purana version diya to us par training mat karo
    raise SystemExit(f"round {ROUND} ke liye round {ROUND - 1} ka adapter chahiye, mila round {prev['round']}")
ADAPTER = os.path.dirname(FILES["adapter_config.json"]) if ROUND > 1 else None


def lines(name, shuffle=True):
    path = FILES.get(name) or FILES[name.replace(".gz", "")]
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        rows = f.readlines()
    if shuffle:
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
    system, ask = TASKS[row.get("task", "headnote")]
    msgs = [{"role": "system", "content": system},
            {"role": "user", "content": "Faisla:\n" + clip(row["input"], row.get("in_tok", IN_TOK)) + "\n\n" + ask}]
    return tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)


def encode(row):
    if "text" in row:  # padhai: poore tukde par
        ids = tok(row["text"] + tok.eos_token, add_special_tokens=False)["input_ids"][:LM_TOK]
        return {"input_ids": ids, "labels": list(ids)}
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
    if keep > len(b["labels"]):  # padhai: har token par loss
        return {"input_ids": ids, "labels": torch.tensor([b["labels"]]), "attention_mask": torch.ones_like(ids)}
    return {"input_ids": ids, "labels": torch.tensor([b["labels"][-keep:]]),
            "attention_mask": torch.ones_like(ids), "logits_to_keep": keep}


# Har data kahan tak padha (plan mein ek data do hisson mein: SC Constitution Bench, phir HC, phir SC baaki)
OFFSETS = dict(prev.get("offsets") or {})
OFFSETS.setdefault(prev.get("data", V1), prev["offset"])
FROM = os.environ.get("NYAY_FROM", "")   # plan ka "from": is daur mein data shuru se/yahan se (jaise kaam dobara)
if prev.get("data", V1) == DATA:
    OFF = prev["offset"]
elif FROM.isdigit():
    OFF = int(FROM)
else:
    OFF = OFFSETS.get(DATA, 0)
UPTO = int(os.environ.get("NYAY_UPTO") or 0)   # plan ka "upto": daur yahan tak (jaise SC sirf 5+ judge)
END = min(OFF + N_TRAIN, UPTO) if UPTO else OFF + N_TRAIN
n_replay = 0
if MODE == "padhai":
    # kram se (bade bench pehle): jin shard mein [OFF, OFF+N) aata hai wahi kholo; 10% pichhle padhe hisse se
    TOTAL, SH = INDEX["chunks"], INDEX["shard"]
    raw = []
    for k in range(OFF // SH, min(INDEX["shards"], -(-END // SH))):
        part = lines(f"padhai-{k + 1:05d}.jsonl.gz", shuffle=False)
        raw += part[max(0, OFF - k * SH):END - k * SH]
    rng = random.Random(ROUND)
    if OFF >= SH:
        old = lines(f"padhai-{rng.randrange(OFF // SH) + 1:05d}.jsonl.gz", shuffle=False)
        replay = rng.sample(old, min(len(old), len(raw) // 10))
        n_replay = len(replay)
        mixed = []   # har 10 naye tukdon ke baad ek purana (samay ki seema beech mein aaye to bhi mila-jula)
        for j, x in enumerate(raw):
            mixed.append(x)
            if j % 10 == 9 and replay:
                mixed.append(replay.pop())
        raw = mixed + replay
    if any(k.startswith("headnote.jsonl") for k in FILES):   # headnote ke jode bhi beech-beech mein (bhoole nahi)
        hn = lines("headnote.jsonl.gz", shuffle=False)
        hn = random.Random(1000 + ROUND).sample(hn, min(len(hn), int(len(raw) * HN_MIX)))
        n_replay += len(hn)
        step = max(1, len(raw) // max(1, len(hn)))
        mixed = []
        for j, x in enumerate(raw):
            mixed.append(x)
            if j % step == step - 1 and hn:
                mixed.append(hn.pop())
        raw = mixed + hn
    train = [encode(json.loads(x)) for x in raw]
    del raw
    stages = [s["stage"] for s in INDEX["stages"] if s["from"] <= OFF]
    log(f"round {ROUND}: padhai {INDEX['court']} ({stages[-1] if stages else '?'}): tukde {OFF}-{OFF + len(train) - n_replay}"
        f" / {TOTAL}, dobara {n_replay}")
else:
    all_train = lines("train.jsonl.gz")
    TOTAL = len(all_train)
    train = [encode(json.loads(x)) for x in all_train[OFF:END]]
    del all_train
    log(f"round {ROUND}: train {len(train)} ({OFF}-{OFF + len(train)} / {TOTAL})")
# jaanch: headnote ke wahi 1000 (v1 wale kram mein) -> Random(7) se wahi 20 har daur mein; vargikaran alag
tests = lines("test.jsonl.gz", shuffle=False) if any(k.startswith("test.jsonl") for k in FILES) else []
test = [x for x in tests if '"task": "vargikaran"' not in x]
test_v = [x for x in tests if '"task": "vargikaran"' in x]
random.Random(7).shuffle(test)
random.Random(7).shuffle(test_v)
test = [json.loads(x) for x in test[:N_EVAL]]
test_v = [json.loads(x) for x in test_v[:N_EVAL_V]]
evals = [json.loads(x) for x in lines("eval.jsonl.gz", shuffle=False)] if "eval.jsonl.gz" in FILES or \
    "eval.jsonl" in FILES else []
del tests
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
    num_train_epochs=1, learning_rate=float(os.environ.get("NYAY_LR") or (2e-4 if ROUND == 1 else 1e-4)),
    lr_scheduler_type="cosine",
    warmup_steps=max(1, int(steps * 0.03)), fp16=True, logging_steps=10, save_strategy="no", report_to=[],
    gradient_checkpointing=True, gradient_checkpointing_kwargs=GC, optim="paged_adamw_8bit", max_grad_norm=0.3,
    ddp_find_unused_parameters=False)))
class KramTrainer(Trainer):
    """Padhai mein kram se (bade bench pehle; samay ki seema par jitna padha, agla round wahin se)."""

    def _get_train_sampler(self, *a, **kw):
        return SequentialSampler(self.train_dataset) if MODE == "padhai" else super()._get_train_sampler(*a, **kw)


trainer = KramTrainer(model=model, args=args, train_dataset=train, data_collator=collate, callbacks=[Budget()])
trainer.train()
seen = min(len(train), trainer.state.global_step * accum * WORLD)
trained = round(seen * (len(train) - n_replay) / len(train))   # naye (dobara wale nahi) — agla round yahan se
log(f"training done: {trainer.state.global_step} step, {seen} ({trained} naye)")
if not MAIN:  # jaanch sirf pehle GPU par
    sys.exit(0)
model.save_pretrained(f"{OUT}/adapter")

# Jaanch: test ke faislon par headnote likhwao (bina training wala model vs hamara model),
# court ke asli headnote se ROUGE-L. Har round wahi faisle, taaki round dar round tulna imaandaar ho.
model.eval()
model.config.use_cache = True
tok.padding_side = "left"
scorer = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=True)


def write(row, n=OUT_TOK):
    enc = tok(prompt(row), return_tensors="pt", add_special_tokens=False).to(model.device)
    with torch.no_grad():
        out = model.generate(**enc, max_new_tokens=n, do_sample=False, repetition_penalty=1.05, use_cache=True)
    return tok.decode(out[0][enc["input_ids"].shape[1]:], skip_special_tokens=True)


def fields(text):
    """'Shreni: X / Vishay: a > b; c > d / Nateeja: Y' -> {'shreni', 'vishay' [upvishay], 'nateeja'}."""
    d = {}
    for line in text.splitlines():
        k, _, v = line.partition(":")
        d[k.strip().lower()] = v.strip()
    return {"shreni": d.get("shreni", ""), "nateeja": d.get("nateeja", ""),
            "vishay": [x.split(">")[-1].strip() for x in d.get("vishay", "").split(";") if x.strip()]}


def marks(gold, text):
    f = fields(text)
    return {"shreni": f["shreni"] == gold["shreni"], "nateeja": f["nateeja"] == gold["nateeja"],
            "vishay": bool(f["vishay"]) and f["vishay"][0] in gold["vishay"]}


def lm_loss(text):
    ids = tok(text, return_tensors="pt", add_special_tokens=False)["input_ids"][:, :LM_TOK].to(model.device)
    with torch.no_grad():
        return model(input_ids=ids, labels=ids).loss.item()


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
v_samples = []
for row in test_v:  # vargikaran: shreni / pehla vishay / nateeja sahi?
    ours = write(row, V_TOK)
    ck = "v:" + row["key"]
    if ck not in base_cache:
        with model.disable_adapter():
            base_cache[ck] = marks(row["gold"], write(row, V_TOK))
    v_samples.append({"key": row["key"], "court": row["court"], "gold": row["target"], "ours": ours[:400],
                      "marks": marks(row["gold"], ours), "base": base_cache[ck]})
ppl = []
for row in evals:  # padhai: na padhe faislon ke tukdon par loss (kam = model kanoon ki bhasha behtar samajhta)
    ck = "p:" + row["key"]
    if ck not in base_cache:
        with model.disable_adapter():
            base_cache[ck] = round(lm_loss(row["text"]), 4)
    ppl.append((base_cache[ck], lm_loss(row["text"])))
mean = lambda k: round(sum(x[k] for x in samples) / max(len(samples), 1), 4)  # noqa: E731
summary = {"round": ROUND, "data": DATA, "mode": MODE, "base_model": BASE, "trained": trained, "from": OFF,
           "to": OFF + trained, "total": TOTAL, "n_eval": len(samples), "rougeL_base": mean("rougeL_base"),
           "rougeL_ours": mean("rougeL_ours"), "gpus": WORLD, "seconds": round(time.time() - T0)}
if MODE == "padhai":
    summary["stage"] = ([s["stage"] for s in INDEX["stages"] if s["from"] <= OFF] or ["?"])[-1]
if v_samples:
    for who in ("ours", "base"):
        for k in ("shreni", "vishay", "nateeja"):
            got = [x["marks"][k] if who == "ours" else x["base"][k] for x in v_samples]
            summary[f"sahi_{k}_{who}"] = round(sum(got) / len(got), 3)
    summary["n_eval_v"] = len(v_samples)
if ppl:
    summary["loss_base"] = round(sum(b for b, _ in ppl) / len(ppl), 4)
    summary["loss_ours"] = round(sum(o for _, o in ppl) / len(ppl), 4)
json.dump(dict(summary, samples=samples, v_samples=v_samples[:40]), open(f"{OUT}/eval.json", "w"),
          ensure_ascii=False, indent=1)
OFFSETS[DATA] = OFF + trained
json.dump({"round": ROUND, "data": DATA, "offset": OFF + trained, "total": TOTAL, "offsets": OFFSETS, "base": base_cache,
           "history": prev.get("history", []) + [summary]},
          open(f"{OUT}/adapter/state.json", "w"), ensure_ascii=False, indent=1)
log({k: v for k, v in summary.items() if k not in ("base_model",)})
