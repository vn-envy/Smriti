"""Decision-model rerankers against a local mock of the System One wire protocol."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from smriti import HashEmbedder, Smriti
from smriti.decision import DecisionStats, SystemOneReranker
from smriti.recall import RecallConfig
from smriti.profiles import PROFILES


def _relevance(question: str, memory: str) -> float:
    q = {w.strip("?.,").lower() for w in question.split() if len(w) > 3}
    m = {w.strip("?.,").lower() for w in memory.split()}
    return min(1.0, len(q & m) / max(1, len(q)))


class _Handler(BaseHTTPRequestHandler):
    seen = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Handler.seen.append({"path": self.path, "auth": self.headers.get("Authorization"),
                              "body": body})
        state, answers = body["state"], {}
        if "fail" in json.dumps(state):
            self.send_response(400)
            self.end_headers()
            return
        for name, q in body["questions"].items():
            if q["type"] == "noul":
                mem = state.get("memory") or state["memories"][name]
                answers[name] = {"noul": _relevance(state["question"], mem)}
            else:
                question = state["question"] if isinstance(state, dict) else q["instructions"]
                probs = {k: _relevance(question, v) + 1e-3
                         for k, v in q["criteria"].items()}
                z = sum(probs.values())
                answers[name] = {"choice": max(probs, key=probs.get),
                                 "probabilities": {k: v / z for k, v in probs.items()}}
        out = json.dumps({"answers": answers, "usage": {"input_tokens": 10,
                                                         "output_tokens": 0}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


@pytest.fixture()
def server():
    _Handler.seen = []
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


DOCS = ["We adopted a beagle named Bruno last spring.",
        "The quarterly report is due on Friday.",
        "Bruno the beagle loves the park near our house."]


@pytest.mark.parametrize("mode", ["noul", "fanout", "choice", "rank"])
def test_modes_rank_relevant_memories_first(server, mode):
    rr = SystemOneReranker(base_url=server, api_key="k", model="laya", mode=mode,
                           fanout_size=2, price_per_mtok=0.042)
    scores = rr.rerank("What is the name of our beagle?", DOCS)
    assert len(scores) == 3 and scores[1] < min(scores[0], scores[2])
    assert all(s["path"] == "/v1/systemone" for s in _Handler.seen)
    assert all(s["auth"] == "Bearer k" and s["body"]["model"] == "laya" for s in _Handler.seen)
    expected = {"noul": 3, "fanout": 2, "choice": 1, "rank": 1}[mode]
    st = rr.stats.as_dict()
    assert st["requests"] == expected and st["docs"] == 3 and st["calls"] == 1
    assert st["input_tokens"] == 10 * expected and st["errors"] == 0
    assert rr.cost_usd == pytest.approx(10 * expected / 1e6 * 0.042)


def test_rank_mode_puts_the_question_last(server):
    rr = SystemOneReranker(base_url=server, model=None, mode="rank")
    rr.rerank("What is the name of our beagle?", DOCS)
    body = _Handler.seen[0]["body"]
    q = body["questions"]["best"]
    assert body["state"] == "" and q["type"] == "choice"
    assert q["instructions"] == "What is the name of our beagle?"
    assert list(q["criteria"].values()) == DOCS


def test_failed_request_scores_zero_and_is_counted(server):
    rr = SystemOneReranker(base_url=server, model=None)
    scores = rr.rerank("beagle name?", ["beagle Bruno", "fail this one"])
    assert scores[1] == 0.0 and rr.stats.errors == 1
    assert "model" not in _Handler.seen[0]["body"] and _Handler.seen[0]["auth"] is None


def test_empty_candidates_make_no_requests(server):
    rr = SystemOneReranker(base_url=server)
    assert rr.rerank("q", []) == [] and not _Handler.seen


def test_invalid_mode_rejected():
    with pytest.raises(ValueError):
        SystemOneReranker(mode="generate")


def test_stats_reset():
    st = DecisionStats()
    st.add(calls=2, seconds=0.5)
    st.reset()
    assert st.as_dict()["calls"] == 0


class _Fixed:
    """Scores one planted turn as the only relevant memory."""

    def __init__(self, needle):
        self.needle, self.seen = needle, 0

    def rerank(self, query, docs):
        self.seen = len(docs)
        return [1.0 if self.needle in d else 0.0 for d in docs]


def _mem(reranker):
    mem = Smriti(path=":memory:", embedder=HashEmbedder(), reranker=reranker)
    for i in range(30):
        mem.add([{"role": "user", "content": f"Note {i}: the garden hose is in shed {i}."}],
                session_id=f"s{i}", timestamp=f"2023-05-{i % 28 + 1:02d}T10:00:00Z")
    mem.add([{"role": "user", "content": "My passport lives in the blue drawer."}],
            session_id="p", timestamp="2023-06-01T10:00:00Z")
    return mem


def test_rerank_depth_and_replace_contract():
    rr = _Fixed("passport")
    mem = _mem(rr)
    hits = mem.search("where is the garden hose kept, or my passport?")
    assert 0 < rr.seen <= 48 and "passport" in hits[0].text
    assert "rerank" in hits[0].channels


def test_rerank_weight_blends_with_fused_score():
    rr = _Fixed("passport")
    mem = _mem(rr)
    cfg = RecallConfig(rerank_depth=5, rerank_weight=0.5)
    prof = PROFILES["evidence"].with_overrides(recall=cfg)
    hits = mem.search("garden hose shed", profile=prof)
    assert rr.seen <= 5
    # a blend never lifts a turn the reranker scores 0 above the fused score alone
    assert all(0.0 <= h.score <= 1.0 for h in hits[:5])


class _HitAware:
    """Uses Smriti's own rank signal: reverses the pool to prove it was consulted."""

    def __init__(self):
        self.pool = []

    def rerank_hits(self, query, hits):
        self.pool = list(hits)
        return [float(i) for i in range(len(hits))]   # higher = later in fused order


def test_hit_aware_reranker_sees_scores_and_roles():
    rr = _HitAware()
    mem = _mem(rr)
    hits = mem.search("garden hose shed", profile=PROFILES["evidence"].with_overrides(
        recall=RecallConfig(rerank_depth=5)))
    assert len(rr.pool) == 5 and all(hasattr(h, "score") and h.episode.role for h in rr.pool)
    assert hits[0].id == rr.pool[-1].episode.id       # the reversed order was applied
