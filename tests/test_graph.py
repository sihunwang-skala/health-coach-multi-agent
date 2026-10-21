import asyncio

from coach.graph import build_graph
from coach.runner import run_after
from tests.fakes import container, fake_llm


def run(coro):
    return asyncio.run(coro)


def test_exercise_route_runs_evidence_and_safety_agents_in_parallel():
    deps, _ = container()
    r = run(run_after(build_graph(), deps, "u1", "Can I try interval training?"))
    assert r["route"] == "exercise"
    for node in ("supervisor", "make_queries", "retrieve_mcp", "pick_notes", "verify_notes", "safety_agent", "writer", "validate"):
        assert node in r["trace"]
    assert r["trace"].count("supervisor") == 1
    assert any(s["id"] == "R1" for s in r["safety_notes"])  # rule table fired for the insulin user
    assert r["notes"] and r["issues"] == []


def test_emergency_skips_the_llm():
    deps, _ = container()
    r = run(run_after(build_graph(), deps, "u1", "I'm sweating, shaky and confused after my walk"))
    assert r["route"] == "emergency" and r["calls"] == 0 and "119" in r["answer"]


def test_med_change_gets_fixed_reply():
    deps, _ = container(fake_llm(route="med_change"))
    r = run(run_after(build_graph(), deps, "u1", "Can I skip my insulin before tennis?"))
    assert "do not skip" in r["answer"].lower() and "make_queries" not in r["trace"]


def test_unsafe_answer_is_retried_once_then_removed():
    deps, _ = container(fake_llm(answer="Heavy lifting is great. Do it daily."))
    r = run(run_after(build_graph(), deps, "u2", "Can I lift weights?"))
    assert r["retries"] == 1                       # retry cap = 1
    assert "Heavy lifting is great." not in r["answer"] and r["removed"]
    assert r["answer"].startswith("With severe non-proliferative")   # rule table text goes first after a removal


def test_delete_needs_human_approval():
    deps, logs = container(fake_llm(route="log"))
    g = build_graph()
    run(run_after(g, deps, "u1", "I walked 30 minutes"))
    assert len(logs) == 1
    deps.llm = fake_llm(route="delete_record")
    r = run(run_after(g, deps, "u1", "Delete my last record"))
    assert r["interrupt"] and len(logs) == 1        # paused, nothing deleted yet
    r2 = run(run_after(g, deps, "u1", "", thread_id=r["thread_id"], resume="yes"))
    assert len(logs) == 0 and "Deleted" in r2["answer"]


def test_note_not_in_passages_is_dropped():
    llm = fake_llm()
    llm.rules["picker"] = lambda m: {"best": [1], "notes": [{"note": "Avoid flying across time zones with insulin pumps.", "source": "PMC6546780"}]}
    deps, _ = container(llm)
    r = run(run_after(build_graph(), deps, "u1", "Can I fly across time zones?"))
    assert not r["notes"] and r["dropped_notes"]
