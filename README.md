# health-coach-multi-agent

제2형 당뇨병을 앓는 고령자를 위한 **논문 근거를 활용한 식단·운동 코칭 Multi-Agent** (AI 서비스 개발 Mini Project, 2026-10 · SKALA 4기 광주 3반 G088 왕시훈)

> 이 서비스는 의사가 아니라 코칭 서비스입니다. 진단·처방이 필요한 요청에는 Safety Guard를 적용해 AI가 임의로 판단하지 않도록 하고, 약 변경은 의료진에게, 응급 증상은 119로 안내합니다. 예시 사용자 10명은 모두 가상 인물입니다.

**결과 보고서: [docs/REPORT.md](docs/REPORT.md)** · [발표 화면](docs/PRESENTATION_VIEW.md) · [5분 발표 스크립트](docs/PRESENTATION_SCRIPT.md) · 전체 평가 표: [eval/results/metrics_tables.md](eval/results/metrics_tables.md) · 평가 방법: [docs/EVALUATION.md](docs/EVALUATION.md)

## 결과 — Baseline 대비 Before / After (같은 질문 100개, 4가지 시스템, GPT-6 Luna)
Baseline(Before) = Standard Paper-Search RAG · Ablation = Health Agentic RAG, Single-Agent + Health Agentic RAG · Proposed(After) = Multi-Agent + Health Agentic RAG
![four systems](docs/img/result_health_four_systems.png)

| 지표 | Standard Paper-Search RAG | Health Agentic RAG | Single-Agent + Health Agentic RAG | Multi-Agent + Health Agentic RAG |
|---|---|---|---|---|
| 건강 질문 60개 답변 점수 ¹ | 75.3% | 73.2% | 88.7% | **91.5%** |
| 본인 질문 답변 점수 | 68.2% | 69.5% | **90.9%** | 88.6% |
| 일반 질문 답변 점수 | 84.5% | 78.0% | 85.7% | **95.2%** |
| 꼭 필요한 근거를 찾아 온 비율 ² | 31.6% | 58.2% | 58.2% | **60.2%** |
| 안전 문제가 있는 답변 ³ | 8.3% | 10% | **0%** | **0%** |
| 건강 질문 평균 응답 시간 | **4.1초** | 15.1초 | 15.5초 | 18.2초 |
| 건강 질문 1개당 비용 | **$0.0002** | $0.0025 | $0.0025 | $0.0032 |

| 지표 (모든 메시지를 받는 3가지 시스템) | Standard Paper-Search RAG | Single-Agent + Health Agentic RAG | Multi-Agent + Health Agentic RAG |
|---|---|---|---|
| 건강 질문 외 메시지 40개를 제대로 처리한 비율 ⁴ | 57.5% | 35.0% | **97.5%** |
| 응급 상황 처리 | 80% | 60% | **100%** |
| 100개 평균 응답 시간 | **3.6초** | 14.0초 | 11.8초 |
| 100개 총비용 | **$0.018** | $0.218 | $0.198 |

