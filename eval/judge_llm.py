"""Cheap LLM-as-judge (gpt-4o-mini) on the same rubric points, only to measure how far it agrees with the main grades
(Claude, eval/scores_claude.json). One call per answer (48 calls, about $0.01). Review item: "judge vs human agreement"."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import coach.config  # noqa: E402,F401  (loads .env)
from coach.llm import OpenAIJSON, Usage  # noqa: E402

PROMPT = """Grade an exercise coach's answer for an older adult with type 2 diabetes against the must-answer points.
For each point: 1 = conveyed correctly and specifically (numbers present when the point has a number), 0.5 = right
direction but vague or incomplete, 0 = missing or contradicted. Judge only what the ANSWER says; different wording is fine.
Return JSON {{"scores": [numbers in point order]}}.

Question: {q}
Points:
{points}
Answer: {a}"""


def main():
    Q = json.loads((ROOT / "eval" / "questions.json").read_text())
    llm, u, out = OpenAIJSON("gpt-4o-mini"), Usage(), {}
    for s in ("before", "after"):
        rows = json.loads((ROOT / "eval" / "results" / f"{s}.json").read_text())
        batch = [[("user", PROMPT.format(q=h["q"], points="\n".join(f"{i + 1}. {p}" for i, p in enumerate(h["points"])),
                                         a=rows[h["id"]]["answer"]))] for h in Q["health"]]
        res = llm.json_batch("judge", batch, u)
        out[s] = {h["id"]: [float(x) for x in r.get("scores", [])][:len(h["points"])] for h, r in zip(Q["health"], res)}
    (ROOT / "eval" / "judge_llm.json").write_text(json.dumps(out, indent=1))
    print(f"judge calls {u.calls} | cost ${u.cost(0.15, 0.6):.4f}")


if __name__ == "__main__":
    main()
