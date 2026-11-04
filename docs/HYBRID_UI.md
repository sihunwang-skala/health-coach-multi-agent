# Hybrid 한국어 UI 고도화 (feature/hybrid-korean-ui)

2026-10-31 작업 기록. **이 문서는 구현한 것, 검증한 것, 아직 검증하지 못한 것을 따로 적습니다.** 2026-10-22 평가 결과(README, `eval/results/`)는 이 작업으로 바뀌지 않았고, 아래 변경에는 새 평가 점수가 없습니다.

## 1. 구분 표
| 구분 | 내용 | 상태 |
|---|---|---|
| 2026-10-22 평가 결과 | 100문항, 4개 시스템, `eval/results/*.json` | 그대로 보존. 이 작업의 결과가 아님 |
| 실제 구현 (코드) | 한국어 응급 표현, 한국어 고정 답변, 번역 1단계, 인용 contract, `health_simple`/`health_deep`, SSE `route`/`error`, 한국어 PWA 화면 | 구현 + 단위 테스트 26개(무료) 통과 |
| 실제 실행 화면 | `docs/ui/screenshots/` (Chrome으로 실제 페이지를 캡처) | 답변 화면은 **기록된 평가 답변을 다시 보여 준 것**(`/replay`), 응급 화면은 실제 코드 경로 |
| 번역 이미지 | 이전 ChatGPT 작업의 한국어 번역 이미지 | 이 저장소에 없음. 실제 실행 화면이 아님 |
| 미검증 | 한국어 질문의 검색 품질, 번역 품질, `health_simple`의 답변 품질/비용/시간 | **API key 인증 실패(401)로 실행하지 못함** (§6) |

## 2. 구조 선택: 정적 HTML 유지
- 선택: `web/index.html`을 다시 쓰되 빌드 단계 없는 정적 HTML + FastAPI 제공을 유지. React/Vite로 바꾸지 않았습니다.
- 이유: 화면이 한 페이지 + 관리자 한 페이지이고, 상태가 대화 목록과 패널 정도입니다. 빌드 도구를 넣으면 실행 방법(`uvicorn` 한 줄)과 공개 저장소의 단순함이 깨집니다.
- 대가: 컴포넌트 재사용과 타입 검사가 없습니다. 화면이 3개 이상으로 늘면 그때 Vite로 옮기는 것이 맞습니다.
- 반응형 PWA 하나로 desktop/tablet/mobile을 처리합니다. Capacitor wrapper는 **만들지 않았습니다**(PWA 설치 조건을 확인한 뒤의 단계이고, 시간/검증이 필요해 다음 우선순위로 넘김).

## 3. 인용 contract (`coach/citations.py`)
`/chat/stream`의 `done` event에 `statements`, `citations`를 **추가**했습니다. 기존 `sources`(PMC id 목록)는 그대로 있어 이전 화면과 호환됩니다.
```json
{"statements":[{"statement_id":"s1","text":"...","citation_ids":[1,2]}],
 "citations":[{"citation_id":1,"document_id":"PMC6190726","title":"...","authors_year":null,"url":"https://pmc.ncbi.nlm.nih.gov/articles/PMC6190726/",
   "chunk_id":2271,"section":"Abstract","source_text":"...","support_sentences":["..."],"notes":["..."],
   "translated_text":null,"document_version":"PMC open-access full text (scripts/fetch_papers.py)","location":null}]}
```
- `source_text` = picker가 고른 조각(parent chunk). `support_sentences` = 그 조각 안에서 근거 메모와 단어가 가장 많이 겹치는 문장(코드 계산, LLM 없음). **직접 뒷받침한다는 보장이 아니라 단어 겹침 기준의 근사**입니다.
- `authors_year`는 저장된 논문 데이터에 없어 `null`. 화면에 "정보 없음"으로 표시합니다.
- `location`(HTML anchor/offset, PDF page/bbox)은 인덱스에 없어 항상 `null`. 화면은 "원문에서 위치 보기"를 **만들지 않고** 링크와 발췌만 보여 줍니다. 위치 이동은 구현하지 않았습니다.
- `translated_text`는 `null`: 논문 원문의 한국어 번역은 제공하지 않습니다. 한국어는 답변 문장에만 있고, 논문 원문은 영어로 구분해 표시합니다.
- 알려진 한계: 논문 원문에 문장 사이 공백이 빠진 곳(예: `40%.ResultsPost-dinner`)이 있어 강조 문장이 길게 잡히는 경우가 있습니다.

## 4. 건강 질문 경량/심층 경로
- `COACH_HEALTH_LITE=1`일 때만 켜집니다. **기본은 꺼짐**이라 평가된 서비스와 동작이 같습니다.
- 결정 순서: (1) 응급 코드 검사와 supervisor 경로는 그대로 먼저 적용 (2) 건강 route(diet/exercise/diet_exercise)에서 `health_path()`:
  **저장된 프로필에 안전 규칙이 걸리면(인슐린, 망막병증, 신장질환 등) → deep**(이용자가 병을 직접 쓰지 않아도 적용) / 식단+운동 → deep / 본인 질문(`about_user`) → deep / 약/저혈당/합병증/음주 단어 포함 → deep / 그 외 → simple. **질문 길이는 쓰지 않습니다.**