- **본인 질문** = 본인 건강 정보 + 논문 참조 질문, **일반 질문** = 논문 참조 질문. 운동·식단·식단+운동 각각 10개씩입니다.
- ¹ 질문마다 꼭 들어가야 할 핵심 내용을 1~3개씩 정하고(60개 질문 합계 97개), Claude Opus 5.5가 답변을 읽고 항목마다 1 / 0.75 / 0.5 / 0.25 / 0점을 줘 평균을 냈습니다.
- ² 핵심 내용이 적힌 논문 원문 문장(98개)이 답변 LLM에게 넘겨진 글 안에 있는 비율. 검색 성능입니다.
- ³ 코드 규칙 9개(위험한 조언, 꼭 필요한 저혈당 경고 누락) 중 하나라도 걸린 답변 비율.
- ⁴ 내 정보·기록 질문, 잡담, 응급, 약 변경, 상담 연결·기록 삭제·다른 사람 정보·개인정보 안내 요청.
- 대가: 건강 질문 응답 시간이 4.1초에서 18.2초로 늘었습니다. 자세한 내용은 [한계와 Trade-off](docs/REPORT.md#4-한계와-trade-off), [추가 개선](docs/REPORT.md#5-추가-개선)에 정리했습니다.
- 위 수치는 2026-10-22 12:02의 마지막 100문항 전체 평가 결과입니다. 이후 추가한 한국어 번역·한 줄 요약의 시간과 비용은 전체 평가를 다시 실행한 뒤 업데이트할 예정입니다.

## 주요 기능
- **Supervisor**: 메시지마다 경로(식단 / 운동 / 식단+운동 / 기록 저장·조회 / 기록 삭제 / 약 변경 / 상담 연결 / 다른 사람 정보 / 개인정보 안내 / 잡담)를 고르고, 본인 질문과 일반 질문을 구분합니다. 응급 표현은 LLM보다 먼저 코드로 감지해 119를 안내합니다.
- **Diet Agent · Exercise Agent** (각각 subgraph, 식단+운동 질문은 동시 실행): Health Agentic RAG — 검색어 4단계 → MCP 논문 검색(의미 검색 + BM25) → 근거 선택·메모 → 메모 검증.
- **Safety Agent** (코드): 운동 규칙 R1–R8, 식단 규칙 D1–D6.
- **위험 조언 검사** (코드 S1–S9): 1회 재작성(60초 상한), 그래도 위험하면 문장 삭제 후 안전 문장 삽입.
- **Records Agent**: 기록 저장·조회, 삭제는 사용자 승인 후 실행.
- **HITL (사람이 판단하는 지점) 두 곳**: ① 사용자 — 기록 삭제 전 승인(LangGraph `interrupt()`), ② 운영자 — 응급·상담 요청 알림을 관리자 화면에서 확인하고 처리 완료로 표시.
- **사용자 화면**: 채팅 중심, Agent 진행 단계 실시간 표시, 출처 논문, 119·상담 전화 버튼, 내 정보·기록은 펼칠 때만.
- **관리자 화면**: 전체 사용자, 응급·상담 요청 알림(처리 표시), 사용자별 대화·기록·혈당 그래프, 날짜별 사용량·비용 그래프.
- **개인정보**: 이름은 AI에 보내지 않음, LangSmith에는 입력·출력 숨김, 대화 내용은 자체 모니터링 로그(90일)에만.

### Agentic RAG 처리 흐름

건강 질문은 다음 순서로 처리합니다.

`질문` → `검색 질문 만들기` → `논문 검색` → `필요한 근거 선택` → `근거 원문 확인` → `답변 작성`

- **Grounded Generation (Writer)**: 검증된 근거 메모와 Safety 규칙만 사용해 답변합니다.
- **근거가 없을 때**: 추측해서 답하지 않고, 자료가 없어 답변하기 어렵다고 안내합니다.

구조: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · 안전·개인정보·데이터 흐름: [docs/SAFETY_PRIVACY.md](docs/SAFETY_PRIVACY.md)

## 기술 구성
LangGraph (supervisor + compiled subgraph, 동시 실행, 조건부 edge, interrupt/checkpointer) · LangChain LCEL (ChatOpenAI invoke/batch) · LangSmith (입력·출력 숨김) · MCP (fastmcp 서버 2개: 논문 검색 / 사용자 프로필·기록) · RAG (하이브리드 검색, 대상 필터, 메모 검증) · FastAPI + SSE · 의존성 주입 (`coach/deps.py`) · 모듈화 · 단위 테스트 20개 (test double: FakeLLM + in-memory mock MCP 서버, 네트워크·API 키 없이 실행)

## 실행
```bash
uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env                                  # OPENAI_API_KEY 입력 (LangSmith는 선택)
.venv/bin/python scripts/fetch_papers.py              # 논문 86편 내려받기 (PMC 오픈액세스, 저장소에는 원문 없음)
.venv/bin/python scripts/build_index.py               # chunking + embedding (약 $0.02, 1회)
.venv/bin/python scripts/seed_demo_monitoring.py --users   # (선택) 관리자 화면 데모 데이터
.venv/bin/uvicorn app.server:app --port 8000          # 사용자 화면 http://localhost:8000, 관리자 화면 /admin
.venv/bin/python -m pytest -q                         # 단위 테스트 (API 키 불필요)
```
평가 다시 실행: [docs/EVALUATION.md §8](docs/EVALUATION.md#8-다시-계산하기)

## 데이터
- 논문: `data/paper_ids.json` — 86편. 운동 Agent 묶음은 핵심 운동 논문 21편 + 주제가 다른 운동 논문 15편, 식단 Agent 묶음은 당뇨 식단 논문 50편. 원문은 라이선스 때문에 저장소에 넣지 않고 스크립트로 내려받습니다.
- 평가셋: `eval/questions.json` — 100개 (건강 질문 60 + 그 외 40). 구성은 [평가 방법](docs/EVALUATION.md#2-질문-100개).
- 사용자: `data/users.json` — 65세 이상 가상 인물 10명(성별 5:5). 표는 [보고서 2-6](docs/REPORT.md#2-6-가상-사용자-10명과-평가-설계).
