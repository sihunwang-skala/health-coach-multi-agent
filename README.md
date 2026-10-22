# health-coach-multi-agent

고령 2형 당뇨 사용자를 위한 **근거 기반 식단·운동 코칭 Multi-Agent** (AI 서비스 개발 Mini Project, 2026-10)

> 의료 조언이 아닙니다. 약·증상은 의사·간호사·약사에게, 응급은 119로 안내합니다. 예시 사용자 10명은 모두 가상 인물입니다.

## 결과 — 같은 입력, Before = 표준 RAG 챗봇 / After = 이 Multi-Agent

![before after](docs/img/before_after_quality.png)

| 지표 (건강 질문 38개 = 운동 24 + 식단 8 + 식단·운동 혼합 6) | Before | After |
|---|---|---|
| 답변 정확도 (꼭 답할 내용 65개, 1 / 0.5 / 0) | 0.58 | **0.85** |
| ㄴ 운동 / 식단 / 혼합 | 0.60 / 0.46 / 0.63 | 0.80 / 0.89 / **1.00** |
| 넘겨받은 근거 안의 정답 근거 문장 | 0.19 | **0.56** |
| 위험 조언이 있는 답변 (코드 규칙 S1–S9) | 11 | **0** |
| 응급 메시지 → 119 안내 (LLM 없이) | 0 / 3 | **3 / 3** (0.01초) |
| "약 건너뛰어도 돼?" 직접 변경 거절 | 1 / 2 | **2 / 2** |
| Supervisor 라우팅 정확도 (식단·운동·혼합·기록·조회·삭제·약 변경·응급·잡담) | — | **56 / 56** |
| 지연 평균 / p95 | 3.0초 / 3.9초 | 14.2초 / 16.2초 |
| 질문 1개 비용 (단일 분야 / 혼합) | $0.0003 | $0.006 / $0.013 (혼합은 두 agent **병렬**이라 지연은 같고 비용만 2배) |
| 연구가 필요 없는 메시지 11개 | — | 합계 $0.0008, 평균 1.5초 (모든 agent를 돌렸다면 $0.077) |

- 채점: Claude가 rubric으로 채점. 비교용 LLM judge(gpt-4o-mini)와 **정확 일치 76%, 0.5점 이내 98%, 상관 0.74** (judge가 평균 0.09 후하고, 같은 답을 다시 채점하면 흔들림 → 주 지표로 쓰지 않음). judge로 매겨도 Before 0.71 → After 0.91.
- **데모 영상**: [docs/demo.mp4](docs/demo.mp4) (실제 실행 녹화) · 자세한 수치·실패 사례·한계: [docs/REPORT.md](docs/REPORT.md)

![live](docs/img/live_mixed_diet_exercise.png)

## 무엇을 하나
- **Supervisor 라우팅**: 식단 / 운동 / **식단+운동** / 기록 / 내 정보 조회 / 기록 삭제 / 약 변경 질문 / 잡담 — 응급은 LLM보다 먼저 코드로 걸러 119 안내
- **Diet Agent · Exercise Agent** (각각 subgraph, 혼합 질문은 **병렬**): 검색어 4단계 → MCP 논문 검색(분야별 논문 묶음, dense + BM25) → 검색어별 근거 고르기·메모 → 메모 검증 — 당뇨 식단 RAG PoC에서 실험으로 고른 최종 모델
- **Safety Agent** (코드, 병렬): 운동 규칙 R1–R8(저혈당, 망막병증, 신경병증, 고혈압, 신장병, 낙상) + 식단 규칙 D1–D6(신장병 단백질, metformin eGFR, 끼니 거르기·음주 저혈당, 소금, 체중 감소)
- **Validate**: 위험 조언 S1–S9 검사 → 1회 재작성(60초 상한) → 남으면 해당 문장 삭제 + 규칙표 문장을 맨 앞에
- **Records Agent**: 기록 저장·조회, **삭제는 사용자 승인(Human-in-the-loop)** 후 실행
- **웹 채팅**: agent 진행 단계 실시간 표시(SSE), 출처 논문 링크, 적용된 안전 규칙, 승인 버튼

구조: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · 안전·개인정보·데이터 흐름: [docs/SAFETY_PRIVACY.md](docs/SAFETY_PRIVACY.md)

## 기술
LangGraph (supervisor + subgraph, 병렬 fan-out, 조건부 edge, interrupt/checkpointer) · LangChain LCEL (ChatOpenAI invoke/batch) · MCP (fastmcp 서버 2개: 논문 검색 / 사용자 프로필·기록) · RAG (하이브리드 검색, 대상 필터, 메모 검증) · FastAPI + SSE · 의존성 주입 (`coach/deps.py`) · LangSmith (입력·출력 숨김) · 모듈화 · 단위 테스트 14개 (FakeLLM + 가짜 MCP 서버, 네트워크 없음)

## 실행
```bash
uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env            # OPENAI_API_KEY 입력
.venv/bin/python scripts/fetch_papers.py          # 논문 86편 내려받기 (PMC 오픈액세스, 저장소에는 원문 없음)
.venv/bin/python scripts/build_index.py           # 청킹 + embedding (약 $0.02, 1회)
.venv/bin/uvicorn app.server:app --port 8000      # http://localhost:8000
.venv/bin/python scripts/record_demo.py           # (선택) 실제 실행 화면 녹화 → docs/demo.mp4, docs/img/live_*.png (약 $0.02)
.venv/bin/python -m pytest -q                     # 단위 테스트 (API 키 불필요)
.venv/bin/python eval/run_eval.py && .venv/bin/python eval/score.py && .venv/bin/python eval/charts.py   # Before / After (약 $0.2)
```

## 데이터
- 논문: `data/paper_ids.json` — 86편. Exercise Agent 묶음 = 운동 핵심 21 + 주제가 다른 운동 논문 15, Diet Agent 묶음 = 당뇨 식단 논문 50(당뇨 PoC 코퍼스, 핵심 + 방해). 원문은 라이선스 때문에 저장소에 넣지 않고 스크립트로 받는다.
- 평가셋: `eval/questions.json` — 건강 질문 38(운동 24 + 식단 8 + 혼합 6, 꼭 답할 내용 65, 정답 근거 문장 모두 코퍼스 원문 확인), 라우팅 13, 근거 없는 주제 5
- 사용자: `data/users.json` — 가상 인물 10명
