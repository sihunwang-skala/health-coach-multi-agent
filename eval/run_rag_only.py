"""RAG comparison: our agentic RAG ALONE vs the standard RAG (Before), on the 60 health questions.

To isolate the retrieval method, this re-uses exactly the notes that the single agent's agentic RAG found
(eval/results/single.json: query chain -> hybrid search -> picker -> note check) and only writes the answer again with the
same writer prompt but WITHOUT the safety layer: no rule-table notes, no dangerous-advice check, no retry.
So standard RAG vs this file differs only in how evidence is found and handed to the writer.

    .venv/bin/python eval/run_rag_only.py                 # our writer prompt, about $0.05 -> agentic_rag.json
    .venv/bin/python eval/run_rag_only.py --same-prompt   # the standard RAG's own answer prompt (BASELINE), about $0.02
                                                          # -> agentic_rag_same_prompt.json
--same-prompt is the strict retrieval-only comparison: both systems then use the identical answer prompt (which allows
general knowledge when the evidence is silent), so only the evidence handed to it differs: standard RAG = top-5 passages,
agentic RAG = the checked notes. Latency and cost = the single agent's retrieval steps + this answer call.
"""
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from coach.agents.prompts import BASELINE  # noqa: E402
from coach.agents.writer import writer  # noqa: E402
from coach.deps import default_container  # noqa: E402
from coach.llm import Usage  # noqa: E402

R = ROOT / "eval" / "results"
ANSWER_STEPS = ("writer", "writer_retry")


async def main():
    deps = default_container()
    s = deps.settings
    Q = json.loads((ROOT / "eval" / "questions.json").read_text())
    single = json.loads((R / "single.json").read_text())
    same = "--same-prompt" in sys.argv
    out_path = R / ("agentic_rag_same_prompt.json" if same else "agentic_rag.json")
    out = json.loads(out_path.read_text()) if out_path.exists() else {}
    for h in Q["health"]:
        if h["id"] in out:
            continue
        src = single[h["id"]]
        prof = (await deps.users("get_profile", user_id=h["user"]))["profile"]
        u = Usage()
        t = time.time()
        if same:
            ev = "\n\n".join(f"[{n.get('source', '')}] {n['note']}" for n in src["notes"])
            j = await asyncio.to_thread(deps.llm.json, "baseline_answer",
                                        [("user", BASELINE.format(profile=prof, evidence=ev, question=h["q"]))], u)
            st = {"answer": str(j.get("answer", ""))}
        else:
            st = await writer({"message": h["q"], "profile": prof, "evidence": {"all": {"notes": src["notes"]}}, "safety_notes": []},
                              {"configurable": {"deps": deps, "usage": u}})
        w_lat = time.time() - t
        # retrieval part of the single agent (everything except writing and checking the answer)
        ret = {k: v for k, v in src["by_step"].items() if k not in ANSWER_STEPS}
        ret_cost = sum(v["in"] * s.price_in + v["out"] * s.price_out for v in ret.values()) / 1e6 + src["embed_tokens"] * s.price_embed / 1e6
        ret_lat = sum(v for k, v in src["timings"].items() if k.startswith("all."))
        out[h["id"]] = {"system": "agentic_rag_same_prompt" if same else "agentic_rag", "user": h["user"], "q": h["q"], "kind": "health", "route": "rag",
                        "answer": st["answer"], "notes": src["notes"], "passages": src.get("passages", []),
                        "passage_texts": src.get("passage_texts", []), "latency_s": round(ret_lat + w_lat, 2),
                        "calls": sum(v["calls"] for v in ret.values()) + u.calls,
                        "cost": round(ret_cost + u.cost(s.price_in, s.price_out), 6), "retries": 0}
        out_path.write_text(json.dumps(out, indent=1, ensure_ascii=False))
        print(f"agentic_rag {h['id']:14} {out[h['id']]['latency_s']:6.2f}s ${out[h['id']]['cost']:.5f}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
