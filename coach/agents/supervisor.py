"""Supervisor: emergency guard (code, before any LLM), then the LLM router that picks the agent."""
from __future__ import annotations

import time

from coach.agents.common import deps, llm_json, timed
from coach.agents.prompts import SUPERVISOR
from coach.safety.rules import EMERGENCY_REPLY, MED_CHANGE_REPLY, is_emergency

ROUTES = {"exercise", "med_change", "log", "my_data", "delete_record", "chat"}


@timed("guard")
async def guard(state, config):
    prof = (await deps(config).users("get_profile", user_id=state["user_id"]))["profile"]
    return {"profile": prof, "started": time.time(), "retries": 0,
            "route": "emergency" if is_emergency(state["message"]) else ""}


@timed("supervisor")
async def supervisor(state, config):
    j = await llm_json(config, "supervisor", [("user", SUPERVISOR.format(profile=state["profile"], message=state["message"]))])
    route = j.get("route") if j.get("route") in ROUTES else "chat"
    return {"route": route, "route_reason": str(j.get("reason", ""))}


@timed("emergency_reply")
async def emergency_reply(state, config):
    return {"answer": EMERGENCY_REPLY}


@timed("med_change_reply")
async def med_change_reply(state, config):
    return {"answer": MED_CHANGE_REPLY}
