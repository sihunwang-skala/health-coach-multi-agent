"""Fake MCP servers and a FakeLLM: the whole graph runs in tests without network, key or index (dependency injection)."""
from fastmcp import FastMCP

from coach.config import Settings
from coach.deps import Container
from coach.llm import FakeLLM

PROFILE = {"u1": "age: 77; gender: male; conditions: type 2 diabetes; medications: insulin glargine, metformin; activity: walks; mobility: good; goal: fitter",
           "u2": "age: 69; gender: male; conditions: type 2 diabetes, proliferative diabetic retinopathy; medications: metformin; activity: lifts; mobility: good; goal: sport"}
PASSAGE = {"pid": 1, "pmcid": "PMC6546780", "title": "Resources to Guide Exercise Specialists Managing Adults with Diabetes", "section": "T2D",
           "text": "Hypoglycaemia during exercise, or for up to 12 h after exercise, is the main risk for individuals with type 2 diabetes taking insulin and/or sulfonylurea medication."}


def fake_servers():
    papers, users, logs = FastMCP("p"), FastMCP("u"), []

    @papers.tool
    def search_papers(queries: list[str], k: int = 10, domain: str = "") -> dict:
        return {"results": {q: [PASSAGE] for q in queries}, "embed_tokens": 0}

    @users.tool
    def get_profile(user_id: str) -> dict:
        return {"profile": PROFILE.get(user_id, "")}

    @users.tool
    def log_record(user_id: str, text: str) -> dict:
        logs.append({"id": len(logs) + 1, "ts": "t", "text": text})
        return logs[-1]

    @users.tool
    def list_records(user_id: str, limit: int = 20) -> dict:
        return {"records": list(reversed(logs))[:limit]}

    @users.tool
    def delete_record(user_id: str, record_id: int) -> dict:
        n = len(logs)
        logs[:] = [x for x in logs if x["id"] != record_id]
        return {"deleted": n - len(logs)}

    return papers, users, logs


def fake_llm(route="exercise", answer="Check your glucose first; lows can happen up to 12 h after exercise [PMC6546780]."):
    rules = {"supervisor": lambda m: {"route": route},
             "writer": lambda m: {"answer": answer}, "writer_retry": lambda m: {"answer": answer},
             "records_reply": lambda m: {"answer": "Recorded."}}
    for d in ("exercise", "diet", "all"):
        rules.update({
            f"{d}_query_stage1": lambda m: {"subject": "exercise on insulin", "paper_term": "exercise", "conditions": ["insulin"]},
            f"{d}_query_stepback": lambda m: {"queries": ["guidelines for diabetes"]},
            f"{d}_query_conditions": lambda m: {"queries": ["hypoglycaemia with insulin"]},
            f"{d}_query_decompose": lambda m: {"queries": ["timing of hypoglycaemia"]},
            f"{d}_picker": lambda m: {"best": [1], "notes": [{"note": "Hypoglycaemia can occur for up to 12 h after exercise with insulin.", "source": "PMC6546780"}]},
        })
    return FakeLLM(rules)


def container(llm=None):
    papers, users, logs = fake_servers()
    return Container(settings=Settings(), llm=llm or fake_llm(), papers_server=papers, users_server=users), logs
