"""Round 2, step 2: train relevance heads on dev pairs, evaluate on held-out test pairs.

Heads (L2 logistic regression; C picked by 5-fold CV grouped by question on dev):
  smriti  - Smriti's own signals: fused score, score/top, rank, is-assistant, log length
  laya    - frozen Laya-family encoder features (768-d mean pool of question+memory)
  both    - the two together
Reports per-question AUC (questions with both classes), top-1 hit rate and
recall@5 within the top-20 pool, next to Smriti's raw fused order.
Saves each head to OUT_DIR/head_<name>.npz for the lab reranker.
"""
import json
import sys

import numpy as np
import torch

torch.set_num_threads(4)
D = sys.argv[1]
dev, test = np.load(f"{D}/dev.npz"), np.load(f"{D}/test.npz")
SM_COLS = [0, 1, 2, 3, 4]          # drop the constant "rerank channel" column


def feats(z, kind):
    parts = []
    if kind in ("smriti", "both"):
        parts.append(z["X_s"][:, SM_COLS].astype(np.float32))
    if kind in ("laya", "both"):
        parts.append(z["X_enc"].astype(np.float32))
    return np.concatenate(parts, axis=1)


def fit(X, y, l2):
    Xt, yt = torch.tensor(X), torch.tensor(y, dtype=torch.float32)
    w = torch.zeros(X.shape[1], requires_grad=True)
    b = torch.zeros(1, requires_grad=True)
    pos = max(1.0, float(yt.sum()))
    pw = torch.tensor((len(yt) - pos) / pos)        # balance classes
    opt = torch.optim.LBFGS([w, b], lr=0.5, max_iter=300, line_search_fn="strong_wolfe")

    def closure():
        opt.zero_grad()
        loss = torch.nn.functional.binary_cross_entropy_with_logits(Xt @ w + b, yt, pos_weight=pw) \
            + l2 * (w * w).sum()
        loss.backward()
        return loss
    opt.step(closure)
    return w.detach().numpy(), float(b.detach())


def per_question(score, y, qid):
    aucs, top1, r5 = [], [], []
    for q in np.unique(qid):
        m = qid == q
        s, t = score[m], y[m]
        if t.sum() == 0:
            continue
        order = np.argsort(-s, kind="stable")
        top1.append(float(t[order[0]]))
        r5.append(float(t[order[:5]].sum() / t.sum()))
        if t.sum() < len(t):
            pos, neg = s[t == 1], s[t == 0]
            aucs.append(float(((pos[:, None] > neg[None, :]) + 0.5 * (pos[:, None] == neg[None, :])).mean()))
    return {"auc": round(float(np.mean(aucs)), 4), "top1": round(float(np.mean(top1)), 4),
            "recall@5_of_pool": round(float(np.mean(r5)), 4), "n_q": len(top1)}


report = {"smriti_fused_order": {"dev": per_question(-dev["X_s"][:, 2], dev["y"], dev["qid"]),
                                 "test": per_question(-test["X_s"][:, 2], test["y"], test["qid"])}}
for kind in ("smriti", "laya", "both"):
    Xd, Xt = feats(dev, kind), feats(test, kind)
    mu, sd = Xd.mean(0), Xd.std(0) + 1e-6
    Xd, Xt = (Xd - mu) / sd, (Xt - mu) / sd
    y, qid = dev["y"].astype(np.float32), dev["qid"]
    uq = np.unique(qid)
    rng = np.random.default_rng(0)
    fold = dict(zip(uq, rng.permutation(len(uq)) % 5))
    folds = np.array([fold[q] for q in qid])
    best = None
    for l2 in (1e-4, 1e-3, 1e-2, 1e-1):
        oof = np.zeros(len(y))
        for f in range(5):
            tr, va = folds != f, folds == f
            w, b = fit(Xd[tr], y[tr], l2)
            oof[va] = Xd[va] @ w + b
        cv = per_question(oof, dev["y"], qid)["auc"]
        if best is None or cv > best[0]:
            best = (cv, l2)
    w, b = fit(Xd, y, best[1])
    test_scores = Xt @ w + b
    report[kind] = {"cv_auc_dev": best[0], "l2": best[1],
                    "test": per_question(test_scores, test["y"], test["qid"])}
    np.savez(f"{D}/head_{kind}.npz", w=w, b=b, mu=mu, sd=sd, kind=kind, sm_cols=np.array(SM_COLS))
print(json.dumps(report, indent=1))
json.dump(report, open(f"{D}/report.json", "w"), indent=1)
