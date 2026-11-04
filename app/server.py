"""FastAPI service.
Two roles, two sign-ins (app/auth.py): users sign in at /login, care-team staff at /admin/login. Nobody can pick a user id any more:
every user API takes the person from the session cookie.
Screens: GET / (chat), GET /login, GET /admin (care-team console), GET /admin/login.
Auth: POST /api/auth/signup|login|logout, GET /api/auth/me, POST /api/me/password|delete; POST /api/staff/login|logout, GET /api/staff/me.
Chat: POST /chat/stream (SSE: each agent step as it finishes; a POST so the pipeline cannot be started by a link), POST /chat,
POST /approve (human-in-the-loop decision for a pending record deletion). Every handled message is written to our own
monitoring log (coach/tracelog.py).
Care team: GET /api/admin/summary|users|users/{id}|alerts|audit, POST /api/admin/alerts/{event_id}. GET /health.
    .venv/bin/uvicorn app.server:app --port 8000
"""
from __future__ import annotations

import json
import os
import re
import secrets
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from coach.deps import Container, default_container  # noqa: E402
from coach.graph import build_graph  # noqa: E402
from coach.llm import Usage  # noqa: E402
from coach.runner import run_after  # noqa: E402
from coach import tracelog  # noqa: E402
from coach.citations import build as build_citations  # noqa: E402
from coach.i18n import fixed_ko, to_korean  # noqa: E402
from app import auth  # noqa: E402
from mcp_servers.user_server import create_user, delete_user, full_profiles, get_full_profile  # noqa: E402

MED_KO = {  # (Korean name, what it is) shown next to each medicine on both screens (display only; the LLM sees the plain English profile)
    "metformin": ("메트포르민", "먹는 당뇨약"), "glimepiride": ("글리메피리드", "먹는 당뇨약 · 저혈당 주의"),
    "gliclazide": ("글리클라지드", "먹는 당뇨약 · 저혈당 주의"), "insulin glargine": ("글라진 인슐린", "지속형 인슐린"),
    "insulin aspart": ("아스파트 인슐린", "식사 인슐린"), "premixed insulin": ("혼합형 인슐린", "인슐린"),
    "amlodipine": ("암로디핀", "혈압약"), "lisinopril": ("리시노프릴", "혈압약")}
MED_EN = {"metformin": "oral diabetes medicine", "glimepiride": "oral diabetes medicine, can cause low blood sugar",
          "gliclazide": "oral diabetes medicine, can cause low blood sugar", "insulin glargine": "long-acting insulin",
          "insulin aspart": "mealtime insulin", "premixed insulin": "premixed insulin", "amlodipine": "blood pressure medicine",
          "lisinopril": "blood pressure medicine"}
COND_KO = [("type 2 diabetes", "제2형 당뇨병"), ("hypertension", "고혈압"), ("kidney", "만성 신장병"), ("retinopathy", "당뇨병성 망막병증"),
           ("neuropathy", "말초신경병증(발 저림)"), ("heart", "심장 질환"), ("low muscle", "근육량 부족")]
SEED_KO = {  # display only (the English profile text is what the agents read): the 10 synthetic people, free-text fields in Korean
    "u01": ("저녁 식사 후 대부분 앉아 있고 잘 걷지 않아요", "양호", "식후 혈당 낮추기", "하루 콜라 한 캔, 흰쌀밥을 좋아해요"),
    "u02": ("공원 걷기를 좋아해요", "양호, 발 저림", "안전하게 활동 유지", "락토오보 채식, 밤 11시쯤 야식"),
    "u03": ("천천히 걷고 쉽게 지쳐요", "쇠약, 느린 걸음", "근력 유지", "매일 아침 오렌지 주스 한 잔"),
    "u04": ("주 3회 헬스장에서 무거운 웨이트", "양호", "근육 키우기", "하루 맥주 2~3잔, 대부분 외식"),
    "u05": ("넘어질까 봐 잘 걷지 않아요", "균형이 불안", "넘어지지 않기", "보통 아침을 거르고 식사 시간이 들쭉날쭉"),
    "u06": ("점심 전 짧은 산책", "다리 힘이 약함", "근육 되찾기", "식욕이 없고 최근 6개월간 의도치 않게 5kg 감소"),
    "u07": ("저녁에 40분 걷기", "양호", "혈압 낮추기", "짠 절임 반찬, 저녁은 밤 9~10시쯤"),
    "u08": ("빠르게 걷기, 인터벌 운동을 해 보고 싶어요", "양호", "체력 키우기", "저녁에 와인 1~2잔, 아침은 자주 거름"),
    "u09": ("대부분 앉아 지내고 지팡이를 써요", "지팡이 사용", "넘어지지 않고 더 움직이기", "불규칙한 시간에 소량, 부드러운 음식"),
    "u10": ("주 2회 테니스, 웨이트 운동", "양호", "운동 계속하기", "빵과 면을 많이 먹고 주말에 맥주 여러 잔")}
