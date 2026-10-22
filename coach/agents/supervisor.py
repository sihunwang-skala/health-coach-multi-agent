"""Supervisor: emergency guard (code, before any LLM), then the LLM router that picks the agent."""
from __future__ import annotations

import time

from coach.agents.common import deps, llm_json, timed
from coach.agents.prompts import SUPERVISOR
from coach.safety.rules import EMERGENCY_REPLY, HANDOFF_REPLY, MED_CHANGE_REPLY, OTHER_USER_REPLY, PRIVACY_INFO_REPLY, is_emergency

ROUTES = {"handoff", "other_user", "privacy_info", "emergency", "diet", "exercise", "diet_exercise", "med_change", "log", "my_data", "delete_record", "chat"}


@timed("guard")
async def guard(state, config):
    prof = (await deps(config).users("get_profile", user_id=state["user_id"]))["profile"]
    return {"profile": prof, "started": time.time(), "retries": 0,
            "route": "emergency" if is_emergency(state["message"]) else ""}


@timed("supervisor")
async def supervisor(state, config):
    j = await llm_json(config, "supervisor", [("user", SUPERVISOR.format(profile=state["profile"], message=state["message"]))])
    route = j.get("route") if j.get("route") in ROUTES else "chat"
    return {"route": route, "about_user": j.get("about_user") is not False, "route_reason": str(j.get("reason", ""))}


@timed("emergency_reply")
async def emergency_reply(state, config):
    return {"answer": EMERGENCY_REPLY}


@timed("med_change_reply")
async def med_change_reply(state, config):
    return {"answer": MED_CHANGE_REPLY}


FIXED = {"handoff": HANDOFF_REPLY, "other_user": OTHER_USER_REPLY, "privacy_info": PRIVACY_INFO_REPLY}


@timed("fixed_reply")
async def fixed_reply(state, config):
    """Service and privacy situations: fixed, reviewed text (no LLM, no papers)."""
    return {"answer": FIXED[state["route"]]}
