"""LLM access behind one small interface so the graph can run on OpenAI, or on a FakeLLM in unit tests (dependency
injection). Every call returns parsed JSON and adds its token usage to a per-request Usage object."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable, Protocol


@dataclass
class Usage:
    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    embed_tokens: int = 0
    by_step: dict = field(default_factory=dict)

    def add(self, step: str, tin: int, tout: int) -> None:
        self.calls += 1
        self.tokens_in += tin
        self.tokens_out += tout
        s = self.by_step.setdefault(step, {"calls": 0, "in": 0, "out": 0})
        s["calls"] += 1
        s["in"] += tin
        s["out"] += tout

    def cost(self, price_in: float, price_out: float, price_embed: float = 0.02) -> float:
        return (self.tokens_in * price_in + self.tokens_out * price_out + self.embed_tokens * price_embed) / 1e6


class LLM(Protocol):
    def json(self, step: str, messages: list[tuple[str, str]], usage: Usage) -> dict: ...

    def json_batch(self, step: str, batch: list[list[tuple[str, str]]], usage: Usage) -> list[dict]: ...


def _parse(text: str) -> dict:
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        m = re.search(r"\{.*\}", text or "", re.S)
        try:
            return json.loads(m.group(0)) if m else {}
        except ValueError:
            return {}


THINK_STEPS = {"supervisor", "writer", "writer_retry", "baseline_answer", "judge"}


class OpenAIJSON:
    """LangChain ChatOpenAI in JSON mode (LCEL runnable: invoke / batch). Reasoning models (gpt-5 / gpt-6 families) get a
    reasoning effort per step: 'think' steps (routing, answer writing, judging) a little reasoning, the high-volume steps none."""

    def __init__(self, model: str = "gpt-6-luna", max_concurrency: int = 16, effort_fast: str = "none", effort_think: str = "low"):
        from langchain_openai import ChatOpenAI

        kw = {"model_kwargs": {"response_format": {"type": "json_object"}}}
        if model.startswith(("gpt-5", "gpt-6", "o")):
            self.fast = ChatOpenAI(model=model, reasoning_effort=effort_fast, **kw)
            self.think = ChatOpenAI(model=model, reasoning_effort=effort_think, **kw)
        else:
            self.fast = self.think = ChatOpenAI(model=model, temperature=0, **kw)
        self.chat = self.fast
        self.max_concurrency = max_concurrency

    def _client(self, step: str):
        return self.think if step in THINK_STEPS else self.fast

    @staticmethod
    def _count(step, msg, usage):
        u = msg.usage_metadata or {}
        usage.add(step, u.get("input_tokens", 0), u.get("output_tokens", 0))

    def json(self, step, messages, usage):
        msg = self._client(step).invoke(messages, config={"run_name": step})
        self._count(step, msg, usage)
        return _parse(msg.content)

    def json_batch(self, step, batch, usage):
        msgs = self._client(step).batch(batch, config={"max_concurrency": self.max_concurrency, "run_name": step})
        for m in msgs:
            self._count(step, m, usage)
        return [_parse(m.content) for m in msgs]


class FakeLLM:
    """Deterministic stand-in for tests: `rules` maps a step name to a function(messages) -> dict."""

    def __init__(self, rules: dict[str, Callable[[list], dict]]):
        self.rules = rules
        self.seen: list[str] = []

    def json(self, step, messages, usage):
        self.seen.append(step)
        usage.add(step, 10, 5)
        return self.rules.get(step, lambda m: {})(messages)

    def json_batch(self, step, batch, usage):
        return [self.json(step, m, usage) for m in batch]
