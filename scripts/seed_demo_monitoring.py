"""Fill the admin screen with demo history (no API calls, $0).

- events: the 100 recorded evaluation answers (eval/results/after.json, real runs of this system), each placed back on
  its own synthetic user and spread over the last 14 days, plus a second copy of some advice answers on other days so
  usage differs between people. Rows are marked source = "demo-replay".
- records: synthetic diary entries (walks, glucose readings, meals) that fit each person's profile.
- alerts older than two days are marked handled; recent ones stay open.

    .venv/bin/python scripts/seed_demo_monitoring.py            # adds demo rows (removes earlier demo rows first)
    .venv/bin/python scripts/seed_demo_monitoring.py --users    # also reload the users table from data/users.json
"""
from __future__ import annotations

import json
import random
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from coach import tracelog  # noqa: E402
from coach.config import Settings  # noqa: E402
from mcp_servers.user_server import _db  # noqa: E402

DIARY = {  # per person: things they would plausibly log, (text, glucose range)
    "u01": ["walked 15 min after dinner", "white rice at lunch, half bowl", "1 can of soda"], "u02": ["walked 30 min in the park, checked feet: ok", "snack at 11 pm: yogurt"],
    "u03": ["slow walk 10 min", "orange juice at breakfast"], "u04": ["gym: weights 45 min", "2 beers with dinner", "ate out: noodle soup"],
    "u05": ["chair exercises 10 min", "skipped breakfast"], "u06": ["short walk before lunch", "ate half of lunch, low appetite"],
    "u07": ["walked 40 min in the evening", "dinner at 9:30 pm, kimchi and pickles"], "u08": ["brisk walk 30 min", "a glass of wine with dinner"],
    "u09": ["sat-to-stand practice 5 times", "soft rice porridge at 3 pm"], "u10": ["tennis 1 hour", "noodles for lunch", "beers on Saturday"],
}


def main():
    rnd = random.Random(7)
    con = _db()
    tracelog._db().close()
    if "--users" in sys.argv:
        con.execute("DELETE FROM users")
        for u in json.loads((ROOT / "data" / "users.json").read_text()):
            con.execute("INSERT INTO users VALUES (?, ?, ?)", (u["id"], u["name"], json.dumps(u)))
    con.execute("DELETE FROM events WHERE source = 'demo-replay'")
    con.execute("DELETE FROM logs WHERE text LIKE '[demo] %'")
    con.commit()

    now = datetime.now()

    def when(days_back: int) -> datetime:
        return (now - timedelta(days=days_back)).replace(hour=rnd.randint(7, 21), minute=rnd.randint(0, 59), second=0)

    results = json.loads((ROOT / "eval" / "results" / "after.json").read_text())
    items = list(results.items())
    rnd.shuffle(items)
    advice = [(k, r) for k, r in items if r.get("route") in ("diet", "exercise", "diet_exercise")]
    extra = [advice[i % len(advice)] for i in range(45)]
    for n, (k, r) in enumerate(items + extra):
        t = when(rnd.randint(0, 13) if n < len(items) else rnd.randint(0, 6))
        tracelog.log_event(r["user"], r["q"], r, source="demo-replay", ts=t.isoformat(timespec="seconds"))
    cut = (now - timedelta(days=2)).isoformat(timespec="seconds")
    tc = tracelog._db()
    tc.execute("UPDATE events SET alert_status = 'handled' WHERE source = 'demo-replay' AND alert IS NOT NULL AND ts < ?", (cut,))
    tc.commit()

    for uid, texts in DIARY.items():
        for d in range(13, -1, -1):
            for x in rnd.sample(texts, k=rnd.randint(0, len(texts))):
                con.execute("INSERT INTO logs (user_id, ts, text) VALUES (?, ?, ?)", (uid, when(d).isoformat(timespec="minutes"), "[demo] " + x))
            if rnd.random() < 0.6:
                g = rnd.randint(95, 165) + (25 if uid in ("u04", "u10") else 0)
                con.execute("INSERT INTO logs (user_id, ts, text) VALUES (?, ?, ?)", (uid, when(d).isoformat(timespec="minutes"),
                                                                                    f"[demo] blood sugar {g} mg/dL"))
    con.commit()
    s = tracelog.summary()
    print(f"events {s['messages']} (open alerts {s['open_alerts']}), records:",
          con.execute("SELECT COUNT(*) FROM logs WHERE text LIKE '[demo] %'").fetchone()[0], "db:", Settings().db_path)


if __name__ == "__main__":
    main()
