"""Before / After charts for the report (docs/img/*.png) from eval/results/summary.json and after.json."""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
S = json.loads((ROOT / "eval" / "results" / "summary.json").read_text())
A = json.loads((ROOT / "eval" / "results" / "after.json").read_text())
IMG = ROOT / "docs" / "img"
IMG.mkdir(parents=True, exist_ok=True)
b, a = S["before"], S["after"]


def frac(x):
    n, d = x.split("/")
    return int(n) / int(d)


labels = ["answer score\n(rubric)", "gold evidence\nin context", "emergency\nhandled", "medicine change\nrefused", "held back on\nno evidence", "answers without\ndangerous advice"]
bv = [b["rubric_score"], b["gold_in_context"], frac(b["emergency_handled"]), frac(b["medicine_change_refused"]), frac(b["refusal_held_back"]), 1 - b["dangerous_advice_answers (rules S1-S7)"] / 24]
av = [a["rubric_score"], a["gold_in_context"], frac(a["emergency_handled"]), frac(a["medicine_change_refused"]), frac(a["refusal_held_back"]), 1 - a["dangerous_advice_answers (rules S1-S7)"] / 24]
x = np.arange(len(labels))
fig, ax = plt.subplots(figsize=(10, 4.2))
ax.bar(x - 0.2, bv, 0.4, label="Before: standard RAG", color="#98a2b3")
ax.bar(x + 0.2, av, 0.4, label="After: multi-agent", color="#2f6fed")
for i, (p, q) in enumerate(zip(bv, av)):
    ax.text(i - 0.2, p + 0.02, f"{p:.2f}", ha="center", fontsize=8)
    ax.text(i + 0.2, q + 0.02, f"{q:.2f}", ha="center", fontsize=8)
ax.set_xticks(x, labels, fontsize=9)
ax.set_ylim(0, 1.15)
ax.set_title("Quality and safety (same 42 messages)")
ax.legend(loc="upper left", fontsize=9)
fig.tight_layout()
fig.savefig(IMG / "before_after_quality.png", dpi=150)

steps = ["supervisor", "make_queries", "retrieve_mcp", "pick_notes", "writer"]
health = [r for r in A.values() if r["kind"] == "health"]
means = [np.mean([r["timings"].get(s, 0) for r in health]) for s in steps]
fig, ax = plt.subplots(figsize=(8, 3))
left = 0
colors = ["#7a5af8", "#f79009", "#12b76a", "#2e90fa", "#ee46bc"]
for s, m, c in zip(steps, means, colors):
    ax.barh([0], [m], left=left, color=c, label=f"{s} {m:.1f}s")
    left += m
ax.set_yticks([])
ax.set_xlabel("seconds (mean over 24 exercise questions)")
ax.set_title(f"After: where the time goes (mean {a['latency_mean_s (health)']} s, Before {b['latency_mean_s (health)']} s)")
ax.legend(fontsize=8, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.45))
fig.tight_layout()
fig.savefig(IMG / "after_latency_breakdown.png", dpi=150)
print("charts written")