NOT_GIVEN = "입력 안 함"
RECORD_KO = {  # display only: the demo records are English text; a person's own records are shown exactly as typed
    "1 can of soda": "탄산음료 1캔", "2 beers with dinner": "저녁에 맥주 2잔", "I had oatmeal with berries for breakfast.": "아침으로 오트밀과 베리를 먹었어요.",
    "I walked 15 minutes with my cane this morning.": "오늘 아침 지팡이를 짚고 15분 걸었어요.", "I walked 30 minutes after dinner today.": "오늘 저녁 식사 후 30분 걸었어요.",
    "My glucose was 132 before my walk.": "걷기 전 혈당이 132였어요.", "a glass of wine with dinner": "저녁에 와인 한 잔", "ate half of lunch, low appetite": "점심을 절반만 먹었어요, 식욕이 없어요",
    "ate out: noodle soup": "외식: 국수", "beers on Saturday": "토요일에 맥주", "brisk walk 30 min": "빠르게 걷기 30분", "chair exercises 10 min": "의자 운동 10분",
    "dinner at 9:30 pm, kimchi and pickles": "저녁 9시 30분, 김치와 절임 반찬", "gym: weights 45 min": "헬스장: 웨이트 45분", "noodles for lunch": "점심은 국수",
    "orange juice at breakfast": "아침에 오렌지 주스", "sat-to-stand practice 5 times": "앉았다 일어서기 연습 5회", "short walk before lunch": "점심 전 짧은 산책", "skipped breakfast": "아침을 걸렀어요",
    "slow walk 10 min": "천천히 걷기 10분", "snack at 11 pm: yogurt": "밤 11시 간식: 요거트", "soft rice porridge at 3 pm": "오후 3시 부드러운 죽", "tennis 1 hour": "테니스 1시간",
    "walked 15 min after dinner": "저녁 식사 후 15분 걸었어요", "walked 30 min in the park, checked feet: ok": "공원에서 30분 걸었어요, 발 상태 확인: 이상 없음",
    "walked 40 min in the evening": "저녁에 40분 걸었어요", "white rice at lunch, half bowl": "점심에 흰쌀밥 반 공기"}


def _records(recs: list[dict]) -> list[dict]:
    out = []
    for r in recs:
        t = r["text"].replace("[demo] ", "")
        ko = RECORD_KO.get(t) or (re.sub(r"^blood sugar (\d+) mg/dL$", r"혈당 \1 mg/dL", t) if t.startswith("blood sugar ") else None)
        out.append({**r, "text_ko": ko})
    return out
# sign-up choices: key sent by the page -> English token the safety rules and agents read
SIGNUP_COND = {"hypertension": "hypertension", "kidney": "chronic kidney disease", "retinopathy": "diabetic retinopathy",
               "neuropathy": "peripheral neuropathy (numb feet)", "heart": "heart disease", "muscle": "low muscle mass"}
SIGNUP_MED = {"metformin": "metformin", "glimepiride": "glimepiride", "gliclazide": "gliclazide", "glargine": "insulin glargine",
              "aspart": "insulin aspart", "premixed": "premixed insulin", "amlodipine": "amlodipine", "lisinopril": "lisinopril"}
