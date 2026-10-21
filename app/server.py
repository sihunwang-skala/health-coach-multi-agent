"""FastAPI service: POST /chat (one answer), GET /chat/stream (SSE: each agent step as it finishes), POST /approve
(human-in-the-loop decision for a pending record deletion), GET / (web chat), GET /health.
    .venv/bin/uvicorn app.server:app --port 8000
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from coach.deps import Container, default_container  # noqa: E402
from coach.graph import build_graph  # noqa: E402
from coach.llm import Usage  # noqa: E402
from coach.runner import run_after  # noqa: E402

STATE: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    STATE["deps"] = default_container()   # built once: settings, LLM, MCP servers (dependency injection)
    STATE["graph"] = build_graph()
    yield


app = FastAPI(title="Exercise coach multi-agent", lifespan=lifespan)


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


@app.get("/replay/{item_id}")
def replay(item_id: str, system: str = "after"):
    """A recorded evaluation run (eval/results), shown in the web page without calling the LLM again."""
    rows = json.loads((ROOT / "eval" / "results" / f"{system}.json").read_text())
    return rows.get(item_id, {})


@app.post("/chat")
async def chat(body: ChatIn, deps: Container = Depends(get_deps)):
    return await run_after(STATE["graph"], deps, body.user_id, body.message)


@app.post("/approve")
async def approve(body: ApproveIn, deps: Container = Depends(get_deps)):
    return await run_after(STATE["graph"], deps, body.user_id, "", thread_id=body.thread_id,
                           resume="yes" if body.approve else "no")


@app.get("/chat/stream")
async def chat_stream(user_id: str, message: str, deps: Container = Depends(get_deps)):
    async def events():
        u, tid, t = Usage(), str(uuid.uuid4()), time.time()
        cfg = {"configurable": {"deps": deps, "usage": u, "thread_id": tid}, "recursion_limit": 30}
        final = {}
        async for upd in STATE["graph"].astream({"user_id": user_id, "message": message, "trace": [], "timings": {}}, cfg,
                                                stream_mode="updates", subgraphs=True):
            ns, data = upd
            for node, out in (data or {}).items():
                if node == "__interrupt__":
                    final["interrupt"] = out[0].value if out else None
                    continue
                out = out or {}
                final.update({k: v for k, v in out.items() if k in ("answer", "route", "notes", "safety_notes", "retries")})
                yield f"data: {json.dumps({'step': node, 'seconds': (out.get('timings') or {}).get(node), 'route': out.get('route')})}\n\n"
        s = deps.settings
        yield "data: " + json.dumps({"done": True, "answer": final.get("answer", ""), "route": final.get("route"),
                                     "interrupt": final.get("interrupt"), "thread_id": tid,
                                     "sources": sorted({n.get("source") for n in final.get("notes", []) if n.get("source")}),
                                     "safety_notes": final.get("safety_notes", []), "latency_s": round(time.time() - t, 2),
                                     "calls": u.calls, "cost": round(u.cost(s.price_in, s.price_out, s.price_embed), 5)}) + "\n\n"
    return StreamingResponse(events(), media_type="text/event-stream")
