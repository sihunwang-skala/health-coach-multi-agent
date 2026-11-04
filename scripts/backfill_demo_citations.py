"""Give the demo-history rows (source = demo-replay) their evidence AND their Korean text, so the chat history shows the same numbered references as a
live answer and can be read in Korean or English.
The rows were made from the recorded 2026-10-22 evaluation answers; this matches each row to its recorded run by the answer text and stores the
citation data (title, link, the passage the picker chose, supporting sentences) in the row's `meta`. Re-runnable: it rewrites only `meta` (citations), nothing else in the row.
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
ko = json.loads((ROOT / "data" / "demo_translations_ko.json").read_text())   # English text -> Korean (Claude-written, checked for markers and numbers)
tracelog._db().close()   # makes sure the meta column exists
con = sqlite3.connect(Settings().db_path)
n = t = 0
for eid, message, answer, route, old in con.execute("SELECT id, message, answer, route, meta FROM events WHERE source IN ('demo-replay', 'live')").fetchall():
    meta = json.loads(old) if old else {"route": route}
    r = by_answer.get(answer)
    if r and "citations" not in meta or r and meta.get("citations") is not None and not meta.get("en"):
        ev = {"recorded": {"notes": r["notes"], "picks": [{"query": "q", "best": r["passages"]}], "results": {"q": [_hit(p) for p in r["passages"]]}}}
        meta["citations"] = build(answer, ev, {})["citations"]
        n += 1
    if answer in ko or message in ko:
        meta["en"] = {"answer": answer}
        meta["ko"] = {k: ko[v] for k, v in (("message", message), ("answer", answer)) if v in ko}
        t += 1
    con.execute("UPDATE events SET meta = ? WHERE id = ?", (json.dumps(meta, ensure_ascii=False), eid))
con.commit()
print("rows given citations:", n, "| rows given Korean text:", t)
