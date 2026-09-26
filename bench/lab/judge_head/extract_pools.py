"""Round 2 features from exported pools: ``extract.py`` without rebuilding Smriti.

Encodes every (question, candidate) pair of ``pools-dev`` / ``pools-test``
(``export_pools.py``) with a frozen Laya encoder (mean-pooled last hidden
state of "question [SEP] memory", 384 tokens, as ``extract.py``), on a GPU when
there is one, in fp32. Writes, into OUT_DIR:

* ``dev.npz`` / ``test.npz`` in ``extract.py``'s format, for ``train.py``;
* ``feat-cache.sqlite`` in ``LearnedHeadReranker``'s format, so an end-to-end
  lab run on a CPU box reuses the GPU encodings;
* ``timing.json``: encoder milliseconds per question (20 pairs, one batch).

Usage: extract_pools.py POOLS_DIR OUT_DIR [--model ID_OR_DIR] [--revision REV] [--device cuda]
"""
import argparse
import gzip
import hashlib
import json
import os
import sqlite3
import time

import numpy as np
import torch
import laya

ap = argparse.ArgumentParser()
ap.add_argument("pools_dir")
ap.add_argument("out_dir")
ap.add_argument("--model", default="convaiinnovations/laya")
ap.add_argument("--revision", default=None, help="hub revision to pin (downloads a snapshot)")
ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
ap.add_argument("--splits", default="dev,test")
a = ap.parse_args()
MAX_TOK, MAX_CHARS = 384, 1500
os.makedirs(a.out_dir, exist_ok=True)

model = a.model
if a.revision and not os.path.isdir(model):
    from huggingface_hub import snapshot_download
    model = snapshot_download(model, revision=a.revision,
                              allow_patterns=["model.safetensors", "rl_agent_config.json",
                                              "encoder/*", "tokenizer/*"])
agent = laya.load(model, device=a.device)
enc, tok = agent.model.encoder, agent.tok
enc.eval().float()
dev = next(enc.parameters()).device

db = sqlite3.connect(os.path.join(a.out_dir, "feat-cache.sqlite"))
db.execute("CREATE TABLE IF NOT EXISTS feat(k TEXT PRIMARY KEY, v BLOB)")


@torch.no_grad()
def encode(question, texts):
    batch = tok([question] * len(texts), [t[:MAX_CHARS] for t in texts], truncation="only_second",
                max_length=MAX_TOK, padding=True, return_tensors="pt")
    ids, mask = batch["input_ids"].to(dev), batch["attention_mask"].to(dev)
    hid = enc(input_ids=ids, attention_mask=mask).last_hidden_state
    m = mask.unsqueeze(-1).float()
    return ((hid * m).sum(1) / m.sum(1)).float().cpu().numpy()


timing = {"device": str(dev), "gpu": torch.cuda.get_device_name(0) if dev.type == "cuda" else "",
          "model": a.model, "revision": a.revision, "splits": {}}
for split in a.splits.split(","):
    pools = [json.loads(line) for line in
             gzip.open(os.path.join(a.pools_dir, f"pools-{split}.jsonl.gz"), "rt", encoding="utf-8")]
    X_enc, X_s, ys, qids, cats, ms = [], [], [], [], [], []
    t0 = time.time()
    for i, p in enumerate(pools):
        if dev.type == "cuda":
            torch.cuda.synchronize()
        t = time.perf_counter()
        vecs = encode(p["question"], p["docs"])
        ms.append(1000 * (time.perf_counter() - t))
        v16 = vecs.astype(np.float16)
        db.executemany("INSERT OR REPLACE INTO feat VALUES (?, ?)",
                       [(hashlib.sha1(f"{p['question']}\x00{d}".encode()).hexdigest(), v16[j].tobytes())
                        for j, d in enumerate(p["docs"])])
        X_enc.extend(v16)
        X_s.extend(p["X_s"])
        ys.extend(p["gold"])
        qids.extend([p["qid"]] * len(p["docs"]))
        cats.extend([p["category"]] * len(p["docs"]))
        if i % 10 == 0 or i == len(pools) - 1:
            db.commit()
            json.dump({"split": split, "done": i + 1, "total": len(pools), "pairs": len(ys),
                       "elapsed_s": round(time.time() - t0, 1)},
                      open(os.path.join(a.out_dir, f"{split}.progress.json"), "w"))
    np.savez_compressed(os.path.join(a.out_dir, f"{split}.npz"), X_enc=np.stack(X_enc),
                        X_s=np.array(X_s, dtype=np.float32), y=np.array(ys, dtype=np.int8),
                        qid=np.array(qids), cat=np.array(cats))
    warm = sorted(ms[3:] or ms)                    # skip CUDA warm-up batches
    timing["splits"][split] = {"questions": len(pools), "pairs": len(ys),
                               "ms_per_question_p50": round(warm[len(warm) // 2], 1),
                               "ms_per_question_p95": round(warm[int(0.95 * (len(warm) - 1))], 1),
                               "wall_s": round(time.time() - t0, 1)}
    print(split, json.dumps(timing["splits"][split]))
db.commit()
json.dump(timing, open(os.path.join(a.out_dir, "timing.json"), "w"), indent=1)
