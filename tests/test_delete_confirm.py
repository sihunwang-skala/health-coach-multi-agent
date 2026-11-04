"""Deleting a record: the user must confirm the exact record; an unclear request is never guessed; confirmations belong to one person,
work once and expire (fake LLM and fake MCP servers, no network)."""
import asyncio
import json
import types

import pytest
from fastapi.testclient import TestClient

from app import auth, server
from coach import tracelog
from coach.graph import build_graph
from coach.runner import run_after
from mcp_servers import user_server
from tests.fakes import container, fake_llm


def run(c):
    return asyncio.run(c)


def setup(pick):
    llm = fake_llm(route="delete_record")
    llm.rules["delete_pick"] = lambda m: {"ids": pick}
    deps, logs = container(llm)
    logs += [{"id": 1, "ts": "2026-10-20T08:00", "text": "walked 30 min"}, {"id": 2, "ts": "2026-10-20T12:00", "text": "white rice at lunch"},
             {"id": 3, "ts": "2026-10-21T18:00", "text": "walked 15 min after dinner"}]
    return deps, logs, build_graph()


def test_the_record_the_user_describes_is_the_one_shown_and_deleted():
    deps, logs, g = setup([2])
    r = run(run_after(g, deps, "u1", "Delete the rice entry from lunch"))
    assert r["interrupt"]["action"] == "delete_record" and r["interrupt"]["record"]["id"] == 2 and len(logs) == 3   # asked first, nothing deleted
    r2 = run(run_after(g, deps, "u1", "", thread_id=r["thread_id"], resume="yes"))
    assert [x["id"] for x in logs] == [1, 3] and "white rice" in r2["answer"]


def test_last_means_the_newest_record_without_asking_the_llm():
    deps, logs, g = setup([1])
    r = run(run_after(g, deps, "u1", "Delete my last record"))
    assert r["interrupt"]["record"]["id"] == 3 and "delete_pick" not in deps.llm.seen


@pytest.mark.parametrize("answer", ["no", "maybe", "approve", None, "", 0])
def test_anything_but_an_explicit_yes_deletes_nothing(answer):
    deps, logs, g = setup([2])
    r = run(run_after(g, deps, "u1", "Delete the rice entry"))
    run(run_after(g, deps, "u1", "", thread_id=r["thread_id"], resume=answer))
    assert len(logs) == 3


def test_several_matches_are_not_guessed_the_user_chooses_then_confirms():
    deps, logs, g = setup([1, 3])
    r = run(run_after(g, deps, "u1", "Delete the walk"))
    assert r["interrupt"]["action"] == "choose_record" and {o["id"] for o in r["interrupt"]["options"]} == {1, 3} and len(logs) == 3
    r2 = run(run_after(g, deps, "u1", "", thread_id=r["thread_id"], resume=1))
    assert r2["interrupt"]["action"] == "delete_record" and r2["interrupt"]["record"]["id"] == 1 and len(logs) == 3   # chosen, still not deleted
    run(run_after(g, deps, "u1", "", thread_id=r["thread_id"], resume="yes"))
    assert [x["id"] for x in logs] == [2, 3]


def test_an_unrelated_pick_is_ignored_and_no_match_shows_the_latest_records_to_choose_from():
    deps, logs, g = setup([99])          # an id that is not one of the user's records
    r = run(run_after(g, deps, "u1", "Delete the thing from last week"))
    assert r["interrupt"]["action"] == "choose_record" and {o["id"] for o in r["interrupt"]["options"]} == {1, 2, 3}
    r2 = run(run_after(g, deps, "u1", "", thread_id=r["thread_id"], resume=42))     # not one of the offered records
    assert len(logs) == 3 and "nothing was deleted" in r2["answer"]


# ---- the web layer: a confirmation belongs to one person, works once and expires
@pytest.fixture()
def web(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    monkeypatch.setattr(auth, "DB_PATH", db)
    monkeypatch.setattr(user_server, "DB", db)
    monkeypatch.setattr(tracelog, "Settings", lambda: types.SimpleNamespace(db_path=db))
    auth.FAILS.clear()
    server.PENDING.clear()
    deps, logs, g = setup([2])
    server.STATE.update(deps=deps, graph=g)
    auth.create_account("owner_t", "Testpass12", "user", "주인", "u1")
    auth.create_account("other_t", "Testpass12", "user", "다른 사람", "u2")
    mk = lambda name: (lambda c: (c.post("/api/auth/login", json={"username": name, "password": "Testpass12"}), c)[1])(TestClient(server.app))
    return mk("owner_t"), mk("other_t"), logs


def ask_to_delete(c):
    text = c.post("/chat/stream", json={"message": "Delete the rice entry", "lang": "en"}).text
    return [json.loads(x[6:]) for x in text.split("\n\n") if x.startswith("data: ")][-1]


def test_only_the_owner_can_answer_once_and_a_wrong_person_cannot_confirm(web):
    owner, other, logs = web
    done = ask_to_delete(owner)
    tid = done["thread_id"]
    assert done["interrupt"]["record"]["id"] == 2 and len(logs) == 3
    assert other.post("/approve", json={"thread_id": tid, "approve": True}).status_code == 410     # someone else's confirmation
    assert len(logs) == 3
    assert owner.post("/approve", json={"thread_id": tid, "approve": True}).status_code == 410     # the foreign attempt used it up
    tid = ask_to_delete(owner)["thread_id"]
    assert owner.post("/approve", json={"thread_id": tid, "approve": True}).status_code == 200 and [x["id"] for x in logs] == [1, 3]
    assert owner.post("/approve", json={"thread_id": tid, "approve": True}).status_code == 410     # one use only


def test_a_confirmation_expires_and_an_unknown_thread_is_refused(web):
    owner, _, logs = web
    tid = ask_to_delete(owner)["thread_id"]
    server.PENDING[tid]["expires"] -= server.PENDING_TTL + 1
    assert owner.post("/approve", json={"thread_id": tid, "approve": True}).status_code == 410 and len(logs) == 3
    assert owner.post("/approve", json={"thread_id": "no-such-thread", "approve": True}).status_code == 410


@pytest.mark.parametrize("msg,newest", [("Delete my last record", True), ("Remove the most recent entry", True), ("delete the one I just added", True),
                                        ("마지막 기록 지워 주세요", True), ("방금 적은 거 지워 주세요", True),
                                        ("Delete what I ate last night", False), ("Delete the walk from last week", False), ("지난주 기록 지워 주세요", False)])
def test_only_clear_last_wording_skips_the_llm_match(msg, newest):
    from coach.agents.records import LATEST
    assert bool(LATEST.search(msg)) is newest
