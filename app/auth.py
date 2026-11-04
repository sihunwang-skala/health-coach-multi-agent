"""Accounts, sign-in and sessions (user screen and care-team console are separate roles).

- Passwords: scrypt (standard library), per-password salt. Never stored or logged in plain text.
- Sessions: a random token in an HttpOnly cookie; only its SHA-256 is stored. User sessions last 14 days, care-team sessions
  8 hours. Two cookies (`coach_session`, `coach_staff`) so one browser can hold both, but each API checks only its own role.
- Brute force: 5 failed sign-ins per (username, address) in 10 minutes lock that pair for the rest of the window.
- CSRF: cookies are SameSite=Lax and every state-changing request must carry the page's own Origin (see `same_origin`).
- Audit: every time a care-team member opens a person's data or changes an alert, a row is written (`audit`).
Accounts live in the same SQLite file as the profiles; an account is linked to its profile only by `user_id`.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from datetime import datetime

from fastapi import HTTPException, Request, Response

from coach.config import Settings

DB_PATH = Settings().db_path
USER_COOKIE, STAFF_COOKIE = "coach_session", "coach_staff"
TTL = {"user": 14 * 24 * 3600, "staff": 8 * 3600}
COOKIE = {"user": USER_COOKIE, "staff": STAFF_COOKIE}
SCHEMA = [
    """CREATE TABLE IF NOT EXISTS accounts (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, pw_hash TEXT, role TEXT,
       user_id TEXT, display_name TEXT, created TEXT, disabled INTEGER DEFAULT 0)""",
    "CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, account_id INTEGER, role TEXT, created REAL, expires REAL)",
    "CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, staff TEXT, action TEXT, target TEXT)",
]
FAILS: dict[tuple[str, str], list[float]] = {}
MAX_FAILS, WINDOW = 5, 600


def _con() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    for q in SCHEMA:
        con.execute(q)
    return con


def run(sql: str, args=(), *, one: bool = False, many: bool = False):
    """One statement on its own short-lived connection (committed and closed before returning), so no request can hold the
    database file while another one writes."""
    con = _con()
    try:
        cur = con.execute(sql, args)
        out = cur.fetchone() if one else cur.fetchall() if many else cur
        res = (dict(out) if out else None) if one else [dict(r) for r in out] if many else (cur.lastrowid, cur.rowcount)
        con.commit()
        return res
    finally:
        con.close()


# ---- passwords -------------------------------------------------------------------------------------------------------
def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${salt.hex()}${h.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, h = stored.split("$")
        got = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(got.hex(), h)
    except (ValueError, TypeError):
        return False


DUMMY = hash_password("not-a-real-password")   # checked for unknown usernames so timing does not reveal which usernames exist


def check_password_rules(pw: str) -> str | None:
    if len(pw) < 8:
        return "비밀번호는 8자 이상이어야 해요."
    if pw.isdigit() or pw.isalpha():
        return "비밀번호에 문자와 숫자를 함께 사용해 주세요."
    return None


# ---- accounts --------------------------------------------------------------------------------------------------------
def norm(username: str) -> str:
    return (username or "").strip().lower()


def create_account(username: str, password: str, role: str, display_name: str, user_id: str | None = None) -> int:
    try:
        return run("INSERT INTO accounts (username, pw_hash, role, user_id, display_name, created) VALUES (?,?,?,?,?,?)",
                   (norm(username), hash_password(password), role, user_id, display_name, datetime.now().isoformat(timespec="seconds")))[0]
    except sqlite3.IntegrityError:
        raise HTTPException(409, "이미 사용 중인 아이디예요.")


def set_password(account_id: int, password: str) -> None:
    run("UPDATE accounts SET pw_hash = ? WHERE id = ?", (hash_password(password), account_id))
    run("DELETE FROM sessions WHERE account_id = ?", (account_id,))   # a new password signs out every device


def delete_account(account_id: int) -> None:
    run("DELETE FROM sessions WHERE account_id = ?", (account_id,))
    run("DELETE FROM accounts WHERE id = ?", (account_id,))


# ---- sign-in ---------------------------------------------------------------------------------------------------------
def _locked(key) -> bool:
    now = time.time()
    FAILS[key] = [t for t in FAILS.get(key, []) if now - t < WINDOW]
    return len(FAILS[key]) >= MAX_FAILS


def login(request: Request, response: Response, username: str, password: str, role: str) -> dict:
    ip = request.client.host if request.client else "?"
    key = (norm(username), ip)
    if _locked(key):
        raise HTTPException(429, "로그인에 여러 번 실패했어요. 10분 후에 다시 시도해 주세요.")
    row = run("SELECT * FROM accounts WHERE username = ?", (norm(username),), one=True)
    ok = verify_password(password or "", row["pw_hash"] if row else DUMMY)
    if not (row and ok and row["role"] == role and not row["disabled"]):   # same message for every cause
        FAILS.setdefault(key, []).append(time.time())
        raise HTTPException(401, "아이디 또는 비밀번호가 맞지 않아요.")
    FAILS.pop(key, None)
    start_session(request, response, row["id"], role)
    return row


def start_session(request: Request, response: Response, account_id: int, role: str) -> None:
    token = secrets.token_urlsafe(32)
    now = time.time()
    run("DELETE FROM sessions WHERE expires < ?", (now,))
    run("INSERT INTO sessions VALUES (?,?,?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), account_id, role, now, now + TTL[role]))
    secure = request.url.scheme == "https" or os.environ.get("COACH_COOKIE_SECURE") == "1"
    response.set_cookie(COOKIE[role], token, max_age=TTL[role], httponly=True, samesite="lax", secure=secure, path="/")


def end_session(request: Request, response: Response, role: str) -> None:
    token = request.cookies.get(COOKIE[role])
    if token:
        run("DELETE FROM sessions WHERE token_hash = ?", (hashlib.sha256(token.encode()).hexdigest(),))
    response.delete_cookie(COOKIE[role], path="/")


def session_account(request: Request, role: str) -> dict | None:
    token = request.cookies.get(COOKIE[role])
    if not token:
        return None
    return run("SELECT a.* FROM sessions s JOIN accounts a ON a.id = s.account_id WHERE s.token_hash = ? AND s.role = ? "
               "AND s.expires > ? AND a.disabled = 0 AND a.role = ?",
               (hashlib.sha256(token.encode()).hexdigest(), role, time.time(), role), one=True)


def current_user(request: Request) -> dict:
    a = session_account(request, "user")
    if not a:
        raise HTTPException(401, "로그인이 필요해요.")
    return a


def current_staff(request: Request) -> dict:
    a = session_account(request, "staff")
    if not a:
        raise HTTPException(401, "의료진 로그인이 필요해요.")
    return a


def same_origin(request: Request) -> None:
    """State-changing requests must come from our own pages: an Origin header, when present, must match the host."""
    origin = request.headers.get("origin")
    if origin and origin.split("://", 1)[-1] != request.headers.get("host"):
        raise HTTPException(403, "허용되지 않은 요청이에요.")


def audit(staff: str, action: str, target: str = "") -> None:
    run("INSERT INTO audit (ts, staff, action, target) VALUES (?,?,?,?)", (datetime.now().isoformat(timespec="seconds"), staff, action, target))


def audit_rows(limit: int = 100) -> list[dict]:
    return run("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,), many=True)
