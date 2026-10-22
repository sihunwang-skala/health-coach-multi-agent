# AGENTS.md — handoff for coding agents (Codex, Claude, …)

Read this first. It says what this repo is, where everything is, how to run and measure it, and the rules the owner works by.

## 1. What this is
AI Service Mini Project (SKALA 4기 광주 3반 왕시훈), assignment option 2 (new agent): **diet + exercise coaching multi-agent for
older adults with type 2 diabetes**, with a Before (standard RAG chatbot) / After (this multi-agent) comparison on the same
inputs. Deliverables: working code, `README.md` (results table + how to run), `docs/REPORT.md` (the assignment report),
screenshots + demo video, and the presentation (not made yet).

- GitHub (PUBLIC): https://github.com/sihunwang-skala/health-coach-multi-agent — branch `main`
- Local: `/Users/gplace/capstone_health_agent`
- Sister repo (PRIVATE, local only, never push): `/Users/gplace/health_rag_agent` — the diabetes-diet RAG research (≈130
  recorded experiments) whose final model is reused here as the Diet / Exercise agents. See its `AGENTS.md`.
- Everything here is written for this project (the course "Base" code `/Users/gplace/all_total_vue_student` was NOT copied:
  its cover says redistribution is prohibited). All users are synthetic.

## 2. Architecture (details: `docs/ARCHITECTURE.md`)
```
guard (emergency regex, no LLM) ─┬─ emergency_reply (119 text)
                                 └─ supervisor (LLM router: diet / exercise / diet_exercise / my_data / log / delete_record / med_change / chat)
   diet | exercise | diet_exercise → [Diet Agent ‖ Exercise Agent (compiled subgraphs, as needed) ‖ Safety Agent (rule table, code)]
                                   → writer (LLM) → validate (dangerous-advice rules S1–S9) ─┬─ done
                                                                                             ├─ retry (max 1, 60 s budget) → writer
                                                                                             └─ remove_unsafe (+ rule text first)
   med_change → fixed safety reply · log / my_data / chat → records agent · delete_record → interrupt() (human approval)
```
| Path | Role |
|---|---|
| `coach/graph.py` | supervisor graph assembly (parallel fan-out, joins, HITL checkpointer) |
| `coach/agents/evidence.py` | Diet/Exercise agent subgraph: query chain (4 LLM calls) → MCP search → per-query picker (LCEL batch) → note check; `evidence_node(domain)` |
| `coach/agents/{supervisor,safety_agent,writer,records}.py` | other agents |
| `coach/agents/prompts.py` | all prompts (owner rule: each prompt states the GOAL and the TASK concretely) |
| `coach/safety/rules.py` | emergency patterns, rule table R1–R8 (exercise) + D1–D6 (diet), dangerous-advice checks S1–S9 |
| `coach/retrieval/` | PMC XML parser (tables linearised), chunking (parent 800 / child 300), hybrid index (OpenAI embedding + BM25, RRF 0.5, population filter, per-domain paper collections) |
| `coach/deps.py`, `coach/llm.py` | dependency injection container; LLM interface (OpenAI via LangChain LCEL / FakeLLM) + token & cost accounting |
| `coach/runner.py` | `run_after` (graph) and `run_before` (standard RAG) with latency / calls / cost |
| `mcp_servers/papers_server.py`, `user_server.py` | the 2 MCP servers (fastmcp; in-process or stdio). User profile is masked (no name) |
| `app/server.py`, `web/index.html` | FastAPI: `/chat`, `/chat/stream` (SSE), `/approve`, `/replay/{id}`; web chat |
| `eval/` | `questions.json` (set), `run_eval.py`, `score.py`, `judge_llm.py`, `charts.py`, `scores_claude.json` (grades), `results/` |
| `scripts/` | `fetch_papers.py`, `build_index.py`, `record_demo.py` (Playwright + system ffmpeg), `search_pmc.py` |
| `tests/` | 14 unit tests, no network (FakeLLM + fake MCP servers) |
| `docs/` | `REPORT.md`, `ARCHITECTURE.md`, `SAFETY_PRIVACY.md` (data-flow table, review responses), `img/`, `demo.mp4` |

