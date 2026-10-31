"""Korean output, citation contract, health_simple / health_deep split (no network)."""
import asyncio

from coach.agents.supervisor import health_path
from coach.citations import build
from coach.config import Settings
from coach.graph import build_graph
from coach.i18n import FIXED_KO, to_korean
from coach.llm import FakeLLM, Usage
from coach.runner import run_after
from coach.safety import rules
from tests.fakes import container, fake_llm, fake_servers
from coach.deps import Container


def run(c):
    return asyncio.run(c)


def test_korean_emergency_wording_is_caught_before_any_llm():
    deps, _ = container()
    for m in ("산책 후 가슴이 조이고 숨이 막혀요", "혈당이 45 나왔어요", "손이 떨리고 어지러워요"):
        r = run(run_after(build_graph(), deps, "u1", m))
        assert r["route"] == "emergency" and r["calls"] == 0
    assert not rules.is_emergency("혈당이 145예요") and not rules.is_emergency("저녁 먹고 걸어도 돼요?")


def test_every_fixed_reply_has_korean_text():
    for en in (rules.EMERGENCY_REPLY, rules.MED_CHANGE_REPLY, rules.HANDOFF_REPLY, rules.OTHER_USER_REPLY, rules.PRIVACY_INFO_REPLY):
        assert en in FIXED_KO
    assert "119" in FIXED_KO[rules.EMERGENCY_REPLY]


def test_translation_keeps_citations_or_falls_back_to_english():
    en = "Walking after dinner may lower glucose [PMC6546780]."
    ok = Container(settings=Settings(), llm=FakeLLM({"translate_ko": lambda m: {"answer": "저녁 식사 뒤 걷기는 혈당을 낮출 수 있습니다 [PMC6546780]."}}),
                   papers_server=fake_servers()[0], users_server=fake_servers()[1])
    assert run(to_korean(ok, Usage(), en))["translated"] is True
    bad = Container(settings=Settings(), llm=FakeLLM({"translate_ko": lambda m: {"answer": "걷기는 혈당을 낮춥니다."}}),
                    papers_server=fake_servers()[0], users_server=fake_servers()[1])
    r = run(to_korean(bad, Usage(), en))
    assert r["translated"] is False and r["answer"] == en     # a dropped marker -> keep the checked English text


def test_citation_contract_numbers_markers_and_marks_support_sentences():
    ev = {"exercise": {"notes": [{"note": "Hypoglycaemia can occur up to 12 h after exercise with insulin.", "source": "PMC1"}],
                       "picks": [{"query": "q", "best": [7]}],
                       "results": {"q": [{"pid": 7, "pmcid": "PMC1", "title": "T", "section": "S",
                                          "text": "Intro sentence. Hypoglycaemia during exercise, or for up to 12 h after exercise, is the main risk with insulin."}]}}}
    c = build("Check glucose first [PMC1]. Eat a snack. See also [PMC1] [PMC2].", ev)
    assert [x["citation_id"] for x in c["citations"]] == [1, 2]
    assert c["statements"][0]["citation_ids"] == [1] and c["statements"][1]["citation_ids"] == []
    first = c["citations"][0]
    assert first["location"] is None and first["support_sentences"] and "Intro" not in first["support_sentences"][0]
    assert c["citations"][1]["source_text"] is None          # cited but no chunk known: no invented excerpt


def test_health_path_rules_use_content_not_length():
    assert health_path("diet", False, "Is oatmeal good for breakfast?")[0] == "health_simple"
    assert health_path("diet", True, "Is oatmeal good for me?")[0] == "health_deep"
    assert health_path("exercise", False, "Exercise on insulin?")[0] == "health_deep"
    assert health_path("diet_exercise", False, "Walk and diet?")[0] == "health_deep"


def test_profile_rules_send_a_generally_worded_question_to_deep():
    insulin = "age: 77; conditions: type 2 diabetes; medications: insulin glargine, metformin; activity: walks"
    assert health_path("exercise", False, "Is interval training good?", insulin)[0] == "health_deep"
    assert health_path("exercise", False, "Is interval training good?", "")[0] == "health_simple"


def _lite(on=True, notes=True):
    llm = fake_llm(route="exercise")
    if not notes:
        llm.rules["exercise_picker"] = lambda m: {"best": [1], "notes": []}
    return Container(settings=Settings(health_lite=on), llm=llm, papers_server=fake_servers()[0], users_server=fake_servers()[1])


def _ask(deps, about_user):
    llm = deps.llm
    llm.rules["supervisor"] = lambda m: {"route": "exercise", "about_user": about_user}
    return run(run_after(build_graph(), deps, "u3", "What do guidelines say about walking?"))


def test_simple_path_uses_fewer_calls_than_deep():
    simple = _ask(_lite(True), False)
    deep = _ask(_lite(False), False)
    assert simple["calls"] < deep["calls"]
    assert "lite" not in " ".join(deep["trace"]) and "exercise.make_queries_lite" in simple["trace"]


def test_simple_escalates_to_deep_without_verified_notes():
    r = _ask(_lite(True, notes=False), False)
    assert "escalate" in " ".join(r["trace"]) and "exercise.make_queries" in r["trace"]


def test_insulin_user_asking_generally_still_goes_deep_end_to_end():
    r = run(run_after(build_graph(), _lite(True), "u1", "What do guidelines say about walking?"))
    assert r["trace"].count("exercise.make_queries") == 1 and "exercise.make_queries_lite" not in r["trace"]


def test_own_question_never_takes_the_simple_path():
    r = _ask(_lite(True), True)
    assert "exercise.make_queries" in r["trace"] and "exercise.make_queries_lite" not in r["trace"]
