"""Deterministic local retrieval comparison (no answer LLM or LLM judge).

This track measures evidence retrieval only. It does not claim to measure answer
generation, automatic fact extraction, or knowledge-graph construction quality.
Run from the repository root:
  python3 -m bench.comparative --adapter smriti-episodes --out result.json
  python3 -m bench.comparative --adapter lexical --out lexical.json
  python3 -m bench.comparative --adapter mem0 --out mem0.json
"""
from __future__ import annotations

import argparse, hashlib, json, math, os, platform, re, statistics, subprocess, sys, tempfile, time
from pathlib import Path

from smriti import HashEmbedder, Smriti

DOC_RE = re.compile(r"\[DOC:([^\]]+)\]")


def pct(xs, p):
    if not xs: return None
    ys = sorted(xs); i = max(0, min(len(ys)-1, math.ceil(p * len(ys))-1))
    return round(ys[i], 3)


class SmritiEpisodes:
    label = "Smriti lite / raw episodes / HashEmbedder"
    def __init__(self): self.root=tempfile.mkdtemp(prefix="smriti-comparative-"); self.path=os.path.join(self.root,"memory.db"); self.m = Smriti(path=self.path, mode="lite", embedder=HashEmbedder())
    def add(self, d): self.m.add([{"role":"user","content":f"[DOC:{d['id']}] {d['text']}"}], session_id=d["id"], timestamp=d["timestamp"])
    def search(self, q, k): return [(m.group(1), r.score) for r in self.m.search(q, k=k) if (m := DOC_RE.search(r.text))]
    def storage(self): return sum(os.path.getsize(os.path.join(dp,f)) for dp,_,fs in os.walk(self.root) for f in fs)
    def close(self): self.m.store.db.close()


class Lexical:
    """Transparent sanity-control, not a named competitor."""
    label = "token-overlap control"
    def __init__(self): self.docs=[]
    def add(self,d): self.docs.append(d)
    def search(self,q,k):
        qt=set(re.findall(r"[a-z0-9]+",q.lower()))
        scored=[(d["id"],len(qt & set(re.findall(r"[a-z0-9]+",d["text"].lower())))) for d in self.docs]
        return [(i,float(s)) for i,s in sorted(scored,key=lambda x:(-x[1],x[0])) if s>0][:k]
    def storage(self): return len(json.dumps(self.docs).encode())
    def close(self): pass


class Mem0:
    label = "mem0 OSS / infer=False / FastEmbed BAAI-bge-small-en-v1.5 / local Qdrant (BM25 unavailable)"
    def __init__(self):
        from mem0 import Memory
        # infer=False avoids extraction, making this the matched raw-document
        # retrieval path. Provider/model must be supplied explicitly by env.
        cfg=json.loads(os.environ.get("MEM0_BENCH_CONFIG","{}")); self.cfg=cfg
        if not cfg: raise RuntimeError("MEM0_BENCH_CONFIG is required; see benchmark manifest")
        self.m=Memory.from_config(cfg); self.user="comparative-v1"
    def add(self,d): self.m.add(f"[DOC:{d['id']}] {d['text']}",user_id=self.user,infer=False,metadata={"doc_id":d["id"],"timestamp":d["timestamp"]})
    def search(self,q,k):
        # mem0 2.x requires entity scoping inside filters (older releases
        # accepted user_id as a top-level search argument).
        raw=self.m.search(q,filters={"user_id":self.user},top_k=k)
        rows=raw.get("results",raw) if isinstance(raw,dict) else raw
        out=[]
        for r in rows:
            did=(r.get("metadata") or {}).get("doc_id")
            if not did:
                m=DOC_RE.search(str(r.get("memory",r.get("text","")))); did=m.group(1) if m else None
            if did: out.append((did,float(r.get("score",0))))
        return out[:k]
    def storage(self):
        paths=[self.cfg.get("history_db_path"),self.cfg.get("vector_store",{}).get("config",{}).get("path")]
        return sum(os.path.getsize(os.path.join(dp,f)) for p in paths if p and os.path.exists(p) for dp,_,fs in os.walk(p) for f in fs) + sum(os.path.getsize(p) for p in paths if p and os.path.isfile(p))
    def close(self): pass


