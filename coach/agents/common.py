"""Helpers shared by the agents: access to the injected container / usage, node timing, text checks."""
from __future__ import annotations

import asyncio
import functools
import re
import time

MED_TERMS = [(r"glimepiride|glipizide|gliclazide|glyburide|glibenclamide|sulfonylurea", "sulfonylurea exercise hypoglycaemia"),
             (r"insulin|glargine|aspart|premixed", "insulin treated exercise hypoglycaemia"),
             (r"amlodipine|lisinopril|losartan|hypertension", "hypertension blood pressure response to exercise"),
             (r"kidney|ckd", "chronic kidney disease exercise"),
             (r"retinopathy", "diabetic retinopathy exercise precautions"),
             (r"neuropathy|numb", "peripheral neuropathy foot exercise")]


def deps(config):
    return config["configurable"]["deps"]


def usage(config):
    return config["configurable"]["usage"]


def timed(name: str):
    """Records the wall time of a node in state['timings'] and its name in state['trace'] (shown live over SSE)."""
    def deco(fn):
        @functools.wraps(fn)
        async def wrap(state, config):
            t = time.time()
            out = dict(await fn(state, config) or {})
            out["timings"] = {name: round(time.time() - t, 3)}
            out["trace"] = [name]
            return out
        return wrap
    return deco


async def llm_json(config, step, messages):
    d, u = deps(config), usage(config)
    return await asyncio.to_thread(d.llm.json, step, messages, u)


async def llm_batch(config, step, batch):
    d, u = deps(config), usage(config)
    return await asyncio.to_thread(d.llm.json_batch, step, batch, u)


WORD = re.compile(r"[a-z][a-z\-]{3,}")
STOP = set("with that this from have been which their there these those into also such than more less most very about "
           "should could would being they them were when what where while your other some each only does".split())


def stems(text: str) -> set[str]:
    """Spelling-tolerant word stems (British/American 'ae', first 5 letters) for the note check."""
    return {w.replace("ae", "e").replace("oe", "e")[:5] for w in WORD.findall(text.lower()) if w not in STOP}
