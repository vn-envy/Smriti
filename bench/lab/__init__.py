"""pariksha-lab: offline, deterministic retrieval + context-fidelity benchmarks.

Unlike the answer/judge harnesses, nothing here needs an LLM. Every metric is
computed against dataset evidence labels (LoCoMo ``evidence`` dialog ids,
LongMemEval ``has_answer`` turns), so any change to retrieval or context
packing can be A/B tested in minutes on a laptop CPU.
"""
