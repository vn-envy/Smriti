"""SMRITI MCP server — drop-in memory for any MCP-compatible agent.

Design follows the Codebase-Memory blueprint (Vogel et al., 2026): expose a
small set of *typed* tools that return structured JSON rather than raw content,
keep it zero-dependency, and harden it like the supply-chain risk it is — an
MCP server runs with the host agent's full permissions.

- Transport: newline-delimited JSON-RPC 2.0 over stdio. Stdlib only (json, sys).
  No `mcp` SDK, no extra dependency — consistent with the rest of SMRITI.
- Tools (3 groups): write (remember, add_fact), read (recall, search,
  facts_about), introspect (stats). Each returns structured JSON.
- Security: SQLite authorizer denies ATTACH/DETACH (blocks SQL-injection file
  creation); the db path is fixed at launch and never taken from tool args
  (no path traversal); inputs are size-validated; malformed JSON-RPC and tool
  exceptions are caught and returned as errors — the loop never crashes.

Run:  python -m smriti.mcp_server --db memory.db
      SMRITI_DB=memory.db python -m smriti.mcp_server   # env config too
Defaults to lite mode (offline, no keys); set SMRITI_LLM_MODEL/PROVIDER/API_KEY
for full mode (extraction + supersession).
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from typing import Optional

from . import __version__
from .embedder import HashEmbedder, OllamaEmbedder, OpenAICompatEmbedder
from .llm import LLM
from .memory import Smriti
from .retrieval import expand_channels
from .types import Fact

PROTOCOL_VERSION = "2025-06-18"
MAX_QUERY = 4000
MAX_MESSAGES = 200
MAX_CONTENT = 8000


class McpError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# --- tool definitions (typed, structured-JSON contract) --------------------
TOOL_DEFS = [
    {"name": "remember",
     "description": "Store a conversation turn or session into long-term memory. "
                    "Returns counts of episodes and facts written.",
     "inputSchema": {"type": "object", "properties": {
         "messages": {"type": "array", "items": {"type": "object", "properties": {
             "role": {"type": "string"}, "content": {"type": "string"}}, "required": ["content"]}},
         "session_id": {"type": "string"}, "timestamp": {"type": "string"}},
         "required": ["messages"]}},
    {"name": "recall",
     "description": "Retrieve answer-ready memory context for a query, with validity "
                    "windows (CURRENT / SUPERSEDED-on-date) annotated. Pick a profile "
                    "for the search type: 'facts' for current-state lookups, "
                    "'relations' for who/how-connected questions, 'timeline' for "
                    "when/before/after questions, 'deep' for counts, totals and "
                    "summarize-everything questions, 'auto' to let the router choose.",
     "inputSchema": {"type": "object", "properties": {
         "query": {"type": "string"}, "k": {"type": "integer"},
         "char_budget": {"type": "integer"},
         "profile": {"type": "string",
                     "enum": ["auto", "facts", "relations", "timeline", "deep", "precision"]},
         "channels": {"type": "array", "description":
                      "Optional channel mask (overrides the profile's channels): "
                      "lexical, semantic, entity, temporal — Sanskrit aliases "
                      "shabda, artha, sambandha, kala also accepted.",
                      "items": {"type": "string"}}},
         "required": ["query"]}},
    {"name": "search",
     "description": "Structured retrieval: ranked memory hits as JSON "
                    "(kind, text, score, validity window, channels). Same profile/"
                    "channels selection as recall: 'facts' current-state, 'relations' "
                    "connections, 'timeline' when-questions, 'deep' counts/summaries.",
     "inputSchema": {"type": "object", "properties": {
         "query": {"type": "string"}, "k": {"type": "integer"},
         "profile": {"type": "string",
                     "enum": ["auto", "facts", "relations", "timeline", "deep", "precision"]},
         "channels": {"type": "array", "items": {"type": "string"}}},
         "required": ["query"]}},
    {"name": "facts_about",
     "description": "All facts linked to an entity, each flagged current or superseded "
                    "(full history, never deleted).",
     "inputSchema": {"type": "object", "properties": {
         "entity": {"type": "string"}}, "required": ["entity"]}},
    {"name": "add_fact",
     "description": "Insert a single fact the agent observed, with conflict resolution "
                    "(supersedes an older value rather than deleting it).",
     "inputSchema": {"type": "object", "properties": {
         "statement": {"type": "string"}, "subject": {"type": "string"},
         "predicate": {"type": "string"}, "object": {"type": "string"},
         "entities": {"type": "array", "items": {"type": "string"}}},
         "required": ["statement"]}},
    {"name": "stats",
     "description": "Memory store statistics (episodes, facts, valid facts, entities, mode).",
     "inputSchema": {"type": "object", "properties": {}}},
]


def _check_str(v, name, limit):
    if not isinstance(v, str):
        raise McpError(-32602, f"{name} must be a string")
    if len(v) > limit:
        raise McpError(-32602, f"{name} exceeds {limit} chars")
    return v


class SmritiMCP:
    def __init__(self, mem: Smriti):
        self.mem = mem
        # security: block ATTACH/DETACH at the SQLite engine level so no tool
        # input (even via a future SQL path) can create/attach files.
        try:
            self.mem.store.db.set_authorizer(self._authorizer)
        except Exception:
            pass

    @staticmethod
    def _authorizer(action, *_):
        if action in (sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH):
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    # ---- tool handlers (return JSON-serializable objects) ----
    def t_remember(self, a):
        msgs = a.get("messages")
        if not isinstance(msgs, list) or not msgs:
            raise McpError(-32602, "messages must be a non-empty array")
        if len(msgs) > MAX_MESSAGES:
            raise McpError(-32602, f"too many messages (>{MAX_MESSAGES})")
        clean = []
        for m in msgs:
            if not isinstance(m, dict):
                raise McpError(-32602, "each message must be an object")
            clean.append({"role": str(m.get("role", "user"))[:40],
                          "content": _check_str(m.get("content", ""), "content", MAX_CONTENT)})
        return self.mem.add(clean, session_id=a.get("session_id"), timestamp=a.get("timestamp"))

    @staticmethod
    def _profile_args(a):
        """Validate optional profile/channels tool args (drishti selection)."""
        profile = a.get("profile")
        if profile is not None:
            profile = _check_str(profile, "profile", 40)
        channels = a.get("channels")
        if channels is not None:
            if not isinstance(channels, list) or not channels:
                raise McpError(-32602, "channels must be a non-empty array")
            channels = {_check_str(c, "channel", 40) for c in channels}
            try:
                expand_channels(channels)
            except ValueError as e:
                raise McpError(-32602, str(e))
            # a bare channel mask still needs a policy to ride on
            profile = profile or "precision"
        return profile, channels

    def t_recall(self, a):
        q = _check_str(a.get("query", ""), "query", MAX_QUERY)
        k = _clamp_k(a.get("k", 12))
        cb = a.get("char_budget", 9000)
        cb = cb if isinstance(cb, int) and 200 <= cb <= 64000 else 9000
        profile, channels = self._profile_args(a)
        try:
            return {"context": self.mem.context(q, k=k, char_budget=cb,
                                                profile=profile, channels=channels)}
        except ValueError as e:
            raise McpError(-32602, str(e))

    def t_search(self, a):
        q = _check_str(a.get("query", ""), "query", MAX_QUERY)
        k = _clamp_k(a.get("k", 12))
        profile, channels = self._profile_args(a)
        try:
            hits = self.mem.search(q, k=k, profile=profile, channels=channels)
        except ValueError as e:
            raise McpError(-32602, str(e))
        return {"results": [
            {"kind": r.kind, "text": r.text, "score": round(r.score, 4),
             "valid_from": r.valid_from, "invalid_at": r.invalid_at,
             "current": (r.kind != "fact") or (r.invalid_at is None),
             "ts": r.ts, "role": r.role, "channels": r.channels}
            for r in hits]}

    def t_facts_about(self, a):
        ent = _check_str(a.get("entity", ""), "entity", 200)
        facts = self.mem.store.facts_for_entity(ent, valid_only=False, include_observations=True)
        return {"entity": ent, "facts": [
            {"statement": f.statement, "valid_from": f.valid_from,
             "invalid_at": f.invalid_at, "current": f.invalid_at is None}
            for f in facts]}

    def t_add_fact(self, a):
        stmt = _check_str(a.get("statement", ""), "statement", MAX_CONTENT)
        ents = a.get("entities") or []
        if not isinstance(ents, list):
            raise McpError(-32602, "entities must be an array")
        fid = self.mem.add_fact(Fact(
            id=None, statement=stmt, subject=str(a.get("subject", "user")),
            predicate=str(a.get("predicate", "")), object=str(a.get("object", "")),
            entities=[str(e)[:120] for e in ents][:20]))
        return {"fact_id": fid, "stored": fid is not None}

    def t_stats(self, a):
        return self.mem.stats()

    HANDLERS = {"remember": "t_remember", "recall": "t_recall", "search": "t_search",
                "facts_about": "t_facts_about", "add_fact": "t_add_fact", "stats": "t_stats"}

    # ---- JSON-RPC dispatch ----
    def dispatch(self, method, params):
        if method == "initialize":
            return {"protocolVersion": params.get("protocolVersion", PROTOCOL_VERSION),
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "smriti", "version": __version__}}
        if method == "tools/list":
            return {"tools": TOOL_DEFS}
        if method == "tools/call":
            name = params.get("name")
            handler = self.HANDLERS.get(name)
            if not handler:
                raise McpError(-32602, f"unknown tool: {name}")
            args = params.get("arguments") or {}
            if not isinstance(args, dict):
                raise McpError(-32602, "arguments must be an object")
            try:
                out = getattr(self, handler)(args)
            except McpError:
                raise
            except Exception as e:  # tool failure -> error result, not a crash
                return {"content": [{"type": "text", "text": f"tool error: {str(e)[:300]}"}],
                        "isError": True}
            return {"content": [{"type": "text", "text": json.dumps(out, default=str)}]}
        if method == "ping":
            return {}
        raise McpError(-32601, f"method not found: {method}")

    def handle(self, msg) -> Optional[dict]:
        """Map one JSON-RPC message to a response dict (None for notifications)."""
        if not isinstance(msg, dict):
            return _err(None, -32600, "invalid request")
        mid = msg.get("id")
        is_notification = "id" not in msg
        method = msg.get("method")
        if not isinstance(method, str):
            return None if is_notification else _err(mid, -32600, "missing method")
        try:
            result = self.dispatch(method, msg.get("params") or {})
        except McpError as e:
            return None if is_notification else _err(mid, e.code, e.message)
        except Exception as e:  # never crash the loop
            return None if is_notification else _err(mid, -32603, f"internal error: {str(e)[:200]}")
        return None if is_notification else {"jsonrpc": "2.0", "id": mid, "result": result}

    def serve_stdio(self):
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                _write(_err(None, -32700, "parse error"))
                continue
            resp = self.handle(msg)
            if resp is not None:
                _write(resp)


def _clamp_k(k):
    return k if isinstance(k, int) and 1 <= k <= 100 else 12


def _err(mid, code, message):
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def _write(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def build_memory(db: str, *, embed_model="", provider="", model="", api_key="",
                 embed_provider="") -> Smriti:
    """Construct a Smriti instance from env/flags. Lite (offline) by default."""
    llm = LLM(model=model, provider=provider, api_key=api_key) if model else None
    if embed_provider == "ollama" or (not embed_provider and embed_model and not provider):
        embedder = OllamaEmbedder(model=embed_model or "nomic-embed-text")
    elif embed_provider in ("openai", "openai-compat") and embed_model:
        embedder = OpenAICompatEmbedder(model=embed_model, base_url="", api_key=api_key)
    else:
        embedder = HashEmbedder()
    return Smriti(path=db, embedder=embedder, llm=llm,
                  mode="full" if llm else "lite")


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description="SMRITI MCP server (stdio)")
    p.add_argument("--db", default=os.environ.get("SMRITI_DB", "smriti_memory.db"))
    p.add_argument("--model", default=os.environ.get("SMRITI_LLM_MODEL", ""))
    p.add_argument("--provider", default=os.environ.get("SMRITI_LLM_PROVIDER", ""))
    p.add_argument("--api-key", default=os.environ.get("SMRITI_API_KEY", ""))
    p.add_argument("--embed-model", default=os.environ.get("SMRITI_EMBED_MODEL", ""))
    p.add_argument("--embed-provider", default=os.environ.get("SMRITI_EMBED_PROVIDER", ""))
    args = p.parse_args(argv)
    # path containment: never accept a db path from tool calls; fixed here.
    db = os.path.abspath(os.path.expanduser(args.db))
    mem = build_memory(db, embed_model=args.embed_model, provider=args.provider,
                       model=args.model, api_key=args.api_key,
                       embed_provider=args.embed_provider)
    SmritiMCP(mem).serve_stdio()


if __name__ == "__main__":
    main()
