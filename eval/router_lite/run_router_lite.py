"""Router-lite experiment (English, 30 messages, each run once). No paid API: the router call is made by a Haiku model outside
this script; this script builds the prompts and scores the answers. Nothing here touches eval/results/ (2026-10-22).

  python eval/router_lite/run_router_lite.py prompts            # writes prompts_before.json / prompts_after.json (shuffled)
  python eval/router_lite/run_router_lite.py score answers_before.json answers_after.json
answers_*.json: {"<item id>": {"route": ..., ...}} exactly as the router returned them.
"""
from __future__ import annotations

import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from coach.agents.prompts import SUPERVISOR  # noqa: E402
from coach.agents.supervisor import DEEP_TERMS  # noqa: E402
from coach.safety.rules import applicable_rules, is_emergency  # noqa: E402

HERE = Path(__file__).parent
ITEMS = json.loads((HERE / "items.json").read_text())
USERS = {u["id"]: u for u in json.loads((ROOT / "data/users.json").read_text())}
AFTER = (HERE / "prompt.txt").read_text()
# question-side code check for "change my medicine" wording (deliberately simple: it misses rephrasings, the router is the backup)
MED_Q = re.compile(r"(?i)\b(skip|stop|double|halve|half|cut|reduce|omit)\b.{0,25}\b(insulin|metformin|glimepiride|gliclazide|medicine|medication|pills?|dose)")
FAST = {"emergency", "med_change"}


def profile(uid: str) -> str:
    u = USERS[uid]
    return "; ".join(f"{k}: {', '.join(u[k]) if isinstance(u[k], list) else u[k]}" for k in
                     ("age", "gender", "conditions", "medications", "activity", "mobility", "goal", "diet"))


def build(variant: str, it: dict) -> str:
    p = profile(it["user"])
    if variant == "before":
        return SUPERVISOR.format(profile=p, message=it["message"])
    return AFTER.replace("{profile}", p).replace("{message}", it["message"])


def normalise(variant: str, a: dict) -> dict:
    """Both router outputs -> {route, ambiguous, needs_escalation}."""
    if variant == "after":
        return {"route": a.get("route"), "ambiguous": bool(a.get("ambiguous")), "needs_escalation": bool(a.get("needs_escalation"))}
    r = a.get("route")
    if r in ("diet", "exercise", "diet_exercise"):
        r = "personal" if a.get("about_user") is not False else "general"
    elif r in ("handoff", "other_user", "privacy_info"):
        r = "service"
    return {"route": r, "ambiguous": False, "needs_escalation": False}


def decide(it: dict, a: dict) -> dict:
    """Code first, router second. Escalation never rests on the router's own flag alone."""
    msg, prof = it["message"], profile(it["user"])
    if is_emergency(msg):
        return {"route": "emergency", "by": "code"}
    if MED_Q.search(msg):
        return {"route": "med_change", "by": "code"}
    route = a.get("route")
    if route in FAST:                       # the router may only ADD a fixed safety reply, never remove one
        return {"route": route, "by": "router"}
    signals = []
    if applicable_rules(prof, msg, ("diet", "exercise")):
        signals.append("safety rule applies to profile")
    if DEEP_TERMS.search(msg):
        signals.append("medicine/low-sugar/complication/alcohol word")
    if a.get("needs_escalation"):
        signals.append("router flag")
    if a.get("ambiguous"):
        signals.append("ambiguous")
    if route == "personal":
        signals.append("personal question")
    return {"route": route, "by": "router", "deep": bool(signals), "signals": signals, "ambiguous": bool(a.get("ambiguous"))}


def correct(it: dict, a: dict, d: dict) -> bool:
    k = it["kind"]
    if k == "ambiguous":                    # do not commit wrongly: flagged ambiguous, or sent down the deep path
        return bool(a.get("ambiguous")) or bool(d.get("deep"))
    return d["route"] == k


def score(variant: str, answers: dict) -> dict:
    rows, conf = [], defaultdict(Counter)
    for it in ITEMS:
        raw = answers[it["id"]]
        a = normalise(variant, raw)
        d = decide(it, a)
        ok_final = correct(it, a, d)
        model_label = "ambiguous" if a["ambiguous"] else a["route"]
        ok_router = (a["ambiguous"] or bool(d.get("deep"))) if it["kind"] == "ambiguous" else a["route"] == it["kind"]
        conf[it["kind"]][model_label] += 1
        rows.append({"id": it["id"], "kind": it["kind"], "message": it["message"], "router": raw, "router_ok": ok_router,
                     "final": d, "final_ok": ok_final})
    by_kind = {}
    for k in dict.fromkeys(i["kind"] for i in ITEMS):
        r = [x for x in rows if x["kind"] == k]
        by_kind[k] = {"n": len(r), "router_alone": sum(x["router_ok"] for x in r), "code_plus_router": sum(x["final_ok"] for x in r)}
    tot = {"router_alone": sum(x["router_ok"] for x in rows), "code_plus_router": sum(x["final_ok"] for x in rows), "n": len(rows)}
    return {"variant": variant, "by_kind": by_kind, "total": tot, "confusion": {k: dict(v) for k, v in conf.items()},
            "failures": [x for x in rows if not (x["router_ok"] and x["final_ok"])], "rows": rows}


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "prompts":
        order = ITEMS[:]
        random.Random(7).shuffle(order)
        for v in ("before", "after"):
            (HERE / f"prompts_{v}.json").write_text(json.dumps([{"id": i["id"], "prompt": build(v, i)} for i in order], indent=1, ensure_ascii=False))
        print("wrote prompts_before.json prompts_after.json,", len(order), "items each")
    elif cmd == "score":
        out = {}
        for v, f in zip(("before", "after"), sys.argv[2:4]):
            out[v] = score(v, json.loads(Path(f).read_text()))
        (HERE / "scores.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
        for v, s in out.items():
            print(v, s["total"], {k: (x["router_alone"], x["code_plus_router"], x["n"]) for k, x in s["by_kind"].items()})
