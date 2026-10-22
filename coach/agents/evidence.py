"""Evidence Agent (compiled subgraph): query chain (4 LLM calls) -> paper search through MCP -> per-query picker
(LLM, batched) -> note check (code). Same pipeline as the diabetes PoC final model."""
from __future__ import annotations

import re

from langgraph.graph import END, START, StateGraph

from coach.agents.common import MED_TERMS, deps, llm_batch, llm_json, stems, timed
from coach.agents.prompts import CONDITIONS, DECOMPOSE, PICKER, STAGE1, STEPBACK, TOPIC
from coach.state import EvidenceState

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
    # [발표 코드 2-1 | Agentic RAG 1단계: 검색 질문 만들기]
    # 질문을 여러 개의 검색어로 바꿉니다.
    # 질환과 약에 맞는 논문을 더 잘 찾기 위한 단계입니다.
    q, prof = state["message"], ("User profile (health fields): " + state["profile"] + "\n") if state["profile"] else ""
    topic, dom = TOPIC[state["domain"]], state["domain"]
    terms = [t for pat, t in MED_TERMS if re.search(pat, state["profile"].lower())]
    if dom == "diet":
        terms = [t.replace("exercise ", "").replace(" exercise", "").replace(" response to", " and") for t in terms]
    j = await llm_json(config, f"{dom}_query_stage1", [("user", STAGE1.format(topic=topic, profile=prof, question=q))])
    subj, term = str(j.get("subject") or q).strip(), str(j.get("paper_term") or "").strip()
    conds = [str(c) for c in j.get("conditions", []) if str(c).strip()]
    s1 = subj + (f" ({term})" if term and term.lower() not in subj.lower() else "") + (" in " + " and ".join(conds) if conds else "")
    med = [f"{q} {' '.join(terms)} older adults"] if terms else []
    earlier = [q, s1] + med
    sb = (await _checked(config, f"{dom}_query_stepback", STEPBACK.format(s1=subj + (f" ({term})" if term else "")), earlier, q, True))[:1]
    earlier += sb
    cq = await _checked(config, f"{dom}_query_conditions", CONDITIONS.format(topic=topic, profile=prof, question=q, terms="; ".join(terms) or "none",
                                                                        earlier="\n".join(earlier)), earlier, q)
    earlier += cq
    dq = await _checked(config, f"{dom}_query_decompose", DECOMPOSE.format(topic=topic, profile=prof, question=q, earlier="\n".join(earlier)), earlier, q)
    return {"queries": list(dict.fromkeys([q, s1] + med + sb + cq + dq))}


@timed("retrieve_mcp")
async def retrieve(state, config):
    # [발표 코드 2-2 | Agentic RAG 2단계: MCP로 논문 검색하기]
    # 논문을 찾는 일은 papers MCP에 맡깁니다.
    # Agent가 논문 파일을 직접 다루지 않게 나눠 둔 것입니다.
    d = deps(config)
    r = await d.papers("search_papers", queries=state["queries"], k=d.settings.top_k,
                       domain="" if state["domain"] == "all" else state["domain"])
    config["configurable"]["usage"].embed_tokens += r.get("embed_tokens", 0)
    titles = {h["pmcid"]: h["title"] for hs in r["results"].values() for h in hs}
    return {"results": r["results"], "titles": titles}


@timed("pick_notes")
async def pick_notes(state, config):
    # [발표 코드 2-3 | Agentic RAG 3단계: 필요한 근거 고르기]
    # 찾은 논문 문단 중 답변에 필요한 내용만 고릅니다.
    # 너무 많은 내용을 답변에 넣지 않기 위한 단계입니다.
    prof = ("User profile (health fields): " + state["profile"] + "\n") if state["profile"] else ""
    batch = []
    for q in state["queries"]:
        hits = state["results"].get(q, [])
        passages = "\n\n".join(f"[{n + 1}] ({h['pmcid']}) {h['text']}" for n, h in enumerate(hits))
        batch.append([("user", PICKER.format(topic=TOPIC[state["domain"]], profile=prof, question=state["message"], query=q, passages=passages))])
    outs = await llm_batch(config, f"{state['domain']}_picker", batch)
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
    # [발표 코드 2-4 | Agentic RAG 4단계: 근거가 원문에 있는지 확인하기]
    # 고른 메모가 실제 논문에 있는 내용인지 다시 확인합니다.
    # 논문에 없는 내용은 답변에 사용하지 않습니다.
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
    # [발표 코드 2-5 | Agentic RAG 전체 과정을 subgraph로 묶기]
    # 논문을 찾고 확인하는 과정을 하나의 작은 graph로 묶었습니다.
    # 식단과 운동 Agent가 같은 과정을 사용합니다.
    g = StateGraph(EvidenceState)
    for name, fn in [("make_queries", make_queries), ("retrieve", retrieve), ("pick_notes", pick_notes), ("verify_notes", verify_notes)]:
        g.add_node(name, fn)
    g.add_edge(START, "make_queries")
    g.add_edge("make_queries", "retrieve")
    g.add_edge("retrieve", "pick_notes")
    g.add_edge("pick_notes", "verify_notes")
    g.add_edge("verify_notes", END)
    return g.compile()


_SUBGRAPH = build_evidence_agent()


def evidence_node(domain: str):
    """Parent-graph node for one research agent: runs the compiled subgraph with its own state and returns only its result
    under evidence[domain], so the diet and exercise agents can run in parallel without overwriting each other."""
    # [발표 코드 2-6 | 같은 RAG 흐름을 식단·운동에 재사용하기]
    # 같은 과정을 식단과 운동에 각각 적용합니다.
    # 결과를 따로 저장하기 때문에 동시에 처리할 수 있습니다.
    async def node(state, config):
        # a general question is searched without the user's conditions and medicines (diabetes PoC router: about_user)
        prof = state["profile"] if state.get("about_user", True) else ""
        out = await _SUBGRAPH.ainvoke({"message": state["message"], "profile": prof, "domain": domain,
                                       "timings": {}, "trace": []}, config)
        keep = {k: out.get(k) for k in ("queries", "results", "picks", "notes", "dropped_notes")}
        return {"evidence": {domain: keep}, "titles": out.get("titles", {}),
                "timings": {f"{domain}.{k}": v for k, v in out.get("timings", {}).items()},
                "trace": [f"{domain}_agent"] + [f"{domain}.{t}" for t in out.get("trace", [])]}
    node.__name__ = f"{domain}_agent"
    return node
