"""Score the three systems on the same 100 messages -> eval/results/summary.json.

Systems (eval/results/<system>.json, all GPT-6 Luna, same papers, same masked profile):
- before: Standard Paper-Search RAG - question -> dense top-5 passages from all papers -> one answer call.
- agentic_rag: Health Agentic RAG alone - the single agent's evidence notes, answered again without any safety layer
  (eval/run_rag_only.py); health questions only.
- single: Single-Agent + Health Agentic RAG - one agentic RAG agent - our query chain, picker and note check over all papers, safety rules and answer check,
  but no supervisor: no routing, no personal / general split, no diet / exercise split, no records or service routes.
- after:  Multi-Agent + Health Agentic RAG - the multi-agent service (supervisor + diet / exercise / safety agents + records + fixed safety replies).

Measures
- answer accuracy on the 60 health questions: must-answer points graded by Claude Opus 5.5 (eval/scores_claude.json,
  1 / 0.75 / 0.5 / 0.25 / 0), per domain (exercise, diet, diet + exercise) and type (A own health, B general).
- gold evidence in context: verbatim gold sentences found in the passages handed to the answer step.
- dangerous advice: answers flagged by the code rules S1-S9.
- the 40 other messages (C my information and records, D chat, safety, service and privacy): handled correctly or not
  (graded by Claude from the answer, eval/scores_claude.json "handled"), and routing accuracy for the multi-agent system.
- latency (mean, p95), cost and LLM calls per message.
"""
import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from coach.retrieval.index import build_chunks  # noqa: E402
from coach.safety.rules import check_answer  # noqa: E402
from mcp_servers.user_server import profile_text  # noqa: E402

R = ROOT / "eval" / "results"
SYSTEMS = [s for s in ("before", "agentic_rag", "single", "after") if (R / f"{s}.json").exists()]
norm = lambda s: re.sub(r"\s+", " ", s).strip()  # noqa: E731
mean = lambda xs: round(float(np.mean(xs)), 3) if len(xs) else None  # noqa: E731


def gold_found(h, row) -> int:
    got = [norm(t) for t in row.get("passage_texts", [])]
    n = 0
    for g in h["gold"]:
        e = norm(g)
        probes = [e[:50], e[max(0, len(e) // 2 - 25): len(e) // 2 + 25], e[-50:]]
        n += any(any(p in t for p in probes) for t in got)
    return n


def main():
    Q = json.loads((ROOT / "eval" / "questions.json").read_text())
    users = {u["id"]: profile_text(u) for u in json.loads((ROOT / "data" / "users.json").read_text())}
    _, _, meta = build_chunks(ROOT / "data" / "papers")
    titles = {k: v["title"] for k, v in meta.items()}
    claude = json.loads((ROOT / "eval" / "scores_claude.json").read_text())
    res = {s: json.loads((R / f"{s}.json").read_text()) for s in SYSTEMS}
    out = {}
    for s, rows in res.items():
        H = Q["health"]
        hr = [rows[h["id"]] for h in H]
        pts = lambda hs: [v for h in hs for v in claude.get(s, {}).get(h["id"], [])]  # noqa: E731
        by = {}
        for dom in ("exercise", "diet", "diet_exercise"):
            for t in ("A", "B"):
                by[f"{dom} {t}"] = mean(pts([h for h in H if h["domain"] == dom and h["type"] == t]))
        n_gold = sum(len(h["gold"]) for h in H)
        found = sum(gold_found(h, rows[h["id"]]) for h in H)
        flagged = {h["id"]: [i["rule"].split()[0] for i in check_answer(rows[h["id"]]["answer"], users[h["user"]], h["q"], titles)]
                   for h in H}
        lat = [r["latency_s"] for r in hr]
        groups = {}
        for x in [x for x in Q["routing"] if x["id"] in rows]:
            key = x["group"] if x["group"] != "safety" else ("safety: emergency" if x["route"] == "emergency" else "safety: changing medicine")
            g = groups.setdefault(key, {"n": 0, "handled": 0, "route_ok": 0, "latency": [], "cost": []})
            r = rows[x["id"]]
            g["n"] += 1
            g["handled"] += claude.get("handled", {}).get(s, {}).get(x["id"], 0)
            g["route_ok"] += r.get("route") == x["route"]
            g["latency"].append(r["latency_s"])
            g["cost"].append(r["cost"])
        for g in groups.values():
            g["latency_mean_s"] = round(float(np.mean(g.pop("latency"))), 2)
            g["cost_total_$"] = round(float(np.sum(g.pop("cost"))), 5)
            if s != "after":
                g.pop("route_ok")
        o = {
            "answer_score (60 health questions)": mean(pts(H)),
            "answer_score A own health": mean(pts([h for h in H if h["type"] == "A"])),
            "answer_score B general": mean(pts([h for h in H if h["type"] == "B"])),
            "answer_score by domain and type": by,
            "points full / partial / zero": (lambda p: f"{sum(v == 1 for v in p)} / {sum(0 < v < 1 for v in p)} / {sum(v == 0 for v in p)}")(pts(H)),
            "gold_in_context": round(found / n_gold, 3),
            "safety_problem_answers (S1-S9)": sum(bool(v) for v in flagged.values()),
            "  of which dangerous advice (S1-S4, S6-S9)": sum(any(r != "S5" for r in v) for v in flagged.values()),
            "  of which missing low-blood-sugar warning only (S5)": sum(bool(v) and all(r == "S5" for r in v) for v in flagged.values()),
            "dangerous_advice_detail": {k: v for k, v in flagged.items() if v},
            "other 40 messages handled correctly": sum(g["handled"] for g in groups.values()) if groups else None,
            "other 40 by group": groups,
            "latency_mean_s (health)": round(float(np.mean(lat)), 2),
            "latency_p95_s (health)": round(float(np.percentile(lat, 95)), 2),
            "cost_per_message_$ (health)": round(float(np.mean([r["cost"] for r in hr])), 5),
            "cost_total_$ (all messages)": round(float(sum(r["cost"] for r in rows.values())), 4),
            "latency_mean_s (all messages)": round(float(np.mean([r["latency_s"] for r in rows.values()])), 2),
            "llm_calls_per_message (health)": round(float(np.mean([r["calls"] for r in hr])), 1),
            "retries": sum(r.get("retries", 0) for r in rows.values()),
            "removed_sentences": sum(len(r.get("removed", [])) for r in rows.values()),
            "dropped_notes": sum(len(r.get("dropped_notes", [])) for r in rows.values()),
        }
        if s == "after":
            exp = {x["id"]: x["route"] for x in Q["routing"]} | {h["id"]: h["domain"] for h in H}
            wrong = {k: rows[k]["route"] for k, v in exp.items() if rows[k]["route"] != v}
            o["routing_accuracy"] = f"{len(exp) - len(wrong)}/{len(exp)}"
            o["routing_errors"] = wrong
            if any("about_user" in rows[h["id"]] for h in H):
                o["personal_general_split"] = f"{sum(rows[h['id']].get('about_user') == (h['type'] == 'A') for h in H)}/{len(H)}"
        out[s] = o
    (R / "summary.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps({s: {k: v for k, v in o.items() if k not in ("dangerous_advice_detail", "other 40 by group")} for s, o in out.items()},
                     indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
