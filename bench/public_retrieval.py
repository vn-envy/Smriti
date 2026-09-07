"""Session-evidence retrieval on the official LongMemEval oracle split.

This deliberately bypasses extraction and answer generation. Each oracle
session is one document and `answer_session_ids` are relevance labels. Oracle
contains evidence sessions only, so scores are a retrieval sanity ceiling and
must not be presented as full-haystack LongMemEval quality.
"""
from __future__ import annotations
import argparse, hashlib, json, math, os, platform, statistics, sys, time
from pathlib import Path
from smriti import OllamaEmbedder, Smriti

def percentile(xs,p):
    ys=sorted(xs); return round(ys[max(0,min(len(ys)-1,math.ceil(p*len(ys))-1))],3) if ys else None

def session_text(session):
    # Fixed payload cap for both adapters. Smriti.add otherwise truncates each
    # turn internally while mem0 sends the full session to Ollama, which is not
    # comparable and can exceed nomic's context window.
    return "\n".join(f"{t.get('role','user')}: {t.get('content','')}" for t in session if t.get("content"))[:4000]

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--adapter",choices=["smriti","mem0"],default="smriti"); ap.add_argument("--data",required=True); ap.add_argument("--out",required=True); ap.add_argument("--limit",type=int,default=500); ap.add_argument("--k",type=int,default=5); ap.add_argument("--base-url",default="http://127.0.0.1:11436"); ap.add_argument("--embed-model",default="nomic-embed-text:v1.5"); a=ap.parse_args()
    raw=Path(a.data).read_bytes(); items=json.loads(raw)[:a.limit]; results=[]; failures=[]; lat=[]; started=time.time()
    embed=OllamaEmbedder(model=a.embed_model,base_url=a.base_url)
    shared_mem0=None
    if a.adapter=="mem0":
        from mem0 import Memory
        cfg=json.loads(os.environ.get("MEM0_BENCH_CONFIG","{}"))
        if not cfg: raise RuntimeError("MEM0_BENCH_CONFIG is required")
        shared_mem0=Memory.from_config(cfg)
    for ix,item in enumerate(items):
        try:
            if not (len(item["haystack_session_ids"]) == len(item["haystack_dates"]) == len(item["haystack_sessions"])):
                raise ValueError("mismatched session/id/date lengths")
            mem=Smriti(path=":memory:",mode="lite",embedder=embed,aggregate=False) if a.adapter=="smriti" else shared_mem0
            mapping={}
            for sid,dt,sess in zip(item["haystack_session_ids"],item["haystack_dates"],item["haystack_sessions"]):
                text=f"[SESSION:{sid}] {session_text(sess)}"
                if a.adapter=="smriti": rec=mem.add([{"role":"user","content":text}],session_id=sid,timestamp=dt); mapping[rec["session_id"]]=sid
                else: mem.add(text,user_id=item["question_id"],infer=False,metadata={"session_id":sid,"timestamp":dt})
            t=time.perf_counter_ns()
            hits=(mem.search(item["question"],k=a.k) if a.adapter=="smriti" else mem.search(item["question"],filters={"user_id":item["question_id"]},top_k=a.k).get("results",[]))
            elapsed=(time.perf_counter_ns()-t)/1e6; lat.append(elapsed)
            got=[]
            for h in hits[:a.k]:
                if a.adapter=="smriti": sid=mem.store.get_episode(h.id).session_id
                else: sid=(h.get("metadata") or {}).get("session_id")
                if sid and sid not in got: got.append(sid)
            got=got[:a.k]; rel=set(item.get("answer_session_ids") or []); ranks=[got.index(s)+1 for s in rel if s in got]
            results.append({"question_id":item["question_id"],"question_type":item["question_type"],"relevant":sorted(rel),"returned":got,"recall_at_k":len(ranks)/len(rel) if rel else None,"reciprocal_rank":1/min(ranks) if ranks else 0.0,"latency_ms":elapsed})
            if a.adapter=="smriti": mem.store.db.close()
        except Exception as e:
            failures.append({"question_id":item.get("question_id"),"type":type(e).__name__,"message":str(e)})
        if (ix+1)%25==0: print(f"{ix+1}/{len(items)} failures={len(failures)}",flush=True)
    complete=len(results)+len(failures)==len(items); scored=[r for r in results if r["recall_at_k"] is not None]
    summary={"requested":len(items),"scored":len(results),"failures":len(failures),"mean_recall_at_k":round(sum(r["recall_at_k"] for r in scored)/len(items),4) if complete else None,"mrr":round(sum(r["reciprocal_rank"] for r in scored)/len(items),4) if complete else None,"latency_ms_p50":percentile(lat,.5),"latency_ms_p95":percentile(lat,.95)}
    out={"schema_version":1,"status":"complete" if complete else "partial","track":"LongMemEval oracle session-evidence retrieval; extraction bypassed; evidence-only split","adapter":"Smriti lite" if a.adapter=="smriti" else "mem0 OSS infer=False","embedding":{"provider":"Ollama","model":a.embed_model,"base_url":a.base_url},"dataset":{"path":a.data,"sha256":hashlib.sha256(raw).hexdigest(),"total_items":len(json.loads(raw))},"run":{"started_utc":time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime(started)),"platform":platform.platform(),"python":sys.version,"k":a.k,"limit":a.limit,"failure_policy":"failures remain in denominator as zero"},"summary":summary,"results":results,"failure_records":failures}
    Path(a.out).parent.mkdir(parents=True,exist_ok=True); Path(a.out).write_text(json.dumps(out,indent=2)+"\n"); print(json.dumps(summary,indent=2))
if __name__=="__main__": main()
