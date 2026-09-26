# Candidate pools (rounds 3–4)

Smriti 0.4.1's top 20 episode hits for every LME-X question in the dev (256)
and held-out test (244) splits: the exact lists a reranker judges. One JSON
object per line: `qid`, `category`, `question`, `docs` (full candidate texts),
`gold` (1 = an evidence turn), `X_s` (Smriti's per-candidate signals: fused
score, score / top, rank, is-assistant, log length, rerank channel).

Made by `bench/lab/judge_head/export_pools.py` at commit 14f1215. They
reproduce round 3 exactly: replaying the round 3 Jev cache over these pools
gives AUC 0.953 (dev) and 0.954 (test) with every score a cache hit. Texts are
LongMemEval (MIT) conversation turns. Used by the Colab notebooks in
`bench/lab/colab/`.
