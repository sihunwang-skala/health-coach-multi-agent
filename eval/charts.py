"""Charts for the report (docs/img/*.png), computed from eval/results/*.json and eval/scores_claude.json.
    .venv/bin/python eval/charts.py
"""
import json
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from coach.safety.rules import check_answer  # noqa: E402
from mcp_servers.user_server import profile_text  # noqa: E402

plt.rcParams["font.family"] = ["AppleGothic", "Noto Sans CJK KR", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
R = ROOT / "eval" / "results"
IMG = ROOT / "docs" / "img"
IMG.mkdir(parents=True, exist_ok=True)
SYS = ["before", "agentic_rag", "single", "after"]
LBL = {"before": "Standard Paper-Search RAG", "agentic_rag": "Health Agentic RAG",
       "single": "Single-Agent +\nHealth Agentic RAG", "after": "Multi-Agent +\nHealth Agentic RAG"}
COL = {"before": "#98a2b3", "agentic_rag": "#7a5af8", "single": "#f79009", "after": "#2f6fed"}
Q = json.loads((ROOT / "eval" / "questions.json").read_text())
H, O = Q["health"], Q["routing"]
G = json.loads((ROOT / "eval" / "scores_claude.json").read_text())
RES = {s: json.loads((R / f"{s}.json").read_text()) for s in SYS}
PROF = {u["id"]: profile_text(u) for u in json.loads((ROOT / "data" / "users.json").read_text())}
norm = lambda s: re.sub(r"\s+", " ", s).strip()  # noqa: E731


def score(s, hs):
    p = [v for h in hs for v in G[s][h["id"]]]
    return 100 * sum(p) / len(p)


def gold(s):
    tot = found = 0
    for h in H:
        got = [norm(t) for t in RES[s][h["id"]].get("passage_texts", [])]
        for g in h["gold"]:
            e = norm(g)
            probes = [e[:50], e[max(0, len(e) // 2 - 25): len(e) // 2 + 25], e[-50:]]
            found += any(any(p in t for p in probes) for t in got)
            tot += 1
    return 100 * found / tot


def bars(ax, groups, systems, values, title, unit="%", ylim=None):
    x = np.arange(len(groups))
    w = 0.8 / len(systems)
    for i, s in enumerate(systems):
        v = values[s]
        b = ax.bar(x + (i - (len(systems) - 1) / 2) * w, v, w, label=LBL[s].replace("\n", " "), color=COL[s])
        for r, val in zip(b, v):
            ax.text(r.get_x() + r.get_width() / 2, r.get_height() + (ylim or 100) * 0.01, f"{val:.0f}{unit}", ha="center", fontsize=7)
    ax.set_xticks(x, groups, fontsize=9)
    ax.set_title(title, fontsize=11)
    if ylim:
        ax.set_ylim(0, ylim)
    ax.spines[["top", "right"]].set_visible(False)


# 1. headline quality and safety (60 health questions, four systems)
fig, ax = plt.subplots(figsize=(11, 4.4))
safe = {s: 100 * (1 - sum(bool(check_answer(RES[s][h["id"]]["answer"], PROF[h["user"]], h["q"], {})) for h in H) / len(H)) for s in SYS}
vals = {s: [score(s, H), score(s, [h for h in H if h["type"] == "A"]), score(s, [h for h in H if h["type"] == "B"]), gold(s), safe[s]] for s in SYS}
bars(ax, ["답변 점수", "본인 질문\n답변 점수", "일반 질문\n답변 점수", "꼭 필요한 근거를\n찾아 온 비율", "안전 문제가\n없는 답변"], SYS, vals,
     "건강 질문 60개: 4가지 시스템 비교 (같은 질문, 같은 논문, GPT-6 Luna)", ylim=115)
ax.legend(fontsize=8, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.2))
fig.tight_layout()
fig.savefig(IMG / "result_health_four_systems.png", dpi=150)

# 2. answer score by question kind
kinds = [("운동", "exercise"), ("식단", "diet"), ("식단+운동", "diet_exercise")]
groups, vals = [], {s: [] for s in SYS}
for name, d in kinds:
    for t, tn in (("A", "본인"), ("B", "일반")):
        groups.append(f"{name}\n{tn} 질문")
        for s in SYS:
            vals[s].append(score(s, [h for h in H if h["domain"] == d and h["type"] == t]))
fig, ax = plt.subplots(figsize=(11, 4.4))
bars(ax, groups, SYS, vals, "질문 종류별 답변 점수 (각 질문 10개)", ylim=115)
ax.legend(fontsize=8, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.2))
fig.tight_layout()
fig.savefig(IMG / "result_by_question_kind.png", dpi=150)

# 3. the 40 non-health messages (three systems)
S3 = ["before", "single", "after"]
og = [("내 정보·기록", lambda x: x["group"].startswith("C")), ("잡담", lambda x: x["group"].startswith("D")),
      ("응급 상황", lambda x: x["route"] == "emergency"), ("약 변경 거절", lambda x: x["route"] == "med_change"),
      ("상담·삭제·\n다른 사람·개인정보", lambda x: x["group"] == "service and privacy"), ("전체 40개", lambda x: True)]
vals = {s: [100 * sum(G["handled"][s][x["id"]] for x in O if f(x)) / sum(1 for x in O if f(x)) for _, f in og] for s in S3}
fig, ax = plt.subplots(figsize=(11, 4.2))
bars(ax, [n for n, _ in og], S3, vals, "건강 질문 외 메시지 40개: 제대로 처리한 비율", ylim=115)
ax.legend(fontsize=8, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.2))
fig.tight_layout()
fig.savefig(IMG / "result_other_messages.png", dpi=150)

# 4. time and cost per message (three systems, health vs other messages)
fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
for ax, (key, unit, title, f) in zip(axes, [("latency_s", "초", "평균 응답 시간 (초)", lambda v: v),
                                            ("cost", "", "메시지 1개당 비용 (센트)", lambda v: 100 * v)]):
    v = {s: [f(np.mean([RES[s][h["id"]][key] for h in H])), f(np.mean([RES[s][x["id"]][key] for x in O])),
             f(np.mean([r[key] for r in RES[s].values()]))] for s in S3}
    x = np.arange(3)
    for i, s in enumerate(S3):
        b = ax.bar(x + (i - 1) * 0.26, v[s], 0.26, label=LBL[s].replace("\n", " "), color=COL[s])
        for r, val in zip(b, v[s]):
            ax.text(r.get_x() + r.get_width() / 2, r.get_height() * 1.01, f"{val:.2f}" if key == "cost" else f"{val:.1f}", ha="center", fontsize=7)
    ax.set_xticks(x, ["건강 질문 60개", "건강 질문 외 40개", "100개 전체"], fontsize=9)
    ax.set_title(title, fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
h, l = axes[0].get_legend_handles_labels()
fig.legend(h, l, fontsize=8, ncol=3, loc="lower center")
fig.tight_layout(rect=(0, 0.08, 1, 1))
fig.savefig(IMG / "result_time_cost.png", dpi=150)

# 5. where the multi-agent time goes (health questions)
steps = [("supervisor", "Supervisor"), ("make_queries", "검색어 만들기"), ("retrieve_mcp", "논문 검색 (MCP)"),
         ("pick_notes", "근거 고르기·메모"), ("writer", "답변 쓰기")]
A = RES["after"]
means = [np.mean([max([v for k, v in A[h["id"]]["timings"].items() if k == s or k.endswith("." + s)] or [0]) for h in H]) for s, _ in steps]
fig, ax = plt.subplots(figsize=(9, 2.6))
left = 0
for (s, name), m, c in zip(steps, means, ["#7a5af8", "#f79009", "#12b76a", "#2e90fa", "#ee46bc"]):
    ax.barh([0], [m], left=left, color=c, label=f"{name} {m:.1f}초")
    left += m
ax.set_yticks([])
ax.set_xlabel("초 (건강 질문 60개 평균, 식단·운동 Agent는 동시에 실행되어 더 긴 쪽만 반영)")
ax.set_title(f"Multi-Agent 응답 시간은 어디에 쓰이나 (평균 {np.mean([A[h['id']]['latency_s'] for h in H]):.1f}초)", fontsize=11)
ax.legend(fontsize=8, ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.45))
fig.tight_layout()
fig.savefig(IMG / "result_latency_breakdown.png", dpi=150)
print("charts written to", IMG)