- `health_simple`: 검색어 만들기를 LLM 1번(4번 대신)으로 줄이고, 나머지(검색, 근거 선택, 근거 확인, 작성, 위험 조언 검사)는 deep과 같습니다. 근거 없는 일반 답변은 허용하지 않습니다.
- escalation: 검증된 근거 메모가 하나도 없으면 같은 질문을 deep 경로로 다시 실행하고 `escalated=true`로 표시합니다(trace에 `escalate`).
- **검증 범위**: 단위 테스트로 "simple이 deep보다 LLM 호출이 적다", "근거 없으면 escalate", "본인 질문은 simple을 타지 않는다"를 확인했습니다. 실제 질문에서의 답변 품질/시간/비용은 **측정하지 못했습니다**. 하나뿐인 simple 질문의 검색어(4개 → 2개)가 줄어 근거 적중률이 떨어질 수 있어, 측정 전에는 기본값을 켜지 않습니다.

## 5. SSE event (`GET /chat/stream?user_id=&message=&lang=ko|en`)
| event | 내용 |
|---|---|
| `{"event":"route","route","path","path_reason"}` | route가 정해졌을 때 1번 |
| `{"step","seconds","route"}` | 노드 하나가 끝날 때마다 (기존과 같음) |
| `{"done":true,"answer","answer_en","lang","route","path","escalated","interrupt","thread_id","sources","statements","citations","safety_notes","answer_ready_s","latency_s","calls","cost"}` | 끝. **답변 전체를 한 번에** 보냄 |
| `{"event":"error","error":"<예외 이름>"}` | 실행 실패. 화면은 "다시 시도" 버튼을 보여 줌 |
- 이것은 **token streaming이 아닙니다.** 본문 streaming은 만들지 않았습니다. 검증이 끝난 답변만 이용자에게 보여 주기 위한 선택입니다(작성 중인 답변은 위험 조언 검사 전이라 보여 주면 안 됨).
- `answer_ready_s` = 영어 답변이 검사까지 끝난 시각. 첫 "의미 있는 content" 시간은 진행 단계 chip이 아니라 이 값과 `latency_s`(번역 포함)의 차이로 구분해 기록합니다.
- 자동 재연결 없음: EventSource가 재연결하면 같은 질문의 유료 파이프라인이 다시 돕니다. 화면은 오류 시 연결을 닫고 이용자가 누르는 "다시 시도"만 제공합니다.

## 6. 한국어 처리와 알려진 한계
- 응급 표현: 한국어 패턴을 코드에 추가(가슴 조임, 숨 막힘, 기절, 정신 혼미, 떨림+어지러움, 혈당 10~53). 단위 테스트 + 화면에서 확인(LLM 호출 0).
- 고정 답변(응급, 약 변경, 상담, 다른 사람 정보, 개인정보, 삭제 확인)은 **검토한 한국어 문구**를 씁니다(LLM 없음).
- LLM 답변: 영어로 검색/작성/위험 조언 검사(S1–S9)를 끝낸 뒤 번역 1번(`translate_ko`). 번역에서 `[PMC…]` 표시가 빠지거나 바뀌면 영어 답변을 그대로 보여 줍니다. **번역된 한국어 문장은 S1–S9 규칙(영어)으로 다시 검사하지 않습니다.**
- 한국어로 입력한 질문은 원문 그대로도 검색어 1개로 쓰입니다(영어 논문에 대한 의미 검색). 한국어 질문의 검색 품질은 측정하지 못했습니다.
- **API key 인증 실패**: 이 컴퓨터의 환경변수 key와 `.env` key 모두 `OpenAIAuthenticationError`(401). 그래서 이번 작업에서 실제 LLM 호출, 한국어 답변 번역, `health_simple` 실측, 100문항 regression을 실행하지 못했습니다. 새 key를 `.env`에 넣은 뒤 `eval/run_hybrid_sample.py --run`(약 $0.08 이하)으로 먼저 확인하세요.

## 7. 테스트 (모두 무료, 네트워크/key 불필요)
- `pytest`: 26개 통과 (기존 18 + `tests/test_hybrid.py` 8). README의 "20개"는 실제 18개였음.
- PWA: Chrome(Playwright)에서 service worker active, 캐시 항목은 화면 파일 4개(`/`, 아이콘 2, manifest)뿐, API/chat/admin은 캐시되지 않음. 설치 가능성 검사의 유일한 오류는 `in-incognito`(headless 새 profile 때문), manifest 오류 없음. 실제 "설치" 버튼 동작은 확인하지 않았습니다.
- 접근성: axe-core(wcag2a, wcag2aa) 자동 검사 위반 0건(이용자 3개 viewport + 관리자). 자동 검사는 일부만 잡으므로 스크린 리더로 직접 확인하지 않았습니다.
- 반응형: 360 / 768 / 1280px에서 가로 스크롤 없음. 근거 패널은 900px 이하에서 bottom sheet.
- 삭제 승인 dialog: 화면 상태만 확인(샘플 질문을 넣어 열어 봄). 실제 삭제 흐름(supervisor → `interrupt()` → 승인)은 기존 단위 테스트가 확인하지만 LLM이 필요한 end-to-end는 실행하지 못했습니다.
- SSE 오류 처리: 인증 실패가 `error` event로 전달되고 화면에 "다시 시도"가 뜨는 것을 실제로 확인했습니다.
- 언어 전환(한국어/English)과 글자 크기: 코드로 구현, 자동 테스트는 없음.

## 8. 실행
```bash
.venv/bin/uvicorn app.server:app --port 8000        # http://localhost:8000 (관리자 /admin)
COACH_HEALTH_LITE=1 .venv/bin/uvicorn app.server:app --port 8000   # 경량 경로 켜기 (실측 전에는 권장하지 않음)
.venv/bin/python scripts/ui_screenshots.py          # screenshot + 접근성 검사 ($0, 응급 화면 때문에 로그 1줄이 추가됨)
.venv/bin/python eval/run_hybrid_sample.py          # 계획만 출력. --run 이면 유료
```
