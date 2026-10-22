"""Writer (LLM) and Validator (code): the answer is checked against the dangerous-advice rules; one rewrite at most, within
a wall-clock budget (whichever limit comes first); still-unsafe sentences are removed before the user sees them."""
from __future__ import annotations

import time

from coach.agents.common import deps, llm_json, timed
from coach.agents.prompts import GENERAL_QUESTION, TRANSLATE, WRITER_SYSTEM, WRITER_USER
from coach.safety.rules import check_answer


@timed("writer")
async def writer(state, config):
    notes = "\n".join(f"- ({dom}) {n['note']} [{n.get('source', '')}]" for dom, ev in sorted(state.get("evidence", {}).items())
                      for n in ev.get("notes", [])) or "(none)"
    safety = "\n".join(f"- {s['advice']} [{s['source']}]" for s in state.get("safety_notes", [])) or "(none)"
    user = WRITER_USER.format(profile=state["profile"], notes=notes, safety=safety, question=state["message"])
    if state.get("about_user") is False:
        user += GENERAL_QUESTION
    if state.get("issues"):
        user += ("\n\nYour previous answer had these safety problems; write it again without them:\n- "
                 + "\n- ".join(f"{i['rule']}: {i['quote']}" for i in state["issues"]))
    j = await llm_json(config, "writer" if not state.get("issues") else "writer_retry",
                       [("system", WRITER_SYSTEM), ("user", user)])
    return {"answer": str(j.get("answer", "")).strip(), "answer_ko": str(j.get("answer_ko", "")).strip(),
            "summary_ko": str(j.get("summary_ko", "")).strip()}


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
    out = {"answer": ans, "removed": removed}
    if ans != state["answer"]:   # the Korean text of the old answer no longer matches: translate the final answer once
        j = await llm_json(config, "translate", [("user", TRANSLATE.format(answer=ans))])
        out |= {"answer_ko": str(j.get("answer_ko", "")).strip(), "summary_ko": str(j.get("summary_ko", "")).strip()}
    return out