SIGNUP_MOB = {"good": "good", "balance": "poor balance", "cane": "uses a cane", "legs": "weak legs"}

# Demo mode (default ON for this synthetic-data PoC): the 10 synthetic users and a demo care-team account can be entered with one
# click, no password. Set COACH_DEMO=0 for anything with real people's data (docs/ACCOUNTS.md).
DEMO = os.environ.get("COACH_DEMO", "1") == "1"
SYNTHETIC = {u["id"] for u in json.loads((ROOT / "data" / "users.json").read_text())}

STATE: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    if DEMO:
        print("WARNING: COACH_DEMO=1 - one-click demo sign-in is ON. Set COACH_DEMO=0 when real people's data is stored.")
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
    message: str = Field(min_length=1, max_length=1000)
    lang: str = "ko"


class ApproveIn(BaseModel):
    thread_id: str
    approve: bool
    lang: str = "ko"


class LoginIn(BaseModel):
    username: str = Field(max_length=40)
    password: str = Field(max_length=200)


class SignupIn(LoginIn):
    name: str = Field(min_length=1, max_length=20)
    age: int = Field(ge=18, le=110)
    gender: str
    conditions: list[str] = []
    medications: list[str] = []
    other_medications: str = Field("", max_length=60)
    mobility: str = "good"
    activity: str = Field("", max_length=100)
    diet: str = Field("", max_length=100)
    goal: str = Field("", max_length=100)
    consent: bool = False


class PasswordIn(BaseModel):
    current: str = Field(max_length=200)
    new: str = Field(max_length=200)


class DeleteIn(BaseModel):
    password: str = Field(max_length=200)


@app.get("/health")
def health():
    return {"ok": True}


NO_STORE = {"Cache-Control": "no-store"}


def _page(name: str) -> FileResponse:
    return FileResponse(ROOT / "web" / name, headers=NO_STORE)


@app.get("/")
def web(request: Request):
    return _page("index.html") if auth.session_account(request, "user") else RedirectResponse("/login", 303)


@app.get("/login")
def login_page(request: Request):
    return RedirectResponse("/", 303) if auth.session_account(request, "user") else _page("login.html")


@app.get("/admin")
def admin_web(request: Request):
    return _page("admin.html") if auth.session_account(request, "staff") else RedirectResponse("/admin/login", 303)


@app.get("/admin/login")
def admin_login_page(request: Request):
    return RedirectResponse("/admin", 303) if auth.session_account(request, "staff") else _page("admin-login.html")


PWA_FILES = {"manifest.webmanifest": "application/manifest+json", "sw.js": "text/javascript", "icon.svg": "image/svg+xml",
             "icon-192.png": "image/png", "icon-512.png": "image/png", "ds.css": "text/css", "ds.js": "text/javascript", "i18n.js": "text/javascript"}


@app.get("/{name}", include_in_schema=False)
def pwa_file(name: str):
    """Static shell files (design-system CSS/JS, manifest, service worker, icons). Only this fixed list is served."""
    if name not in PWA_FILES:
        raise HTTPException(404)
    return FileResponse(ROOT / "web" / name, media_type=PWA_FILES[name], headers={"Cache-Control": "no-cache"})


def _show(p: dict | None) -> dict | None:
    """A stored profile as the screens show it: Korean labels for conditions and medicines."""
    if not p:
        return None
    cond = [next((ko for key, ko in COND_KO if key in c.lower()), c) for c in p["conditions"]]
    meds = [{"name": MED_KO.get(m, (m, ""))[0], "kind": MED_KO.get(m, (m, ""))[1], "name_en": m, "kind_en": MED_EN.get(m, "")} for m in p["medications"]]
    ko = dict(zip(("activity", "mobility", "goal", "diet"), SEED_KO.get(p.get("id"), ())))
    for k in ("activity", "mobility", "goal", "diet"):   # real sign-ups: free text is already what the person typed
        ko.setdefault(k, NOT_GIVEN if p.get(k) == "not given" else {"good": "양호", "poor balance": "균형이 불안", "uses a cane": "지팡이 사용", "weak legs": "다리 힘이 약함"}.get(p.get(k), p.get(k)))
    return {**p, "ko": ko, "conditions_ko": cond, "conditions_en": p["conditions"], "medications": meds, "gender_ko": {"female": "여성", "male": "남성"}.get(p["gender"], p["gender"])}


