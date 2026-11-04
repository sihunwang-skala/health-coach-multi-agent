# Router-lite experiment (English, 30 messages, one run each) — 2026-11-01

Status: **measurement only.** The production supervisor prompt (`coach/agents/prompts.py`) is NOT changed. Not the production
model: a Haiku model played the router (via sub-agent; the Haiku CLI login had expired), so this says how the prompt reads, not
how `gpt-6-luna` performs. Nothing in `eval/results/` (2026-10-22) was touched. Final check on `gpt-6-luna` with the same set
is planned after a new API key exists.

Files: `eval/router_lite/items.json` (30 messages, 10 personal / 8 general / 5 ambiguous / 7 fast path), `prompt.txt` (short
JSON router prompt), `run_router_lite.py` (prompt builder + scorer, deterministic code layer), `answers_*.json` (raw router
answers), `scores.json`.

Code layer (before/after the router): emergency regex → fixed reply; question-side "skip/stop/halve my medicine" regex → fixed
reply; the router can only ADD a fixed safety reply. Deep path when a profile safety rule applies, a medicine/low-sugar/
complication/alcohol word appears, or the router flags it; a router flag alone is never the only reason to trust a message.

| | before (current supervisor prompt) | after (short JSON prompt) |
|---|---|---|
| personal (10) | 10 | 10 |
| general (8) | 8 | 8 (but all 8 also flagged ambiguous) |
| ambiguous (5) | 4 | 5 |
| emergency (3) / med change (2) | 3 / 2 | 3 / 2 |
| chat (1) / service (1) | 1 / 1 | 1 / 1 |
| total | 29/30 | 30/30 |

- Emergency F02, F03 and med-change F05 are NOT caught by the regex; the router caught them (3/3). F01, F04 by code.
- Before: A04 ("Is a can of soda a day bad?") was judged general with no escalation signal → the only failure.
- After: the `ambiguous` flag fired on all 8 clear general questions (Haiku: "profile overlaps"), so it does not separate
  ambiguous from general. The effect is that profile-relevant general questions go deep — safe, but it costs time. 30/30 is
  therefore weaker evidence than it looks; it also is one run, one proxy model, and the prompt was written knowing the set.
- Tokens/latency: per-call numbers are not available through sub-agents. Aggregate sub-agent totals for 30 items: before 94k
  tokens / 26 s, after 84k tokens / 40 s (includes sub-agent overhead). Router-only estimate: ~540 input + ~35 output tokens
  per message with the short prompt. No dollar figure (no metered API call was made).

## Planned, not implemented: two answers for ambiguous questions
When the router says ambiguous: answer first as a general (B) answer ("In general, ..."), then a personal (A) part ("For you,
...", from the profile and the safety rules). Needs a writer-prompt change and a live run to measure; blocked by the API key.
