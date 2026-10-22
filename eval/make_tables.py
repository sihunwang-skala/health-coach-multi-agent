"""Every number in the result tables, computed from the saved runs (eval/results/*.json) and the grades
(eval/scores_claude.json) - no number is typed by hand. Fills the {{...}} blocks of eval/tables_template.md and writes
eval/results/metrics_tables.md.
    .venv/bin/python eval/make_tables.py
"""
import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from coach.safety.rules import check_answer  # noqa: E402
from mcp_servers.user_server import profile_text  # noqa: E402

R = ROOT / "eval" / "results"
NAMES = {"before": "Standard Paper-Search RAG", "agentic_rag": "Health Agentic RAG",
         "single": "Single-Agent + Health Agentic RAG", "after": "Multi-Agent + Health Agentic RAG"}
ALL4, MSG3 = ["before", "agentic_rag", "single", "after"], ["before", "single", "after"]
DOMAIN = {"exercise": "운동", "diet": "식단", "diet_exercise": "식단+운동"}
TYPE = {"A": "본인 질문", "B": "일반 질문"}
norm = lambda s: re.sub(r"\s+", " ", s).strip()  # noqa: E731

Q = json.loads((ROOT / "eval" / "questions.json").read_text())
H, O = Q["health"], Q["routing"]
G = json.loads((ROOT / "eval" / "scores_claude.json").read_text())
RES = {s: json.loads((R / f"{s}.json").read_text()) for s in ALL4}
PROF = {u["id"]: profile_text(u) for u in json.loads((ROOT / "data" / "users.json").read_text())}


def pct(a, b, d=1):
    v = 100 * a / b
    return f"{v:.{d}f}%".replace(".0%", "%") if d else f"{v:.0f}%"


def num(x):
    return f"{x:g}"


def table(head, rows, systems):
    out = "| " + head + " | " + " | ".join(NAMES[s] for s in systems) + " |\n|" + "---|" * (len(systems) + 1) + "\n"
    return out + "".join("| " + label + " | " + " | ".join(cells) + " |\n" for label, cells in rows)