def _profiles() -> dict:
    return {p["id"]: _show(p) for p in full_profiles()}


def _history(user_id: str, limit: int = 40) -> list[dict]:
    rows = tracelog.rows("SELECT ts, route, message, answer, meta FROM events WHERE user_id = ? ORDER BY ts DESC, id DESC LIMIT ?", (user_id, limit))
    for r in rows:
        r["meta"] = json.loads(r["meta"]) if r.get("meta") else None
    return rows[::-1]


def _same_origin(request: Request):
    auth.same_origin(request)


@app.post("/api/auth/signup", dependencies=[Depends(_same_origin)])
def signup(body: SignupIn, request: Request, response: Response):
    import re
    name = body.username.strip().lower()
    if not re.fullmatch(r"[a-z0-9_]{4,20}", name):
        raise HTTPException(422, "아이디는 영문 소문자, 숫자, 밑줄(_)로 4~20자예요.")
    if (msg := auth.check_password_rules(body.password)):
        raise HTTPException(422, msg)
    if not body.consent:
        raise HTTPException(422, "개인정보와 건강정보 이용에 동의해 주세요.")
    if body.gender not in ("female", "male"):
        raise HTTPException(422, "성별을 선택해 주세요.")
    clean = lambda t: re.sub(r"[;\n\r]+", ", ", t).strip()   # the profile is sent as "field: value; field: value"
    meds = [SIGNUP_MED[m] for m in body.medications if m in SIGNUP_MED] + ([clean(body.other_medications)] if body.other_medications.strip() else [])
    uid = "w" + secrets.token_hex(4)
    profile = {"name": body.name.strip(), "age": body.age, "gender": body.gender,
               "conditions": ["type 2 diabetes"] + [SIGNUP_COND[c] for c in body.conditions if c in SIGNUP_COND],
               "medications": meds or ["none"], "activity": clean(body.activity) or "not given", "mobility": SIGNUP_MOB.get(body.mobility, "good"),
               "goal": clean(body.goal) or "not given", "diet": clean(body.diet) or "not given"}
    aid = auth.create_account(name, body.password, "user", profile["name"], uid)   # fails with 409 before any profile exists
    create_user(uid, profile)
    auth.start_session(request, response, aid, "user")
    return {"ok": True}


@app.post("/api/auth/login", dependencies=[Depends(_same_origin)])
def user_login(body: LoginIn, request: Request, response: Response):
    a = auth.login(request, response, body.username, body.password, "user")
    return {"ok": True, "name": a["display_name"]}


@app.post("/api/auth/logout", dependencies=[Depends(_same_origin)])
def user_logout(request: Request, response: Response):
    auth.end_session(request, response, "user")
    return {"ok": True}


@app.get("/api/auth/me")
async def me(user: dict = Depends(auth.current_user), deps: Container = Depends(get_deps)):
    """The signed-in person's own profile, records and chat history (the id comes from the session, never from the page)."""
    uid = user["user_id"]
    recs = await deps.users("list_records", user_id=uid, limit=20)
    return {"account": {"username": user["username"], "name": user["display_name"]}, "profile": _show(get_full_profile(uid)),
            "records": _records(recs["records"]), "history": _history(uid)}


@app.post("/api/me/password", dependencies=[Depends(_same_origin)])
def change_password(body: PasswordIn, request: Request, response: Response, user: dict = Depends(auth.current_user)):
    if not auth.verify_password(body.current, user["pw_hash"]):
        raise HTTPException(403, "현재 비밀번호가 맞지 않아요.")
    if (msg := auth.check_password_rules(body.new)):
        raise HTTPException(422, msg)
    auth.set_password(user["id"], body.new)
    auth.start_session(request, response, user["id"], "user")   # keep this device signed in
    return {"ok": True}


