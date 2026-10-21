"""Evidence Agent (compiled subgraph): query chain (4 LLM calls) -> paper search through MCP -> per-query picker
(LLM, batched) -> note check (code). Same pipeline as the diabetes PoC final model."""
from __future__ import annotations

import re

from langgraph.graph import END, START, StateGraph

from coach.agents.common import MED_TERMS, deps, llm_batch, llm_json, stems, timed
from coach.agents.prompts import CONDITIONS, DECOMPOSE, PICKER, STAGE1, STEPBACK
from coach.state import CoachState, EvidenceIn

FIELD = re.compile(r"\b[a-z]+(_[a-z]+)*:\s")


def _broken(x: str, earlier: list[str], question: str, stepback=False) -> str:
    xl = x.strip().lower().rstrip(".?")
    for e in earlier:
        el = e.strip().lower().rstrip(".?")
        if xl == el or (len(el) >= 20 and xl.startswith(el)):
            return "it repeats an earlier query - write a new natural phrase"
    if FIELD.search(x):
        return "it contains profile field names - write a natural phrase"
    if stepback and question.lower().rstrip("?") in xl:
        return "it repeats the question - ask the broader general question"
    return ""


async def _checked(config, step, prompt, earlier, question, stepback=False):
    qs = [str(x) for x in (await llm_json(config, step, [("user", prompt)])).get("queries", []) if str(x).strip()]
    good, bad = [], []
    for x in qs:
        why = _broken(x, earlier + good, question, stepback)
        (bad if why else good).append((x, why) if why else x)
    if bad:  # one retry with the reasons, then drop what is still broken
        fb = prompt + "\n\nThese queries break a rule; rewrite each one (same order):\n" + "\n".join(f"- {x} ({w})" for x, w in bad)
        for x in [str(x) for x in (await llm_json(config, step + "_retry", [("user", fb)])).get("queries", [])][:len(bad)]:
            if not _broken(x, earlier + good, question, stepback):
                good.append(x)
    return good


@timed("make_queries")
async def make_queries(state, config):
    q, prof = state["message"], "User profile (health fields): " + state["profile"] + "\n"
    terms = [t for pat, t in MED_TERMS if re.search(pat, state["profile"].lower())]
    j = await llm_json(config, "query_stage1", [("user", STAGE1.format(profile=prof, question=q))])
    subj, term = str(j.get("subject") or q).strip(), str(j.get("paper_term") or "").strip()
    conds = [str(c) for c in j.get("conditions", []) if str(c).strip()]
    s1 = subj + (f" ({term})" if term and term.lower() not in subj.lower() else "") + (" in " + " and ".join(conds) if conds else "")
    med = [f"{q} {' '.join(terms)} older adults"] if terms else []
    earlier = [q, s1] + med
    sb = (await _checked(config, "query_stepback", STEPBACK.format(s1=subj + (f" ({term})" if term else "")), earlier, q, True))[:1]
    earlier += sb
    cq = await _checked(config, "query_conditions", CONDITIONS.format(profile=prof, question=q, terms="; ".join(terms) or "none",
                                                                        earlier="\n".join(earlier)), earlier, q)
    earlier += cq
    dq = await _checked(config, "query_decompose", DECOMPOSE.format(profile=prof, question=q, earlier="\n".join(earlier)), earlier, q)
    return {"queries": list(dict.fromkeys([q, s1] + med + sb + cq + dq))}


@timed("retrieve_mcp")
async def retrieve(state, config):
    d = deps(config)
    r = await d.papers("search_papers", queries=state["queries"], k=d.settings.top_k)
    config["configurable"]["usage"].embed_tokens += r.get("embed_tokens", 0)
    titles = {h["pmcid"]: h["title"] for hs in r["results"].values() for h in hs}
    return {"results": r["results"], "titles": titles}


@timed("pick_notes")
async def pick_notes(state, config):
    prof = "User profile (health fields): " + state["profile"] + "\n"
    batch = []
    for q in state["queries"]:
        hits = state["results"].get(q, [])
        passages = "\n\n".join(f"[{n + 1}] ({h['pmcid']}) {h['text']}" for n, h in enumerate(hits))
        batch.append([("user", PICKER.format(profile=prof, question=state["message"], query=q, passages=passages))])
    outs = await llm_batch(config, "picker", batch)
    picks = []
    for q, j in zip(state["queries"], outs):
        hits = state["results"].get(q, [])
        best = [hits[n - 1]["pid"] for n in j.get("best", []) if isinstance(n, int) and 1 <= n <= len(hits)][:2]
        notes = [n for n in j.get("notes", []) if isinstance(n, dict) and n.get("note")]
        picks.append({"query": q, "best": best, "notes": notes})
    return {"picks": picks}


@timed("verify_notes")
async def verify_notes(state, config):
    """Output check before the next step (diabetes PoC L105/L121/L129): drop duplicate notes, and drop a note that is not
    in the passages the picker saw - 2+ words absent from its source passages, or 1 absent word copied from the query."""
    seen, notes, dropped = set(), [], []
    for p in state["picks"]:
        if p["best"] and set(p["best"]) <= seen:
            continue
        seen.update(p["best"])
        shown = {}
        for h in state["results"].get(p["query"], []):
            shown.setdefault(h["pmcid"], set()).update(stems(h["text"]))
        for n in p["notes"]:
            src = shown.get(n.get("source", ""), set())
            novel = stems(n["note"]) - src
            if not src or len(novel) >= 2 or (novel & stems(p["query"])):
                dropped.append({**n, "novel": sorted(novel)})
                continue
            w = set(re.findall(r"\w+", n["note"].lower()))
            if any(n.get("source") == m.get("source") and len(w & set(re.findall(r"\w+", m["note"].lower()))) >= 0.7 * max(1, min(len(w), len(set(re.findall(r"\w+", m["note"].lower()))))) for m in notes):
                continue
            notes.append(n)
    return {"notes": notes, "dropped_notes": dropped}


def build_evidence_agent():
    g = StateGraph(CoachState, input_schema=EvidenceIn)
    for name, fn in [("make_queries", make_queries), ("retrieve", retrieve), ("pick_notes", pick_notes), ("verify_notes", verify_notes)]:
        g.add_node(name, fn)
    g.add_edge(START, "make_queries")
    g.add_edge("make_queries", "retrieve")
    g.add_edge("retrieve", "pick_notes")
    g.add_edge("pick_notes", "verify_notes")
    g.add_edge("verify_notes", END)
    return g.compile()