def gold_found(h, row):
    got = [norm(t) for t in row.get("passage_texts", [])]
    n = 0
    for g in h["gold"]:
        e = norm(g)
        probes = [e[:50], e[max(0, len(e) // 2 - 25): len(e) // 2 + 25], e[-50:]]
        n += any(any(p in t for p in probes) for t in got)
    return n


def pts(s, hs):
    return [v for h in hs for v in G[s][h["id"]]]


def flags(s, hs):
    out = {}
    for h in hs:
        rules = [i["rule"].split()[0] for i in check_answer(RES[s][h["id"]]["answer"], PROF[h["user"]], h["q"], {})]
        if rules:
            out[h["id"]] = rules
    return out


def bold_best(cells, values, high=True):
    best = max(values) if high else min(values)
    return [f"**{c}**" if v == best else c for c, v in zip(cells, values)]


GROUPS = [(f"{DOMAIN[d]} · {TYPE[t]}", [h for h in H if h["domain"] == d and h["type"] == t]) for d in DOMAIN for t in TYPE]
TOTALS = [(f"**{TYPE[t]} 전체**", [h for h in H if h["type"] == t]) for t in TYPE]


def score_rows(hs_list, systems):
    top, base = [], []
    for label, hs in hs_list:
        vals = [sum(pts(s, hs)) / len(pts(s, hs)) for s in systems]
        top.append((label, bold_best([pct(sum(pts(s, hs)), len(pts(s, hs))) for s in systems], vals)))
        base.append((label.replace("**", ""), [f"{num(sum(pts(s, hs)))} ÷ {len(pts(s, hs))}" for s in systems]))
    return top, base


def gold_rows(hs_list, systems):
    top, base = [], []
    for label, hs in hs_list:
        tot = sum(len(h["gold"]) for h in hs)
        found = [sum(gold_found(h, RES[s][h["id"]]) for h in hs) for s in systems]
        top.append((label, bold_best([pct(f, tot) for f in found], found)))
        base.append((label.replace("**", ""), [f"{f} ÷ {tot}" for f in found]))
    return top, base


def lat(rows):
    x = [r["latency_s"] for r in rows]
    return np.mean(x), np.median(x), np.percentile(x, 95), min(x), max(x)


def step1():
    rows, base = [], []
    vals = {s: pts(s, H) for s in ALL4}
    n = len(vals["before"])
    def line(label, f, high=True, fmt=lambda a: pct(a, n)):
        v = [f(vals[s]) for s in ALL4]
        rows.append((label, bold_best([fmt(x) for x in v], v, high)))
    line("답변 점수 ¹", sum)
    line("만점(1점)을 받은 필수 답변 항목", lambda p: sum(x == 1 for x in p))
    line("일부만 답한(0.25~0.75점) 필수 답변 항목", lambda p: sum(0 < x < 1 for x in p), high=False)
    line("빠졌거나 틀린(0점) 필수 답변 항목", lambda p: sum(x == 0 for x in p), high=False)
    fl = {s: flags(s, H) for s in ALL4}
    sp = [len(fl[s]) for s in ALL4]
    rows.append(("안전 문제가 있는 답변 ³", bold_best([pct(x, len(H)) for x in sp], sp, high=False)))
    da = [sum(any(r != "S5" for r in v) for v in fl[s].values()) for s in ALL4]
    mw = [sum(all(r == "S5" for r in v) for v in fl[s].values()) for s in ALL4]
    rows.append(("　└ 위험한 조언을 한 답변", bold_best([pct(x, len(H)) for x in da], da, high=False)))
    rows.append(("　└ 꼭 필요한 저혈당 경고가 빠진 답변", bold_best([pct(x, len(H)) for x in mw], mw, high=False)))
    base = [("답변 점수 = 받은 점수 합 ÷ 필수 답변 항목", [f"{num(sum(vals[s]))} ÷ {n}" for s in ALL4]),
            ("만점(1점) 항목", [f"{sum(x == 1 for x in vals[s])} ÷ {n}" for s in ALL4]),
            ("일부만 답한 항목", [f"{sum(0 < x < 1 for x in vals[s])} ÷ {n}" for s in ALL4]),
            ("빠졌거나 틀린 항목", [f"{sum(x == 0 for x in vals[s])} ÷ {n}" for s in ALL4]),
            ("안전 문제가 있는 답변", [f"{x} ÷ {len(H)}" for x in sp]),
            ("　└ 위험한 조언", [f"{x} ÷ {len(H)}" for x in da]),
            ("　└ 저혈당 경고 누락", [f"{x} ÷ {len(H)}" for x in mw])]
    out = table("지표", rows, ALL4) + "\n계산 근거:\n" + table("항목", base, ALL4)
    which = {s: ", ".join(f"{k}({'·'.join(sorted(set(v)))})" for k, v in fl[s].items()) or "없음" for s in ALL4}
    out += "\n안전 문제가 걸린 질문:\n| 시스템 | 질문 (걸린 규칙) |\n|---|---|\n" + "".join(f"| {NAMES[s]} | {which[s]} |\n" for s in ALL4)
    return out


def step2():
    top, base = score_rows(GROUPS + TOTALS, ALL4)
    return table("질문 종류", top, ALL4) + "\n계산 근거 (받은 점수 합 ÷ 필수 답변 항목 수; 질문 종류마다 질문 10개, 전체는 30개):\n" + table("질문 종류", base, ALL4)


def step3():
    top, base = gold_rows(GROUPS + TOTALS + [("**전체**", H)], ALL4)
    return table("질문 종류", top, ALL4) + "\n계산 근거 (찾아 온 정답 근거 문장 ÷ 정답 근거 문장 수):\n" + table("질문 종류", base, ALL4)


def step4():
    rows = []
    L = {s: lat([RES[s][h["id"]] for h in H]) for s in ALL4}
    rows.append(("평균 응답 시간", bold_best([f"{L[s][0]:.1f}초" for s in ALL4], [L[s][0] for s in ALL4], high=False)))
    rows.append(("가운데 값 응답 시간 (중앙값)", bold_best([f"{L[s][1]:.1f}초" for s in ALL4], [L[s][1] for s in ALL4], high=False)))
    rows.append(("느린 쪽 5% 기준 응답 시간 ⁵", bold_best([f"{L[s][2]:.1f}초" for s in ALL4], [L[s][2] for s in ALL4], high=False)))
    rows.append(("가장 빠른 응답", bold_best([f"{L[s][3]:.1f}초" for s in ALL4], [L[s][3] for s in ALL4], high=False)))
    rows.append(("가장 느린 응답", bold_best([f"{L[s][4]:.1f}초" for s in ALL4], [L[s][4] for s in ALL4], high=False)))
    c = [np.mean([RES[s][h["id"]]["cost"] for h in H]) for s in ALL4]
    rows.append(("질문 1개당 비용 ⁶", bold_best([f"${x:.4f}" for x in c], c, high=False)))
    k = [np.mean([RES[s][h["id"]]["calls"] for h in H]) for s in ALL4]
    rows.append(("질문 1개당 LLM 호출 수", bold_best([f"{x:.1f}회" for x in k], k, high=False)))
    out = table("지표", rows, ALL4)
    tok = [("질문 1개당 입력 token", [f"약 {np.mean([RES[s][h['id']].get('tokens_in', 0) for h in H]):,.0f}" for s in MSG3]),
           ("질문 1개당 출력 token", [f"약 {np.mean([RES[s][h['id']].get('tokens_out', 0) for h in H]):,.0f}" for s in MSG3])]
    out += "\ntoken 사용량 (Health Agentic RAG는 Single-Agent의 검색 결과로 답변만 다시 쓴 비교용이라 token을 따로 재지 않아 제외):\n" + table("지표", tok, MSG3)
    saf = [("위험한 조언이 있어 답변을 다시 쓴 횟수 (60개 합계)", [f"{sum(RES[s][h['id']].get('retries', 0) for h in H)}회" for s in ("single", "after")]),
           ("다시 써도 위험해서 지운 문장 수 (60개 합계)", [f"{sum(len(RES[s][h['id']].get('removed', [])) for h in H)}개" for s in ("single", "after")])]
    out += "\n안전 검사 동작 (안전 검사가 있는 2가지 시스템):\n" + table("지표", saf, ["single", "after"])
    tl = [(lbl, [f"{np.mean([RES[s][h['id']]['latency_s'] for h in hs]):.1f}초" for s in ALL4]) for lbl, hs in GROUPS]
    out += "\n질문 종류별 평균 응답 시간:\n" + table("질문 종류", tl, ALL4)
    tc = [(lbl, [f"${np.mean([RES[s][h['id']]['cost'] for h in hs]):.4f}" for s in ALL4]) for lbl, hs in GROUPS]
    out += "\n질문 종류별 질문 1개당 비용:\n" + table("질문 종류", tc, ALL4)
    return out


OGROUPS = [("내 정보·기록 질문", lambda x: x["group"].startswith("C")), ("잡담", lambda x: x["group"].startswith("D")),
           ("응급 상황", lambda x: x["route"] == "emergency"), ("스스로 약을 바꾸려는 질문", lambda x: x["route"] == "med_change"),
           ("상담 연결·기록 삭제·다른 사람 정보·개인정보 안내 요청", lambda x: x["group"] == "service and privacy")]


def step5():
    hd = G["handled"]
    top, base = [], []
    for lbl, f in OGROUPS + [("**전체 ⁴**", lambda x: True)]:
        xs = [x for x in O if f(x)]
        ok = [sum(hd[s][x["id"]] for x in xs) for s in MSG3]
        top.append((lbl, bold_best([pct(o, len(xs), 0) if len(xs) == 10 else pct(o, len(xs)) for o in ok], ok)))
        base.append((lbl.replace("**", "").replace(" ⁴", ""), [f"{o} ÷ {len(xs)}" for o in ok]))
    out = table("메시지 묶음", top, MSG3) + "\n계산 근거 (제대로 처리한 메시지 ÷ 메시지 수):\n" + table("메시지 묶음", base, MSG3)
    rows = [(lbl, [f"{np.mean([RES[s][x['id']]['latency_s'] for x in O if f(x)]):.1f}초" for s in MSG3]) for lbl, f in OGROUPS]
    out += "\n메시지 묶음별 평균 응답 시간:\n" + table("메시지 묶음", rows, MSG3)
    rows = [(lbl, [f"${sum(RES[s][x['id']]['cost'] for x in O if f(x)):.4f}" for s in MSG3]) for lbl, f in OGROUPS]
    out += "\n메시지 묶음별 합계 비용:\n" + table("메시지 묶음", rows, MSG3)
    L = {s: lat([RES[s][x["id"]] for x in O]) for s in MSG3}
    rows = [("평균 응답 시간", bold_best([f"{L[s][0]:.1f}초" for s in MSG3], [L[s][0] for s in MSG3], high=False)),
            ("느린 쪽 5% 기준 응답 시간 ⁵", bold_best([f"{L[s][2]:.1f}초" for s in MSG3], [L[s][2] for s in MSG3], high=False)),
            ("메시지 1개당 비용 ⁶", bold_best([f"${np.mean([RES[s][x['id']]['cost'] for x in O]):.5f}" for s in MSG3],
                                         [np.mean([RES[s][x['id']]['cost'] for x in O]) for s in MSG3], high=False)),
            ("메시지 1개당 LLM 호출 수", [f"{np.mean([RES[s][x['id']]['calls'] for x in O]):.1f}회" for s in MSG3]),
            ("메시지 1개당 token", [f"약 {np.mean([RES[s][x['id']].get('tokens_in', 0) + RES[s][x['id']].get('tokens_out', 0) for x in O]):,.0f}" for s in MSG3])]
    out += "\n40개 전체의 응답 시간·비용·자원:\n" + table("지표", rows, MSG3)
    A = RES["after"]
    exp = {x["id"]: x["route"] for x in O}
    exp_all = exp | {h["id"]: h["domain"] for h in H}
    ok40 = sum(A[k]["route"] == v for k, v in exp.items())
    ok100 = sum(A[k]["route"] == v for k, v in exp_all.items())
    split = sum(A[h["id"]].get("about_user") == (h["type"] == "A") for h in H)
    out += ("\nMulti-Agent의 경로 선택 정확도:\n| 항목 | 정확도 | 계산 근거 |\n|---|---|---|\n"
            f"| Supervisor 경로 선택 (건강 질문 외 40개) | {pct(ok40, 40, 0)} | {ok40} ÷ 40 |\n"
            f"| Supervisor 경로 선택 (100개 전체) | {pct(ok100, 100, 0)} | {ok100} ÷ 100 |\n"
            f"| 본인 질문·일반 질문 구분 (건강 질문 60개) | {pct(split, 60, 0)} | {split} ÷ 60 |\n")
    return out


def final():
    out = "### 8-1. 건강 질문 60개 (4가지 시스템 모두에 있는 지표)\n"
    v = {s: pts(s, H) for s in ALL4}
    n = len(v["before"])
    fl = {s: flags(s, H) for s in ALL4}
    L = {s: lat([RES[s][h["id"]] for h in H]) for s in ALL4}
    A = [h for h in H if h["type"] == "A"]
    B = [h for h in H if h["type"] == "B"]
    tg = sum(len(h["gold"]) for h in H)
    gf = {s: sum(gold_found(h, RES[s][h["id"]]) for h in H) for s in ALL4}
    def row(label, vals, fmt, high=True):
        return (label, bold_best([fmt(x) for x in vals], vals, high))
    rows = [row("답변 점수 ¹", [sum(v[s]) / n for s in ALL4], lambda x: f"{100 * x:.1f}%"),
            row("본인 질문 답변 점수", [sum(pts(s, A)) / len(pts(s, A)) for s in ALL4], lambda x: f"{100 * x:.1f}%"),
            row("일반 질문 답변 점수", [sum(pts(s, B)) / len(pts(s, B)) for s in ALL4], lambda x: f"{100 * x:.1f}%"),
            row("만점(1점)을 받은 필수 답변 항목", [sum(x == 1 for x in v[s]) / n for s in ALL4], lambda x: f"{100 * x:.1f}%"),
            row("빠졌거나 틀린(0점) 필수 답변 항목", [sum(x == 0 for x in v[s]) / n for s in ALL4], lambda x: f"{100 * x:.1f}%", False),
            row("꼭 필요한 근거를 찾아 온 비율 ²", [gf[s] / tg for s in ALL4], lambda x: f"{100 * x:.1f}%"),
            row("안전 문제가 있는 답변 ³", [len(fl[s]) / len(H) for s in ALL4], lambda x: f"{100 * x:.1f}%".replace(".0%", "%"), False),
            row("평균 응답 시간", [L[s][0] for s in ALL4], lambda x: f"{x:.1f}초", False),
            row("느린 쪽 5% 기준 응답 시간 ⁵", [L[s][2] for s in ALL4], lambda x: f"{x:.1f}초", False),
            row("질문 1개당 비용 ⁶", [np.mean([RES[s][h["id"]]["cost"] for h in H]) for s in ALL4], lambda x: f"${x:.4f}", False),
            row("질문 1개당 LLM 호출 수", [np.mean([RES[s][h["id"]]["calls"] for h in H]) for s in ALL4], lambda x: f"{x:.1f}회", False)]
    out += table("지표", rows, ALL4)
    base = [("답변 점수", [f"{num(sum(v[s]))} ÷ {n}" for s in ALL4]),
            ("본인 질문 답변 점수", [f"{num(sum(pts(s, A)))} ÷ {len(pts(s, A))}" for s in ALL4]),
            ("일반 질문 답변 점수", [f"{num(sum(pts(s, B)))} ÷ {len(pts(s, B))}" for s in ALL4]),
            ("만점 항목", [f"{sum(x == 1 for x in v[s])} ÷ {n}" for s in ALL4]),
            ("0점 항목", [f"{sum(x == 0 for x in v[s])} ÷ {n}" for s in ALL4]),
            ("근거 비율", [f"{gf[s]} ÷ {tg}" for s in ALL4]),
            ("안전 문제 답변", [f"{len(fl[s])} ÷ {len(H)}" for s in ALL4])]
    out += "\n계산 근거:\n" + table("항목", base, ALL4)
    out += "\n### 8-2. 메시지 100개 전체 (모든 메시지를 받는 3가지 시스템에 있는 지표)\nHealth Agentic RAG는 건강 질문 60개에만 쓰는 비교용이라 이 표에서 뺐습니다.\n"
    hd = G["handled"]
    em = [x for x in O if x["route"] == "emergency"]
    md = [x for x in O if x["route"] == "med_change"]
    allrows = {s: list(RES[s].values()) for s in MSG3}
    LA = {s: lat(allrows[s]) for s in MSG3}
    LO = {s: lat([RES[s][x["id"]] for x in O]) for s in MSG3}
    rows = [row("건강 질문 답변 점수 ¹", [sum(v[s]) / n for s in MSG3], lambda x: f"{100 * x:.1f}%"),
            row("안전 문제가 있는 답변 ³", [len(fl[s]) / len(H) for s in MSG3], lambda x: f"{100 * x:.1f}%".replace(".0%", "%"), False),
            row("건강 질문 외 메시지를 제대로 처리한 비율 ⁴", [sum(hd[s][x["id"]] for x in O) / len(O) for s in MSG3], lambda x: f"{100 * x:.1f}%"),
            row("응급 상황 처리", [sum(hd[s][x["id"]] for x in em) / len(em) for s in MSG3], lambda x: f"{100 * x:.0f}%"),
            row("스스로 약을 바꾸려는 질문 거절", [sum(hd[s][x["id"]] for x in md) / len(md) for s in MSG3], lambda x: f"{100 * x:.0f}%"),
            row("평균 응답 시간 (100개)", [LA[s][0] for s in MSG3], lambda x: f"{x:.1f}초", False),
            row("느린 쪽 5% 기준 응답 시간 (100개) ⁵", [LA[s][2] for s in MSG3], lambda x: f"{x:.1f}초", False),
            row("건강 질문 외 메시지 평균 응답 시간", [LO[s][0] for s in MSG3], lambda x: f"{x:.1f}초", False),
            row("총비용 (100개) ⁶", [sum(r["cost"] for r in allrows[s]) for s in MSG3], lambda x: f"${x:.3f}", False),
            row("LLM 호출 합계 (100개)", [sum(r["calls"] for r in allrows[s]) for s in MSG3], lambda x: f"{x:,}회", False),
            row("token 합계 (100개)", [sum(r.get("tokens_in", 0) + r.get("tokens_out", 0) for r in allrows[s]) for s in MSG3],
                lambda x: f"약 {x / 1e4:.0f}만", False)]
    out += table("지표", rows, MSG3)
    base = [("건강 질문 답변 점수", [f"{num(sum(v[s]))} ÷ {n}" for s in MSG3]),
            ("안전 문제 답변", [f"{len(fl[s])} ÷ {len(H)}" for s in MSG3]),
            ("제대로 처리한 메시지", [f"{sum(hd[s][x['id']] for x in O)} ÷ {len(O)}" for s in MSG3]),
            ("응급 상황 처리", [f"{sum(hd[s][x['id']] for x in em)} ÷ {len(em)}" for s in MSG3]),
            ("약 변경 거절", [f"{sum(hd[s][x['id']] for x in md)} ÷ {len(md)}" for s in MSG3])]
    out += "\n계산 근거:\n" + table("항목", base, MSG3)
    return out


def main():
    t = (ROOT / "eval" / "tables_template.md").read_text()
    for key, fn in {"STEP1": step1, "STEP2": step2, "STEP3": step3, "STEP4": step4, "STEP5": step5, "FINAL": final}.items():
        t = t.replace("{{" + key + "}}", fn().rstrip())
    (R / "metrics_tables.md").write_text(t)
    print("written", R / "metrics_tables.md")


if __name__ == "__main__":
    main()
