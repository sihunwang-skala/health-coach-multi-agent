"""Give the demo-history rows (source = demo-replay) their evidence, so the chat history shows the same numbered references as a live answer.
The rows were made from the recorded 2026-10-22 evaluation answers; this matches each row to its recorded run by the answer text and stores the
citation data (title, link, the passage the picker chose, supporting sentences) in the row's `meta`. Additive: nothing else in the row changes.
  .venv/bin/python scripts/backfill_demo_citations.py
"""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from coach import tracelog  # noqa: E402
from coach.citations import build  # noqa: E402
from coach.config import Settings  # noqa: E402
from mcp_servers.papers_server import _hit  # noqa: E402

runs = json.loads((ROOT / "eval" / "results" / "after.json").read_text())
by_answer = {v["answer"]: v for v in runs.values() if isinstance(v, dict) and v.get("answer") and v.get("passages") and v.get("notes")}
tracelog._db().close()   # makes sure the meta column exists
con = sqlite3.connect(Settings().db_path)
n = 0
for eid, answer, route in con.execute("SELECT id, answer, route FROM events WHERE meta IS NULL AND source = 'demo-replay'").fetchall():
    r = by_answer.get(answer)
    if not r:
        continue
    ev = {"recorded": {"notes": r["notes"], "picks": [{"query": "q", "best": r["passages"]}], "results": {"q": [_hit(p) for p in r["passages"]]}}}
    con.execute("UPDATE events SET meta = ? WHERE id = ?", (json.dumps({"citations": build(answer, ev, {})["citations"], "route": route}, ensure_ascii=False), eid))
    n += 1
con.commit()
print("rows given citations:", n)
