"""Round 2, step 1: frozen Laya-family encoder features for (question, candidate) pairs.

For every LME-X question in a split, rebuild Smriti's top-20 candidates exactly as the
evidence engine ranks them (the reranker's pool), then encode each "question [SEP] memory"
pair once with the Laya-family encoder (mean-pooled last hidden state, 768-d).
Also records Smriti's own signals per candidate and the gold label.

Usage: extract.py SPLIT OUT_DIR [LIMIT]
Writes OUT_DIR/SPLIT.npz plus OUT_DIR/SPLIT.progress.json while running.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
import numpy as np  # noqa: E402
import torch  # noqa: E402

torch.set_num_threads(4)
import laya  # noqa: E402
from bench.lab.data import load_lmex  # noqa: E402
from bench.lab.run import LME_PATH, in_split  # noqa: E402
from bench.lab.systems import SmritiSystem  # noqa: E402
from smriti import RetrievalProfile  # noqa: E402
from smriti.recall import RecallConfig  # noqa: E402

MODEL = os.environ.get("SMRITI_LAB_LAYA")
split, out_dir = sys.argv[1], sys.argv[2]
limit = int(sys.argv[3]) if len(sys.argv) > 3 else 0
DEPTH, MAX_TOK, MAX_CHARS = 20, 384, 1500

agent = laya.load(MODEL, device="cpu")
enc, tok = agent.model.encoder, agent.tok
enc.eval()

cases = [c for c in load_lmex(LME_PATH) if in_split("lmex", c.case_id, split)]
if limit:
    cases = cases[:limit]
prof = RetrievalProfile(name="r2", engine="evidence", recall=RecallConfig())
rows_enc, rows_s, ys, qids, cats = [], [], [], [], []
prog = os.path.join(out_dir, f"{split}.progress.json")
t0 = time.time()
n_pairs = 0


@torch.no_grad()
def encode(question, texts):
    batch = tok([question] * len(texts), [t[:MAX_CHARS] for t in texts], truncation="only_second",
                max_length=MAX_TOK, padding=True, return_tensors="pt")
    hid = enc(input_ids=batch["input_ids"], attention_mask=batch["attention_mask"]).last_hidden_state
    m = batch["attention_mask"].unsqueeze(-1).float()
    return ((hid * m).sum(1) / m.sum(1)).numpy()


for qi, case in enumerate(cases):
    for q in case.questions:
        sysm = SmritiSystem("r2", search_kw={"profile": prof}, context_kw={"profile": prof})
        sysm.build(case)
        hits = [h for h in sysm.mem.search(q.question, k=DEPTH, now=q.question_date, profile=prof)
                if h.kind == "episode"][:DEPTH]
        if not hits:
            sysm.close()
            continue
        gold = set(q.evidence_turns)
        top = hits[0].score or 1.0
        feats = encode(q.question, [h.text for h in hits])
        for i, h in enumerate(hits):
            rows_enc.append(feats[i].astype(np.float16))
            rows_s.append([h.score, h.score / top, i, float(h.role == "assistant"),
                           float(np.log1p(len(h.text))), float("rerank" in h.channels)])
            ys.append(int(sysm.ep2turn.get(h.id) in gold))
            qids.append(q.qid)
            cats.append(q.category)
        n_pairs += len(hits)
        sysm.close()
    if qi % 5 == 0 or qi == len(cases) - 1:
        json.dump({"split": split, "done": qi + 1, "total": len(cases), "pairs": n_pairs,
                   "elapsed_s": round(time.time() - t0, 1)}, open(prog, "w"))

np.savez_compressed(os.path.join(out_dir, f"{split}.npz"), X_enc=np.stack(rows_enc),
                    X_s=np.array(rows_s, dtype=np.float32), y=np.array(ys, dtype=np.int8),
                    qid=np.array(qids), cat=np.array(cats))
print(f"{split}: {len(cases)} questions, {n_pairs} pairs, {sum(ys)} positives, "
      f"{time.time() - t0:.0f}s ({1000 * (time.time() - t0) / max(1, n_pairs):.0f} ms/pair)")