class Gbrain:
    label = "gbrain PGLite / keyless keyword-only / raw pages"
    def __init__(self):
        self.root=tempfile.mkdtemp(prefix="gbrain-comparative-")
        self.cli=os.environ.get("GBRAIN_BENCH_CLI")
        if not self.cli: raise RuntimeError("GBRAIN_BENCH_CLI must point to gbrain src/cli.ts")
        self.env={**os.environ,"GBRAIN_HOME":self.root}
        self._run("init","--pglite","--non-interactive","--no-embedding","--path",os.path.join(self.root,"db"),"--json")
    def _run(self,*args):
        cp=subprocess.run(["bun",self.cli,*args],cwd=self.root,env=self.env,text=True,capture_output=True)
        if cp.returncode: raise RuntimeError(f"gbrain {' '.join(args)} failed: {cp.stderr[-500:]}")
        # Some commands emit diagnostics before their JSON payload.
        text=cp.stdout.strip(); starts=[i for i,c in enumerate(text) if c in "[{"]
        for i in starts:
            try: return json.loads(text[i:])
            except json.JSONDecodeError: pass
        raise RuntimeError(f"gbrain returned no JSON: {text[-500:]}")
    def add(self,d): self._run("capture",f"[DOC:{d['id']}] {d['text']}","--slug",f"bench/{d['id']}","--json")
    def search(self,q,k):
        rows=self._run("search",q,"--limit",str(k),"--json")
        return [(str(r.get("slug",r.get("id", ""))).split("/")[-1],float(r.get("score",0))) for r in rows]
    def storage(self): return sum(os.path.getsize(os.path.join(dp,f)) for dp,_,fs in os.walk(self.root) for f in fs)
    def close(self): pass


def main():
    p=argparse.ArgumentParser(); p.add_argument("--adapter",choices=["smriti-episodes","lexical","mem0","gbrain"],required=True); p.add_argument("--data",default=str(Path(__file__).with_name("comparative_dataset.json"))); p.add_argument("--out",required=True); p.add_argument("--k",type=int,default=5); p.add_argument("--warmups",type=int,default=2); p.add_argument("--repeats",type=int,default=5); a=p.parse_args()
    raw=Path(a.data).read_bytes(); data=json.loads(raw); cls={"smriti-episodes":SmritiEpisodes,"lexical":Lexical,"mem0":Mem0,"gbrain":Gbrain}[a.adapter]
    started=time.time(); error=None; records=[]; ingest=[]
    try:
        ad=cls()
        for d in data["documents"]:
            t=time.perf_counter_ns(); ad.add(d); ingest.append((time.perf_counter_ns()-t)/1e6)
        for q in data["queries"]:
            for _ in range(a.warmups): ad.search(q["query"],a.k)
            ts=[]; hits=[]
            for _ in range(a.repeats):
                t=time.perf_counter_ns(); hits=ad.search(q["query"],a.k); ts.append((time.perf_counter_ns()-t)/1e6)
            ids=[x[0] for x in hits]; rel=set(q["relevant"]); ranks=[ids.index(x)+1 for x in rel if x in ids]
            if rel: recall=len(ranks)/len(rel); rr=1/min(ranks) if ranks else 0.0; success=None
            else: recall=None; rr=None; success=len(ids)==0
            records.append({**q,"returned":ids,"scores":[x[1] for x in hits],"recall_at_k":recall,"reciprocal_rank":rr,"abstention_success":success,"latency_ms":ts})
        storage=ad.storage(); ad.close()
    except Exception as e:
        error={"type":type(e).__name__,"message":str(e)}; storage=None
    answerable=[r for r in records if r["relevant"]]; abst=[r for r in records if not r["relevant"]]
    lat=[x for r in records for x in r["latency_ms"]]
    complete=error is None and len(records)==len(data["queries"])
    summary={"mean_recall_at_k":round(statistics.fmean(r["recall_at_k"] for r in answerable),4) if complete and answerable else None,"mrr":round(statistics.fmean(r["reciprocal_rank"] for r in answerable),4) if complete and answerable else None,"abstention_precision":round(statistics.fmean(r["abstention_success"] for r in abst),4) if complete and abst else None,"latency_ms_p50":pct(lat,.5) if complete else None,"latency_ms_p95":pct(lat,.95) if complete else None,"ingest_ms_total":round(sum(ingest),3),"storage_bytes":storage,"errors":0 if complete else 1}
    result={"schema_version":2,"status":"complete" if complete else "blocked","error":error,"adapter":a.adapter,"configuration":getattr(cls,"label",a.adapter),"track":"diagnostic matched raw-document retrieval (extraction bypassed; 20 documents / 12 queries)","dataset":{"path":a.data,"sha256":hashlib.sha256(raw).hexdigest(),"documents":len(data["documents"]),"queries":len(data["queries"])},"run":{"utc_started":time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime(started)),"python":sys.version,"platform":platform.platform(),"k":a.k,"warmups":a.warmups,"timed_repeats":a.repeats,"clock":"time.perf_counter_ns","pid":os.getpid(),"latency_scope":"in-process" if a.adapter in {"smriti-episodes","lexical","mem0"} else "end-to-end CLI subprocess startup + query"},"summary":summary,"results":records}
    Path(a.out).parent.mkdir(parents=True,exist_ok=True); Path(a.out).write_text(json.dumps(result,indent=2)+"\n"); print(json.dumps(result["summary"],indent=2));
    if error: print(json.dumps(error),file=sys.stderr); raise SystemExit(2)

if __name__=="__main__": main()
