"""Records Agent: log / show the user's records through the users MCP server; deleting a record needs the user's approval
(LangGraph interrupt = human-in-the-loop on an irreversible data operation)."""
from __future__ import annotations

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


@timed("confirm_delete")
async def confirm_delete(state, config):
    recs = (await deps(config).users("list_records", user_id=state["user_id"], limit=1))["records"]
    if not recs:
        return {"answer": "There is no record to delete.", "pending_delete": {}}
    decision = interrupt({"action": "delete_record", "record": recs[0],
                          "question": f"Delete this record? \"{recs[0]['text']}\" ({recs[0]['ts']})"})
    if decision in (True, "yes", "approve", "approved"):
        await deps(config).users("delete_record", user_id=state["user_id"], record_id=recs[0]["id"])
        return {"answer": f"Deleted: \"{recs[0]['text']}\".", "pending_delete": recs[0]}
    return {"answer": "Okay, nothing was deleted.", "pending_delete": {}}
