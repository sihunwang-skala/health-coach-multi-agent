"""Before / After on the same inputs. Before = standard RAG agent (question -> dense top-5 -> one answer). After = the
multi-agent graph. Every message runs one at a time (sequential), so the latency is the latency a user would see.
    .venv/bin/python eval/run_eval.py [--only after|before] [--ids a,b]
Results: eval/results/{before,after}.json (answers, passages, latency, calls, tokens, cost, route, retries)."""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from coach.deps import default_container  # noqa: E402
from coach.graph import build_graph  # noqa: E402
from coach.runner import run_after, run_before  # noqa: E402

OUT = ROOT / "eval" / "results"


async def main():
    a = sys.argv
    only = a[a.index("--only") + 1] if "--only" in a else None
    ids = set(a[a.index("--ids") + 1].split(",")) if "--ids" in a else None
    Q = json.loads((ROOT / "eval" / "questions.json").read_text())
    items = [("health", x) for x in Q["health"]] + [("refusal", x) for x in Q["refusal"]] + [("routing", x) for x in Q["routing"]]
    items = [(k, x) for k, x in items if not ids or x["id"] in ids]
    deps, graph = default_container(), build_graph()
    for system in ("before", "after"):
        if only and system != only:
            continue
        path = OUT / f"{system}.json"
        res = json.loads(path.read_text()) if path.exists() else {}
        for kind, x in items:
            if x["id"] in res and not ids:
                continue
            r = await (run_after(graph, deps, x["user"], x["q"]) if system == "after" else run_before(deps, x["user"], x["q"]))
            if r.get("interrupt"):  # delete request: the evaluation declines, so nothing is deleted
                r = {**r, "interrupt_shown": r["interrupt"]}
            res[x["id"]] = {"kind": kind, "user": x["user"], "q": x["q"], **{k: v for k, v in r.items() if k != "interrupt"}}
            path.write_text(json.dumps(res, indent=1, ensure_ascii=False))
            print(f"{system} {x['id']:14} {r.get('route', ''):12} {r['latency_s']:6.2f}s calls {r['calls']:2} ${r['cost']:.5f} retries {r.get('retries', 0)}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
