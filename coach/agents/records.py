"""Records Agent: log / show the user's records through the users MCP server; deleting a record needs the user's approval
(LangGraph interrupt = human-in-the-loop on an irreversible data operation)."""
from __future__ import annotations

import re

from langgraph.types import interrupt

from coach.agents.common import deps, llm_json, timed
from coach.agents.prompts import PROFILE_REPLY


@timed("records")
async def records(state, config):
    d = deps(config)
    if state["route"] == "log":
        await d.users("log_record", user_id=state["user_id"], text=state["message"])
    recs = (await d.users("list_records", user_id=state["user_id"], limit=10))["records"]
    j = await llm_json(config, "records_reply", [("user", PROFILE_REPLY.format(
        profile=state["profile"], records="; ".join(f"{r['ts']} {r['text']}" for r in recs) or "(none)", message=state["message"]))])
    return {"answer": str(j.get("answer", "")), "records": recs}


# "the last record" / "the one I just added" only; "last week", "last night" etc. must go to the LLM match, never to "newest"
LATEST = re.compile(r"(?i)\b(last|latest|most recent|previous)\s+(record|entry|log|one|item)\b|\bjust (now|added|logged)\b|마지막\s*(으로 (적은|남긴|쓴)\s*)?(기록|항목|것)|방금|가장 최근|최근 기록")

PICK_RECORD = """You help an older adult delete ONE of their own logged records (a meal, an activity or a glucose reading).
Goal: find the record the user means, so the app can ask them to confirm exactly that record. A wrong record must never be deleted.
Task: from the numbered records choose the ones the user's message clearly refers to (what it says: food, activity, reading, day or time).
Do not guess. If nothing clearly matches, return an empty list. If several match equally well, return all of them.
Return JSON {{"ids": [record id, ...]}}.

Records (newest first):
{records}

User message: {message}"""


@timed("pick_delete_target")
async def pick_delete_target(state, config):
    """Which record does the user mean? 'last / latest' is decided by code; anything else by one LLM call whose ids are checked against the
    user's own records. 0 or several candidates are not guessed: the next node asks the user to choose."""
    recs = (await deps(config).users("list_records", user_id=state["user_id"], limit=30))["records"]
    if not recs:
        return {"delete_options": []}
    if LATEST.search(state["message"]):
        return {"delete_options": [recs[0]]}
    j = await llm_json(config, "delete_pick", [("user", PICK_RECORD.format(
        records="\n".join(f"id {r['id']}: {r['ts']} {r['text']}" for r in recs), message=state["message"]))])
    ids = {int(i) for i in (j.get("ids") or []) if str(i).lstrip("-").isdigit()}
    return {"delete_options": [r for r in recs if r["id"] in ids]}


def _same(a: dict, b: dict) -> bool:
    return a.get("id") == b.get("id") and a.get("text") == b.get("text")


@timed("confirm_delete")
async def confirm_delete(state, config):
    """Human approval before an irreversible operation. The user sees the exact record; only an explicit yes deletes it, and only that
    record id. Zero or several candidates are never guessed: the user picks one first (or cancels)."""
    d = deps(config)
    options = state.get("delete_options") or []
    latest = (await d.users("list_records", user_id=state["user_id"], limit=8))["records"]
    if not latest:
        return {"answer": "There is no record to delete.", "pending_delete": {}}
    target = options[0] if len(options) == 1 else None
    if target is None:
        shown = options or latest
        pick = interrupt({"action": "choose_record", "options": shown,
                          "question": "Which record do you mean?" if options else "I could not tell which record you mean. Which one?"})
        target = next((r for r in shown if isinstance(pick, int) and r["id"] == pick), None)
        if target is None:
            return {"answer": "Okay, nothing was deleted.", "pending_delete": {}}
    decision = interrupt({"action": "delete_record", "record": target,
                          "question": f"Delete this record? \"{target['text']}\" ({target['ts']})"})
    if decision in (True, "yes"):
        now = (await d.users("list_records", user_id=state["user_id"], limit=100))["records"]
        if not any(_same(target, r) for r in now):
            return {"answer": "That record no longer exists.", "pending_delete": {}}
        n = (await d.users("delete_record", user_id=state["user_id"], record_id=target["id"])).get("deleted", 0)
        return ({"answer": f"Deleted: \"{target['text']}\".", "pending_delete": target} if n == 1
                else {"answer": "The record could not be deleted.", "pending_delete": {}})
    return {"answer": "Okay, nothing was deleted.", "pending_delete": {}}
