"""Growing-corpus cost/speed simulation; not longitudinal wall-clock evidence."""
from __future__ import annotations
import argparse,json,os,statistics,tempfile,time
from pathlib import Path
from bench.comparative import Gbrain,Mem0,SmritiEpisodes,pct
from smriti import OllamaEmbedder, Smriti

class SmritiOllama(SmritiEpisodes):
    label="Smriti lite / Ollama nomic-embed-text:v1.5"
    def __init__(self):
        self.root=tempfile.mkdtemp(prefix="smriti-growth-nomic-"); self.path=os.path.join(self.root,"memory.db")
        self.m=Smriti(path=self.path,mode="lite",embedder=OllamaEmbedder(model=os.environ.get("GROWTH_EMBED_MODEL","nomic-embed-text:v1.5"),base_url=os.environ.get("GROWTH_OLLAMA_URL","http://127.0.0.1:11436")))

QUERIES=["passport renewal appointment","doctor knee recommendation","project launch date","invoice due date","emergency contact"]
def doc(i):
    topics=["passport renewal appointment","doctor knee recommendation","project launch date","invoice due date","emergency contact"]
    return {"id":f"n{i:07d}","timestamp":f"2024-{i%12+1:02d}-{i%28+1:02d}T09:00:00Z","text":f"Synthetic record {i}: {topics[i%len(topics)]}; reference code {i*7919}."}
def size_tree(path): return sum(os.path.getsize(os.path.join(dp,f)) for dp,_,fs in os.walk(path) for f in fs)
def main():
    p=argparse.ArgumentParser(); p.add_argument("--adapter",choices=["smriti","smriti-nomic","mem0","gbrain"],required=True); p.add_argument("--checkpoints",nargs="+",type=int,default=[100,1000,5000]); p.add_argument("--out",required=True); p.add_argument("--repeats",type=int,default=10); a=p.parse_args()
    if not a.checkpoints or any(x<=0 for x in a.checkpoints) or a.checkpoints != sorted(set(a.checkpoints)):
        p.error("checkpoints must be unique, positive, and increasing")
    cls={"smriti":SmritiEpisodes,"smriti-nomic":SmritiOllama,"mem0":Mem0,"gbrain":Gbrain}[a.adapter]; m=cls(); rows=[]; added=0
    for target in a.checkpoints:
        t=time.perf_counter_ns()
        for i in range(added,target): m.add(doc(i))
        ingest_ms=(time.perf_counter_ns()-t)/1e6; added=target
        t=time.perf_counter_ns(); first_hits=m.search(QUERIES[0],5); first=(time.perf_counter_ns()-t)/1e6
        if not first_hits: raise RuntimeError("retrieval returned no results at checkpoint")
        samples=[]
        for j in range(a.repeats):
            t=time.perf_counter_ns(); m.search(QUERIES[j%len(QUERIES)],5); samples.append((time.perf_counter_ns()-t)/1e6)
        rows.append({"documents":target,"incremental_ingest_ms":round(ingest_ms,3),"first_query_after_ingest_ms":round(first,3),"warm_query_ms_p50":pct(samples,.5),"warm_query_ms_p95":pct(samples,.95),"timed_query_samples":len(samples),"first_query_returned":len(first_hits),"storage_bytes":m.storage()})
        print(rows[-1],flush=True)
    m.close(); out={"schema_version":2,"adapter":a.adapter,"configuration":m.label,"measurement":"growing-corpus simulation in one run, not elapsed-day longitudinal data","timing_scope":"gbrain includes a new CLI process per operation" if a.adapter=="gbrain" else "in-process calls; first_query_after_ingest is not a process-restart cold query","model_cost":{"observed_paid_api_usd":0 if ("local" in m.label.lower() or "ollama" in m.label.lower() or "hash" in m.label.lower() or "keyless" in m.label.lower()) else None,"note":"Only valid for the recorded local configuration; electricity and hardware depreciation unmeasured; shared model-cache bytes excluded"},"checkpoints":rows}
    Path(a.out).parent.mkdir(parents=True,exist_ok=True); Path(a.out).write_text(json.dumps(out,indent=2)+"\n")
if __name__=="__main__": main()
