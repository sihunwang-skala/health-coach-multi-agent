"""FastAPI service.
Screens: GET / (user screen: my information + chat), GET /admin (care-team screen: monitoring, alerts, one person).
Chat: POST /chat (one answer), GET /chat/stream (SSE: each agent step as it finishes), POST /approve (human-in-the-loop
decision for a pending record deletion). Every handled message is written to our own monitoring log (coach/tracelog.py).
Data: GET /api/me/{user_id}, GET /api/admin/summary, GET /api/admin/users, GET /api/admin/users/{user_id},
GET /api/admin/alerts, POST /api/admin/alerts/{event_id}. GET /health.
    .venv/bin/uvicorn app.server:app --port 8000
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from coach.deps import Container, default_container  # noqa: E402
from coach.graph import build_graph  # noqa: E402
from coach.llm import Usage  # noqa: E402
from coach.runner import run_after  # noqa: E402
from coach import tracelog  # noqa: E402
from mcp_servers.user_server import full_profiles  # noqa: E402

MED_CLASS = {  # shown next to each medicine on both screens (display only; the LLM sees the plain profile)
    "metformin": "oral diabetes medicine", "glimepiride": "oral diabetes medicine, can cause low blood sugar",
    "gliclazide": "oral diabetes medicine, can cause low blood sugar", "insulin glargine": "long-acting insulin",
    "insulin aspart": "mealtime insulin", "premixed insulin": "premixed insulin", "amlodipine": "blood pressure medicine",
    "lisinopril": "blood pressure medicine"}

STATE: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    STATE["deps"] = default_container()   # built once: settings, LLM, MCP servers (dependency injection)
    STATE["graph"] = build_graph()
    import asyncio

    from mcp_servers.papers_server import index
    await asyncio.to_thread(index)        # load the paper index at startup, not on the first question
    tracelog.purge()                      # retention: drop monitoring rows older than COACH_LOG_DAYS
    yield


app = FastAPI(title="Diet & exercise coach multi-agent", lifespan=lifespan)


def get_deps() -> Container:
    return STATE["deps"]


class ChatIn(BaseModel):
    user_id: str = "u01"
    message: str


class ApproveIn(BaseModel):
    user_id: str
    thread_id: str
    approve: bool


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/")
def web():
    return FileResponse(ROOT / "web" / "index.html")


@app.get("/admin")
def admin_web():
    return FileResponse(ROOT / "web" / "admin.html")


def _profiles() -> dict:
    return {p["id"]: {**p, "medications": [{"name": m, "kind": MED_CLASS.get(m, "")} for m in p["medications"]]}
            for p in full_profiles()}


def staff_only(x_admin_token: str | None = Header(default=None)):
    """Demo guard for the care-team API: when COACH_ADMIN_TOKEN is set, the request must carry it."""
    import os
    want = os.environ.get("COACH_ADMIN_TOKEN")
    if want and x_admin_token != want:
        raise HTTPException(401, "care-team token required")


@app.get("/api/users")
def user_list():
    """For the demo sign-in menu: id and first name only."""
    return [{"id": i, "name": p["name"].split()[0]} for i, p in _profiles().items()]


@app.get("/api/me/{user_id}")
async def me(user_id: str, deps: Container = Depends(get_deps)):
    """User screen: my own profile and my records (a real service would take the id from the login session)."""
    recs = await deps.users("list_records", user_id=user_id, limit=20)
    chats = tracelog.rows("SELECT ts, route, message, answer FROM events WHERE user_id = ? ORDER BY ts DESC LIMIT 10", (user_id,))
    return {"profile": _profiles().get(user_id), "records": recs["records"], "chats": chats}


@app.get("/api/admin/summary", dependencies=[Depends(staff_only)])
def admin_summary(days: int = 14):
    return tracelog.summary(days)


@app.get("/api/admin/users", dependencies=[Depends(staff_only)])
def admin_users():
    stats = {r["user_id"]: r for r in tracelog.rows(
        "SELECT user_id, COUNT(*) AS messages, MAX(ts) AS last_ts, SUM(cost) AS cost, "
        "SUM(CASE WHEN alert IS NOT NULL THEN 1 ELSE 0 END) AS alerts, "
        "SUM(CASE WHEN alert_status = 'open' THEN 1 ELSE 0 END) AS open_alerts FROM events GROUP BY user_id")}
    return [{**p, **{k: v for k, v in stats.get(i, {}).items() if k != "user_id"}} for i, p in _profiles().items()]


@app.get("/api/admin/users/{user_id}", dependencies=[Depends(staff_only)])
async def admin_user(user_id: str, deps: Container = Depends(get_deps)):
    recs = await deps.users("list_records", user_id=user_id, limit=50)
    ev = tracelog.rows("SELECT * FROM events WHERE user_id = ? ORDER BY ts DESC LIMIT 100", (user_id,))
    return {"profile": _profiles().get(user_id), "records": recs["records"], "events": ev}


@app.get("/api/admin/alerts", dependencies=[Depends(staff_only)])
def admin_alerts(status: str = "all"):
    q = "SELECT id, ts, user_id, alert, alert_status, message, answer FROM events WHERE alert IS NOT NULL"
    q += "" if status == "all" else " AND alert_status = ?"
    return tracelog.rows(q + " ORDER BY (alert_status = 'open') DESC, ts DESC LIMIT 200", () if status == "all" else (status,))


class AlertIn(BaseModel):
    status: str = "handled"


@app.post("/api/admin/alerts/{event_id}", dependencies=[Depends(staff_only)])
def admin_alert_status(event_id: int, body: AlertIn):
    return {"updated": tracelog.set_alert_status(event_id, body.status)}


@app.get("/replay/{item_id}")
def replay(item_id: str, system: str = "after"):
    """A recorded evaluation run (eval/results), shown in the web page without calling the LLM again."""
    rows = json.loads((ROOT / "eval" / "results" / f"{system}.json").read_text())
    return rows.get(item_id, {})


@app.post("/chat")
async def chat(body: ChatIn, deps: Container = Depends(get_deps)):
    r = await run_after(STATE["graph"], deps, body.user_id, body.message)
    tracelog.log_event(body.user_id, body.message, r)
    return r


@app.post("/approve")
async def approve(body: ApproveIn, deps: Container = Depends(get_deps)):
    r = await run_after(STATE["graph"], deps, body.user_id, "", thread_id=body.thread_id,
                        resume="yes" if body.approve else "no")
    tracelog.log_event(body.user_id, "(approval) " + ("yes" if body.approve else "no"), r)
    return r


@app.get("/chat/stream")
async def chat_stream(user_id: str, message: str, deps: Container = Depends(get_deps)):
    async def events():
        u, tid, t = Usage(), str(uuid.uuid4()), time.time()
        cfg = {"configurable": {"deps": deps, "usage": u, "thread_id": tid}, "recursion_limit": 30}
        final = {}
        async for upd in STATE["graph"].astream({"user_id": user_id, "message": message, "trace": [], "timings": {}}, cfg,
                                                stream_mode="updates", subgraphs=True):
            ns, data = upd
            prefix = (ns[0].split(":")[0].replace("_agent", "") + ".") if ns else ""   # diet. / exercise. inside the subgraphs
            for node, out in (data or {}).items():
                if node == "__interrupt__":
                    final["interrupt"] = out[0].value if out else None
                    continue
                out = out or {}
                final.update({k: v for k, v in out.items() if k in ("answer", "answer_ko", "summary_ko", "route", "safety_notes", "retries", "removed")})
                for dom, ev in (out.get("evidence") or {}).items():
                    final.setdefault("notes", []).extend((ev or {}).get("notes") or [])
                    final.setdefault("domains", []).append(dom)
                yield f"data: {json.dumps({'step': prefix + node, 'seconds': (out.get('timings') or {}).get(node), 'route': out.get('route')})}\n\n"
        s = deps.settings
        tracelog.log_event(user_id, message, {**final, "latency_s": round(time.time() - t, 2), "calls": u.calls,
                                              "tokens_in": u.tokens_in, "tokens_out": u.tokens_out,
                                              "cost": round(u.cost(s.price_in, s.price_out, s.price_embed), 5)})
        yield "data: " + json.dumps({"done": True, "answer": final.get("answer", ""), "answer_ko": final.get("answer_ko", ""),
                                     "summary_ko": final.get("summary_ko", ""), "route": final.get("route"),
                                     "interrupt": final.get("interrupt"), "thread_id": tid,
                                     "sources": sorted({n.get("source") for n in final.get("notes", []) if n.get("source")}),
                                     "safety_notes": final.get("safety_notes", []), "latency_s": round(time.time() - t, 2),
                                     "calls": u.calls, "cost": round(u.cost(s.price_in, s.price_out, s.price_embed), 5)}) + "\n\n"
    return StreamingResponse(events(), media_type="text/event-stream")