@app.post("/api/me/delete", dependencies=[Depends(_same_origin)])
def delete_me(body: DeleteIn, request: Request, response: Response, user: dict = Depends(auth.current_user)):
    """Account deletion: the account, the profile, the records and the monitoring-log rows of this person are removed."""
    if not auth.verify_password(body.password, user["pw_hash"]):
        raise HTTPException(403, "비밀번호가 맞지 않아요.")
    delete_user(user["user_id"])
    auth.delete_account(user["id"])
    response.delete_cookie(auth.USER_COOKIE, path="/")
    return {"ok": True}


def _demo_only():
    if not DEMO:
        raise HTTPException(404)


class DemoIn(BaseModel):
    user_id: str


@app.get("/api/demo/users", dependencies=[Depends(_demo_only)])
def demo_users():
    """Login page, demo mode: the synthetic people (first name, age, one line) - never real sign-ups."""
    return [{"id": i, "name": p["name"].split()[0], "age": p["age"], "line": ", ".join(c for c in p["conditions_ko"] if c != "제2형 당뇨병") or "제2형 당뇨병",
             "line_en": ", ".join(c.capitalize() for c in p["conditions_en"] if c != "type 2 diabetes") or "Type 2 diabetes"}
            for i, p in _profiles().items() if i in SYNTHETIC]


@app.post("/api/demo/enter", dependencies=[Depends(_demo_only), Depends(_same_origin)])
def demo_enter(body: DemoIn, request: Request, response: Response):
    if body.user_id not in SYNTHETIC:
        raise HTTPException(404)
    row = auth.run("SELECT id FROM accounts WHERE user_id = ? AND role = 'user'", (body.user_id,), one=True)
    aid = row["id"] if row else auth.create_account(f"demo_{body.user_id}", secrets.token_urlsafe(24) + "a1", "user",
                                                    (get_full_profile(body.user_id) or {}).get("name", body.user_id), body.user_id)
    auth.start_session(request, response, aid, "user")
    return {"ok": True}


@app.post("/api/demo/staff", dependencies=[Depends(_demo_only), Depends(_same_origin)])
def demo_staff(request: Request, response: Response):
    row = auth.run("SELECT id FROM accounts WHERE username = 'demo_staff'", one=True)
    aid = row["id"] if row else auth.create_account("demo_staff", secrets.token_urlsafe(24) + "a1", "staff", "데모 의료진")
    auth.start_session(request, response, aid, "staff")
    auth.audit("demo_staff", "sign in (demo)")
    return {"ok": True}


@app.get("/api/config")
def config():
    return {"demo": DEMO}


@app.post("/api/staff/login", dependencies=[Depends(_same_origin)])
def staff_login(body: LoginIn, request: Request, response: Response):
    a = auth.login(request, response, body.username, body.password, "staff")
    auth.audit(a["username"], "sign in")
    return {"ok": True, "name": a["display_name"]}


@app.post("/api/staff/logout", dependencies=[Depends(_same_origin)])
def staff_logout(request: Request, response: Response):
    auth.end_session(request, response, "staff")
    return {"ok": True}


@app.get("/api/staff/me")
def staff_me(staff: dict = Depends(auth.current_staff)):
    return {"username": staff["username"], "name": staff["display_name"]}


@app.get("/api/admin/summary", dependencies=[Depends(auth.current_staff)])
def admin_summary(days: int = 14):
    return tracelog.summary(days)


@app.get("/api/admin/users", dependencies=[Depends(auth.current_staff)])
def admin_users():
    stats = {r["user_id"]: r for r in tracelog.rows(
        "SELECT user_id, COUNT(*) AS messages, MAX(ts) AS last_ts, SUM(cost) AS cost, "
        "SUM(CASE WHEN alert IS NOT NULL THEN 1 ELSE 0 END) AS alerts, "
        "SUM(CASE WHEN alert_status = 'open' THEN 1 ELSE 0 END) AS open_alerts FROM events GROUP BY user_id")}
    return [{**p, **{k: v for k, v in stats.get(i, {}).items() if k != "user_id"}} for i, p in _profiles().items()]


