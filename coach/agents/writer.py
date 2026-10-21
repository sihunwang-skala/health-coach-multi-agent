"""Writer (LLM) and Validator (code): the answer is checked against the dangerous-advice rules; one rewrite at most, within
a wall-clock budget (whichever limit comes first); still-unsafe sentences are removed before the user sees them."""
from __future__ import annotations

import time

from coach.agents.common import deps, llm_json, timed
from coach.agents.prompts import WRITER_SYSTEM, WRITER_USER
from coach.safety.rules import check_answer


@timed("writer")
async def writer(state, config):
    notes = "\n".join(f"- {n['note']} [{n.get('source', '')}]" for n in state.get("notes", [])) or "(none)"
    safety = "\n".join(f"- {s['advice']} [{s['source']}]" for s in state.get("safety_notes", [])) or "(none)"
    user = WRITER_USER.format(profile=state["profile"], notes=notes, safety=safety, question=state["message"])
    if state.get("issues"):
        user += ("\n\nYour previous answer had these safety problems; write it again without them:\n- "
                 + "\n- ".join(f"{i['rule']}: {i['quote']}" for i in state["issues"]))
    j = await llm_json(config, "writer" if not state.get("issues") else "writer_retry",
                       [("system", WRITER_SYSTEM), ("user", user)])
    return {"answer": str(j.get("answer", "")).strip()}


@timed("validate")
async def validate(state, config):
    return {"issues": check_answer(state["answer"], state["profile"], state["message"], state.get("titles", {}))}


def after_validate(state, config) -> str:
    s = deps(config).settings
    if not state.get("issues"):
        return "done"
    if state.get("retries", 0) < s.max_retries and time.time() - state.get("started", time.time()) < s.time_budget_s:
        return "retry"
    return "remove"


async def retry(state, config):
    return {"retries": state.get("retries", 0) + 1, "trace": ["retry"]}


@timed("remove_unsafe")
async def remove_unsafe(state, config):
    ans, removed = state["answer"], []
    for i in state.get("issues", []):
        if i["quote"] and i["quote"] in ans:
            ans = ans.replace(i["quote"], "").replace("  ", " ").strip()
            removed.append(i["quote"])
    if removed or any(not i["quote"] for i in state.get("issues", [])):
        # the writer ignored the rule table twice: its rules go first, verbatim, so the key safety content is never lost
        rules = " ".join(f"{s_['advice']} [{s_['source']}]" for s_ in state.get("safety_notes", []))
        if rules:
            ans = rules + (" " + ans if ans else "")
    return {"answer": ans, "removed": removed}
