"""LLM clients.

SMRITI is provider-agnostic: anything speaking the OpenAI-compatible
chat-completions protocol works (Ollama, vLLM, LM Studio, Groq,
OpenRouter, hosted APIs). Stdlib HTTP only.
"""
from __future__ import annotations

import json
import re
from typing import List, Optional

from .embedder import _post_json

PRESETS = {
    "ollama": "http://localhost:11434/v1",
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
}


class LLM:
    def __init__(self, model: str, base_url: str = "", api_key: str = "",
                 provider: str = "", temperature: float = 0.0, max_tokens: int = 2048,
                 extra_body: Optional[dict] = None):
        self.model = model
        self.base_url = (base_url or PRESETS.get(provider, PRESETS["ollama"])).rstrip("/")
        self.api_key = api_key
        self.temperature = temperature
        self.max_tokens = max_tokens
        # provider-specific request fields merged into every payload.
        # DeepSeek V4 defaults to thinking mode, which spends the token budget
        # on hidden reasoning and returns empty `content` under small limits —
        # fatal for short answers and the yes/no judge. Disable it by default.
        self.extra_body = extra_body or {}
        if not extra_body and provider == "deepseek":
            self.extra_body = {"thinking": {"type": "disabled"}}
        self.tokens_in = 0
        self.tokens_out = 0
        self.calls = 0

    def complete(self, messages: List[dict], json_mode: bool = False,
                 max_tokens: Optional[int] = None) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }
        payload.update(self.extra_body)
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            resp = _post_json(f"{self.base_url}/chat/completions", payload, headers)
        except Exception:
            if json_mode:
                payload.pop("response_format", None)  # some servers reject it
                resp = _post_json(f"{self.base_url}/chat/completions", payload, headers)
            else:
                raise
        usage = resp.get("usage") or {}
        self.tokens_in += usage.get("prompt_tokens", 0)
        self.tokens_out += usage.get("completion_tokens", 0)
        self.calls += 1
        # fall back to reasoning_content so a thinking-mode reply is never blank
        msg = resp["choices"][0]["message"]
        return msg.get("content") or msg.get("reasoning_content") or ""


class MockLLM:
    """Scripted LLM for offline tests."""

    def __init__(self, responses: Optional[List[str]] = None):
        self.responses = list(responses or [])
        self.calls = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self.history: List[List[dict]] = []

    def complete(self, messages: List[dict], json_mode: bool = False,
                 max_tokens: Optional[int] = None) -> str:
        self.history.append(messages)
        self.calls += 1
        return self.responses.pop(0) if self.responses else "[]"


def extract_json(text: str):
    """Robustly pull the first JSON array/object out of an LLM reply."""
    text = re.sub(r"```(?:json)?", "", text).strip()
    for opener, closer in (("[", "]"), ("{", "}")):
        start = text.find(opener)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(text)):
            if text[i] == opener:
                depth += 1
            elif text[i] == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
    return None