@app.get("/api/admin/users/{user_id}", dependencies=[Depends(auth.current_staff)])
async def admin_user(user_id: str, deps: Container = Depends(get_deps), staff: dict = Depends(auth.current_staff)):
    auth.audit(staff["username"], "opened a person's data", user_id)   # every look at personal health data is logged
    recs = await deps.users("list_records", user_id=user_id, limit=50)
    ev = tracelog.rows("SELECT * FROM events WHERE user_id = ? ORDER BY ts DESC LIMIT 100", (user_id,))
    return {"profile": _profiles().get(user_id), "records": _records(recs["records"]), "events": ev}


@app.get("/api/admin/alerts", dependencies=[Depends(auth.current_staff)])
def admin_alerts(status: str = "all"):
    q = "SELECT id, ts, user_id, alert, alert_status, message, answer FROM events WHERE alert IS NOT NULL"
    q += "" if status == "all" else " AND alert_status = ?"
    return tracelog.rows(q + " ORDER BY (alert_status = 'open') DESC, ts DESC LIMIT 200", () if status == "all" else (status,))


class AlertIn(BaseModel):
    status: str = "handled"


@app.post("/api/admin/alerts/{event_id}", dependencies=[Depends(_same_origin)])
def admin_alert_status(event_id: int, body: AlertIn, staff: dict = Depends(auth.current_staff)):
    auth.audit(staff["username"], f"alert marked {body.status}", str(event_id))
    return {"updated": tracelog.set_alert_status(event_id, body.status)}


@app.get("/api/admin/audit", dependencies=[Depends(auth.current_staff)])
def admin_audit():
    return auth.audit_rows()


@app.get("/replay/{item_id}", dependencies=[Depends(auth.current_staff)])
def replay(item_id: str, system: str = "after"):
    """A recorded evaluation run (eval/results), shown in the web page without calling the LLM again."""
    rows = json.loads((ROOT / "eval" / "results" / f"{system}.json").read_text())
    r = rows.get(item_id, {})
    if r.get("passages") and r.get("notes"):   # rebuild the citation contract from the recorded passages (English answer, as recorded)
        from mcp_servers.papers_server import _hit
        hits = [_hit(pid) for pid in r["passages"]]
        ev = {"recorded": {"notes": r["notes"], "picks": [{"query": "q", "best": r["passages"]}], "results": {"q": hits}}}
        r = {**r, **build_citations(r.get("answer", ""), ev, {}), "replayed": True}
    return r


@app.post("/chat", dependencies=[Depends(_same_origin)])
async def chat(body: ChatIn, user: dict = Depends(auth.current_user), deps: Container = Depends(get_deps)):
    r = await run_after(STATE["graph"], deps, user["user_id"], body.message)
    tracelog.log_event(user["user_id"], body.message, r)
    if body.lang == "ko":
        r = {**r, "answer_en": r["answer"], **(await to_korean(deps, Usage(), r["answer"]))}
    return r


@app.post("/approve", dependencies=[Depends(_same_origin)])
async def approve(body: ApproveIn, user: dict = Depends(auth.current_user), deps: Container = Depends(get_deps)):
    r = await run_after(STATE["graph"], deps, user["user_id"], "", thread_id=body.thread_id,
                        resume="yes" if body.approve else "no")
    tracelog.log_event(user["user_id"], "(approval) " + ("yes" if body.approve else "no"), r)
    if body.lang == "ko":
        r = {**r, "answer_en": r["answer"], **(await to_korean(deps, Usage(), r["answer"]))}
    return r


