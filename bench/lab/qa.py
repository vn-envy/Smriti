"""Blinded answer-quality evaluation on top of lab contexts.

Three stages, each a plain file so any reader/judge (a local model, an API,
or a human panel) can be plugged in:

1. ``export``  — build each system's context for the sampled questions,
   shuffle all (system, question) items together under opaque ids, and write
   reader batches (``batch_XX.jsonl``: id, question, question_date, context)
   plus a private key file mapping ids to system / question / gold answer.
2. *read*      — a reader answers every item of a batch from its context only
   and writes ``answers_XX.jsonl`` (id, answer). The reader never sees which
   system produced a context.
3. ``judge-export`` / ``score`` — judge batches (id, question, gold, answer;
   still blind to system) and the final scorer joining verdicts with the key:
   accuracy by system and category, paired McNemar tests and bootstrap CIs.

``python -m bench.lab.qa export --dataset locomo --split test --sample 200
--systems smriti,evidence,mem0 --out DIR``
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import statistics
import sys
from collections import defaultdict
from typing import Dict, List

READER_INSTRUCTIONS = """You are an assistant answering a question about a user, using ONLY the memory context provided.
- Today's date is {today}. Interpret relative time in the question against this date.
- Facts marked SUPERSEDED were true during their validity window but changed later; use CURRENT facts for present-tense questions and the validity windows for "as of <date>" / "before X" questions.
- Be concise and direct. Give the specific answer (name, number, date, item).
- If the memory context does not contain the answer, say exactly: "I don't have enough information to answer that."
"""

JUDGE_INSTRUCTIONS = """Grade whether the response answers the question correctly given the gold answer.
- Correct if it contains the gold answer's key information (paraphrase and extra detail are fine).
- Numbers, counts and dates must match in substance (a date off by a day is wrong unless the gold is approximate; a different count is wrong).
- If the gold answer lists several items, the response must contain all of them.
- A response that abstains ("I don't have enough information") is wrong unless the gold says the information is not available.
- A response that gives several conflicting candidate answers is wrong.
Output "yes" or "no"."""


def _opaque(seed: str, *parts) -> str:
    return hashlib.sha256("|".join([seed, *map(str, parts)]).encode()).hexdigest()[:10]


def export(argv=None):
    from .data import load_locomo, load_lmex, stratified
    from .run import LME_PATH, LOCOMO_PATH, in_split, make_system, split_systems
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", choices=["locomo", "lmex"], required=True)
    ap.add_argument("--split", default="test")
    ap.add_argument("--sample", type=int, default=200)
    ap.add_argument("--systems", required=True)
    ap.add_argument("--budget", type=int, default=9000)
    ap.add_argument("--batch", type=int, default=25)
    ap.add_argument("--seed", default="qa-v1")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    names = split_systems(a.systems)
    os.makedirs(a.out, exist_ok=True)
    if a.dataset == "locomo":
        cases = load_locomo(LOCOMO_PATH, categories=[1, 2, 3, 4])
    else:
        cases = load_lmex(LME_PATH, include_abstention=True)
    if a.split != "all":
        cases = [c for c in cases if in_split(a.dataset, c.case_id, a.split)]
    # stratified question sample across categories (deterministic)
    pairs = [(c, q) for c in cases for q in c.questions]
    by_cat: Dict[str, list] = defaultdict(list)
    for c, q in pairs:
        by_cat[q.category].append((c, q))
    for k in by_cat:
        by_cat[k].sort(key=lambda cq: _opaque(a.seed, cq[1].qid))
    chosen, i = [], 0
    cats = sorted(by_cat)
    while len(chosen) < min(a.sample, len(pairs)):
        for k in cats:
            if i < len(by_cat[k]) and len(chosen) < a.sample:
                chosen.append(by_cat[k][i])
        i += 1
    wanted: Dict[str, set] = defaultdict(set)
    for c, q in chosen:
        wanted[c.case_id].add(q.qid)
    items, key = [], {}
    for c in cases:
        if c.case_id not in wanted:
            continue
        qs = [q for q in c.questions if q.qid in wanted[c.case_id]]
        for name in names:
            sysm = make_system(name)
            sysm.build(c)
            for q in qs:
                _ranked, ctx = sysm.query(q, a.budget)
                iid = _opaque(a.seed, name, q.qid)
                items.append({"id": iid, "question": q.question,
                              "question_date": (q.question_date or "")[:10], "context": ctx})
                key[iid] = {"system": name, "qid": q.qid, "category": q.category,
                            "gold": q.answer, "abstention": q.abstention,
                            "question": q.question}
            if hasattr(sysm, "close"):
                sysm.close()
    random.Random(a.seed).shuffle(items)
    nb = 0
    for start in range(0, len(items), a.batch):
        with open(os.path.join(a.out, f"batch_{nb:02d}.jsonl"), "w") as f:
            for it in items[start:start + a.batch]:
                f.write(json.dumps(it) + "\n")
        nb += 1
    with open(os.path.join(a.out, "key.json"), "w") as f:
        json.dump({"dataset": a.dataset, "split": a.split, "systems": names,
                   "budget": a.budget, "n_questions": len(chosen), "items": key}, f, indent=1)
    with open(os.path.join(a.out, "READER.md"), "w") as f:
        f.write(READER_INSTRUCTIONS)
    print(f"wrote {len(items)} items in {nb} batches for {len(chosen)} questions -> {a.out}")


def export_fullctx(argv=None):
    """Full-conversation reference (LoCoMo): one file per conversation holding
    the whole dated transcript once plus the same sampled questions, so a
    reader can answer them all from the complete history. Items reuse the
    ``fullctx`` system name in the key of an existing export directory."""
    from .data import load_locomo
    from .run import LOCOMO_PATH
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="existing export dir (reads its key.json)")
    ap.add_argument("--seed", default="qa-v1")
    a = ap.parse_args(argv)
    meta = json.load(open(os.path.join(a.dir, "key.json")))
    if meta["dataset"] != "locomo":
        raise SystemExit("full-context reference is only built for LoCoMo")
    qids = {m["qid"] for m in meta["items"].values()}
    cases = {c.case_id: c for c in load_locomo(LOCOMO_PATH, categories=[1, 2, 3, 4])}
    n = 0
    for cid, c in sorted(cases.items()):
        qs = [q for q in c.questions if q.qid in qids]
        if not qs:
            continue
        lines = []
        for sess in c.sessions:
            lines.append(f"[Session {(sess.ts or '?')[:16].replace('T', ' ')}]")
            lines.extend("  " + t.content for t in sess.turns)
        doc = {"conversation": "\n".join(lines), "question_date": (qs[0].question_date or "")[:10],
               "questions": []}
        for q in qs:
            iid = _opaque(a.seed, "fullctx", q.qid)
            doc["questions"].append({"id": iid, "question": q.question})
            meta["items"][iid] = {"system": "fullctx", "qid": q.qid, "category": q.category,
                                  "gold": q.answer, "abstention": q.abstention,
                                  "question": q.question}
        with open(os.path.join(a.dir, f"fullctx_{n:02d}.json"), "w") as f:
            json.dump(doc, f, indent=1)
        n += 1
    if "fullctx" not in meta["systems"]:
        meta["systems"].append("fullctx")
    with open(os.path.join(a.dir, "key.json"), "w") as f:
        json.dump(meta, f, indent=1)
    print(f"wrote {n} full-context conversation files")


def judge_export(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--batch", type=int, default=60)
    a = ap.parse_args(argv)
    key = json.load(open(os.path.join(a.dir, "key.json")))["items"]
    answers = _load_answers(a.dir)
    rows = []
    for iid, meta in key.items():
        if iid in answers:
            rows.append({"id": iid, "question": meta["question"], "gold": meta["gold"],
                         "response": answers[iid]})
    rows.sort(key=lambda r: _opaque("judge", r["id"]))
    nb = 0
    for start in range(0, len(rows), a.batch):
        with open(os.path.join(a.dir, f"judge_{nb:02d}.jsonl"), "w") as f:
            for r in rows[start:start + a.batch]:
                f.write(json.dumps(r) + "\n")
        nb += 1
    with open(os.path.join(a.dir, "JUDGE.md"), "w") as f:
        f.write(JUDGE_INSTRUCTIONS)
    print(f"wrote {len(rows)} judge rows in {nb} batches; missing answers: {len(key) - len(rows)}")


def _load_jsonl_glob(d: str, prefix: str) -> Dict[str, dict]:
    out = {}
    for fn in sorted(os.listdir(d)):
        if fn.startswith(prefix) and fn.endswith(".jsonl"):
            for line in open(os.path.join(d, fn)):
                line = line.strip()
                if line:
                    row = json.loads(line)
                    out[row["id"]] = row
    return out


def _load_answers(d: str) -> Dict[str, str]:
    return {k: str(v.get("answer", "")) for k, v in _load_jsonl_glob(d, "answers_").items()}


ABSTAIN = ("don't have enough information", "do not have enough information",
           "not enough information", "no information")


def _mcnemar(b: int, c: int) -> float:
    """Exact two-sided McNemar p-value on discordant counts."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def score(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    meta = json.load(open(os.path.join(a.dir, "key.json")))
    key = meta["items"]
    answers = _load_answers(a.dir)
    verdicts = {k: str(v.get("verdict", "")).strip().lower()
                for k, v in _load_jsonl_glob(a.dir, "verdicts_").items()}
    per: Dict[str, Dict[str, bool]] = defaultdict(dict)
    rows = []
    for iid, m in key.items():
        ans = answers.get(iid)
        if m["abstention"]:
            ok = ans is not None and any(t in ans.lower() for t in ABSTAIN)
        else:
            ok = verdicts.get(iid) == "yes"
        per[m["system"]][m["qid"]] = ok
        rows.append({**m, "id": iid, "answer": ans, "verdict": verdicts.get(iid), "correct": ok})
    systems = meta["systems"]
    report = {"dataset": meta["dataset"], "split": meta["split"], "budget": meta["budget"],
              "n_questions": meta["n_questions"], "systems": {}, "pairs": {}}
    cats = sorted({m["category"] for m in key.values()})
    rng = random.Random(7)
    for s in systems:
        vals = per[s]
        cat_acc = {}
        for c in cats:
            qs = [m["qid"] for m in key.values() if m["system"] == s and m["category"] == c]
            if qs:
                cat_acc[c] = round(sum(vals[q] for q in qs) / len(qs), 4)
        qids = sorted(vals)
        acc = sum(vals.values()) / max(1, len(vals))
        boots = []
        for _ in range(2000):
            sample = [vals[qids[rng.randrange(len(qids))]] for _ in qids]
            boots.append(sum(sample) / len(sample))
        boots.sort()
        report["systems"][s] = {
            "accuracy": round(acc, 4), "n": len(vals),
            "missing_answers": sum(1 for iid, m in key.items() if m["system"] == s and iid not in answers),
            "ci95": [round(boots[50], 4), round(boots[1949], 4)], "by_category": cat_acc}
    for i, s1 in enumerate(systems):
        for s2 in systems[i + 1:]:
            common = sorted(set(per[s1]) & set(per[s2]))
            b = sum(1 for q in common if per[s1][q] and not per[s2][q])
            c = sum(1 for q in common if per[s2][q] and not per[s1][q])
            report["pairs"][f"{s1} vs {s2}"] = {"only_first": b, "only_second": c,
                                                "mcnemar_p": round(_mcnemar(b, c), 5)}
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=1))
    if a.out:
        report["rows"] = rows
        with open(a.out, "w") as f:
            json.dump(report, f, indent=1)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    rest = sys.argv[2:]
    {"export": export, "export-fullctx": export_fullctx, "judge-export": judge_export,
     "score": score}.get(
        cmd, lambda _r: sys.exit("usage: python -m bench.lab.qa export|judge-export|score ..."))(rest)
