"""Supervisor: emergency guard (code, before any LLM), then the LLM router that picks the agent."""
from __future__ import annotations

import re
import time

from coach.agents.common import deps, llm_json, timed
from coach.agents.prompts import SUPERVISOR
from coach.safety.rules import applicable_rules, EMERGENCY_REPLY, HANDOFF_REPLY, MED_CHANGE_REPLY, OTHER_USER_REPLY, PRIVACY_INFO_REPLY, is_emergency

DOMAINS = {"diet": ("diet",), "exercise": ("exercise",), "diet_exercise": ("diet", "exercise")}
ROUTES = {"handoff", "other_user", "privacy_info", "emergency", "diet", "exercise", "diet_exercise", "med_change", "log", "my_data", "delete_record", "chat"}


@timed("guard")
async def guard(state, config):
    prof = (await deps(config).users("get_profile", user_id=state["user_id"]))["profile"]
    return {"profile": prof, "started": time.time(), "retries": 0,
            "route": "emergency" if is_emergency(state["message"]) else ""}


# health_deep whenever the message names a medicine, low blood sugar, a complication or alcohol (docs/HYBRID_UI.md §4)
DEEP_TERMS = re.compile(
    r"(?i)insulin|sulfonyl|glimepiride|gliclazide|glipizide|metformin|medicine|medication|pill|dose|hypo|low blood sugar|"
    r"kidney|renal|retinopath|neuropath|heart|cardiac|stroke|foot ulcer|pregnan|alcohol|beer|wine|"
    r"인슐린|약|저혈당|신장|콩팥|망막|신경병증|심장|협심증|뇌졸중|발 ?궤양|임신|술|음주|맥주|소주|와인")


def health_path(route: str, about_user: bool, message: str, profile: str = "") -> tuple[str, str]:
    """Deterministic rule first; the structured router output (route, about_user) second. Length is not used.
    The user's stored profile counts too: users do not type their conditions, so if any safety rule applies to this profile
    and message (insulin, retinopathy, kidney disease ...) the question goes deep even when its wording is general."""
    if profile and applicable_rules(profile, message, DOMAINS.get(route, ("exercise",))):
        return "health_deep", "a safety rule applies to this user's profile"
    if route == "diet_exercise":
        return "health_deep", "two topics"
    if about_user:
        return "health_deep", "own health question (conditions and medicines matter)"
    if DEEP_TERMS.search(message):
        return "health_deep", "medicine, low blood sugar, complication or alcohol in the question"
    return "health_simple", "general single-topic question"


@timed("supervisor")
async def supervisor(state, config):
    j = await llm_json(config, "supervisor", [("user", SUPERVISOR.format(profile=state["profile"], message=state["message"]))])
    route = j.get("route") if j.get("route") in ROUTES else "chat"
    out = {"route": route, "about_user": j.get("about_user") is not False, "route_reason": str(j.get("reason", ""))}
    if route in ("diet", "exercise", "diet_exercise"):
        path, why = health_path(route, out["about_user"], state["message"], state["profile"])
        if not deps(config).settings.health_lite:
            path, why = "health_deep", "health_simple is switched off (COACH_HEALTH_LITE)"
        out.update(path=path, path_reason=why)
    return out


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
