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
    titles: Annotated[dict[str, str], merge]
    evidence: Annotated[dict[str, dict], merge]   # domain -> {queries, notes, picks, results, dropped_notes} (parallel agents)
    timings: Annotated[dict[str, float], merge]
    trace: Annotated[list[str], operator.add]
    started: float
    meta: dict[str, Any]


class EvidenceState(TypedDict, total=False):
    """Private state of one Evidence Agent subgraph (diet or exercise); the parent sees only what the wrapper returns."""
    message: str
    profile: str
    domain: str
    queries: list[str]
    results: dict[str, list[dict]]
    titles: dict[str, str]
    picks: list[dict]
    notes: list[dict]
    dropped_notes: list[dict]
    timings: Annotated[dict[str, float], merge]
    trace: Annotated[list[str], operator.add]