## 3. Run
```bash
uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python -r requirements.txt
# .env (git-ignored): OPENAI_API_KEY=...  (on this machine it already exists; never print or commit it)
.venv/bin/python scripts/fetch_papers.py      # papers → data/papers (git-ignored); --local DIR reuses XML on disk
.venv/bin/python scripts/build_index.py       # embeddings cached in cache/ (≈ $0.024 once)
.venv/bin/uvicorn app.server:app --port 8000  # web UI http://localhost:8000 (index is preloaded at startup)
.venv/bin/python -m pytest -q                 # 14 tests, free
.venv/bin/python eval/run_eval.py [--only after|before] [--ids A,B]   # PAID; skips ids already in eval/results/*.json
.venv/bin/python eval/score.py && .venv/bin/python eval/charts.py     # free
.venv/bin/python scripts/record_demo.py [--only live_xxx]             # PAID (~$0.015 per run; --only = screenshots only)
```

## 4. Current results (eval/results/summary.json) and how to read them
38 health questions (exercise 24 + diet 8 + mixed 6; 65 must-answer points), 13 routing, 5 no-evidence topics:
answer score 0.58 → **0.85** (exercise 0.60 → 0.80, diet 0.46 → 0.89, mixed 0.63 → 1.00), gold evidence in context
0.19 → 0.56, dangerous answers 11 → 0, emergency → 119: 0/3 → 3/3, med-change refused 1/2 → 2/2, routing 56/56,
latency 3.0 s → 14.2 s, cost $0.0003 → $0.006 (mixed $0.013; diet and exercise agents run in parallel).
- **Grader**: answer points graded by Claude (`eval/scores_claude.json`, 1 / 0.5 / 0; golden evidence is ONE example, not
  required wording). gpt-4o-mini judge agreement 76 % exact, r 0.74, and it drifts between runs → not the main metric.
- **Caveats (keep them in the report)**: the 24 exercise + 18 routing/no-evidence items were measured BEFORE the Diet Agent
  existed (results reused to save cost); diet + mixed 14 items after. The paper index was rebuilt afterwards (parser fix),
  so for the old 24 exercise items `score.py` uses the frozen gold counts in `eval/results/v1_exercise_only/summary.json`
  (old passage ids no longer match). New results store `passage_texts`, so this does not repeat.
- To add an item: append it to `eval/questions.json` (gold = verbatim corpus sentences, check they are found), run
  `run_eval.py --ids NEW`, grade it in `eval/scores_claude.json`, then `score.py`, `charts.py`, update README / REPORT.

## 5. Open items (next)
1. `docs/REPORT.md` first line: presentation **number** is blank (the owner must give it).
2. `docs/demo.mp4` has the 6 exercise scenes only (recorded before the Diet Agent); a mixed diet+exercise screenshot exists
   (`docs/img/live_mixed_diet_exercise.png`). Re-record with `scripts/record_demo.py` only if needed (~$0.04).
3. Presentation slides (not started): use README table, `docs/img/*`, REPORT §5 limitations.
4. Known limitations (REPORT §5): latency (query chain 4 serial calls ≈ 6 s), only 1/5 clean refusals + 1 over-warning
   (golf), picker misses some gold passages, single grader, small set.
5. Optional: SSE heartbeat; multi-turn memory (profile is re-read each turn by design); LangSmith run screenshots need a key.

## 6. Owner's working rules (follow them)
- Reply to the owner in **Korean**, technical terms in English (RAG, retrieval, chunk, …). Use readable names (Maria, "diet
  agent", "standard RAG") not codes.
- **Cost**: gpt-4o-mini / text-embedding-3-small only. Use the cheapest design, reuse caches/results, test changes on a few
  **representative examples** (failing cases + a few controls), adopt a change only if nothing degrades. Don't ask before
  small runs; stop and report before a sudden large spend. Total API spend since the current key ≈ **$1.45**; stop near $10.
- Never commit `.env`, `data/coach.db`, `data/papers/`, `data/raw/`, `cache/`. Run a secret scan before pushing (this repo is public).
- No hard-coded caps on agent-decided counts (number of queries/pieces is the LLM's decision).
- Safety first: dangerous advice is blocked (never "approved" by the user); HITL only for data operations.
- Record what you change and why (here: README/REPORT; research decisions go to the sister repo's decision log).
