"""Run one message through the After system (graph) or the Before system (standard RAG), with cost and latency."""
from __future__ import annotations

import time
import uuid

from coach.agents.prompts import BASELINE
from coach.deps import Container
from coach.llm import Usage


async def run_after(graph, deps: Container, user_id: str, message: str, thread_id: str | None = None, resume=None) -> dict:
    from langgraph.types import Command

    u = Usage()
    tid = thread_id or str(uuid.uuid4())
    cfg = {"configurable": {"deps": deps, "usage": u, "thread_id": tid}, "recursion_limit": 30}
    t = time.time()
    inp = Command(resume=resume) if resume is not None else {"user_id": user_id, "message": message, "trace": [], "timings": {}}
    st = await graph.ainvoke(inp, cfg)
    snap = graph.get_state(cfg)
    pending = [i.value for t_ in snap.tasks for i in (t_.interrupts or [])]
    s = deps.settings
    return {"system": "after", "answer": st.get("answer", ""), "route": st.get("route", ""), "trace": st.get("trace", []),
            "timings": st.get("timings", {}),
            "queries": [q for ev in st.get("evidence", {}).values() for q in ev.get("queries") or []],
            "notes": [n for ev in st.get("evidence", {}).values() for n in ev.get("notes") or []],
            "dropped_notes": [n for ev in st.get("evidence", {}).values() for n in ev.get("dropped_notes") or []],
            "domains": sorted(st.get("evidence", {})), "safety_notes": st.get("safety_notes", []),
            "issues": st.get("issues", []), "retries": st.get("retries", 0), "removed": st.get("removed", []),
            "passages": sorted({h["pid"] for ev in st.get("evidence", {}).values() for p in ev.get("picks") or []
                                for h in (ev.get("results") or {}).get(p["query"], []) if h["pid"] in p["best"]}),
            "passage_texts": [h["text"] for ev in st.get("evidence", {}).values() for p in ev.get("picks") or []
                              for h in (ev.get("results") or {}).get(p["query"], []) if h["pid"] in p["best"]],
            "latency_s": round(time.time() - t, 2), "calls": u.calls, "tokens_in": u.tokens_in, "tokens_out": u.tokens_out,
            "embed_tokens": u.embed_tokens, "cost": round(u.cost(s.price_in, s.price_out, s.price_embed), 6),
            "by_step": u.by_step, "interrupt": pending[0] if pending else None, "thread_id": tid}


async def run_before(deps: Container, user_id: str, message: str) -> dict:
    """Before = standard RAG agent: profile + the question -> dense top-5 passages -> one answer call. No routing, no safety
    rules, no checks (the usual single RAG chatbot)."""
    import asyncio

    u = Usage()
    t = time.time()
    prof = (await deps.users("get_profile", user_id=user_id))["profile"]
    r = await deps.papers("search_baseline", question=message, k=5)
    u.embed_tokens += r.get("embed_tokens", 0)
    ev = "\n\n".join(f"[{h['pmcid']}] {h['text']}" for h in r["results"])
    j = await asyncio.to_thread(deps.llm.json, "baseline_answer", [("user", BASELINE.format(profile=prof, evidence=ev, question=message))], u)
    s = deps.settings
    return {"system": "before", "answer": str(j.get("answer", "")), "route": "rag", "passages": [h["pid"] for h in r["results"]],
            "passage_texts": [h["text"] for h in r["results"]],
            "titles": {h["pmcid"]: h["title"] for h in r["results"]}, "latency_s": round(time.time() - t, 2), "calls": u.calls,
            "tokens_in": u.tokens_in, "tokens_out": u.tokens_out, "embed_tokens": u.embed_tokens,
            "cost": round(u.cost(s.price_in, s.price_out, s.price_embed), 6), "retries": 0}
