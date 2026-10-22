"""Supervisor graph (multi-agent):

  START -> guard (emergency check, code) ─┬─ emergency_reply -> END                     (no LLM, fixed 119 text)
                                          └─ supervisor (LLM router) ─┬─ diet / exercise / diet_exercise:
                                                                      │     [Diet Agent ‖ Exercise Agent (subgraphs, as needed) ‖ Safety Agent]
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

from coach.agents.evidence import evidence_node
from coach.agents.records import confirm_delete, records
from coach.agents.safety_agent import safety_agent
from coach.agents.supervisor import emergency_reply, fixed_reply, guard, med_change_reply, supervisor
from coach.agents.writer import after_validate, remove_unsafe, retry, validate, writer
from coach.state import CoachState


def build_graph(checkpointer=None):
    # [발표 코드 1-1 | LangGraph·Multi-Agent 전체 흐름]
    # 여러 Agent를 연결해 서비스 전체 처리 순서를 정합니다.
    # 질문이 들어온 뒤 답변이 나갈 때까지의 흐름입니다.
    g = StateGraph(CoachState)
    g.add_node("guard", guard)
    g.add_node("supervisor", supervisor)
    g.add_node("emergency_reply", emergency_reply)
    g.add_node("med_change_reply", med_change_reply)
    g.add_node("fixed_reply", fixed_reply)
    g.add_node("diet_agent", evidence_node("diet"))
    g.add_node("exercise_agent", evidence_node("exercise"))
    g.add_node("safety_agent", safety_agent)
    g.add_node("writer", writer)
    g.add_node("validate", validate)
    g.add_node("retry", retry)
    g.add_node("remove_unsafe", remove_unsafe)
    g.add_node("records", records)
    g.add_node("confirm_delete", confirm_delete)

    # [발표 코드 1-2 | LangGraph의 분기와 병렬 실행]
    # 먼저 응급 상황인지 확인하고, Supervisor가 질문 종류를 나눕니다.
    # 식단과 운동을 함께 물으면 필요한 Agent를 동시에 실행합니다.
    g.add_edge(START, "guard")
    g.add_conditional_edges("guard", lambda s: "emergency" if s["route"] == "emergency" else "route",
                            {"emergency": "emergency_reply", "route": "supervisor"})
    g.add_conditional_edges("supervisor", lambda s: {
        "exercise": ["exercise_agent", "safety_agent"], "diet": ["diet_agent", "safety_agent"],
        "diet_exercise": ["diet_agent", "exercise_agent", "safety_agent"],          # both research agents in parallel
        "med_change": ["med_change_reply"], "delete_record": ["confirm_delete"],
        "emergency": ["emergency_reply"],                                            # LLM backup for the code check
        "handoff": ["fixed_reply"], "other_user": ["fixed_reply"], "privacy_info": ["fixed_reply"],
    }.get(s["route"], ["records"]), ["diet_agent", "exercise_agent", "safety_agent", "med_change_reply", "confirm_delete", "records",
                                     "emergency_reply", "fixed_reply"])
    # [발표 코드 1-3 | LangGraph의 답변 검증과 승인 대기]
    # 각 Agent가 찾은 내용을 Writer가 하나의 답변으로 합칩니다.
    # 답변을 확인하고, 삭제 승인이 끝나면 MemorySaver가 중단한 작업을 이어갑니다.
    for n in ("diet_agent", "exercise_agent", "safety_agent"):   # same superstep -> the writer runs once, after all of them
        g.add_edge(n, "writer")
    g.add_edge("writer", "validate")
    g.add_conditional_edges("validate", after_validate, {"done": END, "retry": "retry", "remove": "remove_unsafe"})
    g.add_edge("retry", "writer")
    for n in ("remove_unsafe", "emergency_reply", "med_change_reply", "records", "confirm_delete", "fixed_reply"):
        g.add_edge(n, END)
    # MemorySaver는 graph의 현재 상태를 저장하는 checkpointer입니다.
    # 기록 삭제 요청에서 confirm_delete가 승인을 기다리며 멈추면,
    # 승인 후 같은 요청을 처음부터 다시 처리하지 않고 중단한 지점부터 재개할 수 있게 합니다.
    return g.compile(checkpointer=checkpointer or MemorySaver())


def build_single_agent_graph(checkpointer=None):
    """Comparison system (not the service): ONE agentic RAG agent for every message - no supervisor, no diet / exercise
    split, no records / service routes. Same emergency code check, rule table, writer and dangerous-advice check, so the
    difference to build_graph() is exactly what the multi-agent design adds."""
    g = StateGraph(CoachState)
    g.add_node("guard", guard)
    g.add_node("emergency_reply", emergency_reply)
    g.add_node("single_route", _single_route)
    g.add_node("all_agent", evidence_node("all"))
    g.add_node("safety_agent", safety_agent)
    g.add_node("writer", writer)
    g.add_node("validate", validate)
    g.add_node("retry", retry)
    g.add_node("remove_unsafe", remove_unsafe)
    g.add_edge(START, "guard")
    g.add_conditional_edges("guard", lambda s: "emergency" if s["route"] == "emergency" else "route",
                            {"emergency": "emergency_reply", "route": "single_route"})
    g.add_edge("single_route", "all_agent")
    g.add_edge("single_route", "safety_agent")
    g.add_edge("all_agent", "writer")
    g.add_edge("safety_agent", "writer")
    g.add_edge("writer", "validate")
    g.add_conditional_edges("validate", after_validate, {"done": END, "retry": "retry", "remove": "remove_unsafe"})
    g.add_edge("retry", "writer")
    g.add_edge("remove_unsafe", END)
    g.add_edge("emergency_reply", END)
    return g.compile(checkpointer=checkpointer or MemorySaver())


async def _single_route(state, config):
    return {"route": "single", "trace": ["single_route"]}