@app.post("/chat/stream", dependencies=[Depends(_same_origin)])
async def chat_stream(body: ChatIn, user: dict = Depends(auth.current_user), deps: Container = Depends(get_deps)):
    """SSE. Events: {"event":"route"} once the route is known; {"step":...} per finished node; {"done":true,...} with the whole
    checked answer (NOT token streaming); {"event":"error"} if the run fails (the browser does not auto-retry: a retry would
    run the whole paid pipeline again)."""
    user_id, message, lang = user["user_id"], body.message, body.lang

    async def events():
        u, tid, t = Usage(), str(uuid.uuid4()), time.time()
        cfg = {"configurable": {"deps": deps, "usage": u, "thread_id": tid}, "recursion_limit": 30}
        final, routed = {}, False
        try:
            async for upd in STATE["graph"].astream({"user_id": user_id, "message": message, "trace": [], "timings": {}}, cfg,
                                                    stream_mode="updates", subgraphs=True):
                ns, data = upd
                prefix = (ns[0].split(":")[0].replace("_agent", "") + ".") if ns else ""   # diet. / exercise. inside the subgraphs
                for node, out in (data or {}).items():
                    if node == "__interrupt__":
                        final["interrupt"] = out[0].value if out else None
                        continue
                    out = out or {}
                    final.update({k: v for k, v in out.items() if k in ("answer", "route", "safety_notes", "retries", "removed", "path",
                                                                       "path_reason", "escalated")})
                    if out.get("route") and not routed and node in ("guard", "supervisor"):
                        routed = True
                        yield f"data: {json.dumps({'event': 'route', 'route': out['route'], 'path': out.get('path'), 'path_reason': out.get('path_reason')})}\n\n"
                    for dom, ev in (out.get("evidence") or {}).items():
                        final.setdefault("evidence", {})[dom] = ev
                        final.setdefault("notes", []).extend((ev or {}).get("notes") or [])
                        final.setdefault("domains", []).append(dom)
                    yield f"data: {json.dumps({'step': prefix + node, 'seconds': (out.get('timings') or {}).get(node), 'route': out.get('route')})}\n\n"
            s = deps.settings
            answer_ready = round(time.time() - t, 2)   # the checked English answer exists; it is sent whole with `done`
            cites = build_citations(final.get("answer", ""), final.get("evidence", {}), {})
            shown = {"answer": final.get("answer", ""), "translated": False}
            if lang == "ko":   # English mode (lang = "en") shows the safety-checked English answer as is: no extra LLM call
                try:
                    shown = await to_korean(deps, u, final.get("answer", ""))
                except Exception:   # translation failed: the safety-checked English answer is still shown
                    pass
            log = {k: v for k, v in final.items() if k not in ("evidence", "answer")}
            tracelog.log_event(user_id, message, {**log, "answer": shown["answer"], "meta": {"citations": cites["citations"], "route": final.get("route"), "en": {"answer": final.get("answer", "")},
                                                                                     **({"ko": {"answer": shown["answer"]}} if shown["translated"] else {})}, "latency_s": round(time.time() - t, 2), "calls": u.calls, "tokens_in": u.tokens_in,
                                                  "tokens_out": u.tokens_out, "cost": round(u.cost(s.price_in, s.price_out, s.price_embed), 5)})
            ask = final.get("interrupt")
            if lang == "ko" and ask and fixed_ko(ask.get("question", "")):
                ask = {**ask, "question": fixed_ko(ask["question"])}
            yield "data: " + json.dumps({"done": True, "answer": shown["answer"], "answer_en": final.get("answer", ""),
                                         "lang": "ko" if shown["translated"] else "en", "route": final.get("route"),
                                         "path": final.get("path"), "escalated": bool(final.get("escalated")),
                                         "interrupt": ask, "thread_id": tid,
                                         "sources": sorted({n.get("source") for n in final.get("notes", []) if n.get("source")}),
                                         "statements": cites["statements"], "citations": cites["citations"],
                                         "safety_notes": final.get("safety_notes", []), "answer_ready_s": answer_ready,
                                         "latency_s": round(time.time() - t, 2), "calls": u.calls,
                                         "cost": round(u.cost(s.price_in, s.price_out, s.price_embed), 5)}) + "\n\n"
        except Exception as e:   # noqa: BLE001 - reported to the page, which shows a retry button
            yield "data: " + json.dumps({"event": "error", "error": type(e).__name__}) + "\n\n"
    return StreamingResponse(events(), media_type="text/event-stream")
