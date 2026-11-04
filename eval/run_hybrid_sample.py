"""Small, separate measurement of the health_simple / health_deep split (NOT the 2026-10-22 100-question evaluation).

Runs a few representative health questions twice - everything on the deep path (COACH_HEALTH_LITE=0, the evaluated service)
and with the split on (COACH_HEALTH_LITE=1) - and writes eval/results_hybrid/<timestamp>.json. Nothing in eval/results/ is
touched. Answer quality is NOT scored here (that needs the Claude grading of eval/scores_claude.json); this records route,
path, escalation, LLM calls, tokens, cost, latency and citation counts so the cost of the split can be compared first.

    .venv/bin/python eval/run_hybrid_sample.py                 # dry run: prints the plan and an upper cost estimate
    .venv/bin/python eval/run_hybrid_sample.py --run [--ids A,B]   # PAID (about $0.005 per question per mode)
Default ids: general (non-personal) questions plus two own-health controls that must stay on the deep path.
"""
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from coach.citations import build  # noqa: E402
from coach.config import Settings  # noqa: E402
from coach.deps import Container, default_container  # noqa: E402
from coach.graph import build_graph  # noqa: E402
from coach.runner import run_after  # noqa: E402

DEFAULT_IDS = ["Exercise-B1", "Exercise-B2", "Diet-B1", "Diet-B2", "Mixed-B1", "Maria-E1", "Walter-E1"]
PER_Q_UPPER = 0.006   # $ per question per mode, upper estimate from the 2026-10-22 mean of $0.0032


async def main():
    ids = next((a.split("=", 1)[1] if "=" in a else sys.argv[sys.argv.index(a) + 1] for a in sys.argv if a.startswith("--ids")), None)
    ids = ids.split(",") if ids else DEFAULT_IDS
    Q = {h["id"]: h for h in json.loads((ROOT / "eval" / "questions.json").read_text())["health"]}
    missing = [i for i in ids if i not in Q]
    if missing:
        sys.exit(f"unknown ids: {missing}")
    print(f"{len(ids)} questions x 2 modes = {2 * len(ids)} runs, upper cost estimate ${2 * len(ids) * PER_Q_UPPER:.3f}")
    if "--run" not in sys.argv:
        print("dry run - add --run to spend money")
        return
    base = default_container()
    rows = []
    for mode, lite in (("deep_only", False), ("split", True)):
        deps = Container(settings=Settings(health_lite=lite), llm=base.llm, papers_server=base.papers_server, users_server=base.users_server)
        for i in ids:
            r = await run_after(build_graph(), deps, Q[i]["user"], Q[i]["q"])
            ev = {d: {"notes": [n for n in r["notes"]], "picks": [], "results": {}} for d in r["domains"]}
            cites = build(r["answer"], ev)
            rows.append({"id": i, "mode": mode, "route": r["route"], "about_user": r.get("about_user"), "trace_escalated": "escalate" in " ".join(r["trace"]),
                         "latency_s": r["latency_s"], "calls": r["calls"], "tokens_in": r["tokens_in"], "tokens_out": r["tokens_out"],
                         "cost": r["cost"], "notes": len(r["notes"]), "issues": r["issues"], "citations_in_answer": len(cites["citations"]),
                         "answer": r["answer"]})
            print(mode, i, r["route"], r["latency_s"], "s", r["calls"], "calls", r["cost"])
    out = ROOT / "eval" / "results_hybrid"
    out.mkdir(exist_ok=True)
    f = out / f"{datetime.now():%Y%m%d_%H%M%S}.json"
    f.write_text(json.dumps({"config": {"model": base.settings.model, "ids": ids, "note": "sample, not the 100-question evaluation"}, "rows": rows},
                            ensure_ascii=False, indent=1))
    print("wrote", f)


asyncio.run(main())
