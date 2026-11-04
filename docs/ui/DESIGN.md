# DESIGN.md — 식단·운동 코치 design system v1 (2026-11-04)

Source of truth for values: `web/ds.css` (tokens + components), `web/ds.js` (helpers). Pages add layout only.
Status: implemented and checked in a real browser (see "Checked"); the reference measurements are labelled **measured** or **assumed**.

## 1. Direction and references
Goal: a consumer chat app that older adults can use daily — warm, calm, large text — not a hospital form.
No reference URL was given, so three were chosen for what they teach, not to copy:

| Reference | Learned from it | Not taken |
|---|---|---|
| ChatGPT chat screen (generic style values only, **measured**: body 16/24 px, ink #0d0d0d on #fcfcfc, 8 px control radius, composer line height 26 px) | Flat assistant text without a card, user bubble on the right, one rounded composer at the bottom, almost no chrome | Neutral grey look (too cold for a health service), dense small type |
| Ada Health site (**measured**: Noto Sans 17/28 px, navy ink #293754, pill buttons radius 100 px, serif headings) | Friendly health tone, 17 px body, pill buttons | Serif headings (poor Korean pairing), marketing layout |
| KakaoTalk-style messenger (**assumed** from product knowledge, not measured) | Bubble shapes, big touch targets, date separators, a calm single accent | Yellow brand colour |

Chosen (revised 2026-11-04 after review): keep the look of the first published UI — cool grey background, **blue accent #1D4ED8**, white cards with thin borders — and
add the chat structure: user bubble, assistant answer in a white card with an avatar, evidence as small numbered chips that open a side panel / bottom sheet.
The first draft used a warm paper background and a green accent; it was dropped because it looked less polished than the published version.

## 2. Tokens (all in `ds.css`; light, with a dark variant)
- **Colour:** `--bg #F6F7F9`, `--surface #FFF`, `--ink #1D2430`, `--ink-2 #4B5565`, `--brand #1D4ED8` (contrast 6.7 on white), `--brand-soft #E3ECFF`,
  `--danger #B42318`, `--warn #B54708`, `--ok #067647`. Semantic use only: brand = actions and user bubble, danger = emergency, warn = caution.
- **Type:** system Korean stack (Apple SD Gothic Neo, Noto Sans KR, Malgun Gothic). Base **17 px** (user can set 15–26 px), line height 1.65,
  `word-break: keep-all` so Korean words do not split. Scale: 0.85 / 1 / 1.15 / 1.45 / 1.9 rem.
- **Space:** 4 px scale `--s1…--s8` (4, 8, 12, 16, 24, 32, 48, 72). **Radius:** 8 / 14 / 22 / pill. **Shadow:** two levels. **Touch target:** 48 px.
- **Breakpoints:** 900 px (sidebar becomes a drawer, evidence becomes a bottom sheet), 1000 / 560 px for the care-team KPI grid.
- **Motion:** 150 ms colour/transform only; typing dots; all disabled under `prefers-reduced-motion`.

## 3. Components (one design per role)
Button (`.btn` + `secondary | ghost | danger-btn`, `.icon-btn`) · Field (`.field`, `.input`, `.hint`, `.error`) · Card · Chip (toggle with `aria-pressed`) ·
Tag (alert kinds) · Avatar · Banner (`danger | info | warn`) · Dialog / bottom sheet · Toast · Table (care team) · Skeleton.
Chat-only: user bubble, assistant text block, evidence chips and `cite` number buttons, typing indicator, composer, date separator.
Rules: emergency is the only red surface; every control has a visible 3 px focus ring; no new colour or size outside the tokens.

## 4. Information architecture
- `/login` (log in / sign up in 3 steps: account → health profile → consent; in demo mode also “가상 사용자로 체험하기” cards) · `/` chat with sidebar (profile summary, records, settings, log out) ·
  `/admin/login` → `/admin` (overview, alerts, people, access log). Two separate sign-ins and roles.
- Always visible in chat: “응급 119” and an “의료진과 이야기하기” button. A banner repeats the 119 call on an emergency answer.
- Evidence: numbered buttons inside the answer + chips under it → panel with the supporting sentence, the paper excerpt (supporting sentences highlighted) and the PMC link.

## 5. Korean UX writing review (done)
- Chat and onboarding use the polite “해요체” (friendly, short); the care-team console uses short noun-style labels.
- Concrete wording instead of marketing: “식사나 운동에 대해 물어보세요”, “건강 답변은 보통 20초쯤 걸려요”, progress lines such as “논문을 읽고 있어요…”.
- Example questions contain no disease words (users do not type their condition): “무거운 운동을 계속해도 되나요?”.
- One term per concept: 근거 (evidence), 기록 (record), 의료진 (care team), 이용자 (user, console only).
- Errors say what to do and repeat the 119 hint: “죄송해요, 답변을 만들다가 문제가 생겼어요. 급한 증상이 있으면 기다리지 말고 119에 전화하세요.”
- Not changed: the answer text itself comes from the translation step (`coach/i18n.py`, 존댓말); its tone was not re-tuned because it cannot be tested while the OpenAI key is invalid.

## 5b. Korean / English
Switch at the top right of the sign-in pages and the chat (한국어 | EN); one preference (`coach_lang`) shared by the pages, switching reloads the page.
Korean is the source text in the HTML; `web/i18n.js` holds the English text (`tests/test_i18n.py` fails if a Korean string has no English entry).
In English mode the chat asks the server for `lang=en`: the safety-checked English answer is shown as is (no translation call).
Demo-history rows carry both versions (`meta.ko` / `meta.en`); the Korean text of the 198 demo messages and answers was written by Claude (sub-agents) and checked by
script for identical citation markers and numbers (`data/demo_translations_ko.json`, applied by `scripts/backfill_demo_citations.py`).
Live Korean answers still need the service model (OpenAI key) for the translation step. The care-team console is Korean only.

## 6. Checked / not checked
Checked (real Chrome via Playwright, throw-away database): axe-core WCAG 2 A/AA scan on login, chat (empty, evidence panel at 390 / 768 / 1280 px) and the care-team
screens = **0 violations**, no horizontal scroll; keyboard sign-in; emergency message end-to-end (code path, no LLM); screenshots in `docs/ui/screenshots/`
(`scripts/ui_screenshots.py`). Recorded answers in those screenshots are a past evaluation run drawn with the page renderer, in English — not live answers.
Not checked: live LLM answers and Korean translation quality (API key invalid), real phone devices, screen-reader listening, dark mode visually, the
care-team console on a phone.
