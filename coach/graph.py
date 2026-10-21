"""Supervisor graph (multi-agent):

  START -> guard (emergency check, code) ─┬─ emergency_reply -> END                     (no LLM, fixed 119 text)
                                          └─ supervisor (LLM router) ─┬─ exercise: [Evidence Agent (subgraph) ‖ Safety Agent]
                                                                      │             -> writer -> validate ─┬─ done -> END
                                                                      │                                    ├─ retry -> writer
                                                                      │                                    └─ remove_unsafe -> END
                                                                      ├─ med_change -> med_change_reply -> END   (fixed text)
                                                                      ├─ log / my_data / chat -> records -> END
                                                                      └─ delete_record -> confirm_delete (interrupt: HITL) -> END
"""
from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from coach.agents.evidence import build_evidence_agent
from coach.agents.records import confirm_delete, records
from coach.agents.safety_agent import safety_agent
from coach.agents.supervisor import emergency_reply, guard, med_change_reply, supervisor
from coach.agents.writer import after_validate, remove_unsafe, retry, validate, writer
from coach.state import CoachState


def build_graph(checkpointer=None):
    g = StateGraph(CoachState)
    g.add_node("guard", guard)
    g.add_node("supervisor", supervisor)
    g.add_node("emergency_reply", emergency_reply)
    g.add_node("med_change_reply", med_change_reply)
    g.add_node("evidence_agent", build_evidence_agent())
    g.add_node("safety_agent", safety_agent)
    g.add_node("writer", writer)
    g.add_node("validate", validate)
    g.add_node("retry", retry)
    g.add_node("remove_unsafe", remove_unsafe)
    g.add_node("records", records)
    g.add_node("confirm_delete", confirm_delete)

    g.add_edge(START, "guard")
    g.add_conditional_edges("guard", lambda s: "emergency" if s["route"] == "emergency" else "route",
                            {"emergency": "emergency_reply", "route": "supervisor"})
    g.add_conditional_edges("supervisor", lambda s: {
        "exercise": ["evidence_agent", "safety_agent"], "med_change": ["med_change_reply"], "delete_record": ["confirm_delete"],
    }.get(s["route"], ["records"]), ["evidence_agent", "safety_agent", "med_change_reply", "confirm_delete", "records"])
    g.add_edge(["evidence_agent", "safety_agent"], "writer")
    g.add_edge("writer", "validate")
    g.add_conditional_edges("validate", after_validate, {"done": END, "retry": "retry", "remove": "remove_unsafe"})
    g.add_edge("retry", "writer")
    for n in ("remove_unsafe", "emergency_reply", "med_change_reply", "records", "confirm_delete"):
        g.add_edge(n, END)
    return g.compile(checkpointer=checkpointer or MemorySaver())
