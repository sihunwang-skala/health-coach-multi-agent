"""MCP server 2 - user profile and records (SQLite). The profile goes out WITHOUT the name (masking: no direct identifier
reaches an LLM or a trace). Deleting a record is a separate tool that the graph calls only after human approval.
    .venv/bin/python mcp_servers/user_server.py      # stdio server for external MCP clients
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from fastmcp import FastMCP

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from coach.config import Settings  # noqa: E402

mcp = FastMCP("coach-users")
DB = Settings().db_path


def _db() -> sqlite3.Connection:
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, name TEXT, profile TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, ts TEXT, text TEXT)")
    if not con.execute("SELECT 1 FROM users LIMIT 1").fetchone():
        for u in json.loads((ROOT / "data" / "users.json").read_text()):
            con.execute("INSERT INTO users VALUES (?, ?, ?)", (u["id"], u["name"], json.dumps(u)))
        con.commit()
    return con


def profile_text(u: dict) -> str:
    """Health fields only - name and id are never included (masking)."""
    return (f"age: {u['age']}; gender: {u['gender']}; conditions: {', '.join(u['conditions'])}; "
            f"medications: {', '.join(u['medications'])}; diet: {u.get('diet', '')}; activity: {u['activity']}; mobility: {u['mobility']}; "
            f"goal: {u['goal']}")


def full_profiles() -> list[dict]:
    """Server-side only (user and admin screens): the stored profiles WITH names. Not an MCP tool, so no agent or LLM
    can read names."""
    con = _db()
    try:
        return [json.loads(p) for (p,) in con.execute("SELECT profile FROM users ORDER BY id").fetchall()]
    finally:
        con.close()


def get_full_profile(user_id: str) -> dict | None:
    """Server-side only (not an MCP tool): one stored profile WITH the name, for the signed-in user's own screen."""
    con = _db()
    try:
        row = con.execute("SELECT profile FROM users WHERE id = ?", (user_id,)).fetchone()
    finally:
        con.close()
    return json.loads(row[0]) if row else None


def create_user(user_id: str, profile: dict) -> None:
    """Server-side only: store a new profile at sign-up (the account itself lives in app/auth.py)."""
    con = _db()
    con.execute("INSERT INTO users VALUES (?, ?, ?)", (user_id, profile["name"], json.dumps({**profile, "id": user_id}, ensure_ascii=False)))
    con.commit()
    con.close()


def delete_user(user_id: str) -> None:
    """Server-side only: account deletion removes the profile, the records and the monitoring log rows of this person."""
    con = _db()
    con.execute("DELETE FROM users WHERE id = ?", (user_id,))
    con.execute("DELETE FROM logs WHERE user_id = ?", (user_id,))
    try:
        con.execute("DELETE FROM events WHERE user_id = ?", (user_id,))
    except sqlite3.OperationalError:   # the monitoring table is created by coach.tracelog on first use
        pass
    con.commit()
    con.close()


@mcp.tool
def get_profile(user_id: str) -> dict:
    """The user's health profile as text (masked: no name)."""
    row = _db().execute("SELECT profile FROM users WHERE id = ?", (user_id,)).fetchone()
    return {"profile": profile_text(json.loads(row[0])) if row else ""}


@mcp.tool
def log_record(user_id: str, text: str) -> dict:
    """Record an activity or reading the user reported."""
    con = _db()
    cur = con.execute("INSERT INTO logs (user_id, ts, text) VALUES (?, ?, ?)", (user_id, datetime.now().isoformat(timespec="minutes"), text))
    con.commit()
    return {"id": cur.lastrowid, "text": text}


@mcp.tool
def list_records(user_id: str, limit: int = 20) -> dict:
    """The user's latest records."""
    rows = _db().execute("SELECT id, ts, text FROM logs WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit)).fetchall()
    return {"records": [{"id": i, "ts": t, "text": x} for i, t, x in rows]}


@mcp.tool
def delete_record(user_id: str, record_id: int) -> dict:
    """Delete one record. Irreversible: the graph calls this only after the user approved it (human-in-the-loop)."""
    con = _db()
    n = con.execute("DELETE FROM logs WHERE user_id = ? AND id = ?", (user_id, record_id)).rowcount
    con.commit()
    return {"deleted": n}


if __name__ == "__main__":
    mcp.run()
