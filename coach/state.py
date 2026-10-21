"""Graph state. Parallel agents write different keys; timings are merged with a reducer."""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def merge(a: dict, b: dict) -> dict:
    return {**(a or {}), **(b or {})}


class CoachState(TypedDict, total=False):
    user_id: str
    message: str
    profile: str
    route: str
    route_reason: str
    queries: list[str]
    results: dict[str, list[dict]]       # query -> passages from the papers MCP server
    picks: list[dict]
    notes: list[dict]
    dropped_notes: list[dict]
    safety_notes: list[dict]             # rule table hits (Safety Agent)
    answer: str
    issues: list[dict]
    retries: int
    removed: list[str]
    records: list[dict]
    pending_delete: dict
    titles: dict[str, str]
    timings: Annotated[dict[str, float], merge]
    trace: Annotated[list[str], operator.add]
    started: float
    meta: dict[str, Any]


class EvidenceIn(TypedDict, total=False):
    """What the Evidence Agent subgraph receives from the supervisor graph (no trace, so it is not duplicated)."""
    message: str
    profile: str
