"""Our own monitoring log (instead of sending conversation content to LangSmith).

One row per message, kept on our own server (SQLite, the same file as the user records):
- who: the internal user id only. Names live in the users table and are joined only on the admin screen.
- what happened: route, which agents ran, safety rules applied, dangerous-advice retries / removed sentences.
- how much: latency, LLM calls, tokens, cost.
- content: the message and the answer, so the care team can read an emergency or a call request. It never leaves the
  server, and rows older than COACH_LOG_DAYS (default 90) are deleted by purge().
- alert: emergency / handoff (call request) / med_change (wants to change a medicine) / other_user (asked for someone
  else's data). Alerts stay "open" until a staff member marks them handled on the admin screen.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta

from coach.config import Settings

ALERT_ROUTES = {"emergency": "Emergency", "handoff": "Call request", "med_change": "Medicine change", "other_user": "Other person's data"}

SCHEMA = """CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, user_id TEXT, route TEXT, domains TEXT, message TEXT, answer TEXT,
  safety_rules TEXT, retries INTEGER, removed INTEGER, latency_s REAL, calls INTEGER, tokens INTEGER, cost REAL,
  alert TEXT, alert_status TEXT, source TEXT)"""


def _db(path=None) -> sqlite3.Connection:
    con = sqlite3.connect(path or Settings().db_path)
    con.execute(SCHEMA)
    return con


def log_event(user_id: str, message: str, r: dict, source: str = "live", ts: str | None = None, path=None) -> int:
    """Store one handled message. r is the dict returned by coach.runner.run_after (or the SSE summary)."""
    route = r.get("route") or ""
    alert = route if route in ALERT_ROUTES else None
    row = (ts or datetime.now().isoformat(timespec="seconds"), user_id, route, ",".join(r.get("domains") or []), message,
           r.get("answer", ""), ",".join(s.get("id", "") for s in r.get("safety_notes") or []), r.get("retries") or 0,
           len(r.get("removed") or []), r.get("latency_s"), r.get("calls"), (r.get("tokens_in") or 0) + (r.get("tokens_out") or 0),
           r.get("cost"), alert, "open" if alert else None, source)
    con = _db(path)
    cur = con.execute("INSERT INTO events (ts, user_id, route, domains, message, answer, safety_rules, retries, removed, latency_s, "
                      "calls, tokens, cost, alert, alert_status, source) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", row)
    con.commit()
    return cur.lastrowid


def purge(days: int | None = None, path=None) -> int:
    """Retention: delete rows older than `days` (env COACH_LOG_DAYS, default 90)."""
    days = days or int(os.environ.get("COACH_LOG_DAYS", "90"))
    cut = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    con = _db(path)
    n = con.execute("DELETE FROM events WHERE ts < ?", (cut,)).rowcount
    con.commit()
    return n


def rows(sql: str, args=(), path=None) -> list[dict]:
    con = _db(path)
    con.row_factory = sqlite3.Row
    return [dict(x) for x in con.execute(sql, args).fetchall()]


def set_alert_status(event_id: int, status: str, path=None) -> int:
    con = _db(path)
    n = con.execute("UPDATE events SET alert_status = ? WHERE id = ? AND alert IS NOT NULL", (status, event_id)).rowcount
    con.commit()
    return n


def summary(days: int = 14, path=None) -> dict:
    """Numbers for the admin screen: per-day counts by route, route mix, cost / latency per day, open alerts."""
    since = (datetime.now() - timedelta(days=days - 1)).date().isoformat()
    ev = rows("SELECT * FROM events WHERE ts >= ? ORDER BY ts", (since,), path)
    day_list = [(datetime.now().date() - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    groups = {"Diet / exercise advice": ("diet", "exercise", "diet_exercise"), "Records & my data": ("log", "my_data", "delete_record"),
              "Chat & service": ("chat", "privacy_info"), "Alerts": tuple(ALERT_ROUTES)}
    per_day = {g: [sum(1 for e in ev if e["ts"][:10] == d and e["route"] in rs) for d in day_list] for g, rs in groups.items()}
    cost = [round(sum(e["cost"] or 0 for e in ev if e["ts"][:10] == d), 4) for d in day_list]
    lat = [e["latency_s"] for e in ev if e["route"] in groups["Diet / exercise advice"] and e["latency_s"]]
    routes: dict = {}
    for e in ev:
        routes[e["route"]] = routes.get(e["route"], 0) + 1
    return {"days": day_list, "per_day": per_day, "cost_per_day": cost, "routes": routes, "messages": len(ev),
            "active_users": len({e["user_id"] for e in ev}), "cost": round(sum(cost), 4),
            "advice_latency_avg": round(sum(lat) / len(lat), 1) if lat else None,
            "safety_retries": sum(e["retries"] or 0 for e in ev), "removed_sentences": sum(e["removed"] or 0 for e in ev),
            "open_alerts": sum(1 for e in ev if e["alert_status"] == "open"),
            "by_user": {u: sum(1 for e in ev if e["user_id"] == u) for u in sorted({e["user_id"] for e in ev})},
            "rules": _count(",".join(e["safety_rules"] or "" for e in ev).split(","))}


def _count(xs) -> dict:
    out: dict = {}
    for x in xs:
        if x:
            out[x] = out.get(x, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))

